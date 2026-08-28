import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { applyCropThumb, closeMediaLightbox, hasImageCrop, kindIconSvg, openPreview, viewUrl } from "./thumbs.js";
import { captureNodeSize, restoreNodeSizeSoon } from "./nodeSize.js";
import { mountPromptEditor } from "./promptEditor.js";
import {
    installBuilderMediaNode,
    installBuilderMediaRuntime,
    isSocketMedia,
    labelMediaInput,
    mediaItemTitle,
    pruneTransportInputsFromNode,
    setOnVirtualLinksChanged,
    syncBuilderMediaList,
    syncLinksFromMediaOrder,
} from "./builderMedia.js";

const NODE_NAME = "H3StudioBuilder";
const MAX_MODELS = 12;
const MIN_NODE_WIDTH = 380;
const MIN_NODE_HEIGHT = 500;
const MIN_WIDGET_HEIGHT = 360;
const SPLIT_PROP = "h3_studio_builder_split";
const DEFAULT_SPLIT = 0.46;
const MIN_LIST_PX = 64;
const MIN_PLAN_PX = 88;
const MODE_AUTO_CHAIN = "auto_chain";
const MODE_MUSIC_VIDEO = "music_video";
const MUSIC_VIDEO_SONG_TIP = "Music Video uses the Builder song (drop a file or wire Lyrics Timer). Builder audio refs are unused.";
const COPY_PACK_LABEL = "Copy pack summary";
const COPY_PACK_TIP = "Copies duration, segments, loop, enabled labels, and the plan field.";
const MIN_REGION_SEC = 2;
const MIN_DURATION_SEC = 5;
const MAX_DURATION_SEC = 15;
const MAX_SEGMENTS = 999;
const SEGMENTS_SLIDER_MAX = 10;
const MIN_VIEW_SEC = 1;
const SERIAL_WIDGETS = ["state_json", "mode", "max_clip_duration", "segments", "loop", "song_file", "lyrics"];
const REGION_COLORS = [
    ["rgba(120,185,255,.28)", "#7ec8ff"],
    ["rgba(120,220,160,.28)", "#7ee0a8"],
    ["rgba(240,190,90,.28)", "#f0c05a"],
    ["rgba(200,140,255,.28)", "#c78cff"],
    ["rgba(255,140,140,.28)", "#ff8c8c"],
    ["rgba(140,220,220,.28)", "#8cdcdc"],
];

function targetNames(node) {
    return new Set([
        node?.type,
        node?.comfyClass,
        node?.constructor?.type,
        node?.constructor?.comfyClass,
        node?.constructor?.ComfyClass,
        node?.constructor?.nodeData?.name,
    ].filter(Boolean));
}

function isTarget(node) {
    return targetNames(node).has(NODE_NAME);
}

function isTargetDefinition(nodeType, nodeData) {
    return [
        nodeData?.name,
        nodeType?.type,
        nodeType?.comfyClass,
        nodeType?.ComfyClass,
        nodeType?.nodeData?.name,
    ].filter(Boolean).includes(NODE_NAME);
}

function findWidget(node, name) {
    return node?.widgets?.find((item) => item?.name === name);
}

function findInput(node, name) {
    return node.inputs?.find((slot) => slot?.name === name);
}

function songSocketLinked(node) {
    return slotLinked(findInput(node, "song"));
}

function isAudioFile(file) {
    const name = String(file?.name || "").toLowerCase();
    const type = String(file?.type || "");
    return type.startsWith("audio/") || /\.(mp3|wav|flac|ogg|m4a|aac|wma)$/.test(name);
}

function slotLinked(input) {
    if (!input) return false;
    if (input.link != null && input.link !== -1) return true;
    if (Array.isArray(input.links) && input.links.length) return true;
    return false;
}

function ensureMinSize(node) {
    const width = Array.isArray(node.size) && Number.isFinite(node.size[0]) ? node.size[0] : 0;
    const height = Array.isArray(node.size) && Number.isFinite(node.size[1]) ? node.size[1] : 0;
    if (width >= MIN_NODE_WIDTH && height >= MIN_NODE_HEIGHT) return;
    node.setSize?.([Math.max(width, MIN_NODE_WIDTH), Math.max(height, MIN_NODE_HEIGHT)]);
}

function refreshNodeLayout(node) {
    node._widgetSlotsDirty = true;
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

function builderDomWidget(node) {
    return findWidget(node, "h3_builder_list");
}

function builderSplitRatio(node) {
    const raw = Number(node?.properties?.[SPLIT_PROP]);
    if (Number.isFinite(raw) && raw > 0 && raw < 1) return raw;
    return DEFAULT_SPLIT;
}

function setBuilderSplitRatio(node, ratio) {
    node.properties ||= {};
    const next = Math.max(0.12, Math.min(0.88, Number(ratio) || DEFAULT_SPLIT));
    node.properties[SPLIT_PROP] = next;
    return next;
}

function applyBuilderSplit(node) {
    const ui = node.__h3BuilderUi;
    if (!ui?.list || !ui?.plan) return;
    const ratio = builderSplitRatio(node);
    ui.list.style.flex = `${ratio} 1 0`;
    ui.plan.style.flex = `${1 - ratio} 1 0`;
}

function bindBuilderSplit(node, handle) {
    if (!handle) return;
    handle.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        const split = node.__h3BuilderUi?.split;
        if (!split) return;
        handle.classList.add("is-dragging");
        const onMove = (moveEvent) => {
            const box = split.getBoundingClientRect();
            const usable = Math.max(1, box.height - handle.offsetHeight);
            const listPx = Math.max(MIN_LIST_PX, Math.min(usable - MIN_PLAN_PX, moveEvent.clientY - box.top));
            setBuilderSplitRatio(node, listPx / usable);
            applyBuilderSplit(node);
        };
        const onUp = () => {
            handle.classList.remove("is-dragging");
            document.removeEventListener("pointermove", onMove, true);
            document.removeEventListener("pointerup", onUp, true);
            document.removeEventListener("pointercancel", onUp, true);
        };
        document.addEventListener("pointermove", onMove, true);
        document.addEventListener("pointerup", onUp, true);
        document.addEventListener("pointercancel", onUp, true);
        onMove(event);
    });
}

function isMusicVideoMode(node) {
    const raw = String(findWidget(node, "mode")?.value || MODE_AUTO_CHAIN).toLowerCase();
    return raw.includes("music");
}

function usedClipLength(item, maxLen) {
    clipMediaRegion(item, maxLen, mediaRegionCount(item));
    return Number(item.length) || 0;
}

function mediaRegionCount(item, fallback = 1) {
    const fromItem = Array.isArray(item?.regions) ? item.regions.length : 0;
    const extra = Math.round(Number(item?.segments) || 0);
    return Math.max(1, Math.min(MAX_SEGMENTS, fromItem || extra || Math.round(Number(fallback) || 1)));
}

function clipOneRegion(region, source, cap) {
    const src = Math.max(0, Number(source) || 0);
    const limit = Math.max(MIN_REGION_SEC, Math.min(MAX_DURATION_SEC, Number(cap) || 10));
    if (src <= 0) return { start: 0, length: 0 };
    let length = Number(region?.length);
    if (!Number.isFinite(length) || length <= 0) length = Math.min(src, limit);
    length = Math.min(length, src, limit);
    if (src >= MIN_REGION_SEC) length = Math.max(MIN_REGION_SEC, length);
    else length = src;
    let start = Number(region?.start);
    if (!Number.isFinite(start) || start < 0) start = 0;
    if (start + length > src) start = Math.max(0, src - length);
    return { start, length };
}

function adjacentRegions(first, count, source, cap) {
    const n = Math.max(1, Math.min(MAX_SEGMENTS, Math.round(Number(count) || 1)));
    const src = Math.max(0, Number(source) || 0);
    const seed = clipOneRegion(first || { start: 0, length: 0 }, src, cap);
    if (n <= 1) return [seed];
    const length = seed.length;
    const total = length * n;
    let begin = seed.start;
    if (total <= src) begin = Math.max(0, Math.min(begin, src - total));
    else begin = 0;
    const out = [];
    for (let i = 0; i < n; i += 1) {
        out.push(clipOneRegion({ start: begin + i * length, length }, src, cap));
    }
    return out;
}

function clipMediaRegion(item, maxLen, segmentCount) {
    if (!item || (item.kind !== "video" && item.kind !== "audio")) return item;
    const source = Math.max(0, Number(item.duration) || 0);
    const cap = Math.max(MIN_REGION_SEC, Math.min(MAX_DURATION_SEC, Number(maxLen) || 10));
    const count = Math.max(1, Math.min(MAX_SEGMENTS, Math.round(Number(segmentCount) || mediaRegionCount(item, 1))));
    let regions = Array.isArray(item.regions)
        ? item.regions.map((entry) => clipOneRegion(entry, source, cap))
        : [];
    if (!regions.length) {
        regions = adjacentRegions({ start: item.start, length: item.length }, count, source, cap);
    } else if (regions.length < count) {
        const extra = adjacentRegions(regions[regions.length - 1], 2, source, cap)[1];
        while (regions.length < count) {
            const last = regions[regions.length - 1];
            regions.push(clipOneRegion({
                start: last.start + last.length,
                length: extra?.length || last.length,
            }, source, cap));
        }
    } else if (regions.length > count) {
        regions = regions.slice(0, count);
    }
    item.regions = regions;
    item.segments = count;
    item.start = regions[0]?.start || 0;
    item.length = regions[0]?.length || 0;
    return item;
}

function clampAllRegions(node) {
    const ui = node.__h3BuilderUi;
    if (!ui?.state?.media) return;
    const maxLen = builderDuration(node);
    const segs = builderSegments(node);
    for (const item of ui.state.media) clipMediaRegion(item, maxLen, segs);
}

function setBuilderDuration(node, value, clamp = true) {
    const widget = findWidget(node, "max_clip_duration");
    const next = Math.max(MIN_DURATION_SEC, Math.min(MAX_DURATION_SEC, Number(value) || 10));
    if (widget) {
        widget.value = next;
        widget.callback?.(next, node, widget);
    }
    if (clamp) clampAllRegions(node);
    return next;
}

function setBuilderSegments(node, value, clamp = true) {
    const widget = findWidget(node, "segments");
    const next = Math.max(1, Math.min(MAX_SEGMENTS, Math.round(Number(value) || 1)));
    if (widget) {
        widget.value = next;
        widget.callback?.(next, node, widget);
    }
    if (clamp) clampAllRegions(node);
    return next;
}

function builderDuration(node) {
    const raw = Number(findWidget(node, "max_clip_duration")?.value);
    return Number.isFinite(raw) ? raw : 10;
}

function builderSegments(node) {
    const raw = Number(findWidget(node, "segments")?.value);
    return Number.isFinite(raw) ? Math.round(raw) : 2;
}

function builderLoop(node) {
    return Boolean(findWidget(node, "loop")?.value);
}

function setWidgetOption(widget, key, value) {
    if (!widget) return;
    widget.options ||= {};
    if (value === undefined) delete widget.options[key];
    else widget.options[key] = value;
    if (widget._state?.options) {
        if (value === undefined) delete widget._state.options[key];
        else widget._state.options[key] = value;
    }
}

function setWidgetVisible(widget, visible) {
    if (!widget) return;
    widget.hidden = !visible;
    setWidgetOption(widget, "hidden", visible ? undefined : true);
    if (visible) {
        delete widget.computeSize;
        widget.computedHeight = undefined;
        if (widget.inputEl) widget.inputEl.style.display = "";
        if (widget.element) widget.element.style.display = "";
    } else {
        widget.computeSize = () => [0, -4];
        widget.computedHeight = 0;
        if (widget.inputEl) widget.inputEl.style.display = "none";
        if (widget.element) widget.element.style.display = "none";
    }
}

function setInputVisible(node, name, visible) {
    const input = node.inputs?.find((slot) => slot?.name === name && !String(slot?.type || "").includes("MODEL"));
    if (!input) return;
    input.hidden = !visible;
}

function lyricsSocketLinked(node) {
    return slotLinked(findInput(node, "lyrics"));
}

function keepDomVisibleWhenWired(widget) {
    if (!widget || widget.__h3KeepDomVisible) return;
    widget.__h3KeepDomVisible = true;
    widget.isVisible = function () {
        if (this.hidden) return false;
        return this.node?.isWidgetVisible?.(this) !== false;
    };
}

function hideSongFileWidget(node) {
    const widget = findWidget(node, "song_file");
    if (!widget) return;
    widget.serialize = true;
    setWidgetVisible(widget, false);
}

function ensureLyricsSocket(node) {
    const widget = findWidget(node, "lyrics");
    if (!widget) return;
    setWidgetOption(widget, "hideOnConnect", false);
    keepDomVisibleWhenWired(widget);
}

function songDropLabel(node) {
    if (songSocketLinked(node)) return "Using wired song";
    const name = String(findWidget(node, "song_file")?.value || "").trim();
    return name || "Drop song or click to upload";
}

function isVueNodesMode() {
    return Boolean(globalThis.LiteGraph?.vueNodesMode);
}

function applyNativeWidgetTheme(element) {
    if (!element?.style) return;
    const LiteGraph = globalThis.LiteGraph || {};
    const modern = isVueNodesMode();
    const widgetBg = LiteGraph.WIDGET_BGCOLOR || "#222";
    const widgetText = LiteGraph.WIDGET_TEXT_COLOR || "#ddd";
    element.classList?.toggle("h3-native-vue-nodes", modern);
    if (modern) {
        element.style.setProperty("--h3-native-widget-bg", "var(--component-node-widget-background, var(--secondary-background, #222))");
        element.style.setProperty("--h3-native-widget-text", "var(--component-node-foreground, var(--base-foreground, #ddd))");
        element.style.setProperty("--h3-native-widget-outline", "var(--component-node-widget-background-highlighted, var(--border-default, rgba(255, 255, 255, 0.18)))");
        element.style.setProperty("--h3-native-widget-focus", "var(--component-node-widget-background-highlighted, var(--border-default, rgba(255, 255, 255, 0.28)))");
        element.style.setProperty("--h3-native-widget-radius", "var(--radius-lg, 8px)");
        element.style.setProperty("--h3-native-widget-text-size", "var(--text-xs, 12px)");
        element.style.setProperty("--h3-native-widget-line-height", "var(--text-xs--line-height, 1.333)");
        return;
    }
    element.style.setProperty("--h3-native-widget-bg", `var(--comfy-input-bg, ${widgetBg})`);
    element.style.setProperty("--h3-native-widget-text", `var(--input-text, ${widgetText})`);
    element.style.setProperty("--h3-native-widget-outline", "var(--border-color, rgba(255, 255, 255, 0.18))");
    element.style.setProperty("--h3-native-widget-focus", "var(--border-color, rgba(255, 255, 255, 0.28))");
    element.style.setProperty("--h3-native-widget-radius", "0px");
    element.style.setProperty("--h3-native-widget-text-size", "12px");
    element.style.setProperty("--h3-native-widget-line-height", "1.3");
}

function ensureSongDropStyle() {
    if (document.getElementById("h3-builder-song-style")) return;
    const style = document.createElement("style");
    style.id = "h3-builder-song-style";
    style.textContent = `
.h3-builder-song-drop {
  display: flex; align-items: stretch; width: 100%; height: 100%; min-height: 24px;
  box-sizing: border-box; background: transparent;
}
.h3-builder-song-drop-face {
  flex: 1 1 auto; min-width: 0; display: grid; grid-template-columns: auto minmax(0, 1fr);
  align-items: center; gap: 8px; min-height: 24px; padding: 0; border: 0; background: transparent;
  color: var(--h3-native-widget-text, var(--component-node-foreground, var(--input-text, #ddd)));
  font: 500 var(--h3-native-widget-text-size, 12px)/var(--h3-native-widget-line-height, 1.3) Inter, system-ui, sans-serif;
  cursor: pointer; user-select: none;
}
.h3-builder-song-name { flex: 0 0 auto; opacity: .78; padding-left: 2px; }
.h3-builder-song-value {
  min-width: 0; height: 24px; display: flex; align-items: center; justify-content: flex-end;
  padding: 0 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  background: var(--h3-native-widget-bg, var(--component-node-widget-background, var(--comfy-input-bg, #353535)));
  border-radius: var(--h3-native-widget-radius, var(--radius-lg, 8px)); color: inherit;
}
.h3-builder-song-drop-face:hover .h3-builder-song-value {
  background: var(--h3-native-widget-outline, var(--component-node-widget-background-highlighted, rgba(255,255,255,.08)));
}
.h3-builder-song-drop-face.is-drag .h3-builder-song-value {
  box-shadow: 0 0 0 1px var(--h3-native-widget-focus, rgba(120,185,255,.7));
}
.h3-builder-song-drop-face.is-disabled { opacity: .55; cursor: default; pointer-events: none; }
`;
    document.head.appendChild(style);
}

function dropHitsElement(event, el) {
    if (!el || !event) return false;
    const x = Number(event.clientX);
    const y = Number(event.clientY);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
    const rect = el.getBoundingClientRect?.();
    if (!rect) return false;
    return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
}

function dropTargetZone(node, event) {
    const target = event?.target;
    if (target && node.__h3SongDrop?.root?.contains?.(target)) return "song";
    if (target && node.__h3BuilderUi?.list?.contains?.(target)) return "list";
    if (dropHitsElement(event, node.__h3SongDrop?.root)) return "song";
    if (dropHitsElement(event, node.__h3BuilderUi?.list)) return "list";
    return "";
}

function takeFileDrop(node) {
    const now = globalThis.performance?.now?.() ?? Date.now();
    if (node.__h3FileDropAt && now - node.__h3FileDropAt < 200) return false;
    node.__h3FileDropAt = now;
    return true;
}

function orderSongBeforeLyrics(node) {
    const widgets = node.widgets;
    if (!Array.isArray(widgets)) return;
    const song = node.__h3SongDrop?.widget || findWidget(node, "song");
    const lyrics = findWidget(node, "lyrics");
    if (!song || !lyrics || song.serialize !== false) return;
    const from = widgets.indexOf(song);
    const to = widgets.indexOf(lyrics);
    if (from < 0 || to < 0 || from === to - 1) return;
    widgets.splice(from, 1);
    widgets.splice(widgets.indexOf(lyrics), 0, song);
}

function syncSongDropWidget(node) {
    const drop = node.__h3SongDrop;
    if (!drop?.face || !drop?.label) return;
    const linked = songSocketLinked(node);
    drop.face.classList.toggle("is-disabled", linked);
    drop.label.textContent = songDropLabel(node);
    const widget = drop.widget;
    if (widget) widget.disabled = linked;
}

function ensureSongDropWidget(node) {
    if (node.__h3SongDrop?.widget && node.widgets?.includes(node.__h3SongDrop.widget)) {
        const existing = node.__h3SongDrop.widget;
        setWidgetOption(existing, "hideOnConnect", false);
        keepDomVisibleWhenWired(existing);
        syncSongDropWidget(node);
        return existing;
    }
    ensureSongDropStyle();
    const root = document.createElement("div");
    root.className = "h3-builder-song-drop";
    applyNativeWidgetTheme(root);
    root.innerHTML = `
      <input type="file" accept="audio/*,.mp3,.wav,.flac,.ogg,.m4a,.aac,.wma" hidden>
      <div class="h3-builder-song-drop-face" data-act="song-face">
        <span class="h3-builder-song-name">song</span>
        <span class="h3-builder-song-value" data-act="song-label"></span>
      </div>
    `;
    const fileInput = root.querySelector("input[type=file]");
    const face = root.querySelector("[data-act=song-face]");
    const label = root.querySelector("[data-act=song-label]");
    face.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (songSocketLinked(node)) return;
        fileInput.click();
    });
    fileInput.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        fileInput.value = "";
        if (!file) return;
        try {
            await setSongFromFile(node, file);
        } catch (exc) {
            window.alert(exc?.message || String(exc));
        }
    });
    face.addEventListener("dragenter", (event) => {
        if (!isFileDrag(event) || songSocketLinked(node)) return;
        event.preventDefault();
        face.classList.add("is-drag");
    });
    face.addEventListener("dragover", (event) => {
        if (!isFileDrag(event) || songSocketLinked(node)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        face.classList.add("is-drag");
    });
    face.addEventListener("dragleave", () => face.classList.remove("is-drag"));
    face.addEventListener("drop", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        face.classList.remove("is-drag");
        if (songSocketLinked(node) || !takeFileDrop(node)) return;
        const file = [...(event.dataTransfer?.files || [])].find(isAudioFile);
        if (!file) return;
        try {
            await setSongFromFile(node, file);
        } catch (exc) {
            window.alert(exc?.message || String(exc));
        }
    });
    const widget = node.addDOMWidget("song", "div", root, {
        serialize: false,
        hideOnConnect: false,
        getMinHeight: () => 28,
        getHeight: () => 28,
    });
    if (widget) {
        widget.serialize = false;
        setWidgetOption(widget, "hideOnConnect", false);
        keepDomVisibleWhenWired(widget);
        widget.computeSize = function () {
            if (this.hidden) return [0, -4];
            return [node.size?.[0] || 200, 28];
        };
    }
    const input = findInput(node, "song");
    if (input) {
        input.label = "song";
        if (!input.widget) input.widget = widget;
    }
    node.__h3SongDrop = { root, face, label, widget, fileInput };
    syncSongDropWidget(node);
    return widget;
}

function decodeWidgetsValues(values) {
    if (!Array.isArray(values) || !values.length) return null;
    const durationOf = (value) => {
        const n = Number(value);
        return Number.isFinite(n) && n >= MIN_DURATION_SEC ? n : NaN;
    };
    if (Number.isFinite(durationOf(values[2]))) {
        return {
            state_json: values[0],
            mode: values[1],
            max_clip_duration: values[2],
            segments: values[3],
            loop: values[4],
            song_file: values[5],
            lyrics: values[6],
        };
    }
    if (typeof values[2] === "string" && Number.isFinite(durationOf(values[6]))) {
        return {
            state_json: values[0],
            mode: values[1],
            song_file: values[2],
            lyrics: values[3],
            loop: values[4],
            segments: values[5],
            max_clip_duration: values[6],
        };
    }
    return null;
}

function applyNamedWidgetValues(node, values) {
    const named = decodeWidgetsValues(values);
    if (!named) return;
    for (const name of SERIAL_WIDGETS) {
        if (named[name] === undefined) continue;
        const widget = findWidget(node, name);
        if (widget) widget.value = named[name];
    }
}

function syncModeUi(node) {
    const music = isMusicVideoMode(node);
    const lyricsLinked = lyricsSocketLinked(node);
    ensureSongDropWidget(node);
    ensureLyricsSocket(node);
    hideSongFileWidget(node);
    setWidgetVisible(findWidget(node, "segments"), !music);
    setWidgetVisible(findWidget(node, "loop"), !music);
    const songWidget = node.__h3SongDrop?.widget || findWidget(node, "song");
    if (songWidget) {
        setWidgetOption(songWidget, "hideOnConnect", false);
        keepDomVisibleWhenWired(songWidget);
        setWidgetVisible(songWidget, music);
        if (music) {
            songWidget.computeSize = function () {
                return [node.size?.[0] || 200, 28];
            };
        }
    }
    orderSongBeforeLyrics(node);
    const lyricsWidget = findWidget(node, "lyrics");
    if (lyricsWidget) {
        setWidgetOption(lyricsWidget, "hideOnConnect", false);
        keepDomVisibleWhenWired(lyricsWidget);
        lyricsWidget.disabled = Boolean(music && lyricsLinked);
        if (lyricsWidget.inputEl) lyricsWidget.inputEl.disabled = Boolean(music && lyricsLinked);
        if (lyricsWidget.element) {
            lyricsWidget.element.style.pointerEvents = music && lyricsLinked ? "none" : "";
        }
    }
    setWidgetVisible(lyricsWidget, music);
    syncModeSlots(node);
    syncSongDropWidget(node);
    hideModeWidget(node);
    const ui = node.__h3BuilderUi;
    ui?.syncModeButtons?.();
    if (ui?.hint) {
        ui.hint.textContent = music
            ? "Drop a song on the song row. Drop image / video / audio on the list, or wire them to Media. Audio refs are unused in Music Video mode."
            : "Drop image / video / audio here, or wire them to Media. Drag a thumbnail or handle to reorder. Right-click a reference for details.";
    }
    ui?.render?.();
    refreshNodeLayout(node);
}

function visualNodeHeight(node) {
    const rendered = node?.renderingSize;
    const renderedH = Array.isArray(rendered) ? Number(rendered[1]) : 0;
    const body = Number(node?.bodyHeight);
    const sizeH = Array.isArray(node?.size) ? Number(node.size[1]) : 0;
    return Math.max(MIN_NODE_HEIGHT, renderedH || 0, body || 0, sizeH || 0);
}

function remainingBuilderHeight(node, dom) {
    const nodeHeight = visualNodeHeight(node);
    const y = Number(dom?.y ?? dom?.last_y);
    if (Number.isFinite(y) && y > 0 && y < nodeHeight) {
        return Math.max(MIN_WIDGET_HEIGHT, Math.floor(nodeHeight - y));
    }
    return MIN_WIDGET_HEIGHT;
}

function bindBuilderWidgetSize(widget) {
    if (!widget) return;
    widget.options ||= {};
    widget.options.getMinHeight = () => MIN_WIDGET_HEIGHT;
    widget.options.getHeight = () => "100%";
    delete widget.options.getMaxHeight;
    if (Object.hasOwn(widget, "computeSize")) delete widget.computeSize;
    widget.computeLayoutSize = function () {
        return { minHeight: MIN_WIDGET_HEIGHT, minWidth: 0 };
    };
}

function syncBuilderWidget(node, widget) {
    const dom = widget || builderDomWidget(node);
    const root = node.__h3BuilderUi?.root;
    if (!dom || !root) return;
    bindBuilderWidgetSize(dom);
    const fill = remainingBuilderHeight(node, dom);
    const current = Number(dom.computedHeight) || 0;
    if (fill > current) dom.computedHeight = fill;
    root.style.flex = "1 1 auto";
    root.style.width = "100%";
    root.style.minHeight = "0px";
    root.style.height = "100%";
    applyBuilderSplit(node);
}

function forEachGraphLink(graph, fn) {
    const links = graph?.links ?? graph?._links;
    if (!links) return;
    if (typeof links.forEach === "function" && !Array.isArray(links)) {
        links.forEach((link) => { if (link) fn(link); });
        return;
    }
    const list = Array.isArray(links) ? links : Object.values(links);
    for (const link of list) {
        if (link) fn(link);
    }
}

function moveInput(node, fromIndex, toIndex) {
    if (!Array.isArray(node.inputs)) return;
    if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;
    if (fromIndex >= node.inputs.length || toIndex > node.inputs.length) return;
    const [item] = node.inputs.splice(fromIndex, 1);
    node.inputs.splice(toIndex, 0, item);

    const remap = (slot) => {
        if (slot === fromIndex) return toIndex;
        if (fromIndex < toIndex && slot > fromIndex && slot <= toIndex) return slot - 1;
        if (toIndex < fromIndex && slot >= toIndex && slot < fromIndex) return slot + 1;
        return slot;
    };
    forEachGraphLink(node.graph, (link) => {
        if (link.target_id !== node.id) return;
        const next = remap(link.target_slot);
        if (next !== link.target_slot) link.target_slot = next;
    });
}

function ensureInputAt(node, name, type, desiredIndex) {
    let idx = node.inputs.findIndex((slot) => slot?.name === name);
    if (idx < 0) {
        node.addInput?.(name, type);
        idx = node.inputs.findIndex((slot) => slot?.name === name);
        if (idx < 0) idx = node.inputs.length - 1;
    }
    if (idx >= 0 && idx !== desiredIndex) {
        moveInput(node, idx, desiredIndex);
    }
}

function removeInputByName(node, name) {
    const idx = node.inputs.findIndex((slot) => slot?.name === name);
    if (idx < 0) return;
    if (typeof node.removeInput === "function") {
        node.removeInput(idx);
    } else {
        node.inputs.splice(idx, 1);
    }
}

function connectedModelSlots(node) {
    const slots = [];
    if (!Array.isArray(node.inputs)) return slots;
    for (let i = 1; i <= MAX_MODELS; i++) {
        const input = node.inputs.find((slot) => slot?.name === `model_${i}`);
        if (slotLinked(input)) slots.push(i);
    }
    return slots;
}

function syncModelInputs(node) {
    if (!Array.isArray(node.inputs)) return;
    if (node.inputs.findIndex((slot) => slot?.name === "model_1") < 0) return;

    let showCount = 1;
    for (let i = 1; i < MAX_MODELS; i++) {
        const input = node.inputs.find((slot) => slot?.name === `model_${i}`);
        if (slotLinked(input)) showCount = i + 1;
        else break;
    }

    for (let i = MAX_MODELS; i > showCount; i--) {
        const input = node.inputs.find((slot) => slot?.name === `model_${i}`);
        if (slotLinked(input)) continue;
        removeInputByName(node, `model_${i}`);
    }

    let mediaIdx = node.inputs.findIndex((slot) => slot?.name === "media");
    if (mediaIdx < 0) {
        node.addInput?.("media", "*");
        mediaIdx = node.inputs.findIndex((slot) => slot?.name === "media");
    }
    if (mediaIdx > 0) moveInput(node, mediaIdx, 0);
    labelMediaInput(node);
    const mediaAt = node.inputs.findIndex((slot) => slot?.name === "media");
    const modelBase = mediaAt >= 0 ? mediaAt + 1 : 0;
    for (let i = 1; i <= showCount; i++) {
        ensureInputAt(node, `model_${i}`, "MODEL", modelBase + (i - 1));
        const input = node.inputs.find((slot) => slot?.name === `model_${i}`);
        if (input) {
            input.hidden = false;
            input.label = `model_${i}`;
        }
    }
    refreshNodeLayout(node);
}

function lastPinnedInputIndex(node) {
    let last = node.inputs.findIndex((slot) => slot?.name === "media");
    for (let i = 1; i <= MAX_MODELS; i++) {
        const idx = node.inputs.findIndex((slot) => slot?.name === `model_${i}`);
        if (idx > last) last = idx;
    }
    return last;
}

function detachModeInput(node, name) {
    const widget = findWidget(node, name);
    if (widget) setWidgetOption(widget, "socketless", true);
    removeInputByName(node, name);
}

function attachModeInput(node, name, type, index) {
    const widget = findWidget(node, name);
    if (widget) setWidgetOption(widget, "socketless", undefined);
    ensureInputAt(node, name, type, index);
    const input = findInput(node, name);
    if (!input) return;
    input.hidden = false;
    input.type = type;
    input.label = name;
    if (widget && !input.widget) input.widget = widget;
}

function syncModeSlots(node) {
    if (!Array.isArray(node.inputs)) return;
    const music = isMusicVideoMode(node);
    for (const name of ["song_file", "state_json", "mode"]) detachModeInput(node, name);
    if (music) {
        detachModeInput(node, "segments");
        detachModeInput(node, "loop");
        let at = lastPinnedInputIndex(node) + 1;
        if (at < 0) at = 0;
        attachModeInput(node, "song", "AUDIO", at);
        attachModeInput(node, "lyrics", "STRING", at + 1);
        return;
    }
    detachModeInput(node, "song");
    detachModeInput(node, "lyrics");
    let at = lastPinnedInputIndex(node) + 1;
    if (at < 0) at = 0;
    attachModeInput(node, "segments", "INT", at);
    attachModeInput(node, "loop", "BOOLEAN", at + 1);
}

function defaultState() {
    return { media: [], models: [], include_skill: false, plan: "" };
}

function parseState(raw) {
    try {
        const data = JSON.parse(String(raw || "{}"));
        if (!data || typeof data !== "object") return defaultState();
        return {
            media: Array.isArray(data.media) ? data.media : [],
            models: Array.isArray(data.models) ? data.models : [],
            include_skill: Boolean(data.include_skill),
            plan: String(data.plan || ""),
        };
    } catch (_) {
        return defaultState();
    }
}

function fileName(path) {
    const text = String(path || "").replace(/\\/g, "/");
    return text.split("/").pop() || text;
}

function skillSlash(node) {
    return isMusicVideoMode(node) ? "/prompt-minimax-h3-music-video" : "/prompt-minimax-h3-infinite";
}

function formatDump(node, state, slots) {
    const music = isMusicVideoMode(node);
    const lines = [];
    if (state?.include_skill) lines.push(skillSlash(node));
    lines.push("H3 Studio Builder pack");
    lines.push(`duration: ${builderDuration(node).toFixed(2)}s`);
    if (!music) {
        lines.push(`segments: ${builderSegments(node)}`);
        if (builderLoop(node)) lines.push("loop: true");
    }
    let modelN = 0;
    for (const slot of slots) {
        const meta = state.models.find((item) => Number(item?.slot) === slot) || {};
        if (meta.enabled === false) continue;
        modelN += 1;
        const desc = String(meta.description || "").trim() || "(no description)";
        lines.push(`Model ${modelN}: ${desc}`);
    }
    let pic = 0;
    let vid = 0;
    let aud = 0;
    for (const item of state.media) {
        if (item?.enabled === false) continue;
        if (music && item.kind === "audio") continue;
        const desc = String(item.description || "").trim() || "(no description)";
        const dur = usedClipLength(item, builderDuration(node));
        if (item.kind === "image") {
            pic += 1;
            const extra = item.first_frame ? " (first frame)" : "";
            lines.push(`Picture ${pic}: ${desc}${extra}`);
        } else if (item.kind === "video") {
            vid += 1;
            const extra = item.has_soundtrack ? " (with soundtrack)" : "";
            lines.push(`Video ${vid}: ${dur.toFixed(1)}s ${desc}${extra}`);
        } else if (item.kind === "audio") {
            aud += 1;
            lines.push(`Audio ${aud}: ${dur.toFixed(1)}s ${desc}`);
        }
    }
    const plan = String(state?.plan || "").trim();
    if (plan) {
        lines.push("plan:");
        lines.push(plan);
    }
    return `${lines.join("\n")}\n`;
}

function hideStateWidget(node) {
    const widget = findWidget(node, "state_json");
    if (!widget) return;
    widget.serialize = true;
    setWidgetVisible(widget, false);
}

function hideModeWidget(node) {
    const widget = findWidget(node, "mode");
    if (!widget) return;
    widget.serialize = true;
    setWidgetVisible(widget, false);
}

function setMode(node, mode) {
    const widget = findWidget(node, "mode");
    const next = mode === MODE_MUSIC_VIDEO ? MODE_MUSIC_VIDEO : MODE_AUTO_CHAIN;
    const prev = widget?.value;
    if (widget && prev !== next) {
        widget.value = next;
        if (widget._state) widget._state.value = next;
        widget.callback?.(next, node, widget);
        node.onWidgetChanged?.("mode", next, prev, widget);
    }
    syncModeUi(node);
}

function persist(node, state) {
    const widget = findWidget(node, "state_json");
    if (widget) widget.value = JSON.stringify(state);
    node.widgets_values = SERIAL_WIDGETS.map((name) => findWidget(node, name)?.value);
}

async function uploadSongFile(file) {
    const body = new FormData();
    body.append("image", file);
    const response = await api.fetchApi("/upload/image", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload?.error || `upload failed (${response.status})`);
    }
    return payload;
}

async function setSongFromFile(node, file) {
    if (songSocketLinked(node)) return;
    const widget = findWidget(node, "song_file");
    if (!widget) return;
    const info = await uploadSongFile(file);
    const name = info.name || file.name;
    widget.value = name;
    widget.callback?.(name, node, widget);
    syncSongDropWidget(node);
    refreshNodeLayout(node);
}

setOnVirtualLinksChanged((node) => {
    const ui = node.__h3BuilderUi;
    if (!ui?.state) return;
    const changed = syncBuilderMediaList(node, ui.state);
    for (const item of ui.state.media) {
        if (!isSocketMedia(item)) continue;
        if (item.kind === "video" || item.kind === "audio") {
            clipMediaRegion(item, builderDuration(node), builderSegments(node));
        }
    }
    if (changed) persist(node, ui.state);
    ui.render?.();
    refreshNodeLayout(node);
});

async function uploadFile(file) {
    const body = new FormData();
    body.append("file", file, file.name);
    const response = await api.fetchApi("/h3_studio_builder/upload", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload?.error || `upload failed (${response.status})`);
    }
    return payload;
}

function formatByteCount(value) {
    const bytes = Math.max(0, Number(value) || 0);
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KiB", "MiB", "GiB", "TiB"];
    let amount = bytes;
    let unit = -1;
    do {
        amount /= 1024;
        unit += 1;
    } while (amount >= 1024 && unit < units.length - 1);
    return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unit]}`;
}

function propertyLines(properties, item) {
    const summary = [];
    const width = Number(properties?.width);
    const height = Number(properties?.height);
    if (width > 0 && height > 0) summary.push(`${width} × ${height}`);
    const format = String(properties?.format || "").trim();
    if (format) summary.push(format);
    const bytes = Number(properties?.size);
    if (Number.isFinite(bytes) && bytes >= 0) summary.push(formatByteCount(bytes));
    const duration = Number(properties?.duration ?? item?.duration);
    if (duration > 0) summary.push(`${duration.toFixed(2)}s`);
    const frames = Math.max(1, Number(properties?.frames) || 1);
    if (frames > 1) summary.push(`${frames} frames`);

    const lines = [];
    if (summary.length) lines.push(summary.join(" · "));
    const modified = Number(properties?.mtime_ms);
    if (modified > 0) lines.push(`Modified ${new Date(modified).toLocaleString()}`);
    const path = String(properties?.relative_path || item?.path || "").trim();
    if (path) lines.push(path);
    return lines;
}

function closeBuilderMenu() {
    const existing = document.querySelector(".h3-builder-menu");
    existing?.remove?.();
}

function closeBuilderLightbox() {
    closeMediaLightbox();
}

function closeBuilderEditor() {
    document.querySelector(".h3-builder-editor")?.remove?.();
}

function formatClock(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const m = Math.floor(total / 60);
    const rem = total - m * 60;
    return `${String(m).padStart(2, "0")}:${rem.toFixed(2).padStart(5, "0")}`;
}

function iconEye() {
    return `<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 3C2.8 3 .5 8 .5 8S2.8 13 8 13s7.5-5 7.5-5S13.2 3 8 3zm0 8.2A3.2 3.2 0 1 1 8 4.8a3.2 3.2 0 0 1 0 6.4z"/><circle fill="currentColor" cx="8" cy="8" r="1.6"/></svg>`;
}

function iconTrash() {
    return `<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M6.1 1.8h3.8l.5 1.1H14v1.3H2V2.9h3.6l.5-1.1zM3.5 5.4h9l-.7 8.4A1.5 1.5 0 0 1 10.3 15H5.7a1.5 1.5 0 0 1-1.5-1.2L3.5 5.4zm2.2 1.4v6.2h1.2V6.8H5.7zm3.4 0v6.2h1.2V6.8H9.1z"/></svg>`;
}

function downsamplePeaks(channel, bars) {
    const count = Math.max(1, bars | 0);
    const step = Math.max(1, Math.floor(channel.length / count));
    const peaks = new Array(count);
    for (let i = 0; i < count; i++) {
        let peak = 0;
        const start = i * step;
        const end = Math.min(channel.length, start + step);
        for (let j = start; j < end; j++) peak = Math.max(peak, Math.abs(channel[j]));
        peaks[i] = peak;
    }
    return peaks;
}

function paintWaveform(canvas, peaks, startFrac = 0, endFrac = 1) {
    if (!canvas || !peaks?.length) return;
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(180, 210, 255, 0.72)";
    const mid = height / 2;
    const a = Math.max(0, Math.min(1, Number(startFrac) || 0));
    const b = Math.max(a + 1e-6, Math.min(1, Number(endFrac) || 1));
    for (let x = 0; x < width; x++) {
        const at = a + (x / width) * (b - a);
        const peak = peaks[Math.min(peaks.length - 1, Math.floor(at * peaks.length))] || 0;
        const amp = Math.max(1, peak * (height * 0.46));
        ctx.fillRect(x, mid - amp, 1, amp * 2);
    }
}

async function loadAudioPeaks(url, canvas, alive) {
    try {
        const buf = await fetch(url).then((response) => {
            if (!response.ok) throw new Error("waveform fetch failed");
            return response.arrayBuffer();
        });
        if (!alive()) return;
        const actx = new (window.AudioContext || window.webkitAudioContext)();
        const decoded = await actx.decodeAudioData(buf.slice(0));
        actx.close();
        if (!alive()) return;
        const channel = decoded.getChannelData(0);
        const peaks = downsamplePeaks(channel, Math.min(2400, Math.max(400, Math.max(1, canvas.clientWidth) * 2)));
        paintWaveform(canvas, peaks);
        return peaks;
    } catch (_) {
        return null;
    }
}

function openMediaEditor(node, item, save) {
    closeBuilderEditor();
    closeBuilderLightbox();
    if (item.kind === "image") openCropEditor(node, item, save);
    else openRegionEditor(node, item, save);
}

function openCropEditor(node, item, save) {
    const overlay = document.createElement("div");
    overlay.className = "h3-builder-editor";
    overlay.innerHTML = `
      <div class="h3-builder-editor-panel">
        <div class="h3-builder-editor-head">
          <h3>Crop ${escapeAttr(fileName(item.path))}</h3>
          <button type="button" data-act="cancel">Cancel</button>
        </div>
        <div class="h3-builder-editor-stage">
          <img alt="">
          <div class="h3-crop-rect" hidden>
            <div class="h3-crop-handle nw" data-handle="nw"></div>
            <div class="h3-crop-handle ne" data-handle="ne"></div>
            <div class="h3-crop-handle sw" data-handle="sw"></div>
            <div class="h3-crop-handle se" data-handle="se"></div>
          </div>
        </div>
        <div class="h3-builder-editor-hint">Drag on the image to draw a crop. Leave empty to use the full image.</div>
        <div class="h3-builder-editor-actions">
          <button type="button" data-act="clear">Clear crop</button>
          <button type="button" data-act="cancel">Cancel</button>
          <button type="button" data-act="apply">Apply crop</button>
        </div>
      </div>
    `;
    const img = overlay.querySelector("img");
    const rectEl = overlay.querySelector(".h3-crop-rect");
    img.draggable = false;
    img.src = viewUrl(item.path);
    let crop = item.crop && Number(item.crop.w) > 0 && Number(item.crop.h) > 0
        ? { ...item.crop }
        : null;

    function hasCrop() {
        return Boolean(crop && crop.w > 0 && crop.h > 0);
    }
    function layout() {
        const width = img.clientWidth;
        const height = img.clientHeight;
        if (!width || !height) return;
        if (!hasCrop()) {
            rectEl.hidden = true;
            return;
        }
        rectEl.hidden = false;
        rectEl.style.left = `${crop.x * width}px`;
        rectEl.style.top = `${crop.y * height}px`;
        rectEl.style.width = `${crop.w * width}px`;
        rectEl.style.height = `${crop.h * height}px`;
    }

    img.addEventListener("load", layout);
    window.addEventListener("resize", layout);

    let drag = null;
    function beginDrag(event, handle, originCrop) {
        event.preventDefault();
        event.stopPropagation();
        const box = img.getBoundingClientRect();
        if (!box.width || !box.height) return;
        drag = {
            handle,
            startX: event.clientX,
            startY: event.clientY,
            crop: { ...originCrop },
            width: box.width,
            height: box.height,
        };
    }
    function onPointerMove(event) {
        if (!drag) return;
        const dx = (event.clientX - drag.startX) / drag.width;
        const dy = (event.clientY - drag.startY) / drag.height;
        let { x, y, w, h } = drag.crop;
        if (drag.handle === "draw") {
            const ox = drag.crop.x;
            const oy = drag.crop.y;
            const nx = Math.max(0, Math.min(1, ox + dx));
            const ny = Math.max(0, Math.min(1, oy + dy));
            x = Math.min(ox, nx);
            y = Math.min(oy, ny);
            w = Math.max(0.02, Math.abs(nx - ox));
            h = Math.max(0.02, Math.abs(ny - oy));
            if (x + w > 1) w = 1 - x;
            if (y + h > 1) h = 1 - y;
        } else if (drag.handle === "move") {
            x += dx;
            y += dy;
        } else {
            if (drag.handle.includes("w")) {
                x += dx;
                w -= dx;
            }
            if (drag.handle.includes("e")) w += dx;
            if (drag.handle.includes("n")) {
                y += dy;
                h -= dy;
            }
            if (drag.handle.includes("s")) h += dy;
        }
        if (w < 0.02) w = 0.02;
        if (h < 0.02) h = 0.02;
        if (x < 0) { if (drag.handle === "move") w = Math.min(w, 1); x = 0; }
        if (y < 0) { if (drag.handle === "move") h = Math.min(h, 1); y = 0; }
        if (x + w > 1) {
            if (drag.handle === "move") x = 1 - w;
            else w = 1 - x;
        }
        if (y + h > 1) {
            if (drag.handle === "move") y = 1 - h;
            else h = 1 - y;
        }
        crop = { x, y, w, h };
        layout();
    }
    function onPointerUp() { drag = null; }
    img.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        const box = img.getBoundingClientRect();
        const x = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
        const y = Math.max(0, Math.min(1, (event.clientY - box.top) / box.height));
        crop = { x, y, w: 0.02, h: 0.02 };
        layout();
        beginDrag(event, "draw", { ...crop });
    });
    rectEl.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || !hasCrop()) return;
        beginDrag(event, event.target.dataset.handle || "move", crop);
    });
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);

    function close() {
        window.removeEventListener("resize", layout);
        document.removeEventListener("pointermove", onPointerMove);
        document.removeEventListener("pointerup", onPointerUp);
        document.removeEventListener("keydown", onKey, true);
        overlay.remove();
    }
    const onKey = (event) => { if (event.key === "Escape") close(); };
    document.addEventListener("keydown", onKey, true);
    overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
    overlay.querySelectorAll("[data-act=cancel]").forEach((btn) => btn.addEventListener("click", close));
    overlay.querySelector("[data-act=clear]").addEventListener("click", () => {
        crop = null;
        layout();
    });
    overlay.querySelector("[data-act=apply]").addEventListener("click", () => {
        item.crop = hasCrop() ? { ...crop } : null;
        save();
        close();
    });
    document.body.appendChild(overlay);
    layout();
}

function openRegionEditor(node, item, save) {
    clipMediaRegion(item, builderDuration(node), builderSegments(node));
    const overlay = document.createElement("div");
    overlay.className = "h3-builder-editor";
    overlay.innerHTML = `
      <div class="h3-builder-editor-panel">
        <div class="h3-builder-editor-head">
          <h3>Trim ${escapeAttr(fileName(item.path))}</h3>
          <label>duration
            <input type="range" min="${MIN_DURATION_SEC}" max="${MAX_DURATION_SEC}" step="0.1" data-act="duration">
            <input type="number" min="${MIN_DURATION_SEC}" max="${MAX_DURATION_SEC}" step="0.1" data-act="duration-num">
          </label>
          <label>segments
            <input type="range" min="1" max="${SEGMENTS_SLIDER_MAX}" step="1" data-act="segments">
            <input type="number" min="1" max="${MAX_SEGMENTS}" step="1" data-act="segments-num">
          </label>
        </div>
        <div class="h3-builder-editor-stage"></div>
        <div class="h3-region-transport">
          <button type="button" data-act="play">Play selection</button>
        </div>
        <div class="h3-region-timeline">
          <canvas class="h3-region-wave"></canvas>
          <div class="h3-region-playhead"></div>
        </div>
        <div data-act="region-label" class="h3-builder-editor-hint"></div>
        <div class="h3-builder-editor-actions">
          <button type="button" data-act="cancel">Cancel</button>
          <button type="button" data-act="apply">Apply trim</button>
        </div>
      </div>
    `;
    const stage = overlay.querySelector(".h3-builder-editor-stage");
    const media = document.createElement(item.kind === "video" ? "video" : "audio");
    media.controls = true;
    media.preload = "auto";
    media.src = viewUrl(item.path);
    if (item.kind === "audio") {
        stage.classList.add("h3-builder-editor-stage-audio");
        media.style.width = "100%";
    }
    stage.appendChild(media);
    const timeline = overlay.querySelector(".h3-region-timeline");
    const wave = overlay.querySelector(".h3-region-wave");
    const playhead = overlay.querySelector(".h3-region-playhead");
    const durationInput = overlay.querySelector("[data-act=duration]");
    const durationNum = overlay.querySelector("[data-act=duration-num]");
    const segmentsInput = overlay.querySelector("[data-act=segments]");
    const segmentsNum = overlay.querySelector("[data-act=segments-num]");
    const regionLabel = overlay.querySelector("[data-act=region-label]");
    const playBtn = overlay.querySelector("[data-act=play]");
    const draft = {
        regions: (item.regions || []).map((entry) => ({ start: entry.start, length: entry.length })),
    };
    let active = 0;
    let spanEls = [];
    let wavePeaks = null;
    let closed = false;
    let drag = null;
    let viewStart = 0;
    let viewSpan = 0;

    function cap() {
        return Math.max(MIN_REGION_SEC, Math.min(MAX_DURATION_SEC, Number(durationInput.value) || 10));
    }
    function source() {
        return Math.max(0, Number(item.duration) || 0);
    }
    function currentSegments() {
        const raw = Number(segmentsNum.value);
        if (Number.isFinite(raw)) return Math.max(1, Math.min(MAX_SEGMENTS, Math.round(raw)));
        return Math.max(1, Math.min(MAX_SEGMENTS, Math.round(Number(segmentsInput.value) || 1)));
    }
    function setSegmentsFields(value) {
        const n = Math.max(1, Math.min(MAX_SEGMENTS, Math.round(Number(value) || 1)));
        segmentsInput.value = String(Math.min(SEGMENTS_SLIDER_MAX, n));
        segmentsNum.value = String(n);
        return n;
    }
    function viewWindow() {
        const src = source() || 1;
        const span = viewSpan > 0 ? Math.min(src, Math.max(MIN_VIEW_SEC, viewSpan)) : src;
        const start = Math.max(0, Math.min(Math.max(0, src - span), viewStart));
        return { start, span, end: start + span };
    }
    function clampView() {
        const src = source() || 1;
        if (viewSpan <= 0 || viewSpan >= src) {
            viewSpan = 0;
            viewStart = 0;
            return;
        }
        viewSpan = Math.max(MIN_VIEW_SEC, Math.min(src, viewSpan));
        viewStart = Math.max(0, Math.min(src - viewSpan, viewStart));
    }
    function timeToPct(t) {
        const win = viewWindow();
        return ((t - win.start) / win.span) * 100;
    }
    function clientXToTime(clientX) {
        const box = timeline.getBoundingClientRect();
        const win = viewWindow();
        return win.start + ((clientX - box.left) / Math.max(1, box.width)) * win.span;
    }
    function paintWave() {
        if (!wavePeaks) return;
        const src = source() || 1;
        const win = viewWindow();
        paintWaveform(wave, wavePeaks, win.start / src, win.end / src);
    }
    function fieldFocused(el) {
        return document.activeElement === el;
    }
    function activeRegion() {
        return draft.regions[Math.max(0, Math.min(active, draft.regions.length - 1))] || draft.regions[0];
    }
    function clampDraft() {
        const src = source();
        const limit = cap();
        const n = currentSegments();
        if (!draft.regions.length) {
            draft.regions = adjacentRegions({ start: item.start, length: item.length }, n, src, limit);
        } else if (draft.regions.length !== n) {
            draft.regions = adjacentRegions(draft.regions[0], n, src, limit);
        } else {
            draft.regions = draft.regions.map((entry) => clipOneRegion(entry, src, limit));
        }
        if (active >= draft.regions.length) active = draft.regions.length - 1;
    }
    function syncSpans() {
        while (spanEls.length > draft.regions.length) spanEls.pop().remove();
        while (spanEls.length < draft.regions.length) {
            const index = spanEls.length;
            const el = document.createElement("div");
            el.className = "h3-region-span";
            const mark = document.createElement("span");
            mark.className = "h3-region-index";
            const left = document.createElement("div");
            left.className = "h3-region-edge left";
            left.dataset.edge = "start";
            const right = document.createElement("div");
            right.className = "h3-region-edge right";
            right.dataset.edge = "end";
            el.append(left, mark, right);
            el.addEventListener("pointerdown", (event) => {
                active = Number(el.dataset.index) || 0;
                beginRegionDrag(event, event.target.dataset.edge || "move", event.shiftKey);
                paint();
            });
            timeline.appendChild(el);
            spanEls.push(el);
        }
        spanEls.forEach((el, index) => {
            el.dataset.index = String(index);
            el.querySelector(".h3-region-index").textContent = String(index + 1);
            const color = REGION_COLORS[index % REGION_COLORS.length];
            el.style.background = color[0];
            el.style.borderColor = color[1];
        });
    }
    function paint() {
        clampDraft();
        clampView();
        syncSpans();
        spanEls.forEach((el, index) => {
            const region = draft.regions[index];
            el.style.left = `${timeToPct(region.start)}%`;
            el.style.width = `${(region.length / viewWindow().span) * 100}%`;
            el.classList.toggle("is-active", index === active);
        });
        if (!fieldFocused(durationNum)) {
            durationNum.value = Number(durationInput.value).toFixed(1);
        }
        if (!fieldFocused(segmentsNum)) {
            setSegmentsFields(currentSegments());
        }
        regionLabel.textContent = draft.regions.map((region, index) => (
            `${index + 1}: ${formatClock(region.start)}–${formatClock(region.start + region.length)}`
        )).join("   ");
        updatePlayhead();
        paintWave();
    }
    function updatePlayhead() {
        const win = viewWindow();
        const region = activeRegion();
        const t = Number.isFinite(media.currentTime) ? media.currentTime : region?.start || 0;
        if (t < win.start || t > win.end) {
            playhead.hidden = true;
            return;
        }
        playhead.hidden = false;
        playhead.style.left = `${timeToPct(t)}%`;
    }
    function inSelection(time) {
        const region = activeRegion();
        if (!region) return false;
        return time >= region.start - 0.05 && time < region.start + region.length;
    }
    media.addEventListener("loadedmetadata", () => {
        if (!item.duration && Number.isFinite(media.duration) && media.duration > 0) {
            item.duration = media.duration;
        }
        paint();
    });
    media.addEventListener("play", () => {
        const region = activeRegion();
        if (region && !inSelection(media.currentTime)) {
            try { media.currentTime = region.start; } catch (_) {}
        }
        playBtn.textContent = "Pause";
    });
    media.addEventListener("pause", () => { playBtn.textContent = "Play selection"; });
    media.addEventListener("timeupdate", () => {
        const region = activeRegion();
        if (!media.paused && region && !inSelection(media.currentTime)) {
            try { media.currentTime = region.start; } catch (_) {}
        }
        updatePlayhead();
    });
    playBtn.addEventListener("click", () => {
        const region = activeRegion();
        if (media.paused) {
            if (region) try { media.currentTime = region.start; } catch (_) {}
            void media.play().catch(() => {});
        } else {
            media.pause();
        }
    });
    durationInput.value = String(builderDuration(node));
    setSegmentsFields(builderSegments(node));
    durationNum.value = Number(durationInput.value).toFixed(1);
    function applyDurationNum(clamp) {
        const raw = Number(durationNum.value);
        if (!Number.isFinite(raw)) {
            if (clamp) durationNum.value = Number(durationInput.value).toFixed(1);
            return;
        }
        if (!clamp && (raw < MIN_DURATION_SEC || raw > MAX_DURATION_SEC)) return;
        durationInput.value = String(Math.max(MIN_DURATION_SEC, Math.min(MAX_DURATION_SEC, raw)));
        if (clamp) durationNum.value = Number(durationInput.value).toFixed(1);
        paint();
    }
    function applySegmentsNum(clamp) {
        const raw = Number(segmentsNum.value);
        if (!Number.isFinite(raw)) {
            if (clamp) setSegmentsFields(currentSegments());
            return;
        }
        if (!clamp && (raw < 1 || raw > MAX_SEGMENTS)) return;
        const n = setSegmentsFields(raw);
        draft.regions = adjacentRegions(draft.regions[0] || { start: item.start, length: item.length }, n, source(), cap());
        if (active >= n) active = n - 1;
        paint();
    }
    durationInput.addEventListener("input", paint);
    durationNum.addEventListener("input", () => applyDurationNum(false));
    durationNum.addEventListener("change", () => applyDurationNum(true));
    segmentsInput.addEventListener("input", () => {
        const n = setSegmentsFields(segmentsInput.value);
        draft.regions = adjacentRegions(draft.regions[0] || { start: item.start, length: item.length }, n, source(), cap());
        if (active >= n) active = n - 1;
        paint();
    });
    segmentsNum.addEventListener("input", () => applySegmentsNum(false));
    segmentsNum.addEventListener("change", () => applySegmentsNum(true));

    function beginRegionDrag(event, edge, shift) {
        event.preventDefault();
        event.stopPropagation();
        const region = activeRegion();
        if (!region) return;
        drag = {
            edge: shift && (!edge || edge === "move") ? "move-all" : (edge || "move"),
            startX: event.clientX,
            start: region.start,
            length: region.length,
            snapshot: draft.regions.map((entry) => ({ start: entry.start, length: entry.length })),
            width: timeline.clientWidth || 1,
            viewSpan: viewWindow().span,
        };
    }
    function onPointerMove(event) {
        if (!drag) return;
        const src = source() || 1;
        let dt = ((event.clientX - drag.startX) / drag.width) * drag.viewSpan;
        if (drag.edge === "move-all") {
            let minStart = Infinity;
            let maxEnd = -Infinity;
            for (const entry of drag.snapshot) {
                minStart = Math.min(minStart, entry.start);
                maxEnd = Math.max(maxEnd, entry.start + entry.length);
            }
            if (minStart + dt < 0) dt = -minStart;
            if (maxEnd + dt > src) dt = src - maxEnd;
            draft.regions = drag.snapshot.map((entry) => ({ start: entry.start + dt, length: entry.length }));
        } else if (drag.edge === "move") {
            draft.regions[active] = clipOneRegion({ start: drag.start + dt, length: drag.length }, src, cap());
        } else if (drag.edge === "start") {
            const end = drag.start + drag.length;
            draft.regions[active] = clipOneRegion({
                start: drag.start + dt,
                length: end - (drag.start + dt),
            }, src, cap());
        } else {
            draft.regions[active] = clipOneRegion({ start: drag.start, length: drag.length + dt }, src, cap());
        }
        paint();
    }
    function onPointerUp() { drag = null; }
    timeline.addEventListener("pointerdown", (event) => {
        if (event.target.closest(".h3-region-span")) return;
        const src = source() || 1;
        const t = clientXToTime(event.clientX);
        const region = activeRegion();
        if (!region) return;
        if (event.shiftKey) {
            const dt = t - (region.start + region.length / 2);
            beginRegionDrag(event, "move", true);
            drag.startX = event.clientX - (dt / drag.viewSpan) * drag.width;
            onPointerMove(event);
            return;
        }
        draft.regions[active] = clipOneRegion({
            start: t - region.length / 2,
            length: region.length,
        }, src, cap());
        paint();
        beginRegionDrag(event, "move", false);
        drag.start = draft.regions[active].start;
        drag.length = draft.regions[active].length;
        drag.snapshot = draft.regions.map((entry) => ({ start: entry.start, length: entry.length }));
    });
    timeline.addEventListener("wheel", (event) => {
        event.preventDefault();
        const src = source() || 1;
        const win = viewWindow();
        if (event.shiftKey) {
            const pan = (event.deltaY || event.deltaX) / Math.max(1, timeline.clientWidth) * win.span;
            viewStart = win.start + pan;
            viewSpan = win.span;
            clampView();
            paint();
            return;
        }
        const t = clientXToTime(event.clientX);
        const factor = event.deltaY < 0 ? 0.85 : 1 / 0.85;
        let nextSpan = win.span * factor;
        if (nextSpan >= src * 0.98) {
            viewSpan = 0;
            viewStart = 0;
        } else {
            nextSpan = Math.max(MIN_VIEW_SEC, Math.min(src, nextSpan));
            const frac = (t - win.start) / win.span;
            viewSpan = nextSpan;
            viewStart = t - frac * nextSpan;
            clampView();
        }
        paint();
    }, { passive: false });
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);

    function close() {
        closed = true;
        media.pause();
        window.removeEventListener("resize", onResize);
        document.removeEventListener("pointermove", onPointerMove);
        document.removeEventListener("pointerup", onPointerUp);
        document.removeEventListener("keydown", onKey, true);
        overlay.remove();
    }
    const onKey = (event) => { if (event.key === "Escape") close(); };
    function onResize() {
        paint();
    }
    window.addEventListener("resize", onResize);
    document.addEventListener("keydown", onKey, true);
    overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
    overlay.querySelector("[data-act=cancel]").addEventListener("click", close);
    overlay.querySelector("[data-act=apply]").addEventListener("click", () => {
        clampDraft();
        item.regions = draft.regions.map((entry) => ({ start: entry.start, length: entry.length }));
        item.segments = item.regions.length;
        item.start = item.regions[0]?.start || 0;
        item.length = item.regions[0]?.length || 0;
        setBuilderDuration(node, durationInput.value, false);
        setBuilderSegments(node, currentSegments(), true);
        save();
        close();
    });
    document.body.appendChild(overlay);
    paint();
    void loadAudioPeaks(viewUrl(item.path), wave, () => !closed).then((peaks) => {
        wavePeaks = peaks;
        if (peaks) paint();
    });
}

function previewLabel(kind) {
    if (kind === "video") return "Open video preview";
    if (kind === "audio") return "Open audio preview";
    return "Open image preview";
}

function copyPathLabel(kind) {
    if (kind === "video") return "Copy video path";
    if (kind === "audio") return "Copy audio path";
    return "Copy image path";
}

function copyFileLabel(kind) {
    if (kind === "video") return "Copy video file";
    if (kind === "audio") return "Copy audio file";
    return "Copy image file";
}

function thumbMarkup(item) {
    if (item.kind === "image" && item.path) {
        const src = escapeAttr(viewUrl(item.path));
        return `<div class="h3-builder-thumb h3-builder-drag" draggable="true" title="Drag to reorder"><img src="${src}" alt="" draggable="false"></div>`;
    }
    return `<div class="h3-builder-icon h3-builder-drag is-${item.kind}" draggable="true" title="Drag to reorder">${kindIconSvg(item.kind)}</div>`;
}

async function imageBlobForClipboard(blob) {
    if (blob.type === "image/png") return blob;
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    return await new Promise((resolve, reject) => {
        canvas.toBlob((out) => (out ? resolve(out) : reject(new Error("Could not encode PNG."))), "image/png");
    });
}

async function copyMediaFile(item) {
    const response = await fetch(viewUrl(item.path));
    if (!response.ok) throw new Error("Could not read the file.");
    const blob = await response.blob();
    if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
        throw new Error("This browser cannot copy files to the clipboard.");
    }
    let payload = blob;
    let mime = blob.type;
    if (item.kind === "image") {
        payload = await imageBlobForClipboard(blob);
        mime = payload.type || "image/png";
    } else if (!mime) {
        mime = item.kind === "video" ? "video/mp4" : "audio/wav";
        payload = new Blob([blob], { type: mime });
    }
    try {
        await navigator.clipboard.write([new ClipboardItem({ [mime]: payload })]);
    } catch (_) {
        throw new Error(`Could not copy this ${item.kind} file. Use ${copyPathLabel(item.kind)} instead.`);
    }
}

async function copyText(text) {
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }
    window.prompt("Copy", text);
}

function showMediaMenu(node, item, index, clientX, clientY) {
    closeBuilderMenu();
    const menu = document.createElement("div");
    menu.className = "h3-builder-menu";
    menu.setAttribute("role", "menu");
    menu.addEventListener("contextmenu", (event) => event.preventDefault());

    const title = document.createElement("div");
    title.className = "h3-builder-menu-title";
    title.textContent = item.path ? fileName(item.path) : mediaItemTitle(item);
    const properties = document.createElement("div");
    properties.className = "h3-builder-menu-properties";
    properties.textContent = "Loading properties…";
    menu.append(title, properties);

    const addSeparator = () => {
        const separator = document.createElement("div");
        separator.className = "h3-builder-menu-separator";
        separator.setAttribute("role", "separator");
        menu.appendChild(separator);
    };
    const addAction = (label, handler, { danger = false } = {}) => {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("role", "menuitem");
        button.textContent = label;
        if (danger) button.classList.add("h3-builder-danger");
        button.addEventListener("click", async () => {
            try {
                await handler();
            } catch (error) {
                window.alert(error?.message || "The reference action failed.");
            } finally {
                closeBuilderMenu();
            }
        });
        menu.appendChild(button);
        return button;
    };

    addSeparator();
    let openButton = null;
    if (item.path) {
        openButton = addAction(previewLabel(item.kind), () => openPreview(item));
        addAction(item.kind === "image" ? "Crop image" : `Trim ${item.kind}`, () => {
            openMediaEditor(node, item, () => node.__h3BuilderUi?.save?.());
        });
        addAction(copyFileLabel(item.kind), () => copyMediaFile(item));
        addAction(copyPathLabel(item.kind), async () => {
            const path = String(item.path || "").replace(/\\/g, "/");
            if (!path) throw new Error("Path is unavailable.");
            await copyText(path);
        });
        addSeparator();
    }
    addAction("Clear reference", () => {
        const ui = node.__h3BuilderUi;
        if (!ui) return;
        ui.state.media.splice(index, 1);
        ui.save();
    }, { danger: true });

    document.body.appendChild(menu);
    const x = Math.max(8, Number(clientX) || 8);
    const y = Math.max(8, Number(clientY) || 8);
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    const rect = menu.getBoundingClientRect();
    if (rect.right > innerWidth - 8) menu.style.left = `${Math.max(8, innerWidth - rect.width - 8)}px`;
    if (rect.bottom > innerHeight - 8) menu.style.top = `${Math.max(8, innerHeight - rect.height - 8)}px`;

    const pointerdown = (event) => {
        if (!menu.contains(event.target)) {
            document.removeEventListener("pointerdown", pointerdown, true);
            document.removeEventListener("keydown", keydown, true);
            closeBuilderMenu();
        }
    };
    const keydown = (event) => {
        if (event.key !== "Escape") return;
        document.removeEventListener("pointerdown", pointerdown, true);
        document.removeEventListener("keydown", keydown, true);
        closeBuilderMenu();
    };
    document.addEventListener("pointerdown", pointerdown, true);
    document.addEventListener("keydown", keydown, true);
    (openButton || menu.querySelector("button"))?.focus({ preventScroll: true });

    if (!item.path) {
        properties.textContent = mediaItemTitle(item);
        return;
    }

    const params = new URLSearchParams({ path: String(item.path || "") });
    void api.fetchApi(`/h3_studio_builder/properties?${params.toString()}`).then(async (response) => {
        if (!document.body.contains(menu)) return;
        const payload = await response.json();
        const lines = response.ok
            ? propertyLines(payload, item)
            : [payload?.error || "Properties unavailable"];
        properties.replaceChildren(...(lines.length ? lines : ["Properties unavailable"]).map((line) => {
            const row = document.createElement("div");
            row.textContent = line;
            return row;
        }));
        const nextRect = menu.getBoundingClientRect();
        if (nextRect.bottom > innerHeight - 8) {
            menu.style.top = `${Math.max(8, innerHeight - nextRect.height - 8)}px`;
        }
    }).catch(() => {
        if (!document.body.contains(menu)) return;
        properties.textContent = "Properties unavailable";
    });
}

function unusedTitle(kind) {
    if (kind === "image") return "Picture (unused)";
    if (kind === "video") return "Video (unused)";
    if (kind === "audio") return "Audio (unused)";
    return "Model (unused)";
}

function attachPlanEditor(node) {
    const ui = node.__h3BuilderUi;
    const host = ui?.root?.querySelector("[data-act=plan]");
    if (!ui || !host) return;
    mountPromptEditor(node, host, {
        getValue: () => String(ui.state.plan || ""),
        setValue: (text) => {
            ui.state.plan = String(text || "");
            persist(node, ui.state);
        },
        inventoryNode: node,
        label: "plan",
        placeholder: "Story / visual plan. Copied into the pack summary for the prompt skills.",
    });
}

function ensureUi(node) {
    if (node.__h3BuilderUi) return node.__h3BuilderUi;
    hideStateWidget(node);
    hideModeWidget(node);
    const root = document.createElement("div");
    root.className = "h3-builder";
    root.innerHTML = `
<style>
.h3-builder {
  --comfy-widget-min-height: ${MIN_WIDGET_HEIGHT}px;
  --comfy-widget-height: 100%;
  display: flex; flex-direction: column; gap: 6px;
  flex: 1 1 auto; height: 100%; min-height: 0; min-width: 280px;
  overflow: hidden; box-sizing: border-box;
  color: #ddd; font: 12px/1.3 sans-serif;
}
.h3-builder-list {
  min-height: ${MIN_LIST_PX}px; min-width: 0; overflow: auto; flex: 1 1 0;
  border: 1px dashed #555; padding: 6px; background: #1b1b1b;
  display: flex; flex-direction: column; gap: 4px;
}
.h3-builder-list.h3-builder-drop-target {
  outline: 2px dashed rgba(120, 185, 255, 0.95); outline-offset: -4px;
  background: rgba(80, 145, 225, 0.14); border-color: rgba(120, 185, 255, 0.95);
}
.h3-builder-row {
  display: grid; grid-template-columns: 18px 16px 36px minmax(0, 1fr);
  gap: 6px; align-items: center; background: #2a2a2a; padding: 4px;
}
.h3-builder-row img, .h3-builder-icon {
  width: 36px; height: 36px; object-fit: cover; background: #111;
  display: flex; align-items: center; justify-content: center; color: #e8e8e8;
}
.h3-builder-icon svg { width: 18px; height: 18px; display: block; overflow: hidden; }
.h3-builder-icon.is-video { background: linear-gradient(135deg, #1557b8, #49b6ff); color: #fff; }
.h3-builder-icon.is-audio { background: #2a5038; color: #d8f5de; }
.h3-builder-icon.is-image { background: #4a3a20; color: #f5e6c8; }
.h3-builder-icon.is-model { background: #3a2a4a; color: #eddff8; }
.h3-builder-thumb {
  width: 36px; height: 36px; overflow: hidden; position: relative; background: #111; flex: 0 0 auto;
  cursor: grab;
}
.h3-builder-row .h3-builder-thumb img {
  position: absolute; left: 0; top: 0; width: 100%; height: 100%;
  object-fit: cover; max-width: none; max-height: none; pointer-events: none;
}
.h3-builder-row:not(.h3-builder-fixed) .h3-builder-icon.h3-builder-drag { cursor: grab; }
.h3-builder-thumb:active, .h3-builder-icon.h3-builder-drag:active { cursor: grabbing; }
.h3-builder-fields { min-width: 0; }
.h3-builder-title { display: flex; align-items: center; gap: 4px; min-width: 0; }
.h3-builder-title > span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h3-builder-fields input[type=text], .h3-builder-row input[type=text] {
  width: 100%; box-sizing: border-box; min-width: 0;
}
.h3-builder-row-actions { display: flex; gap: 3px; flex: 0 0 auto; align-items: center; }
.h3-builder-first-frame {
  display: inline-flex; align-items: center; gap: 4px; flex: 0 0 auto; margin: 0 4px 0 0;
  color: #bbb; font: 11px/1 system-ui, sans-serif; cursor: pointer; user-select: none; white-space: nowrap;
}
.h3-builder-first-frame input {
  margin: 0; width: 14px; height: 14px; cursor: pointer; accent-color: #7ec8ff;
}
.h3-builder-first-frame:has(input:checked) { color: #cfe; }
.h3-builder-first-frame:has(input:disabled) { cursor: not-allowed; opacity: 0.45; }
.h3-builder-icon-btn {
  flex: 0 0 auto; width: 22px; height: 22px; padding: 0; line-height: 20px;
  background: #333; color: #eee; border: 1px solid #555; cursor: pointer; font-size: 12px;
  display: inline-flex; align-items: center; justify-content: center;
}
.h3-builder-icon-btn svg { width: 13px; height: 13px; display: block; }
.h3-builder-icon-btn:hover { background: #444; }
.h3-builder-icon-btn.h3-builder-danger { color: #f4a; }
.h3-builder-editor {
  position: fixed; inset: 0; z-index: 100010; display: flex; align-items: center;
  justify-content: center; padding: 24px; background: rgba(0,0,0,.72);
}
.h3-builder-editor-panel {
  width: min(920px, calc(100vw - 32px)); max-height: calc(100vh - 32px);
  overflow: auto; background: #202124; color: #f0f0f0; border: 1px solid rgba(255,255,255,.18);
  border-radius: 10px; padding: 14px; box-shadow: 0 18px 50px rgba(0,0,0,.5);
  font: 12px/1.35 system-ui, sans-serif;
}
.h3-builder-editor-head { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.h3-builder-editor-head h3 { margin: 0; font-size: 14px; flex: 1; }
.h3-builder-editor-head label { display: flex; align-items: center; gap: 6px; color: #ccc; }
.h3-builder-editor-head input[type=range] { width: 120px; }
.h3-builder-editor-head input[type=number] {
  width: 4.2em; background: #191919; color: #eee; border: 1px solid #555;
  border-radius: 4px; padding: 2px 4px;
}
.h3-builder-editor-stage { position: relative; display: inline-block; max-width: 100%; }
.h3-builder-editor-stage img { cursor: crosshair; }
.h3-builder-editor-stage img, .h3-builder-editor-stage video {
  display: block; max-width: min(860px, 88vw); max-height: 62vh; background: #111;
}
.h3-builder-editor-stage-audio { display: block; width: 100%; }
.h3-builder-editor-stage audio { width: 100%; display: block; }
.h3-builder-editor-hint { margin-top: 6px; color: #bbb; }
.h3-region-transport { margin: 8px 0 0; }
.h3-region-transport button { background: #333; color: #eee; border: 1px solid #555; padding: 5px 10px; cursor: pointer; }
.h3-crop-rect {
  position: absolute; border: 2px solid #7ec8ff; background: rgba(120,185,255,.16); box-sizing: border-box; cursor: move;
}
.h3-crop-rect[hidden] { display: none !important; }
.h3-crop-handle {
  position: absolute; width: 10px; height: 10px; background: #7ec8ff; border: 1px solid #123;
}
.h3-crop-handle.nw { left: -5px; top: -5px; cursor: nwse-resize; }
.h3-crop-handle.ne { right: -5px; top: -5px; cursor: nesw-resize; }
.h3-crop-handle.sw { left: -5px; bottom: -5px; cursor: nesw-resize; }
.h3-crop-handle.se { right: -5px; bottom: -5px; cursor: nwse-resize; }
.h3-region-timeline {
  position: relative; height: 72px; margin-top: 10px; background: #111; border: 1px solid #444; border-radius: 6px;
  user-select: none; overflow: hidden;
}
.h3-region-wave { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.h3-region-playhead {
  position: absolute; top: 0; bottom: 0; width: 1px; background: #fff; pointer-events: none; z-index: 2;
}
.h3-region-playhead[hidden] { display: none !important; }
.h3-region-span {
  position: absolute; top: 4px; bottom: 4px; background: rgba(120,185,255,.28);
  border: 1px solid #7ec8ff; border-radius: 4px; cursor: grab; z-index: 1;
  box-sizing: border-box;
}
.h3-region-span.is-active { z-index: 3; box-shadow: inset 0 0 0 1px rgba(255,255,255,.35); }
.h3-region-span:active { cursor: grabbing; }
.h3-region-index {
  position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  pointer-events: none; font: 700 11px/1 system-ui, sans-serif; color: #fff;
  text-shadow: 0 1px 2px rgba(0,0,0,.7);
}
.h3-region-edge {
  position: absolute; top: 0; bottom: 0; width: 8px; background: #7ec8ff; cursor: ew-resize;
}
.h3-region-edge.left { left: 0; border-radius: 3px 0 0 3px; }
.h3-region-edge.right { right: 0; border-radius: 0 3px 3px 0; }
.h3-builder-editor-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.h3-builder-editor-actions button { background: #333; color: #eee; border: 1px solid #555; padding: 6px 12px; cursor: pointer; }
.h3-builder-row.drag { opacity: 0.6; }
.h3-builder-row.h3-builder-audio-disabled, .h3-builder-row.h3-builder-unused { opacity: 0.45; }
.h3-builder-mode {
  display: flex; flex: 0 0 auto; border: 1px solid #555; border-radius: 8px;
  overflow: hidden; background: #1b1b1b;
}
.h3-builder-mode-btn {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
  background: transparent; color: #bbb; border: 0 !important; border-radius: 0;
  padding: 7px 8px; cursor: pointer; font: inherit;
}
.h3-builder-mode-btn + .h3-builder-mode-btn { border-left: 1px solid #444 !important; }
.h3-builder-mode-btn[aria-pressed="true"] { background: rgba(120, 185, 255, 0.22); color: #dff; }
.h3-builder-mode-btn svg { width: 14px; height: 14px; flex: 0 0 auto; }
.h3-builder-grip {
  cursor: grab; color: #8aa; user-select: none; letter-spacing: -1px;
  font-size: 13px; line-height: 1; padding: 4px 0; text-align: center;
}
.h3-builder-grip:active { cursor: grabbing; }
.h3-builder-row.h3-builder-fixed .h3-builder-grip { visibility: hidden; cursor: default; }
.h3-builder-split {
  flex: 1 1 auto; min-height: 0; min-width: 0; display: flex; flex-direction: column;
}
.h3-builder-split-handle {
  flex: 0 0 8px; margin: 3px 6px; border-radius: 4px; background: #333;
  cursor: row-resize; touch-action: none; position: relative;
}
.h3-builder-split-handle::after {
  content: ""; position: absolute; left: 50%; top: 50%; width: 32px; height: 2px;
  transform: translate(-50%, -50%); background: #777; border-radius: 1px;
}
.h3-builder-split-handle:hover, .h3-builder-split-handle.is-dragging { background: #35506a; }
.h3-builder-split-handle:hover::after, .h3-builder-split-handle.is-dragging::after { background: #9cf; }
.h3-builder-plan { display: flex; flex-direction: column; gap: 4px; padding: 0 2px 2px; min-height: ${MIN_PLAN_PX}px; min-width: 0; }
.h3-builder-plan-label { color: #aaa; font: 11px system-ui, sans-serif; flex: 0 0 auto; }
.h3-builder-plan-host {
  position: relative; flex: 1 1 auto; min-height: 0; min-width: 0;
  border: 1px solid #444; border-radius: 8px; overflow: hidden; background: #1c1c1c;
}
.h3-builder-plan-host .h3-studio-prompt-wrap {
  position: absolute; inset: 0; height: auto; width: auto;
}
.h3-builder-actions { display: flex; gap: 6px; flex-wrap: wrap; flex: 0 0 auto; align-items: center; }
.h3-builder-actions button { background: #333; color: #eee; border: 1px solid #555; padding: 4px 8px; cursor: pointer; }
.h3-builder-switch {
  display: inline-flex; align-items: center; gap: 6px; color: #ccc; cursor: pointer; user-select: none;
}
.h3-builder-switch input {
  appearance: none; -webkit-appearance: none; width: 28px; height: 16px; margin: 0;
  border-radius: 999px; background: #3a3a3a; border: 1px solid #666; position: relative; cursor: pointer;
}
.h3-builder-switch input::after {
  content: ""; position: absolute; top: 1px; left: 1px; width: 12px; height: 12px;
  border-radius: 50%; background: #ddd;
}
.h3-builder-switch input:checked { background: #3d6a93; border-color: #7ec8ff; }
.h3-builder-switch input:checked::after { left: 13px; }
.h3-builder button.h3-builder-copied { border-color: #6c9; color: #cfe; background: #2a4033; }
.h3-builder-hint { color: #888; flex: 0 0 auto; }
.h3-builder-footer { display: flex; flex-direction: column; gap: 6px; flex: 0 0 auto; }
.h3-builder-menu {
  position: fixed; z-index: 100002; width: min(300px, calc(100vw - 16px));
  padding: 7px; box-sizing: border-box; border: 1px solid rgba(255,255,255,.22);
  border-radius: 9px; background: #202124; color: #f0f0f0;
  box-shadow: 0 14px 40px rgba(0,0,0,.48); font: 12px/1.35 system-ui, sans-serif;
}
.h3-builder-menu-title { padding: 4px 7px 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 680; }
.h3-builder-menu-properties { padding: 2px 7px 7px; color: rgba(255,255,255,.68); overflow-wrap: anywhere; }
.h3-builder-menu-properties > div + div { margin-top: 2px; }
.h3-builder-menu-separator { height: 1px; margin: 5px 3px; background: rgba(255,255,255,.12); }
.h3-builder-menu button {
  display: block; width: 100%; border: 0; border-radius: 6px; padding: 6px 7px;
  background: transparent; color: inherit; text-align: left; font: inherit; cursor: pointer;
}
.h3-builder-menu button:hover, .h3-builder-menu button:focus-visible { background: rgba(120,175,240,.18); outline: none; }
.h3-builder-menu button.h3-builder-danger { color: #ffaaaa; }
.h3-builder-lightbox {
  position: fixed; inset: 0; z-index: 100000; display: flex; align-items: center;
  justify-content: center; padding: 36px; background: rgba(0,0,0,.86);
}
.h3-builder-lightbox img, .h3-builder-lightbox video {
  max-width: 94vw; max-height: 90vh; object-fit: contain; box-shadow: 0 18px 60px rgba(0,0,0,.45);
}
.h3-builder-lightbox-label {
  position: absolute; left: 24px; bottom: 18px; right: 70px; color: white;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.h3-builder-lightbox-close {
  position: absolute; top: 18px; right: 20px; font-size: 24px; color: white;
  background: rgba(255,255,255,.12); border: 0; border-radius: 8px; width: 38px; height: 38px; cursor: pointer;
}
</style>
<div class="h3-builder-mode" role="group" aria-label="Builder mode">
  <button type="button" class="h3-builder-mode-btn" data-mode="auto_chain" aria-pressed="true">
    <svg viewBox="0 0 16 16" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.7"><ellipse cx="5.2" cy="8" rx="4.1" ry="2.6" transform="rotate(-35 5.2 8)"/><ellipse cx="10.8" cy="8" rx="4.1" ry="2.6" transform="rotate(-35 10.8 8)"/></g></svg>
    Auto Chain
  </button>
  <button type="button" class="h3-builder-mode-btn" data-mode="music_video" aria-pressed="false">
    ${kindIconSvg("audio")}
    Music Video
  </button>
</div>
<div class="h3-builder-split">
  <div class="h3-builder-list"></div>
  <div class="h3-builder-split-handle" data-act="split" role="separator" aria-orientation="horizontal" title="Drag to resize list and plan"></div>
  <div class="h3-builder-plan">
    <div class="h3-builder-plan-label">Plan</div>
    <div class="h3-builder-plan-host" data-act="plan"></div>
  </div>
</div>
<div class="h3-builder-footer">
<div class="h3-builder-hint">Drop image / video / audio here, or wire them to Media. Drag a thumbnail or handle to reorder. Right-click a reference for details.</div>
<div class="h3-builder-actions">
  <button type="button" data-act="upload">Upload</button>
  <button type="button" data-act="copy" title="${COPY_PACK_TIP}">${COPY_PACK_LABEL}</button>
  <label class="h3-builder-switch" title="When on, the copy starts with /prompt-minimax-h3-infinite or /prompt-minimax-h3-music-video for the selected mode.">
    <input type="checkbox" data-act="skill-slash">
    <span>Skill slash</span>
  </label>
</div>
</div>
<input type="file" multiple accept="image/*,video/*,audio/*" hidden />
`;
    const list = root.querySelector(".h3-builder-list");
    const plan = root.querySelector(".h3-builder-plan");
    const split = root.querySelector(".h3-builder-split");
    const hint = root.querySelector(".h3-builder-hint");
    const fileInput = root.querySelector("input[type=file]");
    const copyBtn = root.querySelector("[data-act=copy]");
    const musicBtn = root.querySelector('[data-mode="music_video"]');
    if (musicBtn) musicBtn.title = MUSIC_VIDEO_SONG_TIP;
    const modeBar = root.querySelector(".h3-builder-mode");
    modeBar?.addEventListener("pointerdown", (event) => {
        if (!event.target.closest("[data-mode]")) return;
        event.preventDefault();
        event.stopPropagation();
    });
    modeBar?.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-mode]");
        if (!btn) return;
        event.preventDefault();
        event.stopPropagation();
        setMode(node, btn.dataset.mode);
    });
    const widget = node.addDOMWidget("h3_builder_list", "div", root, {
        getMinHeight: () => MIN_WIDGET_HEIGHT,
        getHeight: () => "100%",
        onDraw: (domWidget) => syncBuilderWidget(node, domWidget),
        afterResize: () => syncBuilderWidget(node, builderDomWidget(node)),
        serialize: false,
    });
    if (widget) {
        widget.serialize = false;
        bindBuilderWidgetSize(widget);
    }

    const ui = {
        root, list, plan, split, hint, fileInput, widget, fileDragDepth: 0,
        state: parseState(findWidget(node, "state_json")?.value),
        syncModeButtons() {
            const music = isMusicVideoMode(node);
            root.querySelectorAll("[data-mode]").forEach((btn) => {
                const on = btn.dataset.mode === (music ? MODE_MUSIC_VIDEO : MODE_AUTO_CHAIN);
                btn.setAttribute("aria-pressed", on ? "true" : "false");
            });
        },
    };
    node.__h3BuilderUi = ui;
    bindBuilderSplit(node, root.querySelector("[data-act=split]"));
    applyBuilderSplit(node);

    const save = () => {
        syncLinksFromMediaOrder(node, ui.state);
        persist(node, ui.state);
        render();
        refreshNodeLayout(node);
        window.dispatchEvent(new CustomEvent("h3-studio-builder-changed"));
    };

    function render() {
        hideStateWidget(node);
        hideModeWidget(node);
        ui.syncModeButtons?.();
        syncModelMeta();
        const scrollTop = list.scrollTop;
        list.replaceChildren();
        const music = isMusicVideoMode(node);
        const slots = connectedModelSlots(node);
        let modelN = 0;
        for (const slot of slots) {
            const meta = ui.state.models.find((item) => Number(item.slot) === slot) || { slot, enabled: true, description: "" };
            if (meta.enabled !== false) modelN += 1;
            list.appendChild(modelRow(meta, meta.enabled === false ? unusedTitle("model") : `Model ${modelN}`, save));
        }
        let pic = 0;
        let vid = 0;
        let aud = 0;
        ui.state.media.forEach((item, index) => {
            const audioLocked = music && item.kind === "audio";
            const unused = audioLocked || item.enabled === false;
            let label = unusedTitle(item.kind);
            if (!unused) {
                if (item.kind === "image") { pic += 1; label = `Picture ${pic}`; }
                else if (item.kind === "video") { vid += 1; label = `Video ${vid}`; }
                else if (item.kind === "audio") { aud += 1; label = `Audio ${aud}`; }
            }
            list.appendChild(mediaRow(node, item, index, label, audioLocked, unused, save, ui));
        });
        if (!slots.length && !ui.state.media.length) {
            const empty = document.createElement("div");
            empty.className = "h3-builder-hint";
            empty.textContent = "No media yet.";
            list.appendChild(empty);
        }
        if (ui.hint) {
            ui.hint.textContent = music
                ? "Drop a song on the song row. Drop image / video / audio on the list, or wire them to Media. Audio refs are unused in Music Video mode."
                : "Drop image / video / audio here, or wire them to Media. Drag a thumbnail or handle to reorder. Right-click a reference for details.";
        }
        const skillToggle = root.querySelector("[data-act=skill-slash]");
        if (skillToggle) skillToggle.checked = Boolean(ui.state.include_skill);
        list.scrollTop = scrollTop;
    }

    function syncModelMeta() {
        const slots = connectedModelSlots(node);
        const prev = new Map((ui.state.models || []).map((item) => [Number(item.slot), item]));
        ui.state.models = slots.map((slot) => {
            const old = prev.get(slot) || {};
            return {
                slot,
                enabled: old.enabled !== false,
                description: String(old.description || ""),
            };
        });
    }

    list.addEventListener("dragenter", (event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        ui.fileDragDepth += 1;
        list.classList.add("h3-builder-drop-target");
    });
    list.addEventListener("dragleave", (event) => {
        if (!isFileDrag(event)) return;
        ui.fileDragDepth = Math.max(0, ui.fileDragDepth - 1);
        if (ui.fileDragDepth === 0) list.classList.remove("h3-builder-drop-target");
    });
    list.addEventListener("dragover", (event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        list.classList.add("h3-builder-drop-target");
    });
    list.addEventListener("drop", (event) => {
        event.preventDefault();
        event.stopPropagation();
        ui.fileDragDepth = 0;
        list.classList.remove("h3-builder-drop-target");
        const files = [...(event.dataTransfer?.files || [])];
        if (files.length && takeFileDrop(node)) void addFiles(files);
    });
    root.querySelector("[data-act=upload]").addEventListener("click", () => fileInput.click());
    root.querySelector("[data-act=skill-slash]")?.addEventListener("change", (event) => {
        ui.state.include_skill = Boolean(event.target.checked);
        persist(node, ui.state);
    });
    copyBtn.addEventListener("click", async () => {
        const dump = formatDump(node, ui.state, connectedModelSlots(node));
        try {
            await navigator.clipboard.writeText(dump);
        } catch (_) {
            window.prompt("Copy Builder dump", dump);
        }
        copyBtn.textContent = "Copied";
        copyBtn.classList.add("h3-builder-copied");
        clearTimeout(copyBtn._h3Copied);
        copyBtn._h3Copied = setTimeout(() => {
            copyBtn.textContent = COPY_PACK_LABEL;
            copyBtn.classList.remove("h3-builder-copied");
        }, 1500);
    });
    fileInput.addEventListener("change", () => {
        const files = [...(fileInput.files || [])];
        fileInput.value = "";
        if (files.length) void addFiles(files);
    });

    async function addFiles(files) {
        for (const file of files) {
            try {
                const payload = await uploadFile(file);
                ui.state.media.push({
                    path: payload.path,
                    kind: payload.kind,
                    enabled: true,
                    description: "",
                    duration: Number(payload.duration) || 0,
                    has_soundtrack: Boolean(payload.has_soundtrack),
                    start: 0,
                    length: 0,
                    crop: null,
                    first_frame: false,
                });
                clipMediaRegion(ui.state.media[ui.state.media.length - 1], builderDuration(node), builderSegments(node));
            } catch (exc) {
                window.alert(exc?.message || String(exc));
            }
        }
        save();
    }

    ui.render = render;
    ui.save = save;
    ui.addFiles = addFiles;
    attachPlanEditor(node);
    render();
    return ui;
}

function isFileDrag(event) {
    const types = event.dataTransfer?.types;
    if (!types) return false;
    return [...types].includes("Files");
}

function modelRow(meta, label, save) {
    const row = document.createElement("div");
    row.className = "h3-builder-row h3-builder-fixed";
    if (meta.enabled === false) row.classList.add("h3-builder-unused");
    row.innerHTML = `
      <input type="checkbox" ${meta.enabled === false ? "" : "checked"} title="Enable">
      <span class="h3-builder-grip" aria-hidden="true">⋮⋮</span>
      <div class="h3-builder-icon is-model">${kindIconSvg("model")}</div>
      <div class="h3-builder-fields">
        <div class="h3-builder-title">${label}</div>
        <input type="text" placeholder="description" value="${escapeAttr(meta.description)}">
      </div>
    `;
    row.querySelector("input[type=checkbox]").addEventListener("change", (event) => {
        meta.enabled = event.target.checked;
        save();
    });
    row.querySelector("input[type=text]").addEventListener("change", (event) => {
        meta.description = event.target.value;
        save();
    });
    return row;
}

function mediaRow(node, item, index, label, audioLocked, unused, save, ui) {
    const row = document.createElement("div");
    row.className = "h3-builder-row";
    if (unused) row.classList.add("h3-builder-unused");
    if (audioLocked) row.classList.add("h3-builder-audio-disabled");
    const thumb = thumbMarkup(item);
    const editLabel = item.kind === "image" ? "Crop" : "Trim";
    const checked = !audioLocked && item.enabled !== false;
    const tip = audioLocked ? MUSIC_VIDEO_SONG_TIP : "Enable";
    const firstFrame = item.kind === "image";
    const firstChecked = firstFrame && !unused && Boolean(item.first_frame);
    const firstTip = unused
        ? "Enable this image to use it as the first image for clip 1"
        : "Use this still as the first image for clip 1";
    const firstMarkup = firstFrame
        ? `<label class="h3-builder-first-frame" title="${escapeAttr(firstTip)}"><input type="checkbox" data-act="first-frame" ${firstChecked ? "checked" : ""} ${unused ? "disabled" : ""}>First image</label>`
        : "";
    const hasFile = Boolean(item.path);
    if (audioLocked) row.title = MUSIC_VIDEO_SONG_TIP;
    row.innerHTML = `
      <input type="checkbox" data-act="enable" ${checked ? "checked" : ""} title="${escapeAttr(tip)}" ${audioLocked ? "disabled" : ""}>
      <span class="h3-builder-grip" draggable="true" title="Drag to reorder">⋮⋮</span>
      ${thumb}
      <div class="h3-builder-fields">
        <div class="h3-builder-title">
          <span>${label}</span>
          <div class="h3-builder-row-actions">
            ${firstMarkup}
            ${hasFile ? `<button type="button" class="h3-builder-icon-btn" data-act="preview" title="${escapeAttr(previewLabel(item.kind))}">${iconEye()}</button>` : ""}
            ${hasFile ? `<button type="button" class="h3-builder-icon-btn" data-act="edit" title="${escapeAttr(editLabel)}">✂</button>` : ""}
            <button type="button" class="h3-builder-icon-btn h3-builder-danger" data-act="delete" title="Delete reference">${iconTrash()}</button>
          </div>
        </div>
        <input type="text" placeholder="description" value="${escapeAttr(item.description)}">
      </div>
    `;
    for (const btn of row.querySelectorAll(".h3-builder-icon-btn")) {
        btn.addEventListener("contextmenu", (event) => event.stopPropagation());
    }
    row.querySelector("[data-act=preview]")?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openPreview(item);
    });
    row.querySelector("[data-act=edit]")?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openMediaEditor(node, item, save);
    });
    row.querySelector("[data-act=delete]").addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        ui.state.media.splice(index, 1);
        save();
    });
    const grip = row.querySelector(".h3-builder-grip");
    const thumbEl = row.querySelector(".h3-builder-drag");
    row.querySelector("[data-act=enable]").addEventListener("change", (event) => {
        if (audioLocked) return;
        item.enabled = event.target.checked;
        if (!item.enabled) item.first_frame = false;
        save();
    });
    row.querySelector("[data-act=first-frame]")?.addEventListener("change", (event) => {
        event.stopPropagation();
        const on = event.target.checked;
        for (const other of ui.state.media) {
            if (other.kind === "image") other.first_frame = false;
        }
        if (on) item.first_frame = true;
        save();
    });
    row.querySelector("input[type=text]").addEventListener("change", (event) => {
        item.description = event.target.value;
        save();
    });
    row.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        showMediaMenu(node, item, index, event.clientX, event.clientY);
    });
    bindMediaReorder(grip, row, index);
    bindMediaReorder(thumbEl, row, index);
    if (hasImageCrop(item)) applyCropThumb(row.querySelector(".h3-builder-thumb img"), item.crop);
    row.addEventListener("dragover", (event) => {
        if (isFileDrag(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
    });
    row.addEventListener("drop", (event) => {
        if (isFileDrag(event)) return;
        const raw = event.dataTransfer.getData("text/h3-builder-index");
        if (raw === "") return;
        const from = Number(raw);
        if (!Number.isFinite(from) || from === index) return;
        event.preventDefault();
        event.stopPropagation();
        const [moved] = ui.state.media.splice(from, 1);
        ui.state.media.splice(index, 0, moved);
        save();
    });
    return row;
}

function bindMediaReorder(handle, row, index) {
    if (!handle) return;
    handle.draggable = true;
    handle.addEventListener("dragstart", (event) => {
        event.stopPropagation();
        event.dataTransfer.setData("text/h3-builder-index", String(index));
        event.dataTransfer.effectAllowed = "move";
        row.classList.add("drag");
    });
    handle.addEventListener("dragend", () => row.classList.remove("drag"));
}

function escapeAttr(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;");
}

function installSizeGuard(node) {
    if (node.__h3BuilderSizeGuard) return;
    node.__h3BuilderSizeGuard = true;
    const originalCompute = node.computeSize?.bind(node);
    node.computeSize = function (out) {
        const size = originalCompute ? originalCompute(out) : [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
        size[0] = Math.max(size[0], MIN_NODE_WIDTH);
        size[1] = Math.max(size[1], MIN_NODE_HEIGHT);
        return size;
    };
    const previousResize = node.onResize;
    node.onResize = function (...args) {
        const result = previousResize?.apply(this, args);
        syncBuilderWidget(this, builderDomWidget(this));
        return result;
    };
    ensureMinSize(node);
}

function installSongDrop(node) {
    if (node.__h3BuilderSongDrop) return;
    node.__h3BuilderSongDrop = true;
    const previousOver = node.onDragOver;
    node.onDragOver = function (event) {
        if (!isFileDrag(event)) return previousOver?.apply(this, arguments);
        const zone = dropTargetZone(this, event);
        if (zone === "song" && isMusicVideoMode(this) && !songSocketLinked(this)) return true;
        if (zone === "list") return true;
        return previousOver?.apply(this, arguments);
    };
    const previousDrop = node.onDragDrop;
    node.onDragDrop = async function (event) {
        const files = [...(event?.dataTransfer?.files || [])];
        if (!files.length) return previousDrop?.apply(this, arguments) ?? false;
        const zone = dropTargetZone(this, event);
        if (zone === "song" && isMusicVideoMode(this) && !songSocketLinked(this)) {
            const audio = files.find(isAudioFile);
            if (audio && takeFileDrop(this)) {
                try {
                    await setSongFromFile(this, audio);
                } catch (exc) {
                    window.alert(exc?.message || String(exc));
                }
                return true;
            }
        }
        if (zone === "list") {
            const add = this.__h3BuilderUi?.addFiles;
            if (add && takeFileDrop(this)) {
                await add(files);
                return true;
            }
        }
        return previousDrop?.apply(this, arguments) ?? false;
    };
}

function install(node) {
    if (!isTarget(node)) return;
    applyNamedWidgetValues(node, node.__h3SavedWidgetValues);
    hideStateWidget(node);
    hideModeWidget(node);
    hideSongFileWidget(node);
    installSizeGuard(node);
    installSongDrop(node);
    const durationWidget = findWidget(node, "max_clip_duration");
    if (durationWidget) {
        durationWidget.options ||= {};
        durationWidget.options.socket = true;
        durationWidget.options.display = "number";
        if (durationWidget.type === "slider") durationWidget.type = "number";
    }
    for (const name of ["segments", "loop"]) {
        const widget = findWidget(node, name);
        if (!widget) continue;
        widget.options ||= {};
        widget.options.socket = true;
    }
    ensureSongDropWidget(node);
    ensureLyricsSocket(node);
    syncModelInputs(node);
    pruneTransportInputsFromNode(node);
    labelMediaInput(node);
    const ui = ensureUi(node);
    ui.state = parseState(findWidget(node, "state_json")?.value);
    if (syncBuilderMediaList(node, ui.state)) persist(node, ui.state);
    clampAllRegions(node);
    syncModeUi(node);
    attachPlanEditor(node);
    ui.render?.();
    syncBuilderWidget(node, builderDomWidget(node));
    restoreNodeSizeSoon(node);
}

app.registerExtension({
    name: "H3Studio.Builder",

    setup() {
        installBuilderMediaRuntime();
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isTargetDefinition(nodeType, nodeData)) return;
        installBuilderMediaNode(nodeType, nodeData);
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info, ...rest) {
            captureNodeSize(this, info?.size);
            this.__h3SavedWidgetValues = info?.widgets_values;
            const result = originalOnConfigure?.apply(this, [info, ...rest]);
            applyNamedWidgetValues(this, this.__h3SavedWidgetValues);
            queueMicrotask(() => install(this));
            return result;
        };
        const originalOnConnectInput = nodeType.prototype.onConnectInput;
        nodeType.prototype.onConnectInput = function (slot, ...args) {
            const input = this.inputs?.[slot];
            if (input?.hidden) return false;
            const name = String(input?.name || "");
            const music = isMusicVideoMode(this);
            if (!music && (name === "song" || name === "lyrics")) return false;
            if (music && (name === "segments" || name === "loop")) return false;
            return originalOnConnectInput?.apply(this, [slot, ...args]) ?? true;
        };
        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = originalOnConnectionsChange?.apply(this, args);
            queueMicrotask(() => {
                if (!isTarget(this)) return;
                pruneTransportInputsFromNode(this);
                labelMediaInput(this);
                syncModelInputs(this);
                syncModeUi(this);
                const ui = this.__h3BuilderUi;
                if (ui?.state && syncBuilderMediaList(this, ui.state)) persist(this, ui.state);
                ui?.render?.();
                refreshNodeLayout(this);
            });
            return result;
        };
        const originalOnWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
            const result = originalOnWidgetChanged?.apply(this, arguments);
            const widgetName = widget?.name ?? name;
            if (widgetName === "mode") queueMicrotask(() => syncModeUi(this));
            if (widgetName === "max_clip_duration" || widgetName === "segments") {
                queueMicrotask(() => {
                    clampAllRegions(this);
                    this.__h3BuilderUi?.save?.();
                });
            }
            return result;
        };
    },

    async nodeCreated(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => install(node));
    },

    loadedGraphNode(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => install(node));
    },
});

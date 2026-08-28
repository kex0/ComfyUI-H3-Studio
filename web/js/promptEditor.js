import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { applyCropThumb, hasImageCrop, kindIconSvg, normalizeKind, openPreview } from "./thumbs.js";
import {
    applyVisualSize, applyVueCssSize, captureNodeSize, cssContentHeight, installSizeWatch, restoreNodeSizeSoon,
    setKeptSize, snapshotVisualSize, wrapExpandToFit,
} from "./nodeSize.js";

const PROMPT_NODES = new Set([
    "H3StudioAutoChain",
    "H3StudioMusicVideo",
    "H3StudioAutoChainClipFixer",
    "H3StudioMusicVideoClipFixer",
]);
const ADVANCED_AUTO_CHAIN = "H3StudioAutoChain";
const MUSIC_VIDEO = "H3StudioMusicVideo";
const AUTO_CHAIN_CLIP_FIXER = "H3StudioAutoChainClipFixer";
const MUSIC_VIDEO_CLIP_FIXER = "H3StudioMusicVideoClipFixer";
const MAX_CLIP_PROMPTS = 999;
const MUSIC_MAX_CLIP_PROMPTS = 48;
const LEGACY_CLIP_PROMPT_WIDGETS = 12;
const MIN_PROMPT_HEIGHT = 96;
const DEFAULT_PROMPT_HEIGHT = 96;
const PROMPT_HOST_CHROME = 40;
const PER_CLIP_FIELD_HEIGHT = 100;
const CLIP_PICKS_HEIGHT = 36;
const DEFAULT_NODE_WIDTH = 360;
const NODE_BODY_CHROME = 54;
const PROGRESS_WIDGET_NAME = "$$node-text-preview";
const PROGRESS_HEIGHT = 52;
const VIEW_PROP = "h3_studio_prompt_view";
const TOKEN_RE = /(@(?:Picture|Video|Audio|Model)\s*\d+(?::\d+)?|<(?:Picture|Video|Audio|Model)\s+\d+(?::\d+)?>)/gi;
const PART_RE = /(<d>[\s\S]*?<\/d>|@(?:Picture|Video|Audio|Model)\s*\d+(?::\d+)?|<(?:Picture|Video|Audio|Model)\s+\d+(?::\d+)?>)/gi;
const TAG_RE = /(Picture|Video|Audio|Model)\s*(\d+)(?::(\d+))?/i;
const CARET_SINK = "\u200b";
const DIALOGUE_CLASS = "h3-dialogue-block";
const DIALOGUE_LANG_RE = /^\[([^\]]+)\][ \t]*/;
const DIALOGUE_LANGUAGES = [
    { name: "English", code: "EN" },
    { name: "Chinese", code: "CN" },
    { name: "Japanese", code: "JP" },
    { name: "Korean", code: "KR" },
    { name: "Spanish", code: "ES" },
    { name: "French", code: "FR" },
    { name: "German", code: "DE" },
    { name: "Portuguese", code: "BR" },
    { name: "Italian", code: "IT" },
    { name: "Russian", code: "RU" },
    { name: "Arabic", code: "SA" },
    { name: "Hindi", code: "IN" },
];

function ensureStyle() {
    let style = document.getElementById("h3-studio-prompt-editor-style");
    if (!style) {
        style = document.createElement("style");
        style.id = "h3-studio-prompt-editor-style";
        document.head.appendChild(style);
    }
    style.textContent = `
.h3-studio-prompt-wrap {
  position: relative; display: block; width: 100%; height: 100%; min-width: 0; min-height: 0; max-height: 100%;
  box-sizing: border-box; padding: 0; border-radius: var(--h3-native-widget-radius, 0); overflow: hidden; contain: size layout paint;
}
.h3-studio-prompt-editor {
  --h3-prompt-text-size: var(--h3-native-widget-text-size, var(--comfy-textarea-font-size, 12px));
  display: block; width: 100%; height: 100%; min-width: 0; min-height: 0; max-height: 100%; box-sizing: border-box;
  padding: var(--h3-native-widget-padding, 2px);
  padding-bottom: calc(var(--h3-native-widget-padding, 2px) + 24px); overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain;
  white-space: pre-wrap; overflow-wrap: anywhere; border: 0; border-radius: var(--h3-native-widget-radius, 0); outline: none;
  resize: none; background-color: var(--h3-native-widget-bg, var(--comfy-input-bg, #222));
  color: var(--h3-native-widget-text, var(--input-text, #ddd)); caret-color: var(--h3-native-widget-text, var(--input-text, #ddd));
  font-family: Consolas, "Courier New", monospace; font-size: var(--h3-prompt-text-size); font-weight: 400;
  font-style: normal; line-height: var(--h3-native-widget-line-height, normal); letter-spacing: 0;
}
.h3-studio-prompt-editor:empty::before {
  content: attr(data-placeholder); color: color-mix(in srgb, var(--h3-native-widget-text, #ddd) 38%, transparent);
  pointer-events: none;
}
.h3-studio-prompt-wrap.h3-native-vue-nodes .h3-studio-prompt-editor:focus {
  box-shadow: 0 0 0 1px var(--h3-native-widget-focus, var(--h3-native-widget-outline, rgba(255,255,255,.18)));
}
.lg-node:has(.h3-studio-prompt-wrap, .h3-studio-prompt-host) .lg-node-widgets,
.lg-node:has(.h3-studio-prompt-wrap, .h3-studio-prompt-host) [data-testid="node-widgets"] {
  flex: 1 1 auto !important; min-height: 0;
}
.lg-node:has(.h3-studio-prompt-wrap, .h3-studio-prompt-host) .lg-node-widget:has(.h3-studio-prompt-wrap, .h3-studio-prompt-host),
.lg-node:has(.h3-studio-prompt-wrap, .h3-studio-prompt-host) [data-testid="node-widget"]:has(.h3-studio-prompt-wrap, .h3-studio-prompt-host) {
  min-height: 96px; min-width: 0; overflow: hidden;
}
.dom-widget.h3-studio-progress-pin,
.dom-widget:has(.h3-studio-progress-pin) {
  height: 52px !important; max-height: 52px !important;
}
.h3-studio-prompt-host {
  display: flex; flex-direction: column; gap: 8px; width: 100%; height: 100%;
  min-width: 0; min-height: 0; max-height: 100%; box-sizing: border-box; overflow: hidden;
}
.h3-studio-prompt-mode {
  display: flex; flex: 0 0 auto; min-width: 0; border: 1px solid rgba(255,255,255,.16); border-radius: 8px;
  overflow: hidden; background: rgba(0,0,0,.18);
}
.h3-studio-prompt-mode-btn {
  flex: 1 1 0; min-width: 0; appearance: none; display: flex; align-items: center; justify-content: center;
  background: transparent; color: rgba(255,255,255,.62); border: 0; border-radius: 0;
  padding: 6px 4px; cursor: pointer; font: 600 11px/1.2 system-ui, sans-serif;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.h3-studio-prompt-mode-btn + .h3-studio-prompt-mode-btn { border-left: 1px solid rgba(255,255,255,.12); }
.h3-studio-prompt-mode-btn[aria-pressed="true"] { background: rgba(120,185,255,.22); color: #dff; }
.h3-studio-prompt-stack {
  display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; min-width: 0; gap: 8px;
}
.h3-studio-clip-picks {
  display: flex; flex-wrap: nowrap; flex: 0 0 auto; align-items: center; gap: 4px;
  min-width: 0; min-height: 28px; max-height: 32px; padding: 4px 0 0;
  overflow-x: auto; overflow-y: hidden; scrollbar-width: thin;
}
.h3-studio-clip-picks[hidden] { display: none !important; }
.h3-studio-clip-picks button {
  appearance: none; flex: 0 0 auto; min-width: 26px; height: 24px; padding: 0 7px; box-sizing: border-box;
  border: 1px solid rgba(255,255,255,.16); border-radius: 6px;
  background: rgba(0,0,0,.18); color: rgba(255,255,255,.68);
  cursor: pointer; font: 600 11px/1 system-ui, sans-serif; white-space: nowrap;
}
.h3-studio-clip-picks button.h3-studio-clip-picks-loop { min-width: 40px; }
.h3-studio-clip-picks button[aria-pressed="true"] {
  background: rgba(120,185,255,.22); color: #dff; border-color: rgba(120,185,255,.42);
}
.h3-studio-prompt-field {
  display: flex; flex-direction: column; flex: 1 1 0; min-height: 0; min-width: 0; gap: 3px;
}
.h3-studio-prompt-field .h3-studio-prompt-wrap { flex: 1 1 auto; min-height: 0; }
.h3-studio-prompt-tools {
  position: absolute; right: 14px; bottom: 4px; z-index: 3; display: flex; align-items: center; gap: 3px; pointer-events: auto;
}
.h3-studio-prompt-tools.is-top { top: 4px; bottom: auto; }
.h3-studio-prompt-tool {
  appearance: none; display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 18px; padding: 0;
  border: 1px solid transparent; border-radius: 4px; outline: none; background: transparent; box-shadow: none;
  color: var(--h3-native-widget-text, rgba(255,255,255,.78)); opacity: .34; cursor: pointer; user-select: none;
  font: 600 9px/1 Consolas, "Courier New", monospace; letter-spacing: -.4px;
}
.h3-studio-prompt-tool svg { display: block; width: 11px; height: 11px; }
.h3-studio-prompt-tool:hover, .h3-studio-prompt-tool:focus-visible {
  opacity: .62; background: rgba(255,255,255,.045); border-color: rgba(255,255,255,.1);
}
.h3-caret-sink {
  display: inline; padding: 0; margin: 0; border: 0; font: inherit; line-height: inherit;
  white-space: pre; background: transparent; color: inherit;
}
.h3-dialogue-block {
  display: inline; margin: 0 1px; padding: 1px 5px; vertical-align: baseline; border: 0; border-radius: 4px;
  background: rgba(0,226,187,.14); color: rgba(190,255,244,.98);
  box-shadow: inset 0 0 0 1px rgba(0,226,187,.16); font: inherit; line-height: inherit; letter-spacing: 0;
  white-space: pre-wrap; -webkit-box-decoration-break: clone; box-decoration-break: clone;
  user-select: text; cursor: text; outline: none;
}
.h3-dialogue-block:focus {
  background: rgba(0,226,187,.19); box-shadow: inset 0 0 0 1px rgba(0,226,187,.26);
}
.h3-dialogue-flag {
  appearance: none; display: inline-flex; align-items: center; justify-content: center;
  margin: 0 5px 0 0; padding: 0; border: 0; background: transparent;
  height: 1em; vertical-align: bottom; cursor: pointer; user-select: none;
}
.h3-dialogue-flag-glyph {
  display: block; font: 700 .72em/1 system-ui, sans-serif; letter-spacing: .04em;
}
.h3-chip-menu.h3-dialogue-lang-menu { max-height: min(420px, calc(100vh - 16px)); min-width: 240px; }
.h3-chip-menu.h3-dialogue-lang-menu > button {
  display: flex; align-items: center; gap: 8px;
}
.h3-dialogue-lang-menu .h3-dialogue-flag-glyph {
  flex: none; width: 1.6em; font-size: 11px; text-align: center;
}
.h3-chip-menu .h3-dialogue-lang-custom {
  display: flex; align-items: center; gap: 6px; padding: 4px 6px; width: 100%; box-sizing: border-box;
}
.h3-chip-menu .h3-dialogue-lang-custom input {
  flex: 1 1 auto; min-width: 10em; width: 0; box-sizing: border-box;
  border: 1px solid rgba(255,255,255,.16); border-radius: 4px;
  background: rgba(0,0,0,.28); color: inherit; font: inherit; padding: 4px 6px; outline: none;
}
.h3-chip-menu .h3-dialogue-lang-custom input:focus { border-color: rgba(0,226,187,.45); }
.h3-chip-menu .h3-dialogue-lang-custom button {
  display: block; width: auto; flex: 0 0 auto; padding: 4px 8px;
}
.h3-mention-chip {
  display: inline-flex; align-items: center; gap: 2px; margin: 0 1px; padding: 0 3px 0 2px;
  box-sizing: border-box; vertical-align: middle; overflow: hidden; line-height: 1;
  border-radius: 3px; background: #2d3b4a; border: 1px solid #6aa; color: #dff;
  cursor: pointer; user-select: text; -webkit-user-select: text; font: 600 10px/1 system-ui, sans-serif;
}
.h3-mention-chip-thumb, .h3-mention-menu-thumb {
  display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative;
  flex: none; background: rgba(255,255,255,.12); color: #f2f2f2;
}
.h3-mention-chip-thumb {
  width: 1em; height: 1em; border-radius: 2px; pointer-events: none; user-select: none;
}
.h3-mention-chip-thumb svg { width: .78em; height: .78em; display: block; overflow: hidden; flex: none; }
.h3-mention-chip-thumb img {
  display: block; position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: cover;
  max-width: none; max-height: none; border: 0; pointer-events: none; user-select: none;
}
.h3-mention-menu, .h3-chip-menu {
  position: fixed; z-index: 1000020; min-width: 220px; max-width: min(360px, calc(100vw - 16px)); max-height: 320px; overflow: auto;
  padding: 6px; border-radius: 8px; background: #202124; color: #f0f0f0;
  border: 1px solid rgba(255,255,255,.2); box-shadow: 0 12px 32px rgba(0,0,0,.45);
  font: 12px/1.35 system-ui, sans-serif;
}
.h3-mention-menu button, .h3-chip-menu button {
  display: block; width: 100%; border: 0; background: transparent; color: inherit;
  text-align: left; padding: 6px 8px; border-radius: 6px; cursor: pointer; font: inherit;
}
.h3-mention-menu button.h3-mention-menu-row, .h3-mention-menu-row {
  display: flex; align-items: center; gap: 8px; padding: 4px 6px;
}
.h3-mention-picker-row {
  display: flex; align-items: center; gap: 6px; border-radius: 6px;
}
.h3-mention-picker-row > button.h3-mention-menu-row {
  flex: 1; min-width: 0; width: auto;
}
.h3-mention-picker-row:hover, .h3-mention-picker-row.is-active {
  background: rgba(120,175,240,.18);
}
.h3-mention-menu-row > span:last-child { min-width: 0; overflow: hidden; }
.h3-mention-menu-thumb {
  width: 28px; height: 28px; border-radius: 4px;
}
.h3-mention-menu-thumb svg { width: 16px; height: 16px; display: block; }
.h3-mention-menu-thumb img {
  position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; max-width: none; max-height: none;
}
.h3-mention-chip-thumb.h3-kind-image, .h3-mention-menu-thumb.h3-kind-image { background: #5aa9f0; }
.h3-mention-chip-thumb.h3-kind-video, .h3-mention-menu-thumb.h3-kind-video { background: linear-gradient(135deg, #1557b8, #49b6ff); color: #fff; }
.h3-mention-chip-thumb.h3-kind-audio, .h3-mention-menu-thumb.h3-kind-audio { background: #2a5038; color: #d8f5de; }
.h3-mention-chip-thumb.h3-kind-model, .h3-mention-menu-thumb.h3-kind-model { background: #3a2a4a; color: #eddff8; }
.h3-mention-chip-thumb.is-video::after, .h3-mention-menu-thumb.is-video::after {
  content: none !important; display: none !important; border: 0 !important;
}
.h3-mention-menu-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h3-mention-menu-detail { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 1px; color: rgba(255,255,255,.55); font-size: 11px; }
.h3-mention-menu button:hover, .h3-chip-menu button:hover,
.h3-mention-menu button.is-active, .h3-chip-menu button.is-active, .h3-chip-menu button:focus-visible { background: rgba(120,175,240,.18); outline: none; }
.h3-mention-menu .h3-mention-picker-row > button:hover,
.h3-mention-menu .h3-mention-picker-row > button.is-active { background: transparent; }
.h3-chip-menu button:disabled { opacity: .45; cursor: default; }
.h3-chip-menu button.h3-chip-menu-danger { color: #ffaaaa; }
.h3-mention-chip-seg {
  flex: none; min-width: 1.1em; padding: 0 3px; margin-left: 1px; border-radius: 2px;
  background: rgba(0,0,0,.28); font: 700 9px/1.1 system-ui, sans-serif; text-align: center;
}
.h3-chip-menu-picks {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 6px;
}
.h3-chip-menu-picks button {
  width: 22px; flex: 0 0 auto; text-align: center; padding: 4px 0;
}
.h3-chip-menu .h3-chip-menu-picks button { width: 28px; padding: 6px 0; }
.h3-mention-picker-row .h3-chip-menu-picks {
  flex: 0 0 auto; max-width: calc(4 * 22px + 3 * 4px); padding: 2px 4px 2px 0;
}
.h3-mention-picker-row .h3-chip-menu-picks button {
  background: rgba(255,255,255,.08);
}
.h3-mention-picker-row .h3-chip-menu-picks button:hover {
  background: rgba(120,175,240,.28);
}
`;
}

function targetNames(node) {
    return new Set([
        node?.type, node?.comfyClass, node?.constructor?.type,
        node?.constructor?.comfyClass, node?.constructor?.ComfyClass,
        node?.constructor?.nodeData?.name,
    ].filter(Boolean));
}

function isPromptNode(node) {
    return [...targetNames(node)].some((name) => PROMPT_NODES.has(name));
}

function isAdvancedAutoChain(node) {
    return [...targetNames(node)].some((name) => name === ADVANCED_AUTO_CHAIN || name === AUTO_CHAIN_CLIP_FIXER);
}

function isMusicVideo(node) {
    return [...targetNames(node)].some((name) => name === MUSIC_VIDEO || name === MUSIC_VIDEO_CLIP_FIXER);
}

function isAdvancedPromptNode(node) {
    return isAdvancedAutoChain(node) || isMusicVideo(node);
}

function isClipFixer(node) {
    return [...targetNames(node)].some((name) => (
        name === AUTO_CHAIN_CLIP_FIXER || name === MUSIC_VIDEO_CLIP_FIXER
    ));
}

function documentMode(node) {
    return isMusicVideo(node) ? "music_video" : "auto_chain";
}

function maxClipSegments(node) {
    return isMusicVideo(node) ? MUSIC_MAX_CLIP_PROMPTS : MAX_CLIP_PROMPTS;
}

function clipRole(index, segments, node) {
    if (index === 1) return "Start";
    if (isClipFixer(node) || isMusicVideo(node)) return "Continue";
    const indices = node ? storyClipIndices(node) : [];
    const last = indices.length ? indices[indices.length - 1] : segments;
    const fromOne = !indices.length || indices.every((n, i) => n === i + 1);
    if (fromOne && index === last) return "Finish";
    return "Continue";
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

function isVueNodesMode() {
    return Boolean(globalThis.LiteGraph?.vueNodesMode);
}

function applyNativeEditorTheme(element) {
    if (!element?.style) return;
    const LiteGraph = globalThis.LiteGraph || {};
    const modern = isVueNodesMode();
    const widgetBg = LiteGraph.WIDGET_BGCOLOR || "#222";
    const widgetText = LiteGraph.WIDGET_TEXT_COLOR || "#ddd";
    const outline = LiteGraph.WIDGET_OUTLINE_COLOR || "rgba(255, 255, 255, 0.18)";
    const menuBg = LiteGraph.NODE_DEFAULT_BGCOLOR || "#1f1f1f";
    element.classList?.toggle("h3-native-vue-nodes", modern);
    if (modern) {
        element.style.setProperty("--h3-native-widget-bg", "var(--component-node-widget-background, var(--secondary-background, #222))");
        element.style.setProperty("--h3-native-widget-text", "var(--component-node-foreground, var(--base-foreground, #ddd))");
        element.style.setProperty("--h3-native-widget-outline", "var(--component-node-widget-background-highlighted, var(--border-default, rgba(255, 255, 255, 0.18)))");
        element.style.setProperty("--h3-native-widget-focus", "var(--component-node-widget-background-highlighted, var(--border-default, rgba(255, 255, 255, 0.28)))");
        element.style.setProperty("--h3-native-widget-radius", "var(--radius-lg, 8px)");
        element.style.setProperty("--h3-native-widget-padding", "8px 12px");
        element.style.setProperty("--h3-native-widget-line-height", "var(--text-xs--line-height, 1.3333333)");
        element.style.setProperty("--h3-native-widget-text-size", "var(--text-xs, var(--comfy-textarea-font-size, 12px))");
        return;
    }
    element.style.setProperty("--h3-native-widget-bg", `var(--comfy-input-bg, ${widgetBg})`);
    element.style.setProperty("--h3-native-widget-text", `var(--input-text, ${widgetText})`);
    element.style.setProperty("--h3-native-widget-outline", `var(--border-color, ${outline})`);
    element.style.setProperty("--h3-native-widget-focus", `var(--border-color, ${outline})`);
    element.style.setProperty("--h3-native-menu-bg", `var(--comfy-menu-bg, ${menuBg})`);
    element.style.setProperty("--h3-native-widget-radius", "0px");
    element.style.setProperty("--h3-native-widget-padding", "2px");
    element.style.setProperty("--h3-native-widget-line-height", "normal");
    element.style.setProperty("--h3-native-widget-text-size", "var(--comfy-textarea-font-size, 12px)");
}

const SKIP_SERIALIZE = new Set(["h3_prompt_editor", "h3_prompt_mentions"]);

function hideOriginalPromptWidget(widget) {
    if (!widget) return;
    widget.hidden = true;
    widget.serialize = true;
    widget.computeSize = () => [0, -4];
    widget.computedHeight = 0;
    setWidgetOption(widget, "hidden", true);
    if (widget.inputEl) widget.inputEl.style.display = "none";
    if (widget.element) widget.element.style.display = "none";
}

function isSerializedDefWidget(widget) {
    if (!widget || SKIP_SERIALIZE.has(widget.name)) return false;
    if (widget.serialize === false) return false;
    if (widget.options?.serialize === false) return false;
    return true;
}

function defInputNames(node) {
    const data = node?.constructor?.nodeData || {};
    const order = data.input_order || {};
    const input = data.input || {};
    const names = [];
    for (const group of ["required", "optional"]) {
        const listed = order[group];
        if (Array.isArray(listed) && listed.length) {
            names.push(...listed);
            continue;
        }
        const spec = input[group];
        if (spec && typeof spec === "object" && !Array.isArray(spec)) names.push(...Object.keys(spec));
    }
    return names;
}

function serializedWidgetsInDefOrder(node) {
    const widgets = (node.widgets || []).filter(isSerializedDefWidget);
    const byName = new Map();
    for (const widget of widgets) {
        if (widget?.name && !byName.has(widget.name)) byName.set(widget.name, widget);
    }
    const ordered = [];
    const used = new Set();
    for (const name of defInputNames(node)) {
        const widget = byName.get(name);
        if (!widget) continue;
        used.add(widget);
        ordered.push(widget);
    }
    for (const widget of widgets) {
        if (!used.has(widget)) ordered.push(widget);
    }
    return ordered;
}

function listedWidgetValues(node) {
    return serializedWidgetsInDefOrder(node).map((widget) => widget.value);
}

function liftPerClipTimingValues(names, values) {
    if (!Array.isArray(names) || !Array.isArray(values) || values.length !== names.length) return values;
    const promptI = names.indexOf("prompt");
    const durI = names.indexOf("duration");
    const segI = names.indexOf("segments");
    const loopI = names.indexOf("seamless_loop");
    if (promptI < 0 || durI < 0 || segI < 0 || loopI !== promptI + 1) return values;
    if (typeof values[promptI + 1] !== "number" || typeof values[promptI + 2] !== "number") return values;
    const loopVal = values[promptI + 3];
    if (loopVal !== true && loopVal !== false && loopVal !== 0 && loopVal !== 1) return values;
    const duration = values[promptI + 1];
    const segments = values[promptI + 2];
    const next = values.slice();
    next.splice(promptI + 1, 2);
    next.splice(durI, 0, duration);
    next.splice(segI, 0, segments);
    return next;
}

function dropDomWidgetValue(node, values) {
    if (!Array.isArray(values)) return values;
    const expected = serializedWidgetsInDefOrder(node);
    if (!expected.length) return values;
    const names = expected.map((widget) => widget.name);
    let next = values.slice();
    const promptIndex = names.indexOf("prompt");
    while (next.length > expected.length && promptIndex >= 0) {
        next.splice(promptIndex + 1, 1);
    }
    if (next.length > expected.length) next = next.slice(0, expected.length);
    if (next.length === expected.length) next = liftPerClipTimingValues(names, next);
    return next;
}

function linkedBuilder(node) {
    const slot = node.inputs?.find((item) => item?.name === "pack");
    if (!slot?.link || !node.graph) return null;
    const links = node.graph.links ?? node.graph._links;
    const link = typeof links?.get === "function" ? links.get(slot.link) : links?.[slot.link];
    const origin = node.graph.getNodeById?.(link?.origin_id ?? link?.[0]);
    if (!origin) return null;
    const names = new Set([
        origin.type, origin.comfyClass, origin.constructor?.type, origin.constructor?.comfyClass,
    ].filter(Boolean));
    return names.has("H3StudioBuilder") ? origin : null;
}

function findWidget(node, name) {
    return node?.widgets?.find((widget) => widget?.name === name);
}

function visualNodeHeight(node) {
    const sizeH = Array.isArray(node?.size) ? Number(node.size[1]) : 0;
    if (Number.isFinite(sizeH) && sizeH > 0) return sizeH;
    const rendered = node?.renderingSize;
    const renderedH = Array.isArray(rendered) ? Number(rendered[1]) : 0;
    const body = Number(node?.bodyHeight);
    return Math.max(renderedH || 0, body || 0);
}

function isCollapsedLayoutWidget(widget) {
    if (!widget || widget.hidden || widget.type === "hidden") return true;
    const name = String(widget.name || "");
    if (name === "prompt" || name === "prompt_mode" || name === "loop_prompt") return true;
    if (name === "h3_prompt_mentions") return true;
    if (/^prompt_\d+$/.test(name)) return true;
    return false;
}

function widgetLayoutHeight(widget) {
    if (isCollapsedLayoutWidget(widget)) return 0;
    if (typeof widget.computeSize === "function") {
        const size = widget.computeSize(200);
        const h = Array.isArray(size) ? Number(size[1]) : Number(size);
        if (Number.isFinite(h) && h <= 0) return 0;
        if (Number.isFinite(h) && h > 0) return h;
    }
    const computed = Number(widget.computedHeight);
    if (Number.isFinite(computed) && computed > 0) return computed;
    return Math.max(globalThis.LiteGraph?.NODE_WIDGET_HEIGHT || 20, 28);
}

function trailingWidgetsHeight(node, dom) {
    const widgets = node?.widgets || [];
    const idx = widgets.indexOf(dom);
    if (idx < 0) return 0;
    let height = 0;
    for (let i = idx + 1; i < widgets.length; i++) height += widgetLayoutHeight(widgets[i]);
    return height;
}

function promptMinHeight(node) {
    const extra = isAdvancedPromptNode(node) ? PROMPT_HOST_CHROME : 0;
    const picks = isAdvancedPromptNode(node) && promptMode(node) === "per_clip" ? CLIP_PICKS_HEIGHT : 0;
    return DEFAULT_PROMPT_HEIGHT + extra + picks;
}

function remainingPromptHeight(node, dom) {
    const nodeHeight = visualNodeHeight(node);
    const y = Number(dom?.y ?? dom?.last_y);
    const after = trailingWidgetsHeight(node, dom);
    const min = Math.max(MIN_PROMPT_HEIGHT, promptMinHeight(node));
    if (Number.isFinite(y) && y > 0 && y < nodeHeight) {
        return Math.max(min, Math.floor(nodeHeight - y - after));
    }
    return min;
}

function widgetsHeightBefore(node, dom) {
    const widgets = node?.widgets || [];
    const end = widgets.indexOf(dom);
    const last = end < 0 ? widgets.length : end;
    let height = 0;
    for (let i = 0; i < last; i++) height += widgetLayoutHeight(widgets[i]);
    return height;
}

function fittingPromptNodeHeight(node) {
    const dom = node.__h3DomWidget;
    const promptH = promptMinHeight(node);
    const after = trailingWidgetsHeight(node, dom);
    const above = widgetsHeightBefore(node, dom);
    return Math.ceil(NODE_BODY_CHROME + above + promptH + after);
}

function isProgressWidget(widget) {
    const name = String(widget?.name || "");
    const type = String(widget?.type || "");
    return name === PROGRESS_WIDGET_NAME || type === "progressText";
}

function pinProgressWidget(widget) {
    if (!widget) return;
    if (!widget.__h3PinnedProgress) {
        widget.__h3PinnedProgress = true;
        widget.hasLayoutSize = false;
        widget.options ||= {};
        widget.options.getMinHeight = () => PROGRESS_HEIGHT;
        widget.options.getMaxHeight = () => PROGRESS_HEIGHT;
        widget.computeLayoutSize = function () {
            return { minHeight: PROGRESS_HEIGHT, maxHeight: PROGRESS_HEIGHT, minWidth: 0 };
        };
        widget.computeSize = function () {
            return [200, PROGRESS_HEIGHT];
        };
    }
    widget.computedHeight = PROGRESS_HEIGHT;
    const el = widget.element;
    el?.classList?.add("h3-studio-progress-pin");
    const overlay = el?.closest?.(".dom-widget") || (el?.classList?.contains("dom-widget") ? el : null);
    overlay?.classList?.add("h3-studio-progress-pin");
    if (overlay?.style) {
        overlay.style.height = `${PROGRESS_HEIGHT}px`;
        overlay.style.maxHeight = `${PROGRESS_HEIGHT}px`;
    }
}

function pinProgressWidgets(node) {
    for (const widget of node?.widgets || []) {
        if (isProgressWidget(widget)) pinProgressWidget(widget);
    }
}

function installProgressPin(node) {
    if (!node || node.__h3ProgressPin) return;
    node.__h3ProgressPin = true;
    const original = node.addCustomWidget;
    if (typeof original === "function") {
        node.addCustomWidget = function (widget, ...rest) {
            const result = original.call(this, widget, ...rest);
            pinProgressWidgets(this);
            return result;
        };
    }
    pinProgressWidgets(node);
}

function promptWidgetsGrid(wrap) {
    return wrap?.closest?.("[data-testid='node-widgets'], .lg-node-widgets") || null;
}

function promptWidgetRow(wrap) {
    return wrap?.closest?.("[data-testid='node-widget'], .lg-node-widget") || null;
}

function pinPromptGrid(wrap) {
    const grid = promptWidgetsGrid(wrap);
    if (!grid) return;
    const row = promptWidgetRow(wrap);
    let rows = [...grid.children].filter((el) => (
        el.matches?.("[data-testid='node-widget'], .lg-node-widget")
    ));
    if (!rows.length) {
        rows = [...grid.querySelectorAll(":scope > [data-testid='node-widget'], :scope > .lg-node-widget")];
    }
    const idx = row ? rows.indexOf(row) : -1;
    const host = wrap?.closest?.(".h3-studio-prompt-host");
    const fieldCount = host?.querySelectorAll?.(".h3-studio-prompt-field")?.length || 0;
    const picksOn = Boolean(host?.querySelector?.(".h3-studio-clip-picks:not([hidden])"));
    const min = host
        ? (fieldCount > 1
            ? PROMPT_HOST_CHROME + fieldCount * PER_CLIP_FIELD_HEIGHT
            : DEFAULT_PROMPT_HEIGHT + PROMPT_HOST_CHROME + (picksOn ? CLIP_PICKS_HEIGHT : 0))
        : DEFAULT_PROMPT_HEIGHT;
    const template = rows.map((_, i) => (i === idx ? `minmax(${min}px, 1fr)` : "min-content")).join(" ");
    if (template && grid.style.getPropertyValue("grid-template-rows") !== template) {
        grid.style.setProperty("grid-template-rows", template, "important");
    }
    grid.style.flex = "1 1 auto";
    grid.style.minHeight = "0px";
}

function bindPromptWidgetSize(widget, node) {
    if (!widget) return;
    const min = () => promptMinHeight(node);
    widget.options ||= {};
    widget.options.getMinHeight = min;
    widget.options.getHeight = min;
    widget.options.getMaxHeight = () => 1e6;
    widget.hasLayoutSize = true;
    if (Object.hasOwn(widget, "computeSize")) delete widget.computeSize;
    widget.computeLayoutSize = function () {
        return { minHeight: min(), maxHeight: 1e6, minWidth: 0 };
    };
}

function syncPromptWidget(node, widget) {
    const dom = widget || node.__h3DomWidget;
    const wrap = node.__h3PromptHost || node.__h3EditorWrap;
    if (!dom || !wrap) return;
    pinProgressWidgets(node);
    bindPromptWidgetSize(dom, node);
    const fill = remainingPromptHeight(node, dom);
    if (Number.isFinite(fill) && fill > 0) dom.computedHeight = fill;
    wrap.style.flex = "1 1 auto";
    wrap.style.width = "100%";
    wrap.style.minHeight = "0px";
    wrap.style.height = "100%";
    pinPromptGrid(node.__h3PromptHost || wrap);
    applyNativeEditorTheme(wrap);
}

function installPromptSizeGuard(node) {
    if (!node || node.__h3PromptSizeGuard) return;
    node.__h3PromptSizeGuard = true;
    installPromptSizeLock(node);
    installSizeWatch(node);
    const previousResize = node.onResize;
    node.onResize = function (...args) {
        const result = previousResize?.apply(this, args);
        if (!this.__h3GrowingSize && !this.__h3SizeHold) {
            const size = snapshotVisualSize(this);
            if (this.__h3UserResizing) {
                if (size) captureKeptSize(this, size, true);
            } else if (this.__h3KeepSize && cssContentHeight(this) < this.__h3KeepSize[1] - 8) {
                restoreKeptPromptNodeSize(this);
            } else if (size && this.__h3KeepSize && size[1] < this.__h3KeepSize[1] - 8) {
                restoreKeptPromptNodeSize(this);
            } else if (size) {
                captureKeptSize(this, size);
            }
        }
        syncPromptWidget(this, this.__h3DomWidget);
        return result;
    };
}

function isRawView(node) {
    const editor = node.__h3Editor;
    if (editor && Object.prototype.hasOwnProperty.call(editor, "__h3RawView")) {
        return Boolean(editor.__h3RawView);
    }
    return String(node?.properties?.[VIEW_PROP] || "") === "raw";
}

function setRawView(node, raw) {
    if (node.__h3Editor) node.__h3Editor.__h3RawView = !!raw;
    node.properties ||= {};
    node.properties[VIEW_PROP] = raw ? "raw" : "structured";
}

function mentionToken(kind, index, segment) {
    const n = Number(index);
    const s = Math.max(1, Number(segment) || 1);
    return s > 1 ? `<${kind} ${n}:${s}>` : `<${kind} ${n}>`;
}

function parseTag(token) {
    const match = String(token || "").match(TAG_RE);
    if (!match) return null;
    const kind = match[1][0].toUpperCase() + match[1].slice(1).toLowerCase();
    const index = Number(match[2]);
    const segment = Math.max(1, Number(match[3]) || 1);
    return { kind, index, segment, token: mentionToken(kind, index, segment) };
}

function serializeEditor(editor) {
    let text = "";
    const walk = (node) => {
        if (node.nodeType === Node.TEXT_NODE) {
            const skip = node.parentElement?.closest?.(".h3-mention-chip, .h3-dialogue-flag");
            if (skip) return;
            text += String(node.nodeValue || "").replace(/\u200b/g, "");
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (node.classList?.contains("h3-caret-sink")) {
            text += String(node.textContent || "").replace(/\u200b/g, "");
            return;
        }
        if (node.classList?.contains("h3-mention-chip")) {
            text += node.dataset.token || "";
            return;
        }
        if (node.classList?.contains("h3-dialogue-flag")) return;
        if (node.classList?.contains(DIALOGUE_CLASS)) {
            text += `<d>${wrapDialogueInner(node)}</d>`;
            return;
        }
        if (node.tagName === "BR") {
            text += "\n";
            return;
        }
        if (node.tagName === "DIV" || node.tagName === "P") {
            if (text && !text.endsWith("\n")) text += "\n";
            const kids = [...node.childNodes];
            const dummyBr = kids[0]?.nodeName === "BR" && kids.some((child, index) => (
                index > 0 && !isEmptyText(child) && (isChipNode(child) || isCaretSink(child) || child.nodeName === "BR"
                    || (child.nodeType === Node.TEXT_NODE && String(child.nodeValue || "").replace(/\u200b/g, "")))
            ));
            for (const child of kids) {
                if (dummyBr && child === kids[0]) continue;
                walk(child);
            }
            return;
        }
    };
    walk(editor);
    return text.replace(/\u00a0/g, " ").replace(/\u200b/g, "");
}

function serializeRange(range) {
    if (!range || range.collapsed) return "";
    const holder = document.createElement("div");
    holder.appendChild(range.cloneContents());
    return serializeEditor(holder);
}

function expandRangeToChips(range) {
    if (!range) return range;
    const startChip = range.startContainer.nodeType === Node.ELEMENT_NODE
        ? range.startContainer.closest?.(".h3-mention-chip")
        : range.startContainer.parentElement?.closest?.(".h3-mention-chip");
    const endChip = range.endContainer.nodeType === Node.ELEMENT_NODE
        ? range.endContainer.closest?.(".h3-mention-chip")
        : range.endContainer.parentElement?.closest?.(".h3-mention-chip");
    if (startChip) range.setStartBefore(startChip);
    if (endChip) range.setEndAfter(endChip);
    return range;
}

function editorSelectionRange(editor) {
    const selection = window.getSelection?.();
    if (!selection?.rangeCount || !editor) return null;
    const range = selection.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer) && range.commonAncestorContainer !== editor) return null;
    return range;
}

function kindKey(kind) {
    return normalizeKind(kind);
}

const ICON_THUMB_TEMPLATES = new Map();
let chipThumbObserver = null;

function iconThumb(kind, className) {
    const key = `${className}:${kind || "image"}`;
    let template = ICON_THUMB_TEMPLATES.get(key);
    if (!template) {
        template = document.createElement("span");
        template.className = `${className} h3-kind-${kind || "image"}`;
        template.setAttribute("aria-hidden", "true");
        template.innerHTML = kindIconSvg(kind);
        ICON_THUMB_TEMPLATES.set(key, template);
    }
    return template.cloneNode(true);
}

function ensureChipThumbObserver() {
    if (chipThumbObserver || typeof IntersectionObserver !== "function") return chipThumbObserver;
    chipThumbObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            chipThumbObserver.unobserve(entry.target);
            hydrateChipThumb(entry.target);
        }
    }, { rootMargin: "160px" });
    return chipThumbObserver;
}

function attachThumbImage(wrap, item, menu) {
    const img = document.createElement("img");
    img.src = item.thumb;
    img.alt = "";
    img.draggable = false;
    img.loading = "lazy";
    img.decoding = "async";
    wrap.replaceChildren(img);
    img.addEventListener("error", () => {
        wrap.replaceWith(makeThumb({ ...item, thumb: "" }, menu));
    }, { once: true });
    if (hasImageCrop(item)) applyCropThumb(img, item.crop);
}

function hydrateChipThumb(wrap) {
    const url = wrap?.dataset?.thumb;
    if (!url || !wrap.isConnected) return;
    let crop = null;
    try {
        crop = wrap.dataset.crop ? JSON.parse(wrap.dataset.crop) : null;
    } catch {
        crop = null;
    }
    delete wrap.dataset.thumb;
    delete wrap.dataset.crop;
    attachThumbImage(wrap, { kind: "Picture", thumb: url, crop }, false);
}

function observeChipThumb(wrap) {
    const observer = ensureChipThumbObserver();
    if (observer) observer.observe(wrap);
    else hydrateChipThumb(wrap);
}

function makeThumb(item, menu) {
    const className = menu ? "h3-mention-menu-thumb" : "h3-mention-chip-thumb";
    const kind = kindKey(item?.kind);
    if (kind === "image" && item?.thumb) {
        const wrap = document.createElement("span");
        wrap.className = `${className} h3-kind-image`;
        if (menu) {
            attachThumbImage(wrap, item, true);
            return wrap;
        }
        wrap.dataset.thumb = item.thumb;
        if (hasImageCrop(item)) wrap.dataset.crop = JSON.stringify(item.crop);
        wrap.appendChild(iconThumb("image", className));
        observeChipThumb(wrap);
        return wrap;
    }
    return iconThumb(kind, className);
}

function fillMenuButton(btn, spec) {
    if (!spec.kind && !spec.thumb) {
        btn.textContent = spec.label;
        return;
    }
    btn.classList.add("h3-mention-menu-row");
    const text = document.createElement("span");
    text.className = "h3-mention-menu-label";
    text.textContent = spec.label;
    if (spec.detail) {
        const detail = document.createElement("span");
        detail.className = "h3-mention-menu-detail";
        detail.textContent = spec.detail;
        const wrap = document.createElement("span");
        wrap.append(text, detail);
        btn.append(makeThumb(spec, true), wrap);
        return;
    }
    btn.append(makeThumb(spec, true), text);
}

function chipFor(item) {
    const span = document.createElement("span");
    span.className = "h3-mention-chip";
    span.contentEditable = "false";
    const segment = Math.max(1, Number(item.segment) || 1);
    span.dataset.token = item.token || mentionToken(item.kind, item.index, segment);
    span.dataset.kind = item.kind;
    span.dataset.index = String(item.index);
    span.dataset.segment = String(segment);
    const label = document.createElement("span");
    label.textContent = `@${item.kind} ${item.index}`;
    span.append(makeThumb(item, false), label);
    if ((item.kind === "Video" || item.kind === "Audio") && Number(item.segmentCount || segment) > 1) {
        const badge = document.createElement("span");
        badge.className = "h3-mention-chip-seg";
        badge.textContent = String(segment);
        span.append(badge);
    }
    return span;
}

function fillPlain(editor, text) {
    const frag = document.createDocumentFragment();
    String(text || "").split("\n").forEach((line, index) => {
        if (index) frag.appendChild(document.createElement("br"));
        if (line) frag.appendChild(document.createTextNode(line));
    });
    editor.replaceChildren(frag);
}

function inventoryIndex(inventory) {
    if (inventory instanceof Map) return inventory;
    const map = new Map();
    for (const item of inventory || []) {
        if (!item?.kind || item.index == null) continue;
        map.set(`${item.kind}:${item.index}`, item);
    }
    return map;
}

function lookupInventoryItem(inventory, tag) {
    if (!tag) return tag;
    const key = `${tag.kind}:${tag.index}`;
    if (inventory instanceof Map) return inventory.get(key) || tag;
    if (Array.isArray(inventory)) {
        return inventory.find((entry) => entry.kind === tag.kind && entry.index === tag.index) || tag;
    }
    return tag;
}

function appendChip(host, tag, inventory) {
    const item = lookupInventoryItem(inventory, tag);
    const chip = chipFor({
        ...item, ...tag, token: tag.token, segment: tag.segment,
        segmentCount: item.segmentCount || tag.segment,
    });
    if (needsCaretSinkFrom(host.lastChild)) host.appendChild(makeCaretSink());
    host.appendChild(chip);
    return chip;
}

function fillEditor(editor, text, inventory) {
    const lookup = inventoryIndex(inventory);
    const frag = document.createDocumentFragment();
    const parts = String(text || "").split(PART_RE);
    for (const part of parts) {
        if (!part) continue;
        const dialogue = parseDialoguePart(part);
        if (dialogue != null) {
            frag.appendChild(makeDialogueBlock(dialogue, lookup));
            continue;
        }
        const tag = parseTag(part);
        if (!tag) {
            fillPlainChunk(frag, part);
            continue;
        }
        appendChip(frag, tag, lookup);
    }
    editor.replaceChildren(frag);
    repairCaretSinks(editor);
}

function fillPlainChunk(editor, text) {
    String(text || "").split("\n").forEach((line, index) => {
        if (index) editor.appendChild(document.createElement("br"));
        if (line) editor.appendChild(document.createTextNode(line));
    });
}

function parseDialoguePart(part) {
    const match = String(part || "").match(/^<d>([\s\S]*?)<\/d>$/i);
    return match ? match[1] : null;
}

function isDialogueBlock(node) {
    return node?.nodeType === Node.ELEMENT_NODE && node.classList?.contains(DIALOGUE_CLASS);
}

function isDialogueFlag(node) {
    return node?.nodeType === Node.ELEMENT_NODE && node.classList?.contains("h3-dialogue-flag");
}

function canonicalLanguage(name) {
    const clean = String(name || "").replace(/[\[\]]/g, "").trim() || "English";
    const known = DIALOGUE_LANGUAGES.find((item) => item.name.toLowerCase() === clean.toLowerCase());
    return known?.name || clean;
}

function languageCode(name) {
    const language = canonicalLanguage(name);
    const known = DIALOGUE_LANGUAGES.find((item) => item.name === language);
    if (known?.code) return known.code;
    const letters = language.replace(/[^\p{L}\p{N}]+/gu, "");
    return (letters.slice(0, 2) || "?").toUpperCase();
}

function setFlagGlyph(el, language) {
    let glyph = el.querySelector?.(".h3-dialogue-flag-glyph");
    if (!glyph) {
        glyph = document.createElement("span");
        glyph.className = "h3-dialogue-flag-glyph";
        el.replaceChildren(glyph);
    }
    glyph.textContent = languageCode(language);
}

function parseDialogueLanguage(text) {
    const raw = String(text || "");
    const match = raw.match(DIALOGUE_LANG_RE);
    if (!match) return { language: "English", body: raw };
    return { language: canonicalLanguage(match[1]), body: raw.slice(match[0].length) };
}

function dialogueLanguage(block) {
    return canonicalLanguage(block?.dataset?.language || "English");
}

function dialogueLanguagePrefix(block) {
    return `[${dialogueLanguage(block)}] `;
}

function firstDialogueBodyNode(block) {
    for (const child of block?.childNodes || []) {
        if (isDialogueFlag(child)) continue;
        return child;
    }
    return null;
}

function dialogueBlockBody(block) {
    let text = "";
    const walk = (node) => {
        if (isDialogueFlag(node) || node.parentElement?.closest?.(".h3-dialogue-flag")) return;
        if (node.nodeType === Node.TEXT_NODE) {
            text += String(node.nodeValue || "").replace(/\u200b/g, "");
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (node.classList?.contains("h3-mention-chip")) {
            text += node.dataset.token || "";
            return;
        }
        if (node.tagName === "BR") {
            text += "\n";
            return;
        }
        for (const child of node.childNodes) walk(child);
    };
    for (const child of block?.childNodes || []) walk(child);
    return text;
}

function wrapDialogueInner(block) {
    return `${dialogueLanguagePrefix(block)}${dialogueBlockBody(block)}`;
}

function applyDialogueLanguage(block, language) {
    const name = canonicalLanguage(language);
    block.dataset.language = name;
    let flag = [...block.childNodes].find(isDialogueFlag);
    if (!flag) {
        flag = document.createElement("button");
        flag.type = "button";
        flag.className = "h3-dialogue-flag";
        flag.contentEditable = "false";
        flag.tabIndex = -1;
        flag.draggable = false;
        block.insertBefore(flag, block.firstChild);
    }
    if (block.firstChild !== flag) block.insertBefore(flag, block.firstChild);
    flag.dataset.language = name;
    flag.title = name;
    flag.setAttribute("aria-label", `${name} dialogue`);
    setFlagGlyph(flag, name);
}

function makeDialogueBlock(value = "", inventory = []) {
    const parsed = parseDialogueLanguage(value);
    const block = document.createElement("span");
    block.className = DIALOGUE_CLASS;
    block.spellcheck = false;
    block.dataset.dialogue = "true";
    applyDialogueLanguage(block, parsed.language);
    const lookup = inventoryIndex(inventory);
    const parts = String(parsed.body || "").split(TOKEN_RE);
    for (const part of parts) {
        if (!part) continue;
        const tag = parseTag(part);
        if (!tag) {
            fillPlainChunk(block, part);
            continue;
        }
        appendChip(block, tag, lookup);
    }
    ensureDialogueInnerCaret(block);
    return block;
}

function ensureDialogueInnerCaret(block) {
    if (!block || dialogueBlockBody(block)) return;
    if (![...block.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && String(node.nodeValue || ""))) {
        block.appendChild(document.createTextNode(CARET_SINK));
    }
}

function dialogueBlockAtRange(range) {
    if (!range) return null;
    const node = range.startContainer;
    const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return el?.closest?.(`.${DIALOGUE_CLASS}`) || null;
}

function setCaretInNode(node, atEnd) {
    if (!node) return false;
    if (isDialogueBlock(node) && !atEnd) {
        const start = firstDialogueBodyNode(node);
        if (start?.nodeType === Node.TEXT_NODE) return setCaret(start, 0);
        if (start) return setCaretInNode(start, false);
        return setCaret(node, node.childNodes.length);
    }
    if (atEnd) {
        let target = node;
        while (target.lastChild) target = target.lastChild;
        if (isDialogueFlag(target)) return setCaret(node, node.childNodes.length);
        if (target.nodeType === Node.TEXT_NODE) return setCaret(target, String(target.nodeValue || "").length);
        return setCaret(node, node.childNodes.length);
    }
    const first = node.firstChild;
    if (first?.nodeType === Node.TEXT_NODE) return setCaret(first, 0);
    return setCaret(node, 0);
}

function caretAtDialogueBodyStart(range, block) {
    if (!range?.collapsed || !block) return false;
    const node = range.startContainer;
    if (isDialogueFlag(node) || node.parentElement?.closest?.(".h3-dialogue-flag")) return true;
    const pre = document.createRange();
    try {
        pre.selectNodeContents(block);
        pre.setEnd(range.startContainer, range.startOffset);
    } catch {
        return false;
    }
    const holder = document.createElement("div");
    holder.appendChild(pre.cloneContents());
    let text = "";
    const walk = (child) => {
        if (isDialogueFlag(child) || child.parentElement?.closest?.(".h3-dialogue-flag")) return;
        if (child.nodeType === Node.TEXT_NODE) {
            text += String(child.nodeValue || "").replace(/\u200b/g, "");
            return;
        }
        if (child.nodeType !== Node.ELEMENT_NODE) return;
        if (child.classList?.contains("h3-mention-chip")) {
            text += child.dataset.token || "x";
            return;
        }
        if (child.tagName === "BR") {
            text += "\n";
            return;
        }
        for (const next of child.childNodes) walk(next);
    };
    for (const child of holder.childNodes) walk(child);
    return !text;
}

function exitDialogueBlock(editor, block) {
    if (!editor || !block?.parentNode) return;
    editor.focus({ preventScroll: true });
    let next = block.nextSibling;
    while (isEmptyText(next)) next = next.nextSibling;
    const chip = skipSink(next);
    if (isChipNode(chip)) {
        ensureCaretSink(chip);
        const sink = isCaretSink(chip.previousSibling) ? chip.previousSibling : null;
        if (sink && setCaret(sink.firstChild || sink, 0)) return;
    }
    if (next?.nodeType === Node.TEXT_NODE) {
        const raw = String(next.nodeValue || "");
        if (raw === CARET_SINK) {
            setCaret(next, raw.length);
            return;
        }
        if (raw.replace(/\u200b/g, "")) {
            setCaret(next, 0);
            return;
        }
    }
    const marker = document.createTextNode(CARET_SINK);
    block.parentNode.insertBefore(marker, block.nextSibling);
    setCaret(marker, marker.nodeValue.length);
}

function insertDialogueBlockAtSelection(node, editor) {
    const range = editorSelectionRange(editor);
    if (!range || !editor) return false;
    if (dialogueBlockAtRange(range)) return false;
    range.deleteContents();
    const block = makeDialogueBlock("");
    range.insertNode(block);
    if (!block.nextSibling || isEmptyText(block.nextSibling)) {
        block.after(document.createTextNode(CARET_SINK));
    }
    editor.focus({ preventScroll: true });
    setCaretInNode(block, true);
    closeMenus();
    return true;
}

function insertDialogueLineBreak(editor, range) {
    range.deleteContents();
    const br = document.createElement("br");
    range.insertNode(br);
    const marker = document.createTextNode(CARET_SINK);
    br.after(marker);
    return setCaret(marker, 1);
}

function removeDialogueBlock(block) {
    if (!block?.parentNode) return false;
    const parent = block.parentNode;
    const index = [...parent.childNodes].indexOf(block);
    block.remove();
    setCaret(parent, Math.min(index, parent.childNodes.length));
    return true;
}

function deleteLastDialogueContent(block) {
    const leaves = [];
    const visit = (node) => {
        if (isDialogueFlag(node)) return;
        if (node.nodeType === Node.TEXT_NODE) {
            leaves.push(node);
            return;
        }
        if (node.nodeType === Node.ELEMENT_NODE && node.tagName === "BR") {
            leaves.push(node);
            return;
        }
        if (isChipNode(node)) {
            leaves.push(node);
            return;
        }
        for (const child of node.childNodes || []) visit(child);
    };
    for (const child of block.childNodes || []) visit(child);
    for (let i = leaves.length - 1; i >= 0; i -= 1) {
        const leaf = leaves[i];
        if (leaf.nodeType === Node.TEXT_NODE) {
            const text = String(leaf.nodeValue || "").replace(/\u200b/g, "");
            if (text) {
                leaf.nodeValue = String(leaf.nodeValue || "").replace(/\u200b/g, "").slice(0, -1);
                if (!leaf.nodeValue) leaf.remove();
                ensureDialogueInnerCaret(block);
                setCaretInNode(block, true);
                return true;
            }
            if (!String(leaf.nodeValue || "").replace(/\u200b/g, "")) leaf.remove();
            continue;
        }
        if (isChipNode(leaf) || leaf.nodeName === "BR") {
            leaf.remove();
            ensureDialogueInnerCaret(block);
            setCaretInNode(block, true);
            return true;
        }
    }
    ensureDialogueInnerCaret(block);
    setCaretInNode(block, true);
    return false;
}

function dialogueBeforeRange(range) {
    if (!range?.collapsed) return null;
    const node = range.startContainer;
    const offset = range.startOffset;
    if (dialogueBlockAtRange(range)) return null;
    let prev;
    if (node.nodeType === Node.TEXT_NODE) {
        if (offset > 0 && !isEmptyText(node)) return null;
        prev = prevSignificant(node);
    } else {
        prev = node.childNodes[offset - 1];
        while (isEmptyText(prev)) prev = prev.previousSibling;
    }
    if (isCaretSink(prev)) prev = prevSignificant(prev);
    return isDialogueBlock(prev) ? prev : null;
}

function isChipNode(node) {
    return node?.nodeType === Node.ELEMENT_NODE && node.classList?.contains("h3-mention-chip");
}

function isCaretSink(node) {
    return node?.nodeType === Node.ELEMENT_NODE && node.classList?.contains("h3-caret-sink");
}

function sinkFrom(node) {
    if (isCaretSink(node)) return node;
    if (node?.nodeType === Node.TEXT_NODE && isCaretSink(node.parentNode)) return node.parentNode;
    return null;
}

function isEmptyText(node) {
    return node?.nodeType === Node.TEXT_NODE && !String(node.nodeValue || "").length;
}

function prevSignificant(node) {
    let cur = node?.previousSibling;
    while (isEmptyText(cur)) cur = cur.previousSibling;
    return cur;
}

function nextSignificant(node) {
    let cur = node?.nextSibling;
    while (isEmptyText(cur)) cur = cur.nextSibling;
    return cur;
}

function skipSink(node) {
    let cur = node;
    while (isEmptyText(cur)) cur = cur.nextSibling;
    if (isCaretSink(cur)) {
        cur = cur.nextSibling;
        while (isEmptyText(cur)) cur = cur.nextSibling;
    }
    return cur;
}

function linePrev(chip) {
    let prev = prevSignificant(chip);
    if (isCaretSink(prev)) prev = prevSignificant(prev);
    return prev;
}

function textEndsWithBreak(node) {
    const value = String(node?.nodeValue || "");
    return node?.nodeType === Node.TEXT_NODE && /(?:\r\n|\n|\r|\u2028)$/.test(value);
}

function breakSuffixLength(value) {
    const text = String(value || "");
    if (text.endsWith("\r\n")) return 2;
    if (/(?:\n|\r|\u2028)$/.test(text)) return 1;
    return 0;
}

function needsCaretSinkFrom(prev) {
    return !prev || prev.nodeName === "BR" || isChipNode(prev) || textEndsWithBreak(prev);
}

function makeCaretSink() {
    const sink = document.createElement("span");
    sink.className = "h3-caret-sink";
    sink.setAttribute("aria-hidden", "true");
    sink.textContent = CARET_SINK;
    return sink;
}

function ensureCaretSink(chip) {
    if (!chip?.parentNode) return;
    if (isCaretSink(prevSignificant(chip))) return;
    if (!needsCaretSinkFrom(prevSignificant(chip))) return;
    chip.parentNode.insertBefore(makeCaretSink(), chip);
}

function caretSinkChip(range) {
    if (!range?.collapsed) return null;
    const sink = sinkFrom(range.startContainer);
    if (sink && isChipNode(nextSignificant(sink))) return nextSignificant(sink);
    if (range.startContainer.nodeType === Node.ELEMENT_NODE) {
        const child = skipSink(range.startContainer.childNodes[range.startOffset]);
        if (isChipNode(child) && isCaretSink(prevSignificant(child))) return child;
    }
    return null;
}

function flattenEditorBlocks(editor) {
    const blocks = [...editor.querySelectorAll("div, p")].reverse();
    for (const block of blocks) {
        if (isCaretSink(block) || block.classList?.contains("h3-mention-chip") || isDialogueBlock(block)) continue;
        if (block.closest(".h3-mention-chip, .h3-dialogue-block")) continue;
        const parent = block.parentNode;
        if (!parent) continue;
        const prev = prevSignificant(block);
        const needBreak = prev && prev.nodeName !== "BR" && !textEndsWithBreak(prev);
        let lead = block.firstChild;
        while (isEmptyText(lead)) lead = lead.nextSibling;
        if (lead?.nodeName === "BR") lead.remove();
        if (needBreak) parent.insertBefore(document.createTextNode("\n"), block);
        while (block.firstChild) parent.insertBefore(block.firstChild, block);
        block.remove();
    }
}

function repairCaretSinks(editor) {
    if (!editor) return;
    flattenEditorBlocks(editor);
    for (const sink of [...editor.querySelectorAll(".h3-caret-sink")]) {
        const text = String(sink.textContent || "").replace(/\u200b/g, "");
        if (text) sink.replaceWith(document.createTextNode(text));
    }
    for (const chip of editor.querySelectorAll(".h3-mention-chip")) ensureCaretSink(chip);
    for (const sink of [...editor.querySelectorAll(".h3-caret-sink")]) {
        if (!isChipNode(nextSignificant(sink)) || !needsCaretSinkFrom(prevSignificant(sink))) sink.remove();
    }
}

function promptText(node) {
    const editor = node.__h3Editor;
    if (typeof editor?.__h3GetValue === "function") return String(editor.__h3GetValue() || "");
    if (typeof node?.__h3GetPromptText === "function") return String(node.__h3GetPromptText() || "");
    return String(findWidget(node, "prompt")?.value || "");
}

function setPromptText(node, text) {
    const next = String(text ?? "");
    const editor = node.__h3Editor;
    if (typeof editor?.__h3SetValue === "function") {
        editor.__h3SetValue(next);
        return;
    }
    if (typeof node?.__h3SetPromptText === "function") {
        node.__h3SetPromptText(next);
        return;
    }
    const widget = findWidget(node, "prompt");
    if (widget) widget.value = next;
}

function collectedInventory(node, source) {
    const fromBuilder = source ? builderInventory(source).map((item) => (
        source === node ? item : { ...item, builder: source }
    )) : [];
    const fromDoc = inventoryFromText(promptText(node));
    const merged = [...fromBuilder];
    for (const item of fromDoc) {
        if (!merged.some((entry) => entry.token === item.token)) merged.push(item);
    }
    return merged;
}

function renderEditor(node) {
    const editor = node.__h3Editor;
    if (!editor) return;
    const text = promptText(node);
    const inventory = node.__h3GetInventory?.() || [];
    if (isRawView(node)) fillPlain(editor, text);
    else fillEditor(editor, text, inventory);
    syncViewButton(node);
}

function inventoryFromText(text) {
    const found = [];
    const seen = new Set();
    for (const match of String(text || "").matchAll(TOKEN_RE)) {
        const tag = parseTag(match[0]);
        if (!tag) continue;
        const key = `${tag.kind}:${tag.index}`;
        if (seen.has(key)) continue;
        seen.add(key);
        found.push(tag);
    }
    return found;
}

function builderInventory(node) {
    const ui = node.__h3BuilderUi;
    const state = ui?.state || { media: [], models: [] };
    const items = [];
    let pic = 0;
    let vid = 0;
    let aud = 0;
    for (const item of state.media || []) {
        if (item?.enabled === false) continue;
        let kind = "";
        let index = 0;
        if (item.kind === "image") {
            pic += 1;
            kind = "Picture";
            index = pic;
        } else if (item.kind === "video") {
            vid += 1;
            kind = "Video";
            index = vid;
        } else if (item.kind === "audio") {
            aud += 1;
            kind = "Audio";
            index = aud;
        } else continue;
        const rel = String(item.path || "").replace(/\\/g, "/");
        const thumb = kind === "Picture" && rel ? (typeof api.apiURL === "function"
            ? api.apiURL(`/h3_studio_builder/file?path=${encodeURIComponent(rel)}`)
            : `/h3_studio_builder/file?path=${encodeURIComponent(rel)}`) : "";
        const segsRaw = Number(findWidget(node, "segments")?.value);
        const nodeSegs = Number.isFinite(segsRaw) ? Math.round(segsRaw) : 1;
        const regionCount = Array.isArray(item.regions) ? item.regions.length : 0;
        const segmentCount = Math.max(1, regionCount || Number(item.segments) || nodeSegs || 1);
        items.push({
            kind, index, token: `<${kind} ${index}>`,
            description: String(item.description || ""),
            thumb, crop: item.crop, media: item, segmentCount,
        });
    }
    let modelN = 0;
    for (const meta of state.models || []) {
        if (meta?.enabled === false) continue;
        modelN += 1;
        items.push({
            kind: "Model", index: modelN, token: `<Model ${modelN}>`,
            description: String(meta.description || ""),
            modelMeta: meta,
        });
    }
    return items;
}

let activeMenu = null;

function closeMenus(opts = {}) {
    const picker = activeMenu?.picker || activeMenu?.mention;
    if (picker && opts.revert && picker.baseline != null) {
        setPromptText(picker.node, picker.baseline);
        renderEditor(picker.node);
    } else if (picker && !picker.finalized && (picker.appliedChip || picker.dirty)) {
        pushHistory(picker.node);
        picker.finalized = true;
    }
    if (activeMenu) {
        document.removeEventListener("pointerdown", activeMenu.pointerdown, true);
        document.removeEventListener("keydown", activeMenu.keydown, true);
        activeMenu.menu.remove();
        activeMenu = null;
    }
    document.querySelectorAll(".h3-mention-menu, .h3-chip-menu").forEach((el) => el.remove());
}

function placeMenu(menu, x, y) {
    menu.style.left = `${Math.max(8, Number(x) || 8)}px`;
    menu.style.top = `${Math.max(8, Number(y) || 8)}px`;
    const rect = menu.getBoundingClientRect();
    if (rect.right > innerWidth - 8) menu.style.left = `${Math.max(8, innerWidth - rect.width - 8)}px`;
    if (rect.bottom > innerHeight - 8) menu.style.top = `${Math.max(8, innerHeight - rect.height - 8)}px`;
}

function openFloatingMenu(x, y, className, build) {
    closeMenus();
    const menu = document.createElement("div");
    menu.className = className;
    menu.setAttribute("role", "menu");
    menu.addEventListener("contextmenu", (event) => event.preventDefault());
    menu.addEventListener("pointerdown", (event) => event.stopPropagation());
    menu.addEventListener("click", (event) => event.stopPropagation());
    build(menu);
    document.body.appendChild(menu);
    placeMenu(menu, x, y);
    const pointerdown = (event) => {
        if (menu.contains(event.target)) return;
        closeMenus();
    };
    const keydown = (event) => {
        if (handlePickerKey(event)) return;
        if (event.key !== "Escape") return;
        event.preventDefault();
        event.stopPropagation();
        closeMenus();
    };
    activeMenu = { menu, pointerdown, keydown };
    document.addEventListener("keydown", keydown, true);
    queueMicrotask(() => {
        if (activeMenu?.menu !== menu) return;
        document.addEventListener("pointerdown", pointerdown, true);
    });
    return menu;
}

function showMenu(x, y, className, buttons) {
    return openFloatingMenu(x, y, className, (menu) => {
        for (const spec of buttons) {
            if (spec.header) {
                const header = document.createElement("div");
                header.className = "h3-mention-menu-row";
                fillMenuButton(header, spec);
                header.style.pointerEvents = "none";
                menu.appendChild(header);
                continue;
            }
            if (spec.picks) {
                const row = document.createElement("div");
                row.className = "h3-chip-menu-picks";
                for (const pick of spec.picks) {
                    const pickBtn = document.createElement("button");
                    pickBtn.type = "button";
                    pickBtn.textContent = pick.label;
                    if (pick.active) pickBtn.classList.add("is-active");
                    pickBtn.addEventListener("pointerdown", (event) => {
                        event.preventDefault();
                        event.stopPropagation();
                    });
                    pickBtn.addEventListener("click", (event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        closeMenus();
                        pick.run?.();
                    });
                    row.appendChild(pickBtn);
                }
                menu.appendChild(row);
                continue;
            }
            const btn = document.createElement("button");
            btn.type = "button";
            btn.setAttribute("role", "menuitem");
            if (spec.danger) btn.classList.add("h3-chip-menu-danger");
            if (spec.disabled) btn.disabled = true;
            fillMenuButton(btn, spec);
            btn.addEventListener("pointerdown", (event) => {
                event.preventDefault();
                event.stopPropagation();
            });
            btn.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (spec.disabled) return;
                if (!spec.keepOpen) closeMenus();
                spec.run?.();
            });
            menu.appendChild(btn);
        }
    });
}

function openDialogueLangMenu(node, block, x, y) {
    const current = dialogueLanguage(block);
    const known = new Set(DIALOGUE_LANGUAGES.map((item) => item.name));
    openFloatingMenu(x, y, "h3-chip-menu h3-dialogue-lang-menu", (menu) => {
        for (const spec of DIALOGUE_LANGUAGES) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.setAttribute("role", "menuitem");
            if (spec.name === current) btn.classList.add("is-active");
            const glyph = document.createElement("span");
            glyph.className = "h3-dialogue-flag-glyph";
            glyph.textContent = spec.code;
            const label = document.createElement("span");
            label.textContent = spec.name;
            btn.append(glyph, label);
            btn.addEventListener("pointerdown", (event) => {
                event.preventDefault();
                event.stopPropagation();
            });
            btn.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                applyDialogueLanguage(block, spec.name);
                closeMenus();
                syncFromEditor(node);
                pushHistory(node);
            });
            menu.appendChild(btn);
        }
        const custom = document.createElement("div");
        custom.className = "h3-dialogue-lang-custom";
        const input = document.createElement("input");
        input.type = "text";
        input.placeholder = "Custom language";
        input.setAttribute("aria-label", "Custom language");
        if (!known.has(current)) input.value = current;
        const apply = document.createElement("button");
        apply.type = "button";
        apply.textContent = "Apply";
        const applyCustom = () => {
            const typed = String(input.value || "").replace(/[\[\]]/g, "").trim();
            if (!typed) return;
            applyDialogueLanguage(block, typed);
            closeMenus();
            syncFromEditor(node);
            pushHistory(node);
        };
        apply.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            event.stopPropagation();
        });
        apply.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            applyCustom();
        });
        input.addEventListener("pointerdown", (event) => event.stopPropagation());
        input.addEventListener("keydown", (event) => {
            event.stopPropagation();
            if (event.key === "Enter") {
                event.preventDefault();
                applyCustom();
            }
        });
        custom.append(input, apply);
        menu.appendChild(custom);
    });
}

function currentPrompt(node) {
    return promptText(node);
}

function ensureHistory(node) {
    const editor = node.__h3Editor;
    if (editor) {
        if (!editor.__h3PromptHistory) {
            editor.__h3PromptHistory = { undo: [currentPrompt(node)], redo: [], applying: false };
        }
        return editor.__h3PromptHistory;
    }
    if (!node.__h3PromptHistory) {
        node.__h3PromptHistory = { undo: [currentPrompt(node)], redo: [], applying: false };
    }
    return node.__h3PromptHistory;
}

function resetHistory(node) {
    const state = { undo: [currentPrompt(node)], redo: [], applying: false };
    if (node.__h3Editor) node.__h3Editor.__h3PromptHistory = state;
    else node.__h3PromptHistory = state;
}

function pushHistory(node) {
    const history = ensureHistory(node);
    if (history.applying) return;
    const text = currentPrompt(node);
    if (text === history.undo[history.undo.length - 1]) return;
    history.undo.push(text);
    if (history.undo.length > 100) history.undo.shift();
    history.redo.length = 0;
}

function applyHistory(node, text) {
    const history = ensureHistory(node);
    const from = currentPrompt(node);
    history.applying = true;
    try {
        setPromptText(node, text);
        renderEditor(node);
        const editor = node.__h3Editor;
        if (editor) placeCaretAtSerializedOffset(editor, caretAfterDiff(from, text));
    } finally {
        history.applying = false;
    }
    node.__h3Editor?.focus?.({ preventScroll: true });
}

function undoHistory(node) {
    const history = ensureHistory(node);
    syncFromEditor(node);
    const current = currentPrompt(node);
    if (history.undo[history.undo.length - 1] !== current) history.undo.push(current);
    if (history.undo.length <= 1) return;
    history.redo.push(history.undo.pop());
    applyHistory(node, history.undo[history.undo.length - 1]);
}

function redoHistory(node) {
    const history = ensureHistory(node);
    const next = history.redo.pop();
    if (next == null) return;
    history.undo.push(next);
    applyHistory(node, next);
}

function isHistoryKey(event) {
    if (!(event?.ctrlKey || event?.metaKey)) return false;
    const key = String(event.key || "").toLowerCase();
    return key === "z" || key === "y" || event.code === "KeyZ" || event.code === "KeyY";
}

function handleHistoryKey(node, event) {
    if (!isHistoryKey(event)) return false;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    const redo = String(event.key || "").toLowerCase() === "y"
        || event.code === "KeyY"
        || (String(event.key || "").toLowerCase() === "z" && event.shiftKey);
    if (redo) redoHistory(node);
    else undoHistory(node);
    return true;
}

function chipItem(item) {
    return chipFor({
        kind: item.kind,
        index: item.index,
        token: item.token,
        thumb: item.thumb,
        crop: item.crop,
        segment: item.segment,
        segmentCount: item.segmentCount,
    });
}

function promptEditors(node) {
    const host = node.__h3PromptHost;
    if (host) {
        const editors = [...host.querySelectorAll(".h3-studio-prompt-editor")];
        if (editors.length) return editors;
    }
    return node.__h3Editor ? [node.__h3Editor] : [];
}

function persistEditor(node, editor) {
    const text = serializeEditor(editor);
    if (typeof editor?.__h3SetValue === "function") editor.__h3SetValue(text);
    else if (editor === node.__h3Editor) setPromptText(node, text);
}

function replaceOneChip(node, chip, item, { history = true } = {}) {
    if (!chip?.isConnected) return null;
    const next = chipItem(item);
    chip.replaceWith(next);
    ensureCaretSink(next);
    syncFromEditor(node);
    if (history) pushHistory(node);
    return next;
}

function replaceChipsByToken(node, token, item, { history = true, keep } = {}) {
    const editors = promptEditors(node);
    if (!editors.length) return null;
    let nextKeep = null;
    const from = parseTag(token);
    for (const editor of editors) {
        const chips = [...editor.querySelectorAll(".h3-mention-chip")].filter((chip) => {
            if (!from) return chip.dataset.token === token;
            return chip.dataset.kind === from.kind && chip.dataset.index === String(from.index);
        });
        if (!chips.length) continue;
        for (const chip of chips) {
            const next = chipItem(item);
            if (keep && chip === keep) nextKeep = next;
            chip.replaceWith(next);
            ensureCaretSink(next);
        }
        persistEditor(node, editor);
    }
    if (history) pushHistory(node);
    return nextKeep;
}

function setCaret(node, offset) {
    const selection = window.getSelection?.();
    if (!selection || !node) return false;
    const caret = document.createRange();
    try {
        caret.setStart(node, Math.max(0, Math.min(offset, node.nodeType === Node.TEXT_NODE ? String(node.nodeValue || "").length : node.childNodes.length)));
    } catch {
        return false;
    }
    caret.collapse(true);
    selection.removeAllRanges();
    selection.addRange(caret);
    return true;
}

function placeCaretAfter(node, chip) {
    const editor = node?.__h3Editor;
    if (!editor || !chip?.isConnected) return;
    editor.focus({ preventScroll: true });
    const selection = window.getSelection?.();
    if (!selection) return;
    const caret = document.createRange();
    caret.setStartAfter(chip);
    caret.collapse(true);
    selection.removeAllRanges();
    selection.addRange(caret);
}

function placeCaretBefore(node, chip) {
    const editor = node?.__h3Editor;
    if (!editor || !chip?.isConnected) return;
    ensureCaretSink(chip);
    editor.focus({ preventScroll: true });
    const sink = prevSignificant(chip);
    if (isCaretSink(sink) && setCaret(sink.firstChild || sink, 0)) return;
    const selection = window.getSelection?.();
    if (!selection) return;
    const caret = document.createRange();
    caret.setStartBefore(chip);
    caret.collapse(true);
    selection.removeAllRanges();
    selection.addRange(caret);
}

function moveCaretBeforeSink(sink) {
    const prev = prevSignificant(sink);
    if (!prev) {
        setCaret(sink.parentNode, 0);
        return;
    }
    if (prev.nodeName === "BR") {
        const last = prevSignificant(prev);
        if (isChipNode(last)) {
            const caret = document.createRange();
            caret.setStartAfter(last);
            caret.collapse(true);
            const selection = window.getSelection?.();
            if (selection) {
                selection.removeAllRanges();
                selection.addRange(caret);
            }
            return;
        }
        if (last?.nodeType === Node.TEXT_NODE) {
            setCaret(last, String(last.nodeValue || "").length);
            return;
        }
        setCaret(prev.parentNode, [...prev.parentNode.childNodes].indexOf(prev));
        return;
    }
    if (isChipNode(prev)) {
        const caret = document.createRange();
        caret.setStartAfter(prev);
        caret.collapse(true);
        const selection = window.getSelection?.();
        if (selection) {
            selection.removeAllRanges();
            selection.addRange(caret);
        }
        return;
    }
    if (prev.nodeType === Node.TEXT_NODE) {
        const text = String(prev.nodeValue || "");
        setCaret(prev, Math.max(0, text.length - breakSuffixLength(text)));
        return;
    }
    setCaret(prev.parentNode, [...prev.parentNode.childNodes].indexOf(prev) + 1);
}

function removeChip(chip) {
    const sink = isCaretSink(prevSignificant(chip)) ? prevSignificant(chip) : null;
    const parent = chip.parentNode;
    const index = [...parent.childNodes].indexOf(sink || chip);
    chip.remove();
    if (sink?.isConnected) sink.remove();
    setCaret(parent, Math.min(index, parent.childNodes.length));
}

function serializedOffsetAtCaret(editor) {
    const range = editorSelectionRange(editor);
    if (!range) return serializeEditor(editor).length;
    const pre = document.createRange();
    pre.selectNodeContents(editor);
    try {
        pre.setEnd(range.startContainer, range.startOffset);
    } catch {
        return serializeEditor(editor).length;
    }
    if (pre.collapsed) return 0;
    return serializeRange(pre).length;
}

function caretAfterDiff(fromText, toText) {
    const from = String(fromText || "");
    const to = String(toText || "");
    let start = 0;
    const limit = Math.min(from.length, to.length);
    while (start < limit && from.charCodeAt(start) === to.charCodeAt(start)) start += 1;
    let fromEnd = from.length;
    let toEnd = to.length;
    while (fromEnd > start && toEnd > start && from.charCodeAt(fromEnd - 1) === to.charCodeAt(toEnd - 1)) {
        fromEnd -= 1;
        toEnd -= 1;
    }
    return toEnd;
}

function placeCaretAtSerializedOffset(editor, offset) {
    if (!editor) return;
    const target = Math.max(0, Number(offset) || 0);
    let seen = 0;
    let placed = false;
    const finish = (node, off) => {
        placed = setCaret(node, off);
    };
    const walk = (node) => {
        if (placed) return;
        if (node.nodeType === Node.TEXT_NODE) {
            if (node.parentElement?.closest?.(".h3-mention-chip, .h3-dialogue-flag")) return;
            const raw = String(node.nodeValue || "");
            const text = raw.replace(/\u200b/g, "");
            if (!text.length) {
                if (seen === target) finish(node, 0);
                return;
            }
            if (seen + text.length >= target) {
                const local = target - seen;
                const placedText = text.slice(0, local);
                const chip = skipSink(node.nextSibling);
                if (placedText.endsWith("\n") && isChipNode(chip)) {
                    ensureCaretSink(chip);
                    const sink = chip.previousSibling;
                    if (isCaretSink(sink)) finish(sink.firstChild || sink, 0);
                    else finish(node, Math.min(raw.length, local));
                    return;
                }
                finish(node, Math.min(raw.length, local));
                return;
            }
            seen += text.length;
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (node.classList?.contains("h3-dialogue-flag")) return;
        if (node.classList?.contains("h3-caret-sink")) {
            if (seen === target) finish(node.firstChild || node, 0);
            return;
        }
        if (node.classList?.contains(DIALOGUE_CLASS)) {
            const prefix = dialogueLanguagePrefix(node);
            const inner = wrapDialogueInner(node);
            const wrapped = `<d>${inner}</d>`;
            if (seen >= target) {
                finish(node.parentNode, [...node.parentNode.childNodes].indexOf(node));
                return;
            }
            if (seen + 3 >= target) {
                setCaretInNode(node, false);
                placed = true;
                return;
            }
            if (seen + 3 + inner.length >= target) {
                const local = target - seen - 3;
                if (local <= prefix.length) {
                    setCaretInNode(node, false);
                    placed = true;
                    return;
                }
                const bodyLocal = local - prefix.length;
                let innerSeen = 0;
                const walkInner = (child) => {
                    if (placed) return;
                    if (isDialogueFlag(child)) return;
                    if (child.nodeType === Node.TEXT_NODE) {
                        const text = String(child.nodeValue || "").replace(/\u200b/g, "");
                        if (innerSeen + text.length >= bodyLocal) {
                            finish(child, Math.min(String(child.nodeValue || "").length, bodyLocal - innerSeen));
                            return;
                        }
                        innerSeen += text.length;
                        return;
                    }
                    if (child.nodeType !== Node.ELEMENT_NODE) return;
                    if (child.tagName === "BR") {
                        if (innerSeen >= bodyLocal) {
                            finish(child.parentNode, [...child.parentNode.childNodes].indexOf(child) + 1);
                            return;
                        }
                        innerSeen += 1;
                        return;
                    }
                    if (isChipNode(child)) {
                        const token = child.dataset.token || "";
                        if (innerSeen + token.length >= bodyLocal) {
                            finish(child.parentNode, [...child.parentNode.childNodes].indexOf(child) + 1);
                            return;
                        }
                        innerSeen += token.length;
                        return;
                    }
                    for (const next of child.childNodes) walkInner(next);
                };
                for (const child of node.childNodes) walkInner(child);
                if (!placed) setCaretInNode(node, true);
                placed = true;
                return;
            }
            if (seen + wrapped.length >= target) {
                finish(node.parentNode, [...node.parentNode.childNodes].indexOf(node) + 1);
                return;
            }
            seen += wrapped.length;
            return;
        }
        if (node.classList?.contains("h3-mention-chip")) {
            const token = node.dataset.token || "";
            if (seen >= target) {
                ensureCaretSink(node);
                const sink = node.previousSibling;
                if (isCaretSink(sink)) finish(sink.firstChild || sink, 0);
                else finish(node.parentNode, [...node.parentNode.childNodes].indexOf(node));
                return;
            }
            if (seen + token.length >= target) {
                finish(node.parentNode, [...node.parentNode.childNodes].indexOf(node) + 1);
                return;
            }
            seen += token.length;
            return;
        }
        if (node.tagName === "BR") {
            if (seen >= target) {
                finish(node.parentNode, [...node.parentNode.childNodes].indexOf(node) + 1);
                return;
            }
            seen += 1;
            return;
        }
        for (const child of node.childNodes) {
            walk(child);
            if (placed) return;
        }
    };
    walk(editor);
    if (!placed) {
        const selection = window.getSelection?.();
        if (!selection) return;
        const caret = document.createRange();
        caret.selectNodeContents(editor);
        caret.collapse(false);
        selection.removeAllRanges();
        selection.addRange(caret);
    }
}

function chipBeforeRange(range) {
    if (!range?.collapsed) return null;
    const node = range.startContainer;
    const offset = range.startOffset;
    if (sinkFrom(node)) return null;
    let prev;
    if (node.nodeType === Node.TEXT_NODE) {
        if (offset > 0 && !isEmptyText(node)) return null;
        prev = prevSignificant(node);
    } else {
        prev = node.childNodes[offset - 1];
        while (isEmptyText(prev)) prev = prev.previousSibling;
    }
    if (isCaretSink(prev)) prev = prevSignificant(prev);
    return isChipNode(prev) ? prev : null;
}

function chipAfterRange(range) {
    if (!range?.collapsed) return null;
    const node = range.startContainer;
    const offset = range.startOffset;
    const sink = sinkFrom(node);
    if (sink) return isChipNode(sink.nextSibling) ? sink.nextSibling : null;
    let next;
    if (node.nodeType === Node.TEXT_NODE) {
        if (offset < String(node.nodeValue || "").length) return null;
        next = node.nextSibling;
    } else {
        next = node.childNodes[offset];
    }
    return isChipNode(skipSink(next)) ? skipSink(next) : null;
}

function handleDialogueKey(node, event) {
    if (isRawView(node)) return false;
    if (event.altKey || event.ctrlKey || event.metaKey) return false;
    const editor = node.__h3Editor;
    const range = editorSelectionRange(editor);
    if (!range) return false;
    if (event.key === "#" && insertDialogueBlockAtSelection(node, editor)) {
        event.preventDefault();
        event.stopPropagation();
        node.__h3DialogueHashHandled = true;
        setTimeout(() => { node.__h3DialogueHashHandled = false; }, 0);
        syncFromEditor(node);
        pushHistory(node);
        return true;
    }
    const block = dialogueBlockAtRange(range);
    if (event.key === "Enter" && block && !event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation?.();
        exitDialogueBlock(editor, block);
        syncFromEditor(node);
        pushHistory(node);
        return true;
    }
    if (event.key === "Enter" && block && event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        insertDialogueLineBreak(editor, range);
        syncFromEditor(node);
        pushHistory(node);
        return true;
    }
    if (event.key === "Backspace" && range.collapsed) {
        if (block && !dialogueBlockBody(block)) {
            event.preventDefault();
            event.stopPropagation();
            removeDialogueBlock(block);
            syncFromEditor(node);
            pushHistory(node);
            return true;
        }
        if (block && caretAtDialogueBodyStart(range, block)) {
            event.preventDefault();
            event.stopPropagation();
            return true;
        }
        const after = dialogueBeforeRange(range);
        if (after) {
            event.preventDefault();
            event.stopPropagation();
            if (!dialogueBlockBody(after)) removeDialogueBlock(after);
            else deleteLastDialogueContent(after);
            syncFromEditor(node);
            pushHistory(node);
            return true;
        }
    }
    return false;
}

function handleChipKey(node, event) {
    if (isRawView(node)) return false;
    if (event.altKey || event.ctrlKey || event.metaKey) return false;
    const range = editorSelectionRange(node.__h3Editor);
    if (!range?.collapsed) return false;
    const sinkChip = caretSinkChip(range);
    if (event.key === "ArrowLeft") {
        const sink = sinkFrom(range.startContainer);
        if (sinkChip && sink) {
            event.preventDefault();
            event.stopPropagation();
            if (range.startContainer.nodeType === Node.TEXT_NODE && range.startOffset > 0) {
                setCaret(range.startContainer, 0);
                return true;
            }
            moveCaretBeforeSink(sink);
            return true;
        }
        const after = chipBeforeRange(range);
        if (after) {
            event.preventDefault();
            event.stopPropagation();
            placeCaretBefore(node, after);
            return true;
        }
        const before = chipAfterRange(range);
        if (before && needsCaretSinkFrom(linePrev(before))) {
            event.preventDefault();
            event.stopPropagation();
            placeCaretBefore(node, before);
            return true;
        }
        return false;
    }
    if (event.key === "ArrowRight") {
        const chip = sinkChip || chipAfterRange(range);
        if (!chip) return false;
        event.preventDefault();
        event.stopPropagation();
        placeCaretAfter(node, chip);
        return true;
    }
    if (event.key === "Home") {
        const chip = lineStartChipNear(range);
        if (!chip) return false;
        event.preventDefault();
        event.stopPropagation();
        placeCaretBefore(node, chip);
        return true;
    }
    if (event.key === "Enter") {
        const before = sinkChip || chipAfterRange(range);
        const after = chipBeforeRange(range);
        if (!before && !after) return false;
        event.preventDefault();
        event.stopPropagation();
        if (before) {
            const target = isCaretSink(prevSignificant(before)) ? prevSignificant(before) : before;
            target.parentNode.insertBefore(document.createTextNode("\n"), target);
            repairCaretSinks(node.__h3Editor);
            placeCaretBefore(node, before);
        } else {
            const br = document.createTextNode("\n");
            after.parentNode.insertBefore(br, after.nextSibling);
            setCaret(br, 1);
        }
        syncFromEditor(node);
        pushHistory(node);
        return true;
    }
    if (event.key === "Backspace") {
        const chip = chipBeforeRange(range);
        if (chip) {
            event.preventDefault();
            event.stopPropagation();
            removeChip(chip);
            syncFromEditor(node);
            pushHistory(node);
            return true;
        }
        if (sinkChip) {
            const sink = sinkFrom(range.startContainer) || (isCaretSink(prevSignificant(sinkChip)) ? prevSignificant(sinkChip) : null);
            const prev = prevSignificant(sink);
            event.preventDefault();
            event.stopPropagation();
            if (prev?.nodeName === "BR") {
                const last = prevSignificant(prev);
                prev.remove();
                if (isCaretSink(sink) && !needsCaretSinkFrom(prevSignificant(sink))) sink.remove();
                if (isChipNode(last)) placeCaretAfter(node, last);
                else if (last?.nodeType === Node.TEXT_NODE && last.isConnected) setCaret(last, String(last.nodeValue || "").length);
            } else if (textEndsWithBreak(prev)) {
                const text = String(prev.nodeValue || "");
                const last = breakSuffixLength(text) === text.length ? prevSignificant(prev) : prev;
                prev.nodeValue = text.slice(0, -breakSuffixLength(text));
                if (!prev.nodeValue) prev.remove();
                if (isCaretSink(sink) && !needsCaretSinkFrom(prevSignificant(sink))) sink.remove();
                if (isChipNode(last)) placeCaretAfter(node, last);
                else if (last?.nodeType === Node.TEXT_NODE && last.isConnected) setCaret(last, String(last.nodeValue || "").length);
            }
            syncFromEditor(node);
            pushHistory(node);
            return true;
        }
        return false;
    }
    if (event.key === "Delete") {
        const chip = sinkChip || chipAfterRange(range);
        if (!chip) return false;
        event.preventDefault();
        event.stopPropagation();
        removeChip(chip);
        syncFromEditor(node);
        pushHistory(node);
        return true;
    }
    return false;
}

function lineStartChipNear(range) {
    if (!range?.collapsed) return null;
    let node = range.startContainer;
    let offset = range.startOffset;
    const sink = sinkFrom(node);
    if (sink) {
        offset = [...sink.parentNode.childNodes].indexOf(sink);
        node = sink.parentNode;
    } else if (node.nodeType === Node.TEXT_NODE) {
        const value = String(node.nodeValue || "");
        const before = value.slice(0, offset);
        const last = Math.max(before.lastIndexOf("\n"), before.lastIndexOf("\r"));
        if (last >= 0) {
            if (before.slice(last + 1)) return null;
            const next = skipSink(node.nextSibling);
            return isChipNode(next) ? next : null;
        }
        if (before.replace(/[\r\n\u2028\u200b]/g, "")) return null;
        offset = [...node.parentNode.childNodes].indexOf(node);
        node = node.parentNode;
    }
    const children = [...(node?.childNodes || [])];
    for (let i = Math.min(offset, children.length - 1); i >= 0; i--) {
        const child = children[i];
        if (child?.nodeName === "BR" || textEndsWithBreak(child)) {
            const next = skipSink(child.nodeName === "BR" ? children[i + 1] : child.nextSibling);
            return isChipNode(next) ? next : null;
        }
        if (child?.nodeType === Node.TEXT_NODE && String(child.nodeValue || "").replace(/[\u200b\r\n\u2028]/g, "")) return null;
    }
    const first = skipSink(children[0]);
    return isChipNode(first) ? first : null;
}

function removeOneChip(node, chip) {
    if (!chip?.isConnected) return;
    removeChip(chip);
    syncFromEditor(node);
    pushHistory(node);
}

function applyReplace(state, item, { close = false } = {}) {
    if (!state || !item) return;
    state.applying = true;
    try {
        if (state.all) {
            const next = replaceChipsByToken(state.node, state.fromToken, item, { history: false, keep: state.chip });
            if (next) state.chip = next;
            state.fromToken = item.token;
        } else {
            const next = replaceOneChip(state.node, state.chip, item, { history: false });
            if (next) state.chip = next;
        }
        state.dirty = true;
        placeCaretAfter(state.node, state.chip);
        if (close) {
            state.finalized = true;
            pushHistory(state.node);
            closeMenus();
            return;
        }
        if (state.chip?.isConnected && activeMenu?.menu) {
            const rect = state.chip.getBoundingClientRect();
            placeMenu(activeMenu.menu, rect.left, rect.bottom + 4);
        }
    } finally {
        state.applying = false;
    }
}

function showReplaceMenu(node, chip, x, y, all) {
    const tag = parseTag(chip.dataset.token);
    if (!tag) return;
    const inventory = node.__h3GetInventory?.() || [];
    const choices = inventory.filter((item) => !(item.kind === tag.kind && item.index === tag.index));
    if (!choices.length) {
        showMenu(x, y, "h3-mention-menu", [{ label: "No other references", disabled: true }]);
        return;
    }
    const state = {
        mode: "replace",
        node,
        items: choices,
        activeIndex: 0,
        chip,
        all,
        fromToken: tag.token,
        baseline: serializeEditor(node.__h3Editor),
        dirty: false,
    };
    openFloatingMenu(x, y, "h3-mention-menu", (menu) => renderPickerRows(menu, state));
    if (activeMenu) activeMenu.picker = state;
}

function setChipSegment(node, chip, segment, item) {
    if (!chip?.isConnected) return;
    const tag = parseTag(chip.dataset.token);
    if (!tag) return;
    const next = mentionToken(tag.kind, tag.index, segment);
    if (chip.dataset.token === next) return;
    const replacement = chipFor({
        ...item,
        kind: tag.kind,
        index: tag.index,
        segment,
        token: next,
        segmentCount: item?.segmentCount || segment,
        thumb: item?.thumb,
        crop: item?.crop,
    });
    chip.replaceWith(replacement);
    ensureCaretSink(replacement);
    syncFromEditor(node);
    pushHistory(node);
}

function openChipMenu(node, chip, x, y) {
    const tag = parseTag(chip.dataset.token);
    if (!tag) return;
    const current = (node.__h3GetInventory?.() || []).find((item) => item.kind === tag.kind && item.index === tag.index) || tag;
    const buttons = [
        {
            header: true,
            label: `@${tag.kind} ${tag.index}`,
            kind: tag.kind,
            thumb: current.thumb,
            crop: current.crop,
        },
    ];
    const media = current.media;
    const kind = kindKey(tag.kind);
    if (media?.path && (kind === "image" || kind === "video" || kind === "audio")) {
        buttons.push({
            label: "Preview",
            run: () => openPreview(media, { segment: tag.segment }),
        });
    }
    const segmentCount = Math.max(1, Number(current.segmentCount) || 1);
    if ((kind === "video" || kind === "audio") && segmentCount > 1) {
        const currentSeg = Math.max(1, Number(tag.segment) || 1);
        buttons.push({
            picks: Array.from({ length: segmentCount }, (_, i) => {
                const n = i + 1;
                return {
                    label: String(n),
                    active: n === currentSeg,
                    run: () => setChipSegment(node, chip, n, current),
                };
            }),
        });
    }
    buttons.push(
        {
            label: "Replace this",
            run: () => showReplaceMenu(node, chip, x, y, false),
        },
        {
            label: "Replace all",
            run: () => showReplaceMenu(node, chip, x, y, true),
        },
        {
            label: "Remove",
            danger: true,
            run: () => removeOneChip(node, chip),
        },
    );
    showMenu(x, y, "h3-chip-menu", buttons);
}

function insertMentionChip(node, item, range) {
    applyMention(node, item, { close: true, range });
}

function applyMention(node, item, { close = false, range } = {}) {
    const editor = node.__h3Editor;
    const state = activeMenu?.mention;
    if (!editor || !item) return;
    if (state) state.applying = true;
    try {
        if (state?.appliedChip?.isConnected) {
            const next = chipFor(item);
            state.appliedChip.replaceWith(next);
            state.appliedChip = next;
        } else {
            const target = range || state?.range;
            if (!target) return;
            target.deleteContents();
            const chip = chipFor(item);
            target.insertNode(chip);
            if (state) state.appliedChip = chip;
        }
        const chip = state?.appliedChip;
        if (chip?.isConnected) {
            repairCaretSinks(editor);
            placeCaretAfter(node, chip);
        }
        syncFromEditor(node);
        if (close) {
            if (state) state.finalized = true;
            pushHistory(node);
            closeMenus();
        } else if (state?.appliedChip && activeMenu?.menu) {
            const rect = state.appliedChip.getBoundingClientRect();
            placeMenu(activeMenu.menu, rect.left, rect.bottom + 4);
        }
    } finally {
        if (state) state.applying = false;
    }
    editor.focus({ preventScroll: true });
}

function caretClientRect(editor) {
    const selection = window.getSelection?.();
    if (!selection?.rangeCount) return editor?.getBoundingClientRect?.();
    const range = selection.getRangeAt(0).cloneRange();
    range.collapse(true);
    const rect = range.getBoundingClientRect();
    if (rect && (rect.height || rect.width || (rect.top + rect.left))) return rect;
    const marker = document.createElement("span");
    marker.textContent = "\u200b";
    range.insertNode(marker);
    const markerRect = marker.getBoundingClientRect();
    marker.remove();
    return markerRect;
}

function mentionAtCaret(editor) {
    const selection = window.getSelection?.();
    if (!selection?.rangeCount || !selection.isCollapsed || !editor) return null;
    const caret = selection.getRangeAt(0);
    if (!editor.contains(caret.startContainer) && caret.startContainer !== editor) return null;
    const textNode = caret.startContainer;
    if (textNode.nodeType !== Node.TEXT_NODE) return null;
    if (textNode.parentElement?.closest?.(".h3-mention-chip")) return null;
    const before = String(textNode.nodeValue || "").slice(0, caret.startOffset);
    const match = before.match(/@([^@\n]*)$/);
    if (!match) return null;
    const range = document.createRange();
    range.setStart(textNode, caret.startOffset - match[0].length);
    range.setEnd(textNode, caret.startOffset);
    return { range, query: match[1] };
}

function mentionItems(node, query) {
    const needle = String(query || "").toLowerCase();
    return (node.__h3GetInventory?.() || []).filter((item) => {
        if (!needle) return true;
        const hay = `${item.kind} ${item.index} ${item.description || ""} ${item.token}`.toLowerCase();
        return hay.includes(needle);
    }).slice(0, 16);
}

function pickItem(state, item, close) {
    if (!state || !item) return;
    if (state.mode === "replace") applyReplace(state, item, { close });
    else applyMention(state.node, item, { close, range: state.range });
}

function mediaSegmentCount(item) {
    const kind = kindKey(item?.kind);
    if (kind !== "video" && kind !== "audio") return 1;
    return Math.max(1, Math.round(Number(item.segmentCount) || 1));
}

function itemWithSegment(item, segment) {
    const n = Math.max(1, Math.round(Number(segment) || 1));
    return { ...item, segment: n, token: mentionToken(item.kind, item.index, n) };
}

function renderPickerRows(menu, state) {
    menu.replaceChildren();
    if (!state.items.length) {
        const empty = document.createElement("div");
        empty.className = "h3-mention-menu-detail";
        empty.style.padding = "8px";
        empty.textContent = "No references";
        menu.append(empty);
        return;
    }
    state.items.forEach((item, index) => {
        const segs = mediaSegmentCount(item);
        const row = document.createElement("div");
        row.className = "h3-mention-picker-row";
        row.classList.toggle("is-active", index === state.activeIndex);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("role", "menuitem");
        fillMenuButton(btn, {
            label: `@${item.kind} ${item.index}`,
            detail: item.description || "",
            kind: item.kind,
            thumb: item.thumb,
            crop: item.crop,
        });
        btn.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            event.stopPropagation();
            pickItem(state, item, true);
        });
        row.addEventListener("pointermove", () => {
            if (state.activeIndex === index) return;
            state.activeIndex = index;
            renderPickerRows(menu, state);
        });
        row.append(btn);
        if (segs > 1) {
            const picks = document.createElement("div");
            picks.className = "h3-chip-menu-picks";
            for (let n = 1; n <= segs; n++) {
                const pickBtn = document.createElement("button");
                pickBtn.type = "button";
                pickBtn.textContent = String(n);
                pickBtn.addEventListener("pointerdown", (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    pickItem(state, itemWithSegment(item, n), true);
                });
                picks.appendChild(pickBtn);
            }
            row.append(picks);
        }
        menu.append(row);
    });
    menu.querySelector(".is-active")?.scrollIntoView?.({ block: "nearest" });
}

function showMentionMenu(node) {
    const editor = node.__h3Editor;
    if (!editor || isRawView(node)) {
        closeMenus();
        return false;
    }
    const mention = mentionAtCaret(editor);
    if (!mention) {
        if (activeMenu?.mention?.appliedChip) return true;
        closeMenus();
        return false;
    }
    const items = mentionItems(node, mention.query);
    const previous = activeMenu?.mention?.activeIndex || 0;
    const state = {
        node,
        items,
        range: mention.range,
        activeIndex: items.length ? Math.min(previous, items.length - 1) : 0,
        baseline: serializeEditor(editor),
    };
    const rect = caretClientRect(editor);
    const x = rect?.left ?? 8;
    const y = (rect?.bottom ?? 8) + 4;
    openFloatingMenu(x, y, "h3-mention-menu", (menu) => renderPickerRows(menu, state));
    if (activeMenu) {
        activeMenu.mention = state;
        activeMenu.picker = state;
    }
    return true;
}

function handlePickerKey(event) {
    const state = activeMenu?.picker;
    if (!state || activeMenu?.menu?.classList.contains("h3-mention-menu") !== true) return false;
    if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeMenus({ revert: true });
        return true;
    }
    if (event.key === "Tab") {
        event.preventDefault();
        event.stopPropagation();
        if (!state.items.length) return true;
        if (state.appliedChip || state.dirty) {
            const delta = event.shiftKey ? -1 : 1;
            state.activeIndex = (state.activeIndex + delta + state.items.length) % state.items.length;
            renderPickerRows(activeMenu.menu, state);
        }
        pickItem(state, state.items[state.activeIndex], false);
        return true;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        event.stopPropagation();
        if (!state.items.length) return true;
        const delta = event.key === "ArrowUp" ? -1 : 1;
        state.activeIndex = (state.activeIndex + delta + state.items.length) % state.items.length;
        renderPickerRows(activeMenu.menu, state);
        return true;
    }
    if (event.key === "Enter") {
        const item = state.items[state.activeIndex];
        if (!item) return false;
        event.preventDefault();
        event.stopPropagation();
        pickItem(state, item, true);
        return true;
    }
    return false;
}

function handleMentionKey(node, event) {
    return handlePickerKey(event);
}

function insertPlainText(editor, text) {
    if (document.execCommand?.("insertText", false, text)) return;
    const selection = window.getSelection?.();
    if (!selection || !selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    range.deleteContents();
    const node = document.createTextNode(text);
    range.insertNode(node);
    range.setStartAfter(node);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
}

function pasteIntoEditor(node, event) {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    const editor = node.__h3Editor;
    if (!editor) return;
    const text = event.clipboardData?.getData("text/plain") || "";
    if (!text) return;
    const tagged = !isRawView(node) && /<(?:Picture|Video|Audio|Model)\s+\d+(?::\d+)?>|@(?:Picture|Video|Audio|Model)\s*\d+(?::\d+)?|<d>[\s\S]*?<\/d>/i.test(text);
    if (tagged) {
        let prefix = "";
        let suffix = "";
        const range = editorSelectionRange(editor);
        if (range) {
            expandRangeToChips(range);
            try {
                const pre = document.createRange();
                pre.selectNodeContents(editor);
                pre.setEnd(range.startContainer, range.startOffset);
                prefix = pre.collapsed ? "" : serializeRange(pre);
                const post = document.createRange();
                post.selectNodeContents(editor);
                post.setStart(range.endContainer, range.endOffset);
                suffix = post.collapsed ? "" : serializeRange(post);
            } catch {
                prefix = serializeEditor(editor);
            }
        } else {
            prefix = serializeEditor(editor);
        }
        editor.__h3SuppressInput = true;
        setPromptText(node, `${prefix}${text}${suffix}`);
        renderEditor(node);
        placeCaretAtSerializedOffset(editor, prefix.length + text.length);
        pushHistory(node);
        queueMicrotask(() => { editor.__h3SuppressInput = false; });
        return;
    }
    insertPlainText(editor, text);
    syncFromEditor(node);
    pushHistory(node);
}

function copyEditorSelection(node, event, cut) {
    const editor = node.__h3Editor;
    const range = editorSelectionRange(editor);
    if (!range || range.collapsed || !event.clipboardData) return false;
    expandRangeToChips(range);
    const text = serializeRange(range);
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    event.clipboardData.setData("text/plain", text);
    if (!cut) return true;
    const pre = document.createRange();
    pre.selectNodeContents(editor);
    pre.setEnd(range.startContainer, range.startOffset);
    const post = document.createRange();
    post.selectNodeContents(editor);
    post.setStart(range.endContainer, range.endOffset);
    const next = `${pre.collapsed ? "" : serializeRange(pre)}${post.collapsed ? "" : serializeRange(post)}`;
    setPromptText(node, next);
    renderEditor(node);
    placeCaretAtSerializedOffset(editor, pre.collapsed ? 0 : serializeRange(pre).length);
    pushHistory(node);
    return true;
}

function syncFromEditor(node) {
    const editor = node.__h3Editor;
    if (!editor) return;
    setPromptText(node, serializeEditor(editor));
}

function bindEditor(node) {
    const editor = node.__h3Editor;
    let chipPointer = null;
    editor.addEventListener("keydown", (event) => {
        if (handleHistoryKey(node, event)) return;
        if (handleDialogueKey(node, event)) return;
        if (handleChipKey(node, event)) return;
        if (handleMentionKey(node, event)) return;
        event.stopPropagation();
    }, true);
    editor.addEventListener("beforeinput", (event) => {
        if (event.inputType === "historyUndo" || event.inputType === "historyRedo") {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();
            if (event.inputType === "historyRedo") redoHistory(node);
            else undoHistory(node);
            return;
        }
        if (isRawView(node)) return;
        if (node.__h3DialogueHashHandled) {
            node.__h3DialogueHashHandled = false;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();
            return;
        }
        if (event.inputType === "insertText" && event.data === "#" && insertDialogueBlockAtSelection(node, editor)) {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();
            syncFromEditor(node);
            pushHistory(node);
            return;
        }
        if (event.inputType === "insertParagraph") {
            const range = editorSelectionRange(editor);
            const block = dialogueBlockAtRange(range);
            if (!block) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();
            exitDialogueBlock(editor, block);
            syncFromEditor(node);
            pushHistory(node);
        }
    });
    editor.addEventListener("copy", (event) => {
        if (!copyEditorSelection(node, event, false)) {
            event.stopPropagation();
            event.stopImmediatePropagation?.();
        }
    });
    editor.addEventListener("cut", (event) => {
        if (!copyEditorSelection(node, event, true)) {
            event.stopPropagation();
            event.stopImmediatePropagation?.();
        }
    });
    editor.addEventListener("paste", (event) => pasteIntoEditor(node, event), true);
    editor.addEventListener("input", () => {
        if (editor.__h3SuppressInput) return;
        if (editor.__h3PromptHistory?.applying || node.__h3PromptHistory?.applying || activeMenu?.picker?.applying) return;
        repairCaretSinks(editor);
        syncFromEditor(node);
        if (activeMenu?.picker?.mode === "replace") return;
        if (!activeMenu?.mention?.appliedChip) pushHistory(node);
        if (isRawView(node)) {
            closeMenus();
            return;
        }
        if (mentionAtCaret(editor)) showMentionMenu(node);
        else if (!activeMenu?.mention?.appliedChip) closeMenus();
    });

    editor.addEventListener("pointerdown", (event) => {
        chipPointer = null;
        if (event.button !== 0 || isRawView(node)) return;
        const flag = event.target.closest(".h3-dialogue-flag");
        if (flag) {
            event.preventDefault();
            event.stopPropagation();
            const block = flag.closest(`.${DIALOGUE_CLASS}`);
            if (block) openDialogueLangMenu(node, block, event.clientX, event.clientY);
            return;
        }
        const chip = event.target.closest(".h3-mention-chip");
        if (!chip) return;
        const rect = chip.getBoundingClientRect();
        const edge = Math.min(6, Math.max(3, rect.width * 0.12));
        if (event.clientX <= rect.left + edge) {
            event.preventDefault();
            placeCaretBefore(node, chip);
            return;
        }
        if (event.clientX >= rect.right - edge) {
            event.preventDefault();
            placeCaretAfter(node, chip);
            return;
        }
        chipPointer = { x: event.clientX, y: event.clientY, chip, moved: false };
    });
    editor.addEventListener("pointermove", (event) => {
        if (!chipPointer) return;
        if (Math.hypot(event.clientX - chipPointer.x, event.clientY - chipPointer.y) > 4) {
            chipPointer.moved = true;
        }
    });
    editor.addEventListener("pointerup", (event) => {
        const state = chipPointer;
        chipPointer = null;
        if (!state || state.moved || event.shiftKey || event.ctrlKey || event.metaKey) return;
        openChipMenu(node, state.chip, event.clientX, event.clientY);
    });
    editor.addEventListener("pointercancel", () => {
        chipPointer = null;
    });
}

function syncViewButton(node) {
    const button = node.__h3PromptViewButton;
    if (!button) return;
    const raw = isRawView(node);
    button.textContent = raw ? "@" : "</>";
    button.title = raw ? "@ chips" : "Raw";
    button.setAttribute("aria-label", button.title);
    button.setAttribute("aria-pressed", raw ? "true" : "false");
}

function togglePromptView(node) {
    const editor = node.__h3Editor;
    if (!editor) return;
    syncFromEditor(node);
    setRawView(node, !isRawView(node));
    renderEditor(node);
    editor.focus({ preventScroll: true });
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function attachWheelHandler(wrap, editor) {
    const wheelHandler = (event) => {
        const editorFocused = document.activeElement === editor;
        const horizontal = Math.abs(event.deltaX || 0) > Math.abs(event.deltaY || 0);
        const maxScrollTop = Math.max(0, editor.scrollHeight - editor.clientHeight);
        const lineHeight = parseFloat(getComputedStyle(editor).lineHeight) || 16;
        const deltaY = event.deltaMode === 1
            ? event.deltaY * lineHeight
            : event.deltaMode === 2
                ? event.deltaY * editor.clientHeight
                : event.deltaY;
        if (!editorFocused) {
            event.preventDefault();
            event.stopPropagation();
            app.canvas?.processMouseWheel?.(event);
            return;
        }
        if (!event.ctrlKey && !horizontal && maxScrollTop > 0 && deltaY) {
            const next = Math.max(0, Math.min(maxScrollTop, editor.scrollTop + deltaY));
            if (next !== editor.scrollTop) {
                editor.scrollTop = next;
                event.preventDefault();
                event.stopPropagation();
                return;
            }
        }
        if (!event.ctrlKey && !horizontal && maxScrollTop > 0) {
            event.stopPropagation();
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        app.canvas?.processMouseWheel?.(event);
    };
    editor.addEventListener("wheel", wheelHandler, { passive: false, capture: true });
    wrap.addEventListener("wheel", wheelHandler, { passive: false });
}

function patchLiteGraphPromptProcessKey() {
    const proto = globalThis.LGraphCanvas?.prototype;
    if (!proto || proto.__h3StudioPromptKeyHandlingPatched || typeof proto.processKey !== "function") return;
    proto.__h3StudioPromptKeyHandlingPatched = true;
    const original = proto.processKey;
    proto.processKey = function processKeyWithH3StudioPrompt(event) {
        const target = event?.target?.closest?.(".h3-studio-prompt-editor, .h3-mention-menu, .h3-chip-menu, .h3-dialogue-lang-menu")
            || document.activeElement?.closest?.(".h3-studio-prompt-editor, .h3-mention-menu, .h3-chip-menu, .h3-dialogue-lang-menu");
        if (target) return;
        return original.apply(this, arguments);
    };
}

function removePromptEditorWidgets(node) {
    if (!Array.isArray(node.widgets)) return;
    for (let i = node.widgets.length - 1; i >= 0; i--) {
        const name = node.widgets[i]?.name;
        if (name === "h3_prompt_editor" || name === "h3_prompt_mentions") {
            node.widgets[i].element?.remove?.();
            node.widgets.splice(i, 1);
        }
    }
}

function migrateAdvancedPrompt(node) {
    const prompt = findWidget(node, "prompt");
    if (!prompt || String(prompt.value || "").trim()) return;
    const bodies = [];
    for (let i = 1; i <= LEGACY_CLIP_PROMPT_WIDGETS; i++) {
        const text = String(findWidget(node, `prompt_${i}`)?.value || "").trim();
        if (text) bodies.push({ i, text });
    }
    const loop = String(findWidget(node, "loop_prompt")?.value || "").trim();
    if (!bodies.length && !loop) return;
    const duration = Number(findWidget(node, "duration")?.value || 10);
    const segments = Number(findWidget(node, "segments")?.value || bodies.length || 1);
    const lines = promptHeaderLines(node, duration, segments, Boolean(loop));
    for (const body of bodies) {
        lines.push(`## Clip ${body.i} — ${clipRole(body.i, segments, node)}`, body.text, "");
    }
    if (loop) lines.push("## Loop — return to Clip 1", loop, "");
    prompt.value = lines.join("\n").trim() + "\n";
}

function bustThumbUrl(url, bust) {
    const text = String(url || "");
    if (!text) return text;
    const sep = text.includes("?") ? "&" : "?";
    return `${text}${sep}t=${bust}`;
}

function refreshPromptThumbs(node) {
    const editor = node.__h3Editor;
    if (!editor || isRawView(node)) return;
    const inventory = node.__h3GetInventory?.() || [];
    const bust = Date.now();
    for (const chip of editor.querySelectorAll(".h3-mention-chip")) {
        const tag = parseTag(chip.dataset.token);
        if (!tag) continue;
        const item = inventory.find((entry) => entry.kind === tag.kind && entry.index === tag.index);
        if (!item) continue;
        const next = makeThumb({ ...item, thumb: bustThumbUrl(item.thumb, bust) }, false);
        const old = chip.querySelector(".h3-mention-chip-thumb");
        if (old) old.replaceWith(next);
        else chip.prepend(next);
    }
}

function refreshAllPromptThumbs() {
    const nodes = app.graph?._nodes || [];
    for (const node of nodes) node.__h3RefreshPromptThumbs?.();
}

function ensureBuilderThumbListener() {
    if (globalThis.__h3StudioPromptThumbListener) return;
    globalThis.__h3StudioPromptThumbListener = true;
    window.addEventListener("h3-studio-builder-changed", refreshAllPromptThumbs);
}

function activatePromptEditor(node, editor, wrap, viewButton) {
    if (!node || !editor) return;
    node.__h3Editor = editor;
    node.__h3ActiveEditorWrap = wrap;
    if (viewButton) node.__h3PromptViewButton = viewButton;
    node.__h3RefreshPromptThumbs = () => refreshPromptThumbs(node);
}

function createPromptEditorUi(node, {
    label = "prompt", placeholder = "", widgetName = "prompt", getValue, setValue,
} = {}) {
    ensureStyle();
    patchLiteGraphPromptProcessKey();
    ensureBuilderThumbListener();
    const wrap = document.createElement("div");
    wrap.className = "h3-studio-prompt-wrap";
    wrap.style.minHeight = "0px";
    applyNativeEditorTheme(wrap);
    const editor = document.createElement("div");
    editor.className = "comfy-multiline-input h3-studio-prompt-editor";
    editor.contentEditable = "true";
    editor.tabIndex = 0;
    editor.setAttribute("role", "textbox");
    editor.setAttribute("aria-label", label);
    if (placeholder) editor.dataset.placeholder = placeholder;
    editor.spellcheck = false;
    const read = typeof getValue === "function"
        ? getValue
        : () => String(findWidget(node, widgetName)?.value || "");
    const write = typeof setValue === "function"
        ? setValue
        : (text) => {
            const target = findWidget(node, widgetName);
            if (target) target.value = text;
        };
    editor.__h3GetValue = read;
    editor.__h3SetValue = write;
    const tools = document.createElement("div");
    tools.className = "h3-studio-prompt-tools";
    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "h3-studio-prompt-tool";
    viewButton.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
    });
    viewButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        activatePromptEditor(node, editor, wrap, viewButton);
        togglePromptView(node);
    });
    tools.append(viewButton);
    const topTools = document.createElement("div");
    topTools.className = "h3-studio-prompt-tools is-top";
    const refreshButton = document.createElement("button");
    refreshButton.type = "button";
    refreshButton.className = "h3-studio-prompt-tool";
    refreshButton.title = "Reload thumbnails";
    refreshButton.setAttribute("aria-label", "Reload thumbnails");
    refreshButton.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" d="M13.2 8A5.2 5.2 0 1 1 11.1 3.9"/><path fill="currentColor" d="M13.4 1.5v3.8H9.6z"/></svg>';
    refreshButton.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
    });
    refreshButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        activatePromptEditor(node, editor, wrap, viewButton);
        refreshPromptThumbs(node);
    });
    topTools.append(refreshButton);
    wrap.append(editor, tools, topTools);
    wrap.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        activatePromptEditor(node, editor, wrap, viewButton);
        if (event.target?.closest?.(".h3-mention-chip, .h3-dialogue-flag, .h3-mention-menu, .h3-chip-menu")) return;
        closeMenus();
    });
    editor.addEventListener("focusin", () => activatePromptEditor(node, editor, wrap, viewButton));
    attachWheelHandler(wrap, editor);
    activatePromptEditor(node, editor, wrap, viewButton);
    if (!node.__h3EditorWrap) node.__h3EditorWrap = wrap;
    bindEditor(node);
    renderEditor(node);
    resetHistory(node);
    return wrap;
}

function mountPromptEditor(node, host, options = {}) {
    if (!node || !host) return;
    if (typeof options.getValue === "function") node.__h3GetPromptText = options.getValue;
    if (typeof options.setValue === "function") node.__h3SetPromptText = options.setValue;
    node.__h3GetInventory = () => collectedInventory(node, options.inventoryNode || node);
    node.__h3RefreshPromptThumbs = () => refreshPromptThumbs(node);
    if (node.__h3EditorWrap) {
        if (!host.contains(node.__h3EditorWrap)) host.replaceChildren(node.__h3EditorWrap);
        applyNativeEditorTheme(node.__h3EditorWrap);
        renderEditor(node);
        return;
    }
    const wrap = createPromptEditorUi(node, {
        label: options.label || "plan",
        placeholder: options.placeholder || "",
        getValue: options.getValue,
        setValue: options.setValue,
    });
    node.__h3EditorWrap = wrap;
    host.replaceChildren(wrap);
    applyNativeEditorTheme(wrap);
}

function setPromptWidgetVisible(widget, visible) {
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

function setPromptInputHidden(node, name, hidden) {
    const input = node.inputs?.find((slot) => slot?.name === name);
    if (input) input.hidden = hidden;
}

function placeWidgetBefore(node, name, before) {
    const widgets = node.widgets;
    const widget = findWidget(node, name);
    if (!widgets || !widget || !before) return;
    const from = widgets.indexOf(widget);
    const to = widgets.indexOf(before);
    if (from < 0 || to < 0 || from === to - 1) return;
    widgets.splice(from, 1);
    widgets.splice(widgets.indexOf(before), 0, widget);
}

function orderPromptNodeWidgets(node) {
    if (!isMusicVideo(node)) return;
    const before = findWidget(node, "prompt") || node.__h3DomWidget;
    if (!before) return;
    placeWidgetBefore(node, "width", before);
    placeWidgetBefore(node, "height", before);
}

function applyPromptNodeSize(node, next) {
    if (!applyVisualSize(node, next)) return;
    node.__h3StableSize = Array.isArray(next) ? [next[0], next[1]] : next;
    captureNodeSize(node, next);
}

function snapshotPromptNodeSize(node) {
    return snapshotVisualSize(node);
}

function captureKeptSize(node, size, allowShrink) {
    setKeptSize(node, size, allowShrink);
}

function preservePromptNodeSize(node) {
    if (!node) return;
    if (node.__h3SizeHold) {
        if (!node.__h3KeepSize && node.__h3RestoreSize) {
            node.__h3KeepSize = node.__h3RestoreSize.slice();
        }
        return;
    }
    const size = snapshotPromptNodeSize(node);
    if (!size) return;
    captureKeptSize(node, size);
    node.__h3SizeHold = true;
    node.__h3SizeHoldGen = (Number(node.__h3SizeHoldGen) || 0) + 1;
}

function restoreKeptPromptNodeSize(node) {
    const kept = node.__h3KeepSize;
    if (!kept) return false;
    applyPromptNodeSize(node, kept);
    syncPromptWidget(node, node.__h3DomWidget);
    return true;
}

function restoreKeptPromptNodeSizeSoon(node) {
    restoreKeptPromptNodeSize(node);
    restoreNodeSizeSoon(node);
    const token = (node.__h3KeepToken = (Number(node.__h3KeepToken) || 0) + 1);
    const gen = node.__h3SizeHoldGen;
    const apply = () => {
        if (node.__h3KeepToken !== token) return;
        restoreKeptPromptNodeSize(node);
    };
    requestAnimationFrame?.(() => {
        apply();
        requestAnimationFrame?.(() => {
            apply();
            setTimeout(apply, 0);
            setTimeout(apply, 50);
            setTimeout(apply, 200);
            setTimeout(() => {
                if (node.__h3SizeHoldGen === gen) {
                    restoreKeptPromptNodeSize(node);
                    node.__h3SizeHold = false;
                }
            }, 400);
        });
    });
}

function pinSizeToKept(node, size, holdOnly) {
    const kept = node?.__h3KeepSize;
    if (!kept || size == null) return size;
    const width = Number(Array.isArray(size) ? size[0] : 0);
    const height = Number(Array.isArray(size) ? size[1] : size);
    const pin = node.__h3SizeHold || (!holdOnly && Number.isFinite(height) && height < kept[1] - 48);
    if (!pin) return size;
    if (Array.isArray(size)) {
        size[0] = width > 0 ? width : kept[0];
        size[1] = kept[1];
        return size;
    }
    return [kept[0], kept[1]];
}

function installPromptSizeLock(node) {
    if (!node || node.__h3SizeLock) return;
    node.__h3SizeLock = true;
    wrapExpandToFit(node);
    const originalSetSize = node.setSize;
    if (typeof originalSetSize === "function") {
        node.setSize = function (next) {
            const size = pinSizeToKept(this, next);
            const result = originalSetSize.call(this, size);
            const kept = this.__h3KeepSize;
            if (kept && (this.__h3SizeHold || cssContentHeight(this) < kept[1] - 48
                || (Array.isArray(this.size) && this.size[1] < kept[1] - 48))) {
                applyVueCssSize(this, [this.size?.[0] || kept[0], kept[1]]);
            }
            return result;
        };
    }
    const originalCompute = node.computeSize;
    if (typeof originalCompute === "function") {
        node.computeSize = function (...args) {
            return pinSizeToKept(this, originalCompute.apply(this, args), true);
        };
    }
}

function growPromptNodeToFit(node) {
    if (!node || node.__h3GrowingSize) return;
    node.__h3GrowingSize = true;
    try {
        const fitted = fittingPromptNodeHeight(node);
        const current = snapshotPromptNodeSize(node) || [];
        const kept = node.__h3KeepSize;
        const width = (kept && kept[0]) || current[0] || DEFAULT_NODE_WIDTH;
        const height = Math.max(fitted, current[1] || 0, (kept && kept[1]) || 0);
        applyPromptNodeSize(node, [width, height]);
        node.__h3FittedHeight = fitted;
        node._widgetSlotsDirty = true;
        syncPromptWidget(node, node.__h3DomWidget);
        node.onResize?.(node.size);
        node.graph?.setDirtyCanvas?.(true, true);
    } finally {
        node.__h3GrowingSize = false;
    }
}

function growPromptNodeToFitSoon(node) {
    growPromptNodeToFit(node);
    requestAnimationFrame?.(() => {
        growPromptNodeToFit(node);
        requestAnimationFrame?.(() => growPromptNodeToFit(node));
    });
}

function applyDefaultPromptNodeSize(node) {
    if (!node || node.__h3DefaultSizeApplied) return;
    node.__h3DefaultSizeApplied = true;
    const current = Array.isArray(node.size) ? node.size : [];
    const width = Number(current[0]) > 0 ? Number(current[0]) : DEFAULT_NODE_WIDTH;
    const fitted = fittingPromptNodeHeight(node);
    node.__h3FittedHeight = fitted;
    applyPromptNodeSize(node, [width, fitted]);
}

function fitPromptNodeHeight(node) {
    if (!node) return;
    const fitted = fittingPromptNodeHeight(node);
    const current = Array.isArray(node.size) ? node.size : [];
    const width = Number(current[0]) > 0 ? Number(current[0]) : DEFAULT_NODE_WIDTH;
    const currentH = Number(current[1]) || 0;
    const prevFitted = node.__h3FittedHeight;
    const extra = prevFitted == null
        ? Math.max(0, currentH - fitted)
        : Math.max(0, currentH - prevFitted);
    const keptH = Number(node.__h3KeepSize?.[1]) || 0;
    applyPromptNodeSize(node, [width, Math.max(fitted + extra, keptH)]);
    node.__h3FittedHeight = fitted;
}

function fitPromptNodeHeightSoon(node) {
    fitPromptNodeHeight(node);
    requestAnimationFrame?.(() => {
        fitPromptNodeHeight(node);
        requestAnimationFrame?.(() => fitPromptNodeHeight(node));
    });
}

function finishPromptNodeLayout(node) {
    orderPromptNodeWidgets(node);
    applyDefaultPromptNodeSize(node);
    restoreNodeSizeSoon(node);
    fitPromptNodeHeightSoon(node);
}

function isSeamlessLoopOn(node) {
    const value = findWidget(node, "seamless_loop")?.value;
    return value === true || value === "true" || value === 1;
}

function promptMode(node) {
    const raw = String(findWidget(node, "prompt_mode")?.value || "single").trim().toLowerCase().replace(/\s+/g, "_");
    return raw === "per_clip" ? "per_clip" : "single";
}

function setPromptMode(node, mode) {
    const widget = findWidget(node, "prompt_mode");
    const next = mode === "per_clip" ? "per_clip" : "single";
    if (widget) widget.value = next;
}

function storyClipParts(node) {
    return splitPromptClips(findWidget(node, "prompt")?.value).parts.filter((part) => !part.isLoop);
}

function storyClipIndices(node) {
    const indices = [...new Set(
        storyClipParts(node).map((part) => Number(part.index)).filter((n) => Number.isFinite(n) && n >= 1),
    )].sort((a, b) => a - b);
    return indices;
}

function clampClipSegments(node) {
    const cap = maxClipSegments(node);
    if (isClipFixer(node)) {
        const fromDoc = storyClipIndices(node);
        if (fromDoc.length) return Math.min(cap, Math.max(fromDoc[fromDoc.length - 1], fromDoc.length));
        return 1;
    }
    const raw = Number(findWidget(node, "segments")?.value);
    const value = Number.isFinite(raw) ? Math.round(raw) : 3;
    return Math.min(cap, Math.max(1, value));
}

function clipPromptLabel(index, segments, isLoop, node) {
    if (isLoop) return "Loop — return to Clip 1";
    return `Clip ${index} — ${clipRole(index, segments, node)}`;
}

function formatDuration(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "10";
    return n.toFixed(6).replace(/\.?0+$/, "");
}

function splitPromptClips(text) {
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    const header = [];
    const parts = [];
    let current = null;
    for (const line of lines) {
        const heading = line.trim().match(/^##\s+(?:Clip\s+(\d+)|Loop\b)/i);
        if (heading) {
            if (current) parts.push(current);
            current = {
                index: heading[1] ? Number(heading[1]) : null,
                isLoop: !heading[1],
                heading: line.trim(),
                lines: [],
            };
            continue;
        }
        if (current) current.lines.push(line);
        else header.push(line);
    }
    if (current) parts.push(current);
    return { header: header.join("\n"), parts };
}

function defaultClipHeading(index, segments, isLoop, node) {
    if (isLoop) return "## Loop — return to Clip 1";
    return `## Clip ${index} — ${clipRole(index, segments, node)}`;
}

function joinPromptClips(header, parts, node) {
    const story = parts.filter((part) => !part.isLoop);
    const segments = Math.max(1, ...story.map((part) => Number(part.index) || 0));
    const chunks = [String(header || "").replace(/\s+$/, "")];
    for (const part of parts) {
        const title = part.heading || defaultClipHeading(part.index, segments, part.isLoop, node);
        const body = part.lines.join("\n").replace(/^\n+|\n+$/g, "");
        chunks.push("", title, body);
    }
    return `${chunks.join("\n").replace(/\s+$/, "")}\n`;
}

function clipSlotOf(name) {
    if (name === "loop_prompt") return { isLoop: true, index: null };
    const match = String(name || "").match(/^prompt_(\d+)$/);
    if (match) return { isLoop: false, index: Number(match[1]) };
    return null;
}

function getClipSlotText(node, name) {
    const slot = clipSlotOf(name);
    const prompt = String(findWidget(node, "prompt")?.value || "");
    const parsed = splitPromptClips(prompt);
    if (slot && parsed.parts.length) {
        const part = slot.isLoop
            ? parsed.parts.find((item) => item.isLoop)
            : parsed.parts.find((item) => item.index === slot.index);
        const segments = clampClipSegments(node);
        const heading = part?.heading || defaultClipHeading(slot.index, segments, slot.isLoop, node);
        const body = part ? part.lines.join("\n").replace(/^\n+|\n+$/g, "") : "";
        return body ? `${heading}\n${body}` : heading;
    }
    const fallback = String(findWidget(node, name)?.value || "");
    if (!slot || !fallback.trim()) return fallback;
    const segments = clampClipSegments(node);
    const heading = defaultClipHeading(slot.index, segments, slot.isLoop, node);
    return `${heading}\n${fallback}`.replace(/\n+$/, "");
}

function setClipSlotText(node, name, text) {
    const slot = clipSlotOf(name);
    const raw = String(text || "").replace(/\r\n/g, "\n");
    const lines = raw.split("\n");
    let heading = null;
    let bodyLines = lines;
    if (/^##\s+(?:Clip\s+\d+|Loop\b)/i.test(lines[0]?.trim() || "")) {
        heading = lines[0].trim();
        bodyLines = lines.slice(1);
        if (bodyLines[0] === "") bodyLines = bodyLines.slice(1);
    }
    const body = bodyLines.join("\n").replace(/^\n+|\n+$/g, "");
    const widget = findWidget(node, name);
    if (widget) widget.value = body;
    const prompt = findWidget(node, "prompt");
    if (!prompt || !slot) return;
    const parsed = splitPromptClips(prompt.value);
    let found = false;
    const nextParts = parsed.parts.map((part) => {
        if (slot.isLoop ? part.isLoop : part.index === slot.index) {
            found = true;
            return {
                ...part,
                heading: heading || part.heading || defaultClipHeading(slot.index, clampClipSegments(node), slot.isLoop, node),
                lines: body.split("\n"),
            };
        }
        return part;
    });
    if (!found) {
        nextParts.push({
            index: slot.index,
            isLoop: slot.isLoop,
            heading: heading || defaultClipHeading(slot.index, clampClipSegments(node), slot.isLoop, node),
            lines: body.split("\n"),
        });
        nextParts.sort((a, b) => {
            if (a.isLoop !== b.isLoop) return a.isLoop ? 1 : -1;
            return (a.index || 0) - (b.index || 0);
        });
    }
    prompt.value = joinPromptClips(parsed.header, nextParts, node);
}

function headerHasTiming(text) {
    const header = splitPromptClips(text).header;
    return /^(?:H3 Studio prompt\s*|mode\s*:|duration\s*:|max_duration_seconds\s*:|segments\s*:|clip_count\s*:|loop\s*:)/im.test(
        String(header || "").trim(),
    );
}

function promptHeaderLines(node, duration, segments, loopOn) {
    const lines = [
        "H3 Studio prompt",
        `mode: ${documentMode(node)}`,
        `duration: ${formatDuration(duration)}`,
        `segments: ${segments}`,
    ];
    if (!isMusicVideo(node)) lines.push(`loop: ${loopOn ? "true" : "false"}`);
    lines.push("");
    return lines;
}

function patchPromptHeaderTiming(text, duration, segments, loop, node) {
    const raw = String(text || "").replace(/\r\n/g, "\n");
    if (!headerHasTiming(raw)) return raw;
    const lines = raw.split("\n");
    const seen = { duration: false, segments: false, loop: false };
    const wantLoop = node ? !isMusicVideo(node) : true;
    let inHeader = true;
    const next = lines.map((line) => {
        if (inHeader && /^##\s+(?:Clip\s+\d+|Loop\b)/i.test(line.trim())) inHeader = false;
        if (!inHeader) return line;
        const match = line.match(/^(duration|max_duration_seconds|segments|clip_count|loop)\s*:/i);
        if (!match) return line;
        const key = match[1].toLowerCase();
        if (key === "duration" || key === "max_duration_seconds") {
            seen.duration = true;
            return `duration: ${formatDuration(duration)}`;
        }
        if (key === "segments" || key === "clip_count") {
            seen.segments = true;
            return `segments: ${segments}`;
        }
        seen.loop = true;
        return `loop: ${loop ? "true" : "false"}`;
    });
    const hasDocHeader = next.some((line) => /^(H3 Studio prompt\s*|mode\s*:)/i.test(line.trim()));
    if (hasDocHeader && (!seen.duration || !seen.segments || (wantLoop && !seen.loop))) {
        const insert = [];
        if (!seen.duration) insert.push(`duration: ${formatDuration(duration)}`);
        if (!seen.segments) insert.push(`segments: ${segments}`);
        if (wantLoop && !seen.loop) insert.push(`loop: ${loop ? "true" : "false"}`);
        const modeAt = next.findIndex((line) => /^mode\s*:/i.test(line.trim()));
        const clipAt = next.findIndex((line) => /^##\s+(?:Clip\s+\d+|Loop\b)/i.test(line.trim()));
        const at = modeAt >= 0 ? modeAt + 1 : (clipAt >= 0 ? clipAt : 0);
        next.splice(at, 0, ...insert);
    }
    return next.join("\n");
}

function applyHeaderTimingToWidgets(node) {
    if (isClipFixer(node)) return;
    const text = String(findWidget(node, "prompt")?.value || "");
    const timing = parseHeaderTiming(text);
    const story = storyClipParts(node);
    if (timing.duration != null && findWidget(node, "duration")) {
        findWidget(node, "duration").value = timing.duration;
    }
    const segmentsWidget = findWidget(node, "segments");
    if (segmentsWidget) {
        const n = timing.segments != null ? timing.segments : (story.length || Number(segmentsWidget.value) || 3);
        segmentsWidget.value = Math.min(maxClipSegments(node), Math.max(1, Math.round(Number(n) || 3)));
    }
    const loopWidget = findWidget(node, "seamless_loop");
    if (loopWidget) {
        loopWidget.value = timing.loop != null ? Boolean(timing.loop) : story.length !== splitPromptClips(text).parts.length;
    }
}

function applyWidgetsTimingToHeader(node) {
    if (isClipFixer(node)) return;
    const prompt = findWidget(node, "prompt");
    if (!prompt || !headerHasTiming(prompt.value)) return;
    prompt.value = patchPromptHeaderTiming(
        prompt.value,
        findWidget(node, "duration")?.value,
        clampClipSegments(node),
        isSeamlessLoopOn(node),
        node,
    );
}

function ensurePromptClipSections(node) {
    if (isClipFixer(node)) return;
    const prompt = findWidget(node, "prompt");
    if (!prompt) return;
    const parsed = splitPromptClips(prompt.value);
    const byIndex = new Map(parsed.parts.filter((part) => !part.isLoop).map((part) => [part.index, part]));
    const existing = [...byIndex.keys()].filter((n) => Number.isFinite(n) && n >= 1).sort((a, b) => a - b);
    const consecutiveFromOne = existing.length > 0 && existing.every((n, i) => n === i + 1);
    const segments = clampClipSegments(node);
    const loopOn = isSeamlessLoopOn(node);
    const next = [];
    if (existing.length && !consecutiveFromOne) {
        for (const i of existing) next.push(byIndex.get(i));
        let n = existing[existing.length - 1];
        while (next.length < segments) {
            n += 1;
            next.push({
                index: n,
                isLoop: false,
                heading: defaultClipHeading(n, Math.max(n, segments), false, node),
                lines: [],
            });
        }
        if (next.length > segments) next.length = segments;
    } else {
        for (let i = 1; i <= segments; i++) {
            next.push(byIndex.get(i) || {
                index: i,
                isLoop: false,
                heading: defaultClipHeading(i, segments, false, node),
                lines: [],
            });
        }
    }
    const loopPart = parsed.parts.find((part) => part.isLoop);
    if (loopOn) {
        next.push(loopPart || {
            index: null,
            isLoop: true,
            heading: defaultClipHeading(0, segments, true, node),
            lines: [],
        });
    }
    let header = parsed.header;
    if (headerHasTiming(String(header || ""))) {
        header = patchPromptHeaderTiming(header, findWidget(node, "duration")?.value, segments, loopOn, node);
    }
    prompt.value = joinPromptClips(header, next, node);
}

function perClipSlots(node) {
    const parsed = splitPromptClips(findWidget(node, "prompt")?.value);
    const fromDoc = storyClipIndices(node);
    const indices = fromDoc.length
        ? fromDoc
        : (isClipFixer(node) ? [] : Array.from({ length: clampClipSegments(node) }, (_, i) => i + 1));
    const span = Math.max(clampClipSegments(node), ...indices, 1);
    const slots = indices.map((i) => ({
        name: `prompt_${i}`,
        short: String(i),
        label: clipPromptLabel(i, span, false, node),
    }));
    const loopOn = isClipFixer(node)
        ? parsed.parts.some((part) => part.isLoop)
        : isSeamlessLoopOn(node);
    if (loopOn) {
        slots.push({
            name: "loop_prompt",
            short: "Loop",
            label: clipPromptLabel(0, span, true, node),
        });
    }
    return slots;
}

function activePerClipSlot(node) {
    const slots = perClipSlots(node);
    if (!slots.length) {
        return { name: "prompt_1", short: "1", label: clipPromptLabel(1, 1, false, node) };
    }
    const names = slots.map((slot) => slot.name);
    if (!names.includes(node.__h3PerClipSlot)) {
        node.__h3PerClipSlot = names[0];
    }
    return slots.find((slot) => slot.name === node.__h3PerClipSlot) || slots[0];
}

function visibleClipEditors(node) {
    if (promptMode(node) !== "per_clip") {
        return [{ name: "prompt", label: "prompt" }];
    }
    const slots = perClipSlots(node);
    if (!slots.length) return [{ name: "prompt", label: "prompt" }];
    return [activePerClipSlot(node)];
}

function persistActivePromptEditor(node) {
    const editor = node.__h3PromptHost?.querySelector(".h3-studio-prompt-editor");
    if (editor) persistEditor(node, editor);
}

function bindEditorToWidget(node, widgetName, label) {
    const host = node.__h3PromptHost;
    const editor = host?.querySelector(".h3-studio-prompt-editor");
    if (!editor) return;
    persistEditor(node, editor);
    editor.__h3GetValue = () => getClipSlotText(node, widgetName);
    editor.__h3SetValue = (text) => setClipSlotText(node, widgetName, text);
    editor.setAttribute("aria-label", label);
    const wrap = editor.closest(".h3-studio-prompt-wrap");
    const viewButton = wrap?.querySelector(".h3-studio-prompt-tools:not(.is-top) .h3-studio-prompt-tool");
    activatePromptEditor(node, editor, wrap, viewButton);
    renderEditor(node);
    resetHistory(node);
}

function selectPerClipSlot(node, name) {
    if (promptMode(node) !== "per_clip") return;
    const next = perClipSlots(node).find((slot) => slot.name === name);
    if (!next || node.__h3PerClipSlot === name) return;
    bindEditorToWidget(node, next.name, next.label);
    node.__h3PerClipSlot = name;
    syncClipPicks(node);
}

function syncClipPicks(node) {
    const picks = node.__h3PromptHost?.querySelector(".h3-studio-clip-picks");
    if (!picks) return;
    const perClip = promptMode(node) === "per_clip";
    picks.hidden = !perClip;
    if (!perClip) return;
    const slots = perClipSlots(node);
    const active = activePerClipSlot(node);
    const key = slots.map((slot) => slot.name).join("|");
    if (picks.dataset.key !== key) {
        picks.dataset.key = key;
        picks.replaceChildren();
        for (const slot of slots) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.dataset.slot = slot.name;
            btn.textContent = slot.short;
            btn.title = slot.label;
            btn.setAttribute("aria-label", slot.label);
            if (slot.name === "loop_prompt") btn.className = "h3-studio-clip-picks-loop";
            btn.addEventListener("pointerdown", (event) => {
                event.preventDefault();
                event.stopPropagation();
            });
            btn.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                selectPerClipSlot(node, slot.name);
            });
            picks.appendChild(btn);
        }
    }
    picks.querySelectorAll("button").forEach((btn) => {
        btn.setAttribute("aria-pressed", btn.dataset.slot === active.name ? "true" : "false");
    });
    picks.querySelector("button[aria-pressed='true']")?.scrollIntoView?.({ inline: "nearest", block: "nearest" });
}

function parseHeaderTiming(text) {
    let duration = null;
    let segments = null;
    let loop = null;
    for (const line of String(text || "").split(/\r?\n/)) {
        const match = line.trim().match(/^(duration|max_duration_seconds|segments|clip_count|loop)\s*:\s*(.+)$/i);
        if (!match) continue;
        const key = match[1].toLowerCase();
        const raw = match[2].trim();
        if (key === "duration" || key === "max_duration_seconds") {
            const value = Number(raw.replace(/s$/i, ""));
            if (Number.isFinite(value)) duration = value;
        } else if (key === "segments" || key === "clip_count") {
            const value = Number(raw);
            if (Number.isFinite(value)) segments = Math.round(value);
        } else if (key === "loop") {
            loop = ["1", "true", "yes", "on"].includes(raw.toLowerCase());
        }
    }
    return { duration, segments, loop };
}

function sharedSubjectsFromUnified(text) {
    const header = String(text || "").replace(/\r\n/g, "\n").split(/^##\s+/m)[0] || "";
    const match = header.match(/subject_definitions:\s*([\s\S]*?)\s*$/i);
    return match ? match[1].trim() : "";
}

function withSharedSubjects(body, shared) {
    const text = String(body || "").trim();
    if (!shared || /^subject_definitions\s*:/im.test(text)) return text;
    return `subject_definitions:\n${shared}\n\n${text}`.trim();
}

function splitUnifiedIntoClipWidgets(node) {
    const text = String(findWidget(node, "prompt")?.value || "");
    const timing = parseHeaderTiming(text);
    const shared = sharedSubjectsFromUnified(text);
    if (timing.duration != null && findWidget(node, "duration")) {
        findWidget(node, "duration").value = timing.duration;
    }
    const parts = [];
    let current = null;
    for (const line of text.replace(/\r\n/g, "\n").split("\n")) {
        const heading = line.trim().match(/^##\s+(?:Clip\s+(\d+)|Loop\b)/i);
        if (heading) {
            if (current) parts.push(current);
            current = { index: heading[1] ? Number(heading[1]) : null, isLoop: !heading[1], lines: [] };
            continue;
        }
        if (current) current.lines.push(line);
    }
    if (current) parts.push(current);
    const story = parts.filter((part) => !part.isLoop);
    if (timing.segments == null && story.length && findWidget(node, "segments")) {
        findWidget(node, "segments").value = story.length;
    } else if (timing.segments != null && findWidget(node, "segments")) {
        findWidget(node, "segments").value = timing.segments;
    }
    const loopWidget = findWidget(node, "seamless_loop");
    if (loopWidget) {
        loopWidget.value = Boolean(timing.loop) || parts.some((part) => part.isLoop);
    }
    if (!parts.length) {
        const first = findWidget(node, "prompt_1");
        if (first && text.trim()) first.value = text.trim();
        return;
    }
    for (const part of parts) {
        const body = withSharedSubjects(part.lines.join("\n").trim(), shared);
        if (part.isLoop) {
            const widget = findWidget(node, "loop_prompt");
            if (widget) widget.value = body;
        } else if (part.index) {
            const widget = findWidget(node, `prompt_${part.index}`);
            if (widget) widget.value = body;
        }
    }
}

function composeUnifiedFromClipWidgets(node) {
    const prompt = findWidget(node, "prompt");
    if (!prompt) return;
    const segments = clampClipSegments(node);
    const loop = isSeamlessLoopOn(node);
    const duration = Number(findWidget(node, "duration")?.value || 10);
    const bodies = [];
    for (let i = 1; i <= segments; i++) {
        const text = String(findWidget(node, `prompt_${i}`)?.value || "").trim();
        if (text) bodies.push({ i, text });
    }
    const loopText = String(findWidget(node, "loop_prompt")?.value || "").trim();
    if (!bodies.length && !loopText) return;
    const lines = promptHeaderLines(node, duration, segments, loop);
    for (const body of bodies) {
        lines.push(`## Clip ${body.i} — ${clipRole(body.i, segments, node)}`, body.text, "");
    }
    if (loop && loopText) lines.push("## Loop — return to Clip 1", loopText, "");
    prompt.value = `${lines.join("\n").trim()}\n`;
}

function hideNativeClipPromptWidgets(node) {
    hideOriginalPromptWidget(findWidget(node, "prompt_mode"));
    for (const widget of node.widgets || []) {
        const name = String(widget?.name || "");
        if (name === "loop_prompt" || /^prompt_\d+$/.test(name)) {
            setPromptWidgetVisible(widget, false);
        }
    }
}

function timingWidgetNames(node) {
    const names = ["duration", "segments"];
    if (findWidget(node, "seamless_loop")) names.push("seamless_loop");
    return names;
}

function syncAdvancedTimingWidgets(node, perClip) {
    const show = perClip && !isClipFixer(node);
    for (const name of timingWidgetNames(node)) {
        setPromptWidgetVisible(findWidget(node, name), show);
        setPromptInputHidden(node, name, !show);
    }
    const host = node.__h3DomWidget;
    if (show && host) {
        for (const name of timingWidgetNames(node)) {
            placeWidgetBefore(node, name, host);
        }
    }
}

function wrapAdvancedTimingCallback(node, name) {
    const widget = findWidget(node, name);
    if (!widget || widget.__h3AdvancedHostGuard) return;
    widget.__h3AdvancedHostGuard = true;
    const original = widget.callback;
    widget.callback = function (...args) {
        preservePromptNodeSize(node);
        persistActivePromptEditor(node);
        const result = original?.apply(this, args);
        restoreKeptPromptNodeSize(node);
        queueMicrotask(() => syncAdvancedPromptHost(node));
        return result;
    };
}

function mountClipEditorField(node, stack, field) {
    const box = document.createElement("div");
    box.className = "h3-studio-prompt-field";
    const options = field.name === "prompt"
        ? { label: field.label, widgetName: "prompt" }
        : {
            label: field.label,
            widgetName: field.name,
            getValue: () => getClipSlotText(node, field.name),
            setValue: (text) => setClipSlotText(node, field.name, text),
        };
    box.appendChild(createPromptEditorUi(node, options));
    stack.appendChild(box);
}

function syncAdvancedPromptHost(node) {
    if (!isAdvancedPromptNode(node)) return;
    const host = node.__h3PromptHost;
    if (!host) return;
    wrapAdvancedTimingCallback(node, "segments");
    wrapAdvancedTimingCallback(node, "seamless_loop");
    hideNativeClipPromptWidgets(node);
    hideOriginalPromptWidget(findWidget(node, "prompt"));
    const mode = promptMode(node);
    const perClip = mode === "per_clip";
    syncAdvancedTimingWidgets(node, perClip);
    host.querySelectorAll("[data-mode]").forEach((btn) => {
        btn.setAttribute("aria-pressed", btn.dataset.mode === mode ? "true" : "false");
    });
    persistActivePromptEditor(node);
    if (perClip) ensurePromptClipSections(node);
    const fields = visibleClipEditors(node);
    const key = `${mode}|${fields.map((field) => field.name).join("|")}`;
    const stack = host.querySelector(".h3-studio-prompt-stack");
    if (!stack) return;
    syncClipPicks(node);
    if (!(node.__h3PromptHostKey === key && stack.childElementCount === 1)) {
        node.__h3PromptHostKey = key;
        stack.replaceChildren();
        if (fields[0]) mountClipEditorField(node, stack, fields[0]);
    }
    node._widgetSlotsDirty = true;
    node.setDirtyCanvas?.(true, true);
    restoreKeptPromptNodeSizeSoon(node);
}

function switchAdvancedPromptMode(node, mode) {
    const next = mode === "per_clip" ? "per_clip" : "single";
    if (next === promptMode(node)) return;
    persistActivePromptEditor(node);
    preservePromptNodeSize(node);
    if (next === "per_clip") {
        applyHeaderTimingToWidgets(node);
        const prompt = findWidget(node, "prompt");
        if (prompt && !splitPromptClips(prompt.value).parts.length) {
            splitUnifiedIntoClipWidgets(node);
            composeUnifiedFromClipWidgets(node);
        }
        ensurePromptClipSections(node);
    } else if (!isClipFixer(node)) {
        applyWidgetsTimingToHeader(node);
    }
    setPromptMode(node, next);
    node.__h3PromptHostKey = "";
    syncAdvancedPromptHost(node);
}

function ensureAdvancedPromptHost(node) {
    if (node.__h3PromptHost && node.__h3DomWidget && findWidget(node, "h3_prompt_mentions")) {
        syncAdvancedPromptHost(node);
        return node.__h3DomWidget;
    }
    ensureStyle();
    const host = document.createElement("div");
    host.className = "h3-studio-prompt-host";
    const modeBar = document.createElement("div");
    modeBar.className = "h3-studio-prompt-mode";
    modeBar.setAttribute("role", "group");
    modeBar.setAttribute("aria-label", "Prompt layout");
    for (const [id, label] of [["single", "Single prompt"], ["per_clip", "One prompt per clip"]]) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "h3-studio-prompt-mode-btn";
        btn.dataset.mode = id;
        btn.textContent = label;
        btn.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            event.stopPropagation();
        });
        btn.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            switchAdvancedPromptMode(node, id);
        });
        modeBar.appendChild(btn);
    }
    const stack = document.createElement("div");
    stack.className = "h3-studio-prompt-stack";
    const picks = document.createElement("div");
    picks.className = "h3-studio-clip-picks";
    picks.setAttribute("role", "group");
    picks.setAttribute("aria-label", "Clip prompts");
    picks.hidden = true;
    host.append(modeBar, stack, picks);
    node.__h3PromptHost = host;
    node.__h3EditorWrap = host;
    const prompt = findWidget(node, "prompt");
    hideOriginalPromptWidget(prompt);
    const domWidget = node.addDOMWidget("h3_prompt_mentions", "h3_prompt_mentions", host, {
        getValue: () => String(findWidget(node, "prompt")?.value || ""),
        setValue: (value) => {
            const widget = findWidget(node, "prompt");
            if (widget) widget.value = value;
        },
        margin: 10,
        serialize: false,
        getMinHeight: () => promptMinHeight(node),
        getHeight: () => promptMinHeight(node),
        afterResize: () => {
            syncPromptWidget(node, node.__h3DomWidget);
            node._widgetSlotsDirty = true;
            node.setDirtyCanvas?.(true, true);
        },
        onDraw: (drawn) => syncPromptWidget(node, drawn),
    });
    if (!domWidget) return null;
    node.__h3DomWidget = domWidget;
    domWidget.serialize = false;
    setWidgetOption(domWidget, "serialize", false);
    bindPromptWidgetSize(domWidget, node);
    installPromptSizeGuard(node);
    installProgressPin(node);
    const promptIndex = node.widgets?.indexOf(prompt) ?? -1;
    const domIndex = node.widgets?.indexOf(domWidget) ?? -1;
    if (domIndex >= 0 && promptIndex >= 0 && domIndex !== promptIndex + 1) {
        node.widgets.splice(domIndex, 1);
        node.widgets.splice(node.widgets.indexOf(prompt) + 1, 0, domWidget);
    }
    hideOriginalPromptWidget(prompt);
    syncAdvancedPromptHost(node);
    syncPromptWidget(node, domWidget);
    node._widgetSlotsDirty = true;
    node.setDirtyCanvas?.(true, true);
    finishPromptNodeLayout(node);
    return domWidget;
}

function installPromptEditor(node) {
    if (!isPromptNode(node) || typeof node.addDOMWidget !== "function") return;
    const widget = findWidget(node, "prompt");
    if (!widget) return;
    node.__h3GetInventory = () => collectedInventory(node, linkedBuilder(node));
    if (isAdvancedPromptNode(node)) {
        hideOriginalPromptWidget(widget);
        if (promptMode(node) !== "per_clip") migrateAdvancedPrompt(node);
        if (node.__h3PromptHost && node.__h3DomWidget && findWidget(node, "h3_prompt_mentions")) {
            installPromptSizeGuard(node);
            installProgressPin(node);
            syncAdvancedPromptHost(node);
            syncPromptWidget(node, node.__h3DomWidget);
            finishPromptNodeLayout(node);
            return;
        }
        removePromptEditorWidgets(node);
        ensureAdvancedPromptHost(node);
        return;
    }
    if (node.__h3Editor && node.__h3DomWidget && findWidget(node, "h3_prompt_mentions")) {
        hideOriginalPromptWidget(widget);
        node.__h3RefreshPromptThumbs = () => refreshPromptThumbs(node);
        installPromptSizeGuard(node);
        installProgressPin(node);
        syncPromptWidget(node, node.__h3DomWidget);
        finishPromptNodeLayout(node);
        return;
    }
    migrateAdvancedPrompt(node);
    removePromptEditorWidgets(node);
    hideOriginalPromptWidget(widget);
    const wrap = createPromptEditorUi(node, { label: "prompt" });
    node.__h3EditorWrap = wrap;
    const domWidget = node.addDOMWidget("h3_prompt_mentions", "h3_prompt_mentions", wrap, {
        getValue: () => promptText(node),
        setValue: (value) => {
            setPromptText(node, value);
            renderEditor(node);
            resetHistory(node);
        },
        margin: 10,
        serialize: false,
        getMinHeight: () => promptMinHeight(node),
        getHeight: () => promptMinHeight(node),
        afterResize: () => {
            syncPromptWidget(node, node.__h3DomWidget);
            node._widgetSlotsDirty = true;
            node.setDirtyCanvas?.(true, true);
        },
        onDraw: (drawn) => syncPromptWidget(node, drawn),
    });
    if (!domWidget) return;
    node.__h3DomWidget = domWidget;
    domWidget.serialize = false;
    setWidgetOption(domWidget, "serialize", false);
    bindPromptWidgetSize(domWidget, node);
    installPromptSizeGuard(node);
    installProgressPin(node);
    const domIndex = node.widgets?.indexOf(domWidget) ?? -1;
    const promptIndex = node.widgets?.indexOf(widget) ?? -1;
    if (domIndex >= 0 && promptIndex >= 0 && domIndex !== promptIndex + 1) {
        node.widgets.splice(domIndex, 1);
        const nextPromptIndex = node.widgets.indexOf(widget);
        node.widgets.splice(nextPromptIndex + 1, 0, domWidget);
    }
    hideOriginalPromptWidget(widget);
    syncPromptWidget(node, domWidget);
    node._widgetSlotsDirty = true;
    node.setDirtyCanvas?.(true, true);
    finishPromptNodeLayout(node);
}

app.registerExtension({
    name: "H3Studio.PromptEditor",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!PROMPT_NODES.has(nodeData?.name)) return;
        const originalExpand = nodeType.prototype.expandToFitContent;
        if (typeof originalExpand === "function") {
            nodeType.prototype.expandToFitContent = function (...args) {
                if (this.__h3KeepSize || this.__h3SizeHold) return;
                return originalExpand.apply(this, args);
            };
        }
        const originalSerialize = nodeType.prototype.serialize;
        nodeType.prototype.serialize = function () {
            const info = originalSerialize?.apply(this, arguments);
            if (info) info.widgets_values = listedWidgetValues(this);
            return info;
        };
        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info, ...rest) {
            if (Array.isArray(info?.widgets_values)) {
                info.widgets_values = dropDomWidgetValue(this, info.widgets_values);
            }
            return originalConfigure?.apply(this, [info, ...rest]);
        };
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info, ...rest) {
            captureNodeSize(this, info?.size);
            if (Array.isArray(info?.size) && info.size.length >= 2) {
                this.__h3DefaultSizeApplied = true;
            }
            const result = originalOnConfigure?.apply(this, [info, ...rest]);
            queueMicrotask(() => {
                installPromptEditor(this);
                restoreNodeSizeSoon(this);
            });
            return result;
        };
        const originalAddCustomWidget = nodeType.prototype.addCustomWidget;
        nodeType.prototype.addCustomWidget = function (widget, ...rest) {
            const result = originalAddCustomWidget?.call(this, widget, ...rest) ?? widget;
            pinProgressWidgets(this);
            return result;
        };
        if (PROMPT_NODES.has(nodeData?.name)) {
            const originalOnWidgetChanged = nodeType.prototype.onWidgetChanged;
            nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
                const widgetName = widget?.name ?? name;
                if (widgetName === "segments" || widgetName === "seamless_loop" || widgetName === "prompt_mode") {
                    preservePromptNodeSize(this);
                }
                const result = originalOnWidgetChanged?.apply(this, arguments);
                if (widgetName === "segments" || widgetName === "seamless_loop" || widgetName === "prompt_mode") {
                    restoreKeptPromptNodeSize(this);
                    queueMicrotask(() => syncAdvancedPromptHost(this));
                }
                return result;
            };
        }
    },

    async nodeCreated(node) {
        if (isPromptNode(node)) queueMicrotask(() => installPromptEditor(node));
    },

    loadedGraphNode(node) {
        if (isPromptNode(node)) queueMicrotask(() => {
            installPromptEditor(node);
            restoreNodeSizeSoon(node);
        });
    },
});

export { builderInventory, ensureStyle, mountPromptEditor, serializeEditor };

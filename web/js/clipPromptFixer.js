import { app } from "../../scripts/app.js";
import { builderInventory, mountPromptEditor } from "./promptEditor.js";

const NODE_NAME = "H3StudioClipPromptFixer";
const MIN_PLAN_HEIGHT = 120;
const SKILL_SLASH = "/prompt-minimax-h3-clip-fix";
const COPY_LABEL = "Copy skill command";
const COPY_TIP = "Copies /prompt-minimax-h3-clip-fix plus clip_index, plan, Builder dump, and the selected clips with one previous and one following clip.";

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

function findWidget(node, name) {
    return node?.widgets?.find((widget) => widget?.name === name);
}

function hidePlanWidget(widget) {
    if (!widget) return;
    widget.hidden = true;
    widget.serialize = true;
    widget.computeSize = () => [0, -4];
    widget.computedHeight = 0;
    if (widget.inputEl) widget.inputEl.style.display = "none";
    if (widget.element) widget.element.style.display = "none";
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

function isMusicVideoBuilder(builder) {
    return String(findWidget(builder, "mode")?.value || "") === "music_video";
}

function formatLinkedDump(builder) {
    if (!builder) return "";
    const items = builderInventory(builder);
    if (!items.length) return "";
    const music = isMusicVideoBuilder(builder);
    const lines = ["H3 Studio Builder pack"];
    const duration = Number(findWidget(builder, "max_clip_duration")?.value);
    if (Number.isFinite(duration) && duration > 0) lines.push(`duration: ${duration.toFixed(2)}s`);
    if (!music) {
        const segments = Number(findWidget(builder, "segments")?.value);
        if (Number.isFinite(segments) && segments > 0) lines.push(`segments: ${Math.round(segments)}`);
        if (findWidget(builder, "loop")?.value) lines.push("loop: true");
    }
    for (const item of items) {
        const desc = String(item.description || "").trim() || "(no description)";
        if (item.kind === "Model") {
            lines.push(`Model ${item.index}: ${desc}`);
        } else if (item.kind === "Picture") {
            const extra = item.media?.first_frame ? " (first frame)" : "";
            lines.push(`Picture ${item.index}: ${desc}${extra}`);
        } else if (item.kind === "Video") {
            const dur = Number(item.media?.duration) || 0;
            const extra = item.media?.has_soundtrack ? " (with soundtrack)" : "";
            lines.push(`Video ${item.index}: ${dur.toFixed(1)}s ${desc}${extra}`);
        } else if (item.kind === "Audio" && !music) {
            const dur = Number(item.media?.duration) || 0;
            lines.push(`Audio ${item.index}: ${dur.toFixed(1)}s ${desc}`);
        }
    }
    return `${lines.join("\n")}\n`;
}

function parseClipIndex(text) {
    const raw = String(text || "").trim().replace(/\s*-\s*/g, "-");
    if (!raw) return [];
    const found = [];
    const seen = new Set();
    for (const part of raw.split(/[,\s]+/)) {
        if (!part) continue;
        const match = part.match(/^(\d+)(?:-(\d+))?$/);
        if (!match) continue;
        let start = Number(match[1]);
        let end = match[2] != null ? Number(match[2]) : start;
        if (!(start >= 1) || !(end >= 1)) continue;
        if (end < start) [start, end] = [end, start];
        for (let n = start; n <= end; n++) {
            if (seen.has(n)) continue;
            seen.add(n);
            found.push(n);
        }
    }
    return found;
}

function windowIndices(selected) {
    if (!selected?.length) return [];
    const lo = Math.min(...selected) - 1;
    const hi = Math.max(...selected) + 1;
    const out = [];
    for (let n = Math.max(1, lo); n <= hi; n++) out.push(n);
    return out;
}

function extractPromptWindow(text, clipIndex) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    const parsed = splitPromptClips(raw);
    const story = parsed.clips.filter((clip) => !clip.loop && clip.index >= 1);
    if (!story.length) return "";
    const available = new Set(story.map((clip) => clip.index));
    let selected = parseClipIndex(clipIndex);
    if (!selected.length) selected = story.map((clip) => clip.index);
    const want = new Set(windowIndices(selected).filter((n) => available.has(n)));
    const kept = story.filter((clip) => want.has(clip.index)).map((clip) => clip.text);
    return kept.length ? `${kept.join("\n\n").trim()}\n` : "";
}

function splitPromptClips(text) {
    const raw = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const lines = raw.split("\n");
    const starts = [];
    for (let i = 0; i < lines.length; i++) {
        const stripped = lines[i].trim();
        const clip = stripped.match(/^(?:##\s+Clip\s+(\d+)\s*[—\-–]+|\*\*Clip\s+(\d+)\s*[—\-–]+)/i);
        if (clip) {
            starts.push({ line: i, index: Number(clip[1] || clip[2]), loop: false });
            continue;
        }
        if (/^(?:##\s+Loop\b|\*\*Loop\b)/i.test(stripped)) {
            starts.push({ line: i, index: null, loop: true });
        }
    }
    const header = starts.length ? lines.slice(0, starts[0].line).join("\n").trimEnd() : raw.trimEnd();
    const clips = starts.map((start, j) => {
        const end = j + 1 < starts.length ? starts[j + 1].line : lines.length;
        return {
            index: start.index,
            loop: start.loop,
            text: lines.slice(start.line, end).join("\n").trimEnd(),
        };
    });
    return { header, clips };
}

function formatSkillCommand(node) {
    const clipIndex = String(findWidget(node, "clip_index")?.value || "").trim();
    const plan = String(findWidget(node, "plan")?.value || "").trim();
    const seed = String(findWidget(node, "original_prompt")?.value || "").trim();
    const lines = [SKILL_SLASH];
    if (clipIndex) lines.push(`clip_index: ${clipIndex}`);
    lines.push("plan:");
    lines.push(plan || "(no extra plan)");
    lines.push("");
    const dump = formatLinkedDump(linkedBuilder(node));
    if (dump) {
        lines.push(dump.trimEnd());
        lines.push("");
    }
    lines.push("original_prompt:");
    lines.push(extractPromptWindow(seed, clipIndex).trimEnd());
    return `${lines.join("\n").replace(/\n+$/, "")}\n`;
}

async function copySkillCommand(node, button) {
    const text = formatSkillCommand(node);
    try {
        await navigator.clipboard.writeText(text);
    } catch (_) {
        window.prompt("Copy skill command", text);
    }
    button.textContent = "Copied";
    button.classList.add("h3-clip-fixer-copied");
    clearTimeout(button._h3Copied);
    button._h3Copied = setTimeout(() => {
        button.textContent = COPY_LABEL;
        button.classList.remove("h3-clip-fixer-copied");
    }, 1500);
}

function install(node) {
    if (!isTarget(node) || node.__h3ClipFixerUi) return;
    node.__h3ClipFixerUi = true;
    hidePlanWidget(findWidget(node, "plan"));
    const wrap = document.createElement("div");
    wrap.className = "h3-clip-fixer";
    wrap.innerHTML = `
<style>
.h3-clip-fixer {
  display: flex; flex-direction: column; gap: 6px; min-width: 0; min-height: 0; height: 100%;
  box-sizing: border-box;
}
.h3-clip-fixer-plan {
  position: relative; flex: 1 1 auto; min-height: ${MIN_PLAN_HEIGHT}px; min-width: 0;
  border: 1px solid #444; border-radius: 8px; overflow: hidden; background: #1c1c1c;
}
.h3-clip-fixer-plan .h3-studio-prompt-wrap {
  position: absolute; inset: 0; height: auto; width: auto;
}
.h3-clip-fixer-actions { display: flex; gap: 6px; flex-wrap: wrap; flex: 0 0 auto; align-items: center; }
.h3-clip-fixer-actions button {
  background: #333; color: #eee; border: 1px solid #555; padding: 4px 8px; cursor: pointer;
}
.h3-clip-fixer-actions button.h3-clip-fixer-copied { border-color: #6c9; color: #cfe; background: #2a4033; }
</style>
`;
    const host = document.createElement("div");
    host.className = "h3-clip-fixer-plan";
    const footer = document.createElement("div");
    footer.className = "h3-clip-fixer-actions";
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.textContent = COPY_LABEL;
    copyBtn.title = COPY_TIP;
    copyBtn.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
    });
    copyBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        void copySkillCommand(node, copyBtn);
    });
    footer.appendChild(copyBtn);
    wrap.append(host, footer);
    const widget = node.addDOMWidget("h3_clip_fixer_plan", "div", wrap, {
        serialize: false,
        getMinHeight: () => MIN_PLAN_HEIGHT + 28,
        getHeight: () => "100%",
    });
    if (widget) widget.serialize = false;
    mountPromptEditor(node, host, {
        getValue: () => String(findWidget(node, "plan")?.value || ""),
        setValue: (text) => {
            const target = findWidget(node, "plan");
            if (target) target.value = text;
        },
        inventoryNode: node,
        label: "plan",
        placeholder: "What to change in the selected clips. Lyrics and timings stay locked.",
    });
    node.__h3GetInventory = () => {
        const builder = linkedBuilder(node);
        if (!builder) return [];
        return builderInventory(builder).map((item) => ({ ...item, builder }));
    };
    node.__h3FormatSkillCommand = () => formatSkillCommand(node);
}

app.registerExtension({
    name: "H3Studio.ClipPromptFixer",

    async nodeCreated(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => install(node));
    },

    loadedGraphNode(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => install(node));
    },
});

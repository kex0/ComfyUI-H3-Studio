import { app } from "../../scripts/app.js";

const CATEGORY = "H3 Studio";
const descriptions = new Map();
const popups = new Map();

function isH3NodeData(nodeData) {
    return String(nodeData?.category || "").startsWith(CATEGORY);
}

function graphNode(nodeId) {
    const graph = app.graph;
    if (!graph?.getNodeById) return null;
    return graph.getNodeById(nodeId) || graph.getNodeById(Number(nodeId));
}

function descriptionFor(node) {
    if (!node) return "";
    return node._h3Help
        || descriptions.get(node.type)
        || descriptions.get(node.comfyClass)
        || "";
}

function markdownHtml(text) {
    const render = app.extensionManager?.renderMarkdownToHtml;
    if (typeof render === "function") return render(text);
    const escaped = String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    const html = escaped
        .replace(/^### (.+)$/gm, "<h4>$1</h4>")
        .replace(/^## (.+)$/gm, "<h3>$1</h3>")
        .replace(/^# (.+)$/gm, "<h2>$1</h2>")
        .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/^- (.+)$/gm, "<li>$1</li>")
        .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
        .replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>")
        .replace(/\n\n/g, "</p><p>")
        .replace(/\n/g, "<br>");
    return `<p>${html}</p>`;
}

function injectStyle() {
    if (document.getElementById("h3-help-style")) return;
    const style = document.createElement("style");
    style.id = "h3-help-style";
    style.textContent = `
      .h3-help-btn {
        color: orange; font-weight: 700; font-size: 14px; cursor: pointer;
        flex-shrink: 0; padding: 0 4px; line-height: 1; user-select: none;
        margin-left: auto;
      }
      .h3-help-popup {
        position: fixed; z-index: 100050; width: 340px; height: 380px;
        box-sizing: border-box; padding: 14px 28px 18px 12px; overflow: hidden;
        background: var(--comfy-menu-bg, #1e1e1e); color: var(--fg-color, #ddd);
        border: 2px solid var(--border-color, #555); border-radius: 10px;
        font: 12px/1.45 Inter, system-ui, sans-serif;
      }
      .h3-help-body { overflow: auto; max-height: 100%; height: 100%; }
      .h3-help-body h2, .h3-help-body h3, .h3-help-body h4 { margin: 0 0 8px; }
      .h3-help-body p, .h3-help-body ul { margin: 0 0 8px; }
      .h3-help-body ul { padding-left: 1.2em; }
      .h3-help-body code { font-size: 11px; }
      .h3-help-body a { color: #7ec8ff; }
      .h3-help-close {
        position: absolute; top: 2px; right: 4px; cursor: pointer;
        color: #e66; font-size: 12px; padding: 4px;
      }
      .h3-help-resize {
        position: absolute; right: 0; bottom: 0; width: 0; height: 0; cursor: se-resize;
        border: 10px solid var(--border-color, #555); border-top-color: transparent;
        border-left-color: transparent;
      }
    `;
    document.head.appendChild(style);
}

function closePopup(nodeId) {
    const state = popups.get(String(nodeId));
    if (!state) return;
    state.doc?.remove();
    state.abort?.abort();
    if (state.anim) cancelAnimationFrame(state.anim);
    popups.delete(String(nodeId));
}

function openPopup(nodeId, text) {
    closePopup(nodeId);
    injectStyle();
    const abort = new AbortController();
    const doc = document.createElement("div");
    doc.className = "h3-help-popup";
    const body = document.createElement("div");
    body.className = "h3-help-body";
    body.innerHTML = markdownHtml(text);
    const close = document.createElement("div");
    close.className = "h3-help-close";
    close.textContent = "❌";
    close.title = "Close";
    const resize = document.createElement("div");
    resize.className = "h3-help-resize";
    doc.append(body, close, resize);
    document.body.appendChild(doc);

    close.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        closePopup(nodeId);
    }, { signal: abort.signal });
    doc.addEventListener("mousedown", (e) => e.stopPropagation(), { signal: abort.signal });
    doc.addEventListener("pointerdown", (e) => e.stopPropagation(), { signal: abort.signal });

    let resizing = false;
    let startX = 0;
    let startY = 0;
    let startW = 0;
    let startH = 0;
    resize.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        resizing = true;
        startX = e.clientX;
        startY = e.clientY;
        startW = doc.offsetWidth;
        startH = doc.offsetHeight;
    }, { signal: abort.signal });
    document.addEventListener("mousemove", (e) => {
        if (!resizing) return;
        doc.style.width = `${Math.max(240, startW + e.clientX - startX)}px`;
        doc.style.height = `${Math.max(160, startH + e.clientY - startY)}px`;
    }, { signal: abort.signal });
    document.addEventListener("mouseup", () => { resizing = false; }, { signal: abort.signal });

    const state = { doc, abort, anim: 0 };
    popups.set(String(nodeId), state);
    const tick = () => {
        if (!state.doc?.parentNode) return;
        const nodeEl = document.querySelector(`[data-node-id="${nodeId}"]`);
        if (nodeEl) {
            const rect = nodeEl.getBoundingClientRect();
            state.doc.style.left = `${rect.right + 10}px`;
            state.doc.style.top = `${rect.top}px`;
        } else if (app.canvas && !window.LiteGraph?.vueNodesMode) {
            const node = graphNode(nodeId);
            const canvas = app.canvas.canvas;
            const ds = app.canvas.ds;
            if (node?.pos && canvas) {
                const rect = canvas.getBoundingClientRect();
                const x = rect.left + (node.pos[0] + (node.size?.[0] || 0) + ds.offset[0]) * ds.scale;
                const y = rect.top + (node.pos[1] + ds.offset[1]) * ds.scale;
                state.doc.style.left = `${x + 10}px`;
                state.doc.style.top = `${y}px`;
            }
        }
        state.anim = requestAnimationFrame(tick);
    };
    state.anim = requestAnimationFrame(tick);
}

function togglePopup(nodeId, text) {
    if (popups.has(String(nodeId))) closePopup(nodeId);
    else openPopup(nodeId, text);
}

function tryInjectHelpButton(header) {
    if (header.querySelector(".h3-help-btn")) return;
    const nodeEl = header.closest("[data-node-id]");
    if (!nodeEl) return;
    const nodeId = nodeEl.dataset.nodeId;
    const node = graphNode(nodeId);
    const text = descriptionFor(node);
    if (!text) return;
    const row = header.querySelector(":scope > div") || header;
    const btn = document.createElement("span");
    btn.className = "h3-help-btn";
    btn.textContent = "?";
    btn.title = "How to use this node";
    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        togglePopup(nodeId, text);
    });
    row.appendChild(btn);
}

function setupHelpObserver() {
    injectStyle();
    document.querySelectorAll(".lg-node-header").forEach(tryInjectHelpButton);
    let pending = false;
    const observer = new MutationObserver(() => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            document.querySelectorAll(".lg-node-header:not(:has(.h3-help-btn))").forEach(tryInjectHelpButton);
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

function installCanvasHelp(nodeType) {
    const drawFg = nodeType.prototype.onDrawForeground;
    nodeType.prototype.onDrawForeground = function (ctx) {
        const result = drawFg?.apply(this, arguments);
        if (this.flags?.collapsed) return result;
        const text = descriptionFor(this);
        if (!text) return result;
        const iconSize = 14;
        const x = this.size[0] - iconSize - 4;
        ctx.save();
        ctx.translate(x - 2, iconSize - 34);
        ctx.scale(iconSize / 32, iconSize / 32);
        ctx.font = "bold 36px monospace";
        ctx.fillStyle = "orange";
        ctx.fillText("?", 0, 24);
        ctx.restore();
        return result;
    };
    const mouseDown = nodeType.prototype.onMouseDown;
    nodeType.prototype.onMouseDown = function (e, localPos) {
        const result = mouseDown?.apply(this, arguments);
        const text = descriptionFor(this);
        if (!text || this.flags?.collapsed) return result;
        const iconSize = 14;
        const iconX = this.size[0] - iconSize - 4;
        const iconY = iconSize - 34;
        if (
            localPos[0] > iconX && localPos[0] < iconX + iconSize
            && localPos[1] > iconY && localPos[1] < iconY + iconSize
        ) {
            togglePopup(this.id, text);
            return true;
        }
        return result;
    };
    const onRem = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
        closePopup(this.id);
        return onRem?.apply(this, arguments);
    };
}

app.registerExtension({
    name: "H3Studio.NodeHelp",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isH3NodeData(nodeData) || !nodeData.description) return;
        descriptions.set(nodeData.name, nodeData.description);
        installCanvasHelp(nodeType);
    },
    nodeCreated(node) {
        const text = descriptions.get(node.type) || descriptions.get(node.comfyClass);
        if (text) node._h3Help = text;
    },
    setup() {
        setupHelpObserver();
    },
});

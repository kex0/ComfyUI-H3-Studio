function readSize(size) {
    if (!Array.isArray(size) || size.length < 2) return null;
    const width = Number(size[0]);
    const height = Number(size[1]);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
    return [width, height];
}

function titleHeight() {
    return Number(globalThis.LiteGraph?.NODE_TITLE_HEIGHT) || 30;
}

function vueNodeElement(node) {
    if (node?.id != null && node.id !== -1) {
        const fromId = document.querySelector(`.lg-node[data-node-id="${node.id}"]`)
            || document.querySelector(`[data-node-id="${node.id}"]`);
        if (fromId) return fromId;
    }
    const wrap = node?.__h3PromptHost || node?.__h3EditorWrap;
    return wrap?.closest?.(".lg-node") || wrap?.closest?.("[data-node-id]") || null;
}

function cssContentHeight(node) {
    const el = vueNodeElement(node);
    if (!el) return 0;
    const cssFull = parseFloat(el.style?.getPropertyValue?.("--node-height"));
    if (Number.isFinite(cssFull) && cssFull > 0) return Math.max(1, cssFull - titleHeight());
    const inner = el.querySelector?.("[data-testid='node-inner-wrapper']");
    const offsetH = Math.max(Number(el.offsetHeight) || 0, Number(inner?.offsetHeight) || 0);
    return offsetH > 0 ? Math.max(1, offsetH - titleHeight()) : 0;
}

function snapshotVisualSize(node) {
    const logical = readSize(node?.size);
    const rendered = readSize(node?.renderingSize);
    const el = vueNodeElement(node);
    let cssW = 0;
    if (el) {
        cssW = Number(el.offsetWidth) || parseFloat(el.style.getPropertyValue("--node-width")) || 0;
    }
    const cssH = cssContentHeight(node);
    const width = Math.max(logical?.[0] || 0, rendered?.[0] || 0, cssW || 0);
    const height = Math.max(
        logical?.[1] || 0,
        rendered?.[1] || 0,
        cssH || 0,
    );
    if (!(width > 0) || !(height > 0)) return logical;
    return [width, height];
}

function applyVueCssSize(node, size) {
    const next = readSize(size);
    const el = vueNodeElement(node);
    if (!next || !el?.style) return;
    const keptH = Number(node.__h3KeepSize?.[1]) || 0;
    const contentH = Math.max(next[1], keptH);
    const keptW = Number(node.__h3KeepSize?.[0]) || 0;
    el.style.setProperty("--node-width", `${Math.max(next[0], keptW)}px`);
    el.style.setProperty("--node-height", `${contentH + titleHeight()}px`);
}

function assignNodeSize(node, size) {
    if (typeof node.setSize === "function") {
        node.setSize(size);
        return;
    }
    node.size = [size[0], size[1]];
}

function applyVisualSize(node, next) {
    const size = readSize(next);
    if (!node || !size || node.__h3ApplyingSize) return false;
    node.__h3ApplyingSize = true;
    try {
        assignNodeSize(node, size);
        applyVueCssSize(node, size);
        node._widgetSlotsDirty = true;
        node.setDirtyCanvas?.(true, true);
        node.graph?.setDirtyCanvas?.(true, true);
        return true;
    } finally {
        node.__h3ApplyingSize = false;
    }
}

function captureNodeSize(node, size) {
    const named = readSize(size);
    const visual = snapshotVisualSize(node);
    const width = Math.max(named?.[0] || 0, visual?.[0] || 0);
    const height = Math.max(named?.[1] || 0, visual?.[1] || 0);
    if (!node || !(width > 0) || !(height > 0)) return;
    node.__h3RestoreSize = [width, height];
}

function setKeptSize(node, size, allowShrink) {
    captureNodeSize(node, size);
    const next = node.__h3RestoreSize;
    if (!node || !next) return;
    const prev = node.__h3KeepSize;
    const shrinking = prev && next[1] < prev[1];
    if (shrinking && !allowShrink && !node.__h3UserResizing) {
        node.__h3RestoreSize = prev.slice();
        return;
    }
    node.__h3KeepSize = [next[0], next[1]];
}

function isResizeHandle(target) {
    if (!target?.closest) return false;
    if (target.closest("[data-resize], .node-resize, .lg-node-resize, .resize-handle")) return true;
    let el = target;
    for (let i = 0; i < 5 && el; i++) {
        if (String(el.style?.cursor || "").includes("resize")) return true;
        el = el.parentElement;
    }
    return false;
}

function wrapExpandToFit(node) {
    if (!node || node.__h3ExpandGuard) return;
    const original = node.expandToFitContent;
    if (typeof original !== "function") return;
    node.__h3ExpandGuard = true;
    node.expandToFitContent = function (...args) {
        if (this.__h3KeepSize || this.__h3SizeHold) return;
        return original.apply(this, args);
    };
}

function installSizeWatch(node) {
    if (!node || node.__h3SizeWatch) return;
    node.__h3SizeWatch = true;
    wrapExpandToFit(node);
    const apply = () => {
        if (node.__h3UserResizing || node.__h3RestoringHeight) return;
        const kept = node.__h3KeepSize;
        if (!kept) return;
        const cssH = cssContentHeight(node);
        if (cssH >= kept[1] - 8) return;
        node.__h3RestoringHeight = true;
        if (Array.isArray(node.size) && Number(node.size[1]) < kept[1] - 8) {
            assignNodeSize(node, kept);
        }
        applyVueCssSize(node, kept);
        requestAnimationFrame?.(() => {
            node.__h3RestoringHeight = false;
        });
    };
    const bind = (el) => {
        if (el && el !== node.__h3SizeWatchEl) {
            node.__h3HeightRO?.disconnect?.();
            node.__h3SizeWatchEl = el;
            el.addEventListener("pointerdown", (event) => {
                if (isResizeHandle(event.target)) {
                    node.__h3UserResizing = true;
                    return;
                }
                setKeptSize(node, snapshotVisualSize(node));
            }, true);
            if (typeof ResizeObserver === "function") {
                const ro = new ResizeObserver(() => apply());
                ro.observe(el);
                node.__h3HeightRO = ro;
            }
        }
        apply();
    };
    bind(vueNodeElement(node));
    if (!node.__h3SizeWatchPointerUp) {
        node.__h3SizeWatchPointerUp = true;
        window.addEventListener("pointerup", () => {
            if (!node.__h3UserResizing) return;
            node.__h3UserResizing = false;
            setKeptSize(node, snapshotVisualSize(node), true);
        }, true);
    }
    const token = window.setInterval(() => {
        if (!node.__h3SizeWatch) {
            window.clearInterval(token);
            return;
        }
        bind(vueNodeElement(node));
    }, 1000);
}

function restoreNodeSize(node) {
    const kept = node?.__h3KeepSize || node?.__h3RestoreSize;
    return applyVisualSize(node, kept);
}

function restoreNodeSizeSoon(node) {
    if (!restoreNodeSize(node)) return;
    const token = (node.__h3RestoreToken = (Number(node.__h3RestoreToken) || 0) + 1);
    const apply = () => {
        if (node.__h3RestoreToken !== token) return;
        restoreNodeSize(node);
    };
    requestAnimationFrame?.(() => {
        apply();
        requestAnimationFrame?.(() => {
            apply();
            setTimeout(apply, 0);
            setTimeout(apply, 50);
            setTimeout(apply, 200);
            setTimeout(() => {
                if (node.__h3RestoreToken !== token) return;
                restoreNodeSize(node);
                if (!node.__h3SizeHold) node.__h3RestoreSize = null;
            }, 400);
        });
    });
}

export {
    applyVisualSize, applyVueCssSize, captureNodeSize, cssContentHeight, installSizeWatch,
    restoreNodeSize, restoreNodeSizeSoon, setKeptSize, snapshotVisualSize, vueNodeElement,
    wrapExpandToFit,
};

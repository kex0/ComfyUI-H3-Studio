import { app } from "../../scripts/app.js";
import { captureNodeSize, restoreNodeSizeSoon } from "./nodeSize.js";

const TARGET_CLASS = "H3StudioAutoChain";
const TARGET_CLASSES = new Set(["H3StudioAutoChain", "H3StudioAutoChainAdvanced"]);
const MAX_SEGMENTS = 12;

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
    return [...targetNames(node)].some((name) => TARGET_CLASSES.has(name));
}

function isTargetDefinition(nodeType, nodeData) {
    return [
        nodeData?.name,
        nodeType?.type,
        nodeType?.comfyClass,
        nodeType?.ComfyClass,
        nodeType?.nodeData?.name,
    ].filter(Boolean).some((name) => TARGET_CLASSES.has(name));
}

function findWidget(node, name) {
    return node?.widgets?.find((widget) => widget?.name === name);
}

function modelLabel(index, segments) {
    if (index === 1) return `model_${index} (Start)`;
    if (index === segments) return `model_${index} (Finish)`;
    return `model_${index} (Continue)`;
}

function setWidgetVisible(widget, visible) {
    if (!widget) return;
    widget.hidden = !visible;
    if (visible) {
        delete widget.computeSize;
    } else {
        widget.computeSize = () => [0, -4];
    }
}

function snapshotSize(node) {
    const size = node?.size;
    if (!Array.isArray(size) || size.length < 2) return null;
    const width = Number(size[0]);
    const height = Number(size[1]);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
        return null;
    }
    return [width, height];
}

function rememberStableSize(node) {
    const size = snapshotSize(node);
    if (!size) return;
    const prev = node.__h3StableSize;
    if (Array.isArray(prev) && Number.isFinite(prev[1]) && size[1] < prev[1] - 48) return;
    node.__h3StableSize = size;
}

function preserveNodeSize(node) {
    rememberStableSize(node);
    captureNodeSize(node, node.__h3StableSize || node.size);
}

function refreshNodeLayout(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
    restoreNodeSizeSoon(node);
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

function syncModelInputs(node, segments) {
    if (!Array.isArray(node.inputs)) node.inputs = [];
    const model1Index = node.inputs.findIndex((slot) => slot?.name === "model_1");
    if (model1Index < 0) return;

    for (let i = MAX_SEGMENTS; i > segments; i--) {
        if (i <= 1) continue;
        const idx = node.inputs.findIndex((slot) => slot?.name === `model_${i}`);
        if (idx < 0) continue;
        if (typeof node.removeInput === "function") {
            node.removeInput(idx);
        } else {
            node.inputs.splice(idx, 1);
        }
    }

    for (let i = 1; i <= segments; i++) {
        const desired = model1Index + (i - 1);
        if (i > 1) {
            ensureInputAt(node, `model_${i}`, "MODEL", desired);
        }
        const input = node.inputs.find((slot) => slot?.name === `model_${i}`);
        if (input) {
            input.hidden = false;
            input.label = modelLabel(i, segments);
        }
    }
}

function hideLegacyPromptWidgets(node) {
    for (let i = 1; i <= MAX_SEGMENTS; i++) {
        setWidgetVisible(findWidget(node, `prompt_${i}`), false);
    }
    setWidgetVisible(findWidget(node, "loop_prompt"), false);
}

function wrapSizeGuard(node, widget) {
    if (!widget || widget.__h3StudioSizeGuard) return;
    widget.__h3StudioSizeGuard = true;
    const originalCallback = widget.callback;
    widget.callback = function (...args) {
        preserveNodeSize(node);
        const result = originalCallback?.apply(this, args);
        queueMicrotask(() => syncSegmentSlots(node));
        return result;
    };
}

function syncSegmentSlots(node) {
    if (!isTarget(node)) return;
    preserveNodeSize(node);
    hideLegacyPromptWidgets(node);
    const widget = findWidget(node, "segments");
    if (widget) {
        const raw = Number(widget.value ?? 3);
        const segments = Math.min(MAX_SEGMENTS, Math.max(1, Number.isFinite(raw) ? Math.round(raw) : 3));
        syncModelInputs(node, segments);
        syncLoopWidgets(node, segments);
    }
    refreshNodeLayout(node);
}

function isSeamlessLoop(node) {
    const value = findWidget(node, "seamless_loop")?.value;
    return value === true || value === "true" || value === 1;
}

function syncLoopWidgets(node, segments) {
    const on = isSeamlessLoop(node);
    setWidgetVisible(findWidget(node, "loop_prompt"), false);

    if (!Array.isArray(node.inputs)) return;
    const model1Index = node.inputs.findIndex((slot) => slot?.name === "model_1");
    if (on && model1Index >= 0) {
        ensureInputAt(node, "model_loop", "MODEL", model1Index + segments);
        const loopModel = node.inputs.find((slot) => slot?.name === "model_loop");
        if (loopModel) {
            loopModel.hidden = false;
            loopModel.label = "model_loop (Loop)";
        }
        return;
    }
    removeInputByName(node, "model_loop");
}

function installSegmentCallback(node) {
    if (!isTarget(node)) return;
    if (!node.__h3StudioAutoChainSegmentsInstalled) {
        node.__h3StudioAutoChainSegmentsInstalled = true;
        wrapSizeGuard(node, findWidget(node, "segments"));
        wrapSizeGuard(node, findWidget(node, "seamless_loop"));
    }
    rememberStableSize(node);
    syncSegmentSlots(node);
}

app.registerExtension({
    name: "H3Studio.AutoChainSegmentVisibility",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isTargetDefinition(nodeType, nodeData)) return;

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = originalOnConfigure?.apply(this, args);
            queueMicrotask(() => installSegmentCallback(this));
            return result;
        };

        const originalOnResize = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function (size) {
            const result = originalOnResize?.apply(this, arguments);
            rememberStableSize(this);
            return result;
        };

        const originalOnWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
            const result = originalOnWidgetChanged?.apply(this, arguments);
            const widgetName = widget?.name ?? name;
            if (widgetName === "segments" || widgetName === "seamless_loop") {
                preserveNodeSize(this);
                queueMicrotask(() => syncSegmentSlots(this));
            }
            return result;
        };
    },

    async nodeCreated(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => installSegmentCallback(node));
    },

    loadedGraphNode(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => installSegmentCallback(node));
    },

    async afterConfigureGraph() {
        for (const node of app.graph?._nodes ?? []) {
            if (isTarget(node)) installSegmentCallback(node);
        }
    },
});

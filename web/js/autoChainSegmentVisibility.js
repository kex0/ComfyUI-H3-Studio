import { app } from "../../scripts/app.js";

const TARGET_CLASS = "H3StudioAutoChain";
const TARGET_CLASSES = new Set(["H3StudioAutoChain", "H3StudioAutoChainClipFixer"]);

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

function setWidgetVisible(widget, visible) {
    if (!widget) return;
    widget.hidden = !visible;
    if (visible) {
        delete widget.computeSize;
    } else {
        widget.computeSize = () => [0, -4];
    }
}

function hideLegacyPromptWidgets(node) {
    for (const widget of node.widgets || []) {
        const name = String(widget?.name || "");
        if (name === "loop_prompt" || /^prompt_\d+$/.test(name)) {
            setWidgetVisible(widget, false);
        }
    }
}

function isLegacyModelSlot(name) {
    return name === "model_loop" || /^model_\d+$/.test(name);
}

function stripLegacyModelSockets(node) {
    if (!Array.isArray(node.inputs)) return;
    const expand = node.expandToFitContent;
    if (typeof expand === "function") node.expandToFitContent = function () {};
    try {
        for (let i = node.inputs.length - 1; i >= 0; i--) {
            if (!isLegacyModelSlot(String(node.inputs[i]?.name || ""))) continue;
            if (typeof node.removeInput === "function") node.removeInput(i);
            else node.inputs.splice(i, 1);
        }
    } finally {
        if (typeof expand === "function") node.expandToFitContent = expand;
    }
}

function installSegmentCallback(node) {
    if (!isTarget(node)) return;
    hideLegacyPromptWidgets(node);
    if (node.__h3StudioAutoChainSegmentsInstalled) return;
    node.__h3StudioAutoChainSegmentsInstalled = true;
    stripLegacyModelSockets(node);
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

        const originalOnWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
            const result = originalOnWidgetChanged?.apply(this, arguments);
            const widgetName = widget?.name ?? name;
            if (widgetName === "segments" || widgetName === "seamless_loop") {
                hideLegacyPromptWidgets(this);
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

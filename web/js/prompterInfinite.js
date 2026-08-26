import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

const TARGET = "H3StudioLocalInfinitePrompter";
const LOCAL_GGUF = "Local GGUF";

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
    return [...targetNames(node)].some((name) => name === TARGET);
}

function findWidget(node, name) {
    return node?.widgets?.find((widget) => widget?.name === name);
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

function refreshNodeLayout(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

function syncGgufPath(node) {
    if (!isTarget(node)) return;
    const model = String(findWidget(node, "model")?.value || "");
    setWidgetVisible(findWidget(node, "gguf_path"), model === LOCAL_GGUF);
    refreshNodeLayout(node);
}

async function refreshModelCombo(node) {
    if (!isTarget(node)) return;
    const widget = findWidget(node, "model");
    if (!widget) return;
    try {
        const response = await api.fetchApi("/h3_studio_prompter/models");
        if (!response.ok) return;
        const data = await response.json();
        const values = Array.isArray(data?.models) ? data.models.filter(Boolean) : [];
        if (!values.length) return;
        widget.options = widget.options || {};
        widget.options.values = values;
        if (!values.includes(widget.value)) widget.value = values[0];
    } catch (_) {
        // Combo stays on the Python INPUT_TYPES snapshot.
    }
    syncGgufPath(node);
}

function install(node) {
    if (!isTarget(node) || node.__h3StudioPrompterInstalled) {
        syncGgufPath(node);
        return;
    }
    node.__h3StudioPrompterInstalled = true;
    const model = findWidget(node, "model");
    if (model) {
        const original = model.callback;
        model.callback = function (...args) {
            const result = original?.apply(this, args);
            queueMicrotask(() => syncGgufPath(node));
            return result;
        };
    }
    void refreshModelCombo(node);
}

app.registerExtension({
    name: "H3Studio.LocalInfinitePrompter",

    async nodeCreated(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => install(node));
    },

    loadedGraphNode(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => install(node));
    },
});

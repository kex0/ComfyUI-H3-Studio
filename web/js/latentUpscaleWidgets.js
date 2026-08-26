import { app } from "../../scripts/app.js";

const TARGET_CLASSES = new Set(["H3StudioAutoChain", "H3StudioMusicVideo"]);
const MODE_MULTIPLIER = "scale by multiplier";

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
    requestAnimationFrame?.(() => {
        try {
            if (typeof node.computeSize !== "function" || typeof node.setSize !== "function") return;
            const computed = node.computeSize();
            if (!Array.isArray(computed) || !Number.isFinite(computed[1])) return;
            const currentWidth = Array.isArray(node.size) && Number.isFinite(node.size[0])
                ? node.size[0]
                : computed[0];
            const currentHeight = Array.isArray(node.size) && Number.isFinite(node.size[1])
                ? node.size[1]
                : computed[1];
            node.setSize([
                Math.max(currentWidth, computed[0]),
                Math.max(currentHeight, computed[1]),
            ]);
        } catch (_) {
            // Visibility itself is more important than compact resizing.
        }
    });
}

function widgetOn(widget) {
    const value = widget?.value;
    return value === true || value === 1 || value === "true" || value === "True";
}

function syncLatentUpscaleWidgets(node) {
    if (!isTarget(node)) return;
    const enabled = widgetOn(findWidget(node, "latent_upscale"));
    const mode = String(findWidget(node, "latent_upscale_mode")?.value || MODE_MULTIPLIER);
    const multiplier = mode === MODE_MULTIPLIER;
    setWidgetVisible(findWidget(node, "latent_upscale_mode"), enabled);
    setWidgetVisible(findWidget(node, "latent_upscale_scale"), enabled && multiplier);
    setWidgetVisible(findWidget(node, "latent_upscale_megapixels"), enabled && !multiplier);
    setWidgetVisible(findWidget(node, "latent_upscale_precision"), enabled);
    refreshNodeLayout(node);
}

function installLatentUpscaleSync(node) {
    if (!isTarget(node) || node.__h3StudioLatentUpscaleInstalled) {
        syncLatentUpscaleWidgets(node);
        return;
    }
    node.__h3StudioLatentUpscaleInstalled = true;
    for (const name of ["latent_upscale", "latent_upscale_mode"]) {
        const widget = findWidget(node, name);
        if (!widget) continue;
        const original = widget.callback;
        widget.callback = function (...args) {
            const result = original?.apply(this, args);
            queueMicrotask(() => syncLatentUpscaleWidgets(node));
            return result;
        };
    }
    syncLatentUpscaleWidgets(node);
}

app.registerExtension({
    name: "H3Studio.LatentUpscaleWidgets",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isTargetDefinition(nodeType, nodeData)) return;

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = originalOnConfigure?.apply(this, args);
            queueMicrotask(() => installLatentUpscaleSync(this));
            return result;
        };

        const originalOnWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function (name, value, oldValue, widget) {
            const result = originalOnWidgetChanged?.apply(this, arguments);
            const widgetName = widget?.name ?? name;
            if (widgetName === "latent_upscale" || widgetName === "latent_upscale_mode") {
                queueMicrotask(() => syncLatentUpscaleWidgets(this));
            }
            return result;
        };
    },

    async nodeCreated(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => installLatentUpscaleSync(node));
    },

    loadedGraphNode(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => installLatentUpscaleSync(node));
    },

    async afterConfigureGraph() {
        for (const node of app.graph?._nodes ?? []) {
            if (isTarget(node)) installLatentUpscaleSync(node);
        }
    },
});

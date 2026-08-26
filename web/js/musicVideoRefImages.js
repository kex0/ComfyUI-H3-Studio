import { app } from "../../scripts/app.js";

const TARGET_CLASSES = new Set(["H3StudioMusicVideo", "H3StudioAutoChain"]);
const MAX_REF_IMAGES = 9;
const HIDDEN_LEGACY = new Set(["first_frame", "reference_image"]);
const LAST_FRAME_SLOT = /^last_frame_\d+$/;

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

function slotLinked(input) {
    if (!input) return false;
    if (input.link != null && input.link !== -1) return true;
    if (Array.isArray(input.links) && input.links.length) return true;
    return false;
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

function isLegacySlot(name) {
    return HIDDEN_LEGACY.has(name) || LAST_FRAME_SLOT.test(name || "");
}

function syncRefImages(node) {
    if (!isTarget(node) || !Array.isArray(node.inputs)) return;

    for (const input of [...node.inputs]) {
        const name = input?.name;
        if (!isLegacySlot(name)) continue;
        if (slotLinked(input)) input.hidden = true;
        else removeInputByName(node, name);
    }

    const firstIdx = node.inputs.findIndex((slot) => slot?.name === "reference_image_1");
    if (firstIdx < 0) return;

    let showCount = 1;
    for (let i = 1; i < MAX_REF_IMAGES; i++) {
        const input = node.inputs.find((slot) => slot?.name === `reference_image_${i}`);
        if (slotLinked(input)) showCount = i + 1;
        else break;
    }

    for (let i = MAX_REF_IMAGES; i > showCount; i--) {
        const input = node.inputs.find((slot) => slot?.name === `reference_image_${i}`);
        if (slotLinked(input)) continue;
        removeInputByName(node, `reference_image_${i}`);
    }

    for (let i = 1; i <= showCount; i++) {
        ensureInputAt(node, `reference_image_${i}`, "IMAGE", firstIdx + (i - 1));
        const input = node.inputs.find((slot) => slot?.name === `reference_image_${i}`);
        if (input) {
            input.hidden = false;
            input.label = `reference_image_${i}`;
        }
    }

    refreshNodeLayout(node);
}

function installRefImageSync(node) {
    if (!isTarget(node)) return;
    syncRefImages(node);
}

app.registerExtension({
    name: "H3Studio.MusicVideoRefImages",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!isTargetDefinition(nodeType, nodeData)) return;

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = originalOnConfigure?.apply(this, args);
            queueMicrotask(() => installRefImageSync(this));
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = originalOnConnectionsChange?.apply(this, args);
            queueMicrotask(() => syncRefImages(this));
            return result;
        };
    },

    async nodeCreated(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => installRefImageSync(node));
    },

    loadedGraphNode(node) {
        if (!isTarget(node)) return;
        queueMicrotask(() => installRefImageSync(node));
    },

    async afterConfigureGraph() {
        for (const node of app.graph?._nodes ?? []) {
            if (isTarget(node)) installRefImageSync(node);
        }
    },
});

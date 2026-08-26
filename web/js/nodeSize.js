function readSize(size) {
    if (!Array.isArray(size) || size.length < 2) return null;
    const width = Number(size[0]);
    const height = Number(size[1]);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
    return [width, height];
}

function captureNodeSize(node, size) {
    const next = readSize(size);
    if (!node || !next) return;
    node.__h3RestoreSize = next;
}

function restoreNodeSize(node) {
    const next = readSize(node?.__h3RestoreSize);
    if (!node || !next) return false;
    node.setSize?.(next);
    if (Array.isArray(node.size)) {
        node.size[0] = next[0];
        node.size[1] = next[1];
    } else {
        node.size = next;
    }
    node._widgetSlotsDirty = true;
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
    return true;
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
            setTimeout(() => {
                if (node.__h3RestoreToken === token) node.__h3RestoreSize = null;
            }, 250);
        });
    });
}

export { captureNodeSize, restoreNodeSize, restoreNodeSizeSoon };

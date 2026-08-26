import { app } from "../../scripts/app.js";

const NODE_NAME = "H3StudioBuilder";
const LINKS_PROP = "h3_studio_builder_media_links";
const MAX_IMAGES = 9;
const MAX_VIDEOS = 3;
const MAX_AUDIOS = 3;
const MAX_MIXED = 12;
const COLOR_IMAGE = "#FFD500";

let onVirtualLinksChanged = null;
let patchedPrompt = false;
let linkMenu = null;
let pointerCaptureCleanup = null;
let pointerCaptureCanvas = null;

export function setOnVirtualLinksChanged(fn) {
    onVirtualLinksChanged = typeof fn === "function" ? fn : null;
}

function isTarget(node) {
    return [
        node?.type,
        node?.comfyClass,
        node?.constructor?.type,
        node?.constructor?.comfyClass,
        node?.constructor?.ComfyClass,
        node?.constructor?.nodeData?.name,
    ].filter(Boolean).includes(NODE_NAME);
}

function notifyLinksChanged(node) {
    onVirtualLinksChanged?.(node);
}

export function ensureLinks(node) {
    node.properties ||= {};
    if (!Array.isArray(node.properties[LINKS_PROP])) node.properties[LINKS_PROP] = [];
    return node.properties[LINKS_PROP];
}

function isSameNode(left, right) {
    if (!left || !right) return false;
    if (left === right) return true;
    const leftId = Number(left.id);
    const rightId = Number(right.id);
    return Number.isFinite(leftId) && Number.isFinite(rightId) && leftId === rightId;
}

function resequence(node) {
    const counts = { image: 0, video: 0, audio: 0 };
    ensureLinks(node).forEach((link) => {
        const mediaType = String(link.media_type || "image").toLowerCase();
        const sequenceType = Object.hasOwn(counts, mediaType) ? mediaType : "image";
        counts[sequenceType] += 1;
        link.order = counts[sequenceType];
    });
}

export function normalizeLinks(node, removeMissing = true) {
    const links = ensureLinks(node);
    const normalized = [];
    const seen = new Set();
    for (const link of links) {
        const sourceId = Number(link?.source_id);
        const sourceSlot = Number(link?.source_slot) || 0;
        const mediaType = String(link?.media_type || "image").toLowerCase();
        if (!Number.isFinite(sourceId) || !["image", "video", "audio"].includes(mediaType)) continue;
        if (Number.isFinite(Number(node?.id)) && sourceId === Number(node.id)) continue;
        const key = `${sourceId}:${sourceSlot}`;
        if (seen.has(key)) continue;
        const canResolveSource = typeof app.graph?.getNodeById === "function";
        const source = canResolveSource ? app.graph.getNodeById(sourceId) : null;
        if (removeMissing && canResolveSource && !source) continue;
        seen.add(key);
        normalized.push({ ...link, source_id: sourceId, source_slot: sourceSlot, media_type: mediaType });
    }
    const changed = normalized.length !== links.length || normalized.some((link, index) => {
        const previous = links[index];
        return !previous
            || Number(previous.source_id) !== link.source_id
            || Number(previous.source_slot) !== link.source_slot
            || String(previous.media_type || "image").toLowerCase() !== link.media_type;
    });
    if (changed) node.properties[LINKS_PROP] = normalized;
    resequence(node);
    return ensureLinks(node);
}

function getSlotType(slot) {
    return String(slot?.type || slot?.datatype || slot?.label || "").toUpperCase();
}

export function getMediaType(sourceType, sourceNode = null) {
    const type = String(sourceType || "").toUpperCase();
    if (type.includes("AUDIO")) return "audio";
    if (type.includes("VIDEO")) return "video";
    if (type.includes("IMAGE")) return "image";
    const name = String(sourceNode?.comfyClass || sourceNode?.type || "").toLowerCase();
    if (name.includes("audio")) return "audio";
    if (name.includes("video")) return "video";
    return "image";
}

function widgetPath(widget) {
    const value = widget?.value;
    if (typeof value === "string" && value.trim()) return value.replace(/\\/g, "/");
    if (value && typeof value === "object") {
        const name = value.filename || value.path || value.name;
        if (typeof name === "string" && name.trim()) return name.replace(/\\/g, "/");
    }
    return "";
}

export function sourceFilePath(sourceNode) {
    if (!sourceNode?.widgets) return "";
    const preferred = ["image", "video", "audio", "file"];
    for (const name of preferred) {
        const widget = sourceNode.widgets.find((item) => item?.name === name);
        const path = widgetPath(widget);
        if (path) return path;
    }
    for (const widget of sourceNode.widgets) {
        const path = widgetPath(widget);
        if (path && /\.(png|jpe?g|webp|gif|bmp|mp4|webm|mov|mkv|wav|mp3|flac|ogg|m4a)$/i.test(path)) return path;
    }
    return "";
}

export function isSocketMedia(item) {
    return item?.source === "socket" || Number(item?.socket) > 0;
}

function socketKey(link) {
    return `${Number(link.source_id)}:${Number(link.source_slot)}`;
}

function uploadedCounts(state) {
    const counts = { image: 0, video: 0, audio: 0, total: 0 };
    for (const item of state?.media || []) {
        if (isSocketMedia(item)) continue;
        const kind = String(item?.kind || "image");
        if (!Object.hasOwn(counts, kind)) continue;
        counts[kind] += 1;
        counts.total += 1;
    }
    return counts;
}

export function canAccept(node, mediaType) {
    if (!["image", "video", "audio"].includes(mediaType)) return false;
    const caps = { image: MAX_IMAGES, video: MAX_VIDEOS, audio: MAX_AUDIOS };
    const uploaded = uploadedCounts(node.__h3BuilderUi?.state);
    const links = ensureLinks(node);
    if (uploaded.total + links.length >= MAX_MIXED) return false;
    const kindCount = uploaded[mediaType] + links.filter((link) => String(link.media_type || "image") === mediaType).length;
    return kindCount < caps[mediaType];
}

function hasVirtualLink(node, sourceId, sourceSlot) {
    return ensureLinks(node).some((link) =>
        Number(link.source_id) === Number(sourceId) && Number(link.source_slot) === Number(sourceSlot)
    );
}

export function addVirtualLink(targetNode, sourceNode, sourceSlot, sourceType, mediaType = null) {
    if (!targetNode || !sourceNode || isSameNode(targetNode, sourceNode)) return false;
    const sourceId = Number(sourceNode.id);
    if (!Number.isFinite(sourceId)) return false;
    mediaType ||= getMediaType(sourceType, sourceNode);
    if (hasVirtualLink(targetNode, sourceId, sourceSlot)) return false;
    if (!canAccept(targetNode, mediaType)) return false;
    ensureLinks(targetNode).push({
        source_id: sourceId,
        source_slot: Number(sourceSlot) || 0,
        source_type: sourceType || "*",
        media_type: mediaType,
        order: 0,
    });
    resequence(targetNode);
    targetNode.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    app.graph?.change?.();
    notifyLinksChanged(targetNode);
    return true;
}

export function removeVirtualLink(node, index) {
    const links = ensureLinks(node);
    if (index < 0 || index >= links.length) return false;
    links.splice(index, 1);
    resequence(node);
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    app.graph?.change?.();
    notifyLinksChanged(node);
    return true;
}

export function mediaItemTitle(item, sourceNode = null) {
    const path = String(item?.path || "").replace(/\\/g, "/");
    const file = path.split("/").pop();
    if (file) return file;
    const source = sourceNode || app.graph?.getNodeById?.(Number(item?.source_id));
    return String(source?.title || source?.type || "Media socket");
}

export function syncBuilderMediaList(node, state) {
    if (!node || !state || !Array.isArray(state.media)) return false;
    const links = normalizeLinks(node);
    const keys = new Set(links.map(socketKey));
    let changed = false;
    for (let index = state.media.length - 1; index >= 0; index -= 1) {
        const item = state.media[index];
        if (!isSocketMedia(item)) continue;
        const key = `${Number(item.source_id)}:${Number(item.source_slot)}`;
        if (keys.has(key)) continue;
        state.media.splice(index, 1);
        changed = true;
    }
    const byKey = new Map();
    for (const item of state.media) {
        if (isSocketMedia(item)) byKey.set(`${Number(item.source_id)}:${Number(item.source_slot)}`, item);
    }
    links.forEach((link, index) => {
        const key = socketKey(link);
        const source = app.graph?.getNodeById?.(Number(link.source_id));
        const path = sourceFilePath(source);
        const kind = String(link.media_type || "image");
        const socket = index + 1;
        const existing = byKey.get(key);
        if (existing) {
            if (existing.socket !== socket || existing.kind !== kind || existing.path !== path
                || existing.source !== "socket"
                || Number(existing.source_id) !== Number(link.source_id)
                || Number(existing.source_slot) !== Number(link.source_slot)) {
                existing.source = "socket";
                existing.source_id = Number(link.source_id);
                existing.source_slot = Number(link.source_slot);
                existing.socket = socket;
                existing.kind = kind;
                existing.path = path;
                changed = true;
            }
            return;
        }
        state.media.push({
            source: "socket",
            source_id: Number(link.source_id),
            source_slot: Number(link.source_slot),
            socket,
            kind,
            path,
            enabled: true,
            description: "",
            duration: 0,
            has_soundtrack: false,
            start: 0,
            length: 0,
            crop: null,
            first_frame: false,
            regions: [],
        });
        changed = true;
    });
    return changed;
}

export function syncLinksFromMediaOrder(node, state) {
    if (!node || !state) return;
    const byKey = new Map(ensureLinks(node).map((link) => [socketKey(link), link]));
    const next = [];
    for (const item of state.media || []) {
        if (!isSocketMedia(item)) continue;
        const link = byKey.get(`${Number(item.source_id)}:${Number(item.source_slot)}`);
        if (!link) continue;
        next.push(link);
    }
    node.properties ||= {};
    node.properties[LINKS_PROP] = next;
    resequence(node);
    next.forEach((link, index) => {
        const item = (state.media || []).find((entry) =>
            isSocketMedia(entry)
            && Number(entry.source_id) === Number(link.source_id)
            && Number(entry.source_slot) === Number(link.source_slot)
        );
        if (item) item.socket = index + 1;
    });
}

function getMediaInputIndex(node) {
    return node?.inputs?.findIndex((input) => String(input?.name || "") === "media") ?? -1;
}

function getConnectionPosition(node, isInput, slotIndex) {
    const normalize = (point) => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])
        ? [point[0], point[1]]
        : null;
    const modern = isInput
        ? normalize(node?.getInputPos?.(slotIndex))
        : normalize(node?.getOutputPos?.(slotIndex));
    if (modern) return modern;
    const out = [0, 0];
    try {
        if (typeof node?.getConnectionPos === "function") {
            const legacy = normalize(node.getConnectionPos(isInput, slotIndex, out)) || normalize(out);
            if (legacy) return legacy;
        }
    } catch {
        // LiteGraph geometry fallback below.
    }
    const slot = 40 + Math.max(0, slotIndex) * 20;
    return isInput
        ? [Number(node?.pos?.[0] || 0), Number(node?.pos?.[1] || 0) + slot]
        : [Number(node?.pos?.[0] || 0) + Number(node?.size?.[0] || 160), Number(node?.pos?.[1] || 0) + slot];
}

function getMediaDot(node) {
    const index = getMediaInputIndex(node);
    if (index < 0) return null;
    const point = getConnectionPosition(node, true, index);
    return { x: point[0], y: point[1] };
}

function graphPosition(canvas, event) {
    try {
        canvas.adjustMouseEvent?.(event);
    } catch {
        // Older LiteGraph builds do not expose adjustMouseEvent.
    }
    if (Array.isArray(canvas?.graph_mouse)) return [canvas.graph_mouse[0], canvas.graph_mouse[1]];
    if (Number.isFinite(event?.canvasX) && Number.isFinite(event?.canvasY)) return [event.canvasX, event.canvasY];
    const rect = canvas?.canvas?.getBoundingClientRect?.();
    const scale = canvas?.ds?.scale || 1;
    const offset = canvas?.ds?.offset || [0, 0];
    if (rect && Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY)) {
        return [(event.clientX - rect.left) / scale - offset[0], (event.clientY - rect.top) / scale - offset[1]];
    }
    return [0, 0];
}

function pointerGraphPosition(canvas, event) {
    if (Number.isFinite(event?.canvasX) && Number.isFinite(event?.canvasY)) return [event.canvasX, event.canvasY];
    const rect = canvas?.canvas?.getBoundingClientRect?.();
    if (rect && Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY)) {
        const scale = canvas?.ds?.scale || 1;
        const offset = canvas?.ds?.offset || [0, 0];
        return [(event.clientX - rect.left) / scale - offset[0], (event.clientY - rect.top) / scale - offset[1]];
    }
    return graphPosition(canvas, event);
}

function clientPosition(canvas, point) {
    const rect = canvas?.canvas?.getBoundingClientRect?.();
    if (!rect) return null;
    const scale = canvas?.ds?.scale || 1;
    const offset = canvas?.ds?.offset || [0, 0];
    return { x: rect.left + (point[0] + offset[0]) * scale, y: rect.top + (point[1] + offset[1]) * scale };
}

function getNativeGraphLink(graph, linkId) {
    if (!graph || linkId == null) return null;
    for (const links of [graph.links, graph._links]) {
        if (!links) continue;
        if (typeof links.get === "function") {
            const link = links.get(linkId) ?? links.get(String(linkId));
            if (link) return link;
        }
        const link = links[linkId] ?? links[String(linkId)];
        if (link) return link;
    }
    return null;
}

function convertNativeMediaConnection(targetNode, inputIndex, linkInfo = null) {
    if (!isTarget(targetNode) || targetNode.__h3BuilderVirtualWireClearing) return false;
    const input = targetNode.inputs?.[inputIndex];
    if (!input || !/^media(?:_\d+)?$/i.test(String(input.name || ""))) return false;
    const graph = targetNode.graph || app.graph;
    const linkId = input.link ?? linkInfo?.id ?? linkInfo?.link_id ?? linkInfo?.linkId;
    const nativeLink = getNativeGraphLink(graph, linkId) || linkInfo;
    if (!nativeLink) return false;
    const directSourceCandidate = nativeLink.origin_node || nativeLink.originNode
        || nativeLink.fromNode || nativeLink.sourceNode;
    const directSource = directSourceCandidate && typeof directSourceCandidate === "object"
        ? directSourceCandidate
        : null;
    const sourceId = nativeLink.origin_id ?? nativeLink.originId
        ?? nativeLink.from_id ?? nativeLink.fromId
        ?? (directSourceCandidate && typeof directSourceCandidate !== "object" ? directSourceCandidate : directSource?.id);
    const sourceNode = directSource || graph?.getNodeById?.(Number(sourceId));
    if (!sourceNode || isSameNode(targetNode, sourceNode)) return false;
    const rawSourceSlot = nativeLink.origin_slot ?? nativeLink.originSlot
        ?? nativeLink.from_slot ?? nativeLink.fromSlot ?? nativeLink.from?.slot ?? 0;
    const parsedSourceSlot = Number(rawSourceSlot);
    const sourceSlot = Number.isFinite(parsedSourceSlot) ? parsedSourceSlot : 0;
    const output = sourceNode.outputs?.[sourceSlot] || {};
    const sourceType = getSlotType(output)
        || String(nativeLink.type || nativeLink.origin_type || nativeLink.originType || "*").toUpperCase();
    const exists = hasVirtualLink(targetNode, sourceNode.id, sourceSlot);
    if (!exists && !canAccept(targetNode, getMediaType(sourceType, sourceNode))) return false;
    addVirtualLink(targetNode, sourceNode, sourceSlot, sourceType);
    targetNode.__h3BuilderVirtualWireClearing = true;
    try {
        if (targetNode.inputs?.[inputIndex]?.link != null && typeof targetNode.disconnectInput === "function") {
            targetNode.disconnectInput(inputIndex);
        } else if (linkId != null && typeof graph?.removeLink === "function") {
            graph.removeLink(linkId);
        }
        if (targetNode.inputs?.[inputIndex]) targetNode.inputs[inputIndex].link = null;
    } finally {
        targetNode.__h3BuilderVirtualWireClearing = false;
    }
    targetNode.setDirtyCanvas?.(true, true);
    graph?.setDirtyCanvas?.(true, true);
    return true;
}

function scheduleNativeMediaConnectionConversion(targetNode, inputIndex, linkInfo = null) {
    setTimeout(() => convertNativeMediaConnection(targetNode, inputIndex, linkInfo), 0);
    if (!linkInfo) setTimeout(() => convertNativeMediaConnection(targetNode, inputIndex), 50);
}

function cubicPoint(start, end, t) {
    const cp1 = [start[0] + 80, start[1]];
    const cp2 = [end[0] - 80, end[1]];
    const mt = 1 - t;
    return [
        mt * mt * mt * start[0] + 3 * mt * mt * t * cp1[0] + 3 * mt * t * t * cp2[0] + t * t * t * end[0],
        mt * mt * mt * start[1] + 3 * mt * mt * t * cp1[1] + 3 * mt * t * t * cp2[1] + t * t * t * end[1],
    ];
}

function linkGeometry(targetNode, link) {
    const sourceNode = targetNode.graph?.getNodeById?.(Number(link.source_id));
    const dot = getMediaDot(targetNode);
    if (!sourceNode || !dot) return null;
    const source = getConnectionPosition(sourceNode, false, Number(link.source_slot) || 0);
    const target = [dot.x, dot.y];
    return { sourceNode, source, target, mid: cubicPoint(source, target, 0.5) };
}

function getComfyLinkTypeColor(type) {
    const colors = globalThis.LGraphCanvas?.link_type_colors || {};
    const raw = String(type || "");
    const candidates = [raw, raw.toUpperCase(), raw.toLowerCase()].filter(Boolean);
    for (const candidate of candidates) {
        if (colors[candidate]) return colors[candidate];
    }
    return "";
}

function linkHighlighted(canvas, targetNode, sourceNode) {
    return Boolean(
        targetNode?.selected || sourceNode?.selected
        || canvas?.selectedItems?.has?.(targetNode) || canvas?.selectedItems?.has?.(sourceNode)
        || canvas?.selected_nodes?.[targetNode?.id] || canvas?.selected_nodes?.[sourceNode?.id]
    );
}

function linkColor(canvas, targetNode, sourceNode, link) {
    if (linkHighlighted(canvas, targetNode, sourceNode)) return "#FFF";
    const typedColor = getComfyLinkTypeColor(link?.source_type);
    if (typedColor) return typedColor;
    return String(link?.media_type || "image") === "image"
        ? COLOR_IMAGE
        : (canvas?.default_link_color || globalThis.LiteGraph?.LINK_COLOR || "#AAD");
}

function hitTestLinks(graph, x, y) {
    let best = null;
    for (const targetNode of graph?._nodes || []) {
        if (!isTarget(targetNode)) continue;
        ensureLinks(targetNode).forEach((link, index) => {
            const geometry = linkGeometry(targetNode, link);
            if (!geometry) return;
            const distance = Math.hypot(x - geometry.mid[0], y - geometry.mid[1]);
            if (distance <= 18 && (!best || distance < best.distance)) {
                best = { targetNode, index, point: geometry.mid, distance };
            }
        });
    }
    return best;
}

function closeLinkMenu() {
    linkMenu?.close?.();
    linkMenu?.remove?.();
    linkMenu = null;
}

function openLinkMenu(canvas, hit, event) {
    closeLinkMenu();
    const anchor = clientPosition(canvas, hit.point) || { x: event?.clientX || 0, y: event?.clientY || 0 };
    const menuEvent = typeof PointerEvent === "function"
        ? new PointerEvent("pointerdown", { clientX: anchor.x + 8, clientY: anchor.y + 8, bubbles: true, cancelable: true })
        : new MouseEvent("mousedown", { clientX: anchor.x + 8, clientY: anchor.y + 8, bubbles: true, cancelable: true });
    let menuInstance = null;
    const remove = () => {
        removeVirtualLink(hit.targetNode, hit.index);
        menuInstance?.close?.();
        menuInstance?.remove?.();
        if (linkMenu === menuInstance) linkMenu = null;
    };
    if (globalThis.LiteGraph?.ContextMenu) {
        menuInstance = new globalThis.LiteGraph.ContextMenu([
            { content: "Delete", callback: remove },
        ], { event: menuEvent });
        linkMenu = menuInstance;
    }
}

function getSlotIndex(slots, rawSlot) {
    if (typeof rawSlot === "number") return slots?.[rawSlot] ? rawSlot : -1;
    for (const key of ["slot_index", "slot", "index"]) {
        const value = rawSlot?.[key];
        if (typeof value === "number" && slots?.[value]) return value;
    }
    if (Array.isArray(slots) && rawSlot) {
        const direct = slots.indexOf(rawSlot);
        if (direct >= 0) return direct;
        const name = typeof rawSlot === "string" ? rawSlot : rawSlot?.name;
        if (name) return slots.findIndex((slot) => slot?.name === name);
    }
    return -1;
}

function getPendingConnectorLink(canvas) {
    const link = canvas?.linkConnector?.renderLinks?.at?.(0);
    if (!link) return null;
    const endpointNode = link.node || link.fromNode || link.originNode || link.sourceNode || link.toNode || link.targetNode
        || link.inputNode || link.outputNode;
    const endpointSlot = link.fromSlot ?? link.slot ?? link.output ?? link.input ?? link.toSlot ?? {};
    const toType = String(link.toType || link.targetType || link.targetSlotType || "").toLowerCase();
    let direction = toType.includes("output") ? "from_input" : "from_output";
    const inputIndex = getSlotIndex(endpointNode?.inputs, endpointSlot);
    const outputIndex = getSlotIndex(endpointNode?.outputs, endpointSlot);
    if (inputIndex >= 0 && outputIndex < 0) direction = "from_input";
    if (outputIndex >= 0 && inputIndex < 0) direction = "from_output";
    if (direction === "from_input") return null;
    const output = endpointNode?.outputs?.[outputIndex] || endpointSlot || {};
    return {
        direction,
        sourceNode: endpointNode,
        sourceSlot: Math.max(0, outputIndex),
        sourceType: getSlotType(output),
    };
}

function connectingOutput(canvas) {
    const node = canvas?.connecting_node || canvas?.connectingNode;
    if (!node) return null;
    const raw = canvas.connecting_output ?? canvas.connecting_slot ?? canvas.connecting_output_slot;
    if (raw == null && canvas.connecting_input) return null;
    const index = typeof raw === "number" ? raw : Number(raw?.slot_index ?? raw?.slot ?? 0);
    const output = node.outputs?.[Number.isFinite(index) ? index : 0] || raw || {};
    return {
        sourceNode: node,
        sourceSlot: Number.isFinite(index) ? index : 0,
        sourceType: getSlotType(output),
    };
}

function drawLinks(canvas, ctx) {
    const graph = canvas?.graph || app.graph;
    if (!graph?._nodes || canvas.links_render_mode === globalThis.LiteGraph?.HIDDEN_LINK) return;
    for (const targetNode of graph._nodes) {
        if (!isTarget(targetNode)) continue;
        for (const link of ensureLinks(targetNode)) {
            const geometry = linkGeometry(targetNode, link);
            if (!geometry) continue;
            const highlighted = linkHighlighted(canvas, targetNode, geometry.sourceNode);
            const color = linkColor(canvas, targetNode, geometry.sourceNode, link);
            const width = highlighted ? 3 : 2;
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(geometry.source[0], geometry.source[1]);
            ctx.bezierCurveTo(geometry.source[0] + 80, geometry.source[1], geometry.target[0] - 80, geometry.target[1], geometry.target[0], geometry.target[1]);
            ctx.lineWidth = width + 4;
            ctx.strokeStyle = canvas.render_connections_border !== false && !canvas.low_quality ? "#111" : "transparent";
            if (ctx.strokeStyle !== "transparent") ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(geometry.source[0], geometry.source[1]);
            ctx.bezierCurveTo(geometry.source[0] + 80, geometry.source[1], geometry.target[0] - 80, geometry.target[1], geometry.target[0], geometry.target[1]);
            ctx.lineWidth = width;
            ctx.strokeStyle = color;
            ctx.stroke();
            if (canvas.linkMarkerShape !== 0 && (canvas.ds?.scale ?? 1) >= 0.6 && canvas.highquality_render !== false) {
                ctx.beginPath();
                ctx.arc(geometry.mid[0], geometry.mid[1], 5, 0, Math.PI * 2);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.fillStyle = highlighted ? "#222" : "#fff";
                ctx.font = "bold 7px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(String(link.order || 1), geometry.mid[0], geometry.mid[1] + 0.3);
            }
            ctx.restore();
        }
    }
}

function installPointerCapture(canvas) {
    if (!canvas?.canvas) return false;
    if (canvas === pointerCaptureCanvas && canvas.__h3StudioBuilderPointerCapture) return true;
    pointerCaptureCleanup?.();
    pointerCaptureCleanup = null;
    pointerCaptureCanvas = canvas;
    canvas.__h3StudioBuilderPointerCapture = true;
    const handler = (event) => {
        if (event?.button > 0) return;
        const pending = getPendingConnectorLink(canvas) || connectingOutput(canvas);
        if (!pending?.sourceNode) return;
        const [x, y] = pointerGraphPosition(canvas, event);
        const target = (canvas.graph?._nodes || []).find((node) => {
            if (!isTarget(node)) return false;
            const dot = getMediaDot(node);
            return dot && Math.hypot(x - dot.x, y - dot.y) <= 18;
        });
        if (!target || isSameNode(target, pending.sourceNode)) return;
        if (!addVirtualLink(target, pending.sourceNode, pending.sourceSlot, pending.sourceType)) return;
        event.preventDefault?.();
        event.stopPropagation?.();
        event.stopImmediatePropagation?.();
        canvas.linkConnector?.reset?.();
        canvas.connecting_node = null;
        canvas.connecting_output = null;
        canvas.connecting_slot = null;
        canvas.connecting_pos = null;
        canvas.connecting_input = null;
    };
    const targets = [window, document, canvas.canvas];
    for (const target of targets) {
        target.addEventListener?.("pointerup", handler, true);
        target.addEventListener?.("mouseup", handler, true);
    }
    pointerCaptureCleanup = () => {
        for (const target of targets) {
            target.removeEventListener?.("pointerup", handler, true);
            target.removeEventListener?.("mouseup", handler, true);
        }
        canvas.__h3StudioBuilderPointerCapture = false;
        if (pointerCaptureCanvas === canvas) pointerCaptureCanvas = null;
    };
    return true;
}

function patchCanvas() {
    const canvas = app.canvas;
    if (!canvas || typeof canvas.drawConnections !== "function") return;
    installPointerCapture(canvas);
    if (canvas.__h3StudioBuilderCanvasPatched) return;
    canvas.__h3StudioBuilderCanvasPatched = true;
    const originalDraw = canvas.drawConnections;
    canvas.drawConnections = function drawConnectionsWithBuilderMedia(ctx) {
        const result = originalDraw?.apply(this, arguments);
        const connectionContext = ctx || this.bgctx || this.ctx;
        const onConnectionLayer = connectionContext?.canvas === this?.bgcanvas
            || connectionContext === this?.bgctx
            || !this?.bgcanvas;
        if (connectionContext && onConnectionLayer) drawLinks(this, connectionContext);
        return result;
    };
    const originalDown = canvas.processMouseDown;
    canvas.processMouseDown = function processMouseDownWithBuilderMedia(event) {
        const [x, y] = graphPosition(this, event);
        const hit = hitTestLinks(this.graph || app.graph, x, y);
        if (hit) {
            openLinkMenu(this, hit, event);
            event?.preventDefault?.();
            event?.stopImmediatePropagation?.();
            return true;
        }
        return originalDown?.apply(this, arguments);
    };
}

function patchGraphToPrompt() {
    if (patchedPrompt || typeof app.graphToPrompt !== "function") return;
    patchedPrompt = true;
    const original = app.graphToPrompt;
    app.graphToPrompt = async function graphToPromptWithBuilderMedia() {
        const promptData = await original.apply(this, arguments);
        const output = promptData?.output || {};
        for (const node of app.graph?._nodes || []) {
            if (!isTarget(node)) continue;
            const promptNode = output[String(node.id)];
            if (!promptNode) continue;
            promptNode.inputs ||= {};
            delete promptNode.inputs.media;
            for (let index = 1; index <= MAX_MIXED; index += 1) {
                delete promptNode.inputs[`media_${index}`];
                delete promptNode.inputs[`media_type_${index}`];
            }
            const runtimeLinks = normalizeLinks(node).filter((link) => Boolean(output[String(link.source_id)]));
            runtimeLinks.forEach((link, index) => {
                promptNode.inputs[`media_${index + 1}`] = [String(link.source_id), Number(link.source_slot) || 0];
                promptNode.inputs[`media_type_${index + 1}`] = String(link.media_type || "image");
            });
        }
        return promptData;
    };
}

function isTransportInputName(name) {
    const value = String(name || "");
    return /^media_[0-9]+$/i.test(value) || /^media_type_[0-9]+$/i.test(value);
}

function removeInputSlot(node, index) {
    const input = node?.inputs?.[index];
    if (!input) return false;
    if (input.link != null) {
        try {
            node.disconnectInput?.(index);
        } catch {
            // Slot is going away either way.
        }
        if (input.link != null) {
            try {
                node.graph?.removeLink?.(input.link);
            } catch {
                // Ignore - the slot is going away either way.
            }
            input.link = null;
        }
    }
    if (typeof node.removeInput === "function") node.removeInput(index);
    else node.inputs.splice(index, 1);
    return true;
}

export function pruneTransportInputs(nodeData) {
    const sections = [nodeData?.input?.required, nodeData?.input?.optional];
    for (const section of sections) {
        if (!section || typeof section !== "object") continue;
        for (const name of Object.keys(section)) {
            if (isTransportInputName(name)) delete section[name];
        }
    }
    if (Array.isArray(nodeData?.inputs)) {
        nodeData.inputs = nodeData.inputs.filter((input) => !isTransportInputName(input?.name));
    }
}

export function pruneTransportInputsFromNode(node) {
    if (!node || !Array.isArray(node.inputs)) return false;
    let changed = false;
    for (let index = node.inputs.length - 1; index >= 0; index -= 1) {
        const input = node.inputs[index];
        const name = String(input?.name || "");
        if (!isTransportInputName(name)) continue;
        if (/^media_\d+$/i.test(name) && input.link != null) convertNativeMediaConnection(node, index);
        removeInputSlot(node, index);
        changed = true;
    }
    if (Array.isArray(node.widgets)) {
        const stale = node.widgets.filter((widget) => /^media_type_\d+$/i.test(String(widget?.name || "")));
        if (stale.length) {
            node.widgets = node.widgets.filter((widget) => !stale.includes(widget));
            if (Array.isArray(node._widgets)) {
                node._widgets = node._widgets.filter((widget) => !stale.includes(widget));
            }
            changed = true;
        }
    }
    return changed;
}

export function labelMediaInput(node) {
    const input = node?.inputs?.find((slot) => String(slot?.name || "") === "media");
    if (!input) return;
    input.label = "Media";
    input.hidden = false;
    if (!input.type) input.type = "*";
}

export function installBuilderMediaNode(nodeType, nodeData) {
    pruneTransportInputs(nodeData);
    if (nodeType?.nodeData && nodeType.nodeData !== nodeData) pruneTransportInputs(nodeType.nodeData);
    if (nodeType.prototype.__h3StudioBuilderMediaInstalled) return;
    nodeType.prototype.__h3StudioBuilderMediaInstalled = true;
    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreatedBuilderMedia() {
        const result = originalCreated?.apply(this, arguments);
        this.properties ||= {};
        ensureLinks(this);
        normalizeLinks(this);
        pruneTransportInputsFromNode(this);
        labelMediaInput(this);
        patchCanvas();
        return result;
    };
    const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function onConnectionsChangeBuilderMedia(type, index, connected, linkInfo) {
        const result = originalConnectionsChange?.apply(this, arguments);
        const inputIndex = Number(index);
        const input = this.inputs?.[Number.isFinite(inputIndex) ? inputIndex : -1];
        if (connected && !this.__h3BuilderVirtualWireClearing && /^media(?:_\d+)?$/i.test(String(input?.name || ""))) {
            scheduleNativeMediaConnectionConversion(this, inputIndex, linkInfo);
        }
        return result;
    };
}

export function installBuilderMediaRuntime() {
    patchGraphToPrompt();
    patchCanvas();
    for (const delay of [0, 100, 500, 1200]) setTimeout(() => patchCanvas(), delay);
}

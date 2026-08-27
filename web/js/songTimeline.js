import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "H3StudioLoadSong";
const LRC_CLOCK = /^\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?(?:-(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?)?\]\s*(.*)$/;
const LRC_SECS = /^\[(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?\]\s*(.*)$/;
const RANGE_CLOCK = /^\s*\[?(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\s*-\s*(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]?\s*$/;
const RANGE_SECS = /^\s*\[?(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\]?\s*$/;
const MIN_VIEW = 0.25;
const HANDLE_PX = 8;
const DOCK_MINW = 320;
const DOCK_MINH = 280;

const pinnedDocks = new Set();
const liveDocks = new Set();
let _dockRAF = 0;
let _dockIdle = 0;
let _dockWakesInstalled = false;
let _dockLastMode = null;
const DOCK_IDLE_STOP = 6;
window.addEventListener("resize", () => wakeDocks());

function clockToSeconds(minutes, seconds, frac) {
    let sub = 0;
    const f = String(frac || "0");
    if (f.length === 1) sub = Number(f) / 10;
    else if (f.length === 2) sub = Number(f) / 100;
    else sub = Number(f.slice(0, 3).padEnd(3, "0")) / 1000;
    return Number(minutes) * 60 + Number(seconds) + sub;
}

function formatClock(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const m = Math.floor(total / 60);
    const rem = total - m * 60;
    return `${String(m).padStart(2, "0")}:${rem.toFixed(3).padStart(6, "0")}`;
}

function parseRange(text) {
    const first = String(text || "").trim().split("\n")[0].trim();
    if (!first) return null;
    let m = RANGE_CLOCK.exec(first);
    if (m) {
        const start = clockToSeconds(m[1], m[2], m[3]);
        const end = clockToSeconds(m[4], m[5], m[6]);
        if (end > start) return { start, end };
        return null;
    }
    m = RANGE_SECS.exec(first);
    if (m) {
        const start = Number(m[1]);
        const end = Number(m[2]);
        if (end > start) return { start, end };
    }
    return null;
}

function parseLyrics(text) {
    const lines = [];
    for (const raw of String(text || "").replace(/\r\n/g, "\n").split("\n")) {
        const stripped = raw.trim();
        if (!stripped) continue;
        let m = LRC_CLOCK.exec(stripped);
        if (m) {
            const start = clockToSeconds(m[1], m[2], m[3]);
            const end = m[4] != null ? clockToSeconds(m[4], m[5], m[6]) : start;
            const body = (m[7] || "").trim();
            lines.push({ start, end: end > start ? end : start, text: body });
            continue;
        }
        m = LRC_SECS.exec(stripped);
        if (m) {
            const start = Number(m[1]);
            const end = m[2] != null ? Number(m[2]) : start;
            const body = (m[3] || "").trim();
            lines.push({ start, end: end > start ? end : start, text: body });
        }
    }
    return lines;
}

function formatLyrics(lines) {
    return lines.map((ln) => `[${formatClock(ln.start)}-${formatClock(ln.end)}] ${ln.text}`).join("\n") + (lines.length ? "\n" : "");
}

function findWidget(node, name) {
    return node?.widgets?.find((w) => w?.name === name);
}

function viewUrl(filename) {
    return api.apiURL("/view?" + new URLSearchParams({ filename, type: "input" }));
}

async function uploadAudio(file) {
    const body = new FormData();
    body.append("image", file);
    const resp = await fetch(api.apiURL("/upload/image"), { method: "POST", body });
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    return resp.json();
}

function chainCallback(obj, name, fn) {
    const orig = obj[name];
    obj[name] = function () {
        const result = orig?.apply(this, arguments);
        fn.apply(this, arguments);
        return result;
    };
}

function stopProp(el) {
    el.addEventListener("mousedown", (e) => e.stopPropagation());
    el.addEventListener("pointerdown", (e) => e.stopPropagation());
    el.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
}

function dragPointer(e, target, onMove, onEnd) {
    try { target.setPointerCapture(e.pointerId); } catch (_) {}
    const move = (me) => { if (me.pointerId === e.pointerId) onMove(me); };
    const end = (ue) => {
        if (ue.pointerId !== e.pointerId) return;
        target.removeEventListener("pointermove", move);
        target.removeEventListener("pointerup", end);
        target.removeEventListener("pointercancel", end);
        onEnd?.(ue);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", end);
    target.addEventListener("pointercancel", end);
}

function injectStyle() {
    if (document.getElementById("h3-song-dock-style")) return;
    const s = document.createElement("style");
    s.id = "h3-song-dock-style";
    s.textContent = `
      .h3song-wrap { display:flex; flex-direction:column; overflow:hidden; position:relative; pointer-events:auto; gap:6px; }
      .h3song-cv { flex:1 1 auto; min-height:80px; display:flex; overflow:hidden; }
      .h3song-canvas { cursor:ew-resize; display:block; width:100%; height:100%; background:#1a1a1a; border-radius:4px; outline:none; touch-action:none; }
      .h3song-bar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; font:12px sans-serif; color:#ccc; user-select:none; flex:0 0 auto; }
      .h3song-range { width:13em; background:#111; color:#ddd; border:1px solid #444; border-radius:4px; font:11px monospace; padding:2px 6px; }
      .h3song-btn { background:#333; border:1px solid #555; border-radius:4px; color:#bbb; font:11px sans-serif; cursor:pointer; padding:2px 8px; line-height:16px; white-space:nowrap; flex-shrink:0; }
      .h3song-btn:hover { border-color:#46b4e6; color:#fff; }
      .h3song-list { width:100%; flex:0 0 auto; min-height:72px; overflow:auto; background:#111; color:#ddd; border:1px solid #333; box-sizing:border-box; font:12px sans-serif; }
      .h3song-row { display:flex; align-items:center; gap:6px; padding:2px 6px; cursor:pointer; user-select:none; }
      .h3song-row:hover { background:#1c1c1c; }
      .h3song-row.selected { background:#2a3a42; color:#fff; }
      .h3song-stamp { flex:0 0 auto; color:#888; font:11px monospace; white-space:nowrap; }
      .h3song-lyric { flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .h3song-del { flex:0 0 auto; background:none; border:none; color:#777; cursor:pointer; font:13px sans-serif; line-height:1; padding:2px 5px; border-radius:3px; opacity:0; }
      .h3song-row:hover .h3song-del, .h3song-row.selected .h3song-del { opacity:1; }
      .h3song-del:hover { color:#fff; background:#a33; }
      .h3song-edit { flex:1 1 auto; min-width:0; background:#111; color:#fff; border:1px solid #46b4e6; border-radius:3px; font:12px sans-serif; padding:1px 4px; outline:none; }
      .h3song-split { flex:0 0 auto; height:8px; cursor:ns-resize; position:relative; }
      .h3song-split::before { content:""; position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:34px; height:3px; background:#555; border-radius:2px; }
      .h3song-split:hover::before { background:#46b4e6; }
      .h3song-dock { position:fixed; pointer-events:auto; display:flex; flex-direction:column; background:var(--h3-dock-bg,#1a1a1a); border:1px solid var(--h3-dock-border,#555); border-radius:8px; box-shadow:0 8px 30px rgba(0,0,0,0.55); min-width:${DOCK_MINW}px; min-height:${DOCK_MINH}px; overflow:hidden; box-sizing:border-box; }
      .h3song-rsz { position:absolute; z-index:20; touch-action:none; }
      .h3song-rsz.n { top:0; left:11px; right:11px; height:6px; cursor:ns-resize; }
      .h3song-rsz.s { bottom:0; left:11px; right:11px; height:6px; cursor:ns-resize; }
      .h3song-rsz.e { right:0; top:11px; bottom:11px; width:6px; cursor:ew-resize; }
      .h3song-rsz.w { left:0; top:11px; bottom:11px; width:6px; cursor:ew-resize; }
      .h3song-rsz.ne { top:0; right:0; width:12px; height:12px; cursor:nesw-resize; }
      .h3song-rsz.nw { top:0; left:0; width:12px; height:12px; cursor:nwse-resize; }
      .h3song-rsz.se { bottom:0; right:0; width:12px; height:12px; cursor:nwse-resize; }
      .h3song-rsz.sw { bottom:0; left:0; width:12px; height:12px; cursor:nwse-resize; }
      .h3song-dock.minimized { min-height:0 !important; height:auto !important; }
      .h3song-dock.minimized .h3song-dock-body { display:none; }
      .h3song-dock.minimized .h3song-rsz { display:none; }
      .h3song-dock.snap-ready { box-shadow:0 -3px 0 0 #46b4e6, 0 8px 30px rgba(0,0,0,0.55); }
      .h3song-dock-head { display:flex; align-items:center; gap:6px; padding:4px 8px; background:var(--h3-dock-head,#262626); cursor:move; font:12px sans-serif; color:#ccc; user-select:none; border-bottom:1px solid rgba(0,0,0,0.25); flex:0 0 auto; }
      .h3song-dock-body { flex:1 1 auto; min-height:0; padding:8px; box-sizing:border-box; overflow:hidden; }
      .h3song-dock-body .h3song-wrap { height:100%; }
    `;
    document.head.appendChild(s);
}

function applyDockTransform(n, rect) {
    const c = app.canvas;
    const fl = n._h3DockEl;
    if (!c || !fl || !n.graph || n.graph !== c.graph) {
        if (fl) fl.style.display = "none";
        return;
    }
    fl.style.display = "";
    const gr = n.properties.h3DockGraph || (n.properties.h3DockGraph = { x: 0, y: (n.size?.[1] || 0) + 2, w: 480, h: 380 });
    let hostEl = null;
    if (window.LiteGraph?.vueNodesMode && n.id != null) {
        if (n._h3DockHostId !== n.id || !n._h3DockHostEl?.isConnected) {
            n._h3DockHostEl = document.querySelector(`[data-node-id="${n.id}"]`);
            n._h3DockHostId = n.id;
            n._h3DockSig = "";
        }
        hostEl = n._h3DockHostEl;
    }
    if (hostEl) {
        const title = window.LiteGraph?.NODE_TITLE_HEIGHT ?? 30;
        const sig = `v|${n.id}|${gr.x}|${gr.y}`;
        if (fl.parentElement !== hostEl) {
            hostEl.appendChild(fl);
            fl.style.position = "absolute";
            fl.style.transform = "";
            fl.style.transformOrigin = "";
            fl.style.zIndex = "";
            n._h3DockSig = "";
        }
        if (n._h3DockSig !== sig) {
            fl.style.left = `${gr.x}px`;
            fl.style.top = `${title + gr.y}px`;
            n._h3DockSig = sig;
        }
        return;
    }
    if (fl.parentElement !== document.body) {
        document.body.appendChild(fl);
        fl.style.left = "";
        fl.style.top = "";
        n._h3DockSig = "";
    }
    if (!n.pos) return;
    const ds = c.ds;
    const scale = ds.scale;
    rect = rect || c.canvas.getBoundingClientRect();
    const tf = `translate(${rect.left + (n.pos[0] + gr.x + ds.offset[0]) * scale}px,${rect.top + (n.pos[1] + gr.y + ds.offset[1]) * scale}px) scale(${scale})`;
    if (n._h3DockSig !== tf) {
        fl.style.position = "fixed";
        fl.style.transformOrigin = "top left";
        fl.style.transform = tf;
        n._h3DockSig = tf;
    }
    const order = c.graph?.nodes?.indexOf(n);
    if (order != null && order >= 0) fl.style.zIndex = String(order);
}

function tickDocks() {
    const c = app.canvas;
    if (c && pinnedDocks.size) {
        const vue = !!window.LiteGraph?.vueNodesMode;
        if (vue !== _dockLastMode) {
            _dockLastMode = vue;
            for (const n of pinnedDocks) {
                n._h3DockSig = "";
                n._h3DockHostEl = null;
                n._h3DockHostId = null;
            }
        }
        const rect = vue ? null : c.canvas.getBoundingClientRect();
        for (const n of pinnedDocks) applyDockTransform(n, rect);
    }
    if (pinnedDocks.size && ++_dockIdle < DOCK_IDLE_STOP) _dockRAF = requestAnimationFrame(tickDocks);
    else _dockRAF = 0;
}

function wakeDocks() {
    _dockIdle = 0;
    if (!_dockRAF && pinnedDocks.size) _dockRAF = requestAnimationFrame(tickDocks);
}

function installDockWakes() {
    if (_dockWakesInstalled) return;
    const c = app.canvas;
    if (!c) return;
    _dockWakesInstalled = true;
    chainCallback(c, "onDrawForeground", () => {
        for (const n of [...liveDocks]) {
            if (n.graph?.getNodeById?.(n.id) === n) continue;
            try { n._h3DockRO?.disconnect(); } catch (_) {}
            n._h3DockEl?.remove();
            pinnedDocks.delete(n);
            liveDocks.delete(n);
        }
        wakeDocks();
    });
}

function startDockLoop() {
    if (!app.canvas) {
        requestAnimationFrame(startDockLoop);
        return;
    }
    installDockWakes();
    wakeDocks();
}

function installTimeline(node, attempt = 0) {
    if (node._h3SongTimeline) return;
    const audioWidget = findWidget(node, "audio");
    const lyricsWidget = findWidget(node, "lyrics");
    const loopWidget = findWidget(node, "loop");
    if (!audioWidget || !lyricsWidget || !loopWidget) {
        if (attempt < 10) setTimeout(() => installTimeline(node, attempt + 1), 0);
        return;
    }
    node._h3SongTimeline = true;
    node.properties = node.properties || {};
    if (node.properties.h3WriteLoopToLyric == null) node.properties.h3WriteLoopToLyric = false;
    injectStyle();
    node.resizable = true;

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "audio/mpeg,audio/wav,audio/x-wav,audio/ogg,audio/flac,audio/mp4,.mp3,.wav,.flac,.ogg,.m4a";
    fileInput.style.display = "none";
    fileInput.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        if (!file) return;
        try {
            const info = await uploadAudio(file);
            const name = info.name || file.name;
            if (audioWidget.options?.values && !audioWidget.options.values.includes(name)) {
                audioWidget.options.values.push(name);
            }
            audioWidget.value = name;
            audioWidget.callback?.(name);
        } catch (err) {
            alert(err);
        }
    });
    document.body.append(fileInput);
    const uploadBtn = node.addWidget("button", "choose audio to upload", "audio", () => {
        app.canvas.node_widget = null;
        fileInput.click();
    });
    uploadBtn.options = uploadBtn.options || {};
    uploadBtn.options.serialize = false;

    const alignBtn = node.addWidget("button", "Time lyrics", "align", async () => {
        app.canvas.node_widget = null;
        try {
            const resp = await api.fetchApi("/h3_studio_song/align", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filename: audioWidget.value,
                    lyrics: lyricsWidget.value || "",
                }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || `${resp.status} ${resp.statusText}`);
            lyricsWidget.value = data.lyrics;
            lyricsWidget.callback?.(data.lyrics);
            loadLyrics();
        } catch (err) {
            alert(err);
        }
    });
    alignBtn.options = alignBtn.options || {};
    alignBtn.options.serialize = false;

    const wrap = document.createElement("div");
    wrap.className = "h3song-wrap";

    const audioEl = document.createElement("audio");
    audioEl.controls = true;
    audioEl.preload = "metadata";
    audioEl.style.cssText = "width:100%;flex:0 0 auto;";
    stopProp(audioEl);

    const cvBox = document.createElement("div");
    cvBox.className = "h3song-cv";
    const canvas = document.createElement("canvas");
    canvas.className = "h3song-canvas";
    cvBox.append(canvas);

    const controls = document.createElement("div");
    controls.className = "h3song-bar";
    const playBtn = document.createElement("button");
    playBtn.className = "h3song-btn";
    playBtn.textContent = "Play A–B";
    const zoomOutBtn = document.createElement("button");
    zoomOutBtn.className = "h3song-btn";
    zoomOutBtn.textContent = "−";
    zoomOutBtn.title = "Zoom out";
    const zoomInBtn = document.createElement("button");
    zoomInBtn.className = "h3song-btn";
    zoomInBtn.textContent = "+";
    zoomInBtn.title = "Zoom in";
    const fitBtn = document.createElement("button");
    fitBtn.className = "h3song-btn";
    fitBtn.textContent = "Fit";
    const rangeInput = document.createElement("input");
    rangeInput.className = "h3song-range";
    rangeInput.type = "text";
    rangeInput.placeholder = "116.167-123.458";
    rangeInput.title = "Paste A–B range: 116.167-123.458 or 02:05.375-02:09.040";
    const addBtn = document.createElement("button");
    addBtn.className = "h3song-btn";
    addBtn.textContent = "+";
    addBtn.title = "Add current A–B to lyrics at this time";
    const writeLabel = document.createElement("label");
    writeLabel.style.cssText = "display:flex;gap:4px;align-items:center;cursor:pointer;";
    const writeBox = document.createElement("input");
    writeBox.type = "checkbox";
    writeBox.checked = !!node.properties.h3WriteLoopToLyric;
    writeBox.title = "When on, dragging A/B rewrites the selected lyric stamps";
    writeLabel.append(writeBox, document.createTextNode("Write A–B into selected lyric"));
    controls.append(playBtn, zoomOutBtn, zoomInBtn, fitBtn, rangeInput, addBtn, writeLabel);
    for (const el of [playBtn, zoomOutBtn, zoomInBtn, fitBtn, rangeInput, addBtn, writeBox]) stopProp(el);

    const splitter = document.createElement("div");
    splitter.className = "h3song-split";
    splitter.title = "Drag to resize the lyric list";

    const list = document.createElement("div");
    list.className = "h3song-list";
    list.title = "Click to select · double-click to edit · Delete or × to remove";
    list.tabIndex = 0;
    stopProp(list);

    wrap.append(audioEl, cvBox, controls, splitter, list);

    // The timeline is NOT a node widget — it lives in the floating dock, so the node
    // stays an ordinary widgets-only node that ComfyUI sizes with zero custom height handling.

    const state = {
        duration: 0,
        peaks: null,
        a: 0,
        b: 0,
        selected: -1,
        editIdx: -1,
        editInput: null,
        drag: null,
        lines: [],
        viewStart: 0,
        viewEnd: 0,
        listH: node.properties.h3ListH || 120,
    };
    list.style.flex = `0 0 ${state.listH}px`;
    list.style.height = `${state.listH}px`;

    const fl = document.createElement("div");
    fl.className = "h3song-dock";
    fl.dataset.captureWheel = "true";
    stopProp(fl);
    const head = document.createElement("div");
    head.className = "h3song-dock-head";
    const title = document.createElement("span");
    title.textContent = "H3 song timeline";
    title.style.flex = "1";
    const minBtn = document.createElement("button");
    minBtn.className = "h3song-btn";
    stopProp(minBtn);
    const applyMin = (on) => {
        node.properties.h3DockMin = !!on;
        fl.classList.toggle("minimized", !!on);
        minBtn.textContent = on ? "▢" : "—";
        minBtn.title = on ? "Restore timeline" : "Minimize timeline";
        if (!on) requestAnimationFrame(fitCanvas);
    };
    minBtn.addEventListener("click", () => applyMin(!node.properties.h3DockMin));
    head.append(title, minBtn);
    const body = document.createElement("div");
    body.className = "h3song-dock-body";
    body.append(wrap);
    fl.append(head, body);
    for (const dir of ["n", "s", "e", "w", "ne", "nw", "se", "sw"]) {
        const handle = document.createElement("div");
        handle.className = `h3song-rsz ${dir}`;
        handle.addEventListener("pointerdown", (e) => startDockResize(e, dir));
        fl.append(handle);
    }
    document.body.append(fl);
    node._h3DockEl = fl;
    liveDocks.add(node);

    function dockGraph() {
        return node.properties.h3DockGraph || (node.properties.h3DockGraph = {
            x: 0, y: (node.size?.[1] || 0) + 2, w: Math.max(DOCK_MINW, Math.round(node.size?.[0] || 480)), h: 380,
        });
    }

    function saveDockGeom() {
        if (node.properties.h3DockMin) return;
        if (fl.offsetWidth < DOCK_MINW || fl.offsetHeight < DOCK_MINH) return;
        const g = dockGraph();
        g.w = Math.max(DOCK_MINW, Math.round(fl.offsetWidth || g.w));
        g.h = Math.max(DOCK_MINH, Math.round(fl.offsetHeight || g.h));
        node.properties.h3ListH = state.listH;
    }

    function placeDock(fresh) {
        const honor = !fresh && !!node.properties.h3DockGraph && node._h3DockGeomRestored;
        const g = dockGraph();
        if (!honor) {
            g.x = 0;
            g.y = node.size[1] + 2;
            g.w = Math.max(DOCK_MINW, Math.round(node.size[0]));
            if (!(g.h >= DOCK_MINH)) g.h = 380;
        }
        fl.style.width = `${g.w}px`;
        fl.style.height = `${g.h}px`;
        node._h3DockSig = "";
        applyDockTransform(node);
        fitCanvas();
    }

    function startDockResize(e, dir) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const scale = (window.LiteGraph?.vueNodesMode ? 1 : (app.canvas?.ds?.scale || 1));
        const sx = e.clientX;
        const sy = e.clientY;
        const g = dockGraph();
        const w0 = fl.offsetWidth;
        const h0 = fl.offsetHeight;
        const gx0 = g.x;
        const gy0 = g.y;
        dragPointer(e, e.currentTarget, (me) => {
            const dx = (me.clientX - sx) / scale;
            const dy = (me.clientY - sy) / scale;
            let w = w0;
            let h = h0;
            let gx = gx0;
            let gy = gy0;
            if (dir.includes("e")) w = w0 + dx;
            if (dir.includes("s")) h = h0 + dy;
            if (dir.includes("w")) { w = w0 - dx; gx = gx0 + dx; }
            if (dir.includes("n")) { h = h0 - dy; gy = gy0 + dy; }
            if (w < DOCK_MINW) { if (dir.includes("w")) gx -= (DOCK_MINW - w); w = DOCK_MINW; }
            if (h < DOCK_MINH) { if (dir.includes("n")) gy -= (DOCK_MINH - h); h = DOCK_MINH; }
            g.x = gx;
            g.y = gy;
            g.w = Math.round(w);
            g.h = Math.round(h);
            fl.style.width = `${g.w}px`;
            fl.style.height = `${g.h}px`;
            node._h3DockSig = "";
            applyDockTransform(node);
            fitCanvas();
        }, () => { saveDockGeom(); });
    }

    head.addEventListener("pointerdown", (e) => {
        if (e.target === minBtn || e.button !== 0) return;
        if (node.flags?.pinned) return;
        e.preventDefault();
        const sx0 = e.clientX;
        const sy0 = e.clientY;
        const g = dockGraph();
        const gx0 = g.x;
        const gy0 = g.y;
        const scale = window.LiteGraph?.vueNodesMode ? 1 : (app.canvas?.ds?.scale || 1);
        let snapReady = false;
        dragPointer(e, head, (me) => {
            const gx = gx0 + (me.clientX - sx0) / scale;
            const gy = gy0 + (me.clientY - sy0) / scale;
            const snap = 26 / scale;
            const underY = node.size[1] + 2;
            snapReady = Math.abs(gx) < snap && Math.abs(gy - underY) < snap;
            fl.classList.toggle("snap-ready", snapReady);
            g.x = gx;
            g.y = gy;
            node._h3DockSig = "";
            applyDockTransform(node);
        }, () => {
            if (snapReady) {
                g.x = 0;
                g.y = node.size[1] + 2;
                g.w = Math.max(DOCK_MINW, Math.round(node.size[0]));
                fl.style.width = `${g.w}px`;
                node._h3DockSig = "";
                applyDockTransform(node);
            }
            fl.classList.remove("snap-ready");
            saveDockGeom();
        });
    });

    splitter.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const scale = window.LiteGraph?.vueNodesMode ? 1 : (app.canvas?.ds?.scale || 1);
        const sy = e.clientY;
        const h0 = list.offsetHeight;
        dragPointer(e, splitter, (me) => {
            const h = Math.max(72, Math.min(h0 + (me.clientY - sy) / scale, wrap.clientHeight - 140));
            state.listH = Math.round(h);
            list.style.flex = `0 0 ${state.listH}px`;
            list.style.height = `${state.listH}px`;
            fitCanvas();
        }, () => { saveDockGeom(); });
    });

    function fitCanvas() {
        if (wrap.offsetParent === null) return;
        const availW = cvBox.clientWidth;
        const availH = cvBox.clientHeight;
        if (availW < 4 || availH < 4) return;
        canvas.style.width = `${Math.round(availW)}px`;
        canvas.style.height = `${Math.round(availH)}px`;
        draw();
    }

    try {
        node._h3DockRO = new ResizeObserver(() => { fitCanvas(); saveDockGeom(); });
        node._h3DockRO.observe(fl);
    } catch (_) {}
    try {
        node._h3VisObserver = new IntersectionObserver((entries) => {
            if (entries.some((en) => en.isIntersecting)) fitCanvas();
        });
        node._h3VisObserver.observe(wrap);
    } catch (_) {}

    const g0 = dockGraph();
    fl.style.width = `${g0.w}px`;
    fl.style.height = `${g0.h}px`;
    pinnedDocks.add(node);
    startDockLoop();
    applyDockTransform(node);
    applyMin(!!node.properties.h3DockMin);
    requestAnimationFrame(fitCanvas);

    function viewWindow() {
        const dur = state.duration || 1;
        const start = Math.max(0, state.viewStart || 0);
        let end = state.viewEnd > start ? state.viewEnd : dur;
        end = Math.min(dur, end);
        if (end - start < MIN_VIEW) end = Math.min(dur, start + MIN_VIEW);
        return { start, end, span: Math.max(MIN_VIEW, end - start) };
    }

    function xToTime(x, width) {
        if (!state.duration || width <= 0) return 0;
        const v = viewWindow();
        return Math.max(0, Math.min(state.duration, v.start + (x / width) * v.span));
    }

    function timeToX(t, width) {
        const v = viewWindow();
        return ((t - v.start) / v.span) * width;
    }

    function setView(start, end) {
        const dur = state.duration || 0;
        if (!dur) {
            state.viewStart = 0;
            state.viewEnd = 0;
            return;
        }
        let span = Math.max(MIN_VIEW, Math.min(dur, end - start));
        let s = Math.max(0, Math.min(start, dur - span));
        state.viewStart = s;
        state.viewEnd = s + span;
    }

    function zoomAt(t, factor) {
        const v = viewWindow();
        const dur = state.duration || 0;
        if (!dur) return;
        const span = Math.max(MIN_VIEW, Math.min(dur, v.span * factor));
        const ratio = (t - v.start) / v.span;
        setView(t - span * ratio, t - span * ratio + span);
        draw();
    }

    function fitView() {
        state.viewStart = 0;
        state.viewEnd = state.duration || 0;
        draw();
    }

    function canvasLocalX(e) {
        const rect = canvas.getBoundingClientRect();
        const cssW = canvas.clientWidth || 1;
        if (rect.width <= 0) return 0;
        return (e.clientX - rect.left) * (cssW / rect.width);
    }

    let loopFromUi = false;

    function rangeText() {
        if (!(state.b > state.a)) return "";
        return `${formatClock(state.a)}-${formatClock(state.b)}`;
    }

    function zoomToLoop() {
        if (!(state.b > state.a) || !state.duration) return;
        const pad = Math.max(0.25, (state.b - state.a) * 0.25);
        setView(state.a - pad, state.b + pad);
    }

    function applyParsedLoop(parsed, zoom) {
        if (!parsed) return false;
        let a = parsed.start;
        let b = parsed.end;
        if (!(b > a)) return false;
        if (state.duration) {
            a = Math.max(0, Math.min(a, state.duration));
            b = Math.max(a + 0.05, Math.min(b, state.duration));
        }
        state.a = a;
        state.b = b;
        setLoopWidgets();
        if (zoom) zoomToLoop();
        draw();
        return true;
    }

    function setLoopWidgets() {
        const text = rangeText();
        loopFromUi = true;
        loopWidget.value = text;
        if (document.activeElement !== rangeInput) rangeInput.value = text;
        loopWidget.callback?.(loopWidget.value);
        loopFromUi = false;
    }

    function writeBackEnabled() {
        return !!writeBox.checked;
    }

    function applyLoopToSelected() {
        if (!writeBackEnabled()) return;
        if (state.selected < 0 || !state.lines[state.selected]) return;
        state.lines[state.selected].start = state.a;
        state.lines[state.selected].end = state.b;
        lyricsWidget.value = formatLyrics(state.lines);
        lyricsWidget.callback?.(lyricsWidget.value);
        fillList();
    }

    function insertAbLyric() {
        if (!(state.b > state.a)) return;
        const hit = state.lines.findIndex((ln) => (
            Math.abs(ln.start - state.a) < 0.001 && Math.abs(ln.end - state.b) < 0.001
        ));
        if (hit >= 0) {
            selectLine(hit);
            return;
        }
        state.lines.push({ start: state.a, end: state.b, text: "" });
        state.lines.sort((x, y) => (x.start - y.start) || (x.end - y.end));
        state.selected = state.lines.findIndex((ln) => (
            Math.abs(ln.start - state.a) < 0.001 && Math.abs(ln.end - state.b) < 0.001
        ));
        lyricsWidget.value = formatLyrics(state.lines);
        lyricsWidget.callback?.(lyricsWidget.value);
        fillList();
        draw();
        startListEdit(state.selected);
    }

    function deleteLine(i) {
        if (i == null || i < 0 || i >= state.lines.length) return;
        if (state.editIdx === i) {
            state.editInput = null;
            state.editIdx = -1;
        }
        state.lines.splice(i, 1);
        if (!state.lines.length) state.selected = -1;
        else if (state.selected >= state.lines.length) state.selected = state.lines.length - 1;
        else if (state.selected > i) state.selected -= 1;
        lyricsWidget.value = formatLyrics(state.lines);
        lyricsWidget.callback?.(lyricsWidget.value);
        fillList();
        draw();
    }

    function selectLine(i, syncLoop = true) {
        state.selected = i;
        highlightList();
        const ln = state.lines[i];
        if (syncLoop && ln) {
            state.a = ln.start;
            state.b = Math.max(ln.start + 0.05, ln.end);
            setLoopWidgets();
        }
        draw();
    }

    function highlightList() {
        for (const row of list.querySelectorAll(".h3song-row")) {
            const i = Number(row.dataset.i);
            row.classList.toggle("selected", i === state.selected);
        }
        const active = list.querySelector(".h3song-row.selected");
        if (active && typeof active.scrollIntoView === "function") {
            active.scrollIntoView({ block: "nearest" });
        }
    }

    function commitListEdit(save) {
        const input = state.editInput;
        const idx = state.editIdx;
        if (!input) return;
        state.editInput = null;
        state.editIdx = -1;
        const ln = state.lines[idx];
        if (save !== false && ln) {
            ln.text = String(input.value || "").replace(/\r?\n/g, " ").trim();
            lyricsWidget.value = formatLyrics(state.lines);
            lyricsWidget.callback?.(lyricsWidget.value);
        }
        fillList();
    }

    function startListEdit(i) {
        if (i == null || i < 0 || !state.lines[i]) return;
        if (state.editIdx === i) {
            state.editInput?.focus();
            return;
        }
        commitListEdit(true);
        state.selected = i;
        fillList();
        const row = list.querySelector(`.h3song-row[data-i="${i}"]`);
        const body = row?.querySelector(".h3song-lyric");
        if (!row || !body) return;
        const input = document.createElement("input");
        input.className = "h3song-edit";
        input.type = "text";
        input.value = state.lines[i].text || "";
        input.title = "Enter to save · Esc to cancel";
        body.replaceWith(input);
        state.editInput = input;
        state.editIdx = i;
        stopProp(input);
        input.addEventListener("keydown", (e) => {
            e.stopPropagation();
            if (e.key === "Enter") {
                e.preventDefault();
                commitListEdit(true);
            } else if (e.key === "Escape") {
                e.preventDefault();
                commitListEdit(false);
            }
        });
        input.addEventListener("blur", () => commitListEdit(true));
        requestAnimationFrame(() => {
            input.focus();
            input.select();
        });
    }

    function fillList() {
        if (state.editInput) {
            const ln = state.lines[state.editIdx];
            if (ln) ln.text = String(state.editInput.value || "").replace(/\r?\n/g, " ").trim();
            state.editInput = null;
            state.editIdx = -1;
        }
        const keep = state.selected;
        list.innerHTML = "";
        state.lines.forEach((ln, i) => {
            const row = document.createElement("div");
            row.className = "h3song-row";
            row.dataset.i = String(i);
            if (i === keep) row.classList.add("selected");
            const stamp = document.createElement("span");
            stamp.className = "h3song-stamp";
            stamp.textContent = `[${formatClock(ln.start)}-${formatClock(ln.end)}]`;
            const body = document.createElement("span");
            body.className = "h3song-lyric";
            body.textContent = ln.text || "";
            const del = document.createElement("button");
            del.className = "h3song-del";
            del.type = "button";
            del.textContent = "×";
            del.title = "Delete this line";
            del.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                deleteLine(i);
            });
            row.append(stamp, body, del);
            list.append(row);
        });
        highlightList();
    }

    function loadLyrics() {
        state.lines = parseLyrics(lyricsWidget.value);
        fillList();
        draw();
    }

    function loadLoop(zoom) {
        if (loopFromUi) return;
        const parsed = parseRange(loopWidget.value) || parseRange(rangeInput.value);
        if (parsed) {
            applyParsedLoop(parsed, !!zoom);
            return;
        }
        if (state.duration && !(state.b > state.a)) {
            state.a = 0;
            state.b = state.duration;
        }
        if (document.activeElement !== rangeInput) rangeInput.value = rangeText();
        draw();
    }

    function draw() {
        const cssW = Math.max(1, canvas.clientWidth || cvBox.clientWidth || 1);
        const cssH = Math.max(1, canvas.clientHeight || cvBox.clientHeight || 64);
        const dpr = window.devicePixelRatio || 1;
        const w = Math.max(1, Math.floor(cssW * dpr));
        const h = Math.max(1, Math.floor(cssH * dpr));
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#1a1a1a";
        ctx.fillRect(0, 0, w, h);
        const v = viewWindow();
        if (state.peaks && state.peaks.length && state.duration) {
            ctx.fillStyle = "#4a7";
            const mid = h / 2;
            const n = state.peaks.length;
            const i0 = Math.max(0, Math.floor((v.start / state.duration) * n));
            const i1 = Math.min(n, Math.ceil((v.end / state.duration) * n) + 1);
            const vis = Math.max(1, i1 - i0);
            for (let i = i0; i < i1; i++) {
                const t0 = (i / n) * state.duration;
                const x = timeToX(t0, w);
                const mag = state.peaks[i] * (h * 0.42);
                const barW = Math.max(1, w / vis);
                ctx.fillRect(x, mid - mag, barW, mag * 2);
            }
        }
        if (state.duration) {
            state.lines.forEach((ln, i) => {
                if (ln.end < v.start || ln.start > v.end) return;
                const x0 = timeToX(ln.start, w);
                const x1 = timeToX(ln.end, w);
                ctx.fillStyle = i === state.selected ? "rgba(255,200,80,0.28)" : "rgba(80,140,255,0.18)";
                ctx.fillRect(x0, 0, Math.max(2, x1 - x0), h);
            });
            const ax = timeToX(state.a, w);
            const bx = timeToX(state.b, w);
            ctx.fillStyle = "rgba(255,255,255,0.08)";
            ctx.fillRect(ax, 0, Math.max(1, bx - ax), h);
            ctx.fillStyle = "#f80";
            ctx.fillRect(ax - 1, 0, 3, h);
            ctx.fillStyle = "#08f";
            ctx.fillRect(bx - 1, 0, 3, h);
            if (!audioEl.paused) {
                const px = timeToX(audioEl.currentTime, w);
                ctx.fillStyle = "#fff";
                ctx.fillRect(px, 0, 1, h);
            }
        }
    }

    async function loadPeaks(filename) {
        if (!filename) return;
        try {
            const buf = await fetch(viewUrl(filename)).then((r) => r.arrayBuffer());
            const ctx = new AudioContext();
            const decoded = await ctx.decodeAudioData(buf.slice(0));
            ctx.close();
            const ch = decoded.getChannelData(0);
            const bars = Math.min(8000, Math.max(800, Math.floor(ch.length / 256)));
            const step = Math.max(1, Math.floor(ch.length / bars));
            const peaks = new Array(bars);
            for (let i = 0; i < bars; i++) {
                let peak = 0;
                const start = i * step;
                const end = Math.min(ch.length, start + step);
                for (let j = start; j < end; j++) peak = Math.max(peak, Math.abs(ch[j]));
                peaks[i] = peak;
            }
            state.peaks = peaks;
            state.duration = decoded.duration || audioEl.duration || 0;
            if (!(state.b > state.a)) {
                state.a = 0;
                state.b = state.duration;
            }
            if (!(state.viewEnd > state.viewStart)) fitView();
            loadLoop();
            draw();
        } catch (_) {
            state.peaks = null;
            draw();
        }
    }

    function setAudioFile(filename) {
        if (!filename) return;
        audioEl.src = viewUrl(filename);
        loadPeaks(filename);
    }

    audioEl.addEventListener("loadedmetadata", () => {
        if (audioEl.duration && isFinite(audioEl.duration)) {
            state.duration = audioEl.duration;
            if (!(state.viewEnd > state.viewStart)) fitView();
            loadLoop();
            draw();
        }
    });
    audioEl.addEventListener("timeupdate", () => {
        if (!audioEl.paused && state.b > state.a) {
            if (audioEl.currentTime >= state.b || audioEl.currentTime < state.a - 0.05) {
                audioEl.currentTime = state.a;
            }
        }
        draw();
    });

    playBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!state.duration) return;
        audioEl.currentTime = state.a;
        audioEl.play();
    });
    zoomInBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const v = viewWindow();
        zoomAt((state.a + state.b) / 2 || (v.start + v.end) / 2, 0.7);
    });
    zoomOutBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const v = viewWindow();
        zoomAt((v.start + v.end) / 2, 1.4);
    });
    fitBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        fitView();
    });
    writeBox.addEventListener("change", () => {
        node.properties.h3WriteLoopToLyric = !!writeBox.checked;
    });
    function commitRangeInput() {
        const parsed = parseRange(rangeInput.value);
        if (parsed) applyParsedLoop(parsed, true);
        else rangeInput.value = rangeText();
    }
    rangeInput.addEventListener("change", commitRangeInput);
    rangeInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            commitRangeInput();
        }
    });
    addBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        insertAbLyric();
    });

    list.addEventListener("click", (e) => {
        if (e.target.closest(".h3song-edit") || e.target.closest(".h3song-del")) return;
        const row = e.target.closest(".h3song-row");
        if (!row) return;
        selectLine(Number(row.dataset.i));
        list.focus();
    });
    list.addEventListener("dblclick", (e) => {
        if (e.target.closest(".h3song-del")) return;
        const row = e.target.closest(".h3song-row");
        if (!row) return;
        e.preventDefault();
        startListEdit(Number(row.dataset.i));
    });
    list.addEventListener("keydown", (e) => {
        if (state.editInput) return;
        if (e.key !== "Delete" && e.key !== "Backspace") return;
        if (state.selected < 0) return;
        e.preventDefault();
        e.stopPropagation();
        deleteLine(state.selected);
    });

    canvas.addEventListener("wheel", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!state.duration) return;
        const cssW = canvas.clientWidth || 1;
        zoomAt(xToTime(canvasLocalX(e), cssW), e.deltaY < 0 ? 0.8 : 1.25);
    }, { passive: false });

    canvas.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const cssW = canvas.clientWidth || 1;
        const t = xToTime(canvasLocalX(e), cssW);
        const aX = timeToX(state.a, cssW);
        const bX = timeToX(state.b, cssW);
        const px = canvasLocalX(e);
        const pan = e.shiftKey || e.button === 1;
        if (pan) {
            state.drag = "pan";
            state.dragAt = t;
        } else if (Math.abs(px - aX) <= HANDLE_PX) {
            state.drag = "a";
        } else if (Math.abs(px - bX) <= HANDLE_PX) {
            state.drag = "b";
        } else {
            const hit = state.lines.findIndex((ln) => t >= ln.start && t <= ln.end);
            if (hit >= 0) {
                state.selected = hit;
                highlightList();
                state.a = state.lines[hit].start;
                state.b = Math.max(state.lines[hit].start + 0.05, state.lines[hit].end);
                setLoopWidgets();
                if (writeBackEnabled()) {
                    state.drag = "move";
                    state.dragOffset = t - state.a;
                } else {
                    state.drag = null;
                }
            } else {
                state.selected = -1;
                highlightList();
                state.a = t;
                state.b = Math.min(state.duration, t + Math.max(0.5, (state.b - state.a) || 1));
                setLoopWidgets();
                state.drag = "b";
            }
        }
        canvas.setPointerCapture(e.pointerId);
        draw();
    });
    canvas.addEventListener("pointermove", (e) => {
        if (!state.drag) return;
        const cssW = canvas.clientWidth || 1;
        const t = xToTime(canvasLocalX(e), cssW);
        if (state.drag === "pan") {
            const v = viewWindow();
            const dt = (state.dragAt || t) - t;
            setView(v.start + dt, v.end + dt);
        } else if (state.drag === "a") {
            state.a = Math.min(t, state.b - 0.05);
            setLoopWidgets();
            applyLoopToSelected();
        } else if (state.drag === "b") {
            state.b = Math.max(t, state.a + 0.05);
            setLoopWidgets();
            applyLoopToSelected();
        } else if (state.drag === "move") {
            const span = state.b - state.a;
            let start = t - (state.dragOffset || 0);
            start = Math.max(0, Math.min(start, state.duration - span));
            state.a = start;
            state.b = start + span;
            setLoopWidgets();
            applyLoopToSelected();
        }
        draw();
    });
    canvas.addEventListener("pointerup", () => { state.drag = null; });

    chainCallback(audioWidget, "callback", function (value) { setAudioFile(value); });
    chainCallback(lyricsWidget, "callback", () => loadLyrics());
    chainCallback(loopWidget, "callback", () => loadLoop(true));

    node.onDragOver = (e) => !!e?.dataTransfer?.types?.includes?.("Files");
    node.onDragDrop = async function (e) {
        const item = e.dataTransfer?.files?.[0];
        if (!item || !String(item.type || "").startsWith("audio")) return false;
        try {
            const info = await uploadAudio(item);
            const name = info.name || item.name;
            if (audioWidget.options?.values && !audioWidget.options.values.includes(name)) {
                audioWidget.options.values.push(name);
            }
            audioWidget.value = name;
            audioWidget.callback?.(name);
            return true;
        } catch (err) {
            alert(err);
            return false;
        }
    };

    chainCallback(node, "onResize", function () {
        const g = dockGraph();
        if (Math.abs(g.x) < 2) {
            g.w = Math.max(DOCK_MINW, Math.round(node.size[0]));
            g.y = node.size[1] + 2;
            fl.style.width = `${g.w}px`;
            node._h3DockSig = "";
            applyDockTransform(node);
            fitCanvas();
        }
    });

    chainCallback(node, "onRemoved", function () {
        pinnedDocks.delete(node);
        liveDocks.delete(node);
        try { node._h3DockRO?.disconnect(); } catch (_) {}
        try { node._h3VisObserver?.disconnect(); } catch (_) {}
        node._h3DockEl?.remove();
        fileInput.remove();
    });

    chainCallback(node, "onConfigure", function (o) {
        node._h3Configured = true;
        const saved = o?.properties?.h3DockGraph;
        if (saved && typeof saved.w === "number" && typeof saved.h === "number") {
            node.properties.h3DockGraph = saved;
            node._h3DockGeomRestored = true;
        }
        if (typeof o?.properties?.h3ListH === "number") {
            node.properties.h3ListH = o.properties.h3ListH;
            state.listH = o.properties.h3ListH;
            list.style.flex = `0 0 ${state.listH}px`;
            list.style.height = `${state.listH}px`;
        }
        if (o?.properties?.h3DockMin != null) node.properties.h3DockMin = !!o.properties.h3DockMin;
        applyMin(!!node.properties.h3DockMin);
        if (node._h3DockGeomRestored && o && Array.isArray(o.size) && o.size.length === 2) {
            node.setSize([o.size[0], o.size[1]]);
        }
        requestAnimationFrame(() => placeDock(false));
    });

    chainCallback(node, "onExecuted", function (message) {
        const next = message?.lyrics?.[0];
        if (next == null) return;
        lyricsWidget.value = next;
        loadLyrics();
    });

    loadLyrics();
    loadLoop();
    if (audioWidget.value) setAudioFile(audioWidget.value);
    setTimeout(() => {
        if (!node._h3Configured) {
            if (node.size[0] < 360) node.setSize([360, node.size[1]]);
            placeDock(true);
        } else if (!node._h3DockGeomRestored) {
            const fitted = node.computeSize();
            if (node.size[1] > fitted[1] + 80) node.setSize([Math.max(node.size[0], 360), fitted[1]]);
            placeDock(true);
        } else {
            placeDock(false);
        }
    }, 0);
}

app.registerExtension({
    name: "H3Studio.LoadSongTimeline",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE_NAME) return;
        chainCallback(nodeType.prototype, "onNodeCreated", function () {
            installTimeline(this);
        });
    },
    async nodeCreated(node) {
        if (node?.comfyClass === NODE_NAME || node?.type === NODE_NAME) {
            installTimeline(node);
        }
    },
});

import { api } from "../../scripts/api.js";

function normalizeKind(kind) {
    const key = String(kind || "").toLowerCase();
    if (key === "picture" || key === "image") return "image";
    if (key === "video") return "video";
    if (key === "audio") return "audio";
    if (key === "model") return "model";
    return key;
}

function kindIconSvg(kind) {
    const key = normalizeKind(kind);
    if (key === "image") {
        return `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M2.2 3.2h11.6v9.6H2.2zm1.4 1.4v6.8l3.2-3.2 1.8 1.8 2.6-2.6 2.6 2.6V4.6zm7.2 1.4a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4z"/></svg>`;
    }
    if (key === "video") {
        return `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M6 4.4v7.2L12.4 8z"/></svg>`;
    }
    if (key === "audio") {
        return `<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="18" r="3.25"/><path d="M11.25 18V3.5L19.5 6"/></svg>`;
    }
    if (key === "model") {
        return `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 1.7 13.8 5v6L8 14.3 2.2 11V5L8 1.7zm0 1.6L4.4 5.3 8 7.4l3.6-2.1L8 3.3zm-4.4 3.4v3.5L7.4 12V8.5L3.6 6.7zm8.8 0L8.6 8.5V12l3.8-1.8V6.7z"/></svg>`;
    }
    return "";
}

function hasImageCrop(item) {
    const crop = item?.crop;
    if (!crop) return false;
    const w = Number(crop.w);
    const h = Number(crop.h);
    if (!(w > 0) || !(h > 0)) return false;
    const x = Number(crop.x) || 0;
    const y = Number(crop.y) || 0;
    return Math.abs(x) > 1e-6 || Math.abs(y) > 1e-6 || Math.abs(w - 1) > 1e-6 || Math.abs(h - 1) > 1e-6;
}

function applyCropThumb(img, crop) {
    if (!img || !crop) return;
    const layout = () => {
        const nw = img.naturalWidth;
        const nh = img.naturalHeight;
        if (!nw || !nh) return;
        const cropX = (Number(crop.x) || 0) * nw;
        const cropY = (Number(crop.y) || 0) * nh;
        const cropW = Math.max(1, Number(crop.w) * nw);
        const cropH = Math.max(1, Number(crop.h) * nh);
        const basis = Math.min(cropW, cropH);
        img.style.width = `${(nw / basis) * 100}%`;
        img.style.height = `${(nh / basis) * 100}%`;
        img.style.left = `${50 - ((cropX + cropW / 2) / basis) * 100}%`;
        img.style.top = `${50 - ((cropY + cropH / 2) / basis) * 100}%`;
        img.style.maxWidth = "none";
        img.style.maxHeight = "none";
        img.style.objectFit = "fill";
    };
    if (img.complete && img.naturalWidth) layout();
    else img.addEventListener("load", layout, { once: true });
}

function previewWindow(item, opts = {}) {
    const segment = Math.max(1, Math.round(Number(opts.segment) || 1));
    const regions = Array.isArray(item?.regions) ? item.regions : [];
    const region = regions.length
        ? regions[Math.min(regions.length - 1, segment - 1)]
        : {
            start: (Number(item?.start) || 0) + (segment - 1) * (Number(item?.length) || 0),
            length: item?.length,
        };
    const start = Math.max(0, Number(opts.start ?? region?.start) || 0);
    const length = Math.max(0, Number(opts.length ?? region?.length) || 0);
    return { start, length, end: start + length };
}

function viewUrl(path) {
    const rel = String(path || "").replace(/\\/g, "/");
    const q = new URLSearchParams({ path: rel });
    const route = `/h3_studio_builder/file?${q.toString()}`;
    return typeof api.apiURL === "function" ? api.apiURL(route) : route;
}

function ensureLightboxStyle() {
    if (document.getElementById("h3-studio-lightbox-style")) return;
    const style = document.createElement("style");
    style.id = "h3-studio-lightbox-style";
    style.textContent = `
.h3-builder-lightbox {
  position: fixed; inset: 0; z-index: 1000030; display: flex; align-items: center;
  justify-content: center; padding: 36px; background: rgba(0,0,0,.86);
}
.h3-builder-lightbox img, .h3-builder-lightbox video {
  max-width: 94vw; max-height: 90vh; object-fit: contain; box-shadow: 0 18px 60px rgba(0,0,0,.45);
}
.h3-builder-lightbox audio { width: min(520px, 90vw); }
.h3-builder-lightbox-label {
  position: absolute; left: 24px; bottom: 18px; right: 70px; color: white;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.h3-builder-lightbox-close {
  position: absolute; top: 18px; right: 20px; font-size: 24px; color: white;
  background: rgba(255,255,255,.12); border: 0; border-radius: 8px; width: 38px; height: 38px; cursor: pointer;
}
`;
    document.head.appendChild(style);
}

function closeMediaLightbox() {
    document.querySelector(".h3-builder-lightbox")?.remove?.();
}

function openPreview(item, opts = {}) {
    closeMediaLightbox();
    if (!item?.path) return;
    ensureLightboxStyle();
    const root = document.createElement("div");
    root.className = "h3-builder-lightbox";
    root.setAttribute("role", "dialog");
    const close = document.createElement("button");
    close.type = "button";
    close.className = "h3-builder-lightbox-close";
    close.textContent = "×";
    const label = document.createElement("div");
    label.className = "h3-builder-lightbox-label";
    const name = String(item.path || "").replace(/\\/g, "/").split("/").pop() || "";
    label.textContent = name;
    const kind = normalizeKind(item.kind);
    const range = previewWindow(item, opts);
    const url = viewUrl(item.path);
    let media;
    if (kind === "video" || kind === "audio") {
        media = document.createElement(kind === "video" ? "video" : "audio");
        media.controls = true;
        media.autoplay = true;
        media.preload = "auto";
        media.src = range.length > 0
            ? `${url}#t=${range.start.toFixed(3)},${range.end.toFixed(3)}`
            : url;
        if (range.length > 0) {
            let primed = false;
            const seekStart = () => {
                try { media.currentTime = range.start; } catch (_) {}
            };
            media.addEventListener("loadedmetadata", () => {
                const duration = Number(media.duration);
                if (Number.isFinite(duration) && duration > 0) {
                    range.end = Math.min(range.end, duration);
                }
                seekStart();
            });
            media.addEventListener("seeked", () => { primed = true; });
            media.addEventListener("timeupdate", () => {
                if (!primed || media.paused || media.seeking) return;
                if (media.currentTime >= range.end - 0.04 || media.currentTime < range.start - 0.04) {
                    primed = false;
                    seekStart();
                }
            });
        }
    } else {
        media = document.createElement("img");
        media.alt = name;
        media.src = url;
    }
    const hide = () => {
        document.removeEventListener("keydown", onKey, true);
        root.remove();
    };
    const onKey = (event) => {
        if (event.key === "Escape") hide();
    };
    close.addEventListener("click", hide);
    root.addEventListener("click", (event) => {
        if (event.target === root) hide();
    });
    document.addEventListener("keydown", onKey, true);
    root.append(media, label, close);
    document.body.appendChild(root);
}

export { applyCropThumb, closeMediaLightbox, hasImageCrop, kindIconSvg, normalizeKind, openPreview, previewWindow, viewUrl };

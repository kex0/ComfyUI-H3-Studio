"""H3 Studio Builder: pack models + dropped media into H3_STUDIO_PACK."""

from __future__ import annotations

import hashlib
import json
import os
import re

import numpy as np
import torch
from PIL import Image, ImageOps

import folder_paths

from .chain_inputs import MAX_SEGMENTS
from .node_help import NODE_HELP
from .pack import (
    MAX_MODELS, MAX_MIXED, MIN_CLIP_SEC, MAX_CLIP_SEC, assert_ref_caps,
)
from .song_loader import load_song_audio

BUILDER_SUBDIR = "h3_studio_builder"
MIN_DURATION = 5.0
MAX_DURATION = 15.0
DEFAULT_DURATION = 10.0
DEFAULT_SEGMENTS = 2
MODE_AUTO_CHAIN = "auto_chain"
MODE_MUSIC_VIDEO = "music_video"
MODE_CHOICES = (MODE_AUTO_CHAIN, MODE_MUSIC_VIDEO)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _input_root() -> str:
    root = os.path.abspath(folder_paths.get_input_directory())
    os.makedirs(root, exist_ok=True)
    return root


def contained_input_path(rel: str) -> str:
    rel = str(rel or "").replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        raise ValueError(f"h3_studio: invalid builder path {rel!r}")
    root = _input_root()
    full = os.path.abspath(os.path.join(root, rel))
    if not folder_paths.is_within_directory(root, full):
        raise ValueError(f"h3_studio: builder path escapes input/: {rel!r}")
    return full


def kind_from_name(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    raise ValueError(f"h3_studio: unsupported builder file {name!r}")


def _safe_filename(name: str) -> str:
    base = os.path.basename(str(name or "upload"))
    base = _SAFE_NAME.sub("_", base).strip("._") or "upload"
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in IMAGE_EXT | VIDEO_EXT | AUDIO_EXT:
        raise ValueError(f"h3_studio: unsupported builder file {name!r}")
    return (stem[:80] or "upload") + ext


def unique_builder_path(filename: str) -> str:
    dest_dir = os.path.join(_input_root(), BUILDER_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)
    safe = _safe_filename(filename)
    stem, ext = os.path.splitext(safe)
    n = 0
    while True:
        name = safe if n == 0 else f"{stem}_{n}{ext}"
        full = os.path.join(dest_dir, name)
        if not os.path.exists(full):
            return os.path.join(BUILDER_SUBDIR, name).replace("\\", "/")
        n += 1


def infer_media_type(value) -> str:
    if value is None:
        return ""
    if isinstance(value, torch.Tensor):
        return "image"
    if isinstance(value, dict) and "waveform" in value:
        return "audio"
    if hasattr(value, "get_components"):
        return "video"
    return "image"


def collect_socket_media(kwargs) -> dict:
    sockets = {}
    direct = kwargs.get("media")
    if direct is not None:
        sockets[0] = (infer_media_type(direct), direct)
    for index in range(1, MAX_MIXED + 1):
        value = kwargs.get(f"media_{index}")
        if value is None:
            continue
        declared = str(kwargs.get(f"media_type_{index}") or "").strip().lower()
        kind = declared if declared in {"image", "video", "audio"} else infer_media_type(value)
        sockets[index] = (kind, value)
    return sockets


def crop_image_tensor(image, crop=None):
    if image is None:
        raise ValueError("h3_studio: missing connected image")
    if not isinstance(image, torch.Tensor):
        raise ValueError("h3_studio: connected image is not a tensor")
    tensor = image
    if tensor.ndim == 3:
        tensor = tensor.unsqueeze(0)
    if tensor.ndim != 4:
        raise ValueError("h3_studio: connected image has invalid shape")
    height = int(tensor.shape[1])
    width = int(tensor.shape[2])
    box = crop_box((width, height), crop)
    if box is None:
        return tensor.contiguous()
    left, top, right, bottom = box
    return tensor[:, top:bottom, left:right, :].contiguous()


def connected_video_parts(value):
    frames = None
    audio = None
    fps = 24.0
    if hasattr(value, "get_components"):
        parts = value.get_components()
        if isinstance(parts, dict):
            frames = parts.get("images") or parts.get("frames")
            audio = parts.get("audio")
            fps = float(parts.get("fps") or 24.0)
        else:
            frames = parts[0] if parts else None
            audio = parts[1] if parts and len(parts) > 1 else None
            fps = float(parts[2]) if parts and len(parts) > 2 and parts[2] else 24.0
    elif isinstance(value, torch.Tensor):
        frames = value
    if frames is None:
        raise ValueError("h3_studio: connected video has no frames")
    if not isinstance(frames, torch.Tensor):
        raise ValueError("h3_studio: connected video frames are not a tensor")
    if frames.ndim == 3:
        frames = frames.unsqueeze(0)
    if frames.ndim != 4:
        raise ValueError("h3_studio: connected video has invalid shape")
    return frames, audio if isinstance(audio, dict) else None, max(1e-6, float(fps or 24.0))


def resample_video_24fps(frames, duration):
    n_out = max(1, int(round(max(1.0 / 24.0, float(duration)) * 24.0)))
    count = int(frames.shape[0])
    if count == n_out:
        return frames.contiguous()
    picked = []
    for i in range(n_out):
        src_i = min(count - 1, int(round(i * (count - 1) / max(1, n_out - 1))) if n_out > 1 else 0)
        picked.append(frames[src_i])
    return torch.stack(picked, dim=0).contiguous()


def slice_connected_video(value, start, length, max_len):
    frames, audio, fps = connected_video_parts(value)
    source_dur = float(frames.shape[0]) / fps
    begin, used = resolve_region(start, length, source_dur, max_len)
    i0 = max(0, min(int(frames.shape[0]), int(round(begin * fps))))
    i1 = max(i0 + 1, min(int(frames.shape[0]), int(round((begin + used) * fps))))
    sliced = frames[i0:i1]
    duration = max(1.0 / 24.0, float(sliced.shape[0]) / fps)
    soundtrack = slice_audio(audio, begin, used) if audio else None
    return resample_video_24fps(sliced, duration), duration, soundtrack


def load_image_tensor(path: str, crop=None):
    with Image.open(path) as img:
        rgb = ImageOps.exif_transpose(img).convert("RGB")
        box = crop_box(rgb.size, crop)
        if box is not None:
            rgb = rgb.crop(box)
        arr = np.array(rgb).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None,]


def probe_av_duration(path: str) -> tuple[float, bool]:
    import av

    duration = 0.0
    has_audio = False
    with av.open(path) as container:
        has_audio = bool(container.streams.audio)
        if container.duration and container.duration > 0:
            duration = float(container.duration) / float(av.time_base)
        else:
            stream = next(iter(container.streams.video or []), None) or next(
                iter(container.streams.audio or []), None
            )
            if stream is not None and stream.duration and stream.time_base:
                duration = float(stream.duration * stream.time_base)
    return max(0.0, duration), has_audio


def load_video_24fps(path: str, start=0.0, length=None):
    import av

    start = max(0.0, float(start or 0.0))
    frames = []
    src_fps = 24.0
    source_dur = 0.0
    with av.open(path) as container:
        vstream = next(iter(container.streams.video or []), None)
        if vstream is None:
            raise ValueError(f"h3_studio: no video stream in {path}")
        rate = vstream.average_rate or vstream.guessed_rate
        src_fps = float(rate) if rate else 24.0
        if src_fps <= 0:
            src_fps = 24.0
        if container.duration and container.duration > 0:
            source_dur = float(container.duration) / float(av.time_base)
        elif vstream.duration and vstream.time_base:
            source_dur = float(vstream.duration * vstream.time_base)
        if length is None or float(length) <= 0:
            length = max(0.0, source_dur - start)
        end = start + float(length)
        try:
            container.seek(int(max(0.0, start) / float(av.time_base)))
        except (ValueError, av.AVError, OverflowError):
            pass
        for frame in container.decode(video=0):
            t = frame.time
            if t is None:
                t = start + (len(frames) / src_fps)
            if t < start:
                continue
            if t >= end:
                break
            frames.append(frame.to_ndarray(format="rgb24"))
    if not frames:
        raise ValueError(f"h3_studio: no frames in {path}")
    clip_dur = max(1.0 / 24.0, float(length or (len(frames) / src_fps)))
    n_out = max(1, int(round(clip_dur * 24.0)))
    picked = []
    for i in range(n_out):
        src_i = min(len(frames) - 1, int(round(i * (len(frames) - 1) / max(1, n_out - 1))) if n_out > 1 else 0)
        picked.append(frames[src_i])
    stacked = np.stack(picked, axis=0).astype(np.float32) / 255.0
    audio = None
    try:
        audio = slice_audio(load_song_audio(path), start, clip_dur)
    except (ValueError, OSError, av.AVError):
        audio = None
    return torch.from_numpy(stacked), float(clip_dur), audio


def normalize_mode(mode) -> str:
    text = str(mode or "").strip().lower().replace(" ", "_")
    if "music" in text:
        return MODE_MUSIC_VIDEO
    return MODE_AUTO_CHAIN


def clamp_duration(value) -> float:
    return max(MIN_DURATION, min(MAX_DURATION, float(value)))


def clamp_segments(value) -> int:
    return max(1, min(int(MAX_SEGMENTS), int(value)))


def resolve_builder_song(song, song_file):
    if isinstance(song, dict) and song.get("waveform") is not None:
        return song
    name = str(song_file or "").strip()
    if not name:
        return None
    if not folder_paths.exists_annotated_filepath(name):
        raise ValueError(f"h3_studio: invalid song file: {name}")
    return load_song_audio(folder_paths.get_annotated_filepath(name))


def resolve_region(start, length, source_dur, max_len) -> tuple[float, float]:
    source = max(0.0, float(source_dur or 0.0))
    cap = max(MIN_CLIP_SEC, min(MAX_CLIP_SEC, float(max_len or MAX_DURATION)))
    if source <= 0:
        return 0.0, 0.0
    span = min(source, cap)
    if length is None or float(length) <= 0:
        used = span
    else:
        used = min(float(length), span, source)
    if source >= MIN_CLIP_SEC:
        used = max(MIN_CLIP_SEC, used)
    else:
        used = source
    begin = max(0.0, float(start or 0.0))
    if begin + used > source:
        begin = max(0.0, source - used)
    return begin, used


def normalize_regions(raw, source_dur, max_len, segments=1) -> list[tuple[float, float]]:
    count = max(1, min(int(MAX_SEGMENTS), int(segments or 1)))
    source = max(0.0, float(source_dur or 0.0))
    stored = raw.get("regions") if isinstance(raw, dict) else None
    regions = []
    if isinstance(stored, list):
        for entry in stored[:count]:
            if not isinstance(entry, dict):
                continue
            regions.append(resolve_region(entry.get("start"), entry.get("length"), source, max_len))
    if not regions and isinstance(raw, dict):
        regions.append(resolve_region(raw.get("start"), raw.get("length"), source, max_len))
    if not regions:
        regions.append(resolve_region(0.0, None, source, max_len))
    while len(regions) < count:
        start, length = regions[-1]
        regions.append(resolve_region(start + length, length, source, max_len))
    return regions[:count]


def crop_box(size, crop):
    if not isinstance(crop, dict):
        return None
    width, height = int(size[0]), int(size[1])
    if width < 1 or height < 1:
        return None
    x = float(crop.get("x") or 0.0)
    y = float(crop.get("y") or 0.0)
    w = float(crop.get("w") or 0.0)
    h = float(crop.get("h") or 0.0)
    if w <= 0 or h <= 0:
        return None
    if abs(x) < 1e-6 and abs(y) < 1e-6 and abs(w - 1.0) < 1e-6 and abs(h - 1.0) < 1e-6:
        return None
    left = int(round(x * width))
    top = int(round(y * height))
    right = int(round((x + w) * width))
    bottom = int(round((y + h) * height))
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    return left, top, right, bottom


def slice_audio(audio, start, length):
    if not isinstance(audio, dict) or "waveform" not in audio:
        return audio
    waveform = audio["waveform"]
    sr = int(audio["sample_rate"])
    if sr <= 0 or waveform is None:
        return audio
    total = int(waveform.shape[-1])
    i0 = max(0, min(total, int(round(float(start) * sr))))
    i1 = max(i0 + 1, min(total, int(round((float(start) + float(length)) * sr))))
    return {"waveform": waveform[..., i0:i1].contiguous(), "sample_rate": sr}


def media_enabled_for_load(raw, skip_audio: bool) -> bool:
    if not isinstance(raw, dict) or raw.get("enabled", True) is False:
        return False
    if skip_audio and str(raw.get("kind") or "") == "audio":
        return False
    return True


def file_properties(rel: str) -> dict:
    path = contained_input_path(rel)
    if not os.path.isfile(path):
        raise ValueError(f"h3_studio: missing builder file {rel!r}")
    st = os.stat(path)
    kind = kind_from_name(path)
    props = {
        "relative_path": str(rel or "").replace("\\", "/"),
        "filename": os.path.basename(path),
        "format": os.path.splitext(path)[1].lstrip(".").upper(),
        "kind": kind,
        "width": 0,
        "height": 0,
        "frames": 1,
        "duration": 0.0,
        "size": int(st.st_size),
        "mtime_ms": int(st.st_mtime * 1000),
    }
    if kind == "image":
        with Image.open(path) as img:
            upright = ImageOps.exif_transpose(img)
            props["width"], props["height"] = upright.size
            props["format"] = str(img.format or props["format"]).upper()
        return props
    duration, _has_audio = probe_av_duration(path)
    props["duration"] = float(duration)
    if kind != "video":
        return props
    import av

    with av.open(path) as container:
        stream = next(iter(container.streams.video or []), None)
        if stream is None:
            return props
        if stream.width:
            props["width"] = int(stream.width)
        if stream.height:
            props["height"] = int(stream.height)
        if stream.frames:
            props["frames"] = int(stream.frames)
    return props


def parse_state(state_json) -> dict:
    if isinstance(state_json, dict):
        return state_json
    text = str(state_json or "").strip() or "{}"
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("h3_studio: builder state_json must be an object")
    return data


def collect_builder_models(kwargs, state) -> list:
    meta_by_slot = {}
    for item in state.get("models") or []:
        if not isinstance(item, dict):
            continue
        slot = int(item.get("slot") or 0)
        if slot > 0:
            meta_by_slot[slot] = item
    enabled = []
    for i in range(1, MAX_MODELS + 1):
        model = kwargs.get(f"model_{i}")
        if model is None:
            continue
        meta = meta_by_slot.get(i) or {}
        if meta.get("enabled", True) is False:
            continue
        enabled.append({
            "index": len(enabled) + 1,
            "description": str(meta.get("description") or ""),
            "model": model,
            "slot": i,
        })
    if not enabled:
        raise ValueError("h3_studio: enable at least one Builder model")
    return enabled


def builder_file_path(raw) -> str:
    rel = str((raw or {}).get("path") or "").strip()
    if not rel:
        return ""
    try:
        path = contained_input_path(rel)
    except ValueError:
        return ""
    return path if os.path.isfile(path) else ""


def load_enabled_media(state, skip_audio=False, max_clip_sec=DEFAULT_DURATION, segments=DEFAULT_SEGMENTS,
                       sockets=None) -> tuple[list, list, list]:
    pictures, videos, audios = [], [], []
    max_clip_sec = clamp_duration(max_clip_sec)
    segment_count = clamp_segments(segments)
    sockets = sockets or {}
    have_first = False
    for raw in state.get("media") or []:
        if not media_enabled_for_load(raw, skip_audio):
            continue
        path = builder_file_path(raw)
        socket = int(raw.get("socket") or 0)
        connected = sockets.get(socket) if socket else None
        kind = str(raw.get("kind") or "").lower()
        if kind not in {"image", "video", "audio"}:
            if connected:
                kind = connected[0]
            elif path:
                kind = kind_from_name(path)
        desc = str(raw.get("description") or "")
        if kind == "image":
            if connected:
                image = crop_image_tensor(connected[1], raw.get("crop"))
            elif path:
                image = load_image_tensor(path, raw.get("crop"))
            else:
                raise ValueError(f"h3_studio: missing builder image {raw.get('path')!r}")
            is_first = bool(raw.get("first_frame")) and not have_first
            if is_first:
                have_first = True
            pictures.append({
                "index": len(pictures) + 1,
                "description": desc,
                "image": image,
                "duration": 0.0,
                "first_frame": is_first,
            })
        elif kind == "video":
            if connected:
                frames0, _audio0, fps0 = connected_video_parts(connected[1])
                source_dur = float(frames0.shape[0]) / fps0
            elif path:
                source_dur, _has_audio = probe_av_duration(path)
            else:
                raise ValueError(f"h3_studio: missing builder video {raw.get('path')!r}")
            windows = normalize_regions(raw, source_dur, max_clip_sec, segment_count)
            loaded = []
            for start, length in windows:
                if connected:
                    frames, duration, soundtrack = slice_connected_video(connected[1], start, length, max_clip_sec)
                else:
                    frames, duration, soundtrack = load_video_24fps(path, start, length)
                loaded.append({
                    "start": start,
                    "length": length,
                    "frames": frames,
                    "duration": duration,
                    "audio": soundtrack,
                })
            first = loaded[0]
            videos.append({
                "index": len(videos) + 1,
                "description": desc,
                "frames": first["frames"],
                "duration": first["duration"],
                "audio": first["audio"],
                "regions": loaded,
            })
        elif kind == "audio":
            if connected:
                audio = connected[1]
                if not isinstance(audio, dict) or "waveform" not in audio:
                    raise ValueError("h3_studio: connected audio is missing a waveform")
            elif path:
                audio = load_song_audio(path)
            else:
                raise ValueError(f"h3_studio: missing builder audio {raw.get('path')!r}")
            source_dur = float(audio["waveform"].shape[-1]) / float(audio["sample_rate"])
            windows = normalize_regions(raw, source_dur, max_clip_sec, segment_count)
            loaded = []
            for start, length in windows:
                sliced = slice_audio(audio, start, length)
                duration = float(sliced["waveform"].shape[-1]) / float(sliced["sample_rate"])
                loaded.append({
                    "start": start,
                    "length": length,
                    "audio": sliced,
                    "duration": duration,
                })
            first = loaded[0]
            audios.append({
                "index": len(audios) + 1,
                "description": desc,
                "audio": first["audio"],
                "duration": first["duration"],
                "regions": loaded,
            })
        else:
            raise ValueError(f"h3_studio: unknown builder kind {kind!r}")
    return pictures, videos, audios


def _register_builder_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    instance = getattr(PromptServer, "instance", None)
    if instance is None or getattr(instance, "_h3_studio_builder_upload", False):
        return
    instance._h3_studio_builder_upload = True

    @instance.routes.get("/h3_studio_builder/properties")
    async def h3_studio_builder_properties(request):
        rel = request.rel_url.query.get("path", "")
        try:
            return web.json_response(file_properties(rel))
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)

    @instance.routes.get("/h3_studio_builder/file")
    async def h3_studio_builder_file(request):
        rel = request.rel_url.query.get("path", "")
        try:
            path = contained_input_path(rel)
            if not os.path.isfile(path):
                return web.json_response({"error": "missing file"}, status=404)
            return web.FileResponse(path)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)

    @instance.routes.post("/h3_studio_builder/upload")
    async def h3_studio_builder_upload(request):
        post = await request.post()
        upload = post.get("file") or post.get("image")
        filename = getattr(upload, "filename", None) or post.get("filename") or "upload"
        if upload is None or not hasattr(upload, "file"):
            return web.json_response({"error": "expected a file"}, status=400)
        try:
            rel = unique_builder_path(str(filename))
            dest = contained_input_path(rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            data = upload.file.read()
            with open(dest, "wb") as handle:
                handle.write(data)
            kind = kind_from_name(rel)
            duration = 0.0
            has_soundtrack = False
            if kind in ("video", "audio"):
                duration, has_soundtrack = probe_av_duration(dest)
                if kind == "audio":
                    has_soundtrack = False
            return web.json_response({
                "path": rel,
                "kind": kind,
                "duration": duration,
                "has_soundtrack": bool(has_soundtrack and kind == "video"),
            })
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)


_register_builder_routes()


class H3StudioBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_1": ("MODEL", {
                    "tooltip": (
                        "Required patched H3 MODEL (Checkpoint → LoRA → Sigma Shift → "
                        "Sage / SolAttn / Spectrum). Connecting it reveals model_2, and so on."
                    ),
                }),
                "state_json": ("STRING", {
                    "default": "{}", "multiline": True,
                    "tooltip": "Hidden Builder list state (paths, enable, descriptions).",
                }),
                "mode": (list(MODE_CHOICES), {
                    "default": MODE_AUTO_CHAIN,
                    "tooltip": (
                        "Auto Chain keeps picture, video, and standalone audio refs. "
                        "Music Video disables audio refs (the song occupies Audio 1)."
                    ),
                }),
                "max_clip_duration": ("FLOAT", {
                    "default": DEFAULT_DURATION,
                    "min": MIN_DURATION,
                    "max": MAX_DURATION,
                    "step": 0.1,
                    "display": "number",
                    "tooltip": (
                        "Requested clip length in seconds. Music Video treats this as the "
                        "per-clip maximum. Travels with the pack."
                    ),
                }),
                "segments": ("INT", {
                    "default": DEFAULT_SEGMENTS,
                    "min": 1,
                    "max": MAX_SEGMENTS,
                    "step": 1,
                    "tooltip": (
                        "Auto Chain story clip count. Hidden in Music Video mode. "
                        "Wire segments into Auto Chain."
                    ),
                }),
                "loop": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "Auto Chain loop clip that returns to clip 1. Hidden in Music Video mode. "
                        "Travels with the pack for Local Prompter."
                    ),
                }),
                "song_file": ("STRING", {
                    "default": "",
                    "hidden": True,
                    "tooltip": "Uploaded song filename used when the song socket is empty.",
                }),
                "lyrics": ("STRING", {
                    "multiline": True, "default": "", "dynamicPrompts": False,
                    "tooltip": (
                        "Confirm-format LRC lyrics for Music Video. Wire Load Song lyrics, "
                        "or paste here. Hidden in Auto Chain mode."
                    ),
                }),
            },
            "optional": {
                "song": ("AUDIO", {
                    "tooltip": (
                        "Source song for Music Video. Click or drop a file on the widget, "
                        "or wire Load Song. A connection disables the upload widget."
                    ),
                }),
                "media": ("*", {
                    "tooltip": (
                        "Connect IMAGE, VIDEO, or AUDIO. Multiple wires to this socket "
                        "appear immediately in the Builder list."
                    ),
                }),
                **{
                    f"media_{i}": ("*", {"hidden": True})
                    for i in range(1, MAX_MIXED + 1)
                },
                **{
                    f"media_type_{i}": ("STRING", {"default": "", "hidden": True})
                    for i in range(1, MAX_MIXED + 1)
                },
                **{
                    f"model_{i}": ("MODEL", {
                        "tooltip": (
                            f"Optional patched H3 MODEL {i}. Appears when model_{i - 1} is connected."
                        ),
                    })
                    for i in range(2, MAX_MODELS + 1)
                },
            },
        }

    RETURN_TYPES = ("H3_STUDIO_PACK",)
    RETURN_NAMES = ("pack",)
    OUTPUT_TOOLTIPS = (
        "Pack of enabled models and media for Auto Chain / Music Video. "
        "Duration, clip count, loop, song, and lyrics travel with the pack.",
    )
    FUNCTION = "build_pack"
    CATEGORY = "H3 Studio"
    DESCRIPTION = NODE_HELP["H3StudioBuilder"]

    def build_pack(self, model_1, mode=MODE_AUTO_CHAIN, max_clip_duration=DEFAULT_DURATION,
                  segments=DEFAULT_SEGMENTS, loop=False, song_file="", lyrics="",
                  song=None, state_json="{}", **kwargs):
        kwargs = dict(kwargs)
        kwargs["model_1"] = model_1
        mode = normalize_mode(mode)
        duration = clamp_duration(max_clip_duration)
        state = parse_state(state_json)
        models = collect_builder_models(kwargs, state)
        pictures, videos, audios = load_enabled_media(
            state, skip_audio=(mode == MODE_MUSIC_VIDEO), max_clip_sec=duration,
            segments=clamp_segments(segments), sockets=collect_socket_media(kwargs),
        )
        assert_ref_caps(pictures, videos, audios)
        pack = {
            "models": models,
            "pictures": pictures,
            "videos": videos,
            "audios": audios,
            "plan": str(state.get("plan") or "").strip(),
            "duration": duration,
            "segments": clamp_segments(segments),
            "loop": bool(loop) and mode == MODE_AUTO_CHAIN,
        }
        if mode == MODE_MUSIC_VIDEO:
            pack["song"] = resolve_builder_song(song, song_file)
            pack["lyrics"] = str(lyrics or "").strip()
        return (pack,)

    @classmethod
    def IS_CHANGED(cls, model_1, mode=MODE_AUTO_CHAIN, max_clip_duration=DEFAULT_DURATION,
                   segments=DEFAULT_SEGMENTS, loop=False, song_file="", lyrics="",
                   song=None, state_json="{}", **kwargs):
        digest = hashlib.sha256()
        mode = normalize_mode(mode)
        digest.update(mode.encode("utf-8"))
        digest.update(f"{clamp_duration(max_clip_duration):.3f}".encode("utf-8"))
        digest.update(str(clamp_segments(segments)).encode("utf-8"))
        digest.update(str(bool(loop)).encode("utf-8"))
        digest.update(str(lyrics or "").encode("utf-8"))
        digest.update(str(song_file or "").encode("utf-8"))
        if song is not None:
            digest.update(b"song:wired")
            if isinstance(song, dict):
                wave = song.get("waveform")
                if wave is not None:
                    digest.update(str(tuple(wave.shape)).encode("utf-8"))
                digest.update(str(song.get("sample_rate") or "").encode("utf-8"))
        elif str(song_file or "").strip() and folder_paths.exists_annotated_filepath(song_file):
            try:
                st = os.stat(folder_paths.get_annotated_filepath(song_file))
                digest.update(str(st.st_mtime_ns).encode("utf-8"))
                digest.update(str(st.st_size).encode("utf-8"))
            except Exception:
                pass
        digest.update(str(state_json or "").encode("utf-8"))
        try:
            state = parse_state(state_json)
        except Exception:
            return digest.hexdigest()
        skip_audio = mode == MODE_MUSIC_VIDEO
        if kwargs.get("media") is not None:
            digest.update(b"media:direct")
        for index in range(1, MAX_MIXED + 1):
            if kwargs.get(f"media_{index}") is not None:
                digest.update(f"media_{index}:{kwargs.get(f'media_type_{index}')}".encode("utf-8"))
        for raw in state.get("media") or []:
            if not media_enabled_for_load(raw, skip_audio):
                continue
            digest.update(f"socket:{raw.get('socket')}|kind:{raw.get('kind')}|src:{raw.get('source_id')}:{raw.get('source_slot')}".encode("utf-8"))
            digest.update(f"{raw.get('start')}|{raw.get('length')}|{raw.get('first_frame')}".encode("utf-8"))
            digest.update(json.dumps(raw.get("regions") or [], sort_keys=True, default=str).encode("utf-8"))
            crop = raw.get("crop")
            if isinstance(crop, dict):
                digest.update(json.dumps(crop, sort_keys=True, default=str).encode("utf-8"))
            path = builder_file_path(raw)
            if not path:
                continue
            try:
                st = os.stat(path)
            except Exception:
                continue
            digest.update(str(raw.get("path") or "").encode("utf-8"))
            digest.update(str(st.st_mtime_ns).encode("utf-8"))
            digest.update(str(st.st_size).encode("utf-8"))
        return digest.hexdigest()

"""Single-node H3 face refine for a full video (music-video length).

The existing Track / Inject / Denoise / Stitch nodes still handle one H3-legal
clip. This orchestrator tracks the whole sequence once, packs frames that need
paste into H3 windows no longer than chunk_duration, copies close-ups, locks
chunk audio into the target AV stream, denoises only the face tokens inside
each crop, and pastes that face back where the head is small.
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import shutil
import subprocess

import numpy as np
import torch
from PIL import Image

import comfy.model_management
import comfy.nested_tensor
import comfy.sample
import comfy.utils
import folder_paths
import latent_preview
from comfy_extras.nodes_custom_sampler import Guider_Basic
from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo, _encode_ref_audio

from .grid import (
    CHUNK_OVERLAP, CLOSEUP_RAMP, DENOISE_GAMMA, FACE_INPAINT_DILATION, H3_SPATIAL,
    MIN_VISIBLE_SEC, OVERLAP_SOFT_STEPS, align_h3_frames, canvas_rect_to_source,
    chunk_is_all_closeup, chunk_ranges, committed_file_spans, committed_write_span,
    debug_file_slice, denoise_px_range, face_ellipse_mask, face_token_video_mask,
    h3_latent_t, h3_steps_covering, hard_cut_breaks, latent_mask_to_frames,
    overlap_freeze_scale, pack_refine_chunks, per_frame_strength,
    refine_paste_weight, select_chunk_span, segment_hold, sustained_visible,
)
from .nodes import (
    H3FaceStitch, H3FaceTrackCrop, H3InjectVideoLatent, H3PerFrameDenoise,
    _affine_crop, _detector_list, _load_detector, _to_bgr_u8,
    crop_transform_frames,
)
from ..node_help import NODE_HELP

_LOG = logging.getLogger("h3_facerefine")
FPS = 24
WRITE_BATCH = 24
_DEFAULT_PROMPT = (
    "the person in <Picture 1>, sharp natural face, matching identity, "
    "photoreal skin, no makeup change, no identity drift, mouth following <Audio 1>"
)


def _release_loaded_models():
    try:
        import comfy.memory_management
        import comfy.model_prefetch
        import comfy_aimdo.model_vbar
        if comfy.memory_management.aimdo_enabled:
            comfy.model_management.reset_cast_buffers()
            comfy.model_prefetch.cleanup_prefetch_queues()
            comfy_aimdo.model_vbar.vbars_reset_watermark_limits()
    except Exception:
        pass
    comfy.model_management.unload_all_models()
    gc.collect()
    comfy.model_management.soft_empty_cache(True)


def _maskvid_pack_breaks(xform, n, src_w, src_h):
    """MaskVid packing cuts: crop teleports. A zoom is not a cut."""
    if xform.get("maskvid_cut") == "center":
        stored = xform.get("maskvid_breaks")
        if stored is not None and len(stored) == n:
            br = np.asarray(stored, dtype=bool).copy()
            if n:
                br[0] = True
            return br
    boxes = xform.get("boxes") or []
    if len(boxes) == n:
        return hard_cut_breaks(boxes, int(src_w), int(src_h))
    br = np.zeros(n, dtype=bool)
    if n:
        br[0] = True
    return br


def _resolve_media_path(path):
    path = os.path.expanduser(str(path).strip().strip('"'))
    if os.path.isdir(path) or os.path.isfile(path):
        return os.path.abspath(path)
    cand = os.path.join(folder_paths.get_input_directory(), path)
    if os.path.isdir(cand) or os.path.isfile(cand):
        return os.path.abspath(cand)
    raise ValueError(f"h3_facerefine: video or frame folder not found: {path}")


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _job_frames_dir(job_dir):
    return os.path.join(job_dir, "frames")


def _png_path(frames_dir, index):
    return os.path.join(frames_dir, f"{int(index):08d}.png")


def _list_image_frames(folder):
    names = []
    png_only = []
    for name in os.listdir(folder):
        ext = os.path.splitext(name)[1].lower()
        if ext not in _IMAGE_EXTS:
            continue
        names.append(name)
        if ext == ".png":
            png_only.append(name)
    use = png_only if png_only else names
    use.sort()
    if not use:
        raise ValueError(f"h3_facerefine: no PNG/JPEG frames in {folder}")
    return [os.path.join(folder, n) for n in use]


def _read_seq_fps(folder, default=FPS):
    fps_path = os.path.join(folder, "fps.txt")
    if not os.path.isfile(fps_path):
        return float(default)
    try:
        with open(fps_path, "r", encoding="utf-8") as f:
            return float(f.read().strip().split()[0]) or float(default)
    except (OSError, ValueError):
        return float(default)


def _save_png_frame(frames_dir, index, rgb_u8):
    os.makedirs(frames_dir, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(rgb_u8), "RGB").save(
        _png_path(frames_dir, index), compress_level=1,
    )


def _write_png_range(frames_dir, start, images):
    if images is None or int(images.shape[0]) == 0:
        return
    start = int(start)
    images = images[..., :3]
    n = int(images.shape[0])
    for i in range(0, n, WRITE_BATCH):
        arr = _u8_rgb(images[i:i + WRITE_BATCH])
        for j in range(arr.shape[0]):
            _save_png_frame(frames_dir, start + i + j, arr[j])


def _delete_png_from(frames_dir, start, n):
    if not os.path.isdir(frames_dir):
        return
    for i in range(int(start), int(n)):
        path = _png_path(frames_dir, i)
        if os.path.isfile(path):
            os.remove(path)


def _audio_sidecar(frames_dir):
    parent = os.path.dirname(os.path.abspath(frames_dir))
    stem = os.path.basename(os.path.abspath(frames_dir).rstrip("\\/"))
    if stem.endswith("_frames"):
        base = stem[:-7]
        for name in (base + "_song.mp4", base + ".mp4"):
            cand = os.path.join(parent, name)
            if os.path.isfile(cand):
                return cand
    if not os.path.isdir(parent):
        return None
    songs = []
    other = []
    for name in sorted(os.listdir(parent)):
        if not name.lower().endswith(".mp4"):
            continue
        cand = os.path.join(parent, name)
        if not os.path.isfile(cand):
            continue
        if "_song" in name:
            songs.append(cand)
        else:
            other.append(cand)
    if songs:
        return songs[0]
    return other[0] if other else None


def _ffmpeg_exe():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError("h3_facerefine: ffmpeg not found (needed to write the output MP4)")


class _ImageSeqFrames:
    """Random-access frames from a PNG/JPEG folder without holding the clip in RAM."""

    def __init__(self, folder):
        self.path = os.path.abspath(folder)
        self.files = _list_image_frames(self.path)
        self.n = len(self.files)
        with Image.open(self.files[0]) as im:
            w, h = im.size
        self.h = int(h)
        self.w = int(w)
        self.fps = _read_seq_fps(self.path, FPS)
        if self.n <= 0 or self.h <= 0 or self.w <= 0:
            raise ValueError(f"h3_facerefine: unreadable frame folder {folder}")

    def __len__(self):
        return self.n

    @property
    def shape(self):
        return (self.n, self.h, self.w, 3)

    def close(self):
        return None

    def get(self, i):
        i = int(i)
        if i < 0 or i >= self.n:
            raise IndexError(i)
        with Image.open(self.files[i]) as im:
            rgb = np.array(im.convert("RGB"), dtype=np.uint8, copy=True)
        if rgb.shape[0] != self.h or rgb.shape[1] != self.w:
            raise ValueError(
                f"h3_facerefine: frame {i} size {rgb.shape[1]}x{rgb.shape[0]} "
                f"!= {self.w}x{self.h}"
            )
        return torch.from_numpy(np.ascontiguousarray(rgb)).to(torch.float32).div_(255.0)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(self.n)
            if step != 1:
                raise ValueError("h3_facerefine: video slice step must be 1")
            if stop - start > 256:
                raise ValueError(
                    f"h3_facerefine: video slice {start}:{stop} is too large; stream in batches"
                )
            frames = [self.get(i) for i in range(start, stop)]
            if not frames:
                return torch.zeros((0, self.h, self.w, 3), dtype=torch.float32)
            return torch.stack(frames, dim=0)
        return self.get(int(idx))


def _open_source(path):
    resolved = _resolve_media_path(path)
    if os.path.isdir(resolved):
        return _ImageSeqFrames(resolved)
    return _VideoFrames(resolved)


class _VideoFrames:
    """Random-access frames from an MP4 without holding the clip in RAM."""

    def __init__(self, path):
        import cv2
        self._cv2 = cv2
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise ValueError(f"h3_facerefine: cannot open video {path}")
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0) or FPS
        if self.n <= 0 or self.h <= 0 or self.w <= 0:
            self.close()
            raise ValueError(f"h3_facerefine: unreadable video header {path}")
        self._i = -1

    def __len__(self):
        return self.n

    @property
    def shape(self):
        return (self.n, self.h, self.w, 3)

    def close(self):
        if getattr(self, "cap", None) is not None:
            self.cap.release()
            self.cap = None

    def get(self, i):
        i = int(i)
        if i < 0 or i >= self.n:
            raise IndexError(i)
        if i != self._i + 1:
            self.cap.set(self._cv2.CAP_PROP_POS_FRAMES, i)
        ok, bgr = self.cap.read()
        if not ok:
            raise RuntimeError(f"h3_facerefine: failed to read frame {i} from {self.path}")
        self._i = i
        rgb = self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB)
        return torch.from_numpy(np.ascontiguousarray(rgb)).to(torch.float32).div_(255.0)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(self.n)
            if step != 1:
                raise ValueError("h3_facerefine: video slice step must be 1")
            if stop - start > 256:
                raise ValueError(
                    f"h3_facerefine: video slice {start}:{stop} is too large; stream in batches"
                )
            frames = [self.get(i) for i in range(start, stop)]
            if not frames:
                return torch.zeros((0, self.h, self.w, 3), dtype=torch.float32)
            return torch.stack(frames, dim=0)
        return self.get(int(idx))


class _FrameWriter:
    def __init__(self, path, width, height, fps, crf=18):
        self.path = path
        self.w = int(width)
        self.h = int(height)
        self.preview = None
        self._p = subprocess.Popen(
            [
                _ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{self.w}x{self.h}", "-r", str(float(fps)), "-i", "-",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(int(crf)),
                path,
            ],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

    def write(self, images):
        images = images[..., :3]
        n = int(images.shape[0])
        for i in range(0, n, WRITE_BATCH):
            sl = images[i:i + WRITE_BATCH]
            arr = (sl.detach().cpu().clamp(0, 1).numpy() * 255.0).astype(np.uint8)
            if int(arr.shape[1]) != self.h or int(arr.shape[2]) != self.w:
                raise ValueError(
                    f"h3_facerefine: writer size {self.w}x{self.h} != frames {arr.shape[2]}x{arr.shape[1]}"
                )
            self._p.stdin.write(np.ascontiguousarray(arr).tobytes())
            del arr
        self.preview = images[-1:].detach().cpu().contiguous()

    def close(self):
        self._p.stdin.close()
        err = self._p.stderr.read().decode("utf-8", "replace") if self._p.stderr else ""
        rc = self._p.wait()
        if rc != 0:
            raise RuntimeError(f"h3_facerefine: ffmpeg failed ({rc}): {err[-2000:]}")
        return self.preview


def _audio_from_video(video_path, wav_path):
    import torchaudio
    r = subprocess.run(
        [
            _ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            wav_path,
        ],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0 or not os.path.isfile(wav_path):
        raise RuntimeError(r.stderr[-2000:] if r.stderr else "no audio stream")
    wf, sr = torchaudio.load(wav_path)
    if os.path.isfile(wav_path):
        os.remove(wav_path)
    if wf.ndim == 2:
        wf = wf.unsqueeze(0)
    return {"waveform": wf, "sample_rate": int(sr)}


def _progress(unique_id, text):
    from ..png_sequence import send_node_progress
    send_node_progress(unique_id, text)


def _safe_stem(path):
    stem = os.path.splitext(os.path.basename(path or "image_batch"))[0]
    out = "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem).strip("_")
    return (out or "video")[:80]


def _job_dir(source_path, fingerprint=""):
    root = folder_paths.get_temp_directory()
    prefix = "video/h3_face_refine"
    stem = _safe_stem(source_path)
    if fingerprint:
        stem = f"{stem}_{fingerprint}"
    path = os.path.join(root, prefix.replace("/", os.sep), stem)
    os.makedirs(path, exist_ok=True)
    return path


def _source_fingerprint(n, width, height, images=None, path=""):
    h = hashlib.sha1()
    h.update(f"{int(n)}x{int(width)}x{int(height)}".encode())
    path = str(path or "").strip()
    if path:
        abs_path = os.path.abspath(path)
        h.update(abs_path.encode())
        try:
            st = os.stat(abs_path)
            h.update(f"|{st.st_mtime_ns}|{st.st_size}".encode())
        except OSError:
            pass
    elif images is not None:
        arr = images[..., :3]
        count = int(arr.shape[0])
        if count > 0:
            for i in (0, count // 2, count - 1):
                frame = arr[int(i)].detach()
                if frame.device.type != "cpu":
                    frame = frame.cpu()
                u8 = (frame.float().clamp(0, 1) * 255).to(torch.uint8).numpy()
                h.update(np.ascontiguousarray(u8[::32, ::32]).tobytes())
    return h.hexdigest()[:16]


def _media_rel(abs_path):
    abs_path = os.path.abspath(abs_path)
    for root, kind in (
        (folder_paths.get_temp_directory(), "temp"),
        (folder_paths.get_output_directory(), "output"),
        (folder_paths.get_input_directory(), "input"),
    ):
        root = os.path.abspath(root)
        try:
            rel = os.path.relpath(abs_path, root)
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        sub = os.path.dirname(rel).replace("\\", "/")
        if sub == ".":
            sub = ""
        return os.path.basename(rel), sub, kind
    return os.path.basename(abs_path), "", "temp"


def _load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    def _default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, tuple):
            return list(o)
        raise TypeError(type(o).__name__)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, default=_default)
    os.replace(tmp, path)


def _save_xform(path, xform):
    _save_json(path, xform)


def _load_xform(path):
    data = _load_json(path)
    if not data:
        return None
    for k in ("boxes", "weights", "detected", "face_rect", "via_body", "face_h", "face_w"):
        if k in data and isinstance(data[k], list):
            data[k] = [tuple(x) if isinstance(x, list) else x for x in data[k]]
    if "canvas" in data:
        data["canvas"] = tuple(data["canvas"])
    if "src_size" in data:
        data["src_size"] = tuple(data["src_size"])
    return data


def _save_pending(path, frames):
    arr = (frames[..., :3].detach().cpu().clamp(0, 1).numpy() * 255.0).astype(np.uint8)
    np.save(path, arr)


def _load_pending(path):
    if not os.path.isfile(path):
        return None
    arr = np.load(path)
    return torch.from_numpy(np.ascontiguousarray(arr)).to(torch.float32).div_(255.0)


def _chunk_mp4(job_dir, index_1):
    return os.path.join(job_dir, f"chunk_{int(index_1):03d}.mp4")


def _debug_mp4(job_dir, kind, index_1):
    return os.path.join(job_dir, f"debug_{kind}_{int(index_1):03d}.mp4")


def _write_frames_mp4(path, frames, fps, crf=18):
    frames = frames[..., :3]
    writer = _FrameWriter(path, int(frames.shape[2]), int(frames.shape[1]), fps, crf=int(crf))
    try:
        writer.write(frames)
    finally:
        writer.close()


def _mp4_n_frames(path):
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if n > 0:
            return n
        n = 0
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            n += 1
        return n
    finally:
        cap.release()


def _trim_mp4(src, dest, off, count, fps, crf=18):
    import cv2
    cap = cv2.VideoCapture(src)
    writer = None
    kept = 0
    i = 0
    try:
        while kept < int(count):
            ok, bgr = cap.read()
            if not ok:
                break
            if i >= int(off):
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                t = _rgb_to_torch(rgb[None])
                if writer is None:
                    writer = _FrameWriter(
                        dest, int(rgb.shape[1]), int(rgb.shape[0]), fps, crf=int(crf),
                    )
                writer.write(t)
                kept += 1
            i += 1
    finally:
        cap.release()
        if writer is not None:
            writer.close()
    return kept


def _write_source_range(path, source, start, end, fps, crf=18, dest=None, png_dir=None):
    """Encode original frames without holding the whole span in RAM."""
    start, end = int(start), int(end)
    if end <= start:
        return None
    writer = None
    preview = None
    for i in range(start, end, WRITE_BATCH):
        j = min(i + WRITE_BATCH, end)
        frames = source[i:j][..., :3]
        if dest is not None:
            dest[i:j] = frames.to(device=dest.device, dtype=dest.dtype)
        if png_dir is not None:
            _write_png_range(png_dir, i, frames)
        if writer is None:
            writer = _FrameWriter(
                path, int(frames.shape[2]), int(frames.shape[1]), fps, crf=int(crf),
            )
        writer.write(frames)
        preview = frames[-1:].detach().cpu().contiguous()
        del frames
    if writer is not None:
        writer.close()
    return preview


def _u8_rgb(frames):
    return (frames[..., :3].detach().cpu().clamp(0, 1).numpy() * 255.0).astype(np.uint8)


def _rgb_to_torch(arr):
    return torch.from_numpy(np.ascontiguousarray(arr)).to(torch.float32).div_(255.0)


def _debug_label(detected, via_body, paste):
    if not detected:
        return "GAP"
    if float(paste) < 0.05:
        return "SKIP"
    if via_body:
        return "BODY"
    return "DET"


def _draw_debug_track(frames, xform, paste_w, strength, start_frame):
    """Source frames with crop box, face ellipse, and DET/GAP/SKIP labels."""
    import cv2

    rgb = _u8_rgb(frames)
    n, h, w = rgb.shape[:3]
    cw, ch = xform["canvas"]
    boxes = xform["boxes"]
    rects = list(xform.get("face_rect") or [])
    detected = list(xform.get("detected") or [True] * n)
    via_body = list(xform.get("via_body") or [False] * n)
    paste_w = np.asarray(paste_w, dtype=np.float64)
    strength = np.asarray(strength, dtype=np.float64)
    faces = _face_heights(xform)
    scale = max(h / 720.0, 0.7)
    thick = max(2, int(round(2 * scale)))
    font = cv2.FONT_HERSHEY_SIMPLEX
    out = np.empty_like(rgb)
    for i in range(n):
        bgr = cv2.cvtColor(rgb[i], cv2.COLOR_RGB2BGR)
        status = _debug_label(
            bool(detected[i]) if i < len(detected) else True,
            bool(via_body[i]) if i < len(via_body) else False,
            float(paste_w[i]) if i < paste_w.size else 1.0,
        )
        if status == "DET":
            face_bgr = (0, 220, 0)
        elif status == "BODY":
            face_bgr = (0, 220, 220)
        elif status == "SKIP":
            face_bgr = (180, 180, 180)
        else:
            face_bgr = (0, 0, 255)
        if i < len(boxes):
            x, y, bw, bh = (float(v) for v in boxes[i])
            cv2.rectangle(
                bgr, (int(round(x)), int(round(y))),
                (int(round(x + bw)), int(round(y + bh))), (220, 220, 0), thick,
            )
            if i < len(rects):
                sx, sy, sw, sh = canvas_rect_to_source(boxes[i], rects[i], cw, ch)
                cv2.ellipse(
                    bgr,
                    (int(round(sx + sw * 0.5)), int(round(sy + sh * 0.5))),
                    (max(1, int(round(sw * 0.5))), max(1, int(round(sh * 0.5)))),
                    0, 0, 360, face_bgr, thick, cv2.LINE_AA,
                )
        if status == "GAP":
            overlay = bgr.copy()
            cv2.rectangle(overlay, (0, 0), (w, int(48 * scale)), (0, 0, 180), -1)
            bgr = cv2.addWeighted(overlay, 0.45, bgr, 0.55, 0)
        pw = float(paste_w[i]) if i < paste_w.size else 0.0
        st = float(strength[i]) if i < strength.size else 0.0
        fh = float(faces[i]) if i < faces.size else 0.0
        text = (
            f"f{int(start_frame) + i} {status}  paste={pw:.2f}  str={st:.2f}  "
            f"face={fh:.0f}px"
        )
        cv2.putText(bgr, text, (12, int(28 * scale)), font, 0.55 * scale, (255, 255, 255), thick)
        cv2.putText(
            bgr, "CYAN=crop  GREEN=YOLO  YELLOW=body  RED=gap  GRAY=skip",
            (12, int(52 * scale)), font, 0.42 * scale, (220, 220, 220), max(1, thick - 1),
        )
        out[i] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return _rgb_to_torch(out)


def _draw_debug_mask(crops, xform, paste_w, strength):
    """Face-crop frames with inpaint ellipse (magenta) and H3 token mask (cyan)."""
    import cv2

    rgb = _u8_rgb(crops)
    n, ch, cw = rgb.shape[:3]
    rects = list(xform.get("face_rect") or [])
    detected = list(xform.get("detected") or [True] * n)
    via_body = list(xform.get("via_body") or [False] * n)
    paste_w = np.asarray(paste_w, dtype=np.float64)
    strength = np.asarray(strength, dtype=np.float64)
    ellipse = face_ellipse_mask(ch, cw, rects, dilation=FACE_INPAINT_DILATION)
    if ellipse.shape[0] != n:
        ellipse = ellipse[:n] if ellipse.shape[0] > n else np.pad(
            ellipse, ((0, n - ellipse.shape[0]), (0, 0), (0, 0)), mode="edge"
        )
    lh = max(1, ch // H3_SPATIAL)
    lw = max(1, cw // H3_SPATIAL)
    token = face_token_video_mask(
        ch, cw, rects, h3_latent_t(n), lh, lw,
        strength=strength, detected=detected, dilation=FACE_INPAINT_DILATION,
    )
    token_f = latent_mask_to_frames(token, n, ch, cw)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(ch / 768.0, 0.7)
    thick = max(2, int(round(2 * scale)))
    out = np.empty_like(rgb)
    mag = np.array([255, 0, 255], dtype=np.float32)
    cyan = np.array([0, 255, 255], dtype=np.float32)
    for i in range(n):
        frame = rgb[i].astype(np.float32)
        em = ellipse[i][..., None]
        tm = token_f[i][..., None]
        frame = frame * (1.0 - 0.40 * em) + mag * (0.40 * em)
        frame = frame * (1.0 - 0.35 * tm) + cyan * (0.35 * tm)
        bgr = cv2.cvtColor(np.clip(frame, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
        status = _debug_label(
            bool(detected[i]) if i < len(detected) else True,
            bool(via_body[i]) if i < len(via_body) else False,
            float(paste_w[i]) if i < paste_w.size else 1.0,
        )
        if status == "GAP":
            cv2.rectangle(bgr, (0, 0), (cw - 1, ch - 1), (0, 0, 255), thick + 2)
        elif status == "SKIP":
            cv2.rectangle(bgr, (0, 0), (cw - 1, ch - 1), (160, 160, 160), thick + 2)
        text = f"{status}  token={float(token_f[i].mean()) * 100:.0f}%"
        cv2.putText(bgr, text, (12, int(28 * scale)), font, 0.6 * scale, (255, 255, 255), thick)
        cv2.putText(
            bgr, "MAGENTA=face ellipse  CYAN=H3 tokens",
            (12, int(52 * scale)), font, 0.42 * scale, (220, 220, 220), max(1, thick - 1),
        )
        out[i] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return _rgb_to_torch(out)


def _write_debug_chunk(job_dir, index_1, src, xform, paste_w, strength, start_frame, fps, crf=18):
    track = _draw_debug_track(src, xform, paste_w, strength, start_frame)
    track_path = _debug_mp4(job_dir, "track", index_1)
    _write_frames_mp4(track_path, track, fps, crf)
    del track
    crops = crop_transform_frames(src, xform)
    mask = _draw_debug_mask(crops, xform, paste_w, strength)
    del crops
    mask_path = _debug_mp4(job_dir, "mask", index_1)
    _write_frames_mp4(mask_path, mask, fps, crf)
    del mask
    return track_path, mask_path


def _write_debug_concat(job_dir, n_chunks, chunks=None, overlap=0, fps=24.0, crf=18):
    """Concat debug clips on the committed timeline (drop Continue overlap)."""
    wrote = []
    spans = committed_file_spans(chunks, overlap) if chunks else None
    tmp_dir = os.path.join(job_dir, "_debug_concat_tmp")
    for kind in ("track", "mask"):
        parts = []
        temps = []
        for i in range(int(n_chunks)):
            p = _debug_mp4(job_dir, kind, i + 1)
            if not os.path.isfile(p):
                continue
            if spans is None or i >= len(spans):
                parts.append(p)
                continue
            packed_s, packed_e, ws, we, _kind = spans[i]
            n_file = _mp4_n_frames(p)
            sl = debug_file_slice(packed_s, packed_e, ws, we, n_file)
            if sl is None:
                continue
            off, count = sl
            if off == 0 and count == n_file:
                parts.append(p)
                continue
            os.makedirs(tmp_dir, exist_ok=True)
            tmp = os.path.join(tmp_dir, f"{kind}_{i + 1:03d}.mp4")
            if _trim_mp4(p, tmp, off, count, fps, crf) > 0:
                parts.append(tmp)
                temps.append(tmp)
        if len(parts) < 1:
            continue
        dest = os.path.join(job_dir, f"debug_{kind}.mp4")
        _concat_mp4s(parts, dest, drop_audio=True)
        wrote.append(dest)
        for tmp in temps:
            try:
                os.remove(tmp)
            except OSError:
                pass
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass
    return wrote


def _concat_mp4s(paths, out_path, drop_audio=False):
    if not paths:
        return
    if len(paths) == 1 and not drop_audio:
        shutil.copy2(paths[0], out_path)
        return
    list_path = out_path + ".concat.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in paths:
            ap = os.path.abspath(p).replace("\\", "/")
            f.write("file '" + ap.replace("'", "'\\''") + "'\n")
    try:
        cmd = [
            _ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:v", "copy",
        ]
        if drop_audio:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "copy"])
        cmd.append(out_path)
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0 or not os.path.isfile(out_path):
            raise RuntimeError(r.stderr[-2000:] if r.stderr else "concat failed")
    finally:
        if os.path.isfile(list_path):
            os.remove(list_path)


def _send_video_preview(unique_id, abs_path):
    if not unique_id or not abs_path or not os.path.isfile(abs_path):
        return None
    filename, subfolder, kind = _media_rel(abs_path)
    entry = {"filename": filename, "subfolder": subfolder, "type": kind}
    try:
        from server import PromptServer
        ps = PromptServer.instance
        ps.send_sync(
            "executed",
            {
                "node": unique_id,
                "display_node": unique_id,
                "output": {"images": [entry], "animated": (True,)},
                "prompt_id": getattr(ps, "last_prompt_id", None),
            },
            ps.client_id,
        )
    except Exception:
        pass
    return entry


def _delete_chunks_from(job_dir, first_index_0, n_chunks):
    for i in range(int(first_index_0), int(n_chunks)):
        for path in (
            _chunk_mp4(job_dir, i + 1),
            os.path.join(job_dir, f"chunk_{i + 1:03d}_preview.mp4"),
            _debug_mp4(job_dir, "track", i + 1),
            _debug_mp4(job_dir, "mask", i + 1),
        ):
            if os.path.isfile(path):
                os.remove(path)


def _existing_chunk_paths(job_dir, n_chunks):
    out = []
    for i in range(int(n_chunks)):
        p = _chunk_mp4(job_dir, i + 1)
        if not os.path.isfile(p):
            break
        out.append(p)
    return out


def _slice_transform(xform, start, end):
    keys = ("boxes", "weights", "detected", "face_rect", "via_body", "face_h", "face_w")
    out = dict(xform)
    for k in keys:
        if k in xform:
            out[k] = list(xform[k][start:end])
    out["frames"] = int(end - start)
    return out


def _pad_transform(xform, grid):
    n = int(xform["frames"])
    if n >= grid:
        return xform
    extra = grid - n
    out = dict(xform)
    for k in ("boxes", "weights", "detected", "face_rect", "via_body", "face_h", "face_w"):
        if k not in out or not out[k]:
            continue
        last = out[k][-1]
        out[k] = list(out[k]) + [last] * extra
    out["frames"] = grid
    return out


def _pad_images(images, grid):
    n = int(images.shape[0])
    if n >= grid:
        return images[:grid]
    extra = images[-1:].expand(grid - n, -1, -1, -1)
    return torch.cat((images, extra), dim=0)


def _face_heights(xform):
    if xform.get("face_h"):
        return np.array(xform["face_h"], dtype=np.float64)
    cf = float(xform.get("crop_factor", 2.5)) or 2.5
    return np.array([b[3] / cf for b in xform["boxes"]], dtype=np.float64)


def _bind_prompt(prompt, has_picture, has_audio):
    text = (prompt or "").strip() or _DEFAULT_PROMPT
    if has_picture:
        if "<Picture 1>" not in text:
            text = "the person in <Picture 1>, " + text
    else:
        text = text.replace("the person in <Picture 1>, ", "the same person, ")
        text = text.replace("<Picture 1>", "the subject")
    if has_audio:
        if "<Audio 1>" not in text:
            text = text.rstrip(" .,") + ", mouth following <Audio 1>"
    else:
        text = text.replace(", mouth following <Audio 1>", "")
        text = text.replace("mouth following <Audio 1>", "")
    return text


def _headshot_still(image, detector, confidence, crop_factor):
    """Crop <Picture 1> to a headshot so the still matches the face-crop canvas."""
    if image is None:
        return None
    frame = image[:1]
    try:
        model = _load_detector(detector)
        res = model.predict(_to_bgr_u8(frame[0]), conf=confidence, verbose=False)[0]
        boxes = res.boxes.xyxy.tolist() if len(res.boxes) else []
    except Exception as exc:
        _LOG.info("h3_facerefine: headshot ref unavailable (%s)", exc)
        return frame
    if not boxes:
        return frame
    b = max(boxes, key=lambda q: q[3] - q[1])
    h, w = int(frame.shape[1]), int(frame.shape[2])
    fh = float(b[3] - b[1])
    side = max(fh, float(b[2] - b[0])) * float(crop_factor)
    cx = (float(b[0]) + float(b[2])) * 0.5
    cy = (float(b[1]) + float(b[3])) * 0.5
    x = min(max(cx - side * 0.5, 0.0), max(0.0, w - side))
    y = min(max(cy - side * 0.5, 0.0), max(0.0, h - side))
    bw = min(side, float(w) - x)
    bh = min(side, float(h) - y)
    side = min(bw, bh)
    need = int(np.ceil(min(max(side, 256.0), 1024.0) / 32.0) * 32)
    crop = _affine_crop(frame, (x, y, side, side), need, need)
    _LOG.info("h3_facerefine: headshot ref %sx%s from still %sx%s", need, need, w, h)
    return crop


def _paste_locked_audio(av, audio_vae, audio):
    """Copy the chunk song into the target audio stream. Per-frame denoise then
    freezes it (audio noise_mask zeros). Same job as NativeAudioLock, inlined."""
    if audio is None:
        return av
    song, _t = _encode_ref_audio(audio_vae, audio)
    members = list(av["samples"].unbind())
    astream = members[1]
    if song.ndim == 3:
        song = song.unsqueeze(0)
    fitted = song.to(device=astream.device, dtype=astream.dtype)
    if int(fitted.shape[0]) == 1 and int(astream.shape[0]) != 1:
        fitted = fitted.expand(int(astream.shape[0]), *fitted.shape[1:])
    want = int(astream.shape[-1])
    have = int(fitted.shape[-1])
    if have < want:
        fitted = torch.cat(
            (fitted, fitted[..., -1:].expand(*fitted.shape[:-1], want - have)), dim=-1
        )
    elif have > want:
        fitted = fitted[..., :want]
    members[1] = fitted.contiguous()
    out = dict(av)
    out["samples"] = comfy.nested_tensor.NestedTensor(tuple(members))
    return out


def _overlap_latent_path(job_dir):
    return os.path.join(job_dir, "overlap_latent.pt")


def _save_overlap_latent(path, video):
    torch.save(video.detach().cpu().contiguous(), path)


def _load_overlap_latent(path):
    if not os.path.isfile(path):
        return None
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def _continue_overlap_frames(chunks, index):
    """Pixel overlap with the previous refine window, or 0."""
    index = int(index)
    if index <= 0 or index >= len(chunks):
        return 0
    prev = chunks[index - 1]
    cur = chunks[index]
    if len(prev) < 4 or len(cur) < 4:
        return 0
    if prev[3] != "refine" or cur[3] != "refine" or cur[0] >= prev[1]:
        return 0
    return min(int(prev[1] - cur[0]), int(cur[1] - cur[0]), int(prev[1] - prev[0]))


def _freeze_overlap_video(av, prev_video, overlap_frames, soft_steps=OVERLAP_SOFT_STEPS):
    """Copy previous tail video tokens onto this clip's head and freeze them.

    Returns ``(av, applied)``. ``applied`` is False when the copy was skipped.
    """
    if prev_video is None or int(overlap_frames) <= 0:
        return av, False
    samples = av.get("samples")
    if samples is None or not (
            isinstance(samples, comfy.nested_tensor.NestedTensor)
            or getattr(samples, "is_nested", False)):
        return av, False
    members = list(samples.unbind())
    video = members[0]
    ctx = h3_steps_covering(overlap_frames)
    ctx = min(ctx, int(video.shape[-3]) - 1, int(prev_video.shape[-3]))
    if ctx <= 0:
        return av, False
    src = prev_video[:, :, -ctx:].to(device=video.device, dtype=video.dtype)
    if tuple(src.shape[-2:]) != tuple(video.shape[-2:]):
        return av, False
    video = video.clone()
    video[:, :, :ctx] = src
    members[0] = video
    out = dict(av)
    out["samples"] = comfy.nested_tensor.NestedTensor(tuple(members))
    scale = overlap_freeze_scale(int(video.shape[-3]), ctx, soft_steps)
    nm = out.get("noise_mask")
    if nm is not None and (
            isinstance(nm, comfy.nested_tensor.NestedTensor)
            or getattr(nm, "is_nested", False)):
        masks = list(nm.unbind())
        vmask = masks[0]
        view = [1] * vmask.ndim
        view[-3] = int(scale.shape[0])
        scale_t = torch.from_numpy(scale).to(
            device=vmask.device, dtype=vmask.dtype
        ).view(*view)
        masks[0] = vmask * scale_t
        out["noise_mask"] = comfy.nested_tensor.NestedTensor(tuple(masks))
    return out, True


def _commit_chunk(frames, pending, overlap, is_last, dest=None, dest_start=0):
    """Hold ``overlap`` tail frames for the next Continue pass.

    The next clip's frozen head replaces the held tail, so pending is discarded
    rather than pixel-crossfaded.

    Returns ``(new_pending, written)``. ``written`` is the committed timeline
    slice for this chunk (empty if nothing to store yet).
    """
    frames = frames[..., :3]
    body = frames
    hold = 0 if is_last else min(int(overlap), int(body.shape[0]))
    written = body if hold <= 0 else body[:-hold]
    new_pending = None if hold <= 0 else body[-hold:].detach().cpu().contiguous()
    if dest is not None and written.shape[0]:
        dest[dest_start:dest_start + int(written.shape[0])] = written.to(
            device=dest.device, dtype=dest.dtype
        )
    return new_pending, written


def _slice_audio(audio, start_frame, n_frames, fps=FPS):
    if audio is None:
        return None
    waveform = audio["waveform"]
    sr = int(audio["sample_rate"])
    start = int(round(start_frame / float(fps) * sr))
    end = int(round((start_frame + n_frames) / float(fps) * sr))
    total = int(waveform.shape[-1])
    chunk = waveform[..., start:min(end, total)]
    want = max(0, end - start)
    if int(chunk.shape[-1]) < want:
        pad = want - int(chunk.shape[-1])
        zeros = torch.zeros(*chunk.shape[:-1], pad, dtype=chunk.dtype, device=chunk.device)
        chunk = torch.cat((chunk, zeros), dim=-1)
    return {"waveform": chunk, "sample_rate": sr}


def _sample_segment(model, positive, sampler, sigmas, noise, latent):
    guider = Guider_Basic(model)
    guider.set_conds(positive)
    latent = dict(latent)
    latent_image = comfy.sample.fix_empty_latent_channels(
        guider.model_patcher, latent["samples"],
        latent.get("downscale_ratio_spacial", None),
        latent.get("downscale_ratio_temporal", None),
    )
    latent["samples"] = latent_image
    callback = latent_preview.prepare_callback(
        guider.model_patcher, sigmas.shape[-1] - 1, {}
    )
    samples = guider.sample(
        noise.generate_noise(latent), latent_image, sampler, sigmas,
        denoise_mask=latent.get("noise_mask"),
        callback=callback,
        disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
        seed=getattr(noise, "seed", None),
    )
    out = dict(latent)
    out.pop("downscale_ratio_spacial", None)
    out.pop("downscale_ratio_temporal", None)
    out["samples"] = samples.to(comfy.model_management.intermediate_device())
    return out


def _decode_video(vae, latent):
    video = list(latent["samples"].unbind())[0]
    images = vae.decode(video)
    if images.ndim == 5:
        images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
    return images


class H3StudioFaceRefineVideo:
    """Track a full clip, inpaint the face tokens, stitch back."""

    @classmethod
    def INPUT_TYPES(cls):
        from ..png_sequence import save_images_to_disk_spec
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE", {
                    "tooltip": "MiniMax H3 Video VAE.",
                }),
                "audio_vae": ("VAE", {
                    "tooltip": "MiniMax H3 Audio VAE. Required by Ref2VA even if audio is omitted.",
                }),
                "sampler": ("SAMPLER",),
                "sigmas": ("SIGMAS", {
                    "tooltip": "From BasicScheduler. Example workflows use denoise 0.45 at 4 turbo steps.",
                }),
                "noise": ("NOISE",),
                "prompt": ("STRING", {
                    "multiline": True, "dynamicPrompts": False, "default": _DEFAULT_PROMPT,
                    "tooltip": "Face-crop identity prompt. Names <Picture 1> and <Audio 1>. "
                               "Do not paste lyrics or the music-video scene.",
                }),
                "detector": (_detector_list(),),
                "chunk_duration": ("FLOAT", {
                    "default": 10.0, "min": 1.0, "max": 15.0, "step": 0.1,
                    "tooltip": "Maximum seconds per H3 pass at 24 fps (snaps to the 17k+5 grid). "
                               "Passes are packed shorter when only part of the clip needs paste. "
                               "Lower this if a pass OOMs.",
                }),
                "skip_closeup_frac": ("FLOAT", {
                    "default": 0.28, "min": 0.05, "max": 0.9, "step": 0.01,
                    "tooltip": "Paste fully original when face height reaches this fraction of the frame. "
                               "Ramps from 0.06 below that so mixed shots do not pop. "
                               "0.28 is a medium-close; talking-head close-ups stay original.",
                }),
                "confidence": ("FLOAT", {"default": 0.35, "min": 0.05, "max": 0.95, "step": 0.05}),
                "crop_factor": ("FLOAT", {"default": 2.5, "min": 1.2, "max": 8.0, "step": 0.1}),
                "canvas_mode": (["auto_capped_768", "manual", "auto_no_downscale"], {
                    "default": "auto_capped_768",
                }),
                "canvas_width": ("INT", {"default": 512, "min": 128, "max": 1344, "step": 32}),
                "canvas_height": ("INT", {"default": 512, "min": 128, "max": 1344, "step": 32}),
                "feather": ("INT", {"default": 24, "min": 0, "max": 256, "step": 2,
                    "tooltip": "Stitch feather in source pixels. 24 suits the rect paste mask."}),
                "detail_match": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Soften H3's extra sharpness to match the footage around the face. "
                               "Does not copy original face pixels. 0 keeps H3's extra crunch."}),
                "save_images_to_disk": save_images_to_disk_spec(),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "IMAGE batch from Auto Chain / Music Video. Used whenever this "
                               "socket is connected, even if video_path is also set.",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "tooltip": "Path to a PNG folder (preferred) or MP4. Auto Chain / Music Video "
                               "write the sequence under ComfyUI temp. Reading PNG avoids decoding H.264. "
                               "Absolute, or under ComfyUI/input. One H3 chunk at a time; "
                               "IMAGE is loaded from disk or kept in RAM per save_images_to_disk.",
                }),
                "start_chunk": ("INT", {
                    "default": 0, "min": 0, "max": 10000, "step": 1,
                    "tooltip": "1-based chunk to start at. 0 = resume after the last finished chunk "
                               "in the job folder (or 1 if none).",
                }),
                "end_chunk": ("INT", {
                    "default": 0, "min": 0, "max": 10000, "step": 1,
                    "tooltip": "1-based chunk to stop at (inclusive). 0 = last chunk. "
                               "Stop early to preview; resume later with start_chunk 0.",
                }),
                "audio": ("AUDIO", {
                    "tooltip": "Master song for H3 <Audio 1> / audio lock. Optional when video_path "
                               "is a muxed MP4, or a PNG folder next to that MP4. Soundtrack is "
                               "taken from the file for H3 and for saved clips.",
                }),
                "reference_image": ("IMAGE", {
                    "tooltip": "Identity still. Cropped to a headshot for Ref2VA <Picture 1>. "
                               "Use the same Picture 1 as the music video.",
                }),
                "strength_small_face": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Denoise multiplier on the smallest faces (full BasicScheduler denoise, "
                               "applied to face tokens only). Raise scheduler denoise to 0.55-0.7 "
                               "if mouths still barely move."}),
                "strength_large_face": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Denoise multiplier on large-face frames inside a mixed chunk. "
                               "0 = do not rewrite close-ups even if the chunk ran H3."}),
                "debug_videos": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Write debug_track_###.mp4 (detection/gaps on the source) and "
                               "debug_mask_###.mp4 (inpaint ellipse + H3 token mask on the crop). "
                               "Concatenated to debug_track.mp4 / debug_mask.mp4 when every chunk exists.",
                }),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "report")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "H3 Studio"
    DESCRIPTION = NODE_HELP["H3StudioFaceRefineVideo"]

    def run(self, model, clip, vae, audio_vae, sampler, sigmas, noise, prompt,
            detector, chunk_duration, skip_closeup_frac, confidence, crop_factor,
            canvas_mode, canvas_width, canvas_height, feather, detail_match=1.0,
            save_images_to_disk=False,
            images=None, audio=None,
            reference_image=None, strength_small_face=1.0, strength_large_face=0.0,
            video_path="", start_chunk=0, end_chunk=0, debug_videos=False, unique_id=None):
        video_path = str(video_path or "").strip()
        save_images_to_disk = bool(save_images_to_disk)
        source = None
        file_mode = False
        fps = float(FPS)
        preview = None
        png_dir = ""
        write_png_dir = None
        ram_dest = None
        ui_preview = None
        notes = []
        n = 0
        canvas_w = canvas_h = 0
        refined_n = skipped_n = 0
        try:
            if images is not None:
                source = images[..., :3]
                n = int(source.shape[0])
                src_h = int(source.shape[1])
                src_w = int(source.shape[2])
            elif video_path:
                file_mode = True
                source = _open_source(video_path)
                n = int(source.n)
                src_h = int(source.h)
                src_w = int(source.w)
                fps = float(source.fps) or FPS
            else:
                raise ValueError(
                    "h3_facerefine: set video_path to the Music Video PNG folder or MP4, "
                    "or connect a short IMAGE clip."
                )
            from ..png_sequence import require_image_ram, warn_disk_budget
            require_image_ram(n, src_w, src_h, save_images_to_disk)
            if save_images_to_disk:
                warn_disk_budget(
                    n, src_w, src_h, unique_id=unique_id,
                    extra=f"Face Refine: {n} frames at source resolution",
                )
            max_chunk = align_h3_frames(int(round(float(chunk_duration) * FPS)))
            overlap = CHUNK_OVERLAP if max_chunk > CHUNK_OVERLAP else 0
            px_small, px_large = denoise_px_range(src_h, skip_closeup_frac)
            source_path = os.path.abspath(source.path) if file_mode else ""
            source_fp = _source_fingerprint(
                n, src_w, src_h, images=None if file_mode else source, path=source_path,
            )
            source_label = video_path if file_mode else "image_batch"
            job_dir = _job_dir(source_label, source_fp)
            state_path = os.path.join(job_dir, "state.json")
            xform_path = os.path.join(job_dir, "xform.json")
            pending_path = os.path.join(job_dir, "pending.npy")
            overlap_path = _overlap_latent_path(job_dir)
            png_dir = _job_frames_dir(job_dir)
            write_png_dir = png_dir if save_images_to_disk else None
            if isinstance(source, _VideoFrames):
                source_media = os.path.abspath(source.path)
            elif isinstance(source, _ImageSeqFrames):
                source_media = _audio_sidecar(source.path)
            else:
                source_media = None
            fp = {
                "n": int(n),
                "detector": str(detector),
                "confidence": round(float(confidence), 5),
                "crop_factor": round(float(crop_factor), 5),
                "canvas_mode": str(canvas_mode),
                "canvas_width": int(canvas_width),
                "canvas_height": int(canvas_height),
                "max_chunk": int(max_chunk),
                "overlap": int(overlap),
                "source": source_path if file_mode else "image_batch",
                "source_fp": source_fp,
                "inpaint": "face",
                "crop_plan": "face_follow",
                "crop_aspect": "canvas",
                "crop_lock": "causal_scale",
                "chunk_pack": "shot_hull",
                "write_span": "committed",
                "skip_closeup_frac": round(float(skip_closeup_frac), 5),
                "min_visible_sec": float(MIN_VISIBLE_SEC),
            }
            state = _load_json(state_path, {}) or {}
            track_keys = (
                "n", "detector", "confidence", "crop_factor", "canvas_mode",
                "canvas_width", "canvas_height", "source", "source_fp", "inpaint",
                "crop_plan", "crop_aspect", "crop_lock",
            )
            track_ok = all(state.get(k) == fp[k] for k in track_keys)
            fp_ok = all(state.get(k) == v for k, v in fp.items())

            xform = _load_xform(xform_path) if track_ok else None
            track_report = "tracking: loaded from job folder"
            if xform is not None:
                canvas_w, canvas_h = (int(v) for v in xform["canvas"])
                notes.append(f"resumed tracking from {xform_path}")
            else:
                _progress(unique_id, f"Tracking faces on {n} frames")
                tracker = H3FaceTrackCrop()
                _crops, xform, _preview, track_report, canvas_w, canvas_h = tracker.run(
                    source, detector, confidence, crop_factor, canvas_width, canvas_height,
                    canvas_mode, 21, 51, "gaussian", "per_frame",
                    identity_reference=reference_image, identity_track=True,
                    build_crops=False,
                )
                del _crops, _preview
                _save_xform(xform_path, xform)
                _release_loaded_models()

            face_all = _face_heights(xform)
            detected_all = np.array(
                xform.get("detected") or [True] * int(face_all.size), dtype=bool,
            )
            sampleable_all = sustained_visible(detected_all, fps, MIN_VISIBLE_SEC)
            if int(sampleable_all.size) < n:
                extra = np.zeros(n - int(sampleable_all.size), dtype=bool)
                sampleable_all = np.concatenate([sampleable_all, extra])
            elif int(sampleable_all.size) > n:
                sampleable_all = sampleable_all[:n]
            strength_all = per_frame_strength(
                face_all, px_small, px_large,
                float(strength_small_face), float(strength_large_face),
            )
            paste_all = refine_paste_weight(
                face_all, src_h, skip_closeup_frac,
                float(xform.get("crop_factor", crop_factor)),
                canvas_h, strength_all,
            )
            need = (paste_all >= 0.05) & sampleable_all[: paste_all.size]
            if int(need.size) < n:
                extra = np.zeros(n - int(need.size), dtype=bool)
                need = np.concatenate([need, extra])
            elif int(need.size) > n:
                need = need[:n]
            pack_src = xform.get("src_size") or (src_w, src_h)
            pack_breaks = _maskvid_pack_breaks(
                xform, n, int(pack_src[0]), int(pack_src[1]),
            )
            chunks = pack_refine_chunks(
                need, n, max_chunk, overlap=overlap, breaks=pack_breaks,
            )
            n_refine = sum(1 for c in chunks if c[3] == "refine")
            n_copy = sum(1 for c in chunks if c[3] == "copy")
            sampled_n = int(np.asarray(need).sum())
            brief_n = int(detected_all.sum()) - int(sampleable_all.sum())
            uniform_n = len(chunk_ranges(n, max_chunk, overlap=overlap))
            n_mv = int(np.asarray(pack_breaks).sum()) if pack_breaks is not None else 0
            pack_line = (
                f"packed {n_refine} H3 passes (max {max_chunk}f / {float(chunk_duration):g}s); "
                f"{sampled_n}/{n} frames need paste, {n_copy} copy spans streamed; "
                f"{n_mv} MaskVid teleports; uniform {max_chunk}f grid would be {uniform_n} passes"
            )
            if brief_n > 0:
                pack_line += (
                    f"; skipped {brief_n} brief-face frames "
                    f"(<{float(MIN_VISIBLE_SEC):g}s uninterrupted)"
                )
            print(f"[H3FaceRefine] {pack_line}")
            _LOG.info("h3_facerefine: %s", pack_line)
            _progress(unique_id, pack_line)
            first, last = select_chunk_span(
                len(chunks), start_chunk, end_chunk,
                completed_chunk=(
                    int(state.get("completed_chunk", 0))
                    if fp_ok and save_images_to_disk else 0
                ),
            )
            if not save_images_to_disk and first > 0:
                raise RuntimeError(
                    "h3_facerefine: RAM mode cannot resume from chunk "
                    f"{first + 1}. Enable save_images_to_disk, or set start_chunk to 1."
                )

            injector = H3InjectVideoLatent()
            denoiser = H3PerFrameDenoise()
            stitcher = H3FaceStitch()
            picture_ref = _headshot_still(
                reference_image, detector, confidence, crop_factor,
            )
            if audio is None and source_media:
                try:
                    audio = _audio_from_video(
                        source_media, os.path.join(job_dir, "source_audio.wav"),
                    )
                    audio_note = "loaded AUDIO from source MP4"
                except Exception as exc:
                    audio_note = f"could not load AUDIO from source MP4: {exc}"
            else:
                audio_note = None
            ref_images = {"ref_image_1": picture_ref} if picture_ref is not None else None
            prompt = _bind_prompt(prompt, picture_ref is not None, audio is not None)
            notes = [
                track_report.strip(),
                f"job={job_dir}",
                f"files={len(chunks)} ({n_refine} H3 / {n_copy} copy)  "
                f"doing {first + 1}-{last + 1}  "
                f"max={max_chunk}f  overlap={overlap}f  "
                f"skip_frac={skip_closeup_frac:g}  ramp={CLOSEUP_RAMP:g}",
                pack_line,
                f"denoise {px_small:.0f}-{px_large:.0f}px  gamma={DENOISE_GAMMA:g}  "
                f"(small faces keep full scheduler denoise)",
                "face-token inpaint (full face, crop context frozen, audio frozen)",
            ]
            if audio_note:
                notes.append(audio_note)
            if picture_ref is not None:
                notes.append(
                    f"headshot ref {int(picture_ref.shape[2])}x{int(picture_ref.shape[1])}  "
                    f"ref_image_size=max"
                )
            if audio is not None:
                notes.append("audio lock on (target stream frozen + <Audio 1> ref)")
            notes.append(
                f"png frames {png_dir}" if save_images_to_disk else "IMAGE kept in RAM"
            )
            if debug_videos:
                notes.append("debug videos on (debug_track_### / debug_mask_###)")

            if first > last:
                notes.append("nothing to do (already complete for this range)")
                parts = _existing_chunk_paths(job_dir, len(chunks))
                if parts:
                    ui_preview = _send_video_preview(unique_id, parts[-1])
            else:
                _delete_chunks_from(job_dir, first, len(chunks))
                if write_png_dir:
                    _delete_png_from(write_png_dir, int(chunks[first][0]), n)
                    os.makedirs(write_png_dir, exist_ok=True)
                    with open(os.path.join(write_png_dir, "fps.txt"), "w", encoding="utf-8") as f:
                        f.write(f"{float(fps):g}\n")
                else:
                    ram_dest = torch.empty((n, src_h, src_w, 3), dtype=torch.float32)
                if first == 0:
                    pending = None
                    if os.path.isfile(pending_path):
                        os.remove(pending_path)
                    if os.path.isfile(overlap_path):
                        os.remove(overlap_path)
                else:
                    pending = _load_pending(pending_path)
                    ov_lat = _overlap_latent_path(job_dir)
                    if _continue_overlap_frames(chunks, first) and not os.path.isfile(ov_lat):
                        notes.append(
                            f"no overlap latent at chunk {first + 1}; this pass starts fresh"
                        )
                committed_cursor = int(chunks[first][0])
                h3_i = sum(1 for c in chunks[:first] if c[3] == "refine")

                def finish_chunk(ci, chunk_path, start_frame, n_frames):
                    nonlocal ui_preview
                    if n_frames > 0 and chunk_path and os.path.isfile(chunk_path):
                        ui_preview = _send_video_preview(unique_id, chunk_path)
                    if pending is not None:
                        _save_pending(pending_path, pending)
                    elif os.path.isfile(pending_path):
                        os.remove(pending_path)
                    saved = dict(fp)
                    saved["completed_chunk"] = ci + 1
                    saved["committed_end"] = int(start_frame) + int(n_frames)
                    saved["canvas_w"] = int(canvas_w)
                    saved["canvas_h"] = int(canvas_h)
                    _save_json(state_path, saved)

                for ci in range(first, last + 1):
                    comfy.model_management.throw_exception_if_processing_interrupted()
                    start, end, grid, kind = chunks[ci]
                    source_last = ci == len(chunks) - 1
                    hold = segment_hold(chunks, ci, overlap)
                    commit_start = committed_cursor
                    chunk_path = _chunk_mp4(job_dir, ci + 1)

                    if kind == "copy":
                        skipped_n += 1
                        write_start, write_end = committed_write_span(
                            start, end, committed_cursor, hold=0, is_last=True,
                        )
                        _progress(
                            unique_id,
                            f"Copy {write_start}-{write_end} ({write_end - write_start}f)  "
                            f"file {ci + 1}/{len(chunks)}",
                        )
                        preview = _write_source_range(
                            chunk_path, source, write_start, write_end, fps,
                            dest=ram_dest, png_dir=write_png_dir,
                        )
                        notes.append(
                            f"file {ci + 1} {write_start}-{write_end} copy "
                            f"({write_end - write_start}f)"
                        )
                        _LOG.info(
                            "h3_facerefine: copy %s frames %s-%s",
                            ci + 1, write_start, write_end,
                        )
                        n_written = write_end - write_start
                        finish_chunk(
                            ci, chunk_path if n_written else None, write_start, n_written,
                        )
                        committed_cursor = max(committed_cursor, write_end, end)
                        if os.path.isfile(overlap_path):
                            os.remove(overlap_path)
                        continue

                    sl = _slice_transform(xform, start, end)
                    face = _face_heights(sl)
                    detected = sampleable_all[start:end]
                    strength = per_frame_strength(
                        face, px_small, px_large,
                        float(strength_small_face), float(strength_large_face),
                    )
                    paste_w = refine_paste_weight(
                        face, src_h, skip_closeup_frac,
                        float(xform.get("crop_factor", crop_factor)),
                        canvas_h, strength,
                    )
                    src = source[start:end]
                    if chunk_is_all_closeup(paste_w, detected):
                        skipped_n += 1
                        del src
                        write_start, write_end = committed_write_span(
                            start, end, committed_cursor, hold=0, is_last=True,
                        )
                        preview = _write_source_range(
                            chunk_path, source, write_start, write_end, fps,
                            dest=ram_dest, png_dir=write_png_dir,
                        )
                        notes.append(
                            f"file {ci + 1} {write_start}-{write_end} copy (close-up / no face)"
                        )
                        _LOG.info(
                            "h3_facerefine: copy %s frames %s-%s",
                            ci + 1, write_start, write_end,
                        )
                        n_written = write_end - write_start
                        finish_chunk(
                            ci, chunk_path if n_written else None, write_start, n_written,
                        )
                        committed_cursor = max(committed_cursor, write_end, end)
                        if os.path.isfile(overlap_path):
                            os.remove(overlap_path)
                        continue

                    write_start, write_end = committed_write_span(
                        start, end, committed_cursor, hold, source_last,
                    )
                    dbg_skip = max(0, write_start - start)
                    dbg_take = max(0, write_end - write_start)
                    if debug_videos and dbg_take > 0:
                        try:
                            sl_dbg = _slice_transform(xform, write_start, write_end)
                            tpath, mpath = _write_debug_chunk(
                                job_dir, ci + 1,
                                src[dbg_skip:dbg_skip + dbg_take], sl_dbg,
                                paste_w[dbg_skip:dbg_skip + dbg_take],
                                strength[dbg_skip:dbg_skip + dbg_take],
                                write_start, fps,
                            )
                            notes.append(
                                f"file {ci + 1} debug {os.path.basename(tpath)} "
                                f"{os.path.basename(mpath)}"
                            )
                        except Exception as exc:
                            notes.append(f"file {ci + 1} debug failed: {exc}")
                            print(f"[H3FaceRefine] debug failed: {exc}")

                    pad_sl = _pad_transform(sl, grid)
                    pw = np.asarray(paste_w, dtype=np.float64)
                    if int(pw.size) < grid:
                        pw = np.pad(pw, (0, grid - int(pw.size)), mode="edge")
                    wt = np.array(pad_sl.get("weights") or [1.0] * grid, dtype=np.float64)
                    if int(wt.size) < grid:
                        wt = np.pad(wt, (0, grid - int(wt.size)), mode="edge")
                    pad_sl["weights"] = [
                        float(a) * float(b) for a, b in zip(wt[:grid], pw[:grid])
                    ]
                    pad_crops = _pad_images(crop_transform_frames(src, sl), grid)
                    pad_audio = _slice_audio(audio, start, grid, fps=fps)
                    h3_i += 1
                    _progress(
                        unique_id,
                        f"H3 pass {h3_i}/{n_refine} frames {start}-{end} ({grid} H3)",
                    )

                    _release_loaded_models()
                    ref_audios = {"ref_audio_1": pad_audio} if pad_audio is not None else None
                    built = MiniMaxH3ReferenceToVideo.execute(
                        clip, vae, audio_vae, prompt, int(canvas_w), int(canvas_h), int(grid),
                        ref_image_size="max", ref_images=ref_images, ref_audios=ref_audios,
                    )
                    positive, empty = built[0], built[1]
                    _release_loaded_models()

                    av, _inj = injector.run(empty, pad_crops, vae)
                    del empty, pad_crops
                    av = _paste_locked_audio(av, audio_vae, pad_audio)
                    av, _dn = denoiser.run(
                        av, pad_sl, float(strength_small_face), float(strength_large_face),
                        float(px_small), float(px_large), float(DENOISE_GAMMA), 9,
                        scale_mode="absolute_px",
                    )
                    ctx_frames = _continue_overlap_frames(chunks, ci)
                    if ctx_frames:
                        prev_video = _load_overlap_latent(overlap_path)
                        if prev_video is not None:
                            av, froze = _freeze_overlap_video(av, prev_video, ctx_frames)
                            if froze:
                                notes.append(
                                    f"file {ci + 1} Continue freeze {ctx_frames}f "
                                    f"({h3_steps_covering(ctx_frames)} latent steps)"
                                )
                            else:
                                notes.append(
                                    f"file {ci + 1} Continue skip "
                                    f"(overlap {ctx_frames}f, latent mismatch)"
                                )
                            del prev_video
                        else:
                            notes.append(
                                f"file {ci + 1} Continue skip "
                                f"(overlap {ctx_frames}f, no overlap latent)"
                            )
                    _release_loaded_models()
                    sampled = _sample_segment(model, positive, sampler, sigmas, noise, av)
                    del positive, av
                    last_lat = dict(sampled)
                    video, audio_lat = list(sampled["samples"].unbind())
                    last_lat["samples"] = comfy.nested_tensor.NestedTensor((
                        video.detach().cpu().contiguous(),
                        audio_lat.detach().cpu().contiguous(),
                    ))
                    del sampled, video, audio_lat
                    if hold:
                        _save_overlap_latent(
                            overlap_path, list(last_lat["samples"].unbind())[0],
                        )
                    elif os.path.isfile(overlap_path):
                        os.remove(overlap_path)
                    _release_loaded_models()

                    refined = _decode_video(vae, last_lat)
                    del last_lat
                    _release_loaded_models()
                    refined = refined[: end - start].to(device=src.device, dtype=src.dtype)

                    paste_sl = dict(sl)
                    paste_sl["detected"] = [bool(v) for v in detected.tolist()]
                    det_w = list(paste_sl.get("weights") or [1.0] * (end - start))
                    paste_sl["weights"] = [
                        float(w) * float(pw) for w, pw in zip(det_w, paste_w.tolist())
                    ]

                    stitched = stitcher.run(
                        src, refined, paste_sl, "face_only", 16, int(feather),
                        1.0, 1.0, float(detail_match), undetected_frames="fade_out",
                    )[0]
                    del refined
                    skip = write_start - start
                    take = write_end - write_start
                    if take > 0:
                        pending, written = _commit_chunk(
                            stitched[skip:skip + take], pending, 0, True,
                            ram_dest, write_start,
                        )
                    else:
                        pending, written = None, stitched[:0]
                    del src, stitched
                    n_written = int(written.shape[0]) if written is not None else 0
                    if n_written:
                        _write_frames_mp4(chunk_path, written, fps)
                        if write_png_dir:
                            _write_png_range(write_png_dir, write_start, written)
                        preview = written[-1:].detach().cpu().contiguous()
                    finish_chunk(
                        ci, chunk_path if n_written else None, write_start, n_written,
                    )
                    committed_cursor = max(committed_cursor, write_end)
                    del written
                    refined_n += 1
                    notes.append(
                        f"file {ci + 1} H3 packed {start}-{end} write {write_start}-{write_end} "
                        f"({grid}f) "
                        f"({int(detected.sum())} faces, paste mean {float(paste_w.mean()):.2f}, "
                        f"denoise mean {float(strength.mean()):.2f}, face-token inpaint)"
                    )
                    _LOG.info(
                        "h3_facerefine: H3 pass %s/%s frames %s-%s grid %s",
                        h3_i, n_refine, start, end, grid,
                    )
                    gc.collect()


            if debug_videos:
                try:
                    for p in _write_debug_concat(
                        job_dir, len(chunks), chunks, overlap, fps,
                    ):
                        notes.append(f"wrote {p}")
                except Exception as exc:
                    notes.append(f"debug concat failed: {exc}")
                    print(f"[H3FaceRefine] debug concat failed: {exc}")
        finally:
            close = getattr(source, "close", None)
            if callable(close):
                close()

        from ..png_sequence import load_png_sequence, pack_image_output, png_count
        if write_png_dir and png_count(write_png_dir) > 0:
            result_images = load_png_sequence(write_png_dir)
        elif ram_dest is not None:
            result_images = ram_dest
        elif images is not None and not file_mode:
            result_images = images[..., :3]
        else:
            result_images = preview if preview is not None else torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        report = (
            f"h3_face_refine_video: {n} frames | {refined_n} refined | {skipped_n} skipped | "
            f"canvas {canvas_w}x{canvas_h}"
            + (f" | png {write_png_dir}" if write_png_dir else " | RAM")
            + "\n" + "\n".join(notes)
        )
        print("[H3FaceRefine] " + report.replace("\n", "\n[H3FaceRefine] "))
        if write_png_dir and png_count(write_png_dir) > 0:
            return pack_image_output(result_images, write_png_dir, report)
        if ui_preview is not None:
            return {
                "ui": {"images": [ui_preview], "animated": (True,)},
                "result": (result_images, report),
            }
        return pack_image_output(result_images, None, report)

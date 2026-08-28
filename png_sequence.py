"""Lossless PNG timelines in ComfyUI temp, plus a first-thing disk/RAM warning."""

from __future__ import annotations

import logging
import os
import shutil

import numpy as np
import torch
from PIL import Image

from .latent_math import FPS

_LOG = logging.getLogger("h3_continuous")

PNG_RGB_BYTES = 3
IMAGE_FLOAT32_BYTES = 12
RAM_OVERHEAD_BYTES = 2 * 1024 ** 3
_pinned_budget = {}


def estimate_png_bytes(n_frames: int, width: int, height: int) -> int:
    return int(n_frames) * int(width) * int(height) * PNG_RGB_BYTES


def estimate_image_ram_bytes(n_frames: int, width: int, height: int) -> int:
    return int(n_frames) * int(width) * int(height) * IMAGE_FLOAT32_BYTES


def format_bytes(n: int) -> str:
    n = max(0, int(n))
    if n >= 1024 ** 3:
        return f"{n / (1024 ** 3):.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / (1024 ** 2):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def disk_budget_message(n_frames: int, width: int, height: int, temp_dir: str = "",
                        free_bytes: int | None = None) -> str:
    n_frames = int(n_frames)
    width = int(width)
    height = int(height)
    disk = estimate_png_bytes(n_frames, width, height)
    ram = estimate_image_ram_bytes(n_frames, width, height)
    lines = [
        "",
        "!" * 72,
        "H3 STUDIO — PNG DISK / IMAGE RAM",
        f"  {n_frames} frames at {width}x{height}",
        f"  PNG sequence (uncompressed RGB ceiling): {format_bytes(disk)}",
        f"  IMAGE output (float32): {format_bytes(ram)}",
    ]
    if temp_dir:
        lines.append(f"  temp: {temp_dir}")
    if free_bytes is not None:
        lines.append(f"  free on that volume: {format_bytes(free_bytes)}")
        if int(free_bytes) < disk:
            lines.append(
                f"  NOT ENOUGH FREE SPACE — need about {format_bytes(disk)}, "
                f"have {format_bytes(free_bytes)}"
            )
    lines.append("!" * 72)
    lines.append("")
    return "\n".join(lines)


def budget_progress_line(n_frames: int, width: int, height: int) -> str:
    disk = format_bytes(estimate_png_bytes(n_frames, width, height))
    ram = format_bytes(estimate_image_ram_bytes(n_frames, width, height))
    return (
        f"PNG ~{disk} | IMAGE RAM ~{ram} | {int(n_frames)}f {int(width)}x{int(height)}"
    )


def pin_disk_budget(unique_id, line: str):
    if unique_id:
        _pinned_budget[str(unique_id)] = str(line or "")


def progress_display(unique_id, status=""):
    budget = _pinned_budget.get(str(unique_id), "") if unique_id else ""
    parts = [p for p in (budget, str(status or "").strip()) if p]
    return "\n".join(parts)


def send_node_progress(unique_id, status=""):
    if not unique_id:
        return
    text = progress_display(unique_id, status)
    if not text:
        return
    try:
        from server import PromptServer
        PromptServer.instance.send_progress_text(text, unique_id)
    except Exception:
        pass


def available_ram_bytes() -> int:
    import psutil
    return int(psutil.virtual_memory().available)


def save_images_to_disk_spec():
    return ("BOOLEAN", {
        "default": False,
        "tooltip": (
            "Save the IMAGE as a PNG sequence in ComfyUI temp and load that sequence "
            "for the IMAGE output. Off keeps frames in RAM only. Off errors before work "
            "if the IMAGE would not fit in free RAM."
        ),
    })


def require_image_ram(n_frames: int, width: int, height: int, save_to_disk=False):
    """Abort RAM-only runs before work when the IMAGE tensor cannot fit."""
    if save_to_disk:
        return
    need = estimate_image_ram_bytes(n_frames, width, height)
    extra = max(RAM_OVERHEAD_BYTES, int(need * 0.15))
    avail = available_ram_bytes()
    if need + extra <= avail:
        return
    raise RuntimeError(
        f"h3_studio: IMAGE would need {format_bytes(need)} RAM "
        f"({int(n_frames)} frames at {int(width)}x{int(height)}), "
        f"only {format_bytes(avail)} free. Enable save_images_to_disk."
    )


def pack_image_output(images, frames_dir=None, *rest):
    return {"result": (images,) + rest}


def warn_disk_budget(n_frames: int, width: int, height: int, unique_id=None, extra: str = ""):
    import folder_paths

    temp_dir = folder_paths.get_temp_directory()
    free_bytes = None
    try:
        free_bytes = int(shutil.disk_usage(temp_dir).free)
    except OSError:
        pass
    extra_line = str(extra or "").strip()
    text = disk_budget_message(n_frames, width, height, temp_dir=temp_dir, free_bytes=free_bytes)
    if extra_line:
        text = text.replace("!" * 72 + "\n", f"  {extra_line}\n" + "!" * 72 + "\n", 1)
    line = budget_progress_line(n_frames, width, height)
    pin_disk_budget(unique_id, line)
    print(text, flush=True)
    _LOG.warning("%s", text.strip())
    send_node_progress(unique_id, extra_line)
    return line


def png_frame_path(frames_dir: str, index: int) -> str:
    return os.path.join(frames_dir, f"{int(index):08d}.png")


def png_count(frames_dir: str) -> int:
    n = 0
    while os.path.isfile(png_frame_path(frames_dir, n)):
        n += 1
    return n


def write_frames_fps(frames_dir: str, fps: float = FPS) -> None:
    os.makedirs(frames_dir, exist_ok=True)
    with open(os.path.join(frames_dir, "fps.txt"), "w", encoding="utf-8") as f:
        f.write(f"{float(fps):g}\n")


def save_png_frame(frames_dir: str, index: int, rgb_u8) -> None:
    os.makedirs(frames_dir, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(rgb_u8), "RGB").save(
        png_frame_path(frames_dir, index), compress_level=1,
    )


def unique_temp_frames_dir(filename_prefix: str) -> str:
    import folder_paths

    folder, filename, counter, _, _ = folder_paths.get_save_image_path(
        filename_prefix, folder_paths.get_temp_directory()
    )
    os.makedirs(folder, exist_ok=True)
    while True:
        path = os.path.join(folder, f"{filename}_{int(counter):05d}_frames")
        if not os.path.exists(path):
            write_frames_fps(path, FPS)
            return path
        counter += 1


def _safe_dir_component(value) -> str:
    text = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(value or "run"))
    return (text.strip("_") or "run")[:80]


def node_temp_frames_dir(filename_prefix: str, unique_id=None) -> str:
    """Stable per-node PNG folder in temp. Wiped at the start of each run."""
    import folder_paths

    if not unique_id:
        return unique_temp_frames_dir(filename_prefix)
    root = os.path.abspath(folder_paths.get_temp_directory())
    parts = [p for p in str(filename_prefix).replace("\\", "/").split("/") if p]
    parent = os.path.join(root, *[ _safe_dir_component(p) for p in parts ], _safe_dir_component(unique_id))
    parent = os.path.abspath(parent)
    if os.path.commonpath([root, parent]) != root:
        raise ValueError(f"h3_continuous: frames dir escapes temp: {parent}")
    if os.path.isdir(parent):
        shutil.rmtree(parent)
    path = os.path.join(parent, "frames")
    write_frames_fps(path, FPS)
    return path


def load_png_frame(frames_dir: str, index: int) -> torch.Tensor:
    arr = np.array(Image.open(png_frame_path(frames_dir, int(index))).convert("RGB"))
    return torch.from_numpy(np.ascontiguousarray(arr)).to(dtype=torch.float32).div_(255.0)


def load_png_preview(frames_dir: str) -> torch.Tensor:
    """One frame for the IMAGE socket. Full clips do not fit in float32 RAM."""
    n = png_count(frames_dir)
    if n <= 0:
        raise ValueError(f"h3_continuous: no PNG frames in {frames_dir}")
    return load_png_frame(frames_dir, n - 1).unsqueeze(0)


def load_png_sequence(frames_dir: str) -> torch.Tensor:
    n = png_count(frames_dir)
    if n <= 0:
        raise ValueError(f"h3_continuous: no PNG frames in {frames_dir}")
    first = np.array(Image.open(png_frame_path(frames_dir, 0)).convert("RGB"))
    h, w = int(first.shape[0]), int(first.shape[1])
    out = torch.empty((n, h, w, 3), dtype=torch.float32)
    out[0] = torch.from_numpy(np.ascontiguousarray(first)).to(dtype=torch.float32).div_(255.0)
    del first
    for i in range(1, n):
        arr = np.array(Image.open(png_frame_path(frames_dir, i)).convert("RGB"))
        if int(arr.shape[0]) != h or int(arr.shape[1]) != w:
            raise ValueError(
                f"h3_continuous: PNG {i} is {arr.shape[1]}x{arr.shape[0]}, expected {w}x{h}"
            )
        out[i] = torch.from_numpy(np.ascontiguousarray(arr)).to(dtype=torch.float32).div_(255.0)
    return out

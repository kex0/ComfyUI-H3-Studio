"""Decode/stitch 3D H3 latent upscale. Saved Continue latents stay native size."""

import glob
import os
import sys

UPSCALE_MODES = ["scale by multiplier", "megapixels"]
UPSCALE_PRECISIONS = ["fp32", "fp16", "bf16"]
VAE_DOWNSAMPLE = 16
PIXEL_ALIGN = 32
_CUSTOM_NODES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LBH_PACK = os.path.join(_CUSTOM_NODES, "Comfyui_Minimax_h3_latent_Upscaler")


def upscale_input_specs():
    return {
        "latent_upscale": ("BOOLEAN", {
            "default": False,
            "tooltip": (
                "Decode and stitch only: 3D neural upscale of the video latent. "
                "Saved Continue latents stay native width x height. Off by default. "
                "Disk/RAM budget scales with the chosen size."
            ),
        }),
        "latent_upscale_mode": (UPSCALE_MODES, {
            "default": "scale by multiplier",
            "tooltip": "How the 3D upscaler chooses output size.",
        }),
        "latent_upscale_scale": ("FLOAT", {
            "default": 2.0, "min": 1.0, "max": 4.0, "step": 0.05,
            "tooltip": "Spatial multiplier when mode is scale by multiplier.",
        }),
        "latent_upscale_megapixels": ("FLOAT", {
            "default": 1.0, "min": 0.1, "max": 8.0, "step": 0.1,
            "tooltip": "Target megapixels when mode is megapixels (keeps aspect ratio).",
        }),
        "latent_upscale_precision": (UPSCALE_PRECISIONS, {
            "default": "fp32",
            "tooltip": "3D upscaler inference precision. fp32 is the default.",
        }),
    }


def _truthy_enabled(value):
    if value in (True, 1):
        return True
    text = str(value or "").strip().lower()
    return text in ("true", "1", "on", "2x_3d", "2x_2d", "3d")


def normalize_upscale_mode(mode):
    text = str(mode or "scale by multiplier").strip().lower()
    if text in ("megapixels", "mp"):
        return "megapixels"
    return "scale by multiplier"


def normalize_precision(precision):
    text = str(precision or "fp32").strip().lower()
    if text not in UPSCALE_PRECISIONS:
        raise ValueError(f"h3_studio: unknown latent_upscale_precision {precision!r}")
    return text


def collect_upscale_settings(
    enabled=False, mode="scale by multiplier", scale=2.0, megapixels=1.0, precision="fp32",
):
    return {
        "enabled": _truthy_enabled(enabled),
        "mode": normalize_upscale_mode(mode),
        "scale": float(scale),
        "megapixels": float(megapixels),
        "precision": normalize_precision(precision),
    }


def is_upscale_on(settings):
    if isinstance(settings, dict):
        return bool(settings.get("enabled"))
    return _truthy_enabled(settings)


def _snap_pixel_size(width, height):
    w = max(PIXEL_ALIGN, round(float(width) / PIXEL_ALIGN) * PIXEL_ALIGN)
    h = max(PIXEL_ALIGN, round(float(height) / PIXEL_ALIGN) * PIXEL_ALIGN)
    w = max(VAE_DOWNSAMPLE, round(w / VAE_DOWNSAMPLE) * VAE_DOWNSAMPLE)
    h = max(VAE_DOWNSAMPLE, round(h / VAE_DOWNSAMPLE) * VAE_DOWNSAMPLE)
    return int(w), int(h)


def output_pixel_size(width, height, settings):
    w, h = int(width), int(height)
    if not is_upscale_on(settings):
        return w, h
    cfg = settings if isinstance(settings, dict) else collect_upscale_settings(True)
    if cfg["mode"] == "megapixels":
        target = max(0.1, float(cfg.get("megapixels", 1.0))) * 1024 * 1024
        aspect = w / max(h, 1)
        h_t = (target / aspect) ** 0.5
        w_t = h_t * aspect
    else:
        scale = max(1.0, float(cfg.get("scale", 2.0)))
        w_t = w * scale
        h_t = h * scale
    return _snap_pixel_size(w_t, h_t)


def _unwrap_upscaled_latent(result):
    if isinstance(result, dict) and "samples" in result:
        return result
    if isinstance(result, (tuple, list)) and result:
        return _unwrap_upscaled_latent(result[0])
    args = getattr(result, "args", None)
    if args:
        return _unwrap_upscaled_latent(args[0] if isinstance(args, (tuple, list)) else args)
    try:
        return _unwrap_upscaled_latent(next(iter(result)))
    except TypeError:
        pass
    raise ValueError(f"h3_studio: unexpected latent upscale result {type(result)!r}")


def _scan_checkpoint_names():
    import folder_paths

    folder = "latent_upscale_models"
    if folder not in folder_paths.folder_names_and_paths:
        folder_paths.add_model_folder_path(
            folder, os.path.join(folder_paths.models_dir, folder),
        )
    names = []
    for path in folder_paths.get_folder_paths(folder):
        for ext in ("*.pth", "*.safetensors"):
            names.extend(os.path.basename(p) for p in glob.glob(os.path.join(path, ext)))
    return sorted(set(names))


def pick_upscale_checkpoint(precision="fp32", names=None):
    files = list(names if names is not None else _scan_checkpoint_names())
    files = [n for n in files if n and not str(n).startswith("(")]
    if not files:
        raise RuntimeError(
            "latent_upscale requires checkpoints in ComfyUI/models/latent_upscale_models "
            "(hf download LBH-123-AI/Minimax_h3_latent_Upscaler)"
        )
    three_d = [n for n in files if "3d" in n.lower()] or files
    prec = normalize_precision(precision)
    match = [n for n in three_d if prec in n.lower()]
    if match:
        return sorted(match)[0]
    return sorted(three_d)[0]


def _load_lbh_module(filename, module_name):
    import importlib.util

    path = os.path.join(_LBH_PACK, "nodes", filename)
    if not os.path.isfile(path):
        raise RuntimeError(
            "latent_upscale requires Comfyui_Minimax_h3_latent_Upscaler. "
            "Clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler "
            "into ComfyUI/custom_nodes/"
        )
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def apply_video_upscale(video, settings):
    """Upscale a video latent `[B,24,T,H,W]`. Does not wrap NestedTensor audio."""
    import torch

    cfg = settings if isinstance(settings, dict) else collect_upscale_settings(settings)
    if not cfg["enabled"]:
        return video
    name = pick_upscale_checkpoint(cfg["precision"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    mod = _load_lbh_module("minimax_h3_latent_upscaler_3d.py", "h3_studio_lbh_upscaler_3d")
    resize = mod.UpscaleMode.MEGAPIXELS if cfg["mode"] == "megapixels" else mod.UpscaleMode.SCALE_BY
    result = mod.MinimaxH3LatentUpscaler3D.execute(
        {"samples": video}, name,
        {
            "mode": resize,
            "scale": float(cfg["scale"]),
            "width": 1280,
            "height": 704,
            "megapixels": float(cfg["megapixels"]),
        },
        PIXEL_ALIGN, device, cfg["precision"],
    )
    return _unwrap_upscaled_latent(result)["samples"]


def upscale_av_latent(latent, settings):
    """Return a cloned AV latent with video upscaled. Original NestedTensor is not resized."""
    cfg = settings if isinstance(settings, dict) else collect_upscale_settings(settings)
    if not cfg["enabled"]:
        return latent
    import comfy.nested_tensor
    from .nodes import _streams_from_latent

    video, audio = _streams_from_latent(latent)
    src_h, src_w = int(video.shape[-2]), int(video.shape[-1])
    up_video = apply_video_upscale(video.clone(), cfg)
    if int(video.shape[-2]) != src_h or int(video.shape[-1]) != src_w:
        raise RuntimeError("h3_studio: latent upscale mutated the input video tensor")
    return {
        "samples": comfy.nested_tensor.NestedTensor((
            up_video.detach().cpu().contiguous(),
            audio.detach().cpu().contiguous().clone(),
        ))
    }


def av_clone_from_images(images, source_latent, video_vae):
    """VAE-encode images into a clone that keeps the source audio stream."""
    import comfy.nested_tensor
    from .nodes import _streams_from_latent

    encoded = video_vae.encode(images)
    if encoded.ndim == 4:
        encoded = encoded.unsqueeze(0)
    if encoded.ndim != 5:
        raise ValueError(f"h3_studio: unexpected encoded video shape {tuple(encoded.shape)}")
    _video, audio = _streams_from_latent(source_latent)
    return {
        "samples": comfy.nested_tensor.NestedTensor((
            encoded.detach().cpu().contiguous(),
            audio.detach().cpu().contiguous().clone(),
        ))
    }

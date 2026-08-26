"""Windowed MAINodes de-rope for Auto Chain / Music Video. Video-only. Default off."""

import json
import os
import sys
import types

MAINODES_CLASS_NAMES = (
    "H3JerkOracle",
    "H3WindowPlan",
    "H3TimeSmear",
    "H3V2VInit",
    "H3InjectSchedule",
    "H3ExactRecover",
)
_CUSTOM_NODES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAINODES_PACK = os.path.join(_CUSTOM_NODES, "ComfyUI-MAINodes")
_MAINODES_PKG = "h3_studio_mainodes"
_INSTALL = (
    "de_rope requires ComfyUI-MAINodes. "
    "Clone https://github.com/matlowai/ComfyUI-MAINodes into ComfyUI/custom_nodes/ComfyUI-MAINodes"
)


def derope_input_specs():
    return {
        "de_rope": ("BOOLEAN", {
            "default": False,
            "tooltip": (
                "Windowed burst de-rope via MAINodes (jerk oracle, time smear, V2V, exact recover). "
                "Skips Continue overlap head and landing tail so freeze-overlap tokens still match. "
                "Off by default. Requires ComfyUI-MAINodes. Music Video still muxes the original song; "
                "mouths in a repaired action window can drift."
            ),
        }),
        "de_rope_inject": ("FLOAT", {
            "default": 0.48, "min": 0.45, "max": 0.70, "step": 0.01,
            "tooltip": "V2V inject fraction for de-rope windows (H3InjectSchedule). 0.48 is the starting point.",
        }),
    }


def overlap_skip_ranges(n_frames, clip_index, head_skip, tail_skip):
    """Inclusive pixel-frame ranges to leave as baseline (Continue head / landing tail).

    Clip 1 has no head skip. Finish / last clip has no landing tail skip.
    """
    n = max(0, int(n_frames))
    head = 0 if int(clip_index) <= 1 else max(0, int(head_skip or 0))
    tail = max(0, int(tail_skip or 0))
    ranges = []
    if n <= 0:
        return ranges
    if head > 0:
        ranges.append((0, min(head, n) - 1))
    if tail > 0:
        ranges.append((max(0, n - tail), n - 1))
    return ranges


def window_hits_skip(start, end, ranges):
    a = int(start)
    b = int(end)
    for lo, hi in ranges:
        if a <= int(hi) and b >= int(lo):
            return True
    return False


def load_mainodes():
    if not os.path.isfile(os.path.join(_MAINODES_PACK, "motion.py")):
        raise RuntimeError(_INSTALL)
    if _MAINODES_PKG not in sys.modules:
        pkg = types.ModuleType(_MAINODES_PKG)
        pkg.__path__ = [_MAINODES_PACK]
        pkg.__file__ = os.path.join(_MAINODES_PACK, "__init__.py")
        pkg.__package__ = _MAINODES_PKG
        sys.modules[_MAINODES_PKG] = pkg
    import importlib
    motion = importlib.import_module(f"{_MAINODES_PKG}.motion")
    missing = [name for name in MAINODES_CLASS_NAMES if not hasattr(motion, name)]
    if missing:
        raise RuntimeError(f"de_rope: ComfyUI-MAINodes is missing {', '.join(missing)}")
    return motion


def _progress(unique_id, text):
    from .png_sequence import send_node_progress
    send_node_progress(unique_id, text)


def _holds_from_map(hold_map):
    data = json.loads(hold_map) if isinstance(hold_map, str) else hold_map
    return [int(h) for h in data["holds"]]


def derope_clip_images(
    images, latent, *,
    inject=0.48,
    video_vae=None,
    model=None,
    sampler=None,
    sigmas=None,
    noise=None,
    positive=None,
    clip_index=1,
    is_final=False,
    head_skip=0,
    tail_skip=0,
    unique_id=None,
    enabled=True,
):
    """Paste recovered burst windows onto a clone of `images`. Native `latent` is not replaced."""
    if not enabled:
        return images
    if video_vae is None or model is None or sampler is None or sigmas is None or positive is None:
        raise ValueError("h3_studio: de_rope needs MODEL, SAMPLER, SIGMAS, VAE, and conditioning")
    motion = load_mainodes()
    from .auto_chain import _sample_segment, _segment_noise
    from .nodes import release_loaded_models

    n = int(images.shape[0])
    skip = overlap_skip_ranges(n, clip_index, head_skip, 0 if is_final else tail_skip)
    oracle = motion.H3JerkOracle()
    hold_map, _segments, _w0, _wlen, _profile, _report = oracle.read(
        latent, n, 0.75, 4, True, preset="balanced (default)",
    )
    holds = _holds_from_map(hold_map)
    if not any(h > 1 for h in holds):
        return images

    planner = motion.H3WindowPlan()
    smear = motion.H3TimeSmear()
    v2v = motion.H3V2VInit()
    inject_node = motion.H3InjectSchedule()
    recover = motion.H3ExactRecover()
    first = planner.plan(
        images, hold_map, max_dilated_frames=209, window=0,
        handle_frames=12, coverage="held span",
    )
    window_count = int(first[5])
    planned = [first]
    for k in range(1, window_count):
        planned.append(planner.plan(
            images, hold_map, max_dilated_frames=209, window=k,
            handle_frames=12, coverage="held span",
        ))

    kept = []
    for item in planned:
        splice = json.loads(item[2])
        if window_hits_skip(splice["start"], splice["end"], skip):
            continue
        kept.append(item)
    if not kept:
        return images

    out = images.clone()
    total_steps = max(1, int(sigmas.shape[-1]) - 1)
    v2v_sigmas = inject_node.sigmas(
        model, "simple", total_steps, float(inject), preset="custom",
    )[0]
    seed_base = int(clip_index) * 17

    for i, item in enumerate(kept):
        seg_images, seg_holds, splice_json = item[0], item[1], item[2]
        splice = json.loads(splice_json)
        a, b = int(splice["start"]), int(splice["end"])
        _progress(unique_id, f"De-rope window {i + 1}/{len(kept)} (f{a}–f{b})")
        smeared, hold_used, _length, _smear_report = smear.smear(
            seg_images, 4, hold_map=seg_holds, expand_to_end=True,
        )
        release_loaded_models()
        encoded = video_vae.encode(smeared)
        if encoded.ndim == 4:
            encoded = encoded.unsqueeze(0)
        v2v_latent = v2v.build({"samples": encoded})[0]
        release_loaded_models()
        sampled = _sample_segment(
            model, positive, sampler, v2v_sigmas,
            _segment_noise(noise, seed_base + i), v2v_latent,
            join_prefix=False,
        )
        release_loaded_models()
        from .auto_chain import _decode_video
        decoded = _decode_video(video_vae, sampled)
        recovered = recover.recover(decoded, hold_used)[0]
        span = b - a + 1
        if int(recovered.shape[0]) != span:
            recovered = recovered[:span]
        out[a:b + 1] = recovered.to(device=out.device, dtype=out.dtype)
        del smeared, encoded, v2v_latent, sampled, decoded, recovered
        release_loaded_models()
    return out

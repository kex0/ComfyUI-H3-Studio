"""Segment-count helpers for the Auto Chain node. No ComfyUI imports."""

MAX_SEGMENTS = 999
LEGACY_SEGMENT_WIDGETS = 12


def collect_segment_values(segments, kwargs, prefix):
    values = []
    for i in range(1, int(segments) + 1):
        values.append(kwargs.get(f"{prefix}_{i}"))
    return values


def collect_segment_models(segments, default_model, kwargs):
    models = []
    for i in range(1, int(segments) + 1):
        override = kwargs.get(f"model_{i}")
        models.append(override if override is not None else default_model)
    return models


def clips_to_reuse(resume_from_clip, segments, seamless_loop=False):
    segs = int(segments)
    resume = int(resume_from_clip)
    last = segs + (1 if seamless_loop else 0)
    if segs < 1:
        raise ValueError("h3_continuous: segments must be >= 1")
    if resume < 1 or resume > last:
        loop_hint = f"; {last} = generate only the Loop clip" if seamless_loop else ""
        raise ValueError(
            f"h3_continuous: resume_from_clip must be 1..{last} "
            f"(1 = generate from scratch{loop_hint})"
        )
    return list(range(1, min(resume, segs + 1)))


def segment_prompt_specs():
    specs = {}
    for i in range(1, LEGACY_SEGMENT_WIDGETS + 1):
        if i == 1:
            tip = (
                "Clip 1 (Start) prompt. Describe the action, dialogue, camera and audio for the first "
                "segment. Address optional stills as <Picture 1>, <Picture 2>, … inside the prompt. "
                "Keep important dialogue away from the very end, where handover trim may occur."
            )
        else:
            tip = (
                f"Clip {i} prompt. Used as a Continue segment, or as Finish if this is the last clip. "
                "Describe the action continuing from the previous clip. Optional stills stay available "
                "as <Picture N>. Intermediate clips are stitch-trimmed at the freeze-safe tail."
            )
        specs[f"prompt_{i}"] = ("STRING", {
            "multiline": True, "default": "", "dynamicPrompts": True,
            "tooltip": tip,
        })
    return specs


def segment_model_specs():
    specs = {}
    for i in range(2, LEGACY_SEGMENT_WIDGETS + 1):
        specs[f"model_{i}"] = ("MODEL", {
            "tooltip": (
                f"Optional full patched H3 MODEL for clip {i}: Checkpoint → LoRA → Sigma Shift → "
                "Sage / SolAttn / Spectrum. Not a LoRA file. If unconnected, this clip uses model_1."
            ),
        })
    return specs


MUSIC_MAX_REF_IMAGES = 9


def collect_music_video_reference_images(kwargs):
    images = []
    legacy = kwargs.get("reference_image")
    if legacy is not None:
        images.append(legacy)
    for i in range(1, MUSIC_MAX_REF_IMAGES + 1):
        img = kwargs.get(f"reference_image_{i}")
        if img is not None:
            images.append(img)
    return images


def music_video_reference_image_specs():
    specs = {}
    for i in range(1, MUSIC_MAX_REF_IMAGES + 1):
        nxt = f" Slot {i + 1} appears when this is connected." if i < MUSIC_MAX_REF_IMAGES else ""
        specs[f"reference_image_{i}"] = ("IMAGE", {
            "tooltip": (
                f"Identity/style still for every clip (Ref2VA: Qwen + DiT). "
                f"Address it as <Picture {i}>. "
                f"Not a first-frame / last-frame lock.{nxt}"
            ),
        })
    return specs

import gc
import json
import logging
import math
import os

import torch
from safetensors import safe_open
from safetensors.torch import load_file as st_load, save_file as st_save

import comfy.memory_management
import comfy.model_management
import comfy.model_prefetch
import comfy.nested_tensor
import comfy.utils
import comfy_aimdo.model_vbar
import folder_paths
import node_helpers
import nodes
from comfy_extras.nodes_minimax_h3 import adapt_canvas, _encode_ref_audio

from .latent_math import (
    FPS, AUDIO_HZ, FRAME_RESCALE, CONTEXT_TO_STEPS,
    temporal_shape, pixel_frames, context_slice, phase_aware_context_slice, phase_aligned_extended_context_slice, audio_slice_for_pixel_window,
    loop_end_keyframe_offsets,
)
from .patch_layout import HC_INDEX, HC_AUDIO_END_FRAME
from .runtime_patches import ensure_h3_runtime_patches
from .motion_analysis import analyze_freeze_tail, phase_aware_safety_from_confidence
from .release_utils import (
    duration_to_requested_frames, normalize_alignment_mode, normalize_safety_mode,
    resolve_freeze_settings, stitch_trim_plan, apply_no_lock_fallback,
)
from .freeze_overlap import copy_song_audio, freeze_video_head

_LOG = logging.getLogger("h3_continuous")
CANVAS_MULTIPLE = 32
REF_IMAGE_SHORT_EDGE = 2048


def release_loaded_models():
    # Match ComfyUI's per-node AIMDO boundary. Dynamic VRAM will not evict one
    # staged model to load another, so CLIP / H3 / VAE must not overlap.
    if comfy.memory_management.aimdo_enabled:
        comfy.model_management.reset_cast_buffers()
        comfy.model_prefetch.cleanup_prefetch_queues()
        comfy_aimdo.model_vbar.vbars_reset_watermark_limits()
    comfy.model_management.unload_all_models()
    gc.collect()
    comfy.model_management.soft_empty_cache(True)


def _resize(image, width, height, crop):
    samples = image[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, width, height, "lanczos", crop)
    return samples.movedim(1, -1)


def _empty_av_latent(width, height, length, batch_size=1):
    frame_count, vt, at = temporal_shape(length)
    dev = comfy.model_management.intermediate_device()
    video = torch.zeros([batch_size, 24, vt, height // 16, width // 16], device=dev)
    audio = torch.zeros([batch_size, 32, 2, at], device=dev)
    return {"samples": comfy.nested_tensor.NestedTensor((video, audio))}, frame_count


def _streams_from_latent(latent):
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError("h3_continuous: expected a LATENT dict with 'samples'")
    samples = latent["samples"]
    if hasattr(samples, "unbind"):
        parts = list(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = list(samples)
    else:
        raise ValueError(f"h3_continuous: expected H3 AV nested latent, got {type(samples)!r}")
    if len(parts) < 2:
        raise ValueError("h3_continuous: H3 latent must contain both video and audio streams")
    video, audio = parts[0], parts[1]
    if video.ndim == 4:
        video = video.unsqueeze(0)
    if audio.ndim == 3:
        audio = audio.unsqueeze(0)
    if video.ndim != 5 or audio.ndim != 4:
        raise ValueError(
            f"h3_continuous: unexpected H3 shapes video={tuple(video.shape)}, audio={tuple(audio.shape)}"
        )
    return video, audio


def _prepare_qwen_reference_image(image, width, height, mode):
    """Resize ``<Picture N>`` to the stock H3 reference canvas.

    Auto Chain and Music Video both VAE-encode the same resized still into
    DiT ``minimax_refs`` (``kind=image``). Standalone FL2VA Start stills stay
    on ``minimax_keyframes`` when first/last frames are supplied.
    """
    h, w = int(image.shape[1]), int(image.shape[2])
    if mode == "match":
        scale = min(1.0, math.sqrt((width * height) / float(w * h)))
    else:
        scale = min(1.0, REF_IMAGE_SHORT_EDGE / float(min(w, h)))
    tw = max(CANVAS_MULTIPLE, round(w * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
    th = max(CANVAS_MULTIPLE, round(h * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
    return _resize(image[:1], tw, th, "disabled")


def _collect_reference_images(reference_image=None, reference_images=None):
    if reference_images:
        return [img for img in reference_images if img is not None]
    if reference_image is not None:
        return [reference_image]
    return []


def _sole_picture_is_first_frame(first_frame, pics):
    """True when the clip's only still is the same tensor as the FL2VA first-frame lock."""
    return first_frame is not None and len(pics) == 1 and pics[0] is first_frame


def _qwen_picture_items(images, width, height, mode):
    return [
        {"type": "image", "data": _prepare_qwen_reference_image(img, width, height, mode)}
        for img in images
    ]


def _ref2va_image_blocks(images, vae, width, height, mode):
    """Stock MiniMaxH3ReferenceToVideo image refs: Qwen stills plus DiT ``kind=image`` latents."""
    blocks = []
    for image in images:
        resized = _prepare_qwen_reference_image(image, width, height, mode)
        latent = vae.encode(resized)
        blocks.append({
            "kind": "image",
            "latent_h": int(resized.shape[1]) // 16,
            "latent_w": int(resized.shape[2]) // 16,
            "latent": latent,
        })
    return blocks


def _nonzero_refs(values):
    return [item for item in (values or []) if item is not None]


def _ref2va_video_items_and_blocks(videos, video_audios, vae, audio_vae, frame_count):
    """Stock MiniMaxH3ReferenceToVideo video refs: 2 fps Qwen samples plus DiT video blocks."""
    items = []
    blocks = []
    videos = _nonzero_refs(videos)
    video_audios = list(video_audios or [])
    for i, video_frames in enumerate(videos):
        soundtrack = video_audios[i] if i < len(video_audios) else None
        vh, vw = int(video_frames.shape[1]), int(video_frames.shape[2])
        cw, ch = adapt_canvas(vw, vh)
        if vw * vh < cw * ch:
            cw = max(CANVAS_MULTIPLE, round(vw / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
            ch = max(CANVAS_MULTIPLE, round(vh / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
        frames = _resize(video_frames, cw, ch, "disabled")
        if frames.shape[0] > frame_count:
            frames = frames[:frame_count]
        n = int(frames.shape[0])
        if n < 5:
            raise ValueError("h3_studio: reference videos need at least 5 frames (~0.2s at 24 fps)")
        while n % 17 != 5:
            n -= 1
        frames = frames[:n]
        z = vae.encode(frames)
        audio_latent, ref_audio_t = (None, 0)
        if soundtrack is not None:
            if audio_vae is None:
                raise ValueError("h3_studio: video soundtrack refs need audio_vae")
            audio_latent, ref_audio_t = _encode_ref_audio(audio_vae, soundtrack)
            items.append({"type": "audio"})
        sample_idx = list(range(0, int(frames.shape[0]), max(1, int(FPS) // 2)))
        qwen_frames = frames[sample_idx]
        items.append({
            "type": "video",
            "data": qwen_frames,
            "timestamps": [i / 2.0 for i in range(len(sample_idx))],
        })
        blocks.append({
            "kind": "video_audio" if ref_audio_t else "video",
            "latent_t": z.shape[2],
            "latent_h": ch // 16,
            "latent_w": cw // 16,
            "ref_audio_t": ref_audio_t,
            "latent": z,
            "audio_latent": audio_latent,
        })
    return items, blocks


def _ref2va_audio_items_and_blocks(audios, audio_vae):
    items = []
    blocks = []
    for audio in _nonzero_refs(audios):
        if audio_vae is None:
            raise ValueError("h3_studio: standalone audio refs need audio_vae")
        audio_latent, ref_audio_t = _encode_ref_audio(audio_vae, audio)
        items.append({"type": "audio"})
        blocks.append({
            "kind": "audio",
            "ref_audio_t": ref_audio_t,
            "audio_latent": audio_latent,
        })
    return items, blocks


def _apply_song_audio_lock(latent, song, lock):
    video, audio = _streams_from_latent(latent)
    song_t = int(song.shape[-1]) if song is not None else 0
    clip_t = int(audio.shape[-1])
    audio, a_mask = copy_song_audio(audio, song, lock)
    if a_mask is None:
        return latent, ""
    latent = dict(latent)
    if "noise_mask" in latent:
        v_mask = list(latent["noise_mask"].unbind())[0]
    else:
        v_mask = torch.ones(
            (int(video.shape[0]), 1, int(video.shape[2]), 1, 1),
            device=video.device,
            dtype=torch.float32,
        )
    latent["samples"] = comfy.nested_tensor.NestedTensor((video, audio))
    latent["noise_mask"] = comfy.nested_tensor.NestedTensor((v_mask, a_mask))
    note = f" | song audio lock {min(max(float(lock), 0.0), 1.0):.2f}"
    if song_t != clip_t:
        note += f" (fitted {song_t}->{clip_t})"
    return latent, note


def _require_patches():
    # v1.1.4: importing/installing the node pack must not alter ComfyUI's H3
    # runtime. Install the two narrowly marker-gated hooks only when a direct
    # latent continuation is actually requested.
    ensure_h3_runtime_patches()


class H3ContinuousStart:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": True}),
                "width": ("INT", {"default": 1344, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32}),
                "height": ("INT", {"default": 768, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32}),
                "length": ("INT", {"default": 243, "min": 5, "max": 3600, "step": 17,
                                   "tooltip": "Frames at 24 fps; internally snapped upward to H3's 17k+5 grid. 243 ~= 10.1s."}),
                "ref_image_size": (["match", "max"], {"default": "match"}),
            },
            "optional": {
                "first_frame": ("IMAGE", {"tooltip": "Optional start still. If omitted, Clip 1 is not locked to a first-frame image."}),
                "last_frame": ("IMAGE", {"tooltip": "Optional target endpoint. If omitted, there is no fixed landing; Auto Handover may use No-Lock Fallback."}),
                "reference_image": ("IMAGE", {"tooltip": "Optional identity/style reference. Address it as <Picture 1>. Encoded as a Ref2VA image ref (Qwen + DiT)."}),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "latent")
    FUNCTION = "build"
    CATEGORY = "H3 Continuous"
    DESCRIPTION = (
        "Clip 1: native FL2VA first/last anchors (both optional). Optional <Picture N> stills "
        "are Ref2VA (Qwen + DiT image refs). If the clip's only picture is the first-frame lock, "
        "Qwen uses official Image-to-Video canvas stretch instead of a Ref2VA picture ref."
    )

    def build(self, clip, vae, prompt, width, height, length, first_frame=None, last_frame=None,
              ref_image_size="match", reference_image=None, reference_images=None,
              song_audio_latent=None, song_audio_lock=0.0,
              reference_videos=None, reference_video_audios=None, reference_audios=None,
              audio_vae=None):
        # Clip 1 with first/last stills stays on native FL2VA keyframes.
        # <Picture N> stills are stock Ref2VA (Qwen + DiT kind=image).
        # A Music Video song slice adds <Audio 1> to the same Ref2VA refs.
        # Optional video / standalone audio refs follow stock Ref2VA order.
        latent, frame_count = _empty_av_latent(width, height, length)

        images = []
        first = last = None
        if first_frame is not None:
            first = _resize(first_frame[:1], width, height, "disabled")
            images.append(first)
        if last_frame is not None:
            last = _resize(last_frame[:1], width, height, "center")
            images.append(last)

        pics = _collect_reference_images(reference_image, reference_images)
        # One clip picture that is also the first-frame lock: do not also feed it as a
        # Ref2VA match/max still. Callers may clear pics via sole_first_frame; keep the
        # identity check for direct Start wiring.
        sole_first = _sole_picture_is_first_frame(first_frame, pics)
        if sole_first:
            pics = []
        video_items, video_blocks = _ref2va_video_items_and_blocks(
            reference_videos, reference_video_audios, vae, audio_vae, frame_count,
        )
        audio_items, audio_blocks = _ref2va_audio_items_and_blocks(reference_audios, audio_vae)
        ref_items = _qwen_picture_items(pics, width, height, ref_image_size)
        if song_audio_latent is not None:
            ref_items.append({"type": "audio"})
        ref_items.extend(video_items)
        ref_items.extend(audio_items)
        if ref_items:
            # Song/video/audio force Ref2VA tokenize. With no separate picture refs, feed
            # the stretched canvas so Qwen still sees official first-frame geometry.
            if first is not None and not pics:
                ref_items.insert(0, {"type": "image", "data": first})
                _LOG.info("h3_continuous: clip 1 Qwen=FL2VA canvas inside Ref2VA tokenize")
            else:
                _LOG.info("h3_continuous: clip 1 Qwen=Ref2VA pictures=%s", len(pics))
            tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        elif images:
            _LOG.info("h3_continuous: clip 1 Qwen=official Image-to-Video (images=)")
            tokens = clip.tokenize(prompt, images=images)
        else:
            _LOG.info("h3_continuous: clip 1 Qwen=text only")
            tokens = clip.tokenize(prompt)

        release_loaded_models()
        cond = clip.encode_from_tokens_scheduled(tokens)
        if song_audio_latent is not None:
            _require_patches()
        keyframes = []
        if first is not None or last is not None:
            release_loaded_models()
            if first is not None:
                keyframes.append({
                    "resolved_frame_index": 0,
                    "latent": vae.encode(first).detach().cpu().contiguous(),
                })
            if last is not None:
                keyframes.append({
                    "resolved_frame_index": frame_count - 1,
                    "latent": vae.encode(last).detach().cpu().contiguous(),
                })
        extra = {}
        if keyframes:
            extra["minimax_keyframes"] = keyframes
            extra["minimax_frame_count"] = frame_count
        refs = []
        if pics:
            release_loaded_models()
            refs.extend(_ref2va_image_blocks(pics, vae, width, height, ref_image_size))
        if video_blocks:
            release_loaded_models()
            refs.extend(video_blocks)
        refs.extend(audio_blocks)
        if song_audio_latent is not None:
            refs.append({
                "kind": "audio",
                "ref_audio_t": int(song_audio_latent.shape[-1]),
                "audio_latent": song_audio_latent,
                HC_AUDIO_END_FRAME: float(frame_count),
            })
        if refs:
            extra["minimax_refs"] = refs
            extra["minimax_frame_count"] = frame_count
        if extra:
            cond = node_helpers.conditioning_set_values(cond, extra)
        latent, song_lock_note = _apply_song_audio_lock(latent, song_audio_latent, song_audio_lock)
        if song_lock_note:
            _LOG.info("h3_continuous: clip 1%s", song_lock_note)
        return (cond, latent)


def _resolve_continue_slice(prev_video, context_frames, handover_mode, alignment_mode,
                            manual_landing_tail_frames, handover):
    previous_frame_count = pixel_frames(prev_video.shape[2])
    ideal_last_frame = None
    landing_tail_frames = manual_landing_tail_frames
    handover_source = "manual"
    if str(handover_mode).lower() == "auto":
        if isinstance(handover, dict) and handover.get("available"):
            try:
                meta_frames = int(handover.get("frame_count", -1))
                if meta_frames != previous_frame_count:
                    raise ValueError(
                        f"metadata frame_count {meta_frames} != latent frame_count {previous_frame_count}"
                    )
                if handover.get("detector_mode") not in ("final_frame_lock", "final_frame_lock_robust", "stable_tail_consensus"):
                    _LOG.warning(
                        "h3_continuous: loaded handover metadata predates final-frame-lock detection; "
                        "the stored cutoff will still work, but re-analyze/re-save the source clip to get the new later lock point"
                    )
                if alignment_mode in ("phase_aligned_extended", "phase_aware"):
                    if alignment_mode == "phase_aligned_extended" and "phase_aligned_target_end_frame" in handover:
                        ideal_last_frame = int(handover["phase_aligned_target_end_frame"])
                        handover_source = "auto handover metadata / phase-aligned-extended"
                    elif "phase_aware_target_end_frame" in handover:
                        ideal_last_frame = int(handover["phase_aware_target_end_frame"])
                        handover_source = f"auto handover metadata / {alignment_mode}"
                    elif handover.get("freeze_detected") and int(handover.get("freeze_start_frame", -1)) >= 0:
                        freeze_start = int(handover["freeze_start_frame"])
                        confidence = float(handover.get("confidence", 0.0))
                        configured_safety = int(handover.get("safety_margin", 1))
                        legacy_safety_mode = str(handover.get("safety_mode", "adaptive"))
                        effective_safety = phase_aware_safety_from_confidence(
                            confidence, configured_safety, safety_mode=legacy_safety_mode
                        )
                        ideal_last_frame = freeze_start - 1 - effective_safety
                        ideal_last_frame = max(context_frames - 1, ideal_last_frame)
                        handover_source = (
                            f"legacy auto metadata / {alignment_mode} "
                            f"(derived from old freeze point; {legacy_safety_mode} safety {effective_safety})"
                        )
                    elif "ideal_handover_end_frame" in handover:
                        ideal_last_frame = int(handover["ideal_handover_end_frame"])
                        handover_source = f"auto metadata / {alignment_mode} conservative fallback"
                    else:
                        raise ValueError("metadata has no usable phase-aware cutoff")
                else:
                    legacy_tail = handover.get("legacy_landing_tail_frames", handover.get("landing_tail_frames", -1))
                    legacy_tail = int(legacy_tail)
                    if legacy_tail < 0 or legacy_tail % 17 != 0:
                        raise ValueError(f"invalid legacy auto landing tail {legacy_tail}")
                    landing_tail_frames = legacy_tail
                    handover_source = "auto freeze analysis / legacy-17"
            except Exception as e:
                _LOG.warning(
                    "h3_continuous: auto handover metadata rejected (%s); using manual fallback %s",
                    e, manual_landing_tail_frames
                )
                handover_source = "manual fallback (auto metadata invalid)"
        else:
            handover_source = "manual fallback (no auto metadata)"

    if alignment_mode == "phase_aligned_extended":
        if ideal_last_frame is not None:
            sl = phase_aligned_extended_context_slice(
                prev_video.shape[2], context_frames, ideal_last_frame=ideal_last_frame
            )
        else:
            sl = phase_aligned_extended_context_slice(
                prev_video.shape[2], context_frames,
                desired_tail_frames=max(0, manual_landing_tail_frames)
            )
    elif alignment_mode == "phase_aware":
        if ideal_last_frame is not None:
            sl = phase_aware_context_slice(
                prev_video.shape[2], context_frames, ideal_last_frame=ideal_last_frame
            )
        else:
            sl = phase_aware_context_slice(
                prev_video.shape[2], context_frames,
                desired_tail_frames=max(0, manual_landing_tail_frames)
            )
    else:
        if landing_tail_frames < 0 or landing_tail_frames % 17 != 0:
            raise ValueError(
                "h3_continuous: legacy_17 mode requires landing tail 0 or a multiple of 17"
            )
        sl = context_slice(prev_video.shape[2], context_frames, landing_tail_frames)
    return sl, handover_source


class H3ContinuousContinue:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "previous_latent": ("LATENT", {"tooltip": "Loaded sampler output from the previous accepted clip."}),
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": True}),
                "width": ("INT", {"default": 1344, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32}),
                "height": ("INT", {"default": 768, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32}),
                "length": ("INT", {"default": 243, "min": 5, "max": 3600, "step": 17}),
                "context_frames": (["5", "22", "39"], {"default": "22",
                    "tooltip": "Minimum requested direct-latent motion/audio history. phase_aligned_extended may extend backward to the nearest phase-0 start so the head stays on H3's canonical timeline."}),
                "handover_mode": (["auto", "manual"], {"default": "auto",
                    "tooltip": "AUTO uses freeze-analysis metadata saved with the previous latent. MANUAL uses manual_landing_tail_frames."}),
                "alignment_mode": (["phase_aligned_extended", "phase_aware", "legacy_17"], {"default": "phase_aligned_extended",
                    "tooltip": "phase_aligned_extended (v0.4.6 recommended; handover geometry unchanged from v0.4.3): keep the late cutoff but extend context backward to a phase-0 source start, matching the target head timeline. phase_aware is the v0.4.1 experimental non-zero-phase mode; legacy_17 is the conservative baseline."}),
                "manual_landing_tail_frames": ("INT", {"default": 34, "min": 0, "max": 3400, "step": 1,
                    "tooltip": "Manual/fallback desired pixel tail. phase_aligned_extended/phase_aware snap the END only to an actual latent boundary; legacy_17 requires a multiple of 17. Never trims rendered video."}),
                "ref_image_size": (["match", "max"], {"default": "match"}),
            },
            "optional": {
                "handover": ("H3_CONTINUOUS_HANDOVER", {"tooltip": "Auto-handover metadata from Load AV Latent."}),
                "last_frame": ("IMAGE", {"tooltip": "Recommended: next pre-generated keyframe / target endpoint."}),
                "end_latent": ("LATENT", {"tooltip": "Optional destination AV latent. Auto Chain seamless_loop packs clip 1's opening after the I2VA still-hold as end keyframes (video + audio), same grid as Continue head context."}),
                "reference_image": ("IMAGE", {"tooltip": "Optional identity/style reference. Address it as <Picture 1>. Encoded as a Ref2VA image ref (Qwen + DiT)."}),
                "identity_frame": ("IMAGE", {"tooltip": "Last overlap decoded still from the previous clip. Used as an I2V-style appearance lock for the rest of this clip. Does not freeze motion. Auto Chain / Music Video fill this automatically."}),
                "freeze_overlap": ("BOOLEAN", {"default": True,
                    "tooltip": "Copy the previous clip's overlap video tokens into this clip and do not denoise them. Stitch still discards that overlap. Turn off to compare against regenerated-head Continue."}),
                "overlap_soft_steps": ("INT", {"default": 2, "min": 0, "max": 4, "step": 1,
                    "tooltip": "When freeze_overlap is on, the last N frozen video steps get a light denoise ramp so the first kept frames are not a hard inpaint edge. 0 = hard freeze. 2 is the starting point."}),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT", "INT", "INT", "STRING")
    RETURN_NAMES = ("positive", "latent", "actual_head_context_frames", "ignored_tail_frames", "handover_info")
    FUNCTION = "build"
    CATEGORY = "H3 Continuous"
    DESCRIPTION = "Clip 2+: direct AV-latent handover. v0.4.6 keeps the proven phase_aligned_extended handover; calibrated Stable-Tail Consensus defaults plus fixed/adaptive safety selection."

    def build(self, clip, vae, previous_latent, prompt, width, height, length,
              context_frames="22", handover_mode="auto", alignment_mode="phase_aligned_extended",
              manual_landing_tail_frames=34, ref_image_size="match", freeze_overlap=True,
              overlap_soft_steps=2, handover=None,
              last_frame=None, reference_image=None, reference_images=None, end_latent=None,
              song_audio_latent=None, identity_frame=None, song_audio_lock=0.0,
              reference_videos=None, reference_video_audios=None, reference_audios=None,
              audio_vae=None):
        _require_patches()
        context_frames = int(context_frames)
        manual_landing_tail_frames = int(manual_landing_tail_frames)
        overlap_soft_steps = int(overlap_soft_steps)
        alignment_mode = str(alignment_mode).lower()
        if alignment_mode not in ("phase_aligned_extended", "phase_aware", "legacy_17"):
            raise ValueError(f"h3_continuous: unknown alignment_mode {alignment_mode!r}")
        if song_audio_latent is not None and end_latent is not None:
            raise ValueError("h3_continuous: song_audio_latent cannot be combined with end_latent")

        prev_video, prev_audio = _streams_from_latent(previous_latent)
        previous_frame_count = pixel_frames(prev_video.shape[2])
        sl, handover_source = _resolve_continue_slice(
            prev_video, context_frames, handover_mode, alignment_mode,
            manual_landing_tail_frames, handover,
        )

        target_latent, frame_count = _empty_av_latent(width, height, length)
        target_video, target_audio = _streams_from_latent(target_latent)
        if tuple(prev_video.shape[-2:]) != tuple(target_video.shape[-2:]):
            raise ValueError(
                "h3_continuous: direct latent continuation requires identical resolution. "
                f"Previous latent grid {tuple(prev_video.shape[-2:])}, target grid {tuple(target_video.shape[-2:])}."
            )

        source = prev_video[:1, :, sl["start_t"]:sl["end_t"]].clone()
        if int(source.shape[2]) != sl["context_steps"]:
            raise RuntimeError("h3_continuous: internal video context slice length mismatch")

        freeze_note_extra = ""
        if bool(freeze_overlap):
            frozen_video, frozen_audio, v_mask, a_mask = freeze_video_head(
                target_video, source, target_audio, soft_steps=overlap_soft_steps,
            )
            if v_mask is not None:
                target_latent = dict(target_latent)
                target_latent["samples"] = comfy.nested_tensor.NestedTensor(
                    (frozen_video, frozen_audio)
                )
                target_latent["noise_mask"] = comfy.nested_tensor.NestedTensor((v_mask, a_mask))
                freeze_note_extra = (
                    f" | overlap freeze {int(source.shape[2])} video steps, "
                    f"soft {int(overlap_soft_steps)}"
                )

        target_latent, song_lock_note = _apply_song_audio_lock(
            target_latent, song_audio_latent, song_audio_lock,
        )

        # phase_aligned_extended deliberately starts the source run on H3 phase 0,
        # so these offsets exactly match the target clip's canonical head grid.
        # The retained phase_aware fallback can still use non-canonical source-relative
        # offsets for A/B comparison with v0.4.1.
        keyframes = []
        for k, pixel_offset in enumerate(sl["offsets"]):
            keyframes.append({
                "resolved_frame_index": 0,
                HC_INDEX: int(pixel_offset),
                "latent": source[:, :, k:k + 1],
            })

        last = None
        keyframe_images = []
        if last_frame is not None:
            last = _resize(last_frame[:1], width, height, "center")
            keyframe_images.append(last)
        identity = None
        if identity_frame is not None:
            identity = _resize(identity_frame[:1], width, height, "disabled")

        actual_context_frames = int(sl.get("actual_context_frames", context_frames))
        # Clip 1 already has the native still lock (FL2VA / Ref2VA). A second
        # I2V encode of that photograph on a 0-overlap or frame-0 head fries
        # the opening. Identity is Continue-only, after a real overlap.
        if identity is not None and actual_context_frames <= 1:
            identity = None
        if song_audio_latent is not None:
            song = song_audio_latent
            if song.ndim == 3:
                song = song.unsqueeze(0)
            a0, a1 = 0, int(song.shape[-1])
            ref_audio_t = a1
            refs = [{
                "kind": "audio",
                "ref_audio_t": ref_audio_t,
                "audio_latent": song,
                HC_AUDIO_END_FRAME: float(frame_count),
            }]
            audio_note = f"song slice audio ref (full clip, {ref_audio_t} steps; previous generated audio skipped)"
        else:
            a0, a1, end_error_steps = audio_slice_for_pixel_window(
                prev_audio.shape[-1], sl["source_start_frame"], sl["source_end_frame"]
            )
            audio_context = prev_audio[:1, ..., a0:a1].clone()
            ref_audio_t = int(audio_context.shape[-1])
            audio_end_frame = float(actual_context_frames) + float(end_error_steps) / FRAME_RESCALE
            refs = [{
                "kind": "audio",
                "ref_audio_t": ref_audio_t,
                "audio_latent": audio_context,
                HC_AUDIO_END_FRAME: audio_end_frame,
            }]
            audio_note = f"audio latent {a0}:{a1} ({ref_audio_t} steps)"

        pics = _collect_reference_images(reference_image, reference_images)
        video_items, video_blocks = _ref2va_video_items_and_blocks(
            reference_videos, reference_video_audios, vae, audio_vae, frame_count,
        )
        audio_items, audio_blocks = _ref2va_audio_items_and_blocks(reference_audios, audio_vae)
        ref_items = _qwen_picture_items(pics, width, height, ref_image_size)
        if not ref_items and identity is not None:
            ref_items.append({"type": "image", "data": identity})
            if last is not None:
                ref_items.append({"type": "image", "data": last})
        if song_audio_latent is not None:
            ref_items.append({"type": "audio"})
        ref_items.extend(video_items)
        ref_items.extend(audio_items)

        if ref_items:
            tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        elif keyframe_images:
            tokens = clip.tokenize(prompt, images=keyframe_images)
        else:
            tokens = clip.tokenize(prompt)
        cond = clip.encode_from_tokens_scheduled(tokens)
        image_blocks = []
        if pics:
            release_loaded_models()
            image_blocks = _ref2va_image_blocks(pics, vae, width, height, ref_image_size)
        refs = image_blocks + video_blocks + audio_blocks + refs
        end_note = ""
        if end_latent is not None:
            end_video, end_audio = _streams_from_latent(end_latent)
            if tuple(end_video.shape[-2:]) != tuple(target_video.shape[-2:]):
                raise ValueError(
                    "h3_continuous: loop end latent resolution differs from the target clip. "
                    f"End latent grid {tuple(end_video.shape[-2:])}, target grid {tuple(target_video.shape[-2:])}."
                )
            end_spec = loop_end_keyframe_offsets(
                frame_count, context_frames, source_latent_t=int(end_video.shape[2]),
            )
            end_source = end_video[:1, :, end_spec["source_start_t"]:end_spec["source_end_t"]].clone()
            if int(end_source.shape[2]) != end_spec["context_steps"]:
                raise RuntimeError("h3_continuous: loop end context slice length mismatch")
            n_end = end_spec["context_steps"]
            for k, pixel_offset in enumerate(end_spec["offsets"]):
                is_last_end = k == n_end - 1
                keyframes.append({
                    # PackedLayout only accepts resolved_frame_index 0 or last.
                    # Interior opening steps stay on 0 and are moved by HC_INDEX.
                    "resolved_frame_index": (frame_count - 1) if is_last_end else 0,
                    HC_INDEX: (frame_count - 1) if is_last_end else int(pixel_offset),
                    "latent": end_source[:, :, k:k + 1],
                })
            skip_frames = int(end_spec["source_skip_frames"])
            a0e, a1e, end_error_end = audio_slice_for_pixel_window(
                end_audio.shape[-1], skip_frames, skip_frames + end_spec["actual_context_frames"]
            )
            end_audio_context = end_audio[:1, ..., a0e:a1e].clone()
            refs.append({
                "kind": "audio",
                "ref_audio_t": int(end_audio_context.shape[-1]),
                "audio_latent": end_audio_context,
                HC_AUDIO_END_FRAME: float(frame_count) + float(end_error_end) / FRAME_RESCALE,
            })
            skip_note = f", skip {skip_frames} I2VA hold frame(s)" if skip_frames else ""
            end_note = (
                f" | loop sandwich end {end_spec['actual_context_frames']} video frame(s) "
                f"+ {int(end_audio_context.shape[-1])} audio step(s) from clip-1 opening{skip_note}"
            )
        elif last is not None:
            release_loaded_models()
            keyframes.append({
                # Mark the continuation endpoint too. This lets the v1.1.4
                # layout wrapper touch only this suite's own keyframes and
                # leave unrelated stock FL2VA/Ref2VA graphs unchanged.
                "resolved_frame_index": 0,
                HC_INDEX: frame_count - 1,
                "latent": vae.encode(last).detach().cpu().contiguous(),
            })
        identity_note = ""
        if identity is not None:
            identity_at = max(0, actual_context_frames - 1)
            if identity_at > 0:
                release_loaded_models()
                keyframes.append({
                    "resolved_frame_index": 0,
                    HC_INDEX: identity_at,
                    "latent": vae.encode(identity).detach().cpu().contiguous(),
                })
                identity_note = f" | identity still @ {identity_at}"
            else:
                identity = None
        cond = node_helpers.conditioning_set_values(cond, {
            "minimax_keyframes": keyframes,
            "minimax_frame_count": frame_count,
            "minimax_refs": refs,
        })

        ignored_tail = int(sl.get("ignored_tail_frames", previous_frame_count - sl["source_end_frame"]))
        freeze_note = ""
        if isinstance(handover, dict) and handover.get("available"):
            if handover.get("freeze_detected"):
                freeze_note = (
                    f" | detected freeze start {handover.get('freeze_start_frame')} "
                    f"ideal end {handover.get('ideal_handover_end_frame')}"
                )
            elif handover.get("no_lock_fallback_applied"):
                freeze_note = (
                    f" | no trailing freeze detected | NO-LOCK FALLBACK "
                    f"requested exclude {handover.get('no_lock_fallback_requested_excluded_frames')} frame(s) "
                    f"| effective end {handover.get('handover_end_frame')} "
                    f"| effective tail {handover.get('landing_tail_frames')}"
                )
            else:
                freeze_note = " | no trailing freeze detected"

        phase_note = ""
        if alignment_mode == "phase_aligned_extended":
            phase_note = (
                f" | source phase {sl['source_start_phase']}->{sl['source_end_phase']} "
                f"| canonical-head offsets=yes "
                f"| context extension +{sl.get('context_extension_frames', 0)} frame(s) "
                f"| cutoff quantization loss {sl['cutoff_loss_frames']} frame(s)"
            )
        elif alignment_mode == "phase_aware":
            phase_note = (
                f" | source phase {sl['source_start_phase']}->{sl['source_end_phase']} "
                f"| canonical-head offsets=no "
                f"| cutoff quantization loss {sl['cutoff_loss_frames']} frame(s)"
            )

        info = (
            f"handover={handover_source} | alignment={alignment_mode} | "
            f"source frames {sl['source_start_frame']}..{sl['source_end_frame'] - 1} "
            f"of {sl['previous_frame_count']} | video latent {sl['start_t']}:{sl['end_t']} "
            f"({sl['context_steps']} steps / {actual_context_frames} actual frames; "
            f"requested {context_frames}) | offsets {sl['offsets']} | "
            f"{audio_note} | "
            f"ignored previous tail {ignored_tail} frames (latent handover only)" +
            phase_note + freeze_note + freeze_note_extra + identity_note + end_note + song_lock_note
        )
        _LOG.info("h3_continuous: %s", info)
        return (cond, target_latent, actual_context_frames, ignored_tail, info)


class H3ContinuousSaveLatent:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT", {"tooltip": "Sampler output AV latent for the accepted clip."}),
                "filename_prefix": ("STRING", {"default": "h3_continuous/clip"}),
                "clip_index": ("INT", {"default": 1, "min": 0, "max": 99999,
                    "tooltip": "Fixed chain slot. Clip 1 -> 1, clip 2 -> 2. Re-rendering overwrites that slot. 0 = auto-numbered attempt."}),
            },
            "optional": {
                "handover": ("H3_CONTINUOUS_HANDOVER", {"tooltip": "Optional freeze-analysis metadata. The full latent is still saved unchanged."}),
                "head_context_frames": ("INT", {
                    "forceInput": True,
                    "tooltip": "Clip 1: leave unconnected (0). Clip 2+: connect actual_head_context_frames from Continue from Latent so the saved file is self-describing for later seamless stitching.",
                }),
            },
        }
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("latent_path", "latent_info")
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "H3 Continuous"
    DESCRIPTION = "Save the COMPLETE H3 AV latent plus non-destructive handover/head-context metadata for later continuation or seamless saved-chain stitching."

    def save(self, latent, filename_prefix, clip_index=1, handover=None, head_context_frames=0,
             extra_metadata=None):
        video, audio = _streams_from_latent(latent)
        video_cpu = video.detach().cpu().contiguous()
        audio_cpu = audio.detach().cpu().contiguous()
        frame_count = pixel_frames(video_cpu.shape[2])

        folder, filename, counter, _, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory()
        )
        os.makedirs(folder, exist_ok=True)
        if int(clip_index) > 0:
            path = os.path.join(folder, f"{filename}_{int(clip_index):05d}.safetensors")
        else:
            path = os.path.join(folder, f"{filename}_{int(counter):05d}_.safetensors")

        head_context_frames = max(0, int(head_context_frames or 0))
        metadata = {
            "format": "h3_continuous_av_v8",
            "release_version": "1.2.1",
            "fps": str(FPS),
            "frame_count": str(frame_count),
            "clip_index": str(int(clip_index)),
            "head_context_frames": str(head_context_frames),
            "video_shape": json.dumps(list(video_cpu.shape)),
            "audio_shape": json.dumps(list(audio_cpu.shape)),
        }
        handover_summary = "no handover metadata"
        if isinstance(handover, dict) and handover.get("available"):
            analyzed_frames = int(handover.get("frame_count", frame_count))
            if analyzed_frames != frame_count:
                _LOG.warning(
                    "h3_continuous: analyzer frame_count %s != saved latent frame_count %s; "
                    "handover metadata will not be saved", analyzed_frames, frame_count
                )
                handover_summary = "handover metadata rejected (frame-count mismatch)"
            else:
                clean = dict(handover)
                clean["frame_count"] = frame_count
                metadata["handover_json"] = json.dumps(clean, separators=(",", ":"), sort_keys=True)
                handover_summary = (
                    f"phase-aligned tail {clean.get('landing_tail_frames', '?')} | "
                    f"legacy tail {clean.get('legacy_landing_tail_frames', '?')} | "
                    f"freeze={'yes' if clean.get('freeze_detected') else 'no'}"
                )
                if clean.get("no_lock_fallback_applied"):
                    handover_summary += (
                        f" | no-lock-fallback=yes "
                        f"(requested {clean.get('no_lock_fallback_requested_excluded_frames')} -> "
                        f"effective tail {clean.get('landing_tail_frames')})"
                    )

        if extra_metadata:
            for key, value in extra_metadata.items():
                if value is None:
                    continue
                metadata[str(key)] = value if isinstance(value, str) else json.dumps(value)

        st_save({"video": video_cpu, "audio": audio_cpu}, path, metadata=metadata)
        info = (
            f"{frame_count} frames | video {tuple(video_cpu.shape)} | audio {tuple(audio_cpu.shape)} | "
            f"head context {head_context_frames} | {handover_summary}"
        )
        _LOG.info("h3_continuous: saved %s (%s)", path, info)
        return (path, info)


def _resolve_latent_path(path, clip_index):
    p = (path or "").strip().strip('"').strip("'")
    if not p:
        p = "h3_continuous"
    candidates = [p, os.path.join(folder_paths.get_output_directory(), p)]
    for c in candidates:
        if os.path.isfile(c):
            return c
        if os.path.isdir(c):
            files = [os.path.join(c, f) for f in os.listdir(c) if f.endswith(".safetensors")]
            if not files:
                raise FileNotFoundError(f"h3_continuous: no .safetensors files in {c}")
            idx = int(clip_index)
            if idx > 0:
                suffix = f"_{idx:05d}.safetensors"
                fixed = [f for f in files if f.endswith(suffix)]
                if not fixed:
                    raise FileNotFoundError(
                        f"h3_continuous: no fixed slot {idx} in {c} (expected *{suffix})"
                    )
                return max(fixed, key=os.path.getmtime)
            return max(files, key=os.path.getmtime)
    raise FileNotFoundError(
        f"h3_continuous: {p!r} is neither a file nor a folder (also tried ComfyUI output directory)"
    )


class H3ContinuousLoadLatent:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent_path": ("STRING", {"default": "h3_continuous",
                    "tooltip": "Specific safetensors file or folder, absolute or relative to ComfyUI/output."}),
                "clip_index": ("INT", {"default": 1, "min": 0, "max": 99999,
                    "tooltip": "Clip to continue FROM. Generating clip 2: load 1. 0 = newest file (not retry-safe)."}),
            }
        }
    RETURN_TYPES = ("LATENT", "STRING", "STRING", "H3_CONTINUOUS_HANDOVER")
    RETURN_NAMES = ("latent", "resolved_path", "latent_info", "handover")
    FUNCTION = "load"
    CATEGORY = "H3 Continuous"
    DESCRIPTION = "Load a complete H3 AV latent and its optional saved automatic handover metadata."

    def load(self, latent_path, clip_index=1):
        path = _resolve_latent_path(latent_path, clip_index)
        tensors = st_load(path, device="cpu")
        if "video" not in tensors or "audio" not in tensors:
            raise ValueError("h3_continuous: file does not contain both 'video' and 'audio' tensors")
        video, audio = tensors["video"], tensors["audio"]
        if video.ndim != 5 or audio.ndim != 4:
            raise ValueError(f"h3_continuous: invalid shapes video={tuple(video.shape)}, audio={tuple(audio.shape)}")
        latent = {"samples": comfy.nested_tensor.NestedTensor((video, audio))}
        frame_count = pixel_frames(video.shape[2])

        metadata = {}
        try:
            with safe_open(path, framework="pt", device="cpu") as f:
                metadata = f.metadata() or {}
        except Exception as e:
            _LOG.warning("h3_continuous: could not read safetensors metadata from %s: %s", path, e)

        handover = {"available": False, "frame_count": frame_count}
        raw = metadata.get("handover_json")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    parsed["available"] = True
                    parsed["frame_count"] = frame_count
                    handover = parsed
            except Exception as e:
                _LOG.warning("h3_continuous: invalid handover metadata in %s: %s", path, e)

        if handover.get("available"):
            hinfo = (
                f"phase-aligned tail {handover.get('landing_tail_frames')} | "
                f"legacy tail {handover.get('legacy_landing_tail_frames', '?')} | "
                f"freeze={'yes' if handover.get('freeze_detected') else 'no'}"
            )
            if handover.get("no_lock_fallback_applied"):
                hinfo += (
                    f" | no-lock-fallback=yes "
                    f"(requested {handover.get('no_lock_fallback_requested_excluded_frames')} -> "
                    f"effective tail {handover.get('landing_tail_frames')})"
                )
        else:
            hinfo = "no auto handover metadata"
        saved_head = metadata.get("head_context_frames")
        head_info = f"saved head context {saved_head} | " if saved_head is not None else ""
        info = f"{frame_count} frames | video {tuple(video.shape)} | audio {tuple(audio.shape)} | {head_info}{hinfo}"
        _LOG.info("h3_continuous: loaded %s (%s)", path, info)
        return (latent, path, info, handover)


class H3ContinuousAnalyzeHandover:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "Decoded FULL rendered frames from the accepted H3 clip."}),
                "analysis_window": ("INT", {"default": 72, "min": 12, "max": 480, "step": 1,
                    "tooltip": "Inspect this many final frames first. If the whole window is already locked, analysis automatically expands backward."}),
                "freeze_hold": ("INT", {"default": 12, "min": 2, "max": 60, "step": 1,
                    "tooltip": "Minimum trailing lock length. Stable-tail consensus must persist for at least this many ending frames."}),
                "safety_margin": ("INT", {"default": 3, "min": 0, "max": 12, "step": 1,
                    "tooltip": "Pixel-frame safety before the detected lock. With safety_mode=fixed (recommended), this configured margin is always respected; adaptive preserves the older confidence-based behavior."}),
                "context_frames": (["5", "22", "39"], {"default": "22",
                    "tooltip": "Minimum motion/audio history. phase_aligned_extended may extend backward beyond this value to restore canonical phase-0 alignment."}),
                "analysis_size": ("INT", {"default": 192, "min": 64, "max": 512, "step": 16,
                    "tooltip": "Max edge used only for analysis. The rendered video is never resized or modified."}),
                "final_mean_diff_threshold": ("FLOAT", {"default": 0.0120, "min": 0.0001, "max": 0.03, "step": 0.0001,
                    "tooltip": "PRIMARY lock test: maximum mean blurred RGB difference between a candidate frame and the median stable-tail reference. Lower = stricter/later lock."}),
                "final_active_pixel_threshold": ("FLOAT", {"default": 0.025, "min": 0.001, "max": 0.2, "step": 0.001,
                    "tooltip": "PRIMARY lock test: per-pixel RGB-difference level used to decide which image areas differ from the median stable-tail reference."}),
                "max_final_active_area_percent": ("FLOAT", {"default": 3.0, "min": 0.05, "max": 20.0, "step": 0.05,
                    "tooltip": "PRIMARY lock test: at most this percentage of the image may differ materially from the median stable-tail reference."}),
                "transition_mean_diff_threshold": ("FLOAT", {"default": 0.0020, "min": 0.0001, "max": 0.03, "step": 0.0001,
                    "tooltip": "SECONDARY safety test: maximum mean luminance change between consecutive frames inside the detected final-frame lock."}),
                "transition_active_pixel_threshold": ("FLOAT", {"default": 0.010, "min": 0.001, "max": 0.2, "step": 0.001,
                    "tooltip": "SECONDARY safety test: per-pixel luminance change that counts as residual motion."}),
                "max_transition_active_area_percent": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 20.0, "step": 0.05,
                    "tooltip": "SECONDARY safety test: maximum visibly changing area allowed for an individual transition."}),
                "min_static_transition_percent": ("FLOAT", {"default": 70.0, "min": 50.0, "max": 100.0, "step": 1.0,
                    "tooltip": "ROBUST secondary gate: minimum percentage of transitions inside the final-frame-matching suffix that must be near-static. Isolated shimmer/outliers are allowed."}),
                "max_consecutive_motion_outliers": ("INT", {"default": 2, "min": 0, "max": 12, "step": 1,
                    "tooltip": "ROBUST secondary gate: maximum consecutive non-static transitions allowed inside an otherwise locked suffix. Prevents sustained real motion from being accepted."}),
                "final_reference_frames": ("INT", {"default": 15, "min": 3, "max": 31, "step": 2,
                    "tooltip": "STABLE-TAIL reference: build the final-state image from the pixel-wise median of this many ending frames instead of trusting one possibly shimmering last frame."}),
                "min_final_match_percent": ("FLOAT", {"default": 75.0, "min": 50.0, "max": 100.0, "step": 1.0,
                    "tooltip": "ROBUST primary gate: minimum percentage of frames in the candidate locked suffix that must match the median final-state reference."}),
                "max_consecutive_final_outliers": ("INT", {"default": 3, "min": 0, "max": 12, "step": 1,
                    "tooltip": "ROBUST primary gate: maximum consecutive final-state mismatches allowed inside the locked suffix. Candidate start itself must always match."}),
                "safety_mode": (["fixed", "adaptive"], {"default": "fixed",
                    "tooltip": "fixed (recommended): always keep safety_margin frames before the detected lock. adaptive: legacy v0.4.1-v0.4.5 behavior that can reduce the effective margin at high confidence."}),
            }
        }
    RETURN_TYPES = ("H3_CONTINUOUS_HANDOVER", "STRING", "BOOLEAN", "INT", "INT", "INT", "INT", "FLOAT")
    RETURN_NAMES = (
        "handover", "analysis_info", "freeze_detected", "freeze_start_frame",
        "ideal_handover_end_frame", "phase_aligned_handover_end_frame", "ignored_tail_frames", "confidence"
    )
    FUNCTION = "analyze"
    CATEGORY = "H3 Continuous"
    DESCRIPTION = "v0.4.6 calibrated Stable-Tail Consensus detector + phase-aligned-extended handover. Defaults are tuned for safe-early lock detection; fixed safety is recommended."

    def analyze(self, images, analysis_window=72, freeze_hold=12, safety_margin=3,
                context_frames="22", analysis_size=192,
                final_mean_diff_threshold=0.0120,
                final_active_pixel_threshold=0.025,
                max_final_active_area_percent=3.0,
                transition_mean_diff_threshold=0.0020,
                transition_active_pixel_threshold=0.010,
                max_transition_active_area_percent=1.0,
                min_static_transition_percent=70.0,
                max_consecutive_motion_outliers=2,
                final_reference_frames=15,
                min_final_match_percent=75.0,
                max_consecutive_final_outliers=3,
                safety_mode="fixed"):
        context_frames = int(context_frames)
        result = analyze_freeze_tail(
            images,
            analysis_window=analysis_window,
            freeze_hold=freeze_hold,
            safety_margin=safety_margin,
            context_frames=context_frames,
            analysis_size=analysis_size,
            final_mean_diff_threshold=final_mean_diff_threshold,
            final_active_pixel_threshold=final_active_pixel_threshold,
            max_final_active_area_percent=max_final_active_area_percent,
            transition_mean_diff_threshold=transition_mean_diff_threshold,
            transition_active_pixel_threshold=transition_active_pixel_threshold,
            max_transition_active_area_percent=max_transition_active_area_percent,
            min_static_transition_percent=min_static_transition_percent,
            max_consecutive_motion_outliers=max_consecutive_motion_outliers,
            final_reference_frames=final_reference_frames,
            min_final_match_percent=min_final_match_percent,
            max_consecutive_final_outliers=max_consecutive_final_outliers,
            safety_mode=safety_mode,
        )
        if result["freeze_detected"]:
            status = (
                f"FINAL-FRAME LOCK detected | starts frame {result['freeze_start_frame']} | "
                f"locked frames {result['trailing_locked_frames']} | "
                f"conservative ideal end {result['ideal_handover_end_frame']} | "
                f"phase-aligned target end {result['phase_aligned_target_end_frame']} "
                f"({result['safety_mode']} safety {result['phase_aware_effective_safety_margin']}) | "
                f"phase-aligned latent end {result['handover_end_frame']} | "
                f"phase-aligned ignored tail {result['landing_tail_frames']} | "
                f"phase-aligned context {result['phase_aligned_context_frames']} "
                f"(+{result['phase_aligned_context_extension_frames']} extension) | "
                f"v0.4.1 phase-aware end {result['phase_aware_handover_end_frame']} | "
                f"legacy-17 end {result['legacy_handover_end_frame']} | "
                f"legacy-17 tail {result['legacy_landing_tail_frames']} | "
                f"cutoff loss {result['phase_aligned_cutoff_loss_frames']} frame(s) | "
                f"final-match mean diff {result['lock_final_mean_diff']:.6f} | "
                f"final-match active area {result['lock_final_active_area_percent']:.3f}% | "
                f"stable-ref {result['final_reference_frames']} frames | "
                f"primary consensus {result['primary_final_match_ratio_percent']:.1f}% "
                f"({result['primary_final_match_count']}/{result['primary_final_match_frames']}; "
                f"outliers {result['primary_final_match_outliers']}, max streak {result['primary_final_max_consecutive_outliers']}) | "
                f"residual motion mean {result['lock_transition_mean_diff']:.6f} | "
                f"residual active area {result['lock_transition_active_area_percent']:.3f}% | "
                f"residual static {result['residual_static_ratio_percent']:.1f}% "
                f"({result['residual_static_transitions']}/{result['residual_total_transitions']}; "
                f"outliers {result['residual_motion_outliers']}, max streak {result['residual_max_consecutive_outliers']}) | "
                f"confidence {result['confidence']:.3f}"
            )
        else:
            status = (
                f"NO final-frame lock detected | reason {result['no_lock_reason']} | "
                f"primary final-match frames {result['primary_final_match_frames']} | "
                f"phase-aligned tail 0 | legacy tail 0 | "
                f"trailing final-match mean diff {result['lock_final_mean_diff']:.6f} | "
                f"trailing final-match active area {result['lock_final_active_area_percent']:.3f}% | "
                f"stable-ref {result['final_reference_frames']} frames | "
                f"primary consensus {result['primary_final_match_ratio_percent']:.1f}% "
                f"({result['primary_final_match_count']}/{result['primary_final_match_frames']}; "
                f"outliers {result['primary_final_match_outliers']}, max streak {result['primary_final_max_consecutive_outliers']}; "
                f"required >= {result['min_final_match_percent']:.1f}%, streak <= {result['max_consecutive_final_outliers']}) | "
                f"residual motion mean {result['lock_transition_mean_diff']:.6f} | "
                f"residual active area {result['lock_transition_active_area_percent']:.3f}% | "
                f"residual static {result['residual_static_ratio_percent']:.1f}% "
                f"({result['residual_static_transitions']}/{result['residual_total_transitions']}; "
                f"outliers {result['residual_motion_outliers']}, max streak {result['residual_max_consecutive_outliers']}; "
                f"required >= {result['min_static_transition_percent']:.1f}%, streak <= {result['max_consecutive_motion_outliers']})"
            )
        _LOG.info("h3_continuous: %s", status)
        return (
            result, status, bool(result["freeze_detected"]), int(result["freeze_start_frame"]),
            int(result["ideal_handover_end_frame"]), int(result["handover_end_frame"]),
            int(result["landing_tail_frames"]), float(result["confidence"])
        )


class H3ContinuousTrim:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "head_trim_frames": ("INT", {"default": 0, "min": 0, "max": 4096,
                    "tooltip": "OPTIONAL RENDERED-OUTPUT trim only. 0 keeps the complete generated head."}),
                "tail_trim_frames": ("INT", {"default": 0, "min": 0, "max": 4096,
                    "tooltip": "OPTIONAL RENDERED-OUTPUT trim only. 0 keeps the complete generated tail. This is independent of landing_tail_frames in the continuation node."}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
            },
            "optional": {
                "audio": ("AUDIO",),
            },
        }
    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "trim"
    CATEGORY = "H3 Continuous"
    DESCRIPTION = "Optional rendered-output trim only. It never changes the saved AV latent or the continuation node's latent handover window."

    def trim(self, images, head_trim_frames, tail_trim_frames, fps=24.0, audio=None):
        head = max(0, int(head_trim_frames))
        tail = max(0, int(tail_trim_frames))
        # True bypass: 0/0 must not touch either picture OR audio. In v0.1 the
        # audio branch still length-normalized even at 0/0, which made the node
        # technically non-transparent.
        if head == 0 and tail == 0:
            return (images, audio)
        total = int(images.shape[0])
        if head + tail >= total:
            raise ValueError(f"h3_continuous: head({head}) + tail({tail}) >= clip frames({total})")
        end = total - tail if tail else total
        out_images = images[head:end]

        out_audio = audio
        if audio is not None:
            waveform = audio["waveform"]
            sr = int(audio["sample_rate"])
            head_samples = int(round(head / float(fps) * sr))
            kept_frames = total - head - tail
            want_samples = int(round(kept_frames / float(fps) * sr))
            if head_samples >= waveform.shape[-1]:
                raise ValueError("h3_continuous: audio is shorter than requested head trim")
            waveform = waveform[..., head_samples:]
            # Exact duration match removes H3's small per-clip audio-grid rounding drift.
            waveform = waveform[..., :min(want_samples, waveform.shape[-1])]
            out_audio = {"waveform": waveform, "sample_rate": sr}
        return (out_images, out_audio)


class H3ContinuousLatentInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"latent": ("LATENT",)}}
    RETURN_TYPES = ("STRING", "INT", "INT", "INT")
    RETURN_NAMES = ("info", "frame_count", "video_steps", "audio_steps")
    FUNCTION = "inspect"
    CATEGORY = "H3 Continuous"

    def inspect(self, latent):
        video, audio = _streams_from_latent(latent)
        frames = pixel_frames(video.shape[2])
        info = (
            f"H3 AV latent | {frames} frames @ 24fps | "
            f"video {tuple(video.shape)} | audio {tuple(audio.shape)}"
        )
        return (info, frames, int(video.shape[2]), int(audio.shape[-1]))



# ---------------------------------------------------------------------------
# v1.0 release-facing nodes
# ---------------------------------------------------------------------------

class H3ContinuousStartV1(H3ContinuousStart):
    @classmethod
    def INPUT_TYPES(cls):
        base = H3ContinuousStart.INPUT_TYPES()
        required = dict(base["required"])
        required.pop("length", None)
        ordered = {}
        for name, spec in base["required"].items():
            if name == "length":
                ordered["duration"] = ("FLOAT", {
                    "default": 10.0, "min": 0.25, "max": 150.0, "step": 0.1,
                    "tooltip": "Requested duration in seconds at H3's native 24 fps. The actual clip snaps upward to H3's 17k+5 frame grid (10.0 s -> 243 frames ~= 10.125 s).",
                })
            else:
                ordered[name] = required[name]
        return {"required": ordered, "optional": dict(base.get("optional", {}))}

    CATEGORY = "H3 Continuous"
    DESCRIPTION = "v1.0 Clip 1: native FL2VA first/last anchors (both optional) with user-facing duration in seconds. Optional <Picture N> stills are Ref2VA."

    def build(self, clip, vae, prompt, width, height, duration, first_frame=None, last_frame=None,
              ref_image_size="match", reference_image=None, reference_images=None,
              song_audio_latent=None, song_audio_lock=0.0,
              reference_videos=None, reference_video_audios=None, reference_audios=None,
              audio_vae=None):
        requested_frames = duration_to_requested_frames(duration)
        frame_count, _, _ = temporal_shape(requested_frames)
        _LOG.info(
            "h3_continuous: duration %.3fs -> %s requested frames -> %s H3 frames (%.3fs)",
            float(duration), requested_frames, frame_count, frame_count / FPS,
        )
        return super().build(
            clip, vae, prompt, width, height, requested_frames, first_frame, last_frame,
            ref_image_size=ref_image_size, reference_image=reference_image,
            reference_images=reference_images, song_audio_latent=song_audio_latent,
            song_audio_lock=song_audio_lock,
            reference_videos=reference_videos, reference_video_audios=reference_video_audios,
            reference_audios=reference_audios, audio_vae=audio_vae,
        )


class H3ContinuousContinueV1(H3ContinuousContinue):
    @classmethod
    def INPUT_TYPES(cls):
        base = H3ContinuousContinue.INPUT_TYPES()
        required = dict(base["required"])
        ordered = {}
        for name, spec in base["required"].items():
            if name == "length":
                ordered["duration"] = ("FLOAT", {
                    "default": 10.0, "min": 0.25, "max": 150.0, "step": 0.1,
                    "tooltip": "Requested duration in seconds at H3's native 24 fps. The actual clip snaps upward to H3's 17k+5 frame grid (10.0 s -> 243 frames ~= 10.125 s).",
                })
            elif name == "alignment_mode":
                ordered[name] = ([
                    "phase_aligned_extended",
                    "phase_aware (Legacy)",
                    "legacy_17 (Legacy)",
                ], {
                    "default": "phase_aligned_extended",
                    "tooltip": "phase_aligned_extended is the v1.0 recommended direct-latent handover. phase_aware and legacy_17 remain only for reproducing older workflows / A-B diagnostics.",
                })
            else:
                ordered[name] = required[name]
        return {"required": ordered, "optional": dict(base.get("optional", {}))}

    CATEGORY = "H3 Continuous"
    DESCRIPTION = "v1.0 Clip 2+: phase-aligned direct video+audio latent continuation with duration in seconds. Legacy alignment modes remain available for reproducibility."

    def build(self, clip, vae, previous_latent, prompt, width, height, duration,
              context_frames="22", handover_mode="auto", alignment_mode="phase_aligned_extended",
              manual_landing_tail_frames=34, ref_image_size="match", freeze_overlap=True,
              overlap_soft_steps=2, handover=None,
              last_frame=None, reference_image=None, reference_images=None, end_latent=None,
              song_audio_latent=None, identity_frame=None, song_audio_lock=0.0,
              reference_videos=None, reference_video_audios=None, reference_audios=None,
              audio_vae=None):
        requested_frames = duration_to_requested_frames(duration)
        frame_count, _, _ = temporal_shape(requested_frames)
        internal_alignment = normalize_alignment_mode(alignment_mode)
        _LOG.info(
            "h3_continuous: duration %.3fs -> %s requested frames -> %s H3 frames (%.3fs)",
            float(duration), requested_frames, frame_count, frame_count / FPS,
        )
        return super().build(
            clip, vae, previous_latent, prompt, width, height, requested_frames,
            context_frames=context_frames, handover_mode=handover_mode,
            alignment_mode=internal_alignment,
            manual_landing_tail_frames=manual_landing_tail_frames,
            ref_image_size=ref_image_size, freeze_overlap=freeze_overlap,
            overlap_soft_steps=overlap_soft_steps, handover=handover,
            last_frame=last_frame, reference_image=reference_image,
            reference_images=reference_images, end_latent=end_latent,
            song_audio_latent=song_audio_latent, identity_frame=identity_frame,
            song_audio_lock=song_audio_lock,
            reference_videos=reference_videos, reference_video_audios=reference_video_audios,
            reference_audios=reference_audios, audio_vae=audio_vae,
        )


class H3ContinuousAnalyzeHandoverV1(H3ContinuousAnalyzeHandover):
    @classmethod
    def INPUT_TYPES(cls):
        base = H3ContinuousAnalyzeHandover.INPUT_TYPES()
        old = dict(base["required"])
        ordered = {
            "images": old.pop("images"),
            "preset": (["Balanced", "Motion Safe", "Custom"], {
                "default": "Balanced",
                "tooltip": "Balanced = validated v1.0 detector settings. Motion Safe = same validated detector with a larger fixed pre-lock safety margin. Custom = use the advanced values below.",
            }),
        }
        for name, spec in old.items():
            if name == "safety_mode":
                ordered[name] = (["fixed", "adaptive (Legacy)"], {
                    "default": "fixed",
                    "tooltip": "Used only by Custom. fixed is recommended. adaptive (Legacy) can reduce safety at high confidence and is kept only for old workflow reproduction.",
                })
            else:
                kind, opts = spec
                opts = dict(opts)
                tip = opts.get("tooltip", "")
                opts["tooltip"] = ("Advanced: used only when preset = Custom. " + tip).strip()
                ordered[name] = (kind, opts)
        return {"required": ordered}

    CATEGORY = "H3 Continuous"
    DESCRIPTION = "v1.0 Stable-Tail Consensus analyzer. Balanced is the validated default; Motion Safe keeps the same detector and increases the fixed pre-lock margin."

    def analyze(self, images, preset="Balanced", analysis_window=72, freeze_hold=12, safety_margin=3,
                context_frames="22", analysis_size=192,
                final_mean_diff_threshold=0.0120,
                final_active_pixel_threshold=0.025,
                max_final_active_area_percent=3.0,
                transition_mean_diff_threshold=0.0020,
                transition_active_pixel_threshold=0.010,
                max_transition_active_area_percent=1.0,
                min_static_transition_percent=70.0,
                max_consecutive_motion_outliers=2,
                final_reference_frames=15,
                min_final_match_percent=75.0,
                max_consecutive_final_outliers=3,
                safety_mode="fixed"):
        custom = {
            "analysis_window": analysis_window,
            "freeze_hold": freeze_hold,
            "safety_margin": safety_margin,
            "analysis_size": analysis_size,
            "final_mean_diff_threshold": final_mean_diff_threshold,
            "final_active_pixel_threshold": final_active_pixel_threshold,
            "max_final_active_area_percent": max_final_active_area_percent,
            "transition_mean_diff_threshold": transition_mean_diff_threshold,
            "transition_active_pixel_threshold": transition_active_pixel_threshold,
            "max_transition_active_area_percent": max_transition_active_area_percent,
            "min_static_transition_percent": min_static_transition_percent,
            "max_consecutive_motion_outliers": max_consecutive_motion_outliers,
            "final_reference_frames": final_reference_frames,
            "min_final_match_percent": min_final_match_percent,
            "max_consecutive_final_outliers": max_consecutive_final_outliers,
            "safety_mode": normalize_safety_mode(safety_mode),
        }
        preset_id, effective = resolve_freeze_settings(preset, custom)
        _LOG.info(
            "h3_continuous: freeze preset=%s | fixed safety margin=%s | detector thresholds=%s",
            preset_id, effective["safety_margin"],
            "validated-balanced" if preset_id != "custom" else "custom",
        )
        out = list(super().analyze(
            images,
            analysis_window=effective["analysis_window"],
            freeze_hold=effective["freeze_hold"],
            safety_margin=effective["safety_margin"],
            context_frames=context_frames,
            analysis_size=effective["analysis_size"],
            final_mean_diff_threshold=effective["final_mean_diff_threshold"],
            final_active_pixel_threshold=effective["final_active_pixel_threshold"],
            max_final_active_area_percent=effective["max_final_active_area_percent"],
            transition_mean_diff_threshold=effective["transition_mean_diff_threshold"],
            transition_active_pixel_threshold=effective["transition_active_pixel_threshold"],
            max_transition_active_area_percent=effective["max_transition_active_area_percent"],
            min_static_transition_percent=effective["min_static_transition_percent"],
            max_consecutive_motion_outliers=effective["max_consecutive_motion_outliers"],
            final_reference_frames=effective["final_reference_frames"],
            min_final_match_percent=effective["min_final_match_percent"],
            max_consecutive_final_outliers=effective["max_consecutive_final_outliers"],
            safety_mode=effective["safety_mode"],
        ))
        result = out[0]
        result["release_preset"] = preset_id
        result["release_version"] = "1.0.0"
        label = {"balanced": "Balanced", "motion_safe": "Motion Safe", "custom": "Custom"}[preset_id]
        out[1] = f"preset {label} | {out[1]}"
        return tuple(out)


class H3ContinuousStitchOutputV1:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "Decoded FULL rendered frames for the current H3 clip."}),
                "output_mode": (["Full", "Stitch Ready"], {
                    "default": "Full",
                    "tooltip": "Full is a true bypass. Stitch Ready removes the reused head context (clip 2+) and the tail after this clip's exact phase-aligned latent handover boundary.",
                }),
            },
            "optional": {
                "handover": ("H3_CONTINUOUS_HANDOVER", {
                    "tooltip": "Connect the current clip's Auto Handover Analyzer output. Required for Stitch Ready so the tail matches the exact latent cutoff.",
                }),
                "audio": ("AUDIO",),
                "head_context_frames": ("INT", {
                    "forceInput": True,
                    "tooltip": "Clip 1: leave unconnected (0). Clip 2+: connect actual_head_context_frames from H3 Continuous - Continue from Latent v1.0.",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "INT", "INT")
    RETURN_NAMES = ("images", "audio", "trim_info", "head_trim_frames", "tail_trim_frames")
    FUNCTION = "prepare"
    CATEGORY = "H3 Continuous"
    DESCRIPTION = "v1.0 rendered AV output helper. Full preserves the complete render; Stitch Ready removes dynamic continuation overlap and the exact phase-aligned freeze tail for direct concatenation."

    def prepare(self, images, output_mode="Full", head_context_frames=0, handover=None, audio=None):
        total = int(images.shape[0])
        plan = stitch_trim_plan(total, output_mode, head_context_frames, handover)
        head = int(plan["head_trim_frames"])
        tail = int(plan["tail_trim_frames"])
        if head == 0 and tail == 0:
            out_images, out_audio = images, audio
        else:
            out_images, out_audio = H3ContinuousTrim().trim(
                images, head, tail, fps=FPS, audio=audio
            )
        info = (
            f"{plan['mode']} | source {total} frames | head trim {head} | tail trim {tail} | "
            f"kept {int(out_images.shape[0])} frames @ {FPS:g}fps"
        )
        if "handover_end_frame" in plan:
            info += f" | phase-aligned source end frame {plan['handover_end_frame']}"
        if plan["mode"] == "stitch_ready" and isinstance(handover, dict) and handover.get("no_lock_fallback_applied"):
            info += (
                f" | no-lock-fallback=yes "
                f"(requested exclude {handover.get('no_lock_fallback_requested_excluded_frames')}, "
                f"effective tail {handover.get('landing_tail_frames')})"
            )
        _LOG.info("h3_continuous: output %s", info)
        return (out_images, out_audio, info, head, tail)


# ---------------------------------------------------------------------------
# v1.2 release-facing nodes
# ---------------------------------------------------------------------------

class H3ContinuousStartV11(H3ContinuousStartV1):
    CATEGORY = "Herrgotts H3 Infinite Continuation Suite"
    DESCRIPTION = "v1.2 Clip 1: native FL2VA first/last anchors (both optional) with Duration (Seconds). Optional <Picture N> stills are Ref2VA."


class H3ContinuousContinueV11(H3ContinuousContinueV1):
    CATEGORY = "Herrgotts H3 Infinite Continuation Suite"
    DESCRIPTION = "v1.2 Clip 2+: phase-aligned direct video+audio latent continuation. Auto handover consumes lock or no-lock-fallback metadata from the v1.2 analyzer."


def _format_handover_status_v11(result):
    if result["freeze_detected"]:
        return (
            f"FINAL-FRAME LOCK detected | starts frame {result['freeze_start_frame']} | "
            f"locked frames {result['trailing_locked_frames']} | "
            f"conservative ideal end {result['ideal_handover_end_frame']} | "
            f"phase-aligned target end {result['phase_aligned_target_end_frame']} "
            f"({result['safety_mode']} safety {result['phase_aware_effective_safety_margin']}) | "
            f"phase-aligned latent end {result['handover_end_frame']} | "
            f"phase-aligned ignored tail {result['landing_tail_frames']} | "
            f"phase-aligned context {result['phase_aligned_context_frames']} "
            f"(+{result['phase_aligned_context_extension_frames']} extension) | "
            f"cutoff loss {result['phase_aligned_cutoff_loss_frames']} frame(s) | "
            f"final-match mean diff {result['lock_final_mean_diff']:.6f} | "
            f"final-match active area {result['lock_final_active_area_percent']:.3f}% | "
            f"stable-ref {result['final_reference_frames']} frames | "
            f"primary consensus {result['primary_final_match_ratio_percent']:.1f}% "
            f"({result['primary_final_match_count']}/{result['primary_final_match_frames']}; "
            f"outliers {result['primary_final_match_outliers']}, max streak {result['primary_final_max_consecutive_outliers']}) | "
            f"residual motion mean {result['lock_transition_mean_diff']:.6f} | "
            f"residual active area {result['lock_transition_active_area_percent']:.3f}% | "
            f"residual static {result['residual_static_ratio_percent']:.1f}% "
            f"({result['residual_static_transitions']}/{result['residual_total_transitions']}; "
            f"outliers {result['residual_motion_outliers']}, max streak {result['residual_max_consecutive_outliers']}) | "
            f"confidence {result['confidence']:.3f}"
        )

    fallback = ""
    if result.get("no_lock_fallback_applied"):
        fallback = (
            f" | NO-LOCK FALLBACK applied: exclude final "
            f"{result['no_lock_fallback_requested_excluded_frames']} frame(s) before phase alignment | "
            f"fallback target end {result['no_lock_fallback_target_end_frame']} | "
            f"phase-aligned latent end {result['handover_end_frame']} | "
            f"effective ignored tail {result['landing_tail_frames']} | "
            f"phase-aligned context {result['phase_aligned_context_frames']} "
            f"(+{result['phase_aligned_context_extension_frames']} extension) | "
            f"cutoff loss {result['phase_aligned_cutoff_loss_frames']} frame(s)"
        )
    return (
        f"NO final-frame lock detected | reason {result['no_lock_reason']} | "
        f"primary final-match frames {result['primary_final_match_frames']} | "
        f"trailing final-match mean diff {result['lock_final_mean_diff']:.6f} | "
        f"trailing final-match active area {result['lock_final_active_area_percent']:.3f}% | "
        f"stable-ref {result['final_reference_frames']} frames | "
        f"primary consensus {result['primary_final_match_ratio_percent']:.1f}% "
        f"({result['primary_final_match_count']}/{result['primary_final_match_frames']}; "
        f"outliers {result['primary_final_match_outliers']}, max streak {result['primary_final_max_consecutive_outliers']}; "
        f"required >= {result['min_final_match_percent']:.1f}%, streak <= {result['max_consecutive_final_outliers']}) | "
        f"residual motion mean {result['lock_transition_mean_diff']:.6f} | "
        f"residual active area {result['lock_transition_active_area_percent']:.3f}% | "
        f"residual static {result['residual_static_ratio_percent']:.1f}% "
        f"({result['residual_static_transitions']}/{result['residual_total_transitions']}; "
        f"outliers {result['residual_motion_outliers']}, max streak {result['residual_max_consecutive_outliers']}; "
        f"required >= {result['min_static_transition_percent']:.1f}%, streak <= {result['max_consecutive_motion_outliers']})"
        + fallback
    )


class H3ContinuousAnalyzeHandoverV11(H3ContinuousAnalyzeHandoverV1):
    @classmethod
    def INPUT_TYPES(cls):
        base = H3ContinuousAnalyzeHandover.INPUT_TYPES()
        old = dict(base["required"])
        images = old.pop("images")
        # Custom starts from the same calibrated release baseline as Balanced.
        kind, opts = old["freeze_hold"]
        opts = dict(opts)
        opts["default"] = 8
        old["freeze_hold"] = (kind, opts)
        ordered = {
            "images": images,
            "preset": (["Balanced", "Motion Safe", "Custom"], {
                "default": "Balanced",
                "tooltip": "Balanced = validated detector with freeze_hold 8 and fixed 3-frame safety. Motion Safe = same detector with 6-frame safety. Custom reveals the advanced controls.",
            }),
        }
        for name, spec in old.items():
            if name == "safety_mode":
                ordered[name] = (["fixed", "adaptive (Legacy)"], {
                    "default": "fixed",
                    "tooltip": "Custom only. fixed is recommended; adaptive (Legacy) can reduce safety at high confidence.",
                    "advanced": True,
                })
            else:
                kind, opts = spec
                opts = dict(opts)
                tip = opts.get("tooltip", "")
                opts["tooltip"] = ("Custom only. " + tip).strip()
                # Native ComfyUI advanced-widget metadata. The frontend
                # extension additionally ties visibility to preset=Custom.
                opts["advanced"] = True
                ordered[name] = (kind, opts)
        return {"required": ordered}

    CATEGORY = "Herrgotts H3 Infinite Continuation Suite"
    DESCRIPTION = "v1.2 Auto Handover. Balanced/Motion Safe use freeze_hold=8. If no lock is found, freeze_hold-1 ending frames are excluded before phase-aligned latent cutoff selection."

    def analyze(self, images, preset="Balanced", analysis_window=72, freeze_hold=8, safety_margin=3,
                context_frames="22", analysis_size=192,
                final_mean_diff_threshold=0.0120,
                final_active_pixel_threshold=0.025,
                max_final_active_area_percent=3.0,
                transition_mean_diff_threshold=0.0020,
                transition_active_pixel_threshold=0.010,
                max_transition_active_area_percent=1.0,
                min_static_transition_percent=70.0,
                max_consecutive_motion_outliers=2,
                final_reference_frames=15,
                min_final_match_percent=75.0,
                max_consecutive_final_outliers=3,
                safety_mode="fixed"):
        context_frames = int(context_frames)
        custom = {
            "analysis_window": analysis_window,
            "freeze_hold": freeze_hold,
            "safety_margin": safety_margin,
            "analysis_size": analysis_size,
            "final_mean_diff_threshold": final_mean_diff_threshold,
            "final_active_pixel_threshold": final_active_pixel_threshold,
            "max_final_active_area_percent": max_final_active_area_percent,
            "transition_mean_diff_threshold": transition_mean_diff_threshold,
            "transition_active_pixel_threshold": transition_active_pixel_threshold,
            "max_transition_active_area_percent": max_transition_active_area_percent,
            "min_static_transition_percent": min_static_transition_percent,
            "max_consecutive_motion_outliers": max_consecutive_motion_outliers,
            "final_reference_frames": final_reference_frames,
            "min_final_match_percent": min_final_match_percent,
            "max_consecutive_final_outliers": max_consecutive_final_outliers,
            "safety_mode": normalize_safety_mode(safety_mode),
        }
        preset_id, effective = resolve_freeze_settings(preset, custom)
        _LOG.info(
            "h3_continuous: v1.2 freeze preset=%s | freeze_hold=%s | fixed safety margin=%s | detector thresholds=%s",
            preset_id, effective["freeze_hold"], effective["safety_margin"],
            "validated-balanced" if preset_id != "custom" else "custom",
        )
        result = analyze_freeze_tail(
            images,
            analysis_window=effective["analysis_window"],
            freeze_hold=effective["freeze_hold"],
            safety_margin=effective["safety_margin"],
            context_frames=context_frames,
            analysis_size=effective["analysis_size"],
            final_mean_diff_threshold=effective["final_mean_diff_threshold"],
            final_active_pixel_threshold=effective["final_active_pixel_threshold"],
            max_final_active_area_percent=effective["max_final_active_area_percent"],
            transition_mean_diff_threshold=effective["transition_mean_diff_threshold"],
            transition_active_pixel_threshold=effective["transition_active_pixel_threshold"],
            max_transition_active_area_percent=effective["max_transition_active_area_percent"],
            min_static_transition_percent=effective["min_static_transition_percent"],
            max_consecutive_motion_outliers=effective["max_consecutive_motion_outliers"],
            final_reference_frames=effective["final_reference_frames"],
            min_final_match_percent=effective["min_final_match_percent"],
            max_consecutive_final_outliers=effective["max_consecutive_final_outliers"],
            safety_mode=effective["safety_mode"],
        )
        result = apply_no_lock_fallback(
            result, freeze_hold=effective["freeze_hold"], context_frames=context_frames
        )
        result["release_preset"] = preset_id
        result["release_version"] = "1.2.1"
        result["version"] = max(int(result.get("version", 0)), 10)
        status = _format_handover_status_v11(result)
        label = {"balanced": "Balanced", "motion_safe": "Motion Safe", "custom": "Custom"}[preset_id]
        status = f"preset {label} | {status}"
        _LOG.info("h3_continuous: %s", status)
        return (
            result, status, bool(result["freeze_detected"]), int(result["freeze_start_frame"]),
            int(result["ideal_handover_end_frame"]), int(result["handover_end_frame"]),
            int(result["landing_tail_frames"]), float(result["confidence"])
        )


class H3ContinuousStitchOutputV11(H3ContinuousStitchOutputV1):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "Decoded FULL rendered frames for the current H3 clip."}),
                "output_mode": (["Full", "Stitch Ready", "Final Clip"], {
                    "default": "Full",
                    "tooltip": "Full keeps the complete render. Stitch Ready removes reused head context and the tail after the effective handover boundary. Final Clip removes only reused head context so the last segment keeps its complete final-keyframe landing.",
                }),
            },
            "optional": {
                "handover": ("H3_CONTINUOUS_HANDOVER", {
                    "tooltip": "Required for Stitch Ready tail trimming. Final Clip ignores the tail cutoff but the analyzer can remain connected for saved metadata or later extension.",
                }),
                "audio": ("AUDIO",),
                "head_context_frames": ("INT", {
                    "forceInput": True,
                    "tooltip": "Clip 1: leave unconnected (0). Clip 2+: connect actual_head_context_frames from Continue from Latent. Final Clip uses this head trim but keeps the full tail.",
                }),
            },
        }

    CATEGORY = "Herrgotts H3 Infinite Continuation Suite"
    DESCRIPTION = "v1.2 rendered AV output helper. Full keeps everything; Stitch Ready removes continuation overlap plus the effective freeze-safe tail; Final Clip removes only the reused head so the last segment can reach its complete Last Frame landing."



class H3ContinuousSeamlessJoinV11:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "previous_images": ("IMAGE", {"tooltip": "Already prepared/combined previous timeline. For the first join, Clip 1 Stitch Ready is fine."}),
                "next_images": ("IMAGE", {"tooltip": "FULL decoded render of the next clip. Its reused context head is needed for the context-aligned seam."}),
                "next_output_mode": (["Stitch Ready", "Final Clip"], {
                    "default": "Stitch Ready",
                    "tooltip": "Intermediate next clip = Stitch Ready. Current last clip = Final Clip so its complete ending is preserved.",
                }),
                "next_head_context_frames": ("INT", {"forceInput": True,
                    "tooltip": "Connect actual_head_context_frames from the next Continue from Latent node."}),
                "video_crossfade_frames": ("INT", {"default": 4, "min": 0, "max": 16, "step": 1,
                    "tooltip": "Short context-aligned video blend after Safe Tail Bridge. 4 frames is the recommended default; 0 disables the blend."}),
                "audio_crossfade_ms": ("FLOAT", {"default": 15.0, "min": 0.0, "max": 100.0, "step": 1.0,
                    "tooltip": "Short audio de-click crossfade. 15 ms is the tested default; keep it short to reduce phasing/doubled transients."}),
                "luminance_match": ("BOOLEAN", {"default": False,
                    "tooltip": "Experimental fallback only. Safe Tail Bridge is the release default; enable luminance matching only if a persistent brightness seam remains."}),
                "luminance_fade_frames": ("INT", {"default": 16, "min": 0, "max": 96, "step": 1,
                    "tooltip": "Experimental luminance-match fade length. Ignored when luminance_match is off."}),
                "max_luminance_correction_percent": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 25.0, "step": 0.5,
                    "tooltip": "Experimental luminance-match safety clamp. Ignored when luminance_match is off."}),
                "max_safe_tail_bridge_frames": ("INT", {"default": 2, "min": 0, "max": 4, "step": 1,
                    "tooltip": "Recommended: 2. Reuses only detector-approved rendered frames lost to phase alignment; never borrows from the freeze safety margin."}),
            },
            "optional": {
                "previous_audio": ("AUDIO",),
                "next_audio": ("AUDIO",),
                "next_handover": ("H3_CONTINUOUS_HANDOVER", {
                    "tooltip": "Required when next_output_mode is Stitch Ready so the next clip's freeze-safe tail is removed."}),
                "previous_full_images": ("IMAGE", {
                    "tooltip": "Optional FULL decoded render of the previous individual clip. Connect this together with previous_handover to enable Safe Tail Bridge."}),
                "previous_handover": ("H3_CONTINUOUS_HANDOVER", {
                    "tooltip": "Previous clip handover metadata. Together with previous_full_images it exposes up to 1-2 safe rendered frames that latent phase alignment had to discard."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING")
    RETURN_NAMES = ("images", "audio", "join_info")
    FUNCTION = "join"
    CATEGORY = "Herrgotts H3 Infinite Continuation Suite"
    DESCRIPTION = "v1.2 context-aligned rendered AV join. Safe Tail Bridge replaces the first few potentially unstable continuation frames with detector-approved pixels from the previous clip; video gets a short corresponding-context blend and audio keeps the tested 15 ms de-click crossfade."

    def join(self, previous_images, next_images, next_output_mode="Stitch Ready",
             next_head_context_frames=22, video_crossfade_frames=4, audio_crossfade_ms=15.0,
             luminance_match=False, luminance_fade_frames=16, max_luminance_correction_percent=10.0,
             max_safe_tail_bridge_frames=2, previous_audio=None, next_audio=None, next_handover=None,
             previous_full_images=None, previous_handover=None):
        previous_frames = int(previous_images.shape[0])
        next_total = int(next_images.shape[0])
        plan = stitch_trim_plan(
            next_total, next_output_mode, int(next_head_context_frames), next_handover
        )
        audio_head = int(plan["head_trim_frames"])
        tail = int(plan["tail_trim_frames"])

        bridge_images = previous_images[:0]
        bridge_stats = safe_tail_bridge_plan(previous_handover, int(max_safe_tail_bridge_frames))
        bridge = int(bridge_stats["safe_tail_bridge_frames"])
        if bridge > 0:
            if previous_full_images is None:
                # Missing pixel source: fail safe to the old seam rather than invent frames.
                bridge = 0
                bridge_stats = safe_tail_bridge_plan(None, 0)
            else:
                bridge_images, bridge_stats = extract_safe_tail_bridge_images(
                    previous_full_images, previous_handover, int(max_safe_tail_bridge_frames)
                )
                bridge = int(bridge_images.shape[0])

        # The bridge takes video time positions that would otherwise be the first
        # generated body frames of the next clip. Keep the audio boundary unchanged.
        max_bridge_for_next = max(0, next_total - tail - audio_head - 1)
        if bridge > max_bridge_for_next:
            bridge = max_bridge_for_next
            bridge_images = bridge_images[:bridge]
        previous_video = previous_images
        if bridge > 0:
            bridge_images = bridge_images.to(previous_images.device, previous_images.dtype)
            previous_video = torch.cat((previous_images, bridge_images), dim=0)
        video_head = audio_head + bridge

        out_images, vstats = context_aligned_video_join(
            previous_video, next_images, video_head, tail, int(video_crossfade_frames),
            luminance_match=bool(luminance_match),
            luminance_fade_frames=int(luminance_fade_frames),
            max_luminance_correction_percent=float(max_luminance_correction_percent),
        )
        out_audio, astats = context_aligned_audio_join(
            previous_audio, next_audio,
            previous_output_frames=previous_frames,
            next_total_frames=next_total,
            next_head_context_frames=audio_head,
            next_tail_trim_frames=tail,
            crossfade_ms=float(audio_crossfade_ms),
            fps=FPS,
        )
        # Bridge adds N previous pixels and removes N next pixels, so the video
        # timeline must still equal the audio/hard-stitch timeline exactly.
        expected_frames = previous_frames + next_total - audio_head - tail
        if int(out_images.shape[0]) != expected_frames:
            raise ValueError(
                f"safe-tail bridge changed timeline length: output {int(out_images.shape[0])}, expected {expected_frames}"
            )

        luma_text = "off"
        if vstats.get("luminance_match_enabled"):
            luma_text = (
                f"gain {vstats.get('luminance_applied_gain', 1.0):.4f} "
                f"(measured {vstats.get('luminance_measured_gain', 1.0):.4f}, "
                f"fade {vstats.get('luminance_fade_frames', 0)}f, "
                f"clamped={'yes' if vstats.get('luminance_clamped') else 'no'})"
            )
        bridge_text = f"{bridge}f"
        available = int(bridge_stats.get("safe_tail_bridge_available_frames", 0))
        if available > bridge:
            bridge_text += f"/{available}f available"
        info = (
            f"context-aligned join | previous {previous_frames} frames | next source {next_total} frames | "
            f"next audio head {audio_head} | video head {video_head} | safe tail bridge {bridge_text} | "
            f"next tail {tail} | video crossfade {vstats['video_crossfade_frames']} frame(s) | "
            f"boundary luminance {luma_text} | audio crossfade {astats.get('audio_crossfade_samples', 0)} samples "
            f"(~{astats.get('audio_crossfade_ms_effective', 0)} ms) | output {int(out_images.shape[0])} frames"
        )
        _LOG.info("h3_continuous: %s", info)
        return (out_images, out_audio, info)

def _read_safetensors_metadata(path):
    metadata = {}
    try:
        with safe_open(path, framework="pt", device="cpu") as f:
            metadata = f.metadata() or {}
    except Exception as e:
        _LOG.warning("h3_continuous: could not read safetensors metadata from %s: %s", path, e)
    handover = None
    raw = metadata.get("handover_json")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed["available"] = True
                handover = parsed
        except Exception as e:
            _LOG.warning("h3_continuous: invalid handover metadata in %s: %s", path, e)
    return metadata, handover


def _saved_chain_base(prefix):
    p = (prefix or "").strip().strip('"').strip("'")
    if not p:
        p = "h3_continuous/clip"
    if p.lower().endswith(".safetensors"):
        p = p[:-len(".safetensors")]
    if os.path.isabs(p):
        return p
    return os.path.join(folder_paths.get_output_directory(), p)


def _saved_chain_file(prefix, clip_index):
    base = _saved_chain_base(prefix)
    exact = f"{base}_{int(clip_index):05d}.safetensors"
    if os.path.isfile(exact):
        return exact
    # Folder fallback for users who pass h3_continuous rather than h3_continuous/clip.
    if os.path.isdir(base):
        suffix = f"_{int(clip_index):05d}.safetensors"
        matches = [os.path.join(base, f) for f in os.listdir(base) if f.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"h3_continuous: multiple saved chains contain clip {clip_index} in {base}; "
                "use the exact latent prefix, e.g. h3_continuous/clip"
            )
    raise FileNotFoundError(f"h3_continuous: saved chain clip {clip_index} not found at {exact}")


def _discover_saved_last_clip(prefix, first_clip):
    import re
    base = _saved_chain_base(prefix)
    directory = os.path.dirname(base)
    stem = os.path.basename(base)
    if os.path.isdir(base):
        directory = base
        pattern = re.compile(r".*_(\d{5})\.safetensors$")
    else:
        pattern = re.compile(re.escape(stem) + r"_(\d{5})\.safetensors$")
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"h3_continuous: saved chain directory does not exist: {directory}")
    indices = []
    for name in os.listdir(directory):
        m = pattern.fullmatch(name)
        if m:
            idx = int(m.group(1))
            if idx >= int(first_clip):
                indices.append(idx)
    if not indices:
        raise FileNotFoundError(f"h3_continuous: no saved chain clips found for prefix {prefix!r}")
    return max(indices)


def _saved_tail_trim(frame_count, handover, is_final):
    if is_final:
        return 0
    if not isinstance(handover, dict) or not handover.get("available"):
        raise ValueError("intermediate saved clips require handover metadata for freeze-safe stitching")
    meta_frames = int(handover.get("frame_count", frame_count))
    if meta_frames != int(frame_count):
        raise ValueError(f"saved handover frame_count {meta_frames} != latent frame_count {frame_count}")
    end_frame = int(handover.get("handover_end_frame", frame_count - 1))
    tail = int(frame_count) - (end_frame + 1)
    stored = handover.get("landing_tail_frames")
    if stored is not None and int(stored) != tail:
        raise ValueError("saved handover metadata has inconsistent landing_tail_frames")
    return max(0, tail)


def _decode_saved_video_only(video_vae, video_latent):
    images = video_vae.decode(video_latent)
    if len(images.shape) == 5:
        images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
    if images.ndim != 4:
        raise ValueError(f"unexpected decoded video shape {tuple(images.shape)}")
    return images


def _decode_audio_only(audio_vae, audio_latent):
    waveform = audio_vae.decode(audio_latent).movedim(-1, 1)
    std = torch.std(waveform, dim=[1, 2], keepdim=True) * 5.0
    std[std < 1.0] = 1.0
    waveform = waveform / std
    sr = int(getattr(audio_vae, "audio_sample_rate_output", getattr(audio_vae, "audio_sample_rate", 44100)))
    return {"waveform": waveform, "sample_rate": sr}


def _decode_saved_av(video_vae, audio_vae, video_latent, audio_latent):
    images = _decode_saved_video_only(video_vae, video_latent)
    return images, _decode_audio_only(audio_vae, audio_latent)


class H3ContinuousStitchSavedChainV11:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_vae": ("VAE", {"tooltip": "MiniMax H3 Video VAE used to decode the saved full video latents."}),
                "audio_vae": ("VAE", {"tooltip": "MiniMax H3 Audio VAE used to decode the saved full audio latents."}),
                "latent_prefix": ("STRING", {"default": "h3_continuous/clip",
                    "tooltip": "Saved latent prefix relative to ComfyUI/output, e.g. h3_continuous/clip for clip_00001.safetensors, clip_00002.safetensors, ..."}),
                "first_clip": ("INT", {"default": 1, "min": 1, "max": 99999}),
                "last_clip": ("INT", {"default": 0, "min": 0, "max": 99999,
                    "tooltip": "0 = automatically use the highest numbered clip for this prefix."}),
                "filename_prefix": ("STRING", {"default": "video/Herrgotts_H3_Infinite_Stitched"}),
                "video_crossfade_frames": ("INT", {"default": 4, "min": 0, "max": 16, "step": 1,
                    "tooltip": "Context-aligned video crossfade. Recommended: 4 frames."}),
                "audio_crossfade_ms": ("FLOAT", {"default": 15.0, "min": 0.0, "max": 100.0, "step": 1.0,
                    "tooltip": "Short audio de-click crossfade. Recommended: 15 ms."}),
                "luminance_match": ("BOOLEAN", {"default": False,
                    "tooltip": "Experimental fallback only. Safe Tail Bridge is the release default; enable only if a persistent brightness seam remains."}),
                "luminance_fade_frames": ("INT", {"default": 16, "min": 0, "max": 96, "step": 1,
                    "tooltip": "Frames over which the temporary brightness correction returns to native luminance. Recommended: 16."}),
                "max_luminance_correction_percent": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 25.0, "step": 0.5,
                    "tooltip": "Safety clamp for automatic brightness correction. Recommended: 10%."}),
                "crf": ("INT", {"default": 18, "min": 0, "max": 51, "step": 1,
                    "tooltip": "H.264 quality. Lower = larger/higher quality. 18 is a high-quality default."}),
                "max_safe_tail_bridge_frames": ("INT", {"default": 2, "min": 0, "max": 4, "step": 1,
                    "tooltip": "Recommended: 2. Keeps only detector-approved rendered frames lost to phase alignment, then skips the same number of early video frames in the next clip."}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("video_path", "stitch_info")
    FUNCTION = "stitch"
    OUTPUT_NODE = True
    CATEGORY = "Herrgotts H3 Infinite Continuation Suite"
    DESCRIPTION = "v1.2 memory-bounded saved-chain stitcher. Uses Safe Tail Bridge plus short context-aligned video/audio seam smoothing and encodes directly to MP4 so peak memory does not grow with chain length."

    def stitch(self, video_vae, audio_vae, latent_prefix="h3_continuous/clip",
               first_clip=1, last_clip=0, filename_prefix="video/Herrgotts_H3_Infinite_Stitched",
               video_crossfade_frames=4, audio_crossfade_ms=15.0, luminance_match=False,
               luminance_fade_frames=16, max_luminance_correction_percent=10.0, crf=18,
               max_safe_tail_bridge_frames=2):
        try:
            import av  # noqa: F401
        except Exception as e:
            raise RuntimeError("h3_continuous: PyAV is required for Saved Chain Stitching (normally provided by ComfyUI)") from e

        first = int(first_clip)
        last = int(last_clip)
        if last == 0:
            last = _discover_saved_last_clip(latent_prefix, first)
        if last < first:
            raise ValueError(f"last_clip {last} must be >= first_clip {first}")

        paths = [_saved_chain_file(latent_prefix, i) for i in range(first, last + 1)]
        if len(paths) < 1:
            raise ValueError("no clips selected")

        from .stream_stitch import stream_stitch_saved_clips
        result = stream_stitch_saved_clips(
            paths, video_vae, audio_vae,
            filename_prefix=filename_prefix,
            video_crossfade_frames=video_crossfade_frames,
            audio_crossfade_ms=audio_crossfade_ms,
            luminance_match=luminance_match,
            luminance_fade_frames=luminance_fade_frames,
            max_luminance_correction_percent=max_luminance_correction_percent,
            max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
            decode_audio=True,
            collect_audio=False,
            extra_metadata={"clip_range": f"{first}-{last}"},
            info_prefix=f"saved-chain seamless stitch complete | clips {first}-{last}",
        )
        return (result["path"], result["info"])

# Shared release nodes live with the v1.2 suite in the Add Node menu.
H3ContinuousSaveLatent.CATEGORY = "H3 Studio"
H3ContinuousLoadLatent.CATEGORY = "H3 Studio"
H3ContinuousLatentInfo.CATEGORY = "H3 Studio"

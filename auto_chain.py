"""Single-node H3 start/continue/stitch orchestrator."""

import logging
import os

import comfy.model_management
import comfy.nested_tensor
import comfy.sample
import comfy.utils
import latent_preview
import nodes

from comfy_extras.nodes_custom_sampler import Guider_Basic, Noise_RandomNoise

from .chain_inputs import (
    MAX_SEGMENTS, clips_to_reuse, collect_music_video_reference_images,
    collect_segment_models, segment_prompt_specs,
)
from .latent_math import CONTEXT_TO_STEPS, FPS, loop_wrap_start_frames, pixel_frames
from .node_help import NODE_HELP
from .spectrum_join import attach_spectrum_join_prefix

PNG_PREFIX = "video/h3_auto_chain"
_LOG = logging.getLogger("h3_continuous")


def _pack_first_frame(pack):
    if pack is None:
        return None
    from .pack import pack_first_frame
    return pack_first_frame(pack)


def _pack_ref_kwargs(resolved, audio_vae):
    if resolved is None:
        return {}
    return {
        "reference_videos": resolved["videos"] or None,
        "reference_video_audios": resolved["video_audios"] or None,
        "reference_audios": resolved["audios"] or None,
        "audio_vae": audio_vae,
    }


def _start_reference_images(resolved, fallback=None):
    """Drop the sole first-frame still from Ref2VA pictures so Start uses official FL2VA Qwen."""
    if resolved is None:
        return fallback
    if resolved.get("sole_first_frame"):
        return []
    return resolved.get("pictures") or []


def _resolve_clip_pack(pack, prompt, song_audio=False):
    if pack is None:
        return None
    from .pack import resolve_pack_for_clip
    return resolve_pack_for_clip(pack, prompt, song_audio=song_audio)


def _clip_role(index, segments):
    if index == 1:
        return "Start"
    if index == segments:
        return "Finish"
    return "Continue"


def _progress(unique_id, text):
    from .png_sequence import send_node_progress
    send_node_progress(unique_id, text)


def _segment_noise(noise, index):
    if not hasattr(noise, "generate_noise"):
        raise ValueError("h3_continuous: Auto Chain requires a NOISE input (RandomNoise)")
    seed = getattr(noise, "seed", None)
    if seed is None:
        return noise
    return Noise_RandomNoise(int(seed) + int(index))


def _sample_segment(model, positive, sampler, sigmas, noise, latent, join_prefix=False):
    guider = Guider_Basic(model)
    guider.set_conds(positive)
    attach_spectrum_join_prefix(guider, join_prefix)
    latent = dict(latent)
    latent_image = latent["samples"]
    latent_image = comfy.sample.fix_empty_latent_channels(
        guider.model_patcher, latent_image,
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


def _cpu_av_latent(latent):
    from .nodes import _streams_from_latent
    video, audio = _streams_from_latent(latent)
    return {
        "samples": comfy.nested_tensor.NestedTensor((
            video.detach().cpu().contiguous(),
            audio.detach().cpu().contiguous(),
        ))
    }


def _release_loaded_models():
    from .nodes import release_loaded_models
    release_loaded_models()


def _loop_start_trim_frames(end_latent, context_frames):
    from .nodes import _streams_from_latent
    video, _audio = _streams_from_latent(end_latent)
    return loop_wrap_start_frames(int(video.shape[2]), int(context_frames))


def _stitch_saved_to_av(video_vae, audio_vae, saved_paths, video_crossfade_frames,
                        audio_crossfade_ms, max_safe_tail_bridge_frames, unique_id=None,
                        last_as_final_clip=True, close_loop=False,
                        loop_start_trim_frames=0, loop_overlap_frames=0,
                        filename_prefix=PNG_PREFIX, frames_dir=None):
    from .stream_stitch import stream_stitch_saved_clips

    result = stream_stitch_saved_clips(
        saved_paths, video_vae, audio_vae,
        filename_prefix=filename_prefix,
        video_crossfade_frames=video_crossfade_frames,
        audio_crossfade_ms=audio_crossfade_ms,
        max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
        decode_audio=True,
        collect_audio=True,
        first_clip_extra_head=int(loop_start_trim_frames) if close_loop else 0,
        close_loop=bool(close_loop),
        loop_overlap_frames=int(loop_overlap_frames or 0),
        info_prefix="auto-chain stream stitch",
        progress_cb=lambda text: _progress(unique_id, text),
        frames_dir=frames_dir,
        keep_in_ram=frames_dir is None,
    )
    return result["images"], result["audio"], result["info"], result["frames_dir"]


def _decode_audio(audio_vae, latent):
    from .nodes import _decode_audio_only, _streams_from_latent
    _video, audio_latent = _streams_from_latent(latent)
    return _decode_audio_only(audio_vae, audio_latent)


def _write_clip_preview(images, latent_prefix, clip_index, audio=None, suffix=""):
    from .stream_stitch import clip_preview_path, encode_clip_preview
    path = clip_preview_path(latent_prefix, clip_index, suffix=suffix)
    encode_clip_preview(images, path, audio=audio)
    return path


def _open_live_session(**kwargs):
    from .stream_stitch import StreamStitchSession
    return StreamStitchSession(**kwargs)


def _decode_video(video_vae, latent):
    from .nodes import _streams_from_latent
    video, _audio = _streams_from_latent(latent)
    images = video_vae.decode(video)
    if images.ndim == 5:
        images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
    if images.ndim != 4:
        raise ValueError(f"h3_continuous: unexpected decoded video shape {tuple(images.shape)}")
    return images


def _overlap_identity_frame(images, previous_latent, context_frames, handover):
    """Last overlap pixel from a previous decode, for the next Continue I2V lock."""
    from .nodes import _resolve_continue_slice, _streams_from_latent
    if images is None or previous_latent is None:
        return None
    video, _audio = _streams_from_latent(previous_latent)
    sl, _src = _resolve_continue_slice(
        video, int(context_frames), "auto", "phase_aligned_extended", 34, handover,
    )
    idx = int(sl["source_end_frame"]) - 1
    if idx < 1 or idx >= int(images.shape[0]):
        return None
    return images[idx:idx + 1].detach().cpu().contiguous()


class H3StudioAutoChain:
    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "pack": ("H3_STUDIO_PACK", {
                "tooltip": (
                    "Pack from H3 Studio Builder: enabled models plus image/video/audio refs. "
                    "In single-prompt mode, duration, clip count, and loop come from the prompt, "
                    "or duration/clip count from this pack. Per-clip <Model N> / <Picture N> / "
                    "<Video N> / <Audio N> select a subset; otherwise Model 1 and the first refs "
                    "that fit the H3 caps are used."
                ),
            }),
            "clip": ("CLIP", {
                "tooltip": "Qwen3-VL H3 text encoder. Encodes each clip's Ref2VA prompt and optional <Picture N> stills. Keep this encoder paired with the H3 model.",
            }),
            "video_vae": ("VAE", {
                "tooltip": "MiniMax H3 Video VAE. Encodes optional <Picture N> Ref2VA stills, decodes each clip for Auto Handover, and decodes saved clips one at a time while writing the temp PNG sequence.",
            }),
            "audio_vae": ("VAE", {
                "tooltip": "MiniMax H3 Audio VAE. Decodes each clip's native audio stream during the final stitch. Use the matching H3 audio VAE, not the video VAE.",
            }),
            "sampler": ("SAMPLER", {
                "tooltip": "Sampler object from KSampler Select (the tested workflows use res_multistep). Applied identically to every clip.",
            }),
            "sigmas": ("SIGMAS", {
                "tooltip": "Noise schedule from Basic Scheduler (or equivalent). Built from the Sigma-Shifted H3 model. Shared by every clip, including per-clip LoRA models on the same base.",
            }),
            "noise": ("NOISE", {
                "tooltip": "Noise source from RandomNoise. Clip 1 uses this seed; clip i uses seed + (i-1) so each segment gets a distinct noise draw.",
            }),
            "width": ("INT", {
                "default": 1344, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32,
                "tooltip": "Generation width in pixels. Must stay constant for the whole chain. H3 canvases are typically multiples of 32 (tested default 1344).",
            }),
            "height": ("INT", {
                "default": 768, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32,
                "tooltip": "Generation height in pixels. Must stay constant for the whole chain. Tested default is 768.",
            }),
            "duration": ("FLOAT", {
                "default": 10.0, "min": 0.25, "max": 150.0, "step": 0.001, "round": 0.001,
                "tooltip": "Requested length of EACH clip in seconds at H3's native 24 fps. H3 snaps upward to its 17k+5 frame grid (10.0 s -> 243 frames ~= 10.125 s). Every segment uses this duration.",
            }),
            "segments": ("INT", {
                "default": 3, "min": 1, "max": MAX_SEGMENTS, "step": 1,
                "tooltip": "How many story clips to generate. Clip 1 is Ref2VA Start (optional <Picture N> stills); clips 2..N-1 are Continue; clip N is Finish. The prompt document must contain that many ## Clip sections. Models come from the Builder pack. seamless_loop adds one extra Loop clip after these and does not count toward this number.",
            }),
            "prompt": ("STRING", {
                "multiline": True, "default": "", "dynamicPrompts": False,
                "tooltip": (
                    "One H3 Studio prompt for every clip: ## Clip 1 — Start / Continue / Finish, "
                    "each with its own subject_definitions (dump labels that clip loads). Optional "
                    "## Loop when seamless_loop is on. A top-level subject_definitions block is "
                    "legacy fallback for clips that omit one. @Picture N chips replace a reference "
                    "here or in all clips."
                ),
            }),
        }
        required.update(segment_prompt_specs())
        required.update({
            "seamless_loop": ("BOOLEAN", {
                "default": False,
                "tooltip": "After the N story clips, generate one extra Loop clip as: last clip's ending context + generated bridge + clip 1's opening after the I2VA still-hold (video and audio). The Loop clip keeps its generated opening copy. Stitch overlap-adds that copy with clip 1's real opening (same length as context_frames, default 22) so textures dissolve across the wrap. Clip 1's still-hold is trimmed first. Story joins still use the 4-frame / 15 ms knobs.",
            }),
            "loop_prompt": ("STRING", {
                "multiline": True, "default": "", "dynamicPrompts": True,
                "tooltip": "Prompt for the extra Loop clip (only used when seamless_loop is on). Describe continuing from the last clip's world into clip 1's opening action already in motion — not returning to a still pose.",
            }),
            "context_frames": (["5", "22", "39"], {
                "default": "22",
                "tooltip": "Minimum motion/audio history copied from the previous AV latent into the next clip. 22 is the tested default. phase_aligned_extended may extend backward to a canonical H3 phase-0 start, so the actual head can be slightly longer.",
            }),
            "handover_preset": (["Balanced", "Motion Safe"], {
                "default": "Balanced",
                "tooltip": "Auto Handover detector used after every clip. Balanced = tested freeze_hold 8 with a 3-frame safety margin. Motion Safe = same detector with a larger 6-frame safety margin (more conservative cutoff). If no freeze is found, No-Lock Fallback excludes freeze_hold-1 ending frames before phase alignment.",
            }),
            "save_segment_latents": ("BOOLEAN", {
                "default": True,
                "tooltip": "Keep each clip's full AV latent as safetensors under latent_prefix (clip_00001.safetensors, ...). Needed to resume later. If off, only newly generated segment files are deleted after a successful stitch; already-saved clips loaded by resume_from_clip are kept.",
            }),
                "save_clip_videos": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "After each clip's handover decode, write a playable MP4 next to the latent (clip_00001.mp4). You can watch it before the chain finishes. The stitched IMAGE is the temp PNG sequence, not these previews.",
                }),
            "freeze_overlap": ("BOOLEAN", {
                "default": True,
                "tooltip": "Continue clips copy the previous overlap video tokens and do not denoise them. Overlap is not also packed as H3 keyframes unless this clip sandwiches another latent. Stitch still discards that overlap. Turn off to A/B against regenerated-head Continue.",
            }),
            "overlap_soft_steps": ("INT", {
                "default": 0, "min": 0, "max": 4, "step": 1,
                "tooltip": "When freeze_overlap is on, 0 keeps the overlap hard-frozen. 1–4 ramp the last N frozen video steps toward denoise so the first kept frames are not a hard inpaint edge. 0 is the starting point.",
            }),
            "latent_prefix": ("STRING", {
                "default": "h3_auto_chain/clip",
                "tooltip": "Output path prefix relative to ComfyUI/output. Clip 1 is saved as <prefix>_00001.safetensors, clip 2 as _00002, and so on. Re-running with the same prefix overwrites those slots. resume_from_clip loads earlier slots from this prefix.",
            }),
            "resume_from_clip": ("INT", {
                "default": 1, "min": 1, "max": MAX_SEGMENTS + 1, "step": 1,
                "tooltip": "1 = generate the full chain from scratch. 2+ = load only the previous clip's latent and start generating at this clip. Earlier slots must already exist. With seamless_loop, segments+1 generates only the Loop clip (clip 1 is also loaded for the wrap). Keep the same prefix as the previous run.",
            }),
            "video_crossfade_frames": ("INT", {
                "default": 4, "min": 0, "max": 16, "step": 1,
                "tooltip": "After Safe Tail Bridge, blend this many context-aligned video frames at each join. 4 is the tested default. 0 disables the video blend (hard cut after the bridge).",
            }),
            "audio_crossfade_ms": ("FLOAT", {
                "default": 15.0, "min": 0.0, "max": 100.0, "step": 1.0,
                "tooltip": "Audio de-click crossfade at each join, independent of the video bridge. 15 ms is the tested default. Keep it short to avoid phasing or doubled transients. 0 disables the audio crossfade.",
            }),
            "max_safe_tail_bridge_frames": ("INT", {
                "default": 2, "min": 0, "max": 4, "step": 1,
                "tooltip": "Reuse up to this many detector-approved rendered frames from the previous clip that phase alignment had to drop, and skip the same number of early video frames in the next clip. 2 is recommended. Never borrows from the freeze safety margin and does not change total duration. Audio timing is unchanged.",
            }),
        })
        from .png_sequence import save_images_to_disk_spec
        required["save_images_to_disk"] = save_images_to_disk_spec()
        duration_spec = required.pop("duration", None)
        segments_spec = required.pop("segments", None)
        loop_prompt_spec = required.pop("loop_prompt", None)
        prompt_specs = {}
        for key in [name for name in list(required) if str(name).startswith("prompt_")]:
            prompt_specs[key] = required.pop(key)
        optional = {}
        if duration_spec:
            optional["duration"] = duration_spec
        if segments_spec:
            optional["segments"] = segments_spec
        optional.update(prompt_specs)
        if loop_prompt_spec:
            optional["loop_prompt"] = loop_prompt_spec
        optional["prompt_mode"] = (["single", "per_clip"], {
            "default": "single",
            "tooltip": (
                "Only changes how the prompt is shown. It does not affect generation."
            ),
        })
        return {
            "required": required,
            "optional": optional,
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "LATENT", "H3_CONTINUOUS_HANDOVER")
    RETURN_NAMES = ("images", "audio", "chain_info", "last_latent", "last_handover")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    CATEGORY = "H3 Studio"
    DESCRIPTION = NODE_HELP["H3StudioAutoChain"]

    def generate(self, pack, prompt_mode="single", **kwargs):
        from .pack import require_pack
        from .prompt_document import (
            document_has_loop, duration_and_segments_from_pack_or_prompt,
        )
        pack = require_pack(pack)
        mode = str(prompt_mode or "single").strip().lower().replace(" ", "_")
        if mode == "per_clip":
            if kwargs.get("duration") is None:
                raise ValueError("h3_studio: duration is missing")
            if kwargs.get("segments") is None:
                raise ValueError("h3_studio: segments is missing")
            kwargs["duration"] = float(kwargs["duration"])
            kwargs["segments"] = int(kwargs["segments"])
        else:
            duration, segments = duration_and_segments_from_pack_or_prompt(
                pack, kwargs.get("prompt") or "", need_segments=True,
            )
            kwargs["duration"] = duration
            kwargs["segments"] = segments
            kwargs["seamless_loop"] = document_has_loop(kwargs.get("prompt") or "")
        kwargs["pack"] = pack
        kwargs["model_1"] = pack["models"][0]["model"]
        return self._generate_chain(**kwargs)

    def _generate_chain(self, model_1, clip, video_vae, audio_vae, sampler, sigmas, noise,
                 width, height, duration, segments=None, context_frames="22",
                 handover_preset="Balanced", save_segment_latents=True, save_clip_videos=True,
                 freeze_overlap=True, overlap_soft_steps=0,
                 latent_prefix="h3_auto_chain/clip", resume_from_clip=1,
                 video_crossfade_frames=4, audio_crossfade_ms=15.0,
                 max_safe_tail_bridge_frames=2,
                 save_images_to_disk=False,
                 seamless_loop=False, loop_prompt="", prompt="",
                 model_loop=None,
                 unique_id=None, pack=None, clip_fix=False, clip_index="", **kwargs):
        from .nodes import (
            H3ContinuousAnalyzeHandoverV11, H3ContinuousContinueV11,
            H3ContinuousLoadLatent, H3ContinuousSaveLatent, H3ContinuousStartV11,
            _saved_chain_file,
        )

        if clip_fix:
            return self._generate_fix_chain(
                model_1, clip, video_vae, audio_vae, sampler, sigmas, noise,
                width, height, duration, context_frames=context_frames,
                handover_preset=handover_preset, save_segment_latents=save_segment_latents,
                save_clip_videos=save_clip_videos, freeze_overlap=freeze_overlap,
                overlap_soft_steps=overlap_soft_steps, latent_prefix=latent_prefix,
                video_crossfade_frames=video_crossfade_frames,
                audio_crossfade_ms=audio_crossfade_ms,
                max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
                save_images_to_disk=save_images_to_disk, seamless_loop=seamless_loop,
                loop_prompt=loop_prompt, prompt=prompt, model_loop=model_loop,
                unique_id=unique_id, pack=pack, clip_index=clip_index,
                segments=segments, **kwargs,
            )

        segments = int(segments)
        if segments < 1 or segments > MAX_SEGMENTS:
            raise ValueError(f"h3_continuous: segments must be 1..{MAX_SEGMENTS}")
        seamless_loop = bool(seamless_loop)

        from .png_sequence import (
            node_temp_frames_dir, pack_image_output, require_image_ram, warn_disk_budget,
        )
        from .song_math import grid_frame_count
        save_images_to_disk = bool(save_images_to_disk)
        n_png = grid_frame_count(duration) * (segments + (1 if seamless_loop else 0))
        extra = f"Auto Chain: {segments} clip(s) x {float(duration):g}s" + (" + loop" if seamless_loop else "")
        require_image_ram(n_png, width, height, save_images_to_disk)
        out_frames = None
        if save_images_to_disk:
            warn_disk_budget(
                n_png, width, height, unique_id=unique_id,
                extra=extra,
            )
            out_frames = node_temp_frames_dir(PNG_PREFIX, unique_id)

        reuse = clips_to_reuse(resume_from_clip, segments, seamless_loop)
        from .prompt_document import resolve_auto_chain_prompts
        prompts, loop_prompt = resolve_auto_chain_prompts(
            prompt, segments, loop=seamless_loop, loop_prompt=loop_prompt, kwargs=kwargs,
        )
        reference_images = collect_music_video_reference_images(kwargs)
        models = collect_segment_models(segments, model_1, kwargs)
        if pack is not None:
            from .pack import require_pack
            pack = require_pack(pack)
            model_1 = pack["models"][0]["model"]
            models = [model_1] * segments
        context_frames = str(context_frames)
        freeze_overlap = bool(freeze_overlap)
        overlap_soft_steps = int(overlap_soft_steps)

        def model_for_clip(clip_index):
            if pack is not None:
                return _resolve_clip_pack(pack, prompt_for_clip(clip_index))["model"]
            if seamless_loop and int(clip_index) == segments + 1:
                return model_loop if model_loop is not None else model_1
            return models[int(clip_index) - 1]

        def prompt_for_clip(clip_index):
            if seamless_loop and int(clip_index) == segments + 1:
                return str(loop_prompt or "").strip()
            value = prompts[int(clip_index) - 1]
            return value if value is not None else ""

        start = H3ContinuousStartV11()
        cont = H3ContinuousContinueV11()
        analyzer = H3ContinuousAnalyzeHandoverV11()
        saver = H3ContinuousSaveLatent()
        loader = H3ContinuousLoadLatent()

        previous_latent = None
        last_handover = None
        last_latent = None
        saved_paths = []
        generated_paths = []
        notes = []
        loop_end_latent = None
        identity_frame = None

        if seamless_loop and not str(loop_prompt or "").strip():
            raise ValueError(
                "h3_continuous: seamless_loop requires loop_prompt "
                "(Continue from the last clip back to clip 1's opening)"
            )

        save_clip_videos = bool(save_clip_videos)
        session = None
        loop_start_trim = 0
        loop_end_frames = pixel_frames(CONTEXT_TO_STEPS[int(context_frames)]) if seamless_loop else 0
        live_stitch = not reuse

        def ensure_session():
            nonlocal session
            if session is not None:
                return
            session = _open_live_session(
                filename_prefix=PNG_PREFIX,
                video_crossfade_frames=video_crossfade_frames,
                audio_crossfade_ms=audio_crossfade_ms,
                max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
                decode_audio=True,
                collect_audio=True,
                first_clip_extra_head=loop_start_trim if seamless_loop else 0,
                close_loop=seamless_loop,
                loop_overlap_frames=loop_end_frames,
                info_prefix="auto-chain stream stitch",
                frames_dir=out_frames,
                keep_in_ram=not save_images_to_disk,
            )

        def commit_live(images, audio, latent_path, clip_index, is_final, handover):
            from .nodes import _read_safetensors_metadata
            if save_clip_videos:
                preview = _write_clip_preview(images, latent_prefix, clip_index, audio=audio)
                notes.append(f"clip {clip_index} preview {preview}")
                _LOG.info("h3_continuous: Auto Chain clip %s preview %s", clip_index, preview)
            if not live_stitch:
                return
            ensure_session()
            metadata, _ignored = _read_safetensors_metadata(latent_path)
            session.add_decoded_clip(images, audio, metadata, handover, clip_index, is_final)

        try:
            if reuse:
                last_reused = reuse[-1]
                _progress(unique_id, f"Loading saved clip {last_reused} (resume at {resume_from_clip})")
                _LOG.info(
                    "h3_continuous: Auto Chain resume from clip %s, keep 1–%s on disk, load clip %s only",
                    resume_from_clip, last_reused, last_reused,
                )
                for clip_index in reuse:
                    saved_paths.append(_saved_chain_file(latent_prefix, clip_index))
                last_latent, resolved, info, handover = loader.load(saved_paths[-1], clip_index=0)
                last_latent = _cpu_av_latent(last_latent)
                last_handover = handover
                previous_latent = last_latent
                saved_paths[-1] = resolved
                notes.append(f"clips 1–{last_reused} reused; loaded clip {last_reused} {info}")
                _LOG.info("h3_continuous: Auto Chain reused clip %s from %s", last_reused, resolved)
                _progress(unique_id, f"Identity still from saved clip {last_reused}")
                resume_images = _decode_video(video_vae, last_latent)
                identity_frame = _overlap_identity_frame(
                    resume_images, last_latent, context_frames, last_handover,
                )
                del resume_images
                _release_loaded_models()
                if seamless_loop:
                    if last_reused == 1:
                        loop_end_latent = last_latent
                    else:
                        clip1_latent, clip1_path, _clip1_info, _h = loader.load(saved_paths[0], clip_index=0)
                        loop_end_latent = _cpu_av_latent(clip1_latent)
                        saved_paths[0] = clip1_path
                        del clip1_latent
                    loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)

            for i in range(int(resume_from_clip) - 1, segments):
                comfy.model_management.throw_exception_if_processing_interrupted()
                clip_index = i + 1
                prompt = prompts[i] if prompts[i] is not None else ""
                resolved = _resolve_clip_pack(pack, prompt)
                if resolved is not None:
                    prompt = resolved["prompt"]
                    clip_model = resolved["model"]
                    pack_refs = _pack_ref_kwargs(resolved, audio_vae)
                    clip_images = _start_reference_images(resolved) if i == 0 else (resolved["pictures"] or [])
                else:
                    clip_model = models[i]
                    pack_refs = {}
                    clip_images = reference_images
                role = _clip_role(clip_index, segments)
                _release_loaded_models()
                _progress(unique_id, f"Clip {clip_index}/{segments} ({role}) — encoding")
                _LOG.info("h3_continuous: Auto Chain clip %s/%s", clip_index, segments)

                if i == 0:
                    start_still = _pack_first_frame(pack)
                    if resolved is not None:
                        _LOG.info(
                            "h3_continuous: clip 1 first_frame=%s sole_first_frame=%s ref_pictures=%s",
                            start_still is not None,
                            bool(resolved.get("sole_first_frame")),
                            len(clip_images or []),
                        )
                    positive, empty = start.build(
                        clip, video_vae, prompt, width, height, duration,
                        first_frame=start_still, last_frame=None,
                        reference_images=clip_images,
                        **pack_refs,
                    )
                    head_context = 0
                else:
                    positive, empty, head_context, _ignored_tail, handover_info = cont.build(
                        clip, video_vae, previous_latent, prompt, width, height, duration,
                        context_frames=context_frames, handover_mode="auto",
                        alignment_mode="phase_aligned_extended",
                        handover=last_handover, last_frame=None,
                        reference_images=clip_images, freeze_overlap=freeze_overlap,
                        overlap_soft_steps=overlap_soft_steps, identity_frame=identity_frame,
                        **pack_refs,
                    )
                    notes.append(f"clip {clip_index} {handover_info}")

                _release_loaded_models()
                _progress(unique_id, f"Clip {clip_index}/{segments} ({role}) — sampling")
                sampled = _sample_segment(
                    clip_model, positive, sampler, sigmas, _segment_noise(noise, i), empty,
                    join_prefix=(role != "Start"),
                )
                last_latent = _cpu_av_latent(sampled)
                del sampled, empty
                _release_loaded_models()

                _progress(unique_id, f"Clip {clip_index}/{segments} ({role}) — handover decode")
                images = _decode_video(video_vae, last_latent)
                if seamless_loop and clip_index == 1:
                    loop_end_latent = last_latent
                    loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)
                handover, status, *_rest = analyzer.analyze(
                    images, preset=handover_preset, context_frames=context_frames,
                )
                clip_audio = None
                if save_clip_videos or live_stitch:
                    _release_loaded_models()
                    clip_audio = _decode_audio(audio_vae, last_latent)
                    _release_loaded_models()
                last_handover = handover
                previous_latent = last_latent
                identity_frame = _overlap_identity_frame(
                    images, last_latent, context_frames, handover,
                )
                is_final = (not seamless_loop) and clip_index == segments
                del positive
                latent_path, save_info = saver.save(
                    last_latent, latent_prefix, clip_index=clip_index,
                    handover=handover, head_context_frames=int(head_context or 0),
                )
                saved_paths.append(latent_path)
                generated_paths.append(latent_path)
                notes.append(f"clip {clip_index} {status} | saved {save_info}")
                _LOG.info("h3_continuous: Auto Chain clip %s saved %s", clip_index, latent_path)
                if save_clip_videos or live_stitch:
                    commit_live(images, clip_audio, latent_path, clip_index, is_final, handover)
                del images, clip_audio
                _release_loaded_models()

            if seamless_loop:
                if loop_end_latent is None:
                    raise ValueError("h3_continuous: seamless_loop could not load clip 1's opening latent")
                if not loop_start_trim:
                    loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)
                loop_index = segments + 1
                loop_text = str(loop_prompt).strip()
                loop_resolved = _resolve_clip_pack(pack, loop_text)
                if loop_resolved is not None:
                    loop_text = loop_resolved["prompt"]
                    loop_model = loop_resolved["model"]
                    loop_refs = _pack_ref_kwargs(loop_resolved, audio_vae)
                    loop_images = loop_resolved["pictures"]
                else:
                    loop_model = model_loop if model_loop is not None else model_1
                    loop_refs = {}
                    loop_images = reference_images
                _release_loaded_models()
                _progress(unique_id, f"Loop clip {loop_index} — encoding")
                _LOG.info("h3_continuous: Auto Chain loop clip %s (last ending + clip 1 opening)", loop_index)
                positive, empty, head_context, _ignored_tail, handover_info = cont.build(
                    clip, video_vae, previous_latent, loop_text, width, height, duration,
                    context_frames=context_frames, handover_mode="auto",
                    alignment_mode="phase_aligned_extended",
                    handover=last_handover, last_frame=None,
                    reference_images=loop_images, end_latent=loop_end_latent,
                    freeze_overlap=freeze_overlap, overlap_soft_steps=overlap_soft_steps,
                    identity_frame=identity_frame,
                    **loop_refs,
                )
                notes.append(f"loop {handover_info}")
                _release_loaded_models()
                _progress(unique_id, f"Loop clip {loop_index} — sampling")
                sampled = _sample_segment(
                    loop_model, positive, sampler, sigmas, _segment_noise(noise, segments), empty,
                    join_prefix=True,
                )
                last_latent = _cpu_av_latent(sampled)
                del sampled, empty
                _release_loaded_models()
                _progress(unique_id, f"Loop clip {loop_index} — handover decode")
                images = _decode_video(video_vae, last_latent)
                handover, status, *_rest = analyzer.analyze(
                    images, preset=handover_preset, context_frames=context_frames,
                )
                clip_audio = None
                if save_clip_videos or live_stitch:
                    _release_loaded_models()
                    clip_audio = _decode_audio(audio_vae, last_latent)
                    _release_loaded_models()
                last_handover = handover
                previous_latent = last_latent
                del positive
                latent_path, save_info = saver.save(
                    last_latent, latent_prefix, clip_index=loop_index,
                    handover=handover, head_context_frames=int(head_context or 0),
                )
                saved_paths.append(latent_path)
                generated_paths.append(latent_path)
                notes.append(f"loop {status} | saved {save_info}")
                _LOG.info("h3_continuous: Auto Chain loop clip saved %s", latent_path)
                if save_clip_videos or live_stitch:
                    commit_live(images, clip_audio, latent_path, loop_index, True, handover)
                del images, clip_audio
                _release_loaded_models()

            _release_loaded_models()
            if session is not None:
                result = session.finalize()
                images, audio, stitch_info, frames_dir = (
                    result["images"], result["audio"], result["info"], result["frames_dir"],
                )
            else:
                images, audio, stitch_info, frames_dir = _stitch_saved_to_av(
                    video_vae, audio_vae, saved_paths,
                    video_crossfade_frames=video_crossfade_frames,
                    audio_crossfade_ms=audio_crossfade_ms,
                    max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
                    unique_id=unique_id,
                    last_as_final_clip=True,
                    close_loop=seamless_loop,
                    loop_start_trim_frames=loop_start_trim if seamless_loop else 0,
                    loop_overlap_frames=loop_end_frames,
                    frames_dir=out_frames,
                )
        except BaseException:
            if session is not None and not session._closed:
                session.abort()
            raise
        _release_loaded_models()
        done_clips = segments + (1 if seamless_loop else 0)
        _progress(unique_id, f"Done — {done_clips} clip(s) stitched" + (" (loop)" if seamless_loop else ""))

        if not save_segment_latents:
            for path in generated_paths:
                try:
                    os.remove(path)
                except OSError as exc:
                    _LOG.warning("h3_continuous: could not delete temporary segment %s: %s", path, exc)

        resume_note = ""
        if reuse:
            resume_note = f"resume from clip {int(resume_from_clip)} | "
        loop_note = "seamless loop | " if seamless_loop else ""
        info = (
            f"auto chain | {resume_note}{loop_note}{segments} clip(s) | keep latents={'yes' if save_segment_latents else 'no'} | "
            f"clip videos={'yes' if save_clip_videos else 'no'} | "
            f"{'png ' + str(frames_dir) if frames_dir else 'IMAGE in RAM'} | "
            f"{stitch_info}"
        )
        keep_notes = (segments + (1 if seamless_loop else 0)) * 3
        if notes:
            info += " | " + " ; ".join(notes[-keep_notes:])
        _LOG.info("h3_continuous: %s", info)
        return pack_image_output(images, frames_dir, audio, info, last_latent, last_handover)

    def _generate_fix_chain(self, model_1, clip, video_vae, audio_vae, sampler, sigmas, noise,
                 width, height, duration, context_frames="22",
                 handover_preset="Balanced", save_segment_latents=True, save_clip_videos=True,
                 freeze_overlap=True, overlap_soft_steps=0,
                 latent_prefix="h3_auto_chain/clip",
                 video_crossfade_frames=4, audio_crossfade_ms=15.0,
                 max_safe_tail_bridge_frames=2, save_images_to_disk=False,
                 seamless_loop=False, loop_prompt="", prompt="", model_loop=None,
                 unique_id=None, pack=None, clip_index="", segments=None, **kwargs):
        from .clip_fix_chain import (
            clip_fix_neighbors, expand_fix_clip, expand_fix_loop, should_regen_loop,
        )
        from .clip_fixer import prepare_clip_fix
        from .latent_math import steps_for_pixel_frames
        from .nodes import (
            H3ContinuousAnalyzeHandoverV11, H3ContinuousContinueV11,
            H3ContinuousLoadLatent, H3ContinuousSaveLatent, H3ContinuousStartV11,
            _read_safetensors_metadata, _saved_chain_file,
        )
        from .png_sequence import (
            node_temp_frames_dir, pack_image_output, require_image_ram, warn_disk_budget,
        )
        from .song_math import grid_frame_count

        if pack is not None:
            from .pack import require_pack
            pack = require_pack(pack)
            model_1 = pack["models"][0]["model"]
        reference_images = collect_music_video_reference_images(kwargs)
        per_clip = bool(kwargs.pop("clip_fix_per_clip", False))
        loop_hint = bool(seamless_loop or (pack or {}).get("loop"))
        segments_hint = None
        if segments is not None:
            try:
                segments_hint = int(segments)
            except (TypeError, ValueError):
                segments_hint = None
        if segments_hint is None and pack is not None and pack.get("segments") is not None:
            segments_hint = int(pack["segments"])
        prepared = prepare_clip_fix(
            latent_prefix, prompt, clip_index,
            loop_hint=loop_hint, segments_hint=segments_hint, max_story=MAX_SEGMENTS,
            kwargs=kwargs, per_clip_segments=segments_hint if per_clip else None,
        )
        story_n = prepared["story_n"]
        has_loop = prepared["has_loop"]
        regen = prepared["regen"]
        saved_set = set(prepared["saved"])
        regen_loop = should_regen_loop(regen, story_n, has_loop)
        context_frames = str(context_frames)
        freeze_overlap = bool(freeze_overlap)
        overlap_soft_steps = int(overlap_soft_steps)
        save_clip_videos = bool(save_clip_videos)
        save_images_to_disk = bool(save_images_to_disk)
        n_png = grid_frame_count(duration) * (story_n + (1 if has_loop else 0))
        extra = (
            f"Auto Chain clip fix: {len(regen)} clip(s) / {story_n} on disk"
            + (" + loop" if regen_loop else "")
        )
        require_image_ram(n_png, width, height, save_images_to_disk)
        out_frames = None
        if save_images_to_disk:
            warn_disk_budget(n_png, width, height, unique_id=unique_id, extra=extra)
            out_frames = node_temp_frames_dir(PNG_PREFIX, unique_id)

        start = H3ContinuousStartV11()
        cont = H3ContinuousContinueV11()
        analyzer = H3ContinuousAnalyzeHandoverV11()
        saver = H3ContinuousSaveLatent()
        loader = H3ContinuousLoadLatent()
        notes = [f"backup {prepared['backup_dir']}"]
        last_latent = None
        last_handover = None
        previous_latent = None
        identity_frame = None
        generated_this_run = set()
        loop_end_latent = None
        loop_start_trim = 0
        loop_end_frames = pixel_frames(CONTEXT_TO_STEPS[int(context_frames)]) if has_loop else 0

        def load_slot(index, decode_identity=False):
            path = _saved_chain_file(latent_prefix, index)
            latent, resolved, info, handover = loader.load(path, clip_index=0)
            latent = _cpu_av_latent(latent)
            identity = None
            if decode_identity:
                images = _decode_video(video_vae, latent)
                identity = _overlap_identity_frame(
                    images, latent, context_frames, handover,
                )
                del images
                _release_loaded_models()
            return latent, resolved, handover, identity, info

        if has_loop:
            loop_end_latent, _p, _h, _id, _info = load_slot(1, decode_identity=False)
            loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)

        for clip_index_n in regen:
            comfy.model_management.throw_exception_if_processing_interrupted()
            i = clip_index_n - 1
            clip_prompt = expand_fix_clip(prompt, clip_index_n, kwargs=kwargs)
            resolved = _resolve_clip_pack(pack, clip_prompt)
            if resolved is not None:
                clip_prompt = resolved["prompt"]
                clip_model = resolved["model"]
                pack_refs = _pack_ref_kwargs(resolved, audio_vae)
                clip_images = _start_reference_images(resolved) if i == 0 else (resolved["pictures"] or [])
            else:
                clip_model = model_loop if (model_loop is not None and clip_index_n == story_n + 1) else model_1
                if pack is None:
                    models = collect_segment_models(story_n, model_1, kwargs)
                    clip_model = models[i] if i < len(models) else model_1
                pack_refs = {}
                clip_images = reference_images
            existing_path = _saved_chain_file(latent_prefix, clip_index_n)
            metadata, _old = _read_safetensors_metadata(existing_path)
            grid_frames = int(metadata.get("frame_count") or 0)
            clip_duration = float(grid_frames) / FPS if grid_frames else float(duration)
            prev_i, next_i = clip_fix_neighbors(clip_index_n, regen, saved_set)
            role = _clip_role(clip_index_n, story_n)
            _release_loaded_models()
            if clip_index_n > 1:
                if prev_i not in generated_this_run or previous_latent is None:
                    _progress(unique_id, f"Loading saved clip {prev_i} (previous context)")
                    previous_latent, _p, last_handover, identity_frame, info = load_slot(
                        prev_i, decode_identity=True,
                    )
                    notes.append(f"prev clip {prev_i} {info}")
            end_latent = None
            end_skip = None
            if next_i is not None:
                _progress(unique_id, f"Loading saved clip {next_i} (next context)")
                end_latent, end_path, _h, _id, end_info = load_slot(next_i, decode_identity=False)
                end_meta, _ = _read_safetensors_metadata(end_path)
                end_skip = steps_for_pixel_frames(int(end_meta.get("head_context_frames") or 0))
                notes.append(f"next clip {next_i} {end_info}")
            _progress(unique_id, f"Clip {clip_index_n}/{story_n} ({role}) — encoding")
            if clip_index_n == 1:
                start_still = _pack_first_frame(pack)
                positive, empty = start.build(
                    clip, video_vae, clip_prompt, width, height, clip_duration,
                    first_frame=start_still, last_frame=None,
                    reference_images=clip_images,
                    **pack_refs,
                )
                head_context = 0
            else:
                extra_end = {}
                if end_latent is not None:
                    extra_end["end_latent"] = end_latent
                    extra_end["end_skip_steps"] = end_skip
                positive, empty, head_context, _ignored_tail, handover_info = cont.build(
                    clip, video_vae, previous_latent, clip_prompt, width, height, clip_duration,
                    context_frames=context_frames, handover_mode="auto",
                    alignment_mode="phase_aligned_extended",
                    handover=last_handover, last_frame=None,
                    reference_images=clip_images, freeze_overlap=freeze_overlap,
                    overlap_soft_steps=overlap_soft_steps, identity_frame=identity_frame,
                    **extra_end, **pack_refs,
                )
                notes.append(f"clip {clip_index_n} {handover_info}")
            del end_latent
            _release_loaded_models()
            _progress(unique_id, f"Clip {clip_index_n}/{story_n} ({role}) — sampling")
            sampled = _sample_segment(
                clip_model, positive, sampler, sigmas, _segment_noise(noise, i), empty,
                join_prefix=(role != "Start"),
            )
            last_latent = _cpu_av_latent(sampled)
            del sampled, empty
            _release_loaded_models()
            _progress(unique_id, f"Clip {clip_index_n}/{story_n} ({role}) — handover decode")
            images = _decode_video(video_vae, last_latent)
            if has_loop and clip_index_n == 1:
                loop_end_latent = last_latent
                loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)
            handover, status, *_rest = analyzer.analyze(
                images, preset=handover_preset, context_frames=context_frames,
            )
            clip_audio = _decode_audio(audio_vae, last_latent) if save_clip_videos else None
            last_handover = handover
            previous_latent = last_latent
            identity_frame = _overlap_identity_frame(
                images, last_latent, context_frames, handover,
            )
            del positive
            latent_path, save_info = saver.save(
                last_latent, latent_prefix, clip_index=clip_index_n,
                handover=handover, head_context_frames=int(head_context or 0),
            )
            generated_this_run.add(clip_index_n)
            notes.append(f"clip {clip_index_n} {status} | saved {save_info}")
            if save_clip_videos:
                preview = _write_clip_preview(images, latent_prefix, clip_index_n, audio=clip_audio)
                notes.append(f"clip {clip_index_n} preview {preview}")
            del images, clip_audio
            _release_loaded_models()

        if regen_loop:
            if loop_end_latent is None:
                loop_end_latent, _p, _h, _id, _info = load_slot(1, decode_identity=False)
                loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)
            if previous_latent is None or story_n not in generated_this_run:
                previous_latent, _p, last_handover, identity_frame, info = load_slot(
                    story_n, decode_identity=True,
                )
                notes.append(f"prev clip {story_n} {info}")
            loop_index = story_n + 1
            loop_text = expand_fix_loop(prompt, loop_prompt)
            loop_meta, _ = _read_safetensors_metadata(_saved_chain_file(latent_prefix, loop_index))
            loop_frames = int(loop_meta.get("frame_count") or 0)
            loop_duration = float(loop_frames) / FPS if loop_frames else float(duration)
            loop_resolved = _resolve_clip_pack(pack, loop_text)
            if loop_resolved is not None:
                loop_text = loop_resolved["prompt"]
                loop_model = loop_resolved["model"]
                loop_refs = _pack_ref_kwargs(loop_resolved, audio_vae)
                loop_images = loop_resolved["pictures"]
            else:
                loop_model = model_loop if model_loop is not None else model_1
                loop_refs = {}
                loop_images = reference_images
            _release_loaded_models()
            _progress(unique_id, f"Loop clip {loop_index} — encoding")
            positive, empty, head_context, _ignored_tail, handover_info = cont.build(
                clip, video_vae, previous_latent, loop_text, width, height, loop_duration,
                context_frames=context_frames, handover_mode="auto",
                alignment_mode="phase_aligned_extended",
                handover=last_handover, last_frame=None,
                reference_images=loop_images, end_latent=loop_end_latent,
                freeze_overlap=freeze_overlap, overlap_soft_steps=overlap_soft_steps,
                identity_frame=identity_frame,
                **loop_refs,
            )
            notes.append(f"loop {handover_info}")
            _release_loaded_models()
            _progress(unique_id, f"Loop clip {loop_index} — sampling")
            sampled = _sample_segment(
                loop_model, positive, sampler, sigmas, _segment_noise(noise, story_n), empty,
                join_prefix=True,
            )
            last_latent = _cpu_av_latent(sampled)
            del sampled, empty
            _release_loaded_models()
            images = _decode_video(video_vae, last_latent)
            handover, status, *_rest = analyzer.analyze(
                images, preset=handover_preset, context_frames=context_frames,
            )
            clip_audio = _decode_audio(audio_vae, last_latent) if save_clip_videos else None
            last_handover = handover
            del positive
            latent_path, save_info = saver.save(
                last_latent, latent_prefix, clip_index=loop_index,
                handover=handover, head_context_frames=int(head_context or 0),
            )
            notes.append(f"loop {status} | saved {save_info}")
            if save_clip_videos:
                preview = _write_clip_preview(images, latent_prefix, loop_index, audio=clip_audio)
                notes.append(f"loop preview {preview}")
            del images, clip_audio
            _release_loaded_models()

        last_slot = story_n + (1 if has_loop else 0)
        saved_paths = [_saved_chain_file(latent_prefix, n) for n in range(1, last_slot + 1)]
        if has_loop and loop_end_latent is not None and not loop_start_trim:
            loop_start_trim = _loop_start_trim_frames(loop_end_latent, context_frames)
        images, audio, stitch_info, frames_dir = _stitch_saved_to_av(
            video_vae, audio_vae, saved_paths,
            video_crossfade_frames=video_crossfade_frames,
            audio_crossfade_ms=audio_crossfade_ms,
            max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
            unique_id=unique_id,
            last_as_final_clip=True,
            close_loop=has_loop,
            loop_start_trim_frames=loop_start_trim if has_loop else 0,
            loop_overlap_frames=loop_end_frames,
            frames_dir=out_frames,
        )
        _release_loaded_models()
        done_clips = story_n + (1 if has_loop else 0)
        _progress(unique_id, f"Done — {done_clips} clip(s) stitched" + (" (loop)" if has_loop else ""))
        loop_note = "seamless loop | " if has_loop else ""
        info = (
            f"auto chain clip fix | clips {','.join(str(n) for n in regen)} | {loop_note}"
            f"{story_n} clip(s) | backup {prepared['backup_dir']} | "
            f"{'png ' + str(frames_dir) if frames_dir else 'IMAGE in RAM'} | {stitch_info}"
        )
        if notes:
            info += " | " + " ; ".join(notes[-done_clips * 3:])
        _LOG.info("h3_continuous: %s", info)
        return pack_image_output(images, frames_dir, audio, info, last_latent, last_handover)


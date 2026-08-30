"""Single-node H3 music-video orchestrator: lipsync to a source song, PNG sequence in temp."""

import logging
import os

import torch

import comfy.model_management
import nodes

from comfy_extras.nodes_minimax_h3 import _encode_ref_audio

from .auto_chain import (
    _cpu_av_latent, _decode_audio, _decode_video, _open_live_session,
    _overlap_identity_frame, _pack_first_frame, _pack_ref_kwargs, _progress, _release_loaded_models,
    _resolve_clip_pack, _sample_segment, _segment_noise, _start_reference_images, _write_clip_preview,
)
from .chain_inputs import (
    clips_to_reuse,
    collect_music_video_reference_images,
)
from .latent_math import FPS, temporal_shape
from .music_video_prompt import parse_music_video_prompt, validate_music_video_prompt
from .node_help import NODE_HELP
from .release_utils import duration_to_requested_frames
from .seamless_stitch import fit_audio_length, resolve_saved_head_context, safe_tail_bridge_plan
from .song_math import (
    MUSIC_JOIN_TAIL_FRAMES, MUSIC_MAX_SEGMENTS, advance_cursor,
    frame_to_sample, grid_frame_count, mux_spans_are_contiguous, music_video_mux_spans,
    next_slice_start, slice_sample_range, song_frame_count,
)

_LOG = logging.getLogger("h3_continuous")
PNG_PREFIX = "video/h3_music_video"


def _song_seconds(song):
    if not isinstance(song, dict) or "waveform" not in song or "sample_rate" not in song:
        raise ValueError("h3_music_video: required AUDIO (the source song) is missing")
    sr = int(song["sample_rate"])
    if sr <= 0:
        raise ValueError("h3_music_video: song sample_rate must be > 0")
    n = int(song["waveform"].shape[-1])
    if n <= 0:
        raise ValueError("h3_music_video: song waveform is empty")
    return n / float(sr)


def _slice_song_audio(song, start_frame, grid_frames):
    waveform = song["waveform"]
    sr = int(song["sample_rate"])
    start, end = slice_sample_range(start_frame, grid_frames, sr)
    total = int(waveform.shape[-1])
    if start >= total:
        raise ValueError(
            f"h3_music_video: song slice starts at frame {start_frame} past the end of the audio"
        )
    chunk = waveform[..., start:min(end, total)].contiguous().clone()
    want = end - start
    if int(chunk.shape[-1]) < want:
        pad = want - int(chunk.shape[-1])
        zeros = torch.zeros(*chunk.shape[:-1], pad, dtype=chunk.dtype, device=chunk.device)
        chunk = torch.cat((chunk, zeros), dim=-1)
    return {"waveform": chunk, "sample_rate": sr}


def _encode_song_slice(audio_vae, song, start_frame, grid_frames):
    audio = _slice_song_audio(song, start_frame, grid_frames)
    z, _t = _encode_ref_audio(audio_vae, audio)
    return z.detach().cpu().contiguous()


def _apply_music_join_tail(handover, pixel_frame_count, context_frames, previous_latent, is_last):
    """Discard at least 1 s at each join and move Continue context before that cut."""
    if is_last:
        return handover
    from .latent_math import phase_aligned_extended_context_slice
    from .nodes import _streams_from_latent

    prev_video, _ignored = _streams_from_latent(previous_latent)
    freeze_tail = int((handover or {}).get("landing_tail_frames", 0) or 0)
    join_tail = max(MUSIC_JOIN_TAIL_FRAMES, freeze_tail)
    sl = phase_aligned_extended_context_slice(
        prev_video.shape[2], int(context_frames), desired_tail_frames=join_tail,
    )
    ignored = int(sl.get("ignored_tail_frames", join_tail))
    out = dict(handover or {})
    out["available"] = True
    out["frame_count"] = int(pixel_frame_count)
    out["landing_tail_frames"] = ignored
    out["handover_end_frame"] = int(pixel_frame_count) - ignored - 1
    out["phase_aligned_target_end_frame"] = int(out["handover_end_frame"])
    return out


def _write_music_video_clip_previews(images, audio_vae, latent, song, slice_start,
                                     latent_prefix, clip_index):
    """Same picture twice: original song slice, then H3's reconstructed soundtrack."""
    from .stream_stitch import clip_preview_path, mux_audio_onto_mp4

    song_audio = _slice_song_audio(song, slice_start, int(images.shape[0]))
    generated = _decode_audio(audio_vae, latent)
    _release_loaded_models()
    song_path = _write_clip_preview(
        images, latent_prefix, clip_index, audio=song_audio, suffix="song",
    )
    generated_path = clip_preview_path(latent_prefix, clip_index, suffix="generated")
    mux_audio_onto_mp4(song_path, generated, generated_path)
    return song_path, generated_path


def _stitch_saved_video(video_vae, saved_paths, video_crossfade_frames,
                        max_safe_tail_bridge_frames, unique_id=None,
                        filename_prefix=PNG_PREFIX,
                        max_video_frames=None, frames_dir=None):
    from .stream_stitch import stream_stitch_saved_clips

    result = stream_stitch_saved_clips(
        saved_paths, video_vae, audio_vae=None,
        filename_prefix=filename_prefix,
        video_crossfade_frames=video_crossfade_frames,
        audio_crossfade_ms=0.0,
        max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
        decode_audio=False,
        collect_audio=False,
        max_video_frames=max_video_frames,
        info_prefix="music-video stream stitch",
        progress_cb=lambda text: _progress(unique_id, text),
        frames_dir=frames_dir,
        keep_in_ram=frames_dir is None,
    )
    return result


def _effective_bridge(previous_handover, max_bridge, next_grid, next_head, next_tail):
    plan = safe_tail_bridge_plan(previous_handover, int(max_bridge))
    bridge = int(plan["safe_tail_bridge_frames"])
    cap = max(0, int(next_grid) - int(next_tail) - int(next_head) - 1)
    return min(bridge, cap)


def _mux_records_from_saved(saved_paths, max_safe_tail_bridge_frames):
    from .nodes import _read_safetensors_metadata

    records = []
    prev_handover = None
    total = len(saved_paths)
    for i, path in enumerate(saved_paths):
        metadata, handover = _read_safetensors_metadata(path)
        clip_index = i + 1
        is_last = clip_index == total
        if isinstance(handover, dict):
            handover["available"] = True
        head, _source = resolve_saved_head_context(metadata, clip_index, prev_handover)
        head = int(head or 0)
        grid = int(metadata.get("frame_count") or (handover or {}).get("frame_count") or 0)
        if grid <= 0:
            raise ValueError(f"h3_music_video: saved clip has no frame_count: {path}")
        if isinstance(handover, dict):
            handover["frame_count"] = grid
        tail = 0 if is_last else int((handover or {}).get("landing_tail_frames", 0))
        raw_start = metadata.get("song_slice_start_frame")
        if raw_start in (None, ""):
            raise ValueError(
                f"h3_music_video: saved clip {clip_index} is missing song_slice_start_frame; "
                "regenerate this chain from clip 1 with Music Video"
            )
        bridge = 0
        if i > 0:
            bridge = _effective_bridge(prev_handover, max_safe_tail_bridge_frames, grid, head, tail)
        records.append({
            "slice_start": int(raw_start),
            "grid_frames": grid,
            "head": head,
            "tail": tail,
            "bridge": bridge,
            "is_last": is_last,
        })
        prev_handover = handover
    return records


def _mux_original_song(song, spans, target_frames):
    waveform = song["waveform"]
    sr = int(song["sample_rate"])
    total = int(waveform.shape[-1])
    pieces = []
    for start_f, end_f in spans:
        start = max(0, min(total, frame_to_sample(start_f, sr)))
        end = max(start, min(total, frame_to_sample(end_f, sr)))
        pieces.append(waveform[..., start:end])
    if not pieces:
        raise ValueError("h3_music_video: mux produced no song spans")
    joined = pieces[0]
    for piece in pieces[1:]:
        joined = torch.cat((joined, piece.to(joined.device, joined.dtype)), dim=-1)
    target_samples = int(round(int(target_frames) / FPS * sr))
    joined = fit_audio_length(joined, target_samples)
    return {"waveform": joined.contiguous(), "sample_rate": sr}


class H3StudioMusicVideo:
    @classmethod
    def INPUT_TYPES(cls):
        from .png_sequence import save_images_to_disk_spec
        required = {
                "pack": ("H3_STUDIO_PACK", {
                    "tooltip": (
                        "Pack from H3 Studio Builder. Clip count and max duration come from the prompt, "
                        "or duration from this pack. The pack's song is sliced per clip for lipsync "
                        "(<Audio 1>); Builder audios are <Audio 2> and <Audio 3>. Optional <Model N> / "
                        "<Picture N> / <Video N> select a subset per CLIP body."
                    ),
                }),
                "clip": ("CLIP", {
                    "tooltip": "Qwen3-VL H3 text encoder. Encodes each clip's Ref2VA prompt and optional <Picture N> stills.",
                }),
                "video_vae": ("VAE", {
                    "tooltip": "MiniMax H3 Video VAE. Decodes each clip for Auto Handover, and decodes saved clips one at a time while writing the temp PNG sequence.",
                }),
                "audio_vae": ("VAE", {
                    "tooltip": "MiniMax H3 Audio VAE. Encodes each source-song slice as a Ref2VA <Audio 1> latent. The final soundtrack is the original song, not this VAE's decode.",
                }),
                "sampler": ("SAMPLER", {
                    "tooltip": "Sampler object from KSampler Select. Applied identically to every clip.",
                }),
                "sigmas": ("SIGMAS", {
                    "tooltip": "Noise schedule from Basic Scheduler (or equivalent). Shared by every clip.",
                }),
                "noise": ("NOISE", {
                    "tooltip": "Noise source from RandomNoise. Clip 1 uses this seed; clip i uses seed + (i-1).",
                }),
                "width": ("INT", {
                    "default": 1344, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32,
                    "tooltip": "Generation width in pixels. Must stay constant for the whole chain.",
                }),
                "height": ("INT", {
                    "default": 768, "min": 32, "max": nodes.MAX_RESOLUTION, "step": 32,
                    "tooltip": "Generation height in pixels. Must stay constant for the whole chain.",
                }),
                "prompt": ("STRING", {
                    "multiline": True, "dynamicPrompts": False, "default": "",
                    "tooltip": "One H3 Studio prompt for every clip (## Clip N with that clip's subject_definitions). A top-level subject_definitions block is legacy fallback. Legacy h3_music_video / CLIP blocks still parse. Single-prompt mode reads clip count from this text. One-prompt-per-clip mode shows duration and segments widgets plus one editor per clip.",
                }),
                "duration": ("FLOAT", {
                    "default": 10.0, "min": 5.0, "max": 15.0, "step": 0.001, "round": 0.001,
                    "tooltip": (
                        "Maximum requested length of any clip in seconds at 24 fps. H3 snaps upward "
                        "(10.0 s -> 243 frames ~= 10.125 s, 8.0 s -> 8.0 s). Must match the prompt "
                        "header max_duration_seconds. Individual CLIP blocks may be shorter. "
                        "Lower this at high resolution to avoid OOM."
                    ),
                }),
                "context_frames": (["5", "22", "39"], {
                    "default": "22",
                    "tooltip": "Minimum motion history copied from the previous AV latent into the next clip. 22 is the tested default. Audio context is the song slice, not the previous generated soundtrack.",
                }),
                "handover_preset": (["Balanced", "Motion Safe"], {
                    "default": "Balanced",
                    "tooltip": "Auto Handover detector used after every clip. Balanced = tested freeze_hold 8 with a 3-frame safety margin. Motion Safe = 6-frame safety.",
                }),
                "save_segment_latents": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Keep each clip's full AV latent as safetensors under latent_prefix. Needed to resume later.",
                }),
                "save_clip_videos": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "After each clip's handover decode, write two playable MP4s next to the latent: clip_00001_song.mp4 (original song slice) and clip_00001_generated.mp4 (H3 reconstructed audio). Same picture, two soundtracks, so you can compare lipsync. The stitched IMAGE is the temp PNG sequence, not these previews.",
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
                    "default": "h3_music_video/clip",
                    "tooltip": "Output path prefix relative to ComfyUI/output. Clip 1 is <prefix>_00001.safetensors. Metadata stores the song cursor for resume.",
                }),
                "resume_from_clip": ("INT", {
                    "default": 1, "min": 1, "max": MUSIC_MAX_SEGMENTS, "step": 1,
                    "tooltip": "1 = generate from scratch. 2+ = load only the previous clip's latent and start generating at this clip. Earlier slots must already exist. Reused clips are not decoded until the final stitch.",
                }),
                "stop_after_clip": ("INT", {
                    "default": 0, "min": 0, "max": MUSIC_MAX_SEGMENTS, "step": 1,
                    "tooltip": "0 = generate until kept picture covers the song. N = stop after clip N (reuse + generate), then stitch 1..N. Use with resume_from_clip for short tests (e.g. resume 2, stop 2). Skips full-song clip_count coverage checks.",
                }),
                "video_crossfade_frames": ("INT", {
                    "default": 4, "min": 0, "max": 16, "step": 1,
                    "tooltip": "After Safe Tail Bridge, blend this many context-aligned video frames at each join. 4 is the tested default.",
                }),
                "audio_crossfade_ms": ("FLOAT", {
                    "default": 15.0, "min": 0.0, "max": 100.0, "step": 1.0,
                    "tooltip": "Kept for join-knob parity. Muxed master-song slices that are contiguous in the source are concatenated without a crossfade.",
                }),
                "max_safe_tail_bridge_frames": ("INT", {
                    "default": 2, "min": 0, "max": 4, "step": 1,
                    "tooltip": "Reuse up to this many detector-approved rendered frames from the previous clip and skip the same number of early video frames in the next clip. Mux follows those kept pixels.",
                }),
                "save_images_to_disk": save_images_to_disk_spec(),
            }
        duration_spec = required.pop("duration", None)
        optional = {
                "song_audio_lock": ("FLOAT", {
                    "default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": (
                        "Pin this clip's generated audio latent to the song slice. "
                        "0 = H3 generates audio (current). 1 = copy the song latent and do not denoise it; "
                        "video still generates. 0.5 is a useful first try for tighter lips. "
                        "The muxed master soundtrack stays the original song either way."
                    ),
                }),
            }
        if duration_spec:
            optional["duration"] = duration_spec
        optional["segments"] = ("INT", {
            "default": 3, "min": 1, "max": MUSIC_MAX_SEGMENTS, "step": 1,
            "tooltip": (
                "How many ## Clip sections to show in one-prompt-per-clip mode. "
                "Clip 1 is Start; later clips are Continue. The prompt document stores those bodies. "
                "Single-prompt mode still reads clip count from the prompt."
            ),
        })
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
    DESCRIPTION = NODE_HELP["H3StudioMusicVideo"]

    def generate(self, pack, prompt_mode="single", **kwargs):
        from .pack import require_pack
        from .prompt_document import duration_and_segments_from_pack_or_prompt
        pack = require_pack(pack)
        mode = str(prompt_mode or "single").strip().lower().replace(" ", "_")
        if mode == "per_clip" and kwargs.get("duration") is not None and not kwargs.get("clip_fix"):
            kwargs["duration"] = float(kwargs["duration"])
        else:
            duration, _segments = duration_and_segments_from_pack_or_prompt(
                pack, kwargs.get("prompt") or "", need_segments=False,
            )
            kwargs["duration"] = duration
        kwargs["pack"] = pack
        kwargs["model_1"] = pack["models"][0]["model"]
        song = pack.get("song")
        if not isinstance(song, dict) or song.get("waveform") is None:
            raise ValueError(
                "h3_studio: pack has no song; set Music Video mode on Builder and wire Load Song"
            )
        kwargs["song"] = song
        return self._generate_chain(**kwargs)

    def _generate_chain(self, model_1, clip, video_vae, audio_vae, sampler, sigmas, noise, song, prompt,
                 width, height, duration, context_frames="22", handover_preset="Balanced",
                 save_segment_latents=True, save_clip_videos=True,
                 freeze_overlap=True, overlap_soft_steps=0, song_audio_lock=0.9,
                 latent_prefix="h3_music_video/clip",
                 resume_from_clip=1, stop_after_clip=0,
                 video_crossfade_frames=4, audio_crossfade_ms=15.0, max_safe_tail_bridge_frames=2,
                 save_images_to_disk=False,
                 unique_id=None, pack=None, clip_fix=False, clip_index="", **kwargs):
        from .nodes import (
            H3ContinuousAnalyzeHandoverV11, H3ContinuousContinueV11,
            H3ContinuousLoadLatent, H3ContinuousSaveLatent, H3ContinuousStartV11,
            _resolve_continue_slice, _saved_chain_file, _streams_from_latent,
        )

        if clip_fix:
            return self._generate_fix_chain(
                model_1, clip, video_vae, audio_vae, sampler, sigmas, noise, song, prompt,
                width, height, duration, context_frames=context_frames,
                handover_preset=handover_preset, save_segment_latents=save_segment_latents,
                save_clip_videos=save_clip_videos, freeze_overlap=freeze_overlap,
                overlap_soft_steps=overlap_soft_steps, song_audio_lock=song_audio_lock,
                latent_prefix=latent_prefix, video_crossfade_frames=video_crossfade_frames,
                audio_crossfade_ms=audio_crossfade_ms,
                max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
                save_images_to_disk=save_images_to_disk, unique_id=unique_id, pack=pack,
                clip_index=clip_index, **kwargs,
            )

        parsed = parse_music_video_prompt(prompt)
        song_seconds = _song_seconds(song)
        context_frames = str(context_frames)
        stop_after = int(stop_after_clip or 0)
        reference_images = collect_music_video_reference_images(kwargs)
        if pack is not None:
            from .pack import require_pack
            pack = require_pack(pack)
            model_1 = pack["models"][0]["model"]
        parsed_clips = parsed["clips"]
        prompt_n = int(parsed["clip_count"])
        max_grid_frames, _, _ = temporal_shape(duration_to_requested_frames(duration))
        song_frames = song_frame_count(song_seconds)

        from .png_sequence import (
            node_temp_frames_dir, pack_image_output, require_image_ram, warn_disk_budget,
        )
        save_images_to_disk = bool(save_images_to_disk)
        n_clips = stop_after if stop_after > 0 else prompt_n
        extra = (
            f"Music Video: {n_clips} clip(s) x {float(duration):g}s "
            f"(stitched picture ~{song_frames} frames / {song_seconds:.1f}s)"
        )
        require_image_ram(song_frames, width, height, save_images_to_disk)
        out_frames = None
        if save_images_to_disk:
            warn_disk_budget(
                grid_frame_count(duration) * n_clips, width, height,
                unique_id=unique_id, extra=extra,
            )
            out_frames = node_temp_frames_dir(PNG_PREFIX, unique_id)
        validate_music_video_prompt(
            parsed, song_seconds, duration, stop_after_clip=stop_after,
        )

        reuse = clips_to_reuse(resume_from_clip, MUSIC_MAX_SEGMENTS)
        if stop_after > 0 and int(resume_from_clip) > stop_after:
            raise ValueError(
                f"h3_music_video: resume_from_clip={int(resume_from_clip)} is past "
                f"stop_after_clip={stop_after}"
            )
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
        cursor = 0
        identity_frame = None
        save_clip_videos = bool(save_clip_videos)
        freeze_overlap = bool(freeze_overlap)
        overlap_soft_steps = int(overlap_soft_steps)
        song_audio_lock = min(max(float(song_audio_lock), 0.0), 1.0)
        session = None
        live_stitch = not reuse

        def ensure_session():
            nonlocal session
            if session is not None:
                return
            session = _open_live_session(
                filename_prefix=PNG_PREFIX,
                video_crossfade_frames=video_crossfade_frames,
                audio_crossfade_ms=0.0,
                max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
                decode_audio=False,
                collect_audio=False,
                max_video_frames=song_frames,
                info_prefix="music-video stream stitch",
                frames_dir=out_frames,
                keep_in_ram=not save_images_to_disk,
            )

        if reuse:
            last_reused = reuse[-1]
            _progress(unique_id, f"Loading saved clip {last_reused} (resume at {resume_from_clip})")
            _LOG.info(
                "h3_music_video: resume from clip %s, keep 1–%s on disk, load clip %s only",
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
            from .nodes import _read_safetensors_metadata
            metadata, _h = _read_safetensors_metadata(resolved)
            raw_cursor = metadata.get("song_cursor_after")
            raw_start = metadata.get("song_slice_start_frame")
            if raw_cursor not in (None, ""):
                cursor = int(raw_cursor)
            elif raw_start not in (None, ""):
                tail = int((handover or {}).get("landing_tail_frames", 0))
                saved_grid = int(
                    metadata.get("frame_count")
                    or (handover or {}).get("frame_count")
                    or max_grid_frames
                )
                cursor = advance_cursor(int(raw_start), saved_grid, tail, is_last=False)
            else:
                raise ValueError(
                    f"h3_music_video: saved clip {last_reused} has no song cursor metadata; "
                    "regenerate from clip 1"
                )
            _LOG.info("h3_music_video: reused clip %s from %s (cursor %s)", last_reused, resolved, cursor)
            _progress(unique_id, f"Identity still from saved clip {last_reused}")
            resume_images = _decode_video(video_vae, last_latent)
            identity_frame = _overlap_identity_frame(
                resume_images, last_latent, context_frames, last_handover,
            )
            del resume_images
            _release_loaded_models()

        clip_index = int(resume_from_clip)
        while True:
            if cursor >= song_frames:
                break
            if clip_index > MUSIC_MAX_SEGMENTS:
                raise ValueError(
                    f"h3_music_video: covered only {cursor / FPS:.3f}s of {song_seconds:.3f}s "
                    f"after {MUSIC_MAX_SEGMENTS} clips; raise per-clip duration"
                )
            comfy.model_management.throw_exception_if_processing_interrupted()
            i = clip_index - 1
            if i >= prompt_n:
                raise ValueError(
                    f"h3_music_video: need CLIP {clip_index} but prompt only has {prompt_n} "
                    f"block(s). Keep the full document, or set stop_after_clip so generation "
                    f"stops inside the prompt."
                )
            spec = parsed_clips[i]
            clip_prompt = spec["prompt"]
            resolved = _resolve_clip_pack(pack, clip_prompt, song_audio=True)
            if resolved is not None:
                clip_prompt = resolved["prompt"]
                clip_model = resolved["model"]
                pack_refs = _pack_ref_kwargs(resolved, audio_vae)
                clip_images = _start_reference_images(resolved) if i == 0 else (resolved["pictures"] or [])
            else:
                clip_model = model_1
                pack_refs = {}
                clip_images = reference_images
            clip_duration = float(spec["duration_seconds"])
            grid_frames = int(spec["grid_frames"])
            _release_loaded_models()

            head = 0
            if i == 0:
                slice_start = 0
            else:
                prev_video, _prev_audio = _streams_from_latent(previous_latent)
                sl, _src = _resolve_continue_slice(
                    prev_video, int(context_frames), "auto", "phase_aligned_extended",
                    34, last_handover,
                )
                head = int(sl.get("actual_context_frames", context_frames))
                slice_start = next_slice_start(cursor, head)

            stop_here = stop_after > 0 and clip_index >= stop_after
            is_last = slice_start + grid_frames >= song_frames or stop_here
            role = "Start" if i == 0 else ("Finish" if is_last else "Continue")
            _progress(
                unique_id,
                f"Clip {clip_index} ({role}) — {clip_duration:.3f}s slice @ {slice_start} / {song_frames} frames",
            )
            _LOG.info(
                "h3_music_video: clip %s duration=%s slice_start=%s grid=%s cursor=%s song_frames=%s last=%s",
                clip_index, clip_duration, slice_start, grid_frames, cursor, song_frames, is_last,
            )
            song_latent = _encode_song_slice(audio_vae, song, slice_start, grid_frames)
            _release_loaded_models()
            _progress(unique_id, f"Clip {clip_index} ({role}) — encoding")

            if i == 0:
                start_still = _pack_first_frame(pack)
                if resolved is not None:
                    _LOG.info(
                        "h3_music_video: clip 1 first_frame=%s sole_first_frame=%s ref_pictures=%s",
                        start_still is not None,
                        bool(resolved.get("sole_first_frame")),
                        len(clip_images or []),
                    )
                positive, empty = start.build(
                    clip, video_vae, clip_prompt, width, height, clip_duration,
                    first_frame=start_still, last_frame=None,
                    reference_images=clip_images, song_audio_latent=song_latent,
                    song_audio_lock=song_audio_lock,
                    **pack_refs,
                )
                head_context = 0
            else:
                positive, empty, head_context, _ignored_tail, handover_info = cont.build(
                    clip, video_vae, previous_latent, clip_prompt, width, height, clip_duration,
                    context_frames=context_frames, handover_mode="auto",
                    alignment_mode="phase_aligned_extended",
                    handover=last_handover, last_frame=None,
                    reference_images=clip_images, song_audio_latent=song_latent,
                    freeze_overlap=freeze_overlap, overlap_soft_steps=overlap_soft_steps,
                    identity_frame=identity_frame, song_audio_lock=song_audio_lock,
                    **pack_refs,
                )
                notes.append(f"clip {clip_index} {handover_info}")
                if int(head_context) != int(head):
                    _LOG.warning(
                        "h3_music_video: precomputed head %s != Continue head %s",
                        head, head_context,
                    )

            del song_latent
            _release_loaded_models()
            _progress(unique_id, f"Clip {clip_index} ({role}) — sampling")
            sampled = _sample_segment(
                clip_model, positive, sampler, sigmas, _segment_noise(noise, i), empty,
                join_prefix=(i != 0),
            )
            last_latent = _cpu_av_latent(sampled)
            del sampled, empty
            _release_loaded_models()

            _progress(unique_id, f"Clip {clip_index} ({role}) — handover decode")
            images = _decode_video(video_vae, last_latent)
            handover, status, *_rest = analyzer.analyze(
                images, preset=handover_preset, context_frames=context_frames,
            )
            previous_latent = last_latent
            handover = _apply_music_join_tail(
                handover, int(images.shape[0]), context_frames, last_latent, is_last,
            )
            last_handover = handover
            identity_frame = _overlap_identity_frame(
                images, last_latent, context_frames, handover,
            )
            tail = 0 if is_last else int(handover.get("landing_tail_frames", 0))
            cursor = advance_cursor(slice_start, grid_frames, tail, is_last=is_last)
            del positive

            extra = {
                "music_video": "1",
                "song_slice_start_frame": str(int(slice_start)),
                "song_cursor_after": str(int(cursor)),
            }
            latent_path, save_info = saver.save(
                last_latent, latent_prefix, clip_index=clip_index,
                handover=handover, head_context_frames=int(head_context or 0),
                extra_metadata=extra,
            )
            saved_paths.append(latent_path)
            generated_paths.append(latent_path)
            notes.append(f"clip {clip_index} {status} | saved {save_info}")
            _LOG.info("h3_music_video: clip %s saved %s (cursor %s)", clip_index, latent_path, cursor)
            if save_clip_videos:
                song_preview, generated_preview = _write_music_video_clip_previews(
                    images, audio_vae, last_latent, song, slice_start,
                    latent_prefix, clip_index,
                )
                notes.append(f"clip {clip_index} preview {song_preview}")
                notes.append(f"clip {clip_index} generated preview {generated_preview}")
                _LOG.info(
                    "h3_music_video: clip %s previews %s | %s",
                    clip_index, song_preview, generated_preview,
                )
            if live_stitch:
                from .nodes import _read_safetensors_metadata
                metadata, _ignored = _read_safetensors_metadata(latent_path)
                ensure_session()
                session.add_decoded_clip(images, None, metadata, handover, clip_index, is_last)
            del images
            _release_loaded_models()
            if cursor >= song_frames:
                break
            if stop_after > 0 and clip_index >= stop_after:
                break
            clip_index += 1

        _release_loaded_models()
        try:
            if session is not None:
                result = session.finalize()
            else:
                result = _stitch_saved_video(
                    video_vae, saved_paths,
                    video_crossfade_frames=video_crossfade_frames,
                    max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
                    unique_id=unique_id,
                    max_video_frames=song_frames,
                    frames_dir=out_frames,
                )
        except BaseException:
            if session is not None and not session._closed:
                session.abort()
            raise
        images = result["images"]
        frames_dir = result["frames_dir"]
        records = _mux_records_from_saved(saved_paths, max_safe_tail_bridge_frames)
        spans = music_video_mux_spans(records)
        audio = _mux_original_song(song, spans, int(result["video_frames"]))
        stitch_info = result["info"]
        mux_note = "contiguous master" if mux_spans_are_contiguous(spans) else "non-contiguous master spans"
        _release_loaded_models()
        clip_total = len(saved_paths)
        _progress(unique_id, f"Done — {clip_total} clip(s) muxed")

        if not save_segment_latents:
            for path in generated_paths:
                try:
                    os.remove(path)
                except OSError as exc:
                    _LOG.warning("h3_music_video: could not delete temporary segment %s: %s", path, exc)

        resume_note = f"resume from clip {int(resume_from_clip)} | " if reuse else ""
        stop_note = f"stop after clip {stop_after} | " if stop_after > 0 else ""
        xf_note = f"audio_crossfade_ms={float(audio_crossfade_ms):g} (skipped on contiguous master) | "
        info = (
            f"music video | {resume_note}{stop_note}{xf_note}{clip_total} clip(s) | song {song_seconds:.3f}s | "
            f"picture {int(result['video_frames']) / FPS:.3f}s | max {parsed['max_duration_seconds']:.3f}s | mux {mux_note} | "
            f"keep latents={'yes' if save_segment_latents else 'no'} | clip videos={'yes' if save_clip_videos else 'no'} | "
            f"{'png ' + str(frames_dir) if frames_dir else 'IMAGE in RAM'} | {stitch_info}"
        )
        if notes:
            info += " | " + " ; ".join(notes[-clip_total * 4:])
        _LOG.info("h3_continuous: %s", info)
        return pack_image_output(images, frames_dir, audio, info, last_latent, last_handover)

    def _generate_fix_chain(self, model_1, clip, video_vae, audio_vae, sampler, sigmas, noise, song, prompt,
                 width, height, duration, context_frames="22", handover_preset="Balanced",
                 save_segment_latents=True, save_clip_videos=True,
                 freeze_overlap=True, overlap_soft_steps=0, song_audio_lock=0.9,
                 latent_prefix="h3_music_video/clip",
                 video_crossfade_frames=4, audio_crossfade_ms=15.0, max_safe_tail_bridge_frames=2,
                 save_images_to_disk=False, unique_id=None, pack=None, clip_index="", **kwargs):
        from .clip_fix_chain import clip_fix_neighbors, expand_fix_clip
        from .clip_fixer import prepare_clip_fix
        from .latent_math import steps_for_pixel_frames
        from .nodes import (
            H3ContinuousAnalyzeHandoverV11, H3ContinuousContinueV11,
            H3ContinuousLoadLatent, H3ContinuousSaveLatent, H3ContinuousStartV11,
            _read_safetensors_metadata, _saved_chain_file, _streams_from_latent,
        )

        song_seconds = _song_seconds(song)
        context_frames = str(context_frames)
        reference_images = collect_music_video_reference_images(kwargs)
        if pack is not None:
            from .pack import require_pack
            pack = require_pack(pack)
            model_1 = pack["models"][0]["model"]
        song_frames = song_frame_count(song_seconds)
        prepared = prepare_clip_fix(latent_prefix, prompt, clip_index)
        story_n = prepared["story_n"]
        regen = prepared["regen"]
        saved_set = set(prepared["saved"])

        from .png_sequence import (
            node_temp_frames_dir, pack_image_output, require_image_ram, warn_disk_budget,
        )
        save_images_to_disk = bool(save_images_to_disk)
        extra = (
            f"Music Video clip fix: {len(regen)} clip(s) / {story_n} on disk "
            f"(stitched picture ~{song_frames} frames / {song_seconds:.1f}s)"
        )
        try:
            require_image_ram(song_frames, width, height, save_images_to_disk)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc} Clip Fixer restitches the full {story_n}-clip video "
                f"({song_frames} frames), not only the regenerated clip(s)."
            ) from exc
        out_frames = None
        if save_images_to_disk:
            warn_disk_budget(
                song_frames, width, height,
                unique_id=unique_id, extra=extra,
            )
            out_frames = node_temp_frames_dir(PNG_PREFIX, unique_id)

        start = H3ContinuousStartV11()
        cont = H3ContinuousContinueV11()
        analyzer = H3ContinuousAnalyzeHandoverV11()
        saver = H3ContinuousSaveLatent()
        loader = H3ContinuousLoadLatent()
        notes = [f"backup {prepared['backup_dir']}"]
        save_clip_videos = bool(save_clip_videos)
        freeze_overlap = bool(freeze_overlap)
        overlap_soft_steps = int(overlap_soft_steps)
        song_audio_lock = min(max(float(song_audio_lock), 0.0), 1.0)
        last_latent = None
        last_handover = None
        previous_latent = None
        identity_frame = None
        generated_this_run = set()

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

        for clip_index_n in regen:
            comfy.model_management.throw_exception_if_processing_interrupted()
            i = clip_index_n - 1
            clip_prompt = expand_fix_clip(prompt, clip_index_n, song_audio=True, kwargs=kwargs)
            resolved = _resolve_clip_pack(pack, clip_prompt, song_audio=True)
            if resolved is not None:
                clip_prompt = resolved["prompt"]
                clip_model = resolved["model"]
                pack_refs = _pack_ref_kwargs(resolved, audio_vae)
                clip_images = _start_reference_images(resolved) if i == 0 else (resolved["pictures"] or [])
            else:
                clip_model = model_1
                pack_refs = {}
                clip_images = reference_images

            existing_path = _saved_chain_file(latent_prefix, clip_index_n)
            metadata, _old_handover = _read_safetensors_metadata(existing_path)
            raw_start = metadata.get("song_slice_start_frame")
            if raw_start in (None, ""):
                raise ValueError(
                    f"h3_music_video: saved clip {clip_index_n} has no song_slice_start_frame"
                )
            slice_start = int(raw_start)
            grid_frames = int(metadata.get("frame_count") or 0)
            if grid_frames <= 0:
                raise ValueError(f"h3_music_video: saved clip {clip_index_n} has no frame_count")
            clip_duration = float(grid_frames) / FPS
            prev_i, next_i = clip_fix_neighbors(clip_index_n, regen, saved_set)
            is_last = clip_index_n == story_n
            role = "Start" if i == 0 else ("Finish" if is_last else "Continue")
            _release_loaded_models()

            if prev_i is None and clip_index_n != 1:
                raise ValueError(
                    f"h3_music_video: clip {clip_index_n} needs saved clip {clip_index_n - 1}"
                )
            if clip_index_n > 1:
                if prev_i in generated_this_run and previous_latent is not None:
                    pass
                else:
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

            _progress(
                unique_id,
                f"Clip {clip_index_n} ({role}) — {clip_duration:.3f}s slice @ {slice_start} / {song_frames} frames",
            )
            song_latent = _encode_song_slice(audio_vae, song, slice_start, grid_frames)
            _release_loaded_models()
            _progress(unique_id, f"Clip {clip_index_n} ({role}) — encoding")

            if clip_index_n == 1:
                start_still = _pack_first_frame(pack)
                positive, empty = start.build(
                    clip, video_vae, clip_prompt, width, height, clip_duration,
                    first_frame=start_still, last_frame=None,
                    reference_images=clip_images, song_audio_latent=song_latent,
                    song_audio_lock=song_audio_lock,
                    **pack_refs,
                )
                head_context = 0
            else:
                extra_end = {}
                if end_latent is not None:
                    extra_end["end_latent"] = end_latent
                    extra_end["end_skip_steps"] = end_skip
                    extra_end["pack_end_audio"] = False
                positive, empty, head_context, _ignored_tail, handover_info = cont.build(
                    clip, video_vae, previous_latent, clip_prompt, width, height, clip_duration,
                    context_frames=context_frames, handover_mode="auto",
                    alignment_mode="phase_aligned_extended",
                    handover=last_handover, last_frame=None,
                    reference_images=clip_images, song_audio_latent=song_latent,
                    freeze_overlap=freeze_overlap, overlap_soft_steps=overlap_soft_steps,
                    identity_frame=identity_frame, song_audio_lock=song_audio_lock,
                    **extra_end, **pack_refs,
                )
                notes.append(f"clip {clip_index_n} {handover_info}")

            del song_latent, end_latent
            _release_loaded_models()
            _progress(unique_id, f"Clip {clip_index_n} ({role}) — sampling")
            sampled = _sample_segment(
                clip_model, positive, sampler, sigmas, _segment_noise(noise, i), empty,
                join_prefix=(clip_index_n != 1),
            )
            last_latent = _cpu_av_latent(sampled)
            del sampled, empty
            _release_loaded_models()

            _progress(unique_id, f"Clip {clip_index_n} ({role}) — handover decode")
            images = _decode_video(video_vae, last_latent)
            handover, status, *_rest = analyzer.analyze(
                images, preset=handover_preset, context_frames=context_frames,
            )
            previous_latent = last_latent
            handover = _apply_music_join_tail(
                handover, int(images.shape[0]), context_frames, last_latent, is_last,
            )
            last_handover = handover
            identity_frame = _overlap_identity_frame(
                images, last_latent, context_frames, handover,
            )
            tail = 0 if is_last else int(handover.get("landing_tail_frames", 0))
            cursor = advance_cursor(slice_start, grid_frames, tail, is_last=is_last)
            del positive
            extra = {
                "music_video": "1",
                "song_slice_start_frame": str(int(slice_start)),
                "song_cursor_after": str(int(cursor)),
            }
            latent_path, save_info = saver.save(
                last_latent, latent_prefix, clip_index=clip_index_n,
                handover=handover, head_context_frames=int(head_context or 0),
                extra_metadata=extra,
            )
            generated_this_run.add(clip_index_n)
            notes.append(f"clip {clip_index_n} {status} | saved {save_info}")
            _LOG.info("h3_music_video: clip fix %s saved %s", clip_index_n, latent_path)
            if save_clip_videos:
                song_preview, generated_preview = _write_music_video_clip_previews(
                    images, audio_vae, last_latent, song, slice_start,
                    latent_prefix, clip_index_n,
                )
                notes.append(f"clip {clip_index_n} preview {song_preview}")
                notes.append(f"clip {clip_index_n} generated preview {generated_preview}")
            del images
            _release_loaded_models()

        saved_paths = [_saved_chain_file(latent_prefix, n) for n in range(1, story_n + 1)]
        _release_loaded_models()
        result = _stitch_saved_video(
            video_vae, saved_paths,
            video_crossfade_frames=video_crossfade_frames,
            max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
            unique_id=unique_id,
            max_video_frames=song_frames,
            frames_dir=out_frames,
        )
        images = result["images"]
        frames_dir = result["frames_dir"]
        records = _mux_records_from_saved(saved_paths, max_safe_tail_bridge_frames)
        spans = music_video_mux_spans(records)
        audio = _mux_original_song(song, spans, int(result["video_frames"]))
        stitch_info = result["info"]
        mux_note = "contiguous master" if mux_spans_are_contiguous(spans) else "non-contiguous master spans"
        _release_loaded_models()
        clip_total = len(saved_paths)
        _progress(unique_id, f"Done — {clip_total} clip(s) muxed")
        xf_note = f"audio_crossfade_ms={float(audio_crossfade_ms):g} (skipped on contiguous master) | "
        info = (
            f"music video clip fix | clips {','.join(str(n) for n in regen)} | "
            f"{xf_note}{clip_total} clip(s) | song {song_seconds:.3f}s | "
            f"picture {int(result['video_frames']) / FPS:.3f}s | mux {mux_note} | "
            f"backup {prepared['backup_dir']} | "
            f"{'png ' + str(frames_dir) if frames_dir else 'IMAGE in RAM'} | {stitch_info}"
        )
        if notes:
            info += " | " + " ; ".join(notes[-clip_total * 4:])
        _LOG.info("h3_continuous: %s", info)
        return pack_image_output(images, frames_dir, audio, info, last_latent, last_handover)


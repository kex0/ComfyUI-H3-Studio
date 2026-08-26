"""Memory-bounded saved-clip stitch: decode one clip, write PNG, discard pixels."""

from __future__ import annotations

import logging
import os
import shutil

import numpy as np
import torch

import comfy.model_management

from .latent_math import FPS, pixel_frames
from .png_sequence import (
    load_png_sequence,
    png_count,
    png_frame_path,
    save_png_frame,
    unique_temp_frames_dir,
    write_frames_fps,
)
from .seamless_stitch import (
    LUMINANCE_ANALYSIS_FRAMES, apply_luminance_gain_fade, apply_rgb_gain,
    blend_audio_overlap, blend_video_overlap, close_loop_av, estimate_luminance_gain,
    extract_safe_tail_bridge_images, fit_audio_length, frame_trimmed_audio,
    resolve_saved_head_context, safe_tail_bridge_plan,
)

_LOG = logging.getLogger("h3_continuous")


def png_frames_dir(base_path: str) -> str:
    return os.path.splitext(base_path)[0] + "_frames"


def clip_preview_path(latent_prefix: str, clip_index: int, suffix: str = "") -> str:
    from .nodes import _saved_chain_base
    base = _saved_chain_base(latent_prefix)
    folder = os.path.dirname(base)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tag = f"_{suffix}" if suffix else ""
    return f"{base}_{int(clip_index):05d}{tag}.mp4"


def encode_clip_preview(images, out_path: str, crf: int = 18, audio: dict | None = None) -> str:
    """Write a complete playable MP4 for one decoded clip so it can be watched mid-run."""
    import av
    import numpy as np
    from fractions import Fraction

    if images is None or int(images.shape[0]) == 0:
        raise ValueError("h3_continuous: clip preview has no frames")
    h, w = int(images.shape[1]), int(images.shape[2])
    if w % 2 or h % 2:
        raise ValueError(f"H.264 output requires even dimensions, got {w}x{h}")
    output = av.open(out_path, mode="w", options={"movflags": "use_metadata_tags+faststart"})
    try:
        vstream = output.add_stream("h264", rate=Fraction(int(FPS), 1))
        vstream.codec_context.max_b_frames = 0
        vstream.codec_context.time_base = Fraction(1, int(FPS))
        vstream.width = w
        vstream.height = h
        vstream.pix_fmt = "yuv420p"
        vstream.options = {"crf": str(int(crf))}
        astream = None
        layout = None
        sr = None
        if audio is not None:
            sr = int(audio["sample_rate"])
            _channels, layout = _pcm_layout(audio["waveform"])
            astream = output.add_stream("aac", rate=sr, layout=layout)
        for i, frame_tensor in enumerate(images):
            img = (frame_tensor * 255).clamp(0, 255).byte().detach().cpu().numpy()
            frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(img), format="rgb24")
            frame = frame.reformat(format="yuv420p")
            frame.pts = i
            frame.time_base = Fraction(1, int(FPS))
            for packet in vstream.encode(frame):
                output.mux(packet)
        for packet in vstream.encode(None):
            output.mux(packet)
        if astream is not None:
            _encode_pcm_to_aac(output, astream, audio["waveform"], sr, layout)
        output.close()
        output = None
    finally:
        if output is not None:
            try:
                output.close()
            except Exception:
                pass
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
    return out_path


def _pcm_layout(waveform: torch.Tensor) -> tuple[int, str]:
    if waveform.ndim != 3:
        raise ValueError(f"h3_continuous: mux audio expected [B,C,T], got {tuple(waveform.shape)}")
    channels = int(waveform.shape[1])
    if channels not in (1, 2):
        raise ValueError(f"h3_continuous: mux supports mono/stereo, got {channels} channels")
    return channels, ("mono" if channels == 1 else "stereo")


def _encode_pcm_to_aac(output, astream, waveform: torch.Tensor, sample_rate: int, layout: str):
    """Encode PCM in AAC-sized chunks so a full song never becomes one AudioFrame."""
    import av
    import numpy as np
    from fractions import Fraction

    pcm = waveform[0].float().detach().cpu().contiguous()
    hop = 1024
    pts = 0
    total = int(pcm.shape[-1])
    while pts < total:
        chunk = pcm[..., pts:pts + hop].contiguous().numpy()
        frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(chunk), format="fltp", layout=layout)
        frame.sample_rate = sample_rate
        frame.pts = pts
        frame.time_base = Fraction(1, sample_rate)
        for packet in astream.encode(frame):
            output.mux(packet)
        pts += int(chunk.shape[-1])
    for packet in astream.encode(None):
        output.mux(packet)


def mux_audio_onto_mp4(video_path: str, audio: dict, out_path: str, crf: int = 18) -> str:
    """Copy H.264 from ``video_path`` and add AAC from a Comfy AUDIO dict."""
    import av
    import numpy as np
    from fractions import Fraction

    waveform = audio["waveform"]
    sr = int(audio["sample_rate"])
    _channels, layout = _pcm_layout(waveform)

    incoming = av.open(video_path)
    output = av.open(out_path, mode="w", options={"movflags": "use_metadata_tags+faststart"})
    try:
        v_in = incoming.streams.video[0]
        copy_packets = hasattr(output, "add_stream_from_template")
        if copy_packets:
            v_out = output.add_stream_from_template(v_in, opaque=True)
        else:
            v_out = output.add_stream("h264", rate=v_in.average_rate or Fraction(int(FPS), 1))
            v_out.codec_context.max_b_frames = 0
            v_out.width = v_in.width
            v_out.height = v_in.height
            v_out.pix_fmt = "yuv420p"
            v_out.options = {"crf": str(int(crf))}
        a_out = output.add_stream("aac", rate=sr, layout=layout)
        if copy_packets:
            for packet in incoming.demux(v_in):
                if packet.dts is None:
                    continue
                packet.stream = v_out
                output.mux(packet)
        else:
            written = 0
            for frame in incoming.decode(v_in):
                rgb = frame.to_ndarray(format="rgb24")
                out_frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
                out_frame = out_frame.reformat(format="yuv420p")
                out_frame.pts = written
                out_frame.time_base = Fraction(1, int(FPS))
                for packet in v_out.encode(out_frame):
                    output.mux(packet)
                written += 1
            for packet in v_out.encode(None):
                output.mux(packet)
        _encode_pcm_to_aac(output, a_out, waveform, sr, layout)
        output.close()
        output = None
    finally:
        incoming.close()
        if output is not None:
            try:
                output.close()
            except Exception:
                pass
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
    return out_path


def _read_png_u8(frames_dir: str, index: int):
    from PIL import Image
    return np.array(Image.open(png_frame_path(frames_dir, index)).convert("RGB"))


def _close_loop_png(frames_dir: str, overlap_frames: int, audio: dict | None,
                    audio_crossfade_ms: float) -> tuple[str, dict | None, dict, int]:
    """Rewrite a PNG sequence with the same wrap as ``close_loop_av``.

    Only the opening window, the last ``C+2`` frames, and the blended seam
    stay in RAM. The rest is copied through one frame at a time.
    """
    c = max(0, int(overlap_frames))
    n = png_count(frames_dir)
    dst = frames_dir.rstrip("\\/") + "_loop"
    if os.path.exists(dst):
        shutil.rmtree(dst)
    write_frames_fps(dst, FPS)
    written = 0
    first = []
    hold = []
    ok = False

    def emit(rgb):
        nonlocal written
        save_png_frame(dst, written, rgb)
        written += 1

    try:
        hold_max = c + 2 if c else 0
        for i in range(n):
            rgb = _read_png_u8(frames_dir, i)
            if c > 0 and len(first) < c:
                first.append(rgb)
            elif hold_max:
                hold.append(rgb)
                if len(hold) > hold_max:
                    emit(hold.pop(0))
            else:
                emit(rgb)
        stats = {"loop_video_frames": 0, "loop_audio_samples": 0}
        streamed_middle = written > 0
        can_wrap = c > 0 and n >= 2 * c + 1 and len(first) == c
        tiny_ready = can_wrap and (not streamed_middle or len(hold) == c + 2)
        if tiny_ready and (not streamed_middle or n >= 2 * c + 2):
            first_t = torch.from_numpy(np.stack(first, axis=0)).to(dtype=torch.float32).div_(255.0)
            hold_t = torch.from_numpy(np.stack(hold, axis=0)).to(dtype=torch.float32).div_(255.0)
            tiny = torch.cat((first_t, hold_t), dim=0)
            wrapped, audio, stats = close_loop_av(
                tiny, audio, video_crossfade_frames=c, audio_crossfade_ms=audio_crossfade_ms,
            )
            del first_t, hold_t, tiny, first, hold
            for i in range(int(wrapped.shape[0])):
                emit((wrapped[i] * 255).clamp(0, 255).byte().cpu().numpy())
            del wrapped
        else:
            for rgb in first:
                emit(rgb)
            for rgb in hold:
                emit(rgb)
            if audio is not None:
                _, audio, stats = close_loop_av(
                    torch.zeros(max(2, n), 8, 8, 3), audio,
                    video_crossfade_frames=0, audio_crossfade_ms=audio_crossfade_ms,
                )
        ok = True
    finally:
        if not ok and os.path.exists(dst):
            shutil.rmtree(dst, ignore_errors=True)
    if not ok:
        raise ValueError("h3_continuous: loop close failed")
    shutil.rmtree(frames_dir)
    os.replace(dst, frames_dir)
    return frames_dir, audio, stats, written


class StreamStitchSession:
    """Write a PNG sequence one decoded clip at a time. Peak RAM stays one clip plus a short seam."""

    def __init__(
        self,
        *,
        filename_prefix="video/h3_studio",
        video_crossfade_frames=4,
        audio_crossfade_ms=15.0,
        luminance_match=False,
        luminance_fade_frames=16,
        max_luminance_correction_percent=10.0,
        max_safe_tail_bridge_frames=2,
        decode_audio=True,
        collect_audio=True,
        first_clip_extra_head=0,
        max_video_frames=None,
        close_loop=False,
        loop_overlap_frames=0,
        extra_metadata=None,
        info_prefix="stream stitch",
        frames_dir=None,
        keep_in_ram=False,
    ):
        self.filename_prefix = filename_prefix
        self.decode_audio = bool(decode_audio)
        self.collect_audio = bool(collect_audio)
        self.close_loop = bool(close_loop)
        self.loop_overlap_frames = int(loop_overlap_frames or 0)
        self.info_prefix = info_prefix
        self.keep_in_ram = bool(keep_in_ram)
        self.video_chunks = []
        if self.keep_in_ram:
            self.frames_dir = None
        elif frames_dir:
            self.frames_dir = frames_dir
            os.makedirs(self.frames_dir, exist_ok=True)
            if not os.path.isfile(os.path.join(self.frames_dir, "fps.txt")):
                write_frames_fps(self.frames_dir, FPS)
        else:
            self.frames_dir = unique_temp_frames_dir(filename_prefix)
        self.frame_size = None
        self.video_written = 0
        self.audio_written = 0
        self.sr = None
        self.channels = None
        self.layout = None
        self.pending_video = None
        self.pending_bridge_video = None
        self.pending_audio = None
        self.previous_handover = None
        self.bridge_from_previous = 0
        self.logical_frames = 0
        self.logical_audio_samples = 0
        self.audio_chunks = []
        self.clip_summaries = []
        self._added = 0
        self.requested_vfade = max(0, int(video_crossfade_frames))
        self.requested_afade_ms = max(0.0, float(audio_crossfade_ms))
        self.requested_luma_match = bool(luminance_match)
        self.requested_luma_fade = max(0, int(luminance_fade_frames))
        self.requested_luma_max_percent = max(0.0, float(max_luminance_correction_percent))
        self.requested_bridge_max = max(0, int(max_safe_tail_bridge_frames))
        self.video_boundary_hold = max(
            self.requested_vfade,
            LUMINANCE_ANALYSIS_FRAMES if self.requested_luma_match else 0,
        )
        self.extra_head = max(0, int(first_clip_extra_head))
        self.cap = None if max_video_frames is None else max(0, int(max_video_frames))
        self._closed = False

    def abort(self):
        self.video_chunks = []
        if self.frames_dir and os.path.isdir(self.frames_dir):
            shutil.rmtree(self.frames_dir, ignore_errors=True)

    def _write_video(self, frames):
        if frames is None or int(frames.shape[0]) == 0:
            return
        if self.cap is not None:
            remain = self.cap - self.video_written
            if remain <= 0:
                return
            if int(frames.shape[0]) > remain:
                frames = frames[:remain]
        if self.frames_dir:
            for frame_tensor in frames:
                img = (frame_tensor * 255).clamp(0, 255).byte().detach().cpu().numpy()
                save_png_frame(self.frames_dir, self.video_written, img)
                self.video_written += 1
            return
        self.video_chunks.append(frames.detach().cpu().contiguous())
        self.video_written += int(frames.shape[0])

    def _write_audio(self, wave):
        if not self.decode_audio or wave is None or int(wave.shape[-1]) == 0:
            return
        if self.collect_audio:
            self.audio_chunks.append(wave.detach().cpu().contiguous())
        self.audio_written += int(wave.shape[-1])

    def add_decoded_clip(self, images, audio, metadata, handover, clip_index, is_final):
        from .nodes import _saved_tail_trim

        comfy.model_management.throw_exception_if_processing_interrupted()
        offset = self._added
        frame_count = int(images.shape[0])
        if handover is not None:
            handover["frame_count"] = frame_count
        head, head_source = resolve_saved_head_context(metadata, clip_index, self.previous_handover)
        if offset == 0:
            head = int(head) + self.extra_head
        tail = _saved_tail_trim(frame_count, handover, is_final)
        wave = None
        clip_sr = None
        clip_channels = None
        if self.decode_audio:
            if audio is None:
                raise ValueError(f"h3_continuous: clip {clip_index} has no audio for an AV stitch")
            wave = audio["waveform"]
            clip_sr = int(audio["sample_rate"])
            clip_channels = int(wave.shape[1])

        if self.frame_size is None:
            h, w = int(images.shape[1]), int(images.shape[2])
            self.frame_size = (w, h)
            if self.decode_audio:
                self.sr = clip_sr
                self.channels = clip_channels
                if self.channels not in (1, 2):
                    raise ValueError(f"Saved Chain Stitch currently supports mono/stereo audio, got {self.channels} channels")
                self.layout = "mono" if self.channels == 1 else "stereo"
        else:
            if (int(images.shape[2]), int(images.shape[1])) != self.frame_size:
                raise ValueError(f"clip {clip_index} resolution differs from the first clip")
            if self.decode_audio:
                if clip_sr != self.sr:
                    raise ValueError(f"clip {clip_index} audio sample rate {clip_sr} != {self.sr}")
                if clip_channels != self.channels:
                    raise ValueError(f"clip {clip_index} audio channels {clip_channels} != {self.channels}")

        end = frame_count - tail if tail else frame_count
        incoming_bridge = max(0, int(self.bridge_from_previous))
        incoming_bridge = min(incoming_bridge, max(0, end - head - 1))
        video_head = head + incoming_bridge
        body_images = images[video_head:end]
        if self.decode_audio:
            body_audio = frame_trimmed_audio(audio, frame_count, head, tail, FPS)["waveform"]
            base_body_frames = int(frame_count - head - tail)
            target_total_frames = self.logical_frames + base_body_frames
            target_total_samples = int(round(target_total_frames / float(FPS) * self.sr))
            want_body_samples = max(0, target_total_samples - self.logical_audio_samples)
            body_audio = fit_audio_length(body_audio, want_body_samples)
            self.logical_frames = target_total_frames
            self.logical_audio_samples = target_total_samples
        else:
            body_audio = None
            self.logical_frames += int(frame_count - head - tail)

        future_bridge_video = images[:0].detach().cpu()
        future_bridge_stats = safe_tail_bridge_plan(handover, self.requested_bridge_max)
        future_bridge_count = 0
        if not is_final and int(future_bridge_stats.get("safe_tail_bridge_frames", 0)) > 0:
            future_bridge_video, future_bridge_stats = extract_safe_tail_bridge_images(
                images, handover, self.requested_bridge_max
            )
            future_bridge_video = future_bridge_video.detach().cpu()
            future_bridge_count = int(future_bridge_video.shape[0])

        if offset == 0:
            if not is_final:
                vn = min(self.video_boundary_hold, int(body_images.shape[0]))
                self._write_video(body_images[:-vn] if vn else body_images)
                self.pending_video = body_images[-vn:].detach().cpu() if vn else body_images[:0].detach().cpu()
                self.pending_bridge_video = future_bridge_video
                if self.decode_audio:
                    an_req = int(round(self.requested_afade_ms / 1000.0 * self.sr))
                    an = min(an_req, int(body_audio.shape[-1]))
                    self._write_audio(body_audio[..., :-an] if an else body_audio)
                    self.pending_audio = body_audio[..., -an:].detach().cpu() if an else body_audio[..., :0].detach().cpu()
            else:
                self._write_video(body_images)
                self._write_audio(body_audio)
                self.pending_bridge_video = None
            effective_vfade = 0
            effective_afade = 0
            luma_gain = 1.0
            luma_measured = 1.0
            luma_clamped = False
            luma_faded = 0
            luma_analysis = 0
        else:
            previous_boundary = self.pending_video
            if self.pending_bridge_video is not None and int(self.pending_bridge_video.shape[0]) > 0:
                if previous_boundary is None:
                    previous_boundary = self.pending_bridge_video
                else:
                    previous_boundary = torch.cat((previous_boundary, self.pending_bridge_video), dim=0)

            luma_gain = 1.0
            luma_measured = 1.0
            luma_clamped = False
            luma_faded = 0
            luma_analysis = 0
            if self.requested_luma_match and previous_boundary is not None and video_head > 0:
                luma_analysis = min(LUMINANCE_ANALYSIS_FRAMES, video_head, int(previous_boundary.shape[0]))
                if luma_analysis > 0:
                    lstats = estimate_luminance_gain(
                        previous_boundary[-luma_analysis:],
                        images[video_head - luma_analysis:video_head].detach().cpu().to(previous_boundary.dtype),
                        max_correction_percent=self.requested_luma_max_percent,
                    )
                    luma_gain = float(lstats["luminance_applied_gain"])
                    luma_measured = float(lstats["luminance_measured_gain"])
                    luma_clamped = bool(lstats["luminance_clamped"])
                    body_images, luma_faded = apply_luminance_gain_fade(
                        body_images, luma_gain, self.requested_luma_fade, inplace=True
                    )

            vn = min(
                self.requested_vfade, video_head,
                int(previous_boundary.shape[0]) if previous_boundary is not None else 0,
            )
            if previous_boundary is not None:
                if int(previous_boundary.shape[0]) > vn:
                    self._write_video(previous_boundary[:-vn] if vn else previous_boundary)
                if vn:
                    prev_tail = previous_boundary[-vn:]
                    next_overlap = images[video_head - vn:video_head].detach().cpu().to(prev_tail.dtype)
                    if self.requested_luma_match:
                        next_overlap = apply_rgb_gain(next_overlap, luma_gain)
                    self._write_video(blend_video_overlap(prev_tail, next_overlap))

            effective_afade = 0
            if self.decode_audio:
                head_samples = int(round(head / float(FPS) * self.sr))
                an_req = int(round(self.requested_afade_ms / 1000.0 * self.sr))
                an = min(an_req, head_samples, int(self.pending_audio.shape[-1]) if self.pending_audio is not None else 0)
                if self.pending_audio is not None:
                    if int(self.pending_audio.shape[-1]) > an:
                        self._write_audio(self.pending_audio[..., :-an] if an else self.pending_audio)
                    if an:
                        prev_tail_a = self.pending_audio[..., -an:]
                        next_overlap_a = wave[..., head_samples - an:head_samples].detach().cpu().to(prev_tail_a.dtype)
                        self._write_audio(blend_audio_overlap(prev_tail_a, next_overlap_a))
                effective_afade = an

            if not is_final:
                hold_v = min(self.video_boundary_hold, int(body_images.shape[0]))
                self._write_video(body_images[:-hold_v] if hold_v else body_images)
                self.pending_video = body_images[-hold_v:].detach().cpu() if hold_v else body_images[:0].detach().cpu()
                self.pending_bridge_video = future_bridge_video
                if self.decode_audio:
                    hold_a_req = int(round(self.requested_afade_ms / 1000.0 * self.sr))
                    hold_a = min(hold_a_req, int(body_audio.shape[-1]))
                    self._write_audio(body_audio[..., :-hold_a] if hold_a else body_audio)
                    self.pending_audio = body_audio[..., -hold_a:].detach().cpu() if hold_a else body_audio[..., :0].detach().cpu()
            else:
                self._write_video(body_images)
                self._write_audio(body_audio)
                self.pending_video = None
                self.pending_bridge_video = None
                self.pending_audio = None
            effective_vfade = vn

        luma_summary = "off"
        if self.requested_luma_match and offset > 0:
            luma_summary = (
                f"gain {luma_gain:.4f} (measured {luma_measured:.4f}, "
                f"analysis {luma_analysis}f, fade {luma_faded}f, "
                f"clamped={'yes' if luma_clamped else 'no'})"
            )
        self.clip_summaries.append(
            f"clip {clip_index}: audio-head {head} ({head_source}), video-head {video_head}, tail {tail}, "
            f"bridge-in {incoming_bridge}f, bridge-out {future_bridge_count}f, "
            f"join {effective_vfade}f/{round(effective_afade / self.sr * 1000.0, 1) if self.sr else 0}ms, "
            f"luma {luma_summary}"
        )
        self.bridge_from_previous = future_bridge_count
        self.previous_handover = handover
        self._added += 1

    def add_saved_clip(self, path, video_vae, audio_vae, clip_index, is_final):
        from safetensors.torch import load_file as st_load
        from .nodes import (
            _decode_saved_av, _decode_saved_video_only, _read_safetensors_metadata, release_loaded_models,
        )

        tensors = st_load(path, device="cpu")
        if "video" not in tensors:
            raise ValueError(f"saved clip {clip_index} lacks a video tensor: {path}")
        video_latent = tensors["video"]
        if video_latent.ndim != 5:
            raise ValueError(f"invalid saved video shape for clip {clip_index}: {tuple(video_latent.shape)}")
        frame_count = pixel_frames(video_latent.shape[2])
        metadata, handover = _read_safetensors_metadata(path)
        if handover is not None:
            handover["frame_count"] = frame_count
        if self.decode_audio:
            if "audio" not in tensors:
                raise ValueError(f"saved clip {clip_index} lacks an audio tensor: {path}")
            images, audio = _decode_saved_av(video_vae, audio_vae, video_latent, tensors["audio"])
        else:
            images = _decode_saved_video_only(video_vae, video_latent)
            audio = None
        del tensors, video_latent
        if int(images.shape[0]) != frame_count:
            raise ValueError(
                f"decoded clip {clip_index} has {int(images.shape[0])} frames, expected {frame_count}"
            )
        self.add_decoded_clip(images, audio, metadata, handover, clip_index, is_final)
        del images, audio
        release_loaded_models()

    def finalize(self):
        if self._closed:
            raise ValueError("h3_continuous: stitch session already finalized")
        if self.pending_video is not None:
            self._write_video(self.pending_video)
        if self.pending_audio is not None:
            self._write_audio(self.pending_audio)
        if self.video_written <= 0:
            self.abort()
            raise ValueError("h3_continuous: stitch wrote no video frames")
        self._closed = True

        if self.decode_audio and self.video_written != self.logical_frames:
            raise ValueError(
                f"saved-chain video timeline mismatch after Safe Tail Bridge: wrote {self.video_written} frames, expected {self.logical_frames}"
            )
        collected = None
        if self.collect_audio and self.audio_chunks:
            collected = {
                "waveform": torch.cat(self.audio_chunks, dim=-1),
                "sample_rate": int(self.sr),
            }
            self.audio_chunks = []

        frames_dir = self.frames_dir
        video_written = self.video_written
        audio_written = self.audio_written
        loop_note = ""
        if frames_dir:
            if self.close_loop:
                frames_dir, collected, loop_stats, loop_frames = _close_loop_png(
                    frames_dir, self.loop_overlap_frames, collected, self.requested_afade_ms,
                )
                self.frames_dir = frames_dir
                video_written = int(loop_frames)
                if collected is not None:
                    audio_written = int(collected["waveform"].shape[-1])
                loop_note = (
                    f" | loop close video={loop_stats['loop_video_frames']} "
                    f"audio={loop_stats['loop_audio_samples']}"
                    f" | wrapped output {video_written} frames"
                )
            images = load_png_sequence(frames_dir)
            storage = f"png {frames_dir}"
        else:
            images = torch.cat(self.video_chunks, dim=0)
            self.video_chunks = []
            if self.close_loop:
                images, collected, loop_stats = close_loop_av(
                    images, collected,
                    video_crossfade_frames=self.loop_overlap_frames,
                    audio_crossfade_ms=self.requested_afade_ms,
                )
                video_written = int(images.shape[0])
                if collected is not None:
                    audio_written = int(collected["waveform"].shape[-1])
                loop_note = (
                    f" | loop close video={loop_stats['loop_video_frames']} "
                    f"audio={loop_stats['loop_audio_samples']}"
                    f" | wrapped output {video_written} frames"
                )
            storage = "RAM"

        expected_audio_samples = int(round(video_written / float(FPS) * self.sr)) if self.sr else 0
        drift = audio_written - expected_audio_samples if self.sr else 0
        info = (
            f"{self.info_prefix} | {storage} | {video_written} frames @ {FPS:g}fps | "
            f"audio {audio_written} samples @ {self.sr or 0}Hz | A/V sample rounding delta {drift} | "
            f"safe tail bridge <= {self.requested_bridge_max}f | video crossfade <= {self.requested_vfade}f | "
            f"audio crossfade <= {self.requested_afade_ms:g}ms | "
            f"boundary luminance {'on' if self.requested_luma_match else 'off'} "
            f"(experimental; fade {self.requested_luma_fade}f, max ±{self.requested_luma_max_percent:g}%)"
            f"{loop_note}"
        )
        info += " | " + " ; ".join(self.clip_summaries)
        _LOG.info("h3_continuous: %s", info)
        return {
            "path": frames_dir,
            "info": info,
            "video_frames": int(video_written),
            "images": images,
            "last_frame": images[-1:],
            "audio": collected,
            "frames_dir": frames_dir,
        }


def stream_stitch_saved_clips(
    saved_paths,
    video_vae,
    audio_vae=None,
    *,
    filename_prefix="video/h3_studio",
    video_crossfade_frames=4,
    audio_crossfade_ms=15.0,
    luminance_match=False,
    luminance_fade_frames=16,
    max_luminance_correction_percent=10.0,
    max_safe_tail_bridge_frames=2,
    decode_audio=True,
    collect_audio=True,
    first_clip_extra_head=0,
    max_video_frames=None,
    close_loop=False,
    loop_overlap_frames=0,
    extra_metadata=None,
    info_prefix="stream stitch",
    progress_cb=None,
    frames_dir=None,
    keep_in_ram=False,
):
    """Decode one saved clip at a time. PNG on disk, or keep the stitch in RAM."""
    if not saved_paths:
        raise ValueError("h3_continuous: no saved clips to stitch")
    if decode_audio and audio_vae is None:
        raise ValueError("h3_continuous: audio_vae is required to stitch clip soundtracks")

    session = StreamStitchSession(
        filename_prefix=filename_prefix,
        video_crossfade_frames=video_crossfade_frames,
        audio_crossfade_ms=audio_crossfade_ms,
        luminance_match=luminance_match,
        luminance_fade_frames=luminance_fade_frames,
        max_luminance_correction_percent=max_luminance_correction_percent,
        max_safe_tail_bridge_frames=max_safe_tail_bridge_frames,
        decode_audio=decode_audio,
        collect_audio=collect_audio,
        first_clip_extra_head=first_clip_extra_head,
        max_video_frames=max_video_frames,
        close_loop=close_loop,
        loop_overlap_frames=loop_overlap_frames,
        extra_metadata=extra_metadata,
        info_prefix=info_prefix,
        frames_dir=frames_dir,
        keep_in_ram=keep_in_ram,
    )
    try:
        last_index = len(saved_paths)
        for offset, path in enumerate(saved_paths):
            clip_index = offset + 1
            if progress_cb is not None:
                progress_cb(f"Stitching clip {clip_index}/{last_index}")
            session.add_saved_clip(path, video_vae, audio_vae, clip_index, clip_index == last_index)
        return session.finalize()
    except BaseException:
        session.abort()
        raise

import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seamless_stitch import (
    context_aligned_video_join,
    context_aligned_audio_join,
    resolve_saved_head_context,
)


def test_context_aligned_video_join_keeps_hard_stitch_duration():
    prev = torch.zeros((10, 2, 2, 3), dtype=torch.float32)
    nxt = torch.ones((8, 2, 2, 3), dtype=torch.float32)
    out, stats = context_aligned_video_join(prev, nxt, next_head_context_frames=4, next_tail_trim_frames=1, crossfade_frames=4)
    # hard stitch would be 10 + (8 - 4 - 1) = 13 frames
    assert out.shape[0] == 13
    assert stats["video_crossfade_frames"] == 4
    # cosine blend starts exactly on previous and ends exactly on next context
    assert torch.allclose(out[6], torch.zeros_like(out[6]))
    assert torch.allclose(out[9], torch.ones_like(out[9]))


def test_video_join_can_disable_crossfade():
    prev = torch.zeros((5, 1, 1, 3))
    nxt = torch.ones((6, 1, 1, 3))
    out, stats = context_aligned_video_join(prev, nxt, 2, 1, 0)
    assert out.shape[0] == 8
    assert stats["video_crossfade_frames"] == 0
    assert torch.allclose(out[:5], prev)


def test_audio_join_uses_short_corresponding_context_and_exact_total_duration():
    sr = 48000
    fps = 24
    prev_frames = 10
    next_frames = 8
    head = 4
    tail = 1
    prev_samples = round(prev_frames / fps * sr)
    next_samples = round(next_frames / fps * sr)
    prev = {"waveform": torch.zeros((1, 2, prev_samples)), "sample_rate": sr}
    nxt = {"waveform": torch.ones((1, 2, next_samples)), "sample_rate": sr}
    out, stats = context_aligned_audio_join(
        prev, nxt, previous_output_frames=prev_frames, next_total_frames=next_frames,
        next_head_context_frames=head, next_tail_trim_frames=tail,
        crossfade_ms=15.0, fps=fps,
    )
    expected_frames = prev_frames + next_frames - head - tail
    assert out["waveform"].shape[-1] == round(expected_frames / fps * sr)
    assert stats["audio_crossfade_samples"] == 720
    # End of the short fade lands on the next-context waveform, avoiding a hard step into next body.
    boundary = prev_samples - 1
    assert float(out["waveform"][0, 0, boundary]) > 0.99


def test_saved_head_context_prefers_own_metadata_and_has_v117_fallback():
    head, source = resolve_saved_head_context({"head_context_frames": "26"}, 3, {"phase_aligned_context_frames": 22})
    assert head == 26
    assert source == "saved metadata"

    head, source = resolve_saved_head_context({}, 3, {"phase_aligned_context_frames": 35})
    assert head == 35
    assert "previous handover" in source


def test_clip_one_head_is_always_zero():
    assert resolve_saved_head_context({"head_context_frames": "99"}, 1, None)[0] == 0


def test_luminance_gain_estimator_matches_and_clamps_global_brightness_offset():
    from seamless_stitch import estimate_luminance_gain

    prev = torch.full((8, 16, 16, 3), 0.50)
    nxt = torch.full((8, 16, 16, 3), 0.45)

    open_stats = estimate_luminance_gain(prev, nxt, max_correction_percent=20.0)
    assert abs(open_stats["luminance_measured_gain"] - (0.50 / 0.45)) < 1e-4
    assert abs(open_stats["luminance_applied_gain"] - (0.50 / 0.45)) < 1e-4
    assert open_stats["luminance_clamped"] is False

    clamped = estimate_luminance_gain(prev, nxt, max_correction_percent=10.0)
    assert abs(clamped["luminance_applied_gain"] - 1.10) < 1e-6
    assert clamped["luminance_clamped"] is True


def test_video_join_luminance_match_removes_boundary_step_then_fades_to_native():
    prev = torch.full((10, 8, 8, 3), 0.50)
    nxt = torch.full((8, 8, 8, 3), 0.45)
    out, stats = context_aligned_video_join(
        prev, nxt,
        next_head_context_frames=4,
        next_tail_trim_frames=0,
        crossfade_frames=4,
        luminance_match=True,
        luminance_fade_frames=4,
        max_luminance_correction_percent=20.0,
    )
    assert out.shape[0] == 14
    # The final overlap frame and first genuinely new frame meet at the previous brightness.
    assert abs(float(out[9].mean()) - 0.50) < 1e-4
    assert abs(float(out[10].mean()) - 0.50) < 1e-4
    # The temporary correction returns to the next clip's native brightness.
    assert abs(float(out[13].mean()) - 0.45) < 1e-4
    assert stats["luminance_fade_frames"] == 4


def test_video_join_can_disable_luminance_match_independently_of_crossfade():
    prev = torch.full((10, 8, 8, 3), 0.50)
    nxt = torch.full((8, 8, 8, 3), 0.45)
    out, stats = context_aligned_video_join(
        prev, nxt, 4, 0, 4,
        luminance_match=False,
        luminance_fade_frames=16,
        max_luminance_correction_percent=10.0,
    )
    assert abs(float(out[10].mean()) - 0.45) < 1e-4
    assert stats["luminance_match_enabled"] is False
    assert stats["luminance_applied_gain"] == 1.0


def test_luminance_match_does_not_change_audio_join_math():
    # Video-only boundary correction is deliberately isolated from the tested audio path.
    sr = 32000
    prev = {"waveform": torch.zeros((1, 2, round(10 / 24 * sr))), "sample_rate": sr}
    nxt = {"waveform": torch.ones((1, 2, round(8 / 24 * sr))), "sample_rate": sr}
    out, stats = context_aligned_audio_join(prev, nxt, 10, 8, 4, 1, crossfade_ms=15.0, fps=24)
    assert stats["audio_crossfade_samples"] == 480
    assert out["waveform"].shape[-1] == round(13 / 24 * sr)


def test_streaming_luminance_fade_can_modify_only_boundary_frames_in_place():
    from seamless_stitch import apply_luminance_gain_fade

    images = torch.full((6, 4, 4, 3), 0.50)
    ptr = images.data_ptr()
    out, faded = apply_luminance_gain_fade(images, 1.10, fade_frames=4, inplace=True)
    assert out.data_ptr() == ptr
    assert faded == 4
    assert float(out[0].mean()) > 0.54
    assert abs(float(out[3].mean()) - 0.50) < 1e-5
    assert torch.allclose(out[4:], torch.full_like(out[4:], 0.50))


def test_safe_tail_bridge_uses_only_phase_alignment_loss_inside_safe_end():
    from seamless_stitch import safe_tail_bridge_plan

    handover = {
        "available": True,
        "frame_count": 243,
        "handover_end_frame": 208,
        "ideal_handover_end_frame": 210,
        "phase_aligned_cutoff_loss_frames": 2,
    }
    plan = safe_tail_bridge_plan(handover, max_bridge_frames=2)
    assert plan["safe_tail_bridge_frames"] == 2
    assert plan["safe_tail_bridge_start_frame"] == 209
    assert plan["safe_tail_bridge_end_frame"] == 210
    assert plan["safe_tail_bridge_capped"] is False


def test_safe_tail_bridge_never_borrows_from_safety_margin_or_exceeds_cap():
    from seamless_stitch import safe_tail_bridge_plan

    # Even if a malformed/experimental metadata object reports a larger ideal gap,
    # the explicit phase-alignment loss remains the upper bound.
    handover = {
        "available": True,
        "frame_count": 243,
        "handover_end_frame": 208,
        "ideal_handover_end_frame": 214,
        "phase_aligned_cutoff_loss_frames": 3,
    }
    plan = safe_tail_bridge_plan(handover, max_bridge_frames=2)
    assert plan["safe_tail_bridge_available_frames"] == 3
    assert plan["safe_tail_bridge_frames"] == 2
    assert plan["safe_tail_bridge_capped"] is True

    assert safe_tail_bridge_plan(handover, max_bridge_frames=0)["safe_tail_bridge_frames"] == 0


def test_extract_safe_tail_bridge_pixels_are_exact_previous_frames():
    from seamless_stitch import extract_safe_tail_bridge_images

    frames = torch.arange(12, dtype=torch.float32).view(12, 1, 1, 1).repeat(1, 1, 1, 3)
    handover = {
        "available": True,
        "frame_count": 12,
        "handover_end_frame": 7,
        "ideal_handover_end_frame": 9,
        "phase_aligned_cutoff_loss_frames": 2,
    }
    bridge, plan = extract_safe_tail_bridge_images(frames, handover, 2)
    assert bridge.shape[0] == 2
    assert torch.allclose(bridge[:, 0, 0, 0], torch.tensor([8.0, 9.0]))
    assert plan["safe_tail_bridge_frames"] == 2


def test_safe_tail_bridge_keeps_video_timeline_length_when_next_video_head_is_shifted():
    # Model the node-level operation: append 2 safe previous pixels, then skip 2
    # additional early video frames in the next clip. Total duration is unchanged.
    prev = torch.zeros((10, 2, 2, 3), dtype=torch.float32)
    bridge = torch.full((2, 2, 2, 3), 0.25, dtype=torch.float32)
    previous_extended = torch.cat((prev, bridge), dim=0)
    nxt = torch.ones((12, 2, 2, 3), dtype=torch.float32)
    original_head = 4
    tail = 1
    out, _ = context_aligned_video_join(
        previous_extended, nxt,
        next_head_context_frames=original_head + 2,
        next_tail_trim_frames=tail,
        crossfade_frames=0,
        luminance_match=False,
    )
    expected = 10 + (12 - original_head - tail)
    assert out.shape[0] == expected
    # Audio deliberately keeps the original head and therefore the same duration.
    sr = 32000
    prev_audio = {"waveform": torch.zeros((1, 2, round(10 / 24 * sr))), "sample_rate": sr}
    next_audio = {"waveform": torch.ones((1, 2, round(12 / 24 * sr))), "sample_rate": sr}
    audio, _ = context_aligned_audio_join(
        prev_audio, next_audio, 10, 12, original_head, tail, crossfade_ms=15.0, fps=24
    )
    assert audio["waveform"].shape[-1] == round(expected / 24 * sr)


def test_close_loop_av_crossfades_real_opening_and_shortens():
    from seamless_stitch import close_loop_av

    images = torch.zeros((20, 2, 2, 3), dtype=torch.float32)
    for i in range(20):
        images[i] = i / 20.0
    sr = 24000
    samples = 20 * 1000
    audio = {"waveform": torch.linspace(0, 1, samples).view(1, 1, samples).repeat(1, 2, 1), "sample_rate": sr}

    out_images, out_audio, stats = close_loop_av(
        images, audio, video_crossfade_frames=4, audio_crossfade_ms=15.0,
    )
    assert stats["loop_video_frames"] == 4
    assert out_images.shape[0] == 16
    assert torch.allclose(out_images[0], images[4])
    assert torch.allclose(out_images[-1], images[3], atol=1e-6)
    video_drop = round(4 / 24 * sr)
    assert stats["loop_audio_samples"] == video_drop
    assert out_audio["waveform"].shape[-1] == samples - video_drop
    assert torch.allclose(out_audio["waveform"][..., :1], audio["waveform"][..., video_drop:video_drop + 1])


def test_close_loop_tiny_window_rebuilds_full_wrap():
    from seamless_stitch import close_loop_av

    n, c = 40, 4
    images = torch.zeros((n, 8, 8, 3), dtype=torch.float32)
    for i in range(n):
        images[i] = i / float(n)
    full, _, _ = close_loop_av(images, None, video_crossfade_frames=c)
    tiny = torch.cat((images[:c], images[-(c + 2):]), dim=0)
    tail, _, _ = close_loop_av(tiny, None, video_crossfade_frames=c)
    rebuilt = torch.cat((images[c:-(c + 2)], tail), dim=0)
    assert rebuilt.shape == full.shape
    assert torch.allclose(rebuilt, full, atol=1e-5)


def test_close_loop_av_overlap_adds_full_opening_window():
    from seamless_stitch import close_loop_av

    images = torch.zeros((80, 2, 2, 3), dtype=torch.float32)
    for i in range(80):
        images[i] = i / 80.0
    sr = 24000
    samples = 80 * 1000
    audio = {"waveform": torch.linspace(0, 1, samples).view(1, 1, samples), "sample_rate": sr}

    out_images, out_audio, stats = close_loop_av(
        images, audio, video_crossfade_frames=22, audio_crossfade_ms=15.0,
    )
    assert stats["loop_video_frames"] == 22
    assert out_images.shape[0] == 58
    assert torch.allclose(out_images[0], images[22])
    assert torch.allclose(out_images[-1], images[21], atol=1e-6)
    drop = round(22 / 24 * sr)
    hold = min(round(4 / 24 * sr), drop // 4)
    fade = drop - hold
    assert stats["loop_audio_samples"] == drop
    assert out_audio["waveform"].shape[-1] == samples - drop
    assert torch.allclose(out_audio["waveform"][..., -1], audio["waveform"][..., drop - 1])
    assert torch.allclose(
        out_audio["waveform"][..., -drop + fade],
        audio["waveform"][..., fade],
    )


def test_close_loop_av_dims_phase0_flash_without_mixing_pixels():
    from seamless_stitch import close_loop_av

    images = torch.zeros((80, 2, 2, 3), dtype=torch.float32)
    images[..., 0] = 0.2
    images[-22] = torch.tensor([1.0, 1.0, 1.0])
    images[-23] = torch.tensor([1.0, 1.0, 1.0])
    out, _, stats = close_loop_av(images, None, video_crossfade_frames=22)
    assert stats["loop_video_frames"] == 22
    assert out.shape[0] == 58
    assert float(out[-22].mean()) < 0.55
    assert float(out[-23].mean()) < 0.55
    # Luma-only: the white flash stays neutral, not a red neighbor ghost.
    assert torch.allclose(out[-22, 0, 0, 0], out[-22, 0, 0, 1], atol=1e-5)
    assert torch.allclose(out[-23, 0, 0, 0], out[-23, 0, 0, 1], atol=1e-5)


def test_close_loop_av_default_wrap_is_audio_declick_only():
    from seamless_stitch import close_loop_av

    images = torch.zeros((20, 2, 2, 3), dtype=torch.float32)
    for i in range(20):
        images[i] = float(i)
    sr = 24000
    samples = 20 * 1000
    audio = {"waveform": torch.linspace(0, 1, samples).view(1, 1, samples), "sample_rate": sr}

    out_images, out_audio, stats = close_loop_av(
        images, audio, video_crossfade_frames=0, audio_crossfade_ms=15.0,
    )
    fade = round(15.0 / 1000.0 * sr)
    assert stats["loop_video_frames"] == 0
    assert stats["loop_audio_samples"] == fade
    assert torch.equal(out_images, images)
    assert out_audio["waveform"].shape[-1] == samples
    assert not torch.equal(out_audio["waveform"][..., -fade:], audio["waveform"][..., -fade:])


def test_close_loop_av_can_disable_each_medium():
    from seamless_stitch import close_loop_av

    images = torch.randn((12, 1, 1, 3))
    audio = {"waveform": torch.randn((1, 1, 200)), "sample_rate": 1000}
    out_images, out_audio, stats = close_loop_av(
        images, audio, video_crossfade_frames=0, audio_crossfade_ms=0.0,
    )
    assert stats["loop_video_frames"] == 0
    assert stats["loop_audio_samples"] == 0
    assert torch.equal(out_images, images)
    assert torch.equal(out_audio["waveform"], audio["waveform"])

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from latent_math import (
    pixel_frames, temporal_shape, context_slice, phase_aware_context_slice,
    audio_slice_for_pixel_window, latent_boundaries, phase_aligned_extended_context_slice, step_offsets,
)


def test_h3_10s_shape():
    frames, vt, at = temporal_shape(243)
    assert frames == 243
    assert pixel_frames(vt) == 243
    assert vt == 72
    assert at == 405


def test_legacy_default_pre_freeze_slice():
    frames, vt, at = temporal_shape(243)
    s = context_slice(vt, 22, 34)
    assert s["previous_frame_count"] == 243
    assert s["source_end_frame"] == 209
    assert s["source_start_frame"] == 187
    assert s["end_t"] == 62
    assert s["start_t"] == 55
    assert s["offsets"] == [0, 1, 5, 9, 13, 17, 18]
    a0, a1, err = audio_slice_for_pixel_window(at, 187, 209)
    assert 0 <= a0 < a1 <= at
    assert abs(err) <= 0.5


def test_phase_aware_cutoff_keeps_late_motion():
    _, vt, at = temporal_shape(243)
    # v0.3 would round ideal frame 218 all the way back to frame 208.
    # v0.4 keeps the latest actual source latent boundary: exclusive 217,
    # therefore inclusive frame 216 (only 2 frames before the ideal cutoff).
    s = phase_aware_context_slice(vt, 22, ideal_last_frame=218)
    assert s["source_end_frame"] == 217
    assert s["source_end_frame"] - 1 == 216
    assert s["ignored_tail_frames"] == 26
    assert s["cutoff_loss_frames"] == 2
    assert s["actual_context_frames"] == 21
    assert (s["start_t"], s["end_t"]) == (58, 64)
    assert s["offsets"] == [0, 4, 8, 9, 13, 17]
    a0, a1, err = audio_slice_for_pixel_window(at, s["source_start_frame"], s["source_end_frame"])
    assert 0 <= a0 < a1 <= at
    assert abs(err) <= 0.5


def test_phase_aware_no_freeze_matches_full_tail():
    _, vt, _ = temporal_shape(243)
    s = phase_aware_context_slice(vt, 22, ideal_last_frame=242)
    assert s["source_end_frame"] == 243
    assert s["ignored_tail_frames"] == 0
    assert s["actual_context_frames"] == 22
    assert s["offsets"] == [0, 1, 5, 9, 13, 17, 18]


def test_phase_aware_never_crosses_ideal_and_loses_at_most_three_frames():
    _, vt, _ = temporal_shape(243)
    for ideal in range(60, 243):
        s = phase_aware_context_slice(vt, 22, ideal_last_frame=ideal)
        assert s["source_end_frame"] - 1 <= ideal
        assert 0 <= s["cutoff_loss_frames"] <= 3
        assert 1 <= s["actual_context_frames"] <= 22
        assert s["offsets"][0] == 0
        assert all(s["offsets"][i] < s["offsets"][i + 1] for i in range(len(s["offsets"]) - 1))


def test_phase_aware_offsets_preserve_source_boundaries():
    _, vt, _ = temporal_shape(243)
    b = latent_boundaries(vt)
    for ideal in (220, 218, 215, 212, 209):
        s = phase_aware_context_slice(vt, 22, ideal_last_frame=ideal)
        expected = [b[k] - b[s["start_t"]] for k in range(s["start_t"], s["end_t"])]
        assert s["offsets"] == expected


def test_phase_aligned_extended_observed_frame_213_case():
    _, vt, at = temporal_shape(243)
    s = phase_aligned_extended_context_slice(vt, 22, ideal_last_frame=212)
    assert s["source_start_frame"] == 187
    assert s["source_end_frame"] == 213
    assert s["source_end_frame"] - 1 == 212
    assert s["ignored_tail_frames"] == 30
    assert s["actual_context_frames"] == 26
    assert s["context_extension_frames"] == 4
    assert (s["start_t"], s["end_t"]) == (55, 63)
    assert s["source_start_phase"] == 0
    assert s["offsets"] == [0, 1, 5, 9, 13, 17, 18, 22]
    a0, a1, err = audio_slice_for_pixel_window(at, 187, 213)
    assert 0 <= a0 < a1 <= at
    assert abs(err) <= 0.5


def test_phase_aligned_extended_lock_228_case():
    _, vt, _ = temporal_shape(243)
    s = phase_aligned_extended_context_slice(vt, 22, ideal_last_frame=227)
    assert s["source_start_frame"] == 204
    assert s["source_end_frame"] == 226
    assert s["source_end_frame"] - 1 == 225
    assert s["ignored_tail_frames"] == 17
    assert s["actual_context_frames"] == 22
    assert s["context_extension_frames"] == 0
    assert s["source_start_phase"] == 0
    assert s["offsets"] == [0, 1, 5, 9, 13, 17, 18]


def test_phase_aligned_extended_no_freeze_tail_zero():
    _, vt, _ = temporal_shape(243)
    s = phase_aligned_extended_context_slice(vt, 22, ideal_last_frame=242)
    assert s["source_start_frame"] == 221
    assert s["source_end_frame"] == 243
    assert s["actual_context_frames"] == 22
    assert s["ignored_tail_frames"] == 0
    assert s["offsets"] == [0, 1, 5, 9, 13, 17, 18]


def test_phase_aligned_extended_is_canonical_for_all_late_cutoffs():
    _, vt, _ = temporal_shape(243)
    for ideal in range(60, 243):
        s = phase_aligned_extended_context_slice(vt, 22, ideal_last_frame=ideal)
        assert s["source_start_phase"] == 0
        assert s["source_end_frame"] - 1 <= ideal
        assert 0 <= s["cutoff_loss_frames"] <= 3
        assert s["actual_context_frames"] >= 22
        assert s["offsets"] == step_offsets(s["context_steps"])


def test_loop_end_keyframe_offsets_place_opening_on_the_tail():
    from latent_math import LOOP_OPENING_SKIP_STEPS, loop_end_keyframe_offsets, pixel_frames

    spec = loop_end_keyframe_offsets(243, 22, source_latent_t=72)
    assert spec["context_steps"] == 7
    assert spec["actual_context_frames"] == 22
    assert spec["source_skip_steps"] == LOOP_OPENING_SKIP_STEPS
    assert spec["source_skip_frames"] == pixel_frames(LOOP_OPENING_SKIP_STEPS)
    assert spec["source_start_t"] == LOOP_OPENING_SKIP_STEPS
    assert spec["source_end_t"] == LOOP_OPENING_SKIP_STEPS + 7
    assert spec["wrap_start_frames"] == pixel_frames(LOOP_OPENING_SKIP_STEPS)
    assert spec["offsets"][0] == 221
    assert spec["offsets"] == [221 + p for p in step_offsets(7)]
    assert spec["offsets"][-1] + 4 == 243


def test_loop_opening_skip_drops_when_clip_is_too_short():
    from latent_math import loop_end_keyframe_offsets, loop_opening_skip_steps

    assert loop_opening_skip_steps(72, 22) == 5
    assert loop_opening_skip_steps(8, 22) == 0
    spec = loop_end_keyframe_offsets(243, 22, source_latent_t=8)
    assert spec["source_start_t"] == 0
    assert spec["source_skip_frames"] == 0
    assert spec["wrap_start_frames"] == 0


def test_loop_wrap_starts_at_the_first_moving_opening_frame():
    from latent_math import loop_wrap_start_frames, pixel_frames

    assert loop_wrap_start_frames(72, 22) == pixel_frames(5)
    assert loop_wrap_start_frames(72, 22) == 17
    assert loop_wrap_start_frames(8, 22) == 0

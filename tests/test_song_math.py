import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_video_prompt import parse_music_video_prompt, validate_music_video_prompt
from song_math import (
    CLIP_COUNT_TOLERANCE, MUSIC_MAX_DURATION_SECONDS, MUSIC_MAX_SEGMENTS,
    advance_cursor, coverage_clip_count, expected_clip_count, frame_to_sample,
    grid_clip_count, grid_duration_seconds, grid_frame_count, h3_grid_steps,
    kept_video_span, mux_spans_are_contiguous, music_video_mux_spans,
    next_slice_start, plan_clip_windows, planning_clip_windows, planning_join_geometry,
    slice_sample_range, song_frame_count, stb_song_span,
)


SAMPLE_PROMPT = """h3_music_video: 1
duration_seconds: 10.125
clip_count: 2
---
CLIP 1
time: 0.000-10.125
lyrics: hello world
prompt:
subject_definitions
<Audio 1> is the song.
---
CLIP 2
time: 10.125-20.250
lyrics: second line
prompt:
subject_definitions
<Audio 1> is the song.
"""


def test_10s_snaps_to_243_frames_and_10_125s():
    assert grid_frame_count(10.0) == 243
    assert abs(grid_duration_seconds(10.0) - 10.125) < 1e-9
    assert grid_frame_count(10.125) == 243


def test_expected_clip_count_covers_kept_frames_not_raw_grid():
    assert grid_clip_count(10.125, 10.0) == 1
    assert expected_clip_count(10.125, 10.0) == 1
    assert expected_clip_count(15.0, 10.0) == 2
    assert grid_clip_count(165.0, 10.0) == 17
    assert expected_clip_count(165.0, 10.0) == 21
    assert coverage_clip_count(165.0, 10.0, extra=1) == 22
    assert grid_clip_count(180.0, 10.0) == 18
    assert expected_clip_count(180.0, 10.0) == 23
    assert expected_clip_count(20.25, 10.0) == 3


def test_frame_to_sample_24fps():
    assert frame_to_sample(0, 48000) == 0
    assert frame_to_sample(24, 48000) == 48000
    assert frame_to_sample(243, 48000) == 486000


def test_slice_sample_range_matches_grid_length():
    start, end = slice_sample_range(0, 243, 48000)
    assert start == 0
    assert end == frame_to_sample(243, 48000)
    start2, end2 = slice_sample_range(212, 243, 48000)
    assert start2 == frame_to_sample(212, 48000)
    assert end2 - start2 == end - start


def test_cursor_advances_by_kept_frames_not_equal_slices():
    grid = 243
    head = 22
    tail = 9
    cursor = 0
    s1 = next_slice_start(cursor, 0)
    assert s1 == 0
    cursor = advance_cursor(s1, grid, tail, is_last=False)
    assert cursor == 243 - 9
    s2 = next_slice_start(cursor, head)
    assert s2 == cursor - head
    assert s2 != grid


def test_mux_spans_are_contiguous_across_head_overlap_and_stb():
    grid = 243
    head = 22
    tail = 9
    bridge = 2
    s1 = 0
    cursor = advance_cursor(s1, grid, tail)
    s2 = next_slice_start(cursor, head)
    clips = [
        {"slice_start": s1, "grid_frames": grid, "head": 0, "tail": tail, "bridge": 0, "is_last": False},
        {"slice_start": s2, "grid_frames": grid, "head": head, "tail": 0, "bridge": bridge, "is_last": True},
    ]
    spans = music_video_mux_spans(clips)
    assert mux_spans_are_contiguous(spans)
    assert spans[0] == (0, grid - tail)
    stb = stb_song_span(s1, grid, tail, bridge)
    assert spans[1] == stb
    keep_start, keep_end = kept_video_span(grid, head, 0, bridge, is_last=True)
    assert spans[2] == (s2 + keep_start, s2 + keep_end)
    assert spans[1][1] == spans[2][0]


def test_last_clip_keeps_full_landing():
    start, end = kept_video_span(243, 22, 30, bridge_frames=0, is_last=True)
    assert start == 22
    assert end == 243


def test_parse_music_video_prompt_roundtrip():
    parsed = parse_music_video_prompt(SAMPLE_PROMPT)
    assert parsed["version"] == 1
    assert parsed["duration_seconds"] == 10.125
    assert parsed["clip_count"] == 2
    assert parsed["max_duration_seconds"] == 10.125
    assert parsed["clips"][0]["duration_seconds"] == 10.125
    assert parsed["clips"][0]["grid_frames"] == 243
    assert parsed["clips"][0]["index"] == 1
    assert parsed["clips"][0]["lyrics"] == "hello world"
    assert "<Audio 1>" in parsed["clips"][0]["prompt"]
    assert parsed["clips"][1]["time"] == (10.125, 20.250)
    validate_music_video_prompt(parsed, song_seconds=15.0, duration_seconds=10.0)


def test_parse_unified_music_video_prompt():
    unified = """H3 Studio prompt
mode: music_video
duration: 10.125
segments: 2

subject_definitions:
<Subject 1> is the singer.
<Audio 1> is the source-song slice covering 0.000–10.125 of the master.

## Clip 1 — Start
time: 0.000-10.125
duration_seconds: 10.125
lyrics:
hello world
summary:
[reference generation + audio reuse] Opens.

retention_analysis:
<Audio 1>: fully_copy

detailed_description:
[Shot 1] She sings hello world.

overall_soundscape: <Audio 1>

non_diegetic_music: N/A

## Clip 2 — Continue
time: 10.125-20.250
duration_seconds: 10.125
lyrics:
second line
summary:
[video continuation + audio reuse] Continues.

retention_analysis:
<Audio 1>: fully_copy

detailed_description:
[Shot 1] She sings second line.

overall_soundscape: <Audio 1>

non_diegetic_music: N/A
"""
    parsed = parse_music_video_prompt(unified)
    assert parsed["clip_count"] == 2
    assert parsed["clips"][0]["lyrics"] == "hello world"
    assert "<Audio 1>" in parsed["clips"][0]["prompt"]
    assert parsed["clips"][1]["time"] == (10.125, 20.250)
    validate_music_video_prompt(parsed, song_seconds=15.0, duration_seconds=10.0)


def test_parse_rejects_clip_count_mismatch():
    bad = SAMPLE_PROMPT.replace("clip_count: 2", "clip_count: 3")
    try:
        parse_music_video_prompt(bad)
    except ValueError as exc:
        assert "clip_count=3" in str(exc)
    else:
        raise AssertionError("expected clip_count mismatch")


def test_validate_rejects_too_few_clips_versus_song_length():
    parsed = parse_music_video_prompt(SAMPLE_PROMPT)
    try:
        validate_music_video_prompt(parsed, song_seconds=165.0, duration_seconds=10.0)
    except ValueError as exc:
        message = str(exc)
        assert "clip_count=2" in message
        assert "need at least 21" in message
    else:
        raise AssertionError("expected song-length mismatch")


def test_validate_allows_partial_run_with_stop_after_clip():
    parsed = parse_music_video_prompt(SAMPLE_PROMPT)
    validate_music_video_prompt(
        parsed, song_seconds=165.0, duration_seconds=10.0, stop_after_clip=2,
    )
    try:
        validate_music_video_prompt(
            parsed, song_seconds=165.0, duration_seconds=10.0, stop_after_clip=3,
        )
    except ValueError as exc:
        assert "stop_after_clip=3" in str(exc)
    else:
        raise AssertionError("expected stop_after beyond clip_count")


def test_validate_allows_extra_clips():
    parsed = parse_music_video_prompt(SAMPLE_PROMPT)
    # 2 clips vs coverage(10.125s)=1 is allowed; too few is not
    assert CLIP_COUNT_TOLERANCE >= 1
    validate_music_video_prompt(parsed, song_seconds=10.125, duration_seconds=10.0)


def test_music_max_segments_is_48():
    assert MUSIC_MAX_SEGMENTS == 48


def test_planning_windows_cover_song_after_trims():
    song = 165.0
    windows = planning_clip_windows(song, 10.0, extra=0)
    geom = planning_join_geometry(243)
    assert len(windows) == 21
    assert windows[0]["start"] == 0.0
    assert abs(windows[0]["end"] - (243 - geom["tail_frames"]) / 24.0) < 1e-9
    for i in range(len(windows) - 1):
        assert abs(windows[i]["end"] - windows[i + 1]["start"]) < 1e-9
    assert windows[-1]["end_frame"] == song_frame_count(song)
    assert abs(windows[-1]["end"] - song) < 1e-9
    assert windows[0]["grid_frames"] == 243
    assert abs(windows[0]["duration_seconds"] - 10.125) < 1e-9


def test_h3_grid_steps_from_five_to_ten():
    frames = [step["frames"] for step in h3_grid_steps(5.0, 10.0)]
    assert frames[0] == 124
    assert frames[-1] == 243
    assert 192 in frames
    assert MUSIC_MAX_DURATION_SECONDS == 15.0
    assert h3_grid_steps(5.0, 15.0)[-1]["frames"] == 362


def test_plan_keeps_max_when_lyric_sits_in_join_discard():
    windows = plan_clip_windows(20.25, 10.0, lyric_starts=[9.5])
    assert windows[0]["grid_frames"] == 243
    assert windows[0]["end"] <= 9.5
    assert windows[1]["start"] <= 9.5 < windows[1]["end"]


def test_plan_keeps_max_length_when_lyrics_are_not_near_the_join():
    windows = plan_clip_windows(20.25, 10.0, lyric_starts=[2.0, 12.0])
    assert windows[0]["grid_frames"] == 243


def test_plan_will_not_shrink_past_an_early_lyric_start():
    windows = plan_clip_windows(20.25, 10.0, lyric_starts=[2.0, 9.5])
    assert windows[0]["start"] == 0.0
    assert windows[0]["end"] > 2.0
    assert windows[0]["end"] < 9.5
    assert windows[1]["start"] <= 9.5 < windows[1]["end"]


def test_plan_join_discards_one_second():
    windows = plan_clip_windows(20.25, 10.0, lyric_starts=[2.0])
    geom = planning_join_geometry(windows[0]["grid_frames"])
    assert windows[0]["grid_frames"] - int(round(windows[0]["end"] * 24.0)) == geom["tail_frames"]
    assert geom["tail_frames"] >= 24


def test_planning_join_geometry_matches_generate_phase_snap():
    for frames in (243, 209, 124):
        geom = planning_join_geometry(frames)
        assert geom["head_frames"] == 30
        assert geom["tail_frames"] == 26
        assert geom["source_end_frame"] == frames - 26


def test_plan_windows_match_generate_cursor_loop():
    song = 165.0
    windows = plan_clip_windows(song, 10.0)
    cursor = 0
    for i, window in enumerate(windows):
        if i == 0:
            head = 0
        else:
            head = planning_join_geometry(windows[i - 1]["grid_frames"])["head_frames"]
        slice_start = next_slice_start(cursor, head)
        assert slice_start == window["slice_start"]
        is_last = i == len(windows) - 1
        tail = 0 if is_last else planning_join_geometry(window["grid_frames"])["tail_frames"]
        cursor = advance_cursor(slice_start, window["grid_frames"], tail, is_last)
    assert cursor >= song_frame_count(song)


def test_guessed_30_48_trims_drift_from_generate_by_clip_26():
    song_frames = song_frame_count(165.0)
    grid = 243
    old_cursor = 0
    new_cursor = 0
    old_slice = 0
    new_slice = 0
    for i in range(26):
        old_head = 0 if i == 0 else 30
        new_head = 0 if i == 0 else planning_join_geometry(grid)["head_frames"]
        old_slice = next_slice_start(old_cursor, old_head)
        new_slice = next_slice_start(new_cursor, new_head)
        old_last = old_slice + grid >= song_frames
        new_last = new_slice + grid >= song_frames
        old_cursor = advance_cursor(old_slice, grid, 0 if old_last else 48, old_last)
        new_cursor = advance_cursor(
            new_slice, grid,
            0 if new_last else planning_join_geometry(grid)["tail_frames"],
            new_last,
        )
    assert new_slice - old_slice >= 100


def test_plan_keeps_line_that_sits_in_discard_tail():
    windows = plan_clip_windows(20.25, 10.0, lyric_starts=[9.6])
    assert windows[0]["grid_frames"] == 243
    assert windows[0]["end"] <= 9.6
    assert windows[1]["start"] <= 9.6 < windows[1]["end"]


def test_plan_moves_line_whose_end_overruns_generate():
    windows = plan_clip_windows(20.25, 10.0, lyric_spans=[(8.0, 10.5)])
    assert windows[0]["end"] <= 8.0
    assert windows[1]["start"] <= 8.0 < windows[1]["end"]
    assert windows[1]["end"] >= 10.5


def test_plan_keeps_max_when_line_end_fits_in_generate():
    windows = plan_clip_windows(20.25, 10.0, lyric_spans=[(2.0, 8.0)])
    assert windows[0]["grid_frames"] == 243
    assert windows[0]["start"] <= 2.0 < windows[0]["end"]


def test_parse_per_clip_duration_and_max_header():
    text = """h3_music_video: 1
max_duration_seconds: 10.125
clip_count: 2
---
CLIP 1
time: 0.000-8.417
duration_seconds: 9.417
lyrics: hello
prompt:
subject_definitions
<Audio 1> is the song.
---
CLIP 2
time: 8.417-20.250
duration_seconds: 10.125
lyrics: later
prompt:
subject_definitions
<Audio 1> is the song.
"""
    parsed = parse_music_video_prompt(text)
    assert parsed["max_duration_seconds"] == 10.125
    assert parsed["clips"][0]["grid_frames"] == 226
    assert parsed["clips"][1]["grid_frames"] == 243
    validate_music_video_prompt(parsed, song_seconds=15.0, duration_seconds=10.0)


def test_validate_rejects_clip_longer_than_max():
    text = SAMPLE_PROMPT.replace(
        "lyrics: hello world",
        "duration_seconds: 15.083\nlyrics: hello world",
    )
    parsed = parse_music_video_prompt(text)
    try:
        validate_music_video_prompt(parsed, song_seconds=15.0, duration_seconds=10.0)
    except ValueError as exc:
        assert "exceeds max" in str(exc)
    else:
        raise AssertionError("expected clip longer than max")


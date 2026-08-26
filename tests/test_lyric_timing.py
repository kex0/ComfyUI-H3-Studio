import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyric_timing import (
    assign_lyrics_to_windows, complete_line_words, crop_line_to_window, dump_aligned_lyrics,
    format_lrc, format_music_video_skeleton, format_window_lyrics, has_timestamps,
    is_instrumental_marker, merge_asr_and_user_lyrics, parse_time_range,
    parse_timestamped_lyrics, phrase_lines_from_words, _load_aligned_json,
)


INSTRUMENTAL_INTRO = """
[00:12.000] hello world
[00:15.500] second line
"""


def test_has_timestamps_detects_lrc_and_rejects_plain_text():
    assert has_timestamps("[00:12.00] hello")
    assert has_timestamps("[12.0] hello")
    assert has_timestamps("1\n00:00:12,000 --> 00:00:15,000\nhello\n")
    assert not has_timestamps("hello world\nsecond line")


def test_lrc_instrumental_intro_does_not_land_in_clip_1():
    lines = parse_timestamped_lyrics(INSTRUMENTAL_INTRO)
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    assert len(windows) == 3
    assert windows[0]["instrumental"] is True
    assert format_window_lyrics(windows[0]) == "(instrumental)"
    assert windows[1]["instrumental"] is False
    assert "hello" in windows[1]["lines"][0]["text"].lower()
    assert any(ln["text"] == "second line" for w in windows for ln in w["lines"])


def test_confirm_instrumental_marker_stays_in_mixed_clip():
    lines = parse_timestamped_lyrics(
        "[01:01.214-01:04.790] Hit restore press replay\n"
        "[01:04.849-01:14.556] <instrumental>\n"
        "[01:14.657-01:16.422] Cloud copy of me\n"
    )
    windows = assign_lyrics_to_windows(lines, song_seconds=90.0, duration_seconds=10.0)
    mixed = [
        w for w in windows
        if any(is_instrumental_marker(ln.get("text")) for ln in w["lines"])
        and any(not is_instrumental_marker(ln.get("text")) for ln in w["lines"])
    ]
    assert mixed
    assert mixed[0]["instrumental"] is False
    body = format_window_lyrics(mixed[0])
    assert "<instrumental>" in body
    assert "Hit restore" in body or "Cloud copy" in body
    assert "(instrumental)" not in body
    assert not any(
        is_instrumental_marker(ln.get("text")) and (ln.get("words") or [])
        for w in windows for ln in w["lines"]
    )


def test_line_only_in_discard_tail_is_prompted_on_the_generating_clip():
    lines = parse_timestamped_lyrics("[00:09.000-00:10.000] overlap line")
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    sung = [w for w in windows if any("overlap line" in ln["text"] for ln in w["lines"])]
    assert sung
    assert sung[0]["index"] == 1
    assert not any(
        w["start"] >= 10.0 and any("overlap line" in ln["text"] for ln in w["lines"])
        for w in windows
    )


def test_line_starting_in_clip1_generate_tail_continues_after_previous_generate():
    lines = parse_timestamped_lyrics("[00:10.000] still clip one")
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    texts = [ln["text"] for w in windows for ln in w["lines"]]
    assert any("still clip one" in t or "clip one" in t for t in texts)


def test_boundary_lyric_in_generate_tail_is_also_on_next_audio_slice():
    lines = parse_timestamped_lyrics("[00:09.500-00:10.000] near the join")
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    assert windows[0]["duration_seconds"] == 10.125
    assert any("near the join" in ln["text"] for ln in windows[0]["lines"])
    assert any("near the join" in ln["text"] for ln in windows[1]["lines"])


def test_line_straddling_kept_join_follows_each_clip_audio():
    join = assign_lyrics_to_windows([], song_seconds=20.25, duration_seconds=10.0)[0]["end"]
    lines = [{
        "start": join - 0.5,
        "end": join + 1.5,
        "text": "spanning line",
        "words": [
            {"start": join - 0.5, "end": join, "text": "spanning"},
            {"start": join, "end": join + 1.5, "text": "line"},
        ],
    }]
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    sung = [w for w in windows if any("spann" in ln["text"] or ln["text"] == "line" for ln in w["lines"])]
    assert sung
    assert 2 in [w["index"] for w in sung]
    for w in sung:
        gen_s = int(w["slice_start"]) / 24.0
        gen_e = gen_s + float(w["duration_seconds"])
        for ln in w["lines"]:
            assert float(ln["end"]) > gen_s
            assert float(ln["start"]) < gen_e


def test_line_ending_before_generate_start_is_never_prompted():
    lines = parse_timestamped_lyrics("[01:01.359-01:04.600] Hit restore… press replay")
    windows = assign_lyrics_to_windows(lines, song_seconds=165.0, duration_seconds=10.0)
    end = 64.600
    for w in windows:
        has = any(
            "restore" in ln["text"].lower() or "replay" in ln["text"].lower()
            for ln in w["lines"]
        )
        gen_s = int(w["slice_start"]) / 24.0
        gen_e = gen_s + float(w["duration_seconds"])
        if gen_s >= end:
            assert not has
        if has:
            assert gen_s < end and gen_e > 61.359


def test_parse_srt_keeps_explicit_end():
    srt = """1
00:00:12,350 --> 00:00:14,000
hello world

2
00:00:14,000 --> 00:00:16,000
second line
"""
    lines = parse_timestamped_lyrics(srt)
    assert lines[0]["start"] == 12.35
    assert lines[0]["end"] == 14.0
    assert lines[1]["text"] == "second line"


def test_simple_seconds_cues():
    lines = parse_timestamped_lyrics("[12.5] hello\n[18] later")
    assert lines[0]["start"] == 12.5
    assert lines[1]["start"] == 18.0
    assert lines[0]["end"] == 18.0


def test_lrc_range_stamp_keeps_explicit_end():
    lines = parse_timestamped_lyrics("[00:32.380-00:35.120] Every joke, every scar")
    assert abs(lines[0]["start"] - 32.38) < 1e-9
    assert abs(lines[0]["end"] - 35.12) < 1e-9
    windows = assign_lyrics_to_windows(lines, song_seconds=40.0, duration_seconds=10.0)
    sung = next(w for w in windows if not w["instrumental"])
    assert "00:32.380-00:35.120" in format_window_lyrics(sung)
    assert sung["end"] >= 35.12


def test_line_end_past_generate_moves_whole_line_to_next_clip():
    lines = parse_timestamped_lyrics("[00:08.000-00:10.500] rushed line")
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    assert windows[0]["instrumental"] is True
    assert windows[1]["lines"][0]["text"] == "rushed line"
    assert windows[1]["end"] >= 10.5


def test_clip16_overrun_is_also_prompted_on_the_next_clip():
    lines = parse_timestamped_lyrics(
        "[02:01.110-02:02.911] Cloud copy of me\n"
        "[02:03.691-02:08.173] Still laughing somewhere in the binary\n"
        "[02:08.333-02:10.474] Every joke, every scar\n"
    )
    windows = assign_lyrics_to_windows(lines, song_seconds=165.0, duration_seconds=10.0)
    joke_windows = [
        w for w in windows
        if any("Every joke" in ln["text"] for ln in w["lines"])
    ]
    assert len(joke_windows) >= 1
    assert any(w["end"] >= 130.474 for w in joke_windows)
    laughing = next(
        w for w in windows
        if any("Still laughing" in ln["text"] for ln in w["lines"])
    )
    cloud = next(
        w for w in windows
        if any("Cloud copy" in ln["text"] or "copy of me" in ln["text"] for ln in w["lines"])
    )
    assert cloud["index"] <= laughing["index"]


def test_align_user_lyrics_keeps_words_and_whisper_intro_gap():
    from lyric_timing import align_user_lyrics_to_segments, split_plain_lyric_lines

    assert split_plain_lyric_lines("[Chorus]\nHello world\n\nSecond line") == [
        "Hello world", "Second line",
    ]
    segments = [
        {
            "start": 12.0, "end": 14.0, "text": "yellow world",
            "words": [
                {"start": 12.0, "end": 12.6, "text": "yellow"},
                {"start": 12.6, "end": 14.0, "text": "world"},
            ],
        },
        {
            "start": 15.5, "end": 17.0, "text": "second line",
            "words": [
                {"start": 15.5, "end": 16.2, "text": "second"},
                {"start": 16.2, "end": 17.0, "text": "line"},
            ],
        },
    ]
    aligned = align_user_lyrics_to_segments("Hello world\nSecond line", segments)
    assert [ln["text"] for ln in aligned] == ["Hello world", "Second line"]
    assert aligned[0]["start"] >= 12.0
    assert aligned[1]["start"] >= 15.0
    assert [w["text"] for w in aligned[0]["words"]] == ["Hello", "world"]
    windows = assign_lyrics_to_windows(aligned, song_seconds=20.25, duration_seconds=10.0)
    assert windows[0]["instrumental"] is True
    assert windows[1]["lines"][0]["text"] == "Hello world"


def test_align_drops_stray_token_that_would_crush_a_line():
    from lyric_timing import align_user_lyrics_to_segments

    segments = [
        {
            "start": 91.5, "end": 93.3, "text": "Save it save it oh whole",
            "words": [
                {"start": 91.546, "end": 91.866, "text": "Save"},
                {"start": 91.986, "end": 92.066, "text": "it"},
                {"start": 92.426, "end": 92.746, "text": "save"},
                {"start": 92.906, "end": 93.046, "text": "it"},
                {"start": 93.226, "end": 93.286, "text": "whole"},
            ],
        },
        {
            "start": 102.0, "end": 104.0, "text": "Keep a ghost in the",
            "words": [
                {"start": 102.057, "end": 102.337, "text": "Keep"},
                {"start": 102.637, "end": 102.758, "text": "a"},
                {"start": 102.798, "end": 103.418, "text": "ghost"},
                {"start": 103.578, "end": 103.819, "text": "in"},
                {"start": 103.859, "end": 103.999, "text": "the"},
            ],
        },
    ]
    user = (
        "Save it, save it (oh)\n"
        "Even the crashes, the late-night confessions\n"
        "The parts of me I never learned to mention\n"
        "Don’t let the silence swallow me whole\n"
        "Keep a ghost in the glow…"
    )
    aligned = {ln["text"]: ln for ln in align_user_lyrics_to_segments(user, segments)}
    swallow = aligned["Don’t let the silence swallow me whole"]
    assert swallow.get("end", 0) - swallow["start"] > 0.5
    assert not swallow.get("words") or len(swallow["words"]) > 1


CODE_STREAM_LINE = {
    "start": 20.797,
    "end": 23.959,
    "text": "Let my code keep dancing in the data stream",
    "words": [
        {"start": 20.797, "end": 21.050, "text": "Let"},
        {"start": 21.050, "end": 21.280, "text": "my"},
        {"start": 21.280, "end": 21.620, "text": "code"},
        {"start": 21.620, "end": 22.050, "text": "keep"},
        {"start": 22.400, "end": 22.900, "text": "dancing"},
        {"start": 22.900, "end": 23.100, "text": "in"},
        {"start": 23.100, "end": 23.250, "text": "the"},
        {"start": 23.250, "end": 23.550, "text": "data"},
        {"start": 23.550, "end": 23.959, "text": "stream"},
    ],
}


def test_crop_keeps_only_words_inside_kept_time():
    prev = crop_line_to_window(CODE_STREAM_LINE, {"start": 15.500, "end": 22.375})
    nxt = crop_line_to_window(
        CODE_STREAM_LINE,
        {"start": 22.375, "end": 28.542},
        prev={"start": 15.500, "end": 22.375},
    )
    assert prev["text"] == "Let my code keep"
    assert nxt["text"] == "dancing in the data stream"
    assert nxt["start"] >= 22.375
    assert "Let my code" not in nxt["text"]


def test_crop_includes_continuation_head_that_is_in_audio_1():
    prev = {
        "start": 72.417, "end": 78.583,
        "slice_start": 1708, "duration_seconds": 9.417,
    }
    nxt = {
        "start": 78.583, "end": 84.042,
        "slice_start": 1856, "duration_seconds": 8.708,
    }
    free = {
        "start": 76.764, "end": 78.725,
        "text": "Living on when these bones finally break free",
        "words": [
            {"start": 76.764, "end": 78.480, "text": "Living on when these bones finally break"},
            {"start": 78.583, "end": 78.725, "text": "free"},
        ],
    }
    joke = {
        "start": 79.145, "end": 80.266,
        "text": "Every joke, every scar",
        "words": [
            {"start": 79.145, "end": 79.400, "text": "Every"},
            {"start": 79.400, "end": 79.700, "text": "joke,"},
            {"start": 79.700, "end": 80.000, "text": "every"},
            {"start": 80.132, "end": 80.266, "text": "scar"},
        ],
    }
    cheap = {
        "start": 80.306, "end": 82.127,
        "text": "Every cheap memory we made",
        "words": [
            {"start": 80.306, "end": 80.500, "text": "Every"},
            {"start": 80.500, "end": 80.750, "text": "cheap"},
            {"start": 80.750, "end": 81.200, "text": "memory"},
            {"start": 81.200, "end": 81.450, "text": "we"},
            {"start": 81.450, "end": 82.127, "text": "made"},
        ],
    }
    free_next = crop_line_to_window(free, nxt, prev=prev)
    assert free_next is not None
    assert "free" in free_next["text"]
    joke_next = crop_line_to_window(joke, nxt, prev=prev)
    assert joke_next is not None
    assert "scar" in joke_next["text"]
    cheap_next = crop_line_to_window(cheap, nxt, prev=prev)
    assert cheap_next is not None
    assert "made" in cheap_next["text"]
    joke_prev = crop_line_to_window(joke, prev)
    assert joke_prev is not None
    assert "scar" in joke_prev["text"]
    free_prev = crop_line_to_window(free, prev)
    assert free_prev is not None
    assert "free" in free_prev["text"]


def test_clip25_lyrics_follow_audio_slice_not_kept_time():
    line = {
        "start": 142.319,
        "end": 146.721,
        "text": "When the lights go out, I’ll still be in the machine",
        "words": [
            {"start": 143.74, "end": 144.06, "text": "still"},
            {"start": 144.12, "end": 144.42, "text": "be"},
            {"start": 144.52, "end": 144.70, "text": "in"},
            {"start": 144.72, "end": 144.86, "text": "the"},
            {"start": 144.88, "end": 146.721, "text": "machine"},
        ],
    }
    window = {
        "start": 144.708, "end": 151.792,
        "slice_start": 3451, "duration_seconds": 10.125,
    }
    cropped = crop_line_to_window(line, window)
    assert "in the machine" in cropped["text"]
    assert "be" in cropped["text"]


def test_crop_without_word_times_keeps_the_whole_line():
    line = {
        "start": 20.797,
        "end": 23.959,
        "text": "Let my code keep dancing in the data stream",
    }
    nxt = crop_line_to_window(line, {"start": 22.375, "end": 28.542})
    assert nxt["text"] == line["text"]
    assert nxt["cropped"] is False


def test_clip5_word_clocks_drop_lyrics_past_audio_end():
    line = {
        "start": 39.575,
        "end": 41.712,
        "text": "If the screen goes dark, I’m still in the machine",
        "words": [
            {"start": 39.575, "end": 39.70, "text": "If"},
            {"start": 39.70, "end": 39.82, "text": "the"},
            {"start": 39.82, "end": 40.15, "text": "screen"},
            {"start": 40.15, "end": 40.35, "text": "goes"},
            {"start": 40.35, "end": 40.60, "text": "dark,"},
            {"start": 40.60, "end": 40.80, "text": "I’m"},
            {"start": 40.80, "end": 41.05, "text": "still"},
            {"start": 41.05, "end": 41.20, "text": "in"},
            {"start": 41.20, "end": 41.35, "text": "the"},
            {"start": 41.35, "end": 41.712, "text": "machine"},
        ],
    }
    window = {
        "start": 31.708, "end": 38.792,
        "slice_start": 731, "duration_seconds": 9.417,
    }
    cropped = crop_line_to_window(line, window)
    assert cropped is not None
    assert cropped["text"] == "If the"
    assert "machine" not in cropped["text"]
    assert "screen" not in cropped["text"]


def test_dump_aligned_lyrics_keeps_confirm_line_stamps():
    import json
    from tempfile import TemporaryDirectory

    lines = [{
        "start": 39.575,
        "end": 41.712,
        "text": "If the screen goes dark",
        "words": [
            {"start": 39.60, "end": 39.70, "text": "If"},
            {"start": 39.70, "end": 39.82, "text": "the"},
        ],
    }]
    payload = json.loads(dump_aligned_lyrics(lines, song_seconds=165.21, source="wav2vec2-refine"))
    item = payload["lines"][0]
    assert item["start"] == 39.575
    assert item["end"] == 41.712
    assert item["text"] == "If the screen goes dark"
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "song.confirm.words.json"
        path.write_text(dump_aligned_lyrics(lines), encoding="utf-8")
        loaded = _load_aligned_json(str(path))
    assert loaded[0]["start"] == 39.575
    assert loaded[0]["end"] == 41.712
    assert loaded[0]["text"] == "If the screen goes dark"
    assert [w["text"] for w in loaded[0]["words"]] == "If the screen goes dark".split()


def test_aligned_words_json_roundtrip_keeps_word_clocks():
    import json
    from tempfile import TemporaryDirectory

    lines = [{
        "start": 135.956,
        "end": 141.498,
        "text": "Cloud copy of me",
        "words": [
            {"start": 138.90, "end": 139.70, "text": "Cloud"},
            {"start": 139.80, "end": 140.20, "text": "copy"},
            {"start": 140.20, "end": 140.50, "text": "of"},
            {"start": 140.50, "end": 141.498, "text": "me"},
        ],
    }]
    raw = dump_aligned_lyrics(lines, song_seconds=165.21, source="whisperx")
    payload = json.loads(raw)
    assert payload["lines"][0]["words"][0]["text"] == "Cloud"
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "song.words.json"
        path.write_text(raw, encoding="utf-8")
        loaded = _load_aligned_json(str(path))
    window = {
        "start": 139.750, "end": 144.708,
        "slice_start": 3332, "duration_seconds": 8.0,
    }
    cropped = crop_line_to_window(loaded[0], window)
    assert "copy of me" in cropped["text"]
    assert "Cloud" in cropped["text"]


def test_crop_splits_long_word_on_char_times():
    chars = []
    text = "dancing"
    for i, glyph in enumerate(text):
        t0 = 22.0 + i / len(text)
        chars.append({"char": glyph, "start": t0, "end": 22.0 + (i + 1) / len(text)})
    line = {
        "start": 22.0,
        "end": 23.0,
        "text": "dancing",
        "words": [{"start": 22.0, "end": 23.0, "text": "dancing", "chars": chars}],
    }
    prev = crop_line_to_window(line, {"start": 20.0, "end": 22.5})
    nxt = crop_line_to_window(line, {"start": 22.5, "end": 28.0})
    assert prev["text"]
    assert nxt["text"]
    assert prev["text"] + nxt["text"] == "dancing"
    assert prev["text"] != "dancing"
    assert nxt["text"] != "dancing"


def test_skeleton_emits_kept_headers_and_empty_prompts():
    lines = parse_timestamped_lyrics("[00:12.000-00:14.000] hello world")
    windows = assign_lyrics_to_windows(lines, song_seconds=20.25, duration_seconds=10.0)
    text = format_music_video_skeleton(windows, 10.0)
    assert text.startswith("h3_music_video: 1\nmax_duration_seconds: 10.125\n")
    assert f"clip_count: {len(windows)}" in text
    first = windows[0]
    assert f"time: {first['start']:.3f}-{first['end']:.3f}" in text
    assert "duration_seconds: 10.125" in text
    assert "lyrics: (instrumental)" in text
    assert "hello world" in text
    assert "prompt:" in text
    for w in windows:
        gen_s = int(w["slice_start"]) / 24.0
        gen_e = gen_s + float(w["duration_seconds"])
        for line in w["lines"]:
            assert float(line["end"]) > gen_s
            assert float(line["start"]) < gen_e


def test_format_lrc_puts_a_space_after_the_stamp():
    text = format_lrc([{
        "start": 119.680, "end": 122.480, "text": "Cloud copy of me",
    }])
    assert text == "[01:59.680-02:02.480] Cloud copy of me\n"


def test_format_lrc_keeps_instrumental_marker():
    text = format_lrc([{
        "start": 64.849, "end": 74.556, "text": "<instrumental>", "words": [],
    }])
    assert text == "[01:04.849-01:14.556] <instrumental>\n"


def test_parse_time_range_accepts_seconds_and_clocks():
    assert parse_time_range("131.042-136.917") == (131.042, 136.917)
    start, end = parse_time_range("02:11.042-02:12.720")
    assert abs(start - 131.042) < 1e-9
    assert abs(end - 132.720) < 1e-9
    assert parse_time_range("[02:11.042-02:12.720]")[0] == start


def test_merge_keeps_extra_asr_and_drafts_missing_user_line():
    segments = [{
        "start": 134.0, "end": 141.5, "text": "Save it save it Cloud copy of me Yeah",
        "words": [
            {"start": 134.0, "end": 134.3, "text": "Save"},
            {"start": 134.3, "end": 134.5, "text": "it"},
            {"start": 135.0, "end": 135.3, "text": "save"},
            {"start": 135.3, "end": 135.5, "text": "it"},
            {"start": 139.5, "end": 140.0, "text": "Cloud"},
            {"start": 140.0, "end": 140.4, "text": "copy"},
            {"start": 140.4, "end": 140.6, "text": "of"},
            {"start": 140.6, "end": 141.0, "text": "me"},
            {"start": 141.2, "end": 141.5, "text": "Yeah"},
        ],
    }]
    merged = merge_asr_and_user_lyrics(
        segments,
        "Save it, save it\nHey!\nCloud copy of me",
        song_seconds=150.0,
    )
    texts = [ln["text"] for ln in merged]
    assert "Hey!" in texts
    assert any(t == "Yeah" or t.endswith("Yeah") for t in texts)
    save = next(ln for ln in merged if ln["text"].startswith("Save it"))
    assert abs(save["start"] - 134.0) < 1e-6
    cloud = next(ln for ln in merged if "Cloud copy of me" in ln["text"])
    assert abs(cloud["start"] - 139.5) < 1e-6
    assert cloud["text"] == "Cloud copy of me"
    hey = next(ln for ln in merged if "Hey" in ln["text"])
    assert 135.5 <= hey["start"] < 139.5
    assert hey["end"] <= 139.5


def test_merge_matched_line_uses_user_wording_on_asr_clocks():
    segments = [{
        "start": 12.0, "end": 14.0, "text": "yellow world",
        "words": [
            {"start": 12.0, "end": 12.6, "text": "yellow"},
            {"start": 12.6, "end": 14.0, "text": "world"},
        ],
    }]
    merged = merge_asr_and_user_lyrics(segments, "Hello world", song_seconds=20.0)
    assert merged[0]["text"] == "Hello world"
    assert merged[0]["start"] == 12.0
    assert merged[0]["end"] == 14.0


def test_phrase_lines_split_on_rests():
    words = [
        {"start": 1.0, "end": 1.2, "text": "Save"},
        {"start": 1.2, "end": 1.4, "text": "it"},
        {"start": 4.0, "end": 4.3, "text": "Cloud"},
        {"start": 4.3, "end": 4.6, "text": "copy"},
    ]
    lines = phrase_lines_from_words(words)
    assert len(lines) == 2
    assert lines[0]["text"] == "Save it"
    assert lines[1]["text"] == "Cloud copy"

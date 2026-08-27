import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyric_align import apply_line_refine, lines_from_aligned_words, refine_confirm_lyrics, resolve_timed_lyrics
from lyric_timing import format_lrc

ROOT = Path(__file__).resolve().parents[1]
LRC_CLOCK = re.compile(
    r"^\[\d{2}:\d{2}\.\d{3}-\d{2}:\d{2}\.\d{3}\] .+\n$",
)


def test_lines_from_aligned_words_groups_by_user_breaks():
    lines = ["hello world", "second line"]
    words = [
        {"start": 1.0, "end": 1.2, "text": "HELLO"},
        {"start": 1.2, "end": 1.5, "text": "WORLD"},
        {"start": 2.0, "end": 2.3, "text": "SECOND"},
        {"start": 2.3, "end": 2.6, "text": "LINE"},
    ]
    out = lines_from_aligned_words(lines, words)
    assert out[0]["text"] == "hello world"
    assert out[0]["start"] == 1.0
    assert out[0]["end"] == 1.5
    assert out[1]["text"] == "second line"
    assert out[1]["start"] == 2.0
    assert out[1]["end"] == 2.6


def test_lines_from_aligned_words_keeps_hold_markup():
    out = lines_from_aligned_words(
        ["sing ~time~"],
        [
            {"start": 4.0, "end": 4.2, "text": "SING"},
            {"start": 4.2, "end": 5.0, "text": "TIME"},
        ],
    )
    assert out[0]["text"] == "sing ~time~"
    assert out[0]["start"] == 4.0
    assert out[0]["end"] == 5.0


def test_lines_from_aligned_words_leftover_clocks_extend_last_line():
    out = lines_from_aligned_words(
        ["hello"],
        [
            {"start": 1.0, "end": 1.2, "text": "HELLO"},
            {"start": 1.4, "end": 1.8, "text": "THERE"},
        ],
    )
    assert out[0]["text"] == "hello"
    assert out[0]["start"] == 1.0
    assert out[0]["end"] == 1.8


def test_lines_from_aligned_words_fills_instrumental_gap():
    out = lines_from_aligned_words(
        ["hello world", "<instrumental>", "second line"],
        [
            {"start": 1.0, "end": 1.2, "text": "HELLO"},
            {"start": 1.2, "end": 1.5, "text": "WORLD"},
            {"start": 3.0, "end": 3.2, "text": "SECOND"},
            {"start": 3.2, "end": 3.6, "text": "LINE"},
        ],
    )
    assert out[1]["text"] == "<instrumental>"
    assert out[1]["start"] == 1.5
    assert out[1]["end"] == 3.0


def test_resolve_timed_lyrics_passthrough_lrc():
    lrc = "[00:12.000-00:15.000] hello world\n"
    assert resolve_timed_lyrics("unused.wav", lrc) == lrc


def test_resolve_timed_lyrics_empty():
    with pytest.raises(ValueError, match="lyrics are required"):
        resolve_timed_lyrics("unused.wav", "")
    with pytest.raises(ValueError, match="lyrics are required"):
        resolve_timed_lyrics("unused.wav", "[Chorus]\n\n")


def test_format_lrc_matches_timeline_clock():
    text = format_lrc([{"start": 12.0, "end": 15.5, "text": "hello"}])
    assert LRC_CLOCK.match(text)
    assert text == "[00:12.000-00:15.500] hello\n"


def test_load_song_align_wiring():
    loader = (ROOT / "song_loader.py").read_text(encoding="utf-8")
    js = (ROOT / "web" / "js" / "songTimeline.js").read_text(encoding="utf-8")
    assert "resolve_timed_lyrics" in loader
    assert 'return "h3_studio: lyrics are required"' in loader
    assert "/h3_studio_song/align" in loader
    assert '{"ui": {"lyrics": [timed]}, "result": (loaded, timed)}' in loader
    assert 'node.addWidget("button", "Time lyrics"' in js
    assert 'api.fetchApi("/h3_studio_song/align"' in js
    assert 'chainCallback(node, "onExecuted"' in js
    assert "function syncFromWidgets()" in js
    assert "function audioFilename()" in js
    assert "syncFromWidgets();" in js
    assert 'chainCallback(node, "onConfigure"' in js


def test_apply_line_refine_keeps_confirm_stamps():
    line = {"start": 1.0, "end": 3.0, "text": "hello world"}
    words = [
        {"start": 1.1, "end": 1.5, "text": "hello"},
        {"start": 1.5, "end": 2.0, "text": "world"},
    ]
    out = apply_line_refine(line, words, 10.0)
    assert out["start"] == 1.0
    assert out["end"] == 3.0
    assert out["text"] == "hello world"
    assert [w["text"] for w in out["words"]] == ["hello", "world"]


def test_apply_line_refine_even_splits_when_align_fails():
    line = {"start": 1.0, "end": 3.0, "text": "hello world"}
    out = apply_line_refine(line, None, 10.0)
    assert out["start"] == 1.0
    assert out["end"] == 3.0
    assert out["text"] == "hello world"
    assert len(out["words"]) == 2
    assert out["words"][0]["start"] == 1.0
    assert out["words"][-1]["end"] == 3.0


def test_refine_confirm_lyrics_rejects_untimed():
    with pytest.raises(ValueError, match="time lyrics"):
        refine_confirm_lyrics(None, 16000, "hello world\nsecond line")

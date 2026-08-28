import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from types import SimpleNamespace

from lyric_align import (
    _spans_to_words, apply_line_refine, lines_from_aligned_words,
    refine_confirm_lyrics, resolve_timed_lyrics,
)
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
    assert "/h3_studio_song/path" in loader
    assert "/h3_studio_song/refine" in loader
    assert "/h3_studio_song/plan" in loader
    assert "def plan_music_video" in loader
    assert "format_music_video_skeleton" in loader
    assert "dump_aligned_lyrics" in loader
    assert "return web.json_response(planned)" in loader
    assert "def resolve_song_file_path" in loader
    assert "refine_confirm_lyrics" in loader
    assert '{"ui": {"lyrics": [timed]}, "result": (loaded, timed)}' in loader
    assert '"loop": ("STRING"' not in loader
    assert "h3song-action-upload" in js
    assert "Upload audio" in js
    assert 'alignBtn.textContent = "Time lyrics"' in js
    assert "without H3 loaded" in js
    assert "h3song-btn-add" in js
    assert 'addBtn.textContent = "Add A–B"' in js
    assert 'writeLabel.append(writeBox, document.createTextNode("Live Edit"))' in js
    assert "h3AbRange" in js
    assert "function stripLeftoverSongWidgets" in js
    assert "function pinSongWidgetGrid" in js
    assert "h3song-panel" in js
    assert "h3song-footer" in js
    assert 'getHeight: () => "100%"' in js
    assert ".lg-node:has(.h3song-panel)" in js
    assert "const MIN_NODE_HEIGHT = 240" in js
    assert "function ensureMinSize" in js
    assert "function installSizeGuard" in js
    assert 'api.fetchApi("/h3_studio_song/align"' in js
    assert 'chainCallback(node, "onExecuted"' in js
    assert "function syncFromWidgets()" in js
    assert "function audioFilename()" in js
    assert "syncFromWidgets();" in js
    assert 'chainCallback(node, "onConfigure"' in js


def test_apply_line_refine_keeps_confirm_stamps():
    line = {"start": 1.0, "end": 3.0, "text": "hello world"}
    words = [
        {
            "start": 1.1, "end": 1.5, "text": "hello",
            "chars": [
                {"char": "H", "start": 1.1, "end": 1.3},
                {"char": "E", "start": 1.3, "end": 1.5},
            ],
        },
        {"start": 1.5, "end": 2.0, "text": "world"},
    ]
    out = apply_line_refine(line, words, 10.0)
    assert out["start"] == 1.0
    assert out["end"] == 3.0
    assert out["text"] == "hello world"
    assert [w["text"] for w in out["words"]] == ["hello", "world"]
    assert [c["char"] for c in out["words"][0]["chars"]] == ["H", "E"]


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


def test_spans_to_words_emits_char_clocks():
    labels = ("-", "|", "H", "I")
    spans = [
        SimpleNamespace(token=2, start=0, end=4),
        SimpleNamespace(token=3, start=4, end=8),
        SimpleNamespace(token=1, start=8, end=9),
        SimpleNamespace(token=2, start=10, end=12),
        SimpleNamespace(token=3, start=12, end=16),
    ]
    words = _spans_to_words(spans, labels, 0.02)
    assert [w["text"] for w in words] == ["HI", "HI"]
    assert words[0]["start"] == 0.0
    assert words[0]["end"] == pytest.approx(0.16)
    assert [c["char"] for c in words[0]["chars"]] == ["H", "I"]
    assert words[0]["chars"][0]["char"] == "H"
    assert words[0]["chars"][0]["start"] == 0.0
    assert words[0]["chars"][0]["end"] == pytest.approx(0.08)
    assert words[0]["chars"][1]["char"] == "I"
    assert words[0]["chars"][1]["start"] == pytest.approx(0.08)
    assert words[0]["chars"][1]["end"] == pytest.approx(0.16)
    assert [c["char"] for c in words[1]["chars"]] == ["H", "I"]
    assert words[1]["start"] == pytest.approx(0.20)
    assert words[1]["end"] == pytest.approx(0.32)


def test_spans_to_words_rejects_empty():
    with pytest.raises(ValueError, match="no word clocks"):
        _spans_to_words([], ("-", "|", "A"), 0.02)

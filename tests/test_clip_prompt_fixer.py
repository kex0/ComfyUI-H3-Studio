import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = "herrgotts_h3_suite_testpkg"

FULL = """H3 Studio prompt
mode: music_video
duration: 10.125
segments: 2

## Clip 1 — Start
time: 0.000-9.125
duration_seconds: 10.125
slice: 0.000
audio: 0.000-10.125
lyrics:
[00:01.000-00:03.000] hello
subject_definitions:
<Subject 1> is the singer.
summary:
opens
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A

## Clip 2 — Continue
time: 9.125-18.250
duration_seconds: 10.125
slice: 8.208
audio: 8.208-18.333
lyrics:
[00:12.000-00:14.000] next
subject_definitions:
<Subject 1> is the singer.
summary:
continues
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A
"""

PARTIAL = """## Clip 11 — Continue
time: 90.000-99.125
duration_seconds: 10.125
slice: 81.000
audio: 81.000-91.125
lyrics:
[01:32.000-01:34.000] later
subject_definitions:
<Subject 1> is the singer.
summary:
fix me
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A

## Clip 12 — Continue
time: 99.125-108.250
duration_seconds: 10.125
slice: 89.208
audio: 89.208-99.333
lyrics:
[01:41.000-01:43.000] after
subject_definitions:
<Subject 1> is the singer.
summary:
also fix
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A
"""

MISMATCHED = """H3 Studio prompt
mode: music_video
duration: 10.125
segments: 30

## Clip 1 — Start
time: 0.000-9.125
duration_seconds: 10.125
audio: 0.000-10.125
lyrics:
[00:01.000-00:03.000] hello
summary:
opens
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A

## Clip 2 — Continue
time: 9.125-18.250
duration_seconds: 10.125
audio: 8.208-18.333
lyrics:
[00:12.000-00:14.000] next
summary:
continues
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A
"""


def _load(name):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
    return importlib.import_module(f"{PKG}.{name}")


def _pack(**kwargs):
    pack = {
        "models": [{"index": 1, "description": "base", "model": "m"}],
        "pictures": [],
        "videos": [],
        "audios": [],
        "duration": 10.125,
        "plan": "builder plan",
    }
    pack.update(kwargs)
    return pack


def test_parse_clip_index_ranges_and_lists():
    fixer = _load("clip_prompt_fixer")
    assert fixer.parse_clip_index("11-12") == [11, 12]
    assert fixer.parse_clip_index("11,12") == [11, 12]
    assert fixer.parse_clip_index("11, 12") == [11, 12]
    assert fixer.parse_clip_index("3") == [3]
    assert fixer.parse_clip_index("11 - 12") == [11, 12]
    assert fixer.parse_clip_index("12-11") == [11, 12]
    assert fixer.parse_clip_index("1,3,5") == [1, 3, 5]
    assert fixer.parse_clip_index("") == []
    with pytest.raises(ValueError, match="invalid clip_index"):
        fixer.parse_clip_index("foo")
    with pytest.raises(ValueError, match=">= 1"):
        fixer.parse_clip_index("0")


def test_empty_index_on_full_doc_errors():
    fixer = _load("clip_prompt_fixer")
    parsed = _load("prompt_document").parse_prompt_document(FULL)
    assert fixer.seed_is_partial(parsed) is False
    with pytest.raises(ValueError, match="clip_index is required"):
        fixer.resolve_fix_clips("", parsed)
    assert fixer.resolve_fix_clips("2", parsed) == [2]


def test_empty_index_on_partial_uses_pasted_indices():
    fixer = _load("clip_prompt_fixer")
    docs = _load("prompt_document")
    partial = docs.parse_prompt_document(PARTIAL)
    assert fixer.seed_is_partial(partial) is True
    assert fixer.resolve_fix_clips("", partial) == [11, 12]
    mismatched = docs.parse_prompt_document(MISMATCHED)
    assert fixer.seed_is_partial(mismatched) is True
    assert fixer.resolve_fix_clips("", mismatched) == [1, 2]
    with pytest.raises(ValueError, match="no clip 13"):
        fixer.resolve_fix_clips("11-13", partial)


def test_attach_fix_mutates_pack():
    fixer = _load("clip_prompt_fixer")
    node = fixer.H3StudioClipPromptFixer()
    pack, = node.attach_fix(_pack(), FULL, "2", "make clip 2 darker")
    assert pack["prompt_mode"] == "clip_fix"
    assert pack["seed_prompt"] == FULL.strip()
    assert pack["fix_clips"] == [2]
    assert pack["plan"] == "make clip 2 darker"
    assert pack["duration"] == 10.125
    assert pack["models"][0]["model"] == "m"
    through = _load("pack").require_pack(pack)
    assert through["prompt_mode"] == "clip_fix"
    assert through["fix_clips"] == [2]
    assert through["plan"] == "make clip 2 darker"

    partial, = node.attach_fix(_pack(), PARTIAL, "", "fix those two")
    assert partial["fix_clips"] == [11, 12]

    with pytest.raises(ValueError, match="Plan is required"):
        node.attach_fix(_pack(), FULL, "1", "  ")
    with pytest.raises(ValueError, match="original_prompt is empty"):
        node.attach_fix(_pack(), "", "1", "fix")
    with pytest.raises(ValueError, match="clip_index is required"):
        node.attach_fix(_pack(), FULL, "", "fix")


def test_copy_skill_command_js_and_docs():
    js = (ROOT / "web" / "js" / "clipPromptFixer.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Copy skill command" in js
    assert "COPY_TIP" in js
    assert "/prompt-minimax-h3-clip-fix" in js
    assert "formatSkillCommand" in js
    assert "formatLinkedDump" in js
    assert "original_prompt:" in js
    assert "clip_index:" in js
    assert "extractPromptWindow" in js
    assert "windowIndices" in js
    assert 'button.textContent = "Copied"' in js
    assert "h3-clip-fixer-copied" in js
    assert "Copy skill command" in readme
    assert "/prompt-minimax-h3-clip-fix" in readme
    assert "one previous and one following" in readme


def _numbered_doc(count: int) -> str:
    parts = ["H3 Studio prompt", "mode: music_video", f"segments: {count}", ""]
    for n in range(1, count + 1):
        role = "Start" if n == 1 else "Continue"
        parts.append(f"## Clip {n} — {role}")
        parts.append(f"summary:\nclip {n}")
        parts.append("retention_analysis:\nx")
        parts.append("detailed_description:\nshot")
        parts.append("overall_soundscape:\na")
        parts.append("non_diegetic_music:\nN/A")
        parts.append("")
    return "\n".join(parts)


def test_extract_prompt_window_includes_neighbors():
    fixer = _load("clip_prompt_fixer")
    assert fixer.window_indices([11]) == [10, 11, 12]
    assert fixer.window_indices([11, 12]) == [10, 11, 12, 13]
    assert fixer.window_indices([4]) == [3, 4, 5]
    assert fixer.window_indices([1]) == [1, 2]
    doc = _numbered_doc(15)
    window = fixer.extract_prompt_window(doc, "11")
    assert window.startswith("## Clip 10 — Continue")
    assert "## Clip 11 — Continue" in window
    assert "## Clip 12 — Continue" in window
    assert "## Clip 9 — Continue" not in window
    assert "## Clip 13 — Continue" not in window
    assert "H3 Studio prompt" not in window
    assert "segments:" not in window
    pair = fixer.extract_prompt_window(doc, "11,12")
    assert "## Clip 10 — Continue" in pair
    assert "## Clip 13 — Continue" in pair
    assert "## Clip 14 — Continue" not in pair
    four = fixer.extract_prompt_window(doc, "4")
    assert "## Clip 3 — Continue" in four
    assert "## Clip 4 — Continue" in four
    assert "## Clip 5 — Continue" in four
    assert "## Clip 2 — Continue" not in four
    first = fixer.extract_prompt_window(doc, "1")
    assert "## Clip 1 — Start" in first
    assert "## Clip 2 — Continue" in first
    assert "## Clip 3 — Continue" not in first
    partial = fixer.extract_prompt_window(PARTIAL, "")
    assert "## Clip 11 — Continue" in partial
    assert "## Clip 12 — Continue" in partial
    assert "H3 Studio prompt" not in partial

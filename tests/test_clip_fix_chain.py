import importlib
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = "herrgotts_h3_suite_testpkg"


def _load(name):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
    return importlib.import_module(f"{PKG}.{name}")

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
[01:40.000-01:42.000] next
subject_definitions:
<Subject 1> is the singer.
summary:
fix me too
retention_analysis:
x
detailed_description:
shot
overall_soundscape:
a
non_diegetic_music:
N/A
"""


def test_clip_fix_neighbors_sandwich_policy():
    fixer = _load("clip_fix_chain")
    saved = list(range(1, 32))
    assert fixer.clip_fix_neighbors(11, [11], saved) == (10, 12)
    assert fixer.clip_fix_neighbors(11, [11, 12], saved) == (10, None)
    assert fixer.clip_fix_neighbors(12, [11, 12], saved) == (11, 13)
    assert fixer.clip_fix_neighbors(11, [11, 13], saved) == (10, 12)
    assert fixer.clip_fix_neighbors(13, [11, 13], saved) == (12, 14)
    assert fixer.clip_fix_neighbors(1, [1], saved) == (None, 2)
    assert fixer.clip_fix_neighbors(31, [31], saved) == (30, None)


def test_resolve_regen_empty_uses_prompt_clips():
    fixer = _load("clip_fix_chain")
    indices = fixer.prompt_story_indices(PARTIAL)
    assert indices == [11, 12]
    assert fixer.resolve_regen_clips("", indices) == [11, 12]
    assert fixer.resolve_regen_clips("11", indices) == [11]
    with pytest.raises(ValueError, match="no clip 13"):
        fixer.resolve_regen_clips("11-13", indices)


def test_require_contiguous_and_fix_slots():
    fixer = _load("clip_fix_chain")
    assert fixer.require_contiguous_chain(list(range(1, 6))) == 5
    with pytest.raises(ValueError, match="missing saved clip 3"):
        fixer.require_contiguous_chain([1, 2, 4, 5])
    with pytest.raises(ValueError, match="no contiguous"):
        fixer.require_contiguous_chain([2, 3, 4])
    saved = list(range(1, 6))
    fixer.require_fix_slots([2, 3], saved, 5)
    with pytest.raises(ValueError, match="no saved clip 4"):
        fixer.require_fix_slots([2], [1, 2, 3], 5)
    with pytest.raises(ValueError, match="outside the saved chain"):
        fixer.require_fix_slots([11], saved, 5)


def test_infer_story_and_loop_and_regen_loop():
    fixer = _load("clip_fix_chain")
    assert fixer.infer_story_and_loop(4, segments_hint=3, loop_hint=True) == (3, True)
    assert fixer.infer_story_and_loop(3, segments_hint=3, loop_hint=True) == (3, False)
    assert fixer.infer_story_and_loop(13, loop_hint=True, max_story=12) == (12, True)
    assert fixer.infer_story_and_loop(5, loop_hint=False) == (5, False)
    assert fixer.should_regen_loop([3], 3, True) is True
    assert fixer.should_regen_loop([2], 3, True) is False
    assert fixer.should_regen_loop([3], 3, False) is False


def test_list_saved_indices_and_backup(tmp_path):
    fixer = _load("clip_fix_chain")
    names = ["clip_00001.safetensors", "clip_00002.safetensors", "other_00003.safetensors"]
    assert fixer.list_saved_indices(names, "clip") == [1, 2]
    chain = tmp_path / "h3_music_video"
    chain.mkdir()
    (chain / "clip_00011.safetensors").write_text("latent11", encoding="utf-8")
    (chain / "clip_00011_song.mp4").write_text("mp4", encoding="utf-8")
    (chain / "clip_00012.safetensors").write_text("latent12", encoding="utf-8")
    (chain / "clip_00010.safetensors").write_text("keep", encoding="utf-8")
    dest = fixer.backup_folder(str(chain), fixer.backup_stamp(datetime(2026, 8, 27, 17, 12, 5)))
    assert dest.endswith("backup_20260827_171205")
    copied = fixer.backup_clip_slots(str(chain), "clip", [11], dest)
    basenames = sorted(Path(p).name for p in copied)
    assert basenames == ["clip_00011.safetensors", "clip_00011_song.mp4"]
    assert (Path(dest) / "clip_00011.safetensors").read_text(encoding="utf-8") == "latent11"
    assert not (Path(dest) / "clip_00012.safetensors").exists()
    assert fixer.files_for_clip_slot(str(chain), "clip", 12) == [str(chain / "clip_00012.safetensors")]


def test_expand_fix_clip_sparse_prompt():
    fixer = _load("clip_fix_chain")
    body = fixer.expand_fix_clip(PARTIAL, 11, song_audio=True)
    assert "fix me" in body
    assert "<Subject 1>" in body
    with pytest.raises(ValueError, match="no clip 10"):
        fixer.expand_fix_clip(PARTIAL, 10)


def test_next_clip_end_skip_uses_head_not_i2va():
    math = _load("latent_math")
    assert math.steps_for_pixel_frames(22) == math.CONTEXT_TO_STEPS[22]
    loop = math.loop_end_keyframe_offsets(243, 22, source_latent_t=72)
    nxt = math.next_clip_end_keyframe_offsets(243, 22, 72, math.CONTEXT_TO_STEPS[22])
    assert loop["source_skip_steps"] == 5
    assert nxt["source_skip_steps"] == math.CONTEXT_TO_STEPS[22]
    assert nxt["source_skip_steps"] != loop["source_skip_steps"]
    assert math.pixel_frames(nxt["source_skip_steps"]) == 22
    assert nxt["source_start_t"] == math.CONTEXT_TO_STEPS[22]
    assert nxt["context_steps"] == math.CONTEXT_TO_STEPS[22]


def test_end_context_skips_audio_when_song_present():
    math = _load("latent_math")
    assert math.end_context_includes_audio(song_audio_latent="z") is False
    assert math.end_context_includes_audio(song_audio_latent="z", pack_end_audio=True) is False
    assert math.end_context_includes_audio(pack_end_audio=False) is False
    assert math.end_context_includes_audio() is True


def test_clip_fixer_nodes_registered_and_documented():
    init = (ROOT / "__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    editor = (ROOT / "web" / "js" / "promptEditor.js").read_text(encoding="utf-8")
    mv = (ROOT / "music_video.py").read_text(encoding="utf-8")
    ac = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    assert '"H3StudioMusicVideoClipFixer": H3StudioMusicVideoClipFixer' in init
    assert '"H3StudioAutoChainClipFixer": H3StudioAutoChainClipFixer' in init
    assert "H3 Studio - Music Video Clip Fixer" in init
    assert "H3 Studio - Auto Chain Clip Fixer" in init
    assert "Music Video Clip Fixer" in readme
    assert "Auto Chain Clip Fixer" in readme
    assert "backup_YYYYMMDD_HHMMSS" in readme
    assert "H3StudioMusicVideoClipFixer" in editor
    assert "H3StudioAutoChainClipFixer" in editor
    assert "def _generate_fix_chain" in mv
    assert 'extra_end["pack_end_audio"] = False' in mv
    assert "restitches the full" in mv
    assert "warn_disk_budget(\n                song_frames, width, height," in mv
    assert "def _generate_fix_chain" in ac
    assert "should_regen_loop" in ac
    assert "next_clip_end_keyframe_offsets" in nodes
    assert "end_context_includes_audio" in nodes
    assert "resume_from_clip" in (ROOT / "clip_fixer.py").read_text(encoding="utf-8")
    fixer = (ROOT / "clip_fixer.py").read_text(encoding="utf-8")
    assert 'drop=("resume_from_clip", "stop_after_clip", "duration", "segments", "seamless_loop")' in fixer
    assert 'drop=("resume_from_clip", "duration", "segments", "seamless_loop")' in fixer
    assert 'mode == "per_clip" and kwargs.get("duration")' not in fixer
    assert "Only changes how the prompt is shown. It does not affect generation." in fixer
    assert "clip_fix" in mv
    assert 'not kwargs.get("clip_fix")' in mv


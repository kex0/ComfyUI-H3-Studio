import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = "herrgotts_h3_suite_testpkg"

DUMP = """H3 Studio Builder pack
duration: 10.00s
segments: 2
Model 1: cinematic identity LoRA stack
Picture 1: blonde woman, red jacket (first frame)
Picture 2: night street
Video 1: 4.2s walking cycle (with soundtrack)
Audio 1: 3.1s rain bed
"""

VALID_CLIP1 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Picture 1> is the first frame of [Shot 1], showing a blonde woman in a red jacket.
<Subject 2> is the night street in <Picture 2>.

summary:
[keyframe completion + reference generation] The woman stands on the street and starts walking.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same face and red jacket.
<Picture 1> ([Shot 1] first frame): fully_preserved - opening crop matches the still.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] She is already in the still's pose, then steps forward down the street.

overall_soundscape: rain and distant traffic

non_diegetic_music: N/A
"""

VALID_CLIP2 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.

summary:
[video continuation + reference generation] She keeps walking down the street.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same red jacket.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] She is already mid-stride from the previous clip and keeps walking.

overall_soundscape: rain on pavement

non_diegetic_music: N/A
"""

MV_CLIP1 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Picture 1> is the first frame of [Shot 1], showing a blonde woman in a red jacket.
<Audio 1> is the source-song slice covering 0.000–10.125 of the master.

summary:
[keyframe completion + reference generation] She sings this window in sync with <Audio 1>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same face and red jacket.
<Picture 1> ([Shot 1] first frame): fully_preserved - opening crop matches the still.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] hello world</d>.

overall_soundscape: city night

non_diegetic_music: N/A
"""


def _load(name):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
    return importlib.import_module(f"{PKG}.{name}")


def test_parse_builder_dump_tags_and_first_frame():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    assert inventory["duration"] == 10.0
    assert inventory["segments"] == 2
    assert inventory["loop"] is False
    assert inventory["first_frame"] == 1
    assert [item["index"] for item in inventory["pictures"]] == [1, 2]
    assert inventory["pictures"][0]["first_frame"] is True
    assert inventory["pictures"][0]["description"] == "blonde woman, red jacket"
    assert inventory["videos"][0]["index"] == 1
    assert inventory["audios"][0]["index"] == 1
    assert inventory["models"][0]["index"] == 1
    looped = prompter.parse_builder_dump(DUMP.replace("segments: 2", "segments: 2\nloop: true"))
    assert looped["loop"] is True
    planned = prompter.parse_builder_dump(DUMP + "plan:\nshe walks the street\n")
    assert planned["plan"] == "she walks the street"
    assert planned["pictures"][0]["description"] == "blonde woman, red jacket"


def test_validate_clip1_requires_first_frame_row():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    missing = VALID_CLIP1.replace(
        "<Picture 1> is the first frame of [Shot 1], showing a blonde woman in a red jacket.\n",
        "",
    )
    issues = prompter.validate_clip_prompt(missing, inventory, 1)
    assert any("first frame of [Shot 1]" in item for item in issues)


def test_validate_unknown_tag_and_t2va_lock():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    bad = VALID_CLIP1.replace("<Picture 2>", "<Picture 9>").replace(
        "overall_soundscape: rain and distant traffic",
        "The woman at 0.00 seconds is fully referenced.\noverall_soundscape: rain and distant traffic",
    )
    issues = prompter.validate_clip_prompt(bad, inventory, 1)
    assert any("unknown pictures" in item for item in issues)
    assert any("T2VA lock" in item for item in issues)


def test_validate_continue_rejects_first_frame_row():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    bad = VALID_CLIP2.replace(
        "<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.",
        "<Picture 1> is the first frame of [Shot 1], showing the still again.",
    )
    issues = prompter.validate_clip_prompt(bad, inventory, 2)
    assert any("must not reopen" in item for item in issues)
    assert prompter.validate_clip_prompt(VALID_CLIP1, inventory, 1) == []
    assert prompter.validate_clip_prompt(VALID_CLIP2, inventory, 2) == []


def test_validate_continue_requires_identity_picture():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    missing = VALID_CLIP2.replace(" in <Picture 1>, matching that still's face, hair, and wardrobe.", ".")
    issues = prompter.validate_clip_prompt(missing, inventory, 2)
    assert any("cite dump <Picture N>" in item for item in issues)
    empty = prompter.parse_builder_dump("H3 Studio Builder pack\nModel 1: style\n")
    assert prompter.validate_clip_prompt(missing, empty, 2) == []


def test_generate_clip_bodies_labels_and_repair(monkeypatch):
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    calls = {"n": 0}

    def chat(messages):
        calls["n"] += 1
        last = messages[-1]["content"]
        if "Repair" in last:
            return VALID_CLIP1
        if "clip 2" in last:
            return VALID_CLIP2
        return VALID_CLIP1.replace("non_diegetic_music: N/A", "")

    seen = []
    bodies, notes = prompter.generate_clip_bodies(
        inventory, "she walks", 2, 10.0, False, chat, progress=seen.append,
    )
    assert [item[0] for item in bodies] == ["**Clip 1 — Start**", "**Clip 2 — Finish**"]
    assert "non_diegetic_music:" in bodies[0][1]
    assert notes == []
    assert calls["n"] == 3
    assert any(item.startswith("Clip 1/2 (Start) — writing") for item in seen)
    assert any(item.startswith("Clip 1/2 (Start) — repairing") for item in seen)
    assert any(item.startswith("Clip 2/2 (Finish) — writing") for item in seen)
    document = prompter.assemble_auto_chain_document(
        10.0, 2, False,
        [(role, body, role == "Loop") for _heading, body, role in bodies],
    )
    assert document.startswith("H3 Studio prompt")
    assert "## Clip 1 — Start" in document
    assert "## Clip 2 — Finish" in document
    assert "<Picture 1> is the first frame of [Shot 1]" in document
    parsed = _load("prompt_document").parse_prompt_document(document)
    assert parsed["segments"] == 2
    clip2 = _load("prompt_document").expand_clip(parsed, 2)
    assert "<Picture 1> is the first frame" not in clip2
    assert "<Subject 2> is the night street" not in clip2
    turn = prompter._user_turn(inventory, "she walks", 2, "Finish", 10.0, "")
    assert "this clip's subject_definitions" in turn


def test_dump_from_pack_and_loop_label():
    prompter = _load("prompter_infinite")
    pack_mod = _load("pack")
    pack = {
        "models": [{"index": 1, "description": "base"}],
        "pictures": [{"index": 1, "description": "face", "first_frame": True}],
        "videos": [],
        "audios": [],
        "duration": 10.0,
        "segments": 2,
        "plan": "walk",
        "loop": True,
    }
    dump = prompter.dump_from_pack(pack)
    assert dump == pack_mod.format_builder_dump(
        pack["models"], pack["pictures"], pack["videos"], pack["audios"],
        plan="walk", duration=10.0, segments=2, loop=True,
    )
    assert "duration: 10.00s" in dump
    assert "segments: 2" in dump
    assert "loop: true" in dump
    assert "plan:\nwalk" in dump
    inventory = prompter.parse_builder_dump(dump)
    assert inventory["first_frame"] == 1
    assert inventory["duration"] == 10.0
    assert inventory["segments"] == 2
    assert inventory["loop"] is True
    assert inventory["plan"] == "walk"

    loop_inventory = prompter.parse_builder_dump(DUMP)

    def chat(messages):
        last = messages[-1]["content"]
        if "Loop clip" in last:
            return VALID_CLIP2
        return VALID_CLIP1

    bodies, notes = prompter.generate_clip_bodies(
        loop_inventory, "stay in place", 1, 10.0, True, chat,
    )
    assert [item[0] for item in bodies] == [
        "**Clip 1 — Start**",
        "**Loop — return to Clip 1**",
    ]
    assert notes == []


def test_missing_catalog_without_download_does_not_fetch(monkeypatch, tmp_path):
    llama = _load("prompter_llama")
    monkeypatch.setattr(llama, "llm_roots", lambda: [str(tmp_path)])
    monkeypatch.setattr(llama, "find_catalog_gguf", lambda: None)
    called = []
    monkeypatch.setattr(llama, "_download_catalog", lambda progress=None: called.append(True) or "nope")
    with pytest.raises(FileNotFoundError, match="allow_download"):
        llama.resolve_gguf(llama.CATALOG_LABEL, allow_download=False)
    assert called == []


def test_init_mapping_and_docs():
    init = (ROOT / "__init__.py").read_text(encoding="utf-8")
    node = (ROOT / "prompter_infinite.py").read_text(encoding="utf-8")
    llama = (ROOT / "prompter_llama.py").read_text(encoding="utf-8")
    js = (ROOT / "web" / "js" / "prompterInfinite.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    system = (ROOT / "prompts" / "infinite_system.txt").read_text(encoding="utf-8")
    assert "H3StudioLocalInfinitePrompter" in init
    assert "H3 Studio - Local Prompter" in init
    assert "Local Infinite Prompter" not in init
    assert "RETURN_TYPES = (\"STRING\", \"INT\", \"STRING\")" in node
    assert "allow_download" in node
    assert "127.0.0.1" in llama
    assert "hf_hub_download" in llama
    assert "/h3_studio_prompter/models" in llama
    assert "Loading GGUF into llama-server" in llama
    assert " — writing" in node
    assert "H3StudioLocalInfinitePrompter" in js
    assert "Local Prompter" in readme
    assert "Local Infinite Prompter" not in readme
    assert "llama-server" in readme
    assert "allow_download" in readme
    assert "ComfyUI/user/llama.cpp/" in readme
    assert "ggml-org/llama.cpp" in readme
    assert "prompt_1" not in readme
    assert "H3 Studio prompt" in readme
    assert "assemble_auto_chain_document" in node
    assert '"pack": ("H3_STUDIO_PACK"' in node
    assert '"dump": ("STRING"' not in node
    assert '"plan": ("STRING"' not in node
    assert '"segments": ("INT"' not in node
    assert '"duration": ("FLOAT"' not in node
    assert '"loop": ("BOOLEAN"' not in node
    assert "dump_from_pack" in node
    assert "duration_and_segments_from_pack_or_prompt" in node
    assert "subject_definitions" in system
    assert "Do not copy unused extra dump stills" in system
    assert "at 0.00 seconds" in system
    assert "first frame of [Shot 1]" in system


def test_music_video_pack_inputs_and_locked_d():
    prompter = _load("prompter_infinite")

    class FakeWav:
        shape = (1, 1, 48000)

    song = {"waveform": FakeWav(), "sample_rate": 16000}
    timed = "[00:01.000-00:03.000] hello world\n"
    assert prompter.music_video_pack_inputs({}) is None
    assert prompter.music_video_pack_inputs({"lyrics": ""}) is None
    with pytest.raises(ValueError, match="need a song"):
        prompter.music_video_pack_inputs({"lyrics": timed})
    with pytest.raises(ValueError, match="missing lyrics"):
        prompter.music_video_pack_inputs({"song": song, "lyrics": ""})
    with pytest.raises(ValueError, match="time lyrics"):
        prompter.music_video_pack_inputs({"song": song, "lyrics": "hello world"})
    got_song, got_lyrics = prompter.music_video_pack_inputs({"song": song, "lyrics": timed})
    assert got_song is song
    assert got_lyrics == timed.strip()
    assert abs(prompter.song_seconds_from_audio(song) - 3.0) < 1e-6
    tags = prompter.locked_d_tags(timed)
    assert tags == ["<d>[English] hello world</d>"]
    assert prompter.locked_d_tags("[00:01.000-00:02.000] <instrumental>\n") == []


def test_generate_music_video_bodies_locks_lyrics():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(
        "H3 Studio Builder pack\n"
        "duration: 10.00s\n"
        "Model 1: cinematic identity LoRA stack\n"
        "Picture 1: blonde woman, red jacket (first frame)\n"
    )
    lyrics = "[00:01.000-00:04.000] hello world"
    clip = {
        "index": 1,
        "time": (0.0, 9.125),
        "duration_seconds": 10.125,
        "slice": 0.0,
        "audio": (0.0, 10.125),
        "lyrics": lyrics,
        "instrumental": False,
    }
    captured = []

    def chat(messages):
        captured.append(messages[-1]["content"])
        last = messages[-1]["content"]
        if "Repair" in last:
            return MV_CLIP1
        return MV_CLIP1.replace("<d>[English] hello world</d>", "")

    bodies, notes = prompter.generate_music_video_bodies(
        inventory, "she sings", [clip], chat,
    )
    assert "lyrics:" in captured[0]
    assert "[00:01.000-00:04.000] hello world" in captured[0]
    assert "<d>[English] hello world</d>" in captured[0]
    assert "this clip's subject_definitions" in captured[0]
    assert notes == []
    assert bodies[0]["lyrics"] == lyrics
    document = _load("prompt_document").assemble_music_video_document(10.125, bodies)
    assert "mode: music_video" in document
    assert "lyrics:\n[00:01.000-00:04.000] hello world" in document
    assert "## Clip 1 — Start" in document
    assert "<d>[English] hello world</d>" in document
    mv_system = (ROOT / "prompts" / "music_video_system.txt").read_text(encoding="utf-8")
    assert "source-song slice" in mv_system
    node = (ROOT / "prompter_infinite.py").read_text(encoding="utf-8")
    assert "assemble_music_video_document" in node
    assert "refine_confirm_lyrics" in node


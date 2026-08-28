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
    assert "Expand this clip's share of the plan" in turn


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
    assert "H3StudioClipPromptFixer" in init
    assert "H3 Studio - Clip Prompt Fixer" in init
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
    assert "Clip Prompt Fixer" in readme
    assert "/prompt-minimax-h3-clip-fix" in readme
    assert "Copy skill command" in readme
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
    assert "## Expand the plan" in system
    assert "visible physics" in system
    assert "Do not invent a walking-morph, reality-bend, or footsteps story" not in system


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
    assert "slice: 0.000" in captured[0]
    assert "Shot clocks are clip-relative" in captured[0]
    assert notes == []
    assert bodies[0]["lyrics"] == lyrics
    document = _load("prompt_document").assemble_music_video_document(10.125, bodies)
    assert "mode: music_video" in document
    assert "lyrics:\n[00:01.000-00:04.000] hello world" in document
    assert "## Clip 1 — Start" in document
    assert "<d>[English] hello world</d>" in document
    mv_system = (ROOT / "prompts" / "music_video_system.txt").read_text(encoding="utf-8")
    assert "source-song slice" in mv_system
    assert "## Expand the plan" in mv_system
    assert "the camera cuts" in mv_system
    assert "Do not invent a walking-morph, reality-bend, or footsteps story" not in mv_system
    node = (ROOT / "prompter_infinite.py").read_text(encoding="utf-8")
    assert "assemble_music_video_document" in node
    assert "refine_confirm_lyrics" in node


MV_CLIP2 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Audio 1> is the source-song slice covering 8.208–18.333 of the master.

summary:
[video continuation + reference generation] REWRITTEN clip two.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same red jacket.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] second line</d>.

overall_soundscape: city night

non_diegetic_music: N/A
"""

SEED_BODY_1 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Picture 1> is the first frame of [Shot 1], showing a blonde woman in a red jacket.
<Audio 1> is the source-song slice covering 0.000–10.125 of the master.

summary:
[keyframe completion + reference generation] Seed clip one.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same face and red jacket.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] hello world</d>.

overall_soundscape: city night

non_diegetic_music: N/A
"""

SEED_BODY_2 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Audio 1> is the source-song slice covering 8.208–18.333 of the master.

summary:
[video continuation + reference generation] Seed clip two.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same red jacket.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] second line</d>.

overall_soundscape: city night

non_diegetic_music: N/A
"""

SEED_BODY_3 = """subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Audio 1> is the source-song slice covering 16.416–26.541 of the master.

summary:
[video continuation + reference generation] Seed clip three.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same red jacket.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] third line</d>.

overall_soundscape: city night

non_diegetic_music: N/A
"""


def _mv_clip(index, t0, t1, slice_s, a0, a1, lyrics, prompt):
    return {
        "index": index,
        "time": (t0, t1),
        "duration_seconds": 10.125,
        "slice": slice_s,
        "audio": (a0, a1),
        "lyrics": lyrics,
        "instrumental": False,
        "prompt": prompt,
    }


def test_clip_fix_rewrites_selected_indices_only():
    prompter = _load("prompter_infinite")
    docs = _load("prompt_document")
    inventory = prompter.parse_builder_dump(
        "H3 Studio Builder pack\n"
        "duration: 10.00s\n"
        "Model 1: cinematic identity LoRA stack\n"
        "Picture 1: blonde woman, red jacket (first frame)\n"
    )
    clips = [
        _mv_clip(1, 0.0, 9.125, 0.0, 0.0, 10.125, "[00:01.000-00:04.000] hello world", SEED_BODY_1),
        _mv_clip(2, 9.125, 18.25, 8.208, 8.208, 18.333, "[00:12.000-00:14.000] second line", SEED_BODY_2),
        _mv_clip(3, 18.25, 27.375, 16.416, 16.416, 26.541, "[00:22.000-00:24.000] third line", SEED_BODY_3),
    ]
    captured = []

    def chat(messages):
        captured.append(messages[-1]["content"])
        return MV_CLIP2

    bodies, notes = prompter.generate_music_video_bodies(
        inventory, "make clip 2 darker", clips, chat, rewrite_indices=[2],
    )
    assert notes == []
    assert len(captured) == 1
    turn = captured[0]
    assert "Existing clip body to revise:" in turn
    assert "Seed clip two." in turn
    assert "Previous clip body:" in turn
    assert "Seed clip one." in turn
    assert "Following clip (do not rewrite; land so this body can continue):" in turn
    assert "Seed clip three." in turn
    assert "Apply the user plan as filmable beats" in turn
    assert bodies[0]["prompt"] == SEED_BODY_1
    assert bodies[2]["prompt"] == SEED_BODY_3
    assert "REWRITTEN clip two" in bodies[1]["prompt"]
    assert bodies[0]["lyrics"] == "[00:01.000-00:04.000] hello world"
    assert bodies[1]["lyrics"] == "[00:12.000-00:14.000] second line"
    assert bodies[1]["time"] == (9.125, 18.25)
    assert bodies[2]["time"] == (18.25, 27.375)
    document = docs.assemble_music_video_document(10.125, bodies)
    parsed = docs.parse_prompt_document(document, mode="music_video")
    assert parsed["clips"][0]["lyrics"] == clips[0]["lyrics"]
    assert parsed["clips"][1]["lyrics"] == clips[1]["lyrics"]
    assert parsed["clips"][2]["lyrics"] == clips[2]["lyrics"]
    assert "REWRITTEN clip two" in docs.clip_body(parsed["clips"][1])
    assert "Seed clip one." in docs.clip_body(parsed["clips"][0])
    selected = prompter.clip_fix_output_clips(bodies, [2])
    assert [int(c["index"]) for c in selected] == [2]
    out = docs.assemble_music_video_document(10.125, selected, header=False)
    assert out.startswith("## Clip 2 — Continue")
    assert "H3 Studio prompt" not in out
    assert "mode: music_video" not in out
    assert "segments:" not in out
    assert "## Clip 1 — Start" not in out
    assert "## Clip 3 — Continue" not in out
    assert "Seed clip one." not in out
    assert "Seed clip three." not in out
    ac_items = prompter.clip_fix_output_bodies(
        [{"index": 1}, {"index": 2}, {"index": 3}],
        [("**Clip 1 — Start**", "a", "Start"), ("**Clip 2 — Continue**", "b", "Continue"),
         ("**Clip 3 — Finish**", "c", "Finish")],
        [2],
    )
    ac_doc = docs.assemble_auto_chain_document(10.0, 1, False, ac_items, header=False)
    assert ac_doc.startswith("## Clip 2 — Continue")
    assert "H3 Studio prompt" not in ac_doc
    assert "mode: auto_chain" not in ac_doc
    assert "## Clip 1 — Start" not in ac_doc
    assert "## Clip 3 — Finish" not in ac_doc


def test_load_clip_fix_seed_skips_retiming():
    prompter = _load("prompter_infinite")
    fixer = _load("clip_prompt_fixer")
    seed = (
        "H3 Studio prompt\nmode: music_video\nduration: 10.125\nsegments: 2\n\n"
        "## Clip 1 — Start\n"
        "time: 0.000-9.125\nduration_seconds: 10.125\naudio: 0.000-10.125\n"
        "lyrics:\n[00:01.000-00:03.000] hello\n"
        "subject_definitions:\nx\nsummary:\none\nretention_analysis:\nx\n"
        "detailed_description:\nshot\noverall_soundscape:\na\nnon_diegetic_music:\nN/A\n\n"
        "## Clip 2 — Continue\n"
        "time: 9.125-18.250\nduration_seconds: 10.125\naudio: 8.208-18.333\n"
        "lyrics:\n[00:12.000-00:14.000] next\n"
        "subject_definitions:\nx\nsummary:\ntwo\nretention_analysis:\nx\n"
        "detailed_description:\nshot\noverall_soundscape:\na\nnon_diegetic_music:\nN/A\n"
    )
    pack = {
        "models": [{"index": 1, "description": "base", "model": "m"}],
        "prompt_mode": "clip_fix",
        "seed_prompt": seed,
        "fix_clips": [2],
        "plan": "darker",
        "song": {"waveform": object(), "sample_rate": 16000},
        "lyrics": "[00:01.000-00:03.000] hello",
    }
    through = _load("pack").require_pack(pack)
    loaded = prompter.load_clip_fix_seed(through)
    assert loaded["song_audio"] is True
    assert loaded["rewrite"] == [2]
    assert [int(c["index"]) for c in loaded["items"]] == [1, 2]
    assert loaded["items"][0]["lyrics"] == "[00:01.000-00:03.000] hello"
    assert "one" in loaded["items"][0]["prompt"]
    node = (ROOT / "prompter_infinite.py").read_text(encoding="utf-8")
    assert 'str(pack.get("prompt_mode") or "") == "clip_fix"' in node
    assert "load_clip_fix_seed" in node
    js = (ROOT / "web" / "js" / "clipPromptFixer.js").read_text(encoding="utf-8")
    assert "H3StudioClipPromptFixer" in js
    assert "Copy skill command" in js
    assert "/prompt-minimax-h3-clip-fix" in js
    assert fixer.PROMPT_MODE_CLIP_FIX == "clip_fix"


def test_is_changed_includes_clip_fix_fields():
    prompter = _load("prompter_infinite")
    base = {
        "models": [{"index": 1, "description": "base"}],
        "pictures": [],
        "videos": [],
        "audios": [],
        "plan": "walk",
    }
    a = prompter.H3StudioLocalInfinitePrompter.IS_CHANGED(pack=base)
    b = prompter.H3StudioLocalInfinitePrompter.IS_CHANGED(pack={
        **base,
        "prompt_mode": "clip_fix",
        "seed_prompt": "## Clip 2",
        "fix_clips": [2],
    })
    c = prompter.H3StudioLocalInfinitePrompter.IS_CHANGED(pack={
        **base,
        "prompt_mode": "clip_fix",
        "seed_prompt": "## Clip 2 changed",
        "fix_clips": [2],
    })
    assert a != b
    assert b != c


def test_generate_clip_bodies_rewrite_keeps_neighbors():
    prompter = _load("prompter_infinite")
    inventory = prompter.parse_builder_dump(DUMP)
    seed_clips = [
        {"index": 1, "role": "Start", "prompt": VALID_CLIP1, "is_loop": False},
        {"index": 2, "role": "Finish", "prompt": VALID_CLIP2, "is_loop": False},
    ]
    captured = []

    def chat(messages):
        captured.append(messages[-1]["content"])
        return VALID_CLIP1.replace("starts walking", "REWRITTEN start")

    bodies, notes = prompter.generate_clip_bodies(
        inventory, "darker start", 2, 10.0, False, chat,
        seed_clips=seed_clips, rewrite_indices=[1],
    )
    assert notes == []
    assert len(captured) == 1
    assert "Existing clip body to revise:" in captured[0]
    assert "starts walking" in captured[0]
    assert "Following clip (do not rewrite; land so this body can continue):" in captured[0]
    assert "keeps walking" in captured[0]
    assert "REWRITTEN start" in bodies[0][1]
    assert bodies[1][1] == VALID_CLIP2
    assert bodies[1][0] == "**Clip 2 — Finish**"


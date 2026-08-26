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
    assert inventory["first_frame"] == 1
    assert [item["index"] for item in inventory["pictures"]] == [1, 2]
    assert inventory["pictures"][0]["first_frame"] is True
    assert inventory["pictures"][0]["description"] == "blonde woman, red jacket"
    assert inventory["videos"][0]["index"] == 1
    assert inventory["audios"][0]["index"] == 1
    assert inventory["models"][0]["index"] == 1
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

    bodies, notes = prompter.generate_clip_bodies(
        inventory, "she walks", 2, 10.0, False, chat,
    )
    assert [item[0] for item in bodies] == ["**Clip 1 — Start**", "**Clip 2 — Finish**"]
    assert "non_diegetic_music:" in bodies[0][1]
    assert notes == []
    assert calls["n"] == 3
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
    assert "<Picture 1> is the first frame" not in _load("prompt_document").expand_clip(parsed, 2)


def test_dump_from_pack_and_loop_label():
    prompter = _load("prompter_infinite")
    pack_mod = _load("pack")
    pack = {
        "models": [{"index": 1, "description": "base"}],
        "pictures": [{"index": 1, "description": "face", "first_frame": True}],
        "videos": [],
        "audios": [],
    }
    dump = prompter._dump_text("", pack)
    assert dump == pack_mod.format_builder_dump(
        pack["models"], pack["pictures"], pack["videos"], pack["audios"],
    )
    inventory = prompter.parse_builder_dump(dump)
    assert inventory["first_frame"] == 1

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
    assert "H3 Studio - Local Infinite Prompter" in init
    assert "RETURN_TYPES = (\"STRING\", \"INT\", \"STRING\")" in node
    assert "allow_download" in node
    assert "127.0.0.1" in llama
    assert "hf_hub_download" in llama
    assert "/h3_studio_prompter/models" in llama
    assert "H3StudioLocalInfinitePrompter" in js
    assert "Local Infinite Prompter" in readme
    assert "llama-server" in readme
    assert "allow_download" in readme
    assert "ComfyUI/user/llama.cpp/" in readme
    assert "ggml-org/llama.cpp" in readme
    assert "prompt_1" not in readme
    assert "H3 Studio prompt" in readme
    assert "assemble_auto_chain_document" in node
    assert "subject_definitions" in system
    assert "at 0.00 seconds" in system
    assert "first frame of [Shot 1]" in system

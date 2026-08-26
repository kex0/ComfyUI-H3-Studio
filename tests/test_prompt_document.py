import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt_document import (
    assemble_auto_chain_document,
    document_has_loop,
    duration_and_segments_from_pack_or_prompt,
    expand_clip,
    looks_like_unified,
    parse_prompt_document,
    resolve_auto_chain_prompts,
    rewrite_mentions,
)


DOC = """H3 Studio prompt
mode: auto_chain
duration: 10.00
segments: 2
loop: false

subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Picture 1> is the first frame of [Shot 1], showing a blonde woman in a red jacket.

## Clip 1 — Start
summary:
[keyframe completion + reference generation] She starts walking.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same face.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] She is already in the still's pose, then steps forward.

overall_soundscape: rain

non_diegetic_music: N/A

## Clip 2 — Finish
summary:
[video continuation + reference generation] She keeps walking.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - same jacket.

detailed_description:
The target video is live-action, cinematic, night street lighting.
[Shot 1] She is already mid-stride and keeps walking.

overall_soundscape: rain on pavement

non_diegetic_music: N/A
"""

MV = """H3 Studio prompt
mode: music_video
duration: 10.125
segments: 2

subject_definitions:
<Subject 1> is the singer.
<Audio 1> is the source-song slice covering 0.000–10.125 of the master, reused as the complete soundtrack.

## Clip 1 — Start
time: 0.000-9.125
duration_seconds: 10.125
slice: 0.000
audio: 0.000-10.125
lyrics:
[00:01.000-00:03.000] hello world
summary:
[reference generation + audio reuse] Opens singing.

retention_analysis:
<Audio 1>: fully_copy

detailed_description:
The target video is live-action, cinematic, music-video.
[Shot 1] She sings.

overall_soundscape: <Audio 1> reused as-is.

non_diegetic_music: N/A

## Clip 2 — Continue
time: 9.125-18.250
duration_seconds: 10.125
slice: 8.208
audio: 8.208-18.333
lyrics:
[00:12.000-00:14.000] second line
summary:
[video continuation + audio reuse] Continues singing.

retention_analysis:
<Audio 1>: fully_copy

detailed_description:
The target video is live-action, cinematic, music-video.
[Shot 1] She keeps singing.

overall_soundscape: <Audio 1> reused as-is.

non_diegetic_music: N/A
"""


def test_header_blank_lines_still_parse():
    spaced = DOC.replace("mode: auto_chain\nduration:", "mode: auto_chain\n\nduration:")
    parsed = parse_prompt_document(spaced)
    assert parsed["duration"] == 10.0
    assert parsed["segments"] == 2
    assert "<Subject 1>" in parsed["shared_subjects"]
    assert rewrite_mentions("use @Picture 2 and @audio 1") == "use <Picture 2> and <Audio 1>"


def test_parse_and_expand_shared_subjects():
    parsed = parse_prompt_document(DOC)
    assert parsed["mode"] == "auto_chain"
    assert parsed["segments"] == 2
    assert "<Picture 1> is the first frame" in parsed["shared_subjects"]
    start = expand_clip(parsed, 1)
    cont = expand_clip(parsed, 2)
    assert "<Picture 1> is the first frame of [Shot 1]" in start
    assert "<Picture 1> is the first frame of [Shot 1]" not in cont
    assert "<Subject 1> is the woman in <Picture 1>" in cont
    assert "She keeps walking" in cont


def test_resolve_unified_and_legacy():
    bodies, loop = resolve_auto_chain_prompts(DOC, segments=2)
    assert len(bodies) == 2
    assert loop == ""
    legacy, loop2 = resolve_auto_chain_prompts(
        "", segments=2, kwargs={"prompt_1": "a", "prompt_2": "b"},
    )
    assert legacy == ["a", "b"]
    assert loop2 == ""
    try:
        resolve_auto_chain_prompts(DOC, segments=3)
    except ValueError as exc:
        assert "segments=3" in str(exc)
    else:
        raise AssertionError("expected clip-count mismatch")


def test_assemble_roundtrip_and_loop():
    bodies = resolve_auto_chain_prompts(DOC, segments=2)[0]
    assembled = assemble_auto_chain_document(
        10.0, 2, True,
        [("Start", bodies[0], False), ("Finish", bodies[1], False), ("Loop", bodies[1], True)],
    )
    assert looks_like_unified(assembled)
    parsed = parse_prompt_document(assembled)
    assert parsed["loop"] is True
    assert any(clip.get("is_loop") for clip in parsed["clips"])
    loop_body = expand_clip(parsed, 2, is_loop=True)
    assert "<Picture 1> is the first frame of [Shot 1]" not in loop_body


def test_music_video_unified_audio_cover():
    from music_video_prompt import parse_music_video_prompt

    parsed = parse_music_video_prompt(MV)
    assert parsed["clip_count"] == 2
    assert parsed["clips"][0]["lyrics"] == "[00:01.000-00:03.000] hello world"
    assert parsed["clips"][1]["time"] == (9.125, 18.250)
    assert parsed["clips"][1]["audio"] == (8.208, 18.333)
    assert "covering 8.208–18.333" in parsed["clips"][1]["prompt"]
    assert "covering 0.000–10.125" in parsed["clips"][0]["prompt"]
    assert "<Subject 1> is the singer." in parsed["clips"][1]["prompt"]


def test_duration_and_segments_from_pack_or_prompt():
    duration, segments = duration_and_segments_from_pack_or_prompt(
        {"duration": 8.0, "segments": 4}, DOC, need_segments=True,
    )
    assert duration == 10.0
    assert segments == 2
    duration, segments = duration_and_segments_from_pack_or_prompt(
        {"duration": 8.0, "segments": 4}, "", need_segments=True,
    )
    assert duration == 8.0
    assert segments == 4
    duration, segments = duration_and_segments_from_pack_or_prompt(
        {"duration": 9.0}, MV, need_segments=False,
    )
    assert duration == 10.125
    assert segments is None
    try:
        duration_and_segments_from_pack_or_prompt({}, "", need_segments=True)
    except ValueError as exc:
        assert "duration is missing" in str(exc)
    else:
        raise AssertionError("expected missing duration to fail")


def test_document_has_loop_and_per_clip_resolve():
    assert document_has_loop(DOC) is False
    assert document_has_loop("not a prompt") is False
    looped = DOC.replace("loop: false", "loop: true") + "\n## Loop — return to Clip 1\nsummary:\nback\n"
    assert document_has_loop(looped) is True
    bodies, loop = resolve_auto_chain_prompts(
        "",
        segments=2,
        loop=True,
        loop_prompt="loop body",
        kwargs={"prompt_1": "clip one", "prompt_2": "clip two"},
    )
    assert bodies == ["clip one", "clip two"]
    assert loop == "loop body"

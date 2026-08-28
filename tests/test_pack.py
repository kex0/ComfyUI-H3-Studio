import importlib
import sys
import types
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


def _item(index, **extra):
    item = {
        "index": index,
        "description": extra.pop("description", f"d{index}"),
        "model": extra.pop("model", f"m{index}"),
        "image": extra.pop("image", f"p{index}"),
        "frames": extra.pop("frames", f"v{index}"),
        "audio": extra.pop("audio", None),
        "duration": extra.pop("duration", 0.0),
    }
    item.update(extra)
    return item


def _pack(**kwargs):
    return {
        "models": kwargs.get("models") or [_item(1, model="base")],
        "pictures": kwargs.get("pictures") or [],
        "videos": kwargs.get("videos") or [],
        "audios": kwargs.get("audios") or [],
    }


def test_parse_prompt_citations_tags_and_lines():
    pack = _load("pack")
    cites = pack.parse_prompt_citations(
        "<Picture 5> and <picture 2>\nVideo 1: walking\n<Model 2> <Audio 3>"
    )
    assert cites["pictures"] == [5, 2]
    assert cites["videos"] == [1]
    assert cites["audios"] == [3]
    assert cites["models"] == [2]


def test_require_pack_keeps_duration_and_segments():
    pack = _load("pack")
    got = pack.require_pack({
        "models": [_item(1, model="m")],
        "duration": 10.0,
        "segments": 3,
        "plan": "walk",
        "loop": True,
    })
    assert got["duration"] == 10.0
    assert got["segments"] == 3
    assert got["plan"] == "walk"
    assert got["loop"] is True
    assert got["lyrics"] == ""
    with_song = pack.require_pack({
        "models": [_item(1, model="m")],
        "song": {"waveform": "w", "sample_rate": 48000},
        "lyrics": "[00:00.000-00:02.000] hello",
    })
    assert with_song["song"]["sample_rate"] == 48000
    assert with_song["lyrics"] == "[00:00.000-00:02.000] hello"
    assert "pictures" in got
    assert "prompt_mode" not in got
    assert "seed_prompt" not in got
    assert "fix_clips" not in got


def test_require_pack_keeps_clip_fix_fields():
    pack = _load("pack")
    got = pack.require_pack({
        "models": [_item(1, model="m")],
        "plan": "builder plan",
        "prompt_mode": "clip_fix",
        "seed_prompt": "## Clip 11 — Continue\nsummary:\nfix\n",
        "fix_clips": [11, 12, 11],
        "noise": "drop me",
    })
    assert got["prompt_mode"] == "clip_fix"
    assert got["seed_prompt"].startswith("## Clip 11")
    assert got["fix_clips"] == [11, 12]
    assert got["plan"] == "builder plan"
    assert "noise" not in got


def test_assert_ref_caps_limits():
    pack = _load("pack")
    pics = [_item(i) for i in range(1, 10)]
    pack.assert_ref_caps(pics, [], [])
    with pytest.raises(ValueError, match="at most 9 images"):
        pack.assert_ref_caps(pics + [_item(10)], [], [])
    with pytest.raises(ValueError, match="at most 3 videos"):
        pack.assert_ref_caps([], [_item(i, duration=2.0) for i in range(1, 5)], [])
    with pytest.raises(ValueError, match="at most 3 audio"):
        pack.assert_ref_caps([], [], [_item(i, duration=2.0) for i in range(1, 5)])
    with pytest.raises(ValueError, match="mixed reference files"):
        pack.assert_ref_caps(
            [_item(i) for i in range(1, 10)],
            [_item(1, duration=2.0), _item(2, duration=2.0), _item(3, duration=2.0)],
            [_item(1, duration=2.0)],
        )
    with pytest.raises(ValueError, match="each video"):
        pack.assert_ref_caps([], [_item(1, duration=1.0)], [])
    with pytest.raises(ValueError, match="total video duration"):
        pack.assert_ref_caps(
            [],
            [_item(1, duration=8.0), _item(2, duration=8.0)],
            [],
        )


def test_select_default_fills_in_order_under_caps():
    pack = _load("pack")
    pics = [_item(i, image=f"p{i}") for i in range(1, 12)]
    vids = [_item(i, duration=2.0, frames=f"v{i}") for i in range(1, 4)]
    auds = [_item(i, duration=2.0, audio=f"a{i}") for i in range(1, 4)]
    out_p, out_v, out_a = pack.select_default(pics, vids, auds)
    assert [item["index"] for item in out_p] == list(range(1, 10))
    assert [item["index"] for item in out_v] == [1, 2, 3]
    assert out_a == []
    out_p, out_v, out_a = pack.select_default(pics[:2], vids[:1], auds, extra_audio=1)
    assert [item["index"] for item in out_p] == [1, 2]
    assert [item["index"] for item in out_v] == [1]
    assert [item["index"] for item in out_a] == [1, 2]


def test_resolve_default_model_and_strip_model_tag():
    pack = _load("pack")
    result = pack.resolve_pack_for_clip(
        _pack(models=[_item(1, model="m1"), _item(2, model="m2")]),
        "hello <Model 2> world",
    )
    assert result["model"] == "m2"
    assert "<Model" not in result["prompt"]
    missing = pack.resolve_pack_for_clip(
        _pack(models=[_item(1, model="m1")]),
        "no model tag",
    )
    assert missing["model"] == "m1"
    with pytest.raises(ValueError, match="Model 3"):
        pack.resolve_pack_for_clip(_pack(), "<Model 3>")


def test_resolve_remaps_cited_pictures_to_contiguous_ordinals():
    pack = _load("pack")
    pictures = [_item(i, image=f"p{i}") for i in range(1, 6)]
    result = pack.resolve_pack_for_clip(
        _pack(pictures=pictures),
        "use <Picture 5> then <Picture 2>",
    )
    assert result["pictures"] == ["p2", "p5"]
    assert result["prompt"] == "use <Picture 2> then <Picture 1>"


def test_resolve_music_video_song_occupies_audio_1():
    pack = _load("pack")
    audios = [_item(1, audio="rain", duration=3.0), _item(2, audio="crowd", duration=3.0)]
    result = pack.resolve_pack_for_clip(
        _pack(audios=audios, pictures=[_item(1, image="face")]),
        "<Audio 1> fully_copy. Also <Audio 2> rain.",
        song_audio=True,
    )
    assert result["audios"] == ["rain"]
    assert "<Audio 1>" in result["prompt"]
    assert "<Audio 2>" in result["prompt"]
    defaulted = pack.resolve_pack_for_clip(
        _pack(audios=audios, pictures=[_item(1, image="face")]),
        "<Audio 1>: fully_copy. No builder audio tags.",
        song_audio=True,
    )
    assert defaulted["pictures"] == ["face"]
    assert defaulted["audios"] == ["rain", "crowd"]


def test_resolve_video_soundtrack_shifts_standalone_audio_labels():
    pack = _load("pack")
    videos = [_item(1, frames="walk", duration=4.0, audio="bed")]
    audios = [_item(1, audio="rain", duration=3.0)]
    result = pack.resolve_pack_for_clip(
        _pack(videos=videos, audios=audios),
        "keep <Video 1> and <Audio 1>",
        song_audio=False,
    )
    assert result["videos"] == ["walk"]
    assert result["video_audios"] == ["bed"]
    assert result["audios"] == ["rain"]
    assert "<Video 1>" in result["prompt"]
    assert "<Audio 2>" in result["prompt"]


def test_resolve_video_segment_suffix_picks_region_and_strips_tag():
    pack = _load("pack")
    videos = [_item(
        1, frames="full", duration=4.0, audio="full-a",
        regions=[
            {"frames": "a", "duration": 4.0, "audio": "aa"},
            {"frames": "b", "duration": 4.0, "audio": "bb"},
        ],
    )]
    result = pack.resolve_pack_for_clip(
        _pack(videos=videos),
        "use <Video 1:2> here",
    )
    assert result["videos"] == ["b"]
    assert result["video_audios"] == ["bb"]
    assert result["prompt"] == "use <Video 1> here"
    cites = pack.parse_prompt_citations("<Video 1:2> and <Audio 1:3>")
    assert cites["videos"] == [1]
    assert cites["video_picks"] == [(1, 2)]
    assert cites["audio_picks"] == [(1, 3)]


def test_format_builder_dump_enabled_labels():
    pack = _load("pack")
    dump = pack.format_builder_dump(
        [_item(1, description="cinematic identity LoRA stack")],
        [_item(1, description="blonde woman, red jacket", first_frame=True)],
        [_item(1, description="walking cycle", duration=4.2, audio="sfx")],
        [_item(1, description="rain bed", duration=3.1)],
    )
    assert dump.startswith("H3 Studio Builder pack\n")
    assert "Model 1: cinematic identity LoRA stack" in dump
    assert "Picture 1: blonde woman, red jacket (first frame)" in dump
    assert "Video 1: 4.2s walking cycle (with soundtrack)" in dump
    assert "Audio 1: 3.1s rain bed" in dump
    assert "plan:" not in dump
    planned = pack.format_builder_dump(
        [_item(1, description="cinematic identity LoRA stack")],
        [_item(1, description="blonde woman, red jacket", first_frame=True)],
        [],
        [],
        plan="two women talk in a kitchen",
    )
    assert "plan:\ntwo women talk in a kitchen" in planned
    timed = pack.format_builder_dump(
        [_item(1, description="cinematic identity LoRA stack")],
        [],
        [],
        [],
        plan="stay in place",
        duration=10.0,
        segments=1,
        loop=True,
    )
    assert "duration: 10.00s" in timed
    assert "segments: 1" in timed
    assert "loop: true" in timed
    builder = (ROOT / "builder.py").read_text(encoding="utf-8")
    assert '"plan": str(state.get("plan")' in builder
    assert '"duration": duration' in builder
    assert '"segments": clamp_segments(segments)' in builder
    assert '"loop": bool(loop)' in builder
    builder_js = (ROOT / "web" / "js" / "builder.js").read_text(encoding="utf-8")
    assert 'data-act="plan"' in builder_js
    assert "h3-builder-plan-host" in builder_js
    assert "h3-builder-split" in builder_js
    assert "h3-builder-split-handle" in builder_js
    assert "h3-builder-footer" in builder_js
    assert "visualNodeHeight" in builder_js
    assert "remainingBuilderHeight" in builder_js
    assert "bindBuilderWidgetSize" in builder_js
    assert "computeLayoutSize" in builder_js
    assert "minHeight: MIN_WIDGET_HEIGHT" in builder_js
    assert "getHeight: () => \"100%\"" in builder_js
    assert "h3_studio_builder_split" in builder_js
    assert 'data-act="split"' in builder_js
    assert "mountPromptEditor" in builder_js
    assert "attachPlanEditor" in builder_js
    assert "plan:" in builder_js
    assert "builderLoop" in builder_js
    assert "loop: true" in builder_js
    assert 'setWidgetVisible(findWidget(node, "loop"), !music)' in builder_js
    assert "function detachModeInput(node, name)" in builder_js
    assert '"loop": ("BOOLEAN"' in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert '"max_clip_duration": ("FLOAT"' in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert '"song": ("AUDIO"' in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert '"song_file": ("STRING"' in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert '"hidden": True' in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert '"lyrics": ("STRING"' in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert "builder_song_choices" not in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert "audio_upload" not in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert "resolve_builder_song" in (ROOT / "builder.py").read_text(encoding="utf-8")
    assert "ensureSongDropWidget" in builder_js
    assert "ensureLyricsSocket" in builder_js
    assert 'addDOMWidget("song"' in builder_js
    assert "Drop song or click to upload" in builder_js
    assert "setWidgetVisible(lyricsWidget, music)" in builder_js
    assert "LYRICS_MAX_HEIGHT = 200" in builder_js
    assert "function capLyricsWidget" in builder_js
    assert "capLyricsWidget(lyricsWidget)" in builder_js
    assert "max-height: ${LYRICS_MAX_HEIGHT}px !important" in builder_js
    assert "SERIAL_WIDGETS" in builder_js
    assert '"max_clip_duration", "segments", "loop", "song_file", "lyrics"' in builder_js
    assert "function decodeWidgetsValues(values)" in builder_js
    assert "function applyNamedWidgetValues(node, values)" in builder_js
    assert "node.widgets_values = SERIAL_WIDGETS.map" in builder_js
    assert "placeWidgetBefore" not in builder_js
    assert "orderTimingWidgets" not in builder_js
    assert "hideOnConnect: false" in builder_js
    assert "hideOnConnect: true" not in builder_js
    assert 'setWidgetOption(widget, "hideOnConnect", false)' in builder_js
    assert "function setWidgetOption(widget, key, value)" in builder_js
    assert "widget._state?.options" in builder_js
    assert "node._widgetSlotsDirty = true" in builder_js
    assert "function syncModeSlots(node)" in builder_js
    assert "function detachModeInput(node, name)" in builder_js
    assert "function attachModeInput(node, name, type, index)" in builder_js
    assert 'attachModeInput(node, "song", "AUDIO", at)' in builder_js
    assert 'attachModeInput(node, "lyrics", "STRING", at + 1)' in builder_js
    assert "function dropTargetZone(node, event)" in builder_js
    assert "function takeFileDrop(node)" in builder_js
    assert "function orderSongBeforeLyrics(node)" in builder_js
    assert 'if (zone === "song"' in builder_js
    assert 'if (zone === "list")' in builder_js
    assert "ui.addFiles = addFiles" in builder_js
    assert "if (music && isAudioFile(file))" not in builder_js
    assert "h3-builder-song-name" in builder_js
    assert "h3-builder-song-value" in builder_js
    assert "applyNativeWidgetTheme" in builder_js
    assert 'detachModeInput(node, "song")' in builder_js
    assert 'detachModeInput(node, "lyrics")' in builder_js
    assert 'setWidgetOption(widget, "socketless", true)' in builder_js
    assert "originalOnConnectInput" in builder_js
    assert 'input.widget = { name: "lyrics" }' not in builder_js
    assert "if (!input.widget) input.widget = widget" in builder_js
    assert 'addEventListener("pointerdown"' in builder_js
    assert "keepDomVisibleWhenWired" in builder_js
    assert "widget.__h3KeepDomVisible" in builder_js
    assert "installSongDrop" in builder_js
    assert "setSongFromFile" in builder_js
    loader = (ROOT / "song_loader.py").read_text(encoding="utf-8")
    assert 'RETURN_NAMES = ("song", "lyrics")' in loader
    assert 'RETURN_TYPES = ("AUDIO", "STRING")' in loader
    assert 'RETURN_NAMES = ("audio", "lyrics", "duration")' not in loader


def test_resolve_builder_song_prefers_wired_audio():
    builder = (ROOT / "builder.py").read_text(encoding="utf-8")
    assert "def resolve_builder_song(song, song_file):" in builder
    assert 'isinstance(song, dict) and song.get("waveform") is not None' in builder
    assert 'raise ValueError(f"h3_studio: invalid song file: {name}")' in builder
    assert "load_song_audio(folder_paths.get_annotated_filepath(name))" in builder


def test_pack_first_frame_uses_marked_picture():
    pack = _load("pack")
    assert pack.pack_first_frame(None) is None
    assert pack.pack_first_frame(_pack(pictures=[_item(1, image="face")])) is None
    assert pack.pack_first_frame(_pack(pictures=[
        _item(1, image="face"),
        _item(2, image="still", first_frame=True),
    ])) == "still"


def test_resolve_sole_first_frame_flag():
    pack = _load("pack")
    still = object()
    other = object()
    marked = pack.resolve_pack_for_clip(
        _pack(pictures=[
            _item(1, image=still, first_frame=True),
            _item(2, image=other),
        ]),
        "open on <Picture 1>",
    )
    assert marked["sole_first_frame"] is True
    assert marked["pictures"] == [still]
    both = pack.resolve_pack_for_clip(
        _pack(pictures=[
            _item(1, image=still, first_frame=True),
            _item(2, image=other),
        ]),
        "<Picture 1> and <Picture 2>",
    )
    assert both["sole_first_frame"] is False
    unmarked = pack.resolve_pack_for_clip(
        _pack(pictures=[_item(1, image=still)]),
        "<Picture 1>",
    )
    assert unmarked["sole_first_frame"] is False


def test_start_uses_official_qwen_when_sole_picture_is_first_frame():
    text = (ROOT / "nodes.py").read_text(encoding="utf-8")
    assert "def _sole_picture_is_first_frame(first_frame, pics):" in text
    assert "sole_first = _sole_picture_is_first_frame(first_frame, pics)" in text
    assert 'if first is not None and not pics:' in text
    assert "tokenize(prompt, images=images)" in text
    assert "Qwen=official Image-to-Video" in text
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    assert "def _start_reference_images" in auto_chain
    assert 'resolved.get("sole_first_frame")' in auto_chain
    assert "_start_reference_images(resolved)" in auto_chain
    assert '"sole_first_frame"' in (ROOT / "pack.py").read_text(encoding="utf-8")


def test_advanced_nodes_use_pack_not_model_or_picture_sockets():
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music_video = (ROOT / "music_video.py").read_text(encoding="utf-8")
    init = (ROOT / "__init__.py").read_text(encoding="utf-8")
    builder = (ROOT / "builder.py").read_text(encoding="utf-8")
    builder_js = (ROOT / "web" / "js" / "builder.js").read_text(encoding="utf-8")
    assert "H3StudioAutoChainAdvanced" not in auto_chain
    assert "H3StudioMusicVideoAdvanced" not in music_video
    assert '"pack": ("H3_STUDIO_PACK"' in auto_chain
    assert 'required.pop("duration"' in auto_chain
    assert 'required.pop("segments"' in auto_chain
    assert 'required.pop("loop_prompt"' in auto_chain
    assert 'str(name).startswith("prompt_")' in auto_chain
    assert "prompt_mode" in auto_chain
    assert 'optional["prompt_mode"]' in auto_chain
    assert "document_has_loop" in auto_chain
    assert "duration_and_segments_from_pack_or_prompt" in auto_chain
    assert '"pack": ("H3_STUDIO_PACK"' in music_video
    assert '"song": ("AUDIO"' not in music_video
    assert 'required.pop("duration"' in music_video
    assert "duration_and_segments_from_pack_or_prompt" in music_video
    assert "prompt_mode" in music_video
    assert 'optional["prompt_mode"]' in music_video
    assert "H3StudioAutoChainAdvanced" not in init
    assert "H3 Studio - Auto Chain Advanced" not in init
    assert "H3StudioMusicVideoAdvanced" not in init
    assert "H3 Studio - Music Video Advanced" not in init
    assert '"H3StudioAutoChain": H3StudioAutoChain' in init
    assert '"H3StudioMusicVideo": H3StudioMusicVideo' in init
    assert "H3StudioBuilder" in init
    assert "H3 Studio - Builder" in init
    assert 'RETURN_TYPES = ("H3_STUDIO_PACK",)' in builder
    assert 'RETURN_NAMES = ("pack",)' in builder
    assert 'RETURN_NAMES = ("pack", "max_clip_duration")' not in builder
    assert '"model_1"' in builder
    assert "model_{i}" in builder
    assert "MAX_MODELS" in builder
    assert "MODE_MUSIC_VIDEO" in builder
    assert "skip_audio" in builder
    assert '"display": "number"' in builder
    assert "/h3_studio_builder/file" in builder
    assert "Copy skill command" in builder_js
    assert "COPY_SKILL_TIP" in builder_js
    assert "Copy pack summary" not in builder_js
    assert "copy-info" not in builder_js
    assert "include_skill" not in builder_js
    assert "h3-builder-switch" not in builder_js
    assert "/prompt-minimax-h3-auto_chain" in builder_js
    assert "/prompt-minimax-h3-infinite" not in builder_js
    assert "/prompt-minimax-h3-music-video" in builder_js
    assert "skillSlash" in builder_js
    assert "/h3_studio_song/path" in builder_js
    assert "lines.push(\"lyrics:\")" in builder_js
    assert "lines.push(`song: ${songPath}`)" in builder_js
    assert "lines.push(`comfy: ${origin}`)" in builder_js
    assert "window.location?.origin" in builder_js
    assert "function lyricsSocketLinked" in builder_js
    assert builder_js.count("function lyricsSocketLinked") == 1
    assert "H3StudioBuilder" in builder_js
    assert "model_${i}" in builder_js
    assert "getMinHeight" in builder_js
    assert "MIN_WIDGET_HEIGHT" in builder_js
    assert "h3-builder-drop-target" in builder_js
    assert "h3-builder-grip" in builder_js
    assert "h3-builder-copied" in builder_js
    assert 'copyBtn.textContent = "Copied"' in builder_js
    assert "Open image preview" in builder_js
    assert "Copy image path" in builder_js
    assert "Copy image file" in builder_js
    assert "Copy video file" in builder_js
    assert "Copy audio file" in builder_js
    assert "copyMediaFile" in builder_js
    assert "Clear reference" in builder_js
    assert "h3-builder-menu" in builder_js
    assert "h3-builder-mode" in builder_js
    assert "MUSIC_VIDEO_SONG_TIP" in builder_js
    assert "unusedTitle" in builder_js
    assert "openCropEditor" in builder_js
    assert "openRegionEditor" in builder_js
    assert "Shift + drag moves all segments at once." in builder_js
    assert "h3-builder-editor-tip" in builder_js
    assert 'data-act="segments"' in builder_js
    assert "SEGMENTS_SLIDER_MAX = 10" in builder_js
    assert "function setSegmentsFields" in builder_js
    assert 'data-act="duration-num"' in builder_js
    assert 'data-act="segments-num"' in builder_js
    assert 'type="number"' in builder_js
    assert "viewSpan" in builder_js
    assert "viewWindow" in builder_js
    assert 'addEventListener("wheel"' in builder_js
    assert "adjacentRegions" in builder_js
    assert "move-all" in builder_js
    assert "item.regions" in builder_js
    assert "h3-region-index" in builder_js
    assert 'data-act="preview"' in builder_js
    assert 'data-act="edit"' in builder_js
    assert 'data-act="delete"' in builder_js
    assert 'data-act="enable"' in builder_js
    assert 'data-act="first-frame"' in builder_js
    assert "h3-builder-first-frame" in builder_js
    assert "First image" in builder_js
    assert " (first frame)" in builder_js
    assert "iconEye" in builder_js
    assert ">✂<" in builder_js
    assert "iconScissors" not in builder_js
    assert "loadAudioPeaks" in builder_js
    assert "thumbMarkup" in builder_js
    assert "applyCropThumb" in builder_js
    assert "kindIconSvg" in builder_js
    assert "./thumbs.js" in builder_js
    assert "h3-studio-builder-changed" in builder_js
    thumbs_js = (ROOT / "web" / "js" / "thumbs.js").read_text(encoding="utf-8")
    assert "function kindIconSvg" in thumbs_js
    assert 'key === "video"' in thumbs_js
    assert 'key === "audio"' in thumbs_js
    assert 'key === "model"' in thumbs_js
    assert "function applyCropThumb" in thumbs_js
    assert "function openPreview" in thumbs_js
    assert "function previewWindow" in thumbs_js
    assert "opts.segment" in thumbs_js
    assert "#t=" in thumbs_js
    assert "function viewUrl" in thumbs_js
    assert "h3_studio_builder/file" in thumbs_js
    assert "(cropX + cropW / 2)" in thumbs_js
    assert 'width="16"' in thumbs_js
    assert "stroke-linecap" in thumbs_js
    assert "M6.3 12.5" not in thumbs_js
    assert 'kindIconSvg("audio")' in builder_js
    assert "kindIconSvg(item.kind)" in builder_js
    assert "./nodeSize.js" in builder_js
    assert "captureNodeSize" in builder_js
    assert "restoreNodeSizeSoon" in builder_js
    assert "M6.3 12.5" not in builder_js
    assert "bindMediaReorder" in builder_js
    assert "h3-builder-thumb" in builder_js
    assert "viewUrl" in builder_js
    assert "openPreview" in builder_js
    assert "mode: ${" not in builder_js
    assert "drawChainIcon" not in builder_js
    assert "setSize([Math.max(currentWidth, computed[0]), computed[1]])" not in builder_js
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    assert "reference_videos=None" in nodes
    assert "reference_audios=None" in nodes
    assert "_ref2va_video_items_and_blocks" in nodes
    assert "max(1, int(FPS) // 2)" in nodes
    assert "kind\": \"video_audio\"" in nodes or '"kind": "video_audio"' in nodes
    js_seg = (ROOT / "web" / "js" / "autoChainSegmentVisibility.js").read_text(encoding="utf-8")
    assert "H3StudioAutoChain" in js_seg
    assert "H3StudioAutoChainAdvanced" not in js_seg
    assert "hideLegacyPromptWidgets" in js_seg
    assert "stripLegacyModelSockets" in js_seg
    assert "./nodeSize.js" not in js_seg
    assert "node.setSize([" not in js_seg
    js_ref = (ROOT / "web" / "js" / "musicVideoRefImages.js").read_text(encoding="utf-8")
    assert "H3StudioAutoChainAdvanced" not in js_ref
    assert "H3StudioMusicVideoAdvanced" not in js_ref


def test_builder_mode_and_media_helpers():
    builder_src = (ROOT / "builder.py").read_text(encoding="utf-8")
    ns = {}
    exec(
        "MODE_AUTO_CHAIN = 'auto_chain'\n"
        "MODE_MUSIC_VIDEO = 'music_video'\n"
        "MIN_DURATION = 5.0\n"
        "MAX_DURATION = 15.0\n"
        "MIN_CLIP_SEC = 2.0\n"
        "MAX_CLIP_SEC = 15.0\n"
        "MAX_SEGMENTS = 999\n"
        "def normalize_mode"
        + builder_src.split("def normalize_mode", 1)[1].split("def file_properties", 1)[0],
        ns,
        ns,
    )
    normalize_mode = ns["normalize_mode"]
    clamp_duration = ns["clamp_duration"]
    clamp_segments = ns["clamp_segments"]
    media_enabled_for_load = ns["media_enabled_for_load"]
    resolve_region = ns["resolve_region"]
    crop_box = ns["crop_box"]
    assert normalize_mode("auto_chain") == "auto_chain"
    assert normalize_mode("Music Video") == "music_video"
    assert clamp_duration(99) == 15.0
    assert clamp_duration(1) == 5.0
    assert clamp_segments(0) == 1
    assert clamp_segments(99) == 99
    assert clamp_segments(1000) == 999
    assert media_enabled_for_load({"kind": "audio", "enabled": True}, True) is False
    assert media_enabled_for_load({"kind": "audio", "enabled": True}, False) is True
    assert media_enabled_for_load({"kind": "image", "enabled": True}, True) is True
    assert media_enabled_for_load({"kind": "audio", "enabled": False}, False) is False
    assert resolve_region(0, None, 46.694, 10) == (0.0, 10.0)
    assert resolve_region(40, 10, 46.694, 10) == (36.694, 10.0)
    assert resolve_region(0, 3, 46.694, 10) == (0.0, 3.0)
    assert resolve_region(0, 20, 8, 10) == (0.0, 8.0)
    normalize_regions = ns["normalize_regions"]
    assert normalize_regions({"start": 0, "length": 10}, 60, 10, 3) == [
        (0.0, 10.0), (10.0, 10.0), (20.0, 10.0),
    ]
    assert normalize_regions({
        "regions": [{"start": 5, "length": 8}, {"start": 20, "length": 8}],
    }, 60, 10, 2) == [(5.0, 8.0), (20.0, 8.0)]
    assert crop_box((100, 80), None) is None
    assert crop_box((100, 80), {"x": 0, "y": 0, "w": 1, "h": 1}) is None
    assert crop_box((100, 80), {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.4}) == (10, 16, 60, 48)


def test_builder_media_socket():
    builder = (ROOT / "builder.py").read_text(encoding="utf-8")
    builder_js = (ROOT / "web" / "js" / "builder.js").read_text(encoding="utf-8")
    media_js = (ROOT / "web" / "js" / "builderMedia.js").read_text(encoding="utf-8")
    thumbs_js = (ROOT / "web" / "js" / "thumbs.js").read_text(encoding="utf-8")
    assert '"media": ("*"' in builder
    assert 'f"media_{i}"' in builder
    assert 'f"media_type_{i}"' in builder
    assert '{"hidden": True}' in builder
    assert "collect_socket_media" in builder
    assert "crop_image_tensor" in builder
    assert "sockets=collect_socket_media" in builder
    assert "h3_studio_builder_media_links" in media_js
    assert "function addVirtualLink" in media_js
    assert "function syncBuilderMediaList" in media_js
    assert "app.graphToPrompt" in media_js
    assert "installBuilderMediaNode" in builder_js
    assert "syncBuilderMediaList" in builder_js
    assert "syncLinksFromMediaOrder" in builder_js
    assert "or wire them to Media" in builder_js
    assert "moveInput(node, mediaIdx, 0)" in builder_js
    assert "mediaAt + 1" in builder_js
    assert 'key === "image"' in thumbs_js
    torch = pytest.importorskip("torch")
    ns = {"torch": torch}
    exec(
        "def infer_media_type"
        + builder.split("def infer_media_type", 1)[1].split("def collect_socket_media", 1)[0],
        ns,
        ns,
    )
    assert ns["infer_media_type"]({"waveform": True, "sample_rate": 8}) == "audio"
    exec(
        "def crop_box"
        + builder.split("def crop_box", 1)[1].split("def slice_audio", 1)[0]
        + "def crop_image_tensor"
        + builder.split("def crop_image_tensor", 1)[1].split("def connected_video_parts", 1)[0],
        ns,
        ns,
    )
    image = torch.zeros(1, 8, 8, 3)
    cropped = ns["crop_image_tensor"](image, {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5})
    assert tuple(cropped.shape) == (1, 4, 4, 3)


def test_plan_music_video_rejects_untimed():
    loader = _load("song_loader")
    with pytest.raises(ValueError, match="stamps"):
        loader.plan_music_video("unused.wav", "hello world")
    assert loader._plan_duration("10.00s") == 10.0
    assert loader._plan_duration(8) == 8.0

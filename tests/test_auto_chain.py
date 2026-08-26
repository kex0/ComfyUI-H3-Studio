import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = "herrgotts_h3_suite_testpkg"


def _load(name):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
    return importlib.import_module(f"{PKG}.{name}")


def test_auto_chain_frontend_targets_release_node_class():
    text = (ROOT / "web" / "js" / "autoChainSegmentVisibility.js").read_text(encoding="utf-8")
    assert 'TARGET_CLASS = "H3StudioAutoChain"' in text
    assert "MAX_SEGMENTS = 12" in text
    assert "removeInput" in text
    assert "addInput" in text
    assert "hideLegacyPromptWidgets" in text
    assert "syncModelInputs" in text
    assert "ensureInputAt" in text
    assert "syncLoopWidgets" in text
    assert "loop_prompt" in text
    assert "model_loop" in text
    assert "seamless_loop" in text
    assert "setWidgetVisible(findWidget(node, `prompt_${i}`), false)" in text
    assert 'setWidgetVisible(findWidget(node, "loop_prompt"), false)' in text
    assert "./nodeSize.js" in text
    assert "captureNodeSize" in text
    assert "restoreNodeSizeSoon" in text
    assert "preserveNodeSize" in text
    assert "node.setSize([" not in text
    editor = (ROOT / "web" / "js" / "promptEditor.js").read_text(encoding="utf-8")
    assert "H3StudioAutoChain" in editor
    assert "H3StudioMusicVideo" in editor
    assert "Replace all" in editor
    assert "Remove" in editor
    assert "replaceOneChip" in editor
    assert "replaceChipsByToken" in editor
    assert "pushHistory" in editor
    assert "undoHistory" in editor
    assert "serializeRange" in editor
    assert "copyEditorSelection" in editor
    assert "openFloatingMenu" in editor
    assert "openChipMenu" in editor
    assert "No other references" in editor
    assert 'document.addEventListener("pointerdown"' in editor
    assert 'document.addEventListener("keydown"' in editor
    assert "mountPromptEditor" in editor
    assert "function promptText" in editor
    assert "function setPromptText" in editor
    assert "createPromptEditorUi" in editor
    assert "h3-studio-prompt-wrap" in editor
    assert "h3_prompt_mentions" in editor
    assert "getMinHeight: () => 50" in editor
    assert "getHeight: () => \"100%\"" in editor
    assert "remainingPromptHeight" in editor
    assert "bindPromptWidgetSize" in editor
    assert "syncPromptWidget" in editor
    assert "visualNodeHeight" in editor
    assert "trailingWidgetsHeight" in editor
    assert "installPromptSizeGuard" in editor
    assert "computedHeight" in editor
    assert "computeLayoutSize" in editor
    assert "pinPromptGrid" in editor
    assert "minmax(50px, 1fr)" in editor
    assert "lg-node-widgets" in editor
    assert "hasLayoutSize = true" in editor
    assert "pinProgressWidget" in editor
    assert "$$node-text-preview" in editor
    assert "progressText" in editor
    assert "h3-studio-progress-pin" in editor
    assert "function isAdvancedAutoChain" in editor
    assert "h3-studio-prompt-mode" in editor
    assert "One prompt per clip" in editor
    assert "Single prompt" in editor
    assert "syncAdvancedPromptHost" in editor
    assert "MAX_CLIP_PROMPTS = 12" in editor
    assert "prompt_mode" in editor
    assert "hideOriginalPromptWidget" in editor
    assert "listedWidgetValues" in editor
    assert "dropDomWidgetValue" in editor
    assert 'widget.type = "hidden"' not in editor
    assert "togglePromptView" in editor
    assert "comfy-multiline-input" in editor
    assert "insertPlainText" in editor
    assert "pasteIntoEditor" in editor
    assert 'editor.addEventListener("paste"' in editor
    assert "stopImmediatePropagation" in editor
    assert "insertMentionChip" in editor
    assert "applyMention" in editor
    assert "refreshPromptThumbs" in editor
    assert "bustThumbUrl" in editor
    assert "Reload thumbnails" in editor
    assert "h3-studio-prompt-tools is-top" in editor
    assert 'label: "Preview"' in editor
    assert "openPreview(media, { segment: tag.segment })" in editor
    assert "h3-dialogue-block" in editor
    assert "insertDialogueBlockAtSelection" in editor
    assert "<d>" in editor
    assert "handleDialogueKey" in editor
    assert "h3-dialogue-flag" in editor
    assert "openDialogueLangMenu" in editor
    assert "wrapDialogueInner" in editor
    assert "dialogueLanguagePrefix" in editor
    assert 'name: "English"' in editor
    assert 'code: "EN"' in editor
    assert "h3-dialogue-flag-glyph" in editor
    assert "Custom language" in editor
    assert "setChipSegment" in editor
    assert "h3-chip-menu-picks" in editor
    assert "mentionToken" in editor
    assert "(?::\\d+)?" in editor
    assert "h3-studio-builder-changed" in editor
    assert "kindIconSvg" in editor
    assert "./thumbs.js" in editor
    assert "showMentionMenu" in editor
    assert "handleMentionKey" in editor
    assert "handlePickerKey" in editor
    assert "renderPickerRows" in editor
    assert "h3-mention-picker-row" in editor
    assert "itemWithSegment" in editor
    assert "mediaSegmentCount" in editor
    assert 'mode: "replace"' in editor
    assert "activeMenu.picker" in editor
    assert "applyReplace" in editor
    assert "placeCaretAfter" in editor
    assert "placeCaretBefore" in editor
    assert "placeCaretAtSerializedOffset" in editor
    assert "caretAfterDiff" in editor
    assert "handleChipKey" in editor
    assert "flattenEditorBlocks" in editor
    assert 'event.key === "Enter"' in editor
    assert "isEmptyText" in editor
    assert "textEndsWithBreak" in editor
    assert "makeCaretSink" in editor
    assert "repairCaretSinks" in editor
    assert "needsCaretSinkFrom" in editor
    assert "moveCaretBeforeSink" in editor
    assert "placeCaretBefore" in editor
    assert "h3-kind-video" in editor
    assert "is-video::after" in editor
    assert "vertical-align: middle" in editor
    assert "./nodeSize.js" in editor
    assert "captureNodeSize" in editor
    assert "restoreNodeSizeSoon" in editor
    assert "caretClientRect" in editor
    assert "mentionAtCaret" in editor
    assert "h3-mention-menu-thumb" in editor
    assert "makeThumb" in editor
    chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    assert '"prompt": ("STRING"' in chain
    assert "resolve_auto_chain_prompts" in chain
    assert "removeInputByName" in text
    assert 'removeInputByName(node, "model_loop")' in text
    assert "last_frame" not in text
    assert "lastFrameLabel" not in text


def test_auto_chain_returns_images_and_audio_first():
    text = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    assert '_LOG = logging.getLogger("h3_continuous")' in text
    assert 'RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "LATENT", "H3_CONTINUOUS_HANDOVER")' in text
    assert "hidden" in text
    assert '"unique_id": "UNIQUE_ID"' in text
    assert "send_node_progress" in text
    assert "release_loaded_models" in text
    assert "resume_from_clip" in text
    assert "clips_to_reuse" in text
    assert '"model_1"' in text
    assert "seamless_loop" in text
    assert "loop_prompt" in text
    assert '"prompt": ("STRING"' in text
    assert "resolve_auto_chain_prompts" in text
    assert "model_loop" in text
    assert "last_as_final_clip=True" in text
    assert "close_loop=seamless_loop" in text
    assert "end_latent=loop_end_latent" in text
    assert "last_frame=None" in text
    assert "first_frame=start_still" in text
    assert "_pack_first_frame" in text
    assert "first_frame=None" not in text
    assert "first_frame=first_frame" not in text
    assert "reference_images=" in text
    assert "collect_music_video_reference_images" in text
    assert "music_video_reference_image_specs" in text
    assert '"first_frame"' not in text
    assert "segment_last_frame_specs" not in text
    assert "last_frame_" not in text
    assert "loop_start_trim_frames" in text
    assert "loop_overlap_frames=loop_end_frames" in text
    assert "stream_stitch_saved_clips" in text
    assert "filename_prefix" in text
    assert "class H3StudioAutoChain" in text
    adv = text.split("class H3StudioAutoChainAdvanced", 1)[1]
    assert 'required.pop("loop_prompt"' in adv
    assert 'required.pop(f"prompt_{i}"' in adv
    assert "prompt_mode" in adv
    assert "document_has_loop" in adv
    assert 'kwargs["prompt"] = ""' in adv
    assert 'kwargs["seamless_loop"] = document_has_loop' in adv
    assert 'optional["prompt_mode"]' in adv
    assert "def _clip_role" in text
    assert "combined_images" not in text
    assert "save_clip_videos" in text
    assert "save_png_frames" not in text
    assert "debug_exposure" not in text
    assert '"filename_prefix"' not in text
    assert '"crf"' not in text
    assert "freeze_overlap" in text
    assert "freeze_overlap=freeze_overlap" in text
    assert "overlap_soft_steps=overlap_soft_steps" in text
    assert "identity_frame=identity_frame" in text
    assert "Stitching reused clip" not in text
    assert "load clip %s only" in text
    assert "encode_clip_preview" in (ROOT / "stream_stitch.py").read_text(encoding="utf-8")
    assert "StreamStitchSession" in (ROOT / "stream_stitch.py").read_text(encoding="utf-8")
    assert "add_decoded_clip" in (ROOT / "stream_stitch.py").read_text(encoding="utf-8")
    assert "loop sandwich" in (ROOT / "nodes.py").read_text(encoding="utf-8")


def test_clips_to_reuse_starts_generation_at_requested_clip():
    ci = _load("chain_inputs")
    assert ci.clips_to_reuse(1, 5) == []
    assert ci.clips_to_reuse(2, 5) == [1]
    assert ci.clips_to_reuse(5, 5) == [1, 2, 3, 4]
    try:
        ci.clips_to_reuse(6, 5)
    except ValueError as exc:
        assert "resume_from_clip" in str(exc)
    else:
        raise AssertionError("expected resume_from_clip > segments to fail")


def test_clips_to_reuse_can_resume_at_loop_clip():
    ci = _load("chain_inputs")
    assert ci.clips_to_reuse(3, 2, seamless_loop=True) == [1, 2]
    assert ci.clips_to_reuse(2, 2, seamless_loop=True) == [1]
    assert ci.clips_to_reuse(4, 3, seamless_loop=True) == [1, 2, 3]
    try:
        ci.clips_to_reuse(3, 2, seamless_loop=False)
    except ValueError as exc:
        assert "1..2" in str(exc)
    else:
        raise AssertionError("expected resume_from_clip=3 without loop to fail")
    try:
        ci.clips_to_reuse(4, 2, seamless_loop=True)
    except ValueError as exc:
        assert "1..3" in str(exc)
    else:
        raise AssertionError("expected resume past the Loop clip to fail")


def test_collect_segment_values_keeps_requested_prefix_order():
    ci = _load("chain_inputs")
    kwargs = {"prompt_1": "a", "prompt_2": "b", "prompt_3": "c", "prompt_4": "ignored"}
    assert ci.collect_segment_values(3, kwargs, "prompt") == ["a", "b", "c"]
    assert ci.collect_segment_values(2, {"last_frame_1": None, "last_frame_2": "x"}, "last_frame") == [None, "x"]
    assert set(ci.segment_prompt_specs()) == {f"prompt_{i}" for i in range(1, ci.MAX_SEGMENTS + 1)}
    assert set(ci.segment_model_specs()) == {f"model_{i}" for i in range(2, ci.MAX_SEGMENTS + 1)}
    assert ci.collect_segment_models(3, "base", {"model_2": "lora_b"}) == ["base", "lora_b", "base"]
    assert ci.collect_segment_models(3, "base", {"model_1": "start", "model_3": "lora_c"}) == ["start", "base", "lora_c"]


def test_continue_song_audio_ref_skips_previous_generated_audio():
    text = (ROOT / "nodes.py").read_text(encoding="utf-8")
    assert "song_audio_latent=None" in text
    assert "previous generated audio skipped" in text
    assert "song_audio_latent cannot be combined with end_latent" in text
    assert "HC_AUDIO_END_FRAME: float(frame_count)" in text


def test_timeline_audio_slot_skips_persistent_ref_audio():
    pl = _load("patch_layout")
    refs = [
        {"kind": "image"},
        {"kind": "video_audio", "ref_audio_t": 4},
        {"kind": "audio", "ref_audio_t": 5},
        {"kind": "audio", "ref_audio_t": 11, pl.HC_AUDIO_END_FRAME: 10.0},
    ]
    assert pl._emits_ref_audio(refs[0]) is False
    assert pl._emits_ref_audio(refs[1]) is True
    assert pl._ref_audio_slot(refs, 3) == 2


def test_music_video_node_contract():
    text = (ROOT / "music_video.py").read_text(encoding="utf-8")
    assert "class H3StudioMusicVideo" in text
    assert 'RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "LATENT", "H3_CONTINUOUS_HANDOVER")' in text
    assert '"song": ("AUDIO"' in text
    assert text.find('"model_1": ("MODEL"') < text.find('"song": ("AUDIO"') < text.find('"clip": ("CLIP"')
    adv = text.split("class H3StudioMusicVideoAdvanced", 1)[1]
    assert '"pack": ("H3_STUDIO_PACK"' in adv
    assert 'required.pop("model_1"' in adv
    assert 'required.pop("duration"' in adv
    assert "duration_and_segments_from_pack_or_prompt" in adv
    assert "ordered.update(required)" in adv
    assert "parse_music_video_prompt" in text
    assert "song_audio_latent=" in text
    assert "from comfy_extras.nodes_minimax_h3 import _encode_ref_audio" in text
    assert "MiniMaxH3ReferenceToVideo._encode_ref_audio" not in text
    assert "music_video_mux_spans" in text
    assert "MUSIC_MAX_SEGMENTS" in text
    assert "song_slice_start_frame" in text
    assert "song_cursor_after" in text
    assert "_stitch_saved_video" in text
    assert "stream_stitch_saved_clips" in text
    assert "decode_audio=False" in text
    assert "mux_audio_onto_mp4" in text
    assert "max_video_frames=song_frames" in text
    assert "save_clip_videos" in text
    assert "save_png_frames" not in text
    assert "debug_exposure" not in text
    assert '"filename_prefix"' not in text
    assert '"crf"' not in text
    assert "freeze_overlap" in text
    assert "freeze_overlap=freeze_overlap" in text
    assert "overlap_soft_steps=overlap_soft_steps" in text
    assert "identity_frame=identity_frame" in text
    assert "stop_after_clip" in text
    assert "song_audio_lock=song_audio_lock" in text
    assert '"song_audio_lock"' in text
    assert "reference_images=" in text
    assert "collect_music_video_reference_images" in text
    assert "music_video_reference_image_specs" in text
    assert "first_frame=start_still" in text
    assert "_pack_first_frame" in text
    assert "first_frame=None" not in text
    assert "first_frame=first_frame" not in text
    assert '"first_frame"' not in text
    chain = (ROOT / "chain_inputs.py").read_text(encoding="utf-8")
    assert 'f"reference_image_{i}"' in chain
    assert "MUSIC_MAX_REF_IMAGES = 9" in chain
    js = (ROOT / "web" / "js" / "musicVideoRefImages.js").read_text(encoding="utf-8")
    assert "H3StudioMusicVideo" in js
    assert "H3StudioAutoChain" in js
    assert "TARGET_CLASSES" in js
    assert "reference_image_${i}" in js
    assert "removeInput" in js
    assert "addInput" in js
    assert "_write_music_video_clip_previews" in text
    assert 'suffix="song"' in text
    assert 'suffix="generated"' in text
    assert "_decode_audio" in text
    assert "_apply_music_join_tail" in text
    assert "MUSIC_JOIN_TAIL_FRAMES" in text
    assert "_slice_song_audio(song, slice_start, int(images.shape[0]))" in text
    assert "add_decoded_clip" in text
    assert "live_stitch" in text
    assert "Stitching reused clip" not in text
    assert "load clip %s only" in text
    assert "combined_images" not in text
    mappings = (ROOT / "nodes.py").read_text(encoding="utf-8")
    init = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"H3StudioMusicVideo": H3StudioMusicVideo' in init
    assert '"H3 Studio - Music Video"' in init
    assert '"H3StudioLoadSong": H3StudioLoadSong' in init
    assert '"H3 Studio - Load Song"' in init
    assert '"H3StudioAutoChain": H3StudioAutoChain' in init
    assert '"H3StudioFaceRefineVideo": H3StudioFaceRefineVideo' in init
    assert "H3ContinuousMusicVideoV11" not in init
    assert "H3ContinuousAutoChainV11" not in init
    song_js = (ROOT / "web" / "js" / "songTimeline.js").read_text(encoding="utf-8")
    assert 'const NODE_NAME = "H3StudioLoadSong"' in song_js
    assert "reference_images=None" in mappings
    assert "if not ref_items and identity is not None" in mappings
    assert "_ref2va_image_blocks" in mappings
    assert '"kind": "image"' in mappings
    start_src = mappings.split("class H3ContinuousStart:", 1)[1].split("def _resolve_continue_slice", 1)[0]
    assert "refs.extend(_ref2va_image_blocks" in start_src
    assert "if pics:" in start_src
    assert start_src.rfind("refs.extend(audio_blocks)") < start_src.find("HC_AUDIO_END_FRAME: float(frame_count)")
    cont_src = mappings.split("class H3ContinuousContinue:", 1)[1].split("class H3ContinuousSaveLatent", 1)[0]
    assert "_ref2va_image_blocks(pics, vae, width, height, ref_image_size)" in cont_src
    assert "video_blocks" in cont_src
    assert "image_blocks + video_blocks + audio_blocks + refs" in cont_src
    assert "image_blocks + refs + video_blocks + audio_blocks" not in cont_src
    assert "image_blocks + video_blocks + refs + audio_blocks" not in cont_src
    assert "if pics:" in cont_src
    assert "if song_audio_latent is not None and pics:" not in cont_src


def test_music_video_collects_numbered_reference_images():
    chain = _load("chain_inputs")
    assert chain.MUSIC_MAX_REF_IMAGES == 9
    assert chain.collect_music_video_reference_images({}) == []
    assert chain.collect_music_video_reference_images({
        "reference_image_1": "a",
        "reference_image_3": "c",
        "reference_image_2": "b",
    }) == ["a", "b", "c"]
    assert chain.collect_music_video_reference_images({"reference_image": "legacy"}) == ["legacy"]
    specs = chain.music_video_reference_image_specs()
    assert list(specs) == [f"reference_image_{i}" for i in range(1, 10)]


def test_spectrum_join_prefix_matches_interop_v1():
    sj = _load("spectrum_join")
    payload = sj.SPECTRUM_JOIN_PREFIX
    assert type(payload["api"]) is int and payload["api"] == 1
    assert type(payload["active"]) is bool and payload["active"] is True
    assert type(payload["min_actual_prefix_steps"]) is int
    assert payload["min_actual_prefix_steps"] == 2
    assert payload["api"] is not True
    assert payload["min_actual_prefix_steps"] is not True


def test_attach_spectrum_join_prefix_copies_model_options():
    sj = _load("spectrum_join")
    shared = {"transformer_options": {"other": 1}}

    class Guider:
        model_options = shared

    guider = Guider()
    sj.attach_spectrum_join_prefix(guider, False)
    assert guider.model_options is shared
    sj.attach_spectrum_join_prefix(guider, True)
    assert guider.model_options is not shared
    assert shared["transformer_options"] == {"other": 1}
    transformer = guider.model_options["transformer_options"]
    assert transformer["other"] == 1
    assert transformer["h3_continuum"] == sj.SPECTRUM_JOIN_PREFIX
    assert transformer["h3_continuum"] is not sj.SPECTRUM_JOIN_PREFIX


def test_continue_samples_request_spectrum_join_prefix():
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music_video = (ROOT / "music_video.py").read_text(encoding="utf-8")
    assert "attach_spectrum_join_prefix" in auto_chain
    assert 'join_prefix=(role != "Start")' in auto_chain
    assert "join_prefix=True" in auto_chain
    assert "join_prefix=(i != 0)" in music_video


def test_saved_chain_stitch_uses_shared_stream_encoder():
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    stream = (ROOT / "stream_stitch.py").read_text(encoding="utf-8")
    assert "from .stream_stitch import stream_stitch_saved_clips" in nodes
    assert "def _write_video(self, frames):" in stream
    assert "pending_video" in stream
    assert "decode_audio" in stream
    assert "collect_audio" in stream
    assert "max_video_frames" in stream
    assert "_close_loop_png" in stream
    assert "class StreamStitchSession" in stream
    assert "def encode_clip_preview" in stream
    assert "def clip_preview_path" in stream
    assert 'suffix: str = ""' in stream
    assert "def png_frames_dir" in stream
    assert "save_png_frame" in stream
    assert "save_png_frames" not in stream
    assert "unique_temp_frames_dir" in stream
    assert "frames_dir=None" in stream
    assert "node_temp_frames_dir" in (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    assert "load_png_sequence" in stream
    assert "keep_in_ram=False" in stream
    assert "self.video_chunks" in stream

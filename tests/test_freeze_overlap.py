import importlib
import sys
import types
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
PKG = "herrgotts_h3_suite_testpkg"


def _load(name):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
    return importlib.import_module(f"{PKG}.{name}")


def test_freeze_video_head_copies_source_and_masks_only_video():
    fo = _load("freeze_overlap")
    video = torch.zeros(1, 24, 8, 4, 4)
    source = torch.arange(1 * 24 * 3 * 4 * 4, dtype=torch.float32).reshape(1, 24, 3, 4, 4)
    audio = torch.zeros(1, 32, 2, 16)
    frozen, out_audio, v_mask, a_mask = fo.freeze_video_head(
        video, source, audio, soft_steps=0,
    )
    assert out_audio is audio
    assert torch.equal(frozen[:, :, :3], source)
    assert torch.count_nonzero(frozen[:, :, 3:]) == 0
    assert v_mask.shape == (1, 1, 8, 1, 1)
    assert torch.count_nonzero(v_mask[:, :, :3]) == 0
    assert torch.all(v_mask[:, :, 3:] == 1)
    assert a_mask.shape == (1, 1, 1, 16)
    assert torch.all(a_mask == 1)


def test_freeze_video_head_ramps_last_frozen_steps():
    fo = _load("freeze_overlap")
    video = torch.zeros(1, 24, 8, 2, 2)
    source = torch.ones(1, 24, 5, 2, 2)
    audio = torch.zeros(1, 32, 2, 8)
    frozen, _, v_mask, _ = fo.freeze_video_head(video, source, audio, soft_steps=2)
    assert torch.equal(frozen[:, :, :5], source)
    assert float(v_mask[0, 0, 0, 0, 0]) == 0.0
    assert float(v_mask[0, 0, 1, 0, 0]) == 0.0
    assert float(v_mask[0, 0, 2, 0, 0]) == 0.0
    assert abs(float(v_mask[0, 0, 3, 0, 0]) - 1.0 / 3.0) < 1e-6
    assert abs(float(v_mask[0, 0, 4, 0, 0]) - 2.0 / 3.0) < 1e-6
    assert torch.all(v_mask[:, :, 5:] == 1)


def test_freeze_video_head_keeps_one_hard_step():
    fo = _load("freeze_overlap")
    video = torch.zeros(1, 24, 4, 2, 2)
    source = torch.ones(1, 24, 2, 2, 2)
    audio = torch.zeros(1, 32, 2, 8)
    _, _, v_mask, _ = fo.freeze_video_head(video, source, audio, soft_steps=4)
    assert float(v_mask[0, 0, 0, 0, 0]) == 0.0
    assert abs(float(v_mask[0, 0, 1, 0, 0]) - 0.5) < 1e-6
    assert torch.all(v_mask[:, :, 2:] == 1)


def test_freeze_video_head_skips_when_head_covers_clip():
    fo = _load("freeze_overlap")
    video = torch.zeros(1, 24, 4, 2, 2)
    source = torch.ones(1, 24, 4, 2, 2)
    audio = torch.zeros(1, 32, 2, 8)
    frozen, out_audio, v_mask, a_mask = fo.freeze_video_head(video, source, audio)
    assert frozen is video
    assert out_audio is audio
    assert v_mask is None
    assert a_mask is None


def test_freeze_video_head_skips_empty_head():
    fo = _load("freeze_overlap")
    video = torch.zeros(1, 24, 4, 2, 2)
    source = torch.zeros(1, 24, 0, 2, 2)
    audio = torch.zeros(1, 32, 2, 8)
    frozen, out_audio, v_mask, a_mask = fo.freeze_video_head(video, source, audio)
    assert frozen is video
    assert out_audio is audio
    assert v_mask is None
    assert a_mask is None


def test_copy_song_audio_lock_pastes_and_masks():
    fo = _load("freeze_overlap")
    audio = torch.zeros(1, 32, 2, 8)
    song = torch.arange(1 * 32 * 2 * 8, dtype=torch.float32).reshape(1, 32, 2, 8)
    out, a_mask = fo.copy_song_audio(audio, song, 0.5)
    assert torch.equal(out, song)
    assert a_mask.shape == (1, 1, 1, 8)
    assert torch.all(a_mask == 0.5)
    untouched, none_mask = fo.copy_song_audio(audio, song, 0.0)
    assert untouched is audio
    assert none_mask is None
    locked, zero_mask = fo.copy_song_audio(audio, song, 1.0)
    assert torch.equal(locked, song)
    assert torch.all(zero_mask == 0)


def test_copy_song_audio_fits_off_by_one_time():
    fo = _load("freeze_overlap")
    audio = torch.zeros(1, 32, 2, 377)
    song = torch.arange(1 * 32 * 2 * 376, dtype=torch.float32).reshape(1, 32, 2, 376)
    out, a_mask = fo.copy_song_audio(audio, song, 1.0)
    assert out.shape[-1] == 377
    assert torch.equal(out[..., :376], song)
    assert torch.equal(out[..., 376:], song[..., -1:])
    assert a_mask.shape[-1] == 377
    long_song = torch.arange(1 * 32 * 2 * 378, dtype=torch.float32).reshape(1, 32, 2, 378)
    cropped, _ = fo.copy_song_audio(audio, long_song, 1.0)
    assert cropped.shape[-1] == 377
    assert torch.equal(cropped, long_song[..., :377])


def test_freeze_overlap_wired_through_continue_and_chains():
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music_video = (ROOT / "music_video.py").read_text(encoding="utf-8")
    assert "from .freeze_overlap import copy_song_audio, freeze_video_head" in nodes
    assert "copy_song_audio" in nodes
    assert "_apply_song_audio_lock" in nodes
    assert "overlap freeze" in nodes
    assert '"freeze_overlap"' in nodes
    assert "freeze_overlap=freeze_overlap" in nodes
    assert "overlap_soft_steps=overlap_soft_steps" in nodes
    assert "identity_frame=identity_frame" in nodes
    assert "identity still @" in nodes
    assert "target_latent[\"noise_mask\"]" in nodes
    assert "denoise_mask=latent.get(\"noise_mask\")" in auto_chain
    assert "freeze_overlap=freeze_overlap" in auto_chain
    assert "overlap_soft_steps=overlap_soft_steps" in auto_chain
    assert "identity_frame=identity_frame" in auto_chain
    assert "_overlap_identity_frame" in auto_chain
    assert "if i == 0:" in auto_chain
    start_call = auto_chain.split("positive, empty = start.build(", 1)[1].split(")", 1)[0]
    assert "identity_frame" not in start_call
    assert "song_audio_latent" not in start_call
    assert "song_audio_lock" not in start_call
    assert "identity_frame=identity_frame" in auto_chain.split("else:", 1)[1]
    assert "end_latent=loop_end_latent" in auto_chain
    assert "freeze_overlap=freeze_overlap" in music_video
    assert "overlap_soft_steps=overlap_soft_steps" in music_video
    assert "identity_frame=identity_frame" in music_video
    mv_start = music_video.split("positive, empty = start.build(", 1)[1].split(")", 1)[0]
    assert "identity_frame" not in mv_start
    assert "actual_context_frames <= 1" in nodes
    assert "song_audio_latent=song_latent" in music_video
    assert "song_audio_lock=song_audio_lock" in music_video
    assert '"song_audio_lock"' in music_video


def test_continue_skips_overlap_keyframes_when_freeze_without_end_latent():
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    assert "pack_overlap_kfs = not (bool(freeze_overlap) and end_latent is None)" in nodes
    assert "if pack_overlap_kfs:" in nodes
    assert "overlap not packed as keyframes" in nodes
    continue_src = nodes.split("class H3ContinuousContinue:", 1)[1].split("class H3ContinuousSaveLatent", 1)[0]
    loop = continue_src.split("if pack_overlap_kfs:", 1)[1].split("last = None", 1)[0]
    assert "for k, pixel_offset in enumerate(sl[\"offsets\"])" in loop
    after_kfs = continue_src.split("last = None", 1)[1]
    assert "end_latent is not None" in after_kfs
    assert "identity still @" in after_kfs
    assert "HC_INDEX: identity_at" in after_kfs
    assert "HC_AUDIO_END_FRAME" in after_kfs


def test_overlap_soft_steps_defaults_to_hard_freeze():
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music_video = (ROOT / "music_video.py").read_text(encoding="utf-8")
    freeze = (ROOT / "freeze_overlap.py").read_text(encoding="utf-8")
    assert '"default": 0, "min": 0, "max": 4, "step": 1' in nodes.split("overlap_soft_steps", 1)[1]
    assert '"default": 0, "min": 0, "max": 4, "step": 1' in auto_chain.split("overlap_soft_steps", 1)[1]
    assert '"default": 0, "min": 0, "max": 4, "step": 1' in music_video.split("overlap_soft_steps", 1)[1]
    assert "overlap_soft_steps=0" in nodes
    assert "overlap_soft_steps=0" in auto_chain
    assert "overlap_soft_steps=0" in music_video
    assert "def freeze_video_head(video, source_head, audio, soft_steps=0):" in freeze
    assert "OVERLAP_SOFT_STEPS = 2" in (ROOT / "face_refine" / "grid.py").read_text(encoding="utf-8")

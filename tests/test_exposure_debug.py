from pathlib import Path

import pytest


def _load():
    import importlib
    import sys
    import types

    root = Path(__file__).resolve().parents[1]
    pkg = "herrgotts_h3_suite_testpkg"
    if pkg not in sys.modules:
        module = types.ModuleType(pkg)
        module.__path__ = [str(root)]
        module.__package__ = pkg
        sys.modules[pkg] = module
    return importlib.import_module(f"{pkg}.exposure_debug")


def test_packed_keyframes_hit_vae_chunk_starts():
    ed = _load()
    assert ed.packed_keyframe_frames(40) == [0, 17, 34]


def test_flat_clip_is_clean():
    ed = _load()
    luma = [0.40] * 80
    report = ed.classify_exposure(luma, head_context_frames=30, clip_index=2)
    assert report["verdict"] == "none"
    assert report["cause"] == "clean"


def test_head_pump_that_dies_before_trim_is_preview_or_reconstruction():
    ed = _load()
    luma = [0.12] * 80
    for i in range(0, 16):
        luma[i] = 0.12 + 0.08 * (i / 15)
    luma[16] = 0.12
    source = [0.12] * 80
    report = ed.classify_exposure(
        luma, head_context_frames=30, ignored_tail_frames=9,
        previous_luma=source, clip_index=2,
    )
    assert report["verdict"] == "head_only"
    assert report["cause"] == "reconstruction_pump_head_only"
    assert report["source"]["available"] is True
    assert report["max_delta_frame"] < 30


def test_pump_past_head_is_leak():
    ed = _load()
    luma = [0.10] * 80
    for i in range(34):
        luma[i] = 0.22
    source = [0.10] * 80
    report = ed.classify_exposure(
        luma, head_context_frames=22, ignored_tail_frames=0,
        previous_luma=source, clip_index=2,
    )
    assert report["verdict"] == "leak"
    assert report["cause"] == "reconstruction_pump_leaks"
    assert report["leak_peaks"]


def test_matching_source_head_flash_is_preview_only():
    ed = _load()
    luma = [0.11] * 80
    for i in range(12):
        luma[i] = 0.20
    previous = [0.11] * 50 + luma[:30]
    report = ed.classify_exposure(
        luma, head_context_frames=30, ignored_tail_frames=0,
        previous_luma=previous, clip_index=2,
    )
    assert report["verdict"] == "head_only"
    assert report["cause"] == "preview_head_only"
    assert report["source"]["mae"] < 0.001


def test_clip1_open_is_not_a_join_cause():
    ed = _load()
    luma = [0.50] * 8 + [0.20] * 70
    report = ed.classify_exposure(luma, head_context_frames=0, clip_index=1)
    assert report["cause"] == "clip1_open"


def test_frame_luma_series_rec709():
    import torch

    ed = _load()
    red = torch.zeros(2, 4, 4, 3)
    red[..., 0] = 1.0
    series = ed.frame_luma_series(red)
    assert series[0] == pytest.approx(0.2126, abs=1e-5)
    assert series[1] == pytest.approx(0.2126, abs=1e-5)


def test_log_line_names_cause():
    ed = _load()
    report = ed.classify_exposure([0.2] * 40, head_context_frames=22, clip_index=2)
    line = ed.format_log_line(report)
    assert "cause=clean" in line
    assert "exposure clip 2" in line


def test_nodes_keep_freeze_overlap_knobs():
    root = Path(__file__).resolve().parents[1]
    auto_chain = (root / "auto_chain.py").read_text(encoding="utf-8")
    music_video = (root / "music_video.py").read_text(encoding="utf-8")
    assert "debug_exposure" not in auto_chain
    assert "debug_exposure" not in music_video
    assert "freeze_overlap" in auto_chain
    assert "freeze_overlap" in music_video
    assert "overlap_soft_steps" in auto_chain
    assert "overlap_soft_steps" in music_video
    assert "report_clip_exposure" not in auto_chain
    assert "report_clip_exposure" not in music_video

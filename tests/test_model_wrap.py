import importlib
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PKG = "h3_studio_testpkg"


def _load(name):
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
    return importlib.import_module(f"{PKG}.{name}")


def test_adapt_marked_layout_unmarked_payload_is_noop():
    pl = _load("patch_layout")

    class Layout:
        signature = (7, 7, 22, 38, 16)
        segments = []

    layout = Layout()
    payload = {
        "layout": layout,
        "keyframes": [{"resolved_frame_index": 9, "latent": object()}],
        "refs": [{"kind": "audio", "ref_audio_t": 5}],
    }
    assert pl.adapt_marked_layout(payload) is payload
    assert not getattr(layout, pl.LAYOUT_ADAPT_MARKER, False)


def test_adapt_marked_layout_skips_already_marked_layout():
    pl = _load("patch_layout")

    class Layout:
        signature = (7, 7, 22, 38, 16)

    layout = Layout()
    setattr(layout, pl.LAYOUT_ADAPT_MARKER, True)
    payload = {
        "layout": layout,
        "keyframes": [{pl.HC_INDEX: 9, "latent": object()}],
    }
    assert pl.adapt_marked_layout(payload) is payload


def test_rewrite_marked_payload_concatenates_keyframes_and_refs():
    pp = _load("patch_payload")
    pl = _load("patch_layout")
    keyframes = [{pl.HC_INDEX: 0, "latent": "k"}]
    refs = [{
        "kind": "audio",
        "latent": "r",
        "audio_latent": "a",
        pl.HC_AUDIO_END_FRAME: 5.0,
    }]
    payload = {"keyframes": keyframes, "refs": refs}
    pp.maybe_rewrite_marked_payload(payload)
    assert payload["cond_video_latents"] == ["k", "r"]
    assert payload["cond_audio_latents"] == ["a"]
    unmarked = {"keyframes": [{"latent": "k"}], "refs": [{"latent": "r"}]}
    pp.maybe_rewrite_marked_payload(unmarked)
    assert "cond_video_latents" not in unmarked


def test_apply_model_wrapper_passes_unmarked_payload_through():
    mw = _load("model_wrap")
    seen = {}

    def executor(*args, **kwargs):
        seen["kwargs"] = kwargs
        return "ok"

    payload = {"keyframes": [{"resolved_frame_index": 0}], "refs": []}
    assert mw.apply_model_wrapper(executor, minimax_payload=payload) == "ok"
    assert seen["kwargs"]["minimax_payload"] is payload


def test_wrap_h3_model_adds_apply_model_wrapper_once():
    pytest.importorskip("comfy.patcher_extension")
    mw = _load("model_wrap")
    from comfy.patcher_extension import WrappersMP

    class FakeModel:
        def __init__(self):
            self.wrappers = {}

        def clone(self):
            other = FakeModel()
            other.wrappers = {
                k: {kk: list(vv) for kk, vv in v.items()}
                for k, v in self.wrappers.items()
            }
            return other

        def add_wrapper_with_key(self, wrapper_type, key, wrapper):
            self.wrappers.setdefault(wrapper_type, {}).setdefault(key, []).append(wrapper)

        def get_wrappers(self, wrapper_type, key):
            return self.wrappers.get(wrapper_type, {}).get(key, [])

    model = FakeModel()
    wrapped = mw.wrap_h3_model(model)
    assert wrapped is not model
    first = wrapped.get_wrappers(WrappersMP.APPLY_MODEL, mw.WRAPPER_KEY)
    assert first == [mw.apply_model_wrapper]
    again = mw.wrap_h3_model(wrapped)
    assert again.get_wrappers(WrappersMP.APPLY_MODEL, mw.WRAPPER_KEY) == first


def test_adapt_marked_layout_self_test_on_stock_packed_layout():
    pl = _load("patch_layout")
    try:
        mm = pl._import_mm()
        mm.PackedLayout
    except Exception:
        pytest.skip("comfy.ldm.minimax.model PackedLayout is not importable")
    pl._run_self_test(mm)


def test_sample_segment_wraps_model_and_nodes_do_not_install_global_patches():
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    nodes = (ROOT / "nodes.py").read_text(encoding="utf-8")
    sample = auto_chain.split("def _sample_segment(", 1)[1].split("def _cpu_av_latent", 1)[0]
    assert "model = wrap_h3_model(model)" in sample
    assert "Guider_Basic(model)" in sample
    assert "attach_spectrum_join_prefix" in sample
    assert "ensure_h3_runtime_patches" not in nodes
    assert "_require_patches" not in nodes
    layout_src = (ROOT / "patch_layout.py").read_text(encoding="utf-8")
    assert "PackedLayout.__init__ =" not in layout_src
    assert "MiniMaxH3.extra_conds" not in (ROOT / "patch_payload.py").read_text(encoding="utf-8")
    assert not (ROOT / "runtime_patches.py").exists()
    assert not (ROOT / "patch_utils.py").exists()
    face = (ROOT / "face_refine" / "video_refine.py").read_text(encoding="utf-8")
    assert "wrap_h3_model" not in face

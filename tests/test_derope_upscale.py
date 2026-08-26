import sys
import types

import torch

from test_auto_chain import ROOT, _load, PKG


def test_enhancement_widgets_default_off():
    lu = _load("latent_upscale")
    derope = _load("derope")
    specs = lu.upscale_input_specs()
    assert specs["latent_upscale"][1]["default"] is False
    assert specs["latent_upscale_mode"][0] == ["scale by multiplier", "megapixels"]
    assert specs["latent_upscale_mode"][1]["default"] == "scale by multiplier"
    assert specs["latent_upscale_scale"][1]["default"] == 2.0
    assert specs["latent_upscale_megapixels"][1]["default"] == 1.0
    assert specs["latent_upscale_precision"][0] == ["fp32", "fp16", "bf16"]
    assert specs["latent_upscale_precision"][1]["default"] == "fp32"
    derope_specs = derope.derope_input_specs()
    assert derope_specs["de_rope"][1]["default"] is False
    assert derope_specs["de_rope_inject"][1]["default"] == 0.48
    auto = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music = (ROOT / "music_video.py").read_text(encoding="utf-8")
    assert "upscale_input_specs()" in auto and "derope_input_specs()" in auto
    assert "upscale_input_specs()" in music and "derope_input_specs()" in music
    assert "latent_upscale=False" in auto and "de_rope=False" in auto
    assert "latent_upscale=False" in music and "de_rope=False" in music
    js = (ROOT / "web" / "js" / "latentUpscaleWidgets.js").read_text(encoding="utf-8")
    assert "H3StudioAutoChain" in js
    assert "H3StudioMusicVideo" in js
    assert "latent_upscale_mode" in js
    assert "latent_upscale_scale" in js
    assert "latent_upscale_megapixels" in js
    assert "latent_upscale_precision" in js


def test_derope_import_helper_requires_mainodes_class_names():
    derope = _load("derope")
    for name in (
        "H3JerkOracle", "H3WindowPlan", "H3TimeSmear",
        "H3V2VInit", "H3InjectSchedule", "H3ExactRecover",
    ):
        assert name in derope.MAINODES_CLASS_NAMES
    motion = derope.load_mainodes()
    for name in derope.MAINODES_CLASS_NAMES:
        assert hasattr(motion, name)


def test_derope_missing_pack_install_message(monkeypatch, tmp_path):
    derope = _load("derope")
    monkeypatch.setattr(derope, "_MAINODES_PACK", str(tmp_path / "nope"))
    sys.modules.pop(derope._MAINODES_PKG, None)
    sys.modules.pop(f"{derope._MAINODES_PKG}.motion", None)
    try:
        derope.load_mainodes()
    except RuntimeError as exc:
        assert "ComfyUI-MAINodes" in str(exc)
    else:
        raise AssertionError("expected install message when MAINodes is missing")


def test_overlap_skip_uses_head_and_tail_ints():
    derope = _load("derope")
    assert derope.overlap_skip_ranges(243, 1, 22, 8) == [(235, 242)]
    assert derope.overlap_skip_ranges(243, 2, 22, 8) == [(0, 21), (235, 242)]
    assert derope.overlap_skip_ranges(243, 3, 22, 0) == [(0, 21)]
    assert derope.window_hits_skip(10, 30, [(0, 21)]) is True
    assert derope.window_hits_skip(22, 40, [(0, 21)]) is False
    assert derope.window_hits_skip(200, 242, [(235, 242)]) is True
    assert derope.window_hits_skip(100, 120, [(0, 21), (235, 242)]) is False


def test_upscale_helper_does_not_mutate_input_spatial_size(monkeypatch):
    nt = types.ModuleType("comfy.nested_tensor")

    class NestedTensor:
        def __init__(self, tensors):
            self.tensors = list(tensors)
            self.is_nested = True

        def unbind(self):
            return self.tensors

    nt.NestedTensor = NestedTensor
    comfy_mod = sys.modules.setdefault("comfy", types.ModuleType("comfy"))
    comfy_mod.nested_tensor = nt
    sys.modules["comfy.nested_tensor"] = nt

    nodes_name = f"{PKG}.nodes"
    previous = sys.modules.get(nodes_name)
    nodes = types.ModuleType(nodes_name)

    def _streams_from_latent(latent):
        video, audio = latent["samples"].unbind()
        return video, audio

    nodes._streams_from_latent = _streams_from_latent
    sys.modules[nodes_name] = nodes
    try:
        lu = _load("latent_upscale")
        video = torch.arange(1 * 24 * 2 * 4 * 6, dtype=torch.float32).reshape(1, 24, 2, 4, 6)
        audio = torch.zeros(1, 32, 2, 8)
        before = video.clone()
        latent = {"samples": NestedTensor((video, audio))}

        def fake_apply(v, mode):
            v.zero_()
            return torch.ones(1, 24, 2, 8, 12)

        monkeypatch.setattr(lu, "apply_video_upscale", fake_apply)
        out = lu.upscale_av_latent(latent, lu.collect_upscale_settings(True))
        assert tuple(video.shape[-2:]) == (4, 6)
        assert torch.equal(video, before)
        out_video, out_audio = out["samples"].unbind()
        assert tuple(out_video.shape[-2:]) == (8, 12)
        assert tuple(out_audio.shape) == tuple(audio.shape)
    finally:
        if previous is None:
            sys.modules.pop(nodes_name, None)
        else:
            sys.modules[nodes_name] = previous


def test_pick_3d_checkpoint_matches_precision():
    lu = _load("latent_upscale")
    names = [
        "minimax_h3_latent_upscaler_3d_fp16.safetensors",
        "minimax_h3_latent_upscaler_3d_fp32.pth",
        "minimax_h3_latent_upscaler_3d_bf16.safetensors",
    ]
    assert lu.pick_upscale_checkpoint("fp32", names) == "minimax_h3_latent_upscaler_3d_fp32.pth"
    assert lu.pick_upscale_checkpoint("fp16", names) == "minimax_h3_latent_upscaler_3d_fp16.safetensors"
    assert lu.pick_upscale_checkpoint("bf16", names) == "minimax_h3_latent_upscaler_3d_bf16.safetensors"


def test_output_pixel_size_and_disk_budget_follow_mode():
    lu = _load("latent_upscale")
    off = lu.collect_upscale_settings(False)
    by2 = lu.collect_upscale_settings(True, "scale by multiplier", 2.0)
    mp = lu.collect_upscale_settings(True, "megapixels", 2.0, 2.0)
    assert lu.output_pixel_size(1344, 768, off) == (1344, 768)
    assert lu.output_pixel_size(1344, 768, by2) == (2688, 1536)
    assert lu.output_pixel_size(1344, 768, mp) == (1920, 1088)
    auto = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music = (ROOT / "music_video.py").read_text(encoding="utf-8")
    assert "output_pixel_size(width, height, upscale)" in auto
    assert "output_pixel_size(width, height, upscale)" in music
    assert "enhance_clip=enhance_clip" in auto
    assert "enhance_clip=enhance_clip" in music
    stitch = (ROOT / "stream_stitch.py").read_text(encoding="utf-8")
    assert "self.enhance_clip" in stitch
    assert "De-rope window" in (ROOT / "derope.py").read_text(encoding="utf-8")

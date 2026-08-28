import os

import numpy as np
from PIL import Image

from test_auto_chain import ROOT, _load


def test_disk_budget_uses_uncompressed_rgb_and_float32_image():
    ps = _load("png_sequence")
    assert ps.estimate_png_bytes(2, 4, 3) == 2 * 4 * 3 * 3
    assert ps.estimate_image_ram_bytes(2, 4, 3) == 2 * 4 * 3 * 12
    text = ps.disk_budget_message(243, 1344, 768, temp_dir="C:/temp", free_bytes=10)
    assert "H3 STUDIO — PNG DISK / IMAGE RAM" in text
    assert "243 frames at 1344x768" in text
    assert "NOT ENOUGH FREE SPACE" in text
    assert ps.format_bytes(1024 ** 3) == "1.00 GB"


def test_load_png_sequence_reads_numbered_frames(tmp_path):
    ps = _load("png_sequence")
    frames_dir = str(tmp_path)
    for i, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
        arr = np.zeros((2, 3, 3), dtype=np.uint8)
        arr[:, :] = color
        ps.save_png_frame(frames_dir, i, arr)
    ps.write_frames_fps(frames_dir, 24)
    out = ps.load_png_sequence(frames_dir)
    preview = ps.load_png_preview(frames_dir)
    assert tuple(preview.shape) == (1, 2, 3, 3)
    assert abs(float(preview[0, 0, 0, 2]) - 1.0) < 1e-5
    assert tuple(out.shape) == (3, 2, 3, 3)
    assert abs(float(out[0, 0, 0, 0]) - 1.0) < 1e-5
    assert abs(float(out[1, 0, 0, 1]) - 1.0) < 1e-5
    assert abs(float(out[2, 0, 0, 2]) - 1.0) < 1e-5
    assert ps.png_count(frames_dir) == 3


def test_close_loop_png_rewrites_sequence(tmp_path):
    import sys
    import types

    if "comfy.model_management" not in sys.modules:
        comfy = types.ModuleType("comfy")
        mm = types.ModuleType("comfy.model_management")
        mm.throw_exception_if_processing_interrupted = lambda: None
        sys.modules["comfy"] = comfy
        sys.modules["comfy.model_management"] = mm
    stitch = _load("stream_stitch")
    frames_dir = str(tmp_path / "frames")
    n = 10
    for i in range(n):
        arr = np.full((4, 4, 3), i, dtype=np.uint8)
        stitch.save_png_frame(frames_dir, i, arr)
    stitch.write_frames_fps(frames_dir, 24)
    out_dir, audio, stats, written = stitch._close_loop_png(frames_dir, 2, None, 15.0)
    assert out_dir == frames_dir
    assert audio is None
    assert written > 0
    assert stitch.png_count(frames_dir) == written
    Image.open(stitch.png_frame_path(frames_dir, 0)).close()


def test_progress_keeps_disk_budget_line():
    ps = _load("png_sequence")
    line = ps.budget_progress_line(447, 960, 544)
    assert "PNG ~" in line
    assert "IMAGE RAM ~" in line
    assert "447f 960x544" in line
    ps.pin_disk_budget("n1", line)
    text = ps.progress_display("n1", "Tracking faces on 447 frames")
    assert text.startswith(line)
    assert "Tracking faces on 447 frames" in text
    assert "\n" in text


def test_studio_nodes_warn_before_work_and_return_png_images():
    auto_chain = (ROOT / "auto_chain.py").read_text(encoding="utf-8")
    music_video = (ROOT / "music_video.py").read_text(encoding="utf-8")
    face = (ROOT / "face_refine" / "video_refine.py").read_text(encoding="utf-8")
    assert "warn_disk_budget" in auto_chain
    assert "warn_disk_budget" in music_video
    assert "warn_disk_budget" in face
    assert "pack_image_output" in auto_chain
    assert "pack_image_output" in music_video
    assert "pack_image_output" in face
    assert "require_image_ram" in auto_chain
    assert "require_image_ram" in music_video
    assert "require_image_ram" in face
    assert "save_images_to_disk_spec" in auto_chain
    assert "save_images_to_disk_spec" in music_video
    assert "save_images_to_disk_spec" in face
    assert "save_images_to_disk=False" in auto_chain
    assert "save_images_to_disk=False" in music_video
    assert "save_images_to_disk=False" in face
    assert "load_png_sequence" in face
    assert "load_png_preview" not in face
    assert 'RETURN_TYPES = ("IMAGE", "AUDIO", "STRING")' in face
    assert 'RETURN_NAMES = ("images", "audio", "report")' in face
    assert "out_audio = audio if audio is not None else _empty_audio()" in face
    assert "pack_image_output(result_images, write_png_dir, out_audio, report)" in face
    assert "def _source_media_path" in face
    assert "_audio_from_video" in face
    assert 'get_temp_directory()' in (ROOT / "png_sequence.py").read_text(encoding="utf-8")
    assert "refined.mp4" not in face
    assert "mux_audio_onto_mp4(result" not in music_video
    assert '"filename_prefix"' not in auto_chain
    assert '"filename_prefix"' not in music_video
    assert '"filename_prefix"' not in face
    assert '"crf"' not in auto_chain
    assert '"crf"' not in music_video
    assert "debug_videos=False" in face
    assert "seamless_loop=False" in face
    assert "send_node_progress" in auto_chain
    assert "send_node_progress" in face
    assert "_mux_chunk" not in face
    assert "torchaudio.save" not in face
    assert "node_temp_frames_dir" in auto_chain
    assert "node_temp_frames_dir" in music_video
    assert "frames_dir=out_frames" in auto_chain
    assert "frames_dir=out_frames" in music_video
    assert "dest = None if file_mode else source" not in face
    assert "_source_fingerprint" in face
    assert "source_fp" in face
    assert "if images is not None:" in face


def test_pack_image_output_has_no_node_preview():
    ps = _load("png_sequence")
    png = (ROOT / "png_sequence.py").read_text(encoding="utf-8")
    face = (ROOT / "face_refine" / "video_refine.py").read_text(encoding="utf-8")
    assert "pack_png_node_output" not in png
    assert "png_ui_entries" not in png
    assert '"animated"' not in png
    assert "_send_video_preview" not in face
    assert "_media_rel" not in face
    assert '"animated"' not in face
    payload = ps.pack_image_output(object(), "frames", "info")
    assert "ui" not in payload
    assert payload["result"][1] == "info"
    with_audio = ps.pack_image_output(object(), "frames", {"sample_rate": 44100}, "info")
    assert with_audio["result"][1]["sample_rate"] == 44100
    assert with_audio["result"][2] == "info"


def test_node_temp_frames_dir_wipes_previous_run(tmp_path):
    import sys
    import types

    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_temp_directory = lambda: str(tmp_path)
    sys.modules["folder_paths"] = folder_paths
    ps = _load("png_sequence")
    first = ps.node_temp_frames_dir("video/h3_auto_chain", unique_id="node12")
    marker = os.path.join(first, "00000000.png")
    open(marker, "w", encoding="utf-8").close()
    second = ps.node_temp_frames_dir("video/h3_auto_chain", unique_id="node12")
    assert first == second
    assert not os.path.isfile(marker)
    assert os.path.isfile(os.path.join(second, "fps.txt"))


def test_require_image_ram_errors_when_short():
    ps = _load("png_sequence")
    orig = ps.available_ram_bytes
    ps.available_ram_bytes = lambda: 100
    try:
        try:
            ps.require_image_ram(100, 1920, 1080, save_to_disk=False)
        except RuntimeError as exc:
            assert "Enable save_images_to_disk" in str(exc)
            assert "1920x1080" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
        ps.require_image_ram(100, 1920, 1080, save_to_disk=True)
        ps.available_ram_bytes = lambda: 10 ** 18
        ps.require_image_ram(2, 4, 3, save_to_disk=False)
    finally:
        ps.available_ram_bytes = orig


def test_save_images_to_disk_widget_defaults_off():
    ps = _load("png_sequence")
    kind, opts = ps.save_images_to_disk_spec()
    assert kind == "BOOLEAN"
    assert opts["default"] is False


def _face_refine_src():
    return (ROOT / "face_refine" / "video_refine.py").read_text(encoding="utf-8")


def _exec_face_slice(start_marker, end_marker, ns):
    text = _face_refine_src()
    start = text.index(start_marker)
    end = text.index(end_marker, start + 1)
    exec(text[start:end], ns)
    return ns


def test_audio_sidecar_prefers_song_mp4(tmp_path):
    ns = _exec_face_slice("def _audio_sidecar(", "def _source_media_path(", {"os": os})
    frames = tmp_path / "run_frames"
    frames.mkdir()
    song = tmp_path / "run_song.mp4"
    song.write_bytes(b"song")
    (tmp_path / "other.mp4").write_bytes(b"other")
    got = ns["_audio_sidecar"](str(frames))
    assert os.path.normcase(os.path.abspath(got)) == os.path.normcase(str(song.resolve()))


def test_source_media_path_uses_video_path_file_and_png_sidecar(tmp_path):
    ns = {"os": os}
    _exec_face_slice("def _resolve_media_path(", "_IMAGE_EXTS = ", ns)
    _exec_face_slice("def _audio_sidecar(", "def _empty_audio(", ns)
    ns["_VideoFrames"] = type("VF", (), {})
    ns["_ImageSeqFrames"] = type("IS", (), {})
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"muxed")
    got = ns["_source_media_path"](object(), str(mp4))
    assert os.path.normcase(os.path.abspath(got)) == os.path.normcase(str(mp4.resolve()))

    frames = tmp_path / "clip_frames"
    frames.mkdir()
    seq = ns["_ImageSeqFrames"]()
    seq.path = str(frames)
    got = ns["_source_media_path"](seq, "")
    assert os.path.normcase(os.path.abspath(got)) == os.path.normcase(str(mp4.resolve()))


def test_empty_audio_is_comfy_audio_dict():
    import torch
    ns = _exec_face_slice("def _empty_audio(", "def _ffmpeg_exe(", {"torch": torch})
    out = ns["_empty_audio"]()
    assert out["sample_rate"] == 44100
    assert tuple(out["waveform"].shape) == (1, 2, 1)


def test_audio_from_video_loads_muxed_soundtrack(tmp_path):
    import shutil
    import struct
    import subprocess
    import wave

    import pytest
    import torch

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not on PATH")
    png = tmp_path / "frame.png"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(png)
    wav = tmp_path / "tone.wav"
    sr = 44100
    n = sr // 10
    with wave.open(str(wav), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(struct.pack("<" + "h" * n, *([8000] * n)))
    mp4 = tmp_path / "clip.mp4"
    r = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-t", "0.2", "-i", str(png), "-i", str(wav),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        pytest.skip(r.stderr[-400:] if r.stderr else "ffmpeg mux failed")
    ns = {
        "os": os, "shutil": shutil, "subprocess": subprocess,
        "wave": wave, "np": np, "torch": torch,
    }
    _exec_face_slice("def _ffmpeg_exe(", "class _ImageSeqFrames", ns)
    _exec_face_slice("def _audio_from_video(", "def _progress(", ns)
    out = ns["_audio_from_video"](str(mp4), str(tmp_path / "out.wav"))
    assert int(out["sample_rate"]) == 44100
    assert int(out["waveform"].shape[-1]) > 1000

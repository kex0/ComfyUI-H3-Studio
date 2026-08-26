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
    assert 'get_temp_directory()' in (ROOT / "png_sequence.py").read_text(encoding="utf-8")
    assert "refined.mp4" not in face
    assert "mux_audio_onto_mp4(result" not in music_video
    assert '"filename_prefix"' not in auto_chain
    assert '"filename_prefix"' not in music_video
    assert '"filename_prefix"' not in face
    assert '"crf"' not in auto_chain
    assert '"crf"' not in music_video
    assert "debug_videos=False" in face
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

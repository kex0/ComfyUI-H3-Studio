"""Load a song for Music Video: full AUDIO plus confirm-format lyrics."""

from __future__ import annotations

import hashlib
import os

import av
import folder_paths
import torch

from .lyric_timing import parse_time_range

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}


def _input_audio_files():
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    files = []
    try:
        names = folder_paths.filter_files_content_types(os.listdir(input_dir), ["audio", "video"])
    except Exception:
        names = [
            name for name in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, name))
            and os.path.splitext(name)[1].lower() in AUDIO_EXT
        ]
    files = sorted(names)
    return files or [""]


def _f32_pcm(wav: torch.Tensor) -> torch.Tensor:
    if wav.dtype.is_floating_point:
        return wav
    if wav.dtype == torch.int16:
        return wav.float() / (2 ** 15)
    if wav.dtype == torch.int32:
        return wav.float() / (2 ** 31)
    return wav.float()


def load_song_audio(path: str) -> dict:
    with av.open(path) as container:
        if not container.streams.audio:
            raise ValueError(f"no audio stream in {path}")
        stream = container.streams.audio[0]
        sample_rate = int(stream.codec_context.sample_rate)
        channels = int(stream.channels or 1)
        frames = []
        for frame in container.decode(streams=stream.index):
            buf = torch.from_numpy(frame.to_ndarray())
            if buf.ndim == 1:
                buf = buf.unsqueeze(0)
            if buf.shape[0] != channels:
                buf = buf.view(-1, channels).t()
            frames.append(buf)
        if not frames:
            raise ValueError(f"no audio frames in {path}")
        waveform = _f32_pcm(torch.cat(frames, dim=1))
    return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}


class H3StudioLoadSong:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": (_input_audio_files(),),
                "lyrics": ("STRING", {
                    "multiline": True, "default": "", "dynamicPrompts": False,
                    "tooltip": (
                        "Confirm-format LRC: one [start-end] line per phrase. "
                        "Same text the skill waits on (song.confirm.lrc)."
                    ),
                }),
                "loop": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "A/B preview loop. Paste 116.167-123.458 or 02:05.375-02:09.040 "
                        "to set the timeline handles. Does not crop AUDIO."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "FLOAT")
    RETURN_NAMES = ("audio", "lyrics", "duration")
    FUNCTION = "load_song"
    CATEGORY = "H3 Studio"

    def load_song(self, audio, lyrics="", loop=""):
        if loop and str(loop).strip():
            parse_time_range(loop)
        path = folder_paths.get_annotated_filepath(audio)
        loaded = load_song_audio(path)
        duration = float(loaded["waveform"].shape[-1]) / float(loaded["sample_rate"])
        return (loaded, str(lyrics or ""), duration)

    @classmethod
    def IS_CHANGED(cls, audio, lyrics="", loop=""):
        path = folder_paths.get_annotated_filepath(audio)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            digest.update(handle.read())
        digest.update(str(lyrics or "").encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, audio, lyrics="", loop=""):
        if not folder_paths.exists_annotated_filepath(audio):
            return f"Invalid audio file: {audio}"
        if loop and str(loop).strip():
            try:
                parse_time_range(loop)
            except ValueError as exc:
                return str(exc)
        return True

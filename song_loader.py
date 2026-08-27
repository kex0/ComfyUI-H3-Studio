"""Load a song for Music Video: full AUDIO plus confirm-format lyrics."""

from __future__ import annotations

import asyncio
import hashlib
import os

import av
import folder_paths
import torch

from .lyric_align import resolve_timed_lyrics
from .lyric_timing import parse_time_range, split_plain_lyric_lines

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}


def input_audio_files():
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    try:
        names = folder_paths.filter_files_content_types(os.listdir(input_dir), ["audio", "video"])
    except Exception:
        names = [
            name for name in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, name))
            and os.path.splitext(name)[1].lower() in AUDIO_EXT
        ]
    return sorted(names) or [""]


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
                "audio": (input_audio_files(),),
                "lyrics": ("STRING", {
                    "multiline": True, "default": "", "dynamicPrompts": False,
                    "tooltip": (
                        "Required. Untimed lines are timed on Time lyrics / first queue. "
                        "Already-stamped confirm LRC ([start-end] text) is left as-is."
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

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("song", "lyrics")
    FUNCTION = "load_song"
    CATEGORY = "H3 Studio"

    def load_song(self, audio, lyrics="", loop=""):
        if loop and str(loop).strip():
            parse_time_range(loop)
        path = folder_paths.get_annotated_filepath(audio)
        loaded = load_song_audio(path)
        timed = resolve_timed_lyrics(
            path, lyrics, waveform=loaded["waveform"], sample_rate=loaded["sample_rate"],
        )
        return {"ui": {"lyrics": [timed]}, "result": (loaded, timed)}

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
        if not split_plain_lyric_lines(lyrics):
            return "h3_studio: lyrics are required"
        if loop and str(loop).strip():
            try:
                parse_time_range(loop)
            except ValueError as exc:
                return str(exc)
        return True


def register_song_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    instance = getattr(PromptServer, "instance", None)
    if instance is None or getattr(instance, "_h3_studio_song_routes", False):
        return
    instance._h3_studio_song_routes = True

    @instance.routes.post("/h3_studio_song/align")
    async def h3_studio_song_align(request):
        body = await request.json()
        filename = str(body.get("filename") or "").strip()
        lyrics = str(body.get("lyrics") or "")
        if not folder_paths.exists_annotated_filepath(filename):
            return web.json_response({"error": f"Invalid audio file: {filename}"}, status=400)
        path = folder_paths.get_annotated_filepath(filename)
        try:
            timed = await asyncio.get_running_loop().run_in_executor(
                None, resolve_timed_lyrics, path, lyrics,
            )
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"lyrics": timed})


register_song_routes()

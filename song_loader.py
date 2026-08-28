"""Load a song for Music Video: full AUDIO plus confirm-format lyrics."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os

import av
import folder_paths
import torch

from .lyric_align import refine_confirm_lyrics, resolve_timed_lyrics
from .lyric_timing import (
    assign_lyrics_to_windows, dump_aligned_lyrics, format_lrc,
    format_music_video_skeleton, parse_timestamped_lyrics, split_plain_lyric_lines,
)
from .node_help import NODE_HELP

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
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("song", "lyrics")
    FUNCTION = "load_song"
    CATEGORY = "H3 Studio"
    DESCRIPTION = NODE_HELP["H3StudioLoadSong"]

    def load_song(self, audio, lyrics="", **_kwargs):
        path = folder_paths.get_annotated_filepath(audio)
        loaded = load_song_audio(path)
        timed = resolve_timed_lyrics(
            path, lyrics, waveform=loaded["waveform"], sample_rate=loaded["sample_rate"],
        )
        return {"ui": {"lyrics": [timed]}, "result": (loaded, timed)}

    @classmethod
    def IS_CHANGED(cls, audio, lyrics="", **_kwargs):
        path = folder_paths.get_annotated_filepath(audio)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            digest.update(handle.read())
        digest.update(str(lyrics or "").encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, audio, lyrics="", **_kwargs):
        if not folder_paths.exists_annotated_filepath(audio):
            return f"Invalid audio file: {audio}"
        if not split_plain_lyric_lines(lyrics):
            return "h3_studio: lyrics are required"
        return True


def resolve_song_file_path(filename="", path=""):
    """Resolve a Comfy input audio name (or dump path) to an existing file."""
    seen = []
    for raw in (filename, path):
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.append(text)
        candidates = [text]
        base = os.path.basename(text.replace("\\", "/"))
        if base and base not in candidates:
            candidates.append(base)
        for cand in candidates:
            if not folder_paths.exists_annotated_filepath(cand):
                continue
            resolved = folder_paths.get_annotated_filepath(cand)
            if os.path.isfile(resolved):
                return resolved
    return ""


def _song_path_from_request(body=None, filename=""):
    payload = body or {}
    return resolve_song_file_path(
        filename or payload.get("filename") or "",
        payload.get("path") or "",
    )


def _plan_duration(raw) -> float:
    text = str(raw if raw is not None else 10).strip().rstrip("sS")
    return float(text or 10)


def plan_music_video(path, lyrics, duration=10.0) -> dict:
    """Letter-refine confirm LRC and emit CLIP skeleton for the agent skill."""
    if not parse_timestamped_lyrics(lyrics):
        raise ValueError("h3_studio: lyrics need [start-end] stamps before plan")
    loaded = load_song_audio(path)
    song_seconds = float(loaded["waveform"].shape[-1]) / float(loaded["sample_rate"])
    max_seconds = _plan_duration(duration)
    refined = refine_confirm_lyrics(
        loaded["waveform"], loaded["sample_rate"], lyrics, song_seconds=song_seconds,
    )
    windows = assign_lyrics_to_windows(refined, song_seconds, max_seconds)
    words = json.loads(dump_aligned_lyrics(
        refined, song_seconds=song_seconds, source="wav2vec2-refine",
    ))
    return {
        "song_seconds": song_seconds,
        "source": "wav2vec2-refine",
        "lyrics": format_lrc(refined),
        "words": words,
        "skeleton": format_music_video_skeleton(windows, max_seconds),
    }


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

    @instance.routes.get("/h3_studio_song/path")
    async def h3_studio_song_path(request):
        filename = str(request.query.get("filename") or "").strip()
        path = resolve_song_file_path(filename)
        if not path:
            return web.json_response({"error": f"Invalid audio file: {filename}"}, status=400)
        return web.json_response({"path": path, "filename": os.path.basename(path)})

    @instance.routes.post("/h3_studio_song/align")
    async def h3_studio_song_align(request):
        body = await request.json()
        lyrics = str(body.get("lyrics") or "")
        path = _song_path_from_request(body)
        if not path:
            return web.json_response({"error": "Invalid audio file"}, status=400)
        try:
            timed = await asyncio.get_running_loop().run_in_executor(
                None, resolve_timed_lyrics, path, lyrics,
            )
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"lyrics": timed})

    def _refine_confirm(path, lyrics):
        loaded = load_song_audio(path)
        refined = refine_confirm_lyrics(
            loaded["waveform"], loaded["sample_rate"], lyrics,
        )
        return format_lrc(refined)

    @instance.routes.post("/h3_studio_song/refine")
    async def h3_studio_song_refine(request):
        body = await request.json()
        lyrics = str(body.get("lyrics") or "")
        path = _song_path_from_request(body)
        if not path:
            return web.json_response({"error": "Invalid audio file"}, status=400)
        if not parse_timestamped_lyrics(lyrics):
            return web.json_response(
                {"error": "h3_studio: lyrics need [start-end] stamps before refine"},
                status=400,
            )
        try:
            timed = await asyncio.get_running_loop().run_in_executor(
                None, _refine_confirm, path, lyrics,
            )
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"lyrics": timed})

    @instance.routes.post("/h3_studio_song/plan")
    async def h3_studio_song_plan(request):
        body = await request.json()
        lyrics = str(body.get("lyrics") or "")
        path = _song_path_from_request(body)
        if not path:
            return web.json_response({"error": "Invalid audio file"}, status=400)
        if not parse_timestamped_lyrics(lyrics):
            return web.json_response(
                {"error": "h3_studio: lyrics need [start-end] stamps before plan"},
                status=400,
            )
        try:
            planned = await asyncio.get_running_loop().run_in_executor(
                None, plan_music_video, path, lyrics, body.get("duration"),
            )
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(planned)


register_song_routes()

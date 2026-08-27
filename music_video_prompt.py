"""Parse the H3 Studio Music Video prompt document.

Preferred shape (from /prompt_minimax_h3_music_video):

    H3 Studio prompt
    mode: music_video
    duration: 10.125
    segments: 2

    ## Clip 1 — Start
    time: 0.000-9.125
    duration_seconds: 10.125
    slice: 0.000
    audio: 0.000-10.125
    lyrics:
    ...
    subject_definitions:
    <Subject 1> is ...
    <Audio 1> is the source-song slice covering ...
    summary:
    ...

Legacy `h3_music_video: 1` / CLIP N / prompt: documents still parse.
"""

from __future__ import annotations

import re

try:
    from .song_math import (
        MUSIC_MAX_DURATION_SECONDS, MUSIC_MAX_SEGMENTS, MUSIC_MIN_DURATION_SECONDS,
        PLANNING_HEAD_FRAMES, PLANNING_TAIL_FRAMES, clamp_max_duration_seconds,
        coverage_clip_count, grid_duration_seconds, grid_frame_count,
        planning_join_geometry,
    )
except ImportError:  # direct test import from package directory
    from song_math import (
        MUSIC_MAX_DURATION_SECONDS, MUSIC_MAX_SEGMENTS, MUSIC_MIN_DURATION_SECONDS,
        PLANNING_HEAD_FRAMES, PLANNING_TAIL_FRAMES, clamp_max_duration_seconds,
        coverage_clip_count, grid_duration_seconds, grid_frame_count,
        planning_join_geometry,
    )

_HEADER_KEY = re.compile(
    r"^(h3_music_video|max_duration_seconds|duration_seconds|clip_count)\s*:\s*(.+?)\s*$",
    re.I,
)
_CLIP_HEAD = re.compile(r"^CLIP\s+(\d+)\s*$", re.I)
_TIME = re.compile(r"^time\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)\s*$", re.I)
_DURATION = re.compile(r"^duration_seconds\s*:\s*([0-9.]+)\s*$", re.I)
_LYRICS = re.compile(r"^lyrics\s*:\s*(.*)$", re.I)
_PROMPT = re.compile(r"^prompt\s*:\s*(.*)$", re.I)


def parse_music_video_prompt(text: str) -> dict:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError("h3_music_video: structured prompt is empty")

    try:
        from .prompt_document import looks_like_unified, parse_prompt_document
    except ImportError:
        from prompt_document import looks_like_unified, parse_prompt_document

    if looks_like_unified(raw):
        return _from_unified_document(parse_prompt_document(raw, mode="music_video"))

    parts = re.split(r"\n---\s*\n", raw, maxsplit=1)
    header_text = parts[0]
    body = parts[1] if len(parts) > 1 else ""

    header = {}
    for line in header_text.split("\n"):
        m = _HEADER_KEY.match(line.strip())
        if not m:
            continue
        header[m.group(1).lower()] = m.group(2).strip()

    if "h3_music_video" not in header:
        raise ValueError(
            "h3_music_video: prompt must start with 'h3_music_video: 1' "
            "(use /prompt_minimax_h3_music_video)"
        )
    try:
        version = int(float(header["h3_music_video"]))
    except ValueError as exc:
        raise ValueError("h3_music_video: invalid header version") from exc
    if version != 1:
        raise ValueError(f"h3_music_video: unsupported document version {version}")

    max_raw = header.get("max_duration_seconds", header.get("duration_seconds"))
    if max_raw is None:
        raise ValueError("h3_music_video: header is missing max_duration_seconds")
    try:
        max_duration_seconds = float(max_raw)
    except ValueError as exc:
        raise ValueError("h3_music_video: max_duration_seconds must be a number") from exc
    max_duration_seconds = grid_duration_seconds(clamp_max_duration_seconds(max_duration_seconds))

    if "clip_count" not in header:
        raise ValueError("h3_music_video: header is missing clip_count")
    try:
        clip_count = int(header["clip_count"])
    except ValueError as exc:
        raise ValueError("h3_music_video: clip_count must be an integer") from exc

    clips = _parse_clip_blocks(body if body else header_text)
    if not clips:
        raise ValueError("h3_music_video: no CLIP blocks found")
    if len(clips) != clip_count:
        raise ValueError(
            f"h3_music_video: header clip_count={clip_count} but found {len(clips)} CLIP block(s)"
        )
    expected_indices = list(range(1, clip_count + 1))
    got_indices = [c["index"] for c in clips]
    if got_indices != expected_indices:
        raise ValueError(
            f"h3_music_video: CLIP blocks must be numbered 1..{clip_count} in order, got {got_indices}"
        )
    for clip in clips:
        if not str(clip["prompt"]).strip():
            raise ValueError(f"h3_music_video: CLIP {clip['index']} prompt is empty")
        raw_duration = clip.get("duration_seconds")
        if raw_duration is None:
            clip["duration_seconds"] = max_duration_seconds
        else:
            clip["duration_seconds"] = grid_duration_seconds(float(raw_duration))
        clip["grid_frames"] = grid_frame_count(clip["duration_seconds"])

    return {
        "version": version,
        "duration_seconds": max_duration_seconds,
        "max_duration_seconds": max_duration_seconds,
        "clip_count": clip_count,
        "clips": clips,
    }


def _from_unified_document(parsed: dict) -> dict:
    try:
        from .prompt_document import expand_clip, story_clips
    except ImportError:
        from prompt_document import expand_clip, story_clips
    story = story_clips(parsed)
    if not story:
        raise ValueError("h3_music_video: no CLIP / ## Clip sections found")
    max_raw = parsed.get("duration")
    if max_raw is None:
        raise ValueError("h3_music_video: unified prompt is missing duration / max_duration_seconds")
    max_duration_seconds = grid_duration_seconds(clamp_max_duration_seconds(float(max_raw)))
    clips = []
    for item in story:
        body = expand_clip(parsed, item["index"], song_audio=True)
        if not str(body).strip():
            raise ValueError(f"h3_music_video: CLIP {item['index']} prompt is empty")
        raw_duration = item.get("duration_seconds")
        duration_seconds = (
            max_duration_seconds if raw_duration is None
            else grid_duration_seconds(float(raw_duration))
        )
        clips.append({
            "index": int(item["index"]),
            "time": item.get("time"),
            "duration_seconds": duration_seconds,
            "slice": item.get("slice"),
            "audio": item.get("audio"),
            "lyrics": item.get("lyrics") or "",
            "prompt": body,
            "grid_frames": grid_frame_count(duration_seconds),
        })
    clip_count = int(parsed.get("segments") or len(clips))
    if clip_count != len(clips):
        raise ValueError(
            f"h3_music_video: header clip_count={clip_count} but found {len(clips)} CLIP block(s)"
        )
    expected = list(range(1, clip_count + 1))
    got = [clip["index"] for clip in clips]
    if got != expected:
        raise ValueError(
            f"h3_music_video: CLIP blocks must be numbered 1..{clip_count} in order, got {got}"
        )
    return {
        "version": 1,
        "duration_seconds": max_duration_seconds,
        "max_duration_seconds": max_duration_seconds,
        "clip_count": clip_count,
        "clips": clips,
    }


def validate_music_video_prompt(
    parsed: dict, song_seconds: float, duration_seconds: float,
    head_frames: int = PLANNING_HEAD_FRAMES,
    tail_frames: int = PLANNING_TAIL_FRAMES,
    stop_after_clip: int = 0,
) -> None:
    n = int(parsed["clip_count"])
    if n < 1 or n > MUSIC_MAX_SEGMENTS:
        raise ValueError(f"h3_music_video: clip_count must be 1..{MUSIC_MAX_SEGMENTS}, got {n}")
    max_s = float(parsed["max_duration_seconds"])
    node_max = grid_duration_seconds(clamp_max_duration_seconds(duration_seconds))
    if grid_frame_count(max_s) != grid_frame_count(node_max):
        raise ValueError(
            f"h3_music_video: prompt max_duration_seconds={max_s} "
            f"snaps to {grid_frame_count(max_s)} frames, but the node duration snaps to "
            f"{grid_frame_count(node_max)}. Use the same max duration in the skill and on the node."
        )
    max_frames = grid_frame_count(max_s)
    min_frames = grid_frame_count(MUSIC_MIN_DURATION_SECONDS)
    clips = parsed["clips"]
    stop_after = int(stop_after_clip or 0)
    if stop_after < 0:
        raise ValueError(f"h3_music_video: stop_after_clip must be >= 0, got {stop_after}")
    if stop_after > n:
        raise ValueError(
            f"h3_music_video: stop_after_clip={stop_after} exceeds prompt clip_count={n}"
        )
    for i, clip in enumerate(clips):
        grid = int(clip["grid_frames"])
        if grid > max_frames:
            raise ValueError(
                f"h3_music_video: CLIP {clip['index']} duration_seconds={clip['duration_seconds']} "
                f"exceeds max {max_s}s"
            )
        is_last = i == n - 1 or (stop_after > 0 and int(clip["index"]) == stop_after)
        if not is_last and grid < min_frames:
            raise ValueError(
                f"h3_music_video: CLIP {clip['index']} duration_seconds={clip['duration_seconds']} "
                f"is below the {MUSIC_MIN_DURATION_SECONDS:g}s floor"
            )
    if max_s > MUSIC_MAX_DURATION_SECONDS + 1e-9:
        raise ValueError(
            f"h3_music_video: max duration {max_s}s exceeds the {MUSIC_MAX_DURATION_SECONDS:g}s cap"
        )
    if stop_after > 0:
        # Partial / test runs stitch only through this clip; full-song coverage is not required.
        return
    needed = coverage_clip_count(
        song_seconds, max_s, head_frames=head_frames, tail_frames=tail_frames,
    )
    if n < needed:
        geom = planning_join_geometry(max_frames, int(head_frames), int(tail_frames))
        raise ValueError(
            f"h3_music_video: prompt clip_count={n} is too few to cover {song_seconds:.3f}s "
            f"after head/tail trims; need at least {needed} clips "
            f"(joins drop ~{int(geom['head_frames'])}+{int(geom['tail_frames'])} frames each). "
            "Re-run /prompt_minimax_h3_music_video. Do not use ceil(song / D_grid). "
            "For a short resume test, set stop_after_clip to the last clip you want (e.g. 2)."
        )


def _parse_clip_blocks(body: str) -> list[dict]:
    lines = body.split("\n")
    starts = []
    for i, line in enumerate(lines):
        m = _CLIP_HEAD.match(line.strip())
        if m:
            starts.append((i, int(m.group(1))))
    if not starts:
        return []

    clips = []
    for j, (start, index) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        block_lines = lines[start + 1:end]
        clips.append(_parse_one_clip(index, block_lines))
    return clips


def _parse_one_clip(index: int, lines: list[str]) -> dict:
    time_range = None
    duration_seconds = None
    lyrics_parts = []
    prompt_parts = []
    mode = None
    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            continue
        if mode != "prompt":
            tm = _TIME.match(stripped)
            if tm:
                time_range = (float(tm.group(1)), float(tm.group(2)))
                continue
            dm = _DURATION.match(stripped)
            if dm:
                duration_seconds = float(dm.group(1))
                continue
            lm = _LYRICS.match(line if line.startswith("lyrics") else stripped)
            if lm is None:
                lm = _LYRICS.match(stripped)
            if lm:
                mode = "lyrics"
                rest = lm.group(1)
                if rest.strip():
                    lyrics_parts.append(rest.rstrip())
                continue
            pm = _PROMPT.match(stripped)
            if pm:
                mode = "prompt"
                rest = pm.group(1)
                if rest.strip():
                    prompt_parts.append(rest.rstrip())
                continue
        if mode == "lyrics":
            prompt_try = _PROMPT.match(stripped)
            if prompt_try:
                mode = "prompt"
                rest = prompt_try.group(1)
                if rest.strip():
                    prompt_parts.append(rest.rstrip())
                continue
            lyrics_parts.append(line.rstrip())
        elif mode == "prompt":
            prompt_parts.append(line.rstrip())

    lyrics = "\n".join(lyrics_parts).strip()
    prompt = "\n".join(prompt_parts).strip()
    return {
        "index": int(index),
        "time": time_range,
        "duration_seconds": duration_seconds,
        "lyrics": lyrics,
        "prompt": prompt,
    }

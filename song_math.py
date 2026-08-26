"""H3-grid song slicing and kept-frame cursor math for Music Video.

Pure Python: clip count, slice starts, mux spans. No ComfyUI imports.
The song is the master timeline. Video is generated to follow it; final audio
is the original song, never H3's reconstructed soundtrack.

Cursor rule: after handover, advance by kept picture frames only, then start
the next slice ``head`` frames earlier so the continuation overlap still
covers the song at the join. Muxed spans are then contiguous in the master.
"""

from __future__ import annotations

import math

try:
    from .latent_math import (
        FPS, align_frame_count, phase_aligned_extended_context_slice, video_latent_t,
    )
    from .release_utils import duration_to_requested_frames
except ImportError:  # direct test import from package directory
    from latent_math import (
        FPS, align_frame_count, phase_aligned_extended_context_slice, video_latent_t,
    )
    from release_utils import duration_to_requested_frames

MUSIC_MAX_SEGMENTS = 48
CLIP_COUNT_TOLERANCE = 1
# Requested Continue context and minimum join discard. Actual head/tail come from
# ``planning_join_geometry`` (same ``phase_aligned_extended`` cut Music Video uses).
# On current H3 grids that snaps a 1 s tail to 26 frames and extends head to 30.
MUSIC_CONTEXT_FRAMES = 22
MUSIC_JOIN_TAIL_FRAMES = 24
PLANNING_HEAD_FRAMES = MUSIC_CONTEXT_FRAMES
PLANNING_TAIL_FRAMES = MUSIC_JOIN_TAIL_FRAMES
MUSIC_MIN_DURATION_SECONDS = 5.0
MUSIC_MAX_DURATION_SECONDS = 15.0
# Lyric starts in the last 1.5 s of kept picture used to move the whole line
# to the next clip. Joins now overlap by 1 s instead; a line is listed on every
# CLIP whose kept ``time:`` overlaps it, never on a CLIP it already finished
# before.
LYRIC_BOUNDARY_MARGIN_FRAMES = 36
LYRIC_END_PAD_FRAMES = 0


def planning_join_geometry(
    grid_frames: int,
    context_frames: int = MUSIC_CONTEXT_FRAMES,
    min_tail_frames: int = MUSIC_JOIN_TAIL_FRAMES,
):
    """Head/tail Music Video actually uses for a join on this H3 grid.

    Matches ``_apply_music_join_tail`` when freeze_tail <= min_tail_frames:
    discard at least 1 s, then Continue takes phase-aligned context from before
    that cut. A longer freeze still adds extra discard at generate time.
    """
    sl = phase_aligned_extended_context_slice(
        video_latent_t(int(grid_frames)),
        int(context_frames),
        desired_tail_frames=max(0, int(min_tail_frames)),
    )
    return {
        "head_frames": int(sl["actual_context_frames"]),
        "tail_frames": int(sl["ignored_tail_frames"]),
        "source_start_frame": int(sl["source_start_frame"]),
        "source_end_frame": int(sl["source_end_frame"]),
    }


def grid_frame_count(duration_seconds: float, fps: float = FPS) -> int:
    """Actual H3 frames for a requested duration (10.0 s -> 243)."""
    requested = duration_to_requested_frames(duration_seconds, fps=fps)
    return align_frame_count(requested)


def grid_duration_seconds(duration_seconds: float, fps: float = FPS) -> float:
    return grid_frame_count(duration_seconds, fps=fps) / float(fps)


def song_frame_count(song_seconds: float, fps: float = FPS) -> int:
    song = float(song_seconds)
    if not math.isfinite(song) or song <= 0:
        raise ValueError("h3_music_video: song duration must be a positive finite number")
    return max(1, int(round(song * float(fps))))


def grid_clip_count(song_seconds: float, duration_seconds: float, fps: float = FPS) -> int:
    """``ceil(song / D_grid)`` ignoring handover trims. Too small for a full-song stitch."""
    grid_s = grid_duration_seconds(duration_seconds, fps=fps)
    return max(1, math.ceil(float(song_seconds) / grid_s - 1e-12))


def coverage_clip_count(
    song_seconds: float,
    duration_seconds: float,
    head_frames: int | None = None,
    tail_frames: int | None = None,
    extra: int = 0,
    fps: float = FPS,
) -> int:
    """Clips needed so kept picture can cover the song after head/tail trims.

    Clip 1 keeps ``D - tail``. Each later join keeps about ``D - head - tail``.
    Closed form: ``D + (N-1)*(D-head-tail)``. Defaults snap the requested
    Continue context / 1 s join through ``planning_join_geometry``.
    """
    grid = grid_frame_count(duration_seconds, fps=fps)
    song_frames = song_frame_count(song_seconds, fps=fps)
    if song_frames <= grid:
        return 1
    geom = planning_join_geometry(
        grid,
        MUSIC_CONTEXT_FRAMES if head_frames is None else int(head_frames),
        MUSIC_JOIN_TAIL_FRAMES if tail_frames is None else int(tail_frames),
    )
    head = max(0, int(geom["head_frames"]))
    tail = max(0, int(geom["tail_frames"]))
    body = grid - head - tail
    if body < 1:
        raise ValueError(
            f"h3_music_video: head ({head}) + tail ({tail}) leave no kept frames in a {grid}-frame clip"
        )
    n = 1 + math.ceil((song_frames - grid) / body - 1e-12)
    n = n + max(0, int(extra))
    if n > MUSIC_MAX_SEGMENTS:
        raise ValueError(
            f"h3_music_video: song {song_seconds:.3f}s needs {n} clips after head/tail trims, "
            f"but the cap is {MUSIC_MAX_SEGMENTS}; use a longer per-clip duration"
        )
    return max(1, n)


def expected_clip_count(
    song_seconds: float,
    duration_seconds: float,
    fps: float = FPS,
    head_frames: int | None = None,
    tail_frames: int | None = None,
) -> int:
    """Minimum clips to cover the song after typical stitch trims."""
    return coverage_clip_count(
        song_seconds, duration_seconds, head_frames=head_frames,
        tail_frames=tail_frames, extra=0, fps=fps,
    )


def clamp_max_duration_seconds(duration_seconds: float) -> float:
    requested = float(duration_seconds)
    if not math.isfinite(requested) or requested <= 0:
        raise ValueError("h3_music_video: max duration must be a positive finite number")
    if requested > MUSIC_MAX_DURATION_SECONDS + 1e-9:
        raise ValueError(
            f"h3_music_video: max duration {requested:g}s exceeds the {MUSIC_MAX_DURATION_SECONDS:g}s cap"
        )
    return min(requested, MUSIC_MAX_DURATION_SECONDS)


def h3_grid_steps(
    min_seconds: float = MUSIC_MIN_DURATION_SECONDS,
    max_seconds: float = MUSIC_MAX_DURATION_SECONDS,
    fps: float = FPS,
):
    """Ascending H3-grid lengths from floor to requested max (inclusive snap)."""
    lo = max(float(min_seconds), MUSIC_MIN_DURATION_SECONDS)
    hi = clamp_max_duration_seconds(max_seconds)
    if hi + 1e-9 < MUSIC_MIN_DURATION_SECONDS:
        raise ValueError(
            f"h3_music_video: max duration {hi:g}s is below the {MUSIC_MIN_DURATION_SECONDS:g}s floor"
        )
    n = grid_frame_count(lo, fps=fps)
    cap = grid_frame_count(hi, fps=fps)
    steps = []
    while n <= cap:
        steps.append({"frames": n, "seconds": n / float(fps)})
        n += 17
    if not steps:
        steps.append({"frames": cap, "seconds": cap / float(fps)})
    return steps


def _lyric_span_frames(lyric_spans, lyric_starts, fps: float) -> list[tuple[int, int]]:
    src = lyric_spans
    if not src and lyric_starts:
        src = [(t, t) for t in lyric_starts]
    spans = []
    for raw in src or []:
        if isinstance(raw, dict):
            start = float(raw["start"])
            end = raw.get("end")
            end = start if end is None else float(end)
        else:
            start = float(raw[0])
            end = float(raw[1]) if len(raw) > 1 else start
        if not math.isfinite(start) or start < 0:
            continue
        if not math.isfinite(end) or end < start:
            end = start
        start_f = int(round(start * float(fps)))
        end_f = int(round(end * float(fps)))
        spans.append((start_f, max(start_f, end_f)))
    return spans


def _choose_clip_grid(
    slice_start: int,
    song_frames: int,
    steps,
    lyric_spans,
    tail_frames: int,
    margin_frames: int,
    end_pad_frames: int = LYRIC_END_PAD_FRAMES,
) -> int:
    need = max(1, int(song_frames) - int(slice_start))
    covering = [step["frames"] for step in steps if step["frames"] >= need]
    if covering:
        return covering[0]

    max_g = int(steps[-1]["frames"])
    min_g = int(steps[0]["frames"])
    end_pad = max(0, int(end_pad_frames))
    slice_start = int(slice_start)
    del tail_frames, margin_frames

    gen_end_max = slice_start + max_g
    danger = []
    protected = []
    for start, end in lyric_spans:
        if start < slice_start or start >= gen_end_max:
            continue
        fits = end <= gen_end_max - end_pad
        if not fits:
            danger.append(start)
        else:
            protected.append((start, end))
    if not danger:
        return max_g

    min_keep = min_g
    for start, end in protected:
        min_keep = max(min_keep, start - slice_start + 1)
        min_keep = max(min_keep, end + end_pad - slice_start)

    def protected_fit(grid):
        ge = slice_start + int(grid)
        for start, end in protected:
            if start >= ge or end > ge - end_pad:
                return False
        return True

    if protected:
        ok = [
            int(step["frames"]) for step in steps
            if min_keep <= int(step["frames"]) <= max_g and protected_fit(int(step["frames"]))
        ]
        if ok:
            return ok[0]
        return max_g

    limit = min(danger) - slice_start
    ok = []
    for step in steps:
        grid = int(step["frames"])
        if grid > limit or grid < min_g:
            continue
        ok.append(grid)
    if ok:
        return ok[-1]
    return min_g


def plan_clip_windows(
    song_seconds: float,
    max_duration_seconds: float,
    lyric_starts=None,
    lyric_spans=None,
    head_frames: int = PLANNING_HEAD_FRAMES,
    tail_frames: int = PLANNING_TAIL_FRAMES,
    fps: float = FPS,
    margin_frames: int = LYRIC_BOUNDARY_MARGIN_FRAMES,
):
    """Kept-song windows with per-clip H3 duration.

    Joins discard at least 1 s (phase-snapped) so the next clip regenerates
    that tail as the start of its kept ``time:``. ``head_frames`` /
    ``tail_frames`` are the requested Continue context and minimum join tail;
    each clip snaps them the same way generate does. Generate length never
    stretches past max. A line that cannot finish inside this generate is
    moved whole to the next clip.
    """
    max_s = clamp_max_duration_seconds(max_duration_seconds)
    steps = h3_grid_steps(MUSIC_MIN_DURATION_SECONDS, max_s, fps=fps)
    song_frames = song_frame_count(song_seconds, fps=fps)
    lyric_span_frames = _lyric_span_frames(lyric_spans, lyric_starts, fps)
    context_frames = int(head_frames)
    min_tail = int(tail_frames)
    cursor = 0
    next_head = 0
    windows = []
    while cursor < song_frames:
        if len(windows) >= MUSIC_MAX_SEGMENTS:
            raise ValueError(
                f"h3_music_video: song {song_seconds:.3f}s needs more than {MUSIC_MAX_SEGMENTS} clips "
                f"at max {max_s:g}s; raise max duration"
            )
        is_first = not windows
        head = 0 if is_first else next_head
        slice_start = next_slice_start(cursor, head)
        grid = _choose_clip_grid(
            slice_start, song_frames, steps, lyric_span_frames, min_tail, int(margin_frames),
        )
        is_last = slice_start + grid >= song_frames
        if is_last:
            tail = 0
            next_head = 0
        else:
            geom = planning_join_geometry(grid, context_frames, min_tail)
            tail = int(geom["tail_frames"])
            next_head = int(geom["head_frames"])
        keep_start, keep_end = kept_video_span(grid, head, tail, 0, is_last=is_last)
        start_frame = slice_start + keep_start
        end_frame = min(song_frames, slice_start + keep_end)
        if is_last:
            end_frame = max(end_frame, song_frames)
        if start_frame >= song_frames or end_frame <= start_frame:
            break
        windows.append({
            "index": len(windows) + 1,
            "start": start_frame / float(fps),
            "end": end_frame / float(fps),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "slice_start": slice_start,
            "duration_seconds": grid / float(fps),
            "grid_frames": grid,
        })
        cursor = advance_cursor(slice_start, grid, tail, is_last=is_last)
        if cursor >= song_frames:
            break
    if not windows:
        raise ValueError("h3_music_video: clip planner produced no windows")
    return windows


def planning_clip_windows(
    song_seconds: float,
    duration_seconds: float,
    head_frames: int = PLANNING_HEAD_FRAMES,
    tail_frames: int = PLANNING_TAIL_FRAMES,
    extra: int = 0,
    fps: float = FPS,
    lyric_starts=None,
    lyric_spans=None,
):
    """Estimated kept-song ranges per generation clip (master timeline seconds)."""
    del extra
    return plan_clip_windows(
        song_seconds, duration_seconds, lyric_starts=lyric_starts,
        lyric_spans=lyric_spans,
        head_frames=head_frames, tail_frames=tail_frames, fps=fps,
    )


def frame_to_sample(frame: int, sample_rate: int, fps: float = FPS) -> int:
    return int(round(int(frame) * float(sample_rate) / float(fps)))


def sample_to_frame(sample: int, sample_rate: int, fps: float = FPS) -> int:
    return int(round(int(sample) * float(fps) / float(sample_rate)))


def slice_sample_range(start_frame: int, grid_frames: int, sample_rate: int, fps: float = FPS):
    """Half-open sample range ``[start, start+length)`` for one H3-grid song slice."""
    start = frame_to_sample(start_frame, sample_rate, fps)
    length = frame_to_sample(grid_frames, sample_rate, fps)
    if length <= 0:
        raise ValueError("h3_music_video: song slice length must be > 0")
    return start, start + length


def next_slice_start(cursor_frame: int, head_frames: int) -> int:
    """Clip k slice starts ``head`` frames before the previous kept-picture end."""
    return max(0, int(cursor_frame) - max(0, int(head_frames)))


def advance_cursor(slice_start: int, grid_frames: int, tail_frames: int, is_last: bool = False) -> int:
    """Song frame (exclusive) where this clip's kept picture ends."""
    start = int(slice_start)
    grid = int(grid_frames)
    if is_last:
        return start + grid
    return start + grid - max(0, int(tail_frames))


def kept_video_span(grid_frames: int, head_frames: int, tail_frames: int, bridge_frames: int = 0,
                    is_last: bool = False):
    """Half-open video-frame indices kept from this clip after stitch + STB skip."""
    start = max(0, int(head_frames)) + max(0, int(bridge_frames))
    end = int(grid_frames) if is_last else int(grid_frames) - max(0, int(tail_frames))
    if start >= end:
        raise ValueError(
            f"h3_music_video: kept video span is empty "
            f"(head={head_frames}, bridge={bridge_frames}, tail={tail_frames}, grid={grid_frames})"
        )
    return start, end


def stb_song_span(prev_slice_start: int, prev_grid_frames: int, prev_tail_frames: int, bridge_frames: int):
    """Song frames covered by Safe Tail Bridge pixels taken from the previous clip."""
    bridge = max(0, int(bridge_frames))
    if bridge <= 0:
        return 0, 0
    start = int(prev_slice_start) + int(prev_grid_frames) - max(0, int(prev_tail_frames))
    return start, start + bridge


def music_video_mux_spans(clips):
    """Build contiguous master-song frame spans matching stitched kept video.

    Each clip dict: slice_start, grid_frames, head, tail, bridge (STB applied
    when joining TO this clip; 0 for clip 1), is_last.
    """
    spans = []
    for i, clip in enumerate(clips):
        slice_start = int(clip["slice_start"])
        grid = int(clip["grid_frames"])
        head = max(0, int(clip.get("head", 0)))
        tail = max(0, int(clip.get("tail", 0)))
        bridge = max(0, int(clip.get("bridge", 0)))
        is_last = bool(clip.get("is_last", i == len(clips) - 1))
        if i > 0 and bridge > 0:
            prev = clips[i - 1]
            stb_start, stb_end = stb_song_span(
                int(prev["slice_start"]), int(prev["grid_frames"]),
                max(0, int(prev.get("tail", 0))), bridge,
            )
            if stb_end > stb_start:
                spans.append((stb_start, stb_end))
        keep_start, keep_end = kept_video_span(grid, head, tail, bridge, is_last=is_last)
        spans.append((slice_start + keep_start, slice_start + keep_end))
    return spans


def mux_spans_are_contiguous(spans) -> bool:
    if not spans:
        return True
    prev_end = spans[0][1]
    for start, end in spans[1:]:
        if start != prev_end:
            return False
        prev_end = end
    return True

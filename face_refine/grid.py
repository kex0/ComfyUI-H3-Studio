"""H3 17k+5 frame-grid helpers. No ComfyUI imports."""

import numpy as np

# Consecutive refine chunks overlap by this many frames (7 H3 latent steps,
# Music Video context_frames=22). The next pass freezes those tokens.
HARD_CUT_FRAC = 0.22
MIN_REFINE = 22
MIN_VISIBLE_SEC = 0.5
CHUNK_OVERLAP = 22
OVERLAP_SOFT_STEPS = 2
CLOSEUP_RAMP = 0.06
DENOISE_GAMMA = 2.0
PASTE_MIN_STRENGTH = 0.2
FACE_INPAINT_DILATION = 16
H3_SPATIAL = 16
H3_TOKEN = 2
H3_FRAMES_PER_LATENT = (1, 4, 4, 4, 4)


def align_h3_frames(n: int) -> int:
    n = max(5, int(n))
    while n % 17 != 5:
        n += 1
    return n


def chunk_ranges(n_frames: int, max_chunk: int, overlap: int = 0):
    """Split n_frames into H3-grid chunks. Last chunk may pad (grid > remaining).

    ``overlap`` pulls each later chunk back so it shares that many frames with
    the previous one. 0 is the old abutting split.
    """
    n_frames = int(n_frames)
    max_chunk = align_h3_frames(max(5, int(max_chunk)))
    overlap = max(0, int(overlap))
    if overlap >= max_chunk:
        overlap = 0
    stride = max_chunk - overlap
    out = []
    i = 0
    while i < n_frames:
        remaining = n_frames - i
        if remaining <= max_chunk:
            out.append((i, n_frames, align_h3_frames(remaining)))
            break
        out.append((i, i + max_chunk, max_chunk))
        i += stride
    return out


def hard_cut_breaks(boxes, src_w, src_h, jump_frac=HARD_CUT_FRAC):
    """Packing cuts: the crop center teleports. A zoom is not a cut."""
    n = len(boxes)
    br = np.zeros(n, dtype=bool)
    if n:
        br[0] = True
    if n < 2:
        return br
    cx = np.array([b[0] + b[2] * 0.5 for b in boxes], dtype=np.float64)
    cy = np.array([b[1] + b[3] * 0.5 for b in boxes], dtype=np.float64)
    jump = np.hypot(np.diff(cx), np.diff(cy))
    thresh = float(jump_frac) * min(float(src_w), float(src_h))
    br[1:] = jump > thresh
    return br


def shot_spans(breaks, n_frames):
    """Shot ranges as ``(start, end)``. ``breaks[i]`` is True on the first frame of a shot."""
    n_frames = int(n_frames)
    if n_frames <= 0:
        return []
    br = np.zeros(n_frames, dtype=bool)
    if breaks is not None:
        src = np.asarray(breaks, dtype=bool).reshape(-1)
        ncopy = min(int(src.size), n_frames)
        if ncopy:
            br[:ncopy] = src[:ncopy]
    br[0] = True
    idx = np.flatnonzero(br)
    spans = []
    for i, a in enumerate(idx):
        b = int(idx[i + 1]) if i + 1 < len(idx) else n_frames
        spans.append((int(a), b))
    return spans


def _shot_need_hulls(need, breaks):
    """Whole packing shot when any frame needs paste, including leading/trailing close-ups."""
    need = np.asarray(need, dtype=bool)
    n = int(need.size)
    hulls = []
    for s, e in shot_spans(breaks, n):
        if bool(need[s:e].any()):
            hulls.append((int(s), int(e)))
    return hulls


def _need_runs(need):
    need = np.asarray(need, dtype=bool)
    n = int(need.size)
    runs = []
    i = 0
    while i < n:
        if not need[i]:
            i += 1
            continue
        j = i + 1
        while j < n and need[j]:
            j += 1
        runs.append((i, j))
        i = j
    return runs


def sustained_visible(detected, fps, min_seconds=MIN_VISIBLE_SEC):
    """Keep detections that last at least ``min_seconds`` with no gap.

    Brief flashes do not count as a visible face for H3 sampling.
    """
    detected = np.asarray(detected, dtype=bool)
    n = int(detected.size)
    out = np.zeros(n, dtype=bool)
    rate = float(fps) if float(fps or 0) > 0 else 24.0
    min_len = max(1, int(round(float(min_seconds) * rate)))
    for a, b in _need_runs(detected):
        if b - a >= min_len:
            out[a:b] = True
    return out


def _merge_runs(runs, merge_gap):
    if not runs:
        return []
    gap = max(0, int(merge_gap))
    out = [[int(runs[0][0]), int(runs[0][1])]]
    for a, b in runs[1:]:
        a, b = int(a), int(b)
        if a - out[-1][1] <= gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _pack_runs_to_max(runs, max_span):
    """Merge runs that still fit in one max-length H3 window.

    Interior frames that do not need paste stay in the window (H3 freezes them).
    Leading and trailing skip are not included.
    """
    if not runs:
        return []
    max_span = int(max_span)
    out = []
    i = 0
    while i < len(runs):
        a, b = int(runs[i][0]), int(runs[i][1])
        j = i + 1
        while j < len(runs) and int(runs[j][1]) - a <= max_span:
            b = int(runs[j][1])
            j += 1
        out.append((a, b))
        i = j
    return out


def loop_span_len(tail_start, head_end, n_frames):
    return int(n_frames) - int(tail_start) + int(head_end)


def loop_context_frames(tail_start, head_end, n_frames, overlap):
    """Continue context on each side of a wrap write, or (0, 0) if none.

    ``pre`` frames before ``tail_start`` are the previous clip's ending.
    ``post`` frames after ``head_end`` are the following clip's opening.
    """
    tail_start = int(tail_start)
    head_end = int(head_end)
    n_frames = int(n_frames)
    overlap = max(0, int(overlap))
    if overlap <= 0 or n_frames < 2 or head_end >= tail_start:
        return 0, 0
    room = tail_start - head_end
    pre = min(overlap, tail_start, room)
    post = min(overlap, n_frames - head_end, room - pre)
    return max(0, pre), max(0, post)


def _join_wrap_span(take_head, take_tail, n_frames, max_chunk, min_refine):
    """Cap a wrap around frame 0 so it fits ``max_chunk`` and does not overlap."""
    n_frames = int(n_frames)
    max_chunk = int(max_chunk)
    min_refine = max(1, int(min_refine))
    take_head = max(0, int(take_head))
    take_tail = max(0, int(take_tail))
    if take_head + take_tail < min_refine:
        return None
    if take_head + take_tail >= n_frames:
        if n_frames < min_refine:
            return None
        if n_frames <= max_chunk:
            mid = max(1, n_frames // 2)
            return mid, mid
        take_tail = max_chunk // 2
        take_head = max_chunk - take_tail
        return n_frames - take_tail, take_head
    if take_head + take_tail > max_chunk:
        want_tail = min(take_tail, max_chunk // 2)
        want_head = min(take_head, max_chunk - want_tail)
        extra = max_chunk - want_tail - want_head
        if extra > 0:
            grow = min(extra, take_tail - want_tail)
            want_tail += grow
            extra -= grow
            want_head += min(extra, take_head - want_head)
        take_head, take_tail = want_head, want_tail
        if take_head + take_tail < min_refine:
            return None
    if take_head + take_tail > n_frames:
        take_tail = n_frames - take_head
    return n_frames - take_tail, take_head


def wrap_refine_window(need, n_frames, max_chunk, min_refine=MIN_REFINE, overlap=0):
    """(tail_start, head_end) for a wrap-around H3 *write*, or None.

    Uses paste-need at the actual join, not shot hulls. Adjacent packing
    shots that meet in the middle still wrap. ``overlap`` reserves Continue
    context on both sides so the H3 generate can freeze the previous clip's
    ending and the following clip's opening, same sandwich as Auto Chain.
    ``head_end`` is exclusive.
    """
    n_frames = int(n_frames)
    max_chunk = align_h3_frames(max(5, int(max_chunk)))
    min_refine = max(1, int(min_refine))
    overlap = max(0, int(overlap))
    if n_frames < 2:
        return None
    need = np.asarray(need, dtype=bool).reshape(-1)
    if need.size != n_frames:
        padded = np.zeros(n_frames, dtype=bool)
        ncopy = min(int(need.size), n_frames)
        if ncopy:
            padded[:ncopy] = need[:ncopy]
        need = padded
    if not bool(need[0] or need[-1]):
        return None
    head_end = 0
    while head_end < n_frames and need[head_end]:
        head_end += 1
    tail_start = n_frames
    while tail_start > 0 and need[tail_start - 1]:
        tail_start -= 1
    take_head = head_end
    take_tail = n_frames - tail_start
    ctx = min(CHUNK_OVERLAP, n_frames - 1)
    if take_head == 0 and take_tail > 0:
        take_head = min(ctx, n_frames - take_tail)
    if take_tail == 0 and take_head > 0:
        take_tail = min(ctx, n_frames - take_head)
    span = _join_wrap_span(take_head, take_tail, n_frames, max_chunk, min_refine)
    if span is None:
        return None
    tail_start, head_end = span
    if loop_span_len(tail_start, head_end, n_frames) >= n_frames:
        return span
    ctx_budget = min(overlap, max_chunk // 4)
    write_cap = max_chunk - 2 * ctx_budget
    if write_cap < min_refine:
        return span
    span2 = _join_wrap_span(take_head, take_tail, n_frames, write_cap, min_refine)
    if span2 is None:
        return span
    t2, h2 = span2
    if h2 >= t2:
        return span
    return span2


def _wrap_interior_breaks(breaks, n_frames, head_end, tail_start):
    br = np.zeros(int(n_frames), dtype=bool)
    if breaks is not None:
        src = np.asarray(breaks, dtype=bool).reshape(-1)
        ncopy = min(int(src.size), int(n_frames))
        if ncopy:
            br[:ncopy] = src[:ncopy]
    br[0] = True
    if 0 < int(head_end) < int(n_frames):
        br[int(head_end)] = True
    if 0 < int(tail_start) < int(n_frames):
        br[int(tail_start)] = True
    return br


def _keep_interior_segs(segs, head_end, tail_start):
    out = []
    lo, hi = int(head_end), int(tail_start)
    if hi <= lo:
        return out
    for start, end, grid, kind in segs:
        a, b = max(int(start), lo), min(int(end), hi)
        if b <= a:
            continue
        if kind == "copy":
            out.append((a, b, b - a, "copy"))
        else:
            out.append((a, b, align_h3_frames(b - a), kind))
    return out


def pack_refine_chunks(need, n_frames, max_chunk, overlap=0, merge_gap=None,
                       breaks=None, boxes=None, src_size=None, min_refine=MIN_REFINE,
                       loop=False):
    """H3 windows for whole packing shots that need any paste; copy the rest.

    ``max_chunk`` is a cap. Packing cuts are ``breaks`` (crop teleports).
    Leading/trailing close-ups stay in the H3 window so paste can ramp.
    Hulls shorter than ``min_refine`` are copied. Long hulls split like
    ``chunk_ranges``. ``boxes`` + ``src_size`` is only a fallback when
    ``breaks`` is omitted.

    ``loop`` adds a wrap-around ``loop`` chunk when the join frames need
    paste, so last/first are generated as one clip even if a packing cut
    sits between the last shot and the first.

    Returns (start, end, grid, kind) with kind ``refine``, ``copy``, or ``loop``.
    A ``loop`` chunk is ``source[start:n] + source[0:end]``.
    """
    n_frames = int(n_frames)
    if n_frames <= 0:
        return []
    max_chunk = align_h3_frames(max(5, int(max_chunk)))
    overlap = max(0, int(overlap))
    if overlap >= max_chunk:
        overlap = 0
    if merge_gap is None:
        merge_gap = overlap if overlap else CHUNK_OVERLAP
    min_refine = max(1, int(min_refine))
    need = np.asarray(need, dtype=bool)
    if need.size != n_frames:
        padded = np.zeros(n_frames, dtype=bool)
        ncopy = min(int(need.size), n_frames)
        if ncopy:
            padded[:ncopy] = need[:ncopy]
        need = padded
    if breaks is not None:
        runs = _shot_need_hulls(need, breaks)
    elif boxes is not None and src_size is not None:
        sw, sh = int(src_size[0]), int(src_size[1])
        runs = _shot_need_hulls(need, hard_cut_breaks(boxes, sw, sh))
    else:
        runs = _pack_runs_to_max(
            _merge_runs(_need_runs(need), merge_gap), max_chunk,
        )
    if loop:
        wrap = wrap_refine_window(
            need, n_frames, max_chunk, min_refine, overlap=overlap,
        )
        if wrap is not None:
            tail_start, head_end = wrap
            mid = need.copy()
            mid[:head_end] = False
            mid[tail_start:] = False
            segs = pack_refine_chunks(
                mid, n_frames, max_chunk, overlap=overlap, merge_gap=merge_gap,
                breaks=_wrap_interior_breaks(breaks, n_frames, head_end, tail_start),
                min_refine=min_refine, loop=False,
            )
            segs = _keep_interior_segs(segs, head_end, tail_start)
            write_len = loop_span_len(tail_start, head_end, n_frames)
            pre, post = loop_context_frames(
                tail_start, head_end, n_frames, overlap,
            )
            if not any(s[3] == "refine" for s in segs):
                pre = post = 0
            segs.append((
                int(tail_start), int(head_end),
                align_h3_frames(write_len + pre + post), "loop",
            ))
            return segs
    refine = []
    for a, b in runs:
        span = b - a
        if span < min_refine:
            continue
        if span <= max_chunk:
            refine.append((a, b, align_h3_frames(span), "refine"))
            continue
        for s, e, g in chunk_ranges(span, max_chunk, overlap=overlap):
            refine.append((a + s, a + e, g, "refine"))
    segs = []
    cursor = 0
    for start, end, grid, kind in refine:
        if cursor < start:
            segs.append((cursor, start, start - cursor, "copy"))
        segs.append((start, end, grid, kind))
        cursor = max(cursor, end)
    if cursor < n_frames:
        segs.append((cursor, n_frames, n_frames - cursor, "copy"))
    if not segs:
        segs.append((0, n_frames, n_frames, "copy"))
    return segs


def pack_refine_jobs(need, n_frames, max_chunk, overlap=0, merge_gap=None):
    """Refine windows only. Copy spans are separate files in ``pack_refine_chunks``."""
    segs = pack_refine_chunks(
        need, n_frames, max_chunk, overlap=overlap, merge_gap=merge_gap,
    )
    jobs = []
    for start, end, grid, kind in segs:
        if kind != "refine":
            continue
        jobs.append({
            "kind": "refine",
            "copy_start": start,
            "copy_end": start,
            "start": start,
            "end": end,
            "grid": grid,
            "tail_start": end,
            "tail_end": end,
        })
    return jobs


def job_hold(jobs, index, overlap):
    """Overlap frames to hold only between two overlapping refine jobs."""
    index = int(index)
    if index >= len(jobs) - 1:
        return 0
    a = jobs[index]
    b = jobs[index + 1]
    if a.get("kind") != "refine" or b.get("kind") != "refine":
        return 0
    if int(b["start"]) >= int(a["end"]):
        return 0
    return min(
        max(0, int(overlap)),
        int(a["end"]) - int(b["start"]),
        int(a["end"]) - int(a["start"]),
    )


def segment_hold(chunks, index, overlap):
    """Overlap frames to hold only between two overlapping refine windows.

    A refine followed by a loop holds Continue context for the wrap head.
    """
    index = int(index)
    if index >= len(chunks) - 1:
        return 0
    a = chunks[index]
    b = chunks[index + 1]
    if len(a) < 4 or len(b) < 4:
        return max(0, int(overlap))
    overlap = max(0, int(overlap))
    if a[3] == "refine" and b[3] == "loop":
        gap = int(b[0]) - int(b[1])
        if gap <= 0:
            return 0
        return min(overlap, gap, int(a[1] - a[0]))
    if a[3] != "refine" or b[3] != "refine" or b[0] >= a[1]:
        return 0
    return min(overlap, int(a[1] - b[0]), int(a[1] - a[0]))


def committed_write_span(start, end, committed, hold=0, is_last=False):
    """Source frames to encode: skip already-written prefix, hold Continue overlap.

    Returns ``(write_start, write_end)``. Empty when write_start >= write_end.
    """
    start = int(start)
    end = int(end)
    if end <= start:
        return start, start
    write_start = max(start, int(committed))
    hold = 0 if is_last else min(max(0, int(hold)), max(0, end - start))
    write_end = end - hold
    if write_start >= write_end:
        return write_start, write_start
    return write_start, write_end


def audio_mux_duration(n_frames, fps):
    """Audio slice length that cannot round shorter than ``n_frames`` at ``fps``.

    ``221/24`` formatted to 6 decimals is 9.208333s = 220.999992 frames, so
    ffmpeg ``-t`` plus ``-shortest`` dropped the last frame at every Continue
    join (those writes are max_chunk - 22).
    """
    n_frames = max(0, int(n_frames))
    fps = float(fps)
    if n_frames <= 0 or fps <= 0:
        return 0.0
    return (n_frames + 1) / fps


def committed_file_spans(chunks, overlap):
    """Packed vs committed write span for each file. Copy commits its packed end."""
    out = []
    committed = int(chunks[0][0]) if chunks else 0
    n = len(chunks)
    for i, (start, end, _grid, kind) in enumerate(chunks):
        start, end = int(start), int(end)
        is_last = i == n - 1
        if kind == "loop":
            out.append((start, end, start, start, kind))
            continue
        if kind != "refine":
            ws, we = committed_write_span(start, end, committed, hold=0, is_last=True)
            out.append((start, end, ws, we, kind))
            committed = max(committed, we, end)
            continue
        hold = segment_hold(chunks, i, overlap)
        ws, we = committed_write_span(start, end, committed, hold, is_last)
        out.append((start, end, ws, we, kind))
        committed = max(committed, we)
    return out


def debug_file_slice(packed_start, packed_end, write_start, write_end, n_file):
    """Frame offset/count inside a debug mp4 for the committed write span.

    New debug files are already the write span. Older files are the packed span
    and must drop the Continue overlap so concat does not rewind.
    """
    packed_start, packed_end = int(packed_start), int(packed_end)
    write_start, write_end = int(write_start), int(write_end)
    n_file = int(n_file)
    packed = packed_end - packed_start
    write = write_end - write_start
    if write <= 0 or n_file <= 0:
        return None
    if n_file == write:
        return 0, write
    off = write_start - packed_start
    if off >= 0 and off + write <= n_file:
        return off, write
    if n_file == packed and 0 <= off < n_file:
        return off, min(write, n_file - off)
    return 0, n_file


def closeup_paste_weight(face_h, src_h, skip_frac, ramp=CLOSEUP_RAMP):
    """Paste opacity from measured face height: 1 below the ramp, 0 at skip_frac.

    Undetected frames are not zeroed here — stitch fade_out uses tracker weights
    for those. This only stops a hard switch when a face grows through skip_frac.
    """
    face_h = np.asarray(face_h, dtype=np.float64)
    frac = face_h / max(float(src_h), 1.0)
    hi = float(skip_frac)
    lo = max(0.05, hi - float(ramp))
    span = max(hi - lo, 1e-6)
    return 1.0 - np.clip((frac - lo) / span, 0.0, 1.0)


def denoise_px_range(src_h, skip_frac, small_frac=0.06):
    """Pixel face-height range for per-frame denoise, tied to skip_frac.

    Full denoise at small_frac of the frame; zero at skip_frac (close-up).
    """
    hi = max(float(skip_frac) * float(src_h), 48.0)
    lo = min(float(small_frac) * float(src_h), hi * 0.45)
    lo = max(24.0, lo)
    if lo >= hi:
        lo = hi * 0.4
    return lo, hi


def per_frame_strength(face_h, px_small, px_large, s_small, s_large, gamma=DENOISE_GAMMA):
    face_h = np.asarray(face_h, dtype=np.float64)
    span = max(float(px_large) - float(px_small), 1e-6)
    t = np.clip((face_h - float(px_small)) / span, 0.0, 1.0) ** float(gamma)
    return np.clip(float(s_small) + (float(s_large) - float(s_small)) * t, 0.0, 1.0)


def refine_paste_weight(face_h, src_h, skip_frac, crop_factor, canvas_h, strength,
                        ramp=CLOSEUP_RAMP, min_strength=PASTE_MIN_STRENGTH):
    """Paste only where H3 actually denoised, and never when the crop is downscaled."""
    paste = closeup_paste_gate(face_h, src_h, skip_frac, ramp=ramp)
    mag = float(canvas_h) / np.maximum(np.asarray(face_h, dtype=np.float64) * float(crop_factor), 1.0)
    paste = paste * (mag >= 1.0)
    s = np.asarray(strength, dtype=np.float64)
    return paste * np.clip(s / max(float(min_strength), 1e-6), 0.0, 1.0)


def sharpness_match_amount(e_h3, e_src, amount=1.0):
    """How much to blur H3 so its micro-contrast matches the source surround."""
    e_h3 = np.asarray(e_h3, dtype=np.float64)
    e_src = np.asarray(e_src, dtype=np.float64)
    excess = np.clip((e_h3 - e_src) / np.maximum(e_h3, 1e-8), 0.0, 1.0)
    return np.clip(float(amount) * excess, 0.0, 1.0)


def chunk_is_all_closeup(paste_w, detected, min_w=0.05):
    """Skip H3 when no detected face in the chunk needs a real paste."""
    paste_w = np.asarray(paste_w, dtype=np.float64)
    detected = np.asarray(detected, dtype=bool)
    if paste_w.size == 0 or not bool(detected.any()):
        return True
    return bool((paste_w[detected] < float(min_w)).all())


def select_chunk_span(n_chunks, start_chunk, end_chunk, completed_chunk=0):
    """1-based start/end to inclusive 0-based indices.

    start_chunk 0 resumes after completed_chunk. end_chunk 0 means the last chunk.
    If there is nothing left, first > last.
    """
    n_chunks = int(n_chunks)
    if n_chunks <= 0:
        return 0, -1
    end = int(end_chunk)
    if end <= 0 or end > n_chunks:
        end = n_chunks
    start = int(start_chunk)
    if start <= 0:
        start = int(completed_chunk) + 1
    start = max(1, min(start, n_chunks + 1))
    end = max(0, min(end, n_chunks))
    return start - 1, end - 1


def h3_latent_t(n_frames):
    n = align_h3_frames(max(5, int(n_frames)))
    return 2 if n <= 5 else ((n - 5) // 17) * 5 + 2


def h3_steps_covering(n_frames):
    """Latent steps from clip start (phase 0) that cover ``n_frames`` pixels."""
    n = max(0, int(n_frames))
    if n <= 0:
        return 0
    t = 0
    covered = 0
    spans = H3_FRAMES_PER_LATENT
    while covered < n:
        covered += spans[t % len(spans)]
        t += 1
    return t


def overlap_freeze_scale(latent_t, ctx_steps, soft_steps=OVERLAP_SOFT_STEPS, tail=False):
    """Per-step denoise scale for a frozen Continue head or tail. 1 = sample, 0 = keep."""
    t = max(1, int(latent_t))
    scale = np.ones(t, dtype=np.float32)
    ctx = min(max(0, int(ctx_steps)), t)
    if ctx <= 0 or ctx >= t:
        return scale
    soft = min(max(int(soft_steps), 0), ctx - 1)
    if tail:
        scale[-ctx:] = 0.0
        if soft > 0:
            scale[-ctx:-ctx + soft] = (
                np.arange(soft, 0, -1, dtype=np.float32) / float(soft + 1)
            )
        return scale
    scale[:ctx] = 0.0
    if soft > 0:
        scale[ctx - soft:ctx] = (
            np.arange(1, soft + 1, dtype=np.float32) / float(soft + 1)
        )
    return scale


def canvas_rect_to_source(crop_box, rect, canvas_w, canvas_h):
    """Map a canvas-space face_rect into the source crop box."""
    x, y, bw, bh = (float(v) for v in crop_box)
    fx, fy, fw, fh = (float(v) for v in rect)
    cw = max(float(canvas_w), 1.0)
    ch = max(float(canvas_h), 1.0)
    return (
        x + fx / cw * bw,
        y + fy / ch * bh,
        fw / cw * bw,
        fh / ch * bh,
    )


def face_rect_in_canvas(crop_box, face_cx, face_cy, face_w, face_h, canvas_w, canvas_h):
    """Face box in canvas pixels from source-space face vs crop. Not assumed centred."""
    x, y, bw, bh = (float(v) for v in crop_box)
    bw = max(bw, 1e-6)
    bh = max(bh, 1e-6)
    fw = float(face_w)
    fh = float(face_h)
    fx = float(face_cx) - fw * 0.5
    fy = float(face_cy) - fh * 0.5
    return (
        (fx - x) / bw * float(canvas_w),
        (fy - y) / bh * float(canvas_h),
        fw / bw * float(canvas_w),
        fh / bh * float(canvas_h),
    )


def fit_box_to_aspect(box, src_w, src_h, aspect):
    """Keep the planned centre; force width/height to `aspect` (canvas_w/canvas_h).

    A 16:9 source crop into a 1:1 canvas would squash. If the fitted square does
    not fit in the frame, shrink to the short edge rather than change aspect.
    """
    x, y, bw, bh = (float(v) for v in box)
    aspect = float(aspect) if aspect > 1e-6 else 1.0
    W, H = float(src_w), float(src_h)
    cx = x + bw * 0.5
    cy = y + bh * 0.5
    side_h = max(bh, bw / aspect)
    side_w = side_h * aspect
    if side_w > W:
        side_w, side_h = W, W / aspect
    if side_h > H:
        side_h, side_w = H, H * aspect
    if side_w > W:
        side_w, side_h = W, W / aspect
    x = min(max(cx - side_w * 0.5, 0.0), max(0.0, W - side_w))
    y = min(max(cy - side_h * 0.5, 0.0), max(0.0, H - side_h))
    return (float(x), float(y), float(side_w), float(side_h))


def box_iou(a, b):
    ax, ay, aw, ah = (float(v) for v in a)
    bx, by, bw, bh = (float(v) for v in b)
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = aw * ah + bw * bh - inter
    return inter / ua if ua > 0.0 else 0.0


def shot_breaks_from_boxes(boxes, iou_min=0.4):
    """True where consecutive crop boxes jump (hold-then-cut)."""
    n = len(boxes)
    br = np.zeros(n, dtype=bool)
    if n:
        br[0] = True
    for i in range(1, n):
        if box_iou(boxes[i], boxes[i - 1]) < float(iou_min):
            br[i] = True
    return br


def shot_breaks_from_tracks(cx, cy, sz, jump_frac=0.55, size_ratio=1.8):
    """Cuts where the face jumps; a push-in does not count."""
    cx = np.asarray(cx, dtype=np.float64)
    cy = np.asarray(cy, dtype=np.float64)
    sz = np.asarray(sz, dtype=np.float64)
    n = len(cx)
    br = np.zeros(n, dtype=bool)
    if n:
        br[0] = True
    if n < 2:
        return br
    jump = np.hypot(np.diff(cx), np.diff(cy))
    scale = np.maximum(np.maximum(sz[:-1], sz[1:]), 1.0)
    ratio = np.maximum(sz[1:] / np.maximum(sz[:-1], 1.0),
                       sz[:-1] / np.maximum(sz[1:], 1.0))
    br[1:] = jump > float(jump_frac) * scale
    br[1:] |= (ratio > float(size_ratio)) & (jump > 0.2 * scale)
    return br


def _gauss_smooth(vals, window, wrap=False):
    vals = np.asarray(vals, dtype=np.float64)
    if window <= 1 or len(vals) < 3:
        return vals.copy()
    window = min(int(window), len(vals))
    if window % 2 == 0:
        window += 1
    if window < 3:
        return vals.copy()
    pad = window // 2
    padded = np.pad(vals, pad, mode="wrap" if wrap else "reflect")
    x = np.arange(window, dtype=np.float64) - pad
    sigma = max(window / 6.0, 0.5)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    return np.convolve(padded, k, mode="valid")


def _gauss_smooth_causal(vals, window):
    """Trailing gaussian: current frame does not see future sizes."""
    vals = np.asarray(vals, dtype=np.float64)
    n = len(vals)
    if window <= 1 or n < 3:
        return vals.copy()
    span = min(int(window), n)
    sigma = max(span / 6.0, 0.5)
    dist = np.arange(span, dtype=np.float64)
    k = np.exp(-0.5 * ((span - 1 - dist) / sigma) ** 2)
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        a = max(0, i + 1 - span)
        sl = vals[a:i + 1]
        kk = k[-len(sl):]
        out[i] = float(np.dot(sl, kk / kk.sum()))
    return out


def smooth_per_shot(vals, breaks, window=9, causal=False, loop=False):
    """Gaussian smooth inside each shot; do not blend across planner cuts."""
    vals = np.asarray(vals, dtype=np.float64)
    br = np.asarray(breaks, dtype=bool)
    if br.size != vals.size:
        br = np.zeros(vals.size, dtype=bool)
        if vals.size:
            br[0] = True
    out = vals.copy()
    n = len(vals)
    i = 0
    fn = _gauss_smooth_causal if causal else _gauss_smooth
    while i < n:
        j = i + 1
        while j < n and not br[j]:
            j += 1
        out[i:j] = fn(vals[i:j], window)
        i = j
    if loop and n >= 3:
        if int(br[1:].sum()) == 0:
            return _gauss_smooth(vals, window, wrap=True)
        j = 1
        while j < n and not br[j]:
            j += 1
        k = n
        for i in range(n - 1, 0, -1):
            if br[i]:
                k = i
                break
        if 0 < k < n and j > 0:
            wrap_vals = np.concatenate([vals[k:], vals[:j]])
            sm = _gauss_smooth(wrap_vals, window)
            out[k:] = sm[: n - k]
            out[:j] = sm[n - k:]
    return out


def _face_crop_box(cx, cy, sz, crop_factor, aspect, W, H):
    """Aspect-locked crop around a face, clamped to the source frame."""
    bh = max(float(sz), 1.0) * float(crop_factor)
    bw = bh * float(aspect)
    if bw > W:
        bw, bh = W, W / max(float(aspect), 1e-6)
    if bh > H:
        bh, bw = H, H * float(aspect)
    if bw > W:
        bw, bh = W, W / max(float(aspect), 1e-6)
    x = min(max(float(cx) - bw * 0.5, 0.0), max(0.0, W - bw))
    y = min(max(float(cy) - bh * 0.5, 0.0), max(0.0, H - bh))
    return (float(x), float(y), float(bw), float(bh))


def _face_inside_box(box, cx, cy, fw, sz):
    """True if the face rect still sits inside the held crop."""
    x, y, w, h = box
    fw = max(float(fw), 1.0)
    sz = max(float(sz), 1.0)
    fx0 = float(cx) - fw * 0.5
    fy0 = float(cy) - sz * 0.5
    return (
        fx0 >= x - 1e-3
        and fy0 >= y - 1e-3
        and fx0 + fw <= x + w + 1e-3
        and fy0 + sz <= y + h + 1e-3
    )


def plan_hold_teleports(H, W, cx, cy, fw, sz, crop_factor, aspect,
                        seamless_loop=False):
    """Hold one crop until the face leaves it, then jump. No easing across cuts."""
    H, W = float(H), float(W)
    aspect = float(aspect) if float(aspect) > 1e-6 else 1.0
    cf = float(crop_factor)
    n = len(cx)
    boxes = []
    hold = None
    for i in range(n):
        ideal = fit_box_to_aspect(
            _face_crop_box(cx[i], cy[i], sz[i], cf, aspect, W, H), W, H, aspect,
        )
        if hold is None or not _face_inside_box(hold, cx[i], cy[i], fw[i], sz[i]):
            hold = ideal
        boxes.append(hold)
    if seamless_loop and n > 1 and boxes:
        first = boxes[0]
        if _face_inside_box(first, cx[-1], cy[-1], fw[-1], sz[-1]):
            boxes[-1] = first
    return boxes, {"aspect": aspect}


def follow_face_boxes(cx, cy, sz, crop_factor, src_w, src_h, aspect, breaks,
                      pos_window=9, size_window=15, loop=False):
    """Smooth pan and zoom inside a shot; snap on cuts. Face stays canvas-centred."""
    cx_s = smooth_per_shot(cx, breaks, pos_window, loop=loop)
    cy_s = smooth_per_shot(cy, breaks, pos_window, loop=loop)
    sz_s = np.maximum(
        smooth_per_shot(sz, breaks, size_window, causal=not loop, loop=loop), 1.0,
    )
    aspect = float(aspect) if aspect > 1e-6 else 1.0
    cf = float(crop_factor)
    W, H = float(src_w), float(src_h)
    out = []
    for i in range(len(cx_s)):
        bh = float(sz_s[i]) * cf
        bw = bh * aspect
        if bw > W:
            bw, bh = W, W / aspect
        if bh > H:
            bh, bw = H, H * aspect
        x = min(max(cx_s[i] - bw * 0.5, 0.0), max(0.0, W - bw))
        y = min(max(cy_s[i] - bh * 0.5, 0.0), max(0.0, H - bh))
        out.append(fit_box_to_aspect((x, y, bw, bh), W, H, aspect))
    return out, cx_s, cy_s, sz_s


def closeup_paste_gate(face_h, src_h, skip_frac, ramp=CLOSEUP_RAMP):
    """Binary paste with hysteresis. Partial paste of a denoise-1.0 face ghosts.

    Stay refining until the face hits skip_frac; stay original until it shrinks
    back through skip_frac - ramp.
    """
    frac = np.asarray(face_h, dtype=np.float64) / max(float(src_h), 1.0)
    hi = float(skip_frac)
    lo = max(0.05, hi - float(ramp))
    out = np.ones(frac.shape, dtype=np.float64)
    refining = True
    for i, f in enumerate(frac):
        if refining:
            if f >= hi:
                refining = False
        elif f <= lo:
            refining = True
        out[i] = 1.0 if refining else 0.0
    return out


def latent_mask_to_frames(token_mask, n_frames, canvas_h, canvas_w):
    """Nearest-upsample [1,1,Lt,lh,lw] onto [T,H,W] using the H3 frame groups."""
    m = np.asarray(token_mask, dtype=np.float32)
    if m.ndim == 5:
        m = m[0, 0]
    elif m.ndim != 3:
        raise ValueError("token_mask must be [Lt,H,W] or [1,1,Lt,H,W]")
    lt, lh, lw = (int(v) for v in m.shape)
    n = max(1, int(n_frames))
    ch, cw = int(canvas_h), int(canvas_w)
    sh = max(1, ch // max(lh, 1))
    sw = max(1, cw // max(lw, 1))
    spatial = np.repeat(np.repeat(m, sh, axis=1), sw, axis=2)
    up = np.zeros((lt, ch, cw), dtype=np.float32)
    uh, uw = min(ch, spatial.shape[1]), min(cw, spatial.shape[2])
    up[:, :uh, :uw] = spatial[:, :uh, :uw]
    frames = np.zeros((n, ch, cw), dtype=np.float32)
    for t, (a, b) in enumerate(h3_frame_groups(n, lt)):
        frames[a:b] = up[min(t, lt - 1)]
    return frames


def h3_frame_groups(n_frames, latent_t):
    """Pixel-frame ranges for each H3 latent frame (repeating 1,4,4,4,4).

    The last group eats leftover / padding frames so the count matches the VAE.
    """
    n = max(1, int(n_frames))
    want = max(1, int(latent_t))
    groups = []
    i = 0
    for t in range(want):
        span = H3_FRAMES_PER_LATENT[t % len(H3_FRAMES_PER_LATENT)]
        if t == want - 1:
            groups.append((i, n))
        else:
            groups.append((i, min(i + span, n)))
            i = min(i + span, n)
    for t, (a, b) in enumerate(groups):
        if a >= n:
            groups[t] = (n - 1, n)
        elif b <= a:
            groups[t] = (a, min(a + 1, n))
    return groups


def face_ellipse_mask(canvas_h, canvas_w, face_rects, dilation=FACE_INPAINT_DILATION):
    """Full-face ellipse per frame in canvas pixels. [T, H, W] float32 0/1."""
    h, w = int(canvas_h), int(canvas_w)
    rects = list(face_rects)
    t = len(rects)
    out = np.zeros((t, h, w), dtype=np.float32)
    if t == 0 or h <= 0 or w <= 0:
        return out
    yy = np.arange(h, dtype=np.float64)[:, None]
    xx = np.arange(w, dtype=np.float64)[None, :]
    grow = float(dilation)
    for i, rect in enumerate(rects):
        fx, fy, fw, fh = (float(v) for v in rect)
        fx -= grow
        fy -= grow
        fw += 2.0 * grow
        fh += 2.0 * grow
        rx = max(fw * 0.5, 1.0)
        ry = max(fh * 0.5, 1.0)
        ccx = fx + fw * 0.5
        ccy = fy + fh * 0.5
        out[i] = ((((xx - ccx) / rx) ** 2 + ((yy - ccy) / ry) ** 2) <= 1.0).astype(np.float32)
    return out


def _block_max(arr, out_h, out_w):
    t, h, w = arr.shape
    out_h = max(1, int(out_h))
    out_w = max(1, int(out_w))
    sh = max(1, h // out_h)
    sw = max(1, w // out_w)
    cut = arr[:, : out_h * sh, : out_w * sw]
    return cut.reshape(t, out_h, sh, out_w, sw).max(axis=(2, 4))


def _token_snap(arr, token=H3_TOKEN):
    ph = pw = max(1, int(token))
    t, h, w = arr.shape
    pad_h = (ph - h % ph) % ph
    pad_w = (pw - w % pw) % pw
    if pad_h or pad_w:
        arr = np.pad(arr, ((0, 0), (0, pad_h), (0, pad_w)), mode="edge")
    th, tw = arr.shape[1] // ph, arr.shape[2] // pw
    blocked = arr.reshape(t, th, ph, tw, pw).max(axis=(2, 4))
    snapped = np.repeat(np.repeat(blocked, ph, axis=1), pw, axis=2)
    return snapped[:, :h, :w]


def reduce_mask_h3(pixel_mask, latent_t, latent_h, latent_w, strength=None, token=H3_TOKEN):
    """Pixel [T,H,W] -> [1, 1, latent_t, latent_h, latent_w] on the H3 token grid."""
    pixel_mask = np.asarray(pixel_mask, dtype=np.float64)
    if pixel_mask.ndim != 3:
        raise ValueError("pixel_mask must be [T, H, W]")
    n, _h, _w = pixel_mask.shape
    if strength is not None:
        s = np.asarray(strength, dtype=np.float64).reshape(-1)
        if s.size < n:
            s = np.pad(s, (0, n - s.size), mode="edge")
        pixel_mask = pixel_mask * s[:n, None, None]
    groups = h3_frame_groups(n, latent_t)
    temporal = np.stack(
        [pixel_mask[a:b].max(axis=0) if b > a else pixel_mask[min(a, n - 1)]
         for a, b in groups],
        axis=0,
    )
    reduced = _block_max(temporal, latent_h, latent_w)
    snapped = _token_snap(reduced, token=token)
    return snapped.reshape(1, 1, snapped.shape[0], snapped.shape[1], snapped.shape[2]).astype(
        np.float32
    )


def face_token_video_mask(canvas_h, canvas_w, face_rects, latent_t, latent_h, latent_w,
                          strength=None, detected=None, dilation=FACE_INPAINT_DILATION):
    """Canvas face ellipses reduced to an H3 video denoise mask [1,1,T,h,w]."""
    mask = face_ellipse_mask(canvas_h, canvas_w, face_rects, dilation=dilation)
    if detected is not None and mask.shape[0]:
        d = np.asarray(detected, dtype=np.float64).reshape(-1)
        if d.size < mask.shape[0]:
            d = np.pad(d, (0, mask.shape[0] - d.size), mode="edge")
        mask = mask * d[: mask.shape[0], None, None].astype(np.float32)
    return reduce_mask_h3(mask, latent_t, latent_h, latent_w, strength=strength)


def pack_av_noise_mask(video_mask, audio_shape):
    """Video denoise mask plus a zero audio companion. No Comfy types."""
    video = np.asarray(video_mask, dtype=np.float32)
    audio = np.zeros(tuple(int(x) for x in audio_shape), dtype=np.float32)
    return video, audio

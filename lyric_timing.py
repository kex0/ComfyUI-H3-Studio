"""Parse timestamped lyrics and assign them to Music Video kept-picture windows.

Plain untimed lyrics cannot tell an instrumental intro from a sung downbeat.
LRC / SRT / ``[m:ss] line`` input is the source of truth: a clip with no line
overlapping its kept ``time:`` range is instrumental.
"""

from __future__ import annotations

import json
import math
import os
import re

try:
    from .song_math import (
        FPS, PLANNING_HEAD_FRAMES, PLANNING_TAIL_FRAMES,
        clamp_max_duration_seconds, grid_duration_seconds, plan_clip_windows,
    )
except ImportError:  # direct test import from package directory
    from song_math import (
        FPS, PLANNING_HEAD_FRAMES, PLANNING_TAIL_FRAMES,
        clamp_max_duration_seconds, grid_duration_seconds, plan_clip_windows,
    )

_LRC_LINE = re.compile(
    r"^\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?(?:-(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?)?\]\s*(.*)$"
)
_LRC_META = re.compile(r"^\[(ti|ar|al|au|by|re|ve|offset):", re.I)
_SIMPLE_SECONDS = re.compile(
    r"^\[(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?\]\s*(.*)$"
)
_CLOCK = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[.,](\d{1,3}))?\s+(.*)$"
)
_SRT_ARROW = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
# Sustained vowel in confirm LRC: ~time~ or ~tiiiiiime~
_HOLD_TOKEN = re.compile(r"~([^~\s]+)~")
_INSTRUMENTAL_MARK = re.compile(
    r"^\s*(?:<\s*instrumental\s*>|\(\s*instrumental\s*\)|instrumental)\s*$",
    re.I,
)


def is_instrumental_marker(text: str) -> bool:
    """Confirm/CLIP line that is a timed rest, not sung words."""
    return bool(_INSTRUMENTAL_MARK.match(str(text or "").strip()))


_VOWEL_RUN = re.compile(r"([aeiouAEIOU])\1{2,}")
_VOWELS = "aeiouAEIOU"


def collapse_elongated_vowels(text: str) -> str:
    """Collapse aaa/iii runs so wav2vec2 sees normal orthography."""
    return _VOWEL_RUN.sub(r"\1", str(text or ""))


def align_lyric_text(text: str) -> str:
    """Confirm line text for forced-align: strip ``~holds~``, collapse elongations."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    plain = _HOLD_TOKEN.sub(lambda m: m.group(1), raw)
    return " ".join(
        collapse_elongated_vowels(tok) for tok in plain.split() if tok
    )


def elongate_hold_token(token: str, duration: float | None = None) -> str:
    """Spell a held syllable for lip-sync prompts (tiiiiime)."""
    tok = str(token or "").strip()
    if not tok:
        return tok
    if _VOWEL_RUN.search(tok):
        return tok
    idx = next((i for i, ch in enumerate(tok) if ch in _VOWELS), -1)
    if idx < 0:
        return tok
    span = 1.0 if duration is None else max(0.35, float(duration))
    extra = max(4, min(12, int(round(span * 2.5))))
    ch = tok[idx]
    return tok[:idx] + (ch * (1 + extra)) + tok[idx + 1:]


def hold_token_metas(text: str, line_duration: float | None = None) -> list[dict]:
    """Per-token align/sung/hold from confirm markup or elongated spelling."""
    raw = str(text or "").strip()
    if not raw:
        return []
    metas = []
    pos = 0
    for m in _HOLD_TOKEN.finditer(raw):
        before = raw[pos:m.start()]
        for tok in before.split():
            metas.append(_token_meta(tok, hold=False, duration=None))
        inner = m.group(1)
        metas.append(_token_meta(inner, hold=True, duration=line_duration))
        pos = m.end()
    for tok in raw[pos:].split():
        metas.append(_token_meta(tok, hold=False, duration=None))
    if line_duration is not None and metas:
        held = [m for m in metas if m["hold"]]
        if held:
            share = float(line_duration) / len(held)
            for m in held:
                if not _VOWEL_RUN.search(m["sung"]):
                    m["sung"] = elongate_hold_token(m["align"], share)
    return metas


def _token_meta(tok: str, hold: bool, duration: float | None) -> dict:
    raw = str(tok).strip()
    align = collapse_elongated_vowels(raw)
    auto_hold = bool(_VOWEL_RUN.search(raw))
    is_hold = hold or auto_hold
    if auto_hold:
        sung = raw
    elif is_hold:
        sung = elongate_hold_token(align, duration)
    else:
        sung = align
    return {"align": align, "sung": sung, "hold": is_hold, "raw": raw}


def format_hold_lyric_text(text: str = "", words=None) -> str:
    """Rebuild a lyric line, wrapping held words in ``~sung~``."""
    raw = str(text or "").strip()
    word_list = list(words or [])
    if word_list and (
        any(w.get("hold") for w in word_list)
        or not raw
        or len(word_list) == len(align_lyric_text(raw).split())
    ):
        parts = []
        for word in word_list:
            core = str(word.get("sung") or word.get("text") or "").strip()
            if not core:
                continue
            if word.get("hold"):
                parts.append(f"~{core}~")
            else:
                parts.append(core)
        if parts:
            return " ".join(parts)
    if not raw:
        return ""
    metas = hold_token_metas(raw)
    if not metas:
        return raw
    parts = []
    for m in metas:
        if m["hold"]:
            parts.append(f"~{m['sung']}~")
        else:
            parts.append(m["align"])
    return " ".join(parts)


def apply_hold_markup_to_line(line: dict) -> dict:
    """Attach hold/sung onto words from confirm ``~token~`` / elongated spelling."""
    out = dict(line)
    lo = float(out["start"])
    hi = float(out["end"]) if out.get("end") is not None else lo
    dur = max(0.0, hi - lo)
    raw_text = str(out.get("text") or "").strip()
    metas = hold_token_metas(raw_text, line_duration=dur if dur > 0 else None)
    words = [dict(w) for w in _real_line_words(out)]
    if metas and words and len(metas) == len(words):
        for word, meta in zip(words, metas):
            word["text"] = meta["align"]
            if meta["hold"]:
                word["hold"] = True
                wdur = float(word["end"]) - float(word["start"])
                if _VOWEL_RUN.search(meta["raw"]):
                    word["sung"] = meta["raw"]
                else:
                    word["sung"] = elongate_hold_token(
                        meta["align"], wdur if wdur > 0.05 else (dur if dur > 0 else None),
                    )
            else:
                word.pop("hold", None)
                word.pop("sung", None)
        out["words"] = words
        out["text"] = format_hold_lyric_text(words=words)
        return out
    if metas and words:
        mi = 0
        for word in words:
            nt = _norm_tok(word.get("text", ""))
            matched = None
            for j in range(mi, len(metas)):
                if _norm_tok(metas[j]["align"]) == nt:
                    matched = metas[j]
                    mi = j + 1
                    break
            if matched is None:
                continue
            word["text"] = matched["align"]
            if matched["hold"]:
                word["hold"] = True
                wdur = float(word["end"]) - float(word["start"])
                if _VOWEL_RUN.search(matched["raw"]):
                    word["sung"] = matched["raw"]
                else:
                    word["sung"] = elongate_hold_token(
                        matched["align"], wdur if wdur > 0.05 else (dur if dur > 0 else None),
                    )
        out["words"] = words
        out["text"] = format_hold_lyric_text(words=words)
        return out
    if metas:
        out["text"] = format_hold_lyric_text(text=raw_text)
        return out
    out["text"] = raw_text
    return out


def merge_hold_markup_from_confirm(lines, confirm_lines) -> list[dict]:
    """Copy ``~hold~`` markup from confirm LRC onto aligned JSON lines by stamp."""
    by_start = {}
    for conf in confirm_lines or []:
        key = round(float(conf["start"]), 3)
        by_start[key] = conf
    out = []
    for line in lines or []:
        item = dict(line)
        conf = by_start.get(round(float(item["start"]), 3))
        if conf is not None and str(conf.get("text") or "").strip():
            item["text"] = str(conf["text"]).strip()
        out.append(apply_hold_markup_to_line(item))
    return out


def sung_prompt_text(text: str, start: float | None = None, end: float | None = None) -> tuple[str, bool]:
    """Expand hold markup for ``<d>``; returns (sung_line, has_hold)."""
    dur = None
    if start is not None and end is not None:
        dur = max(0.0, float(end) - float(start))
    metas = hold_token_metas(str(text or ""), line_duration=dur if dur and dur > 0 else None)
    if not metas:
        return str(text or "").strip(), False
    has_hold = any(m["hold"] for m in metas)
    sung = " ".join(m["sung"] for m in metas)
    return sung, has_hold


def _format_word_lyric(word: dict) -> str:
    core = str(word.get("sung") or word.get("text") or "").strip()
    if not core:
        return ""
    if word.get("hold"):
        return f"~{core}~"
    return core


def _clock_to_seconds(hours, minutes, seconds, frac) -> float:
    h = int(hours or 0)
    m = int(minutes or 0)
    s = int(seconds or 0)
    f = str(frac or "0")
    if len(f) == 1:
        sub = int(f) / 10.0
    elif len(f) == 2:
        sub = int(f) / 100.0
    else:
        sub = int(f[:3].ljust(3, "0")) / 1000.0
    return h * 3600 + m * 60 + s + sub


def has_timestamps(text: str) -> bool:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _LRC_LINE.match(stripped) or _SIMPLE_SECONDS.match(stripped) or _CLOCK.match(stripped):
            return True
        if "-->" in stripped:
            return True
    return False


def parse_timestamped_lyrics(text: str) -> list[dict]:
    """Return ``[{start, end, text}, ...]`` sorted by start.

    ``end`` is filled from the next line's start when the source has no explicit
    end (plain LRC / ``[seconds]`` lines). Range stamps and SRT keep their own
    end. The last line with no end stays open until assignment (song/fallback).
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []
    if "-->" in raw:
        lines = _parse_srt(raw)
    else:
        lines = _parse_cue_lines(raw)
    lines = [ln for ln in lines if str(ln.get("text", "")).strip()]
    lines.sort(key=lambda ln: float(ln["start"]))
    return _fill_missing_ends(lines)


def lyric_time_spans(text: str) -> list[tuple[float, float]]:
    """Start/end seconds from a CLIP ``lyrics:`` block. Empty for instrumental."""
    spans = []
    for line in parse_timestamped_lyrics(text):
        start = float(line["start"])
        end = float(line.get("end", start))
        if not math.isfinite(start) or start < 0:
            continue
        if not math.isfinite(end) or end < start:
            end = start
        if end > start:
            spans.append((start, end))
    return spans


def lyric_time_spans_from_clips(clips) -> list[tuple[float, float]]:
    spans = []
    for clip in clips or []:
        spans.extend(lyric_time_spans(clip.get("lyrics") or ""))
    return spans


def assign_lyrics_to_windows(
    lines, song_seconds: float, duration_seconds: float,
    head_frames: int = PLANNING_HEAD_FRAMES,
    tail_frames: int = PLANNING_TAIL_FRAMES,
    extra: int = 0,
) -> list[dict]:
    """Place lyric words on the CLIP whose Ref2VA ``<Audio 1>`` contains them.

    Crop to the generate slice ``[slice, slice+duration)`` (the ``audio:``
    header), not kept ``time:``. Continuation head is in that slice, so those
    words stay in the prompt. The discarded generate tail is also in
    ``<Audio 1>`` and is prompted here. The same overlap words can appear on
    consecutive CLIPs. Crumbs under 0.2s are dropped.
    """
    del extra
    spans = []
    resolved = []
    for line in lines or []:
        item = dict(line)
        item["end"] = _resolved_end(item, song_seconds)
        if is_instrumental_marker(item.get("text")):
            item["text"] = "<instrumental>"
            item["words"] = []
        elif _real_line_words(item):
            item = complete_line_words(item)
        start = float(item["start"])
        resolved.append(item)
        spans.append((start, float(item["end"])))
    planned = plan_clip_windows(
        song_seconds, duration_seconds,
        lyric_spans=spans,
        head_frames=head_frames, tail_frames=tail_frames,
    )
    buckets = [[] for _ in planned]
    for line in resolved:
        start = float(line["start"])
        end = float(line["end"])
        if not math.isfinite(start) or start < 0:
            continue
        for i, window in enumerate(planned):
            gen_s, gen_e = _generate_span(window)
            if not (start < gen_e and end > gen_s):
                continue
            prev = planned[i - 1] if i else None
            cropped = crop_line_to_window(line, window, prev=prev)
            if cropped is not None:
                buckets[i].append(cropped)
    windows = []
    for i, window in enumerate(planned):
        hits = buckets[i]
        hits.sort(key=lambda ln: float(ln["start"]))
        sung_hits = [ln for ln in hits if not is_instrumental_marker(ln.get("text"))]
        windows.append({
            "index": int(window["index"]),
            "start": float(window["start"]),
            "end": float(window["end"]),
            "duration_seconds": float(window["duration_seconds"]),
            "grid_frames": int(window["grid_frames"]),
            "slice_start": int(window["slice_start"]),
            "instrumental": not sung_hits,
            "lines": split_lines_evenly(hits),
        })
    return windows


def _even_chunks(items, n: int) -> list[list]:
    n = max(1, min(int(n), len(items)))
    if n == 1:
        return [list(items)]
    base, extra = divmod(len(items), n)
    out = []
    i = 0
    for k in range(n):
        take = base + (1 if k < extra else 0)
        chunk = items[i:i + take]
        i += take
        if chunk:
            out.append(chunk)
    return out


def split_lines_evenly(lines) -> list[dict]:
    """Keep confirm phrases intact. Only even-split a single long CLIP line into shots."""
    incoming = [ln for ln in (lines or []) if str(ln.get("text") or "").strip() or _real_line_words(ln)]
    if not incoming:
        return []
    out = []
    lone = len(incoming) == 1
    for line in incoming:
        words = _real_line_words(line)
        if not words:
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            item = {
                "start": float(line["start"]),
                "end": float(line.get("end") or line["start"]),
                "text": text,
            }
            if line.get("cropped"):
                item["cropped"] = True
            out.append(item)
            continue
        n = 2 if lone and len(words) >= 4 else 1
        for chunk in _even_chunks(words, n):
            item = {
                "start": float(chunk[0]["start"]),
                "end": float(chunk[-1]["end"]),
                "text": format_hold_lyric_text(words=chunk),
                "words": chunk,
            }
            if line.get("cropped"):
                item["cropped"] = True
            if item["text"]:
                out.append(item)
    return out


def line_overlaps_kept(start: float, end: float, window: dict) -> bool:
    """True when ``[start, end)`` overlaps kept ``time:`` ``[window.start, window.end)``."""
    return float(start) < float(window["end"]) and float(end) > float(window["start"])


MIN_LYRIC_FRAGMENT = 0.20


def _generate_span(window: dict) -> tuple[float, float]:
    if "slice_start" in window and window.get("duration_seconds") is not None:
        gen_s = int(window["slice_start"]) / float(FPS)
        gen_e = gen_s + float(window["duration_seconds"])
        return gen_s, gen_e
    return float(window["start"]), float(window["end"])


def _heard_span(window: dict, prev: dict | None = None) -> tuple[float, float]:
    """Song range this CLIP should sing: the Ref2VA ``<Audio 1>`` slice."""
    del prev
    return _generate_span(window)


def crop_line_to_window(line: dict, window: dict, prev: dict | None = None) -> dict | None:
    """Keep words that fall inside this CLIP's ``<Audio 1>`` slice."""
    del prev
    crop_s, crop_e = _heard_span(window)
    start = float(line["start"])
    end = float(line["end"])
    orig_words = _real_line_words(line)
    if not orig_words:
        return _whole_line_if_overlaps(line, crop_s, crop_e)
    pieces = []
    for word in orig_words:
        piece = _word_piece_for_window(word, crop_s, crop_e)
        if piece is not None:
            pieces.append(piece)
    if not pieces:
        return None
    kept_all = (
        len(pieces) == len(orig_words)
        and all(
            (p.get("sung") or p["text"]) == (o.get("sung") or o["text"])
            and bool(p.get("hold")) == bool(o.get("hold"))
            for p, o in zip(pieces, orig_words)
        )
    )
    if kept_all:
        text = format_hold_lyric_text(words=orig_words) or str(line["text"]).strip()
    else:
        text = " ".join(
            _format_word_lyric(w) for w in pieces if _format_word_lyric(w)
        )
    if not text:
        return None
    out_start = float(pieces[0]["start"])
    out_end = float(pieces[-1]["end"])
    cropped = abs(out_start - start) > 1e-4 or abs(out_end - end) > 1e-4 or text != str(line["text"]).strip()
    if cropped and (out_end - out_start) < MIN_LYRIC_FRAGMENT:
        return None
    out = dict(line)
    out["start"] = out_start
    out["end"] = out_end
    out["text"] = text
    out["words"] = pieces
    out["cropped"] = cropped
    return out


def _real_line_words(line: dict) -> list[dict]:
    """Aligned word clocks only. Never invent even splits from the line stamp."""
    words = []
    for item in line.get("words") or []:
        text = str(item.get("text", item.get("word", ""))).strip()
        if not text:
            continue
        w_start = float(item.get("start", line["start"]))
        w_end = float(item.get("end", w_start))
        word = {"start": w_start, "end": max(w_end, w_start), "text": text}
        chars = _parse_chars(item.get("chars"))
        if chars:
            word["chars"] = chars
        if item.get("hold"):
            word["hold"] = True
            sung = str(item.get("sung") or "").strip()
            if sung:
                word["sung"] = sung
        words.append(word)
    return words


def _whole_line_if_overlaps(line: dict, crop_s: float, crop_e: float) -> dict | None:
    start = float(line["start"])
    end = float(line["end"])
    if end <= crop_s or start >= crop_e:
        return None
    if (min(end, crop_e) - max(start, crop_s)) < MIN_LYRIC_FRAGMENT:
        return None
    out = dict(line)
    out["cropped"] = False
    return out


def _word_piece_for_window(word: dict, ws: float, we: float) -> dict | None:
    w0 = float(word["start"])
    w1 = float(word["end"])
    if w1 <= w0:
        w1 = w0 + 0.01
    if w1 <= ws or w0 >= we:
        return None
    text = str(word["text"])
    if w0 >= ws and w1 <= we:
        out = {"start": w0, "end": w1, "text": text}
        if word.get("chars"):
            out["chars"] = word["chars"]
        if word.get("hold"):
            out["hold"] = True
            if word.get("sung"):
                out["sung"] = word["sung"]
        return out
    cut0 = max(w0, ws)
    cut1 = min(w1, we)
    if word.get("chars"):
        sliced = _slice_word_text(word, cut0, cut1)
        if _letter_count(sliced) >= 2 and not _leading_suffix_crumb(word, sliced, ws):
            out = {"start": cut0, "end": cut1, "text": sliced}
            chars = _chars_in_span(word.get("chars"), cut0, cut1)
            if chars:
                out["chars"] = chars
            return out
    mid = 0.5 * (w0 + w1)
    if ws <= mid < we:
        out = {"start": cut0, "end": cut1, "text": text}
        if word.get("hold"):
            out["hold"] = True
            if word.get("sung"):
                out["sung"] = word["sung"]
        return out
    return None


def _slice_word_text(word: dict, cut0: float, cut1: float) -> str:
    chars = word.get("chars")
    if chars:
        kept = []
        for ch in chars:
            c0 = float(ch["start"])
            if cut0 <= c0 < cut1:
                kept.append(str(ch["char"]))
        if kept:
            return "".join(kept).strip()
    text = str(word["text"])
    w0 = float(word["start"])
    w1 = float(word["end"])
    span = max(w1 - w0, 1e-6)
    n = len(text)
    i0 = max(0, min(n, int(round((cut0 - w0) / span * n))))
    i1 = max(0, min(n, int(round((cut1 - w0) / span * n))))
    if i1 <= i0:
        return ""
    return text[i0:i1].strip()


def _chars_in_span(chars, cut0: float, cut1: float) -> list[dict]:
    out = []
    for ch in chars or []:
        c0 = float(ch["start"])
        if cut0 <= c0 < cut1:
            out.append(dict(ch))
    return out


def _parse_chars(raw) -> list[dict]:
    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ch = str(item.get("char", item.get("text", "")))
        if not ch:
            continue
        start = item.get("start")
        end = item.get("end")
        if start is None or end is None:
            continue
        out.append({"char": ch, "start": float(start), "end": float(end)})
    return out


def _letter_count(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum() or ch in "'’")


def _first_letter(text: str) -> str:
    for ch in str(text):
        if ch.isalnum() or ch in "'’":
            return ch.lower()
    return ""


def _leading_suffix_crumb(word: dict, sliced: str, window_start: float) -> bool:
    """Drop leftovers like ``ta`` from ``data`` at a CLIP audio start."""
    if float(word["start"]) >= window_start:
        return False
    if _letter_count(sliced) >= 3:
        return False
    orig = _first_letter(word.get("text", ""))
    got = _first_letter(sliced)
    return bool(orig) and got != orig


def _norm_tok(text: str) -> str:
    return "".join(ch for ch in str(text).lower() if ch.isalnum() or ch in "'’")


def _line_tokens(text: str) -> list[str]:
    return [tok for tok in align_lyric_text(text).split() if tok]


def _glyph_weight(text: str) -> int:
    return max(1, sum(1 for ch in text if not ch.isspace()))


def _guess_chars(text: str, start: float, end: float) -> list[dict]:
    glyphs = [c for c in str(text) if not c.isspace()]
    if not glyphs:
        return []
    lo = float(start)
    hi = float(end)
    if hi <= lo:
        hi = lo + 0.01
    step = (hi - lo) / len(glyphs)
    out = []
    for i, glyph in enumerate(glyphs):
        out.append({
            "char": glyph,
            "start": lo + i * step,
            "end": hi if i + 1 == len(glyphs) else lo + (i + 1) * step,
        })
    return out


def _even_token_clocks(tokens, start: float, end: float) -> list[dict]:
    tokens = [str(tok).strip() for tok in (tokens or []) if str(tok).strip()]
    if not tokens:
        return []
    lo = float(start)
    hi = float(end)
    if hi <= lo:
        hi = lo + 0.01
    weights = [_glyph_weight(tok) for tok in tokens]
    total = float(sum(weights))
    span = hi - lo
    words = []
    cursor = lo
    for i, (tok, weight) in enumerate(zip(tokens, weights)):
        w1 = hi if i + 1 == len(tokens) else cursor + span * (weight / total)
        word = {"start": cursor, "end": w1, "text": tok, "guessed": True}
        chars = _guess_chars(tok, cursor, w1)
        if chars:
            word["chars"] = chars
        words.append(word)
        cursor = w1
    return words


_MIN_GUESSED_WORD = 0.08
# Aligned clocks that only cover a thin slice of the locked stamp (held vowels,
# failed letter timing) are treated as a miss and even-split across the stamp.
_MIN_ALIGN_COVERAGE = 0.5


def complete_line_words(line: dict) -> dict:
    """Keep every confirm token. Fill clocks wav2vec2 dropped inside the line stamp."""
    out = dict(line)
    lo = float(out["start"])
    hi = float(out["end"]) if out.get("end") is not None else lo
    if hi <= lo:
        hi = lo + 0.01
        out["end"] = hi
    text = str(out.get("text") or "").strip()
    if is_instrumental_marker(text):
        out["text"] = "<instrumental>"
        out["words"] = []
        return out
    out["text"] = text
    tokens = _line_tokens(text)
    if not tokens:
        return out
    aligned = [dict(w) for w in _real_line_words(out)]
    filled = _fit_tokens_to_words(tokens, aligned, lo, hi)
    for word in filled:
        if not word.get("chars"):
            word["chars"] = _guess_chars(word["text"], word["start"], word["end"])
    out["words"] = filled
    return apply_hold_markup_to_line(out)


def _align_covers_stamp(words, lo: float, hi: float) -> bool:
    """True when word clocks are usable for the locked confirm window.

    Late pickups that still finish near the stamp end are kept. A thin burst
    that leaves a large trailing hole (held vowels, failed letter timing) is not.
    """
    if not words:
        return False
    span = float(hi) - float(lo)
    if span <= 1e-9:
        return True
    first = max(float(lo), min(float(w["start"]) for w in words))
    last = min(float(hi), max(float(w["end"]) for w in words))
    covered = last - first
    if covered >= span * _MIN_ALIGN_COVERAGE:
        return True
    trail = float(hi) - last
    return trail <= span * (1.0 - _MIN_ALIGN_COVERAGE)


def _fit_tokens_to_words(tokens, aligned, lo: float, hi: float) -> list[dict]:
    if len(aligned) == len(tokens):
        out = []
        for tok, word in zip(tokens, aligned):
            item = dict(word)
            item["text"] = tok
            out.append(item)
        if _align_covers_stamp(out, lo, hi):
            return out
        return _even_token_clocks(tokens, lo, hi)
    if not aligned:
        return _even_token_clocks(tokens, lo, hi)
    slots = [None] * len(tokens)
    ai = 0
    for ti, tok in enumerate(tokens):
        nt = _norm_tok(tok)
        matched = None
        for j in range(ai, len(aligned)):
            if _norm_tok(aligned[j].get("text", "")) == nt:
                matched = dict(aligned[j])
                matched["text"] = tok
                ai = j + 1
                break
        if matched is None and (len(tokens) - ti) == (len(aligned) - ai) and ai < len(aligned):
            matched = dict(aligned[ai])
            matched["text"] = tok
            ai += 1
        slots[ti] = matched
    i = 0
    while i < len(slots):
        if slots[i] is not None:
            i += 1
            continue
        k = i
        while k < len(slots) and slots[k] is None:
            k += 1
        prev = slots[i - 1] if i else None
        nxt = slots[k] if k < len(slots) else None
        gap_lo = float(prev["end"]) if prev is not None else lo
        gap_hi = float(nxt["start"]) if nxt is not None else hi
        missing = tokens[i:k]
        need = _MIN_GUESSED_WORD * len(missing)
        if gap_hi - gap_lo < need:
            if nxt is None and prev is not None:
                gap_lo = max(lo, min(gap_lo, hi - need))
                if float(prev["end"]) > gap_lo:
                    prev["end"] = gap_lo
                    if prev.get("chars"):
                        prev["chars"] = [
                            c for c in prev["chars"] if float(c["start"]) < gap_lo
                        ] or _guess_chars(prev["text"], prev["start"], prev["end"])
            elif prev is None and nxt is not None:
                gap_hi = min(hi, max(gap_hi, lo + need))
                if float(nxt["start"]) < gap_hi:
                    nxt["start"] = gap_hi
            else:
                steal = need / 2.0
                if prev is not None:
                    gap_lo = max(float(prev["start"]), float(prev["end"]) - steal)
                    prev["end"] = gap_lo
                if nxt is not None:
                    gap_hi = min(float(nxt["end"]), float(nxt["start"]) + steal)
                    nxt["start"] = gap_hi
        if gap_hi <= gap_lo:
            gap_hi = gap_lo + 0.01 * len(missing)
        slots[i:k] = _even_token_clocks(missing, gap_lo, min(hi, gap_hi))
        i = k
    out = [w for w in slots if w is not None]
    if _align_covers_stamp(out, lo, hi):
        return out
    return _even_token_clocks(tokens, lo, hi)


def dump_aligned_lyrics(lines, song_seconds: float | None = None, source: str = "") -> str:
    """JSON with word/char clocks. LRC cannot store these, so rebuilds must load this."""
    payload = {"source": str(source or ""), "lines": []}
    if song_seconds is not None:
        payload["song_seconds"] = float(song_seconds)
    for line in lines or []:
        text = str(line.get("text", "")).strip()
        if not text:
            continue
        words = []
        for word in _real_line_words(line):
            dumped = {
                "start": float(word["start"]),
                "end": float(word["end"]),
                "text": str(word["text"]).strip(),
            }
            chars = _parse_chars(word.get("chars"))
            if chars:
                dumped["chars"] = chars
            if word.get("hold"):
                dumped["hold"] = True
                sung = str(word.get("sung") or "").strip()
                if sung:
                    dumped["sung"] = sung
            words.append(dumped)
        words.sort(key=lambda w: float(w["start"]))
        item = {
            "start": float(line["start"]),
            "end": float(line["end"]) if line.get("end") is not None else float(line["start"]),
            "text": format_hold_lyric_text(text=text, words=words) or text,
        }
        if words:
            item["words"] = words
        payload["lines"].append(item)
    payload["lines"].sort(key=lambda ln: float(ln["start"]))
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def aligned_words_path(lyrics_path: str) -> str:
    root, _ext = os.path.splitext(lyrics_path)
    return root + ".words.json"


def confirm_lyrics_path(out_path: str) -> str:
    root, _ext = os.path.splitext(os.path.abspath(out_path))
    return root + ".confirm.lrc"


def load_timed_lyrics(path: str) -> list[dict]:
    """Prefer ``*.words.json`` (aligned word clocks). Plain LRC/SRT has line stamps only."""
    path = os.path.abspath(path)
    if path.lower().endswith(".json"):
        return [apply_hold_markup_to_line(ln) for ln in _load_aligned_json(path)]
    sibling = aligned_words_path(path)
    with open(path, encoding="utf-8") as handle:
        confirm_lines = parse_timestamped_lyrics(handle.read())
    if os.path.isfile(sibling):
        return merge_hold_markup_from_confirm(_load_aligned_json(sibling), confirm_lines)
    return [apply_hold_markup_to_line(ln) for ln in confirm_lines]


def _load_aligned_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    raw_lines = payload if isinstance(payload, list) else (payload.get("lines") or [])
    out = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = float(item["start"])
        line = {
            "start": start,
            "end": float(item["end"]) if item.get("end") is not None else start,
            "text": text,
        }
        words = _real_line_words(item)
        if words:
            words.sort(key=lambda w: float(w["start"]))
            line["words"] = words
        out.append(complete_line_words(line))
    out.sort(key=lambda ln: float(ln["start"]))
    return out


def format_lrc(lines) -> str:
    rows = []
    for line in lines or []:
        text = str(line.get("text", "")).strip()
        if is_instrumental_marker(text):
            text = "<instrumental>"
        else:
            text = format_hold_lyric_text(
                text=text,
                words=_real_line_words(line) or None,
            )
        if not text:
            continue
        stamp = _format_timestamp(float(line["start"]))
        end = line.get("end")
        if end is not None and float(end) > float(line["start"]):
            stamp = f"{stamp}-{_format_timestamp(float(end))}"
        rows.append(f"[{stamp}] {text}")
    return "\n".join(rows) + ("\n" if rows else "")


_SECTION_HEADER = re.compile(
    r"^\s*\[(verse|chorus|bridge|intro|outro|hook|pre-?chorus|refrain|solo|instrumental|tag).*"
    r"\]\s*$",
    re.I,
)
_WORD = re.compile(r"[a-z0-9']+", re.I)


def split_plain_lyric_lines(text: str) -> list[str]:
    """User lyrics as sung lines. Drops blanks and [Chorus]-style labels."""
    lines = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = raw.strip()
        if not stripped or _SECTION_HEADER.match(stripped):
            continue
        m = _LRC_LINE.match(stripped)
        if m:
            stripped = m.group(7).strip()
            if not stripped:
                continue
        else:
            sm = _SIMPLE_SECONDS.match(stripped)
            if sm:
                stripped = sm.group(3).strip()
                if not stripped:
                    continue
        lines.append(stripped)
    return lines


_RANGE_CLOCK = re.compile(
    r"^\s*\[?(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\s*-\s*(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]?\s*$"
)
_RANGE_SECS = re.compile(
    r"^\s*\[?(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\]?\s*$"
)
PHRASE_GAP = 0.40
MAX_PHRASE_WORDS = 8
SECONDS_PER_DRAFT_WORD = 0.35
MIN_DRAFT_SECONDS = 0.30
MAX_DRAFT_SECONDS = 2.0
GAP_PAD = 0.04


def parse_time_range(text: str) -> tuple[float, float]:
    """Parse ``131.042-136.917`` or ``02:11.042-02:12.720`` into seconds."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError("empty time range")
    first = raw.split("\n", 1)[0].strip()
    m = _RANGE_CLOCK.match(first)
    if m:
        start = _clock_to_seconds(0, m.group(1), m.group(2), m.group(3))
        end = _clock_to_seconds(0, m.group(4), m.group(5), m.group(6))
        if end <= start:
            raise ValueError(f"range end must be after start: {first}")
        return start, end
    m = _RANGE_SECS.match(first)
    if m:
        start = float(m.group(1))
        end = float(m.group(2))
        if end <= start:
            raise ValueError(f"range end must be after start: {first}")
        return start, end
    raise ValueError(
        f"time range must be seconds or clocks, e.g. 131.042-136.917 or 02:11.042-02:12.720; got {first!r}"
    )


def _line_from_words(chunk) -> dict:
    words = [dict(w) for w in chunk]
    return {
        "start": float(words[0]["start"]),
        "end": float(words[-1]["end"]),
        "text": " ".join(str(w["text"]).strip() for w in words if str(w.get("text", "")).strip()),
        "words": words,
    }


def phrase_lines_from_words(words) -> list[dict]:
    """Group consecutive ASR words into short confirm-file lines."""
    items = [w for w in words or [] if str(w.get("text", "")).strip()]
    if not items:
        return []
    lines = []
    chunk = [items[0]]
    for word in items[1:]:
        gap = float(word["start"]) - float(chunk[-1]["end"])
        if gap >= PHRASE_GAP or len(chunk) >= MAX_PHRASE_WORDS:
            lines.append(_line_from_words(chunk))
            chunk = [word]
        else:
            chunk.append(word)
    if chunk:
        lines.append(_line_from_words(chunk))
    return [ln for ln in lines if ln["text"]]


def phrase_lines_from_segments(segments) -> list[dict]:
    return phrase_lines_from_words(_whisper_words(segments))


def _free_gaps(occupied, t0: float, t1: float) -> list[tuple[float, float]]:
    spans = sorted(
        (float(s), float(e)) for s, e in occupied
        if e is not None and float(e) > float(s)
    )
    gaps = []
    cur = float(t0)
    for start, end in spans:
        if start > cur + 1e-4:
            gaps.append((cur, start))
        cur = max(cur, end)
    if t1 > cur + 1e-4:
        gaps.append((cur, t1))
    return gaps


def _draft_duration(text: str) -> float:
    n = max(1, len(_WORD.findall(text)))
    return min(MAX_DRAFT_SECONDS, max(MIN_DRAFT_SECONDS, n * SECONDS_PER_DRAFT_WORD))


def _place_draft(text: str, occupied, prefer_after: float, song_end: float) -> tuple[float, float]:
    dur = _draft_duration(text)
    gaps = _free_gaps(occupied, 0.0, song_end)
    later = [(s, e) for s, e in gaps if e > prefer_after]
    pool = later or gaps
    if not pool:
        start = max(0.0, prefer_after)
        return start, min(song_end, start + dur)

    def usable(gap):
        s = max(float(gap[0]), prefer_after if later else float(gap[0]))
        e = float(gap[1])
        inner_s = s + GAP_PAD if e - s > 2 * GAP_PAD else s
        inner_e = e - GAP_PAD if e - s > 2 * GAP_PAD else e
        return inner_s, inner_e

    fit = None
    for gap in pool:
        inner_s, inner_e = usable(gap)
        if inner_e - inner_s >= dur:
            fit = (inner_s, inner_s + dur)
            break
    if fit is None:
        gap = max(pool, key=lambda g: usable(g)[1] - usable(g)[0])
        inner_s, inner_e = usable(gap)
        end = max(inner_s + MIN_DRAFT_SECONDS, inner_e)
        fit = (inner_s, min(inner_e, end) if inner_e > inner_s else inner_s + MIN_DRAFT_SECONDS)
    start, end = fit
    if end <= start:
        end = start + MIN_DRAFT_SECONDS
    return start, end


def merge_asr_and_user_lyrics(segments, user_text: str, song_seconds: float | None = None) -> list[dict]:
    """User wording on ASR clocks; keep extra ASR; draft unmatched user lines into gaps."""
    words = _whisper_words(segments)
    user_lines = split_plain_lyric_lines(user_text)
    if not user_lines:
        return phrase_lines_from_words(words)
    if not words:
        return []

    user_tokens = []
    for i, line in enumerate(user_lines):
        for match in _WORD.finditer(line):
            user_tokens.append((i, match.group(0), match.group(0).lower()))
    if not user_tokens:
        return phrase_lines_from_words(words)

    whisper_norms = [
        (_WORD.findall(str(w["text"]).lower()) or [""])[0] for w in words
    ]
    user_norms = [norm for _i, _orig, norm in user_tokens]
    pairs = _align_token_indices(whisper_norms, user_norms)

    line_words = {i: [] for i in range(len(user_lines))}
    line_word_idx = {i: [] for i in range(len(user_lines))}
    for w_idx, u_idx in pairs:
        line_i, orig, _norm = user_tokens[u_idx]
        src = words[w_idx]
        start = float(src["start"])
        end = float(src.get("end") or start)
        word = {"start": start, "end": end, "text": orig}
        if src.get("chars"):
            word["chars"] = [dict(ch) for ch in src["chars"]]
        line_words[line_i].append(word)
        line_word_idx[line_i].append(w_idx)

    used = set()
    matched = []
    unmatched = []
    for i, line in enumerate(user_lines):
        usable = _usable_aligned_words(line, line_words[i])
        if usable:
            used.update(line_word_idx[i])
            item = {
                "start": float(usable[0]["start"]),
                "end": float(usable[-1]["end"]),
                "text": line,
                "words": usable,
            }
            matched.append(item)
        else:
            unmatched.append(i)

    leftover = [w for i, w in enumerate(words) if i not in used]
    extras = phrase_lines_from_words(leftover)
    last_word = float(words[-1].get("end") or words[-1]["start"])
    song_end = float(song_seconds) if song_seconds and song_seconds > 0 else last_word + 4.0
    occupied = [(float(ln["start"]), float(ln["end"])) for ln in matched + extras]

    drafts = []
    prefer_after = 0.0
    matched_by_user = {}
    mi = 0
    for i, line in enumerate(user_lines):
        if i in unmatched:
            continue
        matched_by_user[i] = matched[mi]
        mi += 1

    for i, line in enumerate(user_lines):
        if i not in unmatched:
            prefer_after = max(prefer_after, float(matched_by_user[i]["end"]))
            continue
        start, end = _place_draft(line, occupied, prefer_after, song_end)
        item = {"start": start, "end": end, "text": line, "draft": True}
        drafts.append(item)
        occupied.append((start, end))
        prefer_after = end

    out = matched + extras + drafts
    out.sort(key=lambda ln: float(ln["start"]))
    return out


def align_user_lyrics_to_segments(user_text: str, segments) -> list[dict]:
    """Keep the user's words; take start times from Whisper (or similar) segments.

    Instrumental audio before the first aligned vocal does not move lyrics to 0:00.
    """
    user_lines = split_plain_lyric_lines(user_text)
    if not user_lines:
        return []
    words = _whisper_words(segments)
    if not words:
        return []

    user_tokens = []
    for i, line in enumerate(user_lines):
        for match in _WORD.finditer(line):
            user_tokens.append((i, match.group(0), match.group(0).lower()))
    if not user_tokens:
        return [{"start": float(words[0]["start"]), "end": None, "text": line} for line in user_lines]

    whisper_tokens = [_WORD.findall(str(w["text"]).lower()) for w in words]
    whisper_norms = [toks[0] if toks else "" for toks in whisper_tokens]
    user_norms = [norm for _i, _orig, norm in user_tokens]
    pairs = _align_token_indices(whisper_norms, user_norms)

    line_starts = {}
    line_ends = {}
    line_words = {i: [] for i in range(len(user_lines))}
    for w_idx, u_idx in pairs:
        if w_idx is None or u_idx is None:
            continue
        line_i, orig, _norm = user_tokens[u_idx]
        start = float(words[w_idx]["start"])
        end = float(words[w_idx].get("end") or start)
        word = {"start": start, "end": end, "text": orig}
        if words[w_idx].get("chars"):
            word["chars"] = [dict(ch) for ch in words[w_idx]["chars"]]
        line_words[line_i].append(word)
        if line_i not in line_starts:
            line_starts[line_i] = start
        line_ends[line_i] = max(end, line_ends.get(line_i, end))

    for i, line in enumerate(user_lines):
        usable = _usable_aligned_words(line, line_words[i])
        if usable:
            line_words[i] = usable
            line_starts[i] = float(usable[0]["start"])
            line_ends[i] = float(usable[-1]["end"])
        else:
            line_words[i] = []
            line_starts.pop(i, None)
            line_ends.pop(i, None)

    vocal_start = float(words[0]["start"])
    vocal_end = float(words[-1].get("end") or words[-1]["start"])
    aligned = []
    prev_start = None
    for i, line in enumerate(user_lines):
        start = line_starts.get(i)
        if start is None:
            start = _interpolate_line_start(i, len(user_lines), line_starts, vocal_start, vocal_end, prev_start)
        end = line_ends.get(i)
        item = {"start": float(start), "end": None if end is None else float(end), "text": line}
        if line_words[i]:
            item["words"] = line_words[i]
        aligned.append(item)
        prev_start = float(start)
    aligned.sort(key=lambda ln: ln["start"])
    return _fill_missing_ends(aligned)


_MIN_LINE_MATCH_FRACTION = 0.5
_MIN_SECONDS_PER_MATCHED_WORD = 0.12


def _usable_aligned_words(line: str, words: list) -> list:
    """Drop a line's token hits when too few words matched, or the span is too short.

    A leftover ASR token such as ``whole`` must not pull a seven-word line into 60 ms.
    """
    if not words:
        return []
    n = len(_WORD.findall(line))
    if n <= 2:
        return words
    need = max(2, math.ceil(n * _MIN_LINE_MATCH_FRACTION))
    if len(words) < need:
        return []
    span = float(words[-1]["end"]) - float(words[0]["start"])
    if span < _MIN_SECONDS_PER_MATCHED_WORD * n:
        return []
    return words


def _whisper_words(segments) -> list[dict]:
    words = []
    for seg in segments or []:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        raw_words = seg.get("words") or []
        if raw_words:
            for item in raw_words:
                text = str(item.get("text", item.get("word", ""))).strip()
                if not text:
                    continue
                w_start = float(item.get("start", start))
                w_end = float(item.get("end", w_start))
                word = {"start": w_start, "end": w_end, "text": text}
                chars = _parse_chars(item.get("chars"))
                if chars:
                    word["chars"] = chars
                words.append(word)
            continue
        toks = str(seg.get("text", "")).split()
        if not toks:
            continue
        span = max(0.01, end - start)
        step = span / len(toks)
        for i, tok in enumerate(toks):
            words.append({
                "start": start + i * step,
                "end": start + (i + 1) * step,
                "text": tok,
            })
    words.sort(key=lambda w: w["start"])
    return words


def _align_token_indices(whisper_norms, user_norms):
    """Needleman–Wunsch: skip cheap Whisper tokens (intro / filler), keep user words."""
    m, n = len(whisper_norms), len(user_norms)
    if m == 0 or n == 0:
        return []
    skip_w, skip_u, match, mismatch = 0.2, 1.2, 3.0, 1.0
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    ptr = [[""] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        dp[i][0] = -skip_w * i
        ptr[i][0] = "w"
    for j in range(1, n + 1):
        dp[0][j] = -skip_u * j
        ptr[0][j] = "u"
    for i in range(1, m + 1):
        wa = whisper_norms[i - 1]
        for j in range(1, n + 1):
            ub = user_norms[j - 1]
            diag = dp[i - 1][j - 1] + (match if wa and wa == ub else -mismatch)
            up = dp[i - 1][j] - skip_w
            left = dp[i][j - 1] - skip_u
            if diag >= up and diag >= left:
                dp[i][j] = diag
                ptr[i][j] = "m"
            elif up >= left:
                dp[i][j] = up
                ptr[i][j] = "w"
            else:
                dp[i][j] = left
                ptr[i][j] = "u"
    pairs = []
    i, j = m, n
    while i > 0 or j > 0:
        move = ptr[i][j]
        if move == "m":
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif move == "w":
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def _interpolate_line_start(index, count, line_starts, vocal_start, vocal_end, prev_start):
    if not line_starts:
        if count <= 1:
            return vocal_start
        span = max(0.0, vocal_end - vocal_start)
        return vocal_start + span * (index / max(1, count - 1))
    before = [(k, t) for k, t in line_starts.items() if k < index]
    after = [(k, t) for k, t in line_starts.items() if k > index]
    if before and after:
        k0, t0 = max(before)
        k1, t1 = min(after)
        frac = (index - k0) / (k1 - k0)
        return t0 + (t1 - t0) * frac
    if before:
        return max(line_starts[max(before)[0]], prev_start or 0.0)
    first_k, first_t = min(line_starts.items())
    gap = max(0.4, (first_t - vocal_start) / max(1, first_k))
    guessed = first_t - gap * (first_k - index)
    floor = vocal_start if prev_start is None else max(vocal_start, prev_start)
    return max(floor, guessed)


def format_window_lyrics(window: dict) -> str:
    """CLIP ``lyrics:`` body: ``(instrumental)`` or timestamped lines."""
    lines = [ln for ln in (window.get("lines") or []) if str(ln.get("text") or "").strip()]
    if not lines:
        return "(instrumental)"
    out = []
    for line in lines:
        stamp = _format_timestamp(float(line["start"]))
        end = line.get("end")
        if end is not None and float(end) > float(line["start"]):
            stamp = f"{stamp}-{_format_timestamp(float(end))}"
        text = str(line.get("text") or "").strip()
        if not is_instrumental_marker(text):
            text = format_hold_lyric_text(
                text=text,
                words=_real_line_words(line) or None,
            )
        else:
            text = "<instrumental>"
        out.append(f"[{stamp}] {text}")
    return "\n".join(out)


def format_windows_report(windows) -> str:
    rows = []
    for w in windows:
        duration = float(w.get("duration_seconds") or 0.0)
        slice_s = int(w["slice_start"]) / float(FPS) if "slice_start" in w else float(w["start"])
        head = (
            f"CLIP {w['index']} duration={duration:.3f} slice={slice_s:.3f} "
            f"{w['start']:.3f}-{w['end']:.3f}"
        )
        if w["instrumental"]:
            rows.append(f"{head} instrumental")
        else:
            rows.append(head)
            rows.append(format_window_lyrics(w))
    return "\n".join(rows)


def format_music_video_skeleton(windows, max_duration_seconds: float) -> str:
    """Machine-parseable CLIP headers. Fill only the ``prompt:`` bodies."""
    max_s = grid_duration_seconds(clamp_max_duration_seconds(max_duration_seconds))
    parts = [
        "h3_music_video: 1\n"
        f"max_duration_seconds: {max_s:.3f}\n"
        f"clip_count: {len(windows)}"
    ]
    for w in windows:
        slice_s = int(w["slice_start"]) / float(FPS) if "slice_start" in w else float(w["start"])
        audio_end = slice_s + float(w["duration_seconds"])
        block = (
            f"CLIP {w['index']}\n"
            f"time: {w['start']:.3f}-{w['end']:.3f}\n"
            f"duration_seconds: {w['duration_seconds']:.3f}\n"
            f"slice: {slice_s:.3f}\n"
            f"audio: {slice_s:.3f}-{audio_end:.3f}\n"
            f"lyrics: {format_window_lyrics(w)}\n"
            "prompt:"
        )
        parts.append(block)
    return "\n---\n".join(parts) + "\n"


def _parse_cue_lines(raw: str) -> list[dict]:
    lines = []
    for raw_line in raw.split("\n"):
        stripped = raw_line.strip()
        if not stripped or _LRC_META.match(stripped):
            continue
        m = _LRC_LINE.match(stripped)
        if m:
            minutes, seconds, frac, end_m, end_s, end_f, text = m.groups()
            start = _clock_to_seconds(0, minutes, seconds, frac)
            end = None
            if end_m is not None:
                end = _clock_to_seconds(0, end_m, end_s, end_f)
            if text.strip():
                lines.append({"start": start, "end": end, "text": text.strip()})
            continue
        m = _SIMPLE_SECONDS.match(stripped)
        if m:
            start = float(m.group(1))
            end = None if m.group(2) is None else float(m.group(2))
            text = m.group(3).strip()
            if text:
                lines.append({"start": start, "end": end, "text": text})
            continue
        m = _CLOCK.match(stripped)
        if m:
            a, b, c, frac, text = m.groups()
            if c is not None:
                start = _clock_to_seconds(a, b, c, frac)
            else:
                start = _clock_to_seconds(0, a, b, frac)
            if text.strip():
                lines.append({"start": start, "end": None, "text": text.strip()})
    return lines


def _parse_srt(raw: str) -> list[dict]:
    lines = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    for block in blocks:
        block_lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not block_lines:
            continue
        arrow = None
        text_start = 0
        for i, ln in enumerate(block_lines):
            m = _SRT_ARROW.search(ln)
            if m:
                arrow = m
                text_start = i + 1
                break
        if arrow is None:
            continue
        start = _clock_to_seconds(arrow.group(1), arrow.group(2), arrow.group(3), arrow.group(4))
        end = _clock_to_seconds(arrow.group(5), arrow.group(6), arrow.group(7), arrow.group(8))
        text = " ".join(block_lines[text_start:]).strip()
        if text:
            lines.append({"start": start, "end": end, "text": text})
    return lines


def _fill_missing_ends(lines: list[dict]) -> list[dict]:
    out = []
    for i, line in enumerate(lines):
        item = dict(line)
        if item.get("end") is None:
            if i + 1 < len(lines):
                item["end"] = float(lines[i + 1]["start"])
        out.append(item)
    return out


_DEFAULT_LINE_SECONDS = 2.0


def _resolved_end(line, song_seconds: float) -> float:
    start = float(line["start"])
    end = line.get("end")
    if end is not None and math.isfinite(float(end)) and float(end) > start:
        return float(end)
    cap = float(song_seconds) if math.isfinite(float(song_seconds)) else start + _DEFAULT_LINE_SECONDS
    return min(cap, start + _DEFAULT_LINE_SECONDS)


def _format_timestamp(seconds: float) -> str:
    total = max(0.0, float(seconds))
    minutes = int(total // 60)
    rem = total - minutes * 60
    return f"{minutes:02d}:{rem:06.3f}"


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Emit H3 Music Video CLIP headers from timestamped lyrics."
    )
    parser.add_argument("lyrics", nargs="?", default="-", help="LRC/SRT/JSON file, or - for stdin")
    parser.add_argument("--song-seconds", type=float, required=True)
    parser.add_argument("--duration", type=float, default=10.0, help="Maximum requested clip seconds before H3 snap")
    parser.add_argument("--skeleton", default="", help="Write CLIP skeleton UTF-8 file")
    parser.add_argument("--report", action="store_true", help="also print a debug CLIP report to stderr")
    args = parser.parse_args()
    if args.lyrics == "-":
        text = sys.stdin.read()
        if not has_timestamps(text):
            raise SystemExit("lyrics have no timestamps; pass LRC/SRT or [m:ss] lines")
        lines = parse_timestamped_lyrics(text)
    else:
        path = args.lyrics
        lines = load_timed_lyrics(path)
        if not lines:
            raise SystemExit("lyrics have no timestamps; pass LRC/SRT or [m:ss] lines")
    windows = assign_lyrics_to_windows(
        lines, args.song_seconds, args.duration,
    )
    skeleton = format_music_video_skeleton(windows, args.duration)
    if args.skeleton:
        sk_path = os.path.abspath(args.skeleton)
        folder = os.path.dirname(sk_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(sk_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(skeleton)
    sys.stdout.write(skeleton)
    if args.report:
        sys.stderr.write(format_windows_report(windows) + "\n")

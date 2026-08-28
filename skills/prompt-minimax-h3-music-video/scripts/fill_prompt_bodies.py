"""Fill Ref2VA prompt bodies on an H3 Music Video CLIP skeleton.

Copies CLIP headers and lyrics: unchanged. Boilerplate only: six Ref2VA
sections, audio reuse, closed lips on instrumentals, locked <d> strings,
and instrumental-cut clocks. Does not direct the video: no worlds, no
mic/dance, no environment morph.

    python fill_prompt_bodies.py song.skeleton.txt -o song-music-video.h3.txt \
        --subject "a young woman with long dark hair and goth makeup" \
        --picture1 "goth makeup, messy rock hair, skimpy pop-rock wardrobe" \
        --opening "three-quarter thighs-up in night metropolis, looking at camera"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_CLIP = re.compile(
    r"^CLIP (\d+)\n"
    r"time: ([0-9.]+)-([0-9.]+)\n"
    r"duration_seconds: ([0-9.]+)\n"
    r"slice: ([0-9.]+)\n"
    r"audio: ([0-9.]+-[0-9.]+)\n"
    r"lyrics: (.*?)\nprompt:\s*$",
    re.M | re.S,
)
_STAMP = re.compile(
    r"^\[(\d{1,2}):(\d{2})\.(\d{3})-(\d{1,2}):(\d{2})\.(\d{3})\]\s*(.*)$"
)
_HOLD = re.compile(r"~([^~\s]+)~")
_VOWELS = "aeiouAEIOU"
_HEDGE = re.compile(r"\b(sometimes|maybe|occasionally|either)\b|\bor\b", re.I)
_INSTRUMENTAL_MARK = re.compile(
    r"^\s*(?:<\s*instrumental\s*>|\(\s*instrumental\s*\)|instrumental)\s*$",
    re.I,
)


def is_instrumental_marker(text: str) -> bool:
    return bool(_INSTRUMENTAL_MARK.match(str(text or "").strip()))


def _elongate_hold(token: str, duration: float | None = None) -> str:
    tok = str(token or "").strip()
    if not tok:
        return tok
    if re.search(r"[aeiouAEIOU]{4,}", tok):
        return tok
    idx = next((i for i, ch in enumerate(tok) if ch in _VOWELS), -1)
    if idx < 0:
        return tok
    span = 1.0 if duration is None else max(0.35, float(duration))
    extra = max(4, min(12, int(round(span * 2.5))))
    ch = tok[idx]
    return tok[:idx] + (ch * (1 + extra)) + tok[idx + 1:]


def sung_d_text(text: str, start: float | None = None, end: float | None = None) -> tuple[str, bool]:
    raw = str(text or "").strip()
    dur = None
    if start is not None and end is not None:
        dur = max(0.0, float(end) - float(start))
    parts = []
    has_hold = False
    pos = 0
    for m in _HOLD.finditer(raw):
        before = raw[pos:m.start()]
        if before:
            parts.append(before)
        has_hold = True
        parts.append(_elongate_hold(m.group(1), dur))
        pos = m.end()
    parts.append(raw[pos:])
    sung = re.sub(r"\s+", " ", "".join(parts)).strip()
    return sung or raw, has_hold


def _clock(m, s, ms) -> float:
    return int(m) * 60 + int(s) + int(ms) / 1000.0


def _rel(abs_t: float, slice_s: float) -> str:
    t = max(0.0, float(abs_t) - float(slice_s))
    mm = int(t // 60)
    ss = t - mm * 60
    return f"{mm:02d}:{ss:06.3f}"


def parse_lyric_lines(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if not text or text == "(instrumental)":
        return []
    lines = []
    for row in text.splitlines():
        m = _STAMP.match(row.strip())
        if not m:
            raise SystemExit(f"bad lyric line: {row!r}")
        lines.append({
            "start": _clock(m.group(1), m.group(2), m.group(3)),
            "end": _clock(m.group(4), m.group(5), m.group(6)),
            "text": m.group(7),
        })
    return lines


def load_plan_lines(path: str | None, fallback: str, n: int) -> list[str]:
    if path:
        rows = [
            ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not rows:
            raise SystemExit(f"no lines in {path}")
    else:
        rows = [fallback] if str(fallback or "").strip() else [""]
    if not any(rows):
        return [""] * n
    last = rows[-1]
    return [rows[i] if i < len(rows) else last for i in range(n)]


def load_worlds(path: str | None, fallback: str, n: int) -> list[str]:
    return load_plan_lines(path, fallback, n)


def _assert_exact_action(text: str, label: str) -> None:
    raw = str(text or "").strip()
    if not raw:
        return
    for part in raw.split("|"):
        if _HEDGE.search(part):
            raise SystemExit(
                f"{label} is vague ({raw!r}). One committed action per take "
                f"(optional: sung | instrumental). Do not write sometimes/or/maybe."
            )


def _kind_action(clip_action: str, kind: str) -> str:
    """Kept for tests. Filler does not inject actions into shots."""
    parts = [p.strip().rstrip(".") for p in str(clip_action or "").split("|") if p.strip()]
    if not parts:
        return ""
    if kind == "instrumental" and len(parts) > 1:
        return parts[-1]
    return parts[0]


def _shot_action(clip_action: str, shot_index: int) -> str:
    del shot_index
    return _kind_action(clip_action, "sung")


def parse_clips(raw: str) -> list[dict]:
    clips = []
    for m in _CLIP.finditer(raw):
        lyrics_raw = m.group(7).strip()
        clips.append({
            "index": int(m.group(1)),
            "time_s": float(m.group(2)),
            "time_e": float(m.group(3)),
            "duration": float(m.group(4)),
            "slice": float(m.group(5)),
            "audio": m.group(6),
            "lyrics_raw": lyrics_raw,
            "lines": parse_lyric_lines(lyrics_raw),
        })
    if not clips:
        raise SystemExit("no CLIP blocks found")
    return clips


def _picture_notes(args) -> list[tuple[int, str]]:
    notes = []
    for i in range(1, 10):
        text = str(getattr(args, f"picture{i}", "") or "").strip().rstrip(".")
        if text:
            notes.append((i, text))
    return notes


def _subject_line(args) -> str:
    identity = str(args.subject or "").strip().rstrip(".")
    pics = _picture_notes(args)
    if "<Picture" in identity or not pics:
        return f"<Subject 1> is {identity}."
    if len(pics) == 1:
        i, extra = pics[0]
        cite = f"<Picture {i}>"
        if extra.lower() in identity.lower():
            return f"<Subject 1> is {identity} in {cite}."
        return f"<Subject 1> is {identity} in {cite}, {extra}."
    cites = ", ".join(f"<Picture {i}>" for i, _ in pics[:-1]) + f" and <Picture {pics[-1][0]}>"
    extras = "; ".join(extra for _, extra in pics)
    return f"<Subject 1> is {identity} in {cites}, {extras}."


def _audio_line(audio: str, sung: bool) -> str:
    voice = ""
    if sung:
        voice = ", and the singing-voice reference for <Subject 1> (S1)"
    return (
        f"<Audio 1> is the source-song slice covering {audio} of the master, "
        f"reused as the complete soundtrack{voice}."
    )


def _subject_block(args, audio: str, sung: bool) -> str:
    return "\n".join((_subject_line(args), _audio_line(audio, sung)))


def _task_prefix(first: bool, has_pictures: bool) -> str:
    parts = []
    if not first:
        parts.append("video continuation")
    if has_pictures or first:
        parts.append("reference generation")
    parts.append("audio reuse")
    return "[" + " + ".join(parts) + "]"


def _retention(first: bool) -> str:
    if first:
        sub = (
            "<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe "
            "from the reference pictures are retained."
        )
    else:
        sub = (
            "<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe "
            "continue from the previous clip."
        )
    return (
        f"{sub}\n"
        "<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete "
        "final audio track."
    )


def _soundscape() -> str:
    return (
        "The soundtrack is <Audio 1> reused as-is. No other sounds.\n"
        "non_diegetic_music: N/A"
    )


def _style(args) -> str:
    base = getattr(args, "style", None) or "live-action, cinematic, high-budget music-video"
    fx = str(getattr(args, "fx", "") or "").strip().rstrip(".")
    if fx and fx.lower() not in base.lower():
        return f"{base}, {fx}"
    return base


def _portrait_mode(args) -> str:
    mode = (getattr(args, "portrait", None) or "none").strip().lower()
    if mode == "occasional":
        return "none"
    return mode


def _assemble(args, audio: str, sung: bool, first: bool, summary: str, shots: list[str]) -> str:
    return (
        "subject_definitions:\n"
        f"{_subject_block(args, audio, sung)}\n"
        "summary:\n"
        f"{summary}\n"
        "retention_analysis:\n"
        f"{_retention(first)}\n"
        "detailed_description:\n"
        "The target video is " + _style(args) + ". "
        + " ".join(shots)
        + "\n"
        "overall_soundscape:\n"
        f"{_soundscape()}"
    )


def _clip_events(clip: dict) -> list[dict]:
    """One sung pack per vocal run, then a locked cut at each instrumental rest."""
    events = []
    sung_run = []

    def flush():
        nonlocal sung_run
        if not sung_run:
            return
        events.append({
            "kind": "sung",
            "start": float(sung_run[0]["start"]),
            "end": float(sung_run[-1]["end"]),
            "lines": list(sung_run),
        })
        sung_run = []

    for ln in clip.get("lines") or []:
        if is_instrumental_marker(ln.get("text")):
            flush()
            events.append({
                "kind": "instrumental",
                "start": float(ln["start"]),
                "end": float(ln["end"]),
                "text": "<instrumental>",
            })
        else:
            sung_run.append(ln)
    flush()
    return events


def _has_sung_lines(clip: dict) -> bool:
    return any(not is_instrumental_marker(ln.get("text")) for ln in clip.get("lines") or [])


def _late_instrumental_markers(clip: dict) -> list[dict]:
    sl = float(clip["slice"])
    return [
        ln for ln in clip.get("lines") or []
        if is_instrumental_marker(ln.get("text")) and float(ln["start"]) > sl + 0.05
    ]


def _closed_lips(_action: str = "") -> str:
    return "<Subject 1>'s lips stay closed."


def _d_tags(lines, lang: str) -> tuple[str, bool]:
    bits = []
    has_hold = False
    for ln in lines:
        sung, hold = sung_d_text(ln["text"], ln.get("start"), ln.get("end"))
        bits.append(f"<d>[{lang}] {sung}</d>")
        has_hold = has_hold or hold
    return " then ".join(bits), has_hold


def _hold_cue(has_hold: bool) -> str:
    if has_hold:
        return " <Subject 1> holds the sustained vowel."
    return ""


def _shot1_lead(first: bool, opening: str, portrait: bool) -> str:
    if first and opening:
        lead = (
            f"[Shot 1] The scene opens: {opening}. "
            "<Subject 1> (S1) is already in this space."
        )
    elif first:
        lead = "[Shot 1] <Subject 1> (S1) is already in this space."
    else:
        lead = (
            "[Shot 1] <Subject 1> (S1) is already in the previous clip's ending space; "
            "there is no pose reset."
        )
    if portrait:
        lead = lead.replace("[Shot 1] ", "[Shot 1] Close-up of ", 1)
    return lead


def instrumental_body(clip, args, world: str, prev_world: str, action: str = "") -> str:
    del world, prev_world, action
    first = clip["index"] == 1
    task = _task_prefix(first, bool(_picture_notes(args)))
    summary = f"{task} <Subject 1> through an instrumental stretch of <Audio 1>. Lips stay closed."
    if first and args.opening:
        shot1 = f"[Shot 1] The scene opens: {args.opening}. {_closed_lips()}"
    elif first:
        shot1 = f"[Shot 1] <Subject 1> is already in this space. {_closed_lips()}"
    else:
        shot1 = (
            f"[Shot 1] <Subject 1> is already in the previous clip's ending space. "
            f"{_closed_lips()}"
        )
    shots = [shot1]
    n = 2
    for ln in _late_instrumental_markers(clip):
        shots.append(
            f"[Shot {n}] At {_rel(ln['start'], clip['slice'])}, the camera cuts. "
            f"{_closed_lips()}"
        )
        n += 1
    return _assemble(args, clip["audio"], False, first, summary, shots)


def sung_body(clip, args, world: str, prev_world: str, action: str = "") -> str:
    del world, prev_world, action
    first = clip["index"] == 1
    task = _task_prefix(first, bool(_picture_notes(args)))
    portrait = _portrait_mode(args) == "exclusive"
    events = _clip_events(clip)
    mixed = any(ev["kind"] == "instrumental" for ev in events)
    summary = f"{task} <Subject 1> (S1) sings this window in sync with <Audio 1>."
    if mixed:
        summary += (
            " The camera cuts at each instrumental rest; lips stay closed through those rests."
        )
    shots = []
    n = 1
    opening = str(args.opening or "").strip().rstrip(".")
    for ev in events:
        if ev["kind"] == "instrumental":
            if n == 1:
                shots.append(f"{_shot1_lead(first, opening, False)} {_closed_lips()}")
            else:
                shots.append(
                    f"[Shot {n}] At {_rel(ev['start'], clip['slice'])}, the camera cuts. "
                    f"{_closed_lips()}"
                )
        else:
            d, has_hold = _d_tags(ev.get("lines") or [], args.language)
            if n == 1:
                lead = _shot1_lead(first, opening, portrait)
                shots.append(
                    f"{lead} Mouth and face follow <Audio 1>. "
                    f"<Subject 1> (S1) sings, {d}.{_hold_cue(has_hold)}"
                )
            else:
                shots.append(
                    f"[Shot {n}] At {_rel(ev['start'], clip['slice'])}, the camera cuts. "
                    f"Mouth and face follow <Audio 1>. "
                    f"<Subject 1> (S1) sings, {d}.{_hold_cue(has_hold)}"
                )
        n += 1
    return _assemble(args, clip["audio"], True, first, summary, shots)


def lyrics_blobs(text: str) -> list[str]:
    return re.findall(r"lyrics:.*?(?=\nprompt:)", text, flags=re.S)


def to_unified(text: str) -> str:
    header = {}
    for line in text.splitlines():
        m = re.match(
            r"^(h3_music_video|max_duration_seconds|duration_seconds|clip_count)\s*:\s*(.+?)\s*$",
            line.strip(), re.I,
        )
        if m:
            header[m.group(1).lower()] = m.group(2).strip()
    duration = header.get("max_duration_seconds") or header.get("duration_seconds") or "10.125"
    parts = re.split(r"\n---\s*\n", text, maxsplit=1)
    body = parts[1] if len(parts) > 1 else text
    starts = [i for i, line in enumerate(body.splitlines()) if re.match(r"^CLIP\s+\d+\s*$", line.strip(), re.I)]
    lines = body.splitlines()
    clips = []
    for j, start in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        block = lines[start:end]
        head = re.match(r"^CLIP\s+(\d+)\s*$", block[0].strip(), re.I)
        clip = {"index": int(head.group(1)) if head else j + 1, "fields": [], "prompt": []}
        mode = None
        for row in block[1:]:
            stripped = row.strip()
            if stripped == "---":
                continue
            if mode != "prompt" and re.match(r"^(time|duration_seconds|slice|audio)\s*:", stripped, re.I):
                clip["fields"].append(stripped)
                continue
            if mode != "prompt" and re.match(r"^lyrics\s*:", stripped, re.I):
                mode = "lyrics"
                clip["lyrics"] = [row]
                continue
            if re.match(r"^prompt\s*:", stripped, re.I):
                mode = "prompt"
                rest = stripped.split(":", 1)[1].strip()
                if rest:
                    clip["prompt"].append(rest)
                continue
            if mode == "lyrics":
                clip.setdefault("lyrics", []).append(row)
            elif mode == "prompt":
                clip["prompt"].append(row.rstrip())
        clips.append(clip)
    out = [
        "H3 Studio prompt",
        "mode: music_video",
        f"duration: {float(duration):.3f}",
        f"segments: {len(clips)}",
        "",
    ]
    for i, clip in enumerate(clips, 1):
        role = "Start" if i == 1 else "Continue"
        out.append(f"## Clip {clip['index']} — {role}")
        out.extend(clip.get("fields") or [])
        lyrics = "\n".join(clip.get("lyrics") or []).strip()
        if lyrics:
            out.append(lyrics if lyrics.lower().startswith("lyrics:") else f"lyrics:\n{lyrics}")
        prompt = "\n".join(clip.get("prompt") or []).strip()
        out.append(prompt)
        out.append("")
    return "\n".join(out).strip() + "\n"


def fill(raw: str, args) -> str:
    clips = parse_clips(raw)
    actions = load_plan_lines(
        getattr(args, "actions", "") or "",
        getattr(args, "action", "") or "",
        len(clips),
    )
    for i, action in enumerate(actions):
        _assert_exact_action(action, f"CLIP {i + 1} action")
    bodies = []
    for clip in clips:
        if _has_sung_lines(clip):
            bodies.append(sung_body(clip, args, "", "", ""))
        else:
            bodies.append(instrumental_body(clip, args, "", "", ""))
    out = []
    i = 0
    for line in raw.splitlines(keepends=True):
        out.append(line)
        if line.strip() == "prompt:":
            if i >= len(bodies):
                raise SystemExit("more prompt: lines than CLIP blocks")
            out.append(bodies[i] + "\n")
            i += 1
    if i != len(bodies):
        raise SystemExit(f"prompt inserts={i} clips={len(bodies)}")
    text = "".join(out)
    if lyrics_blobs(raw) != lyrics_blobs(text):
        raise SystemExit("lyrics: changed during fill")
    return to_unified(text)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fill H3 Music Video prompt: bodies on a CLIP skeleton.")
    p.add_argument("skeleton", help="UTF-8 skeleton from transcribe_song_lrc.py / lyric_timing.py")
    p.add_argument("-o", "--out", required=True, help="Output .h3.txt path")
    p.add_argument("--subject", required=True, help="Subject 1 identity (no leading <Subject 1> is)")
    for i in range(1, 10):
        p.add_argument(
            f"--picture{i}",
            default="",
            help=(
                "Appearance extras cited inside <Subject 1> as <Picture N>; omit if unused"
                if i == 1 else argparse.SUPPRESS
            ),
        )
    p.add_argument("--worlds", default="", help=argparse.SUPPRESS)
    p.add_argument("--world", default="", help=argparse.SUPPRESS)
    p.add_argument("--actions", default="", help=argparse.SUPPRESS)
    p.add_argument("--action", default="", help=argparse.SUPPRESS)
    p.add_argument("--first-frame", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--audio-only", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--pronoun", default="she", help=argparse.SUPPRESS)
    p.add_argument("--opening", default="", help="Visible opening crop/wardrobe for CLIP 1 Shot 1")
    p.add_argument("--language", default="English")
    p.add_argument(
        "--style",
        default="live-action, cinematic, high-budget music-video",
        help="Style clause after 'The target video is '",
    )
    p.add_argument(
        "--portrait",
        default="none",
        choices=["exclusive", "occasional", "none"],
        help="Only if this song asked: exclusive close-ups, mixed close-up/scene, or scene-only",
    )
    p.add_argument("--fx", default="", help="Optional visual treatment; omit unless this song asked")
    p.add_argument(
        "--cuts",
        action="store_true",
        help="Ignored by filler. After fill, the LLM treats this as a frequent-cut brief.",
    )
    args = p.parse_args(argv)
    raw = Path(args.skeleton).read_text(encoding="utf-8")
    text = fill(raw, args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(out)
    print(f"clip_count={len(re.findall(r'^## Clip ', text, flags=re.M))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Unified H3 Studio prompt document. No ComfyUI imports."""

from __future__ import annotations

import re

SECTION_HEADS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)

_HEADER = re.compile(
    r"^(mode|duration|segments|loop|max_duration_seconds|clip_count|h3_music_video)\s*:\s*(.+?)\s*$",
    re.I,
)
_CLIP_MD = re.compile(
    r"^##\s+(?:Clip\s+(\d+)\s*[—\-–]+\s*(.+)|Loop\b.*)$",
    re.I,
)
_CLIP_BOLD = re.compile(
    r"^\*\*(?:Clip\s+(\d+)\s*[—\-–]+\s*([^*]+)|Loop\b[^*]*)\*\*\s*$",
    re.I,
)
_MENTION = re.compile(r"@(Picture|Video|Audio|Model)\s*(\d+)\b", re.I)
_FIRST_FRAME_LINE = re.compile(
    r"<Picture\s+\d+>\s+is the first frame of \[Shot 1\]",
    re.I,
)
_AUDIO1_LINE = re.compile(r"<Audio\s+1>\s+is\b", re.I)
_TIME = re.compile(r"^time\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)\s*$", re.I)
_DURATION = re.compile(r"^duration(?:_seconds)?\s*:\s*([0-9.]+)\s*$", re.I)
_SLICE = re.compile(r"^slice\s*:\s*([0-9.]+)\s*$", re.I)
_AUDIO_SPAN = re.compile(r"^audio\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)\s*$", re.I)
_LYRICS = re.compile(r"^lyrics\s*:\s*(.*)$", re.I)
_SECTION_START = re.compile(
    rf"^({'|'.join(SECTION_HEADS)})\s*:",
    re.I | re.M,
)
_KIND = re.compile(r"<(Picture|Video|Audio|Model|Subject)\s+(\d+)>", re.I)


def rewrite_mentions(text: str) -> str:
    def repl(match):
        kind = match.group(1)[:1].upper() + match.group(1)[1:].lower()
        return f"<{kind} {int(match.group(2))}>"
    return _MENTION.sub(repl, str(text or ""))


def looks_like_legacy_music_video(text: str) -> bool:
    return bool(re.search(r"^h3_music_video\s*:", str(text or ""), re.I | re.M))


def looks_like_unified(text: str) -> bool:
    raw = str(text or "")
    if looks_like_legacy_music_video(raw):
        return False
    if re.search(r"^H3 Studio prompt\s*$", raw, re.I | re.M):
        return True
    if re.search(r"^##\s+(Clip\s+\d+|Loop\b)", raw, re.I | re.M):
        return True
    if re.search(r"^\*\*Clip\s+\d+", raw, re.I | re.M):
        return True
    return False


def split_sections(body: str) -> dict:
    text = rewrite_mentions(body)
    found = {head: "" for head in SECTION_HEADS}
    matches = list(_SECTION_START.finditer(text))
    for i, match in enumerate(matches):
        name = match.group(1).lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        found[name] = text[start:end].strip()
    return found


def cited_labels(text: str) -> set[tuple[str, int]]:
    found = set()
    for kind, raw in _KIND.findall(rewrite_mentions(text)):
        key = kind[:1].upper() + kind[1:].lower()
        found.add((key, int(raw)))
    return found


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _clip_starts(lines: list[str]) -> list[tuple[int, int | None, str, bool]]:
    starts = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        md = _CLIP_MD.match(stripped)
        if md:
            if md.group(1) is None:
                starts.append((i, None, "Loop", True))
            else:
                starts.append((i, int(md.group(1)), md.group(2).strip(), False))
            continue
        bold = _CLIP_BOLD.match(stripped)
        if bold:
            if bold.group(1) is None:
                starts.append((i, None, "Loop", True))
            else:
                starts.append((i, int(bold.group(1)), bold.group(2).strip(), False))
    return starts


def _parse_clip_block(index, role, is_loop, block: str) -> dict:
    lines = str(block or "").replace("\r\n", "\n").split("\n")
    time_range = None
    duration_seconds = None
    slice_start = None
    audio_range = None
    lyrics_parts = []
    body_lines = []
    mode = None
    for line in lines:
        stripped = line.strip()
        if mode == "lyrics":
            if (
                _SECTION_START.match(stripped) or _TIME.match(stripped)
                or _DURATION.match(stripped) or _SLICE.match(stripped)
                or _AUDIO_SPAN.match(stripped)
            ):
                mode = None
            else:
                lyrics_parts.append(line.rstrip())
                continue
        if mode is None:
            tm = _TIME.match(stripped)
            if tm:
                time_range = (float(tm.group(1)), float(tm.group(2)))
                continue
            dm = _DURATION.match(stripped)
            if dm:
                duration_seconds = float(dm.group(1))
                continue
            sm = _SLICE.match(stripped)
            if sm:
                slice_start = float(sm.group(1))
                continue
            am = _AUDIO_SPAN.match(stripped)
            if am:
                audio_range = (float(am.group(1)), float(am.group(2)))
                continue
            lm = _LYRICS.match(stripped)
            if lm:
                mode = "lyrics"
                rest = lm.group(1)
                if rest.strip():
                    lyrics_parts.append(rest.rstrip())
                continue
        body_lines.append(line.rstrip())
    sections = split_sections("\n".join(body_lines))
    return {
        "index": int(index or 0),
        "role": str(role or "").strip() or "Continue",
        "is_loop": bool(is_loop),
        "time": time_range,
        "duration_seconds": duration_seconds,
        "slice": slice_start,
        "audio": audio_range,
        "lyrics": "\n".join(lyrics_parts).strip(),
        "sections": sections,
        "local_subjects": sections.get("subject_definitions") or "",
    }


def parse_prompt_document(text: str, mode: str | None = None) -> dict:
    raw = rewrite_mentions(str(text or "")).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError("h3_studio: prompt document is empty")
    lines = raw.split("\n")
    header = {}
    preamble = []
    i = 0
    if lines and re.match(r"^H3 Studio prompt\s*$", lines[0], re.I):
        i = 1
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        match = _HEADER.match(stripped)
        if not match:
            break
        header[match.group(1).lower()] = match.group(2).strip()
        i += 1
    rest = lines[i:]
    starts = _clip_starts(rest)
    if not starts:
        raise ValueError("h3_studio: prompt has no ## Clip / Loop sections")
    preamble = rest[:starts[0][0]]
    shared = split_sections("\n".join(preamble)).get("subject_definitions") or ""
    clips = []
    story_n = 0
    for j, (start, index, role, is_loop) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(rest)
        block = "\n".join(rest[start + 1:end])
        if not is_loop:
            story_n += 1
            index = int(index or story_n)
        else:
            index = int(index or story_n)
        clips.append(_parse_clip_block(index, role, is_loop, block))
    inferred = str(header.get("mode") or mode or "").strip().lower()
    if inferred not in ("auto_chain", "music_video"):
        inferred = "music_video" if any(c.get("time") or c.get("lyrics") for c in clips) else "auto_chain"
    duration = header.get("duration") or header.get("max_duration_seconds")
    segments = header.get("segments") or header.get("clip_count")
    return {
        "kind": "unified",
        "mode": inferred,
        "duration": float(duration) if duration else None,
        "segments": int(float(segments)) if segments else None,
        "loop": _truthy(header.get("loop")),
        "shared_subjects": shared,
        "clips": clips,
        "raw": raw,
    }


def story_clips(parsed: dict) -> list[dict]:
    return [clip for clip in parsed.get("clips") or [] if not clip.get("is_loop")]


def _filter_subject_lines(block: str, clip_index: int, is_loop: bool,
                          song_audio=False, time_range=None, duration=None) -> str:
    kept = []
    for line in str(block or "").splitlines():
        if _FIRST_FRAME_LINE.search(line) and (int(clip_index) != 1 or is_loop):
            continue
        if song_audio and _AUDIO1_LINE.search(line) and time_range:
            line = re.sub(
                r"covering\s+[0-9.]+(?:\s*[–-]\s*)[0-9.]+",
                f"covering {time_range[0]:.3f}–{time_range[1]:.3f}",
                line,
            )
        kept.append(line.rstrip())
    text = "\n".join(line for line in kept if line.strip() or line == "").strip()
    if song_audio and not _AUDIO1_LINE.search(text):
        t0 = float(time_range[0]) if time_range else 0.0
        t1 = float(time_range[1]) if time_range else float(duration or 0.0)
        extra = (
            f"<Audio 1> is the source-song slice covering {t0:.3f}–{t1:.3f} of the master, "
            "reused as the complete soundtrack."
        )
        text = f"{text}\n{extra}".strip() if text else extra
    return text


def _merge_subjects(shared: str, local: str) -> str:
    shared = str(shared or "").strip()
    local = str(local or "").strip()
    if not shared:
        return local
    if not local:
        return shared
    shared_set = {line.strip() for line in shared.splitlines() if line.strip()}
    extra = [line for line in local.splitlines() if line.strip() and line.strip() not in shared_set]
    if not extra:
        return shared
    return shared + "\n" + "\n".join(extra)


def _audio_window(clip: dict, parsed: dict):
    if clip.get("audio"):
        return clip["audio"]
    if clip.get("slice") is not None:
        t0 = float(clip["slice"])
        dur = float(clip.get("duration_seconds") or parsed.get("duration") or 0.0)
        return (t0, t0 + dur)
    return clip.get("time")


def expand_clip(parsed: dict, clip_index: int, song_audio=False, is_loop=False) -> str:
    clips = parsed.get("clips") or []
    if is_loop:
        clip = next((item for item in clips if item.get("is_loop")), None)
    else:
        clip = next(
            (item for item in clips if not item.get("is_loop") and int(item["index"]) == int(clip_index)),
            None,
        )
    if clip is None:
        raise ValueError(f"h3_studio: prompt has no clip {clip_index}")
    subjects = _filter_subject_lines(
        _merge_subjects(parsed.get("shared_subjects") or "", clip.get("local_subjects") or ""),
        clip_index=clip["index"],
        is_loop=bool(clip.get("is_loop")),
        song_audio=song_audio,
        time_range=_audio_window(clip, parsed),
        duration=clip.get("duration_seconds") or parsed.get("duration"),
    )
    sections = clip.get("sections") or {}
    parts = [f"subject_definitions:\n{subjects}".rstrip()]
    for head in SECTION_HEADS[1:]:
        parts.append(f"{head}:\n{sections.get(head) or ''}".rstrip())
    return rewrite_mentions("\n\n".join(parts).strip() + "\n")


def resolve_auto_chain_prompts(prompt, segments, loop=False, loop_prompt="", kwargs=None):
    """Return (story_bodies, loop_text) from a unified document or legacy prompt_N widgets."""
    doc = str(prompt or "").strip()
    loop_text = str(loop_prompt or "").strip()
    if looks_like_unified(doc):
        parsed = parse_prompt_document(doc, mode="auto_chain")
        story = story_clips(parsed)
        if len(story) != int(segments):
            raise ValueError(
                f"h3_continuous: prompt has {len(story)} story clip(s) but segments={int(segments)}"
            )
        bodies = [expand_clip(parsed, item["index"]) for item in story]
        if loop:
            try:
                loop_text = expand_clip(parsed, int(segments), is_loop=True)
            except ValueError:
                if not loop_text:
                    raise ValueError(
                        "h3_continuous: seamless_loop needs a ## Loop section or loop_prompt"
                    )
        return bodies, loop_text
    bodies = [
        str((kwargs or {}).get(f"prompt_{i}") or "")
        for i in range(1, int(segments) + 1)
    ]
    if doc and not any(body.strip() for body in bodies):
        if int(segments) != 1:
            raise ValueError(
                "h3_studio: paste an H3 Studio prompt with ## Clip sections, "
                "or use one clip with a single six-section body"
            )
        bodies = [doc]
    return bodies, loop_text


def _header_timing(text) -> tuple[float | None, int | None]:
    duration = None
    segments = None
    for line in str(text or "").splitlines():
        match = _HEADER.match(line.strip())
        if not match:
            continue
        key = match.group(1).lower()
        raw = match.group(2).strip()
        if key in ("duration", "max_duration_seconds", "duration_seconds") and duration is None:
            try:
                duration = float(raw.rstrip("sS"))
            except ValueError:
                pass
        elif key in ("segments", "clip_count") and segments is None:
            try:
                segments = int(float(raw))
            except ValueError:
                pass
    return duration, segments


def document_has_loop(text) -> bool:
    raw = str(text or "")
    if not looks_like_unified(raw):
        return False
    try:
        parsed = parse_prompt_document(raw, mode="auto_chain")
    except ValueError:
        return False
    if parsed.get("loop"):
        return True
    return any(clip.get("is_loop") for clip in parsed.get("clips") or [])


def duration_and_segments_from_pack_or_prompt(pack, prompt, *, need_segments=False):
    """Read clip length (and Auto Chain clip count) from the prompt, else the Builder pack."""
    text = str(prompt or "").strip()
    duration, segments = _header_timing(text)
    if need_segments and looks_like_unified(text):
        try:
            story = story_clips(parse_prompt_document(text, mode="auto_chain"))
            if story:
                segments = len(story)
        except ValueError:
            pass
    if duration is None and isinstance(pack, dict) and pack.get("duration") is not None:
        duration = float(pack["duration"])
    if need_segments and segments is None and isinstance(pack, dict) and pack.get("segments") is not None:
        segments = int(pack["segments"])
    if duration is None:
        raise ValueError("h3_studio: duration is missing; set it on the Builder or in the prompt header")
    if need_segments and (segments is None or int(segments) < 1):
        raise ValueError("h3_studio: segments is missing; set it on the Builder or in the prompt")
    if need_segments:
        return float(duration), int(segments)
    return float(duration), None


def assemble_music_video_document(max_duration, clips) -> str:
    """clips: dicts with index, time, duration_seconds, slice, audio, lyrics, prompt."""
    items = list(clips or [])
    first_body = str(items[0].get("prompt") or "") if items else ""
    shared = split_sections(first_body).get("subject_definitions") or ""
    duration = float(max_duration)
    lines = [
        "H3 Studio prompt",
        "mode: music_video",
        f"duration: {duration:.3f}",
        f"segments: {len(items)}",
        "",
        "subject_definitions:",
        shared,
        "",
    ]
    for i, clip in enumerate(items, 1):
        role = "Start" if i == 1 else "Continue"
        lines.append(f"## Clip {int(clip.get('index') or i)} — {role}")
        time_range = clip.get("time")
        if time_range:
            lines.append(f"time: {float(time_range[0]):.3f}-{float(time_range[1]):.3f}")
        if clip.get("duration_seconds") is not None:
            lines.append(f"duration_seconds: {float(clip['duration_seconds']):.3f}")
        if clip.get("slice") is not None:
            lines.append(f"slice: {float(clip['slice']):.3f}")
        audio = clip.get("audio")
        if audio:
            lines.append(f"audio: {float(audio[0]):.3f}-{float(audio[1]):.3f}")
        lyrics = str(clip.get("lyrics") or "").strip()
        lines.append("lyrics:")
        lines.append(lyrics or "(instrumental)")
        sections = split_sections(str(clip.get("prompt") or ""))
        for head in SECTION_HEADS[1:]:
            lines.append(f"{head}:")
            lines.append(sections.get(head) or "")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def assemble_auto_chain_document(duration, segments, loop, bodies) -> str:
    """bodies: iterable of (role, six-section body, is_loop)."""
    items = list(bodies)
    first = next((item for item in items if not item[2]), None)
    shared = split_sections(first[1] if first else "").get("subject_definitions") or ""
    lines = [
        "H3 Studio prompt",
        "mode: auto_chain",
        f"duration: {float(duration):.2f}",
        f"segments: {int(segments)}",
        f"loop: {'true' if loop else 'false'}",
        "",
        "subject_definitions:",
        shared,
        "",
    ]
    story_i = 0
    for role, body, is_loop_flag in items:
        sections = split_sections(body)
        if is_loop_flag:
            lines.append("## Loop — return to Clip 1")
        else:
            story_i += 1
            label = str(role or "Continue").replace(" (final)", "")
            lines.append(f"## Clip {story_i} — {label}")
        for head in SECTION_HEADS[1:]:
            lines.append(f"{head}:")
            lines.append(sections.get(head) or "")
            lines.append("")
    return "\n".join(lines).strip() + "\n"

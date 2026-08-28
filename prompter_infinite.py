"""H3 Studio Local Prompter: Builder pack → labeled Ref2VA clips."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time

from .chain_inputs import MAX_SEGMENTS
from .lyric_align import refine_confirm_lyrics
from .lyric_timing import (
    assign_lyrics_to_windows, format_window_lyrics, is_instrumental_marker,
    parse_timestamped_lyrics, sung_prompt_text,
)
from .node_help import NODE_HELP
from .pack import format_builder_dump, parse_prompt_citations, require_pack
from .prompt_document import (
    assemble_auto_chain_document, assemble_music_video_document, clip_body,
    duration_and_segments_from_pack_or_prompt, parse_prompt_document, story_clips,
)
from .prompter_llama import (
    CATALOG_LABEL, LOCAL_GGUF_LABEL, find_llama_cli, find_llama_server,
    llama_cli_complete, LlamaServerSession, model_combo_values, resolve_gguf,
    unload_comfy_models,
)
from .song_math import FPS

SECTION_HEADS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
_ITEM_LINE = re.compile(
    r"^(Model|Picture|Video|Audio)\s+(\d+)\s*:\s*(.*)$", re.I | re.M,
)
_DURATION = re.compile(r"^duration:\s*([\d.]+)\s*s?\s*$", re.I | re.M)
_SEGMENTS = re.compile(r"^segments:\s*(\d+)\s*$", re.I | re.M)
_LOOP = re.compile(r"^loop:\s*(.+)$", re.I | re.M)
_CLIP_LABEL = re.compile(r"^\*\*[^*]+\*\*\s*", re.M)
_T2VA_LOCK = re.compile(
    r"at\s+0\.00\s+seconds.{0,80}fully\s+referenced", re.I | re.S,
)
_FIRST_FRAME_ROW = re.compile(
    r"<Picture\s+(\d+)>\s+is the first frame of \[Shot 1\]", re.I,
)
_SYSTEM_PATH = os.path.join(os.path.dirname(__file__), "prompts", "infinite_system.txt")
_MV_SYSTEM_PATH = os.path.join(os.path.dirname(__file__), "prompts", "music_video_system.txt")


def load_system_prompt(path=None) -> str:
    with open(path or _SYSTEM_PATH, encoding="utf-8") as handle:
        return handle.read().strip()


def parse_builder_dump(text: str) -> dict:
    raw = str(text or "")
    plan = ""
    plan_match = re.search(r"^plan:\s*$", raw, re.I | re.M)
    inventory_text = raw
    if plan_match:
        inventory_text = raw[:plan_match.start()].rstrip()
        plan = raw[plan_match.end():].strip()
    else:
        same = re.search(r"^plan:\s+(.+)$", raw, re.I | re.M)
        if same:
            inventory_text = (raw[:same.start()] + raw[same.end():]).rstrip()
            plan = same.group(1).strip()
    items = {"models": [], "pictures": [], "videos": [], "audios": []}
    first_frame = None
    for kind, raw_n, desc in _ITEM_LINE.findall(inventory_text):
        n = int(raw_n)
        key = kind.lower() + "s"
        marked = desc.rstrip().endswith("(first frame)")
        entry = {"index": n, "description": desc.strip(), "first_frame": marked}
        if marked and kind.lower() == "picture":
            first_frame = n
            entry["description"] = re.sub(r"\s*\(first frame\)\s*$", "", desc.strip())
        items[key].append(entry)
    dur_match = _DURATION.search(inventory_text)
    seg_match = _SEGMENTS.search(inventory_text)
    loop_match = _LOOP.search(inventory_text)
    loop_raw = loop_match.group(1).strip().lower() if loop_match else ""
    return {
        "models": items["models"],
        "pictures": items["pictures"],
        "videos": items["videos"],
        "audios": items["audios"],
        "first_frame": first_frame,
        "duration": float(dur_match.group(1)) if dur_match else None,
        "segments": int(seg_match.group(1)) if seg_match else None,
        "loop": loop_raw in ("1", "true", "yes", "on"),
        "plan": plan,
        "raw": raw.strip(),
    }


def dump_indices(inventory: dict, song_audio=False) -> dict:
    audios = [int(item["index"]) for item in inventory.get("audios") or []]
    if song_audio and 1 not in audios:
        audios = [1] + audios
    return {
        "pictures": [int(item["index"]) for item in inventory.get("pictures") or []],
        "videos": [int(item["index"]) for item in inventory.get("videos") or []],
        "audios": audios,
        "models": [int(item["index"]) for item in inventory.get("models") or []],
    }


def clip_role(index: int, segments: int, loop=False, is_loop=False) -> str:
    if is_loop:
        return "Loop"
    if index == 1:
        return "Start" if int(segments) > 1 or loop else "Start (final)"
    if index == int(segments):
        return "Finish"
    return "Continue"


def clip_heading(index: int, role: str) -> str:
    if role == "Loop":
        return "**Loop — return to Clip 1**"
    if role == "Start (final)":
        return "**Clip 1 — Start (final)**"
    return f"**Clip {int(index)} — {role}**"


def strip_generated_body(text: str) -> str:
    body = str(text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:text|markdown)?\s*", "", body)
        body = re.sub(r"\s*```\s*$", "", body)
    body = _CLIP_LABEL.sub("", body).strip()
    return body.strip()


def validate_clip_prompt(body: str, inventory: dict, clip_index: int, is_loop=False,
                         song_audio=False, required_d=None) -> list[str]:
    text = str(body or "")
    issues = []
    for head in SECTION_HEADS:
        if not re.search(rf"^{re.escape(head)}\s*:", text, re.I | re.M):
            issues.append(f"missing section {head}")
    cites = parse_prompt_citations(text)
    allowed = dump_indices(inventory, song_audio=song_audio)
    for kind, used in cites.items():
        if kind in ("video_picks", "audio_picks"):
            continue
        legal = set(allowed.get(kind) or [])
        extra = [n for n in used if n not in legal]
        if extra:
            issues.append(f"unknown {kind} tags {extra}; dump has {sorted(legal)}")
    dump_pics = allowed.get("pictures") or []
    if dump_pics and not (cites.get("pictures") or []):
        issues.append(
            "cite dump <Picture N> for identity in this clip; Continue omits only the first-frame Picture row"
        )
    first_n = inventory.get("first_frame")
    first_row = _FIRST_FRAME_ROW.search(text)
    if first_n and int(clip_index) == 1 and not is_loop:
        if not first_row:
            issues.append(
                f"clip 1 must include '<Picture {first_n}> is the first frame of [Shot 1]'"
            )
        elif int(first_row.group(1)) != int(first_n):
            issues.append(f"first-frame row must cite dump Picture {first_n}")
    elif first_row:
        if int(clip_index) == 1 and not is_loop:
            issues.append("no dump picture is marked first frame")
        else:
            issues.append("Continue/Finish/Loop must not reopen the first-frame still")
    if _T2VA_LOCK.search(text):
        issues.append("do not write the T2VA lock sentence 'at 0.00 seconds … fully referenced'")
    for tag in required_d or []:
        if tag and tag not in text:
            issues.append(f"missing locked {tag}")
    return issues


def _progress(unique_id, text):
    from .png_sequence import send_node_progress
    send_node_progress(unique_id, text)


def _run_with_status(progress, label, fn, interval=2.0):
    if progress is None:
        return fn()
    stop = threading.Event()
    started = time.monotonic()
    progress(label)

    def beat():
        while not stop.wait(interval):
            progress(f"{label} — {int(time.monotonic() - started)}s")

    thread = threading.Thread(target=beat, name="h3-studio-prompter-status", daemon=True)
    thread.start()
    try:
        return fn()
    finally:
        stop.set()
        thread.join(timeout=1)


def _progress_bar(total, unique_id):
    try:
        import comfy.utils
    except ImportError:
        return None
    return comfy.utils.ProgressBar(max(1, int(total)), node_id=unique_id)


def dump_from_pack(pack) -> str:
    if not isinstance(pack, dict):
        raise ValueError("h3_studio: connect H3 Studio Builder to pack")
    return format_builder_dump(
        pack.get("models") or [],
        pack.get("pictures") or [],
        pack.get("videos") or [],
        pack.get("audios") or [],
        plan=pack.get("plan") or "",
        duration=pack.get("duration"),
        segments=pack.get("segments"),
        loop=bool(pack.get("loop")),
    )


def pack_song_sig(pack) -> str:
    song = pack.get("song") if isinstance(pack, dict) else None
    if not isinstance(song, dict) or song.get("waveform") is None:
        return ""
    wav = song["waveform"]
    sr = int(song.get("sample_rate") or 0)
    shape = tuple(int(n) for n in getattr(wav, "shape", ()))
    return f"{sr}:{shape}"


def song_seconds_from_audio(song) -> float:
    if not isinstance(song, dict) or song.get("waveform") is None:
        raise ValueError("h3_studio: pack song is missing AUDIO")
    wav = song["waveform"]
    sr = int(song.get("sample_rate") or 0)
    if sr <= 0:
        raise ValueError("h3_studio: pack song is missing sample_rate")
    return float(wav.shape[-1]) / float(sr)


def music_video_pack_inputs(pack):
    """Return (song, lyrics) for Music Video, or None for Auto Chain."""
    if not isinstance(pack, dict):
        return None
    song = pack.get("song")
    lyrics = str(pack.get("lyrics") or "").strip()
    has_song = isinstance(song, dict) and song.get("waveform") is not None
    if not has_song and not lyrics:
        return None
    if not has_song:
        raise ValueError("h3_studio: lyrics need a song on the Builder pack")
    if not lyrics:
        raise ValueError("h3_studio: song pack is missing lyrics")
    if not parse_timestamped_lyrics(lyrics):
        raise ValueError("h3_studio: time lyrics on Load Song before the Local Prompter")
    return song, lyrics


def locked_d_tags(lyrics_blob, language="English") -> list[str]:
    tags = []
    for line in parse_timestamped_lyrics(lyrics_blob):
        text = str(line.get("text") or "").strip()
        if not text or is_instrumental_marker(text):
            continue
        sung, _hold = sung_prompt_text(text, line.get("start"), line.get("end"))
        if sung:
            tags.append(f"<d>[{language}] {sung}</d>")
    return tags


def window_clip_fields(window: dict) -> dict:
    slice_s = int(window["slice_start"]) / float(FPS) if "slice_start" in window else float(window["start"])
    duration = float(window["duration_seconds"])
    lyrics = format_window_lyrics(window)
    return {
        "index": int(window["index"]),
        "time": (float(window["start"]), float(window["end"])),
        "duration_seconds": duration,
        "slice": slice_s,
        "audio": (slice_s, slice_s + duration),
        "lyrics": lyrics,
        "instrumental": bool(window.get("instrumental")),
    }


def _rewrite_addendum(existing_body="", following_body="") -> list[str]:
    parts = []
    if existing_body:
        parts.extend([
            "",
            "Existing clip body to revise:",
            str(existing_body).rstrip(),
            "Apply the user plan as filmable beats (crop, body, dressed set, light), not a paraphrase. "
            "Do not rewrite lyrics wording, time:, audio:, or locked dialogue tags.",
        ])
    if following_body:
        parts.extend([
            "",
            "Following clip (do not rewrite; land so this body can continue):",
            str(following_body).rstrip(),
        ])
    return parts


def parsed_clip_job(clip) -> dict:
    item = dict(clip)
    lyrics = str(clip.get("lyrics") or "").strip()
    item["prompt"] = clip_body(clip)
    item["instrumental"] = (
        not lyrics or lyrics == "(instrumental)" or is_instrumental_marker(lyrics)
    )
    if item.get("duration_seconds") is None and item.get("time"):
        t0, t1 = item["time"]
        item["duration_seconds"] = float(t1) - float(t0)
    if item.get("audio") is None and item.get("slice") is not None and item.get("duration_seconds") is not None:
        t0 = float(item["slice"])
        item["audio"] = (t0, t0 + float(item["duration_seconds"]))
    if item.get("audio") is None and item.get("time"):
        item["audio"] = item["time"]
    return item


def load_clip_fix_seed(pack) -> dict:
    seed = str(pack.get("seed_prompt") or "").strip()
    if not seed:
        raise ValueError("h3_studio: clip_fix pack is missing seed_prompt")
    parsed = parse_prompt_document(seed)
    targets = [int(n) for n in (pack.get("fix_clips") or [])]
    if not targets:
        raise ValueError("h3_studio: clip_fix pack is missing fix_clips")
    story = story_clips(parsed)
    available = {int(clip["index"]) for clip in story}
    missing = [n for n in targets if n not in available]
    if missing:
        raise ValueError(f"h3_studio: seed_prompt has no clip {missing[0]}")
    song_audio = parsed.get("mode") == "music_video" or any(
        clip.get("time") or clip.get("lyrics") for clip in parsed.get("clips") or []
    )
    items = [parsed_clip_job(clip) for clip in parsed.get("clips") or []]
    if song_audio:
        for clip in items:
            if clip.get("is_loop"):
                continue
            if not clip.get("time") or not clip.get("audio") or clip.get("duration_seconds") is None:
                raise ValueError(
                    f"h3_studio: clip {int(clip['index'])} is missing time/audio headers"
                )
    return {
        "parsed": parsed,
        "rewrite": targets,
        "song_audio": song_audio,
        "items": items,
    }


def _mv_user_turn(inventory, plan, clip, previous_body, existing_body="",
                  following_body="") -> str:
    index = int(clip["index"])
    role = "Start" if index == 1 else "Continue"
    t0, t1 = clip["time"]
    a0, a1 = clip["audio"]
    lyrics = str(clip.get("lyrics") or "").strip() or "(instrumental)"
    tags = [] if clip.get("instrumental") else locked_d_tags(lyrics)
    job = (
        f"Revise the six-section body for clip {index} ({role}), duration {float(clip['duration_seconds']):.2f}s."
        if existing_body else
        f"Write the body for clip {index} ({role}), duration {float(clip['duration_seconds']):.2f}s."
    )
    parts = [
        "Builder dump:",
        inventory["raw"] or "(empty dump)",
        "",
        "User plan:",
        str(plan or "").strip() or "(no extra plan)",
        "",
        job,
        "Choose which dump Picture / Video / Model this clip needs. Identity stills that still apply must appear as <Picture N> in this clip's subject_definitions (inside the Subject line). If the dump has one identity Picture, every clip cites it. Omit unused extra stills.",
        "Expand this clip's picture and blocking. Shot clocks are clip-relative: 0.00 is this generate start (slice). Subtract slice from song lyric stamps for At mm:ss.sss. Place each <d> in a shot covering that line. Do not leave the plan's crop or place words as the whole shot.",
        "",
        "Locked CLIP headers (do not rewrite lyrics wording):",
        f"time: {t0:.3f}-{t1:.3f}",
        f"slice: {float(clip.get('slice', a0)):.3f}",
        f"audio: {a0:.3f}-{a1:.3f}",
        "lyrics:",
        lyrics,
    ]
    if clip.get("instrumental"):
        parts.append("This clip is instrumental. Closed lips. Do not write <d> tags.")
    elif tags:
        parts.append("Required dialogue tags (verbatim):")
        parts.extend(tags)
    first_n = inventory.get("first_frame")
    if first_n and index == 1:
        parts.append(
            f"Dump Picture {first_n} is marked (first frame). Shot 1 must match that still "
            f"and include '<Picture {first_n}> is the first frame of [Shot 1]'."
        )
    elif first_n:
        parts.append(
            f"Keep '<Picture {first_n}>' inside the Subject line so the node loads that still. "
            "Do not add a standalone first-frame Picture row. Continue from the previous "
            "clip's last visible state."
        )
    if previous_body:
        parts.extend(["", "Previous clip body:", previous_body])
    parts.extend(_rewrite_addendum(existing_body, following_body))
    parts.append("Output only the six-section body.")
    return "\n".join(parts)


def _user_turn(inventory, plan, index, role, duration, previous_body, is_loop=False,
               existing_body="", following_body="") -> str:
    if is_loop:
        job = f"Write the body for the Loop clip, duration {float(duration):.2f}s."
    elif existing_body:
        job = f"Revise the six-section body for clip {index} ({role}), duration {float(duration):.2f}s."
    else:
        job = f"Write the body for clip {index} ({role}), duration {float(duration):.2f}s."
    parts = [
        "Builder dump:",
        inventory["raw"] or "(empty dump)",
        "",
        "User plan:",
        str(plan or "").strip() or "(no extra plan)",
        "",
        job,
        "Choose which dump Picture / Video / Audio this clip needs. Identity stills that still apply must appear as <Picture N> in this clip's subject_definitions (inside the Subject line). If the dump has one identity Picture, every clip cites it. Omit unused extra stills.",
        "Expand this clip's share of the plan into filmable beats (crop, body, dressed set, light). Use At mm:ss.sss from this clip's 0.00. Do not repeat plan slang such as every few seconds, reality-bends, or looks around.",
    ]
    if is_loop:
        parts.append(
            "Continue from the last story clip toward clip 1's opening action already in motion."
        )
    first_n = inventory.get("first_frame")
    if first_n and int(index) == 1 and not is_loop:
        parts.append(
            f"Dump Picture {first_n} is marked (first frame). Shot 1 must match that still "
            f"and include '<Picture {first_n}> is the first frame of [Shot 1]'."
        )
    elif first_n:
        parts.append(
            f"Keep '<Picture {first_n}>' inside the Subject line so the node loads that still. "
            "Do not add a standalone first-frame Picture row. Continue from the previous "
            "clip's last visible state."
        )
    if previous_body:
        parts.extend(["", "Previous clip body:", previous_body])
    parts.extend(_rewrite_addendum(existing_body, following_body))
    parts.append("Output only the six-section body.")
    return "\n".join(parts)


def _flatten_cli_messages(messages) -> tuple[str, str]:
    system = ""
    chunks = []
    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role == "system" and not system:
            system = content
        elif role == "user":
            chunks.append(content)
        elif role == "assistant":
            chunks.append("Previous draft:\n" + content)
    return system, "\n\n".join(chunks)


def generate_clip_bodies(inventory, plan, segments, duration, loop, chat_fn,
                         progress=None, seed_clips=None,
                         rewrite_indices=None) -> tuple[list[tuple[str, str, str]], list[str]]:
    system = load_system_prompt()
    rewrite = None if rewrite_indices is None else {int(n) for n in rewrite_indices}
    if seed_clips is not None:
        jobs = []
        for clip in seed_clips:
            if clip.get("is_loop"):
                jobs.append((int(clip.get("index") or 0), "Loop", True, clip))
                continue
            index = int(clip["index"])
            role = str(clip.get("role") or "").strip() or clip_role(
                index, segments, loop=loop,
            )
            jobs.append((index, role, False, clip))
    else:
        jobs = []
        for i in range(1, int(segments) + 1):
            jobs.append((i, clip_role(i, segments, loop=loop), False, None))
        if loop:
            jobs.append((int(segments), "Loop", True, None))
    bodies = []
    notes = []
    previous = ""
    n_jobs = sum(
        1 for index, _role, is_loop, _clip in jobs
        if rewrite is None or (not is_loop and index in rewrite)
    )
    job_i = 0
    for index, role, is_loop, seed in jobs:
        seed_body = clip_body(seed) if seed is not None else ""
        skip = seed is not None and (is_loop or (rewrite is not None and index not in rewrite))
        if skip:
            heading = clip_heading(index, role)
            bodies.append((heading, seed_body, role))
            if not is_loop:
                previous = seed_body
            continue
        following = ""
        if rewrite is not None and seed_clips is not None and not is_loop:
            later = next(
                (item for item in seed_clips
                 if not item.get("is_loop") and int(item["index"]) == index + 1),
                None,
            )
            if later is not None and int(later["index"]) not in rewrite:
                following = clip_body(later)
        job_i += 1
        clip_duration = duration
        if seed is not None and seed.get("duration_seconds") is not None:
            clip_duration = float(seed["duration_seconds"])
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_turn(
                inventory, plan, index, role, clip_duration, previous, is_loop=is_loop,
                existing_body=seed_body if rewrite is not None else "",
                following_body=following,
            )},
        ]
        label = f"Clip {job_i}/{n_jobs} ({role}) — writing"
        raw = _run_with_status(progress, label, lambda msgs=messages: chat_fn(msgs))
        body = strip_generated_body(raw)
        issues = validate_clip_prompt(body, inventory, index, is_loop=is_loop)
        if issues:
            repair = (
                "Repair the draft. Keep the six-section Ref2VA body. Fix:\n- "
                + "\n- ".join(issues)
            )
            messages.extend([
                {"role": "assistant", "content": body},
                {"role": "user", "content": repair},
            ])
            repair_label = f"Clip {job_i}/{n_jobs} ({role}) — repairing"
            body = strip_generated_body(
                _run_with_status(progress, repair_label, lambda msgs=messages: chat_fn(msgs)),
            )
            leftover = validate_clip_prompt(body, inventory, index, is_loop=is_loop)
            if leftover:
                notes.append(f"clip {index} ({role}): " + "; ".join(leftover))
        heading = clip_heading(index, role)
        bodies.append((heading, body, role))
        if not is_loop:
            previous = body
    return bodies, notes


def generate_music_video_bodies(inventory, plan, clips, chat_fn,
                                progress=None, rewrite_indices=None) -> tuple[list[dict], list[str]]:
    system = load_system_prompt(_MV_SYSTEM_PATH)
    rewrite = None if rewrite_indices is None else {int(n) for n in rewrite_indices}
    bodies = []
    notes = []
    previous = ""
    n_jobs = (
        len(clips) if rewrite is None
        else sum(1 for clip in clips if int(clip["index"]) in rewrite)
    )
    job_i = 0
    for clip in clips:
        index = int(clip["index"])
        role = "Start" if index == 1 else "Continue"
        seed_body = str(clip.get("prompt") or "")
        if rewrite is not None and index not in rewrite:
            item = dict(clip)
            item["prompt"] = seed_body
            bodies.append(item)
            previous = seed_body
            continue
        following = ""
        if rewrite is not None:
            later = next(
                (item for item in clips if int(item["index"]) == index + 1),
                None,
            )
            if later is not None and int(later["index"]) not in rewrite:
                following = str(later.get("prompt") or "")
        job_i += 1
        tags = [] if clip.get("instrumental") else locked_d_tags(clip.get("lyrics") or "")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _mv_user_turn(
                inventory, plan, clip, previous,
                existing_body=seed_body if rewrite is not None else "",
                following_body=following,
            )},
        ]
        label = f"Clip {job_i}/{n_jobs} ({role}) — writing"
        raw = _run_with_status(progress, label, lambda msgs=messages: chat_fn(msgs))
        body = strip_generated_body(raw)
        issues = validate_clip_prompt(
            body, inventory, index, song_audio=True, required_d=tags,
        )
        if issues:
            repair = (
                "Repair the draft. Keep the six-section Ref2VA body. Fix:\n- "
                + "\n- ".join(issues)
            )
            messages.extend([
                {"role": "assistant", "content": body},
                {"role": "user", "content": repair},
            ])
            repair_label = f"Clip {job_i}/{n_jobs} ({role}) — repairing"
            body = strip_generated_body(
                _run_with_status(progress, repair_label, lambda msgs=messages: chat_fn(msgs)),
            )
            leftover = validate_clip_prompt(
                body, inventory, index, song_audio=True, required_d=tags,
            )
            if leftover:
                notes.append(f"clip {index} ({role}): " + "; ".join(leftover))
        item = dict(clip)
        item["prompt"] = body
        bodies.append(item)
        previous = body
    return bodies, notes


def clip_fix_output_clips(clips, rewrite) -> list:
    want = {int(n) for n in rewrite}
    return [
        clip for clip in clips
        if not clip.get("is_loop") and int(clip["index"]) in want
    ]


def clip_fix_output_bodies(seed_clips, bodies, rewrite) -> list:
    want = {int(n) for n in rewrite}
    items = []
    for seed, (_heading, body, role) in zip(seed_clips, bodies):
        if seed.get("is_loop"):
            continue
        index = int(seed["index"])
        if index not in want:
            continue
        items.append((role, body, False, index))
    return items


class H3StudioLocalInfinitePrompter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pack": ("H3_STUDIO_PACK", {
                    "tooltip": (
                        "Wire H3 Studio Builder here. Auto Chain uses inventory, plan, duration, "
                        "clip count, and loop. Music Video uses song plus timed lyrics from the pack."
                    ),
                }),
                "model": (model_combo_values(), {
                    "default": CATALOG_LABEL,
                    "tooltip": (
                        "Qwen3.8-27B-Uncensored Q4_K_M looks under models/LLM. Local GGUF uses "
                        "gguf_path. Scanned files appear as local:relative/path.gguf."
                    ),
                }),
                "allow_download": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "If the catalog GGUF is missing, download it into models/LLM from Hugging Face "
                        "(~16 GB). Off raises instead."
                    ),
                }),
                "n_ctx": ("INT", {
                    "default": 16384, "min": 2048, "max": 131072, "step": 256,
                    "tooltip": "llama.cpp context length.",
                }),
                "n_gpu_layers": ("INT", {
                    "default": 99, "min": 0, "max": 999, "step": 1,
                    "tooltip": "GPU layers for llama-server / llama-cli. 99 offloads the whole 27B Q4.",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.6, "min": 0.0, "max": 2.0, "step": 0.05,
                    "tooltip": "Sampling temperature for each clip completion.",
                }),
            },
            "optional": {
                "gguf_path": ("STRING", {
                    "default": "",
                    "tooltip": "Absolute path or filename under models/LLM. Used when model is Local GGUF.",
                }),
                "llama_server": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Path to llama-server. Empty auto-finds H3_STUDIO_LLAMA_SERVER, PATH, "
                        "llama-cli sibling, or ComfyUI/user/**/llama-server."
                    ),
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("prompts", "clip_count", "notes")
    OUTPUT_TOOLTIPS = (
        "One H3 Studio prompt: Auto Chain, or Music Video when the pack has song plus timed lyrics.",
        "Number of generated prompt bodies (N, or N+1 when Auto Chain loop is on).",
        "Model path, binary used, and leftover validator notes after one repair pass.",
    )
    FUNCTION = "generate_prompts"
    CATEGORY = "H3 Studio"
    DESCRIPTION = NODE_HELP["H3StudioLocalInfinitePrompter"]

    @classmethod
    def IS_CHANGED(cls, pack=None, model=CATALOG_LABEL, allow_download=False, n_ctx=16384,
                   n_gpu_layers=99, temperature=0.6, gguf_path="", llama_server="", **_kwargs):
        pack_dump = dump_from_pack(pack) if isinstance(pack, dict) else ""
        lyrics = str(pack.get("lyrics") or "") if isinstance(pack, dict) else ""
        seed = str(pack.get("seed_prompt") or "") if isinstance(pack, dict) else ""
        mode = str(pack.get("prompt_mode") or "") if isinstance(pack, dict) else ""
        fix = ",".join(
            str(int(n)) for n in (pack.get("fix_clips") or [])
        ) if isinstance(pack, dict) else ""
        raw = "|".join((
            str(model or ""), str(bool(allow_download)),
            str(int(n_ctx)), str(int(n_gpu_layers)), f"{float(temperature):.3f}",
            str(gguf_path or ""), str(llama_server or ""), pack_dump, lyrics,
            pack_song_sig(pack) if isinstance(pack, dict) else "",
            mode, seed, fix,
        ))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate_prompts(self, pack, model, allow_download, n_ctx, n_gpu_layers, temperature,
                         gguf_path="", llama_server="", unique_id=None):
        pack = require_pack(pack)
        dump = dump_from_pack(pack)
        inventory = parse_builder_dump(dump)
        if not inventory["raw"]:
            raise ValueError("h3_studio: connect H3 Studio Builder to pack")
        plan = str(pack.get("plan") or "").strip() or str(inventory.get("plan") or "").strip()
        pbar = None
        fix = load_clip_fix_seed(pack) if str(pack.get("prompt_mode") or "") == "clip_fix" else None
        mv_clips = None
        ac_clips = None
        clips = None
        loop = False

        def progress(text, done=None):
            _progress(unique_id, text)
            if pbar is None:
                return
            if done is not None:
                pbar.update_absolute(int(done))
                return
            match = re.match(r"^Clip (\d+)/(\d+)", str(text or ""))
            if match:
                pbar.update_absolute(1 + int(match.group(1)))

        if fix is not None:
            story_items = [clip for clip in fix["items"] if not clip.get("is_loop")]
            clip_total = sum(1 for clip in story_items if int(clip["index"]) in set(fix["rewrite"]))
            if clip_total < 1:
                raise ValueError("h3_studio: clip_fix has no clips to rewrite")
            duration = fix["parsed"].get("duration")
            if duration is None and pack.get("duration") is not None:
                duration = float(pack["duration"])
            if duration is None:
                for clip in story_items:
                    if clip.get("duration_seconds") is not None:
                        duration = float(clip["duration_seconds"])
                        break
            if duration is None:
                raise ValueError(
                    "h3_studio: duration is missing; set it on the Builder or in the prompt header"
                )
            segments = int(fix["parsed"].get("segments") or len(story_items))
            loop = bool(fix["parsed"].get("loop")) or any(
                clip.get("is_loop") for clip in fix["items"]
            )
            if fix["song_audio"]:
                mv_clips = story_items
            else:
                ac_clips = fix["items"]
        else:
            mv = music_video_pack_inputs(pack)
            if mv is not None:
                song, lyrics = mv
                duration, _unused = duration_and_segments_from_pack_or_prompt(
                    pack, dump, need_segments=False,
                )
                unload_comfy_models()
                progress("Timing confirm lyrics (wav2vec2)")
                song_seconds = song_seconds_from_audio(song)
                refined = refine_confirm_lyrics(
                    song["waveform"], song["sample_rate"], lyrics, song_seconds=song_seconds,
                )
                windows = assign_lyrics_to_windows(refined, song_seconds, duration)
                clips = [window_clip_fields(w) for w in windows]
                clip_total = len(clips)
                loop = False
            else:
                duration, segments = duration_and_segments_from_pack_or_prompt(
                    pack, dump, need_segments=True,
                )
                segments = max(1, min(int(MAX_SEGMENTS), int(segments)))
                loop = bool(pack.get("loop")) or bool(inventory.get("loop"))
                clip_total = segments + (1 if loop else 0)
                clips = None

        pbar = _progress_bar(1 + clip_total, unique_id)
        gguf = resolve_gguf(
            model, gguf_path=gguf_path, allow_download=bool(allow_download), progress=progress,
        )
        session = None
        server_exe = None
        cli_exe = None
        try:
            server_exe = find_llama_server(llama_server)
        except RuntimeError:
            if clip_total > 1:
                raise RuntimeError(
                    "h3_studio: llama-server is required for more than one clip. "
                    "Install llama.cpp so llama-server is on PATH, or set llama_server."
                )
            cli_exe = find_llama_cli()

        def chat(messages):
            if session is not None:
                return session.chat(messages, temperature=temperature)
            system, user = _flatten_cli_messages(messages)
            return llama_cli_complete(
                cli_exe, gguf, system, user, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
                temperature=temperature,
            )

        progress("Unloading Comfy models", done=0)
        unload_comfy_models()
        try:
            if server_exe:
                progress(f"Loading GGUF into llama-server ({os.path.basename(gguf)})")
                session = LlamaServerSession(
                    server_exe, gguf, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
                )
                session.start(progress=progress)
                progress("llama-server ready", done=1)
            else:
                progress(f"llama-cli one-shot for clip 1 ({os.path.basename(gguf)})")
            if mv_clips is not None:
                filled, issues = generate_music_video_bodies(
                    inventory, plan, mv_clips, chat, progress=progress,
                    rewrite_indices=fix["rewrite"],
                )
            elif ac_clips is not None:
                bodies, issues = generate_clip_bodies(
                    inventory, plan, segments, duration, loop, chat, progress=progress,
                    seed_clips=ac_clips, rewrite_indices=fix["rewrite"],
                )
            elif clips is not None:
                filled, issues = generate_music_video_bodies(
                    inventory, plan, clips, chat, progress=progress,
                )
            else:
                bodies, issues = generate_clip_bodies(
                    inventory, plan, segments, duration, loop, chat, progress=progress,
                )
        finally:
            if session is not None:
                session.close()

        if mv_clips is not None or clips is not None:
            if fix is not None:
                filled = clip_fix_output_clips(filled, fix["rewrite"])
            prompts = assemble_music_video_document(
                duration, filled, header=fix is None,
            )
            n_clips = len(filled)
        else:
            if fix is not None:
                items = clip_fix_output_bodies(ac_clips, bodies, fix["rewrite"])
                prompts = assemble_auto_chain_document(
                    duration, len(items), False, items, header=False,
                )
                n_clips = len(items)
            else:
                prompts = assemble_auto_chain_document(
                    duration, segments, loop,
                    [(role, body, role == "Loop") for _heading, body, role in bodies],
                )
                n_clips = len(bodies)
        used = server_exe or cli_exe
        progress(f"Done — {n_clips} clip(s)", done=1 + n_clips)
        note_lines = [
            f"model={gguf}",
            f"binary={used}",
            f"clips={n_clips}",
        ]
        note_lines.extend(issues)
        return (prompts, n_clips, "\n".join(note_lines))

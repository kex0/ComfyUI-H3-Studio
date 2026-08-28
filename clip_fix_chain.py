"""Selective clip regenerate helpers. No ComfyUI imports."""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime

from .clip_prompt_fixer import parse_clip_index
from .prompt_document import expand_clip, looks_like_unified, parse_prompt_document, story_clips

_SAVED_CLIP = re.compile(r"^(.+)_(\d{5})\.safetensors$")
_CLIP_FILE = re.compile(r"^(.+)_(\d{5})(?:_.*)?\.(safetensors|mp4)$", re.I)


def prompt_story_indices(prompt: str, kwargs=None, per_clip_segments=None) -> list[int]:
    if looks_like_unified(prompt):
        parsed = parse_prompt_document(prompt)
        indices = [int(clip["index"]) for clip in story_clips(parsed)]
        if indices:
            return indices
    if per_clip_segments:
        found = []
        for i in range(1, int(per_clip_segments) + 1):
            if str((kwargs or {}).get(f"prompt_{i}") or "").strip():
                found.append(i)
        if found:
            return found
        return list(range(1, int(per_clip_segments) + 1))
    parsed = parse_prompt_document(prompt)
    indices = [int(clip["index"]) for clip in story_clips(parsed)]
    if not indices:
        raise ValueError("h3_studio: prompt has no ## Clip sections")
    return indices


def resolve_regen_clips(clip_index, prompt_indices) -> list[int]:
    available = [int(n) for n in (prompt_indices or [])]
    if not available:
        raise ValueError("h3_studio: prompt has no ## Clip sections")
    requested = parse_clip_index(clip_index)
    if not requested:
        return list(available)
    missing = [n for n in requested if n not in set(available)]
    if missing:
        raise ValueError(f"h3_studio: prompt has no clip {missing[0]}")
    return requested


def parse_saved_clip_index(name: str, stem=None):
    match = _SAVED_CLIP.fullmatch(str(name or ""))
    if not match:
        return None
    file_stem, index = match.group(1), int(match.group(2))
    if stem is not None and file_stem != stem:
        return None
    return index


def list_saved_indices(names, stem=None) -> list[int]:
    found = []
    for name in names or []:
        index = parse_saved_clip_index(name, stem)
        if index:
            found.append(index)
    return sorted(set(found))


def require_contiguous_chain(indices) -> int:
    nums = sorted(int(n) for n in (indices or []))
    if not nums or nums[0] != 1:
        raise ValueError(
            "h3_studio: latent_prefix has no contiguous saved chain starting at clip 1"
        )
    expected = list(range(1, nums[-1] + 1))
    if nums != expected:
        gap = next(n for n in expected if n not in set(nums))
        raise ValueError(f"h3_studio: latent_prefix is missing saved clip {gap}")
    return nums[-1]


def infer_story_and_loop(saved_last, *, segments_hint=None, loop_hint=False, max_story=None):
    last = int(saved_last)
    if loop_hint and segments_hint is not None:
        story = int(segments_hint)
        if last == story + 1:
            return story, True
        if last == story:
            return story, False
    if loop_hint and max_story is not None and last == int(max_story) + 1:
        return int(max_story), True
    return last, False


def clip_fix_neighbors(index, regen, saved):
    """Previous / next clip indices for one regen slot. None means no context."""
    i = int(index)
    regen_set = {int(n) for n in regen}
    saved_set = {int(n) for n in saved}
    prev = None
    if i > 1:
        prev = i - 1
        if prev not in saved_set and prev not in regen_set:
            prev = None
    nxt = i + 1
    if nxt in saved_set and nxt not in regen_set:
        next_i = nxt
    else:
        next_i = None
    return prev, next_i


def require_fix_slots(regen, saved, story_n, has_loop=False):
    saved_set = {int(n) for n in saved}
    story_n = int(story_n)
    for i in range(1, story_n + 1):
        if i not in saved_set:
            raise ValueError(f"h3_studio: latent_prefix has no saved clip {i}")
    if has_loop and (story_n + 1) not in saved_set:
        raise ValueError(f"h3_studio: latent_prefix has no saved Loop clip {story_n + 1}")
    for i in regen:
        n = int(i)
        if n < 1 or n > story_n:
            raise ValueError(
                f"h3_studio: clip {n} is outside the saved chain 1..{story_n}"
            )
        if n > 1 and (n - 1) not in saved_set:
            raise ValueError(
                f"h3_studio: clip {n} needs saved clip {n - 1} as previous context"
            )


def should_regen_loop(regen, story_n, has_loop) -> bool:
    return bool(has_loop) and int(story_n) in {int(n) for n in regen}


def backup_stamp(now=None) -> str:
    when = now or datetime.now()
    return when.strftime("%Y%m%d_%H%M%S")


def backup_folder(chain_dir: str, stamp: str) -> str:
    return os.path.join(str(chain_dir), f"backup_{stamp}")


def files_for_clip_slot(directory, stem, index) -> list[str]:
    tag = f"{stem}_{int(index):05d}"
    found = []
    if not os.path.isdir(directory):
        return found
    for name in os.listdir(directory):
        match = _CLIP_FILE.fullmatch(name)
        if not match:
            continue
        if match.group(1) != stem or int(match.group(2)) != int(index):
            continue
        found.append(os.path.join(directory, name))
    latent = os.path.join(directory, f"{tag}.safetensors")
    if os.path.isfile(latent) and latent not in found:
        found.insert(0, latent)
    return found


def backup_clip_slots(directory, stem, indices, dest_dir) -> list[str]:
    os.makedirs(dest_dir, exist_ok=True)
    copied = []
    for index in indices:
        for path in files_for_clip_slot(directory, stem, index):
            dest = os.path.join(dest_dir, os.path.basename(path))
            shutil.copy2(path, dest)
            copied.append(dest)
    if not copied:
        raise ValueError("h3_studio: nothing to backup for the selected clips")
    return copied


def expand_fix_clip(prompt: str, index: int, *, song_audio=False, kwargs=None) -> str:
    doc = str(prompt or "").strip()
    if doc:
        parsed = parse_prompt_document(doc)
        try:
            return expand_clip(parsed, int(index), song_audio=song_audio)
        except ValueError:
            pass
    widget = str((kwargs or {}).get(f"prompt_{int(index)}") or "").strip()
    if widget:
        return widget if widget.endswith("\n") else widget + "\n"
    raise ValueError(f"h3_studio: prompt has no clip {int(index)}")


def expand_fix_loop(prompt: str, loop_prompt="") -> str:
    widget = str(loop_prompt or "").strip()
    parsed = parse_prompt_document(prompt) if str(prompt or "").strip() else None
    if parsed is not None:
        try:
            return expand_clip(parsed, 0, is_loop=True)
        except ValueError:
            pass
    if widget:
        return widget if widget.endswith("\n") else widget + "\n"
    raise ValueError("h3_studio: Loop regen needs a ## Loop section or loop_prompt")

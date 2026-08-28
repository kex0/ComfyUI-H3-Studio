"""Stash a seed prompt, clip indices, and a fix plan onto a Builder pack."""

from __future__ import annotations

import re

from .node_help import NODE_HELP
from .pack import require_pack
from .prompt_document import parse_prompt_document, story_clips

PROMPT_MODE_CLIP_FIX = "clip_fix"
_INDEX_TOKEN = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_clip_index(text: str) -> list[int]:
    raw = re.sub(r"\s*-\s*", "-", str(text or "").strip())
    if not raw:
        return []
    found = []
    seen = set()
    for part in re.split(r"[,\s]+", raw):
        if not part:
            continue
        match = _INDEX_TOKEN.match(part)
        if not match:
            raise ValueError(f"h3_studio: invalid clip_index {part!r}")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        if start < 1 or end < 1:
            raise ValueError("h3_studio: clip_index must be >= 1")
        if end < start:
            start, end = end, start
        for n in range(start, end + 1):
            if n not in seen:
                seen.add(n)
                found.append(n)
    return found


def seed_is_partial(parsed) -> bool:
    story = story_clips(parsed)
    indices = [int(clip["index"]) for clip in story]
    if not indices:
        raise ValueError("h3_studio: prompt has no ## Clip sections")
    n = len(indices)
    header_seg = parsed.get("segments")
    if header_seg is not None and int(header_seg) != n:
        return True
    return sorted(indices) != list(range(1, n + 1))


def resolve_fix_clips(clip_index, parsed) -> list[int]:
    story = story_clips(parsed)
    available = {int(clip["index"]) for clip in story}
    if not available:
        raise ValueError("h3_studio: prompt has no ## Clip sections")
    requested = parse_clip_index(clip_index)
    if not requested:
        if not seed_is_partial(parsed):
            raise ValueError(
                "h3_studio: clip_index is required when original_prompt has a full clip set"
            )
        return [int(clip["index"]) for clip in story]
    missing = [n for n in requested if n not in available]
    if missing:
        raise ValueError(f"h3_studio: original_prompt has no clip {missing[0]}")
    return requested


_CLIP_HEAD = re.compile(
    r"^(?:##\s+Clip\s+(\d+)\s*[—\-–]+|\*\*Clip\s+(\d+)\s*[—\-–]+)",
    re.I,
)
_LOOP_HEAD = re.compile(r"^(?:##\s+Loop\b|\*\*Loop\b)", re.I)


def window_indices(selected) -> list[int]:
    nums = [int(n) for n in (selected or [])]
    if not nums:
        return []
    lo = min(nums) - 1
    hi = max(nums) + 1
    return list(range(max(1, lo), hi + 1))


def extract_prompt_window(text: str, clip_index: str) -> str:
    """Selected story clips plus one previous and one following. No document header."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return ""
    lines = raw.split("\n")
    starts = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        match = _CLIP_HEAD.match(stripped)
        if match:
            starts.append((i, int(match.group(1) or match.group(2)), False))
            continue
        if _LOOP_HEAD.match(stripped):
            starts.append((i, None, True))
    if not starts:
        return ""
    clips = []
    for j, (start, index, is_loop) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).rstrip()
        clips.append((index, is_loop, block))
    story = [(index, block) for index, is_loop, block in clips if not is_loop and index]
    available = {index for index, _block in story}
    selected = parse_clip_index(clip_index)
    if not selected:
        selected = [index for index, _block in story]
    want = set(window_indices(selected)) & available
    kept = [block for index, block in story if index in want]
    if not kept:
        return ""
    return "\n\n".join(kept).strip() + "\n"


class H3StudioClipPromptFixer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pack": ("H3_STUDIO_PACK", {
                    "tooltip": (
                        "Wire H3 Studio Builder here. Inventory, song, lyrics, and duration "
                        "stay on the pack; this node only adds clip-fix metadata."
                    ),
                }),
                "original_prompt": ("STRING", {
                    "multiline": True, "default": "", "dynamicPrompts": False,
                    "tooltip": (
                        "Paste the Music Video or Auto Chain prompt. Full document or just "
                        "the ## Clip sections to rewrite."
                    ),
                }),
                "clip_index": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Story clip indices to rewrite, e.g. 11-12 or 11,12. Empty is allowed "
                        "only when original_prompt is a partial paste."
                    ),
                }),
                "plan": ("STRING", {
                    "multiline": True, "default": "", "dynamicPrompts": False,
                    "tooltip": (
                        "What to change in the selected clip bodies. Lyrics and timings stay "
                        "locked. Overrides the Builder plan for Local Prompter."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("H3_STUDIO_PACK",)
    RETURN_NAMES = ("pack",)
    OUTPUT_TOOLTIPS = (
        "Same Builder pack plus clip_fix metadata for Local Prompter.",
    )
    FUNCTION = "attach_fix"
    CATEGORY = "H3 Studio"
    DESCRIPTION = NODE_HELP["H3StudioClipPromptFixer"]

    def attach_fix(self, pack, original_prompt, clip_index="", plan=""):
        pack = dict(require_pack(pack))
        plan_text = str(plan or "").strip()
        if not plan_text:
            raise ValueError("h3_studio: Plan is required")
        seed = str(original_prompt or "").strip()
        if not seed:
            raise ValueError("h3_studio: original_prompt is empty")
        parsed = parse_prompt_document(seed)
        pack["plan"] = plan_text
        pack["prompt_mode"] = PROMPT_MODE_CLIP_FIX
        pack["seed_prompt"] = seed
        pack["fix_clips"] = resolve_fix_clips(clip_index, parsed)
        return (pack,)

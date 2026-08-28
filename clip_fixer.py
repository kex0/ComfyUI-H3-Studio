"""Music Video / Auto Chain Clip Fixer nodes: regenerate selected slots and restitch."""

from __future__ import annotations

import os

from .auto_chain import H3StudioAutoChain
from .clip_fix_chain import (
    backup_clip_slots, backup_folder, backup_stamp, infer_story_and_loop,
    list_saved_indices, prompt_story_indices, require_contiguous_chain,
    require_fix_slots, resolve_regen_clips, should_regen_loop,
)
from .music_video import H3StudioMusicVideo

CLIP_INDEX_SPEC = ("STRING", {
    "default": "",
    "tooltip": (
        "Story clips to regenerate, e.g. 11-12 or 11,12. Empty regenerates every ## Clip "
        "in prompt. Continue clips sandwich previous + next on-disk latents when the next "
        "slot is not also being rewritten. The full saved chain is restitched."
    ),
})


def with_clip_index(spec, *, drop=()):
    required = dict(spec.get("required") or {})
    optional = dict(spec.get("optional") or {})
    hidden = dict(spec.get("hidden") or {})
    for key in drop:
        required.pop(key, None)
        optional.pop(key, None)
    if "prompt_mode" in optional and "duration" in drop:
        optional["prompt_mode"] = (["single", "per_clip"], {
            "default": "single",
            "tooltip": (
                "single: one H3 Studio prompt with ## Clip sections. "
                "per_clip: one editor per ## Clip in the prompt. "
                "Duration, clip count, and loop are read from the prompt."
            ),
        })
    out = {}
    inserted = False
    for key, value in required.items():
        out[key] = value
        if key == "prompt":
            out["clip_index"] = CLIP_INDEX_SPEC
            inserted = True
    if not inserted:
        out["clip_index"] = CLIP_INDEX_SPEC
    return {"required": out, "optional": optional, "hidden": hidden}


def chain_dir_and_stem(base: str):
    if os.path.isdir(base):
        return base, os.path.basename(base.rstrip("\\/"))
    directory = os.path.dirname(base)
    stem = os.path.basename(base)
    return directory or ".", stem


def prepare_clip_fix(latent_prefix, prompt, clip_index, *, loop_hint=False,
                     segments_hint=None, max_story=None, kwargs=None,
                     per_clip_segments=None, stamp=None):
    from .nodes import _saved_chain_base

    base = _saved_chain_base(latent_prefix)
    directory, stem = chain_dir_and_stem(base)
    if not os.path.isdir(directory):
        raise ValueError(
            f"h3_studio: latent_prefix has no saved chain directory {directory}"
        )
    saved = list_saved_indices(os.listdir(directory), stem)
    last = require_contiguous_chain(saved)
    story_n, has_loop = infer_story_and_loop(
        last, segments_hint=segments_hint, loop_hint=loop_hint, max_story=max_story,
    )
    prompt_indices = prompt_story_indices(
        prompt, kwargs=kwargs, per_clip_segments=per_clip_segments,
    )
    regen = resolve_regen_clips(clip_index, prompt_indices)
    require_fix_slots(regen, saved, story_n, has_loop=has_loop)
    overwrite = list(regen)
    if should_regen_loop(regen, story_n, has_loop):
        overwrite.append(story_n + 1)
    dest = backup_folder(directory, stamp or backup_stamp())
    copied = backup_clip_slots(directory, stem, overwrite, dest)
    return {
        "directory": directory,
        "stem": stem,
        "saved": saved,
        "story_n": story_n,
        "has_loop": has_loop,
        "regen": regen,
        "overwrite": overwrite,
        "backup_dir": dest,
        "backup_files": copied,
    }


class H3StudioMusicVideoClipFixer(H3StudioMusicVideo):
    @classmethod
    def INPUT_TYPES(cls):
        return with_clip_index(
            H3StudioMusicVideo.INPUT_TYPES(),
            drop=("resume_from_clip", "stop_after_clip", "duration", "segments", "seamless_loop"),
        )

    DESCRIPTION = (
        "Regenerate selected Music Video clips under latent_prefix and restitch the full chain. "
        "Continue clips use the previous latent and, when the following slot is kept, that next "
        "opening as end context. Lyrics/song windows stay on the saved slot metadata."
    )

    def generate(self, pack, clip_index="", **kwargs):
        from .pack import require_pack
        from .prompt_document import duration_and_segments_from_pack_or_prompt
        pack = require_pack(pack)
        duration, _segments = duration_and_segments_from_pack_or_prompt(
            pack, kwargs.get("prompt") or "", need_segments=False,
        )
        kwargs["duration"] = duration
        kwargs["clip_fix"] = True
        kwargs["clip_index"] = clip_index
        return super().generate(pack, **kwargs)


class H3StudioAutoChainClipFixer(H3StudioAutoChain):
    @classmethod
    def INPUT_TYPES(cls):
        return with_clip_index(
            H3StudioAutoChain.INPUT_TYPES(),
            drop=("resume_from_clip", "duration", "segments", "seamless_loop"),
        )

    DESCRIPTION = (
        "Regenerate selected Auto Chain clips under latent_prefix and restitch the full chain. "
        "Continue clips sandwich previous + next latents when the next slot is not rewritten. "
        "If Finish is selected and a Loop clip exists, the Loop clip is regenerated too."
    )

    def generate(self, pack, prompt_mode="single", clip_index="", **kwargs):
        from .pack import require_pack
        from .prompt_document import (
            document_has_loop, duration_and_segments_from_pack_or_prompt,
        )
        pack = require_pack(pack)
        prompt = kwargs.get("prompt") or ""
        duration, _segments = duration_and_segments_from_pack_or_prompt(
            pack, prompt, need_segments=False,
        )
        kwargs["duration"] = duration
        kwargs["pack"] = pack
        kwargs["model_1"] = pack["models"][0]["model"]
        kwargs["clip_fix"] = True
        kwargs["clip_index"] = clip_index
        kwargs["segments"] = int(pack["segments"]) if pack.get("segments") is not None else None
        kwargs["seamless_loop"] = bool(pack.get("loop") or document_has_loop(prompt))
        kwargs["clip_fix_per_clip"] = (
            str(prompt_mode or "single").strip().lower().replace(" ", "_") == "per_clip"
        )
        return self._generate_chain(**kwargs)

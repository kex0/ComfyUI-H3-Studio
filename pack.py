"""H3 Studio pack: Builder labels, Ref2VA caps, and per-clip prompt selection."""

from __future__ import annotations

import re

MAX_IMAGES = 9
MAX_VIDEOS = 3
MAX_AUDIOS = 3
MAX_MIXED = 12
MAX_MODELS = 12
MIN_CLIP_SEC = 2.0
MAX_CLIP_SEC = 15.0
MAX_TYPE_TOTAL_SEC = 15.0

_TAG = re.compile(r"<(Picture|Video|Audio|Model)\s+(\d+)(?::(\d+))?>", re.I)
_LINE = re.compile(r"^(Picture|Video|Audio|Model)\s+(\d+)\s*:", re.I | re.M)
_MODEL_TAG = re.compile(r"<Model\s+\d+(?::\d+)?>", re.I)


def parse_prompt_citations(text: str) -> dict:
    text = str(text or "")
    found = {"Picture": [], "Video": [], "Audio": [], "Model": []}
    video_picks = []
    audio_picks = []
    seen_video = set()
    seen_audio = set()
    for kind, raw, seg in _TAG.findall(text):
        key = kind[:1].upper() + kind[1:].lower()
        n = int(raw)
        if n not in found[key]:
            found[key].append(n)
        segment = max(1, int(seg or 1))
        if key == "Video":
            pair = (n, segment)
            if pair not in seen_video:
                seen_video.add(pair)
                video_picks.append(pair)
        elif key == "Audio":
            pair = (n, segment)
            if pair not in seen_audio:
                seen_audio.add(pair)
                audio_picks.append(pair)
    for kind, raw in _LINE.findall(text):
        key = kind[:1].upper() + kind[1:].lower()
        n = int(raw)
        if n not in found[key]:
            found[key].append(n)
        if key == "Video":
            pair = (n, 1)
            if pair not in seen_video:
                seen_video.add(pair)
                video_picks.append(pair)
        elif key == "Audio":
            pair = (n, 1)
            if pair not in seen_audio:
                seen_audio.add(pair)
                audio_picks.append(pair)
    return {
        "pictures": found["Picture"],
        "videos": found["Video"],
        "audios": found["Audio"],
        "models": found["Model"],
        "video_picks": video_picks,
        "audio_picks": audio_picks,
    }


def strip_model_tags(text: str) -> str:
    cleaned = _MODEL_TAG.sub("", str(text or ""))
    return re.sub(r"[ \t]+\n", "\n", cleaned).strip()


def rewrite_kind_tags(text: str, kind: str, mapping: dict) -> str:
    pattern = re.compile(rf"<{re.escape(kind)}\s+(\d+)(?::(\d+))?>", re.I)

    def repl(match):
        old = int(match.group(1))
        seg = int(match.group(2) or 1)
        if mapping and (old, seg) in mapping:
            return f"<{kind} {int(mapping[(old, seg)])}>"
        if mapping and old in mapping:
            return f"<{kind} {int(mapping[old])}>"
        return f"<{kind} {old}>"

    return pattern.sub(repl, text)


def apply_media_region(item, segment=1):
    if not isinstance(item, dict):
        return item
    regions = item.get("regions")
    if not isinstance(regions, list) or not regions:
        out = dict(item)
        out["region_index"] = 1
        return out
    idx = max(1, int(segment or 1)) - 1
    if idx >= len(regions):
        idx = len(regions) - 1
    region = regions[idx] if isinstance(regions[idx], dict) else {}
    out = dict(item)
    out["region_index"] = idx + 1
    if "frames" in region:
        out["frames"] = region.get("frames")
    if "audio" in region:
        out["audio"] = region.get("audio")
    if region.get("duration") is not None:
        out["duration"] = region.get("duration")
    return out


def pick_media_regions(items, picks, kind: str):
    by_idx = {int(item["index"]): item for item in items}
    selected = []
    for index, segment in picks:
        n = int(index)
        if n not in by_idx:
            raise ValueError(
                f"h3_studio: prompt cites {kind} {n} but the pack has no enabled {kind} {n}"
            )
        selected.append(apply_media_region(by_idx[n], segment))
    return selected


def assert_ref_caps(pictures, videos, audios, extra_audio=0, extra_mixed=0):
    n_pic = len(pictures)
    n_vid = len(videos)
    n_aud = len(audios) + int(extra_audio)
    n_mixed = n_pic + n_vid + n_aud + int(extra_mixed)
    if n_pic > MAX_IMAGES:
        raise ValueError(f"h3_studio: at most {MAX_IMAGES} images, got {n_pic}")
    if n_vid > MAX_VIDEOS:
        raise ValueError(f"h3_studio: at most {MAX_VIDEOS} videos, got {n_vid}")
    if n_aud > MAX_AUDIOS:
        raise ValueError(f"h3_studio: at most {MAX_AUDIOS} audio clips, got {n_aud}")
    if n_mixed > MAX_MIXED:
        raise ValueError(
            f"h3_studio: at most {MAX_MIXED} mixed reference files, got {n_mixed}"
        )
    _assert_durations(videos, "video")
    _assert_durations(audios, "audio")


def _item_duration(item) -> float:
    if isinstance(item, dict):
        return float(item.get("duration") or 0.0)
    return 0.0


def _assert_durations(items, kind: str):
    total = 0.0
    for item in items:
        dur = _item_duration(item)
        if dur <= 0:
            continue
        if dur + 1e-9 < MIN_CLIP_SEC or dur - 1e-9 > MAX_CLIP_SEC:
            raise ValueError(
                f"h3_studio: each {kind} must be {MIN_CLIP_SEC:g}–{MAX_CLIP_SEC:g}s, "
                f"got {dur:.3f}s"
            )
        total += dur
    if total - 1e-9 > MAX_TYPE_TOTAL_SEC:
        raise ValueError(
            f"h3_studio: total {kind} duration {total:.3f}s exceeds {MAX_TYPE_TOTAL_SEC:g}s"
        )


def pick_by_index(items, indices, kind: str):
    by_idx = {int(item["index"]): item for item in items}
    selected = []
    for n in sorted(set(int(i) for i in indices)):
        if n not in by_idx:
            raise ValueError(
                f"h3_studio: prompt cites {kind} {n} but the pack has no enabled {kind} {n}"
            )
        selected.append(by_idx[n])
    return selected


def select_default(pictures, videos, audios, extra_audio=0):
    remain_mixed = MAX_MIXED - int(extra_audio)
    remain_aud = MAX_AUDIOS - int(extra_audio)
    pics, vids, auds = [], [], []
    for item in pictures:
        if len(pics) >= MAX_IMAGES or remain_mixed <= 0:
            break
        pics.append(item)
        remain_mixed -= 1
    for item in videos:
        if len(vids) >= MAX_VIDEOS or remain_mixed <= 0:
            break
        vids.append(item)
        remain_mixed -= 1
    for item in audios:
        if len(auds) >= remain_aud or remain_mixed <= 0:
            break
        auds.append(item)
        remain_mixed -= 1
    return pics, vids, auds


def require_pack(pack) -> dict:
    if not isinstance(pack, dict):
        raise ValueError("h3_studio: connect H3 Studio Builder to pack")
    models = list(pack.get("models") or [])
    if not models:
        raise ValueError("h3_studio: pack has no enabled model")
    out = {
        "models": models,
        "pictures": list(pack.get("pictures") or []),
        "videos": list(pack.get("videos") or []),
        "audios": list(pack.get("audios") or []),
    }
    if pack.get("duration") is not None:
        out["duration"] = float(pack["duration"])
    if pack.get("segments") is not None:
        out["segments"] = int(pack["segments"])
    out["plan"] = str(pack.get("plan") or "").strip()
    if pack.get("loop") is not None:
        out["loop"] = bool(pack.get("loop"))
    if pack.get("song") is not None:
        out["song"] = pack["song"]
    out["lyrics"] = str(pack.get("lyrics") or "").strip()
    return out


def _builder_audio_index(prompt_n: int, song: bool) -> int | None:
    if song:
        if int(prompt_n) <= 1:
            return None
        return int(prompt_n) - 1
    return int(prompt_n)


def resolve_pack_for_clip(pack, prompt, song_audio=False) -> dict:
    pack = require_pack(pack)
    song = bool(song_audio)
    extra_audio = 1 if song else 0
    cites = parse_prompt_citations(prompt)
    models = pack["models"]
    if cites["models"]:
        want = int(cites["models"][0])
        model_item = next((m for m in models if int(m["index"]) == want), None)
        if model_item is None:
            raise ValueError(
                f"h3_studio: prompt cites Model {want} but the pack has no enabled Model {want}"
            )
    else:
        model_item = models[0]

    builder_audio_picks = []
    audio_picks = cites.get("audio_picks") or [(n, 1) for n in cites["audios"]]
    for n, seg in audio_picks:
        mapped = _builder_audio_index(n, song)
        if mapped is not None:
            builder_audio_picks.append((mapped, seg))
    video_picks = cites.get("video_picks") or [(n, 1) for n in cites["videos"]]
    any_refs = bool(cites["pictures"] or video_picks or builder_audio_picks)
    if any_refs:
        pictures = pick_by_index(pack["pictures"], cites["pictures"], "Picture")
        videos = pick_media_regions(pack["videos"], video_picks, "Video")
        audios = pick_media_regions(pack["audios"], builder_audio_picks, "Audio")
    else:
        pictures, videos, audios = select_default(
            pack["pictures"], pack["videos"], pack["audios"], extra_audio=extra_audio,
        )

    assert_ref_caps(pictures, videos, audios, extra_audio=extra_audio)

    pic_map = {int(item["index"]): i for i, item in enumerate(pictures, 1)}
    vid_map = {}
    for i, item in enumerate(videos, 1):
        vid_map[int(item["index"])] = i
        vid_map[(int(item["index"]), int(item.get("region_index") or 1))] = i
    h3_audio = 1 if song else 0
    audio_map = {}
    if song:
        audio_map[1] = 1
        audio_map[(1, 1)] = 1
    for item in videos:
        if item.get("audio") is not None:
            h3_audio += 1
    for item in audios:
        h3_audio += 1
        prompt_n = int(item["index"]) + (1 if song else 0)
        seg = int(item.get("region_index") or 1)
        audio_map[prompt_n] = h3_audio
        audio_map[(prompt_n, seg)] = h3_audio

    text = strip_model_tags(prompt)
    text = rewrite_kind_tags(text, "Picture", pic_map)
    text = rewrite_kind_tags(text, "Video", vid_map)
    text = rewrite_kind_tags(text, "Audio", audio_map)

    return {
        "model": model_item["model"],
        "prompt": text,
        "pictures": [item["image"] for item in pictures],
        "videos": [item["frames"] for item in videos],
        "video_audios": [item.get("audio") for item in videos],
        "audios": [item["audio"] for item in audios],
        # Clip cites only the Builder still marked as MiniMax first image.
        "sole_first_frame": len(pictures) == 1 and bool(pictures[0].get("first_frame")),
    }


def pack_first_frame(pack):
    if not isinstance(pack, dict):
        return None
    for item in pack.get("pictures") or []:
        if item.get("first_frame"):
            return item.get("image")
    return None


def format_builder_dump(models, pictures, videos, audios, plan="", duration=None,
                        segments=None, loop=False) -> str:
    lines = ["H3 Studio Builder pack"]
    if duration is not None:
        lines.append(f"duration: {float(duration):.2f}s")
    if segments is not None:
        lines.append(f"segments: {int(segments)}")
    if loop:
        lines.append("loop: true")
    for item in models:
        desc = str(item.get("description") or "").strip() or "(no description)"
        lines.append(f"Model {int(item['index'])}: {desc}")
    for item in pictures:
        desc = str(item.get("description") or "").strip() or "(no description)"
        extra = " (first frame)" if item.get("first_frame") else ""
        lines.append(f"Picture {int(item['index'])}: {desc}{extra}")
    for item in videos:
        desc = str(item.get("description") or "").strip() or "(no description)"
        dur = float(item.get("duration") or 0.0)
        extra = " (with soundtrack)" if item.get("audio") is not None else ""
        lines.append(f"Video {int(item['index'])}: {dur:.1f}s {desc}{extra}")
    for item in audios:
        desc = str(item.get("description") or "").strip() or "(no description)"
        dur = float(item.get("duration") or 0.0)
        lines.append(f"Audio {int(item['index'])}: {dur:.1f}s {desc}")
    plan_text = str(plan or "").strip()
    if plan_text:
        lines.append("plan:")
        lines.append(plan_text)
    return "\n".join(lines) + "\n"

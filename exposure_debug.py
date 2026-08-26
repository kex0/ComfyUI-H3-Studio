"""Per-clip exposure tracer for Continue-head blink vs stitch leak."""

from __future__ import annotations

import json
import logging
import os

VAE_CHUNK_FRAMES = 17
PACKED_GROUP_FRAMES = 17
PROBE_CHUNKS = 2
NONE_ABS = 0.012
PUMP_ABS = 0.025
DARK_SCENE = 0.20
DARK_ABS = 0.015
SOURCE_MAE = 0.020

_LOG = logging.getLogger("h3_continuous")


def packed_keyframe_frames(frame_count: int) -> list[int]:
    n = int(frame_count)
    return list(range(0, n, PACKED_GROUP_FRAMES))


def frame_luma_series(images) -> list[float]:
    """Mean Rec.709 luma per frame. ``images`` is NHWC in 0..1."""
    if images is None:
        return []
    x = images.detach()
    if x.ndim != 4:
        raise ValueError(f"h3_continuous: exposure debug expected NHWC images, got {tuple(x.shape)}")
    luma = x[..., 0].float() * 0.2126 + x[..., 1].float() * 0.7152 + x[..., 2].float() * 0.0722
    return [float(v) for v in luma.mean(dim=(1, 2)).cpu()]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def _threshold(baseline: float) -> float:
    if baseline < DARK_SCENE:
        return min(PUMP_ABS, max(DARK_ABS, 0.08 * max(baseline, 0.04)))
    return PUMP_ABS


def _local_peaks(luma: list[float], start: int, end: int, baseline: float, threshold: float) -> list[dict]:
    peaks = []
    lo = max(1, int(start))
    hi = min(len(luma) - 1, int(end))
    for i in range(lo, hi):
        if luma[i] < luma[i - 1] or luma[i] < luma[i + 1]:
            continue
        delta = luma[i] - baseline
        if delta < threshold:
            continue
        peaks.append({"frame": i, "luma": round(luma[i], 6), "delta": round(delta, 6)})
    peaks.sort(key=lambda p: p["delta"], reverse=True)
    return peaks[:4]


def _source_window(previous_luma: list[float] | None, head: int, ignored_tail: int) -> tuple[int, int]:
    if not previous_luma or head <= 0:
        return 0, 0
    source_end = len(previous_luma) - max(0, int(ignored_tail))
    source_start = source_end - int(head)
    if source_start < 0 or source_end > len(previous_luma) or source_end <= source_start:
        return 0, 0
    return source_start, source_end


def classify_exposure(
    luma: list[float],
    *,
    head_context_frames: int = 0,
    ignored_tail_frames: int = 0,
    previous_luma: list[float] | None = None,
    clip_index: int = 1,
) -> dict:
    n = len(luma)
    head = max(0, min(int(head_context_frames), n))
    probe = min(n, max(head + VAE_CHUNK_FRAMES, PROBE_CHUNKS * VAE_CHUNK_FRAMES))
    body = luma[head:] if head < n else luma
    baseline = _median(body if len(body) >= 8 else luma)
    threshold = _threshold(baseline)
    max_frame = 0
    max_delta = 0.0
    for i, value in enumerate(luma[:probe] or luma):
        delta = abs(value - baseline)
        if delta >= max_delta:
            max_delta = delta
            max_frame = i

    head_peaks = _local_peaks(luma, 0, head, baseline, threshold) if head else []
    leak_end = min(n, head + VAE_CHUNK_FRAMES)
    leak_peaks = _local_peaks(luma, head, leak_end, baseline, threshold) if head else []
    early_peaks = _local_peaks(luma, 0, probe, baseline, threshold)
    body_std = _std(body)

    if max_delta < NONE_ABS and not early_peaks:
        verdict = "none"
    elif head and leak_peaks:
        verdict = "leak"
    elif head and (head_peaks or (max_frame < head and max_delta >= threshold)):
        verdict = "head_only"
    elif body_std >= threshold and max_frame >= max(head, probe // 2):
        verdict = "body_varies"
    elif early_peaks or max_delta >= threshold:
        verdict = "early_pump"
    else:
        verdict = "none"

    source_start, source_end = _source_window(previous_luma, head, ignored_tail_frames)
    source = {
        "available": False,
        "start_frame": source_start,
        "end_frame": source_end,
        "mean": None,
        "regen_mean": None,
        "mae": None,
        "max_abs": None,
    }
    if previous_luma and source_end > source_start and head > 0:
        src = previous_luma[source_start:source_end]
        regen = luma[:head]
        pairs = list(zip(src, regen))
        mae = sum(abs(a - b) for a, b in pairs) / len(pairs)
        max_abs = max(abs(a - b) for a, b in pairs)
        source = {
            "available": True,
            "start_frame": source_start,
            "end_frame": source_end,
            "mean": round(sum(src) / len(src), 6),
            "regen_mean": round(sum(regen) / len(regen), 6),
            "mae": round(mae, 6),
            "max_abs": round(max_abs, 6),
        }

    cause = _cause(verdict, source, clip_index, head)
    return {
        "clip_index": int(clip_index),
        "frame_count": n,
        "head_context_frames": head,
        "ignored_tail_frames": int(ignored_tail_frames),
        "vae_chunk_frames": VAE_CHUNK_FRAMES,
        "probe_frames": probe,
        "baseline_luma": round(baseline, 6),
        "head_mean": round(sum(luma[:head]) / head, 6) if head else None,
        "body_mean": round(sum(body) / len(body), 6) if body else None,
        "body_std": round(body_std, 6),
        "threshold": round(threshold, 6),
        "max_abs_delta": round(max_delta, 6),
        "max_delta_frame": max_frame,
        "packed_keyframes": packed_keyframe_frames(n)[:8],
        "head_peaks": head_peaks,
        "leak_peaks": leak_peaks,
        "early_peaks": early_peaks,
        "source": source,
        "verdict": verdict,
        "cause": cause,
        "luma": [round(v, 6) for v in luma],
    }


def _cause(verdict: str, source: dict, clip_index: int, head: int) -> str:
    if int(clip_index) <= 1:
        return "clip1_open" if verdict != "none" else "clean"
    if verdict == "none":
        return "clean"
    pumped = (
        source.get("available")
        and source.get("mae") is not None
        and source["mae"] >= SOURCE_MAE
        and (source.get("regen_mean") or 0) > (source.get("mean") or 0) + SOURCE_MAE
    )
    if pumped and verdict == "leak":
        return "reconstruction_pump_leaks"
    if pumped:
        return "reconstruction_pump_head_only"
    if verdict == "leak":
        return "join_body_pump"
    if verdict == "head_only":
        return "preview_head_only"
    return verdict


def format_log_line(report: dict) -> str:
    source = report.get("source") or {}
    src = "n/a"
    if source.get("available"):
        src = (
            f"src {source['start_frame']}:{source['end_frame']} "
            f"mean={source['mean']:.3f} regen={source['regen_mean']:.3f} "
            f"mae={source['mae']:.3f}"
        )
    peaks = report.get("early_peaks") or []
    peak_txt = ",".join(str(p["frame"]) for p in peaks[:3]) or "-"
    return (
        f"exposure clip {report['clip_index']} | cause={report['cause']} | "
        f"verdict={report['verdict']} | head {report['head_context_frames']} | "
        f"base {report['baseline_luma']:.3f} | max Δ {report['max_abs_delta']:.3f} "
        f"@ f{report['max_delta_frame']} | peaks {peak_txt} | {src}"
    )


def sidecar_path(latent_prefix: str, clip_index: int) -> str:
    from .nodes import _saved_chain_base
    base = _saved_chain_base(latent_prefix)
    folder = os.path.dirname(base)
    if folder:
        os.makedirs(folder, exist_ok=True)
    return f"{base}_{int(clip_index):05d}_exposure.json"


def write_sidecar(report: dict, path: str) -> str:
    payload = dict(report)
    luma = payload.get("luma") or []
    csv_path = path[:-5] + ".csv" if path.endswith(".json") else path + ".csv"
    lines = ["frame,luma,region,vae_chunk,packed_keyframe"]
    head = int(payload.get("head_context_frames") or 0)
    for i, value in enumerate(luma):
        region = "head" if i < head else "body"
        chunk = i // VAE_CHUNK_FRAMES
        key = 1 if i % PACKED_GROUP_FRAMES == 0 else 0
        lines.append(f"{i},{value:.6f},{region},{chunk},{key}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    with open(csv_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    payload["csv_path"] = csv_path
    return path


def load_sidecar(latent_prefix: str, clip_index: int) -> dict | None:
    path = sidecar_path(latent_prefix, clip_index)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def report_clip_exposure(
    images,
    *,
    clip_index: int,
    role: str,
    head_context_frames: int,
    ignored_tail_frames: int = 0,
    handover=None,
    previous_luma: list[float] | None = None,
    latent_prefix: str | None = None,
) -> dict:
    luma = frame_luma_series(images)
    report = classify_exposure(
        luma,
        head_context_frames=head_context_frames,
        ignored_tail_frames=ignored_tail_frames,
        previous_luma=previous_luma,
        clip_index=clip_index,
    )
    report["role"] = str(role)
    if isinstance(handover, dict):
        report["freeze_detected"] = bool(handover.get("freeze_detected"))
        report["no_lock_fallback"] = bool(handover.get("no_lock_fallback_applied"))
        report["landing_tail_frames"] = handover.get("landing_tail_frames")
    line = format_log_line(report)
    report["log_line"] = line
    _LOG.warning("h3_continuous: %s", line)
    if latent_prefix:
        path = sidecar_path(latent_prefix, clip_index)
        write_sidecar(report, path)
        report["sidecar"] = path
        _LOG.warning("h3_continuous: exposure sidecar %s", path)
    return report

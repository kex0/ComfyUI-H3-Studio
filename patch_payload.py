"""Rewrite MiniMax H3 cond latents when this suite packs both keyframes and refs."""

from .patch_layout import graph_has_our_markers


def _rewrite_marked_payload(payload, keyframes, refs, frame_count=None):
    if not isinstance(payload, dict):
        raise RuntimeError(
            "h3_continuous: could not access the MiniMax H3 conditioning payload; "
            "refusing an unsafe continuation"
        )
    payload["cond_video_latents"] = (
        [k["latent"] for k in keyframes if "latent" in k]
        + [r["latent"] for r in refs if "latent" in r]
    )
    payload["cond_audio_latents"] = [
        r["audio_latent"] for r in refs if r.get("audio_latent") is not None
    ]
    if frame_count is not None:
        payload["frame_count"] = frame_count
    return payload


def maybe_rewrite_marked_payload(payload):
    if not isinstance(payload, dict):
        return payload
    keyframes = payload.get("keyframes")
    refs = payload.get("refs")
    if not keyframes or not refs or not graph_has_our_markers(keyframes, refs):
        return payload
    return _rewrite_marked_payload(payload, keyframes, refs, frame_count=payload.get("frame_count"))

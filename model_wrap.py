"""Per-MODEL APPLY_MODEL wrapper for marked H3 continuation payloads.

Clones the incoming MODEL so the shared checkpoint is not mutated. Unmarked
payloads pass through. Face Refine does not use this path.
"""

from .patch_layout import LAYOUT_ADAPT_MARKER, adapt_marked_layout, graph_has_our_markers
from .patch_payload import maybe_rewrite_marked_payload

WRAPPER_KEY = "h3_studio_apply_model"


def _payload_dict(value):
    if isinstance(value, dict):
        return value
    inner = getattr(value, "cond", None)
    return inner if isinstance(inner, dict) else None


def _apply_h3_payload(payload):
    if payload is None:
        return
    if payload.get("layout") is not None and getattr(payload.get("layout"), LAYOUT_ADAPT_MARKER, False):
        return
    keyframes = payload.get("keyframes")
    refs = payload.get("refs")
    if not graph_has_our_markers(keyframes, refs):
        return
    maybe_rewrite_marked_payload(payload)
    adapt_marked_layout(payload)


def apply_model_wrapper(executor, *args, **kwargs):
    _apply_h3_payload(_payload_dict(kwargs.get("minimax_payload")))
    return executor(*args, **kwargs)


def wrap_h3_model(model):
    from comfy.patcher_extension import WrappersMP

    cloned = model.clone()
    existing = cloned.get_wrappers(WrappersMP.APPLY_MODEL, WRAPPER_KEY)
    if existing:
        return cloned
    cloned.add_wrapper_with_key(WrappersMP.APPLY_MODEL, WRAPPER_KEY, apply_model_wrapper)
    return cloned

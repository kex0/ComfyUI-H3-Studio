"""Lazy runtime patch for MiniMax H3 interior latent anchors and timeline audio.

Nothing is patched when ComfyUI imports this node pack. The hook is installed
only when a continuation node is actually executed. Once installed, the
wrapper is gated on this suite's own marker keys, so unrelated H3 graphs stay
on the stock path.
"""

import logging

from .patch_utils import classify_callable

HC_INDEX = "h3_continuous_index"
HC_AUDIO_END_FRAME = "h3_continuous_audio_end_frame"
LAYOUT_PATCH_MARKER = "_herrgotts_h3_infinite_layout_patch"

_LOG = logging.getLogger("h3_continuous")
_ORIGINAL_INIT = None
_APPLIED = False
_MM = None

_KNOWN_EXTERNAL_MARKERS = (
    ("_h3_motion_context_layout_patch", "ComfyUI-H3-Motion-Context"),
)
# SolAttn Morton observes PackedLayout to register the video token span. It does
# not change position_ids or continuation math, so it is safe to wrap.
_COMPATIBLE_LAYOUT_MODULES = (
    "_morton_h3",
)


def _import_mm():
    import comfy.ldm.minimax.model as mm
    return mm


def get_layout_patch_status():
    try:
        mm = _import_mm()
    except Exception as exc:
        return None, f"cannot import comfy.ldm.minimax.model: {exc}"
    cls = getattr(mm, "PackedLayout", None)
    fn = getattr(cls, "__init__", None) if cls is not None else None
    if cls is None or fn is None:
        return None, "ComfyUI PackedLayout.__init__ is unavailable"
    status = classify_callable(
        cls, fn, LAYOUT_PATCH_MARKER, _KNOWN_EXTERNAL_MARKERS,
        compatible_modules=_COMPATIBLE_LAYOUT_MODULES,
    )
    return status, None


def _ref_cursor_advance(mm, refs):
    if not refs:
        return 0.0
    cursor = 0.0
    for blk in refs:
        kind = blk.get("kind")
        if kind == "image":
            cursor += 1.0
        elif kind == "audio":
            cursor += float(blk.get("ref_audio_t", 0))
        elif kind in ("video", "video_audio"):
            rt = float(blk.get("ref_audio_t", 0))
            vt = int(blk.get("latent_t", 0))
            cursor += max(rt, sum(mm._video_t_spans(vt)))
    return cursor


def _cond_t(mm, text_len, p):
    # PackedLayout: cursor + FRAME_RESCALE * resolved_frame_index
    return float(text_len) + mm.FRAME_RESCALE * float(p)


def _fix_keyframes(mm, layout, text_len, keyframes, refs):
    """Move only Herrgotts-marked keyframes onto the target timeline."""
    offset = _ref_cursor_advance(mm, refs)
    cond_spans = [(a, b) for a, b, kind in layout.segments if kind == "cond"]
    visual_kf = [kf for kf in keyframes or () if kf.get("latent") is not None]
    if len(cond_spans) != len(visual_kf):
        raise RuntimeError(
            "h3_continuous: PackedLayout cond segment count changed; refusing unsafe continuation"
        )
    for (a, b), kf in zip(cond_spans, visual_kf):
        if HC_INDEX not in kf:
            continue
        layout.position_ids[a:b, 0] = _cond_t(mm, text_len, kf[HC_INDEX]) + offset


def _pixel_frames(mm, latent_t):
    return sum(mm.FRAME_PER_TOKEN[k % 5] for k in range(int(latent_t)))


def _init_layout(mm, init, text_len, latent_t, latent_h, latent_w, audio_t,
                 keyframes=None, refs=None):
    layout = mm.PackedLayout.__new__(mm.PackedLayout)
    init(layout, text_len, latent_t, latent_h, latent_w, audio_t,
         keyframes=keyframes, refs=refs)
    return layout


def _emits_ref_audio(blk) -> bool:
    kind = blk.get("kind")
    rt = float(blk.get("ref_audio_t") or 0)
    if rt <= 0:
        return False
    return kind in ("audio", "video", "video_audio")


def _ref_audio_slot(refs, ref_index) -> int:
    slot = 0
    for i, blk in enumerate(refs or []):
        if i == ref_index:
            return slot
        if _emits_ref_audio(blk):
            slot += 1
    return slot


def _fix_audio(mm, layout, text_len, refs):
    marked = [(i, r) for i, r in enumerate(refs or []) if HC_AUDIO_END_FRAME in r]
    if not marked:
        return
    if len(marked) > 2:
        raise RuntimeError("h3_continuous: at most two timeline audio context blocks are supported")
    start = marked[0][0]
    expected = list(range(start, start + len(marked)))
    if [i for i, _ in marked] != expected or any(blk.get("kind") != "audio" for _, blk in marked):
        raise RuntimeError(
            "h3_continuous: timeline audio context must be consecutive audio ref blocks"
        )
    if start + len(marked) != len(refs):
        raise RuntimeError(
            "h3_continuous: timeline audio context must be the last H3 ref blocks"
        )
    ref_audio_segments = [(a, b) for a, b, kind in layout.segments if kind == "ref_audio"]
    if len(ref_audio_segments) < len(marked):
        raise RuntimeError("h3_continuous: PackedLayout produced no ref_audio segment")

    target_origin = float(text_len) + _ref_cursor_advance(mm, refs)
    for _slot, (ref_index, blk) in enumerate(marked):
        rt = int(blk.get("ref_audio_t", 0))
        if rt <= 0:
            continue
        seg_i = _ref_audio_slot(refs, ref_index)
        if seg_i < 0 or seg_i >= len(ref_audio_segments):
            raise RuntimeError("h3_continuous: timeline audio context has no matching ref_audio segment")
        a, b = ref_audio_segments[seg_i]
        if (b - a) != rt * 2:
            raise RuntimeError(
                f"h3_continuous: unexpected audio row count {b-a} for {rt} latent steps"
            )
        stock_end = float(text_len) + _ref_cursor_advance(mm, refs[:ref_index + 1])
        desired_end = target_origin + mm.FRAME_RESCALE * float(blk[HC_AUDIO_END_FRAME])
        layout.position_ids[a:b, 0] += desired_end - stock_end


def _run_self_test(mm, original_init, patched_init):
    """Validate the live ComfyUI layout before committing the wrapper."""
    import torch

    text_len, latent_t, lh, lw, audio_t = 7, 7, 22, 38, 16
    frame_count = _pixel_frames(mm, latent_t)
    # Current PackedLayout emits a cond segment only when the keyframe has a
    # video latent. Continuation keyframes are one latent step; match that.
    kf_latent = torch.empty(1, 1, 1)

    def kf(resolved, **extra):
        item = {"resolved_frame_index": resolved, "latent": kf_latent}
        item.update(extra)
        return item

    # Herrgotts endpoint coordinates must reproduce stock H3 exactly.
    stock_kf = [kf(0), kf(frame_count - 1)]
    custom_kf = [kf(0, **{HC_INDEX: 0}), kf(0, **{HC_INDEX: frame_count - 1})]
    s = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                     keyframes=stock_kf)
    c = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                     keyframes=custom_kf)
    _fix_keyframes(mm, c, text_len, custom_kf, None)
    if not torch.equal(s.position_ids, c.position_ids):
        raise RuntimeError("custom endpoint positions differ from stock H3")

    # The continuation Last Frame is also marked in v1.1.4, allowing the
    # wrapper to leave every unmarked stock graph untouched.
    refs = [{"kind": "audio", "ref_audio_t": 11, HC_AUDIO_END_FRAME: 5.0}]
    marked_last = [kf(0, **{HC_INDEX: frame_count - 1})]
    n = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                     keyframes=marked_last, refs=refs)
    _fix_keyframes(mm, n, text_len, marked_last, refs)
    cond_a = next(a for a, _, kind in n.segments if kind == "cond")
    video_a = next(a for a, _, kind in n.segments if kind == "video")
    expected_last = (
        float(n.position_ids[video_a, 0])
        + sum(mm._video_t_spans(latent_t))
        - mm.FRAME_RESCALE
    )
    if abs(float(n.position_ids[cond_a, 0]) - expected_last) > 1e-9:
        raise RuntimeError("marked Last Frame was not shifted onto the target timeline")

    canonical = [kf(0, **{HC_INDEX: p}) for p in (0, 1, 5, 9, 13, 17, 18, 22)]
    cr = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                      keyframes=canonical)
    _fix_keyframes(mm, cr, text_len, canonical, None)
    cts = [float(cr.position_ids[a, 0]) for a, _, kind in cr.segments if kind == "cond"]
    expected_cts = [float(text_len) + mm.FRAME_RESCALE * p for p in (0, 1, 5, 9, 13, 17, 18, 22)]
    if any(abs(a - b) > 1e-9 for a, b in zip(cts, expected_cts)):
        raise RuntimeError("canonical phase-aligned keyframe times changed")

    run = [kf(0, **{HC_INDEX: p}) for p in (0, 4, 8, 9, 13, 17)]
    r = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                     keyframes=run)
    _fix_keyframes(mm, r, text_len, run, None)
    ts = [float(r.position_ids[a, 0]) for a, _, kind in r.segments if kind == "cond"]
    if any(ts[i] >= ts[i + 1] for i in range(len(ts) - 1)):
        raise RuntimeError("interior keyframe times are not strictly increasing")

    two_refs = [
        {"kind": "audio", "ref_audio_t": 6, HC_AUDIO_END_FRAME: 5.0},
        {"kind": "audio", "ref_audio_t": 6, HC_AUDIO_END_FRAME: float(frame_count)},
    ]
    two_kf = [kf(0, **{HC_INDEX: 0}), kf(0, **{HC_INDEX: frame_count - 1})]
    loop_layout = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                               keyframes=two_kf, refs=two_refs)
    _fix_keyframes(mm, loop_layout, text_len, two_kf, two_refs)
    _fix_audio(mm, loop_layout, text_len, two_refs)
    audio_segs = [(a, b) for a, b, kind in loop_layout.segments if kind == "ref_audio"]
    if len(audio_segs) != 2:
        raise RuntimeError("expected two loop audio context segments")
    head_t = float(loop_layout.position_ids[audio_segs[0][1] - 1, 0])
    tail_t = float(loop_layout.position_ids[audio_segs[1][1] - 1, 0])
    if not (tail_t > head_t):
        raise RuntimeError("loop tail audio was not placed after head audio")

    # Stock Ref2VA order: persistent image refs, then timeline audio.
    img_then_audio = [
        {"kind": "image", "latent_h": 4, "latent_w": 4},
        {"kind": "audio", "ref_audio_t": 11, HC_AUDIO_END_FRAME: float(frame_count)},
    ]
    img_stock = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                             refs=img_then_audio)
    img_fixed = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                             refs=img_then_audio)
    _fix_audio(mm, img_fixed, text_len, img_then_audio)
    img_seg = next((a, b) for a, b, kind in img_stock.segments if kind == "ref_img")
    if not torch.equal(img_stock.position_ids[img_seg[0]:img_seg[1]],
                       img_fixed.position_ids[img_seg[0]:img_seg[1]]):
        raise RuntimeError("Ref2VA image ref positions were moved")
    if torch.equal(img_stock.position_ids, img_fixed.position_ids):
        raise RuntimeError("Ref2VA image-then-audio timeline audio was not remapped")

    # Persistent Ref2VA extras (video + unmarked audio) pack before timeline audio.
    extras_then_audio = [
        {"kind": "image", "latent_h": 4, "latent_w": 4},
        {"kind": "video_audio", "latent_t": 3, "latent_h": 4, "latent_w": 4, "ref_audio_t": 4},
        {"kind": "audio", "ref_audio_t": 5},
        {"kind": "audio", "ref_audio_t": 11, HC_AUDIO_END_FRAME: float(frame_count)},
    ]
    extras_stock = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                                refs=extras_then_audio)
    extras_fixed = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                                refs=extras_then_audio)
    _fix_audio(mm, extras_fixed, text_len, extras_then_audio)
    extra_audio_segs = [(a, b) for a, b, kind in extras_stock.segments if kind == "ref_audio"]
    if len(extra_audio_segs) != 3:
        raise RuntimeError("expected video soundtrack, builder audio, and timeline audio segments")
    if not torch.equal(extras_stock.position_ids[extra_audio_segs[0][0]:extra_audio_segs[0][1]],
                       extras_fixed.position_ids[extra_audio_segs[0][0]:extra_audio_segs[0][1]]):
        raise RuntimeError("video soundtrack ref positions were moved")
    if not torch.equal(extras_stock.position_ids[extra_audio_segs[1][0]:extra_audio_segs[1][1]],
                       extras_fixed.position_ids[extra_audio_segs[1][0]:extra_audio_segs[1][1]]):
        raise RuntimeError("unmarked builder audio ref positions were moved")
    if torch.equal(extras_stock.position_ids[extra_audio_segs[2][0]:extra_audio_segs[2][1]],
                   extras_fixed.position_ids[extra_audio_segs[2][0]:extra_audio_segs[2][1]]):
        raise RuntimeError("timeline audio after Ref2VA extras was not remapped")

    # Crucial v1.1.4 isolation test: unmarked keyframes+refs must be exactly the
    # stock layout even after the wrapper exists.
    unrelated_kf = [kf(frame_count - 1)]
    unrelated_refs = [{"kind": "audio", "ref_audio_t": 5}]
    a = _init_layout(mm, original_init, text_len, latent_t, lh, lw, audio_t,
                     keyframes=unrelated_kf, refs=unrelated_refs)
    b = _init_layout(mm, patched_init, text_len, latent_t, lh, lw, audio_t,
                     keyframes=unrelated_kf, refs=unrelated_refs)
    if not torch.equal(a.position_ids, b.position_ids) or a.segments != b.segments:
        raise RuntimeError("unmarked H3 graph changed under the continuation layout wrapper")


def install_layout_patch():
    global _ORIGINAL_INIT, _APPLIED, _MM
    if _APPLIED:
        return True

    status, err = get_layout_patch_status()
    if status is None:
        _LOG.error("h3_continuous: layout patch unavailable: %s", err)
        return False
    if status.state == "ours":
        _APPLIED = True
        _LOG.info("h3_continuous: compatible Herrgotts H3 layout patch is already active")
        return True
    if status.state == "foreign":
        _LOG.error(
            "h3_continuous: H3 runtime-patch conflict: %s already owns "
            "PackedLayout.__init__ (%s). Disable one H3 chaining pack and restart ComfyUI.",
            status.owner, status.module,
        )
        return False
    if status.state == "compatible":
        _LOG.info(
            "h3_continuous: wrapping compatible PackedLayout observer from %s",
            status.module,
        )

    mm = _import_mm()
    _MM = mm
    _ORIGINAL_INIT = mm.PackedLayout.__init__

    def patched_init(self, text_len, latent_t, latent_h, latent_w, audio_t,
                     keyframes=None, refs=None):
        _ORIGINAL_INIT(self, text_len, latent_t, latent_h, latent_w, audio_t,
                       keyframes=keyframes, refs=refs)
        has_ours_kf = bool(keyframes) and any(HC_INDEX in k for k in keyframes)
        has_ours_audio = bool(refs) and any(HC_AUDIO_END_FRAME in r for r in refs)
        if has_ours_kf:
            _fix_keyframes(mm, self, text_len, keyframes, refs)
        if has_ours_audio:
            _fix_audio(mm, self, text_len, refs)
        # No Herrgotts marker -> stock graph, returned exactly as built.

    setattr(patched_init, LAYOUT_PATCH_MARKER, True)

    try:
        _run_self_test(mm, _ORIGINAL_INIT, patched_init)
    except Exception as exc:
        _LOG.error(
            "h3_continuous: live ComfyUI layout self-test FAILED (%s). "
            "No layout patch was installed.", exc,
        )
        _ORIGINAL_INIT = None
        _MM = None
        return False

    mm.PackedLayout.__init__ = patched_init
    _APPLIED = True
    _LOG.info(
        "h3_continuous v1.2.1: lazy, marker-gated H3 layout patch installed on first continuation use"
    )
    return True


def uninstall_layout_patch_if_owned():
    """Best-effort rollback used only if paired patch installation fails."""
    global _ORIGINAL_INIT, _APPLIED, _MM
    if _MM is None or _ORIGINAL_INIT is None:
        return False
    current = getattr(getattr(_MM, "PackedLayout", None), "__init__", None)
    if current is None or not getattr(current, LAYOUT_PATCH_MARKER, False):
        return False
    _MM.PackedLayout.__init__ = _ORIGINAL_INIT
    _ORIGINAL_INIT = None
    _MM = None
    _APPLIED = False
    _LOG.info("h3_continuous: rolled back Herrgotts H3 layout patch")
    return True


def is_applied():
    return _APPLIED

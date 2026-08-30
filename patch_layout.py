"""In-place PackedLayout remaps for this suite's HC_INDEX / HC_AUDIO_END_FRAME markers.

Stock MiniMaxH3.extra_conds already concatenates keyframes + refs. Remaining work
is moving marked cond / ref_audio rows onto the target timeline. The per-MODEL
APPLY_MODEL wrapper calls ``adapt_marked_layout``; this module does not assign
PackedLayout.__init__.
"""

HC_INDEX = "h3_continuous_index"
HC_AUDIO_END_FRAME = "h3_continuous_audio_end_frame"
LAYOUT_ADAPT_MARKER = "_h3_studio_layout_adapted"


def _import_mm():
    import comfy.ldm.minimax.model as mm
    return mm


def graph_has_our_markers(keyframes, refs):
    return (
        bool(keyframes) and any(HC_INDEX in kf for kf in keyframes)
    ) or (
        bool(refs) and any(HC_AUDIO_END_FRAME in r for r in refs)
    )


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
    """Move only this pack's marked keyframes onto the target timeline."""
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


def adapt_marked_layout(payload):
    """Remap ``payload["layout"]`` once when this suite's markers are present.

    Unmarked payloads are left unchanged. APPLY_MODEL steps are idempotent via
    ``LAYOUT_ADAPT_MARKER`` on the layout object.
    """
    if not isinstance(payload, dict):
        return payload
    layout = payload.get("layout")
    if layout is None or getattr(layout, LAYOUT_ADAPT_MARKER, False):
        return payload
    keyframes = payload.get("keyframes")
    refs = payload.get("refs")
    has_kf = bool(keyframes) and any(HC_INDEX in kf for kf in keyframes)
    has_audio = bool(refs) and any(HC_AUDIO_END_FRAME in r for r in refs)
    if not has_kf and not has_audio:
        return payload
    mm = _import_mm()
    text_len = int(layout.signature[0])
    if has_kf:
        _fix_keyframes(mm, layout, text_len, keyframes, refs)
    if has_audio:
        _fix_audio(mm, layout, text_len, refs)
    setattr(layout, LAYOUT_ADAPT_MARKER, True)
    return payload


def _run_self_test(mm):
    """Validate adapt_marked_layout against a stock ComfyUI PackedLayout."""
    import torch

    text_len, latent_t, lh, lw, audio_t = 7, 7, 22, 38, 16
    frame_count = _pixel_frames(mm, latent_t)
    kf_latent = torch.empty(1, 1, 1)

    def kf(resolved, **extra):
        item = {"resolved_frame_index": resolved, "latent": kf_latent}
        item.update(extra)
        return item

    def packed(keyframes=None, refs=None):
        return mm.PackedLayout(
            text_len, latent_t, lh, lw, audio_t, keyframes=keyframes, refs=refs,
        )

    def adapt(layout, keyframes=None, refs=None):
        return adapt_marked_layout({
            "layout": layout, "keyframes": keyframes, "refs": refs,
        })

    # Marked endpoint coordinates must reproduce stock H3 exactly.
    stock_kf = [kf(0), kf(frame_count - 1)]
    custom_kf = [kf(0, **{HC_INDEX: 0}), kf(0, **{HC_INDEX: frame_count - 1})]
    s = packed(keyframes=stock_kf)
    c = packed(keyframes=custom_kf)
    adapt(c, custom_kf, None)
    if not torch.equal(s.position_ids, c.position_ids):
        raise RuntimeError("custom endpoint positions differ from stock H3")

    refs = [{"kind": "audio", "ref_audio_t": 11, HC_AUDIO_END_FRAME: 5.0}]
    marked_last = [kf(0, **{HC_INDEX: frame_count - 1})]
    n = packed(keyframes=marked_last, refs=refs)
    adapt(n, marked_last, refs)
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
    cr = packed(keyframes=canonical)
    adapt(cr, canonical, None)
    cts = [float(cr.position_ids[a, 0]) for a, _, kind in cr.segments if kind == "cond"]
    expected_cts = [float(text_len) + mm.FRAME_RESCALE * p for p in (0, 1, 5, 9, 13, 17, 18, 22)]
    if any(abs(a - b) > 1e-9 for a, b in zip(cts, expected_cts)):
        raise RuntimeError("canonical phase-aligned keyframe times changed")

    run = [kf(0, **{HC_INDEX: p}) for p in (0, 4, 8, 9, 13, 17)]
    r = packed(keyframes=run)
    adapt(r, run, None)
    ts = [float(r.position_ids[a, 0]) for a, _, kind in r.segments if kind == "cond"]
    if any(ts[i] >= ts[i + 1] for i in range(len(ts) - 1)):
        raise RuntimeError("interior keyframe times are not strictly increasing")

    two_refs = [
        {"kind": "audio", "ref_audio_t": 6, HC_AUDIO_END_FRAME: 5.0},
        {"kind": "audio", "ref_audio_t": 6, HC_AUDIO_END_FRAME: float(frame_count)},
    ]
    two_kf = [kf(0, **{HC_INDEX: 0}), kf(0, **{HC_INDEX: frame_count - 1})]
    loop_layout = packed(keyframes=two_kf, refs=two_refs)
    adapt(loop_layout, two_kf, two_refs)
    audio_segs = [(a, b) for a, b, kind in loop_layout.segments if kind == "ref_audio"]
    if len(audio_segs) != 2:
        raise RuntimeError("expected two loop audio context segments")
    head_t = float(loop_layout.position_ids[audio_segs[0][1] - 1, 0])
    tail_t = float(loop_layout.position_ids[audio_segs[1][1] - 1, 0])
    if not (tail_t > head_t):
        raise RuntimeError("loop tail audio was not placed after head audio")

    img_then_audio = [
        {"kind": "image", "latent_h": 4, "latent_w": 4},
        {"kind": "audio", "ref_audio_t": 11, HC_AUDIO_END_FRAME: float(frame_count)},
    ]
    img_stock = packed(refs=img_then_audio)
    img_fixed = packed(refs=img_then_audio)
    adapt(img_fixed, None, img_then_audio)
    img_seg = next((a, b) for a, b, kind in img_stock.segments if kind == "ref_img")
    if not torch.equal(img_stock.position_ids[img_seg[0]:img_seg[1]],
                       img_fixed.position_ids[img_seg[0]:img_seg[1]]):
        raise RuntimeError("Ref2VA image ref positions were moved")
    if torch.equal(img_stock.position_ids, img_fixed.position_ids):
        raise RuntimeError("Ref2VA image-then-audio timeline audio was not remapped")

    extras_then_audio = [
        {"kind": "image", "latent_h": 4, "latent_w": 4},
        {"kind": "video_audio", "latent_t": 3, "latent_h": 4, "latent_w": 4, "ref_audio_t": 4},
        {"kind": "audio", "ref_audio_t": 5},
        {"kind": "audio", "ref_audio_t": 11, HC_AUDIO_END_FRAME: float(frame_count)},
    ]
    extras_stock = packed(refs=extras_then_audio)
    extras_fixed = packed(refs=extras_then_audio)
    adapt(extras_fixed, None, extras_then_audio)
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

    unrelated_kf = [kf(frame_count - 1)]
    unrelated_refs = [{"kind": "audio", "ref_audio_t": 5}]
    a = packed(keyframes=unrelated_kf, refs=unrelated_refs)
    b = packed(keyframes=unrelated_kf, refs=unrelated_refs)
    adapt(b, unrelated_kf, unrelated_refs)
    if not torch.equal(a.position_ids, b.position_ids) or a.segments != b.segments:
        raise RuntimeError("unmarked H3 graph changed under adapt_marked_layout")

    adapt(c, custom_kf, None)
    if not getattr(c, LAYOUT_ADAPT_MARKER, False):
        raise RuntimeError("adapted layout was not marked for idempotent APPLY_MODEL steps")

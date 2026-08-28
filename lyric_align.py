"""Line-level lyric clocks from known text + song audio (no Parakeet / WhisperX)."""

from __future__ import annotations

import gc
import re

try:
    from .lyric_timing import (
        align_lyric_text, complete_line_words, format_lrc, is_instrumental_marker,
        parse_timestamped_lyrics, split_plain_lyric_lines, _resolved_end,
    )
    from .prompter_llama import unload_comfy_models
except ImportError:
    from lyric_timing import (
        align_lyric_text, complete_line_words, format_lrc, is_instrumental_marker,
        parse_timestamped_lyrics, split_plain_lyric_lines, _resolved_end,
    )
    from prompter_llama import unload_comfy_models

_WORD = re.compile(r"[a-z0-9']+", re.I)
ALIGN_SR = 16000
REFINE_PAD = 0.12


def _line_ctc_words(line: str) -> list[str]:
    if is_instrumental_marker(line):
        return []
    out = []
    for word in _WORD.findall(align_lyric_text(line)):
        letters = "".join(c for c in word.upper() if c.isalpha())
        if letters:
            out.append(letters)
    return out


def lines_from_aligned_words(user_lines, words) -> list[dict]:
    """Assign aligned word clocks to user lines by token order. Keep original text."""
    items = list(user_lines or [])
    clocks = [dict(w) for w in (words or []) if str(w.get("text", "")).strip()]
    counts = [_line_ctc_words(ln) for ln in items]
    out = []
    i = 0
    for line, toks in zip(items, counts):
        n = len(toks)
        if n <= 0:
            out.append({"start": None, "end": None, "text": line})
            continue
        take = clocks[i:i + n]
        i += n
        if not take:
            out.append({"start": None, "end": None, "text": line})
            continue
        out.append({
            "start": float(take[0]["start"]),
            "end": float(take[-1]["end"]),
            "text": line,
        })
    if i < len(clocks):
        last = next((ln for ln in reversed(out) if ln["end"] is not None), None)
        if last is not None:
            last["end"] = float(clocks[-1]["end"])
    _fill_missing_line_times(out, clocks)
    for ln in out:
        if ln["end"] <= ln["start"]:
            ln["end"] = ln["start"] + 0.05
    return out


def _fill_missing_line_times(lines, words) -> None:
    if not lines:
        return
    if all(ln["start"] is None for ln in lines):
        if not words:
            raise ValueError("h3_studio: lyric align produced no word clocks")
        t0 = float(words[0]["start"])
        t1 = max(t0 + 0.05, float(words[-1]["end"]))
        step = (t1 - t0) / len(lines)
        for i, ln in enumerate(lines):
            ln["start"] = t0 + i * step
            ln["end"] = t0 + (i + 1) * step
        return
    for i, ln in enumerate(lines):
        if ln["start"] is not None:
            continue
        prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j]["start"] is not None), None)
        nxt = next((lines[j] for j in range(i + 1, len(lines)) if lines[j]["start"] is not None), None)
        if prev is not None and nxt is not None:
            start = float(prev["end"])
            end = float(nxt["start"])
            if end <= start:
                end = start + 0.05
            ln["start"] = start
            ln["end"] = end
        elif prev is not None:
            ln["start"] = float(prev["end"])
            ln["end"] = ln["start"] + 0.3
        elif nxt is not None:
            ln["end"] = float(nxt["start"])
            ln["start"] = max(0.0, ln["end"] - 0.3)
        else:
            ln["start"] = 0.0
            ln["end"] = 0.3


def resolve_timed_lyrics(audio_path, lyrics, waveform=None, sample_rate=None) -> str:
    raw = str(lyrics or "")
    plain = split_plain_lyric_lines(raw)
    if not plain:
        raise ValueError("h3_studio: lyrics are required")
    if parse_timestamped_lyrics(raw):
        return raw
    words = align_plain_lyrics(audio_path, plain, waveform=waveform, sample_rate=sample_rate)
    return format_lrc(lines_from_aligned_words(plain, words))


def _token_chars(text: str) -> list[str]:
    tokens = []
    for i, word in enumerate(_line_ctc_words(text)):
        if i:
            tokens.append("|")
        tokens.extend(word)
    return tokens


def _release_aligner():
    import torch

    gc.collect()
    try:
        import comfy.model_management as model_management
        model_management.soft_empty_cache(force=True)
    except (ImportError, AttributeError):
        pass
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _load_wav2vec2(device):
    import torchaudio

    bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
    model = bundle.get_model().to(device)
    model.eval()
    return model, bundle.get_labels()


def _ctc_words_from_wav(model, labels, wav_16k, token_chars, device) -> list[dict]:
    import torch
    from torchaudio.functional import forced_align, merge_tokens

    dictionary = {c: i for i, c in enumerate(labels)}
    ids = [dictionary[c] for c in token_chars if c in dictionary]
    if not ids:
        raise ValueError("h3_studio: lyrics have no alignable words")
    batch = wav_16k.unsqueeze(0).to(device)
    try:
        logits, _ = model(batch)
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            raise RuntimeError(
                "h3_studio: lyric align ran out of VRAM. Unload H3 and retry."
            ) from exc
        raise
    log_probs = torch.log_softmax(logits, dim=-1).cpu()
    targets = torch.tensor([ids], dtype=torch.int64)
    try:
        paths, scores = forced_align(log_probs, targets, blank=0)
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            raise RuntimeError(
                "h3_studio: lyric align ran out of VRAM. Unload H3 and retry."
            ) from exc
        raise RuntimeError(f"h3_studio: lyric align failed ({exc})") from exc
    spans = merge_tokens(paths[0], scores[0], blank=0)
    frame_seconds = float(wav_16k.numel()) / float(max(1, log_probs.size(1))) / float(ALIGN_SR)
    return _spans_to_words(spans, labels, frame_seconds)


def _clamp_words(words, lo: float, hi: float, offset: float) -> list[dict]:
    out = []
    for word in words or []:
        start = max(lo, min(hi, float(word["start"]) + offset))
        end = max(lo, min(hi, float(word["end"]) + offset))
        if end <= start:
            continue
        item = dict(word)
        item["start"] = start
        item["end"] = end
        chars = []
        for ch in item.get("chars") or []:
            c0 = max(lo, min(hi, float(ch["start"]) + offset))
            c1 = max(lo, min(hi, float(ch["end"]) + offset))
            if c1 > c0:
                chars.append({**ch, "start": c0, "end": c1})
        if chars:
            item["chars"] = chars
        elif "chars" in item:
            del item["chars"]
        out.append(item)
    return out


def apply_line_refine(line, words, song_seconds: float) -> dict:
    """Keep confirm stamps and text; attach clocks then complete_line_words."""
    out = dict(line)
    out["start"] = float(out["start"])
    out["end"] = _resolved_end(out, song_seconds)
    text = str(out.get("text") or "").strip()
    out["text"] = text
    if is_instrumental_marker(text):
        out["text"] = "<instrumental>"
        out["words"] = []
        return out
    if words:
        out["words"] = list(words)
    else:
        out.pop("words", None)
    return complete_line_words(out)


def refine_confirm_lyrics(waveform, sample_rate, confirm_text, song_seconds=None) -> list[dict]:
    """Forced-align each locked confirm line. Stamps stay put."""
    parsed = parse_timestamped_lyrics(confirm_text)
    if not parsed:
        raise ValueError("h3_studio: time lyrics on Load Song before the Local Prompter")
    import torch

    wav = _mono_16k(None, waveform, sample_rate)
    duration = float(wav.numel()) / float(ALIGN_SR)
    if song_seconds is None:
        song_seconds = duration
    unload_comfy_models()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = None
    try:
        model, labels = _load_wav2vec2(device)
        out = []
        for line in parsed:
            item = dict(line)
            item["end"] = _resolved_end(item, song_seconds)
            text = str(item.get("text") or "").strip()
            item["text"] = text
            if is_instrumental_marker(text):
                out.append(apply_line_refine(item, None, song_seconds))
                continue
            tokens = _token_chars(text)
            words = None
            if tokens:
                lo = float(item["start"])
                hi = float(item["end"])
                pad_lo = max(0.0, lo - REFINE_PAD)
                pad_hi = min(duration, hi + REFINE_PAD)
                a = int(round(pad_lo * ALIGN_SR))
                b = max(a + 1, int(round(pad_hi * ALIGN_SR)))
                try:
                    aligned = _ctc_words_from_wav(
                        model, labels, wav[a:b].contiguous(), tokens, device,
                    )
                    words = _clamp_words(aligned, lo, hi, offset=pad_lo)
                except ValueError:
                    words = None
                except RuntimeError as exc:
                    if "out of memory" in str(exc).lower():
                        raise
                    words = None
            out.append(apply_line_refine(item, words, song_seconds))
        return out
    finally:
        if model is not None:
            del model
        _release_aligner()


def align_plain_lyrics(audio_path, lines, waveform=None, sample_rate=None) -> list[dict]:
    tokens = []
    for line in lines:
        chars = _token_chars(line)
        if not chars:
            continue
        if tokens:
            tokens.append("|")
        tokens.extend(chars)
    if not tokens:
        raise ValueError("h3_studio: lyrics have no alignable words")
    unload_comfy_models()
    import torch

    wav = _mono_16k(audio_path, waveform, sample_rate)
    if wav.numel() < ALIGN_SR // 10:
        raise ValueError("h3_studio: song audio is too short to time lyrics")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = None
    try:
        model, labels = _load_wav2vec2(device)
        return _ctc_words_from_wav(model, labels, wav, tokens, device)
    finally:
        if model is not None:
            del model
        _release_aligner()


def _char_clock(sp, frame_seconds: float) -> tuple[float, float]:
    t0 = float(int(sp.start)) * frame_seconds
    t1 = float(int(sp.end)) * frame_seconds
    if t1 <= t0:
        t1 = t0 + frame_seconds
    return t0, t1


def _flush_word(letters, char_clocks, frame_seconds: float) -> dict:
    t0 = float(char_clocks[0]["start"])
    t1 = float(char_clocks[-1]["end"])
    word = {
        "start": t0,
        "end": t1 if t1 > t0 else t0 + frame_seconds,
        "text": "".join(letters),
        "chars": char_clocks,
    }
    return word


def _spans_to_words(spans, labels, frame_seconds: float) -> list[dict]:
    words = []
    letters = []
    char_clocks = []
    for sp in spans or []:
        tok = labels[int(sp.token)]
        if tok == "|":
            if letters:
                words.append(_flush_word(letters, char_clocks, frame_seconds))
                letters = []
                char_clocks = []
            continue
        if tok == "-":
            continue
        c0, c1 = _char_clock(sp, frame_seconds)
        letters.append(tok)
        char_clocks.append({"char": tok, "start": c0, "end": c1})
    if letters:
        words.append(_flush_word(letters, char_clocks, frame_seconds))
    if not words:
        raise ValueError("h3_studio: lyric align produced no word clocks")
    return words


def _mono_16k(audio_path, waveform, sample_rate):
    import torch
    import torchaudio

    if waveform is not None:
        wav = waveform
        if not isinstance(wav, torch.Tensor):
            wav = torch.as_tensor(wav)
        wav = wav.detach().float().cpu()
        if wav.dim() == 3:
            wav = wav[0]
        if wav.dim() == 2:
            wav = wav.mean(dim=0)
        sr = int(sample_rate or ALIGN_SR)
    else:
        path = str(audio_path or "").strip()
        if not path:
            raise ValueError("h3_studio: song audio is required to time lyrics")
        wav, sr = _load_audio(path)
        if wav.dim() == 2:
            wav = wav.mean(dim=0)
    if sr != ALIGN_SR:
        wav = torchaudio.functional.resample(wav.unsqueeze(0), sr, ALIGN_SR).squeeze(0)
    return wav.contiguous()


def _pcm_float(wav):
    import torch

    if wav.dtype.is_floating_point:
        return wav.float()
    if wav.dtype == torch.int16:
        return wav.float() / (2 ** 15)
    if wav.dtype == torch.int32:
        return wav.float() / (2 ** 31)
    return wav.float()


def _load_audio(path: str):
    import torch
    import torchaudio

    try:
        wav, sr = torchaudio.load(path)
        return _pcm_float(wav), int(sr)
    except Exception:
        pass
    import av

    with av.open(path) as container:
        if not container.streams.audio:
            raise ValueError(f"h3_studio: no audio stream in {path}")
        stream = container.streams.audio[0]
        sample_rate = int(stream.codec_context.sample_rate)
        channels = int(stream.channels or 1)
        frames = []
        for frame in container.decode(streams=stream.index):
            buf = torch.from_numpy(frame.to_ndarray())
            if buf.ndim == 1:
                buf = buf.unsqueeze(0)
            if buf.shape[0] != channels:
                buf = buf.view(-1, channels).t()
            frames.append(_pcm_float(buf))
        if not frames:
            raise ValueError(f"h3_studio: no audio frames in {path}")
        wav = torch.cat(frames, dim=1)
    return wav, sample_rate

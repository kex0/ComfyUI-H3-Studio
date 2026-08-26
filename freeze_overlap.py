"""Copy previous video tokens into a Continue clip's head and mask them out of denoising."""

import torch


def freeze_video_head(video, source_head, audio, soft_steps=2):
    """Paste ``source_head`` onto the start of ``video`` and build denoise masks.

    Denoise mask convention: 1 = sample, 0 = keep. Audio is fully sampled.
    The last ``soft_steps`` frozen video steps ramp toward denoise so the first
    kept frames are not a hard inpaint edge. At least one step stays hard-frozen.
    Returns ``(video, audio, video_mask, audio_mask)``. Masks are ``None`` when
    the head would cover the whole clip or is empty.
    """
    ctx = int(source_head.shape[2])
    latent_t = int(video.shape[2])
    if ctx <= 0 or ctx >= latent_t:
        return video, audio, None, None
    if tuple(source_head.shape[-2:]) != tuple(video.shape[-2:]):
        raise ValueError(
            "h3_continuous: overlap freeze requires identical spatial latent grids "
            f"(source {tuple(source_head.shape[-2:])}, target {tuple(video.shape[-2:])})"
        )
    video = video.clone()
    video[:, :, :ctx] = source_head.to(device=video.device, dtype=video.dtype)
    batch = int(video.shape[0])
    v_mask = torch.ones((batch, 1, latent_t, 1, 1), device=video.device, dtype=torch.float32)
    v_mask[:, :, :ctx] = 0
    soft = min(max(int(soft_steps), 0), ctx - 1)
    if soft > 0:
        ramp = torch.arange(1, soft + 1, device=v_mask.device, dtype=v_mask.dtype) / float(soft + 1)
        v_mask[:, :, ctx - soft:ctx, 0, 0] = ramp.view(1, 1, soft)
    a_mask = torch.ones(
        (int(audio.shape[0]), 1, 1, int(audio.shape[-1])),
        device=audio.device,
        dtype=torch.float32,
    )
    return video, audio, v_mask, a_mask


def copy_song_audio(audio, song, lock):
    """Paste the song latent into the target audio stream.

    Denoise mask convention: 1 = sample, 0 = keep. ``lock`` 0 is a no-op;
    1 copies the song and does not denoise audio. Song time is padded (repeat
    last step) or cropped to the clip's audio length — empty-latent ``round``
    and Audio VAE hop can disagree by one step on some H3 grids.
    Returns ``(audio, a_mask)``.
    """
    amount = min(max(float(lock), 0.0), 1.0)
    if song is None or amount <= 0.0:
        return audio, None
    if song.ndim == 3:
        song = song.unsqueeze(0)
    if tuple(song.shape[1:3]) != tuple(audio.shape[1:3]):
        raise ValueError(
            "h3_continuous: song audio latent shape "
            f"{tuple(song.shape)} does not match clip audio {tuple(audio.shape)}"
        )
    fitted = song.to(device=audio.device, dtype=audio.dtype)
    if int(fitted.shape[0]) == 1 and int(audio.shape[0]) != 1:
        fitted = fitted.expand(int(audio.shape[0]), *fitted.shape[1:])
    want = int(audio.shape[-1])
    have = int(fitted.shape[-1])
    if have < want:
        pad = fitted[..., -1:].expand(*fitted.shape[:-1], want - have)
        fitted = torch.cat((fitted, pad), dim=-1)
    elif have > want:
        fitted = fitted[..., :want]
    audio = fitted.contiguous().clone()
    a_mask = torch.full(
        (int(audio.shape[0]), 1, 1, int(audio.shape[-1])),
        1.0 - amount,
        device=audio.device,
        dtype=torch.float32,
    )
    return audio, a_mask

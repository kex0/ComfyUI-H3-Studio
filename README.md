# ComfyUI-H3-Studio

With this extension you can create videos of any length with MiniMax H3 in ComfyUI, including seamlessly looping videos and full music videos.

Install the pack, then look under category **H3 Studio**. Typical path: **Builder** (plus **Lyrics Timer** for a song) → **Local Prompter** or an [agent skill](skills/README.md) → **Auto Chain** or **Music Video** → optional clip fix and **Face Refine**.

<details>

<summary>EXAMPLE VIDEOS</summary>

### No postprocessing, raw output from the nodes (slightly compressed)

https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/autochain-loop.mp4

https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-poprock-1.mp4

https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-poprock-2.mp4

https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-cloud-1.mp4

https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-cloud-2.mp4

</details>

## Builder

![H3 Studio Builder](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/builder.webp)

Collects models, pictures, videos, and audio for the other H3 Studio nodes. Drop files on the list, or wire IMAGE / VIDEO / AUDIO into **Media**. Connect patched H3 models to `model_1` (and further model sockets). Switch **Auto Chain** or **Music Video**, write a short Plan, then wire `pack` into Local Prompter, Auto Chain, or Music Video.

Music Video needs a song and timed lyrics from Lyrics Timer. Builder audio refs are unused in that mode; the song is `<Audio 1>`. Auto Chain can cite Builder audio as `<Audio 1>`.

Or click **Copy skill command** and paste into an agent that has `/prompt-minimax-h3-auto_chain` or `/prompt-minimax-h3-music-video`.

![Builder image crop](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/builder-image-edit.webp)

![Builder video trim](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/builder-video-edit.webp)

Video and audio open a trim timeline. Clip count follows the Builder **segments** widget. Shift + drag moves all segments at once.

![Builder audio trim](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/builder-audio-edit.webp)

## Lyrics Timer

![Lyrics Timer](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/lyrics-timer.webp)

Stamp lyric times onto your song. Paste lyrics that match the vocal as closely as possible, upload the audio, then press **Time lyrics**. Queue this node **without H3 loaded**; the first run downloads torchaudio wav2vec2 (`WAV2VEC2_ASR_BASE_960H`). Already-stamped confirm LRC (`[start-end]`) is not overwritten.

**Timeline:** drag the A/B handles to a phrase, then **Add A–B**. Click a line to select it. **Live Edit** rewrites that line's times as you drag. Double-click a line to edit the words. Play A–B to check the match.

**Lyric syntax:** `~word~` is a held syllable. `<instrumental>` is a rest with no singing (own line).

Wire `song` and `lyrics` into Builder (Music Video mode). The [music-video skill](skills/README.md) posts the same wav2vec2 refine to `/h3_studio_song/plan` (letter clocks + CLIP skeleton).

### WARNING LOUD AUDIO
https://github.com/user-attachments/assets/5b6bdb6f-00fc-4bc7-9d03-ddbe2f624ef4


## Local Prompter

![Local Prompter](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/local-prompter.webp)

Writes Auto Chain or Music Video prompts on your machine from the Builder pack. Keep the Plan short; the local model expands it into timed, filmable clip bodies.

1. Wire Builder into this node (put **Clip Prompt Fixer** in between to rewrite a few clips).
2. Pick a GGUF and queue **without H3 loaded**. The node unloads Comfy models, starts `llama-server` on `127.0.0.1`, generates each clip, then kills the server.
3. Copy `prompts` into Auto Chain or Music Video.

The node does not bundle llama.cpp. Install the official binaries, then either drop the catalog GGUF in `ComfyUI/models/LLM/` or enable `allow_download` once (~16 GB from Hugging Face). You can also pick a scanned `local:…gguf` or **Local GGUF** plus `gguf_path`. Queue the video graph after the prompter finishes.

Music Video packs need timed lyrics from Lyrics Timer first. Untimed lyrics fail until you Time lyrics. Local Prompter letter-refines locked confirm lines, plans CLIP windows from the song length, and writes `mode: music_video` with `time:` / `lyrics:` locked.

### Install llama.cpp

Ask your AI agent to install llama.cpp for this node, or follow the steps below.

Download a release from [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/releases). Nightly tags (`b#####`) ship the platform zips; `v0.3.0`-style tags may only point at the latest nightly.

**Windows NVIDIA (recommended location for this node):** extract the CUDA zip **and** the matching CUDA runtime zip into `ComfyUI/user/llama.cpp/` so `llama-server.exe`, `llama-cli.exe`, and the CUDA DLLs sit in that folder. The node finds them there without putting them on PATH. Restart ComfyUI afterward.

| GPU / toolchain | llama.cpp zip | CUDA runtime zip |
|---|---|---|
| RTX 40/50, CUDA 13 | `llama-b*-bin-win-cuda-13.3-x64.zip` | `cudart-llama-bin-win-cuda-13.3-x64.zip` |
| CUDA 12 | `llama-b*-bin-win-cuda-12.4-x64.zip` | `cudart-llama-bin-win-cuda-12.4-x64.zip` |
| CPU only | `llama-b*-bin-win-cpu-x64.zip` | (none) |

Linux/macOS: extract the matching `.tar.gz` from the same release and put `llama-server` / `llama-cli` on PATH, or under `ComfyUI/user/`.

Multi-clip jobs need `llama-server`. A single clip can fall back to `llama-cli`. Optional overrides: the node's `llama_server` widget, or `H3_STUDIO_LLAMA_SERVER` / `H3_STUDIO_LLAMA_CLI`.

## Auto Chain

![Auto Chain](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/auto-chain.webp)

Generates a multi-clip video from Builder refs (not lipsync-to-song). Each clip continues from the last, so length is N × clip duration rather than one H3 window.

1. Builder in **Auto Chain** mode.
2. Wire that pack here. Connect CLIP, video VAE, audio VAE, sampler, sigmas, and noise.
3. Paste the prompt from Local Prompter (or `/prompt-minimax-h3-auto_chain`).
4. Queue.

Turn on **seamless loop** for a Loop clip that returns to the start. Keep `latent_prefix` if you might Clip-Fix later. `IMAGE` is the temp PNG sequence.

## Music Video

![Music Video, single prompt](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-video-single-prompt.webp)

Generates a lipsync video that follows the song. Clip count and max duration come from the prompt (or duration from the pack). `<Audio 1>` is always the song slice; extra Builder audios (if you cited them) are `<Audio 2>` / `<Audio 3>`.

1. Builder in **Music Video** mode, with song + timed lyrics.
2. Wire that pack here. Connect CLIP, video VAE, audio VAE, sampler, sigmas, and noise.
3. Paste the prompt from Local Prompter (or `/prompt-minimax-h3-music-video`).
4. Queue.

![Music Video, one prompt per clip](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-video-one-prompt-per-clip.webp)

**Single prompt** / **One prompt per clip** only changes how the prompt is shown. It does not affect generation. Per-clip layout shows duration and segments widgets. Keep `latent_prefix` if you might Clip-Fix later. Face Refine uses the PNG folder printed in `chain_info`.

## Clip Prompt Fixer

![Clip Prompt Fixer](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/clip-prompt-fixer.webp)

Rewrites a few clips in an existing Music Video or Auto Chain prompt. Lyrics, `time:`, `audio:`, and `slice:` stay locked.

1. Wire Builder into this node.
2. Paste the full document (or just the `## Clip` sections to change).
3. Set `clip_index` (`11-12` or `11,12`).
4. Write a Plan of what should change.

Then either wire this node into **Local Prompter** and queue, or click **Copy skill command** and paste `/prompt-minimax-h3-clip-fix` into an agent. The command includes the plan, the selected clips, and one previous and one following clip. Local Prompter output is the selected `## Clip` sections only (no `H3 Studio prompt` header, not neighbor clips). Neighbor clips in the seed are still used as continue-from / land-into context while writing.

![Clip Prompt Fixer into Local Prompter](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/clip-prompt-fixer-local-prompter-output.webp)

## Auto Chain Clip Fixer

![Auto Chain Clip Fixer](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/auto-chain-clip-fixer.webp)

Re-renders chosen clips of an existing Auto Chain, then restitches the chain. Same sockets as Auto Chain plus `clip_index`, including the same Single prompt / One prompt per clip editor. Duration, clip count, and loop are read from the prompt (and pack / on-disk chain).

1. Use the same models / VAE / sampler as the original run.
2. Set `latent_prefix` to that chain's folder.
3. Paste the rewritten clips (or the full document) and set `clip_index`.
4. Queue.

Empty `clip_index` regenerates every `## Clip` in the paste. Overwritten slots are copied into `backup_YYYYMMDD_HHMMSS/` next to the prefix first. Clip `i` continues from the new `i-1` if that slot was just written, else from the on-disk `i-1`; it packs the on-disk `i+1` opening as end context only when `i+1` is **not** also being rewritten. If Finish is selected and a Loop clip exists, Loop is regenerated too. These nodes need H3 loaded, unlike Local Prompter.

## Music Video Clip Fixer

![Music Video Clip Fixer](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-video-clip-fixer.webp)

Same idea as Auto Chain Clip Fixer for a Music Video chain: same sockets as Music Video plus `clip_index`. No duration / clip-count widgets; those come from the pasted `## Clip` sections and saved latents. Same backup / sandwich / full restitch.

## Face Refine Video

![Face Refine Video](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/face-refine-video.webp)

Sharpens small faces on a finished clip. Close-ups are left alone.

1. Set `video_path` to the PNG folder from Music Video / Auto Chain `chain_info`, or to an MP4.
2. Keep the default face prompt — do not paste lyrics or the scene.
3. Connect model, CLIP, VAEs, sampler, sigmas, and noise.
4. Queue after the video is done.

Turn on **seamless loop** if the clip should loop. Faces that need refine at both ends are generated as one wrap-around pass and split back onto the start and end. `IMAGE` is the refined temp PNG sequence. `AUDIO` is the wired song, or the soundtrack from that video (MP4, or a PNG folder next to that MP4). Each run prints a disk/RAM banner first.

https://github.com/user-attachments/assets/f02400eb-04b1-42c8-b528-3060dd233c82

## Prompt editor

Auto Chain and Music Video share one prompt format: `H3 Studio prompt` then `## Clip` sections (Music Video also has `time:` / `lyrics:` per clip). Each clip has its own `subject_definitions`; those tags are the dump stills/videos/audio that clip loads.

Type `@` for the chip autofill. Only media the Builder currently supplies appear (unused, deleted, and out-of-range segments are omitted). Video/audio chips show numbered buttons when the node has more than one segment (`<Video 1:2>` selects slice 2).

![Chip autofill](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/autofill-chip-picker.webp)

Right-click a chip to preview, pick a segment, **Replace this**, **Replace all**, or **Remove**.

![Chip context menu](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/chip-context-menu.webp)

Type `#` to create a dialogue block (`<d>[English] ...</d>` by default); click the flag to change language. Enter leaves the block, Shift+Enter inserts a line break inside it.

![Chip prompt](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/builder-prompt-example.webp)

The raw view is the same document as text (`<Picture 1>` instead of chips).

![Raw prompt](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/builder-raw-prompt-example.webp)

## Help

Every H3 Studio node has a **?** in the header. That guide is the short version of the steps above.

![Question-mark node help](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/question-mark-help.webp)

## Agent skills

Copy the folders in [`skills/`](skills/README.md) into your agent (Cursor, Claude Code, and similar). Music Video **Copy skill command** includes the Comfy origin, song path, and timed lyrics. The music-video skill does not download torch; it reuses this Comfy install.

## Dependencies

- ComfyUI MiniMax H3 (stock nodes, not a custom pack)
- llama.cpp (`llama-server`) for Local Prompter — see [Install llama.cpp](#install-llamacpp)
- `ultralytics`, `scipy`, `insightface` for Face Refine
- MaskVidExperiments is optional (crop-teleport packing). Without it, Face Refine falls back to gaussian crop follow

## Thanks for the inspiration
- https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy
- https://github.com/ukr8b3g-cmyk/ComfyUI-H3-Continuum
- https://github.com/Carasibana/ComfyUI-H3-FaceRefine

## License

[MIT](LICENSE).

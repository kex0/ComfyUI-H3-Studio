# ComfyUI-H3-Studio

Standalone ComfyUI nodes for MiniMax H3 music videos: chain generation, lipsync to a song, lossless PNG handoff, and face refine. This pack does not import Herrgotts or ComfyUI-H3-FaceRefine.

## Nodes

| Node | What it does |
|---|---|
| **H3 Studio - Music Video** | Generate clips to cover a source song from one H3 Studio prompt document, using a Builder pack for models, refs, and the song. One H3 Studio prompt covers every clip, or switch to one prompt per clip. Clip count and max duration come from the prompt (or duration from the pack). Per-clip mode shows duration and segments widgets. `<Audio 1>` stays the song slice; Builder audios are `<Audio 2>` / `<Audio 3>`. `song_audio_lock` defaults to 0.9. `IMAGE` is the temp PNG sequence. |
| **H3 Studio - Auto Chain** | N-clip Ref2VA Start / Continue / Finish stitch from a Builder pack. One H3 Studio prompt document covers every clip, or switch to one prompt per clip. Duration, clip count, and loop come from the prompt (or duration/clip count from the pack). Per-clip `<Model N>` / `<Picture N>` / `<Video N>` / `<Audio N>` select a subset. Optional seamless loop. Same temp PNG sequence as `IMAGE`. |
| **H3 Studio - Builder** | Drop images, videos, and audio, or wire several IMAGE/VIDEO/AUDIO outputs to the `Media` socket; connect patched H3 models. Switch Auto Chain / Music Video (Music Video disables audio refs and shows song plus lyrics). Outputs a pack. Plan, max clip duration, clip count, loop, song, and lyrics travel with the pack. |
| **H3 Studio - Clip Prompt Fixer** | Paste a Music Video (or Auto Chain) prompt, pick clip indices, and write a fix Plan. Passes a `clip_fix` pack to Local Prompter so only those clip bodies are rewritten. Lyrics, `time:`, `audio:`, and `slice:` stay locked. **Copy skill command** copies `/prompt-minimax-h3-clip-fix` with the plan, the selected clips, and one previous and one following clip. Local Prompter output is the selected `## Clip` sections only (no document header). |
| **H3 Studio - Music Video Clip Fixer** | Same sockets as Music Video plus `clip_index`, including the same Single prompt / One prompt per clip editor. No duration / clip-count widgets: those come from the pasted `## Clip` sections (and saved latents). Regenerates those on-disk clips under `latent_prefix` (backs them up first), sandwiches previous + next latents when the next slot is kept, and restitches the full chain. Empty `clip_index` regenerates every `## Clip` in `prompt`. |
| **H3 Studio - Auto Chain Clip Fixer** | Same sockets as Auto Chain plus `clip_index`, including the same Single prompt / One prompt per clip editor. Duration, clip count, and loop are read from the prompt (and pack / on-disk chain). Same backup / sandwich / full restitch. If Finish is selected and a Loop clip exists, the Loop clip is regenerated too. |
| **H3 Studio - Face Refine Video** | Face-refine a finished clip. Set `video_path` to the Music Video PNG folder from `chain_info`. `IMAGE` is the refined temp PNG sequence. |
| **H3 Studio - Lyrics Timer** | Load AUDIO as `song`. Paste required lyrics (untimed lines or confirm LRC). Untimed lines are timed per line with wav2vec2 (Time lyrics or first queue, without H3 loaded). Already-stamped LRC is not overwritten. Edit stamps on the timeline. |
| **H3 Studio - Local Prompter** | Start local llama.cpp on a catalog or local GGUF. Auto Chain pack → Auto Chain prompt. Music Video pack (song + timed lyrics) → letter-refine, CLIP windows, Music Video prompt. Then stop the server. Inventory and plan come from the pack. |

Category: **H3 Studio**.

Class names (`H3StudioMusicVideo`, `H3StudioAutoChain`, `H3StudioMusicVideoClipFixer`, `H3StudioAutoChainClipFixer`, `H3StudioBuilder`, `H3StudioClipPromptFixer`, `H3StudioFaceRefineVideo`, `H3StudioLoadSong`, `H3StudioLocalInfinitePrompter`) are unique, so this pack can sit next to Herrgotts / Face Refine without node-id collisions. Continuation runtime hooks reuse Herrgotts patch markers so both packs do not fight over PackedLayout.

## Local Prompter

The node does not bundle llama.cpp. Install the official binaries, then either drop the catalog GGUF in `ComfyUI/models/LLM/` or enable `allow_download` once (~16 GB from Hugging Face). You can also pick a scanned `local:…gguf` or **Local GGUF** plus `gguf_path`.

Builder (Auto Chain mode) → `pack` → Local Prompter. Duration, clip count, loop, and plan come from the Builder pack.

Builder (Music Video mode) with Lyrics Timer `song` + timed `lyrics` → `pack` → Local Prompter. It letter-refines locked confirm lines with wav2vec2, plans CLIP windows from the song length, llama-fills Ref2VA bodies, and writes `mode: music_video` with `time:` / `lyrics:` locked. Untimed lyrics fail until you Time lyrics on Lyrics Timer.

To rewrite a few clips in an existing Music Video prompt without regenerating the rest: Builder → **Clip Prompt Fixer** → Local Prompter. Paste the full document (or just the `## Clip` sections to change), set `clip_index` (`11-12` or `11,12`), and write a Plan. Local Prompter revises those six-section bodies only and **outputs only the selected `## Clip` sections** (no `H3 Studio prompt` header, not neighbor clips). Lyrics and timings stay locked. Neighbor clips in the seed are still used as continue-from / land-into context while writing. **Copy skill command** copies `/prompt-minimax-h3-clip-fix` plus clip index, plan, Builder dump, the selected clips, and one previous and one following clip so you can paste it into an agent with the matching skill instead of queuing Local Prompter.

To re-render those clips: Builder → **Music Video Clip Fixer** or **Auto Chain Clip Fixer** (same models/VAE/sampler as the original chain). Point `latent_prefix` at the existing chain, paste the rewritten clips (or the full document), and set `clip_index`. Empty `clip_index` regenerates every `## Clip` in the paste. Before sampling, the node checks that `1..N` latents exist, copies the overwritten slots into `backup_YYYYMMDD_HHMMSS/` next to the prefix, then regenerates in order: clip `i` continues from the new `i-1` if that slot was just written, else from the on-disk `i-1`; it packs the on-disk `i+1` opening as end context only when `i+1` is **not** also being rewritten. After overwrites, it restitches the full saved chain (Auto Chain also regenerates Loop when Finish is in the set). These nodes need H3 loaded, unlike Local Prompter.

Queue **this node without H3 loaded**. It unloads Comfy models, starts llama-server on `127.0.0.1`, generates each clip, then kills the server. Copy `prompts` into Auto Chain / Music Video `prompt`. 27B Q4_K_M and H3 cannot share 32 GB VRAM; queue the video graph after the prompter finishes.

Auto Chain and Music Video share one prompt format: `H3 Studio prompt` then `## Clip` sections (Music Video also has `time:` / `lyrics:` per clip). Each clip has its own `subject_definitions`; those tags are the dump stills/videos/audio that clip loads. A top-level `subject_definitions` block is only a fallback for older documents whose clips omit one. The prompt editor turns `@Picture N` into chips; **Replace this** changes that chip, **Replace all** swaps a reference everywhere, and **Remove** deletes the chip. Video/audio chips show numbered buttons when the Builder trim has more than one segment (`<Video 1:2>` selects slice 2). Type `#` to create a dialogue block (`<d>[English] ...</d>` by default); click the flag to change language. Enter leaves the block, Shift+Enter inserts a line break inside it.

### Install llama.cpp

Download a release from [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/releases). Nightly tags (`b#####`) ship the platform zips; `v0.3.0`-style tags may only point at the latest nightly.

**Windows NVIDIA (recommended location for this node):** extract the CUDA zip **and** the matching CUDA runtime zip into `ComfyUI/user/llama.cpp/` so `llama-server.exe`, `llama-cli.exe`, and the CUDA DLLs sit in that folder. The node finds them there without putting them on PATH. Restart ComfyUI afterward.

| GPU / toolchain | llama.cpp zip | CUDA runtime zip |
|---|---|---|
| RTX 40/50, CUDA 13 | `llama-b*-bin-win-cuda-13.3-x64.zip` | `cudart-llama-bin-win-cuda-13.3-x64.zip` |
| CUDA 12 | `llama-b*-bin-win-cuda-12.4-x64.zip` | `cudart-llama-bin-win-cuda-12.4-x64.zip` |
| CPU only | `llama-b*-bin-win-cpu-x64.zip` | (none) |

Linux/macOS: extract the matching `.tar.gz` from the same release and put `llama-server` / `llama-cli` on PATH, or under `ComfyUI/user/`.

Multi-clip jobs need `llama-server`. A single clip can fall back to `llama-cli`. Optional overrides: the node's `llama_server` widget, or `H3_STUDIO_LLAMA_SERVER` / `H3_STUDIO_LLAMA_CLI`.

## Music Video → Face Refine

Point Face Refine `video_path` at the `png …` folder from `chain_info` (ComfyUI temp). Each run prints a disk/RAM banner first: uncompressed RGB ceiling for the PNG sequence, plus float32 RAM for the `IMAGE` output.

## Dependencies

- ComfyUI MiniMax H3 (stock nodes, not a custom pack)
- llama.cpp (`llama-server`) for Local Prompter — see [Install llama.cpp](#install-llamacpp)
- `ultralytics`, `scipy`, `insightface` for Face Refine
- MaskVidExperiments is optional (crop-teleport packing). Without it, Face Refine falls back to gaussian crop follow

## Lyrics Timer

Times untimed lyrics with torchaudio wav2vec2 (`WAV2VEC2_ASR_BASE_960H`). Use **Time lyrics** or queue Lyrics Timer **without H3 loaded**; the first run downloads that bundle. Confirm-format `[start-end]` LRC is passed through so timeline edits stick. Local Prompter then letter-refines those locked lines and fills the Music Video prompt. The **music-video agent skill** posts the same wav2vec2 refine to `/h3_studio_song/plan` (letter clocks + CLIP skeleton). Parakeet / WhisperX stay out of Comfy’s venv.

## Agent skills

Copy the folders in [`skills/`](skills/README.md) into your agent (Cursor, Claude Code, and similar). Music Video **Copy skill command** includes the Comfy origin, song path, and timed lyrics. The music-video skill does not download torch; it reuses this Comfy install.

## License

Continuation / Music Video / Auto Chain / Lyrics Timer code is GPL-3.0 (see `LICENSE`). Face Refine code is MIT (see `LICENSE-FaceRefine`). Combined, this pack is distributed under GPL-3.0.

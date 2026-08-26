# ComfyUI-H3-Studio

Standalone ComfyUI nodes for MiniMax H3 music videos: chain generation, lipsync to a song, lossless PNG handoff, and face refine. This pack does not import Herrgotts or ComfyUI-H3-FaceRefine.

## Nodes

| Node | What it does |
|---|---|
| **H3 Studio - Music Video** | Generate clips to cover a source song from one H3 Studio prompt document, write a lossless PNG sequence under ComfyUI temp. `IMAGE` is that sequence. `reference_image_1` is shown first; connecting it reveals `reference_image_2`, and so on (up to 9). |
| **H3 Studio - Auto Chain** | N-clip Ref2VA Start / Continue / Finish stitch. One H3 Studio prompt document covers every clip. Optional `<Picture N>` stills work like Music Video (`reference_image_1` reveals `_2`, up to 9). Optional seamless loop. Same temp PNG sequence as `IMAGE`. |
| **H3 Studio - Builder** | Drop images, videos, and audio, or wire several IMAGE/VIDEO/AUDIO outputs to the `Media` socket; connect patched H3 models. Switch Auto Chain / Music Video (Music Video disables audio refs). Outputs a pack plus `duration`. Plan field is included in Copy pack summary. |
| **H3 Studio - Auto Chain Advanced** | Same stitch loop as Auto Chain, but takes a Builder pack. Duration and clip count come from the prompt, or from the pack. Per-clip `<Model N>` / `<Picture N>` / `<Video N>` / `<Audio N>` select a subset. |
| **H3 Studio - Music Video Advanced** | Same lipsync loop as Music Video, but takes a Builder pack. Clip count and max duration come from the prompt, or duration from the pack. `<Audio 1>` stays the song slice; Builder audios are `<Audio 2>` / `<Audio 3>`. |
| **H3 Studio - Face Refine Video** | Face-refine a finished clip. Set `video_path` to the Music Video PNG folder from `chain_info`. `IMAGE` is the refined temp PNG sequence. |
| **H3 Studio - Load Song** | Load AUDIO and edit confirm-format lyric stamps on a timeline. |
| **H3 Studio - Local Infinite Prompter** | Start local llama.cpp on a catalog or local GGUF, write one Auto Chain prompt document from a Builder dump plus plan, then stop the server. |

Category: **H3 Studio**.

Class names (`H3StudioMusicVideo`, `H3StudioMusicVideoAdvanced`, `H3StudioAutoChain`, `H3StudioAutoChainAdvanced`, `H3StudioBuilder`, `H3StudioFaceRefineVideo`, `H3StudioLoadSong`, `H3StudioLocalInfinitePrompter`) are unique, so this pack can sit next to Herrgotts / Face Refine without node-id collisions. Continuation runtime hooks reuse Herrgotts patch markers so both packs do not fight over PackedLayout.

## Local Infinite Prompter

The node does not bundle llama.cpp. Install the official binaries, then either drop the catalog GGUF in `ComfyUI/models/LLM/` or enable `allow_download` once (~16 GB from Hugging Face). You can also pick a scanned `local:…gguf` or **Local GGUF** plus `gguf_path`.

Builder (Auto Chain mode) → Copy pack summary → paste into `dump`. The dump's `plan:` block and/or the node's `plan` widget is the story. Queue **this node without H3 loaded**. It unloads Comfy models, starts llama-server on `127.0.0.1`, generates each clip, then kills the server. Copy `prompts` into Auto Chain / Auto Chain Advanced `prompt`. 27B Q4_K_M and H3 cannot share 32 GB VRAM; queue the video graph after the prompter finishes.

Auto Chain and Music Video share one prompt format: `H3 Studio prompt` with shared `subject_definitions`, then `## Clip` sections (Music Video also has `time:` / `lyrics:` per clip). Edit the shared subjects once to update every clip. The prompt editor turns `@Picture N` into chips; **Replace this** changes that chip, **Replace all** swaps a reference everywhere, and **Remove** deletes the chip. Video/audio chips show numbered buttons when the Builder trim has more than one segment (`<Video 1:2>` selects slice 2). Type `#` to create a dialogue block (`<d>[English] ...</d>` by default); click the flag to change language. Enter leaves the block, Shift+Enter inserts a line break inside it.

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

Optional **windowed de-rope** (`de_rope`, default off) runs MAINodes jerk-oracle burst windows after the native decode: Time Smear → V2V → Exact Recover, skipping Continue overlap head/tail so freeze-overlap tokens still match. Requires [ComfyUI-MAINodes](https://github.com/matlowai/ComfyUI-MAINodes) as a sibling pack. Optional **3D latent upscale** (`latent_upscale` toggle) is decode/stitch only — saved Continue latents stay native size. When on, choose `scale by multiplier` or `megapixels`, plus precision. Disk budget follows the chosen output size. De-rope always runs at native resolution before any upscale. Music Video still muxes the original song.

## Dependencies

- ComfyUI MiniMax H3 (stock nodes, not a custom pack)
- llama.cpp (`llama-server`) for Local Infinite Prompter — see [Install llama.cpp](#install-llamacpp)
- `ultralytics`, `scipy`, `insightface` for Face Refine
- MaskVidExperiments is optional (crop-teleport packing). Without it, Face Refine falls back to gaussian crop follow
- Windowed de-rope needs sibling `ComfyUI-MAINodes`. 3D latent upscale needs sibling `Comfyui_Minimax_h3_latent_Upscaler` and checkpoints in `models/latent_upscale_models/`

Song timestamping for music-video prompts lives in the Cursor skill `prompt-minimax-h3-music-video` (Parakeet venv, transcribe script). This pack does not ship that installer.

## License

Continuation / Music Video / Auto Chain / Load Song code is GPL-3.0 (see `LICENSE`). Face Refine code is MIT (see `LICENSE-FaceRefine`). Combined, this pack is distributed under GPL-3.0.

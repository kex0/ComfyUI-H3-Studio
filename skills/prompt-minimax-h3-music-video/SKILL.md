---
name: prompt-minimax-h3-music-video
description: >-
  Writes one human-readable MiniMax H3 Music Video prompt document to a
  workspace .txt file (link in chat; never paste the full doc) from a Builder
  skill command that includes the song path and lyrics. Use when the user
  invokes /prompt_minimax_h3_music_video, /prompt-minimax-h3-music-video, or
  asks for H3 Infinite music-video / lipsync-to-song clip prompts.
disable-model-invocation: true
---

# MiniMax H3 Music Video Prompts

The prompt document is parsed by ComfyUI **H3 Studio - Music Video**. CLIP math and wav2vec2 letter refine run in the user's **running ComfyUI** (H3 Studio). This skill does not install torch, WhisperX, Parakeet, or Demucs. Do **not** transcribe: lyrics come from the user prompt / Builder dump. Generating video still needs that node in Comfy. Clip 1 is **Ref2VA** (six-section body) plus the first song slice as `<Audio 1>`. If a Builder dump Picture line ends with ` (first frame)`, that still is MiniMax's first image for CLIP 1 (hybrid FL2VA start + Ref2VA identity). Later clips Continue **video** from the previous AV latent with the **next song slice** as `<Audio 1>` and the pictures that CLIP cites. Final soundtrack is the original song (muxed). Do not use Auto Chain or `/prompt_minimax_h3_infinite` for this. Unmarked stills are not first-frame locks. Do not write T2VA `at 0.00 seconds … is fully referenced`.

Paste the finished file into the node's single `prompt` field. Each CLIP's `subject_definitions` cites the dump labels that CLIP loads.

When the user pastes an **H3 Studio Builder dump**, wire **Builder → Music Video**. Treat dump lines as the only legal Model / Picture / Video / Audio inventory. Keep `<Audio 1>` as the song slice; cite Builder pictures **inside** `<Subject N>` lines (CLIP 1 also gets a first-frame Picture row when the dump marks one); Builder audios only as `<Audio 2>`+; optional `<Model N>` per CLIP body. Do not put a Builder audio on Audio 1.

**Per-CLIP pack selection (Advanced):** write the dump labels that CLIP still uses (`<Picture 3>`, `<Video 1>`, `<Model 2>`) in **that CLIP's** `subject_definitions`. Identity stills that still apply must be cited (one identity Picture belongs in every CLIP). The node loads **exactly those** Picture / Video / builder-Audio items and remaps them to contiguous H3 ordinals before tokenize. `<Audio 1>` is always the song slice and does **not** count as a builder-audio citation. Do not cite unused extra stills on every CLIP.

Single-clip Ref2VA stays on `prompt-minimax-h3`. Auto Chain continuation stays on `prompt-minimax-h3-infinite`.

## When invoked

**Default: the paste is a Builder Copy skill command.** It starts with `/prompt-minimax-h3-music-video` and includes `song:` (path to the audio), a `lyrics:` block, and the visual `plan:`. Those lyrics are the words. Do not ASR the song.

If `song:` is missing, an attached audio file is the song. Do not ask for `song-seconds` when the audio path is known.

**If the user attaches stills, inspect them before writing.** Unmarked stills are Ref2VA identity/style references (`<Picture 1>` …), not first-frame anchors. A dump line ending ` (first frame)` is the CLIP 1 start lock. Never pretend you saw media you did not open.

**If the user pastes a Builder dump, those labels are the only inventory.** Each CLIP's `subject_definitions` cites the dump labels that CLIP uses. Omit Picture/Video/Model tags on a CLIP to use Builder defaults for that CLIP. Never cite Builder audio as `<Audio 1>`.

Builder dump shape:

```text
/prompt-minimax-h3-music-video
H3 Studio Builder pack
duration: 10.00s
Model 1: cinematic identity LoRA stack
Picture 1: blonde woman, red jacket (first frame)
Video 1: 4.2s walking cycle (with soundtrack)
comfy: http://127.0.0.1:8000
song: C:\ComfyUI\input\song.mp3
lyrics:
[00:00.000-00:04.200] I been waiting in the dark
[00:04.200-00:08.000] <instrumental>
plan:
neon karaoke booth, medium close-up; keep the same singer
```

If the dump includes `duration:`, use it as the max clip length unless the user also passed `Ns`. If it includes a `plan:` block, that is the visual plan. Builder Music Video mode omits audio refs (the song is `<Audio 1>`). If a dump still lists `Audio N`, those are Builder audios and become prompt `<Audio 2>`+. Wire Builder `duration` into Music Video.

`Picture N: … (first frame)` means CLIP 1 Shot 1 must match that still (crop, pose, wardrobe, place). Cite it as `<Picture N>` for identity too. CLIP 2+ continues from the previous ending, not from that still. Unmarked pictures stay identity/style refs only.

Write the finished H3 Studio prompt document to a UTF-8 `.txt` file, then reply with a link (or path) to that file only — do **not** paste the full document into chat (it is large and gets truncated). No suite tutorial, no checklist, no per-clip Comfy widgets. Prefer a workspace path such as `Prompting/<song-stem>-music-video.h3.txt` (or `.tmp/` if the user prefers temp). Open the file in the editor when possible.

Optional leading tokens (case-insensitive, space or colon separated):

| Token | Meaning |
|-------|---------|
| `Ns` or `N sec` (e.g. `8s`, `10s`) | **Maximum** requested clip length before H3 snap (default **10s**, hard cap **15s**). Not a fixed length. Lower this at high resolution to avoid OOM. |
| `Picture1=...` / `Picture2=...` | Optional Qwen identity refs when **not** using a Builder dump. Cite each inside `<Subject 1>`. Omit Picture labels if unused |
| `I2VA` | Unnecessary when the dump already has ` (first frame)`. Unmarked attached stills stay pictures, not first-frame locks |

If the user asks for a max above 15s, stop and use 15s. Do not invent unsnapped lengths such as `12.4s`.

## Song file + timing (do this first)

Lyrics are already in this invocation (Builder `lyrics:` block, or a pasted LRC). Do **not** transcribe. Do **not** run Parakeet, WhisperX, faster-whisper, openai-whisper, or Demucs. Do **not** POST Comfy `/h3_studio_song/refine` — that returns line LRC only, not per-letter `words.json`. Do **not** install Python packages.

**Comfy must be running** with H3 Studio loaded as a custom node. Letter clocks and CLIP planning use Comfy's torchaudio wav2vec2 (`WAV2VEC2_ASR_BASE_960H`) — the same bundle Lyrics Timer already downloads. Prefer Comfy **without H3 loaded** so align has VRAM.

`SKILL_DIR` is the folder that contains this `SKILL.md`. The only local script is `scripts/fill_prompt_bodies.py` (plain Python, no torch).

**Timed lyrics required.** Write the dump/paste to `song.confirm.lrc` as `[start-end] text` (including `~word~` and `<instrumental>`). If lyrics have no `[start-end]` / `[m:ss]` stamps, stop. Tell the user to time them in **Lyrics Timer** and Copy skill command again. Never guess singing starts at 0.00. Dump `lyrics:` with range stamps from Lyrics Timer are already confirmed — do **not** wait for a second confirm.

**Song path** from dump `song:` or an attached audio file. **Comfy origin** from dump `comfy:` (e.g. `http://127.0.0.1:8000`). If `comfy:` is missing, use `http://127.0.0.1:8188`. If there is no audio path, stop.

Mark a sustained / held vowel in `song.confirm.lrc` with tildes around that word: `stories shift over ~time~` or an explicit stretch `stories shift over ~tiiiiiime~`. Refine aligns the plain spelling; skeleton `lyrics:` keep the `~…~` mark; the filler expands it in `<d>` (e.g. `tiiiiiime`) and adds a held-vowel lip cue. Do not invent holds the user did not mark.

Mark a timed rest with `[start-end] <instrumental>` (also `(instrumental)` or a lone `instrumental`). Refine does not align that line. The skeleton keeps the stamp. The filler treats it as a closed-lip rest and cuts a new shot at that start time so the singer does not keep staring through the break. This is a shot cut, not a CLIP split.

Confirm file shape:

```text
[01:59.680-02:02.480] Cloud copy of me
[02:02.640-02:05.200] Still laughing somewhere
[02:05.360-02:06.640] in the binary
```

**Letter refine (always, this invocation):** new tmp dir. Do not reuse an older `*.words.json` / skeleton. POST the confirm LRC and song path to Comfy. Line start/end/text stay exactly as confirmed. Comfy forced-aligns with wav2vec2 and returns letter clocks plus the CLIP skeleton.

```powershell
curl.exe -sS -X POST "<COMFY>/h3_studio_song/plan" -H "Content-Type: application/json" --data-binary "@plan.json"
```

`plan.json`:

```json
{
  "path": "PATH/TO/SONG",
  "lyrics": "<contents of song.confirm.lrc>",
  "duration": 10
}
```

Use dump `duration:` (strip the `s`) unless the user passed `Ns`. Write the response to a new path (`Prompting\.tmp\<stem>-<this-run>`):

- `lyrics` → `song.confirm.lrc`
- `words` → `song.confirm.words.json`
- `skeleton` → `song.skeleton.txt`

`source` must contain `wav2vec2-refine`. Sung lines in `words.lines[].words[]` must include `chars[]` (per-letter clocks). If the POST fails, Comfy is down, `source` is wrong, or sung lines lack `chars`, **stop**. Do not type stamps by hand. Do not fall back to line-only timing.

Never invent, move, drop, ASCII-fold, or re-parse a lyric line after confirm. Cropped `lyrics:` (words that fall past this CLIP's `audio:` end) are the skeleton's job — copy them as written, including partial last words.

## Segment math (must follow)

H3 snaps requested seconds **upward** to the 17k+5 frame grid at 24 fps. Only those grid steps are legal generate lengths. Floor **5s** (124 frames / 5.167s). Cap **15s** requested (362 frames / 15.083s).

| Requested max | Actual frames | Actual seconds |
|---------------|---------------|----------------|
| 5.00s | 124 | 5.167s |
| 8.00s | 192 | 8.000s |
| 10.00s | **243** | **10.125s** |
| 15.00s | 362 | 15.083s |

**`Ns` is a max, not a fixed clip length.** The skeleton already:

- Covers the song after head/tail trims (not `ceil(song / D_grid)`). Joins discard about **1s** of the previous clip; Continue context is taken from before that cut.
- Lists lyrics that overlap this CLIP's ``<Audio 1>`` slice (`audio:` / `[slice, slice+duration)`), not kept `time:`. The continuation head is in that audio, so those words stay in the prompt (CLIP 25 `in the machine`, not a leftover `the machine`). Overlap words may appear on both this CLIP and the previous one. Include the discarded 1s tail on **this** CLIP. Crumbs shorter than 0.2s are dropped. After confirm refine, a line that crosses the slice end is **cropped to the words/letters inside that slice** — do not prompt the rest of the phrase. Keep each confirmed phrase on its own `lyrics:` line; never flatten adjacent phrases and re-chunk them. Copy every sung `lyrics:` line into its own `<d>` with that line's exact wording (including cropped leftovers). The filler packs those `<d>` tags into a scaffold take and cuts only at `<instrumental>`. After fill, **you** time the editorial shots — including frequent cuts when the user asked. Keep `[stamp] <instrumental>` on `lyrics:` and never copy it into `<d>`. Shot 1 is already singing if the first sung line is in this generate (do not add a closed-lip pre-roll shot for a few hundred milliseconds).
- Shrinks a clip only when a line cannot finish inside that generate. Never stretches toward 15s. Never goes below 5s except the last remainder still uses the 5s floor grid.
- Never splits a line across two different wordings. If a single line is longer than the max generate, stop and tell the user to raise max duration (`10s` → `12s` / `15s`).
- CLIP `lyrics:` use `[mm:ss.xxx-mm:ss.xxx] text` (start and end). Copy those stamps from the skeleton. Do not invent ends.

Copy `time:`, `duration_seconds:`, `slice:`, `audio:`, and the entire `lyrics:` block from the skeleton (the filler keeps them under each `## Clip`). Do not pick seconds yourself. Do not write a parser that splits `lyrics:`. Header `duration` / `max_duration_seconds` is the snapped **max** (e.g. `10.125` for `10s`, `8.000` for `8s`). Cap **48** clips. If the helper errors that the song needs more than 48 clips, stop and tell the user to raise max duration or split the song.

The node generates CLIP 1 as generate 1, CLIP 2 as generate 2, and so on. It may stop before the last CLIP if kept picture already covers the song. Do not reorder CLIP blocks.

Do not rewrite `time:`, `duration_seconds:`, or `lyrics:` from the `/plan` skeleton. `slice:` / `audio:` are planner metadata the node ignores; use them for shot clocks and the `<Audio 1>` covering line.

Shot timestamps inside Ref2VA bodies are relative to **generate start** (`slice:`), not the kept `time:` start. For a lyric at 00:09.920 with `slice: 7.500`, write `At 00:02.420`. `<Audio 1>` covers `audio:` (`[slice, slice+duration)`), which is longer than `time:` (head overlap + tail).

## Output document (exact shape)

Write this shape **to the output file**. `fill_prompt_bodies.py` already emits it. The Music Video node parses the file. Do not wrap clip bodies in Markdown. Do not emit one Comfy widget per clip. Do not dump the file body into the chat reply.

```text
H3 Studio prompt
mode: music_video
duration: 10.125
segments: 20

## Clip 1 — Start
time: 0.000-8.125
duration_seconds: 10.125
slice: 0.000
audio: 0.000-10.125
lyrics:
(instrumental)
subject_definitions:
<Subject 1> is the singer in <Picture 1>, matching that still's face, hair, and wardrobe.
<Audio 1> is the source-song slice covering 0.000–10.125 of the master, reused as the complete soundtrack.
summary:
...
retention_analysis:
...
detailed_description:
<Ref2VA body; lips closed; no sung <d>>
overall_soundscape:
...
non_diegetic_music: N/A

## Clip 2 — Continue
time: 8.125-16.250
duration_seconds: 10.125
slice: 6.875
audio: 6.875-17.000
lyrics:
[00:12.000-00:14.800] I been waiting in the dark
subject_definitions:
<Subject 1> is the singer in <Picture 2>, matching that still's face, hair, and wardrobe.
<Audio 1> is the source-song slice covering 6.875–17.000 of the master, reused as the complete soundtrack.
summary:
...
detailed_description:
<Ref2VA body; sings those lines in sync>
```

`time:` is the **kept-picture** range (three decimals). `duration_seconds` is that clip's **generate** length (snapped). `slice:` / `audio:` stay in the document for shot clocks and the `<Audio 1>` covering line. Clip indices are `1..N` in order. Each CLIP's `subject_definitions` is what that CLIP loads — pick dump stills per CLIP; omit unused ones.

Set the Music Video node's duration widget to the same max as the header (the `Ns` token).

Load [templates.md](templates.md) for sung vs instrumental bodies. Base structure on `prompt-minimax-h3/reference-ref2va.md`.

## Continuity

- Clip `k` **Shot 1 continues** clip `k-1`'s last frame: same world, wardrobe, camera crop, and prop. No pose reset, no cut, no “the space becomes”.
- CLIP 1 with dump ` (first frame)`: Shot 1 opens on that still, then the rest of the CLIP can cut. CLIP 2+ does not reopen Shot 1 on that still, but still cites it inside `<Subject 1>` so the still loads.
- Do not write “she starts to sing” on an instrumental clip. On the first **sung** clip, singing begins at that window's first lyric time, not at 0.00 of the whole song.
- You are the creative director. After fill, write a music video of timed `[Shot N]` cuts that make sense with the lyric and the arrangement — not a heuristic of one take per CLIP or one cut per word. If the user asked for **frequent cuts**, typically one editorial shot per lyric line (or about 2–3 seconds), with `At mm:ss.sss, the camera cuts` relative to `slice:` on Shot 2+. Do not even-split a 4+ word line into extra camera cuts. Attach leftover crumbs shorter than ~0.8s to the previous shot.
- A `[stamp] <instrumental>` line is a locked closed-lip cut at that clock. Keep that clock. You may add more editorial cuts around it.
- New environment **only after** `the camera cuts`. Never morph the room behind the subject mid-shot. Shot 1 of a Continue clip stays in the previous ending world until a later shot in that CLIP cuts.
- A wireless mic (or dancing with empty hands) is committed for the **entire shot**. Never pick it up or drop it mid-shot. Change mic / empty hands only on a cut. “Sometimes dancing, sometimes holding a microphone” means some shots dance and other shots hold the mic — never the word *sometimes*, and never both in one shot.
- Occasional face close-ups only on sung shots, and only some of them, when the user asked.
- Identity/wardrobe for a CLIP come from the pictures that CLIP cites in `subject_definitions`. Do not stamp every attached still onto every CLIP. A later CLIP may cite a different dump still when the plan changes identity or look.
- Do not write last-frame landings or freeze poses.

## Audio / lipsync (every clip)

- `<Audio 1>` is **this clip's song slice** (the node feeds a full generate-length slice starting `head` frames before the previous kept end). Copy the skeleton `audio:` range into the covering line. Prompt every skeleton lyric that overlaps that `audio:` span. Do not invent stamps; copy them from the **post-confirm** skeleton.
- Builder dump audios are `<Audio 2>` / `<Audio 3>` only. Never put a Builder audio on `<Audio 1>`. Optional `<Video N>` / `<Model N>` come from that dump.
- `retention_analysis`: `<Audio 1>: fully_copy` — complete slice = complete target track; no new score, SFX bed, or replaced layers.
- **Sung window:** the subject sings those `lyrics:` in sync with `<Audio 1>`. Exact words in `<d>[Language] ...</d>` from the confirmed LRC, except `~hold~` marks which expand to elongated spelling in `<d>` only (skeleton `lyrics:` keep the mark). Place each `<d>` in a shot that is on-camera for that line's clock. A `[stamp] <instrumental>` line is not sung: keep the filler's closed-lip cut at that time (`At mm:ss.sss, the camera cuts. <Subject 1>'s lips stay closed.`) relative to `slice:`. Never put `<instrumental>` inside `<d>`.
- **Instrumental window:** lips stay closed; no `<d>` singing; still `fully_copy`. The body can move with the music. If the only listed line is a late `<instrumental>` stamp, still cut at that clock.
- `overall_soundscape` / `non_diegetic_music`: `<Audio 1>` reused as-is. No other sounds. `non_diegetic_music: N/A`. Do not list forbidden SFX. The filler already writes this; do not add room tone, breath, crowd, or a second score.

## Generation workflow

The filler is a **scaffold**: CLIP headers, `lyrics:`, locked `<d>` strings, six-section wrappers, audio `fully_copy`, soundscape, and the `<instrumental>` cut clock. It does **not** pick worlds, mic vs dance, camera cuts on lyrics, or close-ups. **You** are the creative director. Do not write `worlds.txt` / `actions.txt` and do not leave the filler take as the video.

1. Resolve the song path from dump `song:` and Comfy origin from dump `comfy:`. Write dump `lyrics:` to `song.confirm.lrc`. Optional pictures: inspect stills and note appearance extras (hair, makeup, wardrobe). If a dump Picture is tagged ` (first frame)`, CLIP 1 Shot 1 / `--opening` must match that still. Parse **max** clip duration (default 10s, cap 15s) and visual plan.
2. Timing: Comfy must be running. New tmp dir. Do not search `Downloads\`, `Prompting\`, or `.tmp\` for an older `*.words.json` / `.skeleton.txt` / `.confirm.lrc` and do not copy those clocks. Write this run's confirm LRC / `.words.json` / skeleton to a new path (`Prompting\.tmp\<stem>-<this-run>`). Never use `cloud-copy.*`. Prefer running while ComfyUI is not holding H3 in VRAM. Do **not** transcribe. Do **not** POST `/h3_studio_song/refine`. POST `/h3_studio_song/plan` as above.
3. If `source` contains `wav2vec2-refine` and `song.confirm.words.json` has per-letter `chars` on sung words, run **this skill's** filler (plain Python) for boilerplate only:

```powershell
python scripts/fill_prompt_bodies.py "song.skeleton.txt" -o "Prompting/<stem>-music-video.h3.txt" --subject "<identity>" --opening "<CLIP 1 visible opening; dump first-frame still when marked>" --picture1 "<appearance extras from still 1>"
```

**This invocation only.** Do not reuse `--fx` or a previous `.h3.txt` from another song or an earlier chat. Omit `--picture1` / `--opening` when unused. `--picture1` may stamp the same still onto every CLIP body; the director pass must rewrite **each CLIP's** `subject_definitions` so it cites only the dump stills that CLIP needs. Pass `--fx` only if this song asked for a named treatment (it goes in the style sentence once). Do **not** pass `--portrait occasional`. Do **not** create a new splice script. Do **not** pass `--worlds` / `--actions`.

4. **Direct the video.** Replace each CLIP `summary`, `detailed_description`, and `subject_definitions`. Plan the whole song as one music video: verse / pre-chorus / chorus / bridge / outro environments, when the mic is in the shot, when the body is dancing empty-handed, where the close-ups land, and where 2D/3D VFX hit. Decide **which dump stills each CLIP cites**. Then write shots that are timed to the lyric clocks.

   Hard locks — do not change these:
   - `time:`, `duration_seconds:`, `slice:`, `audio:`, and `lyrics:` under each `## Clip`
   - every `<d>[Language] …</d>` string (redistribute into shots; do not rewrite the words)
   - the filler's `<instrumental>` `At mm:ss.sss, the camera cuts` clock
   - six section names with colons; `overall_soundscape` / `non_diegetic_music`
   - pictures cited inside `<Subject 1>` only, except CLIP 1 may add a standalone `<Picture N> is the first frame of [Shot 1]` row in **that CLIP's** `subject_definitions` when the dump marks that still `(first frame)`

   Shot rules:
   - Shot 1 has no timestamp. CLIP 1 with dump ` (first frame)` opens on that still; CLIP 2+ Shot 1 continues the previous CLIP's last frame.
   - Shot 2+ use `At mm:ss.sss, the camera cuts` relative to `slice:` (lyric start, or the locked instrumental clock).
   - Frequent cuts when asked: usually one `[Shot]` per sung line. Keep a crumb under ~0.8s in the previous shot.
   - Environment and mic/hands change **only** on a cut.
   - Occasional face close-up on a sung shot when asked — not on every line, not from `--portrait occasional`.
   - Never write `sometimes` / `X or Y` / `|` roulette. Never write `The space becomes`.

5. Self-check: output `lyrics:` blobs match the **post-confirm** skeleton; every sung skeleton `[stamp]` appears in that CLIP's `<d>` (do not sing `<instrumental>` — that stamp stays a closed-lip camera cut at the relative clock); held `~word~` marks may expand inside `<d>` only; a short CLIP with one lyric plus `<instrumental>` keeps that rest cut and is not even-split into four filler shots; six Ref2VA sections with colons; pictures cited inside `<Subject 1>` except CLIP 1's dump `(first frame)` still, which also gets a first-frame Picture row; CLIP 1 Shot 1 matches that still when marked; CLIP 2+ does not reopen on it; no T2VA `at 0.00 seconds … first frame of [Shot 1] is fully referenced`; no extra score; **no** `sometimes` / `X or Y` action hedges; no microphone unless this invocation asked for it; no environment change without `the camera cuts`.
6. Reply with the file path/link (and optionally `clip_count` / `max_duration_seconds`). Never paste the full prompt document into chat.

## Shared H3 rules

- English except verbatim lyrics/dialogue in `<d>[Language] ...</d>`.
- One or two style sentences **before** `[Shot 1]` (`The target video is live-action, cinematic, …`).
- Shot 1 has no timestamp. Each confirmed phrase stays on its own `lyrics:` / `<d>` line. Do not dump the whole CLIP into one `<d>`. Do not glue adjacent phrases into new wordings. After fill, you may put each `<d>` in its own `[Shot]` when the user asked for frequent cuts. Name `<Subject 1>`, not he/she.
- Always keep `overall_soundscape` and `non_diegetic_music`.
- Do not invent reference assets, props, or staging the user did not supply in **this** invocation.
- Do not wrap field values in Markdown.
- Follow `prompt-minimax-h3/reference-ref2va.md`: cite identity pictures inside the Subject line; standalone `<Picture N>` for a dump `(first frame)` still on CLIP 1, or other real frame/storyboard anchors.

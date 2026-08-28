---
name: prompt-minimax-h3-infinite
description: >-
  Writes a chain of MiniMax H3 Ref2VA prompts for H3 Studio Auto Chain
  (Start + Continue + Finish, optional Loop). Use when the user invokes
  /prompt_minimax_h3_infinite, /prompt-minimax-h3-infinite, or asks for N
  segment / clip continuation prompts for H3 Infinite, including seamless loop.
disable-model-invocation: true
---

# MiniMax H3 Infinite Continuation Prompts

One **H3 Studio prompt** document for **H3 Studio - Auto Chain** or **Auto Chain Advanced**. Each `## Clip` (and optional `## Loop`) has its own `subject_definitions` with the dump labels that clip loads. Paste the whole document into the node's `prompt` field. Advanced clip 1 may also lock MiniMax's first image when the dump marks a still `(first frame)` (hybrid FL2VA start + Ref2VA refs).

- **Advanced (default when a Builder dump is present):** Wire **Builder → Auto Chain Advanced**. Keep the Ref2VA body. If a dump Picture line ends with ` (first frame)`, that still is MiniMax's first image for clip 1 and may still be cited as `<Picture N>` for identity. Unmarked pictures stay identity/style refs only. Do not use the original Auto Chain model / picture sockets.
- **Original Auto Chain / Herrgotts:** only if the user says they are on that node. Clip 1 may then use I2VA/FL2VA first-frame alignment from `prompt-minimax-h3/reference-base.md`.

Single-clip H3 stays on `prompt-minimax-h3`. Lipsync-to-song stays on `prompt-minimax-h3-music-video`.

Load [prompt-minimax-h3/reference-ref2va.md](../prompt-minimax-h3/reference-ref2va.md) for the six-section Ref2VA contract (`subject_definitions` especially). Load [templates.md](templates.md) for chain-shaped bodies.

## When invoked

Everything after `/prompt_minimax_h3_infinite` is the plan plus tokens. Follow **the user's plan**. Do not invent a walking-morph, reality-bend, or footsteps story.

**If the user pastes an H3 Studio Builder dump (or attaches it), those lines are the only legal Model / Picture / Video / Audio inventory.** Do not invent extra labels. Numbering is 1-based per type among enabled items.

```text
H3 Studio Builder pack
duration: 10.00s
segments: 2
Model 1: cinematic identity LoRA stack
Picture 1: blonde woman, red jacket (first frame)
Picture 2: night street
Video 1: 4.2s walking cycle (with soundtrack)
Audio 1: 3.1s rain bed
plan:
two women talk in a kitchen, then walk to the porch
```

If the dump includes a `plan:` block, that is the story plan. User text after the slash is extra direction on top of it. If the dump includes `duration:` / `segments:`, use those as N and per-clip length unless the user also passed `Nseg` / `Ns` in the invocation.

A Picture line that ends with ` (first frame)` is the Builder checkbox (only one picture). Clip 1 Shot 1 must open on that still's visible crop, pose, wardrobe, and place. Cite it as `<Picture N>` when the clip needs that identity. Clips 2+ do not treat it as a start lock (Continue uses the previous AV latent). Unmarked pictures are never first-frame anchors.

**Per-clip pack selection (Advanced):** write the dump labels this clip still uses (`<Picture 3>`, `<Video 1>`, `<Model 2>`) in **this clip's** `subject_definitions`. Identity stills that still apply must be cited (one identity Picture belongs in every clip). The node loads **exactly those** Picture / Video / Audio items and remaps them to contiguous H3 ordinals before tokenize (`<Picture 1>` + `<Picture 3>` become H3 Picture 1 then 2). `<Model N>` is stripped after the node picks that model. Auto Chain has no song: Builder `Audio 1` is the first standalone audio. Wire Builder `duration` / `segments` into Auto Chain Advanced.

**Inspect attached / dumped stills before writing.** Never pretend you saw media you did not open.

**Output one H3 Studio prompt document and nothing else** — no suite tutorial, no checklist. One fenced `text` block. Optional one-line chain summary after the fence.

Without `loop`: N `## Clip` sections. With `loop`: N story clips **plus** one `## Loop` section.

Optional leading tokens (case-insensitive, space or colon separated):

| Token | Meaning |
|-------|---------|
| `Nseg` / `N segs` / `N clips` / `N segments` (e.g. `5seg`) | Clip count. Dump `segments:` wins unless this token is present; else **3** |
| `Ns` or `N sec` (e.g. `10s`) | Duration **per clip**. Dump `duration:` wins unless this token is present; else **10s** |
| `I2VA` / `FL2VA` | Original Auto Chain: first/last-frame alignment from `reference-base.md`. Advanced: ignore the tokens; clip 1 start lock comes only from dump ` (first frame)`. Never write a last-frame landing. |
| `loop` / `seamless` / `seamless_loop` | Also emit a **Loop** prompt for Auto Chain `seamless_loop` |
| `Picture1=...` | Identity ref when **not** using a Builder dump. Omit Picture tags if unused |
| `ModelN=...` | Optional per-clip model when a Builder dump is present |

Examples:

```text
/prompt_minimax_h3_infinite 5seg 10s two women talk in a kitchen, then walk to the porch
/prompt_minimax_h3_infinite 3seg loop continue the attached scene; keep the same crop
/prompt_minimax_h3_infinite 4seg 8s Builder dump pasted below; swap identity stills per clip
```

## Segment math

`N` = number of **story** clips (`N >= 1`). Loop is extra and does not change N.

| N | Roles (no loop) | Roles (with loop) |
|---|-----------------|-------------------|
| 1 | Clip 1 Start only (also the finish) | Start + Loop |
| 2 | Start + Finish | Start + Finish + Loop |
| 3+ | Start + `(N-2)` Continue + Finish | Start + `(N-2)` Continue + Finish + Loop |

Handover: Clip k **Shot 1 continues** clip k−1's last visible state (same people, wardrobe, crop, and place) unless the user asked for a cut or reset. No pose-hold freeze at clip ends unless they asked.

Loop: the node continues from clip N and packs clip 1's opening as end context. Prompt the return as continuing clip 1's opening **action already in motion**, not as reconstructing a still or “returning to the opening pose”.

## Defaults (override when the user says otherwise)

- **10s** per clip.
- **Ref2VA six sections** in official order. Not `integrated_multimodal_description` (that is T2VA/I2VA/FL2VA).
- **No last-frame FL2VA landing.**
- **Advanced clip 1 with dump ` (first frame)`:** Shot 1 opens on that still (`keyframe completion` plus identity cites). Do not write the T2VA line `at 0.00 seconds … is fully referenced`.
- **Advanced without that suffix:** no first-frame lock.
- **Do not** add reality-bending morphs, footsteps-as-score, or banned/required camera phrases unless the user asked for those.
- Action, crop, cuts, and sound come from the user plan and inspected refs. `non_diegetic_music: N/A` unless they supplied music.

## Generation workflow

1. Parse N, duration, loop, Builder dump / attached media, and the user's actual story.
2. Inspect stills / dump descriptions. If a Picture is tagged ` (first frame)`, clip 1 Shot 1 matches that still. Map dump labels to people, places, motion, and sound.
3. Plan N clips that continue across joins. Assign **which dump labels each clip cites** and write those in **that clip's** `subject_definitions`. Identity stills that still apply must be cited in that clip (if the dump has one identity Picture, every clip cites it inside the Subject line). Omit unused extra stills, videos, and audio.
4. Write Clip 1 Start, clips 2..N−1 Continue, clip N Finish, optional Loop. Use [templates.md](templates.md) and `subject_definitions` from the Ref2VA guide.
5. Self-check: one document with N or N+1 clip sections, each with its own `subject_definitions`; six Ref2VA sections with colons in each clip; pictures that only supply a person/style sit **inside** `<Subject N>` lines; a dump ` (first frame)` still also gets a standalone `<Picture N> is the first frame of [Shot 1]` row in **clip 1's** subjects only; Continue/Finish/Loop still cite that Picture inside the Subject line (the node loads those tags) and do not reopen Shot 1 on that still; no T2VA `at 0.00 seconds … fully referenced` line; no Markdown inside clip bodies.

## Output document

Paste this whole file into Auto Chain / Auto Chain Advanced `prompt`. Set the node's `segments` to the story clip count. Each clip's `subject_definitions` is what that clip loads — pick dump labels per clip; omit unused stills.

```text
H3 Studio prompt
mode: auto_chain
duration: 10.00
segments: 2
loop: false

## Clip 1 — Start
subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Picture 1> is the first frame of [Shot 1], showing a blonde woman in a red jacket.
<Subject 2> is the kitchen in <Picture 2>, same lighting and counter layout.

summary:
[keyframe completion + reference generation] ...

retention_analysis:
...

detailed_description:
The target video is live-action, cinematic, ...
[Shot 1] ...

overall_soundscape: ...

non_diegetic_music: N/A

## Clip 2 — Finish
subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.

summary:
[video continuation + reference generation] ...

retention_analysis:
...

detailed_description:
...

overall_soundscape: ...

non_diegetic_music: N/A
```

With `loop`, set `loop: true` and add `## Loop — return to Clip 1` after the last story clip. For N=1 without loop, label Clip 1 `## Clip 1 — Start`. Do not wrap clip bodies in extra Markdown. Do not emit one Comfy widget per clip.

After the fence, one line only if useful, e.g. `Chain: kitchen talk → porch → street`.

## Shared H3 rules

- English except verbatim dialogue in `<d>[Language] ...</d>`.
- One or two style sentences **before** `[Shot 1]` in `detailed_description`.
- Shot 1 has no timestamp. Extra shots only if the user asked for cuts.
- Always keep `overall_soundscape` and `non_diegetic_music`.
- Do not invent reference assets the user did not supply.
- Do not wrap field values in Markdown.
- Name `<Subject N>`, not he/she, after the subject is defined.

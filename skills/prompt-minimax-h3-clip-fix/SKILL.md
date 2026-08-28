---
name: prompt-minimax-h3-clip-fix
description: >-
  Rewrites selected ## Clip bodies in an existing MiniMax H3 Studio prompt
  (Music Video or Auto Chain) from a fix plan, leaving lyrics and timings
  locked. Use when the user invokes /prompt-minimax-h3-clip-fix,
  /prompt_minimax_h3_clip_fix, pastes a Clip Prompt Fixer skill command, or
  asks to fix / revise only some clips in an H3 prompt document.
disable-model-invocation: true
---

# MiniMax H3 Clip Prompt Fix

Revise **only the selected clip bodies** in a finished H3 Studio prompt. This is the agent-side twin of Comfy **H3 Studio - Clip Prompt Fixer**. Do not regenerate the whole song. Do not run music-video transcribe / fill scripts. Do not use `/prompt-minimax-h3-music-video` or `/prompt-minimax-h3-infinite` (those write a new document from scratch).

Paste the result back into Music Video / Auto Chain `prompt` (or the Fixer's `original_prompt` for another pass).

Load [prompt-minimax-h3/reference-ref2va.md](../prompt-minimax-h3/reference-ref2va.md) for the six-section contract. For Music Video seeds also load [prompt-minimax-h3-music-video/templates.md](../prompt-minimax-h3-music-video/templates.md). For Auto Chain seeds load [prompt-minimax-h3-infinite/templates.md](../prompt-minimax-h3-infinite/templates.md).

## When invoked

Everything after `/prompt-minimax-h3-clip-fix` is the fix job. Typical paste from the node's **Copy skill command**:

```text
/prompt-minimax-h3-clip-fix
clip_index: 11-12
plan:
make these two darker; keep the same singer on the same street

H3 Studio Builder pack
duration: 10.00s
Model 1: cinematic identity LoRA stack
Picture 1: blonde woman, red jacket (first frame)
Picture 2: night street

original_prompt:
## Clip 10 — Continue
...
## Clip 11 — Continue
...
## Clip 12 — Continue
...
## Clip 13 — Continue
...
```

The node's **Copy skill command** copies the `clip_index` clips plus one previous and one following clip (`11` → 10–12; `11,12` → 10–13; `4` → 3–5). Neighbor bodies are context only. Local Prompter output is the rewritten `clip_index` clips only: no neighbors, and no `H3 Studio prompt` / `mode:` / `duration:` / `segments:` header.

Parse, in order:

| Field | Meaning |
|-------|---------|
| `clip_index:` | Story clips to rewrite (`11-12`, `11,12`, `3`). Empty only when `original_prompt` is a **partial** paste (every `## Clip` in it is rewritten). A full `1..N` document with no index is an error — that is a new-document skill. |
| `plan:` | What to change in those bodies. Required. |
| `H3 Studio Builder pack` | Optional. Only legal Model / Picture / Video / Audio labels. Music Video: keep `<Audio 1>` as the song slice; Builder audios are `<Audio 2>`+. |
| `original_prompt:` | Seed window: selected clips plus neighbors when present. Keep their headings (`## Clip 11`). Read neighbors for continuity; do not emit them. |

User text after the slash with no labels is extra plan on top of `plan:`. Attached stills are visual evidence; inspect them. Never pretend you saw media you did not open.

If a dump Picture line ends ` (first frame)`, that still is CLIP 1's start lock only. Do not reopen Shot 1 on it in CLIP 2+.

## Hard locks (v1)

Copy these **verbatim** from the seed clip. The plan cannot change them:

- `time:`, `duration_seconds:`, `slice:`, `audio:`
- the entire `lyrics:` block (including `[stamp] <instrumental>`)
- every `<d>[Language] …</d>` string already in that clip (you may move a tag into a different shot; do not rewrite the words)
- `## Loop` sections (leave as-is; do not emit them unless they were selected)

Rewrite **only** the six Ref2VA sections (`subject_definitions` through `non_diegetic_music`) on the selected clips.

## Rewrite rules

1. Detect Music Video vs Auto Chain from the seed (`mode:`, or `time:` / `lyrics:` present).
2. Resolve targets: explicit `clip_index`, or every story clip in a partial paste. Error if an index is missing from the paste.
3. **Not selected:** do not include that clip in the output. If a neighbor body is in the paste, you may read it for continuity, but do not emit it.
4. **Selected:** rewrite the six-section body to apply the plan. Keep the seed clip index in the heading (`## Clip 11 — Continue`).
5. Keep dump citations legal. Identity stills that still apply stay inside `<Subject N>`. CLIP 1 may keep a standalone `<Picture N> is the first frame of [Shot 1]` row when the dump marks that still. Continue/Finish must not reopen that row.
6. Music Video: keep `<Audio 1>` covering the seed `audio:` range; `retention_analysis` still `fully_copy` that slice; `non_diegetic_music: N/A`; do not add a second score. Sung lines stay in sync with the locked `<d>` tags.
7. Do not write T2VA `at 0.00 seconds … fully referenced`.

Output **only** the `clip_index` clips. Do not return the original full prompt. Do not return neighbor clips. Do not emit `H3 Studio prompt`, `mode:`, `duration:`, `segments:`, or `loop:`. Do not renumber headings to Clip 1.

## Output

One fenced `text` block with only the rewritten selected `## Clip` sections. The first line is `## Clip N — …`. Do **not** paste a 30-clip file into chat. Do **not** wrap the clips in a document header.

No suite tutorial, no checklist, no per-clip Comfy widgets.

## Shared H3 rules

- English except verbatim lyrics/dialogue in `<d>[Language] ...</d>`.
- One or two style sentences **before** `[Shot 1]` in `detailed_description`.
- Shot 1 has no timestamp. Continue Shot 1 is already in the previous ending state.
- Always keep `overall_soundscape` and `non_diegetic_music`.
- Do not invent reference assets the user did not supply.
- Do not wrap field values in Markdown.
- Name `<Subject N>`, not he/she, after the subject is defined.

# Clip templates (Ref2VA)

Duration `S.SS` = requested clip length with two decimals (default `10.00`).

Six sections, official order, colons required. Condensed from the MiniMax Full-Reference guide / `prompt-minimax-h3/reference-ref2va.md`. Do not use T2VA `integrated_multimodal_description`. Do not add morph / VFX / crop-lock language unless the user asked for it. When they did, write the visible mechanism and clip-relative clocks — never echo `reality-bends`, `every few seconds`, or `the space becomes`.

## subject_definitions (every clip)

One line per separately tracked item. If a Picture/Video only supplies a person, place, style, or motion, cite it **inside** the Subject line — no standalone Picture/Video definition row. Standalone `<Picture N>` / `<Video N>` / `<Audio N>` rows only when that asset is a frame/edit/continuation/structure/audio-signal anchor.

Cite **only** the Builder-dump (or attached) labels this clip needs. Those tags are what Auto Chain Advanced loads. Identity stills that still apply must be cited in **this clip**; if the dump has one identity Picture, every clip cites it inside the Subject line. Omit unused extra dump labels. A later clip may cite a different still when identity, place, or look changes.

```text
subject_definitions:
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Subject 2> is the kitchen in <Picture 2>, same lighting and counter layout.
```

Optional `<Model N>` anywhere in the body selects that pack model (stripped before Qwen). Omit it to use Model 1.

## Shared skeleton

```text
subject_definitions:
<Subject lines; dump labels only for this clip>

summary:
[reference generation] <one short paragraph of this clip's task; combine types with + when needed>

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - ...
<one line per defined label>

detailed_description:
The target video is live-action, cinematic, <style>.
[Shot 1] <dressed opening set, crop, camera rig, and body>. At mm:ss.sss, <the next visible beat: set, body, camera, or VFX mechanism>. <never a paraphrase of the plan>.

overall_soundscape: <diegetic sound for this clip>

non_diegetic_music: N/A
```

`summary` task-type prefix from the guide (`reference generation`, `video continuation`, `audio reference`, …). Clip 2+ is usually `[video continuation + reference generation]` when it continues the previous AV latent and still uses stills.

`detailed_description` is a shot list a DP could follow. Each beat needs crop or camera, subject body, dressed environment, and lighting. Vague timing (`then`, `every few seconds`) and unnamed effects (`transforms`, `reality-bends`) are incomplete.

## Clip 1 — Start

If the dump marks a Picture with ` (first frame)`, that still is MiniMax's first image (hybrid FL2VA start + Ref2VA refs). Cite identity inside the Subject line **and** give the marked picture its own row. Shot 1 opens on that still; motion starts from it. Unmarked pictures stay inside Subject only.

```text
<Subject 1> is the woman in <Picture 1>, matching that still's face, hair, and wardrobe.
<Picture 1> is the first frame of [Shot 1], showing <exact visible crop, pose, and place>.
```

`summary` prefix includes `keyframe completion` plus `reference generation` when other stills/videos are identity/motion refs. `retention_analysis` includes `<Picture N> ([Shot 1] first frame): fully_preserved - ...`.

If no dump picture is marked first frame, do not add a first-frame Picture row. Describe the opening from the plan and refs.

Do not write T2VA `at 0.00 seconds … is fully referenced`. Never write a last-frame landing.

## Clip k — Continue (clips 2 … N−1)

No first-frame Picture row, even if a dump Picture was clip 1's MiniMax first image. Still cite that identity Picture **inside** the Subject line so Auto Chain loads it. No last-frame landing. Shot 1 continues the previous clip's last visible state unless the user asked otherwise.

## Clip N — Finish

Same Ref2VA shape as Continue. Keep the action going through the end unless the user asked for a hold.

When `loop` / `seamless` / `seamless_loop` is on, still emit this Finish prompt as clip N. The Loop prompt after it is what returns to clip 1.

## Loop — return to Clip 1

Only when requested. Continue from clip N toward clip 1's opening **already in motion**. Do not reconstruct a still or “return to the opening pose”. Cite the dump labels that clip needs (often clip 1's opening identity / place).

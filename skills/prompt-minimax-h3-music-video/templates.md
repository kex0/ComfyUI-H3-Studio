# Music Video clip templates (Ref2VA)

Duration `D.DDD` = **snapped** per-clip length (10.00s requested → `10.125`). Window `T0–T1` matches the CLIP `time:` line.

Write identity in **each CLIP's** `subject_definitions`. Cite only the dump stills that CLIP needs. The node loads exactly those Picture / Video / builder-Audio tags (`<Audio 1>` is the song slice and does not trigger a builder-audio load). A top-level document `subject_definitions` is legacy fallback for older files whose clips omit one.

Six sections in this order, with colons as in the official MiniMax Ref2VA guide. Do not use T2VA `integrated_multimodal_description`. Do not write T2VA `at 0.00 seconds … is fully referenced`.

Use the **instrumental** template when CLIP `lyrics:` is `(instrumental)` or only `<instrumental>` stamps. Use the **sung** template for windows that contain timestamped vocal lines. A mixed CLIP (sung lines plus `[stamp] <instrumental>`) stays on the sung template: sing the vocal stamps, then cut at the rest (`At mm:ss.sss, the camera cuts. <Subject 1>'s lips stay closed.`) so the singer does not keep the same sung shot through the break.

Attached stills are identity/style references. Cite them **inside** `<Subject 1>` (or other Subject lines). Give `<Picture N>` its own definition row only when that image is a concrete first/key/last frame, edited keyframe, or storyboard/composition anchor. A Builder dump line ending ` (first frame)` is that CLIP 1 first-frame anchor (hybrid FL2VA start + Ref2VA identity): cite it inside Subject **and** as `<Picture N> is the first frame of [Shot 1], showing …`. CLIP 2+ never gets that row, but still cites the identity Picture inside `<Subject 1>` so the still loads. Each CLIP cites the dump stills it still uses; Advanced loads exactly those Picture / Video / builder-Audio tags (`<Audio 1>` is the song slice and does not trigger a builder-audio load).

## Shared audio lines (every clip)

One natural sentence. Sung clips also name the singing-voice role:

```text
<Audio 1> is the source-song slice covering T0–T1 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
```

Instrumental clips omit the singing-voice clause:

```text
<Audio 1> is the source-song slice covering T0–T1 of the master, reused as the complete soundtrack.
```

retention_analysis audio row (do not write `(Sx)` here):

```text
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
```

non_diegetic_music:

```text
non_diegetic_music: N/A
```

overall_soundscape: `<Audio 1>` reused as-is. No other sounds. Do not list forbidden SFX.

## Instrumental window (no vocal lines start in T0–T1)

Lips remain completely closed. No `<d>` singing. Subject can still move with the music.

### Clip 1 instrumental

```text
subject_definitions:
<Subject 1> is <identity> in <Picture 1>, <appearance extras from that still>.
<Audio 1> is the source-song slice covering 0.000–D.DDD of the master, reused as the complete soundtrack.
summary:
[reference generation + audio reuse] <Subject 1> in <opening world> through an instrumental stretch of <Audio 1>. Lips stay closed.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe from the reference pictures are retained.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is in a live-action, cinematic music-video style. [Shot 1] The scene opens: <exact visible start and crop>. <Subject 1>'s lips stay closed.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A
```

When the dump marks that still `(first frame)`, add a Picture row and open Shot 1 on it:

```text
<Picture 1> is the first frame of [Shot 1], showing <exact visible crop, pose, and place>.
```

`summary` prefix includes `keyframe completion`. Shot 1 must match the still; later shots in CLIP 1 may cut. Unmarked stills stay inside the Subject line only.

### Clip k instrumental (Continue)

```text
subject_definitions:
<Subject 1> is <same identity> in <Picture 1>, <same appearance extras>.
<Audio 1> is the source-song slice covering T0–T1 of the master, reused as the complete soundtrack.
summary:
[video continuation + reference generation + audio reuse] <Subject 1> continues from the previous clip into <opening world>. Lips stay closed.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip with no restart.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is in a live-action, cinematic music-video style. [Shot 1] <Subject 1> is already in the previous clip's ending space. <Subject 1>'s lips stay closed.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A
```

If no stills are attached, drop `in <Picture N>` from the Subject line and use `[video continuation + audio reuse]` on Continue clips.

## Sung window

The visible subject sings the CLIP `lyrics:` in lip sync with `<Audio 1>`. Exact words inside `<d>[Language] ...</d>` from the confirmed LRC. Sustained vowels marked as `~time~` / `~tiiiiiime~` in confirm expand in `<d>` only (skeleton keeps the mark) and get a held-vowel lip cue. At a join, `lyrics:` may be a prefix or suffix because `<Audio 1>` includes the continuation head. Never restore dropped crumbs. Copy every sung skeleton lyric into its own `<d>`. The filler packs those tags into a scaffold take and cuts only at `<instrumental>`. After fill, the LLM directs the music video: timed `[Shot N]` cuts, new environments only on a cut, mic or empty hands committed per shot.

If this is the first sung clip after instrumentals, singing begins with that first timestamped line — not at the start of the song and not as a pose reset.

### Clip 1 sung

```text
subject_definitions:
<Subject 1> is <identity> in <Picture 1>, <appearance extras from that still>.
<Audio 1> is the source-song slice covering 0.000–D.DDD of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[reference generation + audio reuse] <Subject 1> (S1) sings the lyric window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe from the reference pictures are retained.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is in a live-action, cinematic music-video style. [Shot 1] The scene opens: <exact visible start and crop>. <Subject 1> (S1) is already in this space. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[Language] <first line></d>. [Shot 2] At mm:ss.sss, the camera cuts. <new crop or world only if this is a cut>. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[Language] <next line></d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A
```

Same dump `(first frame)` Picture row and Shot 1 lock as CLIP 1 instrumental. Singing may start after that opening still; do not describe a different first pose.

### Clip k sung (Continue)

```text
subject_definitions:
<Subject 1> is <same identity> in <Picture 1>, <same appearance extras>.
<Audio 1> is the source-song slice covering T0–T1 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip with no restart.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is in a live-action, cinematic music-video style. [Shot 1] <Subject 1> (S1) is already in the previous clip's ending space; there is no pose reset and no new opening beat. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[Language] <overlap / first line></d>. [Shot 2] At mm:ss.sss, the camera cuts. <new world only here>. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[Language] <next line></d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A
```

Cite extra stills as `<Picture 2>` … `<Picture 9>` inside the same Subject line. On CLIP 1 only, a dump `(first frame)` still also gets `<Picture N> is the first frame of [Shot 1], showing …`. Do not write T2VA `at 0.00 seconds … the first frame of [Shot 1] is fully referenced`. CLIP 2+ does not reopen on that still. Clip N uses the matching Continue shape (sung or instrumental). Keep moving; do not freeze or “end on a pose.”

The filler does not pick mic, dance, or worlds. After fill, rewrite `summary` / `detailed_description` as the music-video direction: timed cuts, dressed sets, committed per-shot business (wireless mic at the mouth **or** dancing with empty hands — never both in one shot), new environments only after `the camera cuts`. Never write `The space becomes`. Never write `sometimes`. Never leave a shot that only restates the plan.

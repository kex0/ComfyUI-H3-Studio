# ComfyUI-H3-Studio

With this extension you can create videos of any length with MiniMax H3 in ComfyUI, including seamlessly looping videos and full music videos.

Typical path: **Builder** (plus **Lyrics Timer** for a song) → an [agent skill](skills/) (or **Local Prompter**) → **Auto Chain** or **Music Video** → optional **Face Refine**. Prefer the skills over the Local Prompter when you can — the prompts are higher quality.

Example workflows: [Auto Chain](example_workflows/auto_chain.json), [Music Video](example_workflows/music_video.json), [Face Refine](example_workflows/face_refine.json), [Clip Prompt Fixer](example_workflows/clip_prompt_fixer.json), [Auto Chain Clip Fixer](example_workflows/auto_chain_clip_fixer.json), [Music Video Clip Fixer](example_workflows/music_video_clip_fixer.json). Same graphs appear under **Workflow → Browse Templates → ComfyUI-H3-Studio**.

**Auto Chain Seamless Loop Example**<br>
*Output straight from the nodes (downscaled and heavily compressed so that it fits into GitHub's 10 MB limit)*

https://github.com/user-attachments/assets/f203a0dd-08e7-4c3d-899c-852ff48902f2

<details>

<summary>EXAMPLE MUSIC VIDEOS</summary>

### Outputs straight from the nodes (downscaled and heavily compressed so that they fit into GitHub's 10 MB limit)

Music source [MiniMax Music 3.0](https://www.minimax.io/blog/minimax-music-3-0-next-generation-open-weights-production-ready-versatile-music-model)

https://github.com/user-attachments/assets/d1cf9344-a2d0-449c-b13c-fcef5994cec7

<details>

<summary>Prompt (music-cloud-1)</summary>

Created with (older version of) [agent skill](skills/)

```
H3 Studio prompt
mode: music_video
duration: 10.125
segments: 28

## Clip 1 — Start
time: 0.000-9.042
duration_seconds: 10.125
slice: 0.000
audio: 0.000-10.125
lyrics: [00:00.529-00:04.784] ~Hmmm~
[00:06.815-00:08.578] ~Hmm~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Picture 1> is the first frame of [Shot 1], showing the visible crop, pose, wardrobe, and place in that still.
<Audio 1> is the source-song slice covering 0.000-10.125 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[keyframe completion + reference generation + audio reuse] <Subject 1> (S1) opens on <Picture 1> and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe from the reference pictures are retained.
<Picture 1> ([Shot 1] first frame): fully_preserved - crop, pose, wardrobe, and place match the still, then the performance begins.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] The scene opens on <Picture 1>: the same crop, pose, wardrobe, and place. No other people. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Hmmm</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:06.815, the camera cuts. Neon wet rooftop at night, medium shot. <Subject 1> holds a wireless microphone at the mouth. Cyan cloud-particle type. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Hmm</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 2 — Continue
time: 9.042-16.833
duration_seconds: 10.125
slice: 7.792
audio: 7.792-17.917
lyrics: [00:10.362-00:12.417] Upload my heart to the cloud tonight
[00:14.882-00:17.120] Save every spark of neon light
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 7.792-17.917 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the neon rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. [Shot 2] At 00:02.570, the camera cuts. Glass server hall, medium shot. Hands stay on the microphone. Heart-upload holograms rise. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Upload my heart to the cloud tonight</d>. [Shot 3] At 00:07.090, the camera cuts. Same hall, wider. Hands stay on the microphone. Neon spark sprites. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save every spark of neon light</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 3 — Continue
time: 16.833-24.625
duration_seconds: 10.125
slice: 15.583
audio: 15.583-25.708
lyrics: [00:15.583-00:17.120] ARK of neon light
[00:18.181-00:20.320] If this body starts to fade away
[00:20.745-00:23.939] Let my code keep dancing in the data stream
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 15.583-25.708 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's server-hall crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ARK of neon light</d>. [Shot 2] At 00:02.598, the camera cuts. Face close-up, same hall light. Hands stay on the microphone. Voxel dust around the body, never across the face. The face stays undistorted. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] If this body starts to fade away</d>. [Shot 3] At 00:05.162, the camera cuts. Endless data-corridor. <Subject 1> dances with empty hands. No microphone. Binary ribbons wrap the body. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Let my code keep dancing in the data stream</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 4 — Continue
time: 24.625-31.708
duration_seconds: 9.417
slice: 23.375
audio: 23.375-32.792
lyrics: [00:23.557-00:23.939] stream
[00:25.831-00:26.895] ~Staaaaay~
[00:28.262-00:29.760] Cloud copy of me
[00:30.321-00:32.160] Living on when these bones finally break free
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 23.375-32.792 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the data-corridor dance crop with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] stream</d>. [Shot 2] At 00:02.456, the camera cuts. Face close-up in the corridor. <Subject 1> holds a wireless microphone at the mouth. Stay-glyph rings around the frame, not the face. The face stays undistorted. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Staaaaay</d>. <Subject 1> holds the sustained vowel. [Shot 3] At 00:04.887, the camera cuts. Rooftop LED wall, medium shot. Hands stay on the microphone. CLOUD COPY title cards. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>. [Shot 4] At 00:06.946, the camera cuts. Wider rooftop. Hands stay on the microphone. Skeleton-wireframe graphics behind <Subject 1>, not on the skin. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Living on when these bones finally break free</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 5 — Continue
time: 31.708-38.792
duration_seconds: 9.417
slice: 30.458
audio: 30.458-39.875
lyrics: [00:30.458-00:32.160] ING on when these bones finally break free
[00:32.704-00:33.631] Every joke, every scar
[00:33.846-00:35.360] Every cheap memory we made
[00:35.725-00:37.159] Save it, save it
[00:37.582-00:39.116] Cloud copy of me
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 30.458-39.875 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ING on when these bones finally break free</d>. [Shot 2] At 00:02.246, the camera cuts. Medium rooftop. Hands stay on the microphone. Joke-caption stickers orbit. No scar close-up. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every joke, every scar</d>. [Shot 3] At 00:03.388, the camera cuts. Same rooftop, slightly tighter. Hands stay on the microphone. Cheap polaroids float outside the crop. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every cheap memory we made</d>. [Shot 4] At 00:05.267, the camera cuts. Hands stay on the microphone. SAVE IT stamps hammer the LED. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>. [Shot 5] At 00:07.124, the camera cuts. Hands stay on the microphone. Duplicate-self holograms. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 6 — Continue
time: 38.792-45.875
duration_seconds: 9.417
slice: 37.542
audio: 37.542-46.958
lyrics: [00:37.582-00:39.116] Cloud copy of me
[00:39.616-00:41.570] If the screen goes dark, I’m still in the machine
[00:41.983-00:42.977] Every glitch, every dream
[00:43.137-00:44.743] Every version you ever did see
[00:45.089-00:46.559] Save it, save it
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 37.542-46.958 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>. [Shot 2] At 00:02.074, the camera cuts. LED wall blacks out. Hands stay on the microphone. Circuit traces remain. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] If the screen goes dark, I’m still in the machine</d>. [Shot 3] At 00:04.441, the camera cuts. RGB-split city alley, medium. Hands stay on the microphone. Glitch blocks, not on the face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every glitch, every dream</d>. [Shot 4] At 00:05.595, the camera cuts. Version-stack mirrors beside <Subject 1>. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every version you ever did see</d>. [Shot 5] At 00:07.547, the camera cuts. Hands stay on the microphone. SAVE IT UI. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 7 — Continue
time: 45.875-50.833
duration_seconds: 7.292
slice: 44.625
audio: 44.625-51.917
lyrics: [00:45.089-00:46.559] Save it, save it
[00:47.116-00:50.825] Tag every laugh in a secret folder
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 44.625-51.917 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's alley crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>. [Shot 2] At 00:02.491, the camera cuts. Infinite file-vault, medium. Hands stay on the microphone. Laugh-tagged folders fly past. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Tag every laugh in a secret folder</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 8 — Continue
time: 50.833-55.083
duration_seconds: 6.583
slice: 49.583
audio: 49.583-56.167
lyrics: [00:50.063-00:50.825] folder
[00:51.890-00:55.404] Archive the nights we outran the thunder
[00:55.865-00:56.065] If the
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 49.583-56.167 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the file-vault crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] folder</d>. [Shot 2] At 00:02.307, the camera cuts. Storm rooftop. <Subject 1> dances with empty hands. No microphone. Lightning-archive bolts. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Archive the nights we outran the thunder</d>. [Shot 3] At 00:06.282, the camera cuts. Rusted server farm. <Subject 1> holds a wireless microphone at the mouth. Gray oxide dust in the air, not on the face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] If the</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 9 — Continue
time: 55.083-60.042
duration_seconds: 7.292
slice: 53.833
audio: 53.833-61.125
lyrics: [00:54.139-00:55.404] the thunder
[00:55.865-01:00.733] If the wiring turns to rust and ~graaaaay~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 53.833-61.125 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the rusted server-farm crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] the thunder</d>. [Shot 2] At 00:02.032, the camera cuts. Face close-up in the farm. Hands stay on the microphone. Gray grade on the walls only. The face stays undistorted. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] If the wiring turns to rust and graaaaay</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 10 — Continue
time: 60.042-64.292
duration_seconds: 6.583
slice: 58.792
audio: 58.792-65.375
lyrics: [00:59.171-01:00.733] and ~graaaaay~
[01:01.335-01:04.589] Hit restore… press replay
[01:04.809-01:14.562] <instrumental>
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 58.792-65.375 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's farm face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] and graaaaay</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:02.543, the camera cuts. Medium farm. Hands stay on the microphone. RESTORE / REPLAY HUD buttons smash in. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Hit restore… press replay</d>. [Shot 3] At 00:06.017, the camera cuts. <Subject 1>'s lips stay closed. Empty-hands dance in the same farm. Hard strobes.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 11 — Continue
time: 64.292-67.125
duration_seconds: 5.167
slice: 63.042
audio: 63.042-68.208
lyrics: [01:03.082-01:04.589] press replay
[01:04.809-01:14.562] <instrumental>
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 63.042-68.208 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's farm dance crop with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] press replay</d>. [Shot 2] At 00:01.767, the camera cuts. <Subject 1>'s lips stay closed. Wider farm. Empty hands. Replay-glitch ribbons.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 12 — Continue
time: 67.125-73.500
duration_seconds: 8.708
slice: 65.875
audio: 65.875-74.583
lyrics: [01:04.809-01:14.562] <instrumental>
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 65.875-74.583 of the master, reused as the complete soundtrack.
summary:
[video continuation + reference generation + audio reuse] <Subject 1> dances a closed-lip instrumental stretch of <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> is already in the previous clip's wide farm crop with empty hands. <Subject 1>'s lips stay closed. Dance continues. [Shot 2] At 00:03.000, the camera cuts. Orbiting wide. Empty hands. Lips stay closed. Neon ribbons. [Shot 3] At 00:06.000, the camera cuts. Medium. Empty hands. Lips stay closed. Hair whip, spark graphics.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 13 — Continue
time: 73.500-81.292
duration_seconds: 10.125
slice: 72.250
audio: 72.250-82.375
lyrics: [01:04.809-01:14.562] <instrumental>
[01:14.737-01:16.261] Cloud copy of me
[01:16.739-01:18.728] Living on when these bones finally break free
[01:19.121-01:20.080] Every joke, every scar
[01:20.262-01:21.990] Every cheap memory we made
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 72.250-82.375 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> is already in the previous clip's farm medium crop with empty hands; there is no pose reset. <Subject 1>'s lips stay closed. [Shot 2] At 00:02.487, the camera cuts. Rooftop LED, medium. <Subject 1> holds a wireless microphone at the mouth. CLOUD COPY cards. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>. [Shot 3] At 00:04.489, the camera cuts. Wider rooftop. Hands stay on the microphone. Wireframe-bone graphics behind <Subject 1>. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Living on when these bones finally break free</d>. [Shot 4] At 00:06.871, the camera cuts. Joke-caption orbit. Hands stay on the microphone. No scar close-up. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every joke, every scar</d>. [Shot 5] At 00:08.012, the camera cuts. Polaroid swarm. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every cheap memory we made</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 14 — Continue
time: 81.292-88.375
duration_seconds: 9.417
slice: 80.042
audio: 80.042-89.458
lyrics: [01:20.262-01:21.990] Every cheap memory we made
[01:22.217-01:23.695] Save it, save it
[01:24.022-01:25.529] Cloud copy of me
[01:26.047-01:27.998] If the screen goes dark, I’m still in the machine
[01:28.421-01:29.374] Every glitch, every dream
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 80.042-89.458 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every cheap memory we made</d>. [Shot 2] At 00:02.175, the camera cuts. Hands stay on the microphone. SAVE IT UI. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>. [Shot 3] At 00:03.980, the camera cuts. Duplicate holograms. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>. [Shot 4] At 00:06.005, the camera cuts. Black LED wall. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] If the screen goes dark, I’m still in the machine</d>. [Shot 5] At 00:08.379, the camera cuts. RGB alley. Hands stay on the microphone. Glitch blocks off-face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every glitch, every dream</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 15 — Continue
time: 88.375-91.917
duration_seconds: 5.875
slice: 87.125
audio: 87.125-93.000
lyrics: [01:27.133-01:27.998] I’m still in the machine
[01:28.421-01:29.374] Every glitch, every dream
[01:29.579-01:31.267] Every version you ever did see
[01:31.538-01:32.691] Save it, save it
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 87.125-93.000 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the RGB alley with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] I’m still in the machine</d>. [Shot 2] At 00:01.296, the camera cuts. Hands stay on the microphone. Glitch blocks. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every glitch, every dream</d>. [Shot 3] At 00:02.454, the camera cuts. Version mirrors. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every version you ever did see</d>. [Shot 4] At 00:04.413, the camera cuts. SAVE IT stamps. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 16 — Continue
time: 91.917-94.750
duration_seconds: 5.167
slice: 90.667
audio: 90.667-95.833
lyrics: [01:30.684-01:31.267] did see
[01:31.538-01:32.691] Save it, save it
[01:32.824-01:35.833] OO
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 90.667-95.833 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's alley crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] did see</d>. [Shot 2] At 00:00.871, the camera cuts. Hands stay on the microphone. SAVE IT stamps. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>. [Shot 3] At 00:02.157, the camera cuts. Face close-up, alley light. Hands stay on the microphone. Soft bloom, undistorted face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] OO</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 17 — Continue
time: 94.750-99.708
duration_seconds: 7.292
slice: 93.500
audio: 93.500-100.792
lyrics: [01:33.500-01:40.379] ~Ooooh~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 93.500-100.792 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Ooooh</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 18 — Continue
time: 99.708-105.375
duration_seconds: 8.000
slice: 98.458
audio: 98.458-106.458
lyrics: [01:41.591-01:43.295] Even the crashes,
[01:43.455-01:45.660] the late-night confessions
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 98.458-106.458 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. [Shot 2] At 00:03.133, the camera cuts. Dim neon bedroom, medium. Hands stay on the microphone. Crash-log type on the walls. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Even the crashes,</d>. [Shot 3] At 00:04.997, the camera cuts. Same bedroom. Hands stay on the microphone. Late-night UI. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] the late-night confessions</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 19 — Continue
time: 105.375-109.625
duration_seconds: 6.583
slice: 104.125
audio: 104.125-110.708
lyrics: [01:44.297-01:45.660] confessions
[01:46.946-01:50.217] The parts of me I never learned to mention
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 104.125-110.708 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the neon bedroom with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] confessions</d>. [Shot 2] At 00:02.821, the camera cuts. Same bedroom, tighter. Hands stay on the microphone. Hidden-layer folders. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] The parts of me I never learned to mention</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 20 — Continue
time: 109.625-117.417
duration_seconds: 10.125
slice: 108.375
audio: 108.375-118.500
lyrics: [01:48.411-01:50.217] never learned to mention
[01:50.515-01:54.383] Don’t let the silence swallow me whole
[01:55.582-01:57.848] Keep a ghost in the glow…
[01:58.206-01:58.466] So
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 108.375-118.500 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the bedroom crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] never learned to mention</d>. [Shot 2] At 00:02.140, the camera cuts. Black void with a single practical. Hands stay on the microphone. Falling ash off-face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Don’t let the silence swallow me whole</d>. [Shot 3] At 00:07.207, the camera cuts. Face close-up in phosphor glow. Hands stay on the microphone. Ghost double behind, undistorted face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Keep a ghost in the glow…</d>. [Shot 4] At 00:09.831, the camera cuts. Same close-up. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] So</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 21 — Continue
time: 117.417-122.375
duration_seconds: 7.292
slice: 116.167
audio: 116.167-123.458
lyrics: [01:56.184-01:57.848] ghost in the glow…
[01:58.206-02:00.211] So I never go
[02:01.075-02:02.680] Cloud copy of me
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 116.167-123.458 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the phosphor face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ghost in the glow…</d>. [Shot 2] At 00:02.039, the camera cuts. Same close-up. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] So I never go</d>. [Shot 3] At 00:04.908, the camera cuts. Rooftop LED encore, medium. Hands stay on the microphone. CLOUD COPY cards. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 22 — Continue
time: 122.375-129.458
duration_seconds: 9.417
slice: 121.125
audio: 121.125-130.542
lyrics: [02:01.125-02:02.680] OUD copy of me
[02:03.662-02:06.888] Still laughing somewhere in the binary
[02:08.333-02:10.312] Every joke, every scar
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 121.125-130.542 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the encore rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] OUD copy of me</d>. [Shot 2] At 00:02.537, the camera cuts. Binary rain around <Subject 1>. Hands stay on the microphone. Laughing-emoji bursts, not a scar CU. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Still laughing somewhere in the binary</d>. [Shot 3] At 00:07.208, the camera cuts. Joke-caption orbit. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every joke, every scar</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 23 — Continue
time: 129.458-135.833
duration_seconds: 8.708
slice: 128.208
audio: 128.208-136.917
lyrics: [02:08.333-02:10.312] Every joke, every scar
[02:10.631-02:12.615] Every moment you saved for me
[02:14.153-02:16.565] Save it, save it
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 128.208-136.917 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the encore rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every joke, every scar</d>. [Shot 2] At 00:02.423, the camera cuts. Timeline ticks. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Every moment you saved for me</d>. [Shot 3] At 00:05.945, the camera cuts. SAVE IT hammers. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it, save it</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 24 — Continue
time: 135.833-140.792
duration_seconds: 7.292
slice: 134.583
audio: 134.583-141.875
lyrics: [02:14.595-02:16.565] it, save it
[02:18.435-02:18.656] ~Heeey~
[02:20.313-02:21.263] Cloud copy of me
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 134.583-141.875 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the encore rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] it, save it</d>. [Shot 2] At 00:03.852, the camera cuts. Face close-up. Hands stay on the microphone. The face stays undistorted. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Heeeeeeey</d>. <Subject 1> holds the sustained vowel. [Shot 3] At 00:05.730, the camera cuts. Medium encore. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 25 — Continue
time: 140.792-145.750
duration_seconds: 7.292
slice: 139.542
audio: 139.542-146.833
lyrics: [02:20.313-02:21.263] Cloud copy of me
[02:22.293-02:25.837] When the lights go out, I’ll still be in the machine
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 139.542-146.833 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the encore rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. [Shot 2] At 00:00.771, the camera cuts. City blackout, medium. Hands stay on the microphone. One remaining machine-core glow. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Cloud copy of me</d>. [Shot 3] At 00:02.751, the camera cuts. City blackout, medium. Hands stay on the microphone. One remaining machine-core glow. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] When the lights go out, I’ll still be in the machine</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 26 — Continue
time: 145.750-152.833
duration_seconds: 9.417
slice: 144.500
audio: 144.500-153.917
lyrics: [02:24.516-02:25.837] in the machine
[02:26.638-02:29.856] Dancing in the code that you still believe
[02:32.727-02:33.336] Save it…
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 144.500-153.917 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the blackout crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] in the machine</d>. [Shot 2] At 00:02.138, the camera cuts. Inside a giant code tunnel. <Subject 1> dances with empty hands. No microphone. Glyph floor. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Dancing in the code that you still believe</d>. [Shot 3] At 00:08.227, the camera cuts. Same tunnel, medium. Empty hands. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it…</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 27 — Continue
time: 152.833-160.625
duration_seconds: 10.125
slice: 151.583
audio: 151.583-161.708
lyrics: [02:32.727-02:33.336] Save it…
[02:34.519-02:35.247] save me
[02:36.813-02:37.279] Save me
[02:38.236-02:40.924] Striver
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 151.583-161.708 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the code-tunnel crop with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. [Shot 2] At 00:01.144, the camera cuts. Face close-up in the tunnel. <Subject 1> holds a wireless microphone at the mouth. The face stays undistorted. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save it…</d>. [Shot 3] At 00:02.936, the camera cuts. Same close-up. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] save me</d>. [Shot 4] At 00:05.230, the camera cuts. Wider tunnel. Hands stay on the microphone. STRIVER chrome type. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Save me</d>. [Shot 5] At 00:06.653, the camera cuts. Wider tunnel. Hands stay on the microphone. STRIVER chrome type. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Striver</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 28 — Continue
time: 160.625-165.208
duration_seconds: 5.875
slice: 159.375
audio: 159.375-165.250
lyrics: [02:39.375-02:40.924] RIVER
[02:41.945-02:44.277] to mind a fate talk me
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, long hair slicked back, pink latex leggings, short open cyan jacket with puffy sleeves, and pink string bikini top.
<Audio 1> is the source-song slice covering 159.375-165.250 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues from the previous clip and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the wide tunnel crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] RIVER</d>. [Shot 2] At 00:02.570, the camera cuts. Same tunnel, moving. Hands stay on the microphone. Scrambled subtitle graphics. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] to mind a fate talk me</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A
```

</details>


https://github.com/user-attachments/assets/03795595-4020-4a92-93d9-c26c0ffded5a

https://github.com/user-attachments/assets/8cd51bbf-c19f-410e-b87d-61103815e1bd

<details>

<summary>Prompt (music-poprock-1)</summary>

Created with (older version of) [agent skill](skills/)

```
H3 Studio prompt
mode: music_video
duration: 10.125
segments: 31

## Clip 1 — Start
time: 0.000-7.625
duration_seconds: 8.708
slice: 0.000
audio: 0.000-8.708
lyrics: [00:00.481-00:02.935] We were the kind who never stayed in one place,
[00:03.213-00:05.520] Running through the city with the wind in our face.
[00:05.841-00:08.400] Trading every secret like a currency of trust,
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Picture 1> is the first frame of [Shot 1], showing the visible crop, pose, wardrobe, and place in that still.
<Audio 1> is the source-song slice covering 0.000-8.708 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[keyframe completion + reference generation + audio reuse] <Subject 1> (S1) opens on <Picture 1> and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe from the reference pictures are retained.
<Picture 1> ([Shot 1] first frame): fully_preserved - crop, pose, wardrobe, and place match the still, then the performance begins.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] The scene opens on <Picture 1>: the same crop, pose, wardrobe, and place. No other people. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] We were the kind who never stayed in one place,</d>. [Shot 2] At 00:03.213, the camera cuts. Neon wet city street at night, medium shot. <Subject 1> holds a wireless microphone at the mouth. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Running through the city with the wind in our face.</d>. [Shot 3] At 00:05.841, the camera cuts. Wider on the same street. Hands stay on the microphone. 3D currency-coin graphics shatter into light. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Trading every secret like a currency of trust,</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 2 — Continue
time: 7.625-15.417
duration_seconds: 10.125
slice: 6.375
audio: 6.375-16.500
lyrics: [00:06.375-00:08.400] ery secret like a currency of trust,
[00:08.732-00:11.363] Didn’t know the moment when it started turning dust.
[00:11.720-00:16.033] I still scroll back just to see your name,
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 6.375-16.500 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues on the night street with the microphone and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the neon wet city street from the previous clip, wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ery secret like a currency of trust,</d>. [Shot 2] At 00:02.357, the camera cuts. Face close-up on the same street. Dust-particle VFX. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Didn’t know the moment when it started turning dust.</d>. [Shot 3] At 00:05.345, the camera cuts. Medium shot, floating phone-screen motion graphics. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] I still scroll back just to see your name,</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 3 — Continue
time: 15.417-21.083
duration_seconds: 8.000
slice: 14.167
audio: 14.167-22.167
lyrics: [00:14.167-00:16.033] see your name,
[00:16.945-00:21.401] But the messages feel like another game.
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 14.167-22.167 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) continues with the microphone into a chat-thread graphic look and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's ending street crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] see your name,</d>. [Shot 2] At 00:02.778, the camera cuts. Dim hotel room, medium close-up. Hands stay on the microphone. Message-bubble motion graphics stack around <Subject 1>. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] But the messages feel like another game.</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 4 — Continue
time: 21.083-25.333
duration_seconds: 6.583
slice: 19.833
audio: 19.833-26.417
lyrics: [00:19.833-00:21.401] her game.
[00:22.485-00:26.192] Forever friends – we promised it one day,
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 19.833-26.417 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) hits the chorus on a rooftop stage and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's hotel crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] her game.</d>. [Shot 2] At 00:02.652, the camera cuts. Rooftop concert LED wall, medium shot. Hands stay on the microphone. Giant title cards read FOREVER FRIENDS. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Forever friends – we promised it one day,</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 5 — Continue
time: 25.333-32.417
duration_seconds: 9.417
slice: 24.083
audio: 24.083-33.500
lyrics: [00:24.349-00:26.192] we promised it one day,
[00:26.711-00:32.007] And we haven’t seen each other since the following ~daaaaay~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 24.083-33.500 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) holds the chorus on the rooftop and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the rooftop LED stage with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] we promised it one day,</d>. [Shot 2] At 00:02.628, the camera cuts. Face close-up on the rooftop. Hands stay on the microphone. Calendar pages tear away as 3D type. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] And we haven’t seen each other since the following daaaaay</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 6 — Continue
time: 32.417-37.375
duration_seconds: 7.292
slice: 31.167
audio: 31.167-38.458
lyrics: [00:31.167-00:32.007] ~daaaaay~
[00:33.377-00:35.301] Guess forever’s quicker than we thought it’d be,
[00:35.726-00:37.963] Faded like a sticker on a teenage diary.
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 31.167-38.458 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) stays on the rooftop then cuts to a diary-graphic look and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's rooftop face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] daaaaay</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:02.210, the camera cuts. Medium rooftop shot. Hands stay on the microphone. Clock-hand motion graphics spin. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Guess forever’s quicker than we thought it’d be,</d>. [Shot 3] At 00:04.559, the camera cuts. Teenage-bedroom set, sticker-sheet VFX peeling off the walls. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Faded like a sticker on a teenage diary.</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 7 — Continue
time: 37.375-44.458
duration_seconds: 9.417
slice: 36.125
audio: 36.125-45.542
lyrics: [00:36.125-00:37.963] ike a sticker on a teenage diary.
[00:38.418-00:45.027] Yeah, we said we’d never ~chaaaaaaaaange~ but life got in the way.
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 36.125-45.542 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) dances the long chorus line empty-handed and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's bedroom crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ike a sticker on a teenage diary.</d>. [Shot 2] At 00:02.293, the camera cuts. Empty warehouse with laser grids. <Subject 1> dances with empty hands. No microphone. Color-shift motion graphics wrap the body. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Yeah, we said we’d never chaaaaaaaaange but life got in the way.</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 8 — Continue
time: 44.458-50.833
duration_seconds: 8.708
slice: 43.208
audio: 43.208-51.917
lyrics: [00:43.208-00:45.027] but life got in the way.
[00:46.305-00:48.759] Now you’re a highlight in a story I outgrew,
[00:49.042-00:51.256] A blurry little moment in a world that was new.
[00:51.498-00:51.819] Funny
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 43.208-51.917 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) returns to a microphone story look and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's warehouse dance crop with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] but life got in the way.</d>. [Shot 2] At 00:03.097, the camera cuts. Highlight-reel collage of city nights, medium shot. <Subject 1> holds a wireless microphone at the mouth. Story-bar UI graphics wipe across. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Now you’re a highlight in a story I outgrew,</d>. [Shot 3] At 00:05.834, the camera cuts. Soft-focus night street, medium close-up. Hands stay on the microphone. Blur-bloom VFX. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] A blurry little moment in a world that was new.</d> then <d>[English] Funny</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 9 — Continue
time: 50.833-55.792
duration_seconds: 7.292
slice: 49.583
audio: 49.583-56.875
lyrics: [00:49.583-00:51.256] ttle moment in a world that was new.
[00:51.498-00:54.030] Funny how the rhythm doesn’t hit the same beat,
[00:54.192-00:56.875] When the people that you dance with walk off down another stre
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 49.583-56.875 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) dances the street lyric empty-handed and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's night-street crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ttle moment in a world that was new.</d>. [Shot 2] At 00:01.915, the camera cuts. Club-stage medium shot. Hands stay on the microphone. Waveform motion graphics miss the downbeat. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Funny how the rhythm doesn’t hit the same beat,</d>. [Shot 3] At 00:04.609, the camera cuts. Empty downtown crosswalk at night. <Subject 1> dances with empty hands. No microphone. Arrow-trail graphics peel away down the street. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] When the people that you dance with walk off down another stre</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 10 — Continue
time: 55.792-60.750
duration_seconds: 7.292
slice: 54.542
audio: 54.542-61.833
lyrics: [00:54.542-00:56.885] eople that you dance with walk off down another street.
[00:57.280-01:01.230] I could call you up, but what would I say?
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 54.542-61.833 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) picks the microphone back up for the phone lyric and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's crosswalk crop with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] eople that you dance with walk off down another street.</d>. [Shot 2] At 00:02.738, the camera cuts. Phone-booth neon, medium close-up. <Subject 1> holds a wireless microphone at the mouth. Dial-pad 3D type. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] I could call you up, but what would I say?</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 11 — Continue
time: 60.750-67.125
duration_seconds: 8.708
slice: 59.500
audio: 59.500-68.208
lyrics: [00:59.506-01:01.230] what would I say?
[01:01.878-01:07.678] “Hey, remember us?”—it feels too far ~aaaaaaway~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 59.500-68.208 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] Face close-up: <Subject 1> (S1) sings the held away line in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's phone-booth crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] what would I say?</d>. [Shot 2] At 00:02.378, the camera cuts. Face close-up, same booth light. Hands stay on the microphone. Prismatic refraction VFX shimmers across the background, bending light without distorting <Subject 1>'s face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] “Hey, remember us?”—it feels too far aaaaaaway</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 12 — Continue
time: 67.125-71.375
duration_seconds: 6.583
slice: 65.875
audio: 65.875-72.458
lyrics: [01:05.875-01:07.678] way.
[01:08.106-01:11.863] Forever friends – we promised it one day,
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 65.875-72.458 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) returns to the chorus on an arena stage and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] way.</d>. [Shot 2] At 00:02.231, the camera cuts. Arena stage in smoke, medium shot. Hands stay on the microphone. A digital glitch VFX effect flickers across the background, creating static artifacts without distorting <Subject 1>'s face. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Forever friends – we promised it one day,</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 13 — Continue
time: 71.375-77.750
duration_seconds: 8.708
slice: 70.125
audio: 70.125-78.833
lyrics: [01:10.125-01:11.863] we promised it one day,
[01:12.370-01:18.430] And we haven’t seen each other since the following ~daaaaay~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 70.125-78.833 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) holds the arena chorus and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the arena stage with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] we promised it one day,</d>. [Shot 2] At 00:02.245, the camera cuts. Face close-up on the arena. Hands stay on the microphone. Calendar-rip VFX. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] And we haven’t seen each other since the following daaaaay</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 14 — Continue
time: 77.750-82.708
duration_seconds: 7.292
slice: 76.500
audio: 76.500-83.792
lyrics: [01:16.724-01:18.430] ~daaaaay~
[01:19.027-01:21.005] Guess forever’s quicker than we thought it’d be,
[01:21.358-01:23.664] Faded like a sticker on a teenage diary.
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 76.500-83.792 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) stays on the arena and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's arena face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] daaaaay</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:02.527, the camera cuts. Medium arena shot. Hands stay on the microphone. Clock graphics. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Guess forever’s quicker than we thought it’d be,</d>. [Shot 3] At 00:04.858, the camera cuts. Sticker-sheet VFX over the same arena. Hands stay on the microphone. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Faded like a sticker on a teenage diary.</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 15 — Continue
time: 82.708-89.792
duration_seconds: 9.417
slice: 81.458
audio: 81.458-90.875
lyrics: [01:21.458-01:23.664] ded like a sticker on a teenage diary.
[01:24.049-01:30.649] Yeah, we said we’d never ~chaaaaaaaaange~ but life got in the way.
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 81.458-90.875 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) dances the change line empty-handed and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the arena with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ded like a sticker on a teenage diary.</d>. [Shot 2] At 00:02.591, the camera cuts. Empty warehouse lasers. <Subject 1> dances with empty hands. No microphone. Morphing color bars. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Yeah, we said we’d never chaaaaaaaaange but life got in the way.</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 16 — Continue
time: 89.792-92.625
duration_seconds: 5.167
slice: 88.542
audio: 88.542-93.708
lyrics: [01:28.763-01:30.649] but life got in the way.
[01:30.697-01:40.159] <instrumental>
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 88.542-93.708 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) finishes the lyric then cuts to a closed-lip instrumental dance.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's warehouse dance crop with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] but life got in the way.</d>. [Shot 2] At 00:02.155, the camera cuts. <Subject 1>'s lips stay closed. Wider warehouse. Empty hands. Hard strobes and 3D light ribbons. No other people.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 17 — Continue
time: 92.625-99.000
duration_seconds: 8.708
slice: 91.375
audio: 91.375-100.083
lyrics: [01:30.697-01:40.159] <instrumental>
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 91.375-100.083 of the master, reused as the complete soundtrack.
summary:
[video continuation + reference generation + audio reuse] <Subject 1> dances a closed-lip instrumental in the warehouse.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> is already in the previous clip's warehouse ending crop with empty hands. <Subject 1>'s lips stay closed. Dance continues. Particle trails. [Shot 2] At 00:03.000, the camera cuts. Wide warehouse. Empty hands. Lips stay closed. Camera orbits. Neon ribbons. [Shot 3] At 00:06.000, the camera cuts. Medium. Empty hands. Lips stay closed. Slow-motion hair whip with spark graphics.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 18 — Continue
time: 99.000-103.250
duration_seconds: 6.583
slice: 97.750
audio: 97.750-104.333
lyrics: [01:30.697-01:40.159] <instrumental>
[01:40.476-01:44.020] Maybe we just ran out of the same headline,
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 97.750-104.333 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] Closed-lip warehouse continues, then <Subject 1> (S1) sings the headline line in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> is already in the previous clip's warehouse medium crop with empty hands; there is no pose reset. <Subject 1>'s lips stay closed. [Shot 2] At 00:02.726, the camera cuts. Rooftop at dawn, medium close-up. <Subject 1> holds a wireless microphone at the mouth. Newspaper-headline motion graphics fly past. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Maybe we just ran out of the same headline,</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 19 — Continue
time: 103.250-110.333
duration_seconds: 9.417
slice: 102.000
audio: 102.000-111.417
lyrics: [01:42.138-01:44.020] of the same headline,
[01:45.705-01:51.213] And maybe that’s okay — stories shift over ~tiiiiiime~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 102.000-111.417 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) sings the time-hold on the rooftop in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the dawn rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] of the same headline,</d>. [Shot 2] At 00:03.705, the camera cuts. Face close-up on the rooftop. Hands stay on the microphone. Clock-face VFX melt. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] And maybe that’s okay — stories shift over tiiiiiime</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 20 — Continue
time: 110.333-114.583
duration_seconds: 6.583
slice: 109.083
audio: 109.083-115.667
lyrics: [01:49.150-01:51.213] ~tiiiiiime~
[01:51.516-01:55.292] Still I hope you’re smiling somewhere out there tonight,
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 109.083-115.667 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) sings the smile-tonight line in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's rooftop face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] tiiiiiime</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:02.433, the camera cuts. Wide rooftop under city lights. Hands stay on the microphone. Horizon-glow graphics. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Still I hope you’re smiling somewhere out there tonight,</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 21 — Continue
time: 114.583-120.958
duration_seconds: 8.708
slice: 113.333
audio: 113.333-122.042
lyrics: [01:53.333-01:55.292] ewhere out there tonight,
[01:55.957-02:01.552] Living loud, living free, living your own ~liiiiife~
[02:01.806-02:02.042] For
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 113.333-122.042 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) dances the living-loud line empty-handed and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the wide rooftop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ewhere out there tonight,</d>. [Shot 2] At 00:02.624, the camera cuts. Open highway at night. <Subject 1> dances with empty hands. No microphone. Freedom-type explosions. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Living loud, living free, living your own liiiiife</d> then <d>[English] For</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 22 — Continue
time: 120.958-125.208
duration_seconds: 6.583
slice: 119.708
audio: 119.708-126.292
lyrics: [01:59.708-02:01.552] own ~liiiiife~
[02:01.806-02:05.512] Forever friends – we promised it one day,
[02:06.045-02:06.286] And we
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 119.708-126.292 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) returns to the microphone for the last chorus and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the night highway with empty hands; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] own liiiiife</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:02.098, the camera cuts. Arena encore, medium shot. <Subject 1> holds a wireless microphone at the mouth. Title cards. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Forever friends – we promised it one day,</d> then <d>[English] And we</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 23 — Continue
time: 125.208-131.583
duration_seconds: 8.708
slice: 123.958
audio: 123.958-132.667
lyrics: [02:03.970-02:05.512] promised it one day,
[02:06.045-02:12.142] And we haven’t seen each other since the following ~daaaaay~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 123.958-132.667 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) holds the last chorus and sings this window in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already on the encore stage with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] promised it one day,</d>. [Shot 2] At 00:02.087, the camera cuts. Face close-up on the encore. Hands stay on the microphone. Calendar-rip VFX. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] And we haven’t seen each other since the following daaaaay</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 24 — Continue
time: 131.583-136.542
duration_seconds: 7.292
slice: 130.333
audio: 130.333-137.625
lyrics: [02:10.417-02:12.142] ~daaaaay~
[02:12.722-02:14.622] But the beat keeps moving and I’ll be okay,
[02:15.013-02:17.390] Even if our forever only lasted one day.
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 130.333-137.625 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) sings the beat-keeps-moving lines in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the encore face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] daaaaay</d>. <Subject 1> holds the sustained vowel. [Shot 2] At 00:02.389, the camera cuts. Medium encore. Hands stay on the microphone. Pulse-ring graphics. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] But the beat keeps moving and I’ll be okay,</d>. [Shot 3] At 00:04.680, the camera cuts. Wider encore. Hands stay on the microphone. One-day hourglass VFX. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Even if our forever only lasted one day.</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 25 — Continue
time: 136.542-142.208
duration_seconds: 8.000
slice: 135.292
audio: 135.292-143.292
lyrics: [02:15.295-02:17.390] if our forever only lasted one day.
[02:17.851-02:23.136] In other forces shell with the south flurry
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 135.292-143.292 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) sings the outro flurry ad-lib in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's encore wide with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] if our forever only lasted one day.</d>. [Shot 2] At 00:02.559, the camera cuts. Wind-tunnel set, medium shot. Hands stay on the microphone. Storm-map motion graphics. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] In other forces shell with the south flurry</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 26 — Continue
time: 142.208-145.042
duration_seconds: 5.167
slice: 140.958
audio: 140.958-146.125
lyrics: [02:21.154-02:23.136] the south flurry
[02:23.205-02:26.125] Win
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 140.958-146.125 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] Face close-up: <Subject 1> (S1) starts the Windyyy hold in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the wind-tunnel crop with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] the south flurry</d>. [Shot 2] At 00:02.247, the camera cuts. Face close-up in the wind tunnel. Hands stay on the microphone. Hair and wind streaks. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Win</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 27 — Continue
time: 145.042-150.708
duration_seconds: 8.000
slice: 143.792
audio: 143.792-151.792
lyrics: [02:23.792-02:31.792] indyyy
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 143.792-151.792 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) holds the Windyyy remnant in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's wind-tunnel face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] indyyy</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 28 — Continue
time: 150.708-153.542
duration_seconds: 5.167
slice: 149.458
audio: 149.458-154.625
lyrics: [02:31.875-02:34.368] Oooh
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 149.458-154.625 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) sings the Oooh in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the wind-tunnel face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Oooh</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 29 — Continue
time: 153.542-161.333
duration_seconds: 10.125
slice: 152.292
audio: 152.292-162.417
lyrics: [02:32.292-02:42.417] ooh flurry windyyy
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 152.292-162.417 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) dances the long flurry line empty-handed and sings in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the previous clip's wind-tunnel face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] ooh flurry windyyy</d>.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 30 — Continue
time: 161.333-169.125
duration_seconds: 10.125
slice: 160.083
audio: 160.083-170.208
lyrics: [02:40.083-02:42.470] yyy
[02:42.685-02:46.625] Oooh flurry ~wiiiiindyyy~
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 160.083-170.208 of the master, reused as the complete soundtrack, and the singing-voice reference for <Subject 1> (S1).
summary:
[video continuation + reference generation + audio reuse] <Subject 1> (S1) sings the last flurry hold in sync with <Audio 1>.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> (S1) is already in the wind-tunnel face close-up with the wireless microphone at the mouth; there is no pose reset. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] yyy</d>. [Shot 2] At 00:02.602, the camera cuts. Wide wind-tunnel. <Subject 1> dances with empty hands. No microphone. Cyclone graphics. Mouth and face follow <Audio 1>. <Subject 1> (S1) sings, <d>[English] Oooh flurry wiiiiindyyy</d>. <Subject 1> holds the sustained vowel.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A

## Clip 31 — Continue
time: 169.125-170.917
duration_seconds: 5.167
slice: 167.875
audio: 167.875-173.042
lyrics: (instrumental)
subject_definitions:
<Subject 1> is the solo skinny young woman in <Picture 1>, matching that still's face, messy goth rock hair, and goth makeup.
<Audio 1> is the source-song slice covering 167.875-173.042 of the master, reused as the complete soundtrack.
summary:
[video continuation + reference generation + audio reuse] <Subject 1> finishes on a closed-lip instrumental in the wind tunnel.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and wardrobe continue from the previous clip.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
detailed_description:
The target video is live-action, cinematic, an expensive pop-rock music video with high-budget motion graphics. [Shot 1] <Subject 1> is already in the previous clip's wide wind-tunnel crop with empty hands. <Subject 1>'s lips stay closed. Dance keeps moving. Cyclone graphics fade. No freeze.
overall_soundscape:
The soundtrack is <Audio 1> reused as-is. No other sounds.
non_diegetic_music: N/A
```

</details>

https://github.com/user-attachments/assets/a06a44f9-8d52-4a74-8ac0-e577053f1f91

</details>


# Nodes:


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

[https://github.com/user-attachments/assets/5b6bdb6f-00fc-4bc7-9d03-ddbe2f624ef4](https://github.com/user-attachments/assets/5b6bdb6f-00fc-4bc7-9d03-ddbe2f624ef4)

## Local Prompter

> [!TIP]
> Use [agent skills](skills/) instead for much better results

![Local Prompter](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/local-prompter.webp)

Writes Auto Chain or Music Video prompts on your machine from the Builder pack. Keep the Plan short; the local model expands it into timed, filmable clip bodies. Prefer an [agent skill](skills/README.md) when you can — the results are better.

1. Wire Builder into this node (put **Clip Prompt Fixer** in between to rewrite a few clips).
2. Pick a GGUF and queue **without H3 loaded**. The node unloads Comfy models, starts `llama-server` on `127.0.0.1`, generates each clip, then kills the server.
3. Copy `prompts` into Auto Chain or Music Video.

The node does not bundle llama.cpp. Install the official binaries, then either drop the catalog GGUF in `ComfyUI/models/LLM/` or enable `allow_download` once (~16 GB from Hugging Face). You can also pick a scanned `local:…gguf` or **Local GGUF** plus `gguf_path`. Queue the video graph after the prompter finishes.

Music Video packs need timed lyrics from Lyrics Timer first. Untimed lyrics fail until you Time lyrics. Local Prompter letter-refines locked confirm lines, plans CLIP windows from the song length, and writes `mode: music_video` with `time:` / `lyrics:` locked.

### Install llama.cpp

Ask your AI agent to install llama.cpp for this node, or follow the steps below.

Download a release from [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/releases). Nightly tags (`b#####`) ship the platform zips; `v0.3.0`-style tags may only point at the latest nightly.

**Windows NVIDIA (recommended location for this node):** extract the CUDA zip **and** the matching CUDA runtime zip into `ComfyUI/user/llama.cpp/` so `llama-server.exe`, `llama-cli.exe`, and the CUDA DLLs sit in that folder. The node finds them there without putting them on PATH. Restart ComfyUI afterward.


| GPU / toolchain    | llama.cpp zip                        | CUDA runtime zip                         |
| ------------------ | ------------------------------------ | ---------------------------------------- |
| RTX 40/50, CUDA 13 | `llama-b*-bin-win-cuda-13.3-x64.zip` | `cudart-llama-bin-win-cuda-13.3-x64.zip` |
| CUDA 12            | `llama-b*-bin-win-cuda-12.4-x64.zip` | `cudart-llama-bin-win-cuda-12.4-x64.zip` |
| CPU only           | `llama-b*-bin-win-cpu-x64.zip`       | (none)                                   |


Linux/macOS: extract the matching `.tar.gz` from the same release and put `llama-server` / `llama-cli` on PATH, or under `ComfyUI/user/`.

Multi-clip jobs need `llama-server`. A single clip can fall back to `llama-cli`. Optional overrides: the node's `llama_server` widget, or `H3_STUDIO_LLAMA_SERVER` / `H3_STUDIO_LLAMA_CLI`.

## Auto Chain

![Auto Chain](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/auto-chain.webp)

Generates a multi-clip video from Builder refs (not lipsync-to-song). Each clip continues from the last, so length is N × clip duration rather than one H3 window.

1. Builder in **Auto Chain** mode.
2. Wire that pack here. Connect CLIP, video VAE, audio VAE, sampler, sigmas, and noise.
3. Paste the prompt from `/prompt-minimax-h3-auto_chain` (or Local Prompter).
4. Queue.

Turn on **seamless loop** for a Loop clip that returns to the start. Keep `latent_prefix` if you might Clip-Fix later. `IMAGE` is the temp PNG sequence.

## Music Video

![Music Video, single prompt](https://github.com/kex0/ComfyUI-H3-Studio/releases/download/docs-assets/music-video-single-prompt.webp)

Generates a lipsync video that follows the song. Clip count and max duration come from the prompt (or duration from the pack). `<Audio 1>` is always the song slice; extra Builder audios (if you cited them) are `<Audio 2>` / `<Audio 3>`.

1. Builder in **Music Video** mode, with song + timed lyrics.
2. Wire that pack here. Connect CLIP, video VAE, audio VAE, sampler, sigmas, and noise.
3. Paste the prompt from `/prompt-minimax-h3-music-video` (or Local Prompter).
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

Prefer **Copy skill command** and `/prompt-minimax-h3-clip-fix` when you can ([skills](skills/README.md)) — quality is higher than Local Prompter. The command includes the plan, the selected clips, and one previous and one following clip. Or wire this node into **Local Prompter** and queue. Local Prompter output is the selected `## Clip` sections only (no `H3 Studio prompt` header, not neighbor clips). Neighbor clips in the seed are still used as continue-from / land-into context while writing.

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

[https://github.com/user-attachments/assets/f02400eb-04b1-42c8-b528-3060dd233c82](https://github.com/user-attachments/assets/f02400eb-04b1-42c8-b528-3060dd233c82)

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

Copy the folders in `[skills/](skills/README.md)` into your agent (Cursor, Claude Code, and similar). Prefer these over Local Prompter when you can — the prompts are higher quality. Music Video **Copy skill command** includes the Comfy origin, song path, and timed lyrics. The music-video skill does not download torch; it reuses this Comfy install.

## Dependencies

- ComfyUI MiniMax H3 (stock nodes, not a custom pack)
- llama.cpp (`llama-server`) for Local Prompter — see [Install llama.cpp](#install-llamacpp)
- `ultralytics`, `scipy`, `insightface` for Face Refine



## Thanks for the inspiration

- [https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy](https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy)
- [https://github.com/ukr8b3g-cmyk/ComfyUI-H3-Continuum](https://github.com/ukr8b3g-cmyk/ComfyUI-H3-Continuum)
- [https://github.com/Carasibana/ComfyUI-H3-FaceRefine](https://github.com/Carasibana/ComfyUI-H3-FaceRefine)
- [https://github.com/drozbay/MaskVidExperiments](https://github.com/drozbay/MaskVidExperiments)



## License

[MIT](LICENSE).
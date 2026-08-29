"""Per-node usage guides shown by the header ? button (web/js/nodeHelp.js)."""

from textwrap import dedent

SKILLS_URL = "https://github.com/kex0/ComfyUI-H3-Studio/tree/main/skills"
CURSOR_SKILLS_URL = "https://cursor.com/docs/context/skills"

NODE_HELP = {
    "H3StudioLoadSong": dedent("""
        ## Lyrics Timer

        Stamp lyric times onto your song.

        1. Paste lyrics that match the song as closely as possible.
        2. Upload your song.
        3. Press **Time lyrics**.

        **Timeline** (the floating dock)
        - Drag the A/B handles to a phrase, then **Add A–B** to insert that range.
        - Click a line to select it. Turn on **Live Edit** to rewrite that line's times as you drag.
        - Double-click a line to edit the words. Play A–B to check the match.

        **Lyric syntax**
        - `~word~` — a held / stretched syllable (`sing ~time~`).
        - `<instrumental>` — a rest with no singing. Put it on its own line.

        Wire `song` and `lyrics` into Builder (Music Video mode).
    """).strip(),
    "H3StudioBuilder": dedent("""
        ## Builder

        Collects models, pictures, videos, and audio for the other H3 Studio nodes.

        1. Connect your patched H3 model to `model_1`.
        2. Drop images / videos / audio, or wire them to **Media**.
        3. Pick **Auto Chain** or **Music Video**.
        4. Write a short Plan.

        Music Video also needs a song and timed lyrics from Lyrics Timer.

        Wire `pack` into Local Prompter, Music Video, or Auto Chain.

        Prefer **Copy skill command** into an agent when you can — quality is higher than Local Prompter.
        `/prompt-minimax-h3-music-video` or `/prompt-minimax-h3-auto_chain`.
        Skills live in this pack: [skills folder](""" + SKILLS_URL + """).
    """).strip(),
    "H3StudioLocalInfinitePrompter": dedent("""
        ## Local Prompter

        Writes prompts on your machine for **Music Video**, **Auto Chain**, and **Clip Prompt Fixer**.
        Prefer an [agent skill](""" + SKILLS_URL + """) when you can — the results are better.

        1. Wire Builder into this node.
        2. For a clip rewrite, put Clip Prompt Fixer between Builder and this node.
        3. Pick a GGUF and queue.
        4. Copy `prompts` into Music Video or Auto Chain.

        Keep the Builder Plan short. The local model expands it into timed, filmable clip bodies.

        Music Video needs timed lyrics from Lyrics Timer first.
    """).strip(),
    "H3StudioMusicVideo": dedent("""
        ## Music Video

        Generates a lipsync video that follows the song.

        1. Builder in **Music Video** mode, with song + timed lyrics.
        2. Wire that pack here. Connect CLIP, video VAE, audio VAE, sampler, sigmas, and noise.
        3. Paste the prompt from the music-video skill (or Local Prompter).
        4. Queue.

        `IMAGE` is the PNG sequence. Keep `latent_prefix` if you might Clip-Fix later.
        Face Refine uses the PNG folder printed in `chain_info`.
    """).strip(),
    "H3StudioAutoChain": dedent("""
        ## Auto Chain

        Generates a multi-clip video from your Builder refs (not lipsync-to-song).

        1. Builder in **Auto Chain** mode.
        2. Wire that pack here. Connect CLIP, video VAE, audio VAE, sampler, sigmas, and noise.
        3. Paste the prompt from the auto_chain skill (or Local Prompter).
        4. Queue.

        Turn on **seamless loop** if you want a Loop clip that returns to the start.
        Keep `latent_prefix` if you might Clip-Fix later.
    """).strip(),
    "H3StudioClipPromptFixer": dedent("""
        ## Clip Prompt Fixer

        Rewrites a few clips in an existing prompt. Lyrics and timings stay locked.

        1. Wire Builder into this node.
        2. Paste the Music Video or Auto Chain prompt.
        3. Set `clip_index` (`11-12` or `11,12`).
        4. Write a Plan of what should change.

        Prefer **Copy skill command** when you can — quality is higher than Local Prompter.

        Then either:

        - Click **Copy skill command** and paste into an agent, or
        - Wire this node into **Local Prompter** and queue.

        The skill `/prompt-minimax-h3-clip-fix` rewrites only those clip bodies. Paste the result back into Music Video or Auto Chain.

        Copy `skills/prompt-minimax-h3-clip-fix` from this pack into your agent's skills folder.
        [Cursor skills](""" + CURSOR_SKILLS_URL + """) · [skills in this repo](""" + SKILLS_URL + """)
    """).strip(),
    "H3StudioMusicVideoClipFixer": dedent("""
        ## Music Video Clip Fixer

        Re-renders chosen clips of an existing Music Video, then restitches the chain.

        1. Use the same models / VAE / sampler as the original run.
        2. Set `latent_prefix` to that chain's folder.
        3. Paste the new clip prompt(s) and set `clip_index` (`11-12`).
        4. Queue.

        Empty `clip_index` regenerates every clip in the paste.
        Overwritten clips are backed up next to the prefix first.
    """).strip(),
    "H3StudioAutoChainClipFixer": dedent("""
        ## Auto Chain Clip Fixer

        Re-renders chosen clips of an existing Auto Chain, then restitches the chain.

        1. Use the same models / VAE / sampler as the original run.
        2. Set `latent_prefix` to that chain's folder.
        3. Paste the new clip prompt(s) and set `clip_index` (`11-12`).
        4. Queue.

        Empty `clip_index` regenerates every clip in the paste.
        If you fix Finish and a Loop clip exists, Loop is regenerated too.
    """).strip(),
    "H3StudioFaceRefineVideo": dedent("""
        ## Face Refine Video

        Sharpens small faces on a finished clip. Close-ups are left alone.

        1. Set `video_path` to the PNG folder from Music Video `chain_info`, or to an MP4.
        2. Keep the default face prompt — do not paste lyrics or the scene.
        3. Connect model, CLIP, VAEs, sampler, sigmas, and noise.
        4. Queue after the music video is done.

        Turn on **seamless loop** if the clip should loop. Faces that need refine at both ends are generated as one wrap-around pass and split back onto the start and end.

        The second output is AUDIO: the wired `audio` socket, or the soundtrack inside `video_path` (MP4, or a PNG folder next to that MP4).
    """).strip(),
}

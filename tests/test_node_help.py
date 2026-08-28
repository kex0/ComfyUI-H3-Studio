import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from node_help import NODE_HELP

ROOT = Path(__file__).resolve().parents[1]


def test_every_h3_node_has_usage_guide():
    keys = {
        "H3StudioBuilder",
        "H3StudioLoadSong",
        "H3StudioLocalInfinitePrompter",
        "H3StudioMusicVideo",
        "H3StudioAutoChain",
        "H3StudioClipPromptFixer",
        "H3StudioMusicVideoClipFixer",
        "H3StudioAutoChainClipFixer",
        "H3StudioFaceRefineVideo",
    }
    assert set(NODE_HELP) == keys
    for name, text in NODE_HELP.items():
        assert text.startswith("## "), name
        assert "1." in text, name
    face = NODE_HELP["H3StudioFaceRefineVideo"]
    assert "second output is AUDIO" in face
    assert "video_path" in face
    assert "seamless loop" in face
    lyrics = NODE_HELP["H3StudioLoadSong"]
    assert "Paste lyrics" in lyrics
    assert "Upload your song" in lyrics
    assert "Time lyrics" in lyrics
    assert "`~word~`" in lyrics
    assert "`<instrumental>`" in lyrics
    prompter = NODE_HELP["H3StudioLocalInfinitePrompter"]
    assert "32 GB" not in prompter
    assert "without H3" not in prompter
    assert "Music Video" in prompter
    assert "Auto Chain" in prompter
    assert "filmable clip bodies" in prompter
    builder = NODE_HELP["H3StudioBuilder"]
    assert "Copy skill command" in builder
    assert "Skill slash" not in builder
    assert "Copy pack summary" not in builder
    fixer = NODE_HELP["H3StudioClipPromptFixer"]
    assert "Copy skill command" in fixer
    assert "Local Prompter" in fixer
    assert "/prompt-minimax-h3-clip-fix" in fixer
    assert "cursor.com/docs/context/skills" in fixer
    assert (ROOT / "skills" / "prompt-minimax-h3-clip-fix" / "SKILL.md").is_file()
    assert (ROOT / "skills" / "prompt-minimax-h3-auto_chain" / "SKILL.md").is_file()
    ac_skill = (ROOT / "skills" / "prompt-minimax-h3-auto_chain" / "SKILL.md").read_text(encoding="utf-8")
    assert "## Expand the plan" in ac_skill
    assert "/prompt-minimax-h3-auto_chain" in ac_skill
    assert "/prompt-minimax-h3-infinite" not in ac_skill
    assert "Follow **the user's plan**" not in ac_skill
    mv_skill = (ROOT / "skills" / "prompt-minimax-h3-music-video" / "SKILL.md").read_text(encoding="utf-8")
    assert (ROOT / "skills" / "prompt-minimax-h3-music-video" / "SKILL.md").is_file()
    assert (ROOT / "skills" / "prompt-minimax-h3-music-video" / "scripts" / "fill_prompt_bodies.py").is_file()
    assert "/h3_studio_song/plan" in mv_skill
    assert "## Expand the plan" in mv_skill
    assert "The filler take is illegal output." in mv_skill
    assert "fill_prompt_bodies.py" in mv_skill
    assert "song.confirm.words.json" in mv_skill
    assert "Do **not** transcribe" in mv_skill or "do **not** transcribe" in mv_skill
    assert "Lyrics Timer" in mv_skill
    assert "wav2vec2-refine" in mv_skill
    assert "setup_lyrics_env.py" not in mv_skill
    assert ".venv-lyrics" not in mv_skill
    assert "/h3_studio_song/align" not in mv_skill
    assert "transcribe_song_lrc.py" not in mv_skill
    skills_readme = (ROOT / "skills" / "README.md").read_text(encoding="utf-8")
    assert "fill_prompt_bodies.py" in skills_readme
    assert "/h3_studio_song/plan" in skills_readme
    assert "Do not copy venvs" in skills_readme


def test_node_help_popup_wiring():
    js = (ROOT / "web" / "js" / "nodeHelp.js").read_text(encoding="utf-8")
    assert 'name: "H3Studio.NodeHelp"' in js
    assert 'const CATEGORY = "H3 Studio"' in js
    assert "function installCanvasHelp" in js
    assert 'ctx.fillText("?", 0, 24)' in js
    assert "function tryInjectHelpButton" in js
    assert 'btn.className = "h3-help-btn"' in js
    assert ".lg-node-header" in js
    assert "function openPopup" in js
    assert "renderMarkdownToHtml" in js
    builder = (ROOT / "builder.py").read_text(encoding="utf-8")
    song = (ROOT / "song_loader.py").read_text(encoding="utf-8")
    assert 'DESCRIPTION = NODE_HELP["H3StudioBuilder"]' in builder
    assert 'DESCRIPTION = NODE_HELP["H3StudioLoadSong"]' in song

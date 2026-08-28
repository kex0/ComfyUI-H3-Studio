# H3 Studio agent skills

These skills write or rewrite MiniMax H3 Studio prompts in Cursor, Claude Code, and similar agents.

| Skill | Slash | Use with |
|---|---|---|
| `prompt-minimax-h3-music-video` | `/prompt-minimax-h3-music-video` | Builder **Copy skill command** (Music Video mode) |
| `prompt-minimax-h3-auto_chain` | `/prompt-minimax-h3-auto_chain` | Builder **Copy skill command** (Auto Chain mode) |
| `prompt-minimax-h3-clip-fix` | `/prompt-minimax-h3-clip-fix` | Clip Prompt Fixer **Copy skill command** |

Copy each folder into your agent's skills directory, then paste the copied command from the node.

**Cursor:** project `.cursor/skills/` or user skills. See [Cursor skills](https://cursor.com/docs/context/skills).

**Claude Code:** project `.claude/skills/` or `~/.claude/skills/`. See [Claude skills](https://code.claude.com/docs/en/skills).

Copy `SKILL.md` and `templates.md`. The music-video skill also needs `scripts/fill_prompt_bodies.py` (plain Python, no torch). Do not copy venvs or caches.

The music-video skill reuses the **running ComfyUI** for wav2vec2 letter clocks (`POST /h3_studio_song/plan`). Time lyrics in Lyrics Timer first, then Copy skill command. Comfy must be running; unload H3 before the agent posts `/plan`. The skill does not install Python packages.

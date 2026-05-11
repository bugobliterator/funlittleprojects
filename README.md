# funlittleprojects

Personal git repo holding side projects and Claude Code skills.

## Layout

- `claude-skills/skills/` — custom Claude Code skills, individually symlinked into `~/.claude/skills/`
  - `android-emulator-debugging/`
  - `log-analyzer/`
- `claude-usage-widget/` — Android home-screen widget showing Claude usage
- `.githooks/` — git hooks (see Hooks below)
- `.claude/settings.json` — Claude Code project settings (PreToolUse personal-info hook)
- `scripts/scan-personal-info.py` — shared scanner used by both hooks

## Hooks

Two layers block personal info from getting into commits:

1. **Claude PreToolUse hook** (`.claude/settings.json`) — denies any `Write`/`Edit`/`NotebookEdit`
   whose new content matches the scanner's patterns. Active automatically when Claude Code
   opens this directory.
2. **Git pre-commit hook** (`.githooks/pre-commit`) — runs the same scanner against
   `git diff --cached`. **No bypass.** Fix the line and re-stage.

Activate the git hook (one-time, per clone):

```sh
git config core.hooksPath .githooks
```

Patterns scanned (see `scripts/scan-personal-info.py`):
personal email addresses, absolute home-directory paths, Anthropic / AWS / GitHub
tokens, PEM private-key headers, and generic credential assignments
(`password=`, `api_key=`, `secret=`, etc).

## Restoring skill symlinks on a new machine

```sh
for d in claude-skills/skills/*/; do
  ln -s "$PWD/$d" ~/.claude/skills/"$(basename "$d")"
done
mkdir -p ~/.claude/agents
for f in claude-skills/agents/*.md; do
  ln -s "$PWD/$f" ~/.claude/agents/"$(basename "$f")"
done
```

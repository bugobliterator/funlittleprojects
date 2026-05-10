# funlittleprojects

Personal git repo holding side projects and Claude Code customizations.

## Layout

- `claude-skills/` — custom Claude Code slash commands and skills, symlinked into `~/.claude/`
  - `commands/` → `~/.claude/commands` (slash commands like `/detail-commit`, `/save-plan`)
  - `skills/` → individual subfolders symlinked into `~/.claude/skills/`
- `claude-usage-widget/` — Android home-screen widget showing Claude usage

## Restoring symlinks on a new machine

```sh
ln -s "$PWD/claude-skills/commands" ~/.claude/commands
for d in claude-skills/skills/*/; do
  ln -s "$PWD/$d" ~/.claude/skills/"$(basename "$d")"
done
```

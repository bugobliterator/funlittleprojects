# funlittleprojects

Personal git repo holding side projects and Claude Code skills.

## Layout

- `claude-skills/skills/` — custom Claude Code skills, individually symlinked into `~/.claude/skills/`
  - `android-emulator-debugging/`
  - `log-analyzer/`
- `claude-usage-widget/` — Android home-screen widget showing Claude usage
- `scanner-cli/` — Python CLI for sending Honeywell N36XX barcode-engine commands over serial
- `.github/workflows/` — GitHub Actions (see `package.yml` under scanner-cli below)
- `.githooks/` — git hooks (see Hooks below)
- `.claude/settings.json` — Claude Code project settings (PreToolUse personal-info hook)
- `scripts/scan-personal-info.py` — shared scanner used by both hooks

## scanner-cli

A Python CLI for talking to a Honeywell N36XX decoded barcode scan engine over an
RS232 serial line: raw menu/query/trigger commands (the `SYN M CR` protocol),
`ACK`/`ENQ`/`NAK` response parsing, and decoded-barcode streaming.

```sh
cd scanner-cli && python3 -m venv .venv && .venv/bin/pip install -e .
scanner -p /dev/cu.usbserial-XXXX scan                 # trigger, wait up to 5s, print one barcode
scanner -p /dev/cu.usbserial-XXXX listen               # stream decodes continuously
scanner -p /dev/cu.usbserial-XXXX send PAP232 --persist # set RS232 interface (persisted)
scanner -p /dev/cu.usbserial-XXXX repl                  # interactive session (:help, :menuhelp)
```

See `scanner-cli/README.md` for the full command reference. Standalone single-folder
builds for Windows and Linux are produced by the **Package scanner** GitHub Actions
workflow (`.github/workflows/package.yml`, run manually from the Actions tab).

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

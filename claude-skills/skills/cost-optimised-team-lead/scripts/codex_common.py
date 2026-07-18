"""Shared helpers for the Codex/iTerm2 teammate scripts.

Screen-state classification is evidence-based (probed live on Codex CLI v0.144.1):
- Every in-turn spinner line carries "esc to interrupt" (Working / Reviewing approval
  request / Running ...) -> WORKING.
- Startup trust prompt & human approval dialogs render as numbered option lists
  ("> 1. Yes ..." / "  2. No ...") -> DIALOG.
- The idle composer shows a rotating PLACEHOLDER suggestion behind ">" (e.g.
  "Run /review on my current changes") — never treat text behind ">" as stuck on its own.
- A stuck paste shows "[Pasted Content N chars]" in the composer -> STUCK_PASTE.
- Codex gone (pane at a bare shell after exec bash) -> DEAD.
"""
import os
import re
import sys

import iterm2

ESC_TO_INTERRUPT = "esc to interrupt"
PASTED_MARKER = "[Pasted Content"
DIALOG_OPTION_RE = re.compile(r"^[›>]\s*1\.\s")
# Codex footer/status bar, e.g. "gpt-5.6-terra high · /path/..."
FOOTER_RE = re.compile(r"^\s*gpt-\S+\s")


def lead_session_guid():
    """The lead pane's iTerm2 session id, from $ITERM_SESSION_ID (format wNtNpN:GUID)."""
    raw = os.environ.get("ITERM_SESSION_ID", "")
    if ":" not in raw:
        sys.exit("ERROR: $ITERM_SESSION_ID not set — not running inside iTerm2")
    return raw.split(":")[-1]


async def get_session(connection, session_id):
    app = await iterm2.async_get_app(connection)
    s = app.get_session_by_id(session_id)
    if s is None:
        sys.exit(f"ERROR: session {session_id} not found (pane closed? run iterm_map.py)")
    return s


async def screen_lines(session):
    contents = await session.async_get_screen_contents()
    lines = [contents.line(i).string.rstrip() for i in range(contents.number_of_lines)]
    return [l for l in lines if l]


def classify(lines):
    """Return (state, detail) for a Codex pane screen.

    States: WORKING | DIALOG | STUCK_PASTE | IDLE | DEAD
    detail: the evidence line(s), for the caller to print/act on.
    """
    if not lines:
        return "DEAD", "(empty screen)"
    tail = lines[-25:]
    joined = "\n".join(tail)

    # Dialogs (trust prompt, human approval, usage-limit, model-downgrade) show a
    # numbered option list; report them BEFORE working/idle — they block everything.
    for i, l in enumerate(tail):
        if DIALOG_OPTION_RE.match(l.strip()):
            return "DIALOG", "\n".join(tail[max(0, i - 6):i + 4])
    if "Press enter to continue" in joined and ESC_TO_INTERRUPT not in joined:
        return "DIALOG", joined[-400:]

    if ESC_TO_INTERRUPT in joined:
        working = [l for l in tail if ESC_TO_INTERRUPT in l]
        return "WORKING", working[-1]

    # Composer = last "›" block on screen.
    composer_idx = None
    for i in range(len(tail) - 1, -1, -1):
        if tail[i].lstrip().startswith("›"):
            composer_idx = i
            break

    if composer_idx is not None and PASTED_MARKER in tail[composer_idx]:
        return "STUCK_PASTE", tail[composer_idx]

    has_footer = any(FOOTER_RE.match(l) for l in tail)
    if not has_footer and composer_idx is None:
        return "DEAD", tail[-1]

    return "IDLE", tail[composer_idx] if composer_idx is not None else tail[-1]


def composer_text(lines):
    """Text currently in the composer (last '›' line + continuation lines), or ''."""
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("›"):
            idx = i
            break
    if idx is None:
        return ""
    out = [lines[idx].lstrip()[1:].strip()]
    for l in lines[idx + 1:]:
        if FOOTER_RE.match(l):
            break
        out.append(l.strip())
    return " ".join(out).strip()

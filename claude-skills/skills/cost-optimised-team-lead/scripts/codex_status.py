"""Classify a Codex teammate pane's state — the monitoring primitive.

Usage: python3 codex_status.py <SESSION_ID>

Prints one of:
  WORKING      — mid-turn (spinner line shown); leave it alone
  DIALOG       — a numbered-option dialog is blocking (trust prompt, human approval,
                 usage-limit, model-downgrade); dialog text printed — surface to the
                 human per skill policy, do NOT blind-answer
  STUCK_PASTE  — composer holds an unsubmitted paste; codex_send.py <id> "" to submit
  IDLE         — turn ended; last final answer printed. IDLE with no new commit and
                 no REPORT.md change usually means Codex is awaiting a ruling
  DEAD         — no Codex TUI in the pane (exited to shell / pane reused)

Exit codes: WORKING=0 DIALOG=3 STUCK_PASTE=4 IDLE=5 DEAD=6 (scriptable in monitors).
"""
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iterm2

from codex_common import get_session, screen_lines, classify

SESSION_ID = sys.argv[1]
EXIT = {"WORKING": 0, "DIALOG": 3, "STUCK_PASTE": 4, "IDLE": 5, "DEAD": 6}


def last_answer(lines):
    """Final message of the last completed turn = text between the last divider pair."""
    dividers = [i for i, l in enumerate(lines) if set(l.strip()) == {"─"} and len(l.strip()) > 20]
    if len(dividers) >= 2:
        return "\n".join(lines[dividers[-2] + 1:dividers[-1]])
    return ""


async def main(connection):
    s = await get_session(connection, SESSION_ID)
    lines = await screen_lines(s)
    state, detail = classify(lines)
    print(state)
    print(detail)
    if state == "IDLE":
        ans = last_answer(lines)
        if ans:
            print("--- last answer ---")
            print(ans)
    sys.exit(EXIT[state])


iterm2.run_until_complete(main)

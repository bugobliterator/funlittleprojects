"""Emit a line ONLY when a Codex pane transitions into a halted state (needs the lead).

Usage: python3 codex_watch.py <SESSION_ID> [<statefile>]

Designed to be driven by the Monitor tool on a loop: it prints nothing while the pane
is WORKING, and prints one `HALT ...` line the moment the pane goes IDLE/DIALOG/STUCK/DEAD
(a transition from working→halted). It records last-state in a statefile so a pane that
stays idle doesn't spam a notification every tick — only the transition fires.

States come from codex_common.classify: WORKING (spinner), IDLE (composer prompt, done-
with-last-message or halted), DIALOG (blocked on approval/trust), STUCK_PASTE, DEAD.
For the lead's purposes any non-WORKING state after WORKING means "look at the pane".
Exit 0 always (Monitor treats new stdout as the signal).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iterm2
from codex_common import get_session, screen_lines, classify

SID = sys.argv[1]
STATEFILE = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/codex_watch_{SID}.state"
HALT = {"IDLE", "DIALOG", "STUCK_PASTE", "DEAD"}


async def main(connection):
    s = await get_session(connection, SID)
    if s is None:
        cur = "DEAD"
        detail = "(pane not found)"
    else:
        lines = await screen_lines(s)
        cur, detail = classify(lines)

    prev = ""
    if os.path.exists(STATEFILE):
        with open(STATEFILE) as f:
            prev = f.read().strip()
    with open(STATEFILE, "w") as f:
        f.write(cur)

    # Fire only on a transition INTO a halted state (prev was working/unknown).
    if cur in HALT and prev not in HALT:
        tail = detail.replace("\n", " ")[:200] if detail else ""
        print(f"HALT {SID} state={cur} :: {tail}")


iterm2.run_until_complete(main)

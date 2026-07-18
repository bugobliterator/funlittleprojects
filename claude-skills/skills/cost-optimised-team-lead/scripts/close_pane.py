"""Close one or more iTerm2 panes by session_id (retire a Codex teammate cleanly).

Usage: python3 close_pane.py <SESSION_ID> [<SESSION_ID> ...]

Closes the pane (ends the Codex process + shell). The Codex SESSION itself survives
pane death — `codex resume <codex-session-id>` still works — so this is reversible.
Only pass session_ids you own; NEVER close another project's pane or a human's session.
Exit 0 = all closed (or already gone); prints one line per id.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iterm2

IDS = sys.argv[1:]
if not IDS:
    sys.exit("usage: close_pane.py <SESSION_ID> [<SESSION_ID> ...]")


async def main(connection):
    app = await iterm2.async_get_app(connection)
    for sid in IDS:
        s = app.get_session_by_id(sid)
        if s is None:
            print(f"{sid}: already gone")
            continue
        try:
            await s.async_close(force=True)
            print(f"{sid}: closed")
        except Exception as e:
            print(f"{sid}: FAILED — {e}")


iterm2.run_until_complete(main)

"""Send a message to a Codex TUI pane and VERIFY delivery — one call, self-healing.

Usage: python3 codex_send.py <SESSION_ID> "<message>"
       python3 codex_send.py <SESSION_ID> --file <path>   # long/multi-line briefs — no shell quoting hazards
       python3 codex_send.py <SESSION_ID> ""              # bare Enter (submit whatever is in the composer)

Protocol baked in (live-verified on Codex CLI v0.144.1):
- Text lands as a bracketed paste; the submit key is CARRIAGE RETURN \\r, sent as a
  SEPARATE keypress after the paste settles (a \\r bundled with the paste is swallowed;
  \\n never submits).
- Settle is adaptive: waits until the composer stops changing before pressing Enter.
- After Enter it verifies delivery (spinner appeared, or composer cleared and the text
  echoed in the transcript) and self-heals: stuck paste -> bare Enter; "Create a plan?"
  overlay -> ESC then Enter. Two heal rounds max.
- Exit 0 = DELIVERED (confirmed). Exit 2 = NOT delivered — pane tail printed; read it,
  do not proceed on hope.
- If the pane shows a blocking DIALOG (trust/approval/usage-limit), it refuses and
  prints the dialog: those are human/lead decisions, not something to type through.

⚠ Shell quoting: for anything beyond a short one-liner use --file. Backticks and $()
inside double quotes are substituted by bash BEFORE python sees the arg (a message once
lost words this way). --file bypasses the shell entirely.
"""
import asyncio
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iterm2

from codex_common import get_session, screen_lines, classify, composer_text

SESSION_ID = sys.argv[1]
if len(sys.argv) > 3 and sys.argv[2] == "--file":
    with open(sys.argv[3]) as f:
        MESSAGE = f.read().rstrip("\n")
else:
    MESSAGE = sys.argv[2]


async def settle(session, timeout=8.0):
    """Wait until the composer stops changing (paste finished rendering)."""
    prev = None
    waited = 0.0
    while waited < timeout:
        await asyncio.sleep(0.4)
        waited += 0.4
        cur = composer_text(await screen_lines(session))
        if cur == prev:
            return
        prev = cur


async def delivered(session, needle):
    lines = await screen_lines(session)
    state, _ = classify(lines)
    if state == "WORKING":
        return True
    if not needle:
        return state not in ("STUCK_PASTE",)
    comp = composer_text(lines)
    echoed = any(needle in l for l in lines)
    return needle not in comp and echoed


async def main(connection):
    s = await get_session(connection, SESSION_ID)

    state, detail = classify(await screen_lines(s))
    if state == "DIALOG" and MESSAGE:
        print("NOT DELIVERED: pane is blocked by a dialog — resolve it first:")
        print(detail)
        sys.exit(2)
    if state == "DEAD":
        print("NOT DELIVERED: no Codex TUI in this pane:")
        print(detail)
        sys.exit(2)

    if MESSAGE:
        await s.async_send_text(MESSAGE)
        await settle(s)
    await s.async_send_text("\r")

    # First 40 chars of the first line are enough to recognize the message on screen.
    needle = MESSAGE.splitlines()[0][:40] if MESSAGE else ""

    for attempt in range(3):
        for _ in range(6):  # up to ~3s per attempt
            await asyncio.sleep(0.5)
            if await delivered(s, needle):
                print("DELIVERED")
                return
        lines = await screen_lines(s)
        state, detail = classify(lines)
        if attempt == 2:
            break
        if state == "DIALOG" and "plan" in detail.lower():
            await s.async_send_text("\x1b")  # dismiss "Create a plan?" overlay
            await asyncio.sleep(0.5)
            await s.async_send_text("\r")
        elif state in ("STUCK_PASTE", "IDLE"):
            await s.async_send_text("\r")  # paste settled late — bare Enter submits it
        else:
            break

    lines = await screen_lines(s)
    state, detail = classify(lines)
    print(f"NOT DELIVERED (state={state}) — pane tail:")
    print("\n".join(lines[-15:]))
    sys.exit(2)


iterm2.run_until_complete(main)

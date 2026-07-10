"""Send a message to a Codex TUI pane by iTerm2 session ID and submit it.
Usage: python3 codex_send.py <SESSION_ID> "<message>"
       python3 codex_send.py <SESSION_ID> ""        # bare Enter (submit whatever is in the composer)

PROVEN PROTOCOL (learned the hard way):
- Text lands in the composer as a bracketed paste ("[Pasted Content N chars]") — it does NOT submit.
- The submit key is CARRIAGE RETURN "\r" — NOT "\n" (a "\n" does nothing in the Codex TUI).
- ALWAYS read the pane back after sending (pane_read.py): if the composer line still shows
  "[Pasted Content ...]" or your text behind the "›" prompt, send a bare "" (which sends just "\r").
- A "Create a plan?" overlay eats the first submit: dismiss with ESC ($'\x1b') then bare Enter.
- Confirm "• Working" appeared before treating the message as delivered.
- ⚠ SHELL QUOTING: never put backticks or $(...) in the message when calling from bash — even inside
  double quotes bash command-substitutes them BEFORE python sees the arg, silently dropping words
  (a `total`-in-backticks became empty once). Use plain quotes/apostrophes for emphasis, or write the
  message to a file and pass it via a $(cat file) that you control. Prefer a heredoc-fed temp file for
  long briefs."""
import iterm2, sys

SESSION_ID = sys.argv[1]
MESSAGE = sys.argv[2]

async def main(connection):
    app = await iterm2.async_get_app(connection)
    s = app.get_session_by_id(SESSION_ID)
    if not s:
        print("ERROR: session not found"); sys.exit(1)
    if MESSAGE:
        await s.async_send_text(MESSAGE)
        # A \r bundled with pasted text gets swallowed by the bracketed paste —
        # the submit must be a SEPARATE keypress after the paste settles.
        import asyncio
        await asyncio.sleep(1.0)
    await s.async_send_text("\r")
    print("sent")

iterm2.run_until_complete(main)

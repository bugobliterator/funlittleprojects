"""Split the lead's pane and launch a Codex teammate; prints the NEW session_id.
Usage: python3 codex_spawn.py <lead_tty e.g. /dev/ttys000> <launcher.sh path>
CAPTURE the printed session_id — it is the only sane address for all later comms."""
import iterm2, sys

LEAD_TTY = sys.argv[1]
LAUNCHER = sys.argv[2]

async def main(connection):
    app = await iterm2.async_get_app(connection)
    for w in app.windows:
        for t in w.tabs:
            for s in t.sessions:
                tty = await s.async_get_variable("tty")
                if tty == LEAD_TTY:
                    new = await s.async_split_pane(vertical=True)
                    await new.async_send_text(f"bash {LAUNCHER}\n")
                    print(new.session_id)
                    return
    print("ERROR: lead tty not found"); sys.exit(1)

iterm2.run_until_complete(main)

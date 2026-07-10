"""Read the visible screen of an iTerm2 session by session ID.
Usage: python3 pane_read.py <SESSION_ID> [n_lines]"""
import iterm2, sys

SESSION_ID = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 35

async def main(connection):
    app = await iterm2.async_get_app(connection)
    s = app.get_session_by_id(SESSION_ID)
    if not s:
        print("ERROR: session not found"); sys.exit(1)
    contents = await s.async_get_screen_contents()
    lines = [contents.line(i).string.rstrip() for i in range(contents.number_of_lines)]
    nonempty = [l for l in lines if l]
    print("\n".join(nonempty[-N:]))

iterm2.run_until_complete(main)

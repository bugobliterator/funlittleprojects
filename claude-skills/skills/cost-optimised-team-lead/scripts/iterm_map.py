"""Enumerate ALL iTerm2 sessions: session_id, tty, job, name, last screen lines.
Use this to identify panes by session_id — NEVER match panes by scrollback content."""
import iterm2

async def main(connection):
    app = await iterm2.async_get_app(connection)
    for w in app.windows:
        for t in w.tabs:
            for s in t.sessions:
                tty = await s.async_get_variable("tty")
                name = await s.async_get_variable("autoName")
                job = await s.async_get_variable("jobName")
                contents = await s.async_get_screen_contents()
                lines = [contents.line(i).string.rstrip() for i in range(contents.number_of_lines)]
                nonempty = [l for l in lines if l]
                tail = " | ".join(nonempty[-2:]) if nonempty else "(empty)"
                print(f"{s.session_id}  tty={tty}  job={job}  name={name!r}\n    tail: {tail[:180]}")

iterm2.run_until_complete(main)

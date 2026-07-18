"""Dispatch a Codex teammate: split the LEAD's pane, launch codex, babysit startup.
One call does everything; prints the new pane's session_id (RECORD IT — it is the only
sane address for all later comms) and the startup state.

Usage:
  python3 codex_spawn.py --cwd <worktree> --brief-file <path> [options]
  python3 codex_spawn.py --cwd <worktree> --resume <codex-session-id|last> --brief-file <follow-up> [options]

Options:
  --profile <name>   e.g. luna (browser driving). Default: config default (gpt-5.6-terra).
  --model <name>     e.g. spark for trivia. Default: config default.
  --trust            pre-register the directory as trusted in ~/.codex/config.toml
                     (the exact entry the trust dialog would write) so the startup
                     trust prompt never renders. ONLY for a worktree the lead itself
                     created. Without it, a first launch in a new directory blocks on
                     the dialog until a human (or codex_send.py <id> "") answers it.
  --lead <sid>       lead pane session id override; default auto-detected from
                     $ITERM_SESSION_ID (works because the Bash tool runs inside the
                     lead's iTerm2 session — no tty-ancestry walk needed).

The brief goes as a CLI arg: live-verified that it survives TUI startup and
auto-submits once ready. The pane ends with `exec bash` so it survives codex exiting.
Startup is polled read-only for ~90s and the final state printed (WORKING = brief
running; DIALOG = blocked — dialog text shown, resolve it via codex_send.py from a
NORMAL shell, never blind).

⚠ Do NOT add keystroke-sending to this process: live-verified iTerm2 quirk — from the
process that performed async_split_pane, screen reads keep working but sends to the
new pane silently vanish (same connection, second connection, and subprocesses all
affected). Interactions after spawn always happen via codex_send.py run from the
lead's Bash tool (a fresh process delivers fine).
"""
import argparse
import asyncio
import shlex
import sys
import tempfile

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iterm2

from codex_common import lead_session_guid, screen_lines, classify, composer_text

p = argparse.ArgumentParser()
p.add_argument("--cwd", required=True)
p.add_argument("--brief-file", required=True)
p.add_argument("--resume")
p.add_argument("--profile")
p.add_argument("--model")
p.add_argument("--effort", help='reasoning effort override, e.g. high (sets -c model_reasoning_effort)')
p.add_argument("--trust", action="store_true")
p.add_argument("--lead")
args = p.parse_args()

CWD = os.path.realpath(args.cwd)
if not os.path.isdir(CWD):
    sys.exit(f"ERROR: --cwd {CWD} is not a directory")

with open(args.brief_file) as f:
    brief = f.read().strip()

if args.trust:
    config = os.path.expanduser("~/.codex/config.toml")
    entry = f'[projects."{CWD}"]'
    with open(config) as f:
        existing = f.read()
    if entry not in existing:
        with open(config, "a") as f:
            f.write(f'\n{entry}\ntrust_level = "trusted"\n')

cmd = ["codex"]
if args.profile:
    cmd += ["--profile", args.profile]
if args.model:
    cmd += ["-m", args.model]
if args.effort:
    cmd += ["-c", f'model_reasoning_effort="{args.effort}"']
if args.resume:
    cmd += ["resume"] + (["--last"] if args.resume in ("last", "--last") else [args.resume])
cmd.append(brief)

launcher = tempfile.NamedTemporaryFile(
    mode="w", suffix=".sh", prefix="codex_launch_", delete=False
)
launcher.write(f"cd {shlex.quote(CWD)} && {' '.join(shlex.quote(c) for c in cmd)}\nexec bash\n")
launcher.close()

LEAD = args.lead or lead_session_guid()

async def main(connection):
    app = await iterm2.async_get_app(connection)
    lead = app.get_session_by_id(LEAD)
    if lead is None:
        sys.exit(f"ERROR: lead session {LEAD} not found")
    new = await lead.async_split_pane(vertical=True)
    await new.async_send_text(f"bash {launcher.name}\n")
    print(new.session_id, flush=True)

    # Read-only startup watch (reads work fine on this connection; sends would not —
    # see the module docstring). The pre-trust entry means no trust dialog appears.
    needle = brief.splitlines()[0][:40]
    state, detail = "DEAD", "(no reads yet)"
    for _ in range(45):
        await asyncio.sleep(2.0)
        s = app.get_session_by_id(new.session_id)
        if s is None:
            state, detail = "DEAD", "(pane closed during startup)"
            break
        lines = await screen_lines(s)
        state, detail = classify(lines)
        if state == "IDLE" and any(needle in l for l in lines):
            if needle in composer_text(lines):
                continue  # brief still queued in the composer (model loading)
            # Submitted — a tiny turn can even finish between polls.
            print("startup: WORKING (brief submitted; may already be IDLE)")
            return
        if state in ("WORKING", "DIALOG"):
            break

    print(f"startup: {state}")
    if state != "WORKING":
        print(detail)
        print("NOT running — resolve via codex_send.py/pane_read.py from a normal shell.")
        sys.exit(3)


iterm2.run_until_complete(main)

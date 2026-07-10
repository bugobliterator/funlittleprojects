"""Print one line per NOT-yet-seen pending comment / rollback request.

Driven by the Monitor tool's poll loop; each printed line becomes a chat
notification to the main Claude thread (which has full session context and
makes the actual change). Dedups via a seen-file so each item emits once.

Run from the dir containing collab.py:  python3 monitor_emit.py
Override the seen-file with the MONITOR_SEEN env var if needed.
"""
import os
import json
from pathlib import Path
import collab

SEEN = Path(os.environ.get("MONITOR_SEEN", str(collab.WIRE_DIR / ".monitor_seen")))
SEEN.parent.mkdir(parents=True, exist_ok=True)
seen = set(SEEN.read_text(encoding="utf-8").split("\n")) if SEEN.is_file() else set()

out = []
for c in collab.pending_comments():
    key = "C|" + str(c["view"]) + "|" + str(c["id"])
    if key not in seen:
        seen.add(key)
        text = (c.get("text") or "").replace("\n", " ")
        out.append(f"NEW COMMENT  view={c['view']}  id={c['id']}  by={c.get('author') or '?'} :: {text}")
for r in collab.rollback_requests():
    key = "R|" + str(r["id"])
    if key not in seen:
        seen.add(key)
        out.append(f"ROLLBACK REQUEST  change={r['id']} :: {r.get('summary') or ''}")
# new reviewer responses on a reply's thread → notify Claude to continue the conversation
for p in sorted(collab.WIRE_DIR.glob("markup--*.json")):
    view = p.stem.replace("markup--", "")
    try:
        anns = json.loads(p.read_text(encoding="utf-8")).get("annotations", [])
    except Exception:
        continue
    for a in anns:
        reply = a.get("reply")
        if not isinstance(reply, dict):
            continue
        for idx, msg in enumerate(reply.get("thread") or []):
            by = msg.get("by") or "?"
            if by == "Claude":
                continue
            key = "T|" + str(view) + "|" + str(a.get("id")) + "|" + str(idx)
            if key not in seen:
                seen.add(key)
                text = (msg.get("text") or "").replace("\n", " ")
                out.append(f"NEW RESPONSE  view={view}  id={a.get('id')}  by={by} :: {text}")
if out:
    SEEN.write_text("\n".join(sorted(seen)), encoding="utf-8")
    print("\n".join(out), flush=True)

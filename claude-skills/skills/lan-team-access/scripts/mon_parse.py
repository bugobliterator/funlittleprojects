#!/usr/bin/env python3
"""Parse a /wait long-poll JSON response (stdin), advance the cursor file, and
print one line per new guest message or file upload. Each printed line becomes
a Monitor notification, so the owner's Claude session reacts as events arrive.

Env: RELAY_CURSOR — path to the cursor file (stores the last seen message id).
"""
import sys, json, os

cursor = os.environ.get("RELAY_CURSOR", "/tmp/relay.cursor")
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

open(cursor, "w").write(str(d.get("last_id", 0)))

for m in d.get("messages", []):
    rid = m.get("id"); name = m.get("name", ""); role = m.get("role")
    if role == "file":
        print(f"[{rid}] FILE from {name}: {m.get('fname')} "
              f"({m.get('size')}B) at {m.get('path')}", flush=True)
    else:
        t = " ".join((m.get("text") or "").split())
        print(f"[{rid}] {name}: {t[:300]}", flush=True)

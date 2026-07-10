#!/usr/bin/env python3
"""Post a Claude answer or a system note to the relay (localhost-only endpoint).

Usage:
  post.py answer <file>   # posts file contents as a Claude reply
  post.py system <file>   # posts file contents as a centered system note

Reads the message from a file to avoid shell-escaping long/markdown text.
Env: RELAY_PORT (default 8420)
"""
import sys, json, os, urllib.request

port = os.environ.get("RELAY_PORT", "8420")
kind = sys.argv[1] if len(sys.argv) > 1 else "answer"
text = open(sys.argv[2]).read().rstrip("\n")
endpoint = "/answer" if kind == "answer" else "/system"
req = urllib.request.Request(
    f"http://127.0.0.1:{port}{endpoint}",
    data=json.dumps({"text": text}).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req, timeout=10).read().decode())

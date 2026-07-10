#!/usr/bin/env python3
"""Minimal LAN server for a wireframe/prototype review system.

Serves ./public over HTTP with no-cache (so every rebuild shows up without a
hard refresh) and exposes the markup + collab endpoints that review.js and the
Monitor loop use. Keep collab.py beside this file.

  python3 serve.py                 # serves ./public on 0.0.0.0:8080 (LAN)

Review data lives in ../uploads/wireframe/ (markup--<view>.json, .changelog.json).
"""
import json
import re
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import collab  # the comment/changelog/rollback/resolve store

SITE = Path(__file__).resolve().parent
PUBLIC = SITE / "public"          # static web root (your built pages)
WIRE = collab.WIRE_DIR            # ../uploads/wireframe
PORT, BIND, MAX = 8080, "0.0.0.0", 4_000_000


def _valid_view(v) -> bool:
    """A client-supplied view must be a bare name (no / . ..) — it becomes a filename."""
    return isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]+", v) is not None


def _wp(v): return WIRE / f"markup--{v}.json"


def load_wire(v):
    p = _wp(v)
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("annotations", []) if p.is_file() else []
    except Exception:
        return []


def _save(v, ann):
    WIRE.mkdir(parents=True, exist_ok=True)
    _wp(v).write_text(json.dumps({"view": v, "annotations": ann}, ensure_ascii=False, indent=2), encoding="utf-8")


def add_wire(d):
    v = str(d.get("view") or "view"); ann = load_wire(v)
    e = {k: d.get(k) for k in ("id", "type", "author", "x", "y", "w", "h", "points", "text", "ts") if d.get(k) is not None}
    # id/type land in DOM attributes client-side — reject anything not a bare token
    for k in ("id", "type"):
        if k in e and not (isinstance(e[k], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", e[k])):
            e.pop(k)
    e.setdefault("id", f"a{len(ann)}"); ann.append(e); _save(v, ann); return ann


def del_wire(v, i):
    v = str(v or "view"); ann = [a for a in load_wire(v) if a.get("id") != i]; _save(v, ann); return ann


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(PUBLIC), **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if 0 < n <= MAX:
            try: return json.loads(self.rfile.read(n).decode())
            except Exception: return {}
        return {}

    def do_GET(self):
        p = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(p.query or "")
        if p.path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
        if p.path == "/wire/markup":
            view = q.get("view", ["view"])[0]
            if not _valid_view(view): return self._json({"error": "invalid view"}, 400)
            return self._json({"annotations": load_wire(view)})
        if p.path == "/wire/summary": return self._json(collab.summary())
        if p.path == "/wire/changelog": return self._json(collab.changelog())
        return super().do_GET()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path; d = self._body()
        if p == "/wire/markup":
            if not str(d.get("author") or "").strip(): return self._json({"error": "author required"}, 400)
            if not _valid_view(str(d.get("view") or "view")): return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "annotations": add_wire(d)})
        if p == "/wire/markup/delete":
            if not _valid_view(str(d.get("view") or "view")): return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "annotations": del_wire(d.get("view"), d.get("id"))})
        if p == "/wire/reviewed":
            if not _valid_view(str(d.get("view") or "")): return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "result": collab.mark_reviewed(str(d.get("view") or ""))})
        if p == "/wire/resolve":
            if not _valid_view(str(d.get("view") or "")): return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "result": collab.set_resolved(str(d.get("view") or ""), str(d.get("id") or ""), bool(d.get("resolved", True)))})
        if p == "/wire/rollback": return self._json({"ok": True, "result": collab.request_rollback(str(d.get("id") or ""))})
        if p == "/wire/respond":
            view = str(d.get("view") or ""); cid = str(d.get("id") or "")
            text = str(d.get("text") or "").strip(); by = str(d.get("by") or "").strip()
            if not (view and cid and text and by): return self._json({"error": "view/id/text/by required"}, 400)
            if not _valid_view(view): return self._json({"error": "invalid view"}, 400)
            # Only internal server calls (collab.reply_to/respond_to by="Claude") may speak as
            # Claude; a client-supplied "Claude" is neutralised so reviewers can't impersonate it.
            if by.strip().lower() == "claude": by = "Reviewer"
            ok = collab.respond_to(view, cid, text, by)
            return self._json({"ok": ok, "annotations": load_wire(view)})
        return self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    PUBLIC.mkdir(parents=True, exist_ok=True)
    print(f"serving {PUBLIC} on http://{BIND}:{PORT}  (LAN-reachable)")
    ThreadingHTTPServer((BIND, PORT), H).serve_forever()

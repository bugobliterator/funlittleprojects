import json
import os
import re
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from vendor import collab

from . import gitio, render


ROOT = Path(__file__).resolve().parent.parent
WIRE = collab.WIRE_DIR
MAX_BODY = 4_000_000


def _valid_view(view):
    return isinstance(view, str) and re.fullmatch(r"[A-Za-z0-9_-]+", view) is not None


def _wire_path(view):
    return WIRE / f"markup--{view}.json"


def _load_wire(view):
    path = _wire_path(view)
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("annotations", []) if path.is_file() else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_wire(view, annotations):
    WIRE.mkdir(parents=True, exist_ok=True)
    _wire_path(view).write_text(
        json.dumps({"view": view, "annotations": annotations}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _add_wire(data):
    view = str(data.get("view") or "view")
    annotations = _load_wire(view)
    fields = ("id", "ref", "type", "kind", "anchor", "author", "x", "y", "w", "h", "points", "text", "ts")
    entry = {key: data.get(key) for key in fields if data.get(key) is not None}
    for key in ("id", "type"):
        if key in entry and not (isinstance(entry[key], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", entry[key])):
            entry.pop(key)
    entry.setdefault("id", f"a{len(annotations)}")
    annotations.append(entry)
    _save_wire(view, annotations)
    return annotations


def _delete_wire(view, comment_id):
    view = str(view or "view")
    annotations = [item for item in _load_wire(view) if item.get("id") != comment_id]
    _save_wire(view, annotations)
    return annotations


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, repo, **kwargs):
        self.repo = Path(repo)
        super().__init__(*args, directory=str(ROOT / "assets"), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def _json(self, value, code=200):
        body = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            return None
        if not 0 < length <= MAX_BODY:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode())
            return value if isinstance(value, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _manifest(self):
        return json.loads((self.repo / "review-manifest.json").read_text(encoding="utf-8"))

    def _diff(self, query):
        manifest = self._manifest()
        theme_id = query.get("theme", [""])[0]
        theme = next((item for item in manifest["themes"] if item.get("id") == theme_id), None)
        if theme is None:
            return None
        sub_id = query.get("sub", [None])[0]
        unit = next((item for item in theme.get("subsections", []) if item.get("id") == sub_id), None) if sub_id else theme
        return None if unit is None else render.unit_diff(self.repo, manifest["base"], unit["commits"])

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query or "")
        if parsed.path == "/":
            self.path = "/board.html"
            return super().do_GET()
        if parsed.path.startswith("/assets/"):
            self.path = parsed.path.removeprefix("/assets")
            return super().do_GET()
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        try:
            if parsed.path == "/api/manifest":
                return self._json(self._manifest())
            if parsed.path == "/api/diff":
                result = self._diff(query)
                return self._json(result, 200) if result is not None else self._json({"error": "unit not found"}, 404)
            if parsed.path in ("/wire/markup", "/wire/thread"):
                view = query.get("view", ["view"])[0]
                if not _valid_view(view):
                    return self._json({"error": "invalid view"}, 400)
                annotations = _load_wire(view)
                if parsed.path == "/wire/thread":
                    return self._json({"comments": [{
                        "author": item.get("author"),
                        "kind": item.get("kind") or item.get("type"),
                        "text": item.get("text"),
                        "anchor": item.get("anchor"),
                        "ref": item.get("ref") or item.get("id"),
                    } for item in annotations]})
                return self._json({"annotations": annotations})
            if parsed.path == "/wire/summary":
                return self._json(collab.summary())
            if parsed.path == "/wire/changelog":
                return self._json(collab.changelog())
        except FileNotFoundError as error:
            return self._json({"error": str(error)}, 404)
        except (json.JSONDecodeError, KeyError, ValueError, gitio.GitError) as error:
            return self._json({"error": str(error)}, 500)
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        data = self._body()
        if data is None:
            return self._json({"error": "JSON object required"}, 400)
        if path == "/wire/comment":
            view = str(data.get("view") or "")
            kind = str(data.get("kind") or "")
            if not (_valid_view(view) and data.get("anchor") and kind in ("question", "change") and str(data.get("text") or "").strip()):
                return self._json({"error": "view/anchor/kind/text required"}, 400)
            data["author"] = str(data.get("author") or "Reviewer")
            data["type"] = kind
            return self._json({"ok": True, "annotations": _add_wire(data)})
        if path == "/wire/markup":
            if not str(data.get("author") or "").strip():
                return self._json({"error": "author required"}, 400)
            if not _valid_view(str(data.get("view") or "view")):
                return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "annotations": _add_wire(data)})
        if path == "/wire/markup/delete":
            if not _valid_view(str(data.get("view") or "view")):
                return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "annotations": _delete_wire(data.get("view"), data.get("id"))})
        if path == "/wire/reviewed":
            view = str(data.get("view") or "")
            if not _valid_view(view):
                return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "result": collab.mark_reviewed(view)})
        if path == "/wire/resolve":
            view = str(data.get("view") or "")
            if not _valid_view(view):
                return self._json({"error": "invalid view"}, 400)
            return self._json({"ok": True, "result": collab.set_resolved(view, str(data.get("id") or ""), bool(data.get("resolved", True)))})
        if path == "/wire/rollback":
            return self._json({"ok": True, "result": collab.request_rollback(str(data.get("id") or ""))})
        if path == "/wire/respond":
            view = str(data.get("view") or "")
            comment_id = str(data.get("id") or "")
            text = str(data.get("text") or "").strip()
            author = str(data.get("by") or "").strip()
            if not (view and comment_id and text and author):
                return self._json({"error": "view/id/text/by required"}, 400)
            if not _valid_view(view):
                return self._json({"error": "invalid view"}, 400)
            if author.lower() == "claude":
                author = "Reviewer"
            result = collab.respond_to(view, comment_id, text, author)
            return self._json({"ok": result, "annotations": _load_wire(view)})
        return self._json({"error": "not found"}, 404)


def make(repo, port=None):
    global WIRE
    repo = Path(repo).resolve()
    WIRE = repo / ".prb" / "wire"
    WIRE.mkdir(parents=True, exist_ok=True)
    collab.WIRE_DIR = WIRE
    collab.CHANGELOG = WIRE / ".changelog.json"
    collab.SNAP_DIR = WIRE / ".snapshots"
    selected_port = int(os.environ.get("PRB_PORT", "8099")) if port is None else port
    return ThreadingHTTPServer(("0.0.0.0", selected_port), partial(Handler, repo=repo))


if __name__ == "__main__":
    make(Path.cwd()).serve_forever()

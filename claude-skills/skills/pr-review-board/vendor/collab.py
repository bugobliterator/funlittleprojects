"""Collaboration store for the wireframe.

Two things live here, shared by serve.py (HTTP endpoints) and the CLI
(Claude, acting as the monitor):

  • comment replies + per-view summary  — so each stakeholder comment can get a
    response, views show a comment count, and a red dot marks "Claude responded".
  • a global change-log with rollback requests — every change is recorded; the UI
    shows the count + list, and a per-change button asks Claude to roll one back.
"""
import json
import os
import re
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIRE_DIR = ROOT / "uploads" / "wireframe"
CHANGELOG = WIRE_DIR / ".changelog.json"
SNAP_DIR = WIRE_DIR / ".snapshots"

# A view name maps directly to a filename (markup--{view}.json); an allowlist of
# safe characters keeps a client-supplied view from escaping WIRE_DIR (no / . ..).
# Permits the real views, including the synthetic "_global".
_VALID_VIEW = re.compile(r'^[A-Za-z0-9_-]+$')


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _wire_path(view: str):
    if not (isinstance(view, str) and _VALID_VIEW.match(view)):
        raise ValueError("invalid view: %r" % (view,))
    return WIRE_DIR / f"markup--{view}.json"


# ───────────────────────── comments / replies ─────────────────────────

def reply_to(view: str, comment_id: str, text: str, by: str = "Claude", commit=None) -> bool:
    """Attach Claude's reply to a comment (shows inline + lights the view's red dot).

    `commit` is the short git hash that resolved the comment, shown inline on the reply.
    The reply seeds an empty `thread` so the reviewer can reply back (see respond_to)."""
    p = _wire_path(view)
    doc = _read(p, {"view": view, "annotations": []})
    for a in doc.get("annotations", []):
        if a.get("id") == comment_id:
            a["reply"] = {"text": text, "by": by, "ts": _now(), "reviewed": False,
                          "commit": commit, "thread": []}
            _write(p, doc)
            return True
    return False


def respond_to(view: str, comment_id: str, text: str, by: str) -> bool:
    """Append a follow-up message to a reply's thread (reviewer ↔ Claude back-and-forth).

    Works on older replies that predate the `thread` key — the list is created on demand."""
    p = _wire_path(view)
    doc = _read(p, None)
    if not doc:
        return False
    for a in doc.get("annotations", []):
        if a.get("id") == comment_id and isinstance(a.get("reply"), dict):
            thread = a["reply"].setdefault("thread", [])
            thread.append({"text": text, "by": by, "ts": _now()})
            a["reply"]["reviewed"] = False   # a new thread message re-lights the view's dot
            _write(p, doc)
            return True
    return False


def set_resolved(view: str, comment_id: str, resolved: bool = True) -> bool:
    """Mark/unmark a comment resolved — resolved ones hide from the canvas but stay in the list."""
    p = _wire_path(view)
    doc = _read(p, None)
    if not doc:
        return False
    for a in doc.get("annotations", []):
        if a.get("id") == comment_id:
            a["resolved"] = bool(resolved)
            _write(p, doc)
            return True
    return False


def mark_reviewed(view: str) -> bool:
    """User opened the view → clear its red dot (replies marked reviewed)."""
    p = _wire_path(view)
    doc = _read(p, None)
    if not doc:
        return False
    changed = False
    for a in doc.get("annotations", []):
        r = a.get("reply")
        if isinstance(r, dict) and not r.get("reviewed"):
            r["reviewed"] = True
            changed = True
    if changed:
        _write(p, doc)
    return changed


def pending_comments():
    """Comments that have no Claude reply yet — the monitor's work queue."""
    out = []
    for p in sorted(WIRE_DIR.glob("markup--*.json")):
        view = p.stem.replace("markup--", "")
        for a in _read(p, {}).get("annotations", []):
            if (a.get("text") or "").strip() and not isinstance(a.get("reply"), dict) and not a.get("resolved"):
                out.append({"view": view, "id": a.get("id"), "author": a.get("author"),
                            "type": a.get("type"), "text": a.get("text"), "ts": a.get("ts")})
    return out


# ───────────────────────────── change-log ─────────────────────────────

def _git_commit(message):
    """Commit the current tree so each logged change maps to a real git commit. No-op if ROOT
    isn't a git repo or there's nothing to commit. Returns the short hash (or "")."""
    import subprocess
    try:
        if not (ROOT / ".git").is_dir():
            return ""
        subprocess.run(["git", "-C", str(ROOT), "add", "-A"], capture_output=True)
        r = subprocess.run(["git", "-C", str(ROOT), "commit", "-m", message], capture_output=True, text=True)
        if r.returncode != 0:
            return ""
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def append_change(summary: str, detail: str = "", views=None) -> str:
    """Record a change. If a build source is configured (env WRS_SNAPSHOT_SRC, default
    site/wire_build.py) and it exists, snapshot it so a rollback has a reference point.
    Projects serving pre-built static pages can leave it unset — the change-log still
    works; only the snapshot reference is skipped."""
    cl = _read(CHANGELOG, {"changes": []})
    cid = "c" + str(len(cl["changes"]) + 1).zfill(3)
    cl["changes"].append({"id": cid, "ts": _now(), "summary": summary, "detail": detail,
                          "views": views or [], "status": "applied", "rollback_requested": False})
    _write(CHANGELOG, cl)
    src = Path(os.environ.get("WRS_SNAPSHOT_SRC", str(ROOT / "site" / "wire_build.py")))
    if src.is_file():
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        (SNAP_DIR / f"{src.stem}.{cid}{src.suffix}").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    h = _git_commit(f"wireframe: {summary}")
    if h:
        cl["changes"][-1]["commit"] = h
        _write(CHANGELOG, cl)
    return cid


def changelog():
    return _read(CHANGELOG, {"changes": []})


def request_rollback(change_id: str) -> bool:
    cl = _read(CHANGELOG, {"changes": []})
    for c in cl["changes"]:
        if c["id"] == change_id and c["status"] == "applied":
            c["rollback_requested"] = True
            _write(CHANGELOG, cl)
            return True
    return False


def set_change_status(change_id: str, status: str) -> bool:
    cl = _read(CHANGELOG, {"changes": []})
    for c in cl["changes"]:
        if c["id"] == change_id:
            c["status"] = status
            c["rollback_requested"] = False
            _write(CHANGELOG, cl)
            return True
    return False


def rollback_requests():
    """Changes the user has asked Claude to roll back — picked up on the next poll."""
    return [c for c in _read(CHANGELOG, {"changes": []})["changes"] if c.get("rollback_requested")]


# ──────────────────────────── summary for UI ───────────────────────────

def summary():
    views = {}
    for p in sorted(WIRE_DIR.glob("markup--*.json")):
        view = p.stem.replace("markup--", "")
        anns = _read(p, {}).get("annotations", [])
        allc = [a for a in anns if (a.get("text") or "").strip()]
        if not allc:
            continue
        open_ = [a for a in allc if not a.get("resolved")]
        responded = [a for a in open_ if isinstance(a.get("reply"), dict)]
        unrev = [a for a in responded if not a["reply"].get("reviewed")]
        views[view] = {"comments": len(open_), "resolved": len(allc) - len(open_),
                       "responded": len(responded), "unreviewed": len(unrev)}
    cl = _read(CHANGELOG, {"changes": []})["changes"]
    return {"views": views,
            "changes": len(cl),
            "rollback_pending": sum(1 for c in cl if c.get("rollback_requested"))}


if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "haswork":
        work = {"pending": pending_comments(), "rollback": rollback_requests()}
        print(json.dumps(work, indent=2))
        sys.exit(0 if (work["pending"] or work["rollback"]) else 1)
    print(json.dumps({"pending": pending_comments(), "rollback": rollback_requests()} if arg == "x"
                     else summary(), indent=2))

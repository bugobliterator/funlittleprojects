#!/usr/bin/env python3
"""Scan text for personal info / credential patterns.

Modes:
  --stdin         Read raw text from stdin, scan, print hits, exit 1 if any.
  --git-staged    Read `git diff --cached`, scan added lines, exit 1 if any.
  --claude-hook   Read Claude Code PreToolUse JSON from stdin. If hits, emit
                  blocking JSON and exit 2 (PreToolUse deny). Else exit 0.

No bypass. If the scanner flags a line, fix the line.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email-cubepilot",   re.compile(r"siddharth@cubepilot\.com", re.I)),
    ("email-gmail",       re.compile(r"siddharthbharatpurohit@gmail\.com", re.I)),
    ("home-path",         re.compile(r"/Users/" + r"sidbh(?:/|\b)")),
    ("anthropic-key",     re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key",    re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token",      re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}")),
    ("private-key",       re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential-assign", re.compile(
        r"""(?ix)
        (?:password|passwd|api[_-]?key|secret|access[_-]?token|auth[_-]?token)
        \s*[:=]\s*
        ["']?[A-Za-z0-9_+/=.-]{8,}
        """)),
]

ALLOWLIST: list[re.Pattern[str]] = [
    re.compile(r"noreply@anthropic\.com", re.I),
    re.compile(r"example@example\.(?:com|org)", re.I),
]


def scan_line(line: str) -> str | None:
    if any(a.search(line) for a in ALLOWLIST):
        return None
    for name, pat in PATTERNS:
        if pat.search(line):
            return name
    return None


def scan_text(text: str, file_label: str = "<input>") -> list[str]:
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        name = scan_line(line)
        if name:
            hits.append(f"[{name}] {file_label}:{i}: {line}")
    return hits


def mode_stdin() -> int:
    hits = scan_text(sys.stdin.read())
    if not hits:
        return 0
    print("\n".join(hits), file=sys.stderr)
    return 1


def mode_git_staged() -> int:
    diff = subprocess.run(
        ["git", "diff", "--cached", "--no-color", "-U0", "--diff-filter=ACMR"],
        capture_output=True, text=True, check=False,
    ).stdout
    if not diff:
        return 0
    hits: list[str] = []
    current_file = "<unknown>"
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:]
        name = scan_line(line)
        if name:
            hits.append(f"[{name}] {current_file}: {line}")
    if not hits:
        return 0
    sys.stderr.write("\n\033[1;31m[pre-commit] personal info detected in staged additions:\033[0m\n\n")
    sys.stderr.write("\n".join(hits) + "\n\n")
    sys.stderr.write("Fix the lines above and re-stage. There is no bypass.\n\n")
    return 1


def _added_lines(old: str, new: str) -> list[tuple[int, str]]:
    """Return (1-based line-number in `new`, line text) for lines added in new vs old."""
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines() if new else []
    out: list[tuple[int, str]] = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(
        a=old_lines, b=new_lines, autojunk=False
    ).get_opcodes():
        if tag in ("insert", "replace"):
            for j in range(j1, j2):
                out.append((j + 1, new_lines[j]))
    return out


def mode_claude_hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input", {}) or {}
    added: list[tuple[int, str]] = []
    if tool == "Write":
        new = tin.get("content", "") or ""
        fp = tin.get("file_path", "") or ""
        old = ""
        try:
            with open(fp) as f:
                old = f.read()
        except OSError:
            pass
        added = _added_lines(old, new)
    elif tool == "Edit":
        added = _added_lines(
            tin.get("old_string", "") or "",
            tin.get("new_string", "") or "",
        )
    elif tool == "NotebookEdit":
        new = tin.get("new_source", "") or ""
        added = [(i, ln) for i, ln in enumerate(new.splitlines(), 1)]
    else:
        return 0
    hits: list[str] = []
    for lineno, line in added:
        name = scan_line(line)
        if name:
            hits.append(f"[{name}] +{lineno}: {line[:200]}")
    if not hits:
        return 0
    reason = (
        "Blocked: the proposed change adds lines matching personal-info / credential "
        "patterns. Added lines:\n" + "\n".join(hits) +
        "\n\nRework the lines above (use ~/ instead of absolute home paths, redact secrets, etc.) "
        "and retry. There is no bypass."
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] == "--stdin":
        return mode_stdin()
    if sys.argv[1] == "--git-staged":
        return mode_git_staged()
    if sys.argv[1] == "--claude-hook":
        return mode_claude_hook()
    print(f"unknown mode: {sys.argv[1]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

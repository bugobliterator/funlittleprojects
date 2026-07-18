---
name: pr-review-board
description: >-
  Review a large or sprawling pull request by INTENT, not raw diff. Restructures a branch's commits into
  clean thematic chunks (reordered, never squashed), then serves a dark-mode local webpage that groups the
  changes by theme and subsection — each with an engineer summary AND a user/business-logic impact — with
  diff2html-rendered diffs, VS Code deep-links, a live per-line Question/Change comment round-trip, and a
  fixup→autosquash finalize. Use whenever a PR/branch is too big to review linearly, when commits need
  reorganising for review, or when someone asks to "review this PR", "restructure the commits", or
  "make this PR reviewable". Reusable on any git repo — inputs are just a base ref and a head ref.
---

# pr-review-board

A 5-stage pipeline: **restructure → manifest → render → review → finalize**. The `prb/` Python package owns
the git/manifest/serve logic (stdlib only) and reuses the wireframe-review-system comment store verbatim; a
static HTML/JS shell (`assets/`) mounts vendored diff2html. Nothing is project-specific.

**Read `references/workflow.md` before running** — it has the exact call sequence for each stage.

## Non-negotiable invariants
- **Tree-identity is sacred.** Restructure must leave the net diff unchanged (`git diff <backup>..<new_head>`
  empty); finalize must leave the net tree unchanged. A mismatch ABORTS, restores the branch to the backup
  tag, and raises — never `-X ours/theirs`, never auto-resolve, never leave a half-rebased branch.
- **Human approves the commit-map before any history rewrite.** `restructure.propose` suggests a grouping;
  Claude enriches it (titles, summaries, user/logic impact, subsections); the user approves; only then
  `restructure.apply` runs.
- **Reorder, don't squash.** Every commit stays its own reviewable chunk; a theme is a contiguous run.
- **No silent failure.** Any git/subprocess failure, orphaned commit, or validation gap surfaces — fix the
  cause, don't paper over it.

## Quick start
1. From the tool dir, drive Stage 1–2 per `references/workflow.md` (propose → enrich → approve → apply →
   build+validate+write `review-manifest.json`).
2. `PRB_PORT=8099 python3 -c "from prb import server; import threading; s=server.make('<repo>'); s.serve_forever()"`
   and open `http://<LAN-IP>:8099/`.
3. Arm the Monitor on `<repo>/.prb/wire`; answer Questions inline, land Changes as `--fixup` commits.
4. `finalize.run(...)` folds the fixups back into the thematic chunks.

## Layout
`prb/` (gitio, manifest, restructure, render, finalize, server) · `vendor/` (collab, monitor_emit — verbatim
from wireframe-review-system) · `assets/` (board.html/css/js + vendored diff2html) · `tests/` (pytest +
node --test) · `references/workflow.md`.

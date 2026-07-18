# pr-review-board — operator workflow (the 5 stages)

Driven by Claude importing the `prb` package (run from `tools/pr-review-board/`, or the installed
`~/.claude/skills/pr-review-board/`). `<repo>` is the target repo's absolute path; `<base>..<head>` the PR.

Two invariants hold at every stage — if either trips, the stage ABORTS, restores, and raises; never paper over it:
- **Tree-identity:** restructure must not change the net diff; finalize must not change the net tree.
- **Human approval before any history rewrite:** the commit-map is shown and approved BEFORE `restructure.apply`.

## Stage 1 — Restructure (reorder into thematic chunks; human-approved)
```python
from prb import restructure, manifest, render, gitio
starter = restructure.propose(repo, base, head)   # groups existing commits by conventional-commit scope
```
Enrich `starter` into the real commit-map: for each theme set `title`, `summary` (engineer-facing),
`userImpact` (operator-facing), `affectedRoles`, and — where a theme is broad (spans server+web or mixes
concerns) — `subsections` (each `{id,title,scope,commits[],detail,impact:{kind:"user"|"logic",role?,text}}`).
Keep every commit as its own chunk; a theme is a contiguous RUN of commits, never squashed to one.
**Present the map to the user and get approval.** Then:
```python
new_head = restructure.apply(repo, base, head, commit_map, backup_tag="prb-backup/<branch>")
```

## Stage 2 — Manifest
```python
m = manifest.build(repo, base, new_head, commit_map)   # adds base/head/backup/repoRoot(abspath)
manifest.validate(repo, base, new_head, m)             # coverage + subsection self-checks (raises on gap)
import json, pathlib; pathlib.Path(repo, "review-manifest.json").write_text(json.dumps(m, indent=2))
```

## Stage 3 — Render is on-demand (diff2html)
No pre-render step: the server calls `render.unit_diff(repo, base, commits)` per theme/subsection on request
and the board mounts it with vendored diff2html. VS Code links use `m["repoRoot"]`.

## Stage 4 — Serve + live round-trip
```python
srv = server.make(repo, port=int(os.environ.get("PRB_PORT", 8099)))   # binds 0.0.0.0, no-store
# serve_forever in a thread; give the user http://<LAN-IP>:8099/
```
Arm the Monitor on the comment store so questions/changes notify you live (reuses the wireframe-review
pattern): watch `<repo>/.prb/wire` for new comments; on each, **Question** → `collab.reply_to(view, id, text)`
inline; **Change** → make the edit + `git commit --fixup=<theme/subsection commit>` + `collab.append_change(...)`.
SHAs stay stable during review.

## Stage 5 — Finalize
```python
from prb import finalize
m2 = finalize.run(repo, base, head_branch, m)   # rebase --autosquash folds fixups; asserts tree-stable; regens manifest
```
History returns to the thematic chunks with review changes absorbed. Push when the user approves.

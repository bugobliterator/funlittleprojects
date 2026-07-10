---
name: wireframe-review-system
description: >-
  Deploy a LAN-served interactive review layer onto any wireframe, prototype, design mock,
  spec, or internal tool: stakeholders mark it up in the browser (pins, boxes, freehand,
  per-view comments), Claude replies inline and a red dot tells reviewers which views have a
  response, every change Claude ships is recorded in a change-log with one-click "request
  rollback", and comments can be resolved (they leave the canvas but stay in the list). Comes
  with a drop-in Python server + a comment/change-log store + the browser overlay + a Claude
  Monitor loop. Use this whenever the user wants people on the local network to review / comment
  on / mark up a wireframe, prototype, design, or internal tool; wants a stakeholder feedback or
  design-review loop; wants Claude to monitor and respond to design comments; or asks to "deploy
  the review system" for a tool or web-service — even if they don't say "wireframe" explicitly.
---

# Wireframe / prototype review system

Turns any served HTML prototype into a collaborative review tool where stakeholders mark it up
on the LAN and Claude responds + tracks every change. This is the reusable version of the system
built for the CubePilot parts platform.

## What it deploys

- **Browser markup overlay** (`assets/review.js` + `review.css`) — self-injecting floating toolbar
  with pin / box / freehand / whole-view comment tools, a per-view comments panel, **plus a global
  "system notes" channel** for architectural feedback not tied to a view, author colours, 6s live
  polling. Drops onto any page via a few hooks (see references/integration.md, incl. the global hook).
- **Comment + change-log store** (`scripts/collab.py`) — replies, per-view summary (counts + red
  dots), resolve, a global change-log, and rollback requests. JSON files under
  `uploads/wireframe/`. Project-agnostic.
- **Drop-in LAN server** (`scripts/serve.py`) — serves `./public` with no-cache + all the
  `/wire/*` endpoints review.js needs, bound to `0.0.0.0` so anyone on the network can review.
- **Monitor loop** (`scripts/monitor_emit.py` + the built-in Monitor tool) — notifies the main
  Claude thread per *new* comment / rollback request; Claude (full context) makes the change,
  replies, and logs it.

## Deploy it (workflow)

1. **Copy the backend** into the project's server dir (the folder that holds `serve.py`; create a
   `site/` if there isn't one):
   ```bash
   cp <skill>/scripts/{collab.py,serve.py,monitor_emit.py} <project>/site/
   ```
   `collab.py` stores data in `site/../uploads/wireframe/` (i.e. one level above its own dir —
   adjust `WIRE_DIR` if your layout differs). Rollback snapshots are opt-in: set `WRS_SNAPSHOT_SRC`
   to whatever your project builds from, or skip it for hand-written static pages (see integration.md addenda). If the project already has its own server,
   instead add the `/wire/*` routes + the `no-cache` `end_headers` to it (copy from `serve.py`).

2. **Copy the overlay** into the web root and wire each page. Put `review.js` + `review.css` in
   `public/`, then add the **six page hooks** (body `data-view`, `#wire-doc`, topnav buttons,
   change-log drawer, sidebar `.wire-navcount` placeholders, and the asset includes). The exact
   copy-paste snippets are in **`references/integration.md`** — read it before wiring pages.
   review.css ships with fallback tokens, so it works standalone; if the project has a design
   system, map the `--cp-*` vars to it.

3. **Serve on the LAN**:
   ```bash
   cd <project>/site && python3 serve.py    # run in background
   ```
   Give the user `http://<LAN-IP>:8080/<first-view>.html` (get the IP with
   `ipconfig getifaddr en0` on macOS). Because it binds `0.0.0.0` and sends no-cache, anyone on
   the network sees the latest build live — no hard refresh.

4. **Arm the Monitor** (never poll inline — use the Monitor tool, persistent):
   ```
   Monitor(description="new wireframe comments + rollback requests", persistent=true,
           command="cd <project>/site && while true; do python3 monitor_emit.py 2>/dev/null; sleep 30; done")
   ```
   Each new comment / rollback arrives as a notification; handle it on the main thread. Full
   behaviour + how to respond is in `references/integration.md` ("The Monitor loop").

5. **Respond to comments** as they arrive. **Triage on the main thread** (full context — this is
   where you weight the pin location), then **always launch a subagent to implement + browser-test
   each change**: give it a tight brief (the comment, the target element, the exact fix, the test to
   run), and have it rebuild, verify in a headless browser, then call `collab.reply_to(...)` for the
   inline reply and `collab.append_change(...)` to log + commit it. Relay the subagent's result.
   **If the change is frontend/UI** — a new view/page, layout, components, or styling — the subagent
   **must invoke the `frontend-design` skill** so the result is a deliberate, production-grade design,
   not ad-hoc markup. (Pure data/logic/copy fixes don't need it.)

## collab.py API (run from the dir holding collab.py)

```python
import collab
collab.reply_to(view, comment_id, text)          # answer a comment (lights its red dot)
collab.append_change(summary, detail, [views])    # record a shipped change (+ snapshots the source)
collab.request_rollback(change_id)                # (server endpoint) reviewer asks to undo a change
collab.set_change_status(change_id, "rolled-back")# after you revert it
collab.set_resolved(view, comment_id, True)       # (server endpoint) hide from canvas, keep in list
collab.mark_reviewed(view)                         # (server endpoint) clear a view's red dot
collab.pending_comments(); collab.rollback_requests(); collab.summary(); collab.changelog()
```

## Key principles (learned the hard way)

- **Weight where a pin sits, not just its text.** A comment pinned on a table column is about that
  column; don't change a chart because the words mention "cost". The pin location is the real target.
- **Detect + triage on the main thread; delegate every change to a subagent.** Use the Monitor tool
  to *detect* (not a separate monitoring agent) and triage each comment on the main thread with full
  context (where you weigh the pin location). Then **always launch a subagent to make + browser-test
  the change** from a precise brief — it rebuilds, verifies in a browser, replies via `collab.reply_to`,
  and `collab.append_change` (which commits). Relay the result. This keeps the main context clean and
  every change tested; the tight brief is what stops the subagent being context-blind.
- **Frontend/UI changes use the `frontend-design` skill.** Any subagent whose change is visual — a new
  view/page, layout, components, or styling — must invoke the `frontend-design` skill in its brief, so
  the output has a deliberate aesthetic and production-grade polish instead of generic markup. Pure
  data/logic/copy fixes don't need it.
- **Log every change.** `append_change` is what powers the change-log count, the list, and rollback.
- **No-cache + `0.0.0.0`** are what make the LAN review loop feel live; keep both.
- **The markup overlay must anchor to itself, and stay immune to the host page's layout.** Pins/boxes
  are positioned inside `#wire-overlay`, so map every pointer event with `overlay.getBoundingClientRect()`
  (the element they live in) — never a parent like `#wire-doc`; mismatched anchors make annotations
  drift, worse the further from the origin. And because the overlay is injected as the *last child* of
  the content container, a host rule like `.content > * + * { margin-top: … }` silently lands a margin on
  it and shoves an `inset:0` element off `top:0` — every pin then drops by that margin *and* the displaced
  overlay overshoots the content (so it also looks "short"). Neutralise it with `#wire-overlay{margin:0}`
  (ID specificity beats the sibling rule). Verify by *measurement*, not eyeballing: a synthetic click's
  coords should land the pin's centre on the cursor (delta ≈ 0) at the top-left, a far edge, and after a
  real scroll. See `references/integration.md` ("Overlay coordinate correctness").

## Bundled files

- `scripts/collab.py` — the store (comments/replies/summary/change-log/rollback/resolve)
- `scripts/serve.py` — minimal LAN server with the `/wire/*` endpoints + no-cache
- `scripts/monitor_emit.py` — emits one line per new comment/rollback for the Monitor loop
- `assets/review.js`, `assets/review.css` — the browser markup + review overlay (drop-in)
- `references/integration.md` — the page hooks, styling, and Monitor-loop details

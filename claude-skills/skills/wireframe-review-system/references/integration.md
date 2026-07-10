# Integration reference

How `review.js` / `review.css` attach to a served page, and how the Monitor loop works.
Read this when wiring the review layer into a project's pages or arming monitoring.

## The six page hooks

`review.js` self-injects the floating markup toolbar, the per-view comments panel, the
pin/box/freehand overlay, and the name modal. The page only has to provide these hooks:

1. **Current view id** — on `<body>`:
   ```html
   <body data-view="dashboard">
   ```
   Every page is one "view". The id is the key under which its comments are stored
   (`uploads/wireframe/markup--dashboard.json`). Use short slugs: `dashboard`, `product`, `finance`.

2. **Content container** — the element the markup overlay positions over (pins/boxes land on it):
   ```html
   <main id="wire-doc"> …your page content… </main>
   ```
   It must be `position: relative` (review.css handles the overlay positioning).

3. **Topnav indicators** — a comments pill + a changes button:
   ```html
   <span class="cp-pill cp-pill--soft cp-pill--accent" id="wire-viewcount"><span class="cp-pill__dot"></span>comments</span>
   <button id="wire-changes-btn"><span id="wire-changes-n">0</span> changes</button>
   ```
   (`cp-pill` classes are optional cosmetics — a bare `<span>`/`<button>` works.)

4. **Change-log drawer** — paste once per page, anywhere before `</body>`:
   ```html
   <div class="wire-cl" id="wire-cl" hidden>
     <div class="wire-cl__backdrop" id="wire-cl-bg"></div>
     <aside class="wire-cl__panel" role="dialog" aria-label="Change log">
       <div class="wire-cl__head"><strong>Change log</strong><span id="wire-cl-count"></span><button class="wire-cl__x" id="wire-cl-close">✕</button></div>
       <div class="wire-cl__list" id="wire-cl-list"></div>
     </aside>
   </div>
   ```

5. **Sidebar per-view counts** — inside each nav item that links to a view, add a placeholder:
   ```html
   <a class="cp-sidenav__item" href="/dashboard.html"> …icon… <span>Dashboard</span>
      <span class="wire-navcount" data-view="dashboard"></span></a>
   ```
   `review.js` fills these with the open-comment count + a red dot when Claude has responded.
   A view that is a *sub-tab* of another (no own nav item) can fold into its parent — see the
   `SUB` map near the top of `loadSummary()` in `review.js` (e.g. `{whereused:"part"}`).

6. **Include the assets** — before `</body>`:
   ```html
   <link rel="stylesheet" href="/review.css">
   <script src="/review.js"></script>
   ```

Optional hooks `review.js` will use if present: `#wire-avatar` (reviewer initials),
`#wire-theme-btn` (light/dark toggle). They're harmless to omit.

## Styling

`review.css` is authored against `@cubepilot/ui` token names (`--cp-color-*`, `--cp-space-*`,
`--cp-font-family-*`, …) and ships with a fallback `:root` so it works standalone (dark).
If the host project has its own design system, define those vars to map to it (or find/replace
the token names). Don't hand-rewrite the component CSS — only the tokens are project-specific.

## What review.js does (behaviour, for reference)

- Markup tools: **pin**, **box**, **freehand**, plus a whole-view **comment**. Each annotation is
  attributed to the reviewer (name prompted once, stored in `localStorage`), colour-coded by author,
  shared with everyone (all-see-all), and polled every 6s so the view evolves live.
- **Replies**: when a comment has a `reply` (written by Claude via `collab.reply_to`), it renders
  inline under the comment, in the panel and the pin/box popover.
- **Per-view counts + red dots**: fetched from `/wire/summary`; a red dot means Claude responded and
  the reviewer hasn't opened that view yet. Opening a view POSTs `/wire/reviewed` → clears its dot.
- **Resolve**: Resolve/Reopen on any comment → POSTs `/wire/resolve`. Resolved comments disappear
  from the canvas but stay in that view's comment list tagged "resolved".
- **Change-log drawer**: the "N changes" button opens `/wire/changelog`; each entry has a
  **Request rollback** button → POSTs `/wire/rollback` (the button shows a red dot until Claude actions it).

## The Monitor loop (how Claude watches + responds)

Do **not** poll inline. Use the built-in **Monitor** tool with a persistent poll over
`monitor_emit.py`, which prints one line per *new* comment / rollback request (deduped):

```
Monitor(
  description="new wireframe comments + rollback requests",
  persistent=true,
  command="cd <project>/site && while true; do python3 monitor_emit.py 2>/dev/null; sleep 30; done"
)
```

Each emitted line becomes a chat notification to the **main Claude thread** (full context), e.g.
`NEW COMMENT  view=finance  id=a123  by=Siddharth :: <text>`. Handle it there:

- **Comment** → on the main thread, decide what it asks for. Crucially, weight **where the pin/box
  sits** (its target element/column), not just the text — a comment on a table column is about that
  column, not a chart. Then **launch a subagent to implement + browser-test the change**: brief it with
  the comment, the target element, the exact fix, and the test to run; have it rebuild, verify in a
  headless browser, then `collab.reply_to('finance','a123','what it did')` and
  `collab.append_change('summary','detail',['finance'])`. **If the fix is frontend/UI** (a view,
  layout, component, or styling), the subagent **must invoke the `frontend-design` skill** so the
  output is a deliberate, polished design rather than ad-hoc markup. If it's a *pure question*, just
  reply on the main thread (no subagent needed).
- **Rollback** → revert that change (the snapshot `uploads/wireframe/.snapshots/<file>.<id>.*` is the
  post-change state for reference), rebuild, then `collab.set_change_status('<id>','rolled-back')`.

Run `collab.append_change(...)` for every change so the reviewer's change-log + rollback work.
**Triage on the main thread** (full context), but **delegate the implementation + browser test to a
subagent** — brief it tightly (comment, target element, exact fix, test to run) so it isn't
context-blind, and relay its result. Don't edit the wireframe inline on the main thread. For any
**frontend/UI** change, the implementing subagent must invoke the **`frontend-design`** skill — visual
work (new pages, layout, components, styling) should be deliberately designed, not improvised markup.

## Addenda

### Global / system comments (a 7th hook)

Beyond per-view comments, the overlay supports **system-wide / architectural** notes not tied to any
view, stored under the reserved view id `_global`. To enable, add a topnav button + a drawer:

```html
<!-- in the topnav, beside the changes button -->
<button id="wire-global-btn"><span id="wire-global-n">0</span> system</button>

<!-- once per page, beside the change-log drawer (reuses the wire-cl styles) -->
<div class="wire-cl" id="wire-gc" hidden>
  <div class="wire-cl__backdrop" id="wire-gc-bg"></div>
  <aside class="wire-cl__panel" role="dialog" aria-label="System & architecture notes">
    <div class="wire-cl__head"><strong>System &amp; architecture notes</strong><span id="wire-gc-count"></span><button class="wire-cl__x" id="wire-gc-close">✕</button></div>
    <div class="wire-cl__list" id="wire-gc-list"></div>
    <div class="wire-gc__compose"><textarea id="wire-gc-compose" placeholder="A structural comment on the whole system…"></textarea><button class="cp-button cp-button--accent cp-button--sm" id="wire-gc-send">Post system note</button></div>
  </aside>
</div>
```

Global notes show on every view, get the same reply / red-dot / resolve treatment, and the Monitor
picks them up as `view=_global` — handle them like any comment.

### Operational notes (cold-deploy gotchas)

- **Where data lands.** `collab.py` derives `WIRE_DIR = <collab.py's dir>/../uploads/wireframe/`. With
  `collab.py` in `site/`, data is written to `site/../uploads/wireframe/` (one level **above** site/).
  If you drop `collab.py` in a flat project root, edit `WIRE_DIR` or it lands a level too high.
- **Rollback snapshots are opt-in.** `append_change` snapshots a build source so a rollback has a
  reference, but **only if that file exists**. It defaults to `site/wire_build.py`; if your project
  builds from something else (a React app, a different generator), set `WRS_SNAPSHOT_SRC` to that path.
  Projects that serve hand-written static pages can ignore this — the change-log + rollback request
  still work; you just revert by hand. `.snapshots/` simply won't be created.
- **`reply_to` / `set_resolved` return `False` on a missing view/id** (and `request_rollback` only acts
  on a change whose `status == "applied"`). The CLI one-liners discard the return — when scripting,
  check it's `True` so a typo'd id doesn't silently no-op.

### Overlay coordinate correctness

The markup overlay (`#wire-overlay`) is injected as a child of the content container (`#wire-doc`) and
sized to cover it, and pins/boxes are absolutely-positioned **inside the overlay**. Two invariants keep
clicks landing where the cursor is — both were learned from a real drift bug:

1. **Map pointer events against the overlay, not a different ancestor.** The event→coordinate helper must
   be `rel(e){ var r = overlay.getBoundingClientRect(); return {x:e.clientX-r.left, y:e.clientY-r.top}; }`.
   `getBoundingClientRect()` is already viewport-relative (it accounts for page scroll), so **don't** add
   `scrollLeft/scrollTop`. Measuring against `#wire-doc` while rendering into `#wire-overlay` is the classic
   mistake: any divergence between the two boxes offsets every annotation, and the error grows with distance
   from the origin.

2. **Keep the overlay immune to the host's layout.** Because the overlay is the *last child* of the content
   container, it inherits the host design system's child-combinator rules. A common one —
   `.content > * + * { margin-top: <space> }` (used to space stacked sections) — silently lands a
   `margin-top` on the overlay, and on an `inset:0` absolutely-positioned element that margin shifts it that
   many pixels **below** `top:0`. The symptom is twofold from a single cause: every pin/box drops by the
   margin, **and** the displaced overlay overshoots the content so the box also looks "short" at the bottom.
   Guard against it with `#wire-overlay{ margin:0 }` (the ID selector out-specifies the sibling rule). When
   you deploy onto a new design system, scan it for `> * + *` / `* + *` margin rules on the overlay's parent
   and confirm the overlay's computed `margin` is `0`.

**Verify by measurement, not by eye.** Dispatch a synthetic click at a known viewport point and read the
rendered pin's actual `getBoundingClientRect()` centre (the pin is centred on its `(x,y)` via a negative
margin): the delta to the cursor should be ≈ 0 at the top-left, at a far edge (e.g. a right-hand table
cell), and after a real scroll. Do the same for a box drag (start/end corners) and a freehand stroke.

### Versioning comments

To keep stakeholder comments + the change-log under version control (recommended), **do not**
gitignore `uploads/wireframe/` — only ignore `uploads/wireframe/.snapshots/` and
`.monitor_seen`. Because `append_change` runs `git add -A`, every change-commit then also captures
the current comment/reply state, giving you a single history of "what was said and what changed".

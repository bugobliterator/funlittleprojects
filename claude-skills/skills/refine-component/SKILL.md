---
name: refine-component
description: Refine a single Svelte 5 + Tailwind v4 component through a paired editor / UI-designer review loop. Use when the user says "polish this component", "make this look better", "review the UI of <file>.svelte", or invokes `/refine-component <path>`. Spawns a `svelte-component-editor` subagent and a `ui-design-expert` subagent for up to 3 rounds of edit → screenshot → critique, ending when the designer says APPROVED or 3 rounds elapse.
---

# refine-component

Paired editor/critic loop for polishing a single Svelte 5 + Tailwind v4 component.

## How to invoke

`/refine-component <path-to.svelte> [goal text] [--url=/route]`

Examples:
- `/refine-component src/lib/Button.svelte`
- `/refine-component src/routes/+page.svelte "make the hero feel less crowded" --url=/`

## The recipe

You (main Claude) run this loop directly. Do NOT spawn another orchestrator agent.

### Step 1 — Parse and validate

- Required: first positional arg is a path ending in `.svelte`. If missing or wrong, abort with: "Usage: /refine-component <path.svelte> [goal] [--url=/route]".
- Optional: free-text goal (everything that isn't `--url=...`). Default to "general polish".
- Optional: `--url=/some/route`. Capture for later.
- Verify the file exists. If not, abort and suggest `glob '**/*.svelte'` to find candidates.

### Step 2 — Pick a browser MCP (no fallback to source-only)

Check which MCP is available in this session by inspecting the tools surfaced in context:

1. `chrome-devtools-mcp` available → use it.
2. Else `playwright` MCP available → use it.
3. Else → halt with: "No browser MCP available. Install or enable chrome-devtools-mcp or playwright and re-run."

Remember the chosen MCP for the rest of the loop.

### Step 3 — Find the dev server

Probe these ports for an HTTP 200, 1-second timeout each, first wins:

```bash
for p in 5173 3000 4173 5174; do
  curl -s -m 1 -o /dev/null -w "%{http_code}\n" "http://localhost:$p"
done
```

If none returns 200, halt with: "No dev server detected on ports 5173/3000/4173/5174. Start `npm run dev` and re-run." Remember the base URL.

### Step 4 — Determine the route

If `--url=` was supplied, use it. Otherwise ask the user once: "Which route renders this component? (e.g. `/`, `/login`, or 'skip' to abort)". If they say 'skip', halt.

### Step 5 — Capture the baseline screenshot

Filename: `/tmp/refine-<basename>-baseline.png` where `<basename>` is the component file's basename without extension.

- chrome-devtools-mcp: `new_page` → `navigate_page <url>` → `take_screenshot path=<filename>`. (The baseline is for the editor only; the designer doesn't see it, so we don't need an a11y tree here.)
- playwright: `browser_navigate <url>` → `browser_take_screenshot path=<filename>`. No a11y tree available.

If capture fails, halt: "Screenshot failed on baseline. <error>. Aborting."

### Step 6 — Run the loop, max 3 rounds

For `n` in 1..3:

**(a) Spawn the editor.** Use the Agent tool with `subagent_type=svelte-component-editor`. Pass a self-contained prompt:

```
Edit the Svelte 5 component at <ABSOLUTE_PATH>. Goal: <GOAL>. Round <n> of 3.

Latest screenshot: <LATEST_SCREENSHOT_PATH>.

<If n >= 2:>
Previous UI-expert critique:
<PASTE THE FULL VERDICT BLOCK + ITEMS HERE>
Address every numbered item.
</If>

Output a short summary of changes, then hand off.
```

`<LATEST_SCREENSHOT_PATH>` is the baseline for round 1, otherwise the previous round's post-edit screenshot.

**(b) Capture the post-edit screenshot.** Path: `/tmp/refine-<basename>-post-r<n>.png`. A11y tree (if chrome-devtools): `/tmp/refine-<basename>-a11y-r<n>.json`. Halt on capture failure.

**(c) Spawn the designer.** Use the Agent tool with `subagent_type=ui-design-expert`. Pass:

```
Review the rendered component. Goal: <GOAL>. Round <n> of 3.

Screenshot: <POST_EDIT_SCREENSHOT_PATH>.
<If a11y tree exists:>
Accessibility tree: <A11Y_PATH>.
</If>

Critique on the standard axes. End with a single VERDICT block.
```

**(d) Parse the verdict.** Search the last 20 lines of the designer's reply for `^VERDICT:\s*(APPROVED|NEEDS_WORK)`. If APPROVED, break. If NEEDS_WORK, capture the items as the critique for round `n+1`. If no verdict block found, treat as NEEDS_WORK with the full reply as the critique.

### Step 7 — Surface the result

Print to the user:
- Rounds run.
- Final verdict (APPROVED or NEEDS_WORK).
- Files modified (run `git diff --name-only` since the start).
- If NEEDS_WORK at exit: the final designer's numbered items so the user can decide whether to continue manually.
- Paths of all screenshots so the user can review the iteration history.

## Failure modes

| Condition | Action |
|---|---|
| Bad args / missing file | Abort with usage. |
| No browser MCP | Halt with install hint. |
| No dev server | Halt with `npm run dev` hint. |
| User chose 'skip' on URL | Halt. |
| Screenshot fails any round | Halt with round number + error. |
| Verdict block missing | Treat as NEEDS_WORK; continue. |
| Editor no-op | Continue to designer; if APPROVED, ship; else continue. |
| Max rounds, no APPROVED | Surface critique; do not claim success. |

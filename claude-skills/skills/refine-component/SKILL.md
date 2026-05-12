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
- Capture the current HEAD as `$START_SHA` (run `git rev-parse HEAD`). You'll use this in Steps 6(a-bis) and 7 to diff against.

### Step 2 — Pick a browser MCP (no fallback to source-only)

Inspect the list of MCP tools surfaced to you in this session's system messages / tool catalog. Look for tool names matching either pattern below:

1. Any tool name beginning with `mcp__plugin_chrome-devtools-mcp_chrome-devtools__` → chrome-devtools-mcp is available, use it.
2. Else any tool name beginning with `mcp__plugin_playwright_playwright__` → playwright is available, use it.
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

### Step 4b — Verify the route resolves

After Steps 3 and 4 you have `<base_url>` and `<route>`. Probe the full URL:

```bash
curl -s -m 2 -o /dev/null -w "%{http_code}" "<base_url><route>"
```

If the status is not 200, surface to the user: "Route `<route>` returned HTTP `<status>` on `<base_url>`. Continue anyway, or abort and pick a different route?" Wait for confirmation before continuing.

### Step 5 — Capture the baseline screenshot

**Pick the screenshot directory based on the chosen MCP** — both browser MCPs sandbox writes:

- chrome-devtools-mcp: write under `$TMPDIR` (the macOS per-user temp, typically `/var/folders/.../T/`). Example: `$TMPDIR/refine-<basename>-baseline.png`. The literal path `/tmp/...` is rejected because `/tmp` is symlinked outside the allowed roots.
- playwright: write under `$CLAUDE_PROJECT_DIR/.playwright-mcp/`. Example: `$CLAUDE_PROJECT_DIR/.playwright-mcp/refine-<basename>-baseline.png`. Add `.playwright-mcp/` to `.gitignore` if it isn't already.

`<basename>` is the component file's basename without extension. Resolve `$TMPDIR` and `$CLAUDE_PROJECT_DIR` from the environment before passing the path to the MCP — the MCPs do not expand env vars themselves.

Capture commands:

- chrome-devtools-mcp: `new_page url=<base_url><route>` → `take_screenshot filePath=<absolute path>`. (Baseline is for the editor only; the designer doesn't see it, so no a11y tree here. A11y trees are captured only in Step 6(b) for the designer.)
- playwright: `browser_navigate url=<base_url><route>` → `browser_take_screenshot filename=<absolute path>`. No a11y tree available.

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

**(a-bis) Detect editor no-op.** Run `git diff --name-only $START_SHA HEAD` to see what changed since the orchestrator started. If the editor's summary indicates no changes were made AND `git diff` shows no new modifications since the previous round, jump out of the loop and proceed to Step 7 with the current verdict (or NEEDS_WORK if none yet). Looping again against an unchanged screenshot wastes tokens and produces a redundant critique.

**(b) Capture the post-edit screenshot.** Use the same MCP-specific directory you picked in Step 5 (`$TMPDIR/...` for chrome-devtools, `$CLAUDE_PROJECT_DIR/.playwright-mcp/...` for playwright). Filename: `refine-<basename>-post-r<n>.png`. A11y tree (chrome-devtools only, via `take_snapshot filePath=...`): `refine-<basename>-a11y-r<n>.txt` in the same directory. Halt on capture failure.

**(c) Spawn the designer.** Use the Agent tool with `subagent_type=ui-design-expert`. Pass:

```
Review the rendered component. Goal: <GOAL>.

Screenshot: <POST_EDIT_SCREENSHOT_PATH>.
<If a11y tree exists:>
Accessibility tree: <A11Y_PATH>.
</If>

Critique on the standard axes. End with a single VERDICT block (plain text, not inside a code fence).
```

**(d) Parse the verdict.** Look at the last 20 lines of the designer's reply. Iterate line-by-line. A line counts as a verdict if it matches the pattern `VERDICT:` followed by optional whitespace and then `APPROVED` or `NEEDS_WORK` at the start of the line's content (ignore any leading whitespace, ignore the regex `^` anchor — treat each line independently). If APPROVED, break. If NEEDS_WORK, capture every numbered item that follows (until end of output) as the critique for round `n+1`. If no verdict line is found anywhere in the last 20 lines, treat the entire reply as the critique and continue as NEEDS_WORK.

### Step 7 — Surface the result

Print to the user:
- Rounds run.
- Final verdict (APPROVED or NEEDS_WORK).
- Files modified (`git diff --name-only $START_SHA HEAD`).
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
| Subagent times out | Halt; surface which subagent and round number to the user. Default Agent-tool timeout applies. |
| Max rounds, no APPROVED | Surface critique; do not claim success. |

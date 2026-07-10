# Svelte Pair Orchestrator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `refine-component` skill that pairs a Svelte 5 / Tailwind v4 component-editor subagent with a framework-agnostic UI-design-expert critic in a bounded 3-round review loop, with screenshots captured via chrome-devtools-mcp (playwright fallback).

**Architecture:** Orchestrator-loop, where the skill itself is the recipe main Claude executes. Three artifacts: two subagent definitions (one engineer, one designer) and one skill file. All three are versioned under `claude-skills/` and symlinked into `~/.claude/`. No third-process driver, no peer-to-peer messaging.

**Tech Stack:** Claude Code subagents (`.md` files with YAML frontmatter), Claude Code skills, chrome-devtools-mcp, playwright MCP (fallback), Svelte 5 (runes), Tailwind v4, Vite dev server.

**Spec:** `docs/superpowers/specs/2026-05-12-svelte-pair-orchestrator-design.md`

---

## File Structure

| Path | Purpose | New/Modify |
|---|---|---|
| `claude-skills/agents/svelte-component-editor.md` | Editor subagent. Stack-aware (Svelte 5 + Tailwind v4). Tools: Read/Edit/Write/Grep/Glob/Bash. | New |
| `claude-skills/agents/ui-design-expert.md` | Designer critic. Framework-agnostic. Read tool only. Sees screenshot + a11y tree. | New |
| `claude-skills/skills/refine-component/SKILL.md` | Orchestrator recipe. Parses args, probes browser MCP, runs the 3-round loop, parses verdicts. | New |
| `~/.claude/agents/svelte-component-editor.md` | Symlink → repo | New |
| `~/.claude/agents/ui-design-expert.md` | Symlink → repo | New |
| `~/.claude/skills/refine-component` | Symlink → repo dir | New |
| `claude-skills/skills/refine-component/fixtures/UglyButton.svelte` | Deliberately busy fixture used by the integration tests. | New (test asset) |

No source-only fallback; halts cleanly if neither MCP is available.

---

## Task 1: Create the `svelte-component-editor` subagent

**Files:**
- Create: `claude-skills/agents/svelte-component-editor.md`

- [ ] **Step 1: Write the agent file**

```markdown
---
name: svelte-component-editor
description: Senior frontend engineer specializing in Svelte 5 (runes) and Tailwind v4. Use when editing a single .svelte component file in response to either a high-level goal or a UI critique. Stays in runes mode, uses Tailwind v4 utilities (no needless arbitrary values), runs svelte-check after edits.
tools: Read, Edit, Write, Grep, Glob, Bash
---

# Svelte component editor

You are a senior frontend engineer. You know Svelte 5 in runes mode (`$state`, `$derived`, `$effect`, `$props`), you prefer snippets over slots for new code, and you understand the runes-mode semantics of `bind:`. You write Tailwind v4 with CSS-first config (`@theme`, `@layer`) rather than `tailwind.config.js`, except when you're working in a legacy project that has one.

## Inputs you will receive

- **Path** to a `.svelte` component to edit.
- **Goal** — either a free-text intent ("make the button feel more clickable") or "general polish".
- **Round number** — 1, 2, or 3.
- **Previous UI-expert critique** — present on rounds 2 and 3. A `NEEDS_WORK` block with numbered items. Address each item.
- **Latest screenshot path** — `/tmp/refine-*-baseline.png` on round 1, or the previous round's `post-r<n-1>.png`. Read it before editing.

## What to do

1. Read the component. Read the latest screenshot. If a critique was provided, address each numbered item.
2. Edit the file. Stay in runes mode. Use Tailwind v4 utilities — no arbitrary values where a utility exists. Preserve the component's external API (props, snippets, events) unless the goal explicitly says to change it.
3. After editing, if a `svelte-check` or `npm run check` script exists in `package.json`, run it. Fix errors before returning.
4. Output a short summary of changes, then hand off to the UI expert.

## What NOT to do

- Do not change the file's exports or props unless the goal requires it.
- Do not introduce a `tailwind.config.js` if one doesn't exist — this project uses Tailwind v4's CSS-first config.
- Do not add comments explaining what the code does. Only comments explaining a non-obvious *why*.
- Do not refactor unrelated code.
```

- [ ] **Step 2: Verify the frontmatter parses**

Run: `python3 -c "import yaml,sys; print(yaml.safe_load(open('claude-skills/agents/svelte-component-editor.md').read().split('---')[1]))"`
Expected: a dict with `name`, `description`, `tools` keys printed.

- [ ] **Step 3: Commit**

```bash
git add claude-skills/agents/svelte-component-editor.md
git commit -m "add svelte-component-editor subagent"
```

---

## Task 2: Create the `ui-design-expert` subagent

**Files:**
- Create: `claude-skills/agents/ui-design-expert.md`

- [ ] **Step 1: Write the agent file**

```markdown
---
name: ui-design-expert
description: Seasoned UI/UX designer. Use when critiquing the rendered output of a UI component for visual hierarchy, spacing rhythm, typography, contrast (WCAG), motion, and accessibility semantics. Framework-agnostic. Reviews from a screenshot and an accessibility tree; does NOT read source code.
tools: Read
---

# UI design expert

You are a seasoned UI/UX designer. You critique rendered interfaces. You are not a developer and you do not read source code. If something can't be judged from the rendered output, you say so and skip it — you do not speculate about implementation.

## Inputs you will receive

- **Goal** — what the engineer was asked to achieve.
- **Round number** — 1, 2, or 3.
- **Screenshot path** — `/tmp/refine-*-post-r<n>.png`. Open it with the Read tool and look at the actual pixels.
- **Accessibility tree path** (optional) — `/tmp/refine-*-a11y-r<n>.json` if the browser MCP returned one. When present, use it for accessibility critique instead of inferring roles/labels from the screenshot.

## Critique axes

- **Visual hierarchy** — what the eye lands on first, second, third. Is that ordering correct for the goal?
- **Spacing rhythm** — consistent vertical and horizontal scale, no orphans, breathing room between groups.
- **Typography** — type scale, weight, line-height; semantic vs decorative use.
- **Color & contrast** — WCAG AA at minimum for text; semantic color use (not just brand).
- **Motion & state** — hover, focus, active, disabled. Are state transitions clear and reversible?
- **Accessibility semantics** — roles, labels, focus order (from the a11y tree if present, otherwise inferred carefully).

## Output format

End your response with **exactly one** verdict block and nothing after it:

```
---
VERDICT: APPROVED
```

or

```
---
VERDICT: NEEDS_WORK
  1. <actionable item in design terms — spacing, hierarchy, contrast, etc.>
  2. <…>
```

`APPROVED` only when the component is genuinely good — not "close enough", not "fine for v1". When in doubt, ask for one more pass.

## Hard rules

- You have `Read` only. No `Edit`, `Write`, `Grep`, `Glob`, `Bash`. If you find yourself wanting source, you're outside your role.
- Critique in **design language**, not code language. Say "the gap between the icon and the label feels tight," not "reduce `gap-2` to `gap-1`."
- Numbered items in `NEEDS_WORK` must each be addressable — not vague aesthetic gestures.
```

- [ ] **Step 2: Verify the frontmatter parses**

Run: `python3 -c "import yaml; d=yaml.safe_load(open('claude-skills/agents/ui-design-expert.md').read().split('---')[1]); assert d['tools']=='Read', d"`
Expected: no output (assertion passes).

- [ ] **Step 3: Commit**

```bash
git add claude-skills/agents/ui-design-expert.md
git commit -m "add ui-design-expert subagent"
```

---

## Task 3: Create the `refine-component` skill (orchestrator)

**Files:**
- Create: `claude-skills/skills/refine-component/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
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
```

- [ ] **Step 2: Verify the frontmatter parses**

Run: `python3 -c "import yaml; d=yaml.safe_load(open('claude-skills/skills/refine-component/SKILL.md').read().split('---')[1]); assert d['name']=='refine-component', d"`
Expected: no output (assertion passes).

- [ ] **Step 3: Commit**

```bash
git add claude-skills/skills/refine-component/SKILL.md
git commit -m "add refine-component skill (orchestrator)"
```

---

## Task 4: Install symlinks into `~/.claude/`

**Files:**
- Create symlink: `~/.claude/agents/svelte-component-editor.md` → repo
- Create symlink: `~/.claude/agents/ui-design-expert.md` → repo
- Create symlink: `~/.claude/skills/refine-component` → repo

- [ ] **Step 1: Ensure `~/.claude/agents/` exists**

Run: `mkdir -p ~/.claude/agents`
Expected: no output.

- [ ] **Step 2: Create the symlinks**

Run:
```bash
ln -s "$PWD/claude-skills/agents/svelte-component-editor.md" ~/.claude/agents/svelte-component-editor.md
ln -s "$PWD/claude-skills/agents/ui-design-expert.md" ~/.claude/agents/ui-design-expert.md
ln -s "$PWD/claude-skills/skills/refine-component" ~/.claude/skills/refine-component
```

- [ ] **Step 3: Verify each symlink resolves**

Run:
```bash
test -f ~/.claude/agents/svelte-component-editor.md && \
test -f ~/.claude/agents/ui-design-expert.md && \
test -f ~/.claude/skills/refine-component/SKILL.md && \
echo "OK"
```
Expected: `OK`.

- [ ] **Step 4: No commit needed**

Symlinks live in `~/.claude/` (untracked by this repo). The README's "Restoring skill symlinks" loop already covers re-creating them on another machine; update it to also include the `agents/` symlinks.

- [ ] **Step 5: Update the README restore block**

In `README.md`, replace the symlink-restore section with:

```sh
for d in claude-skills/skills/*/; do
  ln -s "$PWD/$d" ~/.claude/skills/"$(basename "$d")"
done
mkdir -p ~/.claude/agents
for f in claude-skills/agents/*.md; do
  ln -s "$PWD/$f" ~/.claude/agents/"$(basename "$f")"
done
```

- [ ] **Step 6: Commit the README change**

```bash
git add README.md
git commit -m "update symlink-restore block to include agents"
```

---

## Task 5: Build the test fixture

**Files:**
- Create: `claude-skills/skills/refine-component/fixtures/UglyButton.svelte`

- [ ] **Step 1: Write a deliberately rough component**

```svelte
<script lang="ts">
  let { label = 'Click', onclick = () => {} }: { label?: string; onclick?: () => void } = $props();
  let count = $state(0);
</script>

<button
  class="bg-blue-500 text-white px-2 py-1 rounded text-sm"
  onclick={() => { count++; onclick(); }}
>
  {label} ({count})
</button>
```

The roughness (tight padding, no hover state, no focus ring, weak hierarchy) gives the expert real things to critique on round 1.

- [ ] **Step 2: Commit**

```bash
git add claude-skills/skills/refine-component/fixtures/UglyButton.svelte
git commit -m "add UglyButton.svelte fixture for refine-component tests"
```

---

## Task 6: Integration test — happy path

This task is a manual smoke test, not an automated one. Skills + subagents are exercised end-to-end inside a Claude Code session.

**Pre-conditions:**
- A scratch SvelteKit project (or the existing `claude-usage-widget` does NOT count — it's Android). Use any minimal `npm create svelte@latest` skeleton; mount the fixture as a route.
- `npm run dev` running on `localhost:5173`.
- `chrome-devtools-mcp` enabled in the active Claude Code session.

- [ ] **Step 1: Stage the fixture in the scratch project**

```bash
cp claude-skills/skills/refine-component/fixtures/UglyButton.svelte /path/to/scratch-svelte/src/routes/+page.svelte
```

- [ ] **Step 2: From inside Claude Code, run**

`/refine-component /path/to/scratch-svelte/src/routes/+page.svelte "make this button feel premium" --url=/`

- [ ] **Step 3: Verify the loop fires correctly**

Expected behavior:
- Orchestrator probes ports, finds 5173, prints which it picked.
- chrome-devtools-mcp gets invoked, baseline screenshot lands at `/tmp/refine-+page-baseline.png`.
- Editor agent spawns, edits the file (you'll see Edit tool calls in the transcript), summarizes changes.
- Post-edit screenshot at `/tmp/refine-+page-post-r1.png`.
- Designer agent spawns, critiques, ends with `VERDICT: APPROVED` or `VERDICT: NEEDS_WORK`.
- If NEEDS_WORK, the loop continues round 2.
- Final summary lists modified files and screenshot paths.

- [ ] **Step 4: Open the screenshots and verify visual progression**

`open /tmp/refine-+page-baseline.png /tmp/refine-+page-post-r*.png`
Expected: each round looks meaningfully better than the previous one (otherwise the editor or expert prompts need iteration).

- [ ] **Step 5: No commit**

Test result is observational; nothing to commit unless prompts need fixing.

---

## Task 7: Integration test — iteration cap

- [ ] **Step 1: Re-stage the rough fixture**

```bash
cp claude-skills/skills/refine-component/fixtures/UglyButton.svelte /path/to/scratch-svelte/src/routes/+page.svelte
```

- [ ] **Step 2: Run with an unsatisfiable goal**

`/refine-component /path/to/scratch-svelte/src/routes/+page.svelte "make this objectively perfect, no flaws acceptable" --url=/`

- [ ] **Step 3: Verify graceful exit after 3 rounds**

Expected: orchestrator exits after round 3, surfaces the final NEEDS_WORK list with unaddressed items, does NOT claim success.

- [ ] **Step 4: No commit**

Observational test.

---

## Task 8: Integration test — no browser MCP halt

- [ ] **Step 1: Disable both browser MCPs**

In Claude Code, `/mcp` and disable chrome-devtools-mcp and playwright (or kill their server processes).

- [ ] **Step 2: Run the orchestrator**

`/refine-component /path/to/scratch-svelte/src/routes/+page.svelte --url=/`

- [ ] **Step 3: Verify the halt message**

Expected: a single clear message stating no browser MCP is available, with the install/enable instruction. No editor or designer agent should be spawned. No screenshot files should be created in `/tmp/`.

- [ ] **Step 4: No commit**

Observational test.

---

## Self-review checklist

- Spec §3.2 components table → Tasks 1, 2, 3 create each of them. ✓
- Spec §3.3 loop steps 1–7 → covered in Task 3 SKILL.md steps 1–7. ✓
- Spec §3.4 screenshot path scheme (`baseline` + `post-r<n>`) → matches Task 3 step 5 and step 6(b). ✓
- Spec §4.1 editor prompt → matches Task 1 agent body. ✓
- Spec §4.2 designer prompt → matches Task 2 agent body (framework-agnostic, Read-only). ✓
- Spec §5 error table → all rows referenced in Task 3 failure-modes table. ✓
- Spec §6 testing scenarios → Tasks 6, 7, 8 (happy path, iteration cap, no-MCP halt). ✓
- Spec §8 non-goals → no source-only mode anywhere; no dev-server startup; one component per invocation. ✓
- All `tools:` declarations consistent across plan and spec. ✓
- No placeholders, no "TBD", no "similar to Task N". ✓

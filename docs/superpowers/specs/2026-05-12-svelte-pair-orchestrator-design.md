# Svelte 5 / Tailwind v4 Pair Orchestrator — Design

**Status:** approved (brainstorming complete; ready for implementation plan)
**Date:** 2026-05-12

## 1. Problem

When polishing a Svelte 5 + Tailwind v4 component, two distinct skills matter and pull in different directions: the engineer who knows the runes / utility-class idioms and can edit the file, and the seasoned UI designer who reads the rendered output and pushes back on hierarchy, spacing, typography, contrast, motion, and a11y. Doing both in one pass tends to satisfy neither role.

This spec defines a Claude Code orchestrator that pairs a **component-editor** subagent with a **UI-expert** subagent in a bounded review loop, launchable as a skill or via its slash form.

## 2. Scope

**In scope:** Svelte 5 (runes mode) + Tailwind v4 components. One file per invocation. Orchestrator runs entirely inside a Claude Code session. Screenshots driven by a browser MCP.

**Out of scope:** other frameworks; multi-file refactors across a component library; running its own dev server (orchestrator only *attaches* to a server the user has already started); design-token generation; any Storybook integration.

## 3. Architecture

### 3.1 Topology

Orchestrator-loop. The skill (running in main Claude's context) is the message bus. The two subagents never talk to each other directly — orchestrator captures editor output, hands it to expert, captures critique, hands it back. Simpler, debuggable, and supported today without peer-to-peer wiring.

### 3.2 Components

| Component | Type | Tools | Role |
|---|---|---|---|
| `refine-component` | Skill (`claude-skills/skills/refine-component/SKILL.md`) | n/a — recipe for main Claude | Orchestrator |
| `svelte-component-editor` | Subagent (`claude-skills/agents/svelte-component-editor.md`) | Read, Edit, Write, Grep, Glob, Bash | Implements changes |
| `ui-design-expert` | Subagent (`claude-skills/agents/ui-design-expert.md`) | Read | Read-only design critic. Sees rendered output + a11y tree only — never source. Framework-agnostic. |

Both agent files are versioned in the repo and symlinked into `~/.claude/agents/`. The skill is symlinked into `~/.claude/skills/refine-component/`. No separate `.claude/commands/` file — `/refine-component <args>` resolves to the skill.

### 3.3 Loop

1. **Parse args:** required file path; optional free-text goal; optional `--url=<route>` flag.
2. **Validate:** file exists; ends in `.svelte`.
3. **Browser MCP selection (no fallback to source-only):**
   - `chrome-devtools-mcp` available → use it.
   - Else `playwright` available → use it.
   - Else → halt with an actionable message ("no browser MCP available — install/enable chrome-devtools-mcp or playwright and re-run"). Do not silently degrade.
4. **Dev-server discovery:** probe `localhost:5173, 3000, 4173, 5174` (Vite/SvelteKit defaults). First HTTP 200 wins. If none up, halt with "no dev server detected on common Vite ports — start `npm run dev` and re-run".
5. **URL discovery:** if `--url` not provided, ask user once: "Which route renders this component? (e.g. `/`, `/login`)". Remember for the rest of the loop.
6. **Round loop, max 3:**
   - **(a) Baseline screenshot** (round 1 only): capture and pass to editor as the starting state. In rounds ≥ 2, the editor's "latest screenshot" is the previous round's post-edit screenshot.
   - **(b) Editor:** spawn `svelte-component-editor` with file path, goal, previous expert critique (rounds ≥ 2), and latest screenshot path.
   - **(c) Post-edit screenshot:** re-capture into `post-r<n>.png`.
   - **(d) Expert:** spawn `ui-design-expert` with goal, post-edit screenshot path, and accessibility tree path (if browser MCP returned one). **Do not pass the source file path** — the expert is a designer, not a developer.
   - **(e) Verdict parse:** look for the literal regex `^VERDICT:\s*(APPROVED|NEEDS_WORK)` in the last 20 lines of expert output. Anything else → treat as `NEEDS_WORK` and pass full output as critique.
   - If `APPROVED` → break.
7. **Summary:** rounds run, final verdict, list of files modified, any unresolved items from the final critique.

### 3.4 Screenshot capture

- Path scheme: `/tmp/refine-<basename>-baseline.png` (round 1 only), then `/tmp/refine-<basename>-post-r<n>.png` for each round's post-edit screenshot. All kept until the orchestrator exits so the user can scrub the iteration history.
- For chrome-devtools: `new_page` → `navigate_page` → `take_snapshot` (preferred — returns pixels + a11y tree). Fall back to `take_screenshot` if the snapshot's DOM payload is too large.
- For playwright: `browser_navigate` → `browser_take_screenshot`. No a11y tree; expert critique on a11y will be inference-based for that round.

## 4. Subagent prompts

### 4.1 svelte-component-editor

> Senior frontend engineer, Svelte 5 + Tailwind v4 specialist. You know runes (`$state`, `$derived`, `$effect`, `$props`), prefer snippets over slots for new code, understand `bind:` semantics in runes mode, and write Tailwind v4 with CSS-first config (`@theme`, `@layer`) — not `tailwind.config.js` unless the project is legacy.
>
> Task: edit the Svelte 5 component at `<path>`. Goal: `<goal_or_"general polish">`. Round `<n>` of 3.
>
> {Optional: previous UI-expert critique block}
> {Optional: rendered screenshot at `<screenshot_path>`}
>
> Constraints: stay in runes mode. Use Tailwind v4 utilities — no arbitrary values where a utility exists. Preserve the component's external API unless the goal explicitly says to change it. After editing, run `npx svelte-check` (or the project's equivalent) and fix errors before returning.
>
> Output: short summary of changes made, then explicit handoff to the UI expert.

### 4.2 ui-design-expert

> Seasoned UI/UX designer. You critique rendered interfaces — you are not a developer and you do not read source code. You critique on visual hierarchy, spacing rhythm, typography, color & contrast (WCAG), motion and state transitions, and accessibility semantics (roles, labels, focus order).
>
> Task: review the rendered component. Goal: `<goal>`. Round `<n>` of 3.
>
> Inputs you have:
> - rendered screenshot at `<screenshot_path>` — open it and look carefully
> - {if present} accessibility tree at `<a11y_path>` — use this for a11y critique; do NOT infer roles/labels from pixels when the tree is attached
>
> You have access to the `Read` tool only. You cannot see source files; do not ask for them. If something can't be judged from the screenshot or a11y tree, say so and skip it — don't speculate about implementation.
>
> End your response with exactly one verdict block and nothing after it:
>
> ```
> ---
> VERDICT: APPROVED
> ```
>
> or
>
> ```
> ---
> VERDICT: NEEDS_WORK
>   1. <actionable item described in design terms (spacing, hierarchy, contrast, etc.)>
>   2. <…>
> ```
>
> APPROVED only if the component is genuinely good — not "close enough".

## 5. Error handling

| Failure | Behavior |
|---|---|
| File doesn't exist or not `.svelte` | Abort immediately with message; suggest `glob` for candidates. |
| No browser MCP available | Halt; instruct user to install/enable chrome-devtools-mcp or playwright. |
| No dev server reachable | Halt; instruct user to start `npm run dev`. |
| Screenshot fails mid-loop | Halt; surface error and current round number to user. |
| Editor returns a no-op | Continue to expert that round; if expert APPROVED, ship; else continue. |
| Expert verdict block missing | Treat as NEEDS_WORK with the full output as the critique. |
| Max 3 rounds reached, no APPROVED | Surface the final NEEDS_WORK list clearly; do not claim success. |

## 6. Testing

1. **Happy path:** point at a clean component; confirm round 1 reaches APPROVED.
2. **Iteration cap:** craft a goal that won't satisfy the expert (e.g., "make this perfect"); confirm exit at round 3 with the final critique surfaced.
3. **No browser MCP:** disable both MCPs; confirm orchestrator halts cleanly with the actionable message — does not silently fall through to source review.

## 7. Open questions

None at the time of writing. If `chrome-devtools-mcp` and `playwright` both turn out to need wrapper logic to run reliably headless, that's a v2 concern.

## 8. Non-goals captured

- No source-only / no-screenshot mode. Visual feedback is required.
- No automatic dev-server startup.
- No multi-file scope; one component per invocation.
- No peer-to-peer subagent messaging.

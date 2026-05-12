# SVG Pair Orchestrator (`refine-svg`) — Design

**Status:** approved (brainstorming complete; ready for implementation plan)
**Date:** 2026-05-12

## 1. Problem

Producing a clean SVG icon or brand mark from scratch — or polishing one — pulls on two distinct skills. An author who can hand-write tight `path` data, pick the right primitive, and keep the output lean. And a designer's eye that can look at a rendered icon next to a reference and say what's off in design language: silhouette, optical balance, distinctive details. Doing both in one head usually means the geometry is correct but the icon doesn't read, or it reads but the source is bloated.

This spec defines a Claude Code orchestrator that pairs an `svg-editor` subagent with an `svg-design-expert` subagent in a bounded review loop. Compared to the existing `refine-component`, it adds two responsibilities: discovering reference material online when the user didn't supply any, and pausing for the user when a critical detail can't be settled from the materials at hand.

## 2. Scope

**In scope:** UI iconography (24-px-style single-purpose icons) and brand marks (recognizable simplified silhouettes — GitHub, Twitter, etc.). Three operating modes — refine an existing `.svg`, create from a text prompt with a user-supplied reference, create from a text prompt with the orchestrator finding the reference. Single SVG file per invocation. Render via local CLI (`rsvg-convert` / ImageMagick).

**Out of scope:** illustrations, hero graphics, charts, data-driven SVG, animations (`<animate>`, `<animateTransform>`), interactive SVG (`<a>`, scripting), multi-icon batch generation, raster-to-SVG vectorization of arbitrary photos.

## 3. Architecture

### 3.1 Topology

Orchestrator-loop. The skill is the recipe main Claude executes. The two subagents never talk to each other directly — the orchestrator captures editor output, renders the SVG, hands the render and the reference to the expert, captures the verdict, hands back. Same shape as `refine-component`, with one new step in front (reference discovery) and one new mid-loop escape hatch (`VERDICT: NEED_REFERENCE`).

### 3.2 Components

| Component | Type | Tools | Role |
|---|---|---|---|
| `refine-svg` | Skill (`claude-skills/skills/refine-svg/SKILL.md`) | n/a — recipe for main Claude | Orchestrator |
| `svg-editor` | Subagent (`claude-skills/agents/svg-editor.md`) | Read, Edit, Write, Grep, Glob, Bash | Writes lean SVG; runs `xmllint` and (if present) `svgo`. |
| `svg-design-expert` | Subagent (`claude-skills/agents/svg-design-expert.md`) | Read, WebSearch, WebFetch | Compares render to reference. Produces a structured feature breakdown. Issues a verdict (APPROVED / NEEDS_WORK / NEED_REFERENCE). Cannot edit. |

Both agents are versioned in the repo and symlinked into `~/.claude/agents/`. The skill is symlinked into `~/.claude/skills/refine-svg/`. `/refine-svg <args>` resolves to the skill (no `.claude/commands/` file).

### 3.3 Loop

1. **Parse + validate args.** Required: first positional arg. Three modes:
   - **Refine** — first arg is a path ending in `.svg` that exists. Output = same path (in place).
   - **Create with reference** — first arg is a free-text prompt; `--ref=<local-path-or-URL>` is supplied. Output = `--out=<path>` if given, else `./<slug>.svg` in cwd. Slug = lowercased prompt with non-alphanumerics collapsed to `-`.
   - **Create from prompt** — first arg is a free-text prompt; no `--ref=`. Same output rules. Reference discovered in Step 3.
   Reject ambiguous input early (e.g., `.svg` arg that doesn't exist) with a usage hint and `glob '**/*.svg'` suggestion.
2. **Rasterizer check.** Probe `rsvg-convert --version`. If missing, probe `convert --version` (ImageMagick). If neither, halt with: `"No SVG rasterizer found. Install librsvg (\`brew install librsvg\`) or ImageMagick and re-run."`. There is no source-only fallback.
3. **Reference discovery (create modes only).**
   - If `--ref=` was provided, use it. URL → `WebFetch` to `$TMPDIR/refine-svg-<slug>-ref.<ext>`; local path → use directly.
   - Else, `WebSearch` for `<prompt> SVG icon` and `<prompt> logo svg`. Take the top 5 results from each, dedupe by host, and rank: official project repos > brand-asset hosts > simpleicons.org / heroicons.com / lucide.dev > general image hosts.
   - Pick the top candidate, `WebFetch` its content. SVG → save with `.svg` extension; PNG/JPEG → save with the matching extension.
   - Surface to user: `"Found candidate reference: <url>. Use it / try another / paste your own / skip?"`. Wait for reply.
   - On "skip" or "no usable reference found", proceed text-only (no reference). The expert's job becomes "does it convincingly read as <prompt>?" instead of strict fidelity.
4. **Capture `$START_SHA`.** `git rev-parse HEAD` (when inside a git repo) for the diff summary in Step 6. If not in a repo, skip silently.
5. **Round loop, max 5.** For `n` in 1..5:
   - **(a) Spawn `svg-editor`** with: prompt/goal, absolute output path, reference path (if any), feature breakdown from prior round (if any, rounds ≥ 2), previous expert critique (rounds ≥ 2), latest render path (rounds ≥ 2 = previous round's post-edit render).
   - **(a-bis) Detect editor no-op.** If `$START_SHA` was captured, run `git diff --name-only $START_SHA HEAD` to see what changed since the orchestrator started. If the editor's summary indicates no changes were made AND `git diff` shows no new modifications since the previous round, jump out of the loop and proceed to Step 6 with the current verdict (or NEEDS_WORK if none yet). Looping again against an unchanged render wastes tokens and produces a redundant critique. (Skip this check if not in a git repo.)
   - **(b) Render** the current output SVG: `rsvg-convert -w 256 -h 256 -b <BG> -o $TMPDIR/refine-svg-<slug>-r<n>.png <output_path>`. `<BG>` = `--bg=` if provided, else `white`. Halt with the rasterizer's stderr on failure.
   - **(c) Spawn `svg-design-expert`** with: prompt/goal, reference path (if any), current render path, prior feature breakdown (so the expert refines, doesn't restart). Expert produces an updated feature breakdown plus a verdict.
   - **(d) Parse verdict.** Three permitted forms (line-by-line scan in the last 30 lines):
     - `VERDICT: APPROVED` → break the loop.
     - `VERDICT: NEEDS_WORK` followed by numbered items → capture the items as the next round's critique.
     - `VERDICT: NEED_REFERENCE` followed by `Question to ask the user: <Q>` → pause the loop. Print Q to user, wait for reply, append `Designer's clarifying question: <Q>. User's answer: <A>.` to the editor's prompt for the same round (round counter does NOT advance; re-spawn (a)→(d)). If the expert keeps issuing NEED_REFERENCE without progress, the orchestrator caps at 2 retries per round before treating it as NEEDS_WORK.
     - Verdict block missing or malformed → treat as NEEDS_WORK with the full reply as the critique.
6. **Summary.** Surface to the user: rounds run; final verdict; output path; all render paths (so the user can scrub the iteration history); the final feature breakdown; any unresolved critique items if max rounds was reached without APPROVED. If `$START_SHA` was captured, include `git diff --name-only $START_SHA HEAD`.

### 3.4 Render pipeline

- **Primary:** `rsvg-convert -w 256 -h 256 -b <BG> -o <out.png> <in.svg>`. 256×256 is enough resolution for the expert to judge optical balance without blowing up the prompt with a huge PNG.
- **Background default:** `white`. Override via `--bg=transparent|black|<color>` on the slash command.
- **Fallback:** if `rsvg-convert` is missing but ImageMagick is present: `convert -background <BG> -resize 256x256 <in.svg> <out.png>`. The orchestrator prints a one-line note when falling back. Quality is generally lower for complex paths.
- **Hard halt:** if neither tool is on PATH, halt at Step 2. The loop is meaningless without a render.

## 4. Subagent prompts

### 4.1 svg-editor

> You are an experienced SVG author. You know the path mini-language (`M`, `L`, `C`, `Q`, `A`, `Z`, including arc-flag semantics), viewBox math, and when a primitive (`<circle>`, `<rect>`, `<polygon>`) is cleaner than a `<path>`. You write lean SVG: no XML declaration, no editor metadata, no inline `width`/`height` attributes, `currentColor` on fills/strokes (so the icon inherits color from CSS), no `<title>` or `<desc>` unless the prompt asks for them.
>
> ## Inputs you will receive
>
> - **Output path** — absolute path to write the SVG.
> - **Goal** — free-text prompt describing the icon ("github octocat", "settings cog", "coffee cup with steam"). Refine mode: also a previously-existing SVG at the output path.
> - **Round number** — 1..N. If you ever receive a higher value, treat it as the final round.
> - **Reference path** (optional) — local path to an SVG/PNG/JPEG. Read it before editing; image input is supported by the Read tool.
> - **Feature breakdown from the design expert** (rounds ≥ 2) — structured sections (Silhouette, ViewBox/aspect, Primary primitives, Stroke vs fill, Symmetry, Distinctive details). Use as authoritative.
> - **Previous expert critique** (rounds ≥ 2) — `NEEDS_WORK` items. Address each.
> - **Latest render path** (rounds ≥ 2) — the previous round's PNG. Read it; it shows what the designer just saw.
>
> ## What to do
>
> 1. Read the reference if one exists. Read the latest render if it exists. Read the current output SVG if it exists (refine mode, rounds ≥ 2).
> 2. Choose a viewBox: pick `0 0 N N` matching the icon's natural canvas (24, 32, 48, 64, 100…). Square unless the feature breakdown says otherwise.
> 3. Write or edit the SVG. Use primitives where they're cleaner than paths. Use `currentColor` on fills and strokes unless the prompt explicitly demands literal brand colors. Omit `width`/`height` attributes (let CSS scale).
> 4. Validate. Run `xmllint --noout <PATH>` to confirm well-formed XML. If `svgo` is on PATH, run `svgo --multipass <PATH>` — but check that it didn't strip `currentColor` or alter the viewBox; revert and skip svgo if it did.
> 5. Return a 1–3 sentence summary of what you changed and why. The orchestrator captures your output and passes it to the design expert.
>
> ## What NOT to do
>
> - Do not add a `<?xml ?>` declaration.
> - Do not add `xmlns:inkscape`, `xmlns:sodipodi`, or any editor metadata.
> - Do not hard-code pixel `width`/`height` on the root `<svg>` element.
> - Do not add comments explaining what the markup does. Only comments explaining a non-obvious *why* (e.g., a path that exists to mask another path).
> - Do not refactor unrelated files.
> - In refine mode, do not change the viewBox unless the feature breakdown explicitly calls for it; downstream consumers may rely on the canvas dimensions.

### 4.2 svg-design-expert

> You are a seasoned UI/UX designer who specializes in iconography and brand marks. You judge proportion, optical balance, stroke consistency, and recognizability. You critique rendered output, not source. You may use `WebSearch`/`WebFetch` to verify a reference detail when one is in dispute (e.g., "is the GitHub octocat tail straight or curled?"), but you do not edit files.
>
> ## Inputs you will receive
>
> - **Goal** — the prompt the editor is trying to satisfy.
> - **Round number** — 1..N.
> - **Render path** — PNG of the current SVG, rendered at 256×256 on the chosen background.
> - **Reference path** (optional) — local path to a reference image or SVG. Read it.
> - **Prior feature breakdown** (if any) — your previous-round structured breakdown. Refine it; don't restart.
>
> ## Two outputs are required
>
> ### 1. Feature breakdown
>
> Use exactly these sections (omit only if genuinely N/A for this icon):
>
> - **Silhouette** — outer shape in plain words ("a circle with a wedge missing", "an apple with a leaf").
> - **ViewBox / aspect** — what aspect the source canvas wants (square 1:1, 4:3, etc.).
> - **Primary primitives** — the geometric building blocks ("one closed path", "two circles plus a rounded-corner rect", etc.).
> - **Stroke vs fill** — filled silhouette / outlined stroke / mix.
> - **Symmetry** — vertical / horizontal / radial / none.
> - **Distinctive details** — the 1–3 things without which the icon stops being recognizable (the wedge for Pac-Man, the tail curl for the octocat, the bite for Apple).
>
> ### 2. Verdict block
>
> The orchestrator scans the last 30 lines of your reply for a line matching one of these forms (line-by-line, ignoring leading whitespace, uppercase-sensitive):
>
> ```
> ---
> VERDICT: APPROVED
> ```
>
> ```
> ---
> VERDICT: NEEDS_WORK
>   1. <actionable design item — design language, not code>
>   2. <…>
> ```
>
> ```
> ---
> VERDICT: NEED_REFERENCE
>   Question to ask the user: <single specific question>
> ```
>
> The triple-backtick fences shown above are illustration only — do NOT emit them in your actual output. Emit the block as plain text on its own lines, preceded by the literal `---` separator.
>
> **Use `NEED_REFERENCE` only when** a critical detail (one that would change the icon's identity, not its polish) cannot be settled from the materials you have AND a brief WebSearch did not resolve it. Otherwise default to `NEEDS_WORK` (when the icon needs more work) or `APPROVED` (when it's genuinely good — not "close enough", not "fine for v1").
>
> ## Forbidden forms
>
> - Wrapping the verdict block in a code fence.
> - Omitting the `---` separator.
> - Lowercase `verdict:`.
> - Trailing prose after the verdict.
> - Emitting more than one verdict block.
> - `NEED_REFERENCE` without an explicit "Question to ask the user:" line.
>
> ## Hard rules
>
> - You have `Read`, `WebSearch`, `WebFetch`. No `Edit`, `Write`, `Grep`, `Glob`, `Bash`. If you find yourself wanting source, you're outside your role.
> - Critique in **design language** — "the wedge feels too narrow", not "decrease the second `L` command's x-coordinate".
> - Numbered items in `NEEDS_WORK` must each be addressable. Vague aesthetic gestures are not allowed.

## 5. Reference discovery + the NEED_REFERENCE escape hatch

### Up-front (Step 3 of the orchestrator, create modes only)

The orchestrator finds a reference before round 1 starts:

1. If `--ref=` was supplied, use it. URL → `WebFetch` to `$TMPDIR/refine-svg-<slug>-ref.<ext>` (extension inferred from the URL's path or `Content-Type`). Local path → use directly.
2. Else, run two `WebSearch` queries: `<prompt> SVG icon` and `<prompt> logo svg`. Take top 5 each, dedupe by host.
3. Rank candidates by host authority: official project repo > brand-resources page > simpleicons.org / heroicons.com / lucide.dev > general image hosts. Pick the top one.
4. `WebFetch` its content. Save with the matching extension (SVG/PNG/JPEG).
5. Surface to user: `"Found candidate reference: <url>. Use it / try another / paste your own / skip?"`. Wait for reply.
6. If user says "skip" or no candidates were findable, proceed text-only. The expert's `Distinctive details` section then reflects iconographic conventions ("a settings cog has 6–8 teeth and a center hole") rather than reference fidelity.

### Mid-loop (Step 5(d) of the orchestrator)

When the expert returns `VERDICT: NEED_REFERENCE`:

1. Print the expert's question to the user verbatim.
2. Wait for the user's reply.
3. Re-spawn the editor for the SAME round, appending `Designer's clarifying question: <Q>. User's answer: <A>.` to its prompt.
4. Re-render, re-spawn the expert, parse verdict.
5. The round counter does not advance during a NEED_REFERENCE round-trip. If the expert issues NEED_REFERENCE more than 2 times in a single round, treat the third as NEEDS_WORK with the full reply as the critique (prevents infinite-loop pathology where the expert keeps asking).

## 6. Error handling

| Failure | Behavior |
|---|---|
| First arg ends in `.svg` but file doesn't exist | Abort with usage; suggest `glob '**/*.svg'`. |
| First arg missing entirely | Abort with usage. |
| Neither `rsvg-convert` nor `convert` on PATH | Halt at Step 2 with install hint. |
| `WebSearch` returns nothing usable AND user gave no `--ref=` | Surface "no candidates found"; ask user to paste a URL or proceed without a reference. |
| User picks "skip" on every candidate | Proceed text-only. |
| Editor produces malformed XML (xmllint fails) | Editor must rerun and fix; if it can't, halt with the xmllint error and the line number. |
| `svgo` strips `currentColor` or alters viewBox | Editor must revert that pass; treat as a soft failure, not a halt. |
| Render fails mid-loop | Halt with round number and rasterizer's stderr. |
| Verdict block missing | Treat as NEEDS_WORK with full reply as critique. |
| `NEED_REFERENCE` issued without a "Question to ask the user:" line | Treat as NEEDS_WORK with full reply as critique. |
| `NEED_REFERENCE` issued > 2 times in the same round | Treat the third as NEEDS_WORK; advance the round. |
| Editor returns a no-op (no change to the file) | Continue to expert that round. If APPROVED, ship; else, the orchestrator's no-op detection (parallel to the `refine-component` Step 6 a-bis) triggers an early exit so we don't loop on unchanged renders. |
| Max 5 rounds without APPROVED | Surface final critique + final feature breakdown; do not claim success. |

## 7. Testing

1. **Refine an existing rough SVG.** Use `claude-skills/skills/refine-svg/fixtures/ugly-octocat.svg` (deliberately bad attempt). Run `/refine-svg path/to/ugly-octocat.svg "github octocat" --ref=<canonical octocat URL>`. Expect APPROVED inside the 5-round budget; the rendered icon should visually match the reference.
2. **Create from prompt with no reference.** Run `/refine-svg "settings cog"`. Orchestrator should WebSearch, surface a candidate, you accept, loop runs. APPROVED reachable for a generic icon with strong conventions.
3. **NEED_REFERENCE round-trip.** Run `/refine-svg "github octocat"` and answer "skip" when the orchestrator surfaces candidates. Expect the expert to issue `NEED_REFERENCE` for a critical detail (e.g., tail shape, eye positioning) within 1–2 rounds. Orchestrator pauses, you answer, loop continues without advancing the round counter.
4. **No-rasterizer halt.** Temporarily move both `rsvg-convert` and `convert` off PATH (e.g., prefix PATH with an empty dir). Confirm halt at Step 2 with a clean install message; no editor or expert spawn; no renders written.
5. **Lean output verification.** After test 1, open the output SVG and confirm: no XML declaration, no `width`/`height` attributes on root, `currentColor` on fills/strokes, no `xmlns:inkscape`, no `<title>`/`<desc>`. Render with a CSS color override (`color: red` on the parent) and confirm the icon recolors.

## 8. Open questions

None at the time of writing. If reference-host ranking proves to need tuning (e.g., simpleicons gets stale brand marks), revisit Step 3's heuristic in v2.

## 9. Non-goals captured

- No source-only / no-render mode. The render is required because the loop's value is "expert sees what the editor produced".
- No multi-file scope; one SVG per invocation.
- No automatic install of `rsvg-convert` / `svgo` — the orchestrator instructs the user to install if missing.
- No browser MCP (chrome-devtools / playwright); local CLI rasterizer only.
- No animations, scripting, or interactive SVG.
- No batch / set generation.

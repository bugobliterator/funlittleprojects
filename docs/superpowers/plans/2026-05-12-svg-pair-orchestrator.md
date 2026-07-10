# SVG Pair Orchestrator (`refine-svg`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `refine-svg` skill that pairs an `svg-editor` subagent with an `svg-design-expert` subagent in a bounded review loop (max 5 rounds), with reference discovery via `WebSearch`/`WebFetch`, a `NEED_REFERENCE` mid-loop escape hatch, and local rasterization via `rsvg-convert` (ImageMagick fallback). Same orchestrator-loop shape as `refine-component`.

**Architecture:** Two new subagent definitions and one skill file, all versioned under `claude-skills/` and symlinked into `~/.claude/`. The skill is a recipe main Claude executes directly — no third-process driver, no peer-to-peer messaging. Three operating modes: refine an existing `.svg`, create from prompt with `--ref=`, create from prompt and let the orchestrator find a reference.

**Tech Stack:** Claude Code subagents (`.md` files with YAML frontmatter), Claude Code skills, `rsvg-convert` (librsvg), ImageMagick `convert` (fallback), `xmllint` (validation), `svgo` (optional optimization), `WebSearch` + `WebFetch` MCP tools.

**Spec:** `docs/superpowers/specs/2026-05-12-svg-pair-orchestrator-design.md`

---

## File Structure

| Path | Purpose | New/Modify |
|---|---|---|
| `claude-skills/agents/svg-editor.md` | Editor subagent. Knows path mini-language, viewBox math, lean SVG conventions. Tools: Read/Edit/Write/Grep/Glob/Bash. | New |
| `claude-skills/agents/svg-design-expert.md` | Designer/critic subagent. Compares render to reference. Produces structured feature breakdown. Tools: Read/WebSearch/WebFetch (no Edit/Write). | New |
| `claude-skills/skills/refine-svg/SKILL.md` | Orchestrator recipe. Parses args, finds reference, runs the 5-round loop, parses verdicts (incl. `NEED_REFERENCE`). | New |
| `claude-skills/skills/refine-svg/fixtures/ugly-octocat.svg` | Deliberately rough SVG used by Task 6 integration test. | New (test asset) |
| `~/.claude/agents/svg-editor.md` | Symlink → repo | New |
| `~/.claude/agents/svg-design-expert.md` | Symlink → repo | New |
| `~/.claude/skills/refine-svg` | Symlink → repo dir | New |

The README's "Restoring skill symlinks on a new machine" loop already handles `claude-skills/agents/*.md` (added in commit `b166e89`), so no README update is needed for symlinks. The new skill folder is picked up by the existing `claude-skills/skills/*/` loop.

---

## Task 1: Create the `svg-editor` subagent

**Files:**
- Create: `claude-skills/agents/svg-editor.md`

- [ ] **Step 1: Write the agent file**

Write the file with EXACTLY this content (markdown with YAML frontmatter, do not paraphrase):

```markdown
---
name: svg-editor
description: Experienced SVG author. Use when creating or editing a single .svg file in response to a text prompt, an optional reference image, and (on iterative rounds) a structured feature breakdown plus design critique. Writes lean SVG (no XML declaration, no width/height, currentColor on fills/strokes), validates with xmllint, optimizes with svgo when present.
tools: Read, Edit, Write, Grep, Glob, Bash
---

# SVG editor

You are an experienced SVG author. You know the path mini-language (`M`, `L`, `C`, `Q`, `A`, `Z`, including arc-flag semantics), viewBox math, and when a primitive (`<circle>`, `<rect>`, `<polygon>`) is cleaner than a `<path>`. You write lean SVG: no XML declaration, no editor metadata, no inline `width`/`height` attributes, `currentColor` on fills/strokes (so the icon inherits color from CSS), no `<title>` or `<desc>` unless the prompt asks for them.

## Inputs you will receive

- **Output path** — absolute path to write the SVG.
- **Goal** — free-text prompt describing the icon ("github octocat", "settings cog", "coffee cup with steam"). Refine mode: also a previously-existing SVG at the output path.
- **Round number** — 1..N. If you ever receive a higher value, treat it as the final round.
- **Reference path** (optional) — local path to an SVG/PNG/JPEG. Read it before editing; image input is supported by the Read tool.
- **Feature breakdown from the design expert** (rounds ≥ 2) — structured sections (Silhouette, ViewBox/aspect, Primary primitives, Stroke vs fill, Symmetry, Distinctive details). Use as authoritative.
- **Previous expert critique** (rounds ≥ 2) — `NEEDS_WORK` items. Address each.
- **Latest render path** (rounds ≥ 2) — the previous round's PNG. Read it; it shows what the designer just saw.

## What to do

1. Read the reference if one exists. Read the latest render if it exists. Read the current output SVG if it exists (refine mode, rounds ≥ 2).
2. Choose a viewBox: pick `0 0 N N` matching the icon's natural canvas (24, 32, 48, 64, 100…). Square unless the feature breakdown says otherwise.
3. Write or edit the SVG. Use primitives where they're cleaner than paths. Use `currentColor` on fills and strokes unless the prompt explicitly demands literal brand colors. Omit `width`/`height` attributes (let CSS scale).
4. Validate. Run `xmllint --noout <PATH>` to confirm well-formed XML. If `svgo` is on PATH, run `svgo --multipass <PATH>` — but check that it didn't strip `currentColor` or alter the viewBox; revert and skip svgo if it did.
5. Return a 1–3 sentence summary of what you changed and why. The orchestrator captures your output and passes it to the design expert.

## What NOT to do

- Do not add a `<?xml ?>` declaration.
- Do not add `xmlns:inkscape`, `xmlns:sodipodi`, or any editor metadata.
- Do not hard-code pixel `width`/`height` on the root `<svg>` element.
- Do not add comments explaining what the markup does. Only comments explaining a non-obvious *why* (e.g., a path that exists to mask another path).
- Do not refactor unrelated files.
- In refine mode, do not change the viewBox unless the feature breakdown explicitly calls for it; downstream consumers may rely on the canvas dimensions.
```

- [ ] **Step 2: Verify the frontmatter parses**

Run: `python3 -c "import yaml; d=yaml.safe_load(open('claude-skills/agents/svg-editor.md').read().split('---')[1]); assert d['name']=='svg-editor' and d['tools']=='Read, Edit, Write, Grep, Glob, Bash', d; print(d)"`
Expected: prints the dict; no AssertionError.

- [ ] **Step 3: Commit**

```bash
git add claude-skills/agents/svg-editor.md
git commit -m "add svg-editor subagent"
```

---

## Task 2: Create the `svg-design-expert` subagent

**Files:**
- Create: `claude-skills/agents/svg-design-expert.md`

- [ ] **Step 1: Write the agent file**

The file content contains nested triple-backticks (the verdict-block examples appear inside what would be markdown code fences in this prompt). Write it via `python3 open().write()` with a raw triple-quoted string, or via `cat <<'EOF'` heredoc, to avoid escaping issues. The end result must contain the literal triple-backticks shown below.

Required content (verbatim):

```markdown
---
name: svg-design-expert
description: Seasoned UI/UX designer specializing in iconography and brand marks. Use when comparing a rendered SVG to a reference image and producing both a structured feature breakdown (Silhouette, ViewBox/aspect, Primary primitives, Stroke vs fill, Symmetry, Distinctive details) and a verdict (APPROVED, NEEDS_WORK, or NEED_REFERENCE). Reviews from a rendered PNG and (optionally) a reference image; does NOT read source code.
tools: Read, WebSearch, WebFetch
---

# SVG design expert

You are a seasoned UI/UX designer who specializes in iconography and brand marks. You judge proportion, optical balance, stroke consistency, and recognizability. You critique rendered output, not source. You may use `WebSearch` / `WebFetch` to verify a reference detail when one is in dispute (e.g., "is the GitHub octocat tail straight or curled?"), but you do not edit files.

## Inputs you will receive

- **Goal** — the prompt the editor is trying to satisfy.
- **Round number** — 1..N.
- **Render path** — PNG of the current SVG, rendered at 256×256 on the chosen background.
- **Reference path** (optional) — local path to a reference image or SVG. Read it.
- **Prior feature breakdown** (if any) — your previous-round structured breakdown. Refine it; don't restart.

## Two outputs are required

### 1. Feature breakdown

Use exactly these sections (omit only if genuinely N/A for this icon):

- **Silhouette** — outer shape in plain words ("a circle with a wedge missing", "an apple with a leaf").
- **ViewBox / aspect** — what aspect the source canvas wants (square 1:1, 4:3, etc.).
- **Primary primitives** — the geometric building blocks ("one closed path", "two circles plus a rounded-corner rect", etc.).
- **Stroke vs fill** — filled silhouette / outlined stroke / mix.
- **Symmetry** — vertical / horizontal / radial / none.
- **Distinctive details** — the 1–3 things without which the icon stops being recognizable (the wedge for Pac-Man, the tail curl for the octocat, the bite for Apple).

### 2. Verdict block

The orchestrator scans the last 30 lines of your reply for a line matching one of these forms (line-by-line, ignoring leading whitespace, uppercase-sensitive):

```
---
VERDICT: APPROVED
```

```
---
VERDICT: NEEDS_WORK
  1. <actionable design item — design language, not code>
  2. <…>
```

```
---
VERDICT: NEED_REFERENCE
  Question to ask the user: <single specific question>
```

The triple-backtick fences shown above are illustration only — do NOT emit them in your actual output. Emit the block as plain text on its own lines, preceded by the literal `---` separator.

**Use `NEED_REFERENCE` only when** a critical detail (one that would change the icon's identity, not its polish) cannot be settled from the materials you have AND a brief WebSearch did not resolve it. Otherwise default to `NEEDS_WORK` (when the icon needs more work) or `APPROVED` (when it's genuinely good — not "close enough", not "fine for v1").

## Forbidden forms

- Wrapping the verdict block in a code fence.
- Omitting the `---` separator.
- Lowercase `verdict:`.
- Trailing prose after the verdict.
- Emitting more than one verdict block.
- `NEED_REFERENCE` without an explicit "Question to ask the user:" line.

## Hard rules

- You have `Read`, `WebSearch`, `WebFetch`. No `Edit`, `Write`, `Grep`, `Glob`, `Bash`. If you find yourself wanting source, you're outside your role.
- Critique in **design language** — "the wedge feels too narrow", not "decrease the second `L` command's x-coordinate".
- Numbered items in `NEEDS_WORK` must each be addressable. Vague aesthetic gestures are not allowed.
```

- [ ] **Step 2: Verify the frontmatter parses and the fence count is correct**

Run:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('claude-skills/agents/svg-design-expert.md').read().split('---')[1]); assert d['name']=='svg-design-expert' and d['tools']=='Read, WebSearch, WebFetch', d; print(d)"
grep -c '^```' claude-skills/agents/svg-design-expert.md
```
Expected: prints the dict with `name='svg-design-expert'` and `tools='Read, WebSearch, WebFetch'`. The grep count is `6` (open + close for each of the 3 illustration verdict blocks).

- [ ] **Step 3: Commit**

```bash
git add claude-skills/agents/svg-design-expert.md
git commit -m "add svg-design-expert subagent"
```

---

## Task 3: Create the `refine-svg` skill (orchestrator)

**Files:**
- Create: `claude-skills/skills/refine-svg/SKILL.md`
- Create directory: `claude-skills/skills/refine-svg/` (the `mkdir -p` is implicit in the Write)

- [ ] **Step 1: Write the skill file**

The file contains nested triple-backticks (verdict block examples). Write via `python3 open().write()` with a raw triple-quoted string, or via `cat <<'EOF'` heredoc.

Required content (verbatim):

```markdown
---
name: refine-svg
description: Refine or create a single SVG icon (UI iconography or brand mark) through a paired editor / design-expert review loop. Use when the user says "make me an SVG of X", "polish this icon", "recreate this logo", or invokes `/refine-svg <path-or-prompt>`. Spawns an `svg-editor` subagent and an `svg-design-expert` subagent for up to 5 rounds of edit → render → critique, ending when the designer says APPROVED or 5 rounds elapse. Includes upfront reference discovery via WebSearch/WebFetch and a NEED_REFERENCE mid-loop escape hatch.
---

# refine-svg

Paired editor/critic loop for creating or polishing a single SVG (UI iconography or brand mark).

## How to invoke

`/refine-svg <path-or-prompt> [--ref=<local-path-or-URL>] [--out=<path>] [--bg=<color>]`

Examples:
- `/refine-svg src/lib/icons/cog.svg "settings cog"` — refine an existing icon
- `/refine-svg "github octocat" --ref=https://github.githubassets.com/images/modules/logos_page/Octocat.png` — create with explicit reference
- `/refine-svg "coffee cup with steam"` — create; orchestrator finds reference
- `/refine-svg "apple logo" --out=icons/apple.svg --bg=transparent` — create; custom output path; transparent render background

## The recipe

You (main Claude) run this loop directly. Do NOT spawn another orchestrator agent.

### Step 1 — Parse and validate args

- Required: first positional arg.
- **Refine mode** — first arg ends in `.svg` AND the file exists. Output path = same path (in place).
- **Create with reference mode** — first arg is free-text AND `--ref=<...>` is present. Output = `--out=<path>` if given, else `./<slug>.svg` in cwd. Slug = lowercased prompt with non-alphanumerics collapsed to `-` (e.g., "GitHub Octocat" → `github-octocat`).
- **Create from prompt mode** — first arg is free-text, no `--ref=`. Same output rules. Reference will be discovered in Step 3.

If the first arg ends in `.svg` but the file doesn't exist, abort with: "Usage: /refine-svg <path-or-prompt> [--ref=<...>] [--out=<...>] [--bg=<...>]. The path you supplied doesn't exist; try `glob '**/*.svg'` to find candidates."

If the first arg is missing, abort with the same usage line.

### Step 2 — Rasterizer check (no source-only fallback)

Probe `rsvg-convert --version` via Bash. If exit code is non-zero, probe `convert --version` (ImageMagick).

If both fail, halt with: "No SVG rasterizer found. Install librsvg (`brew install librsvg`) or ImageMagick (`brew install imagemagick`) and re-run."

Remember which tool you found for the rest of the loop.

### Step 3 — Reference discovery (create modes only; skip in refine mode)

If `--ref=<...>` was supplied:
- URL → use `WebFetch` to download to `$TMPDIR/refine-svg-<slug>-ref.<ext>` (extension inferred from URL path or Content-Type).
- Local path → use directly. Verify the file exists; if not, halt with the path and the message "—ref path doesn't exist".

If `--ref=` was NOT supplied:
1. Run `WebSearch` for `<prompt> SVG icon`. Capture the top 5 results.
2. Run `WebSearch` for `<prompt> logo svg`. Capture the top 5.
3. Dedupe by host. Rank by host authority: official project repos > brand-resources pages > simpleicons.org / heroicons.com / lucide.dev > general image hosts.
4. Pick the top-ranked candidate. `WebFetch` its content. Save to `$TMPDIR/refine-svg-<slug>-ref.<ext>` (extension matching the actual content type).
5. Surface to the user: `"Found candidate reference: <url>. Use it / try another / paste your own / skip?"`. Wait for reply.
6. If user says "try another", advance to the next ranked candidate and repeat surface-to-user.
7. If user says "paste your own", prompt them for a URL or path; treat their reply as if it were `--ref=`.
8. If user says "skip", or if no candidates were findable, set `<reference path>` to "(none)" and proceed text-only. The expert's `Distinctive details` section then reflects iconographic conventions instead of reference fidelity.

### Step 4 — Capture START_SHA

Run `git rev-parse HEAD`. If the command fails (not in a git repo), skip silently — Step 5(a-bis) and Step 6's diff line will both be no-ops.

### Step 5 — Round loop, max 5

For `n` in 1..5:

**(a) Spawn the editor.** Use the Agent tool with `subagent_type=svg-editor`. Pass a self-contained prompt:

```
Edit/create the SVG at <ABSOLUTE_OUTPUT_PATH>. Goal: <PROMPT>. Round <n> of 5.

<If reference exists:>
Reference: <ABSOLUTE_REF_PATH>.
</If>

<If n >= 2:>
Feature breakdown from the design expert:
<PASTE THE FULL FEATURE BREAKDOWN HERE>

Previous expert critique:
<PASTE THE FULL VERDICT BLOCK + ITEMS HERE>
Address every numbered item.

Latest render: <PREVIOUS_RENDER_PATH>.
</If>

Output a short summary of changes.
```

**(a-bis) Detect editor no-op.** If `START_SHA` was captured, run `git diff --name-only $START_SHA HEAD`. If the editor's summary indicates no changes were made AND `git diff` shows no new modifications since the previous round, jump out of the loop and proceed to Step 6 with the current verdict (or NEEDS_WORK if none yet). Skip this check if not in a git repo.

**(b) Render.** If you found `rsvg-convert` in Step 2:
```bash
rsvg-convert -w 256 -h 256 -b <BG> -o $TMPDIR/refine-svg-<slug>-r<n>.png <output_path>
```
Otherwise (ImageMagick fallback):
```bash
convert -background <BG> -resize 256x256 <output_path> $TMPDIR/refine-svg-<slug>-r<n>.png
```
`<BG>` = `--bg=` value if provided, else `white`. Halt with the rasterizer's stderr on non-zero exit, prefixed with `Render failed at round <n>:`.

**(c) Spawn the designer.** Use the Agent tool with `subagent_type=svg-design-expert`. Pass:

```
Compare the rendered SVG to the reference. Goal: <PROMPT>. Round <n> of 5.

Render: $TMPDIR/refine-svg-<slug>-r<n>.png.
<If reference exists:>
Reference: <ABSOLUTE_REF_PATH>.
</If>
<If prior feature breakdown exists:>
Prior feature breakdown:
<PASTE>
</If>

Produce an updated feature breakdown and a single verdict block.
```

**(d) Parse the verdict.** Iterate the last 30 lines of the designer's reply line-by-line, looking for `VERDICT:` followed by `APPROVED`, `NEEDS_WORK`, or `NEED_REFERENCE` (uppercase, ignore leading whitespace).

- If `APPROVED`: break the loop.
- If `NEEDS_WORK`: capture every numbered item that follows (until end of output or next blank double-line) as the critique for round `n+1`.
- If `NEED_REFERENCE`: extract the line starting `Question to ask the user:` (after stripping that prefix). Print the question to the user verbatim. Wait for their reply. Re-spawn the editor for the SAME round, appending `\n\nDesigner's clarifying question: <Q>. User's answer: <A>.` to the editor's prompt. Re-render. Re-spawn the designer. The round counter does NOT advance during a NEED_REFERENCE round-trip. Cap at 2 NEED_REFERENCE retries per round; on the third in the same round, treat it as `NEEDS_WORK` with the full reply as the critique and advance.
- If no verdict block is found anywhere in the last 30 lines, treat the entire reply as the critique and continue as `NEEDS_WORK`.

### Step 6 — Surface the result

Print to the user:
- Rounds run.
- Final verdict (APPROVED, or NEEDS_WORK with the final designer's items).
- Output path of the SVG.
- All render paths (`$TMPDIR/refine-svg-<slug>-r*.png`) so the user can scrub the iteration history.
- Final feature breakdown.
- If `START_SHA` was captured, the output of `git diff --name-only $START_SHA HEAD`.

## Failure modes

| Condition | Action |
|---|---|
| Bad args / missing first arg | Abort with usage. |
| First arg ends in `.svg` but file missing | Abort with usage + `glob '**/*.svg'` hint. |
| `--ref=<path>` doesn't exist | Halt with the path and message. |
| No rasterizer (rsvg-convert AND convert) | Halt with install hint at Step 2. |
| WebSearch returns nothing usable AND user gave no `--ref=` | Surface "no candidates"; ask user to paste a URL or proceed text-only. |
| User picks "skip" on every candidate | Proceed text-only. |
| Editor produces malformed XML (xmllint fails) | Editor must rerun and fix; if it can't, halt with the xmllint error and the line number. |
| svgo strips `currentColor` or alters viewBox | Editor reverts that pass; treat as a soft failure, not a halt. |
| Render fails any round | Halt with round number + rasterizer's stderr. |
| Verdict block missing | Treat as NEEDS_WORK with full reply as critique. |
| `NEED_REFERENCE` without "Question to ask the user:" line | Treat as NEEDS_WORK with full reply as critique. |
| `NEED_REFERENCE` issued > 2 times in same round | Treat the third as NEEDS_WORK; advance the round. |
| Editor returns a no-op (5(a-bis)) | Jump to Step 6 with current verdict. |
| Subagent times out | Halt; surface which subagent and round number. |
| Max 5 rounds, no APPROVED | Surface critique + final feature breakdown; do not claim success. |
```

- [ ] **Step 2: Verify the frontmatter parses and the fence count is correct**

Run:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('claude-skills/skills/refine-svg/SKILL.md').read().split('---')[1]); assert d['name']=='refine-svg', d; print(d)"
grep -c '^```' claude-skills/skills/refine-svg/SKILL.md
```
Expected: prints the dict with `name='refine-svg'`. The grep count is `8` (4 fenced blocks × open + close: editor-spawn prompt template, designer-spawn prompt template, rsvg-convert command, convert command).

- [ ] **Step 3: Commit**

```bash
git add claude-skills/skills/refine-svg/SKILL.md
git commit -m "add refine-svg skill (orchestrator)"
```

---

## Task 4: Install symlinks

**Files:**
- Create symlink: `~/.claude/agents/svg-editor.md` → repo
- Create symlink: `~/.claude/agents/svg-design-expert.md` → repo
- Create symlink: `~/.claude/skills/refine-svg` → repo dir

The README's symlink-restore loops already cover both `claude-skills/agents/*.md` and `claude-skills/skills/*/`, so no README changes are needed.

- [ ] **Step 1: Ensure `~/.claude/agents/` exists**

Run: `mkdir -p ~/.claude/agents`
Expected: no output.

- [ ] **Step 2: Create the symlinks**

Run:
```bash
ln -s "$PWD/claude-skills/agents/svg-editor.md" ~/.claude/agents/svg-editor.md
ln -s "$PWD/claude-skills/agents/svg-design-expert.md" ~/.claude/agents/svg-design-expert.md
ln -s "$PWD/claude-skills/skills/refine-svg" ~/.claude/skills/refine-svg
```

- [ ] **Step 3: Verify each symlink resolves**

Run:
```bash
test -f ~/.claude/agents/svg-editor.md && \
test -f ~/.claude/agents/svg-design-expert.md && \
test -f ~/.claude/skills/refine-svg/SKILL.md && \
echo "OK"
```
Expected: `OK`.

- [ ] **Step 4: No commit needed**

The symlinks live in `~/.claude/`, outside the repo. The README's restore loops already cover them.

---

## Task 5: Build the test fixture

**Files:**
- Create: `claude-skills/skills/refine-svg/fixtures/ugly-octocat.svg`

- [ ] **Step 1: Write a deliberately rough fixture**

```svg
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="40" fill="#000"/>
  <circle cx="38" cy="45" r="5" fill="#fff"/>
  <circle cx="62" cy="45" r="5" fill="#fff"/>
  <rect x="40" y="60" width="20" height="8" fill="#fff"/>
</svg>
```

This is a minimal, deliberately wrong attempt at a "github octocat": a black blob with two white dots and a bar mouth — none of the recognizable details (cat ears, tentacles, tail). It gives the design expert real things to critique on round 1.

- [ ] **Step 2: Verify it renders**

Run:
```bash
mkdir -p /tmp/refine-svg-test
rsvg-convert -w 256 -h 256 -b white -o /tmp/refine-svg-test/ugly-octocat.png claude-skills/skills/refine-svg/fixtures/ugly-octocat.svg
file /tmp/refine-svg-test/ugly-octocat.png
```
Expected: `/tmp/refine-svg-test/ugly-octocat.png: PNG image data, 256 x 256, 8-bit/color RGBA, non-interlaced` (or similar PNG header).

If `rsvg-convert` is missing, install via `brew install librsvg` first. (This task validates that the rasterizer the orchestrator depends on is available on the implementer's machine.)

- [ ] **Step 3: Commit**

```bash
git add claude-skills/skills/refine-svg/fixtures/ugly-octocat.svg
git commit -m "add ugly-octocat.svg fixture for refine-svg tests"
```

---

## Task 6: Integration test — refine an existing rough SVG

This task is a manual smoke test. It exercises the full loop end-to-end inside a Claude Code session.

**Pre-conditions:**
- Tasks 1–5 complete and committed.
- `rsvg-convert` on PATH (`brew install librsvg`).
- Claude Code session has been **fully restarted** (quit and relaunched) since Task 4 completed, so the new agents are registered as `subagent_type` values.
- Network access for `WebSearch` / `WebFetch`.

- [ ] **Step 1: Choose a canonical octocat URL**

Open `https://github.githubassets.com/images/modules/logos_page/Octocat.png` (or similar canonical octocat asset) in a browser to confirm it loads. Copy the URL.

- [ ] **Step 2: Stage the fixture into a writable scratch path**

```bash
cp claude-skills/skills/refine-svg/fixtures/ugly-octocat.svg /tmp/refine-svg-test/test-octocat.svg
```

- [ ] **Step 3: From inside Claude Code, run**

`/refine-svg /tmp/refine-svg-test/test-octocat.svg "github octocat" --ref=<URL FROM STEP 1>`

- [ ] **Step 4: Verify the loop fires correctly**

Expected behavior:
- Step 2 of the recipe finds `rsvg-convert`, prints which it picked.
- Step 3 (reference discovery) skips the WebSearch path because `--ref=` was supplied; downloads the URL into `$TMPDIR/refine-svg-test-octocat-ref.png`.
- Round 1: editor agent spawns (`subagent_type=svg-editor`), edits the file (you'll see Edit/Write tool calls in the transcript), summarizes. Render lands at `$TMPDIR/refine-svg-test-octocat-r1.png`. Designer agent spawns (`subagent_type=svg-design-expert`), produces a feature breakdown plus a verdict.
- If NEEDS_WORK, the loop continues round 2 with the previous breakdown + critique passed in.
- Final summary lists modified files (`git diff --name-only`), screenshot paths, final feature breakdown.

- [ ] **Step 5: Open the renders and verify visual progression**

```bash
open /tmp/refine-svg-test/test-octocat.svg $TMPDIR/refine-svg-test-octocat-r*.png
```
Expected: each round looks meaningfully closer to the reference than the previous round (otherwise the editor's prompt or the expert's prompt needs iteration).

- [ ] **Step 6: No commit**

Test result is observational; nothing to commit unless prompts need fixing.

---

## Task 7: Integration test — create from prompt with no reference

**Pre-conditions:** same as Task 6.

- [ ] **Step 1: Run the orchestrator with no `--ref=`**

`/refine-svg "settings cog" --out=/tmp/refine-svg-test/cog.svg`

- [ ] **Step 2: Verify reference-discovery flow**

Expected behavior:
- Orchestrator runs `WebSearch` for `"settings cog SVG icon"` and `"settings cog logo svg"`.
- Surfaces a candidate reference URL to you with the choice "Use it / try another / paste your own / skip?".
- You answer "Use it" — orchestrator downloads the reference to `$TMPDIR/refine-svg-cog-ref.<ext>`.
- Loop runs as in Task 6.

- [ ] **Step 3: Verify text-only fallback**

Re-run with `skip`:

`/refine-svg "settings cog" --out=/tmp/refine-svg-test/cog2.svg`

When prompted with the candidate URL, answer "skip". Confirm:
- Orchestrator proceeds without a reference.
- Designer's feature breakdown reflects iconographic conventions ("a settings cog has 6–8 teeth and a center hole") rather than fidelity to a specific image.
- Loop runs to APPROVED or 5 rounds.

- [ ] **Step 4: No commit**

Observational test.

---

## Task 8: Integration test — NEED_REFERENCE round-trip

**Pre-conditions:** same as Task 6.

- [ ] **Step 1: Run with no reference and skip all candidates**

`/refine-svg "github octocat" --out=/tmp/refine-svg-test/octocat-skipped.svg`

When the orchestrator surfaces candidate references, answer "skip" for each one until proceeding text-only.

- [ ] **Step 2: Verify NEED_REFERENCE escape hatch fires**

Expected behavior within rounds 1–2:
- Designer issues `VERDICT: NEED_REFERENCE` with `Question to ask the user: <single specific question>` (e.g., "Should the GitHub octocat's tail be straight or curled?").
- Orchestrator prints the question verbatim.
- You answer with a short, definite reply (e.g., "curled tentacle on the bottom right").
- Orchestrator re-spawns the editor for the SAME round (no round counter advance), appending `Designer's clarifying question: ... User's answer: ...` to the editor's prompt.
- Re-render → re-spawn designer.
- Loop continues normally from there.

- [ ] **Step 3: Verify the 2-retry cap**

If the designer issues `NEED_REFERENCE` 3 times in the same round, confirm the orchestrator treats the third as `NEEDS_WORK` and advances the round.

- [ ] **Step 4: No commit**

Observational test.

---

## Task 9: Integration test — no-rasterizer halt

**Pre-conditions:** same as Task 6.

- [ ] **Step 1: Hide the rasterizers from PATH**

```bash
mkdir -p /tmp/empty-path
PATH=/tmp/empty-path which rsvg-convert convert || echo "both hidden"
```
Expected: `both hidden`.

- [ ] **Step 2: Run the orchestrator with PATH stripped**

In a Claude Code session, set the environment so the orchestrator can't see the rasterizers. The cleanest way is to launch Claude Code from a shell where `PATH=/tmp/empty-path:/usr/bin /Applications/Claude\ Code.app/...` (or equivalent for your install). Or temporarily move the binaries:
```bash
sudo mv $(which rsvg-convert) /tmp/rsvg-convert.bak
sudo mv $(which convert) /tmp/convert.bak
```

Then run:

`/refine-svg "any prompt" --out=/tmp/refine-svg-test/halt-test.svg`

- [ ] **Step 3: Verify the halt message**

Expected: a single clear message: `"No SVG rasterizer found. Install librsvg (\`brew install librsvg\`) or ImageMagick (\`brew install imagemagick\`) and re-run."`. No editor or designer agent should be spawned. No render files should be created in `$TMPDIR`.

- [ ] **Step 4: Restore the binaries**

```bash
sudo mv /tmp/rsvg-convert.bak $(brew --prefix librsvg)/bin/rsvg-convert
sudo mv /tmp/convert.bak $(brew --prefix imagemagick)/bin/convert
```

- [ ] **Step 5: No commit**

Observational test.

---

## Self-review checklist

- Spec §3.2 components table → Tasks 1, 2, 3 create each of them. ✓
- Spec §3.3 orchestrator loop steps 1–6 → covered in Task 3 SKILL.md "The recipe" section steps 1–6 (with 5(a-bis) editor no-op detection). ✓
- Spec §3.4 render pipeline (rsvg primary, ImageMagick fallback, halt if neither) → Task 3 step 2 + step 5(b) both branches. ✓
- Spec §4.1 editor prompt → matches Task 1 agent body verbatim. ✓
- Spec §4.2 designer prompt (incl. 3 verdict forms + forbidden list) → matches Task 2 agent body verbatim. ✓
- Spec §5 reference discovery + NEED_REFERENCE escape hatch → orchestrator Step 3 (upfront) + Step 5(d) (mid-loop). ✓
- Spec §6 error table — every row referenced in Task 3's failure-modes table. ✓
- Spec §7 testing scenarios (1 refine, 2 create-no-ref, 3 NEED_REFERENCE, 4 no-rasterizer halt, 5 lean-output verification) → Tasks 6–9 (lean-output verification is folded into Task 6 step 5; if you want it separated, split it out). ✓
- Spec §9 non-goals → no source-only mode anywhere; one SVG per invocation; no automatic install. ✓
- Type / name consistency: `svg-editor`, `svg-design-expert`, `refine-svg` used identically across all tasks. ✓
- All `tools:` declarations consistent across plan and spec. ✓
- No "TBD"/"TODO"/"similar to Task N" placeholders. The verbose spec content is repeated verbatim in Tasks 1, 2, 3 instead of referenced — engineers may execute tasks out of order. ✓

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

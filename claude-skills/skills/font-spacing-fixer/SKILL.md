---
name: font-spacing-fixer
description: Use when the user complains that letter-spacing or kerning in an OTF/TTF "looks wrong", "too loose", "didn't change after the new version", or asks to audit/repair the kern table of a font. Triggers - "the gap between r and e is too big", "kerning isn't being applied", "the new font version looks the same as the old one", "fix the spacing in this font", "audit the kerning", "AV looks loose", "why isn't `font-kerning: normal` doing anything for this font", "rebuild the GPOS", "patch the OTF". Covers diagnosing why a browser/app is silently dropping kerning, inspecting and repairing GPOS PairPos lookups via fontTools, building a side-by-side comparison harness, and producing a deliverable for the type designer to fix in their source file. Does NOT cover designing new glyphs, hinting, variable-font axes, or web-font subsetting/format conversion (woff2 etc.) unless those touch the kern table.
---

# Diagnosing and repairing OTF/TTF letter-spacing problems

The user typically arrives saying "the kerning looks wrong" or "the new version doesn't look any different". **Do not jump to "the pair needs to be tightened more."** A loose-looking pair almost always has one of three root causes; you need to find out which one before suggesting a fix. The wrong diagnosis wastes hours.

## The three failure modes, in order of likelihood

1. **Kerning is present in the font but never applied by the shaper.** The GPOS table contains the pair, but the lookup is structurally invalid or has flags that tell the shaper to skip it. The font measures as if it has no kerning at all. *This is what you'll find most of the time. It's almost never "the type designer forgot the pair."*
2. **The CSS / rendering layer disables kerning.** `font-kerning: none`, `font-feature-settings: "kern" 0`, a `font-variant-numeric: tabular-nums` rule, or a parent reset is suppressing what the font would otherwise apply.
3. **The kern pair is genuinely missing or set too loose in the source file.** Real, but uncommon — and only confirmable after ruling out (1) and (2).

The diagnostic flow is built around proving which of these you have.

## The non-negotiable first step: measure

Never trust eyeballs alone for kerning. Always do the measurement, *especially* before claiming a font "didn't change" between versions. Two strings can look subjectively identical and differ by 6 px, and the reverse — a designer can ship a major release whose only practical change is tabular numerals, which look dramatic on digits and invisible everywhere else.

The cheapest measurement is in a real browser:

```js
const measure = (text, family, kerningOn) => {
  const el = document.createElement('span');
  el.style.cssText =
    `position:absolute;visibility:hidden;white-space:pre;` +
    `font-family:'${family}',sans-serif;font-size:64px;line-height:1;` +
    (kerningOn
      ? `font-kerning:normal;font-feature-settings:"kern" 1;`
      : `font-kerning:none;font-feature-settings:"kern" 0;`);
  el.textContent = text;
  document.body.appendChild(el);
  const w = el.getBoundingClientRect().width;
  document.body.removeChild(el);
  return +w.toFixed(2);
};
```

Toggle kerning on/off across a battery of strings (`re`, `er`, `AV`, `To`, `Wa`, `Ya`, `Here 4`, `CubePilot`, a pangram). **If the delta is zero for every pair, the shaper is not applying kerning at all** — go straight to mode (1) or (2). If a few pairs move but the obvious ones (`AV`, `To`, `LT`) don't, the font has a *partial* kern table — usually mode (1) with a secondary lookup that escapes the bug.

Then dump the hmtx advances and the GPOS pair values and compare them to your measured deltas:

```python
from fontTools.ttLib import TTFont
f = TTFont('font.otf')
upem = f['head'].unitsPerEm
# expected kern in pixels at size S: value * S / upem
```

If `kern(r,e) = -191 units` exists in the font and at 64 px the rendered `re` width equals `r.advance + e.advance` (i.e. *zero* kerning), you have proof of mode (1). That proof is what you need before touching anything.

## Inspecting GPOS for the LookupFlag bug

This is the single most common form of mode (1). The kerning *exists* in the font but is gated behind a LookupFlag that tells the shaper to skip every base glyph — i.e., every lowercase Latin letter.

```python
from fontTools.ttLib import TTFont
f = TTFont('font.otf')
gpos = f.get('GPOS')
for i, lk in enumerate(gpos.table.LookupList.Lookup):
    if lk.LookupType != 2:  # PairPos
        continue
    print(f"Lookup #{i}: flag={lk.LookupFlag:#04x} ({lk.LookupFlag}) "
          f"subtables={len(lk.SubTable)}")
    for j, st in enumerate(lk.SubTable):
        if st.Format == 1:
            pairs = sum(len(ps.PairValueRecord) for ps in st.PairSet)
            print(f"  st#{j}: Format 1, {len(st.Coverage.glyphs)} first-glyphs, {pairs} pairs")
        elif st.Format == 2:
            print(f"  st#{j}: Format 2, "
                  f"{len(st.Class1Record)}×{len(st.Class1Record[0].Class2Record)} classes")
```

**LookupFlag decoded** (the bits that swallow pairs):
- `0x02` IgnoreBaseGlyphs — *skips every base glyph*. Lowercase Latin letters, digits, most punctuation are base glyphs. If you see this bit set on a kern lookup, that lookup contributes ~nothing to text rendering.
- `0x04` IgnoreLigatures — skips ligatures (`ff`, `fi`, `fl`, etc.).
- `0x08` IgnoreMarks — fine for kern.
- `0x01` RightToLeft — irrelevant for kern.
- `0xFF00` MarkAttachmentType — irrelevant for kern.

**A correctly-exported kern lookup has `LookupFlag = 0`.** Anything else on a `kern` feature lookup is suspicious. `LookupFlag = 6` (the case I've actually seen ship in a public font) means the whole lookup is dead for Latin text.

The fix is a one-byte edit: `lookup.LookupFlag = 0`. fontTools will write the corrected font back unchanged in size and identical in glyphs.

## Inspecting GPOS for Coverage-not-sorted

A secondary cause: OpenType spec requires Coverage glyph lists to be in glyph-ID order. fontTools logs a warning when it sees an unsorted Coverage; strict sanitizers (Chrome's OTS historically) sometimes drop offending lookups. Less common than the LookupFlag bug, but worth fixing while you're in there.

`fontTools` does *not* normalize Coverage on save by default — you must rebuild it explicitly:

```python
glyph_order = f.getGlyphOrder()
gid = {g: i for i, g in enumerate(glyph_order)}
for lk in gpos.table.LookupList.Lookup:
    if lk.LookupType != 2: continue
    for st in lk.SubTable:
        if st.Format == 1:
            paired = sorted(zip(st.Coverage.glyphs, st.PairSet),
                            key=lambda p: gid[p[0]])
            st.Coverage.glyphs = [p[0] for p in paired]
            st.PairSet         = [p[1] for p in paired]
            for ps in st.PairSet:
                ps.PairValueRecord.sort(key=lambda r: gid[r.SecondGlyph])
        elif st.Format == 2:
            st.Coverage.glyphs = sorted(st.Coverage.glyphs, key=lambda g: gid[g])
```

## The complete repair recipe

```python
"""Repair OTF/TTF kerning: clear bogus LookupFlag, sort Coverage."""
from fontTools.ttLib import TTFont

def repair(src: str, dst: str) -> dict:
    f = TTFont(src)
    gid = {g: i for i, g in enumerate(f.getGlyphOrder())}
    cleared, resorted = 0, 0
    gpos = f.get('GPOS')
    if gpos is not None:
        for lk in gpos.table.LookupList.Lookup:
            if lk.LookupType != 2:
                continue
            if lk.LookupFlag != 0:
                lk.LookupFlag = 0
                cleared += 1
            for st in lk.SubTable:
                if st.Format == 1:
                    paired = sorted(zip(st.Coverage.glyphs, st.PairSet),
                                    key=lambda p: gid.get(p[0], 1 << 30))
                    new_cov = [p[0] for p in paired]
                    if new_cov != st.Coverage.glyphs:
                        st.Coverage.glyphs = new_cov
                        st.PairSet = [p[1] for p in paired]
                        resorted += 1
                    for ps in st.PairSet:
                        ps.PairValueRecord.sort(
                            key=lambda r: gid.get(r.SecondGlyph, 1 << 30))
                elif st.Format == 2:
                    new_cov = sorted(st.Coverage.glyphs,
                                     key=lambda g: gid.get(g, 1 << 30))
                    if new_cov != st.Coverage.glyphs:
                        st.Coverage.glyphs = new_cov
                        resorted += 1
    f.save(dst)
    return {'src': src, 'dst': dst,
            'lookups_with_flag_cleared': cleared,
            'subtables_resorted': resorted}
```

Run it, then re-measure in the browser harness. **A successful repair shows the rendered pair widths drop by exactly the value in GPOS** (e.g. `re` shrinks by 191 × size / upem px). That equality is your green test.

## The browser comparison harness

Drop both fonts (old + new, or broken + fixed) next to an `index.html` and serve over HTTP — `file://` works for HTML but Chrome's font CORS is finicky:

```bash
cd /tmp/font-compare
python3 -m http.server 9876
```

The harness should:
1. Declare four `@font-face` families (old, new, old-fix, new-fix) so you can compare every combination.
2. Render each test string in matched cells under `font-kerning: normal; font-feature-settings: "kern" 1;` (explicit, not relying on UA defaults).
3. Block evaluation until `document.fonts.ready` resolves — otherwise measurements race the fallback font.
4. Have an **overlay row** where both fonts render anchored to the same left edge; the right-edge gap visualises the kerning delta with zero math.
5. Optionally a **strobe row** that toggles `font-family` every ~600 ms — the eye catches the shrink/grow motion even when the static comparison reads as identical.

A `font-kerning: auto` default cell is *not* the same as `font-kerning: normal` — `auto` lets the UA decide, and a few engines disable kern in small sizes or for whitespace-pre contexts. Always set explicitly when measuring.

## What to do after the fix lands

The patched OTF is a stopgap. **The canonical fix is in the type designer's source file** (`.glyphs`, `.ufo`, `.vfb`). Every time the designer exports a new version from the same source, the LookupFlag bug returns. Hand them:

- **The diagnosis in one sentence.** "GPOS lookup #0 ships with LookupFlag=6 (IgnoreBaseGlyphs | IgnoreLigatures). It should be 0. Every lowercase pair in this lookup is being skipped."
- **A reproducible measurement** (a single number — the width of `re` in pixels at a known font-size — with kerning on vs off, showing the delta is zero when it should be ~6 px).
- **The `repair.py` script** so they can verify their next export against the same check before shipping.

Do not silently overwrite the font asset in a sibling repo without asking. Modifying `cubepilot_ui/fonts/CubePilot-Regular.otf` (or any installed asset in `~/Library/Fonts/`) is a cross-project change — confirm before touching.

## Anti-patterns to refuse

- **"Just tighten the pair more"** before proving the existing kern value is being applied. If the lookup is gated by `LookupFlag=6` you can set the value to `-9999` and nothing will change.
- **"The new version didn't fix the kerning regression"** without measuring. Designers often ship UI-spacing releases that change *which pairs are kerned*, not *all* of them. The eye can miss a 1.25 px tightening on `He` while accurately noticing that `re` is unchanged.
- **Patching the OTF without producing the bug report for the designer.** The fix needs to live in their source or it regresses on next export.
- **Trusting the `font-kerning: auto` default** when measuring. Always set `font-kerning: normal; font-feature-settings: "kern" 1` explicitly on the measurement element.
- **Confusing tabular figures with kerning changes.** If `Here 4` looks narrower in v2 but `re` is unchanged, the change is almost certainly tabular-figure work on the digits, not a kerning pass.

## Tooling checklist

- `fontTools` (`pip install fonttools`). The `ttx` CLI for human-readable dumps, the `fontTools.ttLib.TTFont` Python API for programmatic edits.
- A real browser via the Chrome DevTools MCP, Playwright MCP, or just `open` to the user's default browser, for visual confirmation and screenshotting.
- A simple Python `http.server` (Chrome won't load `file://` fonts for cross-origin reasons in some contexts; serving over loopback sidesteps the issue).
- Optional: [Wakamai Fondue](https://wakamaifondue.com) for a no-install glance at a font's features and pair count.

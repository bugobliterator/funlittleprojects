// pr-review-board — board shell.
// Renders the review manifest: theme → AREA section (Server / Web / Other) → per-file
// diffs, each file's name + VS Code link + note sitting directly on top of its own
// diff2html diff. Files from every commit in a theme are merged into their area, so a
// test lands in the same section as the code it exercises.
// No framework, no build step: a plain ES module.

let MANIFEST = null;

function el(doc, tag, cls, text) {
  const node = doc.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}
const short = (sha) => (sha || '').slice(0, 8);
const isDoc = (p) => p.startsWith('docs/') || p.endsWith('.md');

// ---- test ⇄ code pairing (logical identity) ----
// A test file and the code it exercises share a logicalKey (the code file's path),
// so we can nest the test's diff directly under the code file even when they live in
// different subsections (commits). A code file's key is itself.
//   TypeScript:  <dir>/X.spec.ts        → <dir>/X.ts   (covers X.component.spec.ts)
//   Java test:   src/test/**/FooTest.java        → src/main/**/Foo.java
//   Java IT:     src/integrationTest/**/FooIT.java→ src/main/**/Foo.java
const JAVA_TEST_DIR = /\/src\/(?:test|integrationTest)\//;

export function isTestPath(p) {
  if (typeof p !== 'string') return false;
  if (p.endsWith('.spec.ts')) return true;
  if (p.endsWith('.java') && JAVA_TEST_DIR.test(p)) {
    const name = p.slice(p.lastIndexOf('/') + 1);
    return /Test\.java$/.test(name) || /IT\.java$/.test(name);
  }
  return false;
}

export function logicalKey(p) {
  if (typeof p !== 'string') return p;
  if (p.endsWith('.spec.ts')) return p.slice(0, -'.spec.ts'.length) + '.ts';
  if (p.endsWith('.java') && JAVA_TEST_DIR.test(p)) {
    const name = p.slice(p.lastIndexOf('/') + 1);
    if (/Test\.java$/.test(name) || /IT\.java$/.test(name)) {
      return p
        .replace(JAVA_TEST_DIR, '/src/main/')
        .replace(/(?:Test|IT)\.java$/, '.java');
    }
  }
  return p; // code file → itself
}

const ROOT_REQUIREMENT = 'VS Code links need an absolute repoRoot from /api/manifest';

// vscode://file/<abs-path>:<line> — abs path drops its leading slash per the scheme.
// null unless repoRoot is a real absolute path (the scheme does no ~ expansion).
export function vscodeLink(repoRoot, path, line) {
  if (typeof repoRoot !== 'string' || !repoRoot.startsWith('/')) return null;
  const abs = `${repoRoot.replace(/\/$/, '')}/${path}`.replace(/^\/+/, '');
  return `vscode://file/${abs}:${line}`;
}

// Split a raw unified diff into one text chunk per file (keyed by its b/ path).
function splitDiff(raw) {
  const parts = [];
  let cur = null;
  for (const line of (raw || '').split('\n')) {
    if (line.startsWith('diff --git ')) {
      if (cur) parts.push(cur);
      cur = { header: line, lines: [line] };
    } else if (cur) {
      cur.lines.push(line);
    }
  }
  if (cur) parts.push(cur);
  return parts.map((p) => {
    let path = null;
    for (const l of p.lines) {
      if (l.startsWith('+++ b/')) { path = l.slice(6); break; }
      if (l.startsWith('rename to ')) { path = l.slice(10); break; }
    }
    if (!path) { const m = p.header.match(/ b\/(.+)$/); path = m ? m[1] : p.header; }
    return { path, text: p.lines.join('\n') + '\n' };
  });
}

// Turn diff2html's line-number cells into VS Code deep-links for that file + line.
function linkLineNumbers(doc, root, repoRoot, path) {
  for (const cell of root.querySelectorAll('.line-num2')) {
    const line = cell.textContent.trim();
    if (!/^\d+$/.test(line)) continue;
    const href = vscodeLink(repoRoot, path, line);
    if (!href) continue;
    const a = el(doc, 'a', null, line);
    a.href = href;
    a.title = `open line ${line} in VS Code`;
    cell.replaceChildren(a);
  }
}

/**
 * Build ONE collapsible file card: a header bar (name · +adds/−dels · note · ⧉ VS Code)
 * directly on top of that file's diff, which renders lazily on first expand.
 * opts: { path, text, stat:{added,deleted}, note, repoRoot, nested }.
 * `nested` marks a test file nested under the code it exercises (a "tests" tag + indent).
 */
export function buildFileCard(doc, { path, text, stat, note, repoRoot, nested = false }) {
  const card = el(doc, 'div', nested ? 'filecard filecard-test' : 'filecard');

  // filebar is the collapse toggle (default collapsed → a scannable file list).
  const bar = el(doc, 'button', 'filebar');
  bar.type = 'button';
  bar.setAttribute('aria-expanded', 'false');
  bar.append(el(doc, 'span', 'fcaret', '▸'));
  if (nested) bar.append(el(doc, 'span', 'test-tag', 'tests'));
  bar.append(el(doc, 'span', 'fname', path));
  if (stat) {
    if (stat.added) bar.append(el(doc, 'span', 'stat-add', `+${stat.added}`));
    if (stat.deleted) bar.append(el(doc, 'span', 'stat-del', `−${stat.deleted}`));
  }
  // The tag already says "tests"; skip a redundant note that repeats it.
  if (note && !(nested && note.toLowerCase() === 'tests')) bar.append(el(doc, 'span', 'fnote', note));
  const href = vscodeLink(repoRoot, path, 1);
  if (href) {
    const a = el(doc, 'a', 'vscode-link', '⧉ VS Code');
    a.href = href;
    a.addEventListener('click', (e) => e.stopPropagation()); // link, not toggle
    bar.append(a);
  } else if (repoRoot != null) {
    bar.append(el(doc, 'span', 'note no-link', ROOT_REQUIREMENT));
  }

  // Per-file description: a calm prose line under the header, ALWAYS visible (even when
  // the diff is collapsed). Sourced from MANIFEST.descriptions[path]; rendered only when
  // a description exists for this path — no empty block otherwise.
  const descText = MANIFEST?.descriptions?.[path];
  const desc = descText ? el(doc, 'p', 'fdesc', descText) : null;

  const body = el(doc, 'div', 'd2h');
  body.hidden = true;
  bar.addEventListener('click', () => {
    const open = bar.getAttribute('aria-expanded') === 'true';
    bar.setAttribute('aria-expanded', String(!open));
    bar.firstChild.textContent = open ? '▸' : '▾';
    if (body.hidden && !body.dataset.rendered) {
      if (text) {
        // diff2html owns + escapes all diff markup; its own file header is hidden via CSS.
        body.innerHTML = Diff2Html.html(text, { drawFileList: false, outputFormat: 'line-by-line' });
        linkLineNumbers(doc, body, repoRoot, path);
      } else {
        body.append(el(doc, 'div', 'empty', 'diff unavailable'));
      }
      body.dataset.rendered = '1';
    }
    body.hidden = open;
  });

  if (desc) card.append(bar, desc, body);
  else card.append(bar, body);
  return card;
}

/**
 * Mount a raw unified diff into `mountEl`, ONE card per file: a header bar
 * (name · +adds/−dels · note · ⧉ VS Code) directly on top of that file's diff.
 * opts: { files:[{path,added,deleted}], repoRoot, fileNotes:{path:note} }.
 */
export function mountDiff(rawDiff, mountEl, opts = {}) {
  const doc = mountEl.ownerDocument;
  const { files = [], repoRoot, fileNotes = {} } = opts;
  const stat = Object.fromEntries(files.map((f) => [f.path, f]));
  mountEl.replaceChildren();

  let shown = 0;
  for (const { path, text } of splitDiff(rawDiff)) {
    if (isDoc(path)) continue; // docs excluded from the view
    shown++;
    mountEl.append(buildFileCard(doc, { path, text, stat: stat[path], note: fileNotes[path], repoRoot }));
  }
  if (!shown) mountEl.append(el(doc, 'div', 'empty', 'No code changes (docs-only).'));
  return mountEl;
}

// ---- per-theme area index (Server / Web), merging every commit's files ----

const THEME_IDX = new Map();

// Areas are the review unit now: a code file and its tests (feat + test + fix commits)
// live in ONE area section, not scattered across per-commit subsections.
const AREAS = [['server', 'Server'], ['web', 'Web']];
function areaOf(path, subTitle) {
  if (path.startsWith('ERPServer/')) return 'server';
  if (path.startsWith('ERPWeb/')) return 'web';
  if (/\(server\)/.test(subTitle || '')) return 'server'; // fallback: commit-title prefix
  if (/\(web\)/.test(subTitle || '')) return 'web';
  return 'web';
}

/**
 * Index a theme's files once, GROUPED BY AREA (Server/Web). Merges every commit's
 * files into its area, so code and its tests sit together. Within an area:
 *   - code files render first, each with 1:1-matching test files nested under it;
 *   - test files with no 1:1 code match (most Java behaviour/IT tests) render as
 *     regular cards after the code, in the same area — never a separate section.
 * Returns { primaryByArea:Map<area,{path,subId}[]>, nestedByCode:Map<codePath,{path,subId}[]>,
 *           areaSubs:Map<area,Set<subId>>, notesByPath:Map<path,note> }.
 */
export function themeIndex(theme) {
  let idx = THEME_IDX.get(theme.id);
  if (idx) return idx;

  const fileToSub = new Map(); // path → first subId that carries it (theme order)
  const subTitle = new Map();
  const notesByPath = new Map();
  for (const sub of theme.subsections || []) {
    subTitle.set(sub.id, sub.title || '');
    for (const [p, note] of Object.entries(sub.fileNotes || {}))
      if (!isDoc(p) && !fileToSub.has(p)) { fileToSub.set(p, sub.id); notesByPath.set(p, note); }
  }

  const groups = new Map(); // logicalKey → { code:path|null, tests:path[] }
  for (const p of fileToSub.keys()) {
    const key = logicalKey(p);
    let g = groups.get(key);
    if (!g) { g = { code: null, tests: [] }; groups.set(key, g); }
    if (isTestPath(p)) g.tests.push(p);
    else g.code = p;
  }

  const primaryByArea = new Map();
  const nestedByCode = new Map();
  const areaSubs = new Map();
  const push = (area, path, subId) => {
    if (!primaryByArea.has(area)) { primaryByArea.set(area, []); areaSubs.set(area, new Set()); }
    primaryByArea.get(area).push({ path, subId });
    areaSubs.get(area).add(subId);
  };

  // pass 1 — code files first, each with its 1:1-matching tests nested beneath
  for (const [p, subId] of fileToSub) {
    if (isTestPath(p)) continue;
    const area = areaOf(p, subTitle.get(subId));
    push(area, p, subId);
    const tests = (groups.get(p) || {}).tests || [];
    if (tests.length) {
      nestedByCode.set(p, tests.map((tp) => ({ path: tp, subId: fileToSub.get(tp) })));
      for (const tp of tests) areaSubs.get(area).add(fileToSub.get(tp));
    }
  }
  // pass 2 — tests with no 1:1 code match: regular cards in their own area (after code)
  for (const [p, subId] of fileToSub) {
    if (!isTestPath(p)) continue;
    const g = groups.get(logicalKey(p));
    if (g && g.code) continue; // nested under its code in pass 1
    push(areaOf(p, subTitle.get(subId)), p, subId);
  }

  // Total files per area = code files + their nested tests + unmatched tests.
  const countByArea = new Map();
  for (const [area, files] of primaryByArea) {
    let n = 0;
    for (const f of files) n += 1 + (nestedByCode.get(f.path)?.length || 0);
    countByArea.set(area, n);
  }

  idx = { fileToSub, groups, primaryByArea, nestedByCode, areaSubs, notesByPath, countByArea };
  THEME_IDX.set(theme.id, idx);
  return idx;
}

// ---- area section (Server / Web) ----

function areaCard(doc, theme, area, label, idx) {
  const card = el(doc, 'section', 'subsection');
  card.dataset.area = area;

  const head = el(doc, 'button', 'sub-head');
  head.type = 'button';
  head.setAttribute('data-diff-toggle', '');
  head.setAttribute('aria-expanded', 'false');
  head.dataset.theme = theme.id;
  head.dataset.area = area;
  const total = idx.countByArea.get(area) || 0;
  const shas = [...(idx.areaSubs.get(area) || [])].map(short).join(' ');
  head.append(
    el(doc, 'span', 'caret', '▸'),
    el(doc, 'span', 'sub-title', label),
    el(doc, 'span', 'sub-count', `${total} file${total === 1 ? '' : 's'}`),
    el(doc, 'span', 'sc', shas),
    el(doc, 'span', 'sub-status'),
  );

  const panel = el(doc, 'div', 'files');
  panel.hidden = true;

  card.append(head, panel);
  return card;
}

function themeCard(doc, theme) {
  const card = el(doc, 'article', 'theme-card');
  card.dataset.themeId = theme.id;

  const head = el(doc, 'header', 'theme-head');
  head.append(el(doc, 'h2', null, theme.title));
  if (theme.summary) head.append(el(doc, 'p', 'summary', theme.summary));
  if (theme.userImpact) {
    const box = el(doc, 'div', 'impact');
    const lbl = el(doc, 'div', 'lbl', 'What the operator gets');
    for (const role of theme.affectedRoles || []) lbl.append(el(doc, 'span', 'who-tag', role));
    box.append(lbl, el(doc, 'p', null, theme.userImpact));
    head.append(box);
  }
  card.append(head);

  // One section per area (Server / Web), each merging every commit's files for that
  // area. An area with no files is simply not rendered — no empty sections.
  const idx = themeIndex(theme);
  for (const [area, label] of AREAS) {
    if (!(idx.primaryByArea.get(area) || []).length) continue;
    card.append(areaCard(doc, theme, area, label, idx));
  }
  return card;
}

/** Render the manifest's themes into `mount`, replacing whatever was there. */
export function renderBoard(manifestJson, mount) {
  const doc = mount.ownerDocument;
  mount.replaceChildren();
  for (const theme of manifestJson.themes || []) mount.append(themeCard(doc, theme));
  return mount;
}

// ---- page wiring ----

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

function themeById(themeId) {
  return (MANIFEST?.themes || []).find((t) => t.id === themeId);
}

// One fetch per subsection diff, memoised: nested test cards pull chunks from a test
// subsection that a different code subsection also references, so we fetch each once.
const SUB_DIFF = new Map(); // `themeId::subId` → Promise<{ statByPath, textByPath }>
function loadSubDiff(themeId, subId) {
  const key = `${themeId}::${subId}`;
  let pr = SUB_DIFF.get(key);
  if (!pr) {
    pr = (async () => {
      const q = new URLSearchParams({ theme: themeId, sub: subId });
      const { raw, files } = await getJSON(`/api/diff?${q}`);
      const statByPath = Object.fromEntries((files || []).map((f) => [f.path, f]));
      const textByPath = {};
      for (const { path, text } of splitDiff(raw)) textByPath[path] = text;
      return { statByPath, textByPath };
    })();
    SUB_DIFF.set(key, pr);
  }
  return pr;
}

/**
 * Render an AREA section (Server / Web): every code file (merged across the theme's
 * commits) as a card, each with its 1:1-matching tests nested beneath, then the
 * non-matching tests as regular cards. Each file's diff chunk comes from its OWN
 * commit's diff (fetched once per sub, cached). Returns the file count.
 */
async function mountAreaPanel(theme, area, panel) {
  const doc = panel.ownerDocument;
  const idx = themeIndex(theme);
  const files = idx.primaryByArea.get(area) || [];
  const repoRoot = MANIFEST.repoRoot;

  // Fetch every commit this area's files (and their nested tests) come from — once each.
  const subs = new Set();
  for (const f of files) {
    subs.add(f.subId);
    for (const t of idx.nestedByCode.get(f.path) || []) subs.add(t.subId);
  }
  const loaded = {};
  await Promise.all([...subs].map(async (sid) => { loaded[sid] = await loadSubDiff(theme.id, sid); }));

  panel.replaceChildren();
  let count = 0;
  for (const f of files) {
    const src = loaded[f.subId];
    panel.append(buildFileCard(doc, { path: f.path, text: src?.textByPath[f.path], stat: src?.statByPath[f.path], note: idx.notesByPath.get(f.path), repoRoot }));
    count++;
    const tests = idx.nestedByCode.get(f.path) || [];
    if (!tests.length) continue;
    const nest = el(doc, 'div', 'nest');
    for (const t of tests) {
      const ts = loaded[t.subId];
      nest.append(buildFileCard(doc, { path: t.path, text: ts?.textByPath[t.path], stat: ts?.statByPath[t.path], note: idx.notesByPath.get(t.path), repoRoot, nested: true }));
      count++;
    }
    panel.append(nest);
  }
  if (!count) panel.append(el(doc, 'div', 'empty', 'No code changes.'));
  return count;
}

/** Lazy-load an area's merged per-file diffs (with nested tests) on first expand. */
async function toggleDiff(btn) {
  const card = btn.closest('.subsection');
  const panel = card.querySelector('.files');
  const status = btn.querySelector('.sub-status');
  const caret = btn.querySelector('.caret');
  const expanded = btn.getAttribute('aria-expanded') === 'true';

  if (expanded) {
    btn.setAttribute('aria-expanded', 'false');
    caret.textContent = '▸';
    panel.hidden = true;
    return;
  }
  btn.setAttribute('aria-expanded', 'true');
  caret.textContent = '▾';
  panel.hidden = false;
  if (panel.dataset.loaded) return;

  status.textContent = 'loading…';
  status.classList.remove('error');
  try {
    const theme = themeById(btn.dataset.theme);
    const shown = await mountAreaPanel(theme, btn.dataset.area, panel);
    status.textContent = `${shown} file${shown === 1 ? '' : 's'}`;
    panel.dataset.loaded = '1';
  } catch (e) {
    status.textContent = `diff failed: ${e.message}`;
    status.classList.add('error');
  }
}

function renderOutline(manifest, nav) {
  const doc = nav.ownerDocument;
  nav.replaceChildren(el(doc, 'div', 'grp-label', `Themes · ${manifest.themes.length}`));
  for (const theme of manifest.themes) {
    const item = el(doc, 'button', 'theme-item');
    item.type = 'button';
    const areaCount = themeIndex(theme).primaryByArea.size;
    item.append(el(doc, 'span', 'nm', theme.title), el(doc, 'span', 'cc', String(areaCount)));
    item.addEventListener('click', () => {
      doc.querySelector(`.theme-card[data-theme-id="${theme.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      for (const n of nav.querySelectorAll('.theme-item')) n.classList.remove('sel');
      item.classList.add('sel');
    });
    nav.append(item);
  }
}

export async function init(doc = globalThis.document) {
  const mount = doc.getElementById('mount');
  try {
    MANIFEST = await getJSON('/api/manifest');
  } catch (e) {
    mount.replaceChildren(el(doc, 'div', 'empty', `manifest failed: ${e.message}`));
    return;
  }
  doc.getElementById('refs').textContent =
    `${MANIFEST.base} … ${short(MANIFEST.head)} · ${MANIFEST.themes.length} themes`;
  renderOutline(MANIFEST, doc.getElementById('outline'));
  renderBoard(MANIFEST, mount);
  mount.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-diff-toggle]');
    if (btn) toggleDiff(btn);
  });
}

# scanner — CI packaging + REPL help

**Date:** 2026-05-27
**Status:** Approved design

Two independent deliverables for the `scanner-cli` project.

## 1. Standalone single-folder packaging in CI

**Goal:** Produce a self-contained, single-folder build of the `scanner` CLI for
Windows and Linux that runs without a Python install, via GitHub Actions.

**Tool:** PyInstaller `--onedir` (folder with the `scanner` executable + bundled
interpreter + `pyserial`/`click`). Each OS runner builds its own native folder;
no cross-compilation.

**Trigger:** `workflow_dispatch` (manual "Run workflow" only).

**Destination:** GitHub Actions build artifacts (uploaded per-OS, downloadable
from the run page).

**New files:**
- `.github/workflows/package.yml`
- `scanner-cli/packaging/scanner_entry.py` — launcher PyInstaller targets:
  ```python
  from scanner.cli import main
  if __name__ == "__main__":
      main()
  ```

**Workflow:** one matrix job over `ubuntu-latest` + `windows-latest`:
1. `actions/checkout`
2. `actions/setup-python` (3.12)
3. `pip install ./scanner-cli pyinstaller`
4. `pyinstaller --onedir --name scanner --collect-submodules serial packaging/scanner_entry.py`
   (run with `working-directory: scanner-cli`; `--collect-submodules serial`
   bundles pyserial's platform-specific `list_ports_*` modules that static
   analysis misses)
5. Smoke test the built binary so a missing hidden-import fails CI:
   - Linux: `dist/scanner/scanner --help`
   - Windows: `dist\scanner\scanner.exe --help`
6. `actions/upload-artifact` the `scanner-cli/dist/scanner` folder as
   `scanner-linux-x64` / `scanner-windows-x64` (Actions zips automatically).

## 2. REPL `:help`

**Goal:** In `scanner repl`, list every known command with a one-line
description, both on demand (`:help`, alias `:?`) and automatically on startup.

**File:** `scanner-cli/src/scanner/cli.py`.

**Design:** one module-level `_REPL_HELP` constant, printed on REPL start
(replacing the current one-line intro) and when the user types `:help`/`:?`.

Help text:
```
Commands:
  MNEMONIC    Send a menu command, e.g. CBRENA1; prints ACK/ENQ/NAK.
  :scan       Trigger once; print the first barcode (waits up to 5s).
  :trigger    Activate scanning (SYN T).
  :untrigger  Deactivate scanning (SYN U).
  :listen     Stream decoded barcodes until Ctrl-C.
  :menuhelp   Show known menu-command mnemonics.
  :help       Show this help (alias :?).
  :quit       Exit (alias :q).
```

**Test:** `tests/test_cli.py` — invoke `repl` with input `:help\n:quit\n` and
assert each command token (`:scan`, `:trigger`, `:untrigger`, `:listen`,
`:menuhelp`, `:help`, `:quit`, `MNEMONIC`) appears in the output.

## 3. REPL `:menuhelp` — known mnemonic reference

**Goal:** Since the tool is raw-passthrough, give the user a built-in cheat-sheet
of common N36XX mnemonics. Printed when `:menuhelp` is typed in the REPL.

**File:** `scanner-cli/src/scanner/cli.py` — a `_MENU_HELP` module constant.

Content (descriptions sourced from the N36XX datasheet):
```
Known mnemonics (send these; append ? ^ * to query):
  Interface / setup
    PAP232        RS232 serial interface: 115200 8N1, CR+LF suffix, manual trigger
    TERMID0       RS232 interface only (granular; keeps trigger mode)
    232BAD9       Baud 115200 (0=300 ... 8=57600, 9=115200)
    232WRD2       8 data bits, no parity, 1 stop
  Trigger / scan mode
    PAPHHF        Manual trigger (normal)
    PAPPST        Presentation mode (hands-free)
    TRGMOD3       Presentation mode (granular)
    TRGSTO30000   Serial read time-out, ms (0-300000; default 30000)
    DLYGRD0       Good-read delay, ms (0-30000)
    TRGPMS1       Presentation sensitivity (0-20)
  Output formatting
    VSUFCR        Add CR suffix to all symbologies
  Symbology (example)
    CBRENA1       Codabar enable on (0=off)
  Defaults
    DEFALT        Activate defaults
    MNUCDF        Set custom defaults
    MNUCDS        Save custom defaults

Query: append ? (current), ^ (default), * (range), e.g. CBRENA?
```

**Test:** invoke `repl` with input `:menuhelp\n:quit\n` and assert representative
tokens (`PAP232`, `VSUFCR`, `TRGMOD3`, `DEFALT`) appear in the output.

## Verification

- REPL help: `pytest` (new test green; full suite stays green).
- CI workflow: validate YAML parses; cannot execute GitHub Actions locally, so
  rely on the in-workflow smoke test (`scanner --help`) on first manual run.

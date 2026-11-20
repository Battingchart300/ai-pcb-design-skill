# ai-pcb-design-skill — kit

Small, independent Python checkers for the skill. They verify a design
the way the skill requires: **the model never declares a board correct —
small scripts do, and a human reviews the result.**

Standard library only. No installation, no dependencies. Runs on Windows,
macOS and Linux with Python 3.8+.

## Scripts

| Script | What it checks | Input |
|---|---|---|
| `drc_check.py` | Unrouted nets, trace width, via drill/pad, annular ring, 90° corners, copper-to-edge | `.kicad_pcb` file |
| `bom_check.py` | Missing MPN / footprint / value, duplicate reference, quantity mismatch, missing LCSC | BOM `.csv` |
| `trace_width.py` | IPC-2221 trace width for a current (single value, table, or a CSV of nets) | flags / `.csv` |
| `rules_check.py` | Spec-first lint: pin on two nets, unknown reference, unconnected power pin, missing decoupling / bulk cap, I2C without pull-up, single-pin net | `spec.json` |
| `fix_corners.py` | **Fixer, not a checker:** chamfers 90° corners to 45° in a `.kicad_pcb` — writes `<name>.fixed.kicad_pcb` by default; `--in-place` only with a `.bak` backup; `--dry-run` changes nothing; acute angles are reported, never fixed | `.kicad_pcb` file |
| `run_all.py` | Runs all four checks on the example files and prints one summary | — |

## Usage

```powershell
# Windows PowerShell (from the kit folder)
python drc_check.py examples\sample.kicad_pcb
python bom_check.py examples\sample_bom.csv
python trace_width.py --current 2 --copper 1 --layer external
python trace_width.py --check-csv examples\nets.csv
python rules_check.py examples\spec.json
python fix_corners.py examples\sample.kicad_pcb
python fix_corners.py examples\sample.kicad_pcb --dry-run
python run_all.py
```

```bash
# macOS / Linux
python3 drc_check.py examples/sample.kicad_pcb
python3 fix_corners.py examples/sample.kicad_pcb
python3 run_all.py
```

`fix_corners.py` never overwrites the input by default — the fixed
board goes to `sample.fixed.kicad_pcb`. `--in-place` overwrites the
input only after writing a `<name>.bak` backup. After fixing, always
re-run `drc_check.py` on the output: the `corner-90` warnings must
be 0.

Add `--json` to any checker to get machine-readable output
(`fix_corners.py` has no `--json` — it prints the audit log only).

## Exit codes

- `0` — pass (warnings are allowed)
- `1` — fail (at least one error)
- `2` — setup missing (file not found, unparseable file, bad config)

`fix_corners.py` differs: `0` = fixed, or nothing to fix; `1` = parse
error; `2` = setup missing (file not found, bad config).

## Audit log

Every script prints an audit log at the end: script name and version,
start time, input file with SHA-256, config file with SHA-256, checks
that ran, checks that were skipped and why, finding counts, and the
final result. The log is the proof the check ran — the skill must never
claim a check passed if it did not run.

## config.json

All thresholds live in `config.json` — edit the numbers there and every
script picks them up. The values are the skill's **design-to values**
(stricter than fab minimums). Fab minimums are listed separately under
`fab_limits` and are the floor, not the target.

## Examples — expected results

The files in `examples/` contain **intentional errors** (they demonstrate
what the checks catch). The expected result for each is FAIL:

- `sample.kicad_pcb` → `drc_check.py`: **5 errors, 2 warnings**
  - 2× trace too narrow (CANH, 0.12 mm < 0.20 mm)
  - 1× via drill too small (0.20 mm < 0.30 mm)
  - 1× via pad too small (0.50 mm < 0.60 mm)
  - 1× unrouted net (`UNUSED_NET` declared, no copper)
  - 1× warning: 90° corner on CANH
  - 1× warning: copper 0.20 mm from the board edge (< 0.30 mm)
- `sample_bom.csv` → `bom_check.py`: **3 errors, 1 warning**
  - 1× missing MPN (R2 — UNVERIFIED)
  - 1× quantity mismatch (C2: quantity 2, one designator)
  - 1× duplicate reference (U1 twice)
  - 1× warning: missing LCSC number (J1)
- `nets.csv` → `trace_width.py --check-csv`: **1 fail**
  - `+3V3` 2 A needs ≥ 0.79 mm, actual 0.50 mm
- `spec.json` → `rules_check.py`: **1 error, 3 warnings**
  - 1× pin on two nets (U2.3 on SDA and BAD — a short)
  - 1× warning: SCL has no pull-up resistor
  - 1× warning: LONELY is a single-pin net
  - 1× warning: U1.7 is in no net and not in no_connect
- `sample.kicad_pcb` → `fix_corners.py`: **1 corner fixed** (CANH at
  (110, 102), chamfer 0.50 mm) → writes `sample.fixed.kicad_pcb`.
  `drc_check.py` on the fixed file reports **0 `corner-90` warnings**
  (the other intentional errors in the sample remain — the fixer only
  fixes corners, nothing else).

## What the kit does NOT do

The kit does not replace KiCad DRC (`kicad-cli pcb drc`) or ERC
(`kicad-cli sch erc`) — run those too. It is the independent second
check: it reads the raw files and verifies the things a rule file can
silently miss (a pin on two nets, a net class that matches no real net,
a design rule aimed at a fab that is not the one being used).

# ai-pcb-design-skill — kit

Small, independent Python checkers for the skill. They verify a design
the way the skill requires: **the model never declares a board correct —
small scripts do, and a human reviews the result.**

Standard library only. No installation, no dependencies. Runs on Windows,
macOS and Linux with Python 3.8+.

**Version:** 1.2.1 — 2026-11-23

## Changelog

### v1.2.1 — 2026-11-23

- **`drc_check.py` now checks clearance and shorts** (check 6): copper
  of different nets on the same layer closer than `min_clearance_mm`
  (0.20 mm from `config.json`) is an error, touching/overlapping
  copper is reported as a short. Covers segments, arcs (subdivided
  into ≤ 0.3 mm chords), vias and pads (circle, oval, rectangular;
  roundrect approximated by its bounding rectangle). Zones (copper
  pours) are NOT covered — `kicad-cli pcb drc` covers them — and
  custom pads and copper with no net are skipped; see the script's
  docstring for the full limits. The check enforces the skill's
  **design-to** clearance (0.20 mm), which is stricter than fab
  minimums (JLCPCB 0.127 mm): on a board designed to fab minimums
  (for example the ESP32-EVB reference board) it reports many
  clearance findings — triage them: below the fab minimum is a real
  problem, between the fab minimum and design-to is acceptable but
  below the skill's target. The check trusts the file's net
  assignments: if a board file has stale or wrong net labels, it
  reports shorts that are file inconsistencies — human triage
  required. `kicad-cli pcb drc` is still required for full DRC.
- **`run_all.py` takes your own files**: `--pcb`, `--bom`, `--nets`,
  `--spec` (each defaults to the example file, so no arguments still
  means the examples).
- New example: `examples/sample_clearance.kicad_pcb` (planted
  clearance/short violations for check 6).

### v1.2.0 — 2026-11-23

- No script changes. The release adds `prototypes/` (reference
  boards) at the repository root — see `README.md` and
  `SKILL.md` §1, "Reference boards first". The kit scripts
  themselves are unchanged in this version.

## Scripts

| Script | What it checks | Input |
|---|---|---|
| `drc_check.py` | Unrouted nets, trace width, via drill/pad, annular ring, 90° corners, copper-to-edge, clearance and shorts (different nets, same layer) | `.kicad_pcb` file |
| `bom_check.py` | Missing MPN / footprint / value, duplicate reference, quantity mismatch, missing LCSC | BOM `.csv` |
| `trace_width.py` | IPC-2221 trace width for a current (single value, table, or a CSV of nets) | flags / `.csv` |
| `rules_check.py` | Spec-first lint: pin on two nets, unknown reference, unconnected power pin, missing decoupling / bulk cap, I2C without pull-up, single-pin net | `spec.json` |
| `fix_corners.py` | **Fixer, not a checker:** chamfers 90° corners to 45° in a `.kicad_pcb` — writes `<name>.fixed.kicad_pcb` by default; `--in-place` only with a `.bak` backup; `--dry-run` changes nothing; acute angles are reported, never fixed | `.kicad_pcb` file |
| `run_all.py` | Runs all four checks on the example files (or on your files with `--pcb` / `--bom` / `--nets` / `--spec`) and prints one summary | — |

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
python run_all.py --pcb my_board.kicad_pcb --bom my_bom.csv --nets my_nets.csv --spec my_spec.json
python drc_check.py examples\sample_clearance.kicad_pcb
```

```bash
# macOS / Linux
python3 drc_check.py examples/sample.kicad_pcb
python3 fix_corners.py examples/sample.kicad_pcb
python3 run_all.py
python3 run_all.py --pcb my_board.kicad_pcb --bom my_bom.csv --nets my_nets.csv --spec my_spec.json
python3 drc_check.py examples/sample_clearance.kicad_pcb
```

With no arguments `run_all.py` checks the example files. With
`--pcb` / `--bom` / `--nets` / `--spec` it checks your files instead;
each argument is independent (give only the ones you have, the rest
keep their example defaults). Relative paths are resolved against the
current directory, absolute paths pass through unchanged.

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

- `sample.kicad_pcb` → `drc_check.py`: **14 errors, 2 warnings**
  - 2× trace too narrow (CANH, 0.12 mm < 0.20 mm)
  - 1× via drill too small (0.20 mm < 0.30 mm)
  - 1× via pad too small (0.50 mm < 0.60 mm)
  - 1× unrouted net (`UNUSED_NET` declared, no copper)
  - 1× warning: 90° corner on CANH
  - 1× warning: copper 0.20 mm from the board edge (< 0.30 mm)
  - 7× short (check 6, new in v1.2.1): the SDA trace crosses the
    +3V3, CANH and CANL traces; the CANH trace crosses CANL and SDA;
    the CANH via sits on the CANL trace; the GND and +3V3 pads touch
  - 2× clearance (check 6, new in v1.2.1): the SDA trace is 0.10 mm
    from the GND pad and from the CANH pad (< 0.20 mm)
- `sample_clearance.kicad_pcb` → `drc_check.py`: **5 errors,
  0 warnings** (check 6 only — every other check passes on this file)
  - 1× clearance: GND trace 0.10 mm from the +3V3 trace
  - 1× short: CANH trace crosses the CANL trace (−0.30 mm overlap)
  - 1× clearance: GND trace 0.10 mm from the +3V3 via
  - 1× clearance: SDA trace 0.10 mm from the CANL pad
  - 1× short: CANH via overlaps the CANL pad (−0.10 mm)
  - Deliberately NOT flagged: an SDA/SCL pair 0.25 mm apart (above
    the 0.20 mm minimum) and two GND traces 0.05 mm apart (same net)
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

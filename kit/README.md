# ai-pcb-design-skill — kit

Small, independent Python checkers for the skill. They verify a design
the way the skill requires: **the model never declares a board correct —
small scripts do, and a human reviews the result.**

Standard library only. No installation, no dependencies. Runs on Windows,
macOS and Linux with Python 3.8+.

**Version:** 1.2.4 — 2026-11-24

## Changelog

### v1.2.4 — 2026-11-24

Re-audit fixes (ChatGPT re-audit of v1.2.3):

- **`rules_check.py`**: a power pin marked `no_connect` is now an
  error (`power-pin-no-connect`) — a power pin must be connected to
  a power net, it can never be no-connect. It used to pass silently.
  New regression fixture `examples/regression_nc_power.json`
  (must FAIL with that one error).

### v1.2.3 — 2026-11-24

Review fixes (Claude AI + ChatGPT reviews of v1.2.2):

- **`drc_check.py` rotation fix**: pin/footprint rotation was computed
  wrong (KiCad Y-down, position −frot, shape −prot). On the Olimex
  ESP32-EVB reference board it reported 693 false shorts; after the
  fix the EVB has **1 real short** (pad 1 on `+5V` touches pad 2 on
  `Net-(U6-VDD)`). New example `examples/sample_rotated.kicad_pcb`
  (a rotated footprint, planted to catch this bug) passes **0 / 0**.
  The 14 / 5 example numbers are unchanged.
- **`trace_width.py`**: internal-layer factor corrected to **~2.6×**
  (was "~2×" in the docstring and the `--table` note, while SKILL.md
  §5.2 already proved 2.6× from the IPC-2221 formula). The 5 A
  reference-table entry corrected to **2.78 mm** (was 2.50 mm — the
  formula gives 2.78 mm; the other entries already matched). The
  table is now generated from the formula, so the two cannot drift
  apart again.
- **`--json` is valid JSON everywhere it exists**: the audit log moved
  to **stderr** in `bom_check.py`, `rules_check.py`,
  `trace_width.py`, `fix_corners.py` (new `--json` mode) and
  `run_all.py`, so stdout with `--json` is parseable JSON only
  (verified with `python -m json.tool` on each script).
  **Exception: `drc_check.py`** — its audit log is still printed to
  stdout after the JSON, so its `--json` output is still not
  parseable. That file was not touched in v1.2.3 (rotation fix only);
  the same one-line move is still to do there.
- **`rules_check.py` (new checks 10 and 11)**: a pin referenced by a
  net / `no_connect` / a power pin that is not in the part's declared
  pin list is an error (`unknown-pin` — e.g. U1.99 on a QFN-56);
  a 3-layer board is an error (`forbidden-layer-count`, config
  `layers.forbidden_counts`) and any other count outside
  `layers.allowed_counts` is an error (`unsupported-layer-count`).
  Bad spec data is now reported as a clean error instead of crashing:
  spec not an object, parts/nets entries not objects, `no_connect`
  not a list, non-text net names, non-numeric / NaN values
  (`layers: NaN` → `layers-not-a-number`), bad config values —
  exit 1 for a bad spec, exit 2 for setup (missing file, invalid
  JSON, bad config). Structural spec problems that used to raise
  `SetupError` (no `parts` / `nets` list) are now error findings
  (exit 1) — only file/config problems are exit 2.
  The example `spec.json` itself had a latent inconsistency the new
  check caught (net SCL used U2.4 while U2 declared only pins 1–3)
  — U2 now declares pins 1–4; the documented 1 error / 3 warnings
  are unchanged.
- **`fix_corners.py`**: post-fix **regression check** — after writing
  the fixed board it runs `drc_check.py` on the input and the output
  and compares error counts. On the example board the fix takes DRC
  from 14 to 15 errors, so the script now prints a loud REGRESSION
  WARNING, keeps the `.bak` / untouched input, and exits 1 instead of
  silently claiming an improvement. The +1 is a counting effect, not
  a new physical defect: the chamfer splits one 0.12 mm CANH trace
  into three segments and the per-segment trace-width check counts
  each one (the corner-90 warning does disappear). New `--json` mode
  (`--dry-run` skips the regression check — no output file to compare;
  if `drc_check.py` is missing the check is skipped with a note).

### v1.2.2 — 2026-11-24

- **`rules_check.py` (new check 0)**: `pins` / `power_pins` given as
  a string is one error per part (`pins-not-a-list` /
  `power_pins-not-a-list`); a list entry that is not a plain pin
  number is one error (`pins-not-a-number`); `pins` in a net given
  as a string is one error (`net-pins-not-a-list`). Bad values are
  treated as empty afterwards, so checks 4 and 9 do not repeat the
  same problem. Gemini test spec: 5 errors / 296 warnings → 7
  errors / 0 warnings, still FAIL; ChatGPT reference spec still
  0 / 0.

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
| `rules_check.py` | Spec-first lint: pin on two nets, unknown reference, pin not in the part's pin list, unconnected power pin, forbidden 3-layer board / unsupported layer count, missing decoupling / bulk cap, I2C without pull-up, single-pin net | `spec.json` |
| `fix_corners.py` | **Fixer, not a checker:** chamfers 90° corners to 45° in a `.kicad_pcb` — writes `<name>.fixed.kicad_pcb` by default; `--in-place` only with a `.bak` backup; `--dry-run` changes nothing; acute angles are reported, never fixed. Post-fix regression check (v1.2.3): DRC errors before vs after — warns loudly and exits 1 if the fix made the board worse | `.kicad_pcb` file |
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

**Regression check (v1.2.3):** `fix_corners.py` runs `drc_check.py`
on the input and on the output and compares the error counts. If the
output has more errors than the input it prints a loud REGRESSION
WARNING, keeps the `.bak` (or the untouched input), and exits 1.
Warnings are not compared — fixing a corner legitimately removes
`corner-90` warnings. With `--dry-run` the check is skipped (no
output file exists yet).

Add `--json` to any script to get machine-readable output on stdout;
the audit log goes to stderr, so the JSON parses cleanly. (One
exception: `drc_check.py` still prints its audit log to stdout after
the JSON — its `--json` output does not parse yet.)

## Exit codes

- `0` — pass (warnings are allowed)
- `1` — fail (at least one error)
- `2` — setup missing (file not found, unparseable file, bad config)

`fix_corners.py` differs: `0` = fixed, or nothing to fix; `1` = parse
error, or the fix made the board worse (regression — see the warning);
`2` = setup missing (file not found, bad config).

## Audit log

Every script prints an audit log at the end: script name and version,
start time, input file with SHA-256, config file with SHA-256, checks
that ran, checks that were skipped and why, finding counts, and the
final result. The log is the proof the check ran — the skill must never
claim a check passed if it did not run. Since v1.2.3 the audit log
goes to **stderr** (except `drc_check.py`, still stdout — see the
changelog), so `--json` output on stdout parses cleanly.

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
  fixes corners, nothing else) — but **15 errors, 1 warning** in
  total (was 14 / 2): the chamfer splits one undersized CANH trace
  into three segments and the per-segment trace-width check counts
  each one. `fix_corners.py` flags this with a REGRESSION WARNING
  and exits 1 (v1.2.3).
- `sample_rotated.kicad_pcb` → `drc_check.py`: **0 errors,
  0 warnings** — a rotated footprint that must NOT be reported as
  shorted (regression test for the v1.2.3 rotation fix; before the
  fix, rotated pads produced false shorts).

## What the kit does NOT do

The kit does not replace KiCad DRC (`kicad-cli pcb drc`) or ERC
(`kicad-cli sch erc`) — run those too. It is the independent second
check: it reads the raw files and verifies the things a rule file can
silently miss (a pin on two nets, a net class that matches no real net,
a design rule aimed at a fab that is not the one being used).

## Regression fixtures (audit 2026-11-24)

- `examples/regression_nc_power.json` — a power pin (U1.1) marked
  `no_connect`. Must FAIL with exactly one error,
  `power-pin-no-connect` (ChatGPT re-audit P0: it used to pass).

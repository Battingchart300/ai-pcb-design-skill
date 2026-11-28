# ai-pcb-design-skill

Teach AI models to design PCBs — from a single prompt to a manufacturable board: schematic, layout, DRC checks, KiCad 10+ output and scripts.

**Version:** 1.2.7 — 2026-11-27

## Changelog

### v1.2.7 — 2026-11-27

4-skill audit fixes in `rules_check.py` — four inputs that used to PASS now FAIL:

- **`power_pins: 42`** (a bare int, not a list) → `power_pins-not-a-list`.
- **A net pin given as an object** instead of a string label → `net-pin-not-a-string`.
- **`no_connect` with a nonexistent pin** (e.g. `Z99.1`) → `unknown-reference`.
- **A footprint of `UNVERIFIED`** → `part-missing-footprint` (same rule as the BOM MPN check, case-insensitive).

New regression fixtures in `kit/examples/` and a pytest suite in `tests/` (9 tests). Example results unchanged.

### v1.2.6 — 2026-11-25

Wave-2 Codex audit fixes:

- **`bom_check.py`**: a BOM with no MPN column is now an error
  when MPN is required (config `bom.require_mpn`) — the check used
  to be silently skipped and the BOM passed. `UNVERIFIED` in the
  MPN or Footprint column now counts as missing.
- **`rules_check.py`**: strict completeness (new check 13) — every
  part needs a value, a footprint and a non-empty pins list; every
  net needs at least one pin (an empty net is an error, a single-pin
  net stays a warning); the board section must have a name, layers
  and fab. A spec of `{"ref": "U1"}` with empty nets used to PASS.
- **`trace_width.py`**: non-finite or non-positive numeric inputs
  (inf/NaN/zero/negative current, copper weight, temperature rise
  or actual width) are rejected with a clean error — infinite copper
  used to let 10 A fit a 0.01 mm trace. A header-only CSV now FAILs
  instead of passing with zero rows checked.
- **Credit line**: "Made by PTS6845 —
  https://battingchart300.github.io" in the SKILL.md and README.md
  footers and in the `run_all.py` audit log (code constant CREDIT).
  No online check, no behaviour change, no `--json` schema change.
- Example results unchanged: spec.json 1 error / 3 warnings,
  sample_bom.csv 3 errors / 1 warning, nets.csv 1 fail, DRC samples
  24 / 13 / 2 errors.

### v1.2.5 — 2026-11-24

Codex audit fixes (ChatGPT Codex / GPT-6 audit of v1.2.4 — 160 tests,
compared with KiCad 9.0.2):

- **`fix_corners.py`**: a chamfer never disconnects a pad — one that
  would is reverted and reported (`corners_reverted`). New segments
  write the numeric net id only (`(net <id>)`); KiCad 9.0.2 refused
  the old name form. The regression check now compares DRC on the
  ORIGINAL input (`--in-place` used to compare the file with itself).
  `--output` pointing at the input file is refused without
  `--in-place` (which writes a `.bak` backup first).
- **`drc_check.py`**: real per-net connectivity (union-find over
  pads, segments, arcs and vias) — two distant pads of one net with
  no path between them now FAIL as `unrouted-net`. A via is checked
  on every layer it spans, not just F.Cu/B.Cu. Edge clearance is
  measured from the copper edge (centreline minus half the trace
  width).
- **Example counts changed** (all new errors are genuine
  `unrouted-net` findings): `sample.kicad_pcb` 14 → **24 errors**,
  `sample_clearance.kicad_pcb` 5 → **13**, `sample_rotated.kicad_pcb`
  0 → **2** (still 0 shorts — the rotation fix holds).

### v1.2.4 — 2026-11-24

Re-audit fixes (ChatGPT re-audit of v1.2.3):

- **`rules_check.py`**: a power pin marked `no_connect` is now an
  error (`power-pin-no-connect`) — a power pin must be connected to
  a power net, it can never be no-connect. It used to pass silently.
  New regression fixture `kit/examples/regression_nc_power.json`
  (must FAIL with that one error).

### v1.2.3 — 2026-11-24

Review fixes (Claude AI + ChatGPT reviews of v1.2.2 — both re-ran
every kit script):

- **`drc_check.py` rotation fix**: pin/footprint rotation was computed
  wrong (KiCad Y-down, position −frot, shape −prot), which reported
  693 false shorts on the Olimex ESP32-EVB reference board. After the
  fix the EVB has **1 real short**. New example
  `kit/examples/sample_rotated.kicad_pcb` (a rotated footprint) passes
  0 shorts (the rotation fix holds) but now reports 2 unrouted errors
  — two footprints with no segments between them, which is expected.
  The example numbers changed: sample 14 → 24 errors,
  sample_clearance 5 → 13 (new unrouted-net findings).
- **`trace_width.py`**: internal-layer factor corrected to **~2.6×**
  (was "~2×" in the script while SKILL.md §5.2 already proved 2.6×),
  and the 5 A table entry corrected to **2.78 mm** (was 2.50 mm —
  the formula gives 2.78 mm). The reference table is now generated
  from the formula, so the two can never drift apart again.
- **`--json` is valid JSON everywhere**: the audit log moved to
  **stderr** in all scripts, so stdout with `--json` is parseable
  JSON only. (`drc_check.py` is the one exception for now — its
  audit log is still on stdout; see kit/README.md.)
- **`rules_check.py`**: new checks — a pin that is not in the part's
  pin list is an error (`unknown-pin`, e.g. U1.99), and a 3-layer
  board is an error (`forbidden-layer-count`, config
  `layers.forbidden_counts`). Bad spec data (wrong types, NaN,
  strings where lists belong) is reported as a clean error (exit 1),
  never a Python traceback. The example `spec.json` itself had a
  latent inconsistency the new check caught (net SCL used U2.4 while
  U2 declared only pins 1–3) — U2 now declares pins 1–4; the
  documented 1 error / 3 warnings are unchanged.
- **`fix_corners.py`**: post-fix **regression check** — after writing
  the fixed board it runs `drc_check.py` on the input and the output
  and compares error counts. On the example board the fix takes DRC
  from 24 to 25 errors (the chamfer splits one undersized trace into
  three segments, each counted separately) — the script now warns
  loudly, keeps the `.bak` / untouched input, and exits 1 instead of
  silently claiming an improvement. Also new: `--json` output.
- **Numbers synced**: SKILL.md now says JLCPCB min board **6×6 mm**
  (was 3×3 mm; `config.json` already said 6×6) and the §7.x
  cross-references are fixed (§7.2–§7.4 → §7.3–§7.5; toner transfer
  is §7.4, photoresist §7.3).

### v1.2.2 — 2026-11-24

- **`rules_check.py` rejects bad pin formats with one clear error**:
  `pins` / `power_pins` given as text instead of a list is now one
  error per part (`pins-not-a-list` / `power_pins-not-a-list`), instead
  of hundreds of warnings from reading the text character by
  character. Same for non-numeric list entries and `pins` in nets.
  Bad values are treated as empty afterwards, so the same problem is
  not reported twice. (Gemini test spec: 5 errors / 296 warnings →
  7 errors / 0 warnings, still correctly FAIL; ChatGPT reference
  spec still 0 / 0.)

### v1.2.1 — 2026-11-23

- **YAML frontmatter on `SKILL.md`** (`name` + `description`) — Claude
  Code and other Agent Skills hosts need it to load the skill at all.
- **`drc_check.py` now checks clearance and shorts**: copper of
  different nets on the same layer closer than `min_clearance_mm`
  (0.20 mm) is an error, touching/overlapping copper is a short.
  Covers segments, arcs, vias and pads; zones (pours) are not covered
  — `kicad-cli pcb drc` is still required. New example
  `kit/examples/sample_clearance.kicad_pcb` demonstrates the checks.
- **`run_all.py` takes your own files**: `--pcb`, `--bom`, `--nets`,
  `--spec` (each defaults to the example file).
- **Fixed §5.2**: an internal trace needs **~2.6× the width** (not
  ~2×) for the same current — from `I = k·ΔT^0.44·A^0.725`,
  `A_int/A_ext = 2^(1/0.725) ≈ 2.6`.

### v1.2.0 — 2026-11-23

- **Reference boards (`prototypes/`)** — two complete, proven,
  manufactured boards to learn from, so any AI using the skill
  sees what a good board looks like before designing one (see
  `SKILL.md` §1, "Reference boards first"):
  - **Arduino UNO R3** (`prototypes/arduino-uno-r3/`) — official
    reference design (EAGLE schematic + layout, schematic PDF),
    CC BY-SA, with a README on what to learn from it.
  - **Olimex ESP32-EVB, Rev L** (`prototypes/esp32-evb/`) —
    Apache 2.0, KiCad, 2-layer (Rev L schematic + layout, Rev K2
    BOM — Rev L has no BOM of its own), with a README on what to
    learn from it.
  - The reference boards keep their own licenses; the skill
    itself stays MIT.

### v1.1.0 — 2026-11-20

- **Automatic 90° → 45° corner fix** (`kit/fix_corners.py`) — the
  skill now not only finds 90-degree corners, it fixes them: each
  corner is chamfered (default 0.5 mm, configurable in
  `kit/config.json`), the input file is never overwritten by default
  (`<name>.fixed.kicad_pcb`), `--in-place` only with an automatic
  `.bak` backup, `--dry-run` changes nothing. Acute angles are
  reported as manual work, never auto-fixed. See `SKILL.md` §4.4.1.

## What it does

`SKILL.md` is a gated workflow for an AI assistant that helps design
printed circuit boards:

- **13 capabilities** — layers 1/2/4+, components from requirements,
  board outline (rounded and square corners), routing rules, DRC +
  pre-manufacturing check, power, carrier boards for compute modules
  (e.g. Raspberry Pi CM5 via DF40), a board around any chip from its
  datasheet, DIY computers from discrete 74xx logic, a custom
  motherboard, DDR2/DDR3 DIMM and SO-DIMM, design from a single user
  prompt (PCB + BOM), and audit of a PCB the user hands over.
- **All manufacturing methods** — professional fab (JLCPCB), home
  photoresist + UV, thermal transfer + etching, CNC milling, flex,
  rigid-flex, metal-core, HDI, RF, conductive ink, 3D-printed circuits,
  ceramic, LDS.
- **Hard rules** — never invent a value (ask the user instead), verify
  on the web never from memory, mark the unverifiable `UNVERIFIED`,
  never loosen a check, the order is placed only by the human.
- **The 3 checks** of a finished board (schematic & wiring, layout &
  DRC, pre-manufacturing) — each finds as many errors as possible and
  fixes them.
- **A kit of real Python scripts** (`kit/`) that verify the design
  independently: the model never declares a board correct — the scripts
  do, and a human reviews the result.
- **Reference boards (`prototypes/`)** — complete, proven boards to
  study before designing a similar one (Olimex ESP32-EVB, Arduino
  UNO R3). Patterns to learn from, never files to copy blindly.

## Works with any AI

The skill is **backend-agnostic** — nothing in it is tied to one model
or one provider:

| Backend | How to use it |
|---|---|
| **Claude Code** | Copy `SKILL.md` into your skills folder (e.g. `.claude/skills/ai-pcb-design-skill/SKILL.md`) or point the agent at this repo. Copy `kit/` next to it — the scripts are referenced by path. |
| **ChatGPT** | Upload `SKILL.md` as project knowledge / into a custom GPT's instructions, and `kit/` as files the model can run or reference. |
| **Local model** | Load `SKILL.md` into the model's context (system prompt or attached file) and run the kit scripts locally. |
| **API (e.g. NVIDIA NIM)** | Send `SKILL.md` as the system prompt / context with your requests, and run the kit scripts on your own machine. |

The workflow, the rules and the checks are the same everywhere. If a
step needs a tool that does not exist in your environment (for example
`kicad-cli` on a machine without KiCad), the skill says so and tells
you the manual alternative — it never pretends a check ran when it did
not.

## Repository structure

```
ai-pcb-design-skill/
├── SKILL.md            # the skill (the whole workflow)
├── README.md           # this file
├── LICENSE             # MIT
├── prototypes/         # reference boards to study first
│   ├── README.md       # index + how-to-use rules
│   ├── esp32-evb/      # Olimex ESP32-EVB, Rev L (Apache 2.0)
│   └── arduino-uno-r3/ # Arduino UNO R3 (CC BY-SA)
└── kit/
    ├── README.md       # kit usage, expected results
    ├── config.json     # user-editable rules (thresholds)
    ├── drc_check.py    # DRC checks on a .kicad_pcb file
    ├── fix_corners.py  # automatic 90° → 45° corner fix
    ├── bom_check.py    # checks on a BOM CSV
    ├── trace_width.py  # IPC-2221 trace-width calculator
    ├── rules_check.py  # spec-first lint (spec.json)
    ├── run_all.py      # runs all four checks on the examples
    └── examples/       # sample inputs with intentional errors
```

## Quick start

```bash
# 1. Write a spec for your board (see SKILL.md §2 and kit/examples/spec.json)
# 2. Lint the spec — fix errors before drawing anything
python kit/rules_check.py my-board/spec.json

# 3. Design the board in KiCad 10+ (or EasyEDA — see SKILL.md §9),
#    then check it
python kit/drc_check.py my-board/board.kicad_pcb
python kit/bom_check.py my-board/bom.csv
python kit/trace_width.py --check-csv my-board/nets.csv

# 3b. If drc_check reports 90-degree corners, fix them automatically
#     (writes board.fixed.kicad_pcb, input untouched), then re-check
python kit/fix_corners.py my-board/board.kicad_pcb
python kit/drc_check.py my-board/board.fixed.kicad_pcb

# 4. Or run everything on the examples
python kit/run_all.py
```

All scripts are standard library only — no installation needed.
Windows: use `python` (PowerShell). macOS/Linux: use `python3`.

Exit codes: `0` = pass, `1` = fail, `2` = setup missing. Every script
prints an audit log at the end (to stderr since v1.2.3, so `--json`
stdout stays parseable) — the log is the proof the check ran.

## Roadmap

### v1.3 (planned)

- Full EasyEDA API automation (running bridge + complete command set)
- EMC pre-compliance check (44 rules, 18 categories)
- BOM management + sourcing (stock checks, LCSC/DigiKey/Mouser,
  substitutes, 5 boards + 2 spares per part)
- Structured datasheet extraction (typed facts, cache, confidence
  low/medium/high, stop rule)
- Placement recipes and priorities (P0–P7)
- Bring-up + test points (fiducials, SWD/JTAG, bring-up plan)
- Library of verified sub-circuits (LDO, USB-C, ESP32 core, …)
- DDR length tuning (method: DQS/CK first, mm and ps)
- 4-layer plane escalation
- SPICE simulation before manufacturing
- ECO / versioning (changes on a routed board, netlist diffs)
- Audit log / run cache across runs
- Design documentation (design brief, PDF document)

### v1.4 (ideas)

- DDR4 routing (after DDR2/DDR3 is proven)
- More verified sub-circuits from real built boards
- KiCad 10 design variants support

## Honest limits

- A skill is a workflow + checklists + review. The model still
  hallucinates footprints and pinouts — that is why every pin, value
  and footprint must be verified against a datasheet, and why the kit
  scripts and a human review are gates, not formalities.
- The model cannot click wires in EasyEDA. Layout in EasyEDA goes
  through the API/CLI (§9) — or the user finishes it with the mouse.
- DRC 0/0 does not mean manufacturable. The DFM gate (§7.2 in
  `SKILL.md`) and the visual check exist for exactly that reason.
- A home-made GPU, a custom motherboard and DDR routing are big,
  hard projects. The skill teaches the principles and the rules — it
  does not promise a finished computer.

## License

MIT — see `LICENSE`.

---

*Made by PTS6845 — https://battingchart300.github.io*

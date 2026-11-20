# ai-pcb-design-skill

Teach AI models to design PCBs — from a single prompt to a manufacturable board: schematic, layout, DRC checks, KiCad 10+ output and scripts.

**Version:** 1.0.0 — 2026-11-20

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
└── kit/
    ├── README.md       # kit usage, expected results
    ├── config.json     # user-editable rules (thresholds)
    ├── drc_check.py    # DRC checks on a .kicad_pcb file
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

# 4. Or run everything on the examples
python kit/run_all.py
```

All scripts are standard library only — no installation needed.
Windows: use `python` (PowerShell). macOS/Linux: use `python3`.

Exit codes: `0` = pass, `1` = fail, `2` = setup missing. Every script
prints an audit log at the end — the log is the proof the check ran.

## Roadmap

### v1.1 (planned)

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

### v1.2 (ideas)

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

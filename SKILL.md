---
name: ai-pcb-design-skill
description: Teaches an AI assistant to design PCBs from a single prompt to a manufacturable board — schematic, layout, DRC checks, KiCad 10+ output. Use when designing, reviewing or fixing a PCB with an AI.
---

# ai-pcb-design-skill

**Version:** 1.2.7 — 2026-11-27

**v1.2.7 — 2026-11-27 (4-skill audit fixes):** `rules_check.py` now fails four inputs that used to pass: a `power_pins` value that is not a list (e.g. `power_pins: 42` → `power_pins-not-a-list`), a net pin given as an object instead of a string label (`net-pin-not-a-string`), a `no_connect` entry naming a part that is not in the spec (e.g. `Z99.1` → `unknown-reference`), and a footprint of `UNVERIFIED`, which counts as missing — same rule as the BOM MPN check (`part-missing-footprint`, matched case-insensitively). New regression fixtures in `kit/examples/` and a pytest suite in `tests/` (9 tests). Example results unchanged: spec.json 1 error / 3 warnings, sample_bom.csv 3 errors / 1 warning, nets.csv 1 fail, DRC samples 24 / 13 / 2 errors.
**v1.2.6 — 2026-11-25 (Wave-2 Codex audit fixes):** `bom_check.py` no longer skips the MPN check when the BOM has no MPN column (that is an error when MPN is required), and `UNVERIFIED` in the MPN or Footprint column counts as missing. `rules_check.py` now enforces strict completeness (new check 13): every part needs a value, a footprint and a non-empty pins list, every net needs at least one pin, and the board section must have a name, layers and fab — a spec of {"ref": "U1"} with empty nets no longer passes. `trace_width.py` rejects non-finite or non-positive numeric inputs (inf/NaN/zero/negative current, copper weight, temperature rise or actual width) with a clean error, and a header-only CSV now FAILs instead of passing with zero rows checked. Credit line added: "Made by PTS6845 — https://battingchart300.github.io" in the SKILL.md and README.md footers and in the `run_all.py` audit log (code constant CREDIT, no online check, no behaviour change, no --json schema change). Example results unchanged: spec.json 1 error / 3 warnings, sample_bom.csv 3 errors / 1 warning, nets.csv 1 fail, DRC samples 24 / 13 / 2 errors.
**v1.2.5 — 2026-11-24 (Codex audit fixes, ChatGPT Codex / GPT-6 audit of v1.2.4, 160 tests + KiCad 9.0.2):** `fix_corners.py` never disconnects a pad — a chamfer that would leave a pad or via unconnected is reverted and reported (`corners_reverted`); new segments write the numeric net id only (`(net <id>)`, KiCad 9.0.2 refused the old name form); the regression check now compares DRC on the ORIGINAL input (before, `--in-place` compared the file with itself); `--output` pointing at the input is refused without `--in-place`. `drc_check.py` now verifies real connectivity per net (union-find over pads, segments, arcs and vias — two distant pads of one net no longer pass); a via is checked on every layer it spans (not just F.Cu/B.Cu); edge clearance is measured from the copper edge (centreline minus half the trace width). Example counts changed: `sample.kicad_pcb` 14 → **24 errors**, `sample_clearance.kicad_pcb` 5 → **13**, `sample_rotated.kicad_pcb` 0 → **2** (all new errors are genuine `unrouted-net` findings; the rotated fixture still reports 0 shorts).
**v1.2.4 — 2026-11-24 (re-audit fixes, ChatGPT re-audit of v1.2.3):**
`rules_check.py` now errors on a power pin marked no_connect
(`power-pin-no-connect` — a power pin must be connected to a power
net, it can never be no-connect; it used to pass silently). New
regression fixture `kit/examples/regression_nc_power.json` (must FAIL
with that one error).
**v1.2.3 — 2026-11-24 (review fixes, from the Claude AI + ChatGPT
reviews of v1.2.2):** `trace_width.py` internal-layer factor corrected
to ~2.6× and the 5 A table entry to 2.78 mm (formula-generated);
`--json` output is valid JSON in every script (audit log moved to
stderr); `rules_check.py` now errors on a pin that is not in the
part's pin list and on a forbidden 3-layer board, and reports bad spec
data as clean errors instead of crashing; `fix_corners.py` runs a
post-fix regression check (DRC errors before vs after) and warns
loudly if the fix made the board worse; numbers synced between
`config.json`, this file and the scripts (JLCPCB min board 6×6 mm,
§7.x cross-references fixed).
**What it is:** a skill that teaches an AI assistant to design printed
circuit boards (PCBs) — from a single user prompt to a manufacturable
board: schematic, layout, DRC checks, KiCad 10+ output and scripts.

**Who it is for:** a beginner who designs boards and lets the AI do the
drafting — while the human stays in charge of every decision that matters.

**How to use it:** load this file into the AI you are working with. It
works with **any AI backend** — a local model, an API (for example
NVIDIA NIM), or directly inside Claude Code / ChatGPT. Nothing in this
skill is tied to one model or one provider: the workflow, the rules and
the checks are the same everywhere. If a step needs a tool that does not
exist in your environment (for example `kicad-cli` on a machine without
KiCad), the skill says so and tells you the manual alternative — it never
pretends a check ran when it did not.

---

## 0. Hard rules — these never bend

Read this section first. Every later section assumes it.

1. **Never invent a part number, pin, footprint, datasheet value or fab
   limit.** If a value cannot be verified, write `UNVERIFIED` and cite
   the file and page where it should be checked. A guessed pinout is the
   number-one cause of dead AI-designed boards.
2. **When you do not know a value, ASK the user.** Never invent a size,
   a voltage, a pin assignment or a part. A question costs a minute; a
   wrong guess costs a respin.
3. **Verify on the web, never from memory.** Datasheets, component
   specifications and fab capability limits are checked against live
   sources (manufacturer site, distributor page, fab capability page).
   Memory is not a source.
4. **Never disable, filter or loosen a check.** A waiver (knowingly
   breaking a rule) is a human decision, written down with a reason.
   The model never waives anything by itself.
5. **The model never decides correctness.** Small, independently runnable
   scripts in `kit/` verify the design (exit 0 = pass, 1 = fail,
   2 = setup missing). The model is never the one who declares a board
   correct. KiCad ERC/DRC run at every stage.
6. **Never order, upload or publish anything.** The skill may *fill in*
   an order form (Gerbers, BOM, CPL, parameters) — but the order itself
   is placed only by the human, manually, with human review. The skill
   never submits an order and never uploads files anywhere by itself.
7. **Never claim a check ran if it did not run.** If a tool is missing,
   the report says so. A skipped check is a gap in the review, not a
   silent omission.
8. **Never destroy the user's work.** Before the first change to a
   board the user made, make a checkpoint (a copy of the whole project,
   named e.g. `before-skill-run`). Checkpoint again before every risky
   step (schematic → PCB conversion, routing, copper pours). Delete,
   bulk moves and saving happen only after the user confirms — unless
   the user explicitly said "save".
9. **A failed gate stops the work.** Fix the cause, re-run the *same*
   check. Do not work around it, do not relax the rule, do not proceed
   to the next stage. If a stage fails 3 times, stop and ask the human.
10. **The schematic is the design; the layout is only its physical
    implementation.** Errors caught in the schematic are cheap. Errors
    caught after fabrication are a respin.

---

## 1. Gated workflow

Work in stages. Each stage ends in a **gate**: a check that must pass
before the next stage starts. Editing a board after a stage passed
re-opens the dependent stages — their evidence is older than the design.

| Stage | Do | Gate |
|---|---|---|
| 0. Requirements | Write the spec (see §2). Pick the fab method — it sets every later rule. | Spec passes `kit/rules_check.py` with 0 errors. Human approves the spec. |
| 1. Architecture & parts | Block diagram, part choice per §5.2, datasheet for every active part. | Every part has an MPN + datasheet file/page + footprint. No part without a datasheet is used. |
| 2. Schematic | Draw per §5.2, annotate, run ERC. | ERC: 0 errors; every warning justified in writing. |
| 3. Footprints | Verify every footprint against the datasheet land pattern (IPC-7351). | `kit/bom_check.py` on the BOM: 0 errors. |
| 4. Stackup & rules | Enter the fab's numbers into Board Setup / DRC *before* placing anything. Set net classes. | Design rules match the chosen fab (§7). |
| 5. Placement | Floorplan first, then exact placement (§5.4, §6.3). | Human approves the floorplan, then the placement (review stop). |
| 6. Routing | Priority order (§4.4); autorouter only for ordinary nets (§6.4). | All nets routed; `kicad-cli pcb drc`: 0 errors. |
| 7. Power integrity | Decoupling, bulk caps, regulator hot loop (§4.6, §6.1). | `kit/trace_width.py` passes every power net. |
| 8. Checks | The 3 checks (§8). | All 3 checks pass; review report written. |
| 9. Fab pack | Gerber + drill + BOM + CPL (§11). | DFM gate (§7.2) passes; Gerber replay in GerbView. |
| 10. Order & bring-up | Human reviews and places the order (§0 rule 6); bring-up (§10). | Human sign-off in writing. |

**Human review stops (the model waits for the human):**

1. **After the spec** — the human confirms what the board must do, its
   size, connectors.
2. **After the floorplan** — block layout approved before placement.
3. **After placement** — placement approved before routing (moving parts
   after routing costs the most time).
4. **Before the order** — fab gate: the human confirms the order goes out.

**Structural changes need the human:** the model never changes the
architecture, swaps a chip, or changes the layer count without asking.
A waiver is human-only, listed explicitly with a reason.

### Reference boards first — prototypes/

Before designing a board similar to one you already know, study a
real, manufactured board first. The skill ships reference boards in
`prototypes/` — read `prototypes/README.md` first, then the README of
the matching board, **before Stage 0**:

- ESP32 board → `prototypes/esp32-evb/` (Olimex ESP32-EVB, Rev L).
- ATmega / Arduino-compatible board → `prototypes/arduino-uno-r3/`
  (Arduino UNO R3 official reference design).

**Rules for reference boards:**

- **Pattern, not copy.** Learn how the reference solves power,
  reset, decoupling, connectors and routing — then apply the pattern
  to your own spec. Never paste its schematic or layout into your
  design, and never claim your board "is" the reference board.
- **Datasheets still win.** A value in a reference design is a hint,
  not a verified fact. Every pin, value and footprint in your design
  still has to be verified against its datasheet (§0). If the
  reference and the datasheet disagree, the datasheet wins — and the
  disagreement goes into the review report.
- **Licenses stay with the boards.** The reference boards keep their
  own licenses (Apache 2.0 for ESP32-EVB, CC BY-SA for Arduino UNO
  R3). The skill itself stays MIT. Never re-license a reference file
  as MIT.
- **If the matching reference board is not in `prototypes/` yet**
  (its README says the files are pending), say so and continue
  from the spec and datasheets — do not invent a reference.

---

## 2. Spec-first: write the specification before drawing anything

Before the schematic, write one spec file — it is the source of truth
for the whole design. The skill provides the format (`kit/examples/spec.json`):

```json
{
  "board": {"name": "My Board", "layers": 2, "fab": "jlcpcb",
            "outline_mm": [50, 40]},
  "parts": [
    {"ref": "U1", "value": "ESP32-S3", "footprint": "QFN-56",
     "mpn": "ESP32-S3-WROOM-1", "type": "mcu",
     "pins": ["1", "2", "3", "4"],
     "power_pins": ["1", "2"]},
    {"ref": "C1", "value": "100nF", "footprint": "0603",
     "mpn": "CL10B104KB8NNNC", "type": "capacitor", "pins": ["1", "2"]}
  ],
  "nets": [
    {"name": "+3V3", "pins": ["U1.1", "C1.1"]},
    {"name": "GND", "pins": ["U1.2", "C1.2"]}
  ],
  "no_connect": ["U1.8"]
}
```

The spec contains: what the board does (1–2 sentences), power (input
voltage, output rails), size and outline, connectors and their position,
layer count, fab method, the parts list (reference, value, footprint,
MPN), and the net list (net name, which pins it connects).

**Lint the spec before drawing** — fixing a line costs nothing, fixing
geometry costs hours:

```bash
python kit/rules_check.py spec.json
```

Errors that stop the work: unknown reference, a pin number the symbol
does not have, a pin on two nets at once (a short), a pin in a net and
in `no_connect`, a power input pin with no connection, a forbidden
3-layer board or an unsupported layer count.

Warnings to resolve or justify in a note: an IC rail with no capacitor
to ground, a rail with no bulk capacitor (at least 10 µF), SDA/SCL with
no pull-up, a net made only of inputs, a single-pin net (usually a typo
in the name), pins in no net and without no-connect.

Name differential pairs correctly from the start (`<BASE>_P` /
`<BASE>_N`) — KiCad pairs by name. A net that looks like half a pair
(for example an active-low `..._N`) can silently merge with its
complement.

**Rule: nothing is drawn until the spec has 0 errors.** A warning may
stay only with a reason written in a note on the sheet.

---

## 3. Code-first generation

The **code is the source of truth, not the GUI**. When the design is
generated (rather than drawn by hand), it is generated from a
`board_spec.py` — an authoritative netlist (a pad → net map for every
footprint). The schematic is documentation of that netlist, not the
driver of the design. Coordinates are in millimetres from the top-left
corner of the board (+x right, +y down).

**Schematic from code:** symbols are generated from Python
(hierarchical sheets, power-port symbols, real wires and junctions,
buses, named functional blocks — one per circuit, outlines derived from
content). Signals flow left to right; power from the top, ground to the
bottom. Every rail is a power port, never a text label. A label always
sits at the end of a stub ≥ 2.54 mm, never on a pin. Spacing is
calculated, not eyeballed.

**Oracle verification (non-negotiable):** after generating, the result
is proven against KiCad itself — netlist from the generated schematic
vs the spec, ERC, and a render that is looked at (§8). A generator's
`write()` that reports errors means: fix before continuing.

**Preflight is mandatory:** before any build, run a preflight that
checks KiCad CLI + KiCad Python (`pcbnew`) + Java (Freerouting) +
`board_spec.py`, and prints an exact fix for every missing piece. The
build script runs preflight first and stops on failure. **Nothing is
installed without the user's "yes". Close KiCad before a build** (it
locks the board file).

**Two Pythons:** generators run under the system Python; `pcbnew`
scripts must run under KiCad's bundled Python — if the wrong
interpreter is used, the script says which one is correct.

**If no generator exists:** the model writes `.kicad_sch` /
`.kicad_pcb` S-expressions directly — but always with oracle
verification (netlist + ERC + DRC). Never "written and done" without
verification.

---

## 4. What the skill can do — the 13 capabilities

### 4.1 Layers — 1, 2, 3, 4 and more

| Stackup | Use for | Typical arrangement |
|---|---|---|
| 1-layer | Cheapest, simplest: LED drivers, single-sided home-etched boards, through-hole only | Copper on one side only; parts on top |
| 2-layer | Default beginner board: slow MCU, sensors, motor drivers, low-speed IoT | Signals both sides; ground pour on one/both faces |
| 4-layer (workhorse) | USB, Ethernet, radio module, dense MCU board, anything with controlled impedance or EMI concern | L1 Signal / L2 solid GND / L3 Power (or power + signals) / L4 Signal |
| 6 / 8-layer | Routing congestion, DDR/USB3/PCIe/HDMI, mixed-signal isolation | e.g. 6L: SIG–GND–SIG–PWR–GND–SIG |

**3-layer boards: do not design them.** Stackups are built
symmetrically around a central core to avoid warpage; an odd count is
unbalanced. A "3-layer" board is normally manufactured as a 4-layer
board with one layer left blank, at 4-layer cost. Rule: **if 2 layers
are not enough, go to 4; never specify 3** — unless the fab explicitly
quotes 3-layer as a product.

On 2-layer FR-4 a 50 Ω trace is ~2.88 mm wide (plane 1.53 mm away),
on 4-layer ~0.38 mm (plane 0.20 mm away) — controlled impedance on
2 layers is impractical; use 4 layers for USB / Ethernet / radio /
switching regulator above ~1 MHz / fast clocks.

### 4.2 Components from requirements

Method, for every part: (1) write the requirement (voltage, current,
speed, pins, environment); (2) shortlist 2–3 exact part numbers;
(3) open the **manufacturer's datasheet** (not a blog, not the model)
and record the pinout table (pin number → function), package +
recommended land pattern, absolute maximum ratings, operating
conditions, required externals and their values, and the layout
section; (4) check stock + LCSC/JLCPCB Basic vs Extended status if
assembling; (5) only then place the symbol. **If a datasheet cannot be
found, the part is not used — however confident the suggestion sounded.**

**MCU:** core/performance, flash/RAM headroom, peripheral list mapped
**pin by pin** (CAN controller? USB device/host? ADC channels? timers?
UART/SPI/I²C count?), GPIO count *after* reserving boot/strapping,
debug (SWD/JTAG), crystal and reset pins, voltage domain (1.8/3.3/5 V),
sleep current for battery, package (hand-solderable QFP/QFN — BGA is
not a beginner package), toolchain, longevity. Common traps: copying
Arduino pin numbers instead of the chip's physical port pins; assuming
a peripheral can go on any pin (STM32 alternate functions vary by
part/package — use CubeMX / the datasheet pin table); ESP32
strapping/boot pins; choosing a bare chip when a **module** (e.g.
ESP32-WROOM, flash + RF already done) is the right call; forgetting
crystal + load caps, reset pull-up, BOOT0 pull-down, SWD header.

**Voltage regulator:** decide by calculation, not by guess:
`P_dissipated = (V_IN − V_OUT) × I_OUT`. Rule of thumb: **< ~1 W →
LDO** (simpler, quieter); **> ~1 W → buck** (80–95% efficient);
noise-critical rail → buck to an intermediate rail + LDO for the last
drop. Examples: 5 V → 3.3 V at 0.5 A = 0.85 W in an LDO (borderline —
SOT-23-5 will thermal-shutdown without generous copper/thermal vias;
SOT-223 or a buck is safer); 12 V → 3.3 V at 0.5 A = 4.35 W in an LDO
(never — use a buck). LDO checks: dropout *at your load current and
worst-case temperature*, max input voltage, output current, junction
temperature `T_J = T_ambient + P_D × θ_JA` (stay below ~100–125 °C),
input/output capacitor values + ESR/type from the datasheet, enable pin
behaviour. Buck checks: input range, output + peak inductor current,
efficiency at your operating point, inductor + cap values from the
datasheet, switching frequency, hot-loop layout (copy the datasheet
layout), output ripple vs noise budget, UVLO/OCP/OTP.

**CAN transceiver:** the MCU's CAN peripheral (or an external
controller such as MCP2515 over SPI) is logic-level only; a
**transceiver is mandatory** for CANH/CANL. Choose by **logic voltage
first**: 3.3 V MCU → 3.3 V transceiver (TI SN65HVD230/232) or a
dual-rail part with a VIO pin (NXP TJA1051T/3, TI TCAN1042V); 5 V MCU
→ 5 V part (TJA1050, MCP2551). **Never connect a 5 V transceiver's
RXD directly to a 3.3 V MCU unless the GPIO is 5 V-tolerant** — it can
permanently damage the MCU. Check: max bit rate (1 Mbps classic CAN;
CAN FD needs a CAN-FD-capable transceiver), common-mode range, mode
pins (tie deliberately, never float), VREF pin function (varies by
part), ESD rating, AEC-Q100 for automotive. Verify pinout (TXD/RXD vs
CANH/CANL — swapped CANH/CANL is a classic "CAN doesn't work" fault)
and whether the part/module already integrates termination.

**Connectors:** choose by mating part, current per pin, pitch,
mounting (through-hole for mechanical strength on cables), pin-1 /
keying / polarity (a mirrored connector footprint mounts on the wrong
side — verify against the datasheet drawing, not the library),
keep-out around the shell, strain relief. USB-C: CC resistors
(5.1 kΩ pull-downs for a sink), ESD, D+/D− not swapped.

**Passives:** resistors — value, tolerance, power rating
(`P = I²R` / `V²/R`), package (0805 hand-solderable default; 0603
small; 0402/0201 not for hand assembly); capacitors — value,
**voltage rating (≥1.5–2× the rail)**, dielectric (X7R for decoupling,
C0G/NP0 for timing/filtering, never Y5V for decoupling), ESR/ESL where
the datasheet specifies; inductors — saturation current > peak current,
DCR; crystals — load capacitance (two caps = `2 × (C_L − C_stray)`),
ESR, tolerance. Every passive needs a footprint whose pad size matches
its package.

### 4.3 Board outline — rounded edges AND normal corners, as needed

- **Rounded corners, radius ≥ 0.5 mm** — the default. Reduces stress
  concentration, fits enclosures with rounded internal corners, safer
  handling. Use for handheld boards and anything that goes into an
  enclosure.
- **Square (normal) corners** — when the mechanics require a sharp
  corner (panelised boards, a board that must sit flush in a square
  pocket). Square is acceptable only if the enclosure/mechanics
  require it.
- Keep copper ≥ 0.3 mm from the edge and components ≥ 1 mm from the
  edge. Include cutouts/notches/keep-outs around connectors.
- **Mounting holes:** **M3 (3.2 mm drill)** is the standard choice;
  M2.5 (2.7 mm) for small boards. Place at the enclosure's actual
  coordinates, in the corners, with a copper keep-out / ground
  clearance ring around the hole (no copper under a metal screw head
  unless deliberately grounded through a plated hole + washer), and do
  not route traces under a screw head. Add fiducials for assembly
  (at least 3 per side with SMD assembly).
- Edge.Cuts must be one closed shape.

### 4.4 Routing rules

Route in priority order: **differential pairs → clocks/reset →
sensitive analogue → power/ground (or planes) → general signals.**

- **45° corners (or smooth arcs), never 90°, never acute (< 90°).**
  90° corners create an impedance discontinuity and, in older etching,
  acid traps. For RF/microwave use arcs/mitered bends (radius > 3×
  trace width).
- No stubs. No routing over a plane split — the return current
  detours, loop area explodes, and this is the #1 cause of EMI
  failures. Keep a return path under every fast trace.
- Pour ground (and power) zones; **refill zones before DRC and before
  export** — zones do not auto-refill.
- Differential pairs: route as one pair, constant width/spacing
  (solved from *your* stackup with an impedance calculator — there is
  no universal CAN/USB trace width), length-matched, ≥ 3W clearance to
  other signals, unbroken ground plane beneath, never across a plane
  split, minimise vias (symmetrical if unavoidable), stubs effectively
  zero on-board.
- Keep high-current paths short, wide, and on outer layers where
  possible. Route power as pours/planes, not thin traces.
- Switching regulator hot loop small (input cap → switch node →
  inductor → output cap); crystal close to its IC; sensitive sensor
  lines never under a switching regulator.

#### 4.4.1 Automatic corner fix (`fix_corners.py`)

The rule above is checked by `drc_check.py` (warning `corner-90`)
and fixed by `kit/fix_corners.py` — the skill does not leave 90°
corners to manual re-routing:

- **When to use it:** after routing, before the final DRC run. Run
  `drc_check.py` first; if it reports `corner-90` warnings, run
  `fix_corners.py` on the same `.kicad_pcb`, then run `drc_check.py`
  again — the `corner-90` warnings must be 0.
- **What it does:** each 90° corner is replaced by a 45° chamfer —
  both segments are shortened by the chamfer length and a diagonal
  segment is inserted. Chamfer length =
  `min(corner_fix.chamfer_mm, half of the shorter segment)` from
  `kit/config.json` (default 0.5 mm). Nets, widths and layers are
  preserved; 45° corners and arcs are left alone.
- **Safety first:** the input file is **never overwritten by default**
  — the fixed board goes to `<name>.fixed.kicad_pcb`. `--in-place`
  is allowed only with an automatic backup `<name>.bak` (a checkpoint
  before the mutation, skill rule G8). `--dry-run` prints what would
  change and writes nothing. If the fix is disabled in the config
  (`corner_fix.enabled = false`), the script reports the corners and
  changes nothing.
- **Human review:** the fixed board is a proposal, not a proof. The
  user reviews the result (visual/3D check) and re-runs `drc_check`
  before the board is used.
- **Regression check (v1.2.3):** after writing the fixed board,
  `fix_corners.py` runs `drc_check.py` on the input and on the output
  and compares the error counts. A chamfer can make the count go up
  (on the example board DRC went 24 → 25 errors: the chamfer splits
  one undersized trace into three segments, and the per-segment
  trace-width check counts each one). If the output has more errors
  than the input, the script prints a loud REGRESSION WARNING, keeps
  the `.bak` / untouched input, and exits 1 — it never silently
  claims an improvement.
- **Pad safety (v1.2.5):** a chamfer that would disconnect a pad or a via is reverted — the corner is kept as-is and reported in `corners_reverted`, never silently cut.
- **Limits:** only 90° → 45° chamfers. The script never moves
  components, vias or pads, never changes a net, a width or a layer,
  and never touches acute angles (< 90°) — those are reported as
  manual work, as are vertices where 3+ segments meet. A chamfer
  shorter than 0.05 mm is skipped (segment too short to chamfer).

### 4.5 DRC + pre-manufacturing check

- ERC, then DRC, then visual/3D review, then Gerber review. Zero
  unrouted nets, zero DRC errors.
- **ERC-clean ≠ schematic-complete and DRC-clean ≠ manufacturable.**
  Footprint, functional and fab-rule errors pass both. That is why the
  skill runs the 3 checks (§8) and the kit scripts (§11) on top.
- Gerber Viewer replay: all layers present, correct origin, outline
  on every layer.
- Design rules must match the fab (routed at 4 mil / 6 mil drills
  while the fab standard is 5 mil / 8 mil → surcharge, delay or
  rejection). Enter the fab's numbers into Board Setup *before*
  routing (§1, stage 4).

### 4.6 Power

- **Power tree first:** input → regulators → rails → loads, with a
  current for every branch (sum the loads + margin). Analyse before
  routing (§6.1). **Power nets are routed first, signals after.**
- **Decoupling hierarchy:** one **100 nF X7R MLCC per IC power pin**,
  as close as possible — **within 1–3 mm** (2 mm is the target; a cap
  10 mm away contributes little). Smallest value closest to the pin.
  Add **1–10 µF per IC / per rail** within 5–10 mm, and **10–100 µF
  bulk** at the regulator output / power entry. Rule of thumb for
  STM32: `n × 100 nF + 1 × 4.7 µF`, n = number of VDD pins. **Always
  follow the IC datasheet's power/layout section first** — it
  overrides generic rules.
- Loop area is the enemy: every 1 mm of trace ≈ 1 nH. Capacitor → IC
  power pin → ground return must be the shortest possible loop; a
  dedicated via from each capacitor pad straight to the plane (two
  vias per pad where space allows), vias immediately adjacent to the
  pad, never a long trace to a distant via. Do not cross plane splits
  with the decoupling loop.
- **Ground planes:** continuous, unbroken ground plane on the layer
  immediately adjacent to the component layer (L2 on a 4-layer board).
  Keep power and ground planes close together (thin prepreg) — they
  act as distributed capacitance. Via-stitch ground planes together
  (3–5 mm grid typical; 1–2 mm for RF).
- Trace widths by current: see §5 (IPC-2221 table). One 0.3 mm drill
  via carries roughly ~1 A — use 3 vias for 3 A, 4 for margin.

### 4.7 Carrier board for compute modules

- The compute module (for example Raspberry Pi Compute Module 5,
  CM5) is **not** connected with pogo pins. The module interface is
  **2× 100-pin DF40 connectors — 200 high-speed contacts** (PCIe,
  USB 3, HDMI). Pogo pins cannot carry that interface reliably.
  The skill teaches the correct DF40 connector + the module datasheet
  (power, power-up sequencing, high-speed routing).
- **Pogo pins are only for test/programming contacts** — never for
  the module interface.
- Read the module datasheet first: power rails and sequencing, the
  connector pinout, which pins are power / ground / high-speed /
  strapping. Verify every pin against the datasheet — never from
  memory, never from a pinout copied from a forum.
- Storage on the carrier: **SD / microSD slot** (SDIO, pull-ups, card
  detect, ESD) and **M.2 NVMe SSD via PCIe** (differential pair,
  impedance, short traces, 3.3 V power).
- Keep-outs around the module (SoM) per the module datasheet; the
  module sits flat — nothing tall under it. Test points under a
  removable module stay reachable with the module removed.

### 4.8 A board around ANY chip from its datasheet

- When a chip is not in any library, the model creates its own symbol
  + footprint **from the datasheet** — never from a recalled pinout.
- For every pin used: pin number → function, from the datasheet pin
  table (file + page cited). Package outline + recommended land
  pattern (pad size, pitch, thermal-pad size, drill) per IPC-7351.
- Absolute maximum ratings, supply range and sequencing, required
  external components and their exact values, mode/boot/strapping pin
  states, the layout/placement section of the datasheet.
- If the chip's datasheet cannot be found, the chip is not used.
  `UNVERIFIED` is written in the BOM/schematic notes instead.
- This is **not** custom silicon / ASIC design — the skill designs a
  board around an existing chip, it does not design the chip itself.

### 4.9 DIY computer from discrete 74xx logic

- Own CPU / RAM / GPU from 74xx logic (Ben Eater style CPU and RAM,
  Bitluni style GPU) — breadboard first, then a proper PCB.
- Breadboard → PCB transition: decoupling capacitor per chip, solid
  ground, short traces, one ground plane where possible. On a
  breadboard the wiring is the mess; on the PCB the wiring is the
  design — plan the bus first.
- Principles the skill covers: CPU from discrete logic (registers,
  ALU, control logic, clock), RAM from 74xx + latches (the breadboard
  RAM module pattern), GPU basics (framebuffer, VGA/HDMI timing —
  a home-made GPU is a big project; the skill covers the principles,
  not a finished GPU design).
- Honest limit: this is a learning computer built from logic chips.
  It is not a modern CPU and it is not fast — the value is
  understanding, not performance.

### 4.10 Custom motherboard

- The main board that joins a DIY computer's CPU / RAM / GPU /
  storage through a bus, with power and slots/connectors.
- Design: bus definition (which signals, which connector, pinout
  documented), power distribution (one rail per block, decoupling per
  block, current budget per slot), slots/connectors for the modules,
  mechanical fit (the modules must physically fit and be removable).
- Honest limit: this is a motherboard for your own modular computer,
  **not** an x86 motherboard. DDR routing and BGA are another league
  (§4.11) — the motherboard skill covers the bus, power and
  connectors; the hardest part (DDR) is its own capability.

### 4.11 RAM — DDR2 / DDR3, DIMM and SO-DIMM

- **DDR2 and DDR3 only for now.** DDR4 and higher come later as the
  skill grows — DDR4 is the hardest of the three.
- Form factors: **DIMM (desktop PC)** and **SO-DIMM (laptop)**.
  Connectors, voltages (DDR2 1.8 V, DDR3 1.5 V, DDR4 1.2 V), routing
  rules (impedance, trace lengths, termination).
- DDR is the hardest part of a motherboard. Length matching is a
  separate step after routing, not part of ordinary DRC: each DDR
  byte lane is tuned to its DQS, DQS/CK pairs first, the slower branch
  of a pair grows first, then address/command to CK. Report mismatch
  in **mm and ps**. Meanders as window accordions that account for
  the net's own copper. (Full DDR length-tuning method is on the v1.3
  roadmap — see README.md.)
- Honest limit: the skill teaches DDR2/DDR3 DIMM/SO-DIMM design and
  routing rules. A working DDR board still needs the memory
  controller's datasheet, the DIMM specification, and a human review
  before ordering.

### 4.12 From one user prompt: design the PCB + list the components

- The user says what the board must do in plain language ("a board
  with an ESP32, CAN and 5 V input"). The skill turns the prompt into
  a spec (§2), then designs from the spec.
- Steps: (1) restate the requirements back to the user as a spec and
  ask about anything ambiguous — **never guess a missing requirement**;
  (2) derive the components (MCU/module, transceiver, regulator,
  decoupling, termination, connectors) per §4.2; (3) output the
  component list (BOM) with MPNs and footprints; (4) design the PCB
  through the gated workflow (§1).
- The output of a prompt is: the spec, the BOM, and the board files
  (`.kicad_sch` / `.kicad_pcb`, Gerber + BOM on request). If the model
  does not know a value (for example a size), it asks — it never
  invents one.

### 4.13 Check a PCB the user gives you (audit) + fix the errors

- The user hands over an existing board (schematic, layout, or both).
  The skill audits it and fixes what is wrong.
- Audit = the review contract (§8): run every applicable check, cross
  -check the raw files against the datasheets, sort findings into
  **blocker / major / minor / false alarm**, and write a report with a
  verdict. What could not be checked is listed as a gap in the
  review — never silently skipped.
- Fixes: the model fixes what it can (wrong value, missing pull-up,
  trace too narrow, DRC error) and re-runs the checks. Structural
  fixes (different chip, different layer count) go to the human first.
- Before the first change: checkpoint the user's project (§0 rule 8).
  After a fix: verify with a readback or DRC — never claim "fixed"
  without proof.

---

## 5. Numbers — design-to values, not fab minimums

Set DRC to these unless a part forces finer geometry. Fab minimums are
limits, not targets. All values below are the skill's design-to values;
confirm safety-critical spacings against the applicable standard, not
against a blog table.

### 5.1 Defaults

| Rule | Skill value |
|---|---|
| Default signal trace / clearance | **0.20 mm trace, 0.20 mm clearance** (0.15 mm absolute floor for signals on a pro fab) |
| Copper-to-board-edge | ≥ 0.3 mm; components ≥ 1 mm from the edge |
| Silkscreen | Line ≥ 0.15 mm, text height ≥ 1 mm |
| Solder-mask bridge | ≥ 0.10 mm (1 oz) |
| Via (default) | 0.30 mm drill / 0.60 mm pad (annular ring 0.15 mm) |

### 5.2 Trace width vs current (IPC-2221, 1 oz = 35 µm, ΔT = 10 °C, external layer)

Formula: `I = k · ΔT^0.44 · A^0.725`, `A` = width × thickness in mil²,
`k = 0.048` external, `0.024` internal. From the formula, the same
current needs `A_int / A_ext = (0.048 / 0.024)^(1/0.725) = 2^1.38 ≈ 2.6`,
so an **internal trace needs ~2.6× the width** for the same current at
the same copper thickness. IPC-2152 supersedes IPC-2221 for
current capacity, but IPC-2221 remains the standard quick estimator.
Add 15–25% margin, use steady-state (not inrush) current.

| Current | External, 1 oz, ΔT 10 °C |
|---|---|
| 0.5 A | ~0.12 mm (use ≥ 0.20 mm anyway) |
| 1 A | **0.30 mm** |
| 2 A | **0.79 mm** |
| 3 A | **1.4 mm** |
| 5 A | **~2.8 mm** — consider 2 oz Cu, a pour/plane, or a busbar |
| 10 A | 7.2 mm — impractical in 1 oz, use heavier copper / plane |

Also: a 0.5 mm 1 oz track carries ~1.5 A, 1 mm ~2.4 A, 2 mm ~4 A at
ΔT 10 °C. One 0.3 mm drill via carries roughly ~1 A — use 3 vias for
3 A, 4 for margin. Use `kit/trace_width.py` to calculate and check.

### 5.3 Clearance vs voltage (IPC-2221 Table 6-1, external uncoated, bare board)

0–30 V: **0.10 mm**; 31–150 V: 0.60 mm; 151–300 V: **1.25 mm**;
301–500 V: **2.50 mm**; > 500 V: +0.005 mm/V. This is a functional
(not safety) table — mains / safety-certified products must follow
IEC 62368-1 / IEC 60664-1 creepage + clearance, which are usually
stricter. Voltage in the table is the *peak difference between the two
conductors either side of the gap*, not the highest rail on the board.

### 5.4 Differential pairs — CAN and USB

| | CAN (ISO 11898-2) | USB 2.0 |
|---|---|---|
| Differential impedance | **120 Ω ±10%** (tighter for CAN FD) | **90 Ω ±15%** (single-ended 45 Ω ±15%) |
| Termination | **120 Ω at the two physical end nodes only**; powered-off bus measures ~60 Ω CANH↔CANL. Split termination alternative: 2 × 60 Ω + ~4.7 nF midpoint to GND. **Make it switchable with a jumper** | Series termination per MCU datasheet (often 22–33 Ω, or built into the PHY); no 120 Ω bus termination |
| Placement order | Connector → TVS/ESD → (common-mode choke) → termination → transceiver → controller. Transceiver + connector in the same corner | Connector close to MCU/PHY; pair as short as possible, ideally no vias |
| Routing | Constant width/spacing (solved from *your* stackup), length-matched (intra-pair skew ≤ 2.54 mm), ≥ 3W clearance, unbroken ground plane beneath, never across a plane split, minimise vias, stubs effectively zero; daisy-chain only, never star | Length mismatch ≤ 3.81 mm per USB spec (aim ≤ 0.15 mm in practice on a short board); no vias in the pair if avoidable; 3× trace-width clearance; unbroken ground plane beneath; 45° bends; total length < 6″ |
| Protection | Reserve footprints for TVS/ESD diodes + common-mode choke even if not fitted; TVS as close to the connector as possible | ESD protection on D+/D− before the MCU, close to the connector |

### 5.5 Vias

- **Through-hole via (default):** 0.30 mm drill / 0.60 mm pad
  (annular ring 0.15 mm). Aspect ratio (board thickness ÷ drill)
  ≤ 10:1 absolute, ≤ 8:1 preferred (1.6 mm board → ≥ 0.16–0.20 mm
  drill). Annular ring ≥ 0.125–0.15 mm.
- **Blind / buried / microvias** (≤ 150 µm, laser-drilled) are
  HDI-only: expensive, sequential lamination, not for a first board.
- **Via-in-pad:** only resin-filled + capped/plated-over — otherwise
  solder wicks into the via. Never put an unfilled via in a pad for
  hand soldering.
- **Stitching vias:** tie ground planes together around ICs/decoupling
  clusters and the board perimeter; keep a ground via next to any
  signal via that changes layers.
- Avoid vias in differential pairs and under crystals; do not tent a
  via you need to probe.

---

## 6. Design methods from other skills (high-priority gaps, v1)

### 6.1 Power-net analysis

Power is not "a 5 V rail" — it is a tree with currents. Before routing:

1. Load the parts and classify the obvious ones: input connectors
   (J*, P*, TB*, CN*), diodes, transistors, ICs, regulators.
2. Classify unknown parts from the datasheet: what it is, its role,
   estimated current rating. No datasheet → `UNVERIFIED`, not used
   for sizing.
3. Trace power paths from the input through every regulator to the
   loads. For every branch: voltage, estimated current (sum of loads
   + margin), loss on the regulator `(V_IN − V_OUT) × I`.
4. Size: regulator by dissipation — up to ~1 W LDO, above ~1 W buck
   (§4.2). Trace width by current (§5.2).
5. Output: a power tree (input → regulators → rails → loads with
   currents), a list of power nets with recommended widths, and the
   order to route them — **power nets first, signals after**.
   A switching regulator is routed by hand (hot loop as small as
   possible), not by the autorouter.

### 6.2 Stackup + impedance

1. **Read the current stackup.** No stackup section, or all dielectrics
   with the same thickness and εr ≈ 4.5, means an untouched KiCad
   default — impedance calculations then do not match the fab. Say
   the verdict out loud: "stackup looks like the KiCad default" vs
   "stackup looks intentional".
2. **Collect requirements.** Layer count and each layer's role (which
   are GND/power planes, which are signal), impedance targets from
   §6.3 (USB 90 Ω, LVDS/Ethernet/HDMI 100 Ω, PCIe 85 Ω, 50 Ω
   single-ended for RF/clocks), fab (if the user names one — JLCPCB,
   PCBWay — its standard stackup is verified on the web, not invented;
   for example JLCPCB 4-layer: ~0.21 mm prepreg, ~1.0 mm core).
3. **Recommend and validate.** Example 4-layer: F.Cu signal /
   In1.Cu GND plane / In2.Cu power (or power + signals) / B.Cu
   signal. What matters is that every impedance layer has an
   **adjacent solid GND reference** — the second inner layer does not
   have to be a solid plane (both inners as solid planes is minority
   practice and takes routing layers from dense boards).
4. Validate with formulas (IPC-2141): compute the trace width from
   the target impedance on that layer. If the target is not reachable
   with manufacturable geometry, propose the nearest working option
   (thinner prepreg, another layer, relaxed target).
5. **The stackup is the fab's decision — do not change the board
   directly.** Give the user a `(stackup ...)` block for Board Setup
   → Physical Stackup. After a stackup change, impedance routing is
   calculated again — old widths are invalid.

### 6.3 Fast nets and differential pairs — identification

1. **Names.** Pairs by the P/N convention (`_P`/`_N`, `P`/`N`, `+`/`-`,
   `DP`/`DM`, `DPLUS`/`DMINUS`, DDR `_t`/`_c`). That is the baseline.
2. **Pin function from the datasheet.** For every IC that can have a
   fast interface (FPGA, PHY, SERDES, USB, ETH, HDMI, LVDS, MIPI,
   SATA, PCIe, DDR, transceiver, redriver): check `pinfunction` in
   KiCad, otherwise **verify the pinout in the datasheet on the web**
   and map the diff pins to pads and nets. Trace through series
   passives — a pair often gets its "real" name only after the AC
   coupling capacitors or series resistors.
3. **Confirmed vs suspected.** A pair is **confirmed** when both nets
   lead to a documented diff pin pair. By name or topology only =
   **suspected** — listed separately, the user confirms before routing.
   A pair found by name only is a possible false positive.
4. **Parameters by interface:** USB 2.0/3.x 90 Ω, LVDS 100 Ω, Ethernet
   100 Ω, HDMI/TMDS 100 Ω, PCIe 85 Ω (AC capacitors on TX), SATA
   100 Ω (AC capacitors), MIPI D-PHY 100 Ω, DDR (DQS, CK) 100 Ω
   typically (verify in the memory datasheet), CAN 120 Ω (slow,
   relaxed tolerances). Intra-pair matching from USB 2.0 HS up.
5. **Polarity:** every pair gets a verdict `polarity_swappable:
   yes | no | unknown`. `yes` = the endpoint can compensate a swap
   (FPGA/CPLD generic I/O, PCIe lanes, SerDes with polarity inversion,
   1000BASE-T MDI). `no` = polarity-critical (USB D+/D−, MIPI,
   TMDS/HDMI/DP, CAN, RS-485/422, DDR CK/DQS, fixed receivers,
   connectors to unknown hardware). `unknown` = treat as `no`. A swap
   is never done without a `yes` verdict.
6. **RF / antenna feeds:** single-ended 50 Ω or 100 Ω balanced. A
   pair is an RF feed only if it touches an antenna terminal — and is
   not a power/ground net.
7. **Fast single-ended nets:** classify by name patterns (CLK, MCLK,
   BCLK, JTAG, TCK, TDI, TDO, TMS, SWDIO, SWCLK…) and by datasheet
   (interface speed, IC pin count > 40 = probably a fast interface).
   For every fast net: speed, impedance, whether it needs length
   matching and with what.

### 6.4 Autorouting + repair after autorouting

- **When to autoroute:** ordinary signal nets only. Critical copper is
  protected from the autorouter: power, switching loops, RF, USB,
  clocks, time-critical routes are routed by hand first (as
  pre-placed segments/vias) and locked.
- **Flow:** set net classes, export DSN, autoroute (Freerouting —
  **with automatic retries**, it is stochastic), import the result,
  add GND pours + stitching, clean the silkscreen, run DRC — repeat
  until **0 violations / 0 unconnected**. Only then the fab pack.
- **After autorouting:** check that protected copper survived (the
  import must not overwrite it), add zones, check BGA/connector
  fan-outs (rip-up can remove unlocked fan-out vias — verify every
  BGA/connector escape after every rip-up).
- **Repair after autorouting:** DRC loop in this order: shorts,
  clearance, unconnected, crossings, forbidden items, diff-pair and
  dangling problems. For dense single connections use local precise
  routing (A*), via moves, restoring lost fan-outs. If source and
  target sit in disconnected parts of the legality grid, fix the
  placement, not the router parameters.
- **Rule: DRC 0/0 after autorouting does not mean done** — the DFM
  gate (§7.2) and the visual check (§8) follow.

---

## 7. Manufacturing — one section, most common → least common

The designer picks **one** method in the requirements phase (§1). The
skill then loads only that method's rule set into DRC + the pre-order
checklist. **Default for a beginner: §7.1 (professional rigid fab).**
Home methods (§7.3–§7.5) are for same-day learning prototypes only.

### 7.1 Professional rigid FR-4 fab — JLCPCB / PCBWay / OSH Park / Aisler

**Can:** 1–32 layers rigid, plated through-holes/vias, solder mask,
silkscreen, ENIG/HASL/OSP finishes, controlled impedance (±10%
standard, 4+ layers only), electrical testing, assembly (PCBA).
**Cannot:** anything the capability sheet forbids — check it live
before routing; capabilities change.

**JLCPCB rigid capabilities (verify live before ordering):** layers
1–32; controlled impedance on 4/6/8/…/32 layers, ±10%; FR-4 Grade A;
thickness 0.4–4.5 mm (1.6 mm standard); finishes HASL (leaded /
lead-free), ENIG, OSP; solder mask colours green/purple/red/yellow/
blue/white/black; min dimension 6×6 mm (config `fab_limits.min_board_mm`).

**Trace/space & drills (JLCPCB, 1 oz):** 1–2L **0.10/0.10 mm** in the
current capability capture, commonly quoted as 0.127 mm (5 mil) in
older tables — **design to ≥ 0.15 mm and treat 0.10 mm as the floor**;
multilayer 0.09/0.09 mm. Min mechanical drill 0.15 mm (multilayer) /
0.20 mm (some tables); min via pad 0.45 mm (4L+) / 0.60 mm (2L);
annular ring recommended ≥ 0.25 mm (2L, 1 oz); copper-to-edge
≥ 0.3 mm; hole-to-track 0.35 mm recommended / 0.28 mm min; average
hole plating 18 µm; silkscreen line ≥ 0.15 mm, text ≥ 1 mm.

**PCBA (JLCPCB):** Economic PCBA 2–6L, min package 0402, min IC pitch
0.4 mm. Standard PCBA 1–32L, **min board 70×70 mm**, min package
01005, min IC pitch 0.35 mm, min BGA 0.3 mm. Parts are Basic vs
Extended — check stock before locking the BOM.

**Design rules that follow:** use §5 defaults; set DRC to the fab's
numbers *before* routing; order impedance control only on 4+ layers;
run the fab's free online DFM/impedance checker before ordering. The
skill must not quote a price — it must say "get the live quote from
the fab's viewer after uploading Gerbers".

**CPL rotations (JLCPCB conventions differ from KiCad — fix in the
CPL before upload):** SOT-23 / SOT-23-5 / SOT-23-6 +180°, SOT-223
+180°, SOIC-8/16 +90° or +270°, QFN +90°, SMA/SMB/SMC diodes +180°,
USB-C connectors per datasheet. After the first assembled order, note
the corrections needed and apply them to later exports.

**Import the fab's DRU file** if it has one (KiCad Board Editor →
Board Setup → Design Rules → Import Settings) **before** DRC — "clean
DRC" means manufacturable only against the fab's rules, not against
KiCad's defaults.

**Order workflow:** prototype (bare board + stencil) vs production
(assembled). BOM translation KiCad/Altium CSV → JLCPCB BOM CSV
(Comment, Designator, Footprint, LCSC Part #, MPN, Manufacturer,
Quantity, Notes); DNP rows out; R1–R4 expanded. CPL: verify every
rotation in the fab's interactive preview; **never change the CPL
anchor footprint** — a part body legitimately overhangs its pads
(module antenna, connector shell) and a manual "fix" moves
pick-and-place off the pads.

### 7.2 DFM gates — DRC 0/0 ≠ manufacturable

- **DRC 0/0 does not mean manufacturable.** KiCad DRC does not check
  drill-to-drill spacing, via annular ring or drilled-hole-to-pad
  clearance. The DFM check covers that and blocks the fab export — a
  pack that looks done must not carry a known defect.
- The DFM gate runs **after** DRC and **before** the fab gate: JLCPCB
  DFM check (silk, slots, annular, layer count, THT↔SMD), silkscreen
  check, THT/SMD check, track and bend check. Every real flag is
  fixed.
- The skill keeps a catalogue of the fab's **false positives** — what
  is a real defect and what is a false positive that should not be
  chased.
- **Rule: the fab pack is not generated until the DFM gate passes.**
  A BOM/CPL change does not need a re-route — regenerating and
  re-uploading takes seconds.

### 7.3 Home photoresist + UV exposure + etching

**Can:** finer home features than toner transfer; the best home method
for SMD / fine-pitch ICs; single- or double-sided (with a double-sided
UV unit for alignment). **Cannot:** plated through-holes, solder mask,
silkscreen, controlled impedance, multilayer, fine-pitch BGA/QFN below
~0.5 mm pitch reliably; no electrical test; bare copper tarnishes.

**Rules:** design **≥ 0.25 mm trace, ≥ 0.25 mm clearance** (reliable;
one lab guide says ≥ 0.30 mm for both for easy etching); TH pads
≥ 1.8 mm; copper text ≥ 1.5 mm; drills ≥ 0.8 mm. Best-case claims of
6–8 mil (0.15–0.20 mm) need a calibrated process — the skill default
stays at 0.25 mm. Print the artwork on **transparent film with a laser
printer** (inkjet does not work), tracks as dark as possible. No vias
— same wire/rivet rule as §7.4. Keep fine features away from board
edges; use a ground pour to reduce the copper area to etch.

### 7.4 Home thermal transfer (toner transfer) + chemical etching

**File format is not prescribed: PNG is not required.** Any format
that prints 1:1 black-and-white at full density is acceptable — KiCad
Plot to PDF, `kicad-cli pcb export pdf/png --mirror --black-and-white`,
Gerber-to-PDF, or a bitmap. What matters is scale, mirroring and toner
density.

**Process in brief:** print the copper artwork (laser printer, glossy
paper) → iron/laminate the toner face-down onto cleaned copper-clad
board → soak off the paper → toner remains as etch resist → etch in
ferric chloride / sodium persulfate / HCl+H₂O₂ → remove toner with
acetone → drill → tin the copper (it tarnishes) → solder.

**Single-sided is the intended use.** Components on top, all copper on
the bottom; route everything on one layer, using wire jumpers (0 Ω
links / insulated wire on the component side) where a trace cannot
cross. **Double-sided is possible but hard — flag it "advanced,
expect a failed first attempt".** The two sides must be aligned by
hand: matching registration marks on both sides, enlarged via pads on
one side, drill a few via holes first as alignment pins, transfer +
etch one side at a time.

**Minimum trace width & clearance that survive etching (skill rule —
the conservative one):**

| | Design to this | Absolute floor (expert, calibrated process) |
|---|---|---|
| Trace width | **≥ 0.5 mm**; power traces 1.5–2 mm | 0.4 mm reliable; 0.3 mm is about the limit and breaks easily |
| Clearance | **≥ 0.5 mm, prefer 1.0 mm** for pours and anything > ~30 V | 0.4 mm; < 0.3 mm separation is "asking for trouble" |
| Through-hole pads | **≥ 2.0 mm diameter**, oval where possible | 1.5× drill diameter minimum |
| Copper text | ≥ 2.5 mm high | — |
| Drills | 0.8 mm for most leads/ICs, 1.0 mm headers/diodes, 1.2–1.5 mm terminals | Centre-dot in the artwork ~0.42 mm to guide the drill bit |

Why the margin: etchant **undercuts** the resist sideways while it
etches down — over-etching thins traces from the edges. Under-etching
leaves copper between tracks (shorts).

**Mirrored printing — the #1 home-fab mistake:** the print is pressed
**face-down**, so the transfer reverses it. In KiCad: print the **top
copper (F.Cu) mirrored** and the **bottom copper (B.Cu) unmirrored**.
Do not memorise a checkbox; **verify with the text test:** put a short
word on the copper layer; on the *paper* it must read **backwards**;
on the finished board (viewed from the copper side) it must read
**correctly**. Print at **100% / Actual size, never "Fit to page"** —
measure a known dimension on the print (a 14-pin DIP spans 15.24 mm
between outer pins). **Laser printer only** — inkjet ink does not
resist etchant. Maximum toner density / darkest, toner-saving OFF.
Iron on hottest dry setting (no steam), ~190–200 °C, 3–5 min; a
**laminator run 6–10 times is more even** than an iron. Soak in warm
water ≥ 10 min; touch up gaps with a permanent marker (let it dry
fully).

**Etching:** ferric chloride 35–45 °C, 10–20 min; sodium persulfate
45–55 °C, 15–30 min; HCl+H₂O₂ room temperature, 2–5 min (fast,
corrosive fumes — outdoors only). Agitate the tray, warm by standing
the tray in hot water (never on a hob), plastic/glass trays only.
**Safety (the skill must state it):** gloves + splash goggles,
ventilation, never mix etchants, never add bleach, never pour used
etchant down the drain (dissolved copper is toxic to aquatic life) —
sealed, labelled, to hazardous-waste collection. Follow the etchant's
SDS over any guide.

**Vias & holes — the hard limit:** **there are no plated
through-holes at home.** Every layer change is manual: drill the hole,
pass a solid wire (e.g. 30 AWG wire-wrap wire) through, kink it so it
cannot fall out, and solder **both sides**. Alternative: copper **PCB
rivets** (0.8 mm OD / 0.6 mm ID, fitting a 0.8 mm drill, with a rivet
tool). Design vias **large** (≥ 0.8 mm drill, ≥ 2 mm pad), **minimise
the via count**, prefer changing layers at a through-hole component
lead soldered on both sides anyway. No via-in-pad, no blind/buried/
microvias, no tenting to hide a via.

**What must NOT be designed for this method:** fine-pitch parts —
**do not design below 0.65 mm pitch**, prefer ≥ 1.27 mm / DIP / SOIC;
**0.4/0.45 mm pitch, BGA, and 0402/0201 passives are out**. SMD pads:
lengthen by 0.1–0.2 mm so an iron tip can reach them; 0805 is a
comfortable hand-solder size, 0603 is the practical floor. **No solder
mask, no silkscreen. No controlled impedance** (no USB 2.0 high-speed,
no CAN-FD, no RF, no 120 Ω/90 Ω pair targets). No multilayer (> 2
layers), no blind/buried vias, no castellated edges, no ENIG/HASL
finish, no electrical testing, no traces/pads within ~5 mm of the
board edge where transfer is worst.

**Decision gate:** if the design needs any item in this list, the
skill must stop and say "order from a professional fab (§7.1)
instead" — do not try to shrink the design to fit the home process.

### 7.5 CNC milling (isolation routing)

**Can:** same-day, chemical-free, drills holes and cuts the outline in
the same job; good for simple 1–2 layer through-hole boards.
**Cannot:** plated holes, solder mask, silkscreen, fine pitch,
multilayer; surface finish rougher than etched/fab boards.

**Rules:** design **≥ 0.4 mm trace and clearance, recommended
≥ 0.5 mm**; clearance **≥ 2× the cutter diameter** around pads/traces
(a 0.25 mm / 10 mil cutter needs ≥ 0.5 mm gaps); avoid acute angles
(45°/90° only); V-bit groove widens with cut depth (cut 0.05–0.08 mm
for 1 oz Cu) and board flatness/bow dominates accuracy —
auto-levelling (probe grid every 5–10 mm) is effectively mandatory for
fine work; FR1 mills cleaner than FR-4. Vias: drill + wire/rivet as in
§7.4 (no plating). Fine-pitch QFN / 0.4 mm BGA are effectively out of
reach on a hobby mill. Dust is hazardous (FR-4 glass fibre) —
extraction + mask; never blow it away.

### 7.6 Flex, rigid-flex, metal-core, HDI, RF, ink, 3D print, ceramic, LDS

These methods are covered briefly — each is a specialist area. The
skill's rule for all of them: **confirm against the chosen fab's live
capability page; do not hard-code a vendor's extreme limit.**

| Method | Can | Cannot / rules that follow |
|---|---|---|
| **Flex (FPC)** — polyimide | Bend/fold/twist, ultra-thin; 1–4 layers | Rigid mounting needs a stiffener; bend radius (static) 6× thickness (1L), 12× (2L), 24× (4L); traces perpendicular to the bend axis; no vias in dynamic flex zones; coverlay (not solder mask) |
| **Rigid-flex** | Rigid FR-4 sections + flex sections in one board | Not cheap/fast/beginner-friendly; JLCPCB does not offer it — specialist fab; flex layers continuous through zones; no PTH in the transition zone |
| **Metal-core (MCPCB)** — aluminium | Built-in heatsink for high-power LEDs / power stages | Single-sided standard; dielectric is the bottleneck (k = 1–3 W/m·K); copper-to-edge ≥ 0.5 mm, ≥ 1.0 mm along V-score lines; V-score is the separation method — do not rout-cut aluminium |
| **HDI** | Fine-pitch BGA escape (0.4–0.5 mm pitch), phone-class density | Not a beginner board — **escalate to an experienced designer / fab DFM review**. Microvia < 150 µm, trace/space ≤ 100 µm, sequential lamination |
| **RF / microwave** — Rogers / PTFE | Stable impedance and low loss above ~1 GHz | Cannot use FR-4 rules; hybrid stackup is the norm (Rogers for RF, FR-4 for digital); mitered/arc bends, never 90°; via-fence spacing λ/20 |
| **Conductive ink** — Voltera V-One | Same-day double-sided prototypes, no chemicals | Not production / high current / high frequency / fine pitch. Min trace/space 0.20 mm, recommended ≥ 0.40–0.50 mm; min IC pitch 0.65 mm, smallest passives 0603; ink resistivity is far higher than copper — widen every power trace, do not use IPC-2221 copper ampacity for ink |
| **3D-printed circuits** | Circuits conformal to a 3D shape, embedded components | Prototype only — not volume, high current, high frequency or high density. Conductivity 10–60% of copper; traces 0.2–0.5 mm; impedance control needs simulation, not a copied width |
| **Ceramic** — alumina, AlN, LTCC/HTCC | Extreme temperature, hermetic, CTE matched to silicon | Brittle, expensive; LTCC fired shrinkage 12–16% in X-Y (the fab compensates — never scale the artwork yourself); round all corners (R > 0.3 mm) |
| **LDS / MID** | The plastic housing *is* the circuit (antennas, sensors on curved surfaces) | Single-sided 3D surface only, no multilayer, typical current < ~1 A. **Use only when the circuit must be conformal to a housing** — otherwise use flex or a rigid PCB |

**Manufacturing decision table (for the §1 gate):**

| Need | Choose |
|---|---|
| Default / anything with USB, CAN-FD, dense SMD, assembly | §7.1 Professional rigid fab |
| Same-day simple through-hole prototype, learning | §7.4 toner transfer (single-sided, ≥ 0.5 mm) or §7.3 photoresist or §7.5 CNC milling |
| Bend/fold, wearable, camera/display tail | §7.6 Flex (rigid-flex if components need rigid islands — specialist fab) |
| High-power LED / power stage, heat is the problem | §7.6 Metal-core |
| 0.4–0.5 mm BGA, phone-class density | §7.6 HDI (escalate) |
| > 1 GHz RF, antenna, radar | §7.6 Rogers/PTFE (specialist) |
| > 300 °C, hermetic, CTE-matched power/RF module | §7.6 Ceramic |
| Circuit on a curved housing | §7.6 LDS |
| Same-day, no chemicals, low-current SMD prototype | §7.6 Voltera (if available) |
| Conformal 3D prototype, embedded parts | §7.6 3D-printed (prototype only) |

---

## 8. The 3 checks of a finished PCB + the review contract

Every finished board — whether the skill designed it or the user handed
it over (§4.13) — goes through **3 review passes**. Each pass finds as
many errors as possible and fixes them. A board is finished only after
all three pass.

### Check 1 — Schematic & wiring

- Every pin on exactly one net (a pin on two nets is a short).
- No swapped signals: CANH↔CANL, USB D+↔D−, UART TX↔RX (TX goes to
  RX), SPI MOSI/MISO, I²C SDA/SCL.
- Termination present and in the right place: CAN 120 Ω at the two
  physical ends only (powered-off bus reads ~60 Ω, not 120 Ω, 0 Ω or
  open).
- Decoupling on every IC power pin; bulk cap present; crystal load
  caps present; reset/boot pull resistors present; no floating inputs.
- Footprint / pin-1 / connector orientation verified against the
  datasheet drawing (not the library name).
- Diode / electrolytic capacitor polarity correct; reverse-polarity
  protection present and not inverted.
- Regulator: right topology for the dissipation, feedback resistors
  correct, enable pin not floating, input/output caps right type/value.
- ERC clean, every warning justified in writing.

### Check 2 — Layout & DRC

- Zero unrouted nets / ratsnest lines remaining (even a stub acts as
  an antenna).
- DRC: 0 errors — and DRC rules match the fab (§7.1). DRC errors are
  never ignored or waived by the model.
- Ground plane unbroken under every fast trace; no signal crossing a
  plane split.
- Decoupling capacitor ≤ 3 mm from its IC, ground return short.
- Differential pairs: constant spacing, length-matched, no vias in
  the pair, no stub to the termination resistor.
- Switching regulator hot loop small; crystal close to its IC, not
  under a noisy trace; sensitive sensor line not under the switching
  regulator.
- 45° corners only; traces wide enough for their current (§5.2);
  power as pours/planes.
- Test points on every rail + GND; debug header (SWD/JTAG) kept on
  the production board; a way to isolate each rail (0 Ω jumpers in
  series with each supply).
- Mechanical: board fits the enclosure; mounting holes in the right
  place with clearance for screw heads; connector does not overhang
  the board edge; components ≥ 1 mm from the edge; no keep-out
  violations around mounting holes.
- Silkscreen not over pads; fiducials present for assembly.
- Run `kit/drc_check.py` on the `.kicad_pcb` (independent second
  check) and `kit/trace_width.py --check-csv` on the power nets.

### Check 3 — Pre-manufacturing

- DFM gate (§7.2) passes: drill-to-drill, annular ring, hole-to-pad
  clearance, silkscreen, slots.
- BOM complete: every part has an MPN, a footprint and a value.
  `kit/bom_check.py`: 0 errors. Stock checked at the chosen
  distributor (parts can go from 16 → 3 in stock between stages).
- CPL rotations verified in the fab's interactive preview (§7.1).
- Gerber replay in GerbView: all layers present, correct origin,
  outline on every layer. Drill file matches the Gerbers.
- Stackup / thickness / finish / quantity confirmed against the fab's
  live capability page.
- The release report's first line, if any gate is open, must read:
  **"Do not order from these files until the checklist below is
  worked through."**

### Review contract

When the user says "check the board" / "review" / "is it ready for
manufacturing", a review has a contract:

1. Read the whole skill workflow, not just the part about commands.
2. Run **every** applicable checker for the files in the project —
   and write down which ran and which did not.
3. Before the word "verified", cross-check: raw file + datasheet.
   Without a datasheet it is only internal consistency (the board
   agrees with itself, not that it is correct).
4. Sort probable false positives *before* they become blockers.
5. What could not be done is a **gap in the review** in the report,
   not a silent omission.

Findings are sorted: **blocker / major / minor / false alarm**. The
report always has: a verdict, a table of blockers, what the
verification is based on, false positives, and skipped analyses.
Without a verdict it is not a review. A waiver is human-only.

### Visual check (part of Check 2 and Check 3)

Every iteration of a board is checked **by eye, not only by DRC**:
render the board (`kicad-cli pcb render`, top AND bottom, high
quality) + STEP export with real 3D models. Audit the render:
connectors on board edges with openings out; antennas with no copper
AND no parts; rotations aligned with the natural flow of traces and
pick-and-place; decoupling capacitors at their IC's power pins;
user elements (LEDs, buttons) on reachable edges. Compare with **real
photos** of commercial equivalents (manufacturer documentation,
review photos). **Copy proven blocks from real designs** (open-source
dev boards, vendor evaluation modules) and adapt — a layout that was
already manufactured beats a new idea. The visual check blocks the
release.

---

## 9. EasyEDA path

The user's main tool is EasyEDA, and a model **cannot click thin wires
in the editor**. The solution is not clicking — it is the API.

**EasyEDA Pro API (official skill):** ~120 classes, 62 enums, 70
interfaces + a WebSocket bridge server that executes code in a running
EasyEDA Pro client. Flow: check the bridge is running (handshake
`service: "easyeda-bridge"`); if not, start it **in the background**
(never in the foreground — the AI would wait for the server to end);
connect, select the EDA window, verify the connection, then execute
code.

**EasyEDA agent (CLI/daemon/MCP):** typed commands for schematic,
layout, routing, DRC, diff-pair / equal-length reports. Operations:
navigation, board (schematic↔PCB binding), read/check, routing
(traces + vias), copper pour, schematic→PCB sync + component CRUD,
layout edit (deterministic — EasyEDA has no align/grid API), board
outline.

**Guardrails:** confirm before `delete`, `import_changes` and bulk
`arrange` / auto-layout; confirm before saving unless the user said
"save"; after a mutation do not claim done until a readback/DRC
verifies it; no undo — before/after goes into the audit log.

**Auto-layout by conventions:** placement priority P0–P7 (mechanics
first, safety/isolation, EMI hot loop + critical decoupling, datasheet
layout priorities, RF, order/silkscreen last), stackup-conditioned
decoupling, thermal / signal-integrity / DFM rules.

**Rule for this skill: layout in EasyEDA is done exclusively through
the API/CLI, never by clicking in the browser.** If the API is not
available (for example only the web EasyEDA without Pro), the path is:
design in KiCad → export/import into EasyEDA (easyeda2kicad bridge),
or the user finishes it with the mouse in the editor — and the skill
says that plainly instead of promising to click it done.

**EasyEDA's distinctive value** is the LCSC library + one-click
JLCPCB ordering; its lock-in is the same thing (cloud account,
JLCPCB-centric BOM matching — always trust the JLCPCB parts page over
the EasyEDA listing, and check minimum order quantities, which only
appear late in the JLCPCB flow). Gerbers are standard RS-274X, so any
fab can build them — EasyEDA is not JLCPCB-only.

> Realistic scope for v1.0: this skill documents the EasyEDA API path,
> the bridge setup, the guardrails and the fallback. Full automated
> EasyEDA layout (a running bridge + the complete command set) is on
> the v1.3 roadmap (see README.md) — v1.0 does not pretend the bridge
> is already wired up.

---

## 10. Anti-patterns — beginner mistakes & a real failed board

Tick every box; any "no" blocks the order.

**Schematic / netlist**
- [ ] Pin on two nets (a short — the most common AI-generated failure;
  e.g. a pull-up resistor pin listed on both `+3V3` and `EN`).
- [ ] Swapped signals: CANH↔CANL, USB D+↔D−, UART TX↔RX, SPI
  MOSI/MISO, I²C SDA/SCL.
- [ ] Missing termination: CAN 120 Ω absent / fitted at a middle node
  / fitted twice on a tapped bus.
- [ ] Missing decoupling, missing bulk cap, missing crystal load caps,
  missing reset/boot pull resistors, floating inputs.
- [ ] Wrong footprint / pin-1 rotated 90° / connector mirrored / QFN
  thermal pad wrong size / drill 0.1 mm too small for the lead.
  (Leading cause of a dead first board.)
- [ ] Diode / electrolytic capacitor reversed; reverse-polarity
  protection missing or inverted.
- [ ] Regulator: wrong topology for the dissipation, feedback resistors
  wrong, enable pin floating, input/output caps wrong type/value.
- [ ] Power pins with no driver (ERC), outputs tied together,
  unconnected power nets.

**Layout**
- [ ] Unrouted nets / ratsnest lines remaining.
- [ ] DRC errors ignored or waived by the model (never allowed).
- [ ] Design rules do not match the fab.
- [ ] Ground plane cut/split under a fast trace; signal crossing a
  plane split.
- [ ] Decoupling capacitor far from its IC (> 3 mm), or its ground
  return routed a long way round.
- [ ] Differential pair: spacing changed along the route, length
  mismatch, routed over a split, vias in the pair, stub to the
  termination resistor.
- [ ] Switching regulator hot loop large; crystal far from its IC /
  under a noisy trace; sensor line under the switching regulator.
- [ ] 90° / acute trace corners; traces too thin for their current;
  power routed as thin traces instead of pours/planes.
- [ ] No test points, no debug header, no way to isolate a rail, no
  probe access — the board arrives dead and cannot be debugged without
  scraping solder mask.
- [ ] Mechanical: board does not fit the enclosure; mounting holes in
  the wrong place / no clearance for screw heads; connector overhangs
  the board edge; components too close to the edge.
- [ ] Silkscreen over pads; courtyard/silkscreen overlaps; fiducials
  missing for assembly.
- [ ] (CAN-specific) Termination resistor on the wrong side of the
  common-mode choke; TVS far from the connector with a long ground
  return; transceiver far from the connector so CANH/CANL cross the
  whole board.

**Before first power-up (bring-up checklist)**
- [ ] Visual inspection under magnification: solder bridges
  (fine-pitch ICs), tombstoned passives, reversed polarity marks,
  missing parts.
- [ ] Continuity: power rails not shorted to ground; a healthy 3.3 V
  rail reads several hundred ohms to ground (near 0 Ω is a short).
- [ ] Bench supply current-limited to ~110–120% of expected quiescent
  draw before first power-on.
- [ ] Power rails brought up one at a time; check each rail voltage
  before connecting loads.

### A real failed board — IronMan-Base-Module (anti-pattern source)

This skill was built from a real board that went wrong. Its mistakes
are the worked examples below — do not repeat them:

- **CAN shorted:** CANH and CANL were swapped, and vertical copper
  runs joined connector pins 2–3–4. The schematic looked connected;
  the bus was a short. Lesson: verify CANH/CANL pin by pin against
  the transceiver datasheet, and check the connector pins in the
  layout, not only in the schematic.
- **Schematic unwired (0/123 connections):** parts were placed, values
  were set, but no wires were drawn. The board had no circuit. Lesson:
  the spec lint (§2) and Check 1 (§8) catch an unwired schematic
  before any layout work starts.
- **PCB not routed, DRC 19 errors:** the board was never routed and
  never updated from the schematic (17 parts on the PCB vs 27 in the
  schematic). Lesson: update the PCB from the schematic after every
  schematic edit, and never call a board "done" with open DRC errors.
- **JSON exports contained the shorted CAN:** exports were made from
  the broken design. Lesson: never export / import / order from files
  that have not passed the 3 checks.

---

## 11. Outputs — KiCad 10+

The skill's outputs are in the form most compatible with **KiCad 10+**:

| Output | File | Command |
|---|---|---|
| Schematic | `.kicad_sch` | `kicad-cli sch export pdf` for a human-readable copy |
| Board | `.kicad_pcb` | — |
| ERC report | `erc.rpt` | `kicad-cli sch erc board.kicad_sch -o erc.rpt` |
| DRC report | `drc.rpt` | `kicad-cli pcb drc board.kicad_pcb -o drc.rpt` |
| Gerbers | `gerbers/` | `kicad-cli pcb export gerbers … -o gerbers/` |
| Drill | Excellon | `kicad-cli pcb export drill …` |
| BOM | `bom.csv` | `kicad-cli sch export bom … -o bom.csv` |
| Pick-and-place | `pos.csv` | `kicad-cli pcb export pos … -o pos.csv` |
| STEP 3D | `.step` | `kicad-cli pcb export step …` |
| Netlist | `.net` | `kicad-cli sch export netlist …` |
| Render | `.png` | `kicad-cli pcb render …` (top AND bottom, high quality) |

The schematic and board share one netlist (live, bidirectional sync
via F8 — do not redraw the circuit in the PCB Editor; the schematic
is the electrical authority). ERC checks the schematic, DRC checks
board geometry. **Refill all zones before DRC and before export** —
zones do not auto-refill. Then replay the Gerbers in GerbView.

The fab pack for one board: Gerbers + drill + BOM + CPL (+ STEP/PDF
schematic optionally), zipped, with the version in the file name
(e.g. `my-board-v1.0-fab.zip`). A Gerber zip is archived per version,
never overwritten.

---

## 12. Kit — the scripts

`kit/` holds small, independent Python checkers (standard library
only — they run on any machine with Python 3.8+, including the user's
Windows PC, with no installation). See `kit/README.md` for full usage.

| Script | Checks |
|---|---|
| `drc_check.py` | Unrouted nets, trace width, via drill/pad, annular ring, 90° corners, copper-to-edge, clearance and shorts (different nets, same layer; zones not covered, `kicad-cli pcb drc` still required) — on a raw `.kicad_pcb` |
| `bom_check.py` | Missing MPN / footprint / value, duplicate reference, quantity mismatch, missing LCSC — on a BOM CSV |
| `trace_width.py` | IPC-2221 trace width for a current (single value, table, or a CSV of nets) |
| `rules_check.py` | Spec-first lint (§2): pin on two nets, unknown reference, pin not in the part's pin list (`unknown-pin`), unconnected power pin, power pin in no_connect, forbidden 3-layer board / unsupported layer count, missing decoupling / bulk cap, I2C without pull-up, single-pin net. Bad spec data (wrong types, NaN, strings where lists belong) is reported as a clean error, never a traceback |
| `fix_corners.py` | **Fixer (not a checker):** chamfers 90° corners to 45° in a `.kicad_pcb` — writes `<name>.fixed.kicad_pcb` by default, `--in-place` only with a `.bak` backup, `--dry-run` changes nothing; acute angles are reported, never fixed. Post-fix regression check (v1.2.3): DRC errors before vs after — warns loudly and exits 1 if the fix made the board worse |
| `run_all.py` | Runs all four checks on the example files — or on your own board with `--pcb` / `--bom` / `--nets` / `--spec` — and prints one summary |

**Rules are user-editable:** all thresholds live in `kit/config.json`
— edit the numbers there and every script picks them up. The values
are the skill's design-to values (stricter than fab minimums).

**Every script prints an audit log at the end:** script name and
version, start time, input file with SHA-256, config file with
SHA-256, checks that ran, checks skipped and why, finding counts, and
the final result. **The log is the proof the check ran.** Since v1.2.3
the audit log goes to **stderr**, never stdout — with `--json`, stdout
is parseable JSON only.

**Exit codes (all scripts):** `0` = pass (warnings allowed),
`1` = fail (at least one error — including a malformed spec, and a
`fix_corners.py` regression), `2` = setup missing (file not found,
unparseable file, bad config).

---

## 13. What v1.2 does NOT cover

v1.2 covers the 13 capabilities (§4), the high-priority methods
(§6), the automatic corner fix (§4.4.1) and the reference boards in
`prototypes/` (§1). These are on the **v1.3 roadmap** (see README.md)
— the skill does not pretend to do them yet:

- EMC pre-compliance check (44 rules, 18 categories)
- BOM management + sourcing (stock checks, LCSC/DigiKey/Mouser,
  substitutes, 5 boards + 2 spares per part)
- Structured datasheet extraction (typed facts, cache, confidence
  low/medium/high, stop rule)
- Placement recipes and priorities (P0–P7)
- Bring-up + test points (fiducials, SWD/JTAG, bring-up plan) — the
  bring-up checklist in §10 is the v1.0 minimum
- Full EasyEDA API automation (running bridge + complete command set)
- Library of verified sub-circuits (LDO, USB-C, ESP32 core, …)
- DDR length tuning (method: DQS/CK first, mm and ps)
- 4-layer plane escalation
- SPICE simulation before manufacturing
- ECO / versioning (changes on a routed board, netlist diffs)
- Audit log / run cache across runs
- Design documentation (design brief, PDF document)

---

*Made by PTS6845 — https://battingchart300.github.io*

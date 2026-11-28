# Changelog — ai-pcb-design-skill

## v1.2.7 — 2026-11-27

4-skill audit fixes in `rules_check.py` — four inputs that used to PASS now FAIL:

- `power_pins: 42` (a bare int, not a list) → `power_pins-not-a-list`.
- A net pin given as an object instead of a string label → `net-pin-not-a-string`.
- `no_connect` with a nonexistent pin (e.g. `Z99.1`) → `unknown-reference`.
- A footprint of `UNVERIFIED` → `part-missing-footprint` (same rule as the BOM MPN check, case-insensitive).

New regression fixtures in `kit/examples/` and a pytest suite in `tests/` (9 tests). Example results unchanged.

## v1.2.6 — 2026-11-25

Wave-2 Codex audit fixes: `bom_check.py` no longer skips the MPN check when the BOM has no MPN column, and `UNVERIFIED` in the MPN or Footprint column counts as missing; `rules_check.py` strict completeness (check 13); `trace_width.py` rejects inf/NaN/zero/negative numeric inputs and a header-only CSV now FAILs; credit line "Made by PTS6845" added.

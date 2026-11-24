#!/usr/bin/env python3
"""trace_width.py — IPC-2221 trace-width calculator and checker.

The IPC-2221 formula (1 oz = 35 um = 1.37 mil copper):

    I = k * dT^0.44 * A^0.725        A = width * thickness  (in mil^2)
    k = 0.048 for external layers, 0.024 for internal layers
    (an internal trace needs ~2.6x the width for the same current:
    (0.048 / 0.024)^(1/0.725) = 2^1.38 = 2.60 — see SKILL.md §5.2)

Solved for width:  A = (I / (k * dT^0.44)) ^ (1 / 0.725)

IPC-2221 is a quick estimator (IPC-2152 supersedes it for current
capacity). The numbers below include no safety margin — add 15-25%
in real designs, use steady-state current (not inrush), and for
5 A and above consider 2 oz copper, a pour/plane, or a busbar.

Modes:
    1. Single calculation:
         python trace_width.py --current 2 --copper 1 --layer external
    2. Verdict against an actual width:
         python trace_width.py --current 2 --copper 1 --layer external --actual 0.5
    3. Reference table:
         python trace_width.py --table
    4. Check a CSV of nets (columns: net,current_a,actual_mm,copper_oz,layer):
         python trace_width.py --check-csv nets.csv

Exit codes: 0 = pass (all widths sufficient / calculation done),
1 = fail (at least one net undersized), 2 = setup missing (bad arguments
or unreadable file).

Standard library only. Works on Windows, macOS and Linux.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.2.5"
SCRIPT = "trace_width"

MIL_PER_MM = 1.0 / 0.0254          # 1 mm = 39.3701 mil
OZ_TO_MIL = 1.37                   # 1 oz copper = 1.37 mil thick
K_EXTERNAL = 0.048
K_INTERNAL = 0.024

# Reference values (IPC-2221, 1 oz, external, dT = 10 C) — used by --table
# and as a sanity cross-check of the formula. These values are GENERATED
# from required_width_mm() below (rounded to 2 decimals), never typed
# from a table by hand: a hand-typed 2.50 mm for 5 A was wrong — the
# formula gives 2.78 mm (fixed in v1.2.3). If you change the formula,
# regenerate this dict and check --table shows reference == formula.
REFERENCE_MM = {0.5: 0.12, 1.0: 0.30, 2.0: 0.79, 3.0: 1.37, 5.0: 2.78, 10.0: 7.24}


def required_width_mm(current_a, copper_oz=1.0, layer="external", delta_t_c=10.0):
    """Minimum trace width in mm for a given current (IPC-2221)."""
    if current_a <= 0:
        raise ValueError("current must be greater than zero")
    if copper_oz <= 0:
        raise ValueError("copper weight must be greater than zero")
    if delta_t_c <= 0:
        raise ValueError("temperature rise must be greater than zero")
    k = K_EXTERNAL if layer == "external" else K_INTERNAL
    thickness_mil = copper_oz * OZ_TO_MIL
    area_mil2 = (current_a / (k * delta_t_c ** 0.44)) ** (1.0 / 0.725)
    width_mil = area_mil2 / thickness_mil
    return width_mil / MIL_PER_MM


def verdict(required_mm, actual_mm):
    return "PASS" if actual_mm >= required_mm else "FAIL"


def print_audit_log(started, what, rows, failures):
    # Audit log goes to STDERR, never stdout: with --json, stdout must
    # be parseable JSON only (fixed in v1.2.3 — the log used to be
    # appended after the JSON, which broke every JSON consumer).
    print("--- AUDIT LOG ---", file=sys.stderr)
    print(f"script: {SCRIPT} v{VERSION}", file=sys.stderr)
    print(f"started: {started} UTC", file=sys.stderr)
    print(f"input: {what}", file=sys.stderr)
    print("method: IPC-2221, formula I = k * dT^0.44 * A^0.725", file=sys.stderr)
    for row in rows:
        print(f"  - {row}", file=sys.stderr)
    print(f"failures: {failures}", file=sys.stderr)
    print(f"result: {'FAIL' if failures else 'PASS'} (exit {1 if failures else 0})",
          file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="IPC-2221 trace-width calculator.")
    ap.add_argument("--current", type=float, default=None, help="current in amps")
    ap.add_argument("--copper", type=float, default=1.0, help="copper weight in oz (default 1)")
    ap.add_argument("--layer", choices=["external", "internal"], default="external")
    ap.add_argument("--delta-t", type=float, default=10.0,
                    help="allowed temperature rise in C (default 10)")
    ap.add_argument("--actual", type=float, default=None,
                    help="actual trace width in mm — prints a PASS/FAIL verdict")
    ap.add_argument("--table", action="store_true", help="print the reference table")
    ap.add_argument("--check-csv", default=None,
                    help="CSV with columns net,current_a,actual_mm,copper_oz,layer")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    args = ap.parse_args(argv)

    started = datetime.now(timezone.utc).isoformat()

    if args.table:
        print("IPC-2221 trace width, 1 oz copper, external layer, dT = 10 C")
        print(f"{'Current':>8}  {'Required width':>14}  {'Note'}")
        for current, width in sorted(REFERENCE_MM.items()):
            calc = required_width_mm(current, 1.0, "external", 10.0)
            note = "use >= 0.20 mm anyway (design-to minimum)" if width < 0.20 else ""
            print(f"{current:>7.1f} A  {width:>12.2f} mm  "
                  f"(formula: {calc:.2f} mm)  {note}")
        print()
        print("Note: internal layers need ~2.6x the width. "
              "Add 15-25% margin in real designs.")
        print_audit_log(started, "--table (reference values)",
                        ["printed IPC-2221 reference table"], 0)
        return 0

    if args.check_csv:
        path = Path(args.check_csv)
        if not path.is_file():
            print(f"SETUP ERROR: CSV file not found: {path}", file=sys.stderr)
            return 2
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except (OSError, csv.Error) as exc:
            print(f"SETUP ERROR: cannot read CSV: {exc}", file=sys.stderr)
            return 2
        results = []
        failures = 0
        for lineno, row in enumerate(rows, start=2):
            try:
                net = (row.get("net") or "").strip() or f"line {lineno}"
                current = float(row["current_a"])
                actual = float(row["actual_mm"])
                copper = float(row.get("copper_oz") or 1.0)
                layer = (row.get("layer") or "external").strip().lower()
                if layer not in ("external", "internal"):
                    raise ValueError(f"unknown layer '{layer}'")
                required = required_width_mm(current, copper, layer, args.delta_t)
            except (KeyError, TypeError, ValueError) as exc:
                print(f"SETUP ERROR: line {lineno}: {exc}", file=sys.stderr)
                return 2
            v = verdict(required, actual)
            if v == "FAIL":
                failures += 1
            results.append({"net": net, "current_a": current,
                            "required_mm": round(required, 3),
                            "actual_mm": actual, "verdict": v})
        if args.json:
            print(json.dumps({"script": SCRIPT, "version": VERSION,
                              "results": results, "failures": failures}, indent=2))
        else:
            for r in results:
                print(f"{r['verdict']:4} net {r['net']}: {r['current_a']} A needs "
                      f">= {r['required_mm']:.3f} mm, actual {r['actual_mm']:.3f} mm")
            print()
            print(f"Result: {len(results) - failures} pass, {failures} fail.")
        print_audit_log(started, f"CSV {path}",
                        [f"net {r['net']}: required {r['required_mm']:.3f} mm, "
                         f"actual {r['actual_mm']:.3f} mm -> {r['verdict']}"
                         for r in results], failures)
        return 1 if failures else 0

    if args.current is None:
        ap.error("one of --current, --table or --check-csv is required")

    try:
        required = required_width_mm(args.current, args.copper, args.layer, args.delta_t)
    except ValueError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        return 2

    design_min = 0.20
    recommended = max(required, design_min)
    if args.json:
        out = {"script": SCRIPT, "version": VERSION,
               "current_a": args.current, "copper_oz": args.copper,
               "layer": args.layer, "delta_t_c": args.delta_t,
               "required_mm": round(required, 3),
               "recommended_mm": round(recommended, 3)}
        if args.actual is not None:
            out["actual_mm"] = args.actual
            out["verdict"] = verdict(required, args.actual)
        print(json.dumps(out, indent=2))
    else:
        print(f"Current: {args.current} A, copper {args.copper} oz, "
              f"{args.layer} layer, dT {args.delta_t} C")
        print(f"IPC-2221 minimum width: {required:.3f} mm")
        print(f"Recommended width (design-to minimum 0.20 mm applied): "
              f"{recommended:.3f} mm")
        if args.actual is not None:
            v = verdict(required, args.actual)
            print(f"Actual width: {args.actual:.3f} mm -> {v}")
            if v == "FAIL":
                print(f"  Undersized by {required - args.actual:.3f} mm. "
                      "Widen the trace, use a pour/plane, or heavier copper.")
    failures = 0
    if args.actual is not None and verdict(required, args.actual) == "FAIL":
        failures = 1
    print_audit_log(
        started,
        f"single calculation: {args.current} A, {args.copper} oz, {args.layer}",
        [f"required width {required:.3f} mm"
         + (f", actual {args.actual:.3f} mm -> "
            f"{verdict(required, args.actual)}" if args.actual is not None else "")],
        failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

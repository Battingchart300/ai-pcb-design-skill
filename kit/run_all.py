#!/usr/bin/env python3
"""run_all.py — run every kit check on a board and summarise.

This is a convenience runner for the kit. It runs drc_check, bom_check,
trace_width and rules_check and prints one combined summary with a
single audit log.

With no arguments it runs on the example files in kit/examples/ — those
contain INTENTIONAL errors (they demonstrate what the checks catch),
so the expected result there is FAIL; see kit/README.md for the
expected findings per file.

With arguments it runs the same checks on YOUR files instead:

    python run_all.py --pcb my_board.kicad_pcb --bom my_bom.csv \
        --nets my_nets.csv --spec my_spec.json

Each argument is independent: give only the ones you have, the rest
keep their example defaults.

Usage:
    python run_all.py [--json] [--pcb FILE] [--bom FILE]
                      [--nets FILE] [--spec FILE]

Exit codes: 0 = all checks pass, 1 = at least one check fails,
2 = a check could not run (setup error).

Standard library only. Works on Windows, macOS and Linux.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.2.3"
SCRIPT = "run_all"


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Run every kit check on a board (default: the example files).")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--pcb", default="examples/sample.kicad_pcb",
                    help="board file for drc_check.py "
                         "(default: examples/sample.kicad_pcb)")
    ap.add_argument("--bom", default="examples/sample_bom.csv",
                    help="BOM file for bom_check.py "
                         "(default: examples/sample_bom.csv)")
    ap.add_argument("--nets", default="examples/nets.csv",
                    help="nets CSV for trace_width.py --check-csv "
                         "(default: examples/nets.csv)")
    ap.add_argument("--spec", default="examples/spec.json",
                    help="spec file for rules_check.py "
                         "(default: examples/spec.json)")
    args = ap.parse_args(argv)

    on_examples = (args.pcb == "examples/sample.kicad_pcb" and
                   args.bom == "examples/sample_bom.csv" and
                   args.nets == "examples/nets.csv" and
                   args.spec == "examples/spec.json")

    started = datetime.now(timezone.utc).isoformat()
    kit_dir = Path(__file__).resolve().parent

    checks = [
        ("drc_check", ["drc_check.py", args.pcb]),
        ("bom_check", ["bom_check.py", args.bom]),
        ("trace_width", ["trace_width.py", "--check-csv", args.nets]),
        ("rules_check", ["rules_check.py", args.spec]),
    ]

    results = []
    worst = 0

    def _resolve(p):
        """Resolve a check input path: absolute paths pass through,
        the example defaults resolve against the kit folder, and a
        user-given relative path resolves against the current working
        directory (the way the user typed it)."""
        path = Path(p)
        if path.is_absolute():
            return str(path)
        if p.startswith("examples/"):
            return str(kit_dir / p)
        return p

    for name, cmd in checks:
        full_cmd = [sys.executable, str(kit_dir / cmd[0])] + [
            _resolve(c) if not c.startswith("--") else c for c in cmd[1:]
        ]
        proc = subprocess.run(full_cmd, capture_output=True, text=True)
        results.append({
            "check": name,
            "exit_code": proc.returncode,
            "result": "PASS" if proc.returncode == 0 else
                      "FAIL" if proc.returncode == 1 else "SETUP ERROR",
        })
        worst = max(worst, proc.returncode if proc.returncode in (0, 1, 2) else 2)

    if args.json:
        print(json.dumps({"script": SCRIPT, "version": VERSION,
                          "checks": results,
                          "overall_exit_code": worst}, indent=2))
    else:
        for r in results:
            print(f"{r['result']:11} {r['check']} (exit {r['exit_code']})")
        print()
        passed = sum(1 for r in results if r["exit_code"] == 0)
        print(f"Overall: {passed}/{len(results)} checks pass. "
              f"Exit code: {worst}.")
        if worst == 1 and on_examples:
            print("Note: the example files contain intentional errors, "
                  "so FAIL is the expected result here.")

    # Audit log goes to STDERR, never stdout: with --json, stdout must
    # be parseable JSON only (fixed in v1.2.3).
    print("--- AUDIT LOG ---", file=sys.stderr)
    print(f"script: {SCRIPT} v{VERSION}", file=sys.stderr)
    print(f"started: {started} UTC", file=sys.stderr)
    print(f"kit: {kit_dir}", file=sys.stderr)
    print(f"inputs: pcb={args.pcb} bom={args.bom} "
          f"nets={args.nets} spec={args.spec}", file=sys.stderr)
    for r in results:
        print(f"  - {r['check']}: {r['result']} (exit {r['exit_code']})",
              file=sys.stderr)
    print(f"result: {'PASS' if worst == 0 else 'FAIL' if worst == 1 else 'SETUP ERROR'} "
          f"(exit {worst})", file=sys.stderr)
    return worst


if __name__ == "__main__":
    sys.exit(main())

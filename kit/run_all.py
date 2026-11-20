#!/usr/bin/env python3
"""run_all.py — run every kit check on the example files and summarise.

This is a convenience runner for the kit. It runs drc_check, bom_check,
trace_width and rules_check on kit/examples/ and prints one combined
summary with a single audit log.

The example files contain INTENTIONAL errors (they demonstrate what the
checks catch), so the expected result here is FAIL — see kit/README.md
for the expected findings per file.

Usage:
    python run_all.py [--json]

Exit codes: 0 = all checks pass, 1 = at least one check fails,
2 = a check could not run (setup error).

Standard library only. Works on Windows, macOS and Linux.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.1.0"
SCRIPT = "run_all"

CHECKS = [
    ("drc_check", ["drc_check.py", "examples/sample.kicad_pcb"]),
    ("bom_check", ["bom_check.py", "examples/sample_bom.csv"]),
    ("trace_width", ["trace_width.py", "--check-csv", "examples/nets.csv"]),
    ("rules_check", ["rules_check.py", "examples/spec.json"]),
]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Run every kit check on the examples.")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = ap.parse_args(argv)

    started = datetime.now(timezone.utc).isoformat()
    kit_dir = Path(__file__).resolve().parent
    results = []
    worst = 0

    for name, cmd in CHECKS:
        full_cmd = [sys.executable, str(kit_dir / cmd[0])] + [
            str(kit_dir / c) if not c.startswith("--") else c for c in cmd[1:]
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
        if worst == 1:
            print("Note: the example files contain intentional errors, "
                  "so FAIL is the expected result here.")

    print("--- AUDIT LOG ---")
    print(f"script: {SCRIPT} v{VERSION}")
    print(f"started: {started} UTC")
    print(f"kit: {kit_dir}")
    for r in results:
        print(f"  - {r['check']}: {r['result']} (exit {r['exit_code']})")
    print(f"result: {'PASS' if worst == 0 else 'FAIL' if worst == 1 else 'SETUP ERROR'} "
          f"(exit {worst})")
    return worst


if __name__ == "__main__":
    sys.exit(main())

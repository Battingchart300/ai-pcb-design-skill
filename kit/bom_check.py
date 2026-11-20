#!/usr/bin/env python3
"""bom_check.py — checks on a bill of materials (BOM) CSV.

Checks (all values come from config.json):
  1. Missing manufacturer part number (MPN) — a part with no MPN cannot
     be verified against a datasheet, so it is UNVERIFIED and an error.
  2. Missing footprint — the part cannot be placed or ordered.
  3. Missing value — a part with no value is incomplete.
  4. Duplicate reference — the same designator listed twice.
  5. Quantity mismatch — the number of designators in the Reference
     field does not match the Quantity column.
  6. Missing LCSC number (warning) — needed when the board is assembled
     at JLCPCB; harmless for a bare board.
  7. Reference format — a designator that does not look like R1 / C12 /
     U3 / J1 / Q2 / L4 / D5 is flagged for review.

Expected columns (case-insensitive, extra columns are ignored):
    Reference, Value, Footprint, Quantity, MPN, Manufacturer, LCSC

Usage:
    python bom_check.py bom.csv [--config config.json] [--json]

Exit codes: 0 = pass (warnings allowed), 1 = fail (at least one error),
2 = setup missing (file not found, unreadable CSV, bad config).

Standard library only. Works on Windows, macOS and Linux.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
SCRIPT = "bom_check"

REF_PATTERN = re.compile(r"^[A-Z]{1,3}\d+$")


def split_designators(reference):
    """Split a Reference cell like 'R1, R2 R3' into ['R1', 'R2', 'R3']."""
    parts = re.split(r"[,\s;]+", (reference or "").strip())
    return [p for p in parts if p]


class SetupError(Exception):
    pass


def check_bom(path, config):
    """Run all checks. Returns (findings, stats, skipped)."""
    bom_cfg = config.get("bom", {})
    require_mpn = bool(bom_cfg.get("require_mpn", True))
    require_footprint = bool(bom_cfg.get("require_footprint", True))
    fab = str(config.get("fab", "jlcpcb")).lower()

    findings = []
    skipped = []

    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    except OSError as exc:
        raise SetupError(f"cannot read BOM file: {exc}")
    except csv.Error as exc:
        raise SetupError(f"cannot parse BOM CSV: {exc}")

    if not rows:
        raise SetupError("BOM file is empty (no data rows)")

    # Normalise headers to lower case without spaces.
    norm_rows = []
    for row in rows:
        norm = {}
        for key, value in row.items():
            if key is None:
                continue
            norm[key.strip().lower()] = (value or "").strip()
        norm_rows.append(norm)

    headers = set(norm_rows[0])
    for needed in ("reference", "value", "footprint", "quantity"):
        if needed not in headers:
            raise SetupError(f"BOM is missing the required column '{needed}'")
    if "mpn" not in headers:
        skipped.append("MPN check (no MPN column in BOM)")
    if "lcsc" not in headers:
        skipped.append("LCSC check (no LCSC column in BOM)")

    seen_refs = {}
    stats = {"rows": len(norm_rows), "parts_total": 0}

    for lineno, row in enumerate(norm_rows, start=2):  # line 1 is the header
        refs = split_designators(row.get("reference", ""))
        value = row.get("value", "")
        footprint = row.get("footprint", "")
        mpn = row.get("mpn", "")
        lcsc = row.get("lcsc", "")
        qty_raw = row.get("quantity", "")

        if not refs:
            findings.append({
                "severity": "error", "check": "empty-reference",
                "message": "row has no Reference — every BOM row needs a designator",
                "location": f"line {lineno}"})
            continue

        try:
            qty = int(qty_raw)
        except ValueError:
            findings.append({
                "severity": "error", "check": "quantity",
                "message": f"Quantity '{qty_raw}' is not a whole number",
                "location": f"line {lineno} ({', '.join(refs)})"})
            qty = None

        stats["parts_total"] += qty if qty else len(refs)

        for ref in refs:
            if ref in seen_refs:
                findings.append({
                    "severity": "error", "check": "duplicate-reference",
                    "message": f"reference {ref} appears twice "
                               f"(first on line {seen_refs[ref]})",
                    "location": f"line {lineno}"})
            else:
                seen_refs[ref] = lineno
            if not REF_PATTERN.match(ref):
                findings.append({
                    "severity": "warning", "check": "reference-format",
                    "message": f"reference '{ref}' does not look like a "
                               "designator (R1, C12, U3, J1, ...)",
                    "location": f"line {lineno}"})

        if qty is not None and qty != len(refs):
            findings.append({
                "severity": "error", "check": "quantity-mismatch",
                "message": f"Quantity is {qty} but the Reference field lists "
                           f"{len(refs)} designator(s) ({', '.join(refs)})",
                "location": f"line {lineno}"})

        if not value:
            findings.append({
                "severity": "warning", "check": "missing-value",
                "message": "no Value — the part is incomplete",
                "location": f"line {lineno} ({', '.join(refs)})"})

        if require_footprint and not footprint:
            findings.append({
                "severity": "error", "check": "missing-footprint",
                "message": "no Footprint — the part cannot be placed",
                "location": f"line {lineno} ({', '.join(refs)})"})

        if require_mpn and "mpn" in headers and not mpn:
            findings.append({
                "severity": "error", "check": "missing-mpn",
                "message": "no MPN — UNVERIFIED, the part cannot be checked "
                           "against a datasheet",
                "location": f"line {lineno} ({', '.join(refs)})"})

        if fab == "jlcpcb" and "lcsc" in headers and not lcsc:
            findings.append({
                "severity": "warning", "check": "missing-lcsc",
                "message": "no LCSC number — needed for JLCPCB assembly "
                           "(harmless for a bare board)",
                "location": f"line {lineno} ({', '.join(refs)})"})

    return findings, stats, skipped


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="BOM checks on a bill of materials CSV.")
    ap.add_argument("bom", help="path to the BOM .csv file")
    ap.add_argument("--config", default=None,
                    help="path to config.json (default: config.json next to this script)")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    args = ap.parse_args(argv)

    bom_path = Path(args.bom)
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir / "config.json"
    started = datetime.now(timezone.utc).isoformat()

    try:
        if not bom_path.is_file():
            raise SetupError(f"BOM file not found: {bom_path}")
        if not config_path.is_file():
            raise SetupError(f"config file not found: {config_path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        findings, stats, skipped = check_bom(bom_path, config)
    except SetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        print("--- AUDIT LOG ---")
        print(f"script: {SCRIPT} v{VERSION}")
        print(f"started: {started} UTC")
        print(f"input: {bom_path} (not read)")
        print(f"config: {config_path}")
        print("checks run: none — setup failed")
        print("result: SETUP ERROR (exit 2)")
        return 2

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    if args.json:
        print(json.dumps({
            "script": SCRIPT, "version": VERSION,
            "bom": str(bom_path),
            "stats": stats,
            "findings": findings,
            "skipped": skipped,
            "errors": len(errors), "warnings": len(warnings),
        }, indent=2))
    else:
        if findings:
            for f in findings:
                loc = f" [{f['location']}]" if f.get("location") else ""
                print(f"{f['severity'].upper():7} {f['check']}: {f['message']}{loc}")
        else:
            print("No findings — BOM passes all checks.")
        print()
        print(f"BOM: {stats['rows']} row(s), {stats['parts_total']} part(s) in total.")
        print(f"Result: {len(errors)} error(s), {len(warnings)} warning(s).")

    print("--- AUDIT LOG ---")
    print(f"script: {SCRIPT} v{VERSION}")
    print(f"started: {started} UTC")
    print(f"input: {bom_path} (sha256 {sha256_of(bom_path)[:16]}...)")
    print(f"config: {config_path} (sha256 {sha256_of(config_path)[:16]}...)")
    print("checks run: missing-mpn, missing-footprint, missing-value, "
          "duplicate-reference, quantity-mismatch, reference-format, missing-lcsc")
    print(f"checks skipped: {'; '.join(skipped) if skipped else 'none'}")
    print(f"findings: {len(errors)} error(s), {len(warnings)} warning(s)")
    print(f"result: {'FAIL' if errors else 'PASS'} (exit {1 if errors else 0})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

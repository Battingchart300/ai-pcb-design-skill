#!/usr/bin/env python3
"""rules_check.py — spec-first lint for a board specification (G4).

The specification is a JSON file (see examples/spec.json):

    {
      "board": {"name": "Sample Board", "layers": 2, "fab": "jlcpcb"},
      "parts": [
        {"ref": "U1", "value": "ESP32-S3", "footprint": "QFN-56",
         "mpn": "ESP32-S3-WROOM-1", "type": "mcu",
         "pins": ["1","2","3","4","5","6","7","8"],
         "power_pins": ["1","2"]},
        ...
      ],
      "nets": [
        {"name": "+3V3", "pins": ["U1.1", "C1.1"]},
        ...
      ],
      "no_connect": ["U1.8"]
    }

Checks (the spec-first lint from the skill):
  1. Pin on two nets — a short. ERROR.
  2. Pin in a net AND in no_connect — contradictory. ERROR.
  3. Unknown reference — a pin whose part is not in the parts list. ERROR.
  4. Power pin of a part not connected to any net. ERROR.
  5. IC/MCU/regulator with no decoupling capacitor on a shared net. WARNING.
  6. No bulk capacitor (>= bulk_cap_min_uf from config) anywhere. WARNING.
  7. SDA/SCL (I2C) net without a pull-up resistor to a rail. WARNING.
  8. Single-pin net — usually a typo in the net name. WARNING.
  9. Pin declared in a part's pin list but in no net and not no-connect. WARNING.

A value like "10uF", "100nF" or "4.7u" is parsed as a capacitance in uF.

Usage:
    python rules_check.py spec.json [--config config.json] [--json]

Exit codes: 0 = pass (warnings allowed), 1 = fail (at least one error),
2 = setup missing (file not found, invalid JSON, bad config).

Standard library only. Works on Windows, macOS and Linux.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.2.0"
SCRIPT = "rules_check"

CAP_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([unp]?)[fF]\s*$", re.IGNORECASE)
UNIT_MULT = {"": 1.0, "u": 1.0, "n": 0.001, "p": 0.000001}
IC_TYPES = {"mcu", "ic", "regulator", "soc", "fpga", "sensor"}
RAIL_NAMES = {"+3v3", "+5v", "+12v", "vin", "vcc", "vdd", "+3.3v", "+5.0v"}


def parse_capacitance_uf(value):
    """Parse '100nF' / '10uF' / '4.7u' into microfarads, or None."""
    if not value:
        return None
    m = CAP_PATTERN.match(str(value).strip())
    if not m:
        return None
    number = float(m.group(1))
    unit = (m.group(2) or "u").lower()
    return number * UNIT_MULT.get(unit, 1.0)


def parse_pin(pin):
    """Split 'U1.12' into ('U1', '12'). Returns (None, None) if malformed."""
    if not isinstance(pin, str) or "." not in pin:
        return None, None
    ref, num = pin.rsplit(".", 1)
    ref = ref.strip()
    num = num.strip()
    if not ref or not num:
        return None, None
    return ref, num


class SetupError(Exception):
    pass


def check_spec(spec, config):
    """Run all checks. Returns (findings, stats, skipped)."""
    power_cfg = config.get("power", {})
    bulk_min_uf = float(power_cfg.get("bulk_cap_min_uf", 10))
    findings = []
    skipped = []

    parts_list = spec.get("parts")
    nets_list = spec.get("nets")
    if not isinstance(parts_list, list) or not parts_list:
        raise SetupError("spec has no 'parts' list (or it is empty)")
    if not isinstance(nets_list, list):
        raise SetupError("spec has no 'nets' list")
    no_connect = set(spec.get("no_connect") or [])

    parts = {}
    for part in parts_list:
        ref = part.get("ref")
        if not ref:
            findings.append({"severity": "error", "check": "part-no-ref",
                             "message": "a part has no 'ref' — every part "
                                        "needs a designator",
                             "location": ""})
            continue
        if ref in parts:
            findings.append({"severity": "error", "check": "duplicate-part",
                             "message": f"part {ref} is listed twice",
                             "location": f"part {ref}"})
        parts[ref] = part

    # --- pin usage map ------------------------------------------------------
    pin_to_nets = {}   # "U1.3" -> [net names]
    net_names = []
    for net in nets_list:
        name = net.get("name", "")
        pins = net.get("pins") or []
        net_names.append(name)
        for pin in pins:
            pin_to_nets.setdefault(pin, []).append(name)

    # --- check 1: pin on two nets (a short) --------------------------------
    for pin in sorted(pin_to_nets):
        nets = pin_to_nets[pin]
        if len(nets) > 1:
            findings.append({"severity": "error", "check": "pin-on-two-nets",
                             "message": f"pin {pin} is on two nets "
                                        f"({', '.join(nets)}) — a short",
                             "location": f"net {nets[0]}"})

    # --- check 2: pin in a net and in no_connect ---------------------------
    for pin in sorted(no_connect):
        if pin in pin_to_nets:
            findings.append({"severity": "error", "check": "pin-net-and-nc",
                             "message": f"pin {pin} is in net "
                                        f"'{pin_to_nets[pin][0]}' and also in "
                                        "no_connect — contradictory",
                             "location": f"net {pin_to_nets[pin][0]}"})

    # --- check 3: unknown reference -----------------------------------------
    for pin in sorted(pin_to_nets):
        ref, _num = parse_pin(pin)
        if ref is None:
            findings.append({"severity": "error", "check": "malformed-pin",
                             "message": f"pin '{pin}' is not in the form "
                                        "REF.NUM (e.g. U1.12)",
                             "location": ""})
        elif ref not in parts:
            findings.append({"severity": "error", "check": "unknown-reference",
                             "message": f"pin {pin} refers to part {ref}, "
                                        "which is not in the parts list",
                             "location": f"net {pin_to_nets[pin][0]}"})

    # --- check 4: power pins not connected ----------------------------------
    for ref, part in parts.items():
        for pnum in part.get("power_pins") or []:
            pin = f"{ref}.{pnum}"
            if pin not in pin_to_nets and pin not in no_connect:
                findings.append({"severity": "error", "check": "power-pin-unconnected",
                                 "message": f"power pin {pin} of {ref} is not "
                                            "connected to any net",
                                 "location": f"part {ref}"})

    # --- check 5: IC without decoupling -------------------------------------
    caps = [p for p in parts.values()
            if str(p.get("ref", "")).startswith("C")]
    for ref, part in parts.items():
        ptype = str(part.get("type", "")).lower()
        if ptype not in IC_TYPES:
            continue
        part_nets = {n for pin, nets in pin_to_nets.items()
                     for n in nets if pin.startswith(ref + ".")}
        has_decoupling = False
        for cap in caps:
            cap_nets = {n for pin, nets in pin_to_nets.items()
                        for n in nets if pin.startswith(cap["ref"] + ".")}
            if part_nets & cap_nets:
                has_decoupling = True
                break
        if not has_decoupling:
            findings.append({"severity": "warning", "check": "no-decoupling",
                             "message": f"IC {ref} has no decoupling capacitor "
                                        "sharing one of its nets — every IC "
                                        "power pin needs a 100 nF cap within "
                                        "3 mm (see the skill)",
                             "location": f"part {ref}"})

    # --- check 6: no bulk capacitor -----------------------------------------
    bulk_found = False
    for cap in caps:
        uf = parse_capacitance_uf(cap.get("value", ""))
        if uf is not None and uf >= bulk_min_uf:
            bulk_found = True
            break
    if not bulk_found:
        findings.append({"severity": "warning", "check": "no-bulk-cap",
                         "message": f"no bulk capacitor >= {bulk_min_uf:g} uF "
                                    "found in the parts list — every board "
                                    "needs one at the power entry / regulator "
                                    "output",
                         "location": ""})

    # --- check 7: I2C nets without pull-up ----------------------------------
    for net in nets_list:
        name = net.get("name", "")
        if name.upper() not in ("SDA", "SCL"):
            continue
        pins = net.get("pins") or []
        has_pullup = False
        for pin in pins:
            ref, _num = parse_pin(pin)
            part = parts.get(ref or "")
            if part and str(part.get("ref", "")).startswith("R"):
                # A resistor on this net that also touches a rail = pull-up.
                other_nets = {n.lower() for p, ns in pin_to_nets.items()
                              for n in ns if p.startswith(ref + ".")}
                if other_nets & RAIL_NAMES:
                    has_pullup = True
        if not has_pullup:
            findings.append({"severity": "warning", "check": "i2c-no-pullup",
                             "message": f"I2C net '{name}' has no pull-up "
                                        "resistor to a power rail",
                             "location": f"net {name}"})

    # --- check 8: single-pin nets -------------------------------------------
    for net in nets_list:
        pins = net.get("pins") or []
        if len(pins) == 1:
            findings.append({"severity": "warning", "check": "single-pin-net",
                             "message": f"net '{net.get('name', '')}' has only "
                                        f"one pin ({pins[0]}) — usually a typo "
                                        "in the net name",
                             "location": f"net {net.get('name', '')}"})

    # --- check 9: declared pins in no net and not no-connect ---------------
    for ref, part in parts.items():
        for pnum in part.get("pins") or []:
            pin = f"{ref}.{pnum}"
            if pin not in pin_to_nets and pin not in no_connect:
                findings.append({"severity": "warning", "check": "unconnected-pin",
                                 "message": f"pin {pin} is in no net and not "
                                            "in no_connect — connect it or "
                                            "mark it no-connect",
                                 "location": f"part {ref}"})

    stats = {"parts": len(parts), "nets": len(nets_list),
             "pins_in_nets": len(pin_to_nets)}
    return findings, stats, skipped


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Spec-first lint for a board specification JSON.")
    ap.add_argument("spec", help="path to the spec.json file")
    ap.add_argument("--config", default=None,
                    help="path to config.json (default: config.json next to this script)")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    args = ap.parse_args(argv)

    spec_path = Path(args.spec)
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir / "config.json"
    started = datetime.now(timezone.utc).isoformat()

    try:
        if not spec_path.is_file():
            raise SetupError(f"spec file not found: {spec_path}")
        if not config_path.is_file():
            raise SetupError(f"config file not found: {config_path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SetupError(f"spec is not valid JSON: {exc}")
        findings, stats, skipped = check_spec(spec, config)
    except SetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        print("--- AUDIT LOG ---")
        print(f"script: {SCRIPT} v{VERSION}")
        print(f"started: {started} UTC")
        print(f"input: {spec_path} (not read)")
        print(f"config: {config_path}")
        print("checks run: none — setup failed")
        print("result: SETUP ERROR (exit 2)")
        return 2

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    if args.json:
        print(json.dumps({
            "script": SCRIPT, "version": VERSION,
            "spec": str(spec_path),
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
            print("No findings — specification passes all checks.")
        print()
        print(f"Spec: {stats['parts']} part(s), {stats['nets']} net(s), "
              f"{stats['pins_in_nets']} pin(s) in nets.")
        print(f"Result: {len(errors)} error(s), {len(warnings)} warning(s).")

    print("--- AUDIT LOG ---")
    print(f"script: {SCRIPT} v{VERSION}")
    print(f"started: {started} UTC")
    print(f"input: {spec_path} (sha256 {sha256_of(spec_path)[:16]}...)")
    print(f"config: {config_path} (sha256 {sha256_of(config_path)[:16]}...)")
    print("checks run: pin-on-two-nets, pin-net-and-nc, unknown-reference, "
          "malformed-pin, power-pin-unconnected, no-decoupling, no-bulk-cap, "
          "i2c-no-pullup, single-pin-net, unconnected-pin")
    print(f"checks skipped: {'; '.join(skipped) if skipped else 'none'}")
    print(f"findings: {len(errors)} error(s), {len(warnings)} warning(s)")
    print(f"result: {'FAIL' if errors else 'PASS'} (exit {1 if errors else 0})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

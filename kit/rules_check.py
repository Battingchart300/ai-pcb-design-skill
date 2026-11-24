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
 10. Layer count — a 3-layer board is forbidden (config
     layers.forbidden_counts); any count outside layers.allowed_counts
     is an error too. ERROR. (New in v1.2.3.)
 11. Unknown pin — a pin referenced by a net, by no_connect or by a
     power pin that is not in the part's declared pin list
     (e.g. U1.99 on a QFN-56 with pins 1-56). ERROR. (New in v1.2.3.)
 12. Power pin in no_connect — a power pin must be connected to a
     power net, it can never be no-connect. ERROR. (New in v1.2.4.)

A value like "10uF", "100nF" or "4.7u" is parsed as a capacitance in uF.

Usage:
    python rules_check.py spec.json [--config config.json] [--json]

Exit codes: 0 = pass (warnings allowed), 1 = fail (at least one error —
including a malformed spec: wrong types, non-numeric values, NaN),
2 = setup missing (file not found, invalid JSON syntax, bad config).
A bad spec never crashes with a Python traceback: every structural
problem is reported as a clean error finding (exit 1).

Standard library only. Works on Windows, macOS and Linux.
"""

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.2.4"
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
    """Run all checks. Returns (findings, stats, skipped).

    Structural problems in the SPEC (wrong JSON types, non-numeric
    values, NaN, strings where lists belong) are reported as error
    findings (exit 1) — never a Python traceback. Only file/config
    problems raise SetupError (exit 2)."""
    if not isinstance(config, dict):
        raise SetupError("config must be a JSON object")
    power_cfg = config.get("power", {})
    if not isinstance(power_cfg, dict):
        raise SetupError("config 'power' section must be an object")
    try:
        bulk_min_uf = float(power_cfg.get("bulk_cap_min_uf", 10))
    except (TypeError, ValueError):
        raise SetupError("config power.bulk_cap_min_uf must be a number")
    if not math.isfinite(bulk_min_uf):
        raise SetupError("config power.bulk_cap_min_uf must be finite (not NaN/inf)")
    layers_cfg = config.get("layers", {})
    if not isinstance(layers_cfg, dict):
        raise SetupError("config 'layers' section must be an object")
    allowed_counts = layers_cfg.get("allowed_counts", [1, 2, 4, 6, 8])
    forbidden_counts = layers_cfg.get("forbidden_counts", [3])

    findings = []
    skipped = []
    stats = {"parts": 0, "nets": 0, "pins_in_nets": 0}

    # --- structural guards: a bad spec is an error, not a crash ---------
    if not isinstance(spec, dict):
        findings.append({"severity": "error", "check": "spec-not-an-object",
                         "message": "spec must be a JSON object with "
                                    "'parts' and 'nets' lists",
                         "location": ""})
        return findings, stats, skipped
    parts_list = spec.get("parts")
    nets_list = spec.get("nets")
    if not isinstance(parts_list, list) or not parts_list:
        findings.append({"severity": "error", "check": "spec-no-parts",
                         "message": "spec has no 'parts' list (or it is "
                                    "empty) — a spec needs at least one part",
                         "location": ""})
        return findings, stats, skipped
    if not isinstance(nets_list, list):
        findings.append({"severity": "error", "check": "spec-no-nets",
                         "message": "spec has no 'nets' list — a spec "
                                    "needs a 'nets' list (use [] if the "
                                    "board really has no nets yet)",
                         "location": ""})
        return findings, stats, skipped
    no_connect_raw = spec.get("no_connect")
    if no_connect_raw is None:
        no_connect = set()
    elif isinstance(no_connect_raw, list):
        no_connect = {p for p in no_connect_raw if isinstance(p, str)}
        if any(not isinstance(p, str) for p in no_connect_raw):
            findings.append({"severity": "error", "check": "no-connect-not-a-pin",
                             "message": "no_connect has entries that are "
                                        "not pin references (REF.NUM) — "
                                        "every entry must be a string like "
                                        "\"U1.8\"",
                             "location": ""})
    else:
        findings.append({"severity": "error", "check": "no-connect-not-a-list",
                         "message": "spec 'no_connect' must be a list of "
                                    "pin references, not text or a number",
                         "location": ""})
        no_connect = set()

    parts = {}
    for part in parts_list:
        if not isinstance(part, dict):
            findings.append({"severity": "error", "check": "part-not-an-object",
                             "message": "a parts entry is not an object — "
                                        "every part must be {\"ref\", "
                                        "\"value\", \"footprint\", ...}",
                             "location": ""})
            continue
        ref = part.get("ref")
        if not isinstance(ref, str) or not ref:
            findings.append({"severity": "error", "check": "part-no-ref",
                             "message": "a part has no 'ref' (or a "
                                        "non-text ref) — every part needs "
                                        "a designator string",
                             "location": ""})
            continue
        if ref in parts:
            findings.append({"severity": "error", "check": "duplicate-part",
                             "message": f"part {ref} is listed twice",
                             "location": f"part {ref}"})
        parts[ref] = part

    # --- check 0: pins / power_pins / net pins must be lists of pin numbers --
    # A model that writes pins as free text ("UNVERIFIED — verify ...") used to
    # be iterated character by character, producing hundreds of misleading
    # warnings (Gemini spec, 2026-11-23: 296 warnings from one string).
    # Fail once per part / net instead, and treat the bad value as empty so
    # later checks do not double-count it.
    PIN_NUM_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
    for part in parts_list:
        if not isinstance(part, dict):
            continue  # already reported once above as part-not-an-object
        ref = part.get("ref") or "?"
        for field in ("pins", "power_pins"):
            value = part.get(field)
            if value is None:
                continue
            if isinstance(value, str):
                findings.append({"severity": "error", "check": f"{field}-not-a-list",
                                 "message": f"part {ref} has {field} as text, "
                                            f"not a list of pin numbers — use a list "
                                            f"like [\"1\", \"2\"], or [] while the "
                                            f"pinout is still UNVERIFIED",
                                 "location": f"part {ref}"})
            elif isinstance(value, list):
                bad_entries = [e for e in value
                               if not isinstance(e, str) or not PIN_NUM_RE.match(e)]
                if bad_entries:
                    findings.append({"severity": "error", "check": f"{field}-not-a-number",
                                     "message": f"part {ref} has free-text {field} "
                                                f"entries {bad_entries} — a pin entry "
                                                f"must be a pin number from the "
                                                f"datasheet (e.g. \"3\"), not a "
                                                f"description; leave the list empty "
                                                f"until it is verified",
                                     "location": f"part {ref}"})
    for net in nets_list:
        if not isinstance(net, dict):
            findings.append({"severity": "error", "check": "net-not-an-object",
                             "message": "a nets entry is not an object — "
                                        "every net must be {\"name\", "
                                        "\"pins\": [...]}",
                             "location": ""})
            continue
        value = net.get("pins")
        if value is not None and not isinstance(value, list):
            findings.append({"severity": "error", "check": "net-pins-not-a-list",
                             "message": f"net '{net.get('name', '')}' has pins as "
                                        "text, not a list — use a list like "
                                        "[\"U1.1\", \"C1.1\"]",
                             "location": f"net {net.get('name', '')}"})

    def _pin_list(value):
        return value if isinstance(value, list) else []

    # --- pin usage map ------------------------------------------------------
    pin_to_nets = {}   # "U1.3" -> [net names]
    net_names = []
    for net in nets_list:
        if not isinstance(net, dict):
            continue  # already reported once above as net-not-an-object
        name = net.get("name", "")
        if not isinstance(name, str):
            # A non-text net name would crash ', '.join() below — coerce.
            name = "" if name is None else str(name)
        pins = _pin_list(net.get("pins")) or []
        net_names.append(name)
        for pin in pins:
            if not isinstance(pin, str):
                continue  # already reported by check 0 as pins-not-a-number
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

    # --- check 11: pin number not in the part's declared pin list ---------
    # A net (or no_connect, or a power pin) that references U1.99 when
    # U1 only declares pins 1-56 is a typo or a hallucinated pin — it
    # used to pass silently. Parts with an empty/missing pins list are
    # skipped here: with no pinout to check against, nothing can be
    # proven wrong (the pinout is still UNVERIFIED, see check 0).
    declared_pins = {}
    for ref, part in parts.items():
        pins = part.get("pins")
        if isinstance(pins, list) and pins:
            declared_pins[ref] = {str(p) for p in pins
                                  if isinstance(p, str) and PIN_NUM_RE.match(p)}
    for pin in sorted(pin_to_nets):
        ref, num = parse_pin(pin)
        if ref is None or ref not in declared_pins:
            continue  # unknown ref already reported by check 3
        if num not in declared_pins[ref]:
            findings.append({"severity": "error", "check": "unknown-pin",
                             "message": f"pin {pin} is not in part {ref}'s "
                                        f"pin list (declared: "
                                        f"{', '.join(sorted(declared_pins[ref], key=lambda x: (len(x), x))[:8])}"
                                        f"{'...' if len(declared_pins[ref]) > 8 else ''}) "
                                        "— check the datasheet pinout",
                             "location": f"net {pin_to_nets[pin][0]}"})
    for pin in sorted(no_connect):
        ref, num = parse_pin(pin)
        if ref is None or ref not in declared_pins:
            continue
        if num not in declared_pins[ref]:
            findings.append({"severity": "error", "check": "unknown-pin",
                             "message": f"pin {pin} in no_connect is not "
                                        f"in part {ref}'s pin list — check "
                                        "the datasheet pinout",
                             "location": "no_connect"})
    for ref, part in parts.items():
        if ref not in declared_pins:
            continue
        for pnum in _pin_list(part.get("power_pins")):
            pin = f"{ref}.{pnum}"
            # Only when the pin IS connected: an unconnected power pin
            # is already an error under check 4, do not double-report.
            if pin in pin_to_nets and str(pnum) not in declared_pins[ref]:
                findings.append({"severity": "error", "check": "unknown-pin",
                                 "message": f"power pin {pin} is not in "
                                            f"part {ref}'s pin list — check "
                                            "the datasheet pinout",
                                 "location": f"part {ref}"})

    # --- check 10: layer count ----------------------------------------------
    board = spec.get("board")
    if board is not None and not isinstance(board, dict):
        findings.append({"severity": "error", "check": "board-not-an-object",
                         "message": "spec 'board' must be an object "
                                    "{\"name\", \"layers\", \"fab\"}",
                         "location": ""})
    elif isinstance(board, dict) and "layers" in board:
        layers = board["layers"]
        if isinstance(layers, float) and math.isfinite(layers) and layers.is_integer():
            layers = int(layers)  # JSON 2.0 means 2 layers
        if isinstance(layers, bool) or not isinstance(layers, int):
            findings.append({"severity": "error", "check": "layers-not-a-number",
                             "message": f"board layers is {layers!r} — it "
                                        "must be a whole number (1, 2, 4, "
                                        "6 or 8)",
                             "location": "board"})
        elif layers in forbidden_counts:
            findings.append({"severity": "error", "check": "forbidden-layer-count",
                             "message": f"board has {layers} layers — "
                                        "3-layer boards are forbidden "
                                        "(config layers.forbidden_counts): "
                                        "if 2 layers are not enough, go "
                                        "to 4",
                             "location": "board"})
        elif layers not in allowed_counts:
            findings.append({"severity": "error", "check": "unsupported-layer-count",
                             "message": f"board has {layers} layers — "
                                        f"allowed counts are "
                                        f"{list(allowed_counts)} (config "
                                        "layers.allowed_counts)",
                             "location": "board"})

    # --- check 4: power pins not connected ----------------------------------
    for ref, part in parts.items():
        for pnum in _pin_list(part.get("power_pins")):
            if not PIN_NUM_RE.match(str(pnum)):
                continue  # already reported once by check 0, do not repeat
            pin = f"{ref}.{pnum}"
            if pin in no_connect:
                findings.append({"severity": "error", "check": "power-pin-no-connect",
                                 "message": f"power pin {pin} of {ref} is "
                                            "marked no_connect — a power pin "
                                            "must be connected to a power net, "
                                            "it can never be no-connect",
                                 "location": f"part {ref}"})
            elif pin not in pin_to_nets:
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
        if not isinstance(net, dict):
            continue
        name = net.get("name", "")
        if not isinstance(name, str):
            name = "" if name is None else str(name)
        if name.upper() not in ("SDA", "SCL"):
            continue
        pins = _pin_list(net.get("pins"))
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
        if not isinstance(net, dict):
            continue
        pins = _pin_list(net.get("pins"))
        if len(pins) == 1:
            findings.append({"severity": "warning", "check": "single-pin-net",
                             "message": f"net '{net.get('name', '')}' has only "
                                        f"one pin ({pins[0]}) — usually a typo "
                                        "in the net name",
                             "location": f"net {net.get('name', '')}"})

    # --- check 9: declared pins in no net and not no-connect ---------------
    for ref, part in parts.items():
        for pnum in _pin_list(part.get("pins")):
            if not PIN_NUM_RE.match(str(pnum)):
                continue  # already reported once by check 0, do not repeat
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
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SetupError(f"config is not valid JSON: {exc}")
        if not isinstance(config, dict):
            raise SetupError("config must be a JSON object")
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SetupError(f"spec is not valid JSON: {exc}")
        findings, stats, skipped = check_spec(spec, config)
    except SetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        print("--- AUDIT LOG ---", file=sys.stderr)
        print(f"script: {SCRIPT} v{VERSION}", file=sys.stderr)
        print(f"started: {started} UTC", file=sys.stderr)
        print(f"input: {spec_path} (not read)", file=sys.stderr)
        print(f"config: {config_path}", file=sys.stderr)
        print("checks run: none — setup failed", file=sys.stderr)
        print("result: SETUP ERROR (exit 2)", file=sys.stderr)
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

    # Audit log goes to STDERR, never stdout: with --json, stdout must
    # be parseable JSON only (fixed in v1.2.3).
    print("--- AUDIT LOG ---", file=sys.stderr)
    print(f"script: {SCRIPT} v{VERSION}", file=sys.stderr)
    print(f"started: {started} UTC", file=sys.stderr)
    print(f"input: {spec_path} (sha256 {sha256_of(spec_path)[:16]}...)", file=sys.stderr)
    print(f"config: {config_path} (sha256 {sha256_of(config_path)[:16]}...)", file=sys.stderr)
    print("checks run: pin-on-two-nets, pin-net-and-nc, unknown-reference, "
          "pins-not-a-list, power-pins-not-a-list, pins-not-a-number, "
          "power-pin-not-a-number, net-pins-not-a-list, malformed-pin, "
          "power-pin-unconnected, power-pin-no-connect, no-decoupling, no-bulk-cap, "
          "i2c-no-pullup, single-pin-net, unconnected-pin, "
          "unknown-pin, forbidden-layer-count, unsupported-layer-count",
          file=sys.stderr)
    print(f"checks skipped: {'; '.join(skipped) if skipped else 'none'}", file=sys.stderr)
    print(f"findings: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
    print(f"result: {'FAIL' if errors else 'PASS'} (exit {1 if errors else 0})",
          file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

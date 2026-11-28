"""Regression tests for rules_check.py (v1.2.7 audit fixes).

Each test loads a negative fixture from kit/examples/regression_*.json
and asserts it FAILS with exactly one error of the expected check.
The fixtures are documented in kit/README.md ("Regression fixtures").
"""
import json
import subprocess
import sys
from pathlib import Path

from rules_check import check_spec

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"
CONFIG = json.loads((KIT / "config.json").read_text(encoding="utf-8"))


def load_fixture(name):
    return json.loads((KIT / "examples" / name).read_text(encoding="utf-8"))


def errors_for(spec):
    findings, _stats, _skipped = check_spec(spec, CONFIG)
    return [f for f in findings if f["severity"] == "error"]


def test_power_pins_int_fails():
    """Audit P0: power_pins: 42 (a bare int) used to PASS."""
    errors = errors_for(load_fixture("regression_power_pins_int.json"))
    assert [f["check"] for f in errors] == ["power_pins-not-a-list"]


def test_object_pin_fails():
    """Audit P0: a net pin given as an object used to PASS."""
    errors = errors_for(load_fixture("regression_object_pin.json"))
    assert [f["check"] for f in errors] == ["net-pin-not-a-string"]


def test_no_connect_unknown_pin_fails():
    """Audit P1: no_connect with a nonexistent pin (Z99.1) used to PASS."""
    errors = errors_for(load_fixture("regression_no_connect_unknown.json"))
    assert [f["check"] for f in errors] == ["unknown-reference"]


def test_footprint_unverified_fails():
    """Audit P1: a footprint of UNVERIFIED used to PASS (BOM rule)."""
    errors = errors_for(load_fixture("regression_footprint_unverified.json"))
    assert [f["check"] for f in errors] == ["part-missing-footprint"]


def test_clean_spec_passes():
    """The same shape without any defect must still PASS."""
    spec = load_fixture("regression_footprint_unverified.json")
    spec["parts"][0]["footprint"] = "QFN-56"
    findings, _stats, _skipped = check_spec(spec, CONFIG)
    assert findings == []


def test_pins_int_fails_once():
    """pins: 42 fails once (pins-not-a-list), not twice via check 13."""
    spec = load_fixture("regression_footprint_unverified.json")
    spec["parts"][0]["footprint"] = "QFN-56"
    spec["parts"][0]["pins"] = 42
    errors = errors_for(spec)
    assert [f["check"] for f in errors] == ["pins-not-a-list"]


def test_footprint_unverified_case_insensitive():
    """UNVERIFIED is matched case-insensitively, like the BOM rule."""
    spec = load_fixture("regression_footprint_unverified.json")
    spec["parts"][0]["footprint"] = "unverified"
    errors = errors_for(spec)
    assert [f["check"] for f in errors] == ["part-missing-footprint"]


def test_footprint_unverified_prefix_fails():
    """A footprint starting with UNVERIFIED is not a real footprint."""
    spec = load_fixture("regression_footprint_unverified.json")
    spec["parts"][0]["footprint"] = "UNVERIFIED - TBD"
    errors = errors_for(spec)
    assert [f["check"] for f in errors] == ["part-missing-footprint"]


def test_no_connect_unknown_pin_number_still_fails():
    """no_connect U1.99 (part exists, pin does not) stays unknown-pin."""
    spec = load_fixture("regression_no_connect_unknown.json")
    spec["no_connect"] = ["U1.99"]
    errors = errors_for(spec)
    assert [f["check"] for f in errors] == ["unknown-pin"]


def test_no_connect_malformed_string_fails():
    """no_connect "invalid" (no dot, not a pin ref) is malformed-pin."""
    spec = load_fixture("regression_no_connect_unknown.json")
    spec["no_connect"] = ["invalid"]
    errors = errors_for(spec)
    assert [f["check"] for f in errors] == ["malformed-pin"]


def test_power_pins_int_cli_exit_code():
    """End to end: the CLI exits 1 on the power_pins: 42 fixture."""
    result = subprocess.run(
        [sys.executable, str(KIT / "rules_check.py"),
         str(KIT / "examples" / "regression_power_pins_int.json")],
        capture_output=True, text=True)
    assert result.returncode == 1
    assert "power_pins-not-a-list" in result.stdout

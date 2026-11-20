#!/usr/bin/env python3
"""drc_check.py — design-rule checks on a KiCad .kicad_pcb file.

Checks (all values come from config.json, defaults are the skill's
design-to values):
  1. Unrouted / unconnected nets — a declared net with no copper at all.
  2. Trace width below the design-to minimum.
  3. Via drill / pad below the minimum, annular ring too small.
  4. 90-degree trace corners (45-degree / arc corners only).
  5. Copper closer to the board edge than the allowed distance.

This is NOT a replacement for KiCad DRC (kicad-cli pcb drc). It is the
skill's independent second check: it reads the raw .kicad_pcb text and
verifies the things a rule file can silently miss.

Usage:
    python drc_check.py board.kicad_pcb [--config config.json] [--json]

Exit codes: 0 = pass (warnings allowed), 1 = fail (at least one error),
2 = setup missing (file not found, unparseable file, bad config).

Standard library only. Works on Windows, macOS and Linux.
"""

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
SCRIPT = "drc_check"

# ---------------------------------------------------------------------------
# Minimal S-expression parser for KiCad files
# ---------------------------------------------------------------------------

def tokenize(text):
    """Split KiCad S-expression text into tokens: '(', ')', quoted strings,
    and atoms. Returns a list of tokens; quoted strings keep their quotes
    stripped and are tagged so they are not confused with symbols."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
        elif ch == "(":
            tokens.append("(")
            i += 1
        elif ch == ")":
            tokens.append(")")
            i += 1
        elif ch == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()\"":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse_sexp(text):
    """Parse S-expression text into nested Python lists.
    Atoms: numbers become int/float, quoted strings become str,
    symbols stay str. Raises ValueError on unbalanced input."""
    tokens = tokenize(text)
    pos = [0]

    def parse_one():
        if pos[0] >= len(tokens):
            raise ValueError("unexpected end of file inside expression")
        tok = tokens[pos[0]]
        pos[0] += 1
        if tok == "(":
            items = []
            while pos[0] < len(tokens) and tokens[pos[0]] != ")":
                items.append(parse_one())
            if pos[0] >= len(tokens):
                raise ValueError("unbalanced parentheses: missing ')'")
            pos[0] += 1  # consume ')'
            return items
        if tok == ")":
            raise ValueError("unexpected ')'")
        if isinstance(tok, tuple):  # quoted string
            return tok[1]
        try:
            return int(tok)
        except ValueError:
            pass
        try:
            return float(tok)
        except ValueError:
            return tok

    roots = []
    while pos[0] < len(tokens):
        roots.append(parse_one())
    return roots


def find_nodes(tree, head):
    """Yield every sub-list in the tree whose first element is `head`."""
    if isinstance(tree, list):
        if tree and tree[0] == head:
            yield tree
        for item in tree:
            yield from find_nodes(item, head)


def child(node, head):
    """Return the first child list of `node` whose first element is `head`,
    or None."""
    for item in node[1:]:
        if isinstance(item, list) and item and item[0] == head:
            return item
    return None


def child_value(node, head, index=1, default=None):
    c = child(node, head)
    if c is None or len(c) <= index:
        return default
    return c[index]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

class Finding:
    def __init__(self, severity, check, message, location=""):
        self.severity = severity  # "error" or "warning"
        self.check = check
        self.message = message
        self.location = location

    def text(self):
        loc = f" [{self.location}]" if self.location else ""
        return f"{self.severity.upper():7} {self.check}: {self.message}{loc}"


def check_board(path, config):
    """Run all checks. Returns (findings, stats, skipped)."""
    rules = config.get("design_rules", {})
    min_trace = float(rules.get("min_trace_mm", 0.20))
    min_drill = float(rules.get("min_via_drill_mm", 0.30))
    min_via_pad = float(rules.get("min_via_pad_mm", 0.60))
    min_ring = float(rules.get("min_annular_ring_mm", 0.15))
    edge_clear = float(rules.get("copper_to_edge_mm", 0.30))

    findings = []
    skipped = []

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SetupError(f"cannot read board file: {exc}")

    try:
        tree = parse_sexp(raw)
    except ValueError as exc:
        raise SetupError(f"cannot parse .kicad_pcb (not a valid S-expression file?): {exc}")

    if not tree or not isinstance(tree[0], list) or tree[0][0] != "kicad_pcb":
        raise SetupError("file does not look like a KiCad .kicad_pcb (no (kicad_pcb ...) root)")

    root = tree[0]

    # --- net declarations: (net <id> "<name>") with 3 items ----------------
    declared = {}
    for node in root[1:]:
        if isinstance(node, list) and len(node) == 3 and node[0] == "net" \
                and isinstance(node[1], int) and isinstance(node[2], str):
            declared[node[1]] = node[2]

    # --- copper usage: which nets appear in segments / vias / pads / zones -
    used_nets = set()
    segments = []
    for seg in find_nodes(root, "segment"):
        net = child_value(seg, "net", 1)
        if isinstance(net, int):
            used_nets.add(net)
        start = child(seg, "start")
        end = child(seg, "end")
        width = child_value(seg, "width", 1)
        layer = child_value(seg, "layer", 1, "")
        if start and end and isinstance(width, (int, float)):
            segments.append({
                "net": net,
                "start": (float(start[1]), float(start[2])),
                "end": (float(end[1]), float(end[2])),
                "width": float(width),
                "layer": layer,
            })
    vias = []
    for via in find_nodes(root, "via"):
        net = child_value(via, "net", 1)
        if isinstance(net, int):
            used_nets.add(net)
        at = child(via, "at")
        size = child_value(via, "size", 1)
        drill = child_value(via, "drill", 1)
        if at and isinstance(size, (int, float)):
            vias.append({
                "net": net,
                "at": (float(at[1]), float(at[2])),
                "size": float(size),
                "drill": float(drill) if isinstance(drill, (int, float)) else None,
            })
    for pad in find_nodes(root, "pad"):
        net = child_value(pad, "net", 1)
        if isinstance(net, int):
            used_nets.add(net)
    for zone in find_nodes(root, "zone"):
        net = child_value(zone, "net", 1)
        if isinstance(net, int):
            used_nets.add(net)

    # --- check 1: unrouted nets --------------------------------------------
    for net_id in sorted(declared):
        name = declared[net_id]
        if net_id == 0:  # net 0 is the empty net, always unused by design
            continue
        if net_id not in used_nets:
            findings.append(Finding(
                "error", "unrouted-net",
                f"net {net_id} '{name}' is declared but has no copper "
                "(no segment, via, pad or zone) — unrouted net",
                f"net {net_id}"))

    # --- check 2: trace width ----------------------------------------------
    for seg in segments:
        if seg["width"] < min_trace:
            name = declared.get(seg["net"], str(seg["net"]))
            findings.append(Finding(
                "error", "trace-width",
                f"trace on net '{name}' is {seg['width']:.3f} mm wide, "
                f"below the design-to minimum {min_trace:.2f} mm",
                f"({seg['start'][0]:.2f}, {seg['start'][1]:.2f}) -> "
                f"({seg['end'][0]:.2f}, {seg['end'][1]:.2f}) {seg['layer']}"))

    # --- check 3: via drill / pad / annular ring ---------------------------
    for via in vias:
        name = declared.get(via["net"], str(via["net"]))
        loc = f"via at ({via['at'][0]:.2f}, {via['at'][1]:.2f}) net '{name}'"
        if via["size"] < min_via_pad:
            findings.append(Finding(
                "error", "via-pad",
                f"via pad {via['size']:.3f} mm below minimum {min_via_pad:.2f} mm",
                loc))
        if via["drill"] is not None and via["drill"] < min_drill:
            findings.append(Finding(
                "error", "via-drill",
                f"via drill {via['drill']:.3f} mm below minimum {min_drill:.2f} mm",
                loc))
        if via["drill"] is not None:
            ring = (via["size"] - via["drill"]) / 2.0
            if ring < min_ring:
                findings.append(Finding(
                    "error", "annular-ring",
                    f"via annular ring {ring:.3f} mm below minimum {min_ring:.2f} mm",
                    loc))

    # --- check 4: 90-degree corners ----------------------------------------
    by_net = {}
    for seg in segments:
        by_net.setdefault(seg["net"], []).append(seg)
    for net_id, segs in by_net.items():
        name = declared.get(net_id, str(net_id))
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                a, b = segs[i], segs[j]
                shared = None
                for pa in (a["start"], a["end"]):
                    for pb in (b["start"], b["end"]):
                        if abs(pa[0] - pb[0]) < 0.001 and abs(pa[1] - pb[1]) < 0.001:
                            shared = pa
                if shared is None:
                    continue
                va = (a["start"] if a["end"] == shared else a["end"])
                vb = (b["start"] if b["end"] == shared else b["end"])
                da = (va[0] - shared[0], va[1] - shared[1])
                db = (vb[0] - shared[0], vb[1] - shared[1])
                la = math.hypot(*da)
                lb = math.hypot(*db)
                if la == 0 or lb == 0:
                    continue
                cosang = max(-1.0, min(1.0, (da[0] * db[0] + da[1] * db[1]) / (la * lb)))
                angle = math.degrees(math.acos(cosang))
                if 80.0 <= angle <= 100.0:
                    findings.append(Finding(
                        "warning", "corner-90",
                        f"90-degree corner on net '{name}' — use 45-degree "
                        "corners or arcs instead",
                        f"at ({shared[0]:.2f}, {shared[1]:.2f})"))

    # --- check 5: copper too close to the board edge -----------------------
    edge_lines = []
    for line in find_nodes(root, "gr_line"):
        if child_value(line, "layer", 1) == "Edge.Cuts":
            start = child(line, "start")
            end = child(line, "end")
            if start and end:
                edge_lines.append(((float(start[1]), float(start[2])),
                                   (float(end[1]), float(end[2]))))
    if edge_lines:
        xs = [p[0] for seg in edge_lines for p in seg]
        ys = [p[1] for seg in edge_lines for p in seg]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        points = []
        for seg in segments:
            name = declared.get(seg["net"], str(seg["net"]))
            points.append((seg["start"], f"trace on net '{name}'"))
            points.append((seg["end"], f"trace on net '{name}'"))
        for via in vias:
            name = declared.get(via["net"], str(via["net"]))
            points.append((via["at"], f"via on net '{name}'"))
        for (x, y), what in points:
            dist = min(x - bbox[0], bbox[2] - x, y - bbox[1], bbox[3] - y)
            if dist < edge_clear:
                findings.append(Finding(
                    "warning", "copper-to-edge",
                    f"{what} is {dist:.2f} mm from the board edge, "
                    f"below {edge_clear:.2f} mm",
                    f"at ({x:.2f}, {y:.2f})"))
    else:
        skipped.append("copper-to-edge (no Edge.Cuts outline found in file)")

    stats = {
        "nets_declared": len(declared),
        "nets_with_copper": len(used_nets & set(declared)),
        "segments": len(segments),
        "vias": len(vias),
    }
    return findings, stats, skipped


class SetupError(Exception):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="DRC checks on a KiCad .kicad_pcb file.")
    ap.add_argument("board", help="path to the .kicad_pcb file")
    ap.add_argument("--config", default=None,
                    help="path to config.json (default: config.json next to this script)")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    args = ap.parse_args(argv)

    board_path = Path(args.board)
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir / "config.json"

    checks_run = ["unrouted-net", "trace-width", "via-drill",
                  "via-pad", "annular-ring", "corner-90", "copper-to-edge"]
    skipped = []
    started = datetime.now(timezone.utc).isoformat()

    try:
        if not board_path.is_file():
            raise SetupError(f"board file not found: {board_path}")
        if not config_path.is_file():
            raise SetupError(f"config file not found: {config_path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        findings, stats, skipped = check_board(board_path, config)
    except SetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        print("--- AUDIT LOG ---")
        print(f"script: {SCRIPT} v{VERSION}")
        print(f"started: {started} UTC")
        print(f"input: {board_path} (not read)")
        print(f"config: {config_path}")
        print("checks run: none — setup failed")
        print("result: SETUP ERROR (exit 2)")
        return 2

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    if args.json:
        print(json.dumps({
            "script": SCRIPT, "version": VERSION,
            "board": str(board_path),
            "stats": stats,
            "findings": [{"severity": f.severity, "check": f.check,
                          "message": f.message, "location": f.location}
                         for f in findings],
            "skipped": skipped,
            "errors": len(errors), "warnings": len(warnings),
        }, indent=2))
    else:
        if findings:
            for f in findings:
                print(f.text())
        else:
            print("No findings — board passes all checks.")
        print()
        print(f"Board: {stats['nets_declared']} nets declared, "
              f"{stats['nets_with_copper']} with copper, "
              f"{stats['segments']} segments, {stats['vias']} vias.")
        print(f"Result: {len(errors)} error(s), {len(warnings)} warning(s).")

    print("--- AUDIT LOG ---")
    print(f"script: {SCRIPT} v{VERSION}")
    print(f"started: {started} UTC")
    print(f"input: {board_path} (sha256 {sha256_of(board_path)[:16]}...)")
    print(f"config: {config_path} (sha256 {sha256_of(config_path)[:16]}...)")
    print(f"checks run: {', '.join(checks_run)}")
    print(f"checks skipped: {'; '.join(skipped) if skipped else 'none'}")
    print(f"findings: {len(errors)} error(s), {len(warnings)} warning(s)")
    print(f"result: {'FAIL' if errors else 'PASS'} (exit {1 if errors else 0})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

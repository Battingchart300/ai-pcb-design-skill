#!/usr/bin/env python3
"""fix_corners.py — automatically chamfer 90-degree trace corners to 45
degrees in a KiCad .kicad_pcb file.

The skill requires 45-degree corners (or smooth arcs), never 90 degrees:
a 90-degree corner is an impedance discontinuity and, in older etching,
an acid trap. drc_check.py finds the corners; this script fixes them.

How a corner is fixed: at a vertex where two segments of the same net
and layer meet at 90 degrees, each segment is shortened by the chamfer
length and a diagonal segment is inserted between the two cut points.
The result is two 135-degree bends instead of one 90-degree corner.

Chamfer length = min(config chamfer_mm, half of the shorter segment).
Chamfering is done on the working geometry one corner at a time, so a
segment with a corner at both ends can never be over-consumed.

Safety (skill rule G8 — never destroy the user's work):
  - The input file is NEVER overwritten by default. The fixed board is
    written to <name>.fixed.kicad_pcb (or --output).
  - --in-place is allowed only with an automatic backup <name>.bak
    written before the input is touched. If nothing needs fixing,
    --in-place does not touch the file at all.
  - --dry-run prints what would change and writes nothing.
  - Acute angles (< 90 degrees) are NOT fixed — they are reported as
    manual work. The script never moves components, vias or pads, and
    never changes a net, a width or a layer.

After fixing, always re-run drc_check.py on the output: the corner-90
warnings must be 0. A human reviews the result before the board is
used (the fix is a proposal, not a proof).

Usage:
    python fix_corners.py board.kicad_pcb [--config config.json]
                         [--output fixed.kicad_pcb] [--in-place] [--dry-run]

Exit codes: 0 = fixed, or nothing to fix; 1 = parse error;
2 = setup missing (file not found, unparseable file, bad config).

Standard library only. Works on Windows, macOS and Linux.
"""

import argparse
import hashlib
import json
import math
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.2.1"
SCRIPT = "fix_corners"

MIN_CHAMFER_MM = 0.05  # a chamfer shorter than this is not worth cutting
ANGLE_TOL_DEG = 10.0   # a corner is 90 degrees if within 90 +/- this


class QStr(str):
    """A string that was quoted in the source file. Quoted strings must
    stay quoted when the file is written back (KiCad expects net names
    and layer names quoted); plain symbols stay unquoted."""


# ---------------------------------------------------------------------------
# Minimal S-expression parser for KiCad files (same as drc_check.py)
# ---------------------------------------------------------------------------

def tokenize(text):
    """Split KiCad S-expression text into tokens: '(', ')', quoted strings,
    and atoms. Quoted strings keep their quotes stripped and are tagged
    so they are not confused with symbols."""
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
            return QStr(tok[1])
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


def fmt_num(value):
    """Format a coordinate/value the way KiCad writes it: plain decimal,
    up to 6 places, no trailing zeros, never scientific notation."""
    if isinstance(value, int):
        return str(value)
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def sexp_str(node):
    """Serialise a parsed S-expression node back to KiCad text.
    Quoted strings (QStr) are written back quoted; symbols unquoted."""
    if isinstance(node, list):
        return "(" + " ".join(sexp_str(item) for item in node) + ")"
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, int):
        return str(node)
    if isinstance(node, float):
        return fmt_num(node)
    if isinstance(node, QStr):
        return '"' + str(node).replace("\\", "\\\\").replace('"', '\\"') + '"'
    text = str(node)
    if re.fullmatch(r"[A-Za-z0-9_.\-+*/%<>=:]+", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def segment_spans(raw):
    """Find the raw-text span (start, end) of every top-level `(segment`
    node, in document order. Returns a list of (start, end) offsets."""
    spans = []
    for match in re.finditer(r"\(segment\b", raw):
        depth = 0
        i = match.start()
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch == '"':
                i += 1
                while i < n:
                    if raw[i] == "\\":
                        i += 2
                    elif raw[i] == '"':
                        i += 1
                        break
                    else:
                        i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    spans.append((match.start(), i + 1))
                    break
            i += 1
        else:
            raise ValueError("unbalanced parentheses in segment node")
    return spans


# ---------------------------------------------------------------------------
# Corner fixing
# ---------------------------------------------------------------------------

class SetupError(Exception):
    pass


class ParseError(Exception):
    """The file exists but is not a parseable .kicad_pcb — exit 1,
    distinct from a missing file (exit 2)."""
    pass


def angle_between(da, db):
    """Angle in degrees between two direction vectors."""
    la = math.hypot(*da)
    lb = math.hypot(*db)
    if la == 0 or lb == 0:
        return None
    cosang = max(-1.0, min(1.0, (da[0] * db[0] + da[1] * db[1]) / (la * lb)))
    return math.degrees(math.acos(cosang))


def fix_board(path, config):
    """Find and chamfer 90-degree corners.

    Returns (fixed_text, report) where report has:
      fixed: list of (net_name, vertex, chamfer_mm)
      acute: list of (net_name, vertex, angle_deg) — manual work
      skipped_short: list of (net_name, vertex) — chamfer too small
      ambiguous: list of (net_name, vertex) — 3+ segments at one vertex
      segments_total: number of segments found
    Raises SetupError on unreadable / unparseable input.
    """
    corner_cfg = config.get("corner_fix", {})
    chamfer_cfg = float(corner_cfg.get("chamfer_mm", 0.5))
    enabled = bool(corner_cfg.get("enabled", True))

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SetupError(f"cannot read board file: {exc}")

    try:
        tree = parse_sexp(raw)
    except ValueError as exc:
        raise ParseError(f"cannot parse .kicad_pcb (not a valid S-expression file?): {exc}")

    if not tree or not isinstance(tree[0], list) or tree[0][0] != "kicad_pcb":
        raise ParseError("file does not look like a KiCad .kicad_pcb (no (kicad_pcb ...) root)")

    root = tree[0]

    declared = {}
    for node in root[1:]:
        if isinstance(node, list) and len(node) == 3 and node[0] == "net" \
                and isinstance(node[1], int) and isinstance(node[2], str):
            declared[node[1]] = node[2]

    # --- collect segments in document order, with their raw spans ---------
    seg_nodes = list(find_nodes(root, "segment"))
    try:
        spans = segment_spans(raw)
    except ValueError as exc:
        raise ParseError(f"cannot locate segment nodes in file: {exc}")
    if len(spans) != len(seg_nodes):
        raise ParseError(
            f"segment count mismatch: parsed {len(seg_nodes)} segments but "
            f"found {len(spans)} in the raw text — refusing to edit")

    segments = []  # working list; each item tracks its origin span
    for idx, node in enumerate(seg_nodes):
        start = child(node, "start")
        end = child(node, "end")
        width = child_value(node, "width", 1)
        layer = child_value(node, "layer", 1, "")
        net = child_value(node, "net", 1)
        if not start or not end or not isinstance(width, (int, float)):
            continue  # malformed segment: leave it alone, do not touch
        segments.append({
            "origin": idx,
            "node": node,
            "net": net,
            "layer": layer,
            "start": (float(start[1]), float(start[2])),
            "end": (float(end[1]), float(end[2])),
            "width": float(width),
        })

    # Current serialised text per origin span, and diagonals to insert
    # after a span. Untouched spans keep their original text.
    current_text = {idx: raw[s:e] for idx, (s, e) in enumerate(spans)}
    insert_after = {idx: [] for idx in range(len(spans))}

    fixed = []          # (net_name, vertex, chamfer_mm)
    acute = []          # (net_name, vertex, angle) — manual work
    skipped_short = []  # (net_name, vertex) — chamfer below 0.05 mm
    ambiguous = []      # (net_name, vertex) — 3+ segments at one vertex
    handled = set()     # vertices already reported as acute/ambiguous/
                        # too short — their angles never change, so the
                        # loop must not retry them forever

    def vertex_key(point):
        return (round(point[0], 3), round(point[1], 3))

    def build_index():
        index = {}
        for si, seg in enumerate(segments):
            for point in (seg["start"], seg["end"]):
                key = (seg["net"], seg["layer"], vertex_key(point))
                index.setdefault(key, []).append(si)
        return index

    def set_node_point(node, head, point):
        c = child(node, head)
        if c is not None and len(c) >= 3:
            c[1] = point[0]
            c[2] = point[1]

    if not enabled:
        report = {"fixed": fixed, "acute": acute,
                  "skipped_short": skipped_short, "ambiguous": ambiguous,
                  "segments_total": len(segments), "disabled": True}
        return raw, report

    # --- fix loop: one corner at a time, recomputing geometry each time --
    # Each fix removes one 90-degree vertex and creates two 135-degree
    # vertices, so the number of 90-degree corners strictly decreases
    # and the loop always terminates.
    while True:
        index = build_index()
        target = None
        for key in sorted(index):
            if key in handled:
                continue
            members = index[key]
            net_id, layer, point = key
            if len(members) > 2:
                handled.add(key)
                ambiguous.append(
                    (declared.get(net_id, str(net_id)), point))
                continue
            if len(members) != 2:
                continue
            a, b = segments[members[0]], segments[members[1]]
            vertex = point

            # pick the endpoint of each segment that is NOT the vertex
            def other_end(seg):
                if abs(seg["start"][0] - vertex[0]) < 0.001 \
                        and abs(seg["start"][1] - vertex[1]) < 0.001:
                    return seg["end"]
                return seg["start"]
            va = other_end(a)
            vb = other_end(b)
            da = (va[0] - vertex[0], va[1] - vertex[1])
            db = (vb[0] - vertex[0], vb[1] - vertex[1])
            angle = angle_between(da, db)
            if angle is None:
                handled.add(key)
                continue
            if 90.0 - ANGLE_TOL_DEG <= angle <= 90.0 + ANGLE_TOL_DEG:
                target = (key, members, vertex, va, vb, angle)
                break
            # Not a 90-degree corner: acute angles are reported once,
            # wider bends are simply not corners — either way the angle
            # at this vertex never changes, so mark it handled.
            handled.add(key)
            if angle < 90.0 - ANGLE_TOL_DEG:
                acute.append((declared.get(net_id, str(net_id)),
                              vertex, angle))
        if target is None:
            break

        key, members, vertex, va, vb, _angle = target
        net_id, layer, _point = key
        a, b = segments[members[0]], segments[members[1]]
        la = math.hypot(va[0] - vertex[0], va[1] - vertex[1])
        lb = math.hypot(vb[0] - vertex[0], vb[1] - vertex[1])
        chamfer = min(chamfer_cfg, la / 2.0, lb / 2.0)
        if chamfer < MIN_CHAMFER_MM:
            handled.add(key)
            skipped_short.append((declared.get(net_id, str(net_id)), vertex))
            continue

        ua = ((va[0] - vertex[0]) / la, (va[1] - vertex[1]) / la)
        ub = ((vb[0] - vertex[0]) / lb, (vb[1] - vertex[1]) / lb)
        cut_a = (vertex[0] + ua[0] * chamfer, vertex[1] + ua[1] * chamfer)
        cut_b = (vertex[0] + ub[0] * chamfer, vertex[1] + ub[1] * chamfer)

        # Shorten the two segments: replace the vertex end with the cut.
        def shorten(seg, vertex, cut):
            if abs(seg["start"][0] - vertex[0]) < 0.001 \
                    and abs(seg["start"][1] - vertex[1]) < 0.001:
                seg["start"] = cut
                set_node_point(seg["node"], "start", cut)
            else:
                seg["end"] = cut
                set_node_point(seg["node"], "end", cut)
            current_text[seg["origin"]] = sexp_str(seg["node"])

        shorten(a, vertex, cut_a)
        shorten(b, vertex, cut_b)

        # Diagonal between the two cut points.
        diag_width = min(a["width"], b["width"])
        diag_net = a["net"] if a["net"] is not None else b["net"]
        if isinstance(diag_net, int):
            net_child = ["net", diag_net, declared.get(diag_net, "")]
        elif diag_net is not None:
            net_child = ["net", diag_net]
        else:
            net_child = None
        diag_node = [
            "segment",
            ["start", cut_a[0], cut_a[1]],
            ["end", cut_b[0], cut_b[1]],
            ["width", diag_width],
            ["layer", a["layer"]],
        ]
        if net_child is not None:
            diag_node.append(net_child)
        diag_node.append(["tstamp", str(uuid.uuid4())])
        diag_text = sexp_str(diag_node)
        # Insert after the later of the two origin spans in the file.
        after = a["origin"] if spans[a["origin"]][1] >= spans[b["origin"]][1] \
            else b["origin"]
        insert_after[after].append(diag_text)

        fixed.append((declared.get(net_id, str(net_id)), vertex, chamfer))

        # Replace the two consumed segments in the working list with
        # their shortened versions plus the new diagonal.
        diag_seg = {
            "origin": None,
            "node": diag_node,
            "net": a["net"],
            "layer": a["layer"],
            "start": cut_a,
            "end": cut_b,
            "width": diag_width,
        }
        keep = [s for i, s in enumerate(segments)
                if i not in (members[0], members[1])]
        keep.extend([a, b, diag_seg])
        segments = keep

    # --- rebuild the file text from the original, with replacements ------
    parts = []
    pos = 0
    for idx, (s, e) in enumerate(spans):
        parts.append(raw[pos:s])
        parts.append(current_text[idx])
        for diag in insert_after[idx]:
            parts.append("\n  " + diag)
        pos = e
    parts.append(raw[pos:])
    fixed_text = "".join(parts)

    report = {"fixed": fixed, "acute": acute,
              "skipped_short": skipped_short, "ambiguous": ambiguous,
              "segments_total": len(seg_nodes), "disabled": False}
    return fixed_text, report


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Chamfer 90-degree trace corners to 45 degrees in a "
                    "KiCad .kicad_pcb file.")
    ap.add_argument("board", help="path to the .kicad_pcb file")
    ap.add_argument("--config", default=None,
                    help="path to config.json (default: config.json next to this script)")
    ap.add_argument("--output", default=None,
                    help="output path (default: <name>.fixed.kicad_pcb next to the input)")
    ap.add_argument("--in-place", action="store_true",
                    help="overwrite the input file (writes <name>.bak backup first)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would change, write nothing")
    args = ap.parse_args(argv)

    board_path = Path(args.board)
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir / "config.json"

    started = datetime.now(timezone.utc).isoformat()
    dry_run = args.dry_run
    in_place = args.in_place and not dry_run

    if args.output:
        out_path = Path(args.output)
    elif in_place:
        out_path = board_path
    else:
        out_path = board_path.with_name(board_path.stem + ".fixed.kicad_pcb")

    try:
        if not board_path.is_file():
            raise SetupError(f"board file not found: {board_path}")
        if not config_path.is_file():
            raise SetupError(f"config file not found: {config_path}")
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise SetupError(f"cannot read config file: {exc}")
        input_sha = sha256_of(board_path)  # before any write happens
        fixed_text, report = fix_board(board_path, config)
    except ParseError as exc:
        print(f"PARSE ERROR: {exc}", file=sys.stderr)
        print("--- AUDIT LOG ---")
        print(f"script: {SCRIPT} v{VERSION}")
        print(f"started: {started} UTC")
        print(f"input: {board_path} (not fixed)")
        print(f"config: {config_path}")
        print("result: PARSE ERROR (exit 1)")
        return 1
    except SetupError as exc:
        print(f"SETUP ERROR: {exc}", file=sys.stderr)
        print("--- AUDIT LOG ---")
        print(f"script: {SCRIPT} v{VERSION}")
        print(f"started: {started} UTC")
        print(f"input: {board_path} (not read)")
        print(f"config: {config_path}")
        print("result: SETUP ERROR (exit 2)")
        return 2

    fixed_count = len(report["fixed"])
    acute_count = len(report["acute"])

    if report.get("disabled"):
        print("Corner fix is DISABLED in config.json (corner_fix.enabled "
              "= false) — nothing was changed.")
    elif fixed_count:
        for net_name, vertex, chamfer in report["fixed"]:
            print(f"FIXED   corner-90 on net '{net_name}' at "
                  f"({vertex[0]:.2f}, {vertex[1]:.2f}) — "
                  f"chamfer {chamfer:.2f} mm")
    else:
        print("No 90-degree corners to fix.")
    for net_name, vertex, angle in report["acute"]:
        print(f"MANUAL  acute corner ({angle:.0f} degrees) on net "
              f"'{net_name}' at ({vertex[0]:.2f}, {vertex[1]:.2f}) — "
              "fix by hand, the script does not touch acute angles")
    for net_name, vertex in report["skipped_short"]:
        print(f"MANUAL  corner on net '{net_name}' at "
              f"({vertex[0]:.2f}, {vertex[1]:.2f}) — segment too short "
              "to chamfer, fix by hand")
    for net_name, vertex in report["ambiguous"]:
        print(f"MANUAL  vertex on net '{net_name}' at "
              f"({vertex[0]:.2f}, {vertex[1]:.2f}) — 3+ segments meet "
              "here, fix by hand")

    wrote = None
    backup = None
    if not dry_run and not report.get("disabled"):
        if fixed_count:
            if in_place:
                backup = board_path.with_name(board_path.name + ".bak")
                backup.write_bytes(board_path.read_bytes())
                out_path.write_text(fixed_text, encoding="utf-8")
                wrote = out_path
            else:
                out_path.write_text(fixed_text, encoding="utf-8")
                wrote = out_path
        else:
            # Nothing to fix: do not touch the input, write no output.
            wrote = None
    if dry_run:
        print(f"\nDRY RUN — would fix {fixed_count} corner(s), "
              f"write to: {out_path}")

    print()
    print(f"Corners fixed: {fixed_count}")
    if fixed_count:
        per_net = {}
        for net_name, _vertex, _ch in report["fixed"]:
            per_net[net_name] = per_net.get(net_name, 0) + 1
        print("Fixed per net: " + ", ".join(
            f"{name}: {count}" for name, count in sorted(per_net.items())))
    print(f"Acute corners reported (manual): {acute_count}")

    print("--- AUDIT LOG ---")
    print(f"script: {SCRIPT} v{VERSION}")
    print(f"started: {started} UTC")
    print(f"input: {board_path} (sha256 {input_sha[:16]}...)")
    print(f"config: {config_path} (sha256 {sha256_of(config_path)[:16]}...)")
    if wrote is not None:
        print(f"output: {wrote} (sha256 {sha256_text(fixed_text)[:16]}...)")
        if backup is not None:
            print(f"backup: {backup} (sha256 {sha256_of(backup)[:16]}...)")
    elif dry_run:
        print("output: none (dry run)")
    else:
        print("output: none (nothing to fix)")
    print(f"segments in file: {report['segments_total']}")
    print(f"corners fixed: {fixed_count}")
    print(f"acute corners (manual): {acute_count}")
    print(f"skipped (too short): {len(report['skipped_short'])}")
    print(f"ambiguous vertices (manual): {len(report['ambiguous'])}")
    print(f"result: {'FIXED' if fixed_count else 'NO CHANGE'} (exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

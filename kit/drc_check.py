#!/usr/bin/env python3
"""drc_check.py — design-rule checks on a KiCad .kicad_pcb file.

Checks (all values come from config.json, defaults are the skill's
design-to values):
  1. Unrouted / unconnected nets — a declared net with no copper at all.
  2. Trace width below the design-to minimum.
  3. Via drill / pad below the minimum, annular ring too small.
  4. 90-degree trace corners (45-degree / arc corners only).
  5. Copper closer to the board edge than the allowed distance.
  6. Clearance and shorts — copper of DIFFERENT nets on the SAME layer
     closer than min_clearance_mm (error), or touching/overlapping
     (distance <= 0, reported as a short, error). Covers segments,
     arcs (subdivided into short straight chords), vias and pads
     (circle, oval, rectangular — roundrect is approximated by its
     bounding rectangle). Copper pours (zones) are NOT covered, and
     custom-shaped pads are skipped — see "Limits" below.

Limits of check 6 (be honest about them):
  - Zones (copper pours) are skipped entirely — a pour is one big
    copper area and this script does not compute pour geometry.
    kicad-cli DRC covers pours.
  - Arcs are approximated by straight chords (max 0.3 mm each), so a
    clearance measured on a chord is within a fraction of the true
    arc clearance.
  - Roundrect pads are checked as their bounding rectangle (slightly
    conservative at the corners); custom pads are skipped.
  - Copper with no net (net 0 / unassigned, e.g. mounting-hole pads)
    is skipped — it is often intentionally connected (grounded
    mounting holes), so flagging it would be a false positive.

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

VERSION = "1.2.3"
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
# 2D geometry helpers for the clearance / short check (check 6)
# All distances are edge-to-edge in mm. A distance <= 0 means the copper
# touches or overlaps (a short between different nets).
# ---------------------------------------------------------------------------

EPS = 1e-9


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _len(v):
    return math.hypot(v[0], v[1])


def point_seg(p, a, b):
    """Distance from point p to segment a-b. Returns (dist, closest)."""
    ab = _sub(b, a)
    denom = _dot(ab, ab)
    if denom == 0:
        return _len(_sub(p, a)), a
    t = max(0.0, min(1.0, _dot(_sub(p, a), ab) / denom))
    closest = (a[0] + t * ab[0], a[1] + t * ab[1])
    return _len(_sub(p, closest)), closest


def _on_segment(p, a, b):
    """True if p lies on segment a-b (within EPS)."""
    if abs(_cross(_sub(p, a), _sub(b, a))) > 1e-7:
        return False
    return (min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS and
            min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS)


def _segments_intersect(a, b, c, d):
    """True if segments a-b and c-d intersect (including touching)."""
    d1 = _cross(_sub(d, c), _sub(a, c))
    d2 = _cross(_sub(d, c), _sub(b, c))
    d3 = _cross(_sub(b, a), _sub(c, a))
    d4 = _cross(_sub(b, a), _sub(d, a))
    if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and \
       ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)):
        return True
    if abs(d1) <= EPS and _on_segment(a, c, d):
        return True
    if abs(d2) <= EPS and _on_segment(b, c, d):
        return True
    if abs(d3) <= EPS and _on_segment(c, a, b):
        return True
    if abs(d4) <= EPS and _on_segment(d, a, b):
        return True
    return False


def seg_seg(a, b, c, d):
    """Distance between segments a-b and c-d. Returns (dist, pt_on_ab,
    pt_on_cd). 0.0 when they intersect or touch."""
    if _segments_intersect(a, b, c, d):
        # Find one intersection point: use a point that lies on both,
        # or the midpoint of the closest endpoints as a fallback.
        for p in (a, b):
            if _on_segment(p, c, d):
                return 0.0, p, p
        for p in (c, d):
            if _on_segment(p, a, b):
                return 0.0, p, p
        return 0.0, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), \
            ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)
    best = None
    for p, s1, s2 in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)):
        dist, closest = point_seg(p, s1, s2)
        if best is None or dist < best[0]:
            if p in (a, b):
                best = (dist, p, closest)
            else:
                best = (dist, closest, p)
    return best


def point_in_poly(p, poly):
    """Ray-casting point-in-polygon test. Points on an edge count as
    inside (they touch the copper). Works for any simple polygon."""
    inside = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if _on_segment(p, a, b):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            xinters = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < xinters:
                inside = not inside
    return inside


def obj_distance(o1, o2):
    """Edge-to-edge distance between two copper objects. Returns
    (dist, point_on_o1, point_on_o2). dist <= 0 means touching/overlap.
    Object kinds: 'capsule' {a, b, r}, 'circle' {c, r}, 'poly' {pts}."""
    k1, k2 = o1["kind"], o2["kind"]
    if k1 == "circle" and k2 == "circle":
        d = _len(_sub(o1["c"], o2["c"])) - o1["r"] - o2["r"]
        if _len(_sub(o1["c"], o2["c"])) < EPS:
            return d, o1["c"], o2["c"]
        ux = (o2["c"][0] - o1["c"][0]) / _len(_sub(o2["c"], o1["c"]))
        uy = (o2["c"][1] - o1["c"][1]) / _len(_sub(o2["c"], o1["c"]))
        p1 = (o1["c"][0] + ux * o1["r"], o1["c"][1] + uy * o1["r"])
        p2 = (o2["c"][0] - ux * o2["r"], o2["c"][1] - uy * o2["r"])
        return d, p1, p2
    if k1 == "capsule" and k2 == "capsule":
        d, p1, p2 = seg_seg(o1["a"], o1["b"], o2["a"], o2["b"])
        return d - o1["r"] - o2["r"], p1, p2
    if k1 == "capsule" and k2 == "circle":
        d, closest = point_seg(o2["c"], o1["a"], o1["b"])
        return d - o1["r"] - o2["r"], closest, o2["c"]
    if k1 == "circle" and k2 == "capsule":
        d, p2, p1 = obj_distance(o2, o1)
        return d, p1, p2
    if k1 == "poly" and k2 == "poly":
        return _poly_poly(o1["pts"], o2["pts"])
    if k1 == "poly" and k2 in ("capsule", "circle"):
        d, p1, p2 = _poly_other(o1["pts"], o2)
        return d, p1, p2
    if k2 == "poly" and k1 in ("capsule", "circle"):
        d, p2, p1 = _poly_other(o2["pts"], o1)
        return d, p1, p2
    raise ValueError(f"unknown object kinds: {k1}, {k2}")


def _poly_poly(pts1, pts2):
    """Distance between two polygons (convex rects in practice)."""
    for i in range(len(pts1)):
        for j in range(len(pts2)):
            if _segments_intersect(pts1[i], pts1[(i + 1) % len(pts1)],
                                   pts2[j], pts2[(j + 1) % len(pts2)]):
                p = pts1[i]
                return 0.0, p, p
    for p in pts1:
        if point_in_poly(p, pts2):
            return 0.0, p, p
    for p in pts2:
        if point_in_poly(p, pts1):
            return 0.0, p, p
    best = None
    for i in range(len(pts1)):
        for j in range(len(pts2)):
            d, p1, p2 = seg_seg(pts1[i], pts1[(i + 1) % len(pts1)],
                                pts2[j], pts2[(j + 1) % len(pts2)])
            if best is None or d < best[0]:
                best = (d, p1, p2)
    return best


def _poly_other(poly, other):
    """Distance between a polygon and a capsule/circle object.
    Returns (dist, point_on_poly, point_on_other)."""
    if other["kind"] == "capsule":
        a, b, r = other["a"], other["b"], other["r"]
        if point_in_poly(a, poly) or point_in_poly(b, poly):
            p = a if point_in_poly(a, poly) else b
            return 0.0, p, p
        for i in range(len(poly)):
            if _segments_intersect(a, b, poly[i], poly[(i + 1) % len(poly)]):
                for p in (a, b):
                    if _on_segment(p, poly[i], poly[(i + 1) % len(poly)]):
                        return 0.0, p, p
                return 0.0, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), \
                    ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        best = None
        for i in range(len(poly)):
            d, p1, p2 = seg_seg(a, b, poly[i], poly[(i + 1) % len(poly)])
            if best is None or d < best[0]:
                best = (d - r, p2, p1)
        for p in poly:
            d, closest = point_seg(p, a, b)
            if best is None or d - r < best[0]:
                best = (d - r, p, closest)
        return best
    # circle
    c, r = other["c"], other["r"]
    if point_in_poly(c, poly):
        return 0.0, c, c
    best = None
    for i in range(len(poly)):
        d, closest = point_seg(c, poly[i], poly[(i + 1) % len(poly)])
        if best is None or d - r < best[0]:
            best = (d - r, closest, c)
    return best


def rotate(pt, angle_deg):
    """Rotate a point by angle_deg (standard math rotation,
    counter-clockwise in a Y-up system). Callers pass KiCad angles
    already negated, because KiCad's board coordinates are Y-down:
    a positive KiCad angle rotates clockwise in file coordinates.

    Two KiCad conventions this function relies on (both verified
    2026-11-24 on the Olimex ESP32-EVB, where the old code reported
    693 false shorts and the fixed code reports 1):
      1. A footprint's (at x y angle) rotates its pads' POSITIONS
         by -angle (Y-down sign flip).
      2. A pad's own (at x y angle) is its ABSOLUTE orientation in
         board coordinates — KiCad stores it absolute and updates it
         when the footprint rotates — so a pad SHAPE rotates by
         -pad_angle alone, NOT by footprint_angle + pad_angle.
         (The old code used footprint + pad angle and mirrored every
         rotated rect/oval pad onto its neighbours.)"""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return (pt[0] * cos_a - pt[1] * sin_a,
            pt[0] * sin_a + pt[1] * cos_a)


def arc_chords(start, mid, end, max_chord=0.3):
    """Subdivide a KiCad arc (start/mid/end points) into straight chords
    of at most max_chord mm. Returns a list of (a, b) point pairs.
    Degenerate (collinear) arcs become one straight start->end chord."""
    v1 = _sub(mid, start)
    v2 = _sub(end, mid)
    if abs(_cross(v1, v2)) < 1e-9:
        return [(start, end)]
    # Circumcentre of the three points.
    d = 2 * (start[0] * (mid[1] - end[1]) + mid[0] * (end[1] - start[1]) +
             end[0] * (start[1] - mid[1]))
    if abs(d) < 1e-12:
        return [(start, end)]
    sq = lambda p: p[0] * p[0] + p[1] * p[1]
    ux = ((sq(start)) * (mid[1] - end[1]) + (sq(mid)) * (end[1] - start[1]) +
          (sq(end)) * (start[1] - mid[1])) / d
    uy = ((sq(start)) * (end[0] - mid[0]) + (sq(mid)) * (start[0] - end[0]) +
          (sq(end)) * (mid[0] - start[0])) / d
    centre = (ux, uy)
    radius = _len(_sub(start, centre))

    def angle(p):
        return math.atan2(p[1] - centre[1], p[0] - centre[0])

    a0, a1, a2 = angle(start), angle(mid), angle(end)
    # Sweep from a0 to a2 passing through a1.
    sweep = (a2 - a0) % (2 * math.pi)
    mid_rel = (a1 - a0) % (2 * math.pi)
    if mid_rel > sweep:
        sweep = sweep - 2 * math.pi
    steps = max(1, int(math.ceil(abs(sweep) * radius / max_chord)))
    pts = []
    for i in range(steps + 1):
        a = a0 + sweep * i / steps
        pts.append((centre[0] + radius * math.cos(a),
                    centre[1] + radius * math.sin(a)))
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


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
    min_clearance = float(rules.get("min_clearance_mm", 0.20))

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

    # Copper layers declared in the board ((layers ...) section). A layer
    # name ending in ".Cu" is copper; "*.Cu" means "all copper layers".
    copper_layers = set()
    layers_node = child(root, "layers")
    if layers_node:
        for item in layers_node[1:]:
            if isinstance(item, list) and len(item) >= 2 and \
                    isinstance(item[1], str) and item[1].endswith(".Cu"):
                copper_layers.add(item[1])
    if not copper_layers:
        copper_layers = {"F.Cu", "B.Cu"}

    def expand_layers(names):
        """Expand a list of layer names: "*.Cu" becomes all copper
        layers, other names pass through."""
        out = set()
        for name in names:
            if name == "*.Cu":
                out |= copper_layers
            elif isinstance(name, str):
                out.add(name)
        return out

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
        layers = child(via, "layers")
        via_layers = expand_layers(layers[1:]) if layers else set(copper_layers)
        if at and isinstance(size, (int, float)):
            vias.append({
                "net": net,
                "at": (float(at[1]), float(at[2])),
                "size": float(size),
                "drill": float(drill) if isinstance(drill, (int, float)) else None,
                "layers": via_layers,
            })
    # --- arcs: subdivided into short straight chords for check 6 ---------
    arcs = []
    arc_chord_note = False
    for arc in find_nodes(root, "arc"):
        net = child_value(arc, "net", 1)
        if isinstance(net, int):
            used_nets.add(net)
        start = child(arc, "start")
        mid = child(arc, "mid")
        end = child(arc, "end")
        width = child_value(arc, "width", 1)
        layer = child_value(arc, "layer", 1, "")
        if start and mid and end and isinstance(width, (int, float)):
            chords = arc_chords(
                (float(start[1]), float(start[2])),
                (float(mid[1]), float(mid[2])),
                (float(end[1]), float(end[2])))
            for a, b in chords:
                arcs.append({
                    "net": net, "start": a, "end": b,
                    "width": float(width), "layer": layer,
                })
        elif start and end and isinstance(width, (int, float)):
            # Arc without a mid point (old format) — cannot reconstruct
            # the curve reliably; the straight chord is checked instead.
            arcs.append({
                "net": net,
                "start": (float(start[1]), float(start[2])),
                "end": (float(end[1]), float(end[2])),
                "width": float(width), "layer": layer,
            })
            arc_chord_note = True
    if arc_chord_note:
        skipped.append("arc without mid point approximated as straight chord")
    # --- pads: absolute geometry (footprint position + rotation) ----------
    # Pads are collected per footprint because a pad's (at ...) is
    # relative to its footprint. Only copper layers count for check 6.
    pads = []
    pads_no_net = 0
    pads_custom_skipped = 0
    pads_roundrect_approx = 0
    for fp in find_nodes(root, "footprint"):
        fp_at = child(fp, "at")
        if not fp_at:
            continue
        fx, fy = float(fp_at[1]), float(fp_at[2])
        frot = float(fp_at[3]) if len(fp_at) > 3 and isinstance(fp_at[3], (int, float)) else 0.0
        for pad in find_nodes(fp, "pad"):
            net = child_value(pad, "net", 1)
            if isinstance(net, int):
                used_nets.add(net)
            shape = pad[3] if len(pad) > 3 and isinstance(pad[3], str) else ""
            at = child(pad, "at")
            size = child(pad, "size")
            layers = child(pad, "layers")
            if not at or not size:
                continue
            px, py = float(at[1]), float(at[2])
            prot = float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) else 0.0
            sx, sy = float(size[1]), float(size[2])
            cu_layers = set()
            if layers:
                cu_layers = {l for l in expand_layers(layers[1:]) if l.endswith(".Cu")}
            if not cu_layers:
                continue
            if not isinstance(net, int) or net == 0:
                pads_no_net += 1
                continue
            # KiCad Y-down: footprint angle rotates pad positions
            # clockwise in file coordinates -> negate (see rotate()).
            rx, ry = rotate((px, py), -frot)
            cx, cy = fx + rx, fy + ry
            # Pad angle is ABSOLUTE in board coordinates (see rotate()):
            # shape rotation is -prot alone, never frot + prot.
            total_rot = -prot
            base = {"net": net, "layers": cu_layers,
                    "desc": f"pad '{pad[1]}' on net "
                            f"'{declared.get(net, str(net))}'"}
            if shape == "circle":
                pads.append({**base, "kind": "circle", "c": (cx, cy),
                             "r": sx / 2.0})
            elif shape == "oval":
                half = abs(sx - sy) / 2.0
                r = min(sx, sy) / 2.0
                ux, uy = rotate((1.0, 0.0) if sx >= sy else (0.0, 1.0),
                                total_rot)
                pads.append({**base, "kind": "capsule",
                             "a": (cx - ux * half, cy - uy * half),
                             "b": (cx + ux * half, cy + uy * half), "r": r})
            elif shape in ("rect", "roundrect"):
                if shape == "roundrect":
                    pads_roundrect_approx += 1
                hx, hy = sx / 2.0, sy / 2.0
                corners = [rotate((x, y), total_rot) for x, y in
                           ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
                pads.append({**base, "kind": "poly",
                             "pts": [(cx + x, cy + y) for x, y in corners]})
            else:
                # "custom" and anything unknown: not covered.
                pads_custom_skipped += 1
    for pad in find_nodes(root, "pad"):
        net = child_value(pad, "net", 1)
        if isinstance(net, int):
            used_nets.add(net)
    zones_found = 0
    for zone in find_nodes(root, "zone"):
        zones_found += 1
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

    # --- check 6: clearance and shorts (different nets, same layer) -----
    # Copper objects: segments and arc chords are capsules (centreline
    # + half width), vias and round pads are circles, rectangular pads
    # are polygons. Objects with no net (net 0 / unassigned) are skipped
    # — see the module docstring for why.
    def _obj_bbox(o):
        if o["kind"] == "circle":
            cx, cy = o["c"]
            r = o["r"]
            return (cx - r, cy - r, cx + r, cy + r)
        if o["kind"] == "capsule":
            r = o["r"]
            return (min(o["a"][0], o["b"][0]) - r,
                    min(o["a"][1], o["b"][1]) - r,
                    max(o["a"][0], o["b"][0]) + r,
                    max(o["a"][1], o["b"][1]) + r)
        xs = [p[0] for p in o["pts"]]
        ys = [p[1] for p in o["pts"]]
        return (min(xs), min(ys), max(xs), max(ys))

    def _obj_centre(o):
        if o["kind"] == "circle":
            return o["c"]
        if o["kind"] == "capsule":
            return ((o["a"][0] + o["b"][0]) / 2, (o["a"][1] + o["b"][1]) / 2)
        n = len(o["pts"])
        return (sum(p[0] for p in o["pts"]) / n,
                sum(p[1] for p in o["pts"]) / n)

    objects = []
    for seg in segments:
        if not isinstance(seg["net"], int) or seg["net"] == 0:
            continue
        if not seg["layer"].endswith(".Cu"):
            continue
        objects.append({
            "kind": "capsule", "a": seg["start"], "b": seg["end"],
            "r": seg["width"] / 2.0, "layers": {seg["layer"]},
            "net": seg["net"],
            "label": f"trace on net '{declared.get(seg['net'], str(seg['net']))}'",
        })
    for arc in arcs:
        if not isinstance(arc["net"], int) or arc["net"] == 0:
            continue
        if not arc["layer"].endswith(".Cu"):
            continue
        objects.append({
            "kind": "capsule", "a": arc["start"], "b": arc["end"],
            "r": arc["width"] / 2.0, "layers": {arc["layer"]},
            "net": arc["net"],
            "label": f"arc on net '{declared.get(arc['net'], str(arc['net']))}'",
        })
    for via in vias:
        if not isinstance(via["net"], int) or via["net"] == 0:
            continue
        cu = {l for l in via["layers"] if l.endswith(".Cu")}
        if not cu:
            continue
        objects.append({
            "kind": "circle", "c": via["at"], "r": via["size"] / 2.0,
            "layers": cu, "net": via["net"],
            "label": f"via on net '{declared.get(via['net'], str(via['net']))}'",
        })
    for pad in pads:
        objects.append({
            **pad,
            "label": pad["desc"],
        })

    # Spatial grid: only nearby objects can violate clearance, so each
    # object is filed into the 2 mm cells its bounding box (expanded by
    # min_clearance) touches. This keeps the check fast on big boards.
    cell_size = 2.0
    grid = {}
    for idx, obj in enumerate(objects):
        x0, y0, x1, y1 = _obj_bbox(obj)
        x0 -= min_clearance
        y0 -= min_clearance
        x1 += min_clearance
        y1 += min_clearance
        for ix in range(math.floor(x0 / cell_size),
                       math.floor(x1 / cell_size) + 1):
            for iy in range(math.floor(y0 / cell_size),
                           math.floor(y1 / cell_size) + 1):
                grid.setdefault((ix, iy), []).append(idx)
    seen_pairs = set()
    pairs_checked = 0
    for cell_objs in grid.values():
        for i in range(len(cell_objs)):
            for j in range(i + 1, len(cell_objs)):
                a, b = cell_objs[i], cell_objs[j]
                key = (a, b) if a < b else (b, a)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                o1, o2 = objects[a], objects[b]
                if o1["net"] == o2["net"]:
                    continue
                shared = o1["layers"] & o2["layers"]
                if not shared:
                    continue
                pairs_checked += 1
                dist, p1, p2 = obj_distance(o1, o2)
                if dist >= min_clearance - 1e-6:
                    continue
                layer = sorted(shared)[0]
                mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                loc = f"at ({mid[0]:.2f}, {mid[1]:.2f}) on {layer}"
                if dist <= 1e-6:
                    findings.append(Finding(
                        "error", "short",
                        f"{o1['label']} touches {o2['label']} "
                        f"(edge-to-edge distance {dist:.3f} mm — "
                        "different nets are shorted)",
                        loc))
                else:
                    findings.append(Finding(
                        "error", "clearance",
                        f"{o1['label']} is {dist:.3f} mm from "
                        f"{o2['label']}, below the minimum clearance "
                        f"{min_clearance:.2f} mm",
                        loc))

    if zones_found:
        skipped.append("clearance check does not cover zones (copper "
                       "pours) — kicad-cli DRC covers them")
    if pads_custom_skipped:
        skipped.append(f"clearance check skipped {pads_custom_skipped} "
                       "custom-shaped pad(s)")
    if pads_roundrect_approx:
        skipped.append(f"clearance check approximated "
                       f"{pads_roundrect_approx} roundrect pad(s) as "
                       "rectangles (conservative at the corners)")
    if pads_no_net:
        skipped.append(f"clearance check skipped {pads_no_net} pad(s) "
                       "with no net (e.g. mounting holes)")

    stats = {
        "nets_declared": len(declared),
        "nets_with_copper": len(used_nets & set(declared)),
        "segments": len(segments),
        "vias": len(vias),
        "arcs": len(arcs),
        "pads": len(pads),
        "clearance_objects": len(objects),
        "clearance_pairs_checked": pairs_checked,
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
                  "via-pad", "annular-ring", "corner-90", "copper-to-edge",
                  "clearance", "short"]
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
        # Audit log goes to stderr: with --json, stdout must stay
        # parseable JSON (v1.2.3 fix, same as the other kit scripts).
        print("--- AUDIT LOG ---", file=sys.stderr)
        print(f"script: {SCRIPT} v{VERSION}", file=sys.stderr)
        print(f"started: {started} UTC", file=sys.stderr)
        print(f"input: {board_path} (not read)", file=sys.stderr)
        print(f"config: {config_path}", file=sys.stderr)
        print("checks run: none — setup failed", file=sys.stderr)
        print("result: SETUP ERROR (exit 2)", file=sys.stderr)
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
              f"{stats['segments']} segments, {stats['vias']} vias, "
              f"{stats['arcs']} arcs, {stats['pads']} pads, "
              f"{stats['clearance_pairs_checked']} clearance pairs checked.")
        print(f"Result: {len(errors)} error(s), {len(warnings)} warning(s).")

    # Audit log goes to stderr: with --json, stdout must stay parseable
    # JSON (v1.2.3 fix, same as the other kit scripts).
    print("--- AUDIT LOG ---", file=sys.stderr)
    print(f"script: {SCRIPT} v{VERSION}", file=sys.stderr)
    print(f"started: {started} UTC", file=sys.stderr)
    print(f"input: {board_path} (sha256 {sha256_of(board_path)[:16]}...)", file=sys.stderr)
    print(f"config: {config_path} (sha256 {sha256_of(config_path)[:16]}...)", file=sys.stderr)
    print(f"checks run: {', '.join(checks_run)}", file=sys.stderr)
    print(f"checks skipped: {'; '.join(skipped) if skipped else 'none'}", file=sys.stderr)
    print(f"findings: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
    print(f"result: {'FAIL' if errors else 'PASS'} (exit {1 if errors else 0})", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

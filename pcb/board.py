"""Writing the board file: footprints with their nets, tracks, vias, zones,
graphics and text, and the six-layer JLC06161H-7628 stackup."""
import os, sys, hashlib, math
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
from sexp import parse, kids, kid, val, head
import fplib

NAME = "ECP5-2ADC-2DAC"

# copper: F.Cu, In1 (GND), In2, In3, In4 (GND), B.Cu
LAYERS = [(0, "F.Cu", "signal"), (1, "In1.Cu", "power"), (2, "In2.Cu", "signal"), (3, "In3.Cu", "signal"),
          (4, "In4.Cu", "power"), (31, "B.Cu", "signal"),
          (32, "B.Adhes", "user", "B.Adhesive"), (33, "F.Adhes", "user", "F.Adhesive"),
          (34, "B.Paste", "user"), (35, "F.Paste", "user"), (36, "B.SilkS", "user", "B.Silkscreen"),
          (37, "F.SilkS", "user", "F.Silkscreen"), (38, "B.Mask", "user"), (39, "F.Mask", "user"),
          (40, "Dwgs.User", "user", "User.Drawings"), (41, "Cmts.User", "user", "User.Comments"),
          (42, "Eco1.User", "user", "User.Eco1"), (43, "Eco2.User", "user", "User.Eco2"),
          (44, "Edge.Cuts", "user"), (45, "Margin", "user"), (46, "B.CrtYd", "user", "B.Courtyard"),
          (47, "F.CrtYd", "user", "F.Courtyard"), (48, "B.Fab", "user"), (49, "F.Fab", "user")]
COPPER = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
ROUTE_LAYERS = ["F.Cu", "In2.Cu", "In3.Cu", "B.Cu"]

# JLCPCB JLC06161H-7628: 1.6 mm, 1 oz outer, 0.5 oz inner, 7628 prepreg.
STACKUP = [("F.Cu", "copper", 0.035), ("d1", "prepreg", 0.2104), ("In1.Cu", "copper", 0.0152),
           ("d2", "core", 0.4), ("In2.Cu", "copper", 0.0152), ("d3", "prepreg", 0.2104),
           ("In3.Cu", "copper", 0.0152), ("d4", "core", 0.4), ("In4.Cu", "copper", 0.0152),
           ("d5", "prepreg", 0.2104), ("B.Cu", "copper", 0.035)]


_UIDS = {}


def _f(t):
    return float(t[1]) if isinstance(t, tuple) else float(t)


try:
    import models3d
    OUR_MODELS = set(models3d.MODELS)
except Exception:
    OUR_MODELS = set()

BOARD = None          # (width, height) in mm, set by the builder so off-board silk can be dropped


def uid(*p):
    """A UUID that is a function of what it names (so a rebuild is a small
    diff) and unique even when two items would otherwise name themselves the
    same way (two shield pads of one connector, a stub written twice)."""
    key = "ecp5|" + "|".join(map(str, p))
    n = _UIDS.get(key, 0)
    _UIDS[key] = n + 1
    h = hashlib.sha1((key + ("|%d" % n if n else "")).encode()).hexdigest()
    return "%s-%s-4%s-8%s-%s" % (h[:8], h[8:12], h[13:16], h[17:20], h[20:32])


def ser(node, ind=0):
    pad = "\t" * ind
    if isinstance(node, tuple):
        if node[0] == "str":
            return '"%s"' % node[1].replace("\\", "\\\\").replace('"', '\\"')
        return node[1]
    if all(not isinstance(c, list) for c in node):
        return "(" + " ".join(ser(c) for c in node) + ")"
    out = ["(" + " ".join(ser(c) for c in node if not isinstance(c, list))]
    for c in node:
        if isinstance(c, list):
            out.append(pad + "\t" + ser(c, ind + 1))
    out.append(pad + ")")
    return "\n".join(out)


def A(*items):
    out = []
    for i in items:
        if isinstance(i, list):
            out.append(i)
        elif isinstance(i, str):
            out.append(("atom", i))
        elif isinstance(i, tuple):
            out.append(i)
        else:
            out.append(("atom", ("%g" % i) if isinstance(i, float) else str(i)))
    return out


def S(s):
    return ("str", s)


def g(v):
    return "%g" % round(v, 4)


def footprint(fp, ref, value, x, y, rot, layer, padnets, numof, ref_at=None, val_at=None,
              ref_size=0.8, val_size=0.8, val_layer="F.SilkS", lcsc=None, hide_value=False, ref_layer="F.SilkS"):
    """Serialize a footprint at (x, y, rot) on `layer` with its pads' nets.
    ref_at / val_at are in the footprint's own frame (KiCad rotates them with
    the part)."""
    node = parse(fp["text"])[0]
    node[0] = ("atom", "footprint")
    node[1] = S(fp["name"])
    node[:] = [c for c in node if not (isinstance(c, list) and head(c) in ("at", "uuid", "layer", "path", "version", "generator", "generator_version", "tedit"))]
    node.insert(2, A("layer", S(layer)))
    node.insert(3, A("uuid", S(uid("fp", ref))))
    node.insert(4, A("at", round(x, 4), round(y, 4), rot) if rot else A("at", round(x, 4), round(y, 4)))
    back = layer == "B.Cu"
    # 3D models: the easyeda2kicad footprints name their model relative to the
    # library; KiCad resolves relative paths against the project, so say so
    has_model = False
    for c in node:
        if isinstance(c, list) and head(c) == "model" and len(c) > 1 and isinstance(c[1], tuple) and c[1][0] == "str":
            has_model = True
            pth = c[1][1]
            if pth.startswith("easyeda.3dshapes/"):
                c[1] = S("${KIPRJMOD}/library/easyeda/" + pth)
            else:
                base = os.path.splitext(os.path.basename(pth))[0]
                if base in OUR_MODELS:
                    # KiCad names a STEP it does not ship: ours, same basename
                    c[1] = S("${KIPRJMOD}/library/ours.3dshapes/%s.wrl" % base)
    if not has_model:
        base = fp["name"]
        if base in OUR_MODELS:
            node.append(A("model", S("${KIPRJMOD}/library/ours.3dshapes/%s.wrl" % base),
                          A("offset", A("xyz", 0, 0, 0)), A("scale", A("xyz", 1, 1, 1)), A("rotate", A("xyz", 0, 0, 0))))
    # pin 1: a part whose pad pattern maps onto itself under a half turn and
    # whose library prints no silkscreen at all would go in either way round
    # unnoticed; it gets a dot beside pin 1
    pads_ = [(p["x"], p["y"], p["w"], p["h"]) for p in fp["pads"]]
    silk_items = [c for c in node if isinstance(c, list) and head(c) in ("fp_line", "fp_arc", "fp_circle", "fp_poly", "fp_rect", "fp_text")
                  and any(isinstance(k, list) and head(k) == "layer" and "SilkS" in str(k[1]) for k in c)]
    if len(pads_) >= 3 and not silk_items:
        sym = all(any(abs(-px - qx) < 0.05 and abs(-py - qy) < 0.05 and abs(pw - qw) < 0.05 and abs(ph - qh) < 0.05 for (qx, qy, qw, qh) in pads_)
                  for (px, py, pw, ph) in pads_)
        if sym:
            p1 = next((p for p in fp["pads"] if p["num"] == "1"), None)
            if p1:
                dx = -1.0 if p1["x"] < 0 else 1.0
                dy = -1.0 if p1["y"] < 0 else 1.0
                cx, cy = p1["x"] + dx * (p1["w"] / 2.0 + 0.5), p1["y"] + dy * (p1["h"] / 2.0 + 0.5)
                node.append(A("fp_circle", A("center", g(cx), g(cy)), A("end", g(cx + 0.3), g(cy)), A("stroke", A("width", 0.15), A("type", "solid")),
                              A("fill", "yes"), A("layer", S("F.SilkS")), A("uuid", S(uid("dot", ref)))))
    # silkscreen that would print beyond the board edge (an edge-launch SMA's
    # barrel, a socket's overhang) is dropped: the fab clips it anyway and the
    # DRC would otherwise report every piece
    if BOARD:
        import math as _m
        ca, sa = _m.cos(_m.radians(rot)), _m.sin(_m.radians(rot))
        def _tb(px, py):
            if back:
                px = -px
            # KiCad: footprint rotation is counter-clockwise on screen (y down)
            return (x + px * ca + py * sa, y - px * sa + py * ca)
        def _outside(px, py):
            bx, by = _tb(px, py)
            return bx < 0.6 or by < 0.6 or bx > BOARD[0] - 0.6 or by > BOARD[1] - 0.6
        keep = []
        padboxes = [(p["x"] - max(p["w"], p["h"]) / 2.0 - 0.12, p["y"] - max(p["w"], p["h"]) / 2.0 - 0.12,
                     p["x"] + max(p["w"], p["h"]) / 2.0 + 0.12, p["y"] + max(p["w"], p["h"]) / 2.0 + 0.12) for p in fp["pads"]]
        def _hits_pad(x0, y0, x1, y1):
            for (bx0, by0, bx1, by1) in padboxes:
                # segment vs box: sample along the segment (it is a short outline piece)
                for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                    px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                    if bx0 <= px <= bx1 and by0 <= py <= by1:
                        return True
            return False
        for c in node:
            if isinstance(c, list) and head(c) == "fp_text":
                # a library's own silk texts ("ON", pin numbers, "${REFERENCE}") overlap its outline and pads
                # and duplicate what our silkscreen says: none of them is printed
                lay = kid(c, "layer")
                lname = lay[1][1] if lay and isinstance(lay[1], tuple) else (lay[1] if lay else "")
                if lname in ("F.SilkS", "B.SilkS"):
                    continue
            if isinstance(c, list) and head(c) in ("fp_line", "fp_arc", "fp_circle", "fp_poly", "fp_rect"):
                lay = kid(c, "layer")
                lname = lay[1][1] if lay and isinstance(lay[1], tuple) else (lay[1] if lay else "")
                if lname in ("F.SilkS", "B.SilkS") and head(c) == "fp_line":
                    q0, q1 = kid(c, "start"), kid(c, "end")
                    if q0 and q1 and _hits_pad(_f(q0[1]), _f(q0[2]), _f(q1[1]), _f(q1[2])):
                        continue
                if lname in ("F.SilkS", "B.SilkS"):
                    pts = []
                    for k in ("start", "end", "mid", "center"):
                        q = kid(c, k)
                        if q:
                            pts.append((_f(q[1]), _f(q[2])))
                    if head(c) == "fp_circle" and len(pts) == 2:
                        cx, cy = pts[0]; r = _m.hypot(pts[1][0] - cx, pts[1][1] - cy)
                        pts = [(cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)]
                    if head(c) == "fp_poly":
                        pq = kid(c, "pts")
                        pts = [(_f(q[1]), _f(q[2])) for q in kids(pq, "xy")] if pq else []
                    if any(_outside(px, py) for px, py in pts):
                        continue
            keep.append(c)
        node[:] = keep
    if back:
        # mirror every drawn item and pad to the back; KiCad expects the file to
        # already hold back-side coordinates (x negated) with back layers
        for c in node:
            if not isinstance(c, list):
                continue
            h = head(c)
            if h in ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly", "fp_text", "pad", "property"):
                _flip(c)
    silk_layer = "B.SilkS" if back else "F.SilkS"
    fab_layer = "B.Fab" if back else "F.Fab"
    seen = set()
    for prop in list(kids(node, "property")):
        nm = val(prop)
        if nm == "Reference":
            prop[2] = S(ref)
            rl = ref_layer if not back else ref_layer.replace("F.", "B.")
            _set_text(prop, ref_at, ref_size, rl, hide=False)
            seen.add(nm)
        elif nm == "Value":
            prop[2] = S(value)
            vl = (val_layer if not back else val_layer.replace("F.", "B.")) if not hide_value else fab_layer
            _set_text(prop, val_at, val_size, vl, hide=hide_value)
            seen.add(nm)
        elif nm in ("Footprint", "Datasheet", "Description"):
            node.remove(prop)
    node.append(A("property", S("Footprint"), S(fp["id"]), A("at", 0, 0, 0), A("layer", S(fab_layer)), A("hide", "yes"),
                  A("uuid", S(uid("pf", ref))), A("effects", A("font", A("size", 1.27, 1.27), A("thickness", 0.16)))))
    if lcsc:
        node.append(A("property", S("LCSC"), S(lcsc), A("at", 0, 0, 0), A("layer", S(fab_layer)), A("hide", "yes"),
                      A("uuid", S(uid("pl", ref))), A("effects", A("font", A("size", 1.27, 1.27), A("thickness", 0.16)))))
    for p in kids(node, "pad"):
        pn = val(p)
        # a mechanical hole drawn as a plated pad with no copper ring: make it NPTH
        if pn == "" and len(p) > 2 and p[2][1] == "thru_hole":
            sz = kid(p, "size"); dr = kid(p, "drill")
            if sz and dr and float(sz[1][1]) <= float(dr[1][1]) + 0.01:
                p[2] = ("atom", "np_thru_hole")
        if rot:
            for a in kids(p, "at"):
                cur = float(a[3][1]) if len(a) > 3 else 0.0
                ang = (cur + rot) % 360.0
                if len(a) > 3:
                    a[3] = ("atom", g(ang))
                else:
                    a.append(("atom", g(ang)))
        net = padnets.get(pn)
        if net and not net.startswith("unconnected-"):
            p.append(A("net", numof[net], S(net)))
    return ser(node, 1)


def _flip(c):
    """Mirror one footprint item to the back side (x -> -x, F.* -> B.*)."""
    for sub in c:
        if not isinstance(sub, list):
            continue
        h = head(sub)
        if h in ("at", "start", "end", "center", "mid"):
            sub[1] = ("atom", g(-float(sub[1][1])))
            if h == "at" and len(sub) > 3 and head(c) in ("pad",):
                sub[3] = ("atom", g((-float(sub[3][1])) % 360.0))
        elif h == "pts":
            for xy in kids(sub, "xy"):
                xy[1] = ("atom", g(-float(xy[1][1])))
        elif h == "layer":
            sub[1] = S(_mirror_layer(sub[1][1]))
        elif h == "layers":
            for i in range(1, len(sub)):
                sub[i] = S(_mirror_layer(sub[i][1]))
        elif h == "effects":
            for just in kids(sub, "justify"):
                if not any(x[1] == "mirror" for x in just[1:]):
                    just.append(("atom", "mirror"))
            if not kids(sub, "justify"):
                sub.append(A("justify", "mirror"))


def _mirror_layer(l):
    if l.startswith("F."):
        return "B." + l[2:]
    if l.startswith("B."):
        return "F." + l[2:]
    return l


def _set_text(prop, at, size, layer, hide):
    if at is not None:
        for a in kids(prop, "at"):
            a[:] = [a[0], ("atom", g(at[0])), ("atom", g(at[1])), ("atom", g(at[2] if len(at) > 2 else 0))]
    for l in kids(prop, "layer"):
        l[1] = S(layer)
    for h in kids(prop, "hide"):
        prop.remove(h)
    if hide:
        prop.insert(3, A("hide", "yes"))
    for eff in kids(prop, "effects"):
        for fnt in kids(eff, "font"):
            for s in kids(fnt, "size"):
                s[1] = s[2] = ("atom", g(size))
            for th in kids(fnt, "thickness"):
                th[1] = ("atom", g(max(0.16, size * 0.18)))
            if not kids(fnt, "thickness"):
                fnt.append(A("thickness", g(max(0.16, size * 0.18))))


def gr(kind, *items):
    return ser(A(kind, *items), 1)


def line(x0, y0, x1, y1, layer, w=0.15):
    return gr("gr_line", A("start", g(x0), g(y0)), A("end", g(x1), g(y1)),
              A("stroke", A("width", w), A("type", "solid")), A("layer", S(layer)),
              A("uuid", S(uid("l", x0, y0, x1, y1, layer))))


def rect(x0, y0, x1, y1, layer, w=0.15):
    return "\n".join(line(*a, layer=layer, w=w) for a in
                     ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)))


def arc_rect(x0, y0, x1, y1, r, layer, w=0.1):
    """A rounded rectangle outline (Edge.Cuts)."""
    out = [line(x0 + r, y0, x1 - r, y0, layer, w), line(x1, y0 + r, x1, y1 - r, layer, w),
           line(x1 - r, y1, x0 + r, y1, layer, w), line(x0, y1 - r, x0, y0 + r, layer, w)]
    k = 0.70710678
    for (cx, cy, sx, sy, ex, ey) in ((x1 - r, y0 + r, x1 - r, y0, x1, y0 + r),
                                     (x1 - r, y1 - r, x1, y1 - r, x1 - r, y1),
                                     (x0 + r, y1 - r, x0 + r, y1, x0, y1 - r),
                                     (x0 + r, y0 + r, x0, y0 + r, x0 + r, y0)):
        mx = cx + (sx - cx + ex - cx) * k if False else None
        # mid point of the arc: 45 degrees from the centre
        ang0 = math.atan2(sy - cy, sx - cx); ang1 = math.atan2(ey - cy, ex - cx)
        da = (ang1 - ang0)
        while da > math.pi: da -= 2 * math.pi
        while da < -math.pi: da += 2 * math.pi
        am = ang0 + da / 2
        mx, my = cx + r * math.cos(am), cy + r * math.sin(am)
        out.append(gr("gr_arc", A("start", g(sx), g(sy)), A("mid", g(mx), g(my)), A("end", g(ex), g(ey)),
                      A("stroke", A("width", w), A("type", "solid")), A("layer", S(layer)),
                      A("uuid", S(uid("arc", cx, cy, layer)))))
    return "\n".join(out)


def text(x, y, s, layer, size=1.5, thick=None, just="left", angle=0, bold=False):
    thick = thick if thick is not None else max(0.16, round(size * 0.15, 2))
    font = A("font", A("size", size, size), A("thickness", thick))
    if bold:
        font.append(A("bold", "yes"))
    eff = A("effects", font)
    j = [just] if just not in (None, "center") else []
    if layer.startswith("B."):
        j.append("mirror")
    if j:
        eff.append(A("justify", *j))
    return gr("gr_text", S(s), A("at", g(x), g(y), angle), A("layer", S(layer)),
              A("uuid", S(uid("t", x, y, s, layer))), eff)


def via(x, y, net_no, size=0.45, drill=0.25, tag=""):
    return ser(A("via", A("at", g(x), g(y)), A("size", size), A("drill", drill),
                 A("layers", S("F.Cu"), S("B.Cu")), A("net", net_no),
                 A("uuid", S(uid("v", tag, x, y)))), 1)


def track(x0, y0, x1, y1, layer, net_no, w=0.15, tag=""):
    return ser(A("segment", A("start", g(x0), g(y0)), A("end", g(x1), g(y1)), A("width", w),
                 A("layer", S(layer)), A("net", net_no),
                 A("uuid", S(uid("s", tag, x0, y0, x1, y1, layer)))), 1)


def zone(net_no, net_name, layers, poly, name, priority=0, clearance=0.2, min_w=0.2,
         thermal=True, keepout=None):
    pts = A("pts", *[A("xy", g(px), g(py)) for px, py in poly])
    lay = A("layers", *[S(l) for l in layers]) if len(layers) > 1 else A("layer", S(layers[0]))
    items = [A("net", net_no), A("net_name", S(net_name)), lay, A("uuid", S(uid("z", name))),
             A("name", S(name)), A("hatch", "edge", 0.5), A("priority", priority)]
    if keepout:
        items.append(A("keepout", A("tracks", "allowed" if "tracks" not in keepout else "not_allowed"),
                       A("vias", "allowed" if "vias" not in keepout else "not_allowed"),
                       A("pads", "allowed"), A("copperpour", "not_allowed" if "copper" in keepout else "allowed"),
                       A("footprints", "allowed")))
    items.append(A("connect_pads", A("clearance", clearance)) if thermal else A("connect_pads", "yes", A("clearance", clearance)))
    items += [A("min_thickness", min_w), A("filled_areas_thickness", "no"),
              A("fill", "yes", A("thermal_gap", 0.3), A("thermal_bridge_width", 0.4)), A("polygon", pts)]
    return ser(A("zone", *items), 1)


def rule_area(name, layers, poly, no_pour=False):
    """A named area (for the .kicad_dru rules); with no_pour the zones stay out of it (the Ethernet island)."""
    pts = A("pts", *[A("xy", g(px), g(py)) for px, py in poly])
    lay = A("layers", *[S(l) for l in layers])
    return ser(A("zone", A("net", 0), A("net_name", S("")), lay, A("uuid", S(uid("ra", name))), A("name", S(name)),
                 A("hatch", "edge", 0.5), A("priority", 0),
                 A("keepout", A("tracks", "allowed"), A("vias", "allowed"), A("pads", "allowed"),
                   A("copperpour", "not_allowed" if no_pour else "allowed"), A("footprints", "allowed")),
                 A("fill", A("thermal_gap", 0.5), A("thermal_bridge_width", 0.5)), A("polygon", pts)), 1)


def document(body, numof, title_extra=""):
    lay = "\n".join('\t\t(%d "%s" %s%s)' % (l[0], l[1], l[2], (' "%s"' % l[3]) if len(l) > 3 else "") for l in LAYERS)
    nets = "\n".join('\t(net %d "%s")' % (n, nm) for nm, n in sorted(numof.items(), key=lambda kv: kv[1]))
    st = ["\t\t(stackup"]
    for nm, kind, th in STACKUP:
        if kind == "copper":
            st.append('\t\t\t(layer "%s" (type "copper") (thickness %g))' % (nm, th))
        else:
            st.append('\t\t\t(layer "dielectric %s" (type "%s") (thickness %g) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))' % (nm[1:], kind, th))
    st.append('\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)')
    return ('(kicad_pcb\n\t(version 20241229)\n\t(generator "ecp5-2adc-2dac")\n\t(generator_version "9.0")\n'
            '\t(general (thickness 1.6) (legacy_teardrops no))\n\t(paper "A3")\n'
            '\t(title_block (title "ECP5 + 2 ADC + 2 DAC%s") (rev "A") (company "Jason Gallicchio and Claude -- https://github.com/gallicchio"))\n'
            '\t(layers\n%s\n\t)\n\t(setup\n%s\n\t\t(pad_to_mask_clearance 0)\n'
            '\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n'
            '\t(net 0 "")\n%s\n%s\n)\n' % (title_extra, lay, "\n".join(st), nets, body))

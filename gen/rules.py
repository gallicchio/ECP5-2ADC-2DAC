"""The KiCad project file: design rules at least as strict as JLCPCB's for the
JLC06161H-7628 6-layer stackup, net classes, and the custom DRC rules."""
import json, os

# JLCPCB, multilayer, from their capabilities page (fetched 2026-10-01):
#   track/space 0.09/0.09 mm (3.5 mil), 3 mil accepted inside BGA fan-outs;
#   via 0.25 mm pad on a 0.15 mm hole; via-in-pad filled & capped is the
#   default for 6+ layers; filled vias must be <= 0.5 mm.
# OUR rules are stricter everywhere except where the BGA forces the minimum.
LIMITS = {
    "min_clearance": 0.1,          # we route at 0.127 outside the BGA
    "min_track_width": 0.1,
    "min_via_diameter": 0.3,       # 0.3/0.15 under the BGA; 0.45/0.25 elsewhere
    "min_through_hole_diameter": 0.15,
    "min_via_annular_width": 0.075,
    "min_microvia_diameter": 0.3,
    "min_microvia_drill": 0.1,
    "min_hole_clearance": 0.2,
    "min_hole_to_hole": 0.25,
    "min_silk_clearance": 0.0,
    "min_text_height": 0.7,
    "min_text_thickness": 0.153,
    "min_copper_edge_clearance": 0.3,
    "min_connection": 0.1,
    "solder_mask_clearance": 0.0,
    "solder_mask_min_width": 0.0,
}

# name, track, clearance, via dia, via drill, dp width, dp gap
CLASSES = [
    ("Default", 0.15, 0.127, 0.45, 0.25, 0.15, 0.2),
    ("BGA", 0.1, 0.1, 0.3, 0.15, 0.1, 0.1),          # inside the ball field only
    ("Power", 0.5, 0.15, 0.6, 0.3, 0.5, 0.2),
    ("Rail", 0.3, 0.15, 0.45, 0.25, 0.3, 0.2),
    ("Analog", 0.3, 0.3, 0.45, 0.25, 0.3, 0.3),        # 50 ohm single-ended runs and the front ends
    ("AnalogDiff", 0.2, 0.25, 0.45, 0.25, 0.2, 0.2),
    ("HS", 0.127, 0.15, 0.45, 0.25, 0.127, 0.15),     # converter buses, SDRAM, RGMII
    ("MDI", 0.2, 0.15, 0.45, 0.25, 0.2, 0.2),         # 100 ohm differential Ethernet, PHY to magnetics
    ("LAN", 0.25, 0.127, 0.45, 0.25, 0.25, 0.2),      # magnetics to jack: through the jack's 0.52 mm pin gaps
    ("USB", 0.2, 0.15, 0.45, 0.25, 0.2, 0.15),        # 90 ohm differential USB
]
PATTERNS = [
    ("Power", "GND"), ("Power", "+5V"), ("Power", "+3V3"), ("Power", "+1V1"),
    ("Rail", "/^\\+/"), ("Rail", "/^-/"), ("Rail", "/U401C-REG_OUT/"),     # the PHY's switch node to its inductor
    ("MDI", "/ETH_MDI/"), ("LAN", "/ETH_LAN/"), ("LAN", "/T401-MCT/"), ("LAN", "/C4951-Pad1/"),   # the line side: the pairs, the Bob Smith taps and node
    ("USB", "/USB_D[PN]/"), ("USB", "/FTDI_D[PN]/"),
    ("Analog", "/AIN_/"), ("Analog", "/AOUT_/"),
    ("HS", "/ADC_[AB]_(D|CLK|OTR)/"), ("HS", "/DAC_P[12]_D/"), ("HS", "/DAC_(CLK|WRT)/"),
    ("HS", "/SDRAM_/"), ("HS", "/ETH_(TX|RX)/"), ("HS", "/GPDI_(D|CK)/"), ("HS", "/CLK_/"),
]

DRU = '''(version 1)
# Written by gen/rules.py.  Edit that, not this.
# Inside the BGA ball field JLCPCB accepts 3.5 mil, and the escape needs it.
(rule "BGA fanout"
    (constraint track_width (min 0.1mm))
    (constraint clearance (min 0.1mm))
    (condition "A.insideArea('BGA_FANOUT')"))
(rule "via-in-pad under the BGA"
    (constraint hole_size (min 0.15mm))
    (condition "A.Type == 'Via' && A.insideArea('BGA_FANOUT')"))
(rule "Ethernet intra-pair skew"
    (constraint skew (max 5.0mm))
    (condition "A.NetClass == 'MDI' && B.NetClass == 'MDI'"))
(rule "Ethernet line-side intra-pair skew"
    (constraint skew (max 20.0mm))
    (condition "A.NetClass == 'LAN' && B.NetClass == 'LAN'"))
(rule "USB intra-pair skew"
    (constraint skew (max 1.0mm))
    (condition "A.NetClass == 'USB' && B.NetClass == 'USB'"))
(rule "keep every other net 1.5 mm from the Ethernet line side (the LAN nets, inside the island)"
    (constraint physical_clearance (min 1.5mm))
    (condition "A.NetClass != 'LAN' && B.NetClass == 'LAN' && B.insideArea('LAN_ISLAND') && !A.memberOfFootprint('C4951') && !B.memberOfFootprint('C4951') && !A.memberOfFootprint('J401') && !A.memberOfFootprint('T401')"))
# (no silk_clearance rule: KiCad applies one to Fab and courtyard items too and reports every
#  designator as a silkscreen overlap; its built-in silk-to-silk and silk-over-pad checks stay on)
(rule "a USB-C receptacle's locating pegs sit 0.19 mm from its own pads (GCT's land pattern)"
    (constraint hole_clearance (min 0.15mm))
    (condition "A.memberOfFootprint('J501') || A.memberOfFootprint('J502') || B.memberOfFootprint('J501') || B.memberOfFootprint('J502')"))
'''


def write_project(path, name):
    pro = {}
    if os.path.exists(path):
        try:
            pro = json.load(open(path))
        except Exception:
            pro = {}
    pro.setdefault("meta", {"filename": name + ".kicad_pro", "version": 3})
    board = pro.setdefault("board", {})
    ds = board.setdefault("design_settings", {})
    ds.setdefault("defaults", {})
    ds["rules"] = LIMITS
    ds["rule_severities"] = ds.get("rule_severities", {})
    # promote the warnings that matter at a fab to errors
    for k in ("silk_over_copper", "silk_overlap", "silk_edge_clearance", "text_height", "text_thickness",
              "copper_edge_clearance", "holes_co_located", "solder_mask_bridge",
              "courtyards_overlap", "lib_footprint_mismatch"):
        ds["rule_severities"][k] = "error"
    ds["rule_severities"]["lib_footprint_issues"] = "ignore"
    ds["rule_severities"]["footprint_symbol_mismatch"] = "ignore"
    ds["rule_severities"]["footprint_type_mismatch"] = "ignore"
    ds["rule_severities"]["padstack"] = "ignore"
    ds["rule_severities"]["duplicate_footprints"] = "error"
    ds["rule_severities"]["missing_footprint"] = "error"
    ds["rule_severities"]["extra_footprint"] = "error"
    ds["rule_severities"]["unresolved_variable"] = "error"
    ds["rule_severities"]["net_conflict"] = "error"
    ds["rule_severities"]["invalid_outline"] = "error"
    ds["rule_severities"]["malformed_outline"] = "error"
    ds["rule_severities"]["isolated_copper"] = "warning"
    ds["rule_severities"]["through_hole_pad_without_hole"] = "error"
    ds["rule_severities"]["zone_has_empty_net"] = "warning"
    ds["drc_exclusions"] = []
    net = pro.setdefault("net_settings", {})
    out = []
    for name_, tw, cl, vd, vdr, dw, dg in CLASSES:
        out.append({"name": name_, "track_width": tw, "clearance": cl, "via_diameter": vd, "via_drill": vdr,
                    "diff_pair_width": dw, "diff_pair_gap": dg, "diff_pair_via_gap": dg,
                    "bus_width": 12, "wire_width": 6, "line_style": 0, "microvia_diameter": 0.3,
                    "microvia_drill": 0.1, "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647 if name_ == "Default" else 0,
                    "tuning_profile": ""})
    net["classes"] = out
    net["netclass_patterns"] = [{"netclass": c, "pattern": p} for c, p in PATTERNS]
    net.setdefault("meta", {"version": 4})
    # schematic settings: ERC severities, and the netlist export
    sch = pro.setdefault("schematic", {})
    sch.setdefault("meta", {"version": 1})
    pro.setdefault("libraries", {"pinned_footprint_libs": [], "pinned_symbol_libs": []})
    pro.setdefault("pcbnew", {"last_paths": {}, "page_layout_descr_file": ""})
    pro.setdefault("sheets", [])
    pro.setdefault("text_variables", {})
    json.dump(pro, open(path, "w"), indent=2)
    open(os.path.splitext(path)[0] + ".kicad_dru", "w").write(DRU)

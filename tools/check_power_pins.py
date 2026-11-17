#!/usr/bin/env python3
"""Every power, ground, reference and strap pin of every IC on ECP5-2ADC-2DAC, against its data sheet, by voltage.

    python3 tools/check_power_pins.py [-v]        # exit 1 on any FAIL; -v prints the pass rows too

The CLAUDE_PCB.md check "Power pins, by voltage" (its top block; section 10, gate 2a), written 2026-11-16 after board
A's FT2232H turned out to have VPHY and VPLL on 1.8 V (bringup/REVB.md row 12).  The tables are tools/pin_tables.py.

1. Every IC pin that is a supply by type (power_in, power_out) or by name (VCC, VDD, VPHY, ...), and every IC pin
   whose net is a rail, must be in its part's table.  Its rail's range (RAILS, reached through a bead, an inductor or
   a resistor of 10 ohm or less) must lie inside the pin's range.  NC pins must be unconnected.
2. Op-amp and comparator supply spans (V+ - V-) against the data sheet's.
3. Each internal regulator's output feeds only the pins its data sheet names (REG_CONSUMERS).
4. The straps that decide what a supply pin wants (STRAPS): pulled the right way.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit_netlist import load                     # noqa: E402
import pin_tables as T                             # noqa: E402

SUPPLY_NAME = re.compile(r'^~?\{?(V(CC|DD|EE|SS|IO|CORE|PHY|PLL|REG|REF|IN|BAT|BUS|USB|AUX|A|D|S|\+|-)\w*|AVDD\w*|DVDD\w*|AVSS\w*|'
                         r'DVSS\w*|A?GND\w*|D?GND\w*|P?GND\w*|EP|PAD|V\+|V-|VS\+?|VS-|REG_?OUT\w*|LDO\w*|[AD]COM\d?)$', re.I)
IC = re.compile(r'^(U|X)\d')


def ohms(v):
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*([kKM]?)\s*R?\s*', v or '')
    if not m:
        m2 = re.fullmatch(r'(\d+)R(\d+)', v or '')
        return float(m2.group(1) + '.' + m2.group(2)) if m2 else None
    return float(m.group(1)) * {'': 1, 'k': 1e3, 'K': 1e3, 'M': 1e6}[m.group(2)]


def rail_of(net, comps, pins, nets, depth=3, via=()):
    """The rail a net is, or reaches through a bead, an inductor or a resistor of <= 10 ohm: (name, (lo, hi), via)."""
    if net in T.RAILS:
        return net, T.RAILS[net], via
    if depth == 0:
        return None, None, via
    for ref, pin, fn, ty in nets.get(net, []):
        if len(pins[ref]) != 2:
            continue
        r = ohms(comps[ref][0]) if ref.startswith('R') else None
        if ref.startswith(('FB', 'L')) or (r is not None and r <= 10):
            other = pins[ref][[p for p in pins[ref] if p != pin][0]][2]
            if other != net:
                name, rng, v = rail_of(other, comps, pins, nets, depth - 1, via + (ref,))
                if name:
                    return name, rng, v
    return None, None, via


def is_supply(fn, ty):
    f = re.sub(r'_[A-Z]?\d+$', '', fn or '')
    return ty in ('power_in', 'power_out') or bool(f and SUPPLY_NAME.match(f))


def main(argv):
    verbose = '-v' in argv
    comps, pins, nets = load()
    rows, fails = [], 0

    def add(ok, *cols):
        nonlocal fails
        rows.append(('pass' if ok is True else ('FAIL' if ok is False else ok),) + cols)
        if ok is False:
            fails += 1

    # ---- 1. supply, ground, reference and strap pins ----------------------------------------------------------
    n_pins = n_ics = 0
    for ref in sorted(comps, key=lambda r: (re.sub(r'\d', '', r), int(re.sub(r'\D', '', r) or 0))):
        value = comps[ref][0]
        table = T.PARTS.get(value)
        if not IC.match(ref) and table is None:
            continue
        n_ics += 1
        if table is None:
            sup = [p for p, (fn, ty, net) in pins[ref].items() if is_supply(fn, ty) or net in T.RAILS]
            add(False if sup else 'info', ref, value, '-', '-', '-', 'no table' + (' and supply pins %s' % sup if sup else ''))
            continue
        for pin, (fn, ty, net) in sorted(pins[ref].items(), key=lambda x: (len(x[0]), x[0])):
            name, rng, via = rail_of(net, comps, pins, nets)
            if pin not in table:
                if is_supply(fn, ty) or net in T.RAILS:
                    add(False, ref, value, pin, fn, net, 'a supply pin, or a pin on a rail, missing from the table')
                continue
            tname, lo, hi, src = table[pin]
            if tname.startswith('if-tied:') and name is None:
                continue                                  # a signal pin that is checked only when tied to a rail
            n_pins += 1
            if tname == 'NC':
                ok = net.startswith('unconnected') or len(nets.get(net, [])) <= 1
                add(ok, ref, value, pin, tname, net, 'must be unconnected; ' + src)
                continue
            where = net + (' (= %s via %s)' % (name, '+'.join(via)) if via else '')
            if name is None:
                add(False, ref, value, pin, tname, net, 'rail voltage unknown; wants %s..%s V' % (lo, hi))
                continue
            ok = lo - 1e-9 <= rng[0] and rng[1] <= hi + 1e-9
            add(ok, ref, value, pin, tname, where, 'wants %s..%s V; rail %s..%s V; %s' % (lo, hi, rng[0], rng[1], src))
        for pin in set(table) - set(pins[ref]):
            add('info', ref, value, pin, table[pin][0], '(not in netlist)', 'in the table, absent from the netlist')

    # ---- 2. supply spans ------------------------------------------------------------------------------------------
    for ref in sorted(comps):
        span = T.OPA_SPAN.get(comps[ref][0])
        if not span:
            continue
        vp, vn, lo, hi, src = span
        _, rp, _ = rail_of(pins[ref][vp][2], comps, pins, nets)
        _, rn, _ = rail_of(pins[ref][vn][2], comps, pins, nets)
        smin, smax = rp[0] - rn[1], rp[1] - rn[0]
        add(lo <= smin and smax <= hi, ref, comps[ref][0], vp + '-' + vn, 'V+ - V-', '%s .. %s' % (pins[ref][vp][2], pins[ref][vn][2]),
            'span %.2f..%.2f V; wants %s..%s V; %s' % (smin, smax, lo, hi, src))

    # ---- 3. internal regulator outputs: who they feed ----------------------------------------------------------
    for (ref, pin), (allowed, src) in T.REG_CONSUMERS.items():
        start = pins[ref][pin][2]
        # every net this output reaches through beads, inductors and <= 10 ohm resistors
        seen, todo = set(), [start]
        while todo:
            n = todo.pop()
            if n in seen or n == 'GND':
                continue
            seen.add(n)
            for r, p, fn, ty in nets.get(n, []):
                if len(pins[r]) == 2 and (r.startswith(('FB', 'L')) or (r.startswith('R') and (ohms(comps[r][0]) or 99) <= 10)):
                    todo.append(pins[r][[q for q in pins[r] if q != p][0]][2])
        for n in sorted(seen):
            for r, p, fn, ty in nets[n]:
                if not IC.match(r) or (r, p) == (ref, pin):
                    continue
                f = re.sub(r'_\d+$', '', fn)
                add(f in allowed, ref + '.' + pin, comps[ref][0], '%s.%s' % (r, p), f, n,
                    'regulator output may feed only %s; %s' % ('/'.join(sorted(allowed)), src))

    # ---- 4. straps -------------------------------------------------------------------------------------------------
    for ref, pin, want, why in T.STRAPS:
        net = pins[ref][pin][2]
        pulls = []
        for r, p, fn, ty in nets[net]:
            if r.startswith('R') and len(pins[r]) == 2:
                other = pins[r][[q for q in pins[r] if q != p][0]][2]
                name, rng, _ = rail_of(other, comps, pins, nets)
                if name:
                    pulls.append((r, comps[r][0], name, rng))
        highs = [x for x in pulls if x[3][0] > 1.0]
        lows = [x for x in pulls if x[3] == (0.0, 0.0)]
        got = 'high' if highs and not lows else 'low' if lows and not highs else 'contested' if pulls else 'floating'
        add(got == want, ref, comps[ref][0], pin, pins[ref][pin][0], net,
            'strap wants %s, is %s (%s); %s' % (want, got, ', '.join('%s %s to %s' % x[:3] for x in pulls) or 'no pull', why))

    for r in rows:
        if r[0] != 'pass' or verbose:
            print('%-4s %-6s %-20s %-6s %-30s %-44s %s' % r)
    npass = sum(1 for r in rows if r[0] == 'pass')
    print('\n%d ICs with tables or supply pins, %d table pins checked; %d rows: %d pass, %d FAIL, %d info'
          % (n_ics, n_pins, len(rows), npass, fails, sum(1 for r in rows if r[0] == 'info')))
    print('RESULT: %s' % ('FAIL' if fails else 'PASS'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

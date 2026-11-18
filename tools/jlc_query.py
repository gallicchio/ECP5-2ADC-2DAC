#!/usr/bin/env python3
"""Print JLCPCB stock and price for a list of search keywords (one table row
per candidate), Basic parts first, then by stock.  Thin wrapper on jlc_api.

    python3 jlc_query.py "W9825G6KH" "W25Q128JVS" ...
    python3 jlc_query.py --n 8 ...        # rows per keyword (default 6)
"""
import sys, jlc_api

def main(argv):
    n = 6
    if argv and argv[0] == "--n":
        n = int(argv[1]); argv = argv[2:]
    for kw in argv:
        try:
            lst, ts = jlc_api.search(kw, page_size=30)
        except Exception as e:
            print("!! %s: %s" % (kw, e)); continue
        rows = sorted(lst, key=lambda it: (jlc_api.library_type(it) == "Extended",
                                           -(it.get("stockCount") or 0)))
        print("\n== %s  (%s)" % (kw, ts[:16]))
        for it in rows[:n]:
            p1 = jlc_api.unit_price(it, 1); p10 = jlc_api.unit_price(it, 10)
            print("  %-11s %-9s %-26s %-22s stk %-8d $%-8.3f $%-8.3f %s" % (
                it["componentCode"], jlc_api.library_type(it),
                (it.get("componentModelEn") or "")[:26],
                (it.get("componentSpecificationEn") or "")[:22],
                it.get("stockCount") or 0, p1, p10,
                (it.get("describe") or "")[:60]))

if __name__ == "__main__":
    main(sys.argv[1:])

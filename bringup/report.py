"""report.py: the rows a visit produces, printed as they come, logged, summed up and written as markdown.

Every test of a visit is a function that returns rows.  A row is one line of the result:

    row("clocks", "clk_s", "50,000,000 Hz", "50,000,000 +-1", "pass")
    row("sd", "card", "no answer to CMD0", "a card that answers", "FAIL", "push the card in until it clicks; then `v1b --only sd`")

    test      which test made it (the name --only and --skip take)
    name      what was measured
    value     what was found, as text with its unit
    expected  what passes, as text
    verdict   pass | FAIL | info (a number worth keeping, with no pass condition) | skipped
    note      for a FAIL: what to do next.  For the others: anything worth a few words.

Results collects them for one run of one visit: it prints each row when it arrives (nobody may be watching, but
the session reads the output afterwards), appends it to the board's log, and at the end prints the summary and
writes the same as markdown beside the log.
"""
import datetime as dt
import os
import time

VERDICTS = ("pass", "FAIL", "info", "skipped")


def row(test, name, value, expected="", verdict="info", note=""):
    if verdict not in VERDICTS:
        raise ValueError("verdict %r is not one of %s" % (verdict, VERDICTS))
    return {"test": test, "name": name, "value": str(value), "expected": str(expected), "verdict": verdict, "note": str(note)}


def within(value, lo, hi):
    """'pass' when lo <= value <= hi, else 'FAIL'."""
    return "pass" if lo <= value <= hi else "FAIL"


def hz(f):
    """25000000 -> '25,000,000 Hz'"""
    return "{:,.0f} Hz".format(f)


def format_row(r):
    """One row as one line (two when it has a note)."""
    line = "  %-7s %-14s %-40s %-46s %s" % (r["verdict"], r["test"], r["name"], r["value"],
                                           ("want: " + r["expected"]) if r["expected"] else "")
    if r["note"]:
        line += "\n          -> " + r["note"]
    return line.rstrip()


class Results:
    """The rows of one run of one visit (`visit` is 'v1a', 'rails', 'v1b', 'coldboot', 'v2' or 'step')."""

    def __init__(self, bench, visit):
        self.b = bench
        self.visit = visit
        self.rows = []
        self.started = dt.datetime.now()

    def add(self, rows):
        """Take a row or a list of rows: print, log, keep."""
        if isinstance(rows, dict):
            rows = [rows]
        for r in rows:
            self.rows.append(r)
            print(format_row(r), flush=True)
            self.b.log.add("row", self.b.stage, quiet=True, visit=self.visit, **r)

    def run(self, name, function, *args):
        """Run one test function and take its rows.  An exception inside it becomes a FAIL row carrying the
        message, and the run goes on: one broken test must not cost the hour of tests after it."""
        print("\n== %s: %s" % (name, first_line(function.__doc__)), flush=True)
        began = time.time()
        try:
            rows = function(*args)
        except KeyboardInterrupt:
            raise
        except Exception as e:                                   # noqa: BLE001 (on purpose: see the docstring)
            import traceback
            self.b.log.add("exception", self.b.stage, quiet=True, visit=self.visit, test=name, traceback=traceback.format_exc())
            rows = [row(name, "the test itself", "%s: %s" % (type(e).__name__, e), "to run to its end", "FAIL",
                        "the test stopped here and the run went on; the traceback is in the log (kind 'exception'). "
                        "Run it again alone with `--only %s`" % name)]
        self.add(rows or [])
        took = time.time() - began
        self.b.log.add("timing", self.b.stage, quiet=True, visit=self.visit, test=name, seconds=round(took, 1))
        print("          (%s took %.0f s)" % (name, took), flush=True)

    def skip(self, name, why):
        self.add(row(name, "(whole test)", "not run", "", "skipped", why))

    def counts(self):
        return {v: sum(1 for r in self.rows if r["verdict"] == v) for v in VERDICTS}

    def failures(self):
        return [r for r in self.rows if r["verdict"] == "FAIL"]

    def summary_line(self):
        c = self.counts()
        return "%s board %s: %d pass, %d FAIL, %d info, %d skipped" % (self.visit, self.b.board, c["pass"], c["FAIL"], c["info"], c["skipped"])

    def finish(self, write=True):
        """Print the summary (the counts, then every FAIL with what to do about it) and write the markdown
        report.  Returns the report's path (None when write=False)."""
        print("\n" + "=" * 100)
        print("SUMMARY  " + self.summary_line() + ("   (SIMULATED board and instruments)" if self.b.sim else ""))
        fails = self.failures()
        for r in fails:
            print(format_row(r))
        if not fails:
            print("  no FAIL rows")
        path = None
        if write:
            path = os.path.join(self.b.log.dir, "report_%s_%s.md" % (self.visit, self.started.strftime("%Y%m%d_%H%M%S")))
            with open(path, "w") as f:
                f.write(self.markdown())
            print("report: %s" % path)
        return path

    def markdown(self):
        out = ["# %s, board %s, %s%s" % (self.visit, self.b.board, self.started.strftime("%Y-%m-%d %H:%M"),
                                        " (SIMULATED board and instruments)" if self.b.sim else ""), "",
               self.summary_line(), ""]
        fails = self.failures()
        if fails:
            out += ["## FAIL", ""] + markdown_table(fails) + [""]
        out += ["## Every row", ""] + markdown_table(self.rows) + [""]
        return "\n".join(out)


def first_line(doc):
    return (doc or "").strip().split("\n")[0]


def markdown_table(rows, with_visit=False):
    head = (["visit"] if with_visit else []) + ["test", "what", "found", "expected", "verdict", "note"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = ([r.get("visit", "")] if with_visit else []) + [r["test"], r["name"], r["value"], r["expected"], r["verdict"], r["note"]]
        lines.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in cells) + " |")
    return lines


def latest_rows(log_entries):
    """From every log entry of a board (oldest first), the latest row of each (visit, test, name)."""
    latest = {}
    for e in log_entries:
        if e.get("kind") == "row":
            latest[(e.get("visit"), e.get("test"), e.get("name"))] = e
    return list(latest.values())

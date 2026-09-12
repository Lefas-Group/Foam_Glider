"""
One row per phase-run, in SQLite.

Stage 1 computed the first-pass lint violation count and then printed it and
threw it away, which made every comparison anecdotal. That number is the eval:
it is a real measurement over a real artefact, and it is what should decide a
model change or a prompt change rather than an impression formed over two runs.

Lives at `<notebook>/_scratch/nb-metrics.db` -- gitignored, per notebook, and it
survives runs, which `_scratch/run/` deliberately does not.
"""

import sqlite3
import sys
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                     INTEGER PRIMARY KEY,
    ts                     REAL,
    phase                  TEXT,     -- ask | write
    model                  TEXT,
    thinking_level         TEXT,
    question               TEXT,
    chapter                TEXT,
    entry_stem             TEXT,
    turns                  INTEGER,
    prompt_tokens          INTEGER,
    cached_tokens          INTEGER,
    output_tokens          INTEGER,
    solves                 INTEGER,
    solve_seconds          REAL,
    first_pass_violations  INTEGER,  -- write only; the eval
    verify_findings        INTEGER,  -- write only
    outcome                TEXT,
    duration_s             REAL
)
"""


def _db(notebook):
    notebook.scratch.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(notebook.scratch / "nb-metrics.db")
    con.execute(SCHEMA)
    return con


class Run:
    """Accumulates a phase's numbers; writes one row on close."""

    def __init__(self, notebook, phase, question=""):
        from .config import MODEL, THINKING_LEVEL
        self.notebook = notebook
        self.t0 = time.time()
        self.row = dict(
            ts=self.t0, phase=phase, model=MODEL, thinking_level=THINKING_LEVEL,
            question=question, chapter="", entry_stem="", turns=0,
            prompt_tokens=0, cached_tokens=0, output_tokens=0, solves=0,
            solve_seconds=0.0, first_pass_violations=None, verify_findings=None,
            outcome="incomplete", duration_s=0.0)

    def turn(self, resp):
        from .client import usage
        prompt, cached, out = usage(resp)
        self.row["turns"] += 1
        self.row["prompt_tokens"] += prompt
        self.row["cached_tokens"] += cached
        self.row["output_tokens"] += out

    def set(self, **kw):
        self.row.update(kw)

    def close(self, outcome):
        self.row["outcome"] = outcome
        self.row["duration_s"] = round(time.time() - self.t0, 1)
        cols = ", ".join(self.row)
        marks = ", ".join("?" * len(self.row))
        con = _db(self.notebook)
        con.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})",
                    list(self.row.values()))
        con.commit()
        con.close()


def summary(notebook):
    con = _db(notebook)
    rows = con.execute(
        "SELECT phase, model, outcome, turns, prompt_tokens, cached_tokens, "
        "first_pass_violations, solve_seconds, duration_s, question "
        "FROM runs ORDER BY ts DESC LIMIT 25").fetchall()
    if not rows:
        return "no runs recorded yet"
    out = [f"  {'phase':6s} {'model':22s} {'outcome':11s} {'turns':>5s} "
           f"{'cached%':>7s} {'viol':>4s} {'solve_s':>7s} {'wall_s':>6s}  question"]
    for (ph, m, oc, t, pt, ct, fv, ss, du, q) in rows:
        pct = f"{100 * ct / pt:.0f}%" if pt else "-"
        out.append(f"  {ph:6s} {m:22s} {oc:11s} {t:>5d} {pct:>7s} "
                   f"{'-' if fv is None else fv:>4} {ss:>7.1f} {du:>6.0f}  {q[:40]}")
    # The eval, in one line.
    agg = con.execute(
        "SELECT model, COUNT(*), AVG(first_pass_violations), AVG(turns) "
        "FROM runs WHERE phase='write' AND first_pass_violations IS NOT NULL "
        "GROUP BY model").fetchall()
    if agg:
        out.append("\n  first-pass lint violations, by model:")
        for m, n, v, t in agg:
            out.append(f"    {m:22s} {n:>3d} entries   {v:.2f} violations   "
                       f"{t:.1f} turns")
    con.close()
    return "\n".join(out)


def main(argv):
    from .config import Notebook
    if not argv:
        print("usage: python -m nb.metrics <notebook>")
        return 2
    print(summary(Notebook(argv[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

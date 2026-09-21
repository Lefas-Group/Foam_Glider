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

from . import runstate

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
    lint_calls             INTEGER,  -- times the model asked lint before stopping
    renders                INTEGER,  -- quarto renders this phase asked for
    pages_rendered         INTEGER,  -- pages those renders actually executed
    verify_findings        INTEGER,  -- write only
    outcome                TEXT,
    duration_s             REAL
)
"""


# Columns added after a database already existed. `CREATE TABLE IF NOT EXISTS`
# does nothing to a table that is already there, so without this an older
# notebook's db is missing the column and every INSERT fails with `no such
# column`. Additive only -- old rows read NULL, which is the truth: nobody
# counted.
ADDED = (("lint_calls", "INTEGER"),
         ("renders", "INTEGER"),
         ("pages_rendered", "INTEGER"))


def migrate(con):
    """
    Bring an existing db up to the current column list. Idempotent.

    Shared with READERS, not just writers. `nb eval` opened the db directly and
    selected the current columns, so a notebook whose last run predated a column
    failed with `no such column` -- the additive scheme protects the INSERT and
    left the SELECT to find out. A reader that adds a column it is about to read
    as NULL is doing the same thing the writer does, one step earlier.
    """
    con.execute(SCHEMA)
    for col, typ in ADDED:
        try:
            con.execute(f"ALTER TABLE runs ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass                      # already there
    return con


def _db(notebook):
    notebook.scratch.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(notebook.scratch / "nb-metrics.db", timeout=10)
    # The db is shared by every run in the notebook, so with agents in parallel
    # there are several writers. WAL lets readers and one writer proceed at
    # once; busy_timeout makes a second writer wait rather than raise
    # `database is locked`. Both are per-connection and idempotent.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return migrate(con)


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
            solve_seconds=0.0, first_pass_violations=None, lint_calls=0,
            renders=0, pages_rendered=0, verify_findings=None,
            outcome="incomplete", duration_s=0.0)

    def turn(self, resp):
        from .client import usage
        prompt, cached, out = usage(resp)
        self.row["turns"] += 1
        self.row["prompt_tokens"] += prompt
        self.row["cached_tokens"] += cached
        self.row["output_tokens"] += out
        # How hard the model worked to satisfy lint, which
        # `first_pass_violations` cannot see: that samples AFTER the loop
        # returns, so a run that spent eight turns in lint/edit still reported
        # zero. Counted here rather than in each phase's `on_turn` so there is
        # one implementation and no indentation to get wrong -- the first
        # attempt at this patched `write.py` and silently missed `ask.py`.
        parts = (resp.candidates[0].content.parts or []) if resp.candidates else []
        self.row["lint_calls"] += sum(
            1 for p in parts
            if p.function_call and p.function_call.name == "lint")

    def set(self, **kw):
        self.row.update(kw)

    def close(self, outcome):
        # The same word goes to two places. The db is history; `run.json` is
        # what `nb board` and a coordinator read, and without this every ending
        # looked identical there -- a clean commit, a stop at a gate and a run
        # that died on max turns all rendered as `done`, because the board had
        # nothing to go on but a missing pid. A run that never reaches here
        # leaves no outcome at all, which is how `died` stays distinguishable
        # from every ending the system chose.
        runstate.write(self.notebook, outcome=outcome)
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
        "first_pass_violations, lint_calls, solve_seconds, duration_s, question "
        "FROM runs ORDER BY ts DESC LIMIT 25").fetchall()
    if not rows:
        return "no runs recorded yet"
    out = [f"  {'phase':6s} {'model':22s} {'outcome':11s} {'turns':>5s} "
           f"{'cached%':>7s} {'viol':>4s} {'lint':>4s} {'solve_s':>7s} "
           f"{'wall_s':>6s}  question"]
    for (ph, m, oc, t, pt, ct, fv, lc, ss, du, q) in rows:
        pct = f"{100 * ct / pt:.0f}%" if pt else "-"
        out.append(f"  {ph:6s} {m:22s} {oc:11s} {t:>5d} {pct:>7s} "
                   f"{'-' if fv is None else fv:>4} "
                   f"{'-' if lc is None else lc:>4} "
                   f"{ss:>7.1f} {du:>6.0f}  {q[:40]}")
    # The eval, in one line.
    agg = con.execute(
        "SELECT model, COUNT(*), AVG(first_pass_violations), AVG(turns), "
        "AVG(COALESCE(lint_calls, 0)) "
        "FROM runs WHERE phase='write' AND first_pass_violations IS NOT NULL "
        "GROUP BY model").fetchall()
    if agg:
        out.append("\n  first-pass lint violations, by model:")
        for m, n, v, t, lc in agg:
            out.append(f"    {m:22s} {n:>3d} entries   {v:.2f} violations   "
                       f"{t:.1f} turns   {lc:.1f} lint calls")
    con.close()
    return "\n".join(out)


def main(argv):
    from .config import Notebook
    if not argv:
        print("usage: uv run --group nb python -m nb.metrics <notebook>")
        return 2
    print(summary(Notebook(argv[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

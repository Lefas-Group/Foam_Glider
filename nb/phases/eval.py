"""
`nb eval` -- what each model actually did, from the runs on record.

Written because the alternative was tried and failed. A model swap was decided
off a hand-written comment in `config.py` and one encouraging smoke test; the
comment was stale, the smoke test was a much easier question than the real one,
and the switch had to be reversed the same morning after the model burned 40
turns and produced nothing. Every number needed to make that call was already in
`nb-metrics.db` and nobody queried it.

So: no new instrumentation, one query. `metrics.Run` has been writing these
columns all along.

The number that decides it is FIRST-PASS VIOLATIONS -- lint problems before any
correction round. Turns and tokens measure effort; first-pass measures whether
the model knew the rules before it wrote, which is the thing more prompt cannot
fix. `outcome` is the floor under both: a model that never reaches `open_entry` has
no first-pass score at all, and that is the failure worth seeing first.
"""

import sqlite3
import sys

from ..config import Notebook
from ..log import tell

QUERY = """
SELECT model,
       phase,
       COUNT(*)                                        AS runs,
       SUM(outcome IN ('committed', 'committed_refactor')) AS ok,
       ROUND(AVG(turns), 1)                            AS turns,
       ROUND(AVG(lint_calls), 1)                       AS lints,
       ROUND(AVG(first_pass_violations), 2)            AS fpv,
       ROUND(AVG(renders), 1)                          AS renders,
       ROUND(AVG(pages_rendered), 1)                   AS pages,
       ROUND(AVG(duration_s))                          AS secs
FROM runs
GROUP BY model, phase
ORDER BY model, phase
"""


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb eval <notebook>")
        return 2
    notebook = Notebook(argv[0])
    db = notebook.scratch / "nb-metrics.db"
    if not db.exists():
        tell(f"  no metrics yet at {db}")
        return 1

    con = sqlite3.connect(db)
    # A reader migrates too: a notebook whose last run predates a column would
    # otherwise fail with `no such column` on a query the writer was protected
    # from. The added columns read NULL, which is the truth -- nobody counted.
    from .. import metrics
    metrics.migrate(con)
    rows = list(con.execute(QUERY))
    if not rows:
        tell("  no runs recorded")
        return 1

    tell(f"  {'model':22} {'phase':6} {'runs':>4} {'ok':>4} "
         f"{'turns':>6} {'lint':>5} {'1st-pass':>8} "
         f"{'rndrs':>6} {'pages':>6} {'secs':>5}")
    for model, phase, runs, ok, turns, lints, fpv, rnd, pages, secs in rows:
        dash = lambda v: "—" if v is None else v
        tell(f"  {model[:22]:22} {phase:6} {runs:4} {ok or 0:4} "
             f"{turns or 0:6} {lints or 0:5} "
             f"{dash(fpv):>8} {dash(rnd):>6} {dash(pages):>6} {secs or 0:5.0f}")

    tell("\n  ok = committed. 1st-pass = lint problems before any")
    tell("  correction round; lower is the model knowing the rules in advance.")
    tell("  A model with runs but no ok is not cheap, it is not working.")
    # rndrs/pages, not rndrs alone: the COST of a render is the pages it
    # executes, and a chapter target and an entry target are one render each
    # against sixteen pages and one. A model whose pages-per-render is high is
    # targeting chapters where an entry would do.
    tell("  rndrs = quarto renders asked for; pages = what they executed.")
    tell('  Both show "—" for runs recorded before the columns existed.')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""
`nb stop <notebook> [run] ["why"]` -- ask a run to stop.

The other half of `nb answer`: one file in the run directory, so it works from
the board's terminal, a second terminal, a script or a coordinator agent, and
the run cannot tell which wrote it.

COOPERATIVE, not a kill. The run checks before each turn and while it is blocked
on a question -- the two places it spends its time -- and exits through its own
`finally`, which is what shuts the MCP server down and records `outcome`. A
signal would skip all of that and leave the board rendering a deliberate stop as
`died`, which is the one distinction the board exists to make.

A run inside a probe or a render finishes it first. That is a bounded wait, and
`kill` is still there for a run that has stopped listening altogether.

Stopping does NOT revert anything. The entry, the scaffolded chapter and the
edited `_analysis.py` stay in the working tree, because a stop means "spend
nothing more on this", not "throw away what it did" -- and `nb clean` will not
remove the run directory of a chapter that still has uncommitted changes.
"""

import re
import sys

from ..config import Notebook
from ..log import tell
from .. import runstate


# A run id is a timestamp and a suffix. Anything starting that way was MEANT as
# an id, so a near-miss is an error rather than a reason string.
RUN_ID = re.compile(r"\d{8}-[0-9a-f]")


def main(argv):
    if not argv:
        tell('usage: uv run --group nb python -m nb stop <notebook> [run] ["why"]')
        return 2
    notebook = Notebook(argv[0])
    rest = argv[1:]

    known = {d.name for d in notebook.runs()}
    runs = []
    for d in notebook.runs():
        state = runstate.read(d)
        if state and runstate.alive(d) is not False:
            runs.append((d.name, state))

    # Matched against EVERY run, not just the live ones. Matching only live runs
    # meant naming a run that had already finished looked like naming no run at
    # all, and the answer to "stop this one" became a list of the others.
    run_id = None
    if rest and rest[0] in known:
        run_id, rest = rest[0], rest[1:]
    elif rest and RUN_ID.match(rest[0]):
        # It is SHAPED like a run id and is not one. Treating it as the reason
        # instead would silently stop whichever run happened to be the only live
        # one -- a typo in an id quietly killing a different agent is precisely
        # the failure `nb answer` refuses to allow.
        tell(f"  no such run: {rest[0]}")
        if known:
            tell("  known runs: " + ", ".join(sorted(known, reverse=True)[:5]))
        return 1
    why = " ".join(rest)

    if run_id is None:
        if not runs:
            tell(f"  no live runs under {notebook.scratch / 'runs'}")
            return 1
        if len(runs) > 1:
            # Same rule as `nb answer`: guessing which agent a command was
            # meant for is the one mistake here that would be silent.
            tell(f"  {len(runs)} runs are live — name the one to stop:")
            for name, state in runs:
                tell(f"    {name}  {state.get('chapter') or '—'}  "
                     f"{state.get('phase', '?')} turn {state.get('turn', '?')}")
            return 2
        run_id = runs[0][0]

    target = Notebook(notebook.root, run_id=run_id)
    if not target.run.is_dir():
        tell(f"  no such run: {run_id}")
        return 1
    state = runstate.read(target)
    if runstate.alive(target.run) is False:
        tell(f"  {run_id} has already ended"
             f"{' — ' + state['outcome'] if state.get('outcome') else ''}")
        return 0

    path = runstate.request_stop(target, why=why)
    tell(f"  stop      asked {run_id} to stop — {path}")
    tell("  It ends before its next turn, or as soon as any probe or render "
         "in flight returns.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""
bash -- the escape hatch, allowlisted.

Not a security boundary: `uv run python -c "import os; os.system(...)"` walks
straight through it, and `probe` runs arbitrary Python by design. It prevents
accidents and leaves an audit trail. The threat model is a local single-user
notebook, not an adversary.

The load-bearing line is subprocess.run(argv) with a LIST -- no shell, so the
operators have nothing to reach. Rejecting them explicitly just gives a clear
message instead of a confusing argument error.
"""

import shlex
import subprocess

from ..text import tail

# Deliberately no `git log` / `git show`: the first run of this system spent
# eight consecutive turns on git archaeology trying to answer a question about
# the zoom climb. `check.py` shells to git itself for the one workflow that
# needs history, so the agent never has to.
ALLOWED = [("uv", "run", "quarto"), ("uv", "run", "python"),
           ("git", "status"), ("git", "diff")]
FORBIDDEN = set("&|;`$><\n")

# The one allowlisted command that must not be run from inside a turn. `uv run
# python` covers it, so the allowlist alone cannot: `check.py` IS a python
# script, and a legitimate one -- the write phase runs it at the end of every
# chapter that refactored. Run from a TURN it is pure loss.
#
# Measured, 2026-09-18: one run called it five times, at 2m25s, 1m26s, 3m33s,
# 2m23s and 3m13s. Thirteen minutes, against roughly twenty-seven minutes of
# real work in that run -- about half of it -- to learn what the phase was
# going to check anyway, while its freeze-stashing raced another agent's
# render. The model was not being wilful: rule 12's remediation used to print
# the exact command, so it copied it. Rule 12 no longer does, and this is the
# belt to that braces, because rewording alone has failed once already.
CHECKERS = ("check.py", "freezediff.py")


def bash(notebook, command):
    if FORBIDDEN & set(command):
        return "rejected: shell operators (& | ; ` $ > <) are not permitted"
    argv = shlex.split(command)
    hit = next((a.rsplit("/", 1)[-1] for a in argv
                if a.rsplit("/", 1)[-1] in CHECKERS), None)
    if hit:
        return (f"rejected: {hit} is the write phase's job, not a turn's. The "
                f"phase runs it once, after lint passes and the entry builds, and shows you "
                f"any answer that moved"
                + (" — and it re-renders the notebook to do so, minutes per "
                   "call" if hit == "check.py" else "")
                + ". Carry on with the entry.")
    if not any(tuple(argv[:len(p)]) == p for p in ALLOWED):
        allowed = ", ".join(" ".join(p) for p in ALLOWED)
        return (f"rejected: {' '.join(argv[:2]) if argv else '(empty)'} is not "
                f"allowlisted. Allowed: {allowed}")
    # stdin=DEVNULL for the reason given in probe.py: an inherited terminal
    # stdin lets any child stop the whole run with SIGTTIN when it is a
    # background job. `git` is the likeliest to try -- a pager, a credential
    # prompt -- and this tool exists to be an escape hatch, not a trapdoor.
    r = subprocess.run(argv, cwd=notebook.root.parent, capture_output=True,
                       stdin=subprocess.DEVNULL, text=True, timeout=900)
    return tail((r.stdout or "") + (r.stderr or ""))

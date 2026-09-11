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


def bash(notebook, command):
    if FORBIDDEN & set(command):
        return "rejected: shell operators (& | ; ` $ > <) are not permitted"
    argv = shlex.split(command)
    if not any(tuple(argv[:len(p)]) == p for p in ALLOWED):
        allowed = ", ".join(" ".join(p) for p in ALLOWED)
        return (f"rejected: {' '.join(argv[:2]) if argv else '(empty)'} is not "
                f"allowlisted. Allowed: {allowed}")
    r = subprocess.run(argv, cwd=notebook.root.parent, capture_output=True,
                       text=True, timeout=900)
    return tail((r.stdout or "") + (r.stderr or ""))

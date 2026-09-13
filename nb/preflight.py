"""
Invariants the agent can never fix, checked before a single token is spent.

Each of these would otherwise surface as a dead end partway through a run: the
model would read a lint failure it has no way to repair, or reach for a binary
that is not there. Five milliseconds here buys that back.
"""

import shutil
import os
import sys

from .config import Notebook, SYSTEM_INSTRUCTION
from .log import say


def check(root):
    """Return a list of failures. Empty means go."""
    notebook = Notebook(root)
    bad = []

    # Rule 11, run through the vendored linter itself rather than reimplemented,
    # so the two can never disagree about what "byte-identical" means. It covers
    # `_notebook.py` AND `_scratch/_probe_base.py` -- the second was added after
    # an improvement sat in one notebook while the scaffold still held the old
    # text, drift invisible precisely because nothing compared them.
    import lint
    for where, msg in lint._notebook_drift(notebook.root):
        bad.append(f"rule 11: {where.name if where else ''} {msg}")

    if not (notebook.root / "_quarto.yml").exists():
        bad.append(f"no _quarto.yml in {notebook.root}")

    # check.py shells out to both. Without quarto it cannot render; without git
    # it silently falls back to re-rendering everything, which is correct but
    # slow enough to look like a hang.
    for binary, why in (("quarto", "render"), ("git", "freeze scoping and diffs")):
        if shutil.which(binary) is None:
            bad.append(f"{binary} not on PATH -- needed for {why}")

    if not SYSTEM_INSTRUCTION.exists():
        bad.append(f"no system instruction at {SYSTEM_INSTRUCTION}")

    if not os.environ.get("GEMINI_API_KEY"):
        bad.append("GEMINI_API_KEY unset")

    # Deliberately NOT checked: the AeroSandbox version the API index was built
    # against. library_explorer walks the installed package on first call and
    # caches in-process, so the inventory is always the version the notebook
    # actually imports. There is no stored index to go stale.

    return bad


def main(argv):
    if not argv:
        say("usage: python -m nb.preflight <notebook>")
        return 2
    bad = check(argv[0])
    for b in bad:
        say(f"  {b}")
    say(f"\npreflight {'FAILED' if bad else 'ok'}"
          f"{f' -- {len(bad)} problem(s)' if bad else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

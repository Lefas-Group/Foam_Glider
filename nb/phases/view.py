"""
`nb view` -- build the browsable site, and refuse to do it the expensive way.

A run renders one entry, because that is all verify needs to read. Quarto writes
that page into `_site/` and regenerates neither `index.html` nor the sidebar, so
until something renders the PROJECT there is no site to open -- which is exactly
what happened the first time a notebook was built from scratch.

The reason this is guarded rather than folded into verify is the freeze. A
project render does not fail on a missing freeze, it silently RE-EXECUTES it,
and an entry's freeze is hundreds of seconds of aero solves. `aircraft-notebook`
is in that state right now: a commit swept nine chapter-04 freeze files out of
git. Rebuilding them is a legitimate thing to want and a terrible thing to
discover happening in the middle of an unrelated run, so it takes `--force`.
"""

import subprocess
import sys

from ..config import Notebook
from ..log import say, tell


def _unfrozen(notebook):
    """Entries whose freeze is missing -- the ones a project render would re-solve."""
    out = []
    for chapter in notebook.chapters():
        for entry in notebook.entries(chapter):
            f = (notebook.freeze / chapter / entry.stem
                 / "execute-results" / "html.json")
            if not f.exists():
                out.append(f"{chapter}/{entry.stem}")
    return out


def site(notebook, force=False, verbose=True):
    """
    Render the whole project, unless that would mean re-solving.

    Returns the path to the site index, or None if it skipped or failed. Never
    raises and never changes an exit code: in `write` this runs AFTER the commit
    precisely so that nothing it finds can hold an entry hostage.
    """
    holes = [] if force else _unfrozen(notebook)
    if holes:
        one = len(holes) == 1
        tell(f"  site      skipped — {len(holes)} "
              f"{'entry has' if one else 'entries have'} no freeze, and a "
              f"project render would re-solve {'it' if one else 'them'}:")
        for h in holes[:5]:
            tell(f"              {h}")
        if len(holes) > 5:
            tell(f"              … and {len(holes) - 5} more")
        tell(f"              `python -m nb view {notebook.root.name} --force` "
              f"to rebuild them anyway")
        return None

    r = subprocess.run(["quarto", "render", str(notebook.root)],
                       cwd=notebook.root, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        tell("  site      render FAILED — the entry is committed either way")
        for line in tail:
            tell(f"              {line[:120]}")
        return None

    index = notebook.root / "_site" / "index.html"
    if verbose:
        tell(f"  site      {index}")
    return index


def main(argv):
    if not argv:
        tell("usage: python -m nb view <notebook> [--force]")
        return 2
    force = "--force" in argv
    return 0 if site(Notebook(argv[0]), force=force) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

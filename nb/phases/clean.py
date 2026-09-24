"""
`nb clean` -- drop the run directories nothing needs any more.

Runs accumulate forever: `_scratch/runs/<id>/` per question, each holding a
transcript, a status log, `run.json` and the probe script. The board caps what
it DISPLAYS at ten; nothing capped what was on disk.

Two rules, and the second is the one that matters:

  * a live run is never touched -- `runstate.alive()` reads the pid, and a run
    mid-probe would lose its question and its log underneath it;
  * a run whose CHAPTER still has uncommitted changes is reported, never
    deleted, however old it is.

That second rule exists because of a real morning: a run died on max turns with
its entry finished but uncommitted, and the entry was recovered by hand from the
working tree the next day. Scratch is disposable; a working tree is not, and a
tool that cannot tell them apart should delete neither.

Nothing happens without `--yes`. A dry run is the default because the useful
output here is usually the LIST -- "which of these dead runs left something
behind" -- and not the deletion.
"""

import re
import shutil
import subprocess
import sys

from ..config import Notebook
from ..log import tell
from .. import runstate

KEEP = 5
# A run id is a timestamp and a suffix; anything shaped like one was MEANT as
# one, so a near miss is an error rather than a silently ignored argument.
RUN_ID = re.compile(r"\d{8}-[0-9a-f]")


def _dirty_chapters(notebook):
    """Chapter directories with uncommitted changes, by name."""
    try:
        out = subprocess.run(
            # -uall: without it git collapses an untracked directory to one
            # line ("chapters/06-new/"), and a chapter that exists only in the
            # working tree -- a scaffold from a run that died before its commit,
            # which is exactly the case worth protecting -- is the untracked
            # case. Naming every file costs nothing at this size.
            ["git", "status", "--porcelain", "-uall", "--",
             str(notebook.root)],
            cwd=notebook.root.parent, capture_output=True, text=True,
            timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    dirty = set()
    for line in out.splitlines():
        parts = line[3:].split("/")
        if "chapters" in parts:
            i = parts.index("chapters")
            if len(parts) > i + 1:
                dirty.add(parts[i + 1])
    return dirty


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb clean <notebook> "
             "[--keep N] [--yes]")
        return 2
    notebook = Notebook(argv[0])
    keep = KEEP
    if "--keep" in argv:
        try:
            keep = int(argv[argv.index("--keep") + 1])
        except (IndexError, ValueError):
            tell("  --keep wants a number")
            return 2
    commit = "--yes" in argv

    # NAMING ONE RUN. Without this the only way to drop a specific run is to
    # pick a --keep that happens to exclude it, which drops whatever else falls
    # below the line -- done once by accident, on a run nobody had asked about.
    named = None
    for a in argv[1:]:
        if a.startswith("--") or a == str(keep):
            continue
        if not RUN_ID.match(a):
            continue
        named = a

    dirty = _dirty_chapters(notebook)
    runs = notebook.runs()                      # newest first
    if named is not None:
        runs = [d for d in runs if d.name == named]
        if not runs:
            tell(f"  no such run: {named}")
            return 1
        keep = 0                                # the named one is the candidate
    if not runs:
        tell(f"  no runs under {notebook.scratch / 'runs'}")
        return 0

    drop, held, seen = [], [], 0
    for d in runs:
        state = runstate.read(d)
        alive = runstate.alive(state)
        chapter = state.get("chapter")
        if alive is not False:
            held.append((d, "running"))
        elif chapter and chapter in dirty:
            held.append((d, f"{chapter} has uncommitted changes"))
        elif seen < keep:
            seen += 1
            held.append((d, f"recent ({seen}/{keep})"))
        else:
            drop.append(d)

    for d, why in held:
        tell(f"  keep      {d.name}  — {why}")
    for d in drop:
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        tell(f"  {'drop  ' if commit else 'would drop'}  {d.name}  "
             f"— {size / 1024:.0f} kB")
        if commit:
            shutil.rmtree(d, ignore_errors=True)

    if not drop:
        tell("  nothing to drop.")
    elif not commit:
        tell(f"\n  {len(drop)} run(s) would be removed. Add --yes to do it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

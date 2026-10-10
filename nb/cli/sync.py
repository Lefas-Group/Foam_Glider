"""
`nb sync` -- push the scaffold seed into the notebooks that track it.

`_notebook.py` is VENDORED: every notebook holds a copy, because Quarto execs
it at render time and a notebook must render without `nb` installed. Rule 11
pins each copy byte-identical to `nb/scaffold/_notebook.py`, so improving the
seed breaks every notebook at once until each is re-copied.

That re-copy was a `cp` nobody was reminded to run. Observed twice in one
afternoon of editing the seed: three notebooks silently failed rule 11, and
the failure surfaces as a BLOCKING lint finding inside the next run -- which
cannot fix it, cannot write `_notebook.py`, and cannot even read the seed to
copy from, because `nb/` is outside the probe sandbox on purpose. An
unactionable blocker is the worst shape a finding can take; `verifiers.py`
now demotes it to a warning addressed here, and this is where it gets fixed.

A NOTEBOOK THAT DRIFTED ON PURPOSE IS NEVER OVERWRITTEN. Most notebooks in a
repo like this one are frozen corpus or another skill's -- they drift
deliberately and rule 11 does not speak for them. There is no way to tell
"stale copy of the previous seed" from "deliberately edited" by looking at
one file, so this does not guess: it syncs a notebook whose copy matches some
EARLIER committed seed, which is exactly what "stale" means, and reports
everything else for a person to decide. `--force` overrides, one notebook at
a time, never in bulk.
"""

import pathlib
import subprocess
import sys

from ..config import SCAFFOLD
from ..process.log import tell
from .new import COPIED_VERBATIM

#: Where the repo's notebooks live -- the parent of `nb/` itself.
REPO = pathlib.Path(__file__).resolve().parent.parent.parent


def _notebooks():
    """Every directory that is a notebook, by the one test that defines it."""
    return sorted(p for p in REPO.iterdir()
                  if p.is_dir() and (p / "chapters").is_dir())


def _seed_history(name):
    """
    Every committed version of the seed file, as bytes. -> {blob}

    This is what separates STALE from DELIBERATE. A copy equal to some
    earlier commit of the seed is one that simply has not been updated; a
    copy equal to nothing the seed has ever been is somebody's edit, and
    overwriting it would destroy work no one asked to lose.
    """
    rel = f"nb/scaffold/{name}"
    try:
        revs = subprocess.run(
            ["git", "log", "--format=%H", "--", rel],
            cwd=REPO, capture_output=True, text=True, timeout=30, check=False,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return set()
    out = set()
    for r in revs:
        try:
            blob = subprocess.run(
                ["git", "show", f"{r}:{rel}"],
                cwd=REPO, capture_output=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if blob.returncode == 0:
            out.add(blob.stdout)
    return out


def main(argv=()):
    force = "--force" in argv
    named = [a for a in argv if not a.startswith("-")]

    todo = _notebooks()
    if named:
        want = {n.rstrip("/") for n in named}
        todo = [p for p in todo if p.name in want]
        missing = want - {p.name for p in todo}
        for m in sorted(missing):
            tell(f"  {m:28} not a notebook here")
        if not todo:
            return 2

    synced = held = 0
    for seed_name, dest_name in COPIED_VERBATIM:
        seed = SCAFFOLD / seed_name
        if not seed.exists():
            tell(f"  the seed {seed} is missing -- nothing to sync from")
            return 1
        want = seed.read_bytes()
        history = None
        for nb in todo:
            dest = nb / dest_name
            if not dest.exists():
                tell(f"  {nb.name:28} has no {dest_name} — not a notebook "
                     f"this syncs")
                continue
            have = dest.read_bytes()
            if have == want:
                continue
            # LAZILY, because walking the seed's history costs a `git show`
            # per commit and most invocations have nothing to sync.
            if history is None:
                history = _seed_history(seed_name)
            if have in history or force:
                dest.write_bytes(want)
                synced += 1
                tell(f"  {nb.name:28} {dest_name} updated"
                     + ("  (forced)" if force and have not in history else ""))
            else:
                held += 1
                tell(f"  {nb.name:28} {dest_name} DIFFERS and matches no "
                     f"committed seed — it was edited here. Left alone; "
                     f"`nb sync {nb.name} --force` overwrites it.")

    if not synced and not held:
        tell("  every notebook already tracks the seed")
    elif held:
        tell(f"  {synced} synced, {held} left for you to decide")
    return 0


if __name__ == "__main__":
    sys.exit(main(tuple(sys.argv[1:])))

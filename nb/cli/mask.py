"""
`nb mask <notebook> [name ...] [--all] [--force]` -- cut the reference masks.

ONE COMMAND, because the alternative was a throwaway script per photograph and
that is where the errors lived. Cuts with a pinned segmentation model; see
`nb/tools/masks.py` for which, why, and what it was measured against.

OVERWRITING A MASK IS THE DANGEROUS CASE, and this is the only place that
knows it. A mask is an INPUT to a fit whose output is already committed and
frozen, and nothing in the system notices when it changes: Quarto's
`freeze: auto` keys on the `.qmd` alone, `nb/build/render.py` compares page
against freeze by mtime, and rule 12's staleness list names `_model.py`,
`_analysis.py`, `_model.qmd`, `_inputs.yml` and `_fork.yml` -- not
`_reference/`. So a re-cut silently falsifies every rendered number taken from
the old mask, and rule 45 would not catch it either because it reads the
frozen markdown.

Those numbers are load-bearing. The F-16's `2026-10-08-01` hero value IS the
chamfer residual against its mask; `2026-10-08-02`'s hero is a share of that
residual plus three hand-typed millimetre figures read off the overlay; the
Tubby B-17's `2026-10-05-02` hero is its silhouette fit percentage. So a
notebook with committed entries refuses to have an existing mask overwritten,
and says why. A notebook with none -- a fresh aircraft -- is free.
"""

import sys

from ..config import Notebook
from ..process.log import tell
from ..tools import figures, masks


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb mask <notebook> "
             "[name ...] [--all] [--force]")
        return 2
    notebook = Notebook(argv[0])
    flags = {a for a in argv[1:] if a.startswith("--")}
    names = [a for a in argv[1:] if not a.startswith("--")]
    model = _opt(argv, "--model") or masks.MODEL
    redo = "--all" in flags
    force = "--force" in flags

    photos = figures.reference_paths(notebook)
    if not photos:
        tell(f"  no photographs in {notebook.root / figures.REFERENCE_DIR}.")
        return 2
    wanted = names or [p.stem for p in photos]
    known = {p.stem for p in photos}
    for n in wanted:
        if n not in known:
            tell(f"  no photograph {n!r}. Present: {', '.join(sorted(known))}")
            return 2

    have = {p.stem for p in photos if figures.mask_for(p)}
    todo = [n for n in wanted if redo or names or n not in have]
    clash = [n for n in todo if n in have]

    if clash and not redo and not names:
        todo = [n for n in todo if n not in clash]
    if clash and (redo or names) and not force:
        entries = _committed(notebook)
        if entries:
            tell(f"  {len(clash)} mask(s) already exist and this notebook has "
                 f"{len(entries)} COMMITTED ENTRIES.")
            tell("    A mask is an input to fits already rendered and frozen,"
                 " and nothing notices")
            tell("    it changing -- freeze tracks the page, not _reference/"
                 " -- so re-cutting")
            tell("    silently falsifies whatever those entries took from the"
                 " old mask.")
            for e in entries[:6]:
                tell(f"      {e}")
            if len(entries) > 6:
                tell(f"      ... and {len(entries) - 6} more")
            tell("    Re-render those entries yourself if you mean it:")
            tell(f"      uv run --group nb python -m nb mask "
                 f"{notebook.root.name} {' '.join(clash)} --force")
            return 2

    if not todo:
        tell(f"  every photograph in {notebook.root.name} already has a mask. "
             f"`--all` re-cuts them.")
        return 0

    tell(f"  notebook  {notebook.root.name}")
    tell(f"  model     {model}")
    # Measured: about a minute a photograph on CPU, plus ~40 s once for the
    # session. Said out loud because the first run looks hung otherwise, and
    # the first run of all also downloads 214 MB of weights.
    tell(f"  cutting   {len(todo)} photograph(s), about a minute each")
    for n in todo:
        _, report = masks.cut(notebook, n, model=model)
        tell(f"  {report}")
    tell(f"\n  {len(todo)} mask(s) cut. LOOK AT THE OVERLAYS -- the model "
         f"reports nothing when it is")
    tell("  wrong, and a mask missing half an aircraft still looks like a "
         "mask. Then:")
    tell(f"    uv run --group nb python -m nb reference {notebook.root.name}")
    return 0


def _committed(notebook):
    """Entry paths a re-cut could falsify, newest first. [] for a fresh one."""
    out = []
    for chapter in sorted(notebook.chapters_dir.glob("*")):
        if chapter.is_dir():
            out += [f"{chapter.name}/{p.name}"
                    for p in sorted(chapter.glob("[0-9]*.qmd"))]
    return sorted(out, reverse=True)


def _opt(argv, flag):
    if flag in argv and argv.index(flag) + 1 < len(argv):
        return argv[argv.index(flag) + 1]
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

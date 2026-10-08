"""
`nb reference <notebook> [--overlays] [--listing]` -- the photographs, checked.

THE PRE-FLIGHT BEFORE THE FIRST `nb ask`. Three things decide whether a
reconstruction can be checked at all, and before this command they were three
separate `python -c` snippets in a skill document, which is to say they were
run when someone remembered.

  * Is every photograph usable -- labelled `photo`, with a mask beside it?
  * Is each mask the SAME SIZE as its photograph? Nothing else asks. The fit
    takes `H, W` from the mask and then indexes the photograph with it, and
    seeds scale and translation from the mask bounding box, so a mis-sized
    mask does not fail loudly -- it returns a pose in the wrong coordinate
    frame, with a residual, looking like an answer.
  * How far apart are the viewpoints? One camera position pins down what it
    happens to show and nothing else, so shape faults survive in exactly the
    directions nobody photographed.

Refuses on what cannot be deliberate and reports the rest, which is the rule
`_reference_problems` already applies at launch: a mask that is not its
photograph's size is a mistake every time, while no photographs at all, or
two of the same, are judgements a coordinator may have made.
"""

import sys

from ..config import Notebook
from ..process.log import tell
from ..tools import figures

#: Above this, two frames are one viewpoint. Matches `duplicate_photos`.
SAME_VIEWPOINT = 0.80


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb reference <notebook> "
             "[--overlays] [--listing]")
        return 2
    notebook = Notebook(argv[0])
    draw = "--overlays" in argv
    show_listing = "--listing" in argv

    tell(f"  notebook  {notebook.root.name}")
    photos = figures.reference_photos(notebook)
    assets = figures.reference_paths(notebook)

    if not assets:
        tell(f"  NOTHING in {notebook.root / figures.REFERENCE_DIR}. "
             f"Nothing will check the shape of this aircraft.")
        return 1

    # The full `.txt` of every asset is what the RUN is told, not a check --
    # four descriptions is a page of prose, and a table nobody scrolls past is
    # a table nobody reads. Behind a flag, for when the question is what the
    # brief will actually say.
    if show_listing:
        listing = figures.reference_listing(notebook)
        if listing:
            tell("\n  as the run will be told")
            tell(listing.rstrip())

    bad = _report_masks(notebook, assets, photos)
    _report_spread(notebook, photos)

    for p in figures.misplaced_references(notebook):
        tell(f"\n  a stray _reference/ sits at {p} and is read by nothing.")

    if draw:
        bad += _draw(notebook, photos)

    if bad:
        tell(f"\n  {bad} photograph(s) a run cannot use. Fix before asking.")
        return 1
    tell(f"\n  {len(photos)} photograph(s) usable.")
    return 0


def mismatched_masks(notebook):
    """[(name, photo_size, mask_size)] where the two differ. [] when all match.

    Lifted out for `_reference_problems` to refuse on at launch: this is the
    one reference fault that is never deliberate, and the only one nothing
    else in the system detects.
    """
    from ..tools import masks

    out = []
    for name, _, _ in figures.reference_photos(notebook):
        s = masks.stats(notebook, name)
        if not s["matches"]:
            out.append((name, s["photo_size"], s["mask_size"]))
    return out


def _report_masks(notebook, assets, photos):
    """One line per asset, size check included. -> count of unusable ones."""
    from ..tools import masks

    tell(f"\n    {'photograph':16s} {'photo':9s} {'mask':9s} "
         f"{'area':6s}  extent")
    bad = 0
    usable = {name for name, _, _ in photos}
    for p in assets:
        kind = figures.reference_kind(p)
        if kind != "photo":
            tell(f"    {p.stem:16s} labelled {kind or 'nothing'!r}, "
                 f"so no overlay will use it")
            continue
        if p.stem not in usable:
            tell(f"    {p.stem:16s} NO MASK -- a photograph without one "
                 f"cannot be compared against")
            bad += 1
            continue
        s = masks.stats(notebook, p.stem)
        photo = "%dx%d" % s["photo_size"]
        mask = "%dx%d" % s["mask_size"]
        if s["empty"]:
            tell(f"    {p.stem:16s} {photo:9s} {mask:9s} MASK IS EMPTY")
            bad += 1
            continue
        if not s["matches"]:
            tell(f"    {p.stem:16s} {photo:9s} {mask:9s} SIZE MISMATCH -- the "
                 f"fit takes its frame from the mask, so this pose would come "
                 f"back in the wrong coordinates")
            bad += 1
            continue
        y0, y1, x0, x1 = s["bbox"]
        tell(f"    {p.stem:16s} {photo:9s} {mask:9s} {s['area_frac']:<6.4f}  "
             f"rows {y0}-{y1} cols {x0}-{x1}")
    return bad


def _report_spread(notebook, photos):
    """The pairwise viewpoint overlap, every pair, worst-first."""
    if len(photos) < 2:
        tell(f"\n  only {len(photos)} photograph(s): every shape fault not "
             f"visible from that one camera survives.")
        return
    pairs = figures.duplicate_photos(notebook, threshold=0.0)
    if not pairs:
        return
    tell("\n  viewpoint spread (mask IoU, centred on each centroid)")
    for a, b, iou in sorted(pairs, key=lambda t: -t[2]):
        note = "  <- ONE VIEWPOINT, not two" if iou >= SAME_VIEWPOINT else ""
        tell(f"    {a:16s} {b:16s} {iou:.2f}{note}")
    worst = max(iou for _, _, iou in pairs)
    if worst >= SAME_VIEWPOINT:
        tell("    Two frames from one shoot fit one pose and hide the same "
             "faults. A hard mask is work to do, not a reason to drop an "
             "angle.")


def _draw(notebook, photos):
    """Re-render every overlay into _scratch/. -> count that would not draw."""
    from ..tools import masks

    tell("\n  overlays -- LOOK AT THESE. A mask that has lost a wing looks")
    tell("  plausible as a blob and is unmistakable over the photograph.")
    bad = 0
    for name, _, _ in photos:
        try:
            tell(f"    {masks.overlay(notebook, name)}")
        except SystemExit as exc:
            tell(f"    {name}: {exc}")
            bad += 1
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

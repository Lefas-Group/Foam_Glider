"""
`nb intake <notebook> …` -- the aircraft YOU built, before any coordinator runs.

THE RESEARCH PATH CANNOT REACH IT. `coord/research.py` is explicit that there
are no model-supplied paths: `fetch` writes under a generated name in the
session scratch and `add_photo` resolves only inside it, so a photograph can
arrive from a URL and from nowhere else. That boundary is load-bearing and is
not weakened here. Instead the direction of travel is reversed -- a person
types the paths in their own shell, which is the one place a path needs no
defending, and what lands on disk afterwards is indistinguishable from what
`add_photo` would have written.

SO THIS RUNS BEFORE `nb coordinate`, and it is the whole reason the brief can
be write-once and still carry a figure nobody published. `cli/new.py` reads
`_reference/INTAKE.yml` and merges these rows into the brief it writes, so the
same file serves a hand-run `nb new` and the coordinator's `new` tool; there is
one merge, not two.

WHAT IT DELIBERATELY DOES NOT DO IS MASK. `nb mask` constructs `Notebook()`,
which needs a `chapters/`, and at intake time there is none -- the aircraft
does not exist yet. Masking belongs after `new`, where the coordinator already
does it, looks at every overlay and runs `nb reference` until it is clean. A
command that cut masks here would have to half-create a notebook to do it.

`--how` IS REQUIRED FOR A MEASUREMENT, and it is the same rule as everywhere
else in this system: `nb ask` refuses a question with no `--why`, and `source`
refuses a URL this session did not fetch. A number whose provenance is
unrecorded is the one mistake `SOURCES.txt` exists to prevent, and "I measured
it" is a provenance -- "531.5 g" on its own is not.
"""

import datetime
import pathlib
import sys

from ..contract import shared
from ..coord import research
from ..process.log import tell
from ..tools import figures

USAGE = """\
usage: uv run --group nb python -m nb intake <notebook>
         --photo <slug> <path> "<where the camera is, and what the frame shows>"
         --spec   "**Wingspan**: 1200 mm, tip to tip."
         --target "**Wing loading**: 11.5 g/dm2."
         --assume "**Airfoil**: flat foam plate, a declared stand-in."
         --how    "steel tape over the top surface; kitchen scale, 1 g"
         --force

  --photo is repeatable and takes THREE values, in `add_photo`'s own order.
  --spec/--target/--assume are repeatable; see `nb doctrine the-brief.md` for
  which a figure belongs in. --how says how you measured, and is required
  with any of them."""


def _triples(argv, flag):
    """Every `--flag a b c`, in order. Refuses a short one rather than guessing."""
    out = []
    for i, a in enumerate(argv):
        if a != flag:
            continue
        got = argv[i + 1:i + 4]
        if len(got) < 3 or any(g.startswith("--") for g in got):
            raise ValueError(
                f"{flag} takes three values: a slug, a file, and the "
                f"description. Got {got or 'nothing'}.")
        out.append(tuple(got))
    return out


def _repeated(argv, flag):
    """Every `--flag value`, in order."""
    return [argv[i + 1] for i, a in enumerate(argv)
            if a == flag and i + 1 < len(argv) and not argv[i + 1].startswith("--")]


def _opt(argv, flag):
    if flag not in argv:
        return None
    i = argv.index(flag) + 1
    if i >= len(argv) or argv[i].startswith("--"):
        return None
    return argv[i]


def _held(root):
    """What a previous intake into this directory already holds."""
    return shared.parse_inputs(
        pathlib.Path(root) / figures.REFERENCE_DIR / "INTAKE.yml")


def _write_intake(root, specs, targets, assumes, photos):
    """
    `_reference/INTAKE.yml` -- the brief, held until `new` has somewhere to put it.

    SAME SHAPE AS `_inputs.yml`, written by `cli/new.py::_brief` and read by
    `shared.parse_inputs`, because it is the same data one step earlier. That
    is also why it is not real YAML and why nothing here imports a YAML
    library: `nb` has a parser for this format already and a second one could
    disagree with it.

    IT STAYS AFTER `new` HAS CONSUMED IT. `_reference/` is not rendered and is
    read by whoever comes next, which is exactly what this file is for: it says
    which rows of a brief came off a tape measure rather than a product page.

    IT DOES NOT RECORD *HOW*, and that is deliberate. Measuring an aeroplane
    takes more than one sitting, so `--how` differs between the sessions that
    build this file up -- and a single `how:` here could only hold the newest,
    which would then stand over rows it is not true of. `SOURCES.txt` writes
    one block per sitting and is the only honest home for it.
    """
    from .new import _brief

    body = _brief(specs, assumes, targets)
    out = "\n".join([
        "# WHAT THE USER SUPPLIED, written by `nb intake` and merged into the",
        "# brief by `nb new`. Not rendered. Kept afterwards as the record of",
        "# which rows were measured rather than published -- and `SOURCES.txt`",
        "# beside this file says, per sitting, how each was measured.",
        f'at: "{datetime.date.today().isoformat()}"',
    ]) + "\n" + body
    if photos:
        # The slug IS the key -- `install_photo` has already held it to
        # `figures.SLUG`, so there is nothing to derive and nothing to dedupe.
        out += "photos:\n" + "".join(
            f'  - {slug}: "{desc}"\n' for slug, desc in photos)
    (pathlib.Path(root) / figures.REFERENCE_DIR / "INTAKE.yml").write_text(out)


def main(argv):
    if not argv or argv[0].startswith("--"):
        tell(USAGE)
        return 2
    root = pathlib.Path(argv[0])
    rest = argv[1:]
    force = "--force" in rest

    try:
        photos = _triples(rest, "--photo")
    except ValueError as exc:
        tell(f"  {exc}")
        return 2
    specs = _repeated(rest, "--spec")
    targets = _repeated(rest, "--target")
    assumes = _repeated(rest, "--assume")
    how = _opt(rest, "--how")
    rows = specs + targets + assumes

    if not photos and not rows:
        tell(USAGE)
        return 2

    # THE BRIEF IS WRITE-ONCE, and this is where that is enforced for the
    # user's half of it. `_notebook.py` is what `nb new` copies in, so its
    # presence is the honest test for "the brief has been written" -- the same
    # test `coord/tools.py::_scaffolded` makes, for the same reason.
    scaffolded = (root / "_notebook.py").exists()
    if rows and scaffolded:
        tell(f"  {root.name} already has a brief, and a brief is never "
             f"superseded -- a notebook whose")
        tell(f"  specifications changed is a different aeroplane. Edit "
             f"{root / '_inputs.yml'} by hand if")
        tell(f"  a figure was wrong, and say so in the next entry.")
        tell(f"  Photographs are not the brief: `--photo` works here.")
        return 2
    if rows and not how:
        tell("  --how is required with a measurement: it is what `SOURCES.txt` "
             "records, and a")
        tell("  figure whose provenance is unrecorded is the one mistake that "
             "file exists to prevent.")
        tell('  e.g. --how "steel tape over the top surface; kitchen scale, '
             '1 g"')
        return 2

    ref = root / figures.REFERENCE_DIR
    ref.mkdir(parents=True, exist_ok=True)

    installed = []
    for slug, path, description in photos:
        got = figures.install_photo(ref, slug, path, description, force=force)
        if "error" in got:
            tell(f"  {slug}: {got['error']}")
            if got.get("taken"):
                tell(f"  Pass --force to replace it.")
            return 1
        installed.append((got["installed"], description))
        tell(f"  {got['image']:28s} {got['how']}")
        if got.get("replaced"):
            tell(f"    replaced {got['replaced']}")
        if got.get("stale_mask"):
            # NOT DELETED HERE. `cli/mask.py` is the only place that knows
            # whether a committed entry's numbers came out of this mask, and
            # it refuses to overwrite one for that reason. Saying so is this
            # command's whole duty.
            tell(f"    STALE: {got['stale_mask']} was cut from the frame "
                 f"this replaced, so it is now a")
            tell(f"    mask of a different photograph, and every pose fitted "
                 f"against it is wrong.")
            tell(f"    Re-cut it:  uv run --group nb python -m nb mask "
                 f"{root.name} {got['installed']} --force")
            tell(f"    In a notebook with committed entries that refuses and "
                 f"says what depends on it.")

    # MERGED WITH WHAT A PREVIOUS INTAKE HELD, so a second call adds rather
    # than replaces. Measuring an aeroplane is not one sitting.
    was = _held(root)
    keep = {k: [t for _, t in (was.get(k) or [])]
            for k in ("specified", "targets", "assumed")}
    # LAST WRITER WINS PER SLUG, so re-describing a frame re-describes it.
    photo_rows = list({slug: (slug, " ".join(desc.split()))
                       for slug, desc in (was.get("photos") or []) + installed
                       }.values())

    if rows or photo_rows:
        _write_intake(
            root,
            keep["specified"] + [r for r in specs if r not in keep["specified"]],
            keep["targets"] + [r for r in targets if r not in keep["targets"]],
            keep["assumed"] + [r for r in assumes if r not in keep["assumed"]],
            photo_rows)

    # ONE BLOCK PER ORIGIN, not one per row. `write_sources` writes
    # `origin\n  body`, so a body whose lines are already indented two spaces
    # continues inside the same entry -- and what the reader wants to see is
    # one measuring session with everything it produced under it.
    today = datetime.date.today().isoformat()
    sources = []
    if rows:
        sources.append((f"measured by the user, {today} -- {how}",
                        "\n  ".join(rows)))
    if installed:
        sources.append((f"photographed by the user, {today}",
                        "\n  ".join(f"{slug}: {desc}"
                                    for slug, desc in installed)))
    if sources:
        research.write_sources(root, sources)

    tell("")
    if rows:
        tell(f"  {len(rows)} brief row(s) held in "
             f"{ref / 'INTAKE.yml'},")
        tell(f"  merged into the brief by `nb new`. "
             f"{len(sources)} line(s) in SOURCES.txt.")
    if scaffolded:
        tell(f"  next:  uv run --group nb python -m nb mask {root.name}")
        tell(f"         then LOOK at every overlay -- "
             f"nb reference {root.name} --overlays")
    else:
        tell(f"  next:  uv run --group nb python -m nb coordinate "
             f"{root.name} \"<what you want built>\"")
        tell(f"         it reads what you supplied, calls `new`, and masks "
             f"from there.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

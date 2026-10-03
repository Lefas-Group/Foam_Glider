"""
read_figure -- rendered figures, as images.

An entry's prose can claim things about a figure that the figure does not show --
a caption naming a crossover at 6 m/s when the curve crosses at 8 is invisible
to every lint rule, because rule 1 forces the NUMBERS in prose to be computed
and nothing forces a claim about a SHAPE to match the shape. Reading the figure
back is the only way to check one, and after `verify` was deleted the only
reader is the agent itself.

Native rather than MCP. The figures live under `_freeze/`, outside the `chapters/`
allowlist, and the MCP filesystem server has no read-only tier -- adding `_freeze/`
would grant write access to the one directory whose integrity freezediff depends
on. Content the agent may read but not write is a tool, not a file.
"""

import base64


def figure_paths(notebook, chapter, stem=""):
    """Every rendered figure PNG for a chapter, or for one entry within it."""
    root = notebook.freeze / chapter
    if not root.exists():
        return []
    pattern = f"{stem}/figure-html/*.png" if stem else "*/figure-html/*.png"
    return sorted(root.glob(pattern))


def list_figures(notebook, chapter, stem=""):
    paths = figure_paths(notebook, chapter, stem)
    if not paths:
        return f"no rendered figures for {chapter}{'/' + stem if stem else ''}"
    return "\n".join(f"{p.parts[-3]}/{p.name}" for p in paths)


def read_probe_figure(notebook, name=""):
    """
    An image the RUN itself just produced, as bytes for an inline part.

    THE GAP THIS CLOSES. `read_figure` globs the freeze, so a run could only
    ever see a figure after rendering an entry -- it could MEASURE an image
    it built in a probe and never look at one. That blocked the whole
    arrangement where the run rasterises and stitches a plan itself: it could
    assemble a sheet and had no way to check it had assembled it correctly.

    Measured, before this existed: a coordinator stitched the tiles by hand,
    misread the tile key, dropped the LEFT WING part, and the reconstruction
    was built from the wing's assembly jigs. Nobody could see the sheet but
    the coordinator, and the coordinator got it wrong.

    Looks in the RUN DIRECTORY first and then `_scratch/`, which is where
    `probing.md` tells a probe to save and where the kernel's cwd already
    points -- so `fig.savefig("x.png")` in a probe is readable here by name
    with no path to get right.
    """
    roots = [notebook.run, notebook.root / "_scratch"]
    found = [p for r in roots if r.is_dir()
             for p in sorted(r.iterdir())
             if p.suffix.lower() in _SUFFIXES
             and (not name or p.name == name)]
    if not found:
        where = " or ".join(str(r) for r in roots)
        return {"error": f"no image {name or '*'} in {where}. Save one from a "
                         f"probe first -- `fig.savefig(\"check.png\")` lands "
                         f"in the run directory."}
    p = found[0]
    return {"_image": p.read_bytes(),
            "mime_type": _MIME.get(p.suffix.lower(), "image/png"),
            "name": p.name}


def read_figure(notebook, chapter, stem, name=""):
    """
    One figure, as raw bytes for the loop to turn into an inline image part.

    NOT base64 in the function response. That was the first shape this took, and
    it was worse than having no tool at all: the model received a 91,060-character
    string rather than an image, so vision never engaged, and ~23k tokens of noise
    entered the context per figure. Measured against the same PNG, the inline part
    costs 1,298 -- and the model reads the axis labels off it.
    """
    paths = figure_paths(notebook, chapter, stem)
    if name:
        paths = [p for p in paths if p.name == name]
    if not paths:
        return {"error": f"no figure {name or '*'} under {chapter}/{stem}. "
                         f"Available: {list_figures(notebook, chapter, stem)}"}
    p = paths[0]
    return {"_image": p.read_bytes(), "mime_type": "image/png", "name": p.name}


# =============================================================================
# `_reference/` -- what is known about the real aircraft, as pictures.
#
# AT THE NOTEBOOK ROOT, and underscored, which settles two things at once. The
# file tools are rooted at `chapters/`, so nothing here is reachable by
# `read_text_file` or writable by a run -- it is a person's input, like
# `_inputs.yml`, and geography enforces that rather than a guard. And Quarto
# skips an underscored directory, so a reference never reaches `_site`:
# measured, `_scratch/` exists in every notebook and appears in none of them.
#
# WHY A PLAN SHEET AND NOT ONLY A PHOTOGRAPH. An earlier draft of this allowed
# photographs only, on the argument that vision yields estimates where a
# measurement yields numbers. That is true only if the run reads the sheet
# with its EYES. `probe` is not sandboxed -- the kernel starts with
# `cwd=run_dir` and no path guard -- and PIL and numpy are both in the venv,
# so a 1:1 sheet rasterised at a known dpi is not a picture, it is a dataset:
#
#     a = np.array(Image.open("_reference/sheet.png").convert("L"))
#     ink = a[90:1000, 800:1080] < 160          # the h-stab part
#     ys, xs = np.nonzero(ink)                  # -> 63 x 231 mm at 100 dpi
#
# Measured on the FT Mini Corsair sheet, that h-stab is 231 mm. The run that
# had no sheet guessed 250 mm for an aircraft 1.21x larger -- about 10% out,
# on a number that sets tail volume and therefore the static margin.
#
# SO THIS TOOL IS FOR THE FIRST LOOK ONLY. `read_figure` above reads the
# freeze, so a run cannot see an arbitrary image mid-probe; one call here
# orients it -- which part is where -- and everything quantitative after that
# is numpy. The brief says so.
REFERENCE_DIR = "_reference"
_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp"}


def reference_paths(notebook):
    """Every reference image for this notebook, sorted. [] when there are none."""
    root = notebook.root / REFERENCE_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir()
                  if p.suffix.lower() in _SUFFIXES)


# WHAT AN ASSET IS, as a token rather than prose, so the brief can route on
# it instead of hoping a paragraph is read correctly. First word of the
# `.txt` beside the file; everything after it is free description.
#
# The distinction that matters is MEASURABLE or not. A 1:1 sheet at a stated
# dpi is a dataset -- PIL and numpy are in the probe kernel, and a pixel
# count times 25.4/dpi is a millimetre. A photograph is not, and a run told
# merely "image" will read dimensions off one.
KINDS = {
    "plan": "orthographic and to scale. MEASURE IT IN CODE. The scale is "
            "stated above; a pixel count times 25.4/dpi is a millimetre.",
    "photo": "PROPORTIONS AND LAYOUT ONLY. No dimension may be taken from "
             "it -- an estimate off a photograph is not a measurement.",
    "scan": "topology only, scale UNVERIFIED. Calibrate against a published "
            "figure before trusting any dimension, and say so if it "
            "disagrees.",
    "source": "not an image. Rasterise it yourself -- `pdftoppm` is on PATH "
              "and `subprocess` works in a probe. Convert EVERY page; do "
              "not trust a tile key to tell you which ones matter.",
}
_SOURCE_SUFFIXES = (".pdf",)


def reference_paths(notebook, images_only=True):
    """Every reference asset, sorted. [] when the directory is absent."""
    root = notebook.root / REFERENCE_DIR
    if not root.is_dir():
        return []
    ok = _SUFFIXES if images_only else _SUFFIXES + _SOURCE_SUFFIXES
    return sorted(p for p in root.iterdir() if p.suffix.lower() in ok)


def reference_listing(notebook):
    """
    The assets, each with its KIND and what that kind permits. "" if none.

    Includes sources `read_reference_image` cannot return -- a PDF is listed
    so the run knows to rasterise it, which is how the coordinator stops
    having to. Measured: a coordinator stitching tiles by hand misread the
    tile key and dropped the LEFT WING part, and the reconstruction was built
    from the wing's assembly jigs instead.
    """
    out = []
    for p in reference_paths(notebook, images_only=False):
        note = p.with_suffix(".txt")
        raw = note.read_text().strip() if note.exists() else ""
        kind = raw.split()[0].lower() if raw else (
            "source" if p.suffix.lower() in _SOURCE_SUFFIXES else "")
        rule = KINDS.get(kind, "unlabelled -- treat as topology only.")
        detail = " ".join(raw.splitlines()).strip()
        out.append(f"  - {p.name}\n      {detail}\n      -> {rule}")
    return "\n".join(out)


def read_reference_image(notebook, name=""):
    """One reference image, as bytes for the loop to make an inline part."""
    paths = reference_paths(notebook)
    if not paths:
        return {"error": f"no {REFERENCE_DIR}/ images in {notebook.root.name}"}
    if name:
        paths = [p for p in paths if p.name == name]
    if not paths:
        return {"error": f"no reference image {name!r}. Available:\n"
                         + reference_listing(notebook)}
    p = paths[0]
    return {"_image": p.read_bytes(),
            "mime_type": _MIME.get(p.suffix.lower(), "image/png"),
            "name": p.name}

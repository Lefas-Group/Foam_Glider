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


def reference_listing(notebook):
    """
    The assets and what each IS, for the brief. "" when there are none.

    The `.txt` beside an image carries its label -- what it is and, for a
    plan, its scale. THE SCALE IS THE POINT: a sheet with a stated dpi can be
    measured, and one without can only be looked at. A run told merely
    "image" will read dimensions off a photograph.
    """
    out = []
    for p in reference_paths(notebook):
        note = p.with_suffix(".txt")
        label = note.read_text().strip() if note.exists() else "unlabelled"
        out.append(f"  - {p.name} — {label}")
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

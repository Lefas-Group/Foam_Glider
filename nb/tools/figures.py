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
    # `<run>/_scratch` too: a probe's cwd is the run directory, so
    # `savefig("_scratch/x.png")` -- which an older brief asked for -- lands
    # in a subdirectory of it. A run spent two turns discovering that the file
    # it had just written could not be read back by name.
    roots = [notebook.run, notebook.run / "_scratch",
             notebook.root / "_scratch"]
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
# SO `read_reference_image` IS FOR THE FIRST LOOK ONLY. `read_figure` above
# reads the freeze, so a run cannot see an arbitrary image mid-probe; one call
# there orients it -- which part is where -- and everything quantitative after
# that is numpy. The brief says so.
#
# That tool is at the bottom of this file. This comment outlived its deletion
# by five days and pointed at nothing; the deletion was the accident, not the
# reasoning.
REFERENCE_DIR = "_reference"
_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp"}


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


# A SUBJECT MASK, beside its photograph: `studio.jpg` -> `studio.mask.png`.
#
# Cut by the coordinator, never by a run: a bad mask poisons every pose fitted
# against it and nothing downstream catches that.
#
# This comment used to say segmentation itself could not be automated. That was
# true of the per-pixel colour rules it was written about -- they have no
# notion of OBJECT, and they failed exactly where tone does not separate
# subject from ground, dropping every shaded surface on one aircraft and taking
# in the hand holding another. It is no longer true. `nb mask` cuts with a
# pinned model that scored IoU 0.950 against all 13 committed masks and 0.992
# against the one that is exactly right, with a cleaner boundary than any of
# them.
#
# WHAT CANNOT BE AUTOMATED IS LOOKING AT THE RESULT. The model reports nothing
# when it is wrong, so `nb mask` writes a tinted overlay every time and
# `nb reference` scores the boundary. Neither can read it for you.
MASK_SUFFIX = ".mask.png"


def mask_for(path):
    """The mask beside an image, or None. `studio.jpg` -> `studio.mask.png`."""
    m = path.with_name(path.stem + MASK_SUFFIX)
    return m if m.exists() else None


def reference_paths(notebook, images_only=True):
    """
    Every reference asset, sorted. [] when the directory is absent.

    Masks are excluded: they are an input to the pose fit, not an asset to
    be looked at, and listing them would offer the run a picture of a blob.
    """
    root = notebook.root / REFERENCE_DIR
    if not root.is_dir():
        return []
    ok = _SUFFIXES if images_only else _SUFFIXES + _SOURCE_SUFFIXES
    return sorted(p for p in root.iterdir()
                  if p.suffix.lower() in ok and not p.name.endswith(MASK_SUFFIX))


def reference_kind(path):
    """The first word of the `.txt` beside an asset, or "" if unlabelled."""
    note = path.with_suffix(".txt")
    try:
        raw = note.read_text().strip()
    except OSError:
        return "source" if path.suffix.lower() in _SOURCE_SUFFIXES else ""
    return raw.split()[0].lower() if raw else ""


def reference_photos(notebook):
    """
    [(name, image_path, mask_path)] the overlay can actually use.

    A photograph qualifies only with a mask beside it. One without is still
    listed in the brief -- as unusable, so the coordinator sees what it has
    to cut rather than wondering why nothing compared.
    """
    out = []
    for p in reference_paths(notebook):
        if reference_kind(p) != "photo":
            continue
        m = mask_for(p)
        if m is not None:
            out.append((p.stem, p, m))
    return out


def reference_listing(notebook):
    """
    The assets a RUN may use, each with its kind and what that kind permits.
    "" if none.

    A SOURCE PLAN IS NOT LISTED. It is the coordinator's to read: they
    transcribe the figures the plan prints into the brief, and the run works
    from those. Measuring a drawing is the step neither party does well --
    a coordinator hand-stitching tiles misread the tile key and dropped the
    LEFT WING part, and a run given the tiles instead spent most of its turns
    rasterising, stitching and cross-checking a document whose own
    specification table already stated the answer. The overlay diagnoses
    shape; the printed figures fix scale; the drawing itself is needed for
    neither.
    """
    out = []
    for p in reference_paths(notebook, images_only=True):
        note = p.with_suffix(".txt")
        raw = note.read_text().strip() if note.exists() else ""
        kind = reference_kind(p)
        rule = KINDS.get(kind, "unlabelled -- treat as topology only.")
        detail = " ".join(raw.splitlines()).strip()
        if kind == "photo":
            rule = ("usable: `compare_to_photo(airplane, \"%s\")`" % p.stem
                    if mask_for(p) is not None else
                    "NO MASK beside it, so nothing can be fitted against it.")
        out.append(f"  - {p.name}\n      {detail}\n      -> {rule}")
    return "\n".join(out)


def read_reference_image(notebook, name=""):
    """
    One reference photograph, as bytes for the loop to make an inline part.

    THE RUN'S ONLY WAY TO SEE THE AIRCRAFT. Everything else it can look at
    is something it made: `read_figure` globs the freeze, so a figure has to
    be rendered first, and `read_probe_figure` reads the run directory, so a
    probe has to have drawn it. `compare_to_photo` reaches `_reference/` but
    draws the MODEL over the photograph, which requires the model to exist.
    Without this there is no point in a reconstruction at which the subject
    can be looked at before it is built.

    MEASURED, FT A-10 Warthog, 2026-10-10. Turn 2, with no way to look:

        "Let's break down the geometry into its components: the wing,
         fuselage, nacelles, horizontal stabilizer, and twin vertical
         stabilizers. THE REAL A-10 has a constant-chord center wing
         section... the other values will be based on estimates from the
         REAL A-10."

    It listed the components of the jet it remembered, not of the foam
    aircraft in the photographs, and built a nacelle pylon that appears in
    none of them -- as a lifting surface, carrying area and lift into two
    later entries. A wrong COMPONENT LIST is the one error `fit_geometry`
    cannot repair: it moves named constants and can neither delete a surface
    nor invent one. So the list has to come from the photograph, and the
    photograph has to be reachable before the model exists.

    THIS FUNCTION EXISTED AND WAS DELETED by 78bef1a, a forty-file sweep
    that landed `compare_to_photo` and cleared a dozen scratch scripts under
    the message "READNE update". The comment that justifies it survived the
    deletion and sat orphaned above `REFERENCE_DIR` for five days: "SO THIS
    TOOL IS FOR THE FIRST LOOK ONLY... one call here orients it -- which
    part is where -- and everything quantitative after that is numpy." That
    reasoning was never withdrawn; only the code was.

    ONE LOOK, FOR TOPOLOGY. `KINDS["photo"]` already states the rule the
    brief repeats -- proportions and layout only, no dimension off a
    photograph. What this answers is "what parts does it have, and roughly
    where", which is exactly what vision is reliable for and exactly what
    the model needs before its first line.

    Masks are not reachable: `reference_paths` excludes them, because a run
    looking at a white blob learns nothing and the mask is an input to the
    fit rather than a picture of the aircraft.
    """
    paths = reference_paths(notebook)
    if not paths:
        return {"error": f"no {REFERENCE_DIR}/ images in {notebook.root.name}. "
                         f"This notebook has no photographs, so nothing can "
                         f"check the shape -- build from the brief, declare "
                         f"what you supply, and say the shape is unverified."}
    if name:
        hit = [p for p in paths if p.name == name or p.stem == name]
        if not hit:
            return {"error": f"no reference image {name!r}. Available:\n"
                             + reference_listing(notebook)}
        paths = hit
    p = paths[0]
    return {"_image": p.read_bytes(),
            "mime_type": _MIME.get(p.suffix.lower(), "image/png"),
            "name": p.name}




# =============================================================================
# WHAT THE COORDINATOR GOT WRONG, said at launch rather than discovered later.
#
# `_reference/` is a path a person types, and there is no error when they type
# it wrong: `reference_photos` returns [], the brief takes its "there is
# nothing to check the shape against" branch, and the run builds blind. That
# branch is correct -- a notebook may legitimately have no photograph -- which
# is exactly why a mistake hides in it. Measured, on this notebook: two
# photographs were copied to `mini-explorer/mini-explorer/_reference/` because
# the shell was still inside the notebook directory, the run launched with an
# empty reference set, and an entry's worth of turns was spent reconstructing
# an airframe that nothing checked the shape of. Nothing anywhere said so.
#
# So these two functions are the launch's half: one names a directory that
# exists in the wrong place, the other names photographs that are the same
# photograph. Neither is a lint rule, because neither is about the notebook
# being wrong -- they are about the INPUTS being wrong, and the only party who
# can fix an input is the one standing at the terminal when the run starts.
_SKIP_DIRS = {"_site", "_freeze", "_scratch", ".quarto", ".git"}


def misplaced_references(notebook):
    """
    `_reference` directories under the notebook that are NOT the one read.

    [] when there is nothing to report. The usual cause is a copy made from
    inside the notebook directory, which lands at `<nb>/<nb>/_reference`.
    """
    root = notebook.root
    real = root / REFERENCE_DIR
    out = []
    for p in root.rglob(REFERENCE_DIR):
        if not p.is_dir() or p == real:
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return sorted(out)


def duplicate_photos(notebook, threshold=0.80):
    """
    [(a, b, iou)] for photograph pairs whose MASKS are near-identical.

    A SECOND VIEWPOINT IS THE POINT of a second photograph. Two frames from
    one shoot -- the same aircraft, the same camera, a decal set added
    between them -- fit the same pose and hide the same faults, so the run
    spends a turn on the second overlay and learns nothing it did not already
    know. Measured here at IoU 0.87 on a pair that looked like two checks.

    Masks are compared after centring on their own centroid IN A COMMON
    CANVAS, so this reports a repeated VIEWPOINT rather than a repeated
    framing -- and so that two frames cropped to different sizes are still
    compared. They used to be skipped, which meant the one pair most likely
    to be two crops of one shoot was the one pair never checked: the F-16's
    1280x1280 and 1280x985 frames got no comparison at all, at launch or
    anywhere else. Returns [] if numpy or PIL is unavailable: a warning is
    not worth an import error.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return []

    def read(mask_path):
        a = np.array(Image.open(mask_path).convert("L")) > 128
        return a if a.any() else None

    photos = reference_photos(notebook)
    loaded = []
    for name, _, mask in photos:
        try:
            m = read(mask)
        except OSError:
            m = None
        if m is not None:
            loaded.append((name, m))
    if not loaded:
        return []

    # One canvas for every mask, big enough that nothing centred into it is
    # clipped. Sized from the masks themselves rather than a constant so a
    # pair of 4000 px frames is not quietly downsampled into agreement.
    ch = 2 * max(m.shape[0] for _, m in loaded)
    cw = 2 * max(m.shape[1] for _, m in loaded)

    def centred(m):
        out = np.zeros((ch, cw), bool)
        ys, xs = np.nonzero(m)
        y0 = int(ch // 2 - ys.mean())
        x0 = int(cw // 2 - xs.mean())
        out[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
        return out

    loaded = [(name, centred(m)) for name, m in loaded]

    out = []
    for i, (na, ma) in enumerate(loaded):
        for nb_, mb in loaded[i + 1:]:
            union = (ma | mb).sum()
            if not union:
                continue
            iou = float((ma & mb).sum() / union)
            if iou >= threshold:
                out.append((na, nb_, iou))
    return out

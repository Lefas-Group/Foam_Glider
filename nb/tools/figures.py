"""
read_image -- every picture a run may look at, and the `_reference/` inputs.

ONE READER, THREE SOURCES: what a probe just drew, the photographs of the real
aircraft, and the figures an entry rendered. They were three tools with three
declarations and one shape between them; see `read_image` at the foot of this
file for what merging them fixed.

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

# STDLIB ONLY at module level, deliberately. This module is imported into a
# notebook render and into a probe kernel, so the heavy readers -- numpy, PIL
# -- are imported inside the functions that need them, and nothing here costs
# anything to have around.
import base64
import pathlib
import re
import shutil


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
# SO A PHOTOGRAPH IS FOR THE FIRST LOOK ONLY. `read_image`, at the foot of
# this file, is the one way a run sees one: a call orients it -- which part is
# where -- and everything quantitative after that is numpy. The brief says so.
#
# This paragraph has already outlived one deletion. The tool it described was
# removed in a forty-file sweep and the reasoning was left here pointing at
# nothing for five days, which is how the blind spot it warns about came back.
# It is written against the ROLE now rather than against a tool name, so the
# next rename cannot orphan it again.
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
    return _paths_in(notebook.root / REFERENCE_DIR, images_only)


def _paths_in(root, images_only=True):
    """The same, for a `_reference/` directory with no notebook around it yet.

    `install_photo` and `nb intake` both run BEFORE `nb new` has made the
    directory a notebook, so they have a path and nothing to call `.root` on.
    """
    root = pathlib.Path(root)
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


# =============================================================================
# WRITING into `_reference/`, which is the other half of reading it.
#
# TWO DOORS, ONE DOOR FRAME. `coord/research.py::add_photo` installs a frame the
# coordinator fetched off the web; `cli/intake.py` installs one the user shot
# themselves and named in their own shell. Everything that is true of
# `_reference/` is true of both -- the slug, the readable format, the
# eight-word description, and above all the `.txt` written in the same breath
# as the image -- so it is written ONCE, here, beside the `reference_kind` that
# reads it back.

#: A photograph's name. No dots, because `reference_kind` finds the `.txt`
#: beside an image with `with_suffix`, which would eat the tail of `nose-on.v2`.
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}$")

#: What may ARRIVE. Wider than `_SUFFIXES`, which is what the notebook picks
#: up: a HEIC off a phone is a perfectly good frame in a format nothing
#: downstream reads, so it is accepted here and converted below.
_READABLE = _SUFFIXES + (".heic", ".heif", ".tif", ".tiff", ".bmp")

#: Long edge, in pixels, above which an incoming frame is downscaled.
#:
#: MEASURED RATHER THAN CHOSEN: every reference image committed to this repo is
#: between 480 and 1280 px on its long edge, the pinned segmentation model runs
#: at 1024 square, and `_reference/` is committed -- so the 4032 px a phone
#: produces costs megabytes of permanent history and buys no resolution that
#: anything downstream reads.
MAX_EDGE = 2048

#: EXIF orientation. `0x0112` rather than a name, because the name lives in
#: `PIL.ExifTags` and this module imports PIL lazily on purpose.
_ORIENTATION = 0x0112


def install_photo(ref_dir, slug, src, description, force=False):
    """
    Write `<slug>.<ext>` and `<slug>.txt` into `_reference/`. -> dict.

    ONE CALL, NOT TWO, and that is why this is a function rather than four
    lines at each of its two call sites. A photograph whose sibling `.txt` is
    missing is not `kind: photo` to `reference_kind`, so it is not silently
    broken -- it is silently ABSENT: `reference_paths` skips it, a run launches
    with one fewer viewpoint and says so honestly, and nothing points at the
    file that was supposed to be there. Writing both together makes an
    undescribed photograph unrepresentable rather than merely discouraged.

    Reports faults in the return value rather than raising. Both callers answer
    to somebody -- a model reading a tool result, a person reading a terminal
    -- and neither is served by a traceback.
    """
    slug = str(slug).strip().lower()
    if not SLUG.match(slug):
        return {"error": f"{slug!r} is not a usable name: lowercase letters, "
                         f"digits and hyphens, no dots and no path."}
    src = pathlib.Path(str(src)).expanduser()
    if not src.is_file():
        return {"error": f"no such file: {src}"}
    if src.suffix.lower() not in _READABLE:
        return {"error": f"{src.suffix or src.name} is not a photograph. "
                         f"Readable here: {', '.join(_READABLE)}."}
    body = " ".join(str(description).split())
    if len(body.split()) < 8:
        return {"error": "the description is what the run reads as FACT about "
                         "the viewpoint, and nothing checks it. Say where the "
                         "camera is -- above or below, which quarter -- and "
                         "what the frame shows."}

    ref_dir = pathlib.Path(ref_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)
    # FOUND BY STEM, NOT BY NAME. The suffix is not known until the image has
    # been normalised -- a HEIC lands as a `.jpg` -- so `nose-on.png` already
    # being there is what makes this slug taken, whatever this frame will
    # become.
    already = [p for p in _paths_in(ref_dir) if p.stem == slug]
    if already and not force:
        # NOT OVERWRITABLE BY DEFAULT, for `cli/mask.py`'s reason one step
        # earlier: a mask is an input to a fit whose output may already be
        # committed and frozen, and nothing downstream notices when the image
        # under it changes. The caller says how to override, because one has a
        # flag and the other does not.
        return {"error": f"{slug} is already {already[0].name}, and replacing "
                         f"a reference photograph is not automatic: a mask cut "
                         f"from the old frame is an input to fits that may "
                         f"already be committed.",
                "taken": already[0].name}

    try:
        dest, how = _normalise_image(src, ref_dir, slug)
    except Exception as exc:                        # noqa: BLE001 -- reported
        extra = ""
        if src.suffix.lower() in (".heic", ".heif"):
            extra = (" HEIC needs `pillow-heif`, which is in the `nb` "
                     "dependency group -- `uv sync --group nb`.")
        return {"error": f"{src.name} could not be read: "
                         f"{type(exc).__name__}: {exc}.{extra}"}

    # ONLY NOW is the old frame removed, and only if it is a different file:
    # `nose-on.heic` arriving over `nose-on.png` must not leave two images
    # sharing one `.txt`, which `reference_paths` would list as two viewpoints.
    replaced = None
    for p in already:
        if p != dest:
            p.unlink()
            replaced = p.name

    # FIRST WORD `photo`, which is what `reference_kind` reads to tell a
    # photograph from a plan or a scan.
    (ref_dir / f"{slug}.txt").write_text(f"photo {body}\n")

    # A MASK CUT FROM THE FRAME THIS REPLACED is now a mask of a different
    # photograph. Not deleted here: `cli/mask.py` is the only place that knows
    # whether a committed entry's numbers came out of it, and it refuses to
    # overwrite one for that reason. Named, so the caller can say so.
    #
    # THE TEST IS `already`, NOT `replaced`. A frame arriving under the same
    # suffix as the one it replaces leaves `replaced` empty -- nothing was
    # unlinked, the bytes were simply overwritten -- and that is the case most
    # likely to go unnoticed, because nothing about the directory listing
    # changed. What makes a mask stale is that the image under it moved, which
    # is what `already` says.
    stale = mask_for(dest)
    return {"installed": slug, "image": dest.name, "how": how,
            "replaced": replaced,
            "stale_mask": stale.name if stale is not None and already else None}


def _normalise_image(src, ref_dir, slug):
    """
    Copy or convert one frame into `_reference/`. -> (path, what happened).

    DOES THE LEAST IT CAN. A frame already in a format the notebook reads,
    already upright and already within `MAX_EDGE` is copied BYTE FOR BYTE.
    Re-encoding it would be a lossy pass over the one thing in `_reference/`
    that every reconstruction is judged against, and
    `references/coordinator/reference-photographs.md` is explicit that a
    vendor's own cut-out beats anything a model infers -- so what arrived is
    what is kept, wherever that is possible.

    Three things make it impossible, and the middle one is why this function
    exists at all:

    - A FORMAT NOTHING READS. A phone writes HEIC. `_SUFFIXES` does not list
      it and PIL cannot open it without `pillow-heif`.
    - AN EXIF ROTATION. A frame shot in portrait is stored landscape with a
      tag saying so. PIL's own array view, numpy and the segmentation model
      all ignore that tag -- so the mask is cut from a sideways aeroplane with
      a perfectly clean boundary, and every pose fitted against it is ninety
      degrees out with no number to catch it. This is the hand-in-the-frame
      failure in another costume.
    - A 12 MP FRAME, which is `MAX_EDGE`'s business.
    """
    from PIL import Image, ImageOps
    try:
        import pillow_heif
    except ImportError:
        pass
    else:
        pillow_heif.register_heif_opener()

    suffix = src.suffix.lower()
    with Image.open(src) as img:
        turned = img.getexif().get(_ORIENTATION, 1) not in (0, 1)
        wide = max(img.size) > MAX_EDGE
        # ALPHA IS GROUND TRUTH where it exists -- a vendor's cut-out scored
        # IoU 0.82 against the model's own attempt at the same frame, taking
        # in 21.6% extra area -- so a frame carrying one is never flattened.
        alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info

        if suffix in _SUFFIXES and not turned and not wide:
            dest = ref_dir / f"{slug}{suffix}"
            if dest.resolve() != src.resolve():
                shutil.copy(src, dest)
            return dest, f"copied unchanged, {img.size[0]}x{img.size[1]}"

        was = img.size
        out = ImageOps.exif_transpose(img)
        if max(out.size) > MAX_EDGE:
            out.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        if alpha:
            dest = ref_dir / f"{slug}.png"
            out.convert("RGBA").save(dest, "PNG", optimize=True)
        else:
            # 95 and no chroma subsampling: this is the input to a silhouette
            # fit, and the boundary is the whole signal.
            dest = ref_dir / f"{slug}.jpg"
            out.convert("RGB").save(dest, "JPEG", quality=95, subsampling=0,
                                    optimize=True)
        said = [f"{suffix} -> {dest.suffix}"]
        if turned:
            said.append("rotated per EXIF")
        if out.size != was:
            said.append(f"{was[0]}x{was[1]} -> {out.size[0]}x{out.size[1]}")
        return dest, ", ".join(said)


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


def _candidates(notebook, chapter=None, stem=""):
    """
    Every picture a run may look at, newest-relevant first. -> [(tag, path)]

    THE SEARCH ORDER IS THE ANSWER TO "which one did you mean". A run asks
    for a picture far more often than it asks for a particular directory,
    and the four places a picture can live are not equally likely at any
    moment:

      probe/      what this run just drew -- the common case by a long way
      reference/  photographs of the real aircraft
      figure/     what the entry rendered, from the freeze

    Deterministic and documented, so a bare `read_image()` is predictable
    rather than lucky, and every result says which source it came from.
    """
    out = []
    for r in (notebook.run, notebook.run / "_scratch",
              notebook.root / "_scratch"):
        if r.is_dir():
            out += [("probe", p) for p in sorted(r.iterdir())
                    if p.suffix.lower() in _SUFFIXES]
    out += [("reference", p) for p in reference_paths(notebook)]
    # FREEZE LAST, and only this chapter's unless told otherwise. A run reads
    # its OWN rendered figure; measured across every transcript on disk, the
    # `chapter` argument of the old `read_figure` was the run's own chapter
    # in 21 of 21 calls and another chapter's in none.
    if chapter:
        out += [("figure", p) for p in figure_paths(notebook, chapter, stem)]
    return out


def _matches(name, tag, path):
    """Does `path` answer to `name`? Exact, then stem, then prefix."""
    if path.name == name or path.stem == name:
        return True
    # PREFIX, because Quarto's filenames are not the ones anybody guesses.
    # A cell labelled `fig-belly` renders to `fig-belly-output-1.png`, and
    # MEASURED across every transcript, 4 of 21 `read_figure` calls asked
    # for `fig-belly-1.png` and got an error -- the same wrong guess every
    # time, by three different runs on three aircraft. The label is what the
    # entry's source says; the suffix is Quarto's business.
    return path.name.startswith(name) or path.stem.startswith(name)


def read_image(notebook, name="", chapter=None, stem=""):
    """
    Any picture this run may look at, as bytes for an inline part.

    ONE TOOL, THREE PLACES. This replaces `read_probe_figure`,
    `read_reference_image` and `read_figure`, which were three declarations
    of the same function -- resolve a name to bytes, list the candidates on a
    miss -- differing only in which directory they searched. Measured across
    25 runs: zero calls picked the wrong one of the three, so they were not
    confusing, merely three. What they cost was a declaration each in every
    turn of every run, and two defects that live in the seams:

      * `read_figure` REQUIRED a chapter, and every one of its 21 recorded
        calls passed the run's own. A required argument whose only correct
        value the session already holds is an invitation to pass a wrong one
        -- and a wrong chapter here answers about a different aircraft.
      * it matched filenames exactly, and 4 of those 21 calls guessed
        `fig-belly-1.png` for what Quarto writes as `fig-belly-output-1.png`.

    Both are gone: the chapter defaults to this run's, and a name matches by
    prefix, so the label from the entry's own source is enough.

    NO ARGUMENT AT ALL returns the first picture in search order, which is
    whatever this run most recently drew. That is almost always what is
    wanted straight after a probe that saved one.
    """
    cands = _candidates(notebook, chapter, stem)
    if not cands:
        return {"error":
                f"no pictures anywhere for {notebook.root.name}: nothing "
                f"saved from a probe, no _reference/ images, nothing "
                f"rendered. Save one from a probe -- "
                f"`fig.savefig(\"check.png\")` lands in the run directory."}
    hits = [(t, p) for t, p in cands if not name or _matches(name, t, p)]
    if not hits:
        listing = "\n".join(f"  {t:<10} {p.name}" for t, p in cands)
        return {"error": f"no picture matching {name!r}. Available:\n{listing}"}
    tag, p = hits[0]
    return {"_image": p.read_bytes(),
            "mime_type": _MIME.get(p.suffix.lower(), "image/png"),
            "name": f"{tag}/{p.name}"}

"""
masks -- cut a reference photograph's subject mask with a segmentation model.

WHAT CANNOT BE AUTOMATED IS LOOKING AT THE RESULT. `figures.py` used to say
segmentation itself could not be, and that was true of the per-pixel colour
rules this replaces: they have no notion of OBJECT, so they fail wherever tone
alone does not separate subject from ground. Measured twice. On the Little
Piggy a brightness-and-greenness rule put the belly, the chin, both legs and
both wheels OUTSIDE the mask, because a shaded white facet in sunlight is a
warm cream and foliage scores the same on both axes. On the Mustang the same
class of rule dropped the red rudder and spinner, missed the propeller, and
took in part of the hand holding the aircraft.

A model carries the object prior those rules lack, and it was chosen by
measurement over all 13 masks then committed:

    model                   IoU vs 4 verified   IoU vs all 13   own noise
    birefnet-general-lite               0.918           0.950        1.5%
    isnet-general-use                   0.920           0.908        2.3%
    u2net                               0.580           0.807        2.3%
    the hand-cut masks                      -               -        3.0%

On `little-piggy/studio`, whose mask is a vendor's own alpha channel and so is
exactly right, it scores 0.992 from a 480 px JPEG. Its boundary is cleaner than
the hand cuts on the one test that needs no ground truth.

NO ESCAPE HATCH, deliberately. There is no predicate, no bound, no crop. A
salient-object model cannot know that the hand holding the aeroplane is not
part of it, and no parameter fixes that -- on the Mustang every model kept the
hand. When the model takes in something that is not the aircraft, use a
different photograph; a mask is also just a PNG, so paint it out if the
viewpoint is worth keeping. Both beat carrying a rule language for the case.

Coordinator-only. Nothing here is registered in `nb/tools/__init__.py`: a run
must never cut the mask it is then measured against.
"""

from . import figures

#: The session, PINNED. rembg's own default is `bria-rmbg`, whose weights need
#: a paid agreement for commercial use -- rembg is MIT but says plainly that
#: "model weights carry their own licenses". BiRefNet is MIT, code and weights.
MODEL = "birefnet-general-lite"

#: Overlays live under `_scratch/`, which is gitignored, and NOT in
#: `_reference/`: an `x.overlay.png` there would be picked up by
#: `reference_paths` as an unlabelled asset and offered to the run.
OVERLAY_DIR = "masks"

#: The boundary colour over the photograph. Red because no airframe in any
#: reference photograph so far is red, and the edge has to read against both
#: foliage and a white studio ground.
EDGE = (255, 0, 0)

#: The interior tint, and how hard. Green at 55% survives both a white studio
#: ground and a treeline, and leaves enough of the photograph showing that an
#: included patch of BACKGROUND is still recognisable as background.
FILL = (0, 255, 0)
FILL_ALPHA = 0.55


def _np():
    """numpy, PIL.Image and scipy.ndimage, or a SystemExit naming the fix."""
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except ImportError as exc:                      # pragma: no cover
        raise SystemExit(
            f"nb.tools.masks needs numpy, pillow and scipy ({exc}). "
            f"`uv sync --group nb`.")
    return np, Image, ndimage


def _paths(notebook, name):
    """(image, mask) for one reference name. The mask need not exist yet."""
    root = notebook.root / figures.REFERENCE_DIR
    img = next((p for p in sorted(root.glob(f"{name}.*"))
                if p.suffix.lower() in figures._SUFFIXES
                and not p.name.endswith(figures.MASK_SUFFIX)), None)
    if img is None:
        have = ", ".join(sorted(p.stem for p in root.glob("*")
                                if p.suffix.lower() in figures._SUFFIXES
                                and not p.name.endswith(figures.MASK_SUFFIX)))
        raise SystemExit(f"no photograph {name!r} in {root}. "
                         f"Present: {have or 'none'}.")
    return img, root / f"{name}{figures.MASK_SUFFIX}"


#: One session per model, for the life of the process. `new_session` loads 214
#: MB from disk and builds an onnxruntime graph, which is about 40 s -- paid
#: once per `nb mask`, not once per photograph. Four frames went from four
#: loads to one.
_SESSIONS = {}


def _session(model):
    """The rembg session for `model`, built once. -> session."""
    if model not in _SESSIONS:
        try:
            from rembg import new_session
        except ImportError as exc:                  # pragma: no cover
            raise SystemExit(
                f"nb.tools.masks needs rembg to cut a mask ({exc}). "
                f"`uv sync --group nb`. The weights -- 214 MB -- download to "
                f"~/.rembg on first use.")
        _SESSIONS[model] = new_session(model)
    return _SESSIONS[model]


def cut(notebook, name, model=MODEL):
    """The mask for one reference photograph. -> (mask, report).

    Writes `<name>.mask.png` beside the photograph as clean 0/255 L-mode, so
    the `> 127` and `> 128` readers downstream cannot disagree, and the
    overlay, always.

    LOOK AT THE OVERLAY. It is the one step that is still yours: the model
    reports nothing when it is wrong, and a mask read as a white blob on black
    looks plausible while missing half an aircraft.

    Largest component then fill, after the model: the pose fit wants ONE solid
    silhouette, and a detached speck of background would be extra outline for
    the chamfer to chase.
    """
    np, Image, ndimage = _np()

    img_path, mask_path = _paths(notebook, name)
    src = Image.open(img_path)

    # A VENDOR'S OWN ALPHA IS GROUND TRUTH, and beats anything a model infers
    # from the flattened RGB. Retailers cut their product shots, so a store
    # PNG often arrives already masked -- and this was throwing that away with
    # `.convert("RGB")` and then guessing at what it had just discarded.
    #
    # Measured on the FT A-10 Warthog `port-front-above` store photograph,
    # which is 84.5% transparent: against the alpha the model's mask scored
    # IoU 0.82, taking in 21.6% EXTRA area -- most of it the enclosed gap
    # between the port tail fin, the tailplane and the nacelle, which is
    # exactly the region that defines a twin-boom tail. The silhouette it
    # produced was of a different aeroplane.
    #
    # `> 128` rather than `> 0`: a soft edge is a few pixels of partial alpha
    # and the half-covered ones belong outside, which is where the vendor's
    # compositor put them.
    alpha = None
    if "A" in src.mode:
        a = np.asarray(src.convert("RGBA").split()[-1])
        if (a < 250).mean() > 0.02:        # a real cut-out, not a stray channel
            alpha = a > 128
    if alpha is not None and alpha.any():
        m, how = alpha, "the image's own alpha channel"
    else:
        from rembg import remove
        sess = _session(model)
        raw = remove(src.convert("RGB"), session=sess, only_mask=True,
                     post_process_mask=True)
        m = np.asarray(raw.convert("L")) > 127
        how = model
    if m.any():
        lab, n = ndimage.label(m)
        if n > 1:
            sizes = ndimage.sum(m, lab, range(1, n + 1))
            m = lab == (1 + int(np.argmax(sizes)))
        m = ndimage.binary_fill_holes(m)
    _write(Image, np, m, mask_path)
    shot = overlay(notebook, name)
    return m, (f"{name}: {m.sum() / m.size:.4f} of frame, "
               f"{_bbox(m) or 'EMPTY'}  [{how}]"
               f"\n  mask    {mask_path}"
               f"\n  overlay {shot}   <- look at this")


def _write(Image, np, mask, path):
    """The mask as a clean 0/255 L-mode PNG.

    0/255 rather than whatever the model left, because the two readers
    downstream disagree by one level -- `duplicate_photos` binarises at > 128
    and `_reference_image` at > 127. On a clean mask neither can be wrong.
    """
    out = np.where(mask, 255, 0).astype(np.uint8)
    Image.fromarray(out, mode="L").save(path)


def _bbox(mask):
    """(y0, y1, x0, x1) of the set pixels, or None when there are none."""
    np, _, _ = _np()
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def overlay(notebook, name):
    """The mask drawn over its photograph, INTERIOR TINTED. -> path written.

    TINT THE INSIDE, do not just trace the edge. A boundary drawn over a busy
    photograph reads as correct wherever it happens to follow a real edge --
    and the crease between a lit facet and a shaded one IS a real edge, so a
    mask that has dropped the whole shaded underside still draws a clean,
    convincing red line. Three Little Piggy masks passed that inspection and
    were missing the belly, the chin, the legs and both wheels. Filled, the
    hole is unmissable in a glance.

    The edge is drawn too, because the fill alone hides a one-pixel halo of
    background. Separate from `cut` so a mask edited by hand can still be
    checked.
    """
    np, Image, ndimage = _np()
    img_path, mask_path = _paths(notebook, name)
    if not mask_path.exists():
        raise SystemExit(f"no mask at {mask_path} to draw.")
    photo = np.asarray(Image.open(img_path).convert("RGB")).copy()
    mask = np.asarray(Image.open(mask_path).convert("L")) > 127
    if mask.shape != photo.shape[:2]:
        raise SystemExit(
            f"{name}: mask is {mask.shape[1]}x{mask.shape[0]} and the "
            f"photograph is {photo.shape[1]}x{photo.shape[0]}. The fit takes "
            f"its frame from the mask, so a mismatch puts the pose in the "
            f"wrong coordinates. Re-cut it from this photograph.")
    inside = photo[mask] * (1 - FILL_ALPHA) + np.array(FILL) * FILL_ALPHA
    photo[mask] = inside.astype(photo.dtype)
    photo[mask ^ ndimage.binary_erosion(mask)] = EDGE
    out = notebook.scratch / OVERLAY_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.overlay.png"
    Image.fromarray(photo).save(path)
    return path


def stats(notebook, name):
    """What `nb reference` prints for one photograph. -> dict.

    `noise` is the share of the boundary that smoothing at 5 px -- below any
    real feature on these aircraft -- takes away. A clean silhouette loses
    almost none of its outline to that; a mask cut by a per-pixel rule on a
    low-contrast subject loses a seventh of it. Measured: the vendor's own
    alpha 0.6%, a hand-cut `nose-on` 14.4%, the model 1.5% on average across
    all 13 frames against 3.0% for the hand cuts. `roughness` is perimeter
    over sqrt(area), which also rises with genuine thinness -- a head-on wing
    is legitimately a long thin bar -- so read the two together.

    `matches` is the check nothing else in the system makes: `compare_to_photo`
    takes `H, W` from the MASK and then indexes the photograph with it, and
    `_fit_pose` seeds scale and translation from the mask bounding box -- so a
    mis-sized mask does not fail loudly, it returns a pose in the wrong
    coordinate frame with a residual beside it, looking like an answer.
    """
    np, Image, ndimage = _np()
    img_path, mask_path = _paths(notebook, name)
    with Image.open(img_path) as im:
        photo_size = im.size
    if not mask_path.exists():
        return {"photo_size": photo_size, "mask_size": None, "matches": False,
                "area_frac": 0.0, "bbox": None, "empty": True,
                "roughness": 0.0, "noise": 0.0}
    with Image.open(mask_path) as im:
        mask_size = im.size
        mask = np.asarray(im.convert("L")) > 127
    smooth = ndimage.binary_fill_holes(ndimage.binary_opening(
        ndimage.binary_closing(mask, np.ones((5, 5))), np.ones((3, 3))))
    p0 = float((mask ^ ndimage.binary_erosion(mask)).sum())
    p1 = float((smooth ^ ndimage.binary_erosion(smooth)).sum())
    return {"photo_size": photo_size, "mask_size": mask_size,
            "matches": photo_size == mask_size,
            "area_frac": float(mask.sum() / mask.size),
            "bbox": _bbox(mask), "empty": not mask.any(),
            "roughness": p0 / np.sqrt(max(mask.sum(), 1)),
            "noise": (p0 - p1) / p0 if p0 else 0.0}

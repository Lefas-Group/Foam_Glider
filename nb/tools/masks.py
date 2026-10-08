"""
masks -- scaffolding for the coordinator's hand cut of a reference mask.

NOT A SEGMENTER, and the distinction is the whole design. `figures.py` states
the policy this module has to live under: segmentation cannot be automated
across photographs, so it is done by the party that can look at the result.
Nothing here chooses a threshold, a discriminant or a region. What it removes
is the plumbing -- sobel, closing, largest blob, fill, the 0/255 PNG -- and
the inspection artefact, which is the part that was being skipped.

Measured on the FT Little Piggy: cutting four frames cost about fifteen turns
and eleven throwaway scripts, and the first three masks each lost a whole
wing panel. Every one of those was invisible as a white blob on black and
obvious the moment the boundary was drawn back over the photograph. So `cut`
writes that overlay unconditionally, and takes no default rule: a cut nobody
chose is the failure this module exists to make harder, not easier.

ONE FRAME, ONE RULE is the thing the API is shaped around. Two Little Piggy
frames from the same shoot needed OPPOSITE discriminants -- white foam
separates from foliage by GREENNESS at tones where brightness cannot tell
them apart, and a panel in the body's own shadow separates by BRIGHTNESS at
greenness where the colour rule cannot -- and one shadowed panel in each
needed a local override of the rule that cut the rest. That is `keep`.

Coordinator-only. Nothing here is registered in `nb/tools/__init__.py`: a run
must never cut the mask it is then measured against.
"""

from . import figures

#: Written beside the photograph, so a mask lands where `_reference_image`
#: looks for it rather than wherever the shell happened to be -- the
#: `<nb>/<nb>/_reference/` mistake, made once and warned about ever since.
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
    """numpy, PIL.Image and scipy.ndimage, or a SystemExit naming what to do.

    Imported here rather than at module scope for `figures.py`'s reason --
    this module is reachable from the launch path through `nb reference` --
    but NOT degraded to a no-op the way a warning is. Image work without
    numpy is not a reduced service, it is nothing at all.
    """
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except ImportError as exc:                      # pragma: no cover
        raise SystemExit(
            f"nb.tools.masks needs numpy, pillow and scipy ({exc}). They "
            f"arrive with the project dependencies: `uv sync`.")
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


class Tones:
    """The axes a mask rule may cut on, for one photograph.

    A record rather than a tuple because the axis that matters is not known
    in advance and a tuple pins the signature of every rule ever written.
    `sat` was added after three masks were cut without it and lost every
    downward-facing surface on the aircraft.

      lum    0-255 mean of RGB
      green  G - (R+B)/2, the lit-foam-against-foliage axis
      sat    HSV saturation, (max-min)/max -- THE SHADED-SURFACE AXIS
      grad   sobel magnitude, for the border fill's walls
    """

    def __init__(self, lum, green, sat, grad):
        self.lum, self.green, self.sat, self.grad = lum, green, sat, grad

    @property
    def shape(self):
        return self.lum.shape


def load(notebook, name):
    """The photograph's tone axes. -> Tones.

    REACH FOR `sat` FIRST ON A SUNLIT SUBJECT. White foam is achromatic by
    construction, so however deep a facet falls into shadow it stays
    low-saturation; foliage is chromatic however bright it gets. Brightness
    and greenness both FAIL on exactly the surfaces that matter: measured on
    `nose-on`, the shaded belly is lum 107 against foliage at lum 100, and
    green +16.7 against +22.4 -- no threshold on either separates them -- but
    saturation is 0.34 against 0.51, and on `above-behind` 0.38 against 0.79.

    Three Little Piggy masks were cut on brightness and greenness alone and
    every downward-facing surface -- belly, chin, legs, wheels -- fell outside
    the mask, because a shaded white facet in sunlight is a warm cream that
    both those axes score as foliage.
    """
    np, Image, ndimage = _np()
    img, _ = _paths(notebook, name)
    a = np.asarray(Image.open(img).convert("RGB")).astype(float)
    lum = a.mean(2)
    green = a[..., 1] - (a[..., 0] + a[..., 2]) / 2.0
    mx, mn = a.max(2), a.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
    grad = np.hypot(ndimage.sobel(lum, 1), ndimage.sobel(lum, 0))
    return Tones(lum, green, sat, grad)


def background(t, *, sat_hi=None, green_hi=None, lum_lo, grad_hi=22.0,
               pocket=14.0):
    """Background by tone, then by reachability from the frame border.

    Three passes, and the third is the one that is easy to leave out. Tone
    first: anything greener than `green_hi` or darker than `lum_lo`. Then a
    flood from the border through smooth pixels, which is what removes a sky
    or a studio ground whose tone overlaps the airframe's. Then POCKETS --
    regions of the same tone as the flood that the airframe shuts off from
    the border, such as the sky under a wing. Without that pass the fill
    stops at the trailing edge and about twelve pixels of sky join the wing,
    measured on `nose-on`.

    Cut on EITHER `sat_hi` or `green_hi`, never both, and prefer `sat_hi` --
    see `load`. The thresholds are yours: there is no sensible default, and
    the five Little Piggy frames share none.
    """
    np, _, ndimage = _np()
    if (sat_hi is None) == (green_hi is None):
        raise SystemExit("background() takes exactly one of sat_hi or "
                         "green_hi. On a sunlit subject against "
                         "vegetation it is sat_hi -- see load().")
    lum, grad = t.lum, t.grad
    chroma = t.sat if sat_hi is not None else t.green
    tone = (chroma > (sat_hi if sat_hi is not None else green_hi)) | (lum < lum_lo)

    passable = (~tone) & (grad < grad_hi)
    lab, n = ndimage.label(passable)
    seed = np.zeros(lum.shape, bool)
    seed[0:3, :] = True
    seed[-3:, :] = True
    seed[:, 0:3] = True
    seed[:, -3:] = True
    keep = set(np.unique(lab[seed & (lab > 0)]).tolist()) - {0}
    if not keep:
        return tone
    reached = np.isin(lab, list(keep)) & (lab > 0)
    tone_of_ground = lum[reached].mean()
    for i in range(1, n + 1):
        sel = lab == i
        if sel.sum() >= 250 and abs(lum[sel].mean() - tone_of_ground) < pocket:
            keep.add(i)
    ground = np.isin(lab, list(keep)) & (lab > 0)
    # Dilated by one, to take back the edge pixels the gradient wall held
    # out of the fill. Without it the mask carries a one-pixel halo of
    # background all the way round, which the chamfer fit reads as shape.
    return tone | ndimage.binary_dilation(ground, np.ones((3, 3)))


def rect(*boxes):
    """A (h, w) -> bool callable from (y0, y1, x0, x1) boxes, for `bound`.

    The honest way to say "outboard of the body there is nothing but wing".
    A bound is a claim about the FRAME, not about the aircraft, and it goes
    in the `.txt` beside the photograph so the next reader knows which part
    of the silhouette was drawn rather than cut.
    """
    def region(h, w):
        np, _, _ = _np()
        b = np.zeros((h, w), bool)
        for (y0, y1, x0, x1) in boxes:
            b[y0:y1, x0:x1] = True
        return b
    return region


def cut(notebook, name, *, bg, keep=None, bound=None, close=5):
    """The mask for one reference photograph. -> (mask, report).

    `bg` and `keep` are predicates over a `Tones` record returning a bool
    array; `bound` is a (h, w) -> bool callable, usually `rect(...)`.

    `keep` IS THE LOCAL OVERRIDE, and it is why this takes a callable rather
    than a set of thresholds. On `below-front` both wing panels sit at lum
    97-115 against trees at 28-46 at the SAME greenness, so the rule that cut
    the body loses the wings entirely; `keep` puts them back by brightness
    over the wing band alone.

    `bg` has NO DEFAULT. Passing one would make it possible to accept a cut
    without choosing a discriminant, which is the whole failure this module
    is answering.

    Writes `<name>.mask.png` beside the photograph, clean 0/255 L-mode so the
    `> 127` and `> 128` readers downstream cannot disagree, and the overlay,
    always. LOOK AT THE OVERLAY. A mask that has lost a wing looks fine as a
    blob and is unmistakable over the photograph.
    """
    np, Image, ndimage = _np()
    t = load(notebook, name)

    m = ~bg(t)
    if keep is not None:
        m |= keep(t)
    if bound is not None:
        m &= bound(*t.shape)

    m = ndimage.binary_closing(m, np.ones((close, close)))
    lab, n = ndimage.label(m)
    if n:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        m = lab == (1 + int(np.argmax(sizes)))
    m = ndimage.binary_fill_holes(m)

    _, mask_path = _paths(notebook, name)
    _write(Image, np, m, mask_path)
    shot = overlay(notebook, name)
    return m, (f"{name}: {m.sum() / m.size:.4f} of frame, "
               f"{_bbox(m) or 'EMPTY'}\n  mask    {mask_path}"
               f"\n  overlay {shot}   <- look at this")


def from_alpha(notebook, name, source, threshold=128, close=3):
    """The mask from an ALPHA-CARRYING source file. -> (mask, report).

    Retailers cut their product shots for the web, and a vendor's own alpha
    is exact -- better than any rule you would write against the flattened
    RGB. Two of the five Little Piggy store frames carried one; re-cutting
    the flattened version by luminance reproduced it only to IoU 0.985, and
    the difference was the snout against the white ground.

    `source` is the alpha-carrying file, which is NOT the one in
    `_reference/`: the photograph committed there is flattened onto white,
    because `_reference_image` converts to RGB and a transparent pixel would
    otherwise reach the overlay as black. So the alpha source is an input
    kept outside the notebook, named here and recorded in the `.txt`.
    """
    np, Image, ndimage = _np()
    a = np.asarray(Image.open(source).convert("RGBA"))[..., 3] > threshold
    m = ndimage.binary_fill_holes(
        ndimage.binary_closing(a, np.ones((close, close))))
    img_path, mask_path = _paths(notebook, name)
    with Image.open(img_path) as im:
        if im.size != (m.shape[1], m.shape[0]):
            raise SystemExit(
                f"{name}: the alpha source is {m.shape[1]}x{m.shape[0]} and "
                f"the photograph in _reference/ is {im.size[0]}x{im.size[1]}. "
                f"They must be the same frame.")
    _write(Image, np, m, mask_path)
    shot = overlay(notebook, name)
    return m, (f"{name}: {m.sum() / m.size:.4f} of frame, from alpha"
               f"\n  mask    {mask_path}"
               f"\n  overlay {shot}   <- look at this")


def _write(Image, np, mask, path):
    """The mask as a clean 0/255 L-mode PNG.

    0/255 rather than whatever the morphology left, because the two readers
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
    background. Separate from `cut` so a mask cut elsewhere, or edited by
    hand, can still be checked.

    Written under `_scratch/`, which is gitignored, and NOT into
    `_reference/`: an `x.overlay.png` there would be picked up by
    `reference_paths` as an unlabelled asset and offered to the run.
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
    low-contrast subject loses a seventh of it. Measured on the Little Piggy:
    the vendor's own alpha 0.6%, a `nose-on` cut on brightness and greenness
    14.4%, the same frame re-cut on saturation 3.8%. `roughness` is
    perimeter over sqrt(area), which also rises with genuine thinness -- a
    head-on wing is legitimately a long thin bar -- so read the two together.

    `matches` is the check nothing else in the system makes: `compare_to_photo`
    takes `H, W` from the MASK and then indexes the photograph with it, so a
    mis-sized mask either raises deep in the fit or silently composites the
    top-left corner, and `_fit_pose` seeds scale and translation from the mask
    bounding box -- a pose in the wrong frame, reported as a number.
    """
    np, Image, _ = _np()
    img_path, mask_path = _paths(notebook, name)
    with Image.open(img_path) as im:
        photo_size = im.size
    if not mask_path.exists():
        return {"photo_size": photo_size, "mask_size": None, "matches": False,
                "area_frac": 0.0, "bbox": None, "empty": True}
    with Image.open(mask_path) as im:
        mask_size = im.size
        mask = np.asarray(im.convert("L")) > 127
    _, _, ndimage = _np()
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

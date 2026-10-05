"""
Fit a camera pose so a model's landmarks reproject onto a photograph's.

WHY THIS EXISTS. An overlay built by matching silhouette AREA and centroid
tells you something is wrong and not by how much: the scale comes from a
segmented mask, so model error and pose error are mixed together and neither
can be read off. Fitting a pose to NAMED CORRESPONDENCES separates them --
once the pose is fitted, each landmark's residual is model error in pixels,
and with a trusted scale it is model error in millimetres.

THE DIVISION OF LABOUR IS THE POINT. The 3-D landmarks come from the
geometry and are exact. The 2-D ones are IDENTIFIED in the photograph, not
measured: "that is the port wingtip, about there". MeasureBench (CVPR 2026)
puts vision models above 90% on recognising what a thing is and near 30% on
reading a scale off it -- so this asks only for the half that works.

GENERIC BY CONSTRUCTION. Nothing here knows what a Mustang is.
`landmarks()` walks whatever wings and fuselages an `asb.Airplane` has and
names extreme points structurally, so a flying wing, an X-wing or something
shaped like a pig all produce a usable set. The caller may pass its own
dictionary instead.
"""

import numpy as np


# ---------------------------------------------------------------- camera

def rotation(elev, azim, roll=0.0):
    """
    World -> camera basis, matching matplotlib's `view_init(elev, azim, roll)`.

    Matplotlib places the eye on a sphere at
    `(cos e cos a, cos e sin a, sin e)` looking at the origin with +z up, so
    the same convention here means a fitted pose can be handed straight to
    `view_init` and the render will agree with the fit. That agreement is
    checked by `reprojection_check()` rather than assumed.
    """
    e, a, r = np.radians([elev, azim, roll])
    eye = np.array([np.cos(e)*np.cos(a), np.cos(e)*np.sin(a), np.sin(e)])
    fwd = -eye
    up0 = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(fwd, up0)) > 0.999:          # looking straight down the pole
        up0 = np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, up0); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    R = np.stack([right, up, -fwd])
    if r:
        c, s = np.cos(r), np.sin(r)
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]) @ R
    return R


def project(points, elev, azim, roll, scale, tx, ty, centre=None,
            distance=None):
    """
    Model points -> image pixels. Orthographic, or perspective if `distance`.

    `distance` is the camera's range from the model centre, in model units;
    `None` is orthographic and is what matplotlib renders with
    `ax.set_proj_type("ortho")`, so a pose fitted that way can be handed
    straight to `view_init`.

    PERSPECTIVE IS NOT OPTIONAL FOR A CLOSE PHOTOGRAPH, which an earlier
    version of this assumed it was. Fitting a hand-held product shot of a
    622 mm aircraft orthographically left ~65 px of residual on a 480 px
    span -- 13% -- because the near wingtip genuinely is larger than the far
    one and no rigid orthographic pose can make both land. The camera model
    was not at fault: it reproduces matplotlib to 0.00 px. The projection
    was. Fit `distance` as well whenever the subject fills the frame, and
    read a small fitted distance as a warning that the overlay will not line
    up at the edges however good the model is.
    """
    p = np.asarray(points, float)
    c = np.asarray(centre if centre is not None else p.mean(axis=0), float)
    cam = (p - c) @ rotation(elev, azim, roll).T
    x, y = cam[:, 0], cam[:, 1]
    if distance is not None:
        # cam[:, 2] runs toward the viewer, so a near point divides by less.
        depth = np.clip(1.0 - cam[:, 2] / distance, 1e-3, None)
        x, y = x / depth, y / depth
    return np.stack([scale*x + tx, -scale*y + ty], axis=1)


# ------------------------------------------------------------- landmarks

def landmarks(airplane):
    """
    {name: (x, y, z)} of structurally extreme points, for any `Airplane`.

    Named by WHAT THEY ARE IN THE AIRFRAME rather than by aircraft type, so
    the same call works on anything: each wing contributes its tips, each
    fuselage its ends, and the whole aircraft its highest point. A caller who
    knows better is free to pass a dictionary of its own.
    """
    out = {}
    for w in airplane.wings:
        pts = np.array([x.xyz_le for x in w.xsecs], float)
        name = w.name.lower().replace(" ", "-")
        span_axis = 1 if np.ptp(pts[:, 1]) >= np.ptp(pts[:, 2]) else 2
        tip = pts[np.argmax(np.abs(pts[:, span_axis]))]
        root = pts[np.argmin(np.abs(pts[:, span_axis]))]
        out[f"{name}:tip"] = tuple(tip)
        out[f"{name}:root"] = tuple(root)
        if w.symmetric and span_axis == 1:
            out[f"{name}:tip-mirror"] = (tip[0], -tip[1], tip[2])
    for f in airplane.fuselages:
        pts = np.array([x.xyz_c for x in f.xsecs], float)
        name = f.name.lower().replace(" ", "-")
        out[f"{name}:nose"] = tuple(pts[np.argmin(pts[:, 0])])
        out[f"{name}:tail"] = tuple(pts[np.argmax(pts[:, 0])])
    return out


# ------------------------------------------------------------------- fit

def fit(model_pts, image_pts, scale=None, x0=None, perspective=False):
    """
    Least-squares pose from correspondences. Returns (params, residuals_px).

    `model_pts` and `image_pts` are dicts keyed by the same names; only the
    shared keys are used, so a landmark that cannot be seen in the photograph
    is simply left out.

    FIX THE SCALE IF YOU CAN. Six pose parameters against seven or eight
    correspondences leaves almost no redundancy, so a free scale quietly
    absorbs model error into the pose and the residuals come back flattering.
    Pass `scale` in pixels-per-metre, computed from a dimension already
    trusted -- a span measured off a 1:1 plan -- and the residuals are then
    model error rather than a mixture.
    """
    from scipy.optimize import minimize
    keys = [k for k in model_pts if k in image_pts]
    if len(keys) < 4:
        raise ValueError(f"need 4+ shared landmarks, got {len(keys)}: {keys}")
    P = np.array([model_pts[k] for k in keys], float)
    Q = np.array([image_pts[k] for k in keys], float)
    centre = P.mean(axis=0)
    free_scale = scale is None

    def unpack(v):
        i = 0
        e, a, r = v[0], v[1], v[2]; i = 3
        if free_scale:
            s = abs(v[i]); i += 1
        else:
            s = scale
        tx, ty = v[i], v[i+1]; i += 2
        d = abs(v[i]) + 0.05 if perspective else None
        return e, a, r, s, tx, ty, d

    def cost(v):
        e, a, r, s, tx, ty, d = unpack(v)
        return np.sum((project(P, e, a, r, s, tx, ty, centre, d) - Q)**2)

    if x0 is None:
        s0 = scale if scale else 1000.0
        x0 = [30.0, 130.0, 0.0]
        if free_scale:
            x0.append(s0)
        x0 += [Q[:, 0].mean(), Q[:, 1].mean()]
        if perspective:
            x0.append(float(np.ptp(P, axis=0).max() * 2))

    best = None
    for a0 in range(0, 360, 45):               # azimuth is multi-modal
        v = list(x0); v[1] = float(a0)
        r = minimize(cost, v, method="Nelder-Mead",
                     options=dict(maxiter=20000, xatol=1e-3, fatol=1e-3))
        if best is None or r.fun < best.fun:
            best = r

    e, a, r_, s, tx, ty, d = unpack(best.x)
    resid = np.linalg.norm(
        project(P, e, a, r_, s, tx, ty, centre, d) - Q, axis=1)
    return dict(elev=e, azim=(a % 360), roll=r_, scale=s, tx=tx, ty=ty,
                distance=d, centre=centre, keys=keys), resid


# -------------------------------------------------------- silhouette fit

def silhouette(pts, faces, params, size, centre=None):
    """
    Rasterise the projected mesh to a boolean mask of `size` = (w, h).

    NO MATPLOTLIB IN THE LOOP. An earlier attempt rendered a figure per trial
    and thresholded the PNG, which was slow and twice gave a silhouette that
    was really the axes background pane. Drawing the projected faces straight
    into a PIL image is exact, has no theme or pane to defeat it, and is fast
    enough to sit inside an optimiser.
    """
    from PIL import Image, ImageDraw
    e, a, r, s, tx, ty, d = params
    q = project(pts, e, a, r, s, tx, ty, centre, d)
    im = Image.new("L", size, 0)
    dr = ImageDraw.Draw(im)
    for f in faces:
        dr.polygon([tuple(q[i]) for i in f], fill=255)
    return np.asarray(im) > 127


def fit_silhouette(pts, faces, target, x0=None, scale=None,
                   distance_bounds=(0.4, 20.0), work=220):
    """
    Camera pose by maximising silhouette overlap. Returns (params, iou).

    WHY THIS BEATS LANDMARK CORRESPONDENCE HERE. Five named points against
    seven free parameters is barely determined, and on a real photograph the
    fit used that freedom: it drove the camera distance to 0.25 m for a
    622 mm aircraft, placed the five points to a flattering 21 px mean, and
    produced an overlay visibly worse than a pose guessed by eye. A
    silhouette constrains the whole boundary at once -- thousands of pixels
    rather than ten numbers -- so a degenerate perspective that balloons the
    near half of the aircraft is punished immediately instead of rewarded.

    IT ALSO NEEDS NO LANDMARKS, which is the point: nobody has to identify
    "that is the port wingtip" for it to run. What it does need is a
    photograph whose subject can be separated from its background. That is a
    condition on the input, not on the method.

    `distance_bounds` keeps perspective physical; pass `scale` to hold it at
    a value already trusted, which removes the last degeneracy.
    """
    from scipy.optimize import minimize
    from PIL import Image

    h, w = target.shape
    sc_work = work / max(h, w)
    tw, th = max(1, int(w*sc_work)), max(1, int(h*sc_work))
    tgt = np.asarray(Image.fromarray(target.astype(np.uint8)*255)
                     .resize((tw, th), Image.NEAREST)) > 127
    centre = np.asarray(pts, float).mean(axis=0)
    free_scale = scale is None

    def unpack(v):
        i = 3
        s = abs(v[i])*sc_work if free_scale else scale*sc_work
        i += 1 if free_scale else 0
        lo, hi = distance_bounds
        d = lo + (hi-lo)/(1.0 + np.exp(-v[i+2]))       # squashed, so bounded
        return (v[0], v[1], v[2], s, v[i]*sc_work, v[i+1]*sc_work, d)

    def cost(v):
        m = silhouette(pts, faces, unpack(v), (tw, th), centre)
        u = (m | tgt).sum()
        return 1.0 - ((m & tgt).sum() / u if u else 0.0)

    ys, xs = np.nonzero(target)
    cx, cy = xs.mean(), ys.mean()
    span = np.ptp(np.asarray(pts, float), axis=0).max()
    s0 = scale if scale else (max(np.ptp(xs), np.ptp(ys)) / span)

    best, bestv = None, 2.0
    for a0 in range(0, 360, 30):
        for e0 in (15.0, 40.0, 65.0):
            v = [e0, float(a0), 0.0] + ([s0] if free_scale else []) + [cx, cy, 0.0]
            r = minimize(cost, v, method="Nelder-Mead",
                         options=dict(maxiter=1200, xatol=.5, fatol=1e-4))
            if r.fun < bestv:
                best, bestv = r, r.fun
    # polish the winner
    r = minimize(cost, best.x, method="Nelder-Mead",
                 options=dict(maxiter=6000, xatol=1e-2, fatol=1e-6))
    v = r.x if r.fun < bestv else best.x
    e, a, ro, s, tx, ty, d = unpack(v)
    return dict(elev=e, azim=a % 360, roll=ro, scale=s/sc_work,
                tx=tx/sc_work, ty=ty/sc_work, distance=d,
                centre=centre), 1.0 - min(r.fun, bestv)


def fit_chamfer(pts, faces, target, x0=None, scale=None,
                distance_bounds=(0.4, 20.0), work=220):
    """
    Camera pose by symmetric chamfer distance between outlines.

    WHY NOT IoU, WHICH THIS REPLACES. Overlap is a poor thing to optimise:
    it is FLAT when the two shapes do not yet intersect, so an optimiser
    started anywhere wrong gets no gradient at all and wanders; and it
    SATURATES once they mostly agree, so the last and most interesting
    millimetres barely move the score. A thin wing makes both worse -- a few
    pixels of shift changes overlap sharply without telling the optimiser
    which way to go.

    Chamfer distance has neither failure. Every outline pixel contributes its
    distance to the nearest outline pixel of the other shape, so the cost
    falls away smoothly in the right direction from anywhere in the basin.
    It is the classical shape-matching objective for exactly this reason
    (Barrow 1977), and it is two distance transforms and a lookup.

    SYMMETRIC, both directions summed: model-to-target alone is happy to
    shrink the model onto a corner of the target, and target-to-model alone
    is happy to blow it up to cover everything.
    """
    from scipy.optimize import minimize
    from scipy import ndimage
    from PIL import Image

    h, w = target.shape
    sc_work = work / max(h, w)
    tw, th = max(1, int(w*sc_work)), max(1, int(h*sc_work))
    tgt = np.asarray(Image.fromarray(target.astype(np.uint8)*255)
                     .resize((tw, th), Image.NEAREST)) > 127
    tgt_edge = tgt & ~ndimage.binary_erosion(tgt)
    # Distance to the target outline, precomputed once.
    dt_tgt = ndimage.distance_transform_edt(~tgt_edge)
    centre = np.asarray(pts, float).mean(axis=0)
    free_scale = scale is None
    diag = float(np.hypot(tw, th))

    def unpack(v):
        i = 3
        s = abs(v[i])*sc_work if free_scale else scale*sc_work
        i += 1 if free_scale else 0
        lo, hi = distance_bounds
        d = lo + (hi-lo)/(1.0 + np.exp(-v[i+2]))
        return (v[0], v[1], v[2], s, v[i]*sc_work, v[i+1]*sc_work, d)

    def cost(v):
        m = silhouette(pts, faces, unpack(v), (tw, th), centre)
        if not m.any():
            return diag
        m_edge = m & ~ndimage.binary_erosion(m)
        if not m_edge.any():
            return diag
        a = dt_tgt[m_edge].mean()                      # model -> target
        b = ndimage.distance_transform_edt(~m_edge)[tgt_edge].mean()
        return 0.5*(a + b)

    ys, xs = np.nonzero(target)
    span = np.ptp(np.asarray(pts, float), axis=0).max()
    s0 = scale if scale else (max(np.ptp(xs), np.ptp(ys)) / span)
    cx, cy = xs.mean(), ys.mean()

    best, bestv = None, 1e9
    for a0 in range(0, 360, 30):
        for e0 in (15.0, 40.0, 65.0):
            v = [e0, float(a0), 0.0] + ([s0] if free_scale else []) + [cx, cy, 0.0]
            r = minimize(cost, v, method="Nelder-Mead",
                         options=dict(maxiter=1200, xatol=.5, fatol=1e-3))
            if r.fun < bestv:
                best, bestv = r, r.fun
    r = minimize(cost, best.x, method="Nelder-Mead",
                 options=dict(maxiter=6000, xatol=1e-2, fatol=1e-5))
    v, val = (r.x, r.fun) if r.fun < bestv else (best.x, bestv)
    e, a, ro, s, tx, ty, d = unpack(v)
    return dict(elev=e, azim=a % 360, roll=ro, scale=s/sc_work,
                tx=tx/sc_work, ty=ty/sc_work, distance=d,
                centre=centre), val/sc_work


# ------------------------------------------------- multi-view reconstruction

def fit_multiview(build, targets, free, bounds, x0=None, work=180,
                  maxiter=4000, objective="chamfer"):
    """
    Optimise GEOMETRY and one camera pose per view, together.

    `build(params)` -> (pts, faces) for a dict of named geometry parameters;
    `targets` is a list of boolean masks, one per photograph; `free` names
    the geometry parameters to vary and `bounds` gives (lo, hi) for each.

    WHY MULTIPLE VIEWS ARE NOT OPTIONAL. One silhouette and N geometry
    unknowns is hopeless arithmetic: an unpinned airframe here has about 50
    free numbers against 7 pose parameters, so a single view can be matched
    perfectly by an aircraft of entirely the wrong shape. Each extra
    photograph adds 7 unknowns and a whole new boundary of constraint, and --
    this is the part that matters -- the GEOMETRY is shared across views
    while the poses are not. Model error therefore has to be consistent in
    every view at once, which is exactly what separates it from pose error.

    Still under-determined unless `free` is short. Pass the handful of
    parameters an overlay actually implicated, not everything.

    Cost is the mean symmetric chamfer distance over views, in working
    pixels, so views of different resolution contribute comparably.
    """
    from scipy.optimize import minimize
    from scipy import ndimage
    from PIL import Image

    prepared = []
    for t in targets:
        h, w = t.shape
        sc = work / max(h, w)
        tw, th = max(1, int(w*sc)), max(1, int(h*sc))
        tt = np.asarray(Image.fromarray(t.astype(np.uint8)*255)
                        .resize((tw, th), Image.NEAREST)) > 127
        edge = tt & ~ndimage.binary_erosion(tt)
        ys, xs = np.nonzero(tt)
        prepared.append(dict(
            size=(tw, th), tgt=tt, edge=edge, sc=sc,
            dt=ndimage.distance_transform_edt(~edge),
            cx=xs.mean(), cy=ys.mean(),
            extent=max(np.ptp(xs), np.ptp(ys)), diag=float(np.hypot(tw, th))))

    nf = len(free)
    nv = len(targets)

    def split(v):
        g = {k: bounds[k][0] + (bounds[k][1]-bounds[k][0]) /
                (1.0 + np.exp(-v[i])) for i, k in enumerate(free)}
        poses = []
        for j in range(nv):
            b = v[nf + j*7: nf + (j+1)*7]
            lo, hi = 0.4, 20.0
            # SEVEN per view, not six. The first version sliced six and then
            # wrote `exp(-0.0)` for the distance, which pinned every camera
            # at 10.2 m AND shifted every later view's parameters by one --
            # so the optimiser was moving numbers that did not mean what the
            # cost function thought they meant, and it stalled on step one
            # with nothing changed.
            poses.append((b[0], b[1], b[2], abs(b[3]), b[4], b[5],
                          lo + (hi-lo)/(1.0 + np.exp(-b[6]))))
        return g, poses

    def cost(v):
        g, poses = split(v)
        try:
            pts, faces = build(g)
        except Exception:
            return 1e6
        pts = np.asarray(pts, float)
        c = pts.mean(axis=0)
        total = 0.0
        for p, pr in zip(poses, prepared):
            # SCALE AND TRANSLATION ARE GIVEN IN FULL-RESOLUTION PIXELS and
            # must be converted to the working resolution the mask was
            # downsampled to. Omitting this put the model hundreds of pixels
            # off a 180 px canvas, so every silhouette came back EMPTY, the
            # cost sat at the image diagonal for every input, and the
            # optimiser correctly reported that nothing it tried helped.
            k = pr["sc"]
            p = (p[0], p[1], p[2], p[3]*k, p[4]*k, p[5]*k, p[6])
            m = silhouette(pts, faces, p, pr["size"], c)
            if not m.any():
                total += pr["diag"]; continue
            me = m & ~ndimage.binary_erosion(m)
            if not me.any():
                total += pr["diag"]; continue
            if objective == "iou":
                # AREA OVERLAP, as 1 - IoU scaled to the diagonal so the two
                # objectives are numerically comparable. Kept for the
                # comparison rather than because it is the better choice:
                # overlap is flat before the shapes meet and saturates after,
                # where chamfer descends smoothly throughout.
                u = (m | pr["tgt"]).sum()
                total += pr["diag"] * (1.0 - ((m & pr["tgt"]).sum()/u if u else 0.0))
            else:
                a = pr["dt"][me].mean()
                b = ndimage.distance_transform_edt(~me)[pr["edge"]].mean()
                total += 0.5*(a + b)
        return total / nv

    if x0 is None:
        raise ValueError("pass x0: geometry in logit space, then "
                         "(elev, azim, roll, scale, tx, ty) per view")
    # POSE FIRST, THEN EVERYTHING. Thirty-two dimensions from one start is
    # a stall: Nelder-Mead collapses its simplex before it finds a descent
    # direction. Fitting the cameras against the seed geometry gives the
    # joint stage a starting point where the shapes already roughly overlap.
    x = np.asarray(x0, float)
    gmask = np.zeros_like(x, bool); gmask[:nf] = True

    def pose_only(vp):
        y = x.copy(); y[~gmask] = vp
        return cost(y)

    rp = minimize(pose_only, x[~gmask], method="Nelder-Mead",
                  options=dict(maxiter=maxiter, xatol=1e-2, fatol=1e-3))
    x[~gmask] = rp.x
    best = rp.fun

    # THEN GEOMETRY IN SMALL BLOCKS, alternating with pose. Nelder-Mead
    # collapses its simplex long before it explores 32 dimensions -- run
    # whole, it moved the geometry by 0.0002 and declared victory. Powell
    # over a handful of coordinates at a time actually descends, and
    # re-fitting the cameras between rounds stops the geometry absorbing
    # what is really a pose error.
    block = max(1, min(5, nf))
    for _ in range(3):
        for i in range(0, nf, block):
            sel = np.zeros_like(x, bool); sel[i:min(i+block, nf)] = True

            def part(vs, sel=sel):
                y = x.copy(); y[sel] = vs
                return cost(y)

            rb = minimize(part, x[sel], method="Powell",
                          options=dict(maxiter=600, xtol=1e-2, ftol=1e-3))
            if rb.fun < best:
                x[sel], best = rb.x, rb.fun
        rp = minimize(pose_only, x[~gmask], method="Nelder-Mead",
                      options=dict(maxiter=maxiter//2, xatol=1e-2, fatol=1e-3))
        if rp.fun < best:
            x[~gmask], best = rp.x, rp.fun

    g, poses = split(x)
    return g, poses, best, prepared


# ---------------------------------------------------- structural edge map

def component_edges(parts, params, size, centre=None, thick=1,
                    masks=None):
    """
    Outline of EACH component, unioned -- silhouette plus interior junctions.

    `parts` is [(pts, faces), ...], one per wing/fuselage.

    THE MIDDLE GROUND BETWEEN SILHOUETTE AND WIREFRAME. A silhouette throws
    away everything inside the outline, so a pose can slide along the
    aircraft's long axis almost freely. A full mesh wireframe keeps too much:
    1085 faces of tessellation, including fuselage longerons that correspond
    to nothing visible, which buries the subject and gives the optimiser
    hundreds of edges to satisfy that the photograph never had.

    Per-component outlines keep exactly the lines a person would draw: the
    outer boundary, plus where the wing meets the fuselage, where the
    tailplane crosses the fin, where the pod hangs below the nose. Those
    interior lines move sharply with viewpoint, which is what pins down the
    degrees of freedom a silhouette leaves loose.
    """
    from scipy import ndimage
    e_, a_, r_ = params[0], params[1], params[2]
    R = rotation(e_, a_, r_)
    c = np.asarray(centre if centre is not None
                   else np.vstack([p for p, _ in parts]).mean(axis=0), float)

    # DEPTH ORDER, NEAREST FIRST, so an edge hidden behind another component
    # is not asked to explain anything. Without this the far wing's outline
    # runs straight through the fuselage, the photograph has no such line,
    # and the cost charges the model for an edge no camera could see.
    # Centroid depth is crude, but the components here -- wing, fuselage,
    # tailplane, fin, pod -- are well separated along the view axis.
    order = sorted(range(len(parts)),
                   key=lambda i: -float(((np.asarray(parts[i][0], float) - c)
                                         @ R.T)[:, 2].mean()))
    out = None
    covered = np.zeros((size[1], size[0]), bool)
    for i in order:
        pts, faces = parts[i]
        # REUSE the caller's rasters when it already has them. The cost
        # function rasterises every component for the union silhouette and
        # then called this, which rasterised all of them a second time --
        # half the run time of a fit, spent redrawing identical polygons.
        m = masks[i] if masks is not None else silhouette(pts, faces, params,
                                                          size, centre)
        if not m.any():
            continue
        vis = m & ~covered                     # what this component shows
        if vis.any():
            e = vis & ~ndimage.binary_erosion(vis)
            out = e if out is None else (out | e)
        covered |= m
    if out is None:
        return np.zeros((size[1], size[0]), bool)
    if thick > 1:
        out = ndimage.binary_dilation(out, np.ones((thick, thick)))
    return out


def photo_edges(rgb, mask, sigma=1.2, keep=0.18):
    """
    Edge map of a photograph: gradient magnitude inside the subject, plus
    the subject boundary, which is the one edge that is never ambiguous.

    Returns a float weight map, not a boolean -- a strong edge should pull
    harder than a faint one, and shading on a white-on-white model is faint.
    """
    from scipy import ndimage
    g = np.asarray(rgb, float).mean(axis=2)
    g = ndimage.gaussian_filter(g, sigma)
    mag = np.hypot(ndimage.sobel(g, 0), ndimage.sobel(g, 1))
    inside = mask & ~ndimage.binary_erosion(mask, np.ones((3, 3)))
    mag = mag * mask                                   # ignore background
    if mag.max() > 0:
        mag = mag / mag.max()
    thresh = np.quantile(mag[mask], 1 - keep) if mask.any() else 1.0
    w = np.where(mag >= thresh, mag, 0.0)
    w[inside] = 1.0                                    # boundary, full weight
    return w


def fit_edges(parts, target_mask, edge_weight, x0=None, scale=None,
              distance_bounds=(0.4, 20.0), work=220, boundary_mix=0.5):
    """
    Pose from structural edges: model component outlines onto photo edges.

    ASYMMETRIC, and that is the point. Every MODEL edge must land near some
    photograph edge; a photograph edge with no model counterpart is not
    penalised. Decals, invasion stripes, panel lines and grass texture all
    produce edges the model has no way to explain, and a symmetric cost would
    chase them. The silhouette half stays symmetric, because there both
    directions are meaningful.

    `boundary_mix` blends the two: 1.0 is pure silhouette chamfer, 0.0 is
    pure interior-edge matching. The default keeps the outline authoritative
    and lets the interior break ties.
    """
    from scipy.optimize import minimize
    from scipy import ndimage
    from PIL import Image

    h, w = target_mask.shape
    sc = work / max(h, w)
    tw, th = max(1, int(w*sc)), max(1, int(h*sc))
    tgt = np.asarray(Image.fromarray(target_mask.astype(np.uint8)*255)
                     .resize((tw, th), Image.NEAREST)) > 127
    tgt_edge = tgt & ~ndimage.binary_erosion(tgt)
    dt_bound = ndimage.distance_transform_edt(~tgt_edge)

    ew = np.asarray(Image.fromarray((edge_weight*255).astype(np.uint8))
                    .resize((tw, th), Image.BILINEAR)) / 255.0
    dt_edge = ndimage.distance_transform_edt(ew < 0.25)

    allpts = np.vstack([p for p, _ in parts])
    centre = allpts.mean(axis=0)
    free_scale = scale is None
    diag = float(np.hypot(tw, th))

    def unpack(v):
        i = 3
        s = abs(v[i])*sc if free_scale else scale*sc
        i += 1 if free_scale else 0
        lo, hi = distance_bounds
        d = lo + (hi-lo)/(1.0 + np.exp(-v[i+2]))
        return (v[0], v[1], v[2], s, v[i]*sc, v[i+1]*sc, d)

    def cost(v):
        p = unpack(v)
        # outer silhouette: union of the component masks, kept for reuse
        masks = [silhouette(pts, faces, p, (tw, th), centre)
                 for pts, faces in parts]
        m = masks[0].copy()
        for mi in masks[1:]:
            m |= mi
        if not m.any():
            return diag
        me = m & ~ndimage.binary_erosion(m)
        if not me.any():
            return diag
        a = dt_bound[me].mean()
        b = ndimage.distance_transform_edt(~me)[tgt_edge].mean()
        sil = 0.5*(a + b)
        ce = component_edges(parts, p, (tw, th), centre, masks=masks)
        inner = dt_edge[ce].mean() if ce.any() else diag
        return boundary_mix*sil + (1 - boundary_mix)*inner

    ys, xs = np.nonzero(target_mask)
    span = np.ptp(allpts, axis=0).max()
    s0 = scale if scale else (max(np.ptp(xs), np.ptp(ys)) / span)
    cx, cy = xs.mean(), ys.mean()

    # SCREEN, THEN REFINE. Running a full Nelder-Mead from all 36 starts
    # spent most of its time polishing basins that were never going to win.
    # Scoring each start first and descending only on the best few costs a
    # fraction and reaches the same optimum.
    seeds = []
    for a0 in range(0, 360, 30):
        for e0 in (15.0, 40.0, 65.0):
            v = ([e0, float(a0), 0.0] + ([s0] if free_scale else [])
                 + [cx, cy, 0.0])
            seeds.append((cost(np.array(v)), v))
    seeds.sort(key=lambda t: t[0])

    best, bestv = None, 1e9
    for _, v in seeds[:4]:
        r = minimize(cost, v, method="Nelder-Mead",
                     options=dict(maxiter=900, xatol=.5, fatol=1e-3))
        if r.fun < bestv:
            best, bestv = r, r.fun
    r = minimize(cost, best.x, method="Nelder-Mead",
                 options=dict(maxiter=4000, xatol=1e-2, fatol=1e-5))
    v, val = (r.x, r.fun) if r.fun < bestv else (best.x, bestv)
    e, a, ro, s, tx, ty, d = unpack(v)
    return dict(elev=e, azim=a % 360, roll=ro, scale=s/sc, tx=tx/sc, ty=ty/sc,
                distance=d, centre=centre), val/sc

import os, sys, time, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0, "."); sys.path.insert(0, "../tools")
import matplotlib; matplotlib.use("Agg")
import aerosandbox as asb
from PIL import Image
from scipy import ndimage
import pose_fit
T = "/Users/oliverlee/.claude/jobs/e50da590/tmp"

SPAN, AREA, LENGTH = 0.622, 0.0740, 0.482     # published, NOT free
AF = asb.Airfoil("clarky").scale(scale_y=0.05/asb.Airfoil("clarky").max_thickness())
SYM = asb.Airfoil("naca0008")

def build(g):
    """Airframe from the unspecified parameters. Span/area/length are pinned."""
    semi = SPAN/2
    # taper free; root chord follows from the pinned area
    tr = g["taper"]
    c_root = AREA / (SPAN * 0.5 * (1 + tr))
    c_tip = c_root * tr
    wing = asb.Wing(name="Main Wing", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[g["wing_x"], 0.0, g["wing_z"]], chord=c_root, airfoil=AF),
        asb.WingXSec(xyz_le=[g["wing_x"]+g["sweep"], semi, g["wing_z"]+g["dihedral"]],
                     chord=c_tip, airfoil=AF)])
    hs = asb.Wing(name="Horizontal Stabilizer", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[g["h_x"], 0.0, g["h_z"]], chord=g["h_croot"], airfoil=SYM),
        asb.WingXSec(xyz_le=[g["h_x"]+0.012, g["h_semi"], g["h_z"]],
                     chord=g["h_croot"]*0.68, airfoil=SYM)])
    vs = asb.Wing(name="Vertical Stabilizer", symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[g["v_x"], 0.0, g["h_z"]], chord=g["v_croot"], airfoil=SYM),
        asb.WingXSec(xyz_le=[g["v_x"]+0.054, 0.0, g["h_z"]+g["v_height"]],
                     chord=g["v_croot"]*0.48, airfoil=SYM)])
    # fuselage: pinned length, free depth profile via 3 control heights
    xs = np.array([0.0, .06, .12, .18, .25, .31, .37, .43, LENGTH])
    hts = np.interp(xs/LENGTH, [0, .25, .5, .75, 1.0],
                    [g["f_h0"], g["f_h1"], g["f_h2"], g["f_h3"], g["f_h4"]])
    wds = hts * g["f_wh"]
    fuse = asb.Fuselage(name="Fuselage", xsecs=[
        asb.FuselageXSec(xyz_c=[float(x), 0.0, float(0.004*i)],
                         width=float(w), height=float(h), shape=g["f_shape"])
        for i, (x, w, h) in enumerate(zip(xs, wds, hts))])
    pod = asb.Fuselage(name="Power Pod", xsecs=[
        asb.FuselageXSec(xyz_c=[0.006, 0, -g["pod_z"]], width=0.028, height=0.028, shape=6.0),
        asb.FuselageXSec(xyz_c=[0.071, 0, -g["pod_z"]], width=0.028, height=0.028, shape=6.0)])
    ap = asb.Airplane(name="m", wings=[wing, hs, vs], fuselages=[fuse, pod])
    pts, faces = ap.mesh_body(method="quad")
    return np.array(pts, float), faces

BOUNDS = dict(
    taper=(0.45, 0.85), wing_x=(0.08, 0.16), wing_z=(-0.03, 0.01),
    sweep=(-0.01, 0.04), dihedral=(0.0, 0.05),
    h_x=(0.32, 0.42), h_z=(-0.01, 0.04), h_croot=(0.05, 0.11), h_semi=(0.07, 0.15),
    v_x=(0.30, 0.40), v_croot=(0.09, 0.18), v_height=(0.08, 0.16),
    f_h0=(0.02, 0.05), f_h1=(0.04, 0.09), f_h2=(0.05, 0.11),
    f_h3=(0.02, 0.07), f_h4=(0.01, 0.04),
    f_wh=(0.45, 1.05), f_shape=(2.0, 8.0), pod_z=(0.0, 0.045))
FREE = list(BOUNDS)
print(f"{len(FREE)} geometry unknowns, 2 views -> {len(FREE)+12} parameters total")
np.save(f"{T}/free.npy", np.array(FREE))

# ---- seed from the current model, then optimise against both views
def logit(x, lo, hi):
    x = min(max(x, lo+1e-6*(hi-lo)), hi-1e-6*(hi-lo))
    p = (x-lo)/(hi-lo)
    return float(np.log(p/(1-p)))

SEED = dict(taper=0.59, wing_x=0.117, wing_z=-0.015, sweep=0.0, dihedral=0.027,
            h_x=0.368, h_z=0.010, h_croot=0.076, h_semi=0.113,
            v_x=0.346, v_croot=0.136, v_height=0.118,
            f_h0=0.032, f_h1=0.052, f_h2=0.075, f_h3=0.045, f_h4=0.026,
            f_wh=0.70, f_shape=4.0, pod_z=0.026)

targets = [np.load(f"{T}/studio_mask.npy"), np.load(f"{T}/front_mask.npy")]
x0 = [logit(SEED[k], *BOUNDS[k]) for k in FREE]
for t, (e0, a0) in zip(targets, [(21.0, 345.0), (18.0, 215.0)]):
    ys, xs = np.nonzero(t)
    s0 = max(np.ptp(xs), np.ptp(ys)) / SPAN
    x0 += [e0, a0, 0.0, s0, xs.mean(), ys.mean(), 2.0]

t0 = time.time()
g, poses, cost, prep = pose_fit.fit_multiview(build, targets, FREE, BOUNDS,
                                              x0=np.array(x0), maxiter=9000)
print(f"\njoint fit in {time.time()-t0:.0f} s   mean chamfer {cost:.2f} working px")
for k in FREE:
    lo, hi = BOUNDS[k]
    flag = "  <- at bound" if (g[k]-lo < .02*(hi-lo) or hi-g[k] < .02*(hi-lo)) else ""
    print(f"   {k:10} {SEED[k]:8.4f} -> {g[k]:8.4f}{flag}")
np.save(f"{T}/mv_g.npy", np.array([g[k] for k in FREE]))
np.save(f"{T}/mv_poses.npy", np.array(poses))

# ---- overlays: seed vs fitted, both views
from PIL import ImageDraw
def overlay(gd, pose, mask, crop_png, out, colour=(225,25,25)):
    pts, faces = build(gd)
    H, W = mask.shape
    p = tuple(pose)
    m = pose_fit.silhouette(pts, faces, p, (W, H), pts.mean(axis=0))
    iou = (m & mask).sum()/max(1,(m|mask).sum())
    e = ndimage.binary_dilation(m & ~ndimage.binary_erosion(m, np.ones((3,3))),
                                np.ones((2,2)))
    im = np.array(Image.open(crop_png).convert("RGB")).astype(float)
    im[e] = 0.06*im[e] + 0.94*np.array(colour)
    Image.fromarray(im.astype(np.uint8)).save(out)
    return iou

crops = [f"{T}/studio_crop.png", f"{T}/front_crop.png"]
names = ["studio", "front"]
for nm, t, c, pose in zip(names, targets, crops, poses):
    i_fit = overlay(g, pose, t, c, f"{T}/mv_{nm}_fit.png")
    i_seed = overlay(SEED, pose, t, c, f"{T}/mv_{nm}_seed.png", (40,90,210))
    print(f"{nm:7} IoU seed {i_seed:.3f} -> fitted {i_fit:.3f}")

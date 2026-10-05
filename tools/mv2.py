import os, sys, time, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0, "."); sys.path.insert(0, "../tools")
import matplotlib; matplotlib.use("Agg")
from PIL import Image
from scipy import ndimage
import pose_fit
T = "/Users/oliverlee/.claude/jobs/e50da590/tmp"
exec(open(f"{T}/mv.py").read().split("# ---- seed")[0])   # build(), BOUNDS

SEED = dict(taper=0.59, wing_x=0.117, wing_z=-0.015, sweep=0.0, dihedral=0.027,
            h_x=0.368, h_z=0.010, h_croot=0.076, h_semi=0.113,
            v_x=0.346, v_croot=0.136, v_height=0.118,
            f_h0=0.032, f_h1=0.052, f_h2=0.075, f_h3=0.045, f_h4=0.026,
            f_wh=0.70, f_shape=4.0, pod_z=0.026)

# ONLY WHAT THE OVERLAYS IMPLICATED, in both views independently:
#   tailplane too large and too low   -> h_croot, h_semi, h_z
#   fin too tall                      -> v_height
#   aft fuselage too deep             -> f_h3
FREE2 = ["h_croot", "h_semi", "h_z", "v_height", "f_h3"]
B2 = {k: BOUNDS[k] for k in FREE2}

def logit(x, lo, hi):
    p = min(max((x-lo)/(hi-lo), 1e-6), 1-1e-6); return float(np.log(p/(1-p)))

targets = [np.load(f"{T}/studio_mask.npy"), np.load(f"{T}/front_mask.npy")]
def build2(gd):
    full = dict(SEED); full.update(gd); return build(full)

x0 = [logit(SEED[k], *B2[k]) for k in FREE2]
for t, (e0, a0) in zip(targets, [(21.0, 345.0), (18.0, 215.0)]):
    ys, xs = np.nonzero(t)
    x0 += [e0, a0, 0.0, max(np.ptp(xs), np.ptp(ys))/0.622, xs.mean(), ys.mean(), 2.0]

t0 = time.time()
g2, poses2, cost2, _ = pose_fit.fit_multiview(build2, targets, FREE2, B2,
                                              x0=np.array(x0), maxiter=9000)
print(f"focused fit in {time.time()-t0:.0f} s   mean chamfer {cost2:.2f} px "
      f"(20-param run: 3.37)")
print(f"{'param':10}{'seed':>9}{'fitted':>9}   change")
for k in FREE2:
    d = (g2[k]-SEED[k])*1000
    print(f"{k:10}{SEED[k]*1000:9.1f}{g2[k]*1000:9.1f}   {d:+6.1f} mm")

def ov(gd, pose, mask, crop, out, col):
    pts, faces = build2(gd) if gd is not SEED else build(SEED)
    m = pose_fit.silhouette(pts, faces, tuple(pose), (mask.shape[1], mask.shape[0]),
                            pts.mean(axis=0))
    iou = (m & mask).sum()/max(1,(m|mask).sum())
    e = ndimage.binary_dilation(m & ~ndimage.binary_erosion(m, np.ones((3,3))), np.ones((2,2)))
    im = np.array(Image.open(crop).convert("RGB")).astype(float)
    im[e] = 0.06*im[e] + 0.94*np.array(col)
    Image.fromarray(im.astype(np.uint8)).save(out); return iou

for nm, t, c, p in zip(["studio","front"], targets,
                       [f"{T}/studio_crop.png", f"{T}/front_crop.png"], poses2):
    a = ov(SEED, p, t, c, f"{T}/f2_{nm}_seed.png", (40,90,210))
    b = ov(g2,   p, t, c, f"{T}/f2_{nm}_fit.png",  (225,25,25))
    print(f"{nm:7} IoU {a:.3f} -> {b:.3f}")
np.save(f"{T}/g2.npy", np.array([g2[k] for k in FREE2]))

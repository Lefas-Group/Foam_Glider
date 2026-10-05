import os, sys, time, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0, "."); sys.path.insert(0, "../tools")
import matplotlib; matplotlib.use("Agg")
from PIL import Image
from scipy import ndimage
import pose_fit
T = "/Users/oliverlee/.claude/jobs/e50da590/tmp"
ns = {}
exec(open("_notebook.py").read(), ns)
exec(open("chapters/01-airframe-reconstruction/_model.py").read(), ns)
pts, faces = ns["airplane"].mesh_body(method="quad")
pts = np.array(pts, float)
target = np.load(f"{T}/studio_mask.npy")
H, W = target.shape
photo = np.array(Image.open(f"{T}/studio_crop.png").convert("RGB")).astype(float)

def draw(pose, name):
    p = (pose["elev"], pose["azim"], pose["roll"], pose["scale"],
         pose["tx"], pose["ty"], pose["distance"])
    m = pose_fit.silhouette(pts, faces, p, (W, H), pose["centre"])
    iou = (m & target).sum() / max(1, (m | target).sum())
    e = ndimage.binary_dilation(m & ~ndimage.binary_erosion(m, np.ones((3,3))),
                                np.ones((2,2)))
    out = photo.copy()
    out[e] = 0.06*out[e] + 0.94*np.array([225, 25, 25])
    Image.fromarray(out.astype(np.uint8)).save(f"{T}/studio_{name}.png")
    return iou

for label, fn in (("iou", pose_fit.fit_silhouette), ("cham", pose_fit.fit_chamfer)):
    t0 = time.time()
    pose, val = fn(pts, faces, target)
    iou = draw(pose, label)
    print(f"{label:5}  elev {pose['elev']:6.1f}  azim {pose['azim']:6.1f}  "
          f"roll {pose['roll']:5.1f}  dist {pose['distance']:5.2f} m  "
          f"IoU {iou:.3f}  ({time.time()-t0:.0f} s)")
    np.save(f"{T}/pose_{label}.npy", np.array(
        [pose['elev'], pose['azim'], pose['roll'], pose['scale'],
         pose['tx'], pose['ty'], pose['distance']]))

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
target = np.load(f"{T}/mask_m1.npy")

t0 = time.time()
pose, cham = pose_fit.fit_chamfer(pts, faces, target)
print(f"chamfer fit in {time.time()-t0:.0f} s")
print(f"  elev {pose['elev']:6.1f}  azim {pose['azim']:6.1f}  roll {pose['roll']:6.1f}")
print(f"  scale {pose['scale']:6.0f} px/m   distance {pose['distance']:.2f} m")
print(f"  mean outline error {cham:.1f} px")

p = (pose["elev"], pose["azim"], pose["roll"], pose["scale"],
     pose["tx"], pose["ty"], pose["distance"])
H, W = target.shape
m = pose_fit.silhouette(pts, faces, p, (W, H), pose["centre"])
iou = (m & target).sum() / (m | target).sum()
print(f"  IoU of this pose {iou:.3f}  (silhouette fit got 0.694)")
edge = ndimage.binary_dilation(m & ~ndimage.binary_erosion(m, np.ones((4,4))),
                               np.ones((2,2)))
ph = np.array(Image.open(f"{T}/photos/m1.jpg").convert("RGB")).astype(float)
ph[edge] = 0.08*ph[edge] + 0.92*np.array([235, 25, 25])
Image.fromarray(ph.astype(np.uint8)).save(f"{T}/cham_outline.png")

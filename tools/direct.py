import os, sys, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0, "."); sys.path.insert(0, "../tools")
import matplotlib; matplotlib.use("Agg")
from PIL import Image, ImageDraw
import pose_fit
T = "/Users/oliverlee/.claude/jobs/e50da590/tmp"

ns = {}
exec(open("_notebook.py").read(), ns)
exec(open("chapters/01-airframe-reconstruction/_model.py").read(), ns)
airplane = ns["airplane"]
L = pose_fit.landmarks(airplane)

img = {"fuselage:nose": (503, 270),
       "main-wing:tip-mirror": (543, 90), "main-wing:tip": (140, 347),
       "vertical-stabilizer:tip": (408, 63),
       "horizontal-stabilizer:tip": (318, 132)}
pose, resid = pose_fit.fit(L, img, perspective=True)
print(f"elev={pose['elev']:.1f} azim={pose['azim']:.1f} roll={pose['roll']:.1f} "
      f"scale={pose['scale']:.0f}px/m dist={pose['distance']:.2f}m "
      f"resid mean={resid.mean():.1f} max={resid.max():.1f} px")

# PROJECT THE MESH STRAIGHT INTO PHOTO PIXELS -- no render, no rescale.
pts, faces = airplane.mesh_body(method="quad")
pts = np.array(pts, float)
proj = pose_fit.project(pts, pose["elev"], pose["azim"], pose["roll"],
                        pose["scale"], pose["tx"], pose["ty"],
                        pose["centre"], pose["distance"])

photo = Image.open(f"{T}/photos/m1.jpg").convert("RGB")
for style, width, keep in (("wire", 1, 1), ("sparse", 1, 6)):
    im = photo.copy(); d = ImageDraw.Draw(im)
    for n, f in enumerate(faces):
        if n % keep: continue
        poly = [tuple(proj[i]) for i in f]
        d.polygon(poly, outline=(235, 25, 25))
    for k in img:
        u, v = img[k]
        d.ellipse([u-6, v-6, u+6, v+6], outline=(255, 215, 0), width=3)
    im.save(f"{T}/direct_{style}.png")
print(f"{len(pts)} mesh points, {len(faces)} faces")

# CLEAN OUTLINE: rasterise the projected faces into a mask, take its boundary.
from scipy import ndimage
W, H = photo.size
m = Image.new("L", (W, H), 0); dm = ImageDraw.Draw(m)
for f in faces:
    dm.polygon([tuple(proj[i]) for i in f], fill=255)
mask = np.array(m) > 127
edge = mask & ~ndimage.binary_erosion(mask, np.ones((4, 4)))
edge = ndimage.binary_dilation(edge, np.ones((2, 2)))

out = np.array(photo).astype(float)
out[edge] = 0.08*out[edge] + 0.92*np.array([235, 25, 25])
im = Image.fromarray(out.astype(np.uint8)); d = ImageDraw.Draw(im)
for k in img:
    u, v = img[k]
    d.ellipse([u-7, v-7, u+7, v+7], outline=(255, 205, 0), width=3)
im.save(f"{T}/fitted_outline.png")

# Residual table, in millimetres as well as pixels.
mm = 1000.0 / pose["scale"]
print(f"\n{'landmark':34}{'px':>7}{'mm':>8}")
for k, r in zip(pose["keys"], resid):
    print(f"{k:34}{r:7.1f}{r*mm:8.1f}")
print(f"{'':34}{'':7}  ({mm:.2f} mm per px at the fitted scale)")

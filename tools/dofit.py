import os, sys, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0, "."); sys.path.insert(0, "../tools")
import matplotlib; matplotlib.use("Agg")
import pose_fit

ns = {}
exec(open("_notebook.py").read(), ns)
exec(open("chapters/01-airframe-reconstruction/_model.py").read(), ns)
L = pose_fit.landmarks(ns["airplane"])

# Read off the gridded photograph, in m1.jpg pixels (800x450).
px = {
    "nose":      (503, 270),
    "wing-A":    (543,  90),   # wingtip, upper right
    "wing-B":    (140, 347),   # wingtip, lower left
    "fin":       (408,  63),
    "stab":      (318, 132),   # the stab tip that extends left
}

for tag, (wa, wb, st) in {
    "A: starboard=upper-right": ("main-wing:tip", "main-wing:tip-mirror",
                                 "horizontal-stabilizer:tip-mirror"),
    "B: starboard=lower-left":  ("main-wing:tip-mirror", "main-wing:tip",
                                 "horizontal-stabilizer:tip"),
}.items():
    img = {"fuselage:nose": px["nose"], wa: px["wing-A"], wb: px["wing-B"],
           "vertical-stabilizer:tip": px["fin"], st: px["stab"]}
    pose, resid = pose_fit.fit(L, img, perspective=True)
    print(f"\n{tag}")
    print(f"   elev {pose['elev']:6.1f}   azim {pose['azim']:6.1f}   "
          f"roll {pose['roll']:6.1f}   scale {pose['scale']:7.1f} px/m")
    print(f"   residual  mean {resid.mean():5.1f} px   max {resid.max():5.1f} px")
    for k, r in zip(pose["keys"], resid):
        print(f"      {k:34} {r:6.1f} px")

import os, sys, time, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0,"."); sys.path.insert(0,"../tools")
import matplotlib; matplotlib.use("Agg")
from PIL import Image
from scipy import ndimage
import pose_fit
T="/Users/oliverlee/.claude/jobs/e50da590/tmp"
ns={}; exec(open("_notebook.py").read(), ns)
exec(open("chapters/01-airframe-reconstruction/_model.py").read(), ns)
ap=ns["airplane"]
parts=[(np.array(p,float),f) for p,f in
       [w.mesh_body(method="quad") for w in ap.wings]+
       [fu.mesh_body(method="quad") for fu in ap.fuselages]]
allp=np.vstack([p for p,_ in parts]); C=allp.mean(axis=0)

VIEW = os.environ.get("VIEW","studio")
mask=np.load(f"{T}/{VIEW}_mask.npy")
rgb=np.array(Image.open(f"{T}/{VIEW}_crop.png").convert("RGB"))
ew=pose_fit.photo_edges(rgb, mask)
H,W=mask.shape

def draw(pose, tag, col=(225,25,25)):
    p=(pose["elev"],pose["azim"],pose["roll"],pose["scale"],
       pose["tx"],pose["ty"],pose["distance"])
    m=None
    for pts,faces in parts:
        mi=pose_fit.silhouette(pts,faces,p,(W,H),C); m=mi if m is None else (m|mi)
    iou=(m&mask).sum()/max(1,(m|mask).sum())
    ce=pose_fit.component_edges(parts,p,(W,H),C,thick=2)
    im=np.array(Image.open(f"{T}/{VIEW}_crop.png").convert("RGB")).astype(float)
    im[ce]=0.05*im[ce]+0.95*np.array(col)
    Image.fromarray(im.astype(np.uint8)).save(f"{T}/hyb_{VIEW}_{tag}.png")
    return iou

for mix,tag in ((1.0,"sil"), (0.5,"mix50"), (0.25,"mix25")):
    t0=time.time()
    pose,val=pose_fit.fit_edges(parts, mask, ew, boundary_mix=mix)
    iou=draw(pose,tag)
    print(f"mix={mix:<5} elev {pose['elev']:6.1f} azim {pose['azim']:6.1f} "
          f"roll {pose['roll']:5.1f} dist {pose['distance']:5.2f}  "
          f"IoU {iou:.3f}  cost {val:.3f}  ({time.time()-t0:.0f}s)")

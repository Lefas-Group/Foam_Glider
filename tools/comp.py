import os, sys, numpy as np
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
names=[w.name for w in ap.wings]+[f.name for f in ap.fuselages]
parts=[(np.array(p,float),f) for p,f in
       [w.mesh_body(method="quad") for w in ap.wings]+
       [fu.mesh_body(method="quad") for fu in ap.fuselages]]
C=np.vstack([p for p,_ in parts]).mean(axis=0)

# notebook palette: teal, amber, grey, alarm red, plus a violet for the pod
COLS=[(20,101,92),(184,134,11),(92,102,112),(179,65,44),(120,70,150)]

POSES = {   # from fit_chamfer / fit_edges(mix=1.0), the pure-outline method
  "studio": dict(elev=21.1, azim=344.7, roll=0.0),
  "grass":  dict(elev=40.2, azim=133.1, roll=0.0),
}

for view, ang in POSES.items():
    mask=np.load(f"{T}/{view}_mask.npy"); H,W=mask.shape
    # recover scale/translation by re-running the outline fit at this seed
    rgb=np.array(Image.open(f"{T}/{view}_crop.png").convert("RGB"))
    ew=pose_fit.photo_edges(rgb,mask)
    pose,_=pose_fit.fit_edges(parts, mask, ew, boundary_mix=1.0)
    p=(pose["elev"],pose["azim"],pose["roll"],pose["scale"],
       pose["tx"],pose["ty"],pose["distance"])

    # per-component VISIBLE outlines, depth sorted exactly as component_edges
    R=pose_fit.rotation(p[0],p[1],p[2])
    order=sorted(range(len(parts)),
                 key=lambda i: -float(((parts[i][0]-C)@R.T)[:,2].mean()))
    im=np.array(Image.open(f"{T}/{view}_crop.png").convert("RGB")).astype(float)
    covered=np.zeros((H,W),bool); drawn=[]
    for i in order:
        m=pose_fit.silhouette(parts[i][0],parts[i][1],p,(W,H),C)
        vis=m & ~covered
        if vis.any():
            e=ndimage.binary_dilation(vis & ~ndimage.binary_erosion(vis),
                                      np.ones((2,2)))
            col=np.array(COLS[i%len(COLS)],float)
            im[e]=0.05*im[e]+0.95*col
            drawn.append((names[i], int(e.sum()), COLS[i%len(COLS)]))
        covered|=m
    Image.fromarray(im.astype(np.uint8)).save(f"{T}/comp_{view}.png")
    print(f"{view}: elev {pose['elev']:.1f} azim {pose['azim']:.1f}")
    for n,px,c in drawn: print(f"    {n:24} {px:5d} px  rgb{c}")

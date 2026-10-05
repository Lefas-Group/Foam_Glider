import os, sys, numpy as np
os.chdir("/Users/oliverlee/Documents/Careers/Demetrios_Continued/Foam_Glider/mustang-mkr2")
sys.path.insert(0,"."); sys.path.insert(0,"../tools")
import matplotlib; matplotlib.use("Agg")
from PIL import Image, ImageDraw
from scipy import ndimage
import pose_fit
T="/Users/oliverlee/.claude/jobs/e50da590/tmp"
ns={}; exec(open("_notebook.py").read(), ns)
exec(open("chapters/01-airframe-reconstruction/_model.py").read(), ns)
ap=ns["airplane"]
parts=[(np.array(p,float),f) for p,f in
       [w.mesh_body(method="quad") for w in ap.wings]+
       [fu.mesh_body(method="quad") for fu in ap.fuselages]]
C=np.vstack([p for p,_ in parts]).mean(axis=0)
COLS=[(20,101,92),(184,134,11),(92,102,112),(179,65,44),(120,70,150)]

def render(view):
    mask=np.load(f"{T}/{view}_mask.npy"); H,W=mask.shape
    rgb=np.array(Image.open(f"{T}/{view}_crop.png").convert("RGB"))
    ew=pose_fit.photo_edges(rgb,mask)
    pose,_=pose_fit.fit_edges(parts, mask, ew, boundary_mix=1.0)
    p=(pose["elev"],pose["azim"],pose["roll"],pose["scale"],
       pose["tx"],pose["ty"],pose["distance"])
    R=pose_fit.rotation(p[0],p[1],p[2])
    order=sorted(range(len(parts)),
                 key=lambda i: -float(((parts[i][0]-C)@R.T)[:,2].mean()))
    im=np.array(Image.open(f"{T}/{view}_crop.png").convert("RGB")).astype(float)
    covered=np.zeros((H,W),bool)
    # HIDDEN FAINT, VISIBLE SOLID -- the engineering drawing convention, and
    # it exists for exactly this reason: a hidden line still tells you where
    # the part is, while reading clearly as "not something the eye can see".
    for i in order:
        m=pose_fit.silhouette(parts[i][0],parts[i][1],p,(W,H),C)
        full=ndimage.binary_dilation(m & ~ndimage.binary_erosion(m),np.ones((2,2)))
        vis = full & ~covered
        hid = full & covered
        col=np.array(COLS[i%5],float)
        if hid.any(): im[hid]=0.70*im[hid]+0.30*col     # faint
        if vis.any(): im[vis]=0.05*im[vis]+0.95*col     # solid
        covered|=m
    Image.fromarray(im.astype(np.uint8)).save(f"{T}/hl_{view}_both.png")

for v in ("studio","grass"): render(v)

for view in ("studio","grass"):
    ims=[(f"hl_{view}_all.png","ALL lines equal weight"),
         (f"hl_{view}_vis.png","VISIBLE only"),
         (f"hl_{view}_both.png","VISIBLE solid + hidden faint")]
    W=430; tiles=[]
    for f,lab in ims:
        I=Image.open(f"{T}/{f}").convert("RGB")
        tiles.append((I.resize((W,int(I.height*W/I.width)),Image.LANCZOS),lab))
    H=tiles[0][0].height
    s=Image.new("RGB",(W*3+20,H+26),"white"); d=ImageDraw.Draw(s)
    for k,(I,lab) in enumerate(tiles):
        x=k*(W+10); s.paste(I,(x,26)); d.text((x+4,7),lab,fill=(0,0,0))
    s.save(f"{T}/hl3_{view}.png")
print("three-way comparisons written")

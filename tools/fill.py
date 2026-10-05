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

def layers(view):
    mask=np.load(f"{T}/{view}_mask.npy"); H,W=mask.shape
    rgb=np.array(Image.open(f"{T}/{view}_crop.png").convert("RGB"))
    ew=pose_fit.photo_edges(rgb,mask)
    pose,_=pose_fit.fit_edges(parts, mask, ew, boundary_mix=1.0)
    p=(pose["elev"],pose["azim"],pose["roll"],pose["scale"],
       pose["tx"],pose["ty"],pose["distance"])
    R=pose_fit.rotation(p[0],p[1],p[2])
    order=sorted(range(len(parts)),
                 key=lambda i:-float(((parts[i][0]-C)@R.T)[:,2].mean()))
    masks={}; covered=np.zeros((H,W),bool); union=np.zeros((H,W),bool)
    for i in order:
        m=pose_fit.silhouette(parts[i][0],parts[i][1],p,(W,H),C)
        masks[i]=dict(full=m, vis=m & ~covered, hid=m & covered)
        covered|=m; union|=m
    return mask, union, masks, order, rgb

def outline_only(base, masks, order):
    im=base.astype(float).copy()
    for i in order:
        d=masks[i]; col=np.array(COLS[i%5],float)
        for reg,alpha in ((d["hid"],0.30),(d["vis"],0.95)):
            if reg.any():
                e=ndimage.binary_dilation(reg & ~ndimage.binary_erosion(reg),
                                          np.ones((2,2)))
                im[e]=(1-alpha)*im[e]+alpha*col
    return im

def flat_fill(base, masks, order, a=0.22):
    im=base.astype(float).copy()
    for i in order:
        d=masks[i]; col=np.array(COLS[i%5],float)
        if d["vis"].any(): im[d["vis"]]=(1-a)*im[d["vis"]]+a*col
    return outline_only(im.astype(np.uint8), masks, order)

def disparity(base, photo, union, masks, order):
    """Tint strongly where the model is wrong, barely where it agrees."""
    im=base.astype(float).copy()
    over = union & ~photo          # model where there is no aircraft
    under = photo & ~union         # aircraft the model does not cover
    for i in order:
        d=masks[i]; col=np.array(COLS[i%5],float)
        agree = d["vis"] & photo
        if agree.any(): im[agree]=0.90*im[agree]+0.10*col   # faint
        bad = d["vis"] & over
        if bad.any():   im[bad]=0.35*im[bad]+0.65*col       # strong
    if under.any():
        im[under]=0.45*im[under]+0.55*np.array([25,25,25],float)  # dark grey
    return outline_only(im.astype(np.uint8), masks, order)

for view in ("studio","grass"):
    photo, union, masks, order, rgb = layers(view)
    outs=[("outline only", outline_only(rgb, masks, order)),
          ("flat 22% fill", flat_fill(rgb, masks, order)),
          ("disparity shaded", disparity(rgb, photo, union, masks, order))]
    o=(union&~photo).sum(); u=(photo&~union).sum()
    print(f"{view:7} overshoot {o:6d} px   missed {u:6d} px")
    W=430; tiles=[]
    for lab,arr in outs:
        I=Image.fromarray(arr.astype(np.uint8))
        tiles.append((I.resize((W,int(I.height*W/I.width)),Image.LANCZOS),lab))
        I.save(f"{T}/fill_{view}_{lab.split()[0]}.png")
    H=tiles[0][0].height
    s=Image.new("RGB",(W*3+20,H+26),"white"); d=ImageDraw.Draw(s)
    for k,(I,lab) in enumerate(tiles):
        x=k*(W+10); s.paste(I,(x,26)); d.text((x+4,7),lab,fill=(0,0,0))
    s.save(f"{T}/fill3_{view}.png")
print("done")

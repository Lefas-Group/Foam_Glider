import numpy as np
from PIL import Image
from scipy import ndimage
T = "/Users/oliverlee/.claude/jobs/e50da590/tmp"

def segment(path, tol=38):
    """
    Subject mask with no hand-written colour rule and no landmarks.

    Seeded from the BORDER: whatever colours touch the frame edge are
    background by assumption, everything sufficiently unlike them is subject,
    and the largest filled component wins. The earlier version hard-coded
    "green is grass", which worked on one photograph and returned a house and
    some sky on the next.
    """
    a = np.array(Image.open(path).convert("RGB")).astype(float)
    h, w, _ = a.shape
    band = max(2, min(h, w)//40)
    border = np.vstack([a[:band].reshape(-1,3), a[-band:].reshape(-1,3),
                        a[:, :band].reshape(-1,3), a[:, -band:].reshape(-1,3)])
    # A few background clusters, not one mean: grass and sky are both border.
    qs = np.quantile(border, [.1, .3, .5, .7, .9], axis=0)
    dist = np.min([np.abs(a - q).sum(axis=2) for q in qs], axis=0)
    fg = dist > tol*3
    fg = ndimage.binary_opening(fg, np.ones((5,5)))
    fg = ndimage.binary_closing(fg, np.ones((9,9)))
    lab, n = ndimage.label(fg)
    if not n: return fg
    sizes = ndimage.sum(fg, lab, range(1, n+1))
    return ndimage.binary_fill_holes(lab == (np.argmax(sizes)+1))

for name in ("m1", "m4"):
    m = segment(f"{T}/photos/{name}.jpg")
    ys, xs = np.nonzero(m)
    frac = m.sum()/m.size
    print(f"{name}: {int(m.sum()):7d} px ({frac:5.1%} of frame), "
          f"bbox {xs.max()-xs.min()}x{ys.max()-ys.min()}")
    Image.fromarray((m*255).astype(np.uint8)).save(f"{T}/auto_{name}.png")

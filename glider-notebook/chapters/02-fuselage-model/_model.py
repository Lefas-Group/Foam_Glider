# Forked from chapters/01-foam-glider/_model.py at c8bd387.
#
# Differences, all deliberate:
#   * a Fuselage is added -- 200 mm long, 15 mm high, 10 mm wide (two plies of
#     5 mm foam) -- and passed to the Airplane, so its mass and drag now count.
#   * the builder is renamed make_glider_with_fuse, since both aircraft exist.
#
# The wing, both tails and every section are unchanged; the rest of the diff
# against the parent is reflow, not design.
import aerosandbox as asb
import aerosandbox.numpy as np

def make_glider_with_fuse(c_root, taper, cg_x):
    wing = asb.Wing(
        name="Wing", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root, airfoil=asb.Airfoil("naca4405")),
            asb.WingXSec(xyz_le=[0, 0.15, 0], chord=c_root * taper, airfoil=asb.Airfoil("naca4405"))
        ]
    )
    htail = asb.Wing(
        name="H-tail", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.15, 0, 0], chord=0.03, airfoil=asb.Airfoil("naca0005")),
            asb.WingXSec(xyz_le=[0.15, 0.05, 0], chord=0.03, airfoil=asb.Airfoil("naca0005"))
        ]
    )
    vtail = asb.Wing(
        name="V-tail", symmetric=False,
        xsecs=[
            asb.WingXSec(xyz_le=[0.15, 0, 0], chord=0.03, airfoil=asb.Airfoil("naca0005")),
            asb.WingXSec(xyz_le=[0.15, 0, 0.05], chord=0.03, airfoil=asb.Airfoil("naca0005"))
        ]
    )
    fuse = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(xyz_c=[-0.02, 0, 0], width=0.01, height=0.015, shape=4),
            asb.FuselageXSec(xyz_c=[0.18, 0, 0], width=0.01, height=0.015, shape=4)
        ]
    )
    return asb.Airplane(name="Glider", xyz_ref=[cg_x, 0, 0], wings=[wing, htail, vtail], fuselages=[fuse])

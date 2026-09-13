import aerosandbox as asb
import aerosandbox.numpy as np

def make_glider(c_root, taper, cg_x):
    wing = asb.Wing(
        name="Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0, 0, 0],
                chord=c_root,
                airfoil=asb.Airfoil("naca4405")
            ),
            asb.WingXSec(
                xyz_le=[0, 0.15, 0],
                chord=c_root * taper,
                airfoil=asb.Airfoil("naca4405")
            )
        ]
    )
    
    htail = asb.Wing(
        name="H-tail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0.15, 0, 0],
                chord=0.03,
                airfoil=asb.Airfoil("naca0005")
            ),
            asb.WingXSec(
                xyz_le=[0.15, 0.05, 0],
                chord=0.03,
                airfoil=asb.Airfoil("naca0005")
            )
        ]
    )
    
    vtail = asb.Wing(
        name="V-tail",
        symmetric=False,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0.15, 0, 0],
                chord=0.03,
                airfoil=asb.Airfoil("naca0005")
            ),
            asb.WingXSec(
                xyz_le=[0.15, 0, 0.05],
                chord=0.03,
                airfoil=asb.Airfoil("naca0005")
            )
        ]
    )
    
    return asb.Airplane(
        name="Glider",
        xyz_ref=[cg_x, 0, 0],
        wings=[wing, htail, vtail],
    )

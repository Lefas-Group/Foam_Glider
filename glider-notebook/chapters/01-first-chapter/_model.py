import aerosandbox as asb
import aerosandbox.numpy as np

def build_glider(c_root, c_tip, x_wing, ballast_mass=0.0):
    wing = asb.Wing(
        name="Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[x_wing, 0, 0], chord=c_root, airfoil=asb.Airfoil("naca0010")),
            asb.WingXSec(xyz_le=[x_wing, 0.15, 0], chord=c_tip, airfoil=asb.Airfoil("naca0010"))
        ]
    )
    tail = asb.Wing(
        name="Tail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.25, 0, 0], chord=0.025, airfoil=asb.Airfoil("naca0010")),
            asb.WingXSec(xyz_le=[0.25, 0.04, 0], chord=0.025, airfoil=asb.Airfoil("naca0010"))
        ]
    )
    
    airplane = asb.Airplane(
        wings=[wing, tail],
        s_ref=wing.area(),
        c_ref=wing.mean_aerodynamic_chord(),
        b_ref=wing.span()
    )
    return airplane, wing, tail

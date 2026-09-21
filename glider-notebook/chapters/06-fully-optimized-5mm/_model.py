import aerosandbox as asb
import aerosandbox.numpy as np

def make_full_glider(c_root, taper, sweep, dihedral, h_span, h_chord, v_span, v_chord, boom_len, h_inc, cg_x):
    tip_le_x = 0.15 * np.tand(sweep)
    wing = asb.Wing(
        name="Wing", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root, airfoil=asb.Airfoil("naca4405")),
            asb.WingXSec(xyz_le=[tip_le_x, 0.15, 0.15*np.sind(dihedral)], chord=c_root * taper, airfoil=asb.Airfoil("naca4405"))
        ]
    )
    htail = asb.Wing(
        name="H-tail", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[boom_len, 0, 0], chord=h_chord, twist=h_inc, airfoil=asb.Airfoil("naca0005")),
            asb.WingXSec(xyz_le=[boom_len, h_span/2, 0], chord=h_chord, twist=h_inc, airfoil=asb.Airfoil("naca0005"))
        ]
    )
    vtail = asb.Wing(
        name="V-tail", symmetric=False,
        xsecs=[
            asb.WingXSec(xyz_le=[boom_len, 0, 0], chord=v_chord, airfoil=asb.Airfoil("naca0005")),
            asb.WingXSec(xyz_le=[boom_len, 0, v_span], chord=v_chord, airfoil=asb.Airfoil("naca0005"))
        ]
    )
    fuse = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(xyz_c=[-0.02, 0, 0], width=0.010, height=0.015, shape=4),
            asb.FuselageXSec(xyz_c=[boom_len+0.03, 0, 0], width=0.010, height=0.015, shape=4)
        ]
    )
    return asb.Airplane(name="Glider", xyz_ref=[cg_x, 0, 0], wings=[wing, htail, vtail], fuselages=[fuse])

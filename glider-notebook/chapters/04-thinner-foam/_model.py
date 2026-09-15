import aerosandbox as asb

def make_glider_3mm(c_root, taper, cg_x):
    # Tip LE x such that quarter chord x is constant
    tip_le_x = 0.25 * c_root * (1 - taper)
    
    wing = asb.Wing(
        name="Wing", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root, airfoil=asb.Airfoil("naca4403")),
            asb.WingXSec(xyz_le=[tip_le_x, 0.15, 0], chord=c_root * taper, airfoil=asb.Airfoil("naca4403"))
        ]
    )
    htail = asb.Wing(
        name="H-tail", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.15, 0, 0], chord=0.03, airfoil=asb.Airfoil("naca0003")),
            asb.WingXSec(xyz_le=[0.15, 0.05, 0], chord=0.03, airfoil=asb.Airfoil("naca0003"))
        ]
    )
    vtail = asb.Wing(
        name="V-tail", symmetric=False,
        xsecs=[
            asb.WingXSec(xyz_le=[0.15, 0, 0], chord=0.03, airfoil=asb.Airfoil("naca0003")),
            asb.WingXSec(xyz_le=[0.15, 0, 0.05], chord=0.03, airfoil=asb.Airfoil("naca0003"))
        ]
    )
    fuse = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(xyz_c=[-0.02, 0, 0], width=0.006, height=0.015, shape=4),
            asb.FuselageXSec(xyz_c=[0.18, 0, 0], width=0.006, height=0.015, shape=4)
        ]
    )
    return asb.Airplane(name="Glider", xyz_ref=[cg_x, 0, 0], wings=[wing, htail, vtail], fuselages=[fuse])

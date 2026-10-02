##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Mass and Reference Parameters

MASS_AUW = 0.254  # kg, all-up weight (222 g base + 32 g second wing, spar, struts)
MASS_DRY = 0.188  # kg, dry weight (156 g base + 32 g second wing)
CG_X = 0.025      # m, 25 mm aft of wing root leading edge


##### Geometry

# Biplane Wing Cellule: equal total area to monoplane (0.0685 m2)
# Scaled span 440 mm, panel AR 5.7, gap 95 mm, 0 deg dihedral
b_wing = 0.440
gap_wing = 0.095
s_total_wing = 0.068485  # matches monoplane total wing area
taper_wing = 0.087 / 0.133
c_root_wing = (s_total_wing / 2) / (b_wing / 2 * (1 + taper_wing))
c_tip_wing = c_root_wing * taper_wing
sweep_le_deg = 5.0   # LE sweep matching P-51 outline
x_tip_le = (b_wing / 2) * np.tan(np.radians(sweep_le_deg))

wing_lower = asb.Wing(
    name="Lower Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[0.0, 0.0, 0.0],
            chord=c_root_wing,
            airfoil=asb.Airfoil("naca2404"),
        ),
        asb.WingXSec(
            xyz_le=[x_tip_le, b_wing / 2, 0.0],
            chord=c_tip_wing,
            airfoil=asb.Airfoil("naca2404"),
        ),
    ],
)

wing_upper = asb.Wing(
    name="Upper Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[0.0, 0.0, gap_wing],
            chord=c_root_wing,
            airfoil=asb.Airfoil("naca2404"),
        ),
        asb.WingXSec(
            xyz_le=[x_tip_le, b_wing / 2, gap_wing],
            chord=c_tip_wing,
            airfoil=asb.Airfoil("naca2404"),
        ),
    ],
)

# Horizontal Stabilizer: span 213 mm, area 16 in2 (0.01032 m2)
# User-specified tail moment arm: 265 mm (quarter-chord to quarter-chord)
b_htail = 0.213
c_root_htail = 0.060
c_tip_htail = 0.037
x_c4_wing = c_root_wing * 0.25
tail_arm = 0.265  # m, quarter-chord to quarter-chord
x_c4_htail = x_c4_wing + tail_arm
x_htail_le = x_c4_htail - c_root_htail * 0.25  # 0.28325 m
sweep_htail_deg = 8.0
x_tip_htail_le = (b_htail / 2) * np.tan(np.radians(sweep_htail_deg))

htail = asb.Wing(
    name="Horizontal Tail",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[x_htail_le, 0.0, 0.02],
            chord=c_root_htail,
            airfoil=asb.Airfoil("naca0008"),
        ),
        asb.WingXSec(
            xyz_le=[x_htail_le + x_tip_htail_le, b_htail / 2, 0.02],
            chord=c_tip_htail,
            airfoil=asb.Airfoil("naca0008"),
        ),
    ],
)

# Vertical Stabilizer: assumed area 6.6 in2 (0.00427 m2)
b_vtail = 0.088
c_root_vtail = 0.065
c_tip_vtail = 0.032
x_vtail_le = x_htail_le - 0.005
sweep_vtail_deg = 20.0
x_tip_vtail_le = b_vtail * np.tan(np.radians(sweep_vtail_deg))

vtail = asb.Wing(
    name="Vertical Tail",
    symmetric=False,
    xsecs=[
        asb.WingXSec(
            xyz_le=[x_vtail_le, 0.0, 0.02],
            chord=c_root_vtail,
            airfoil=asb.Airfoil("naca0008"),
        ),
        asb.WingXSec(
            xyz_le=[x_vtail_le + x_tip_vtail_le, 0.0, 0.02 + b_vtail],
            chord=c_tip_vtail,
            airfoil=asb.Airfoil("naca0008"),
        ),
    ],
)

# Fuselage: 482 mm total length, 8 cross-sections
fuse = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[-0.100, 0.0, 0.000], width=0.020, height=0.020, shape=4),
        asb.FuselageXSec(xyz_c=[-0.070, 0.0, 0.000], width=0.045, height=0.055, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.000, 0.0, 0.010], width=0.048, height=0.075, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.060, 0.0, 0.020], width=0.048, height=0.085, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.150, 0.0, 0.010], width=0.045, height=0.080, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.250, 0.0, 0.010], width=0.035, height=0.060, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.350, 0.0, 0.015], width=0.020, height=0.035, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.382, 0.0, 0.020], width=0.010, height=0.025, shape=4),
    ],
)


##### Vehicle Assembly

airplane = asb.Airplane(
    name="FT Mighty Mini Mustang Biplane",
    xyz_ref=[CG_X, 0.0, 0.0],
    wings=[wing_lower, wing_upper, htail, vtail],
    fuselages=[fuse],
    s_ref=s_total_wing,
    c_ref=wing_lower.mean_aerodynamic_chord(),
    b_ref=b_wing,
)


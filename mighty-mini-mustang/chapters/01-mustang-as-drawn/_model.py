##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Material and Sheet Properties
# Flite Test Maker Foam: 4.7 mm (~3/16 in) XPS foam core with water-resistant paper.
# Standard sheet: 20 in x 30 in (0.508 m x 0.762 m) = 0.3871 m^2 (600 in^2).
# Standard Maker Foam sheet weighs ~135 g (0.135 kg).
t_foam = 0.0047       # m, sheet thickness
sheet_w = 0.508       # m (20 in)
sheet_l = 0.762       # m (30 in)
sheet_area = sheet_w * sheet_l  # 0.3871 m^2
sheet_mass = 0.135    # kg (135 g)
sigma_foam = sheet_mass / sheet_area  # ~0.3487 kg/m^2 (348.7 g/m^2)

##### Geometry Parameters
# FT Mighty Mini Mustang MKR2 plan specifications
b_w = 0.622           # m, span tip-to-tip (24.5 in)
S_w_spec = 0.0742     # m^2, wing area (115 in^2)
c_root_w = 0.140      # m, wing root chord
c_tip_w = 0.0986      # m, wing tip chord
dihedral_w = 3.0      # deg, dihedral angle per wing half

x_le_w = 0.120        # m, wing root LE station aft of fuselage nose
z_w = 0.0             # m, wing root plane
x_cg_spec = x_le_w + 0.025  # m, CG station (25 mm aft of wing LE)

# Projected span and tip coordinates under dihedral
y_tip_w = (b_w / 2) * np.cosd(dihedral_w)
z_tip_w = (b_w / 2) * np.sind(dihedral_w)

# Airfoil: thin symmetric section (NACA 0006) as stand-in for flat plate foam
airfoil = asb.Airfoil("naca0006")

# Wing
wing = asb.Wing(
    name="Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[x_le_w, 0, z_w], chord=c_root_w, airfoil=airfoil),
        asb.WingXSec(xyz_le=[x_le_w + 0.015, y_tip_w, z_tip_w], chord=c_tip_w, airfoil=airfoil),
    ]
)

# Horizontal tail
b_h = 0.240           # m, stabilizer span
c_root_h = 0.070      # m, root chord
c_tip_h = 0.050       # m, tip chord
x_le_h = 0.430        # m, LE station
z_h = 0.020           # m, stabilizer height

htail = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[x_le_h, 0, z_h], chord=c_root_h, airfoil=airfoil),
        asb.WingXSec(xyz_le=[x_le_h + 0.010, b_h / 2, z_h], chord=c_tip_h, airfoil=airfoil),
    ]
)

# Vertical tail
b_v = 0.120           # m, fin height
c_root_v = 0.080      # m, root chord
c_tip_v = 0.040       # m, tip chord
x_le_v = 0.410        # m, fin LE station
z_root_v = 0.020      # m, fin root height

vtail = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=False,
    xsecs=[
        asb.WingXSec(xyz_le=[x_le_v, 0, z_root_v], chord=c_root_v, airfoil=airfoil),
        asb.WingXSec(xyz_le=[x_le_v + 0.030, 0, z_root_v + b_v], chord=c_tip_v, airfoil=airfoil),
    ]
)

# Fuselage
fuse = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.000, 0, 0.000], width=0.038, height=0.038, shape=4.0),
        asb.FuselageXSec(xyz_c=[0.060, 0, 0.005], width=0.046, height=0.055, shape=4.0),
        asb.FuselageXSec(xyz_c=[0.150, 0, 0.010], width=0.048, height=0.070, shape=4.0),
        asb.FuselageXSec(xyz_c=[0.260, 0, 0.012], width=0.045, height=0.068, shape=4.0),
        asb.FuselageXSec(xyz_c=[0.380, 0, 0.015], width=0.030, height=0.040, shape=4.0),
        asb.FuselageXSec(xyz_c=[0.485, 0, 0.018], width=0.015, height=0.020, shape=4.0),
    ]
)

# Reference surface areas of cut foam parts from FT plan sheet
S_wing_planform = wing.area()        # 0.0742 m^2
S_htail_planform = htail.area()      # 0.0144 m^2
S_vtail_planform = vtail.area()      # 0.0072 m^2
S_fuse_shell = 0.0873                # m^2, 4-sided fuselage box
S_turtle_canopy = 0.0220             # m^2, canopy hatch and curved turtledeck
S_belly_scoop = 0.0150               # m^2, radiator scoop
S_formers_doublers = 0.0100          # m^2, internal formers and doublers
S_power_pod = 0.0200                 # m^2, removable mini power pod

# Total developed cut foam area
area_foam_flat = (S_wing_planform + S_htail_planform + S_vtail_planform +
                  S_fuse_shell + S_turtle_canopy + S_belly_scoop +
                  S_formers_doublers + S_power_pod)

# Folded-airfoil wing uses top skin + bottom skin wrap + fold spar (~1.8x S_w)
area_foam_folded = (1.8 * S_wing_planform + S_htail_planform + S_vtail_planform +
                    S_fuse_shell + S_turtle_canopy + S_belly_scoop +
                    S_formers_doublers + S_power_pod)


def build_airplane():
    """Build the FT Mighty Mini Mustang MKR2 Airplane model."""
    return asb.Airplane(
        name="FT Mighty Mini Mustang MKR2",
        wings=[wing, htail, vtail],
        fuselages=[fuse],
        s_ref=wing.area(),
        c_ref=wing.mean_aerodynamic_chord(),
        b_ref=b_w,
        xyz_ref=[x_cg_spec, 0, 0],
    )


airplane = build_airplane()


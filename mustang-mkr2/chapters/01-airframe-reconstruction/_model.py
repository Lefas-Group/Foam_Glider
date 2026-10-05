##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Wings

wing_airfoil = asb.Airfoil("clarky").scale(scale_y=0.05 / asb.Airfoil("clarky").max_thickness())

main_wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[0.117, 0.0, -0.015],
            chord=0.150,
            airfoil=wing_airfoil,
        ),
        asb.WingXSec(
            xyz_le=[0.117, 0.311, 0.012],
            chord=0.088,
            airfoil=wing_airfoil,
        ),
    ],
)

h_stab = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[0.368, 0.0, 0.010],
            chord=0.076,
            airfoil=asb.Airfoil("naca0008"),
        ),
        asb.WingXSec(
            xyz_le=[0.380, 0.113, 0.010],
            chord=0.052,
            airfoil=asb.Airfoil("naca0008"),
        ),
    ],
)

v_stab = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=False,
    xsecs=[
        asb.WingXSec(
            xyz_le=[0.346, 0.0, 0.010],
            chord=0.136,
            airfoil=asb.Airfoil("naca0008"),
        ),
        asb.WingXSec(
            xyz_le=[0.400, 0.0, 0.128],
            chord=0.065,
            airfoil=asb.Airfoil("naca0008"),
        ),
    ],
)


##### Fuselage

# SUPERELLIPSE EXPONENT. 2.0 is a true ellipse and 2.5 is barely off one, which
# is what the first reconstruction used -- so the model lofted a smooth pod
# where the real aircraft is a FOLDED BOX. Plan part 01 is a flat fold-out:
# two mirrored sides joined by a belly band, which becomes a flat-bottomed
# rectangular section once folded. Formers A, B and C are domed on top with a
# narrow stem, so only the turtle deck is curved.
#
# A superellipse cannot be flat-bottomed and round-topped at once, so 4.0 is
# the compromise -- a rounded rectangle, which is what the assembled section
# actually is once the turtle deck is on.
SHAPE_BOX = 4.0

fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.000, 0.0, 0.000], width=0.038, height=0.032, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.030, 0.0, 0.002], width=0.040, height=0.045, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.060, 0.0, 0.005], width=0.041, height=0.052, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.117, 0.0, 0.005], width=0.041, height=0.058, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.180, 0.0, 0.010], width=0.041, height=0.068, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.242, 0.0, 0.012], width=0.041, height=0.075, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.300, 0.0, 0.010], width=0.038, height=0.064, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.360, 0.0, 0.008], width=0.028, height=0.045, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.420, 0.0, 0.005], width=0.018, height=0.032, shape=SHAPE_BOX),
        asb.FuselageXSec(xyz_c=[0.468, 0.0, 0.002], width=0.012, height=0.026, shape=SHAPE_BOX),
    ],
)


# THE POWER POD -- plan part 00, and it was missing entirely. It appeared in
# the mass breakdown as 6 g and nowhere in the geometry, yet it is the box
# protruding below the nose in every photograph of this aircraft: the motor
# mounts on its firewall and the battery slides into it.
#
# MEASURED off tile 1 at 100 dpi with ndimage: the flat pattern is 83.3 x
# 65.3 mm with two fold bands, so the folded box is about 28 mm square in
# section and 65 mm long -- the standard FT Mini pod, 1.1 in square.
#
# A SECOND `Fuselage`, because `Airplane` takes a list of them and a single
# loft cannot carry a protrusion. It is slung under the nose, its top inside
# the fuselage and its bottom standing proud, which is what the photograph
# shows and what gives the nose its squared-off underside.
POD_W, POD_H, POD_L = 0.028, 0.028, 0.065
POD_Z = -0.026        # section centre, below the fuselage line

power_pod = asb.Fuselage(
    name="Power Pod",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.006, 0.0, POD_Z],
                         width=POD_W, height=POD_H, shape=6.0),
        asb.FuselageXSec(xyz_c=[0.006 + POD_L, 0.0, POD_Z],
                         width=POD_W, height=POD_H, shape=6.0),
    ],
)


##### Mass Properties

dry_components = {
    "motor": asb.MassProperties(mass=0.028, x_cg=0.012),
    "prop": asb.MassProperties(mass=0.005, x_cg=-0.005),
    "firewall": asb.MassProperties(mass=0.003, x_cg=0.015),
    "power_pod": asb.MassProperties(mass=0.006, x_cg=0.065),
    "esc": asb.MassProperties(mass=0.012, x_cg=0.055),
    "receiver": asb.MassProperties(mass=0.003, x_cg=0.090),
    "servos": asb.MassProperties(mass=0.015, x_cg=0.220),
    "wing_structure": asb.MassProperties(mass=0.046, x_cg=0.158),
    "fuselage_structure": asb.MassProperties(mass=0.031, x_cg=0.215),
    "tail_structure": asb.MassProperties(mass=0.007, x_cg=0.405),
}

dry_mass_props = sum(dry_components.values())

battery_props = asb.MassProperties(
    mass=0.066,
    x_cg=0.1482,
)

mass_props = dry_mass_props + battery_props


##### Airplane Assembly

airplane = asb.Airplane(
    name="FT Mighty Mini Mustang MKR2",
    xyz_ref=[mass_props.x_cg, mass_props.y_cg, mass_props.z_cg],
    wings=[main_wing, h_stab, v_stab],
    fuselages=[fuselage, power_pod],
)

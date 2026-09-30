##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Airfoils

af_root = asb.Airfoil("hq17")
af_mid = asb.Airfoil("hq2512")
af_tip = asb.Airfoil("hq2195")
af_tail = asb.Airfoil("hq010")


##### Box-Wing Geometry

# Total wing area: 11.39 m^2 split equally across forward and aft wings (5.695 m^2 each)
# Span: 18.0 m (semi-span 9.0 m)
# Height-to-span ratio h/b = 0.15 -> vertical separation h_box = 2.70 m
b_span = 18.0
hb_ratio = 0.15
h_box = hb_ratio * b_span  # 2.70 m
area_split = 0.5

wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589])
wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]

c_fwd = wing_chords * area_split
c_aft = wing_chords * (1.0 - area_split)
rel_xs = wing_xs_le - wing_xs_le[0]

# Forward wing at fuselage level z = 0.0 m, x = 2.30 m
xsecs_fwd = [
    asb.WingXSec(
        xyz_le=[rel_xs[i], wing_ys[i], 0.0],
        chord=c_fwd[i],
        twist=wing_twists[i],
        airfoil=wing_airfoils[i],
    )
    for i in range(len(wing_ys))
]

forward_wing = asb.Wing(
    name="Forward Wing",
    symmetric=True,
    xsecs=xsecs_fwd,
).translate([2.30, 0.0, 0.0])

# Aft wing at elevated level z = 2.70 m, x = 6.00 m
xsecs_aft = [
    asb.WingXSec(
        xyz_le=[rel_xs[i], wing_ys[i], 0.0],
        chord=c_aft[i],
        twist=wing_twists[i],
        airfoil=wing_airfoils[i],
    )
    for i in range(len(wing_ys))
]

aft_wing = asb.Wing(
    name="Aft Wing",
    symmetric=True,
    xsecs=xsecs_aft,
).translate([6.00, 0.0, h_box])

# Vertical tip endplate joining forward and aft wingtips
tip_endplate = asb.Wing(
    name="Tip Endplate",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[2.30 + rel_xs[-1], wing_ys[-1], 0.0],
            chord=c_fwd[-1],
            airfoil=af_tail,
        ),
        asb.WingXSec(
            xyz_le=[6.00 + rel_xs[-1], wing_ys[-1], h_box],
            chord=c_aft[-1],
            airfoil=af_tail,
        ),
    ],
)


##### Vertical Stabilizer

# Swept vertical fin with rudder
xsecs_vtail = [
    asb.WingXSec(xyz_le=[5.85, 0.0, -0.05], chord=0.85, airfoil=af_tail),
    asb.WingXSec(xyz_le=[6.38, 0.0, 1.25], chord=0.45, airfoil=af_tail),
]

vtail = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=False,
    xsecs=xsecs_vtail,
)


##### Fuselage

# 6.81 m fuselage length (Discus-2b/2c cockpit and slender tailboom)
fuse_xsecs = [
    asb.FuselageXSec(xyz_c=[0.0, 0.0, 0.0], width=0.02, height=0.02),
    asb.FuselageXSec(xyz_c=[0.5, 0.0, 0.02], width=0.45, height=0.55),
    asb.FuselageXSec(xyz_c=[1.1, 0.0, 0.05], width=0.62, height=0.78),
    asb.FuselageXSec(xyz_c=[1.8, 0.0, 0.04], width=0.60, height=0.75),
    asb.FuselageXSec(xyz_c=[2.4, 0.0, 0.00], width=0.50, height=0.65),
    asb.FuselageXSec(xyz_c=[3.2, 0.0, -0.02], width=0.36, height=0.48),
    asb.FuselageXSec(xyz_c=[4.5, 0.0, -0.04], width=0.20, height=0.28),
    asb.FuselageXSec(xyz_c=[5.8, 0.0, -0.05], width=0.14, height=0.22),
    asb.FuselageXSec(xyz_c=[6.81, 0.0, -0.05], width=0.04, height=0.15),
]

fuse = asb.Fuselage(name="Fuselage", xsecs=fuse_xsecs)


##### Mass Properties

# Empty mass breakdown: 337 kg total
empty_mass_props = asb.MassProperties(
    mass=337.0,
    x_cg=2.832,
    y_cg=0.0,
    z_cg=0.097,
    Ixx=1760.5,
    Iyy=189.7,
    Izz=1934.2,
)


def mass_properties(
    pilot_mass: float = 80.0, water_ballast_mass: float = 0.0
) -> asb.MassProperties:
    """Compute all-up mass properties for a given pilot and water ballast load."""
    props = empty_mass_props
    if pilot_mass > 0:
        props = props + asb.MassProperties(
            mass=pilot_mass, x_cg=1.75, y_cg=0.0, z_cg=0.0
        )
    if water_ballast_mass > 0:
        props = props + asb.MassProperties(
            mass=water_ballast_mass, x_cg=2.50, y_cg=0.0, z_cg=0.15
        )
    return props


flight_mass_props = mass_properties(pilot_mass=80.0)


##### Airplane

airplane = asb.Airplane(
    name="Discus-2c-BoxWing",
    xyz_ref=[flight_mass_props.x_cg, flight_mass_props.y_cg, flight_mass_props.z_cg],
    wings=[forward_wing, aft_wing, tip_endplate, vtail],
    fuselages=[fuse],
    s_ref=11.39,
    c_ref=float(forward_wing.mean_aerodynamic_chord()),
    b_ref=b_span,
)

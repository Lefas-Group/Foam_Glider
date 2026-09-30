##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Airfoils

af_root = asb.Airfoil("hq17")
af_mid = asb.Airfoil("hq2512")
af_tip = asb.Airfoil("hq2195")
af_tail = asb.Airfoil("hq010")


##### Tandem Wings

# Total wing area: 11.39 m^2 split equally across two tandem wings (5.695 m^2 each)
# Individual semi-span: 9.0 / sqrt(2) = 6.364 m (12.728 m full span)
# Preserves chord lengths and individual aspect ratio AR = 28.45 per wing
scale_factor = 1.0 / np.sqrt(2.0)
b_ref = 18.0 * scale_factor  # 12.728 m

wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0]) * scale_factor
wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589]) * scale_factor
wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530]) * scale_factor
wing_dihedral_deg = 3.0
wing_zs_le = wing_ys * np.tand(wing_dihedral_deg)
wing_zs_le[-1] = wing_zs_le[-2] + 0.40 * scale_factor  # scaled winglet tip upturn

wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]

# Fore wing positioned ahead of CG
x_fwd_root = 1.00
z_fwd_root = -0.10
xsecs_fore = [
    asb.WingXSec(
        xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
        chord=wing_chords[i],
        twist=wing_twists[i],
        airfoil=wing_airfoils[i],
    )
    for i in range(len(wing_ys))
]

fore_wing = asb.Wing(
    name="Fore Wing",
    symmetric=True,
    xsecs=xsecs_fore,
).translate([x_fwd_root, 0.0, z_fwd_root])

# Aft wing positioned behind CG, elevated on pylon to clear fore-wing downwash
# Decalage: -0.98 deg relative incidence for trimmed cruise and pitch stability
x_aft_root = 4.30
z_aft_root = 0.35
decalage_aft_deg = -0.98
xsecs_aft = [
    asb.WingXSec(
        xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
        chord=wing_chords[i],
        twist=wing_twists[i] + decalage_aft_deg,
        airfoil=wing_airfoils[i],
    )
    for i in range(len(wing_ys))
]

aft_wing = asb.Wing(
    name="Aft Wing",
    symmetric=True,
    xsecs=xsecs_aft,
).translate([x_aft_root, 0.0, z_aft_root])


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
    name="Discus-2c-Tandem",
    xyz_ref=[flight_mass_props.x_cg, flight_mass_props.y_cg, flight_mass_props.z_cg],
    wings=[fore_wing, aft_wing, vtail],
    fuselages=[fuse],
    s_ref=11.39,
    c_ref=float(fore_wing.mean_aerodynamic_chord()),
    b_ref=b_ref,
)


def get_tandem_airplane(
    decalage_aft: float = -0.98,
    x_fwd: float = 1.00,
    x_aft: float = 4.30,
    z_fwd: float = -0.10,
    z_aft: float = 0.35,
) -> asb.Airplane:
    """Return a tandem-wing configuration with specified positioning and aft decalage."""
    wf = asb.Wing(
        name="Fore Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
                chord=wing_chords[i],
                twist=wing_twists[i],
                airfoil=wing_airfoils[i],
            )
            for i in range(len(wing_ys))
        ],
    ).translate([x_fwd, 0.0, z_fwd])

    wa = asb.Wing(
        name="Aft Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
                chord=wing_chords[i],
                twist=wing_twists[i] + decalage_aft,
                airfoil=wing_airfoils[i],
            )
            for i in range(len(wing_ys))
        ],
    ).translate([x_aft, 0.0, z_aft])

    return asb.Airplane(
        name="Discus-2c-Tandem",
        xyz_ref=[flight_mass_props.x_cg, flight_mass_props.y_cg, flight_mass_props.z_cg],
        wings=[wf, wa, vtail],
        fuselages=[fuse],
        s_ref=11.39,
        c_ref=float(wf.mean_aerodynamic_chord()),
        b_ref=b_ref,
    )

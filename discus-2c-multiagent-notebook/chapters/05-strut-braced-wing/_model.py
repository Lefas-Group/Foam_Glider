##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Airfoils

af_root = asb.Airfoil("hq17")
af_mid = asb.Airfoil("hq2512")
af_tip = asb.Airfoil("hq2195")
af_tail = asb.Airfoil("hq010")


##### Main Wing

# Six spanwise stations reproducing the Discus crescent/multi-taper planform
# Semi-span: 9.0 m (18.0 m full span)
# Planform area: calibrated to hit 11.39 m^2 projected area
wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589])
wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
wing_dihedral_deg = 3.0
wing_zs_le = wing_ys * np.tand(wing_dihedral_deg)
wing_zs_le[-1] = wing_zs_le[-2] + 0.40  # winglet tip upturn

wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]

xsecs_wing = [
    asb.WingXSec(
        xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
        chord=wing_chords[i],
        twist=wing_twists[i],
        airfoil=wing_airfoils[i],
    )
    for i in range(len(wing_ys))
]

main_wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=xsecs_wing,
).translate([2.30, 0.0, 0.15])


##### Horizontal Stabilizer

# T-tail mounted atop the vertical fin at z = 1.25 m
xsecs_htail = [
    asb.WingXSec(xyz_le=[6.35, 0.0, 1.25], chord=0.48, twist=-1.0, airfoil=af_tail),
    asb.WingXSec(xyz_le=[6.42, 1.2, 1.25], chord=0.32, twist=-1.0, airfoil=af_tail),
]

htail = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=xsecs_htail,
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


##### Strut

af_strut = asb.Airfoil("hq010")
strut_chord = 0.12  # 120 mm chord
strut_attach_frac = 0.50  # 50% semi-span

# Fuselage attachment (lower fuselage frame at x = 2.40 m, z = -0.30 m)
x_fuse_strut = 2.40
y_fuse_strut = 0.20
z_fuse_strut = -0.30

# Wing attachment (50% semi-span station, y = 4.5 m)
y_wing_strut = 4.50
x_wing_strut = 2.30 + 0.045 + 0.35 * 0.6653
z_wing_strut = 0.15 + y_wing_strut * np.tand(wing_dihedral_deg)

xsecs_strut = [
    asb.WingXSec(
        xyz_le=[x_fuse_strut - 0.25 * strut_chord, y_fuse_strut, z_fuse_strut],
        chord=strut_chord,
        twist=0.0,
        airfoil=af_strut,
    ),
    asb.WingXSec(
        xyz_le=[x_wing_strut - 0.25 * strut_chord, y_wing_strut, z_wing_strut],
        chord=strut_chord,
        twist=0.0,
        airfoil=af_strut,
    ),
]

strut = asb.Wing(
    name="Strut",
    symmetric=True,
    xsecs=xsecs_strut,
)


##### Airplane

airplane = asb.Airplane(
    name="Discus-2c-SBW",
    xyz_ref=[flight_mass_props.x_cg, flight_mass_props.y_cg, flight_mass_props.z_cg],
    wings=[main_wing, htail, vtail, strut],
    fuselages=[fuse],
    s_ref=11.39,
    c_ref=float(main_wing.mean_aerodynamic_chord()),
    b_ref=18.0,
)


def get_strut_braced_airplane(
    ar_target: float = 28.446,
    strut_attach_frac: float = 0.50,
    base_ar: float = 28.446,
    base_s_ref: float = 11.39,
) -> asb.Airplane:
    """Scale the strut-braced wing aspect ratio at fixed wing area while preserving planform taper and twist."""
    import numpy as _np

    k = float(_np.sqrt(ar_target / base_ar))
    wing_orig = main_wing

    xs_le = _np.array([xsec.xyz_le[0] for xsec in wing_orig.xsecs])
    ys_le = _np.array([xsec.xyz_le[1] for xsec in wing_orig.xsecs])
    chords = _np.array([xsec.chord for xsec in wing_orig.xsecs])
    twists = [xsec.twist for xsec in wing_orig.xsecs]
    airfoils = [xsec.airfoil for xsec in wing_orig.xsecs]

    scaled_ys = ys_le * k
    scaled_chords = chords / k

    x_c4 = xs_le + 0.25 * chords
    x_c4_scaled = x_c4[0] + (x_c4 - x_c4[0]) * k
    scaled_xs = x_c4_scaled - 0.25 * scaled_chords

    scaled_zs = 0.15 + scaled_ys * _np.tan(_np.radians(3.0))
    scaled_zs[-1] = scaled_zs[-2] + 0.40

    xsecs_scaled = [
        asb.WingXSec(
            xyz_le=[scaled_xs[i], scaled_ys[i], scaled_zs[i]],
            chord=scaled_chords[i],
            twist=twists[i],
            airfoil=airfoils[i],
        )
        for i in range(len(scaled_ys))
    ]

    wing_scaled = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=xsecs_scaled,
    )

    b_semi = float(18.0 * k / 2)
    y_s = strut_attach_frac * b_semi
    x_le_s = float(_np.interp(y_s, scaled_ys, scaled_xs))
    c_s = float(_np.interp(y_s, scaled_ys, scaled_chords))
    x_attach_wing = x_le_s + 0.35 * c_s
    z_attach_wing = 0.15 + y_s * _np.tan(_np.radians(3.0))

    xsecs_s = [
        asb.WingXSec(
            xyz_le=[x_fuse_strut - 0.25 * strut_chord, y_fuse_strut, z_fuse_strut],
            chord=strut_chord,
            twist=0.0,
            airfoil=af_strut,
        ),
        asb.WingXSec(
            xyz_le=[x_attach_wing - 0.25 * strut_chord, y_s, z_attach_wing],
            chord=strut_chord,
            twist=0.0,
            airfoil=af_strut,
        ),
    ]
    strut_scaled = asb.Wing(name="Strut", symmetric=True, xsecs=xsecs_s)

    return asb.Airplane(
        name=f"Discus-2c-SBW-AR{ar_target:.1f}",
        xyz_ref=airplane.xyz_ref,
        wings=[wing_scaled, htail, vtail, strut_scaled],
        fuselages=[fuse],
        s_ref=base_s_ref,
        c_ref=float(wing_scaled.mean_aerodynamic_chord()),
        b_ref=float(18.0 * k),
    )


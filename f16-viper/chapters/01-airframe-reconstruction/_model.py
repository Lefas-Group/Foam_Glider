##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Geometry Parameters

# Wing
wing_x_root = 0.45
wing_y_root = 0.07
wing_chord_root = 0.52
wing_x_break = 0.70
wing_y_break = 0.15
wing_chord_break = 0.27
wing_semi_span = 0.457
wing_x_tip = 0.93
wing_chord_tip = 0.10

# Stabilator (all-moving horizontal tail)
hstab_x_root = 1.08
hstab_y_root = 0.08
hstab_z_root = -0.01
hstab_chord_root = 0.21
hstab_x_tip = 1.18
hstab_y_tip = 0.26
hstab_z_tip = -0.04
hstab_chord_tip = 0.11

# Vertical stabilizer
vstab_x_fillet = 0.82
vstab_z_fillet = 0.05
vstab_chord_fillet = 0.42
vstab_x_root = 0.96
vstab_z_root = 0.08
vstab_chord_root = 0.28
vstab_x_tip = 1.14
vstab_z_tip = 0.26
vstab_chord_tip = 0.08

# Ventral fins
vfin_x_root = 1.04
vfin_y_root = 0.06
vfin_z_root = -0.05
vfin_chord_root = 0.18
vfin_x_tip = 1.10
vfin_y_tip = 0.08
vfin_z_tip = -0.10
vfin_chord_tip = 0.11

# Missile rails
rail_x = 0.89
rail_chord = 0.18
rail_half_height = 0.012

# Fuselage length
fuse_total_length = 1.295

# Airfoil
airfoil_flat = asb.Airfoil("naca0008")


##### Components

wing = asb.Wing(
    name="Wing",
    xsecs=[
        asb.WingXSec(
            xyz_le=[wing_x_root, 0.00, 0.0],
            chord=wing_chord_root,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[wing_x_root, wing_y_root, 0.0],
            chord=wing_chord_root,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[wing_x_break, wing_y_break, 0.0],
            chord=wing_chord_break,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[wing_x_tip, wing_semi_span, 0.0],
            chord=wing_chord_tip,
            airfoil=airfoil_flat,
        ),
    ],
    symmetric=True,
)

hstab = asb.Wing(
    name="Stabilators",
    xsecs=[
        asb.WingXSec(
            xyz_le=[hstab_x_root, hstab_y_root, hstab_z_root],
            chord=hstab_chord_root,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[hstab_x_tip, hstab_y_tip, hstab_z_tip],
            chord=hstab_chord_tip,
            airfoil=airfoil_flat,
        ),
    ],
    symmetric=True,
)

vstab = asb.Wing(
    name="Vertical Stabilizer",
    xsecs=[
        asb.WingXSec(
            xyz_le=[vstab_x_fillet, 0.0, vstab_z_fillet],
            chord=vstab_chord_fillet,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[vstab_x_root, 0.0, vstab_z_root],
            chord=vstab_chord_root,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[vstab_x_tip, 0.0, vstab_z_tip],
            chord=vstab_chord_tip,
            airfoil=airfoil_flat,
        ),
    ],
    symmetric=False,
)

ventral_fins = asb.Wing(
    name="Ventral Fins",
    xsecs=[
        asb.WingXSec(
            xyz_le=[vfin_x_root, vfin_y_root, vfin_z_root],
            chord=vfin_chord_root,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[vfin_x_tip, vfin_y_tip, vfin_z_tip],
            chord=vfin_chord_tip,
            airfoil=airfoil_flat,
        ),
    ],
    symmetric=True,
)

missile_rails = asb.Wing(
    name="Missile Rails",
    xsecs=[
        asb.WingXSec(
            xyz_le=[rail_x, wing_semi_span, -rail_half_height],
            chord=rail_chord,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[rail_x, wing_semi_span,  rail_half_height],
            chord=rail_chord,
            airfoil=airfoil_flat,
        ),
    ],
    symmetric=True,
)

fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.00, 0, -0.015], radius=0.005),
        asb.FuselageXSec(xyz_c=[0.18, 0, -0.005], width=0.07, height=0.055),
        asb.FuselageXSec(xyz_c=[0.35, 0,  0.005], width=0.12, height=0.10),
        asb.FuselageXSec(xyz_c=[0.55, 0,  0.015], width=0.15, height=0.125),
        asb.FuselageXSec(xyz_c=[0.75, 0,  0.015], width=0.165, height=0.125),
        asb.FuselageXSec(xyz_c=[0.98, 0,  0.005], width=0.16, height=0.11),
        asb.FuselageXSec(xyz_c=[1.16, 0,  0.00], width=0.13, height=0.09),
        asb.FuselageXSec(xyz_c=[fuse_total_length, 0, 0.00], radius=0.045),
    ],
)

canopy = asb.Fuselage(
    name="Canopy",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.30, 0, 0.05], radius=0.01),
        asb.FuselageXSec(xyz_c=[0.45, 0, 0.08], width=0.10, height=0.07),
        asb.FuselageXSec(xyz_c=[0.60, 0, 0.07], width=0.09, height=0.05),
        asb.FuselageXSec(xyz_c=[0.70, 0, 0.04], radius=0.01),
    ],
)

intake = asb.Fuselage(
    name="Intake",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.44, 0, -0.045], width=0.09, height=0.055, shape=4),
        asb.FuselageXSec(xyz_c=[0.58, 0, -0.055], width=0.10, height=0.065, shape=4),
        asb.FuselageXSec(xyz_c=[0.72, 0, -0.035], width=0.11, height=0.045, shape=4),
    ],
)


##### Mass Properties

# Developed foam cut area derived from geometry (wetted skins + internal formers/spars/box)
skin_area = (
    wing.area("wetted")
    + hstab.area("wetted")
    + vstab.area("wetted")
    + ventral_fins.area("wetted")
    + fuselage.area_wetted()
    + canopy.area_wetted()
    + intake.area_wetted()
)
former_area = (
    sum(x.xsec_area() for x in fuselage.xsecs)
    + sum(x.xsec_area() for x in canopy.xsecs)
    + sum(x.xsec_area() for x in intake.xsecs)
)
spar_area = 2 * wing.span(include_centerline_distance=True) * 0.025 + 2 * hstab.span() * 0.015
internal_box_area = 0.55 * fuselage.area_wetted()
developed_cut_area = skin_area + former_area + spar_area + internal_box_area

foam_areal_density = 0.293  # Maker Foam 5 mm areal density (kg/m^2)
mass_foam = foam_areal_density * developed_cut_area
x_foam = 0.730
z_foam = 0.010

# Catalogue electronics and hardware masses
mass_edf = 0.220       # 70 mm 12-blade EDF with 2300 kV motor
x_edf = 0.850
z_edf = 0.000

mass_esc = 0.080       # SkyWalker 80 A ESC
x_esc = 0.550
z_esc = -0.020

mass_servos = 0.060    # 4x micro servos and linkages
x_servos = 0.820
z_servos = 0.010

mass_hardware = 0.150  # Plywood mounts, pushrods, control horns, glue
x_hardware = 0.650
z_hardware = 0.010

dry_mass_props = (
    asb.MassProperties(mass=mass_foam, x_cg=x_foam, y_cg=0, z_cg=z_foam)
    + asb.MassProperties(mass=mass_edf, x_cg=x_edf, y_cg=0, z_cg=z_edf)
    + asb.MassProperties(mass=mass_esc, x_cg=x_esc, y_cg=0, z_cg=z_esc)
    + asb.MassProperties(mass=mass_servos, x_cg=x_servos, y_cg=0, z_cg=z_servos)
    + asb.MassProperties(mass=mass_hardware, x_cg=x_hardware, y_cg=0, z_cg=z_hardware)
)

mass_dry = dry_mass_props.mass
x_cg_dry = dry_mass_props.x_cg
z_cg_dry = dry_mass_props.z_cg
cg_aft_le = x_cg_dry - wing_x_break


##### Aerodynamic Reference Values

wing_area = wing.area("planform")
wing_span = wing.span(include_centerline_distance=True)
wing_mac = wing.mean_aerodynamic_chord()
wing_ar = wing.aspect_ratio()
fuselage_length = fuselage.length()
wing_loading_dry = mass_dry / wing_area


##### Vehicle Assembly

airplane = asb.Airplane(
    name="FT Master Series F-16 Viper",
    xyz_ref=[x_cg_dry, 0, z_cg_dry],
    wings=[wing, hstab, vstab, ventral_fins, missile_rails],
    fuselages=[fuselage, canopy, intake],
    s_ref=wing_area,
    c_ref=wing_mac,
    b_ref=wing_span,
)

airplane_for_fit = airplane

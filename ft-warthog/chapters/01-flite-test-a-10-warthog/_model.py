##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Geometry Constants

# Wing (published span: 1537 mm / 60.5 in)
wing_span = 1.537
wing_x_le = 0.36
wing_root_chord = 0.27
wing_break_y = 0.23
wing_break_x_le = 0.36
wing_break_chord = 0.27
wing_tip_x_le = 0.40
wing_tip_chord = 0.14
wing_dihedral_deg = 5.5
wing_tip_z = (wing_span / 2 - wing_break_y) * np.sin(np.radians(wing_dihedral_deg))

# Fuselage
fuse_nose_x = -0.092867
fuse_cockpit_x = 0.20
fuse_wing_x = 0.38
fuse_mid_x = 0.65
fuse_tail_x = 0.92
fuse_end_x = 1.08

fuse_nose_w = 0.06
fuse_nose_h = 0.06
fuse_cockpit_w = 0.13
fuse_cockpit_h = 0.16
fuse_mid_w = 0.15
fuse_mid_h = 0.14
fuse_tail_w = 0.10
fuse_tail_h = 0.09
fuse_end_w = 0.04
fuse_end_h = 0.03

# Nacelles (twin engines mounted on aft fuselage pylons)
nacelle_x_le = 0.62
nacelle_length = 0.23
nacelle_radius = 0.062
nacelle_y = 0.135
nacelle_z = 0.105

# Horizontal stabilizer
hstab_span = 0.49
hstab_x_le = 0.92
hstab_root_chord = 0.16
hstab_tip_chord = 0.14
hstab_z = 0.045

# Vertical stabilizers (twin fins at H-stab tips)
vstab_x_le = 0.90
vstab_chord = 0.16
vstab_z_bottom = -0.03
vstab_z_top = 0.18

# Stand-in airfoil for flat foam board
airfoil_flat = asb.Airfoil("naca0008")

##### Geometry Definition

wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[wing_x_le, 0, 0],
            chord=wing_root_chord,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[wing_break_x_le, wing_break_y, 0],
            chord=wing_break_chord,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[wing_tip_x_le, wing_span / 2, wing_tip_z],
            chord=wing_tip_chord,
            airfoil=airfoil_flat,
        ),
    ],
)

hstab = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[hstab_x_le, 0, hstab_z],
            chord=hstab_root_chord,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[hstab_x_le + 0.01, hstab_span / 2, hstab_z],
            chord=hstab_tip_chord,
            airfoil=airfoil_flat,
        ),
    ],
)

vstab = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[vstab_x_le + 0.03, hstab_span / 2, vstab_z_bottom],
            chord=vstab_chord * 0.85,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[vstab_x_le, hstab_span / 2, hstab_z],
            chord=vstab_chord,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[vstab_x_le + 0.02, hstab_span / 2, vstab_z_top],
            chord=vstab_chord * 0.8,
            airfoil=airfoil_flat,
        ),
    ],
)

pylon = asb.Wing(
    name="Nacelle Pylons",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[nacelle_x_le + 0.02, fuse_mid_w / 2, 0.02],
            chord=nacelle_length * 0.7,
            airfoil=airfoil_flat,
        ),
        asb.WingXSec(
            xyz_le=[nacelle_x_le + 0.02, nacelle_y, nacelle_z],
            chord=nacelle_length * 0.7,
            airfoil=airfoil_flat,
        ),
    ],
)

fuse_shape = 4  # rounded rectangular box for folded foam board

fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[fuse_nose_x, 0, 0],
            width=fuse_nose_w,
            height=fuse_nose_h,
            shape=fuse_shape,
        ),
        asb.FuselageXSec(
            xyz_c=[fuse_cockpit_x, 0, 0.03],
            width=fuse_cockpit_w,
            height=fuse_cockpit_h,
            shape=fuse_shape,
        ),
        asb.FuselageXSec(
            xyz_c=[fuse_wing_x, 0, 0.01],
            width=fuse_mid_w,
            height=fuse_mid_h,
            shape=fuse_shape,
        ),
        asb.FuselageXSec(
            xyz_c=[fuse_mid_x, 0, 0.01],
            width=fuse_mid_w,
            height=fuse_mid_h,
            shape=fuse_shape,
        ),
        asb.FuselageXSec(
            xyz_c=[fuse_tail_x, 0, 0.02],
            width=fuse_tail_w,
            height=fuse_tail_h,
            shape=fuse_shape,
        ),
        asb.FuselageXSec(
            xyz_c=[fuse_end_x, 0, 0.03],
            width=fuse_end_w,
            height=fuse_end_h,
            shape=fuse_shape,
        ),
    ],
)

nacelle_left = asb.Fuselage(
    name="Nacelle Left",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[nacelle_x_le, -nacelle_y, nacelle_z],
            radius=nacelle_radius * 0.95,
        ),
        asb.FuselageXSec(
            xyz_c=[nacelle_x_le + nacelle_length * 0.4, -nacelle_y, nacelle_z],
            radius=nacelle_radius,
        ),
        asb.FuselageXSec(
            xyz_c=[nacelle_x_le + nacelle_length, -nacelle_y, nacelle_z],
            radius=nacelle_radius * 0.85,
        ),
    ],
)

nacelle_right = asb.Fuselage(
    name="Nacelle Right",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[nacelle_x_le, nacelle_y, nacelle_z],
            radius=nacelle_radius * 0.95,
        ),
        asb.FuselageXSec(
            xyz_c=[nacelle_x_le + nacelle_length * 0.4, nacelle_y, nacelle_z],
            radius=nacelle_radius,
        ),
        asb.FuselageXSec(
            xyz_c=[nacelle_x_le + nacelle_length, nacelle_y, nacelle_z],
            radius=nacelle_radius * 0.85,
        ),
    ],
)

##### Mass Properties

foam_areal_density = 0.380  # kg/m^2 (Maker Foam ~300 g/m^2 plus glue, spars, tape)

m_wing = wing.area("wetted") * foam_areal_density
m_fuse = fuselage.area_wetted() * foam_areal_density
m_hstab = hstab.area("wetted") * foam_areal_density
m_vstab = vstab.area("wetted") * foam_areal_density
m_nacelles = (nacelle_left.area_wetted() + nacelle_right.area_wetted()) * foam_areal_density

m_motors = 0.140  # 2x 70 g Power Pack C motors
m_escs = 0.060    # 2x 30 g ESCs
m_servos = 0.036  # 4x 9 g micro servos
m_rx = 0.010      # 6-ch receiver
m_battery = 0.400 # 4S 3300 mAh LiPo (or twin 3S 2200 mAh)

battery_x = 0.051 # forward nose battery bay station

mass_props = sum([
    asb.MassProperties(mass=m_wing, x_cg=wing.aerodynamic_center(chord_fraction=0.45)[0], z_cg=0.01),
    asb.MassProperties(mass=m_fuse, x_cg=fuselage.x_centroid_projected(), z_cg=0.02),
    asb.MassProperties(mass=m_hstab, x_cg=hstab.aerodynamic_center(chord_fraction=0.45)[0], z_cg=hstab_z),
    asb.MassProperties(mass=m_vstab, x_cg=vstab.aerodynamic_center(chord_fraction=0.45)[0], z_cg=hstab_z),
    asb.MassProperties(mass=m_nacelles, x_cg=nacelle_left.x_centroid_projected(), z_cg=nacelle_z),
    asb.MassProperties(mass=m_motors, x_cg=nacelle_x_le + 0.02, z_cg=nacelle_z),
    asb.MassProperties(mass=m_escs, x_cg=nacelle_x_le, z_cg=nacelle_z),
    asb.MassProperties(mass=m_servos, x_cg=0.60, z_cg=0.02),
    asb.MassProperties(mass=m_rx, x_cg=0.25, z_cg=0.02),
    asb.MassProperties(mass=m_battery, x_cg=battery_x, z_cg=0.01),
])

airplane = asb.Airplane(
    name="Flite Test A-10 Warthog",
    xyz_ref=[mass_props.x_cg, 0, mass_props.z_cg],
    wings=[wing, hstab, vstab, pylon],
    fuselages=[fuselage, nacelle_left, nacelle_right],
)

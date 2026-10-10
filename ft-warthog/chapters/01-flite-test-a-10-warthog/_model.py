##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Geometry parameters

# Main wing (published span = 1537 mm = 1.537 m, fixed)
wing_span = 1.537
wing_x_le = 0.392176
wing_z = -0.02
wing_root_chord = 0.244874
wing_break_y = 0.26
wing_break_chord = 0.266465
wing_break_x_le = 0.0
wing_tip_chord = 0.16045
wing_tip_x_le = 0.05
wing_tip_z = 0.035

# Fuselage stations and cross-sections
fuse_x_0 = 0.00
fuse_w_0 = 0.04
fuse_h_0 = 0.04
fuse_z_0 = 0.00

fuse_x_1 = 0.12
fuse_w_1 = 0.10
fuse_h_1 = 0.09
fuse_z_1 = 0.00

fuse_x_2 = 0.248
fuse_w_2 = 0.12
fuse_h_2 = 0.13
fuse_z_2 = 0.02

fuse_x_3 = 0.38
fuse_w_3 = 0.13
fuse_h_3 = 0.16
fuse_z_3 = 0.03

fuse_x_4 = 0.55
fuse_w_4 = 0.13
fuse_h_4 = 0.14
fuse_z_4 = 0.02

fuse_x_5 = 0.75
fuse_w_5 = 0.11
fuse_h_5 = 0.12
fuse_z_5 = 0.01

fuse_x_6 = 0.95
fuse_w_6 = 0.07
fuse_h_6 = 0.08
fuse_z_6 = 0.01

fuse_x_7 = 1.15
fuse_w_7 = 0.03
fuse_h_7 = 0.04
fuse_z_7 = 0.02

# Horizontal stabilizer
htail_x_le = 1.00
htail_z = 0.03
htail_span = 0.48
htail_root_chord = 0.16
htail_tip_chord = 0.13
htail_tip_x_le = 1.03

# Twin vertical fins
vfin_y = 0.24
vfin_z_bottom = -0.04
vfin_span = 0.20
vfin_root_chord = 0.17
vfin_tip_chord = 0.13
vfin_x_le = 0.98
vfin_tip_x_le = 1.02

# Nacelles
nacelle_x_le = 0.65
nacelle_y = 0.13
nacelle_z = 0.08
nacelle_length = 0.26
nacelle_radius = 0.055

# Underwing pods
pod_x_le = 0.36
pod_y = 0.26
pod_z = -0.04
pod_length = 0.14
pod_width = 0.04
pod_height = 0.05

##### Airfoils
airfoil_wing = asb.Airfoil("naca0008")
airfoil_tail = asb.Airfoil("naca0008")

##### Wings

main_wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[wing_x_le, 0, wing_z],
            chord=wing_root_chord,
            airfoil=airfoil_wing,
        ),
        asb.WingXSec(
            xyz_le=[wing_x_le + wing_break_x_le, wing_break_y, wing_z],
            chord=wing_break_chord,
            airfoil=airfoil_wing,
        ),
        asb.WingXSec(
            xyz_le=[wing_x_le + wing_tip_x_le, wing_span / 2, wing_z + wing_tip_z],
            chord=wing_tip_chord,
            airfoil=airfoil_wing,
        ),
    ],
)

horizontal_stabilizer = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[htail_x_le, 0, htail_z],
            chord=htail_root_chord,
            airfoil=airfoil_tail,
        ),
        asb.WingXSec(
            xyz_le=[htail_tip_x_le, htail_span / 2, htail_z],
            chord=htail_tip_chord,
            airfoil=airfoil_tail,
        ),
    ],
)

vertical_fin_right = asb.Wing(
    name="Vertical Fin Right",
    symmetric=False,
    xsecs=[
        asb.WingXSec(
            xyz_le=[vfin_x_le, vfin_y, vfin_z_bottom],
            chord=vfin_root_chord,
            airfoil=airfoil_tail,
        ),
        asb.WingXSec(
            xyz_le=[vfin_tip_x_le, vfin_y, vfin_z_bottom + vfin_span],
            chord=vfin_tip_chord,
            airfoil=airfoil_tail,
        ),
    ],
)

vertical_fin_left = asb.Wing(
    name="Vertical Fin Left",
    symmetric=False,
    xsecs=[
        asb.WingXSec(
            xyz_le=[vfin_x_le, -vfin_y, vfin_z_bottom],
            chord=vfin_root_chord,
            airfoil=airfoil_tail,
        ),
        asb.WingXSec(
            xyz_le=[vfin_tip_x_le, -vfin_y, vfin_z_bottom + vfin_span],
            chord=vfin_tip_chord,
            airfoil=airfoil_tail,
        ),
    ],
)

##### Fuselages

fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[fuse_x_0, 0, fuse_z_0], width=fuse_w_0, height=fuse_h_0, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_1, 0, fuse_z_1], width=fuse_w_1, height=fuse_h_1, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_2, 0, fuse_z_2], width=fuse_w_2, height=fuse_h_2, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_3, 0, fuse_z_3], width=fuse_w_3, height=fuse_h_3, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_4, 0, fuse_z_4], width=fuse_w_4, height=fuse_h_4, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_5, 0, fuse_z_5], width=fuse_w_5, height=fuse_h_5, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_6, 0, fuse_z_6], width=fuse_w_6, height=fuse_h_6, shape=4),
        asb.FuselageXSec(xyz_c=[fuse_x_7, 0, fuse_z_7], width=fuse_w_7, height=fuse_h_7, shape=4),
    ],
)

nacelle_right = asb.Fuselage(
    name="Nacelle Right",
    xsecs=[
        asb.FuselageXSec(xyz_c=[nacelle_x_le, nacelle_y, nacelle_z], radius=nacelle_radius),
        asb.FuselageXSec(xyz_c=[nacelle_x_le + nacelle_length, nacelle_y, nacelle_z], radius=nacelle_radius),
    ],
)

nacelle_left = asb.Fuselage(
    name="Nacelle Left",
    xsecs=[
        asb.FuselageXSec(xyz_c=[nacelle_x_le, -nacelle_y, nacelle_z], radius=nacelle_radius),
        asb.FuselageXSec(xyz_c=[nacelle_x_le + nacelle_length, -nacelle_y, nacelle_z], radius=nacelle_radius),
    ],
)

pod_right = asb.Fuselage(
    name="Pod Right",
    xsecs=[
        asb.FuselageXSec(xyz_c=[pod_x_le, pod_y, pod_z], width=pod_width, height=pod_height, shape=4),
        asb.FuselageXSec(xyz_c=[pod_x_le + pod_length, pod_y, pod_z], width=pod_width, height=pod_height, shape=4),
    ],
)

pod_left = asb.Fuselage(
    name="Pod Left",
    xsecs=[
        asb.FuselageXSec(xyz_c=[pod_x_le, -pod_y, pod_z], width=pod_width, height=pod_height, shape=4),
        asb.FuselageXSec(xyz_c=[pod_x_le + pod_length, -pod_y, pod_z], width=pod_width, height=pod_height, shape=4),
    ],
)

##### Airplane

airplane = asb.Airplane(
    name="FT A-10 Warthog",
    wings=[
        main_wing,
        horizontal_stabilizer,
        vertical_fin_right,
        vertical_fin_left,
    ],
    fuselages=[
        fuselage,
        nacelle_right,
        nacelle_left,
        pod_right,
        pod_left,
    ],
)

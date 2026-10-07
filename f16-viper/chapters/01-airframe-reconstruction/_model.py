##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Geometry constants

# Wing and strake (LERX) geometry
wing_strake_le_x = 0.430
wing_strake_le_y = 0.000
wing_strake_chord = 0.590

wing_break_le_x = 0.680
wing_break_le_y = 0.175
wing_break_chord = 0.340

wing_tip_le_x = 0.910
wing_tip_y = 0.456
wing_tip_chord = 0.110

wing_z = 0.015

# Vertical tail
vtail_root_le_x = 0.820
vtail_root_z = 0.080
vtail_root_chord = 0.440

vtail_tip_le_x = 1.080
vtail_tip_z = 0.385
vtail_tip_chord = 0.130

# Horizontal stabilators (slab tailplanes)
htail_root_le_x = 1.020
htail_root_y = 0.075
htail_root_z = 0.000
htail_root_chord = 0.255

htail_tip_le_x = 1.155
htail_tip_y = 0.260
htail_tip_z = -0.020
htail_tip_chord = 0.110

# Ventral strakes
vstrake_root_le_x = 0.960
vstrake_root_y = 0.055
vstrake_root_z = -0.060
vstrake_root_chord = 0.200

vstrake_tip_le_x = 1.040
vstrake_tip_y = 0.085
vstrake_tip_z = -0.115
vstrake_tip_chord = 0.120

# Fuselage loft stations
fuse_stations_x = [0.000, 0.080, 0.180, 0.300, 0.440, 0.600, 0.760, 0.920, 1.080, 1.200, 1.290]
fuse_widths =     [0.010, 0.050, 0.095, 0.135, 0.165, 0.185, 0.190, 0.180, 0.160, 0.130, 0.105]
fuse_heights =    [0.010, 0.050, 0.090, 0.130, 0.155, 0.170, 0.175, 0.165, 0.145, 0.125, 0.105]
fuse_z_offsets =  [0.000, 0.000, 0.005, 0.010, 0.015, 0.020, 0.020, 0.015, 0.010, 0.005, 0.000]

# Canopy loft stations
canopy_stations_x = [0.340, 0.430, 0.540, 0.650, 0.720]
canopy_widths =     [0.020, 0.105, 0.115, 0.085, 0.020]
canopy_heights =    [0.010, 0.060, 0.070, 0.045, 0.010]
canopy_z_offsets =  [0.075, 0.095, 0.105, 0.095, 0.080]

# Ventral intake duct stations
intake_stations_x = [0.460, 0.540, 0.640, 0.750]
intake_widths =     [0.085, 0.105, 0.110, 0.110]
intake_heights =    [0.035, 0.060, 0.060, 0.050]
intake_z_offsets =  [-0.060, -0.075, -0.075, -0.065]

# Wingtip missile rails with dummy Sidewinder missiles
missile_stations_x = [0.830, 0.910, 1.000, 1.050]
missile_diameters =  [0.008, 0.016, 0.016, 0.012]
missile_z =          wing_z

# Airfoil section (symmetric stand-in for folded Maker Foam slab)
foam_airfoil = asb.Airfoil("naca0008")

##### Assembly

fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[x, 0.0, z],
            width=w,
            height=h,
        )
        for x, w, h, z in zip(fuse_stations_x, fuse_widths, fuse_heights, fuse_z_offsets)
    ],
)

canopy = asb.Fuselage(
    name="Canopy",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[x, 0.0, z],
            width=w,
            height=h,
        )
        for x, w, h, z in zip(canopy_stations_x, canopy_widths, canopy_heights, canopy_z_offsets)
    ],
)

intake = asb.Fuselage(
    name="Ventral Intake",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[x, 0.0, z],
            width=w,
            height=h,
        )
        for x, w, h, z in zip(intake_stations_x, intake_widths, intake_heights, intake_z_offsets)
    ],
)

missile_starboard = asb.Fuselage(
    name="Starboard Missile",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[x, wing_tip_y, missile_z],
            radius=d / 2,
        )
        for x, d in zip(missile_stations_x, missile_diameters)
    ],
)

missile_port = asb.Fuselage(
    name="Port Missile",
    xsecs=[
        asb.FuselageXSec(
            xyz_c=[x, -wing_tip_y, missile_z],
            radius=d / 2,
        )
        for x, d in zip(missile_stations_x, missile_diameters)
    ],
)

main_wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[wing_strake_le_x, wing_strake_le_y, wing_z],
            chord=wing_strake_chord,
            airfoil=foam_airfoil,
        ),
        asb.WingXSec(
            xyz_le=[wing_break_le_x, wing_break_le_y, wing_z],
            chord=wing_break_chord,
            airfoil=foam_airfoil,
        ),
        asb.WingXSec(
            xyz_le=[wing_tip_le_x, wing_tip_y, wing_z],
            chord=wing_tip_chord,
            airfoil=foam_airfoil,
        ),
    ],
)

vertical_tail = asb.Wing(
    name="Vertical Tail",
    symmetric=False,
    xsecs=[
        asb.WingXSec(
            xyz_le=[vtail_root_le_x, 0.0, vtail_root_z],
            chord=vtail_root_chord,
            airfoil=foam_airfoil,
        ),
        asb.WingXSec(
            xyz_le=[vtail_tip_le_x, 0.0, vtail_tip_z],
            chord=vtail_tip_chord,
            airfoil=foam_airfoil,
        ),
    ],
)

horizontal_stabilator = asb.Wing(
    name="Horizontal Stabilator",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[htail_root_le_x, htail_root_y, htail_root_z],
            chord=htail_root_chord,
            airfoil=foam_airfoil,
        ),
        asb.WingXSec(
            xyz_le=[htail_tip_le_x, htail_tip_y, htail_tip_z],
            chord=htail_tip_chord,
            airfoil=foam_airfoil,
        ),
    ],
)

ventral_strakes = asb.Wing(
    name="Ventral Strakes",
    symmetric=True,
    xsecs=[
        asb.WingXSec(
            xyz_le=[vstrake_root_le_x, vstrake_root_y, vstrake_root_z],
            chord=vstrake_root_chord,
            airfoil=foam_airfoil,
        ),
        asb.WingXSec(
            xyz_le=[vstrake_tip_le_x, vstrake_tip_y, vstrake_tip_z],
            chord=vstrake_tip_chord,
            airfoil=foam_airfoil,
        ),
    ],
)

airplane = asb.Airplane(
    name="FT Master Series F-16 Viper",
    wings=[main_wing, vertical_tail, horizontal_stabilator, ventral_strakes],
    fuselages=[fuselage, canopy, intake, missile_starboard, missile_port],
)

##### Mass Properties (Dry configuration without battery)

# Structure components (Maker Foam + glue + canopy plastic)
mass_fuselage_foam = asb.MassProperties(mass=0.395, x_cg=0.620, y_cg=0.0, z_cg=0.010)
mass_wings_foam = asb.MassProperties(mass=0.252, x_cg=0.775, y_cg=0.0, z_cg=0.015)
mass_empennage_foam = asb.MassProperties(mass=0.142, x_cg=1.060, y_cg=0.0, z_cg=0.080)
mass_canopy = asb.MassProperties(mass=0.046, x_cg=0.505, y_cg=0.0, z_cg=0.095)
mass_linkages_glue = asb.MassProperties(mass=0.054, x_cg=0.760, y_cg=0.0, z_cg=0.010)

# Installed power and RC electronics (dry without flight battery)
mass_edf_motor = asb.MassProperties(mass=0.262, x_cg=0.780, y_cg=0.0, z_cg=0.000)
mass_esc = asb.MassProperties(mass=0.084, x_cg=0.520, y_cg=0.0, z_cg=-0.030)
mass_servos = asb.MassProperties(mass=0.058, x_cg=0.800, y_cg=0.0, z_cg=0.010)
mass_receiver_wiring = asb.MassProperties(mass=0.026, x_cg=0.500, y_cg=0.0, z_cg=0.020)
mass_nose_ballast = asb.MassProperties(mass=0.045, x_cg=0.090, y_cg=0.0, z_cg=0.000)

mass_properties_dry = (
    mass_fuselage_foam
    + mass_wings_foam
    + mass_empennage_foam
    + mass_canopy
    + mass_linkages_glue
    + mass_edf_motor
    + mass_esc
    + mass_servos
    + mass_receiver_wiring
    + mass_nose_ballast
)

# Reference dimensions and derived checks
derived_wingspan = main_wing.span(include_centerline_distance=True)
derived_length = fuselage.length()
derived_dry_mass = mass_properties_dry.mass
derived_cg_x = mass_properties_dry.x_cg
derived_cg_aft_le = derived_cg_x - wing_break_le_x

import aerosandbox as asb
import aerosandbox.numpy as np

# Specified
wingspan = 0.7366
length = 0.50165
wheel_dia = 0.0508

# Assumed / Fittable constants
fuse_width = 0.18
fuse_height = 0.22
fuse_station_mid = 0.15

wing_root_chord = 0.25
wing_tip_chord = 0.12
wing_sweep = 0.05
wing_z = 0.0
wing_dihedral = 0.02

winglet_height = 0.15
winglet_chord = 0.12
winglet_offset = 0.02

motor_y = 0.18
motor_x = 0.18
motor_z = -0.02

leg_width = 0.05
leg_height = 0.10
leg_y = 0.06

foam_areal_density = 0.40 # kg/m^2 (guessed)

def build(props: bool = False) -> asb.Airplane:
    fuse = asb.Fuselage(
        name="fuselage",
        xsecs=[
            asb.FuselageXSec(xyz_c=[0, 0, 0], radius=0.04, shape=4),
            asb.FuselageXSec(xyz_c=[0.05, 0, 0], width=fuse_width*0.8, height=fuse_height*0.8, shape=4),
            asb.FuselageXSec(xyz_c=[fuse_station_mid, 0, 0], width=fuse_width, height=fuse_height, shape=4),
            asb.FuselageXSec(xyz_c=[length*0.7, 0, 0], width=fuse_width*0.8, height=fuse_height*0.8, shape=4),
            asb.FuselageXSec(xyz_c=[length, 0, 0], width=0.1, height=0.1, shape=4),
        ]
    )
    wing = asb.Wing(
        name="wing",
        xsecs=[
            asb.WingXSec(xyz_le=[fuse_station_mid, fuse_width/2, wing_z], chord=wing_root_chord, airfoil=asb.Airfoil("naca0005")),
            asb.WingXSec(xyz_le=[fuse_station_mid + wing_sweep, wingspan/2, wing_z + wing_dihedral], chord=wing_tip_chord, airfoil=asb.Airfoil("naca0005")),
        ],
        symmetric=True
    )
    winglet = asb.Wing(
        name="winglet",
        xsecs=[
            asb.WingXSec(xyz_le=[fuse_station_mid + wing_sweep - winglet_offset, wingspan/2, wing_z + wing_dihedral - winglet_height*0.3], chord=winglet_chord, airfoil=asb.Airfoil("naca0005")),
            asb.WingXSec(xyz_le=[fuse_station_mid + wing_sweep - winglet_offset, wingspan/2, wing_z + wing_dihedral + winglet_height*0.7], chord=winglet_chord, airfoil=asb.Airfoil("naca0005")),
        ],
        symmetric=True
    )
    motor_r = asb.Fuselage(
        name="motor_r",
        xsecs=[
            asb.FuselageXSec(xyz_c=[motor_x, motor_y, motor_z], width=0.03, height=0.04, shape=4),
            asb.FuselageXSec(xyz_c=[motor_x + 0.08, motor_y, motor_z], width=0.03, height=0.04, shape=4),
        ]
    )
    motor_l = asb.Fuselage(
        name="motor_l",
        xsecs=[
            asb.FuselageXSec(xyz_c=[motor_x, -motor_y, motor_z], width=0.03, height=0.04, shape=4),
            asb.FuselageXSec(xyz_c=[motor_x + 0.08, -motor_y, motor_z], width=0.03, height=0.04, shape=4),
        ]
    )
    leg_r = asb.Fuselage(
        name="leg_r",
        xsecs=[
            asb.FuselageXSec(xyz_c=[0.1, leg_y, -0.05], width=leg_width, height=leg_width, shape=4),
            asb.FuselageXSec(xyz_c=[0.15, leg_y, -0.05 - leg_height], width=leg_width, height=leg_width, shape=4),
        ]
    )
    leg_l = asb.Fuselage(
        name="leg_l",
        xsecs=[
            asb.FuselageXSec(xyz_c=[0.1, -leg_y, -0.05], width=leg_width, height=leg_width, shape=4),
            asb.FuselageXSec(xyz_c=[0.15, -leg_y, -0.05 - leg_height], width=leg_width, height=leg_width, shape=4),
        ]
    )
    
    return asb.Airplane(
        name="FT Little Piggy",
        xyz_ref=[fuse_station_mid + 0.06985, 0, 0],
        fuselages=[fuse, motor_r, motor_l, leg_r, leg_l],
        wings=[wing, winglet]
    )

airplane = build()
airplane_for_fit = build(props=True)

# Mass calculation
ballast_mass = 0.1301
battery_x = 0.3483

def get_mass_properties(battery_x=battery_x, ballast_mass=ballast_mass, foam_areal_density=0.40):
    # Airframe mass (foam areas)
    foam_area = 0.0
    for w in airplane.wings:
        foam_area += w.area() * (2 if w.symmetric else 1)
    for f in airplane.fuselages:
        foam_area += f.area_wetted()
        
    airframe_mass = asb.MassProperties(
        mass=foam_area * foam_areal_density,
        x_cg=length/2, # approximation
        y_cg=0,
        z_cg=0,
        Ixx=1e-3, Iyy=1e-3, Izz=1e-3
    )
    
    # Motors
    motors_mass = asb.MassProperties(
        mass=2 * 0.030,
        x_cg=motor_x,
        y_cg=0,
        z_cg=motor_z,
        Ixx=1e-4, Iyy=1e-4, Izz=1e-4
    )
    
    # ESCs + servos + receiver + wires
    elec_mass = asb.MassProperties(
        mass=2 * 0.020 + 2 * 0.009 + 0.010,
        x_cg=length/3,
        y_cg=0,
        z_cg=0,
        Ixx=1e-4, Iyy=1e-4, Izz=1e-4
    )
    
    # Wheels and gear
    gear_mass = asb.MassProperties(
        mass=2 * 0.010 + 0.015,
        x_cg=0.15,
        y_cg=0,
        z_cg=-0.05 - leg_height,
        Ixx=1e-4, Iyy=1e-4, Izz=1e-4
    )
    
    # Battery
    battery_mass = asb.MassProperties(
        mass=0.180,
        x_cg=battery_x,
        y_cg=0,
        z_cg=0.0,
        Ixx=1e-4, Iyy=1e-4, Izz=1e-4
    )
    
    # Ballast
    ballast = asb.MassProperties(
        mass=ballast_mass,
        x_cg=0.05, # put it in the nose
        y_cg=0,
        z_cg=0,
        Ixx=1e-5, Iyy=1e-5, Izz=1e-5
    )
    
    dry_mass_props = airframe_mass + motors_mass + elec_mass + gear_mass + ballast
    all_up_mass_props = dry_mass_props + battery_mass
    
    return dry_mass_props, all_up_mass_props


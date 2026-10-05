##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Geometry parameters

# Wing panel segments along semi-span
dy_fuse = 0.1275      # Fuselage centerline to fuselage side [m] (width 255 mm)
dy_inboard = 0.1425   # Fuselage side to inboard nacelle [m] (y = 0.270 m)
dy_mid = 0.220        # Inboard nacelle to outboard nacelle [m] (y = 0.490 m)
dy_tip = 0.2465       # Outboard nacelle to wing tip [m] (semi-span = 0.7365 m)

y_fuse = dy_fuse
y_inb = y_fuse + dy_inboard
y_outb = y_inb + dy_mid
y_tip = y_outb + dy_tip

dihedral_deg = 2.0
def _dihedral_z(y):
    return (y - y_fuse) * np.tan(np.radians(dihedral_deg)) if y > y_fuse else 0.0

# Wing leading edge sweep and placement
le_sweep = np.radians(1.5)
x_le_root = 0.304     # Wing root leading edge x-station [m]
def _x_le(y):
    return x_le_root + y * np.tan(le_sweep)

# Wing chords
chord_root = 0.330
chord_inb = 0.265
chord_outb = 0.200
chord_tip = 0.145

airfoil_foam = asb.Airfoil("naca0008")

wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[_x_le(0.0), 0.0, -0.060], chord=chord_root, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[_x_le(y_fuse), y_fuse, -0.060], chord=chord_root, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[_x_le(y_inb), y_inb, -0.060 + _dihedral_z(y_inb)], chord=chord_inb, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[_x_le(y_outb), y_outb, -0.060 + _dihedral_z(y_outb)], chord=chord_outb, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[_x_le(y_tip), y_tip, -0.060 + _dihedral_z(y_tip)], chord=chord_tip, airfoil=airfoil_foam),
    ]
)

# Fuselage stations from nose to tailcone
dx_nose = 0.100       # Nose cone tip to aft of nose cap [m]
dx_fwd = 0.140        # Nose cap to windshield base [m]
dx_windshield = 0.100 # Windshield base to cabin crest [m]
dx_cabin = 0.100      # Cabin crest to aft cabin [m]
dx_center = 0.160     # Aft cabin to mid bomb bay [m]
dx_aft = 0.150        # Mid bomb bay to aft wing junction [m]
dx_taper = 0.200      # Aft wing to tail base [m]
dx_tail = 0.218       # Tail base to tailcone tip [m]

x_fuse = np.cumsum([0.0, dx_nose, dx_fwd, dx_windshield, dx_cabin, dx_center, dx_aft, dx_taper, dx_tail])

fuse = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[x_fuse[0], 0.0, -0.020], width=0.160, height=0.130, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[1], 0.0, -0.010], width=0.220, height=0.170, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[2], 0.0,  0.000], width=0.250, height=0.190, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[3], 0.0,  0.040], width=0.255, height=0.230, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[4], 0.0,  0.035], width=0.255, height=0.230, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[5], 0.0,  0.020], width=0.255, height=0.210, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[6], 0.0,  0.025], width=0.200, height=0.170, shape=3.5),
        asb.FuselageXSec(xyz_c=[x_fuse[7], 0.0,  0.035], width=0.110, height=0.120, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_fuse[8], 0.0,  0.045], width=0.040, height=0.045, shape=2.5),
    ]
)

# Empennage
hstab = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[0.970, 0.00, 0.055], chord=0.180, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[1.020, 0.27, 0.055], chord=0.100, airfoil=airfoil_foam),
    ]
)

vstab = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=False,
    xsecs=[
        asb.WingXSec(xyz_le=[0.680, 0.0, 0.105], chord=0.480, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[0.880, 0.0, 0.220], chord=0.280, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[1.000, 0.0, 0.380], chord=0.150, airfoil=airfoil_foam),
    ]
)

# Nacelles
x_inb_le = _x_le(y_inb)
x_outb_le = _x_le(y_outb)

nac_inb_r = asb.Fuselage(
    name="Inboard Nacelle R",
    xsecs=[
        asb.FuselageXSec(xyz_c=[x_inb_le - 0.120,  y_inb, -0.06 + _dihedral_z(y_inb)], width=0.080, height=0.090, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_inb_le,          y_inb, -0.06 + _dihedral_z(y_inb)], width=0.085, height=0.100, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_inb_le + 0.140,  y_inb, -0.04 + _dihedral_z(y_inb)], width=0.065, height=0.065, shape=2.5),
    ]
)
nac_inb_l = asb.Fuselage(
    name="Inboard Nacelle L",
    xsecs=[
        asb.FuselageXSec(xyz_c=[x_inb_le - 0.120, -y_inb, -0.06 + _dihedral_z(y_inb)], width=0.080, height=0.090, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_inb_le,         -y_inb, -0.06 + _dihedral_z(y_inb)], width=0.085, height=0.100, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_inb_le + 0.140, -y_inb, -0.04 + _dihedral_z(y_inb)], width=0.065, height=0.065, shape=2.5),
    ]
)
nac_outb_r = asb.Fuselage(
    name="Outboard Nacelle R",
    xsecs=[
        asb.FuselageXSec(xyz_c=[x_outb_le - 0.100,  y_outb, -0.06 + _dihedral_z(y_outb)], width=0.075, height=0.080, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_outb_le,          y_outb, -0.06 + _dihedral_z(y_outb)], width=0.075, height=0.085, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_outb_le + 0.110,  y_outb, -0.04 + _dihedral_z(y_outb)], width=0.060, height=0.060, shape=2.5),
    ]
)
nac_outb_l = asb.Fuselage(
    name="Outboard Nacelle L",
    xsecs=[
        asb.FuselageXSec(xyz_c=[x_outb_le - 0.100, -y_outb, -0.06 + _dihedral_z(y_outb)], width=0.075, height=0.080, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_outb_le,         -y_outb, -0.06 + _dihedral_z(y_outb)], width=0.075, height=0.085, shape=3.0),
        asb.FuselageXSec(xyz_c=[x_outb_le + 0.110, -y_outb, -0.04 + _dihedral_z(y_outb)], width=0.060, height=0.060, shape=2.5),
    ]
)

airplane = asb.Airplane(
    name="FT Tubby B-17",
    wings=[wing, hstab, vstab],
    fuselages=[fuse, nac_inb_r, nac_inb_l, nac_outb_r, nac_outb_l]
)

##### Mass Properties

# Dry mass components: catalogue and derived figures
x_mot_inb = x_inb_le - 0.120
x_mot_outb = x_outb_le - 0.100
x_gear = x_inb_le - 0.060

component_masses_dry = {
    # Propulsion and radio gear (catalogue figures)
    "motors_inboard": asb.MassProperties(mass=2 * 0.054, x_cg=x_mot_inb),
    "motors_outboard": asb.MassProperties(mass=2 * 0.054, x_cg=x_mot_outb),
    "props": asb.MassProperties(mass=4 * 0.013, x_cg=(x_mot_inb + x_mot_outb) / 2 - 0.110),
    "escs": asb.MassProperties(mass=4 * 0.032, x_cg=x_le_root + 0.050),
    "servos_wing": asb.MassProperties(mass=2 * 0.010, x_cg=x_le_root + 0.150),
    "servos_tail": asb.MassProperties(mass=2 * 0.010, x_cg=0.750),
    "wiring_harness": asb.MassProperties(mass=0.125, x_cg=x_le_root + 0.080),
    "landing_gear_main": asb.MassProperties(mass=0.168, x_cg=x_gear),
    "landing_gear_tail": asb.MassProperties(mass=0.016, x_cg=1.100),
    "firewalls": asb.MassProperties(mass=4 * 0.010, x_cg=(x_mot_inb + x_mot_outb) / 2 - 0.100),
    "linkages": asb.MassProperties(mass=0.025, x_cg=0.600),
    "receiver": asb.MassProperties(mass=0.010, x_cg=x_le_root + 0.060),

    # Airframe foam, plastic, and glue
    "nose_cone": asb.MassProperties(mass=0.050, x_cg=0.050),
    "wing_airframe": asb.MassProperties(mass=0.400, x_cg=x_le_root + 0.105),
    "fuse_airframe": asb.MassProperties(mass=0.470, x_cg=0.485),
    "nacelles_airframe": asb.MassProperties(mass=0.130, x_cg=x_le_root),
    "tail_airframe": asb.MassProperties(mass=0.120, x_cg=1.040),
}

mass_props_dry = sum(component_masses_dry.values(), asb.MassProperties(mass=0.0, x_cg=0.0))

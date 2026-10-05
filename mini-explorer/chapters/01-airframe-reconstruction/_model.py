import aerosandbox as asb
import aerosandbox.numpy as np

##### Geometry

# Main wing: high wing, polyhedral tips, constant chord
wing_x_le = 0.195
wing_z_le = 0.035
chord = 0.190

# Panel layout: flat center panel on cabin, outer panels with dihedral
y_center = 0.225
tip_length = 0.265
dihedral_deg = 6.0
dihedral_rad = np.radians(dihedral_deg)
dy_tip = tip_length * np.cos(dihedral_rad)
dz_tip = tip_length * np.sin(dihedral_rad)
y_tip = y_center + dy_tip
z_tip = wing_z_le + dz_tip

# Airfoils: Clark-Y stand-in for folded foam wing; NACA 0008 for flat foam tail
airfoil_wing = asb.Airfoil("clarky")
airfoil_tail = asb.Airfoil("naca0008")

main_wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[wing_x_le, 0, wing_z_le], chord=chord, airfoil=airfoil_wing),
        asb.WingXSec(xyz_le=[wing_x_le, y_center, wing_z_le], chord=chord, airfoil=airfoil_wing),
        asb.WingXSec(xyz_le=[wing_x_le, y_tip, z_tip], chord=chord, airfoil=airfoil_wing),
    ],
)

# Empennage: conventional tail surfaces
hstab = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[0.582, 0, 0.015], chord=0.110, airfoil=airfoil_tail),
        asb.WingXSec(xyz_le=[0.612, 0.165, 0.015], chord=0.080, airfoil=airfoil_tail),
    ],
)

vstab = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=False,
    xsecs=[
        asb.WingXSec(xyz_le=[0.567, 0, 0.015], chord=0.125, airfoil=airfoil_tail),
        asb.WingXSec(xyz_le=[0.617, 0, 0.155], chord=0.075, airfoil=airfoil_tail),
    ],
)

# Fuselage: slab-sided foam box with cabin, removable nose, and pusher step
fuse = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.000, 0, 0.000], width=0.045, height=0.050, shape=5.0),
        asb.FuselageXSec(xyz_c=[0.090, 0, 0.000], width=0.052, height=0.058, shape=5.0),
        asb.FuselageXSec(xyz_c=[wing_x_le, 0, 0.000], width=0.055, height=0.068, shape=5.0),
        asb.FuselageXSec(xyz_c=[wing_x_le + chord, 0, 0.000], width=0.055, height=0.068, shape=5.0),
        asb.FuselageXSec(xyz_c=[0.410, 0, -0.010], width=0.048, height=0.045, shape=5.0),
        asb.FuselageXSec(xyz_c=[0.500, 0, -0.010], width=0.036, height=0.036, shape=5.0),
        asb.FuselageXSec(xyz_c=[0.655, 0, -0.010], width=0.028, height=0.030, shape=5.0),
    ],
)

# Pusher propulsor: 6-inch diameter disc in fuselage break
prop = asb.Propulsor(
    name="Propeller",
    xyz_c=[0.410, 0, 0.025],
    xyz_normal=[1, 0, 0],
    radius=0.0762,
)

##### Mass Properties

# Maker Foam areal density (348 g/m^2 coated board)
areal_density = 0.348

# Airframe foam components (sheet area * areal density)
foam_masses = {
    "wing": asb.MassProperties(mass=0.4163 * areal_density, x_cg=wing_x_le + 0.38 * chord, y_cg=0, z_cg=0.045),
    "hstab": asb.MassProperties(mass=0.03335 * areal_density, x_cg=0.630, y_cg=0, z_cg=0.015),
    "vstab": asb.MassProperties(mass=0.0150 * areal_density, x_cg=0.625, y_cg=0, z_cg=0.080),
    "fuse": asb.MassProperties(mass=0.1776 * areal_density, x_cg=0.280, y_cg=0, z_cg=0.000),
}

# Installed equipment (dry, catalogue specs and allowances)
equipment_masses = {
    "motor": asb.MassProperties(mass=0.020, x_cg=0.370, y_cg=0, z_cg=0.030),
    "prop": asb.MassProperties(mass=0.008, x_cg=0.410, y_cg=0, z_cg=0.030),
    "esc": asb.MassProperties(mass=0.024, x_cg=0.100, y_cg=0, z_cg=0.000),
    "servos_wing": asb.MassProperties(mass=0.018, x_cg=wing_x_le + 0.080, y_cg=0, z_cg=0.035),
    "servos_tail": asb.MassProperties(mass=0.018, x_cg=wing_x_le + 0.020, y_cg=0, z_cg=0.000),
    "receiver": asb.MassProperties(mass=0.008, x_cg=0.120, y_cg=0, z_cg=0.010),
    "firewall": asb.MassProperties(mass=0.010, x_cg=0.360, y_cg=0, z_cg=0.020),
    "linkages": asb.MassProperties(mass=0.012, x_cg=0.390, y_cg=0, z_cg=0.005),
    "wing_mount": asb.MassProperties(mass=0.008, x_cg=wing_x_le + 0.095, y_cg=0, z_cg=0.035),
    "adhesive": asb.MassProperties(mass=0.038, x_cg=0.280, y_cg=0, z_cg=0.015),
    "tape_velcro": asb.MassProperties(mass=0.008, x_cg=0.150, y_cg=0, z_cg=0.000),
}

dry_mass_props = sum(foam_masses.values()) + sum(equipment_masses.values())

# 850 mAh 3S LiPo battery (~80 g) placed in removable nose to calibrate CG to 51 mm aft of LE
m_batt = 0.080
cg_target_x = wing_x_le + 0.051
dry_mom_x = dry_mass_props.mass * dry_mass_props.x_cg
x_batt_cal = (cg_target_x * (dry_mass_props.mass + m_batt) - dry_mom_x) / m_batt

battery_mass_prop = asb.MassProperties(mass=m_batt, x_cg=x_batt_cal, y_cg=0, z_cg=0.000)
total_mass_props = dry_mass_props + battery_mass_prop

##### Airplane Assembly

airplane = asb.Airplane(
    name="FT Mighty Mini Explorer",
    wings=[main_wing, hstab, vstab],
    fuselages=[fuse],
    propulsors=[prop],
    xyz_ref=[total_mass_props.x_cg, 0, total_mass_props.z_cg],
    s_ref=main_wing.area(),
    c_ref=main_wing.mean_aerodynamic_chord(),
    b_ref=main_wing.span(type="y"),
)

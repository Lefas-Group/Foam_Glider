##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Vehicle

# Airfoils
# Wing uses a 5% cambered flat-bottom section standing in for folded Maker Foam over a spar
wing_airfoil = asb.Airfoil("naca2405")
# Tail surfaces use a thin 5% symmetric section standing in for flat foam sheet
tail_airfoil = asb.Airfoil("naca0005")

# Wing: Inverted gull wing with -15 deg anhedral inner panel and +11 deg dihedral outer panel
wing = asb.Wing(
    name="Main Wing",
    xsecs=[
        asb.WingXSec(xyz_le=[0.085, 0.0, -0.010], chord=0.135, airfoil=wing_airfoil),
        asb.WingXSec(xyz_le=[0.088, 0.0889, -0.034], chord=0.130, airfoil=wing_airfoil),
        asb.WingXSec(xyz_le=[0.110, 0.305, 0.008], chord=0.0803, airfoil=wing_airfoil),
    ],
    symmetric=True,
)

# Horizontal stabilizer: Measured off plan sheet via connected components (231 mm span, 63 mm chord)
hstab = asb.Wing(
    name="Horizontal Stabilizer",
    xsecs=[
        asb.WingXSec(xyz_le=[0.420, 0.0, 0.015], chord=0.063, airfoil=tail_airfoil),
        asb.WingXSec(xyz_le=[0.435, 0.231 / 2, 0.015], chord=0.038, airfoil=tail_airfoil),
    ],
    symmetric=True,
)

# Vertical stabilizer: Measured off plan sheet via connected components (134 mm span, 125 mm chord)
vstab = asb.Wing(
    name="Vertical Stabilizer",
    xsecs=[
        asb.WingXSec(xyz_le=[0.355, 0.0, 0.015], chord=0.125, airfoil=tail_airfoil),
        asb.WingXSec(xyz_le=[0.425, 0.0, 0.015 + 0.134], chord=0.045, airfoil=tail_airfoil),
    ],
    symmetric=False,
)

# Fuselage: 8 loft stations from cowl spinner to rudder hinge line (482 mm total length)
fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[0.000, 0, 0.000], width=0.055, height=0.055, shape=3),
        asb.FuselageXSec(xyz_c=[0.020, 0, 0.000], width=0.072, height=0.072, shape=4),
        asb.FuselageXSec(xyz_c=[0.080, 0, 0.000], width=0.072, height=0.072, shape=4),
        asb.FuselageXSec(xyz_c=[0.180, 0, 0.005], width=0.062, height=0.070, shape=3),
        asb.FuselageXSec(xyz_c=[0.260, 0, 0.012], width=0.058, height=0.065, shape=2),
        asb.FuselageXSec(xyz_c=[0.360, 0, 0.015], width=0.040, height=0.045, shape=2),
        asb.FuselageXSec(xyz_c=[0.440, 0, 0.015], width=0.020, height=0.028, shape=2),
        asb.FuselageXSec(xyz_c=[0.482, 0, 0.015], width=0.005, height=0.015, shape=2),
    ],
)

# Assembled aircraft
airplane = asb.Airplane(
    name="FT Mini Corsair v1.0",
    xyz_ref=[0.123, 0, 0],
    wings=[wing, hstab, vstab],
    fuselages=[fuselage],
    s_ref=wing.area(type="projected"),
    c_ref=wing.mean_aerodynamic_chord(),
    b_ref=wing.span(type="xy"),
)

# Component mass breakdown
mass_components = {
    "motor_prop": asb.MassProperties(mass=0.030, x_cg=0.015, y_cg=0, z_cg=0),
    "esc": asb.MassProperties(mass=0.013, x_cg=0.065, y_cg=0, z_cg=0),
    "servos": asb.MassProperties(mass=0.015, x_cg=0.180, y_cg=0, z_cg=0),
    "receiver": asb.MassProperties(mass=0.005, x_cg=0.160, y_cg=0, z_cg=0),
    "linkages": asb.MassProperties(mass=0.008, x_cg=0.300, y_cg=0, z_cg=0),
    "fuselage_airframe": asb.MassProperties(mass=0.042, x_cg=0.200, y_cg=0, z_cg=0.01),
    "wing_airframe": asb.MassProperties(mass=0.035, x_cg=0.135, y_cg=0, z_cg=-0.01),
    "tail_airframe": asb.MassProperties(mass=0.008, x_cg=0.435, y_cg=0, z_cg=0.03),
}
dry_mass_properties = sum(mass_components.values(), asb.MassProperties(mass=0, x_cg=0, y_cg=0, z_cg=0))

# Battery: 850 mAh 3S LiPo, mass computed from published AUW minus dry weight
x_cg_target = 0.085 + 0.038  # 38 mm aft of wing LE
battery_mass = 0.222 - dry_mass_properties.mass
x_battery = (0.222 * x_cg_target - dry_mass_properties.mass * dry_mass_properties.x_cg) / battery_mass
battery_mass_properties = asb.MassProperties(mass=battery_mass, x_cg=x_battery, y_cg=0, z_cg=-0.005)
auw_mass_properties = dry_mass_properties + battery_mass_properties


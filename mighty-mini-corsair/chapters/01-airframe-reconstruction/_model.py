##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Target specifications from brief

TARGET_SPAN = 0.737        # m (29 in)
TARGET_DRY_WEIGHT = 0.270  # kg (270 g)
TARGET_CG_X = 0.044        # m aft of wing root LE (44 mm)

TOL_SPAN = 0.01            # +/- 1%
TOL_DRY_WEIGHT = 0.05      # +/- 5%
TOL_CG_X = 0.10            # +/- 10%

##### Aerodynamic surfaces

# Flat-bottom folded-foam wing section, 5% thickness
airfoil = asb.Airfoil("naca2405")

# Inverted gull wing
wing = asb.Wing(
    name="Main Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[0.000, 0.000,  0.000], chord=0.150, airfoil=airfoil),
        asb.WingXSec(xyz_le=[0.000, 0.120, -0.032], chord=0.155, airfoil=airfoil),
        asb.WingXSec(xyz_le=[0.030, 0.3685, 0.005], chord=0.095, airfoil=airfoil),
    ]
)

# Empennage
hstab = asb.Wing(
    name="Horizontal Stabilizer",
    symmetric=True,
    xsecs=[
        asb.WingXSec(xyz_le=[0.460, 0.000, 0.035], chord=0.085, airfoil=airfoil),
        asb.WingXSec(xyz_le=[0.485, 0.125, 0.035], chord=0.060, airfoil=airfoil),
    ]
)

vstab = asb.Wing(
    name="Vertical Stabilizer",
    symmetric=False,
    xsecs=[
        asb.WingXSec(xyz_le=[0.430, 0.000, 0.035], chord=0.120, airfoil=airfoil),
        asb.WingXSec(xyz_le=[0.470, 0.000, 0.145], chord=0.060, airfoil=airfoil),
    ]
)

##### Fuselage loft

fuselage = asb.Fuselage(
    name="Fuselage",
    xsecs=[
        asb.FuselageXSec(xyz_c=[-0.120, 0, 0.000], width=0.080, height=0.080, shape=4),
        asb.FuselageXSec(xyz_c=[-0.050, 0, 0.000], width=0.088, height=0.088, shape=4),
        asb.FuselageXSec(xyz_c=[ 0.070, 0, 0.015], width=0.076, height=0.095, shape=3),
        asb.FuselageXSec(xyz_c=[ 0.200, 0, 0.025], width=0.060, height=0.075, shape=2),
        asb.FuselageXSec(xyz_c=[ 0.360, 0, 0.030], width=0.035, height=0.045, shape=2),
        asb.FuselageXSec(xyz_c=[ 0.460, 0, 0.035], width=0.015, height=0.025, shape=2),
    ]
)

##### Mass breakdown (dry, without battery)

components = {
    "motor": asb.MassProperties(mass=0.030, x_cg=-0.115),
    "propeller": asb.MassProperties(mass=0.005, x_cg=-0.130),
    "esc": asb.MassProperties(mass=0.012, x_cg=-0.070),
    "servos_pod": asb.MassProperties(mass=0.012, x_cg=-0.010),
    "servos_wing": asb.MassProperties(mass=0.012, x_cg=0.035),
    "receiver": asb.MassProperties(mass=0.008, x_cg=0.010),
    "pushrods_horns": asb.MassProperties(mass=0.008, x_cg=0.220),
    "wing_structure": asb.MassProperties(mass=0.101, x_cg=0.048),
    "fuselage_structure": asb.MassProperties(mass=0.068, x_cg=0.050),
    "tail_structure": asb.MassProperties(mass=0.014, x_cg=0.450),
}

mass_properties = sum(components.values(), asb.MassProperties(mass=0, x_cg=0, y_cg=0, z_cg=0))

##### Complete Airplane

airplane = asb.Airplane(
    name="FT Mighty Mini Corsair MKR2",
    xyz_ref=[mass_properties.x_cg, 0, 0],
    wings=[wing, hstab, vstab],
    fuselages=[fuselage]
)


##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Vehicle
# PUBLISHED, never fitted: span 1460 mm, CG 45 mm aft of the root leading edge.
# Everything else is a first guess from the real P-38's proportions
# (span 15.85 m, length 11.53 m -> length/span 0.727) and from the reference
# photograph's description. Each is a named module-level constant so
# fit_geometry can take it.

semi_span    = 0.730      # PUBLISHED 1460 mm span

# wing
chord_root   = 0.300
chord_boom   = 0.280
chord_tip    = 0.150
x_le_root    = 0.280
y_boom       = 0.200      # boom centreline from the aircraft centreline
dihedral_deg = 3.0
le_sweep_deg = 2.0

# booms (carry the motors forward and the fins aft)
boom_nose    = 0.150
boom_tail    = 1.010
boom_width   = 0.095
boom_height  = 0.105

# crew nacelle, on the centreline
pod_nose     = 0.230
pod_tail     = 0.700
pod_width    = 0.140
pod_height   = 0.150

# empennage: twin fins on the booms, tailplane spanning between them
fin_x        = 0.880
fin_chord    = 0.190
fin_height   = 0.180
hstab_x      = 0.930
hstab_chord  = 0.160

# propulsion (published Power Pack C: 9x4.5 props)
prop_diameter  = 0.229
prop_angle_deg = 20.0
prop_chord     = 0.026

airfoil_foam = asb.Airfoil("naca0008")

def _x_le(y):
    return x_le_root + abs(y)*np.tan(np.radians(le_sweep_deg))

def _z(y):
    return max(0.0, abs(y) - y_boom)*np.tan(np.radians(dihedral_deg))

wing = asb.Wing(name="Main Wing", symmetric=True, xsecs=[
    asb.WingXSec(xyz_le=[_x_le(0.0),       0.0,       _z(0.0)],       chord=chord_root, airfoil=airfoil_foam),
    asb.WingXSec(xyz_le=[_x_le(y_boom),    y_boom,    _z(y_boom)],    chord=chord_boom, airfoil=airfoil_foam),
    asb.WingXSec(xyz_le=[_x_le(semi_span), semi_span, _z(semi_span)], chord=chord_tip,  airfoil=airfoil_foam),
])

def _boom(name, sign):
    xs = np.linspace(boom_nose, boom_tail, 6)
    return asb.Fuselage(name=name, xsecs=[
        asb.FuselageXSec(xyz_c=[float(x), sign*y_boom, -0.010],
                         width=boom_width, height=boom_height, shape=3.0)
        for x in xs])

boom_r, boom_l = _boom("Boom R", 1), _boom("Boom L", -1)

pod = asb.Fuselage(name="Crew Nacelle", xsecs=[
    asb.FuselageXSec(xyz_c=[pod_nose,              0.0, -0.030], width=0.045,      height=0.050,       shape=2.5),
    asb.FuselageXSec(xyz_c=[pod_nose+0.100,        0.0, -0.020], width=pod_width,  height=pod_height,  shape=3.0),
    asb.FuselageXSec(xyz_c=[pod_tail-0.140,        0.0, -0.015], width=pod_width,  height=pod_height,  shape=3.0),
    asb.FuselageXSec(xyz_c=[pod_tail,              0.0,  0.000], width=0.050,      height=0.055,       shape=2.5),
])

def _fin(name, sign):
    return asb.Wing(name=name, symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[fin_x,       sign*y_boom, 0.020],             chord=fin_chord,      airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[fin_x+0.045, sign*y_boom, 0.020+fin_height],  chord=fin_chord*0.70, airfoil=airfoil_foam),
    ])

fin_r, fin_l = _fin("Fin R", 1), _fin("Fin L", -1)

hstab = asb.Wing(name="Horizontal Stabilizer", symmetric=True, xsecs=[
    asb.WingXSec(xyz_le=[hstab_x, 0.0,    0.095], chord=hstab_chord, airfoil=airfoil_foam),
    asb.WingXSec(xyz_le=[hstab_x, y_boom, 0.095], chord=hstab_chord, airfoil=airfoil_foam),
])

# PROPELLERS ARE SILHOUETTE-ONLY. They are in every photograph and must be
# matched, but AeroBuildup would charge their wetted area as parasite drag on
# a streamlined body, and the propulsion model already accounts for them.
def _prop(name, sign):
    r = prop_diameter/2.0
    a = np.radians(prop_angle_deg)
    dy, dz = r*np.cos(a), r*np.sin(a)
    return asb.Wing(name=name, symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[boom_nose-0.012, sign*y_boom-dy, -0.010-dz], chord=prop_chord, airfoil=airfoil_foam),
        asb.WingXSec(xyz_le=[boom_nose-0.012, sign*y_boom+dy, -0.010+dz], chord=prop_chord, airfoil=airfoil_foam),
    ])

def build(props: bool = False) -> asb.Airplane:
    """`props=True` is for silhouette comparison only, never for aerodynamics."""
    wings = [wing, hstab, fin_r, fin_l]
    if props:
        wings = wings + [_prop("Prop R", 1), _prop("Prop L", -1)]
    return asb.Airplane(name="FT P-38 Lightning MkR2",
                        wings=wings, fuselages=[pod, boom_r, boom_l])

airplane = build()                      # what flies
airplane_for_fit = build(props=True)    # what the camera sees

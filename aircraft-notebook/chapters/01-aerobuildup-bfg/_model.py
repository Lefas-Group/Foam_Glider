# =============================================================================
# The BFG AeroBuildup model.
#
# This file defines the chapter. A different airframe, or a different aero
# method, gets its own directory and its own _model.py, sharing nothing with
# this one.
#
# Loaded two ways, both by exec into the caller's namespace:
#   - entries, via the _model.qmd shim next to this file
#   - scratch scripts, via _scratch/probe.py
#
# (No literal include shortcode in these comments -- the chapter index prints
# this file through `output: asis`, where one risks being expanded.)
# exec rather than import, because every chapter names its model `_model` and
# real imports would collide in sys.modules.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete _freeze/chapters/01-aerobuildup-bfg/ and render normally.
# =============================================================================
import aerosandbox as asb
import aerosandbox.numpy as np
import matplotlib.pyplot as plt

##### Vehicle -- measured off the built glider
b_w      = 0.315      # m, wingspan
c_w      = 0.070      # m, mean chord
S_w      = 0.0220     # m^2, wing area
dihedral = 8.0        # deg
S_h      = 0.0039     # m^2, stabilizer area
AR_h     = 2.5        # stabilizer aspect ratio
S_v      = 0.0011     # m^2, fin area
AR_v     = 1.5        # ASSUMED -- the fin's aspect ratio was not measured
l_tail   = 0.100      # m, tail quarter-chord aft of the wing quarter-chord

##### Material
t_foam   = 0.005      # m, foam thickness
rho_foam = 43.0       # kg/m^3, foam density

##### Derived planform
AR_w     = b_w ** 2 / S_w
b_h, c_h = (S_h * AR_h) ** 0.5, (S_h / AR_h) ** 0.5
b_v, c_v = (S_v * AR_v) ** 0.5, (S_v / AR_v) ** 0.5
z_tip    = (b_w / 2) * np.tand(dihedral)   # m, tip rise from dihedral
x_qc_w   = 0.25 * c_w                       # wing quarter-chord station
x_qc_t   = x_qc_w + l_tail                  # tail quarter-chord station

m_surfaces = (S_w + S_h + S_v) * t_foam * rho_foam  # kg, flying surfaces only

##### Section
# 5 mm foam on a 70 mm chord is 7.1% thick, and flat. NACA 0007 is the nearest
# well-behaved symmetric section NeuralFoil knows; the real plate has a sharper
# leading edge, so it will stall earlier and more gently than this predicts.
airfoil = asb.Airfoil("naca0007")


def build_airplane():
    """The BFG as three flat foam surfaces. No fuselage or boom is modelled."""
    wing = asb.Wing(name="Wing", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=c_w, airfoil=airfoil),
        asb.WingXSec(xyz_le=[0, b_w / 2, z_tip], chord=c_w, airfoil=airfoil),
    ])
    stab = asb.Wing(name="Stabilizer", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[x_qc_t - 0.25 * c_h, 0, 0], chord=c_h, airfoil=airfoil),
        asb.WingXSec(xyz_le=[x_qc_t - 0.25 * c_h, b_h / 2, 0], chord=c_h, airfoil=airfoil),
    ])
    fin = asb.Wing(name="Fin", symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[x_qc_t - 0.25 * c_v, 0, 0], chord=c_v, airfoil=airfoil),
        asb.WingXSec(xyz_le=[x_qc_t - 0.25 * c_v, 0, b_v], chord=c_v, airfoil=airfoil),
    ])
    return asb.Airplane(
        name="BFG", wings=[wing, stab, fin],
        s_ref=S_w, c_ref=c_w, b_ref=b_w,
        xyz_ref=[x_qc_w, 0, 0],  # moments about the wing quarter-chord
    )


bfg = build_airplane()


def polars(alpha, V=6.0):
    """
    Whole-airframe aero over a sweep of angle of attack [deg] at fixed speed.

    Reynolds number is set by V, and at this scale it matters a great deal --
    so V is part of the answer, not a detail. Returns the AeroBuildup dict with
    alpha, V and chord Reynolds number added.
    """
    op = asb.OperatingPoint(velocity=V, alpha=alpha)
    aero = asb.AeroBuildup(airplane=bfg, op_point=op).run()
    return {**aero, "alpha": alpha, "V": V, "Re_c": op.reynolds(c_w)}

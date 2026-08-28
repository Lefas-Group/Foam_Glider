# =============================================================================
# The McEagle-300 AeroBuildup model.
#
# Norm Poff's "McEagle" plan sheet (Aerospace Education Services Project,
# Oklahoma State University), scaled so the wing spans 300 mm, cut from foam
# sheet weighing 27 g per A3.
#
# This file defines the chapter. A different airframe, or a different aero
# method, gets its own directory and its own _model.py, sharing nothing with
# this one.
#
# Loaded two ways, both by exec into the caller's namespace:
#   - entries, via the _model.qmd shim next to this file
#   - scratch scripts, via _scratch/probe.py
#
# exec rather than import, because every chapter names its model `_model` and
# real imports would collide in sys.modules.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete _freeze/chapters/02-mceagle-300/ and render normally.
#
# WHERE THE NUMBERS COME FROM
# The plan sheet is a scan, 1242 px across a 8.5 in page. Every part is a grey
# fill on white, so each was segmented, hole-filled (the white part labels are
# punched out of the fills) and measured: area, chord at a set of span
# stations, centroid. One scale factor converts all of it -- the traced wing
# spans 1252 px, which is 300 mm, giving 0.23981 mm/px. At that scale the plan
# is being enlarged 1.380x from its printed 217 mm span.
#
# The chord tables below are traced values throughout, and every area is the
# trapezoidal integral of its own table rather than the traced pixel area --
# so the reference area a coefficient is divided by is the area the sections
# actually enclose. The two agree to 0.5%, which is the cost of representing a
# rounded tip with straight-line sections.
# =============================================================================
import aerosandbox as asb
import aerosandbox.numpy as np
import matplotlib.pyplot as plt

##### Material
# 27 g per A3 sheet (0.297 x 0.420 m) is the whole of what is specified, and is
# also the only thing mass depends on. Thickness is ASSUMED at 5 mm, carried
# over from the foam measured for the BFG in chapter 1 -- 27 g/A3 works out at
# 43.3 kg/m^3 over 5 mm, which is that same foam to within a percent. Thickness
# is used only to pick the section, not for mass.
sigma    = 0.027 / (0.297 * 0.420)   # kg/m^2, areal density of the sheet
t_foam   = 0.005                     # m, ASSUMED sheet thickness

##### Planform, traced from the plan sheet
S_fus    = 0.009991                  # m^2, traced fuselage side area, one lamination
l_fus    = 0.4376                    # m, nose to tail, the two pieces interlocked

# Fuselage plate depth against station aft of the nose, traced the same way.
# Integrating it returns 0.010027 m^2 against the 0.009991 m^2 traced directly,
# so the profile and the area agree to 0.4%. The nose station is given 0.5 mm
# rather than its traced 0.2 mm to keep the first cross-section from being
# degenerate.
fus_x    = np.array([0, 4.1, 7.9, 16.1, 24.0, 40.0, 60.0, 80.1, 100.0, 119.9,
                     140.0, 160.0, 180.1, 200.0, 240.0, 280.1, 319.9, 360.0,
                     400.0, 437.6]) * 1e-3
fus_d    = np.array([0.5, 21.6, 27.1, 33.3, 36.7, 38.4, 37.9, 36.2, 33.3, 32.6,
                     29.0, 26.6, 25.2, 20.4, 19.9, 18.0, 15.3, 12.7,
                     12.2, 12.0]) * 1e-3

# Wing: straight leading edge, elliptical trailing edge, rounding off to a
# point at the tip. eta is fraction of semispan measured ALONG THE PANEL.
#
# b_w is the flat pattern -- the width of foam you cut, and the scale the plan
# is set to. It is not the span of the finished glider: bending the wing to its
# dihedral pulls the tips inboard, so the built aircraft measures
# 2 * y_tip = 292 mm across. Placing the traced chords at projected y stations
# instead would quietly require a 308 mm flat pattern to build a 300 mm glider.
b_plan   = 0.2172                    # m, the wing's span on the printed plan
                                     # sheet: 1252 px at 1242 px / 8.5 in
b_w      = 0.300                     # m, flat pattern width, tip to tip
wing_eta = np.array([0, .1, .2, .3, .4, .5, .6, .7, .8, .85, .9, .93, .96, .98, 1.0])
wing_c   = np.array([98.80, 98.32, 97.12, 95.68, 94.00, 91.85, 89.45, 86.09,
                     82.01, 79.38, 74.82, 67.39, 51.80, 38.13, 8.00]) * 1e-3

# Stabilizer: straight leading edge, near-constant chord to a rounded tip.
b_h      = 0.1446                    # m, stabilizer span
stab_eta = np.array([0, .25, .5, .7, .85, .95, .99, 1.0])
stab_c   = np.array([65.23, 65.23, 64.51, 63.31, 61.87, 60.70,
                     60.43, 28.00]) * 1e-3

# Fin: straight trailing edge, leading edge swept back over the outer quarter.
b_v      = 0.0614                    # m, fin height above the fuselage
fin_eta  = np.array([0, .25, .5, .75, .9, 1.0])
fin_c    = np.array([43.20, 42.45, 41.73, 41.01, 32.61, 4.00]) * 1e-3

##### Stations, measured aft of the nose
# The plan marks each mounting position with a dashed bracket. The stabilizer
# and fin brackets both run to the square tail end and match their part's chord
# to within 2 mm, so both are mounted flush with the tail. The wing bracket is
# only 47 mm long against a 99 mm root chord -- it marks the glue bead, not the
# chord -- so the root chord is centred on it.
x_le_w   = 0.0934                    # m, wing root leading edge
x_le_h   = l_fus - stab_c[0]         # m, stabilizer root leading edge
x_te_v   = l_fus                     # m, fin trailing edge, at the tail

# Vertical arrangement. The fuselage is a flat plate on edge; its top edge runs
# straight from nose to tail and carries the wing, so z = 0 is the wing root
# chord line. The plan puts the fin on top of that edge and the stabilizer
# under the fuselage, where the tail is 12.2 mm deep.
z_h      = -0.0122                   # m, stabilizer below the wing root plane

dihedral = 13.29                     # deg -- the plan's 2.5 cm tip rise, at
                                     # its printed 108.7 mm semispan
i_h      = -2.0                      # deg, ASSUMED. The build notes call for
                                     # the tail "at a slight negative angle to
                                     # the plane of the wings" and give no
                                     # number.

##### Derived planform
# The panel is rigid foam bent at the root, so eta runs along the panel and the
# tip station is that arc length resolved into y and z.
y_tip    = (b_w / 2) * np.cosd(dihedral)  # m, projected half-span, as built
z_tip    = (b_w / 2) * np.sind(dihedral)  # m, tip rise from the dihedral break
b_proj   = 2 * y_tip                 # m, span of the finished glider
x_qc_w   = x_le_w + 0.25 * wing_c[0]  # m, wing root quarter-chord, the moment reference
x_qc_h   = x_le_h + 0.25 * stab_c[0]  # m, stabilizer root quarter-chord

##### Section
# Every surface is cut from the same flat 5 mm plate with square edges, so
# every surface gets the same section: one thin symmetric shape standing in for
# a flat plate. NACA 0006 is the nearest well-behaved symmetric section
# NeuralFoil knows.
#
# This is NOT a thickness match, and must not be "corrected" into one. The foam
# is 5.7% of the wing's mean chord but 7.9% of the stabilizer's and 12.8% of
# the fin's, and matching those makes the model worse, not better: NeuralFoil's
# smooth sections shed lift-curve slope fast at this scale -- at the fin's Re of
# 15,600 it falls from 0.081 to 0.018 per degree between 6% and 13% thick, which
# is enough to flip Cn_beta negative -- while a real sharp-edged plate does not,
# because the sharp edge fixes separation and reattachment. Thin is the honest
# stand-in for flat at low Reynolds number.
#
# The real plate is sharper-edged still, so it will stall earlier and more
# gently than this predicts.
airfoil = asb.Airfoil("naca0006")


##### Fuselage cross-section
# The plate is two 5 mm laminations glued face to face, so it is a constant
# 10 mm wide over its whole length and its depth is the traced profile. Its
# edges are square, which a super-ellipse reaches only in the limit; an
# exponent of 6 encloses 96.6 cm^3 against the slab's true 100.1 cm^3. The
# exponent is a weak lever on the aero -- CD at zero alpha moves 4% across
# exponents from 2 to 10 -- but a strong one on volume, which is why mass is
# NOT taken from this body. See mass_properties().
w_fus     = 2 * t_foam               # m, two laminations
fus_shape = 6.0                      # -, super-ellipse exponent of the fuselage section


def _surfaces(stab_incidence):
    """The four bodies. Split out so the reference quantities below can be read
    off real geometry instead of being integrated by hand a second time."""
    wing = asb.Wing(name="Wing", symmetric=True, xsecs=[
        asb.WingXSec(
            xyz_le=[x_le_w, eta * y_tip, eta * z_tip],
            chord=c, airfoil=airfoil,
        )
        for eta, c in zip(wing_eta, wing_c)
    ])
    stab = asb.Wing(name="Stabilizer", symmetric=True, xsecs=[
        asb.WingXSec(
            xyz_le=[x_le_h, eta * b_h / 2, z_h], chord=c,
            airfoil=airfoil, twist=stab_incidence,
        )
        for eta, c in zip(stab_eta, stab_c)
    ])
    fin = asb.Wing(name="Fin", symmetric=False, xsecs=[
        asb.WingXSec(
            xyz_le=[x_te_v - c, 0, eta * b_v], chord=c, airfoil=airfoil,
        )
        for eta, c in zip(fin_eta, fin_c)
    ])
    fuselage = asb.Fuselage(name="Fuselage", xsecs=[
        asb.FuselageXSec(
            xyz_c=[x, 0, -d / 2], width=w_fus, height=d, shape=fus_shape,
        )
        for x, d in zip(fus_x, fus_d)
    ])
    return wing, stab, fin, fuselage


##### Reference quantities, read off the geometry
# Not integrated from the chord tables. AeroSandbox already computes all of
# this, and asking it twice -- once by hand, once from the object -- is what
# caught the wing being built 2.75% oversized. They now agree exactly, and that
# agreement is a standing check rather than a coincidence.
#
# area() is the lofted planform, so it follows the dihedral break and, on the
# stabilizer, its -2 deg twist: 0.06% above the flat pattern the part is cut
# from, an eighth of the tracing uncertainty.
#
# c_ref is the true mean AERODYNAMIC chord, not S/b. Static margins are quoted
# as "% MAC", so the denominator had better be the MAC -- 89.8 mm here against
# 87.5 mm for the mean geometric chord. The neutral point itself does not care:
# x_np = x_ref - (dCm/dCL) * c_ref is invariant, because Cm scales as 1/c_ref.
_wing, _stab, _fin, _fus = _surfaces(i_h)
S_w      = _wing.area()              # m^2, wing area, both panels
S_h      = _stab.area()              # m^2, stabilizer area
S_v      = _fin.area()               # m^2, fin area
AR_w     = _wing.aspect_ratio()      # -, wing aspect ratio, on the flat pattern
c_w      = _wing.mean_aerodynamic_chord()  # m, MAC -- the static-margin reference


def build_airplane(stab_incidence=i_h):
    """The McEagle-300: three flat foam surfaces on the laminated fuselage
    plate, which is modelled as a body and carries force as well as mass."""
    wing, stab, fin, fuselage = _surfaces(stab_incidence)
    return asb.Airplane(
        name="McEagle-300", wings=[wing, stab, fin], fuselages=[fuselage],
        s_ref=S_w, c_ref=c_w, b_ref=b_w,
        xyz_ref=[x_qc_w, 0, 0],  # moments about the wing root quarter-chord
    )


mceagle = build_airplane()


def mass_properties(m_ballast=0.0, x_ballast=0.0):
    """
    Airframe mass properties, with ballast as a point mass at `x_ballast`.

    Every component is foam of one areal density, so each mass is its planform
    area times sigma and the fuselage counts twice for its two laminations.
    That is deliberately NOT `fuselage.volume()` times the foam density: the
    part is a rectangular slab, the aero body is a super-ellipse, and the
    super-ellipse under-fills the rectangle by 3-22% depending on `fus_shape`.
    The traced plan area is the physical quantity; the body is an aero
    approximation to it.

    Component CGs are the traced centroids of the plan shapes; radii of
    gyration are those of a uniform plate of the same extent. Returns the sum,
    so `.x_cg` is computed rather than assumed -- the plan's ballast (a dime,
    taped on to suit) is what sets it, and choosing it is a question for an
    entry, not a constant here.
    """
    def plate(mass, x_cg, y_cg, z_cg, ex, ey, ez):
        return asb.mass_properties_from_radius_of_gyration(
            mass=mass, x_cg=x_cg, y_cg=y_cg, z_cg=z_cg,
            radius_of_gyration_x=ex / 12 ** 0.5,
            radius_of_gyration_y=ey / 12 ** 0.5,
            radius_of_gyration_z=ez / 12 ** 0.5,
        )

    mp = (
        # Wing: centroid 45.0 mm aft of the root LE and 69.6 mm out along each
        # panel. That arc length resolves into height and projected offset the
        # same way the tip station does.
        plate(S_w * sigma, x_le_w + 0.0450, 0, 0.0696 * np.sind(dihedral),
              wing_c[0], 2 * 0.0696 * np.cosd(dihedral),
              2 * 0.0696 * np.sind(dihedral))
        # Stabilizer: centroid 31.8 mm aft of its root LE.
        + plate(S_h * sigma, x_le_h + 0.0318, 0, z_h, stab_c[0], b_h, 0)
        # Fin: centroid 20.7 mm aft of its LE, 28.7 mm above the fuselage.
        + plate(S_v * sigma, x_te_v - fin_c[0] + 0.0207, 0, 0.0287,
                fin_c[0], 0, b_v)
        # Fuselage, two laminations, centroid 21.5 mm below the top edge.
        + plate(2 * S_fus * sigma, 0.1163, 0, -0.0215, l_fus, 0, 0.0279)
    )
    if m_ballast:
        mp = mp + asb.MassProperties(mass=m_ballast, x_cg=x_ballast)
    return mp


def polars(alpha, V=6.0, airplane=None):
    """
    Whole-airframe aero over a sweep of angle of attack [deg] at fixed speed.

    Reynolds number is set by V, and at this scale it matters a great deal --
    so V is part of the answer, not a detail. Returns the AeroBuildup dict with
    alpha, V and mean-chord Reynolds number added.
    """
    op = asb.OperatingPoint(velocity=V, alpha=alpha)
    aero = asb.AeroBuildup(airplane=airplane or mceagle, op_point=op).run()
    return {**aero, "alpha": alpha, "V": V, "Re_c": op.reynolds(c_w)}

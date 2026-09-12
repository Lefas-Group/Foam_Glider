import aerosandbox as asb
import aerosandbox.numpy as np

def optimize_glider():
    opti = asb.Opti()

    alpha = opti.variable(init_guess=5.0, lower_bound=-5.0, upper_bound=15.0)
    V = opti.variable(init_guess=5.0, lower_bound=1.0, upper_bound=20.0)

    c_root = opti.variable(init_guess=0.05, lower_bound=0.02, upper_bound=0.15)
    c_tip = opti.variable(init_guess=0.03, lower_bound=0.02, upper_bound=0.15)
    x_wing = opti.variable(init_guess=0.05, lower_bound=0.0, upper_bound=0.15)
    ballast_mass = opti.variable(init_guess=0.005, lower_bound=0.0)

    airplane, wing, tail = build_glider(c_root, c_tip, x_wing, ballast_mass)

    areal_density = 174.4e-3
    mass_foam = (wing.area() + tail.area()) * areal_density
    mass = mass_foam + ballast_mass

    cg_x = (x_wing * wing.area() * areal_density + 0.25 * tail.area() * areal_density) / mass
    xyz_cg = [cg_x, 0, 0]

    aero = asb.AeroBuildup(
        airplane=airplane, 
        op_point=asb.OperatingPoint(velocity=V, alpha=alpha),
        xyz_ref=xyz_cg
    ).run()

    aero_2 = asb.AeroBuildup(
        airplane=airplane, 
        op_point=asb.OperatingPoint(velocity=V, alpha=alpha + 1.0),
        xyz_ref=xyz_cg
    ).run()

    dCm_dalpha = aero_2["Cm"] - aero["Cm"]
    dCL_dalpha = aero_2["CL"] - aero["CL"]

    opti.subject_to(aero["L"] == mass * 9.81)
    opti.subject_to(aero["Cm"] == 0)
    opti.subject_to(-dCm_dalpha / dCL_dalpha == 0.05)

    sink_rate = V * aero["D"] / aero["L"]
    opti.minimize(sink_rate)

    sol = opti.solve()
    
    return sol, V

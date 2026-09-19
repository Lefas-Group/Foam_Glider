import aerosandbox as asb
import aerosandbox.numpy as np

def optimize_glider_3mm(verbose=False):
    opti = asb.Opti()
    c_root = opti.variable(init_guess=0.08, lower_bound=0.01, upper_bound=0.15)
    taper = opti.variable(init_guess=0.5, lower_bound=0.1, upper_bound=1.0)
    alpha = opti.variable(init_guess=5, lower_bound=-5, upper_bound=15)
    V = opti.variable(init_guess=3, lower_bound=1, upper_bound=20)
    gamma = opti.variable(init_guess=-5, lower_bound=-45, upper_bound=45)
    cg_x = opti.variable(init_guess=0.03, lower_bound=-0.05, upper_bound=0.15)

    airplane = make_glider_3mm(c_root, taper, cg_x)
    aero = asb.AeroBuildup(airplane=airplane, op_point=asb.OperatingPoint(velocity=V, alpha=alpha)).run()

    wings_area = airplane.wings[0].area() + airplane.wings[1].area() + airplane.wings[2].area()
    # area density of 3mm foam = 174.4 * (3/5) = 104.64 g/m^2
    area_density = 0.10464
    fuse_mass = (0.2 * 0.015) * 2 * area_density
    mass = wings_area * area_density + fuse_mass
    weight = mass * 9.81

    opti.subject_to([
        aero["L"] == weight * np.cosd(gamma),
        aero["D"] == weight * np.sind(-gamma),
        aero["Cm"] == 0
    ])

    sink_rate = V * np.sind(-gamma)
    opti.minimize(sink_rate)
    sol = opti.solve(verbose=verbose)
    
    return {
        "sol": sol,
        "sink_rate": sol.value(sink_rate),
        "c_root": sol.value(c_root),
        "taper": sol.value(taper),
        "cg_x": sol.value(cg_x),
        "alpha": sol.value(alpha),
        "mass": sol.value(mass)
    }

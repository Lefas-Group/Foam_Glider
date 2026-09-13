import aerosandbox as asb
import aerosandbox.numpy as np

def optimize_glider(verbose=False):
    opti = asb.Opti()
    c_root = opti.variable(init_guess=0.08, lower_bound=0.01, upper_bound=0.15)
    taper = opti.variable(init_guess=0.5, lower_bound=0.1, upper_bound=1.0)
    alpha = opti.variable(init_guess=5, lower_bound=-5, upper_bound=15)
    V = opti.variable(init_guess=3, lower_bound=1, upper_bound=20)
    gamma = opti.variable(init_guess=-5, lower_bound=-45, upper_bound=45)
    cg_x = opti.variable(init_guess=0.03, lower_bound=-0.05, upper_bound=0.15)

    airplane = make_glider(c_root, taper, cg_x)

    aero = asb.AeroBuildup(
        airplane=airplane,
        op_point=asb.OperatingPoint(
            velocity=V,
            alpha=alpha
        )
    ).run()

    mass = (airplane.wings[0].area() + airplane.wings[1].area() + airplane.wings[2].area()) * 0.1744
    weight = mass * 9.81

    L = aero["L"]
    D = aero["D"]
    Cm = aero["Cm"]

    opti.subject_to([
        L == weight * np.cosd(gamma),
        D == weight * np.sind(-gamma),
        Cm == 0
    ])

    sink_rate = V * np.sind(-gamma)
    opti.minimize(sink_rate)
    sol = opti.solve(verbose=verbose)
    
    return {
        "sol": sol,
        "sink_rate": sink_rate,
        "L": L,
        "D": D,
        "vars": {
            "c_root": c_root,
            "taper": taper,
            "alpha": alpha,
            "V": V,
            "gamma": gamma,
            "cg_x": cg_x,
        },
        "bounds": {
            "c_root": (0.01, 0.15),
            "taper": (0.1, 1.0),
            "alpha": (-5, 15),
            "V": (1, 20),
            "gamma": (-45, 45),
            "cg_x": (-0.05, 0.15),
        }
    }

def get_optimized_flight_path():
    res = optimize_glider()
    sol = res['sol']
    opt_sink = sol.value(res['sink_rate'])
    opt_gamma = sol.value(res['vars']['gamma'])
    opt_v = sol.value(res['vars']['V'])
    return opt_sink, opt_gamma, opt_v

def optimize_full_glider(verbose=False, min_sweep=-45, init_sweep=0):
    import aerosandbox as asb
    import aerosandbox.numpy as np

    opti = asb.Opti()
    c_root = opti.variable(init_guess=0.08, lower_bound=0.01, upper_bound=0.15)
    taper = opti.variable(init_guess=0.5, lower_bound=0.1, upper_bound=1.0)
    sweep = opti.variable(init_guess=init_sweep, lower_bound=min_sweep, upper_bound=45)
    dihedral = opti.variable(init_guess=5, lower_bound=0, upper_bound=20)

    h_span = opti.variable(init_guess=0.1, lower_bound=0.02, upper_bound=0.3)
    h_chord = opti.variable(init_guess=0.03, lower_bound=0.01, upper_bound=0.1)
    v_span = opti.variable(init_guess=0.05, lower_bound=0.02, upper_bound=0.2)
    v_chord = opti.variable(init_guess=0.03, lower_bound=0.01, upper_bound=0.1)
    boom_len = opti.variable(init_guess=0.15, lower_bound=0.05, upper_bound=0.4)
    h_inc = opti.variable(init_guess=0, lower_bound=-15, upper_bound=15)
    cg_x = opti.variable(init_guess=0.03, lower_bound=-0.05, upper_bound=0.15)

    alpha = opti.variable(init_guess=5, lower_bound=-5, upper_bound=15)
    V = opti.variable(init_guess=3, lower_bound=1, upper_bound=20)
    gamma = opti.variable(init_guess=-5, lower_bound=-45, upper_bound=45)

    airplane = make_full_glider(c_root, taper, sweep, dihedral, h_span, h_chord, v_span, v_chord, boom_len, h_inc, cg_x)

    op1 = asb.OperatingPoint(velocity=V, alpha=alpha, beta=0)
    op2 = asb.OperatingPoint(velocity=V, alpha=alpha+1, beta=0)
    op3 = asb.OperatingPoint(velocity=V, alpha=alpha, beta=1)

    aero1 = asb.AeroBuildup(airplane=airplane, op_point=op1).run()
    aero2 = asb.AeroBuildup(airplane=airplane, op_point=op2).run()
    aero3 = asb.AeroBuildup(airplane=airplane, op_point=op3).run()

    wings_area = airplane.wings[0].area() + airplane.wings[1].area() + airplane.wings[2].area()
    area_density = 0.1744
    fuse_mass = ((boom_len + 0.05) * 0.015) * 2 * area_density
    mass = wings_area * area_density + fuse_mass
    weight = mass * 9.81

    opti.subject_to([
        aero1["L"] == weight * np.cosd(gamma),
        aero1["D"] == weight * np.sind(-gamma),
        aero1["Cm"] == 0
    ])

    dCm_dalpha = aero2['Cm'] - aero1['Cm']
    dCL_dalpha = aero2['CL'] - aero1['CL']
    SM = -dCm_dalpha / dCL_dalpha

    dCn_dbeta = aero3['Cn'] - aero1['Cn']
    dCl_dbeta = aero3['Cl'] - aero1['Cl']

    opti.subject_to([
        SM >= 0.10,
        dCn_dbeta >= 0.0005,
        dCl_dbeta <= -0.0005
    ])

    sink_rate = V * np.sind(-gamma)
    opti.minimize(sink_rate)
    sol = opti.solve(verbose=verbose)
    
    return {
        "opti": opti,
        "sol": sol,
        "airplane": airplane,
        "mass": mass,
        "sink_rate": sink_rate,
        "sweep": sweep,
        "dihedral": dihedral,
        "h_span": h_span,
        "h_chord": h_chord,
        "boom_len": boom_len
    }

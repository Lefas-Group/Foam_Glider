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
    area_density = 0.10464
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

def evaluate_stability_fix(fix_param, verbose=False):
    import aerosandbox as asb
    import aerosandbox.numpy as np

    opti = asb.Opti()
    area_density = 0.10464
    
    c_root = opti.variable(init_guess=0.08, lower_bound=0.01, upper_bound=0.15)
    taper = opti.variable(init_guess=0.5, lower_bound=0.1, upper_bound=1.0)
    cg_x = opti.variable(init_guess=0.03, lower_bound=-0.05, upper_bound=0.15)
    
    sweep = 0.0
    dihedral = 5.0
    h_span = 0.1
    h_chord = 0.03
    v_span = 0.05
    v_chord = 0.03
    boom_len = 0.126
    h_inc = 0.0
    
    if fix_param == "sweep":
        sweep = opti.variable(init_guess=0, lower_bound=-45, upper_bound=45)
    elif fix_param == "boom_len":
        boom_len = opti.variable(init_guess=0.15, lower_bound=0.05, upper_bound=0.4)
    elif fix_param == "h_tail":
        h_span = opti.variable(init_guess=0.1, lower_bound=0.02, upper_bound=0.3)
        h_chord = opti.variable(init_guess=0.01, lower_bound=0.01, upper_bound=0.1)
    
    alpha = opti.variable(init_guess=5, lower_bound=-5, upper_bound=15)
    V = opti.variable(init_guess=3, lower_bound=1, upper_bound=20)
    gamma = opti.variable(init_guess=-5, lower_bound=-45, upper_bound=45)
    
    airplane = make_full_glider(c_root, taper, sweep, dihedral, h_span, h_chord, v_span, v_chord, boom_len, h_inc, cg_x)
    
    op1 = asb.OperatingPoint(velocity=V, alpha=alpha, beta=0)
    op2 = asb.OperatingPoint(velocity=V, alpha=alpha+1, beta=0)
    
    aero1 = asb.AeroBuildup(airplane=airplane, op_point=op1).run()
    aero2 = asb.AeroBuildup(airplane=airplane, op_point=op2).run()
    
    wings_area = sum(w.area() for w in airplane.wings)
    fuse_length = (boom_len + 0.05) if type(boom_len) != float else 0.176
    fuse_mass = fuse_length * 0.015 * 2 * area_density
    mass = wings_area * area_density + fuse_mass
    weight = mass * 9.81
    
    opti.subject_to([
        aero1["L"] == weight * np.cosd(gamma),
        aero1["D"] == weight * np.sind(-gamma),
        aero1["Cm"] == 0,
        -(aero2['Cm'] - aero1['Cm']) / (aero2['CL'] - aero1['CL']) >= 0.10
    ])
    
    sink_rate = V * np.sind(-gamma)
    opti.minimize(sink_rate)
    sol = opti.solve(verbose=verbose)
    
    return sol.value(sink_rate)

def _make_biplane(c_root, taper, sweep, dihedral, h_span, h_chord, v_span, v_chord, boom_len, h_inc, cg_x, gap, stagger):
    import aerosandbox as asb
    import aerosandbox.numpy as np
    # Base glider for tail/fuse
    glider = make_full_glider(c_root, taper, sweep, dihedral, h_span, h_chord, v_span, v_chord, boom_len, h_inc, cg_x)
    
    # Biplane wings
    span = 0.3  # fixed
    y = np.array([0, span / 2])
    c = c_root * np.array([1, taper])
    x = np.array([0, (span / 2) * np.sind(sweep)])
    z = np.array([0, (span / 2) * np.sind(dihedral)])
    
    wing_top = asb.Wing(
        name="Top Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[x[i] + stagger, y[i], z[i] + gap/2],
                chord=c[i],
                airfoil=asb.Airfoil("naca4403")
            ) for i in range(2)
        ]
    )
    
    wing_bottom = asb.Wing(
        name="Bottom Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[x[i], y[i], z[i] - gap/2],
                chord=c[i],
                airfoil=asb.Airfoil("naca4403")
            ) for i in range(2)
        ]
    )
    
    wings = [wing_top, wing_bottom, glider.wings[1], glider.wings[2]]
    
    return asb.Airplane(
        name="Biplane",
        xyz_ref=[cg_x, 0, 0],
        wings=wings,
        fuselages=glider.fuselages
    )

def evaluate_biplane(verbose=False):
    import aerosandbox as asb
    import aerosandbox.numpy as np
    opti = asb.Opti()
    c_root = opti.variable(init_guess=0.04, lower_bound=0.01, upper_bound=0.15)
    taper = opti.variable(init_guess=0.5, lower_bound=0.1, upper_bound=1.0)
    sweep = opti.variable(init_guess=0.0, lower_bound=-45, upper_bound=45)
    dihedral = opti.variable(init_guess=5.0, lower_bound=0.0, upper_bound=20.0)

    h_span = opti.variable(init_guess=0.1, lower_bound=0.02, upper_bound=0.3)
    h_chord = opti.variable(init_guess=0.03, lower_bound=0.01, upper_bound=0.1)
    v_span = opti.variable(init_guess=0.05, lower_bound=0.02, upper_bound=0.2)
    v_chord = opti.variable(init_guess=0.03, lower_bound=0.01, upper_bound=0.1)
    boom_len = opti.variable(init_guess=0.15, lower_bound=0.05, upper_bound=0.4)
    h_inc = opti.variable(init_guess=0.0, lower_bound=-15.0, upper_bound=15.0)
    cg_x = opti.variable(init_guess=0.03, lower_bound=-0.05, upper_bound=0.15)

    gap = opti.variable(init_guess=0.05, lower_bound=0.01, upper_bound=0.2)
    stagger = opti.variable(init_guess=0.0, lower_bound=-0.1, upper_bound=0.1)

    alpha = opti.variable(init_guess=5.0, lower_bound=-5.0, upper_bound=15.0)
    V = opti.variable(init_guess=3.0, lower_bound=1.0, upper_bound=20.0)
    gamma = opti.variable(init_guess=-5.0, lower_bound=-45.0, upper_bound=45.0)

    airplane = _make_biplane(c_root, taper, sweep, dihedral, h_span, h_chord, v_span, v_chord, boom_len, h_inc, cg_x, gap, stagger)

    op1 = asb.OperatingPoint(velocity=V, alpha=alpha, beta=0)
    op2 = asb.OperatingPoint(velocity=V, alpha=alpha+1, beta=0)
    op3 = asb.OperatingPoint(velocity=V, alpha=alpha, beta=1)

    aero1 = asb.AeroBuildup(airplane=airplane, op_point=op1).run()
    aero2 = asb.AeroBuildup(airplane=airplane, op_point=op2).run()
    aero3 = asb.AeroBuildup(airplane=airplane, op_point=op3).run()

    wings_area = airplane.wings[0].area() + airplane.wings[1].area() + airplane.wings[2].area() + airplane.wings[3].area()
    area_density = 0.10464
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

    return sol.value(sink_rate)


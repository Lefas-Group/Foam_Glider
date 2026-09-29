import aerosandbox as asb
import aerosandbox.numpy as np

def _get_mass_properties_casadi(plane, area_density=0.1744, foam_thickness=0.005):
    vol_density = area_density / foam_thickness
    
    m_tot = 0
    x_cg_m = 0
    
    for wing in plane.wings:
        for i in range(len(wing.xsecs)-1):
            x0 = wing.xsecs[i]
            x1 = wing.xsecs[i+1]
            
            dy = x1.xyz_le[1] - x0.xyz_le[1]
            dz = x1.xyz_le[2] - x0.xyz_le[2]
            ds = np.sqrt(dy**2 + dz**2)
            
            c0, c1 = x0.chord, x1.chord
            area = (c0 + c1)/2 * ds
            
            x_c = (x0.xyz_le[0] + x1.xyz_le[0])/2 + (c0 + c1)/4
            m = area * area_density
            m_tot += m
            x_cg_m += m * x_c
            
    for fuse in plane.fuselages:
        for i in range(len(fuse.xsecs)-1):
            x0 = fuse.xsecs[i]
            x1 = fuse.xsecs[i+1]
            
            dx = x1.xyz_c[0] - x0.xyz_c[0]
            dy = x1.xyz_c[1] - x0.xyz_c[1]
            dz = x1.xyz_c[2] - x0.xyz_c[2]
            ds = np.sqrt(dx**2 + dy**2 + dz**2)
            
            a0, a1 = x0.xsec_area(), x1.xsec_area()
            vol = (a0 + a1)/2 * ds
            x_c = (x0.xyz_c[0] + x1.xyz_c[0])/2
            m = vol * vol_density
            m_tot += m
            x_cg_m += m * x_c
            
    return m_tot, x_cg_m / m_tot

def optimize_geometry_for_sink_rate(get_airplane_func, alpha_max=None, span_max=0.76):
    opti = asb.Opti()
    wing_x_le = opti.variable(init_guess=0.25, lower_bound=0.1, upper_bound=0.4)
    le_sweep = opti.variable(init_guess=10.5, lower_bound=0, upper_bound=45)
    wing_inc = opti.variable(init_guess=-4.0, lower_bound=-15, upper_bound=15)
    mass_ballast = opti.variable(init_guess=0.003, lower_bound=0.0, upper_bound=0.050)
    
    wing_span = opti.variable(init_guess=min(0.508, span_max), lower_bound=0.1, upper_bound=span_max)
    root_chord = opti.variable(init_guess=0.0853, lower_bound=0.02, upper_bound=0.15)
    tip_chord = opti.variable(init_guess=0.0508, lower_bound=0.01, upper_bound=0.15)

    plane = get_airplane_func(
        wing_x_le=wing_x_le, le_sweep=le_sweep, wing_inc=wing_inc,
        wing_span=wing_span, root_chord=root_chord, tip_chord=tip_chord
    )

    m_empty, x_cg_empty = _get_mass_properties_casadi(plane)
    m_total = m_empty + mass_ballast
    x_cg_total = (m_empty * x_cg_empty) / m_total 

    plane.xyz_ref = [x_cg_total, 0, 0]

    alpha_trim = opti.variable(init_guess=5.0, lower_bound=-5, upper_bound=20)
    if alpha_max is not None:
        opti.subject_to(alpha_trim <= alpha_max)
    v_trim = opti.variable(init_guess=5.0, lower_bound=2.0, upper_bound=15.0)

    op_trim = asb.OperatingPoint(velocity=v_trim, alpha=alpha_trim)
    aero_trim = asb.AeroBuildup(airplane=plane, op_point=op_trim).run()

    opti.subject_to([
        aero_trim['L'] == m_total * 9.81,
        aero_trim['Cm'] == 0
    ])

    op_dalpha = asb.OperatingPoint(velocity=v_trim, alpha=alpha_trim + 1.0)
    aero_dalpha = asb.AeroBuildup(airplane=plane, op_point=op_dalpha).run()

    dCm = aero_dalpha['Cm'] - aero_trim['Cm']
    dCL = aero_dalpha['CL'] - aero_trim['CL']

    opti.subject_to(dCm / dCL == -0.1)

    sink = v_trim * (aero_trim['D'] / aero_trim['L'])
    opti.minimize(sink)

    sol = opti.solve(verbose=False)
    
    opt_plane = get_airplane_func(
        wing_x_le=sol.value(wing_x_le), le_sweep=sol.value(le_sweep), wing_inc=sol.value(wing_inc),
        wing_span=sol.value(wing_span), root_chord=sol.value(root_chord), tip_chord=sol.value(tip_chord)
    )
    opt_plane.v_trim = float(sol.value(v_trim))
    opt_plane.alpha_trim = float(sol.value(alpha_trim))
    opt_plane.wing_x_le = float(sol.value(wing_x_le))
    opt_plane.le_sweep = float(sol.value(le_sweep))
    opt_plane.wing_inc = float(sol.value(wing_inc))
    opt_plane.wing_span = float(sol.value(wing_span))
    opt_plane.root_chord = float(sol.value(root_chord))
    opt_plane.tip_chord = float(sol.value(tip_chord))
    opt_plane.mass_ballast = float(sol.value(mass_ballast))
    opt_plane.m_total = float(sol.value(m_total))
    return float(sol.value(sink)), opt_plane


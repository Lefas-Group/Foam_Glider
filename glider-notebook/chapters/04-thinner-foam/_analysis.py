import aerosandbox as asb
import aerosandbox.numpy as np

def simulate_throw_3dof(airplane, mass, v_launch, pitch_launch_deg, Iyy=1e-4, z0=-1.5, t_max=5.0):
    import scipy.integrate as spi
    from scipy.interpolate import RegularGridInterpolator
    
    # Precompute aerodynamic surrogate
    V_grid = np.linspace(1, 10, 5)
    alpha_grid = np.linspace(-15, 25, 6)
    q_grid = np.linspace(-10, 10, 3)
    
    VV, AA, QQ = np.meshgrid(V_grid, alpha_grid, q_grid, indexing='ij')
    op = asb.OperatingPoint(velocity=VV.flatten(), alpha=AA.flatten(), q=QQ.flatten())
    aero = asb.AeroBuildup(airplane, op).run()
    
    Fx_data = aero["F_b"][0].reshape(VV.shape)
    Fz_data = aero["F_b"][2].reshape(VV.shape)
    My_data = aero["M_b"][1].reshape(VV.shape)
    
    Fx_interp = RegularGridInterpolator((V_grid, alpha_grid, q_grid), Fx_data, bounds_error=False, fill_value=None)
    Fz_interp = RegularGridInterpolator((V_grid, alpha_grid, q_grid), Fz_data, bounds_error=False, fill_value=None)
    My_interp = RegularGridInterpolator((V_grid, alpha_grid, q_grid), My_data, bounds_error=False, fill_value=None)
    
    def get_derivatives(t, state):
        x, z, u, w, theta, q = state
        V = max(np.sqrt(u**2 + w**2), 1.0)
        alpha = np.degrees(np.arctan2(w, u))
        pt = (V, alpha, q)
        
        Fx = float(Fx_interp(pt))
        Fz = float(Fz_interp(pt))
        My = float(My_interp(pt))
        
        g = 9.81
        Fx_tot = Fx - mass * g * np.sin(theta)
        Fz_tot = Fz + mass * g * np.cos(theta)
        
        du = Fx_tot / mass - q * w
        dw = Fz_tot / mass + q * u
        dq = My / Iyy
        
        dx = u * np.cos(theta) + w * np.sin(theta)
        dz = -u * np.sin(theta) + w * np.cos(theta)
        
        return [dx, dz, du, dw, q, dq]

    def _hit_ground(t, state): return state[1]
    _hit_ground.terminal = True
    _hit_ground.direction = 1
    
    res = spi.solve_ivp(
        get_derivatives, [0, t_max], 
        [0, z0, v_launch, 0, np.radians(pitch_launch_deg), 0], 
        events=_hit_ground, max_step=0.05
    )
    return res

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

def get_base_3mm_params(opt=None):
    if opt is None:
        opt = optimize_glider_3mm(verbose=False)
    return float(opt["c_root"]), float(opt["taper"]), float(opt["cg_x"])

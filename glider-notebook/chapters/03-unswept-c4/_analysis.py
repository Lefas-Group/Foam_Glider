import scipy.integrate as spi
import aerosandbox as asb
import aerosandbox.numpy as np

def simulate_launch(glider, mass, alpha_trim, v_launch, z0=-1.5, t_max=10.0):
    V_grid = np.linspace(0.1, 15, 50)
    L_grid = []
    D_grid = []
    
    # Compute aero forces across speeds
    for v in V_grid:
        op = asb.OperatingPoint(velocity=v, alpha=alpha_trim)
        aero = asb.AeroBuildup(airplane=glider, op_point=op).run()
        L_grid.append(aero["L"][0])
        D_grid.append(aero["D"][0])
        
    def _dynamics(t, state):
        x, z, V_curr, gamma_curr = state
        if V_curr < 0.1: return [0, 0, 0, 0]
        L = np.interp(V_curr, V_grid, L_grid)
        D = np.interp(V_curr, V_grid, D_grid)
        x_dot = V_curr * np.cos(gamma_curr)
        z_dot = -V_curr * np.sin(gamma_curr)
        V_dot = -D/mass - 9.81 * np.sin(gamma_curr)
        gamma_dot = (L/mass - 9.81 * np.cos(gamma_curr)) / V_curr
        return [x_dot, z_dot, V_dot, gamma_dot]
    
    def _hit_ground(t, state):
        return state[1]
    _hit_ground.terminal = True
    _hit_ground.direction = 1
    
    res = spi.solve_ivp(_dynamics, [0, t_max], [0, z0, v_launch, 0], events=_hit_ground, max_step=0.05)
    return res

def optimize_glider_unswept_c4(verbose=False):
    opti = asb.Opti()
    c_root = opti.variable(init_guess=0.08, lower_bound=0.01, upper_bound=0.15)
    taper = opti.variable(init_guess=0.5, lower_bound=0.1, upper_bound=1.0)
    alpha = opti.variable(init_guess=5, lower_bound=-5, upper_bound=15)
    V = opti.variable(init_guess=3, lower_bound=1, upper_bound=20)
    gamma = opti.variable(init_guess=-5, lower_bound=-45, upper_bound=45)
    cg_x = opti.variable(init_guess=0.03, lower_bound=-0.05, upper_bound=0.15)

    # The vehicle function is already in scope because both files are exec'd into the notebook
    airplane = make_glider_unswept_c4(c_root, taper, cg_x)
    aero = asb.AeroBuildup(airplane=airplane, op_point=asb.OperatingPoint(velocity=V, alpha=alpha)).run()

    wings_area = airplane.wings[0].area() + airplane.wings[1].area() + airplane.wings[2].area()
    fuse_mass = (0.2 * 0.015) * 2 * 0.1744 
    mass = wings_area * 0.1744 + fuse_mass
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

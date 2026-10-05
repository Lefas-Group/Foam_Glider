import aerosandbox as asb
import aerosandbox.numpy as np

def _make_airplane_with_elevator(delta_e_deg: float = 0.0) -> asb.Airplane:
    """Return a copy of the airplane with elevator deflection on the horizontal stabilizer."""
    cs = asb.ControlSurface(name="Elevator", deflection=delta_e_deg)
    hstab_mod = asb.Wing(
        name="Horizontal Stabilizer",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.970, 0.00, 0.055], chord=0.180, airfoil=airfoil_foam, control_surfaces=[cs]),
            asb.WingXSec(xyz_le=[1.020, 0.27, 0.055], chord=0.100, airfoil=airfoil_foam, control_surfaces=[cs]),
        ]
    )
    return asb.Airplane(
        name="FT Tubby B-17",
        wings=[wing, hstab_mod, vstab],
        fuselages=[fuse, nac_inb_r, nac_inb_l, nac_outb_r, nac_outb_l]
    )

def _solve_trimmed_flight(
    velocity: float,
    mass_total: float = 2.360,
    x_cg: float = 0.412,
    tol: float = 1e-3,
    max_iter: int = 6
) -> dict:
    """
    Solve for trimmed level flight (L = W, Cm = 0) at a specified airspeed.
    Returns aerodynamic state and force metrics.
    """
    W = mass_total * 9.80665
    rho = 1.225
    S = wing.area()
    
    CL_target = 2 * W / (rho * S * velocity**2)
    alpha = float(np.clip((CL_target + 0.02) / 0.08, 0.5, 14.0))
    delta_e = -3.0
    
    for _ in range(max_iter):
        plane = _make_airplane_with_elevator(delta_e)
        op = asb.OperatingPoint(velocity=velocity, alpha=alpha)
        res = asb.AeroBuildup(airplane=plane, op_point=op, xyz_ref=[x_cg, 0, 0]).run()
        
        L = float(res['L'][0])
        Cm = float(res['Cm'][0])
        
        dL = W - L
        if abs(dL) < tol * W and abs(Cm) < 1e-3:
            break
            
        q_inf = 0.5 * rho * velocity**2
        dL_da = q_inf * S * 0.08
        dCm_da = 0.005
        dCm_dde = -0.033
        
        da = (W - L) / dL_da
        alpha = float(np.clip(alpha + da, 0.0, 15.0))
        dde = -(Cm + dCm_da * da) / dCm_dde
        delta_e = float(np.clip(delta_e + dde, -16.0, 16.0))
    
    D = float(res['D'][0])
    L = float(res['L'][0])
    return {
        'velocity': velocity,
        'alpha': alpha,
        'delta_e': delta_e,
        'CL': float(res['CL'][0]),
        'CD': float(res['CD'][0]),
        'L': L,
        'D': D,
        'P_aero': D * velocity,
        'LD': L / D,
    }

def sweep_trimmed_envelope(
    velocities: np.ndarray,
    mass_total: float = 2.360,
    x_cg: float = 0.412
) -> dict:
    """Sweep a vector of airspeeds and return trimmed level flight conditions."""
    results = [_solve_trimmed_flight(v, mass_total=mass_total, x_cg=x_cg) for v in velocities]
    return {
        'velocity': np.array([r['velocity'] for r in results]),
        'alpha': np.array([r['alpha'] for r in results]),
        'delta_e': np.array([r['delta_e'] for r in results]),
        'CL': np.array([r['CL'] for r in results]),
        'CD': np.array([r['CD'] for r in results]),
        'L': np.array([r['L'] for r in results]),
        'D': np.array([r['D'] for r in results]),
        'P_aero': np.array([r['P_aero'] for r in results]),
        'LD': np.array([r['LD'] for r in results]),
    }

def find_stall_speed(
    mass_total: float = 2.360,
    x_cg: float = 0.412,
    tol_v: float = 0.05
) -> float:
    """Find the trimmed stall speed via bisection on level-flight lift equilibrium."""
    W = mass_total * 9.80665
    v_low = 10.5
    v_high = 11.5
    max_steps = 15
    for _ in range(max_steps):
        if (v_high - v_low) < tol_v:
            break
        v_mid = 0.5 * (v_low + v_high)
        r = _solve_trimmed_flight(v_mid, mass_total=mass_total, x_cg=x_cg)
        if r['L'] >= 0.99 * W and r['alpha'] < 11.0:
            v_high = v_mid
        else:
            v_low = v_mid
    else:
        raise RuntimeError("Stall speed search did not converge within tolerance.")
    return float(v_high)

import numpy as np

def get_mass_properties(plane, area_density=0.1744, foam_thickness=0.005):
    vol_density = area_density / foam_thickness
    total_mass = 0
    total_moment = np.zeros(3)
    
    for wing in plane.wings:
        area_tot = 0
        cg_tot = np.zeros(3)
        for i in range(len(wing.xsecs)-1):
            x0 = wing.xsecs[i]
            x1 = wing.xsecs[i+1]
            
            dy = x1.xyz_le[1] - x0.xyz_le[1]
            dz = x1.xyz_le[2] - x0.xyz_le[2]
            ds = np.sqrt(dy**2 + dz**2)
            
            c0, c1 = x0.chord, x1.chord
            dx_le = x1.xyz_le[0] - x0.xyz_le[0]
            dc = c1 - c0
            
            strips = 50
            x_cg_sec = 0
            area_sec = 0
            for t in np.linspace(0, 1, strips):
                dt = 1/strips
                chord_t = c0 + t*dc
                x_le_t = x0.xyz_le[0] + t*dx_le
                strip_area = chord_t * ds * dt
                strip_x_cg = x_le_t + chord_t / 2
                x_cg_sec += strip_x_cg * strip_area
                area_sec += strip_area
                
            cg = np.array([x_cg_sec/area_sec, 0, 0])
            cg_tot += cg * area_sec
            area_tot += area_sec
            
        cg = cg_tot / area_tot
        m = area_tot * area_density
        total_mass += m
        total_moment += m * cg

    for fuse in plane.fuselages:
        vol_tot = 0
        cg_tot = np.zeros(3)
        for i in range(len(fuse.xsecs)-1):
            x0 = fuse.xsecs[i]
            x1 = fuse.xsecs[i+1]
            
            dx = x1.xyz_c[0] - x0.xyz_c[0]
            dy = x1.xyz_c[1] - x0.xyz_c[1]
            dz = x1.xyz_c[2] - x0.xyz_c[2]
            ds = np.sqrt(dx**2 + dy**2 + dz**2)
            
            a0, a1 = x0.xsec_area(), x1.xsec_area()
            da = a1 - a0
            
            strips = 50
            x_cg_sec = 0
            vol_sec = 0
            for t in np.linspace(0, 1, strips):
                dt = 1/strips
                area_t = a0 + t*da
                x_c_t = x0.xyz_c[0] + t*dx
                
                strip_vol = area_t * ds * dt
                x_cg_sec += x_c_t * strip_vol
                vol_sec += strip_vol
                
            cg = np.array([x_cg_sec/vol_sec, 0, 0]) if vol_sec > 0 else np.zeros(3)
            cg_tot += cg * vol_sec
            vol_tot += vol_sec
            
        cg = cg_tot / vol_tot if vol_tot > 0 else np.zeros(3)
        m = vol_tot * vol_density
        total_mass += m
        total_moment += m * cg
        
    return total_mass, total_moment / total_mass

import scipy.optimize

def get_cg_x(airplane):
    op1 = asb.OperatingPoint(velocity=10, alpha=0)
    aero1 = asb.AeroBuildup(airplane=airplane, op_point=op1).run()
    op2 = asb.OperatingPoint(velocity=10, alpha=1)
    aero2 = asb.AeroBuildup(airplane=airplane, op_point=op2).run()
    
    CL_alpha = (aero2["CL"] - aero1["CL"]) / np.radians(1)
    Cm_alpha = (aero2["Cm"] - aero1["Cm"]) / np.radians(1)
    mac = airplane.c_ref
    x_np = airplane.xyz_ref[0] - mac * Cm_alpha / CL_alpha
    return float(np.array(x_np - 0.1 * mac).flatten()[0])

def apply_incidence(airplane, inc):
    p2 = airplane.copy()
    for w in p2.wings:
        for xsec in w.xsecs:
            xsec.twist = inc
    return p2

def get_trim_alpha(airplane, req_cg_x, cg_z, bracket=[-10, 80]):
    def get_Cm(alpha):
        res = asb.AeroBuildup(
            airplane=airplane,
            op_point=asb.OperatingPoint(velocity=5.0, alpha=alpha),
            xyz_ref=[req_cg_x, 0, cg_z]
        ).run()['Cm']
        return float(np.atleast_1d(res)[0])
    try:
        return scipy.optimize.root_scalar(get_Cm, bracket=bracket).root
    except Exception:
        return np.nan

def get_trimmed_flight_state(airplane, mass, req_cg_x, cg_z, alpha_trim):
    mg = mass * 9.81
    res_trim = asb.AeroBuildup(
        airplane=airplane,
        op_point=asb.OperatingPoint(velocity=5.0, alpha=alpha_trim),
        xyz_ref=[req_cg_x, 0, cg_z]
    ).run()
    L_5 = float(np.atleast_1d(res_trim['L'])[0])
    
    if L_5 <= 0:
        return np.nan, np.nan, np.nan
        
    v_trim = 5.0 * np.sqrt(mg / L_5)
    
    res_exact = asb.AeroBuildup(
        airplane=airplane,
        op_point=asb.OperatingPoint(velocity=v_trim, alpha=alpha_trim),
        xyz_ref=[req_cg_x, 0, cg_z]
    ).run()
    L = float(np.atleast_1d(res_exact['L'])[0])
    D = float(np.atleast_1d(res_exact['D'])[0])
    
    gamma = np.arctan2(D, L)
    sink = v_trim * np.sin(gamma)
    
    return float(v_trim), float(L/D), float(sink)


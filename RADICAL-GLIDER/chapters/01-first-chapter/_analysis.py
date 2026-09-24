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

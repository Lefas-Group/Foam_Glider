import aerosandbox as asb
import aerosandbox.numpy as np

def get_mass_properties_casadi(plane, area_density=0.1744, foam_thickness=0.005):
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


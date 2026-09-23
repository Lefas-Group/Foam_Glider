##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Vehicle

# Geometry parameters
wing_span = 0.508
semi_span = wing_span / 2
wing_x_le = 0.25
wing_z = 0.0381
root_chord = 0.0853
tip_chord = 0.0508
le_sweep = 10.5
dihedral_deg = 20

def make_cylinder(name, length, radius, xyz_c):
    return asb.Fuselage(
        name=name,
        xsecs=[
            asb.FuselageXSec(xyz_c=[-length/2, 0, 0], radius=radius),
            asb.FuselageXSec(xyz_c=[length/2, 0, 0], radius=radius),
        ]
    ).translate(xyz_c)

def get_airplane():
    airfoil = asb.Airfoil("naca0006")
    
    def make_flat_wing_rolled(name, roll_deg):
        x_le_tip = semi_span * np.tan(np.radians(le_sweep))
        
        xsec_left = asb.WingXSec(
            xyz_le=[x_le_tip, -semi_span * np.cos(np.radians(roll_deg)), -semi_span * np.sin(np.radians(roll_deg))],
            chord=tip_chord,
            airfoil=airfoil
        )
        xsec_root = asb.WingXSec(
            xyz_le=[0, 0, 0],
            chord=root_chord,
            airfoil=airfoil
        )
        xsec_right = asb.WingXSec(
            xyz_le=[x_le_tip, semi_span * np.cos(np.radians(roll_deg)), semi_span * np.sin(np.radians(roll_deg))],
            chord=tip_chord,
            airfoil=airfoil
        )
        
        return asb.Wing(
            name=name,
            symmetric=False,
            xsecs=[xsec_left, xsec_root, xsec_right]
        ).translate([wing_x_le, 0, wing_z])
    
    wing1 = make_flat_wing_rolled("Wing 1", dihedral_deg)
    wing2 = make_flat_wing_rolled("Wing 2", -dihedral_deg)
    
    fuse = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(xyz_c=[0, 0, 0], width=0.0145, height=0.001, shape=10),
            asb.FuselageXSec(xyz_c=[0.0508, 0, 0.0381/2], width=0.0145, height=0.0381, shape=10),
            asb.FuselageXSec(xyz_c=[0.3683, 0, 0.0889/2], width=0.0145, height=0.0889, shape=10),
            asb.FuselageXSec(xyz_c=[0.5080, 0, 0.0762/2], width=0.0145, height=0.0762, shape=10),
        ]
    )
    
    components = [fuse]
    
    engine_len, engine_rad = 0.1016, 0.0317/2
    gun_len, gun_rad = 0.1270, 0.0178/2
    
    for roll_deg, wing_name in [(dihedral_deg, "W1"), (-dihedral_deg, "W2")]:
        for sign, side in [(1, "R"), (-1, "L")]:
            y_e = sign * 0.05
            z_e = y_e * np.tan(np.radians(roll_deg))
            x_e = wing_x_le + abs(y_e) * np.tan(np.radians(le_sweep)) - 0.02
            components.append(make_cylinder(f"Engine_{wing_name}_{side}", engine_len, engine_rad, [x_e, y_e, wing_z + z_e]))
            
            y_g = sign * semi_span
            z_g = y_g * np.tan(np.radians(roll_deg))
            x_g = wing_x_le + abs(y_g) * np.tan(np.radians(le_sweep))
            components.append(make_cylinder(f"Gun_{wing_name}_{side}", gun_len, gun_rad, [x_g, y_g, wing_z + z_g]))
            
    return asb.Airplane(
        name="FliteTest X-Wing",
        xyz_ref=[wing_x_le + root_chord/4, 0, wing_z],
        wings=[wing1, wing2],
        fuselages=components
    )


##### Operating conditions


##### Derived quantities


##### The analysis

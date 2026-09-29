##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np


##### Vehicle

def get_airplane(wing_x_le=0.25, le_sweep=10.5, wing_inc=0.0):
    wing_span = 0.508
    semi_span = wing_span / 2
    wing_z = 0.0381
    root_chord = 0.0853
    tip_chord = 0.0508
    dihedral_deg = 20

    airfoil = asb.Airfoil("naca0006")
    
    def make_flat_wing_rolled(name, roll_deg):
        x_le_tip = semi_span * np.tan(np.radians(le_sweep))
        
        xsec_left = asb.WingXSec(
            xyz_le=[x_le_tip, -semi_span * np.cos(np.radians(roll_deg)), -semi_span * np.sin(np.radians(roll_deg))],
            chord=tip_chord,
            airfoil=airfoil,
            twist=wing_inc
        )
        xsec_root = asb.WingXSec(
            xyz_le=[0, 0, 0],
            chord=root_chord,
            airfoil=airfoil,
            twist=wing_inc
        )
        xsec_right = asb.WingXSec(
            xyz_le=[x_le_tip, semi_span * np.cos(np.radians(roll_deg)), semi_span * np.sin(np.radians(roll_deg))],
            chord=tip_chord,
            airfoil=airfoil,
            twist=wing_inc
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
            
    return asb.Airplane(
        name="FliteTest X-Wing",
        xyz_ref=[0, 0, 0],
        wings=[wing1, wing2],
        fuselages=components
    )


##### Operating conditions


##### Derived quantities


##### The analysis

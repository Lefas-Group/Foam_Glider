##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Mass and CG Analysis

def compute_mass_properties(
    airplane: asb.Airplane,
    battery_mass: float = 0.380,
    battery_x: float = 0.190,
    foam_density: float = 0.300,
) -> asb.MassProperties:
    """Compute the mass properties of the airframe, electronics, and battery."""
    # Main wing: top and bottom skins plus internal spar doubling
    w = airplane.wings[0]
    m_wing = (2 * w.area() + 0.070) * foam_density
    x_wing = float(w.aerodynamic_center(chord_fraction=0.45)[0])

    # Fuselage
    fuse = airplane.fuselages[0]
    m_fuse = fuse.area_wetted() * foam_density
    x_fuse = float(fuse.x_centroid_projected())

    # Horizontal stabilizer
    htail = airplane.wings[1]
    m_htail = 2 * htail.area() * foam_density
    x_htail = float(htail.aerodynamic_center(chord_fraction=0.5)[0])

    # Twin vertical fins
    vfin_r = airplane.wings[2]
    vfin_l = airplane.wings[3]
    m_vfin = 2 * (vfin_r.area() + vfin_l.area()) * foam_density
    x_vfin = float(vfin_r.aerodynamic_center(chord_fraction=0.5)[0])

    # Nacelles
    nac_r = airplane.fuselages[1]
    nac_l = airplane.fuselages[2]
    m_nac = (nac_r.area_wetted() + nac_l.area_wetted()) * foam_density
    x_nac = (nac_r.xsecs[0].xyz_c[0] + nac_r.xsecs[-1].xyz_c[0]) / 2

    # Underwing motor pods
    pod_r = airplane.fuselages[3]
    pod_l = airplane.fuselages[4]
    m_pods = (pod_r.area_wetted() + pod_l.area_wetted()) * foam_density
    x_pods = (pod_r.xsecs[0].xyz_c[0] + pod_r.xsecs[-1].xyz_c[0]) / 2

    # Foam total & glue allowance (25% of foam mass)
    m_foam = m_wing + m_fuse + m_htail + m_vfin + m_nac + m_pods
    x_foam = (
        m_wing * x_wing
        + m_fuse * x_fuse
        + m_htail * x_htail
        + m_vfin * x_vfin
        + m_nac * x_nac
        + m_pods * x_pods
    ) / m_foam
    m_glue = 0.25 * m_foam
    x_glue = x_foam

    # Powertrain & onboard radio (Flite Test Power Pack C Twin)
    pod_x_le = pod_r.xsecs[0].xyz_c[0]
    m_motors = 0.132  # 2x 66 g Radial 2216 / Power Pack C
    x_motors = pod_x_le
    m_props = 0.015
    x_props = pod_x_le - 0.010
    m_escs = 0.050
    x_escs = pod_x_le + 0.060
    m_servos = 0.048
    x_servos = 0.640
    m_rx = 0.010
    x_rx = 0.350

    # Battery (standard 4S pack placed in forward nose compartment, x in [0.12, 0.32] m)
    m_bat = battery_mass
    x_bat = battery_x

    components = [
        asb.MassProperties(mass=m_wing, x_cg=x_wing, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_fuse, x_cg=x_fuse, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_htail, x_cg=x_htail, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_vfin, x_cg=x_vfin, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_nac, x_cg=x_nac, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_pods, x_cg=x_pods, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_glue, x_cg=x_glue, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_motors, x_cg=x_motors, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_props, x_cg=x_props, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_escs, x_cg=x_escs, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_servos, x_cg=x_servos, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_rx, x_cg=x_rx, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
        asb.MassProperties(mass=m_bat, x_cg=x_bat, y_cg=0, z_cg=0, Ixx=1, Iyy=1, Izz=1),
    ]

    return sum(components)


def evaluate_targets(
    airplane: asb.Airplane,
    mass_props: asb.MassProperties,
) -> dict[str, dict[str, float]]:
    """Evaluate reconstructed aircraft against published targets."""
    span_model = float(airplane.wings[0].span(type="top"))
    span_target = 1.537
    span_err = (span_model - span_target) / span_target

    wing_x_le = float(airplane.wings[0].xsecs[0].xyz_le[0])
    cg_aft_le_model = (float(mass_props.x_cg) - wing_x_le) * 1000  # mm
    cg_aft_le_target = 64.0  # mm
    cg_err = (cg_aft_le_model - cg_aft_le_target) / cg_aft_le_target

    return {
        "Wingspan": {
            "model": span_model * 1000,
            "target": span_target * 1000,
            "unit": "mm",
            "error_pct": span_err * 100,
            "kind": "Given input",
        },
        "CG aft of wing LE": {
            "model": cg_aft_le_model,
            "target": cg_aft_le_target,
            "unit": "mm",
            "error_pct": cg_err * 100,
            "kind": "Derived",
        },
    }

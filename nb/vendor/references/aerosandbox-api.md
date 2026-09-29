# AeroSandbox: the surface this notebook uses

Signatures read from the INSTALLED package, so they are current. This is the
5% of AeroSandbox these notebooks actually call -- it is here so you do not
spend a turn asking for what you were always going to need.

It is NOT the whole library. Anything not below still exists: reach for
`api_search` when you know the concept but not the name, `api_list` to browse
an area, `api_signature` for a full method list. A name that is absent here is
absent from this page only, never from AeroSandbox.

### Airplane
Definition for an airplane.
(name, xyz_ref, wings, fuselages, propulsors, s_ref, c_ref, b_ref, analysis_specific_options)
  .draw_three_view(self, axs=None, style: Literal['shaded', 'wireframe'] = 'shaded', show: bool = True) -> numpy.ndarray  Draw a standard 4-panel three-view diagram of the airplane using Matplotlib back
### Wing
Definition for a Wing.
(name, xsecs, symmetric, color, analysis_specific_options, kwargs)
  .area(self, type: Literal['planform', 'wetted', 'xy', 'projected', 'top', 'xz', 'side', 'yz'] = 'planform', include_centerline_distance=False, _sectional: bool = False) -> float | list[float]  Compute the wing area, with options for various measurement methods (see `type` 
  .aspect_ratio(self, type: Literal['geometric', 'effective'] = 'geometric') -> float  Compute the aspect ratio of the wing, with options for various ways of measuring
  .mean_aerodynamic_chord(self) -> float  Compute the length of the mean aerodynamic chord of the wing.
  .mean_geometric_chord(self) -> float  Return the mean geometric chord of the wing (S/b).
  .span(self, type: Literal['xyz', 'xy', 'top', 'yz', 'front', 'xz', 'side', 'x', 'y', 'z'] = 'yz', include_centerline_distance=False, _sectional: bool = False) -> float | list[float]  Compute the span, with options for various ways of measuring this (see `type` ar
  .translate(self, xyz: Union[numpy.ndarray, Sequence[float]]) -> 'Wing'  Translate the entire Wing by a certain amount.
### WingXSec
Definition for a wing cross-section ("X-section").
(xyz_le, chord, twist, airfoil, control_surfaces, analysis_specific_options, deprecated_kwargs)
### Fuselage
Definition for a Fuselage or other slender body (pod, fuel tank, etc.).
(name, xsecs, color, analysis_specific_options, kwargs)
  .area_wetted(self) -> float  Return the wetted area of the fuselage.
  .fineness_ratio(self, assumed_shape: Literal['cylinder', 'sears-haack'] = 'cylinder') -> float  Approximate the fineness ratio using the volume and length.
  .length(self) -> float  Return the total front-to-back length of the fuselage.
  .translate(self, xyz: Union[numpy.ndarray, Sequence[float]]) -> 'Fuselage'  Translate the entire Fuselage by a certain amount.
  .volume(self, _sectional: bool = False) -> float | list[float]  Compute the volume of the Fuselage.
### FuselageXSec
Definition for a fuselage cross-section ("X-section").
(xyz_c, xyz_normal, radius, width, height, shape, analysis_specific_options)
  .xsec_area(self)  Compute the FuselageXSec's cross-sectional (xsec) area.
### Airfoil
An airfoil. See constructor docstring for usage details.
(name, coordinates, deprecated_keyword_arguments)
  .get_aero_from_neuralfoil(self, alpha: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM, Re: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM, mach: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM = 0.0, n_crit: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM = 9.0, xtr_upper: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM = 1.0, xtr_lower: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM = 1.0, model_size: str = 'large', control_surfaces: list['ControlSurface'] | None = None, include_360_deg_effects: bool = True) -> dict[str, int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM]  Compute this airfoil's aerodynamics at given operating conditions using NeuralFo
  .repanel(self, n_points_per_side: int = 100, spacing_function_per_side=<function cosspace at 0x10c63d4e0>) -> 'Airfoil'  Return a repaneled copy of the airfoil with cosine-spaced coordinates on each su
### KulfanAirfoil
An airfoil defined parametrically, using Kulfan (CST) parameters rather than coordinates.
(name, lower_weights, upper_weights, leading_edge_weight, TE_thickness, N1, N2)
### OperatingPoint
Abstract base class for all AeroSandbox objects.
(atmosphere, velocity, alpha, beta, p, q, r)
### AeroBuildup
A workbook-style aerodynamics buildup.
(airplane, op_point, xyz_ref, model_size, include_wave_drag)
  .run(self) -> dict[str, float | numpy.ndarray | list[float | numpy.ndarray]]  Compute the aerodynamic forces and moments on the airplane.
  .run_with_stability_derivatives(self, alpha=True, beta=True, p=True, q=True, r=True) -> dict[str, float | numpy.ndarray | list[float | numpy.ndarray]]  Compute the aerodynamic forces and moments on the airplane, and the stability de
### Opti
The base class for mathematical optimization.
(variable_categories_to_freeze, cache_filename, load_frozen_variables_from_cache, save_to_cache_on_solve, ignore_violated_parametric_constraints, freeze_style)
  .maximize(self, f: int | float | numpy.integer | numpy.floating | casadi.casadi.MX | casadi.casadi.DM) -> None  Set the objective function that the optimizer will attempt to maximize upon `Opt
  .minimize(self, f: int | float | numpy.integer | numpy.floating | casadi.casadi.MX | casadi.casadi.DM) -> None  Set the objective function that the optimizer will attempt to minimize upon `Opt
  .solve(self, parameter_mapping: dict[casadi.casadi.MX, float] | None = None, max_iter: int = 1000, max_runtime: float = 1e+20, callback: Optional[Callable[[int], Any]] = None, verbose: bool = True, jit: bool = False, detect_simple_bounds: bool = False, expand: bool = False, options: dict | None = None, behavior_on_failure: Literal['raise', 'return_last'] = 'raise') -> 'OptiSol'  Solve the optimization problem using CasADi with IPOPT backend.
  .subject_to(self, constraint: Union[int, float, numpy.integer, numpy.floating, numpy.ndarray, casadi.casadi.MX, casadi.casadi.DM, bool, Sequence[ForwardRef('Vectorizable | bool')]], _stacklevel: int = 1) -> casadi.casadi.MX | None | list[casadi.casadi.MX | None]  Initialize a new equality or inequality constraint(s).
  .value(self, *args) -> 'casadi::native_DM'  [INTERNAL]
  .variable(self, init_guess: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM | None = None, n_vars: int | None = None, scale: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM | None = None, freeze: bool = False, log_transform: bool = False, category: str = 'Uncategorized', lower_bound: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM | None = None, upper_bound: int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM | None = None, _stacklevel: int = 1) -> casadi.casadi.MX | float | numpy.ndarray  Initialize a new decision variable (or vector of decision variables).
### OptiSol
A solution to an optimization problem, as produced by `Opti.solve()`.
(opti, cas_optisol)
  .value(self, x: casadi.casadi.MX | numpy.ndarray | float | int | list | tuple | set | dict | typing.Any, recursive: bool = True, warn_on_unknown_types: bool = False) -> Any  Get the value of a variable (or a data structure) at the solution point.
### Atmosphere
Model an atmosphere, computing atmospheric properties as a function of altitude.
(altitude, method, temperature_deviation)
  .density(self) -> int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM  Return the density, in kg/m^3.
  .dynamic_viscosity(self) -> int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM  Return the dynamic viscosity (mu), in kg/(m*s).
  .speed_of_sound(self) -> int | float | numpy.integer | numpy.floating | numpy.ndarray | casadi.casadi.MX | casadi.casadi.DM  Return the speed of sound, in m/s.
### MassProperties
Mass properties of a rigid 3D object.
(mass, x_cg, y_cg, z_cg, Ixx, Iyy, Izz, Ixy, Iyz, Ixz)
### DynamicsPointMass2DSpeedGamma
Simulate point-mass dynamics in 2D, with velocity parameterized in speed-gamma space.
(mass_props, x_e, z_e, speed, gamma, alpha)
### DynamicsRigidBody2DBody
Simulate rigid-body dynamics in 2D, with velocity parameterized in body axes.
(mass_props, x_e, z_e, u_b, w_b, theta, q)

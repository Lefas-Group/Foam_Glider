# AeroSandbox gotchas

API traps and solver behaviour. Read before writing dynamics, optimization or
mass-properties code.

## Return types

- **`float()` on a shape-`(1,)` result raises `TypeError`.** `AeroBuildup`
  returns arrays even for a scalar `alpha`, so `float(aero["CLa"])` fails with
  `only 0-dimensional arrays can be converted to Python scalars`. Index first:
  `float(aero["CLa"][0])`. Same for `RegularGridInterpolator` output.
- `op_point.reynolds(c)` returns a **scalar** when `velocity` is scalar, even if
  `alpha` is a vector — indexing it raises `IndexError`.
- **Cost is per call, not per point.** `AeroBuildup` is fully vectorized: 61
  angles of attack cost about the same as one (~40 ms here), because fixed
  overhead dominates. Sweep in one vectorized call rather than looping.
  `run_with_stability_derivatives()` costs ~5× a plain `run()`, since it
  finite-differences over several perturbations.

## Geometry and aerodynamics

- `AeroBuildup` gets its section data from NeuralFoil. For flat foam, name a
  symmetric section of the right thickness (`asb.Airfoil("naca0007")` for 5 mm
  on a 70 mm chord) rather than inventing coordinates. It stands in for a flat
  plate, which stalls earlier and more softly.
- Dihedral is a `z` offset on the tip `WingXSec`, with `symmetric=True` on the
  `Wing`.
- `Airplane(xyz_ref=…)` sets the moment reference. **It is not the CG unless you
  made it so.**
- `draw_three_view` builds its own figure, so `fig-width`/`fig-height` cell
  options do nothing — it emits ~1896 px square regardless. Only CSS constrains
  it (see `quarto.md`).
- At chuck-glider scale, chord Reynolds number is 1–4 × 10⁴ and the polar moves
  materially with airspeed.

## Mass properties

- `MassProperties` instances **sum**, applying parallel-axis terms automatically.
  Use `mass_properties_from_radius_of_gyration()` for distributed components
  (booms, fuselages) and the plain constructor for point masses.
- It computes the CG from the components you give it — which will not be the CG
  you assumed unless the components actually put it there. Solve for the input
  that makes them agree.
- The 2D rigid-body classes only use `mass`, `x_cg` and `Iyy`, but a singular
  inertia tensor causes trouble; set `Ixx = Izz = 1` as harmless placeholders.

## Dynamics and Opti

- **`dyn.add_moment()` applies moments about the CG**, while `AeroBuildup`
  reports them about `airplane.xyz_ref`. If those two points differ, the aero
  moment is applied at the wrong station and nothing warns you. Make them
  coincide.
- `dyn.op_point` carries `p, q, r` from the state into `AeroBuildup`, so pitch
  damping comes free — no manual `Cmq` term needed. A frozen-at-trim `Cmq`
  agrees with it to <1% below ~3 rad/s and diverges ~10% by 5 rad/s.
- **A problem with the initial state pinned and no objective is square**, so
  `opti.solve()` simply integrates the equations of motion. Ground contact
  becomes `dyn.z_e[-1] == 0` with the final time a free variable.
- **`AeroBuildup` returns NaN outside its valid range**, and a collocation solver
  will explore there. Bound the states — `w_b < u_b * tan(alpha_max)`, a
  `lower_bound` on `u_b` — or the solve dies with
  `NaN detected for output g`. If the true trajectory needs angles outside the
  aero model's range, the bounded problem is *infeasible*: that is the model
  telling you the answer is out of envelope, not a solver-tuning problem.
- **A failed `opti.solve()` raises `RuntimeError` and costs ~10× a success**
  (146 s vs 12 s measured here) as IPOPT thrashes to `max_iter`. Wrap it, and
  think before putting a known-failing case in an entry.
- Report solve cost with `sol.stats()["iter_count"]`, `opti.nx` and `opti.ng`.
- Cost is roughly **linear in the number of nodes** — the sparse-Jacobian
  behaviour the book describes — so refinement checks are cheap.

## The vendored book

`references/aerosandbox-book/` is "The AeroSandbox Book" by Peter Sharpe,
vendored as text to read, not to execute — the `.qmd` files import a `_common`
module that is not included, so they will not render standalone.

| File | Covers |
|---|---|
| `11-optimal-control.qmd` | Direct collocation, `derivative_of` / `constrain_derivative`, free final time, convergence checks |
| `12-dynamics-stack.qmd` | The `Dynamics` classes, axis systems, `dyn.op_point`, worked glide and quadcopter examples |
| `07-atmosphere-propulsion-weights.qmd` | `Atmosphere`, `OperatingPoint`, weight buildups, `MassProperties` |
| `02-robust-optimization-models.qmd` | Scaling and initial-guess hygiene for problems that fail to converge |
| `06-aircraft-aerodynamics.qmd` | What `AeroBuildup` models and when to trust it |

Upstream, to refresh the copy: <https://github.com/peterdsharpe/AeroSandbox>

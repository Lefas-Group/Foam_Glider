# AeroSandbox gotchas

API traps and solver behaviour. Read before writing dynamics, optimization or
mass-properties code.

## Don't reimplement what the library has

Look it up with the `library-explorer` MCP server before writing a calculation:
`search` when you know the concept but not the name, `list_classes` /
`list_functions` to browse, then `get_methods` on the class. It introspects the
installed version, so it is always current — don't substitute your own `dir()`
dump. Note `search` is lexical: `"static margin"` finds nothing because no
aerosandbox docstring uses that phrase, though `run_with_stability_derivatives`
computes what you want.

Every row below was written by hand in this notebook before someone noticed the
library already had it:

| instead of | use |
|---|---|
| `2 * np.trapezoid(chords, eta * b/2)` | `Wing.area()` |
| `b ** 2 / S` | `Wing.aspect_ratio()` |
| `S / b` | `Wing.mean_geometric_chord()`, or `mean_aerodynamic_chord()` for a true MAC |
| a finite difference over `beta` | `run_with_stability_derivatives()` → `Cnb`, `CYb`, `Clb`, `x_np_lateral` |
| `xyz_ref[0] - Cma / CLa * c_ref` | the same call → `x_np` |
| anything about a fuselage's size | `Fuselage.volume()`, `.area_wetted()`, `.length()`, `.fineness_ratio()` |

Two results that look like bugs and are not:

- **`Wing.span()` defaults to `type="yz"`** — the true panel length, *including*
  the dihedral rise, not the projected tip-to-tip span. A wing meant to span
  300 mm read 308.3 mm this way, which is how a real geometry error surfaced:
  flat-pattern chords had been placed at projected stations, so the model needed
  a 308 mm pattern to build a 300 mm glider.
- **`Wing.area()` includes twist.** A stabilizer at `twist=-2°` lofts 0.06%
  larger than the flat pattern it is cut from. Below the tracing uncertainty
  here, but it is why `area()` and a flat integral disagree on a twisted surface.

**`x_np` is a point derivative, not a band average.** `run_with_stability_derivatives()`
finite-differences over a hard-coded 0.001 rad. At chuck-glider Reynolds numbers
`Cm` against `CL` is genuinely curved, so `x_np` varies with the angle you take
it at — 147 to 197 mm across 0–8° in one case, which is real curvature and not
noise. Fitting a line over a stated band is a different, equally defensible
answer. Whichever you use, state the angle or the band.

## Return types

- **`float()` on a shape-`(1,)` result raises `TypeError`.** `AeroBuildup`
  returns arrays even for a scalar `alpha`, so `float(aero["CLa"])` fails with
  `only 0-dimensional arrays can be converted to Python scalars`. Index first:
  `float(aero["CLa"][0])`. Same for `RegularGridInterpolator` output.
- `op_point.reynolds(c)` returns a **scalar** when `velocity` is scalar, even if
  `alpha` is a vector — indexing it raises `IndexError`.
- **Cost is per call, not per point.** `AeroBuildup` is fully vectorized, so
  alpha is nearly free: on the McEagle-300, 1 angle costs 350 ms, 161 cost
  480 ms and 641 cost 830 ms. Sweep in one vectorized call rather than looping.
  `run_with_stability_derivatives()` costs ~5× a plain `run()`, since it
  finite-differences over several perturbations.
- **The corollary: the number of calls is the entire budget.** If a point is
  free and a call is not, then the thing to count is calls — and the usual place
  they hide is a loop whose trip count was chosen rather than measured. An
  iteration runs to a tolerance, with a max-iteration guard that *raises*; it
  does not run to a round number someone picked. `trim()` in the McEagle chapter
  was written `for _ in range(60)` around a fixed point that converges in 9–13,
  which is ~20 s of solving per call, thrown away, at a dozen call sites. The
  vectorization advice above did not catch it: `trim()` obeys that rule
  perfectly, sweeping 161 alphas in one call — and then makes 60 such calls. The
  rule governs the inner dimension; this one governs the outer.
  The notebook already had the right pattern when `trim()` was written —
  `01-aerobuildup-bfg`'s launch-speed entry solves the same lift-equals-weight
  fixed point with `for _ in range(40)` plus `if abs(V_new - V) < 1e-5: break`
  and 50% under-relaxation, three weeks earlier. Copy that shape: a trip cap as
  a guard, a tolerance as the actual exit.
- **Cost scales with spanwise strips, not with the aircraft's complexity as you
  might judge it by eye.** Count them with
  `sum((len(w.xsecs) - 1) * (2 if w.symmetric else 1) for w in airplane.wings)`
  — that is exactly how many times `compute_section_aerodynamics` runs per call.
  Measured here: **BFG, 5 strips, 41 ms; McEagle-300, 47 strips, 350 ms** —
  9.4× the strips for 8.5× the time. Always quote a timing with the aircraft it
  was measured on. An unlabelled figure reads as a property of `AeroBuildup`
  when it is a property of the geometry, and that is what once made a
  60-iteration loop look affordable.
- **Where the time actually goes**, so nobody optimizes the wrong end: only
  ~13% of a call is NeuralFoil's network. The rest is AeroSandbox re-deriving
  the same per-strip geometry and atmosphere every time — Kulfan refits of an
  unchanged airfoil, thickness lookups, sea-level density. It is upstream
  structure, not something to work around. In particular, **shrinking an alpha
  grid buys nothing**; only cutting calls does.

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

`aerosandbox-book/` is "The AeroSandbox Book" by Peter Sharpe, vendored as text
to read, not to execute — the `.qmd` files import a `_common` module that is not
included, so they will not render standalone. Filenames say what each chapter
covers; `SKILL.md` names the ones that come up most.

Upstream, to refresh the copy: <https://github.com/peterdsharpe/AeroSandbox>

## Where "compute both and compare" caught something

SKILL.md carries the three rules; these are the cases that earned the third one.
Neither was caught by reading the code.

- **`Wing.area()` against a traced integral** exposed a wing built 2.75% too
  large.
- **`Fuselage.volume()` against a slab volume** exposed a mass trap: a
  super-ellipse under-fills a rectangular foam slab by up to 22%, so fuselage
  mass in the McEagle chapter deliberately does *not* come from `volume()`. The
  comment saying so, at the point of deviation, is the model working correctly.

Both agreements are now one-line assertions in the chapters, i.e. regression
tests that cost nothing to keep.

## Using library-explorer

Three tools, in the order that works:

1. **`search(query)` first**, when you know what you want but not where it lives.
   It matches full docstrings across functions, classes **and methods**, which is
   the only way to find things whose name gives no clue: `search("neutral")`
   returns `AeroBuildup.run_with_stability_derivatives`. Matching is lexical — a
   no-hit result means those *words* are absent, not that the capability is.
   Retry with one distinctive word before concluding anything.
2. **`list_classes()` / `list_functions(area=…)`** to browse when you don't know
   what to search for. Both group by area (`geometry`, `aerodynamics`,
   `dynamics`, `weights`, …); `library/*` and `tools/*` are mostly
   transport-aircraft correlations and plotting, rarely what a small glider needs.
3. **`get_methods(class)` / `get_docstring(path)`** to go deep once you have a
   name. Signatures live here, never in the listings.

## Trajectories: use `dyn.op_point`, and pick the class by conditioning

**`dyn.op_point` is the bridge from dynamics to aerodynamics.** Every `Dynamics`
instance exposes it, rigid-body classes included, and it derives velocity, alpha
*and* the body rates from the state:

```python
aero = asb.AeroBuildup(airplane=airplane, op_point=dyn.op_point,
                       xyz_ref=[total.x_cg, 0, z_ref]).run()
dyn.add_force(*aero["F_b"], axes="body")     # or F_w with axes="wind"
dyn.add_moment(My=aero["M_b"][1], axes="body")
```

Assembling that operating point by hand is where three separate bugs lived in
this project, each of which produced a plausible trajectory rather than an error:
the pitch rate was omitted, so an aircraft with `Cmq = -12.7` had no damping at
all; a wind-to-body rotation was written out longhand; and a tabulated surrogate
was built about a different CG than the simulation used -- 16 mm, 19% of chord,
and since `Cm` is measured ABOUT that point the pitching moment was wrong from
the first step. `op_point` removes all three by construction.

One trap: it builds an `Atmosphere` at the instance's own altitude. If the
chapter's stated condition is a fixed one, pin it back (`op = dyn.op_point;
op.atmosphere = ATMOSPHERE`) or durations shift by ~0.1%.

**Collocation vs time-marching is a conditioning question, not a taste one.**
Measured on a 300 mm hand-launched glider:

| | result |
|---|---|
| point-mass collocation, design variables free | converged, 113 s, 184 iters, exact gradients |
| rigid-body collocation, tumbling flight | infeasible, even seeded from a converged RK4 trajectory |

Collocation states the whole trajectory as one algebraic system, so it needs the
flight to be *findable* from a guess. An uncontrolled aircraft thrown well above
its trim speed loops and tumbles; that map from initial conditions to final state
is chaotically sensitive, the constraint Jacobian is ill-conditioned, and no
storyboard fixes it -- seeding from an RK4 solution still failed, in 11 s rather
than 140 s. Time-march that case. Collocate the smooth one, where the payoff is
large: symbolic aero over all nodes in one call, and design variables carried in
the same solve as the trajectory, with no surrogate anywhere.

**A point mass cannot loop.** With `alpha` a control it trims instantly, so it
reports a longer flight than the rigid body (6.0 s against 3.8 s here) and the
gap is exactly the launch transient. Constrain `aero["Cm"] == 0` at every node to
keep it honest for a free-flight glider -- alpha is then whatever the airframe
trims at, not a pilot's choice -- and report the launch-to-trim speed ratio,
which is the diagnostic for whether the omission matters.

### Collocation is fast, but the speed is not the answer

Measured on the glider design solve, and worth knowing before trusting a first
converged result:

- **It is multi-modal.** Four alpha boxes differing only in bounds nobody had a
  physical reason to place exactly gave 3.7, 4.2, 5.1 and 5.6 s. A single solve
  lands in whichever basin it started nearest, so vary the START at FIXED
  bounds and report the spread -- that is what a hundred-second solve is *for*.
- **A bound can be load-bearing rather than merely binding.** Widening the alpha
  box did not relax the answer, it made the problem infeasible. So "is the
  optimum on a bound?" is not the whole check; "does it still solve when the
  bound moves?" is the other half.
- **Refinement can fail rather than refine.** A 4-start multistart gave 4.37 s at
  n=40 and 4.04 s at n=60 -- 8% apart -- and n=80 did not converge at all where
  n=40 did, so the usual grid-convergence study was not available and the answer
  stayed a 40-node answer. Say so rather than quoting the number that converged.

# Lookup tables and surrogates

When replacing a computed surface with a cached one is worth it, and the ways it
goes wrong. Every number here was measured, on the 30 cm foam glider.

## Cache at the level whose inputs do not move

The question is not "is this expensive?" but **"what does it actually depend
on?"** Write the list down. If a design variable is on it, you are at the wrong
level and the table will need rebuilding every iteration.

One chapter cached whole-*aircraft* coefficients over (α, speed). That works
while geometry is fixed and is worthless the moment geometry is a design
variable, because the input list quietly grows to include all of them — about
seven dimensions. The 2D *section* polar underneath depends on only (α, Re, t/c),
whatever the design does, and t/c enters as an interpolant input so gradients
still flow through it.

The same move fixes a whole class of bug. The aircraft-level table carried a CG,
and was once built about a different CG than the simulation used — 16 mm, 19% of
chord, and every pitching moment wrong from the first step. A section-level table
holds no CG and no aircraft geometry, so induced drag, tail, downwash and balance
all stay exact in `AeroBuildup` and that failure cannot recur.

## Cut dimensions by finding the real parameterisation

Check whether the family is narrower than it looks. The foam plate is *exactly* a
one-parameter family: all eight Kulfan weights scale linearly with t/c, verified
to `0.00e+00` against a direct fit at t/c 0.05 and 0.20. That is what makes three
dimensions sufficient rather than eight.

A **fixed** standard airfoil removes a dimension again — 2-D in (α, Re), built
once and never invalidated. But check what the coupling was doing first: here t/c
is forced by a fixed 5 mm stock over a varying chord, and pinning it deletes the
penalty that sets the aspect ratio, reading 2.6× optimistic at AR 12. Cheaper to
compute and wrong about the answer.

## Validate at nodes *and* at midpoints, per axis

A B-spline is **exact at its own grid nodes**. So the two tests answer different
questions, and only doing the first tells you nothing:

- error at a node → the plumbing is wrong (ordering, indexing, units);
- error at a midpoint → the grid is too coarse *on that axis*.

Vary one axis at a time. Doing so localised all of one table's error to Reynolds
— 5.9% at a midpoint, against 0.0% for α and 0.1% for t/c — which said exactly
which axis to refine. Going 10 → 30 Reynolds points took the worst case to 0.04%
while leaving the other two alone. Refining everything would have cost far more
and fixed the same thing.

## Costs worth knowing before building

- **Sampling is nearly free; fitting is not.** 41,040 points sampled in 2.2 s (9
  NeuralFoil calls — cost is per call), then 119 s to fit. Fit cost is
  superlinear: 34 s at 16,720 points, 119 s at 41,040. Size the grid deliberately
  rather than sampling generously and discovering the fit afterwards.
- **Serialise the fit.** `casadi.Function.save`/`load` round-trips in 0.16 s /
  0.06 s, bit-exact, so an expensive fit is paid once ever rather than once per
  session.
- **`casadi.interpolant('bspline')` keeps exact Hessians** — MX-callable, with a
  computable dense Hessian. That matters: it is the only way to get the speed of
  a limited-memory Hessian without giving up the exact one.

## A surrogate that moves the optimum is a fidelity change

Not a speed change, and it must be reported as one. Two measured cases:

- a limited-memory Hessian ran 4.2× faster and landed in a **different** optimum;
- a section-spline cache cut per-iteration cost ~21× but took 2.5× more
  iterations (192 → 481, near the 500 cap) and also landed elsewhere.

Neither is wrong, but neither is "the same answer, faster". Report the optimum it
reached, not only the time it took.

## Mirror the model's own choices

A cache must reproduce what the model *does*, not what seems physically sensible.
Chapter 01 builds **one** section from the root chord and reuses it on tail and
fin; a cache giving each surface its own t/c doubled CD at AR 10, where the tail
chord is smallest. The tell was that low-α agreement was fine and the error grew
with surface size mismatch.

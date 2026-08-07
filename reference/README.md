# Reference material

Third-party material kept on disk for reference. **The contents of this
directory are gitignored** — only this README is tracked. Nothing here is my
work, and none of it is needed to render the notebook.

## `aerosandbox-book/`

"The AeroSandbox Book" by Peter Sharpe — a Quarto book documenting AeroSandbox.
Most useful chapters for this project:

| File | Covers |
|---|---|
| `11-optimal-control.qmd` | Direct collocation, `derivative_of` / `constrain_derivative`, free final time, convergence checks |
| `12-dynamics-stack.qmd` | The `Dynamics` classes, axis systems, `dyn.op_point`, worked glide and quadcopter examples |
| `02-robust-optimization-models.qmd` | Scaling and initial-guess hygiene for problems that fail to converge |
| `_common.py` | The book's shared plotting style, which `notebook/_setup.qmd` follows |

Upstream: <https://github.com/peterdsharpe/AeroSandbox>

The bulk of the 27 MB is `_freeze/`, Quarto's execution cache. If it is ever
missing, the book still renders — it just has to re-run all the AeroSandbox
code first.

## `designs/`

Assorted AeroSandbox design scripts collected as worked examples: `RC_glider/`,
`simplified_glider/`, `solar_plane/`, `transport_plane/`, and `miscellaneous/`
(vendored copies of AeroSandbox geometry and VLM source).

Note that **none of these do trajectory optimization** — checked on 2026-08-04.
They are all steady-state point-design optimizations: a single `asb.Opti()` with
one operating point and a force balance. `transport_plane/design_opt.py` looks
closest, but its `DynamicsPointMass2DSpeedGamma` is used at a single cruise
condition and its range comes from the closed-form Breguet equation, not an
integrated trajectory.

`solar_plane/docs/*.md` are readable walkthroughs of that script.

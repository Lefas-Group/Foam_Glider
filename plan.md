# Probes in a persistent kernel

Written 2026-09-30. Replaces the earlier plan, which proposed a solve cache and
rejected a kernel; that rejection rested on a leaked-monkeypatch scenario that
restart-on-kill removes, and on a simplicity claim that did not survive looking
at what each end state has to carry. Nothing here is implemented yet.

Evidence throughout is one run:
`RADICAL-GLIDER/_scratch/runs/20260930-074952-19aa` — *"Does replacing the
hand-rolled mass geometry with `Wing.area()` and `Fuselage.volume()` move any
answer in this chapter?"*, 39 turns, 258.8 s of a 300 s probe pool, committed as
`464848c`.

## The problem

Every probe is a fresh `uv run python probe.py` subprocess. Nothing survives it.
Where that run's pool went:

| | seconds | share |
|---|---:|---:|
| Solves that produced an answer used once | ~119 | 46% |
| Solves re-run because an earlier result was lost or discarded | 50–65 | ~20% |
| The killed probe at turn 34 | 62 | 24% |
| Graph build + IPOPT setup inside each optimiser call | ~40 | 15% |
| Process start + AeroSandbox import + chapter exec | ~36 | 12% |

(Rows overlap — the killed probe contains solve time — so they do not sum.)

Less than half the pool bought an answer used once. Three symptoms, one cause:

- **Results are discarded.** `optimize_geometry_for_sink_rate(get_airplane)` was
  solved for the identical baseline at turns 26, 40 and 52.
- **A kill destroys everything.** Turn 34 printed its entry-03 result at ~20 s
  and its entry-04 result at ~45 s, then died at 62 s. Both were lost — `os._exit`
  skips stdio flushing and `capture_output` makes stdout a block-buffered pipe.
  Turns 40 and 42 re-ran four solves to recover them.
- **Every probe re-pastes its setup.** A 30-line helper plus a
  `__globals__` lookup, repeated verbatim in six consecutive probes. That
  boilerplate is part of why turn 34 overran.

The run ended with 41 s left and two of the chapter's nine entries never
re-solved under the new mass model. Pool waste became scope loss.

## The change

One IPython kernel per run, started on the first probe, living until the run
ends. `run_probe` sends the model's question as a cell instead of writing and
spawning a script. Names survive between probes.

Nothing in the `probe` tool's contract changes for the model except one addition:
each result says what is currently held, and `reset=True` starts clean.

## Four rules that make it safe

These are not optional extras; each one closes a specific failure this run
exhibited or would have exhibited.

**1. A budget kill kills the kernel, not the cell.**

`budgets.py` already records the measurement that settles this: *"A signal cannot
stop a CasADi solve — it lands when the C call returns, 1.15 s measured against a
0.3 s limit. Killing the process can, at the cost of whatever was in memory."*
So `KeyboardInterrupt` into a running solve is not an option, and the kill stays
a process kill followed by a restart.

The safety consequence is the important half. Every probe from turn 26 onward did
`optimize_geometry_for_sink_rate.__globals__['_get_mass_properties_casadi'] =
get_mass_props_library` and restored it afterwards. **Turn 34 was killed with the
patch installed.** Under a kernel that survives its own kill, turn 40's "orig"
baseline would silently have been the library model and the entry would have
shipped wrong with no error anywhere. Restart-on-kill makes that impossible: a
kill degrades exactly to today's behaviour.

**2. A chapter-source change restarts the kernel.**

The run edited `_analysis.py` at turn 56 and probed it at turn 58. Hash
`_model.py`, `_analysis.py` and `_notebook.py` before each probe; on a change,
restart and say so in the result. ~5 lines, and it removes the whole staleness
class.

**3. `_IN_KERNEL` stops standing in for "am I a render".**

`_notebook.py` uses it as that proxy in two places, and both currently disarm
under a kernel:

- `:280` — `ipopt.max_wall_time` is set only outside a kernel. The comment is
  explicit: *"WALL TIME ONLY OUTSIDE A KERNEL — that is, in a probe and not in a
  render."* The reason is sound and must be preserved: a render killed on wall
  time is handed to the model as an error to fix, so a solve slowed by a
  neighbouring process presents as a bug in a correct entry, and the spurious fix
  ships. (`max_runtime` → `ipopt.max_cpu_time` is set in both cases and survives.)
- `:407` — the probe watchdog arms only outside a kernel.

Run probes in a kernel without splitting this and **both wall-clock defences
silently vanish.** Replace the proxy with an explicit signal — `NB_PROBE=1` in
the kernel's environment, read into a module global by the init cell — so
"probe" and "render" are distinguished by what they are rather than by how they
happen to be hosted.

**4. A chapter change restarts the kernel.**

`chapter` is a per-probe argument today; a kernel binds one. Runs are
single-chapter in practice, so restart on change rather than maintaining a
kernel per chapter.

## Components

**`nb/tools/probe_init.py` — new, ordinary module, not vendored.**

The bootstrap `_probe_base.py` performs today: resolve the chapter from
`$NB_CHAPTER`, then `exec(compile(path.read_text(), str(path), "exec"))` over
`_notebook.py`, `_model.py`, `_analysis.py`. The `compile()` with a real path is
load-bearing and must be carried over verbatim — a bare `exec()` of file text
labels every function `<string>`, `inspect.getsource` then raises `OSError`, and
`show_source()` and `api()` go silent. This run leaned on `inspect.getsource`
four times.

The runner reads this module's source and sends it as the kernel's init cell. A
real file, so it is linted and formatted like everything else — not a Python
program living in a string literal.

`_scratch/_probe_base.py` is then deleted, along with its rule-11 entry and its
`.gitignore` exception. It has exactly one consumer once the kernel lands: the
hand-probe path it was written for is not used. **`.claude/skills/design-notebook/SKILL.md`
references it in three places and must be updated in the same change** — leaving
a skill documenting a deleted file is how the next session gets confidently lost.

**`nb/tools/kernel.py` — new.**

Start, send-and-collect, health check, restart, shutdown. `jupyter_client` and
`ipykernel` are already installed (8.9.1 / 7.3.0) via the core `jupyter`
dependency Quarto needs, so nothing new is added to `pyproject.toml`.

Kernel cwd is the run directory, as the subprocess's is today — a probe that
saves a figure writes a relative filename and it must land beside its own run.

Collection reads iopub until idle, accumulating `stream` (stdout and stderr) and
`error` payloads into the single string `run_probe` already returns. Output
arrives as it is produced, so **partial output on a kill is free rather than a
bug to fix**.

**`nb/tools/probe.py` — rewritten around the kernel.**

Deleted: `PREAMBLE`, the `sys.path` insert, the per-run `probe.py` write,
`subprocess.run` with its `stdin=DEVNULL` workaround (and the SIGTTIN incident
that forced it), the `TimeoutExpired` branch and its partial-output salvage, and
the double-timeout arrangement.

Kept unchanged, because they operate on the returned output string and the
session: `_inputs_notice`, `_scope_hint`, the budget line, the `ENTRY_CEILING`
notice, `budgets.aero_cost` parsing (`aero_report()` still prints the same line),
`session.take_probe_budget` / `record_probe` / `record_cost`, and `tail`.

Added: the four restart triggers above, and a held-names line on each result.

**`nb/vendor/notebook.py` — loses the watchdog.**

`_probe_budget()`, `_probe_guard_armed`, `_probe_watch`, `_probe_too_long`, the
`faulthandler` arming and the `NB_PROBE_BUDGET` env channel: ~60 lines, dead once
no probe runs in its own process. The budget timer moves to the runner, which is
the only place that knows the pool. The file stays vendored — render needs the
rest of it — so the change propagates to every notebook.

Keep `faulthandler.dump_traceback_later(PROBE_SILENCE)` in the init cell. Saying
*where* a probe is stuck, from its own thread and through a C call, is worth
keeping and does not depend on who decides to kill it.

**`nb/vendor/lint.py` — rule 11 covers one file instead of two.**

**`nb/budgets.py` — the four-layer docstring becomes three.** Layer 2 is gone;
layer 3 stops being a backstop above a watchdog and becomes the enforcement
itself, so `WATCHDOG_HEADROOM` shrinks to whatever covers kernel start and
collection rather than a 15 s polling interval.

## What the model sees

Two additions to the `probe` schema, and nothing else:

- Each result ends with what is held: `[kernel: holding s1_orig, p1_orig,
  get_mass_props_library (+6 more). Reuse them; re-deriving one costs a solve.]`
  Without this the win is unrealised — the saving is model-directed, and a model
  that does not know state persists will not reach for it.
- `reset=True` to start from a clean namespace.

And when the runner restarts on its own, the result must say so loudly:
`[kernel restarted — _analysis.py changed since the last probe. Nothing is
held.]` A silent restart is a wrong-answer generator.

## Pros

- **Removes the largest waste with no reconstruction problem.** The alternative —
  a solve cache — has to persist what `optimize_geometry_for_sink_rate` returns:
  an `asb.Airplane` with ten monkey-attached floats. Pickle is brittle across
  AeroSandbox versions; the clean boundary (`Opti.solve`) has no stable key,
  since what you would hash is a CasADi graph; and storing the floats to rebuild
  the object requires knowing each helper's return shape, which makes it a
  convention the model must follow. A kernel does not tear the object down, so
  none of that exists.
- **Recovers the partial-output loss as a property, not a patch.** iopub streams.
- **Removes the re-pasting.** A helper defined once stays defined — the boilerplate
  that pushed turn 34 over its budget.
- **~36 s of process start and import**, unconditionally, on every run.
- **Net simplification.** ~60 vendored lines plus the subprocess plumbing deleted;
  one fewer vendored file; rule 11 halved. The bootstrap versions with `nb`
  instead of being copied into four notebooks, two of which have already drifted.
- **Failure mode is "lost state, re-run"**, not "confidently wrong" — provided
  rules 1 and 2 hold.

## Cons and risks

- **The safety knob and the benefit knob are the same knob.** Residual hidden
  state comes from a probe that *raises partway* — turn 22 did exactly that —
  leaving half-applied state behind with no kill and no restart. Reset-by-default
  removes the risk and the benefit together. This plan leans to carrying by
  default, and pays for it with visibility (the held-names line) rather than with
  resets. It is a judgement, not a proof.
- **The saving is model-directed.** The cache would have been automatic; this is
  not. If the model does not reuse carried names, the kernel recovers only the
  ~36 s of startup. **This is the number to measure before building anything
  further.**
- **Kernel lifecycle is the failure-prone kind of complexity** — half-dead
  kernels, zombies when the runner dies, a restart racing a run that holds
  `run.lock`. Bounded to one module, but it is where the long tail will be.
- **It does not touch the ~40 s of graph build and IPOPT setup**, the largest
  per-probe overhead after solving. That row wants a warm start in the helper,
  and is out of scope here.
- **Rule 3 is a genuine trap.** Getting the kernel working and forgetting the
  `_IN_KERNEL` split leaves a system that looks correct and enforces no wall
  clock. Write that test first.
- **`_notebook.py` propagation.** `aircraft-notebook` and
  `optimised-glider-notebook` already differ from `nb/vendor/notebook.py`. They
  will surface as rule 11 failures the moment this propagates. Decide up front
  whether they are resynced or dead.

## Sequence

0. **Flush, now, as a stopgap.** `PYTHONUNBUFFERED=1` in the probe env plus
   `sys.stdout.flush()` before `os._exit(9)`. One line of real change; protects
   every run between now and the kernel landing; deleted when it arrives. Do not
   let it delay anything.
1. **Split `_IN_KERNEL`** into "am I a render" and "am I in a kernel", with a test
   that a probe still gets `ipopt.max_wall_time` and a render still does not.
   Ships safely on its own, before any kernel exists.
2. **`probe_init.py`**, still executed by the subprocess path. Delete
   `_probe_base.py`, its rule-11 entry, its `.gitignore` exception; update
   `SKILL.md`. Provable with the existing runner — a probe that can still call
   `show_source()` proves `compile()`-with-path survived.
3. **`kernel.py` + `run_probe` rewrite**, with restart-on-kill and
   restart-on-source-change from the first commit, not added after.
4. **Delete the vendored watchdog**; propagate `_notebook.py`; resolve the two
   drifted notebooks.
5. **Measure, then decide what is next.**

## What to measure

Baseline is the run above: 258.8 s pool, 18 probes, ~2 s per trivial probe,
8–13 s of non-solve overhead per solving probe, and three solves of the identical
baseline configuration.

After: probes per run, pool spent, and — the one that decides whether any further
work is justified — **how many probes reuse a name carried from an earlier probe.**
If that number is near zero the kernel is worth only its startup saving, and the
automatic-but-harder solve cache comes back onto the table. If it is high, nothing
further is needed.

## Deferred

- **Solve cache.** Superseded unless the reuse measurement disappoints. Its
  serialization core is the reason it is not the primary path.
- **`keep(...)` explicit value pickling.** The kernel subsumes it.
- **Warm-starting the optimiser** to attack the ~40 s graph-build row. Separate
  work, larger prize, touches chapter code rather than tooling.

## Out of scope, but noted

- The chapter now carries two near-identical 40-line optimisers, because
  `declare_refactor`'s re-solve cost pushed the run into copy-paste rather than
  adding a `mass_fn=` parameter. A real cost of the refactor rule, and a separate
  decision.
- Entries 07 and 09 were never re-solved under the library mass model. Whether
  `464848c` needs strengthening is a notebook question, not a tooling one.

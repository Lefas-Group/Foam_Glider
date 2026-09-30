# Scratch probe mechanics

Your instructions carry the rule — probe before writing an entry, and use the
`probe` tool rather than writing a script. This is the machinery, read when a
probe misbehaves or a figure is needed.

## How a probe runs

Every probe for a run goes to ONE kernel, started on the first probe and kept
until the run ends. `nb/tools/probe_init.py` is its first cell: it execs
`_notebook.py`, `_model.py` and `_analysis.py` into the namespace your probes
then run in. There is no file to edit and nothing to import — you send the
question, and the chapter is already there.

**Names survive between probes.** What one probe assigns, the next can use. This
is the single largest per-entry saving available, and it is yours to take: the
tool cannot reuse `sink_baseline` on your behalf. Every probe result ends with
what is held. Read that line and reach for what is on it — a re-derived value
pays for its solves a second time.

`compile()` with the real path is load-bearing, exactly as in the `_model.qmd`
shim: a bare `exec()` of file text labels every function `"<string>"`, and then
`inspect.getsource()` raises `OSError`, breaking `show_source()` and `api()`
together. Probes are where a helper is about to be written, so `api()` must work
here or the discovery listing is empty.

The kernel is thrown away and rebuilt, announced in the result, when: the
chapter's source changes (so you never probe definitions you have just
replaced), the chapter changes, a probe overruns its budget, or you pass
`reset=True`. **After any of those, nothing is held.** The announcement is the
only signal — a number computed before a restart is not comparable with one
computed after unless you recomputed it.

**A surprise about a return type means READ, not probe again.** A `TypeError`
about 0-dimensional arrays, a value that is an array where you expected a
scalar, a CasADi object where you expected numpy — all of it is written down in
`read_reference("aerosandbox")` under *Return types*. One run spent four probes
and about eight turns establishing that `run_with_stability_derivatives()`
returns `Cma` as a shape-(1,) array, which that page states outright. A probe
costs a turn and a subprocess; the reference costs one tool call and answers
several questions at once.

The same applies before you start: if the question needs an AeroSandbox call
this notebook has not used before, read the page first rather than discovering
its shape one probe at a time.

## Figures from a probe

There is no `probe.qmd`. The `probe` tool runs Python in the run's kernel, and
that is the whole surface. A Quarto scratch page existed when a person drove the
tooling by hand; nothing reads one now.

When a probe needs to LOOK at something, save the figure and read it back:

```python
fig.savefig("_scratch/_probe_fig.png", dpi=110, bbox_inches="tight")
```

then `read_figure` it. Rehearsing cells that are about to become an entry is
better done by writing the entry and rendering it — `render` reports what broke,
and the freeze is the thing you actually need.

- **Cell code runs from the notebook root**, not from `_scratch/`, because the
  project sets `execute-dir: project`. Any path inside a probe is relative to the
  notebook directory. A probe's own cwd is its run directory, so a bare filename
  from `savefig` lands beside the run.
- Interpreter startup and the chapter exec are paid ONCE per run, not per probe.
  So the old advice — cram several questions into one probe to amortise it — no
  longer applies, and following it now costs you: a probe that overruns its
  budget is killed, and a long one bundling four solves loses the namespace that
  three of them had already filled. Ask one question, keep the result in a name,
  build on it.

## Why `_scratch/`

The leading underscore is load-bearing: `_scratch/` sits inside the Quarto
project, and Quarto skips `_`-prefixed paths, so `quarto render <notebook>` never
sees it. Don't rename it to `scratch/`. It is gitignored, so nothing in it needs
to be tidy — but nothing in it survives either.

## Timing and benchmark hygiene

More time has been lost here than to any slow model. Each of these cost real
minutes in a single session.

**Never leave a long run unattended and silent.** `probe_init.py` arms
`faulthandler.dump_traceback_later`, which prints where the process is stuck
without killing it, from a separate thread — so unlike a signal it reports from
inside a long C call. A solver flag that turned one solve into ten silent minutes
was indistinguishable from a hang until this existed.

**Kill your strays, and check the machine before believing a number.** Two
orphaned benchmark processes ran 35 minutes unnoticed and corrupted the timing
they were being compared against. `uptime` before and after; a wall-clock figure
from a loaded machine measures the machine. The same solve measured 533.9 s
against a 145 s baseline for this reason.

**Never run two heavy probes at once.** Both starve and neither number means
anything. Sequential is faster in practice and the results are usable.

**Shell traps that silently produce nothing:**

- `grep` in a pipeline buffers — use `--line-buffered`. Piping a live log through
  `| tail` buffers everything until exit, so a finished job looks like an empty
  one. This has twice been mistaken for "still running".
- `pgrep -f "ipykernel"` matches *the shell that is waiting*, so the wait never
  ends. Use a bracket to break the self-match: `pgrep -f "ipykernel[_]launcher"`.
- macOS has no `timeout`, and BSD `find` has no `-newermt` — the latter fails
  silently and returns nothing. Prefer Python when portability matters.

**Report iterations alongside time.** Wall clock alone inverts conclusions: one
comparison showed 8.4× faster while the iteration count went 192 → 481. Solve
counts can mislead too — a collocated solve was 599 s at 8 aero solves against
112 s at 3070, because the graph is built once and the solver iterates inside C
where the counter cannot see.

## A guard must not document its own bypass

The probe budget once read an environment variable, and its kill message ended
"Raise it with NOTEBOOK_PROBE_BUDGET=<seconds>". Across the session that followed
it was overridden on *every* probe — 1200 s, 1800 s, 3600 s — and never once took
effect. Two design errors, and the second is the instructive one: the override was
a single token at the front of a command, and **the failure path advertised it at
the exact moment someone was motivated to use it**. The first override was
reasoned; the rest were copy-paste.

So the budget is granted by the user at the prompt as a POOL, which the agent
divides per probe with `budget_s`. The kill message names the three legitimate
responses and no escape hatch.

Two related traps worth knowing:

- **Set limits from measurements you already have.** The 300 s default was chosen
  by intuition while the freeze already recorded entry runtimes of 251–385 s and a
  single solve had been timed at 210 s. The same session also sized a solve budget
  from a 70 s solve at 30 nodes and applied it to entries running 60.
- **A probe can outlive its own output.** One finished printing its last line and
  then sat at 80% CPU for fifteen minutes — a BLAS/OpenMP pool busy-waiting, or a
  thread CasADi left behind. "It printed the answer" is not "it exited", so check
  the process, not the log.

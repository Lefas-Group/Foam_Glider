"""
One IPython kernel per run, so a probe's names outlive the probe.

Probes used to be a subprocess each: `uv run python probe.py`, a fresh
interpreter, the chapter exec'd again, and everything discarded on exit. The run
that motivated this spent 258.8 s of a 300 s pool and used less than half of it
to buy an answer once. Three symptoms, one cause -- nothing survived a probe:

  * the same baseline optimisation was solved at turns 26, 40 and 52;
  * a probe killed at 62 s lost the two results it had already printed, because
    `os._exit` skips stdio flushing and a captured pipe is block-buffered;
  * a 30-line helper was re-pasted verbatim into six consecutive probes, and
    that boilerplate is part of why the killed probe overran.

A kernel fixes all three by not throwing the namespace away. It also makes the
second one moot rather than fixed: ipub streams output as it is produced, so
what a probe printed before it was killed has already arrived.

WHAT MAKES THIS SAFE, and none of it is optional:

  1  A BUDGET KILL INTERRUPTS FIRST, AND KEEPS THE NAMESPACE IF THAT WORKS.
     This reverses an earlier decision, so both halves are on the record.

     It used to kill the kernel outright, for a real failure: the run that
     motivated the kernel monkey-patched a mass function into
     `optimize_geometry_for_sink_rate.__globals__` and restored it afterwards,
     and the probe that was killed died WITH THE PATCH INSTALLED. A kernel
     that survives its own kill hands the next probe that patch.

     What changed is the measured cost of the other side. On the F-16 Viper
     reconstruction three probes were killed on budget inside a pose fit, and
     the restart cost the run its model: the next probe died on
     `NameError: name 'ap' is not defined` and the rebuild came out of the
     same pool that had just been overspent. A long tool call is exactly where
     a budget kill lands, and it was being punished twice.

     So: SIGINT, wait for idle, and prove the kernel still executes. If it
     comes back, the namespace is kept and the probe's output SAYS SO, and
     says what the hazard is -- a killed probe can leave a global patched or
     an object half-built, and `reset=True` is the way out. If the interrupt
     does not land -- a CasADi solve does not take a signal, which is why the
     stop was a process kill in the first place -- the kernel is shut down and
     the restart is announced exactly as before. The budget is still absolute;
     only the namespace survives, and only when the kernel proved it is sane.

  2  A CHAPTER-SOURCE CHANGE RESTARTS THE KERNEL. The same run edited
     `_analysis.py` and probed it two turns later. A kernel holds the old
     definitions, so the probe would have validated code the model had just
     replaced.

  3  A RESTART IS ANNOUNCED. Silently starting fresh is the same failure as
     silently keeping stale state: the model reads a result whose provenance it
     cannot see. Every restart says so in the probe's own output.

The kernel is bound to `sys.executable`, which is the project venv `nb` itself
runs under, rather than to whatever `python3` kernelspec happens to be
installed. `jupyter_client` and `ipykernel` come in with the `jupyter` dependency
Quarto already needs, so this adds nothing to `pyproject.toml`.
"""

import hashlib
import os
import pathlib
import re
import sys
import time

from ..process.log import say

# One per run directory. Keyed by path rather than held on the session because
# `run_probe` takes the session optionally and the run directory is the thing
# that is always known -- and it is already the unit of isolation that stopped
# two agents running each other's probe script.
_KERNELS = {}

# How long to wait for a kernel to come up. Generous: it imports aerosandbox and
# execs the chapter, which is the ~2 s that every subprocess probe used to pay
# and this pays once per run.
STARTUP_S = 120.0

# The poll interval while collecting output. Short enough that a deadline is
# honoured promptly -- the old watchdog polled every 15 s and could overrun its
# own grant by that much, which is why `budget_s` under ~20 bought nothing.
POLL_S = 0.2


# ipykernel COLOURISES tracebacks -- `IPython.core.ultratb` wraps every frame,
# filename and exception name in SGR escapes. A subprocess probe never saw them,
# because it printed to a pipe and Python does not colour a traceback it is not
# writing to a terminal; a kernel formats them the same way whoever is reading.
#
# Stripped rather than turned off at the source: the colour is a property of how
# IPython renders, and the ways to disable it (a profile, a magic, monkeypatching
# ultratb) all live inside the kernel and would have to survive every restart.
# One regex here is smaller and cannot be forgotten.
#
# It matters more than it looks. The escapes are four to eight characters per
# frame and go into the model's context as literal `[31m`, which is noise on the
# one output it is reading most carefully -- the one that just went wrong.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _spec():
    """A kernelspec pointing at OUR interpreter, built rather than looked up."""
    from jupyter_client.kernelspec import KernelSpec
    return KernelSpec(
        argv=[sys.executable, "-m", "ipykernel_launcher", "-f",
              "{connection_file}"],
        display_name="nb-probe",
        language="python",
    )


class Kernel:
    """A live chapter, and the four reasons to throw it away."""

    def __init__(self, notebook, chapter):
        self.notebook = notebook
        self.chapter = chapter
        self.km = None
        self.kc = None
        self.log = None
        self.fingerprint = None
        self.dead = False

    # ---------------------------------------------------------------- lifecycle

    def _sources(self):
        """The files whose content the namespace was built from."""
        d = self.notebook.root / "chapters" / self.chapter
        return [self.notebook.root / "_notebook.py",
                d / "_model.py", d / "_analysis.py"]

    def _fingerprint(self):
        h = hashlib.sha256()
        for p in self._sources():
            h.update(p.read_bytes() if p.exists() else b"")
            h.update(b"\0")
        return h.hexdigest()

    def start(self):
        # Deferred, with `_spec`'s import: `jupyter_client` costs ~0.3 s to
        # import and every `nb` command pays it at module load otherwise, for
        # the one in three that ever starts a kernel.
        from jupyter_client.manager import KernelManager

        run_dir = self.notebook.run
        run_dir.mkdir(parents=True, exist_ok=True)

        # The kernel's own stdout/stderr, which is NOT cell output -- that
        # arrives on iopub. What lands here is ipykernel's startup chatter (it
        # warns about unencrypted TCP on every launch) and whatever a hard crash
        # prints on the way down. To a file, so the first never reaches the
        # terminal and the second is still there to read.
        self.log = open(self.notebook.kernel_log, "ab")

        env = dict(os.environ,
                   NB_CHAPTER=self.chapter,
                   NB_ROOT=str(self.notebook.root),
                   # What `_notebook.py` reads to tell a probe from a render.
                   # Without it the file assumes render and drops
                   # `ipopt.max_wall_time`, silently unbounding every solve.
                   NB_PROBE="1")

        self.km = KernelManager()
        self.km._kernel_spec = _spec()
        # cwd is the RUN directory, as the subprocess's was: a probe that saves
        # a figure writes a relative filename and it must land beside its own
        # run rather than in a shared scratch.
        self.km.start_kernel(cwd=str(run_dir), env=env,
                             stdout=self.log, stderr=self.log)
        self.kc = self.km.blocking_client()
        self.kc.start_channels()
        self.kc.wait_for_ready(timeout=STARTUP_S)

        init = (pathlib.Path(__file__).parent / "probe_init.py").read_text()
        out, killed = self._run(init, STARTUP_S)
        if killed or "Traceback" in out:
            self.shutdown()
            raise RuntimeError(f"probe kernel failed to load "
                               f"chapters/{self.chapter}:\n{out}")
        self.fingerprint = self._fingerprint()
        return self

    def shutdown(self):
        try:
            if self.kc is not None:
                self.kc.stop_channels()
            if self.km is not None and self.km.is_alive():
                self.km.shutdown_kernel(now=True)
        except Exception:
            # Teardown must not raise into a run that has already produced its
            # answer. A leaked kernel is a nuisance; a traceback here would
            # replace the result the user is waiting for.
            pass
        finally:
            if self.log is not None:
                self.log.close()
            self.km = self.kc = self.log = None
            self.dead = True

    def stale(self):
        """Why this kernel cannot be reused, or None."""
        if self.dead or self.km is None or not self.km.is_alive():
            return "the kernel is gone"
        if self._fingerprint() != self.fingerprint:
            changed = [p.name for p in self._sources()]
            return (f"the chapter's source changed "
                    f"({', '.join(changed)} are re-read on every probe)")
        return None

    # ------------------------------------------------------------------ running

    def _run(self, code, deadline_s):
        """Execute one cell. Returns (output, killed)."""
        import queue

        msg_id = self.kc.execute(code, allow_stdin=False)
        out = []
        t0 = time.monotonic()
        while True:
            left = deadline_s - (time.monotonic() - t0)
            if left <= 0:
                return "".join(out), True
            try:
                msg = self.kc.get_iopub_msg(timeout=min(POLL_S, left))
            except queue.Empty:
                continue
            if msg["parent_header"].get("msg_id") != msg_id:
                continue
            kind, content = msg["msg_type"], msg["content"]
            if kind == "stream":
                out.append(_ANSI.sub("", content["text"]))
            elif kind == "error":
                # The traceback verbatim, minus the colour. `_scope_hint` reads
                # it, and a tool that rewrites what the interpreter SAID teaches
                # the model to distrust its own output -- dropping the escapes
                # that carry no words is the only edit made here.
                out.append(_ANSI.sub("", "\n".join(content["traceback"])))
            elif (kind == "status"
                  and content.get("execution_state") == "idle"):
                return "".join(out), False

    def _interrupt(self, wait_s=15.0):
        """SIGINT the running cell and KEEP the namespace. -> did it come back?

        Two things have to be true before the namespace can be trusted again:
        the kernel has to go idle, and it has to execute something afterwards.
        An interrupt that only does the first leaves a kernel that answers the
        status channel and nothing else, which would hand every later probe a
        timeout instead of a result.
        """
        import queue
        try:
            self.km.interrupt_kernel()
        except Exception:
            return False
        t0 = time.monotonic()
        while time.monotonic() - t0 < wait_s:
            try:
                msg = self.kc.get_iopub_msg(timeout=POLL_S)
            except queue.Empty:
                continue
            if (msg["msg_type"] == "status"
                    and msg["content"].get("execution_state") == "idle"):
                break
        else:
            return False
        out, killed = self._run("pass", 10.0)
        return not killed

    def execute(self, code, deadline_s):
        started = time.perf_counter()
        out, killed = self._run(code, deadline_s)
        elapsed = time.perf_counter() - started
        if killed:
            kept = self._interrupt()
            # The wording the in-process watchdog used, kept deliberately: the
            # model has met this stop before, and it names the three real ways
            # out without naming the one that turns a guard into a formality.
            out += (f"\n[probe killed at {deadline_s:.0f} s, over its "
                    f"{deadline_s:.0f} s budget.\n"
                    f" This is a stop, not a speed bump. Choose one:\n"
                    f"   - decide the answer is not worth this much compute;\n"
                    f"   - make it cheaper -- fewer nodes, a held design, one "
                    f"arm instead of a sweep;\n"
                    f"   - ask the user for more time, with a bigger budget_s "
                    f"or a bigger pool.\n"
                    f" Anything printed before the kill is above")
            if kept:
                # SAID OUT LOUD, for the reason a restart is: the model is
                # about to reuse names from a probe that did not finish.
                out += (", and the kernel was interrupted rather than "
                        "restarted, so names from EARLIER probes are still "
                        "held. Nothing this probe was part-way through "
                        "completed -- a global it patched is still patched, "
                        "an object it was building is half-built. If the next "
                        "result has to be clean, probe with `reset=True`.]")
            else:
                out += (", and the interrupt did not land, so the kernel was "
                        "restarted and nothing is held.]")
                self.shutdown()
        return out, elapsed

    def held(self):
        """Names this run's probes have defined, newest last. [] if unknowable."""
        if self.dead or self.km is None or not self.km.is_alive():
            return []
        code = ("print('\\x00'.join(sorted(n for n in globals() "
                "if not n.startswith('_') and n not in __nb_baseline)))")
        out, killed = self._run(code, 10.0)
        if killed or "\x00" not in out and not out.strip():
            return []
        return [n for n in out.strip().split("\x00") if n]


def _open(notebook, chapter, why=None):
    """The kernel for this run, started or restarted as needed."""
    key = str(notebook.run)
    k = _KERNELS.get(key)

    if k is not None and (k.chapter != chapter or why):
        why = why or f"the chapter changed to {chapter}"
        k.shutdown()
        k = None
    if k is not None:
        stale = k.stale()
        if stale:
            why = stale
            k.shutdown()
            k = None

    if k is None:
        started = time.perf_counter()
        k = Kernel(notebook, chapter).start()
        _KERNELS[key] = k
        say(f"  kernel    chapters/{chapter} loaded in "
            f"{time.perf_counter() - started:.1f} s"
            + (f" — restarted: {why}" if why else ""))
    return k, why


def probe(notebook, chapter, code, deadline_s, reset=False):
    """
    Run `code` in the run's kernel. Returns (output, restarted_because, seconds).

    `restarted_because` is a reason string when this probe got a fresh
    namespace, else None -- `run_probe` puts it in FRONT of the output, because
    a restart the model cannot see is a result it cannot trust.

    `seconds` is the CELL's time, not the call's. Starting a kernel costs a few
    seconds of chapter exec, and that is a per-RUN cost that happens to land on
    whichever probe triggered it. Charging it to the pool would bill one probe
    for the run's setup and, worse, tell the model its own `budget_s` estimate
    was wrong when it was right -- which is how a model learns to pad every
    estimate. The terminal still sees the startup, on its own line.
    """
    k, why = _open(notebook, chapter,
                   why="`reset=True` was asked for" if reset else None)
    out, seconds = k.execute(code, deadline_s)
    return out, why, seconds


def held(notebook):
    """What the run's kernel is holding, for the line that tells the model."""
    k = _KERNELS.get(str(notebook.run))
    return k.held() if k is not None else []


def shutdown(notebook):
    """End of run. Called from `run`'s finally, and idempotent."""
    k = _KERNELS.pop(str(notebook.run), None)
    if k is not None:
        k.shutdown()

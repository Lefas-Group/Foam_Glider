"""
The cell that loads a chapter into a probe kernel. Sent, not imported.

`kernel.py` reads this file's SOURCE and executes it as the kernel's first cell,
so everything below lands in the namespace the model's probes then run in. It is
a real module rather than a string literal in `kernel.py` so that it is linted,
formatted and syntax-checked like any other file -- a twenty-line program living
in a string is the one thing nothing in this repo checks.

It replaces `_scratch/_probe_base.py`, which did the same job for the subprocess
probes and was COPIED into every notebook to do it. That bought one
thing: a human could load a chapter by hand, with no `nb` installed, in two
lines. That is not a path anyone uses, and it cost a second file under lint rule
11 plus a copy in every notebook to keep in step. Nothing else reached it --
`_model.qmd` execs the chapter itself at render time and never touched it.

WHAT MUST NOT CHANGE when editing this file:

  * `compile()` with the real path. A bare `exec()` of file text labels every
    function "<string>"; `inspect.getsource` then raises OSError and both
    `show_source()` and `api()` go silent. Probes read source constantly --
    four times in the run that motivated the kernel -- so this is load-bearing,
    exactly as it is in the `_model.qmd` shim.
  * The chapter comes from the environment. Switching chapters restarts the
    kernel rather than editing anything.
"""

# The kernel's environment carries both, set by `kernel.py` when it starts.
# Read rather than interpolated: the source is sent verbatim, so a placeholder
# would have to be formatted in, and a format string is a syntax error away from
# being unlintable again.
import os as _os
import pathlib as _pathlib

# A BARE KeyError HERE READS AS A BUG IN THE CHAPTER, which is the one thing it
# never is. Both variables are set by `kernel.py`; their absence means this file
# is being run as something other than a probe kernel's first cell -- imported,
# most often -- and the traceback should say so rather than name a dict key.
if not _os.environ.get("NB_ROOT") or not _os.environ.get("NB_CHAPTER"):
    raise RuntimeError(
        "nb/tools/probe_init.py is the SOURCE of a probe kernel's first cell, "
        "not an importable module: it execs a chapter into whatever namespace "
        "it lands in, and reads $NB_ROOT and $NB_CHAPTER to know which. "
        "`kernel.py` sets both when it starts a kernel. Nothing else should run "
        "this file -- `nb.corpus`'s import sweep skips it by name for exactly "
        "this reason."
    )

NB_ROOT = _pathlib.Path(_os.environ["NB_ROOT"])
CHAPTER = _os.environ["NB_CHAPTER"]

# No fallback to "first chapter alphabetically". `_probe_base` had one, warning
# on stderr, and a swallowed warning is how a probe comes to answer confidently
# about the wrong aircraft. `run_probe` refuses an unknown chapter before a
# kernel is ever started, so by here the answer is known and a KeyError above is
# a bug in `nb` rather than a case to paper over.
_chapter_dir = NB_ROOT / "chapters" / CHAPTER

for _p in [NB_ROOT / "_notebook.py",
           _chapter_dir / "_model.py",
           _chapter_dir / "_analysis.py"]:
    if _p.exists():
        exec(compile(_p.read_text(), str(_p), "exec"))

# WHERE a probe is stuck, from its own thread, so it reports from inside a C
# call too. The thread that used to KILL a probe lived in `_notebook.py`; that
# job is `nb`'s now, and this is the half worth keeping either way -- a probe
# that is working and a probe that is hung look identical from outside.
#
# Armed here rather than in `_notebook.py` because a render must not do it: the
# same file is exec'd by every page, and a traceback dumped mid-render lands in
# the page's output.
#
# repeat=False: a solve that legitimately runs for minutes would otherwise dump
# a traceback every couple of minutes, and one report already distinguishes
# "working" from "hung".
import faulthandler as _faulthandler
import sys as _sys

_faulthandler.dump_traceback_later(PROBE_SILENCE, repeat=False,  # noqa: F821
                                   file=_sys.stderr)

# DIE WITH THE RUN THAT STARTED US.
#
# A run is a daemon -- `detach.py` double-forks it out of the terminal's
# session -- and this kernel is its child. Nothing about that child is
# automatic: when the run ends cleanly, `run`'s `finally` shuts it down, but
# when the run is KILLED, or dies down a path that never reaches that finally,
# the kernel is simply reparented to init and keeps running. Observed: a run
# died mid-probe and left a kernel holding a loaded chapter, with nothing left
# alive that knew it existed.
#
# `atexit` in the parent cannot help, because the case that matters is the
# parent not getting to run anything. So the check lives HERE and is the one
# signal a SIGKILLed parent cannot suppress: our ppid changes the moment it
# dies. Polled rather than waited on -- `os.wait` is for children, and this is
# the other direction.
#
# `os._exit`, not `sys.exit`: a kernel whose run is gone has no output anyone
# will read and no reason to unwind gracefully.
import os as _os_guard
import threading as _threading


def _die_with_parent(_ppid=_os_guard.getppid()):
    import time as _t
    while True:
        _t.sleep(5.0)
        if _os_guard.getppid() != _ppid:
            _os_guard._exit(0)


_threading.Thread(target=_die_with_parent, daemon=True).start()

# The names the chapter brought in, so `kernel.py` can tell the model what it is
# holding from earlier probes. Taken here, before any probe has run, so the diff
# against it later is exactly what the probes themselves defined.
__nb_baseline = set(globals())

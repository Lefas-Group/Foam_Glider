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

# =============================================================================
# THE NOTEBOOK IS THE WORLD. A probe may read what belongs to the aircraft and
# nothing else.
#
# `tools/__init__.py` deleted the `bash` tool and noted, correctly, that it
# "changes nothing about what a run CAN do -- only about what it can do
# UNINSTRUMENTED", because `probe` runs arbitrary Python by design. The brief
# asks the model not to explore the filesystem. A request is not a boundary.
#
# MEASURED, on the FT A-10 Warthog, 2026-10-09. The run spent 25 of 54 turns
# probing `nb`'s OWN SOURCE -- `text.find("def _input_item_budget")`,
# `text.find("def _derived_target_not_...")`, `glob.glob` over the repo --
# reading the lint rules it was about to be graded against, looking for the
# tolerance a target check applies. Zero aero solves. Zero `declare_input`.
# `_model.py` untouched at seven lines. It was reading the mark scheme instead
# of sitting the exam, and the only thing stopping it was a sentence in a
# brief.
#
# That is worse than a wasted budget. Rule 44 exists because a run solved
# backwards for a published span and rule 50 because one typed ballast to hit
# a mass; an agent that can read the threshold a check applies can aim at the
# threshold rather than at the aeroplane. The rules have to be something the
# work is measured against, not something the work can consult.
#
# WHAT IS ALLOWED, and why each: the notebook itself (its chapters, its
# references, its freeze), the system temp directory (matplotlib, fontconfig
# and numpy all write caches there), and the installed packages -- AeroSandbox
# is read constantly and legitimately, by `api()` and by `show_source`.
#
# WRAPPED, NOT SANDBOXED. This stops a probe reaching for `nb/` or the rest of
# the repo; it is not a security boundary and does not pretend to be -- the
# kernel runs as the user and `os` is one import away. It is the same kind of
# guard as the chapter lock: it makes the honest mistake impossible and the
# dishonest one deliberate.
# =============================================================================
import builtins as _bi
import pathlib as _pl
import sys as _sys_guard

# `sys.path` MINUS THE EMPTY STRING AND THE CWD. `''` means "where the process
# is", which for a probe kernel is the run directory INSIDE the notebook --
# whose parent chain reaches the repo root, and resolving it whitelisted the
# entire tree including `nb/` itself. Measured: with it in, every refusal
# below silently passed. Site-packages are named explicitly instead.
_ALLOWED = tuple(str(_pl.Path(_p).resolve()) for _p in
                 [NB_ROOT,                                   # noqa: F821
                  __import__("tempfile").gettempdir(),
                  *(_q for _q in _sys_guard.path
                    if _q and _pl.Path(_q).is_dir()
                    and _pl.Path(_q).name in ("site-packages", "dist-packages",
                                              "lib-dynload")
                    or _q.endswith(".zip")),
                  __import__("sysconfig").get_paths()["stdlib"],
                  __import__("sysconfig").get_paths()["purelib"]] if _p)
# WHERE `nb` ITSELF LIVES. Not from `__file__` -- this file is exec'd as a
# cell and has none -- but from the installed module, which is the same code
# the run is using. It sits inside the repo and often inside an allowed
# package root, so it is refused explicitly rather than by omission.
try:
    import importlib.util as _ilu
    _NB_PACKAGE = str(_pl.Path(_ilu.find_spec("nb").origin).resolve().parent)
except Exception:                                            # noqa: BLE001
    _NB_PACKAGE = None


def _outside(path):
    """True when `path` is not the notebook's, nor a package, nor scratch."""
    try:
        full = str(_pl.Path(path).resolve())
    except (OSError, ValueError, TypeError):
        return False
    if _NB_PACKAGE and (full == _NB_PACKAGE or
                        full.startswith(_NB_PACKAGE + "/")):
        return True                       # `nb` itself, even though importable
    return not any(full == a or full.startswith(a + "/") for a in _ALLOWED)


_real_open = _bi.open


def _guarded_open(file, mode="r", *a, **kw):
    if isinstance(file, (str, bytes, _pl.PurePath)) and _outside(file):
        raise PermissionError(
            f"{file} is outside this notebook. A probe reads the aircraft -- "
            f"its chapters, its references, its freeze -- and the libraries "
            f"it models with. `nb`'s own source is not among them: the rules "
            f"are what your entry is MEASURED against, so an entry written "
            f"with them open is measuring itself. If you are looking for a "
            f"tolerance or a target, it is in the brief and in the chapter's "
            f"`_inputs.yml`, both of which are already in front of you.")
    return _real_open(file, mode, *a, **kw)


_bi.open = _guarded_open
# AND IN THIS NAMESPACE. Patching `builtins` alone was not enough: IPython
# puts its own `open` in the user namespace, so a bare `open(...)` in a probe
# resolved to that one and never reached the guard -- `builtins.open` read
# `_guarded_open` while `open` read `open`, and every refusal below silently
# passed. Measured, and the reason this line exists.
open = _guarded_open                                         # noqa: A001

# The names the chapter brought in, so `kernel.py` can tell the model what it is
# holding from earlier probes. Taken here, before any probe has run, so the diff
# against it later is exactly what the probes themselves defined.
__nb_baseline = set(globals())

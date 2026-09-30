"""
The cell that loads a chapter into a probe kernel. Sent, not imported.

`kernel.py` reads this file's SOURCE and executes it as the kernel's first cell,
so everything below lands in the namespace the model's probes then run in. It is
a real module rather than a string literal in `kernel.py` so that it is linted,
formatted and syntax-checked like any other file -- a twenty-line program living
in a string is the one thing nothing in this repo checks.

It replaces `_scratch/_probe_base.py`, which did the same job for the subprocess
probes and was VENDORED into every notebook to do it. Vendoring bought one
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

# The names the chapter brought in, so `kernel.py` can tell the model what it is
# holding from earlier probes. Taken here, before any probe has run, so the diff
# against it later is exactly what the probes themselves defined.
__nb_baseline = set(globals())

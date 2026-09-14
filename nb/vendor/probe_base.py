"""
The preamble every scratch probe repeats. Import it; don't retype it.

    import sys; sys.path.insert(0, "<notebook>/_scratch")
    from _probe_base import *          # chapter loaded, nothing printed

Two lines, from a heredoc or a file, with no file to edit first. That matters
more than it looks: an earlier version pinned CHAPTER as a constant and printed
the whole api() listing on import, and across a session of dozens of probes
spanning four chapters, it was used exactly never -- every probe hand-rolled the
exec instead, which is how a local `G` came to shadow gravity and how a helper
was called with the wrong arity twice. Guidance is only followed when the correct
path is also the cheap one, so:

  * the chapter comes from $NB_CHAPTER, so switching chapters edits no file;
  * nothing prints on import -- call api() when you want the listing, which is
    when you are about to write a helper and the skill says to look first.

`compile()` with the real path is the one load-bearing part, exactly as in the
_model.qmd shim: a bare exec() of file text labels every function "<string>",
inspect.getsource() then raises OSError, and show_source() and api() both go
silent -- in an entry, that is a render that documents nothing.

Probe budget and the stuck-probe traceback are NOT here. They live in
_notebook.py, which every probe execs whether or not it imports this file. See
the PROBE_BUDGET block there.

The leading underscore keeps this out of project renders, like everything in
_scratch/.
"""
import os
import pathlib

_root = pathlib.Path(__file__).resolve().parent.parent
_chapters = sorted(p.name for p in (_root / "chapters").iterdir() if p.is_dir())
CHAPTER = os.environ.get("NB_CHAPTER") or _chapters[0]

# Silent when told which chapter, loud when it had to guess. Nothing else prints
# here -- but a wrong guess surfaces as `NameError: simulate` three functions
# deep, which reads as a broken probe rather than a mis-set chapter, so this one
# line earns its place.
if not os.environ.get("NB_CHAPTER"):
    import sys as _sys
    print(f"[_probe_base: NB_CHAPTER unset, defaulting to {CHAPTER}. "
          f"Others: {', '.join(c for c in _chapters if c != CHAPTER)}]",
          file=_sys.stderr)

_chapter = _root / "chapters" / CHAPTER
for _p in [_root / "_notebook.py", _chapter / "_model.py",
           _chapter / "_analysis.py"]:
    if _p.exists():
        exec(compile(_p.read_text(), str(_p), "exec"))

"""
create_chapter -- scaffold a new chapter, from the template.

The agent triggers it but does not author it: the template is META, outside the
writable set. What the agent gets afterwards is an ordinary chapter directory
inside `chapters/`, which it then fills through the normal file tools.

A new NOTEBOOK is not offered. That wants a fresh session, which is a process
decision rather than the agent's.
"""

import os
import re
import shutil

from ..config import SCAFFOLD

NAME = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")

# What an undescribed chapter's index carries. Doubles as the marker that nobody
# has claimed the chapter yet -- see `Notebook.claimable_stub`.
PLACEHOLDER = ("<one sentence, then a bullet list: the aero method, the section, "
               "what is left out>")
SLUG = re.compile(r"^(?:\d{2}-)?(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")


def _allocate(notebook, slug, start=None):
    """
    Create `chapters/NN-<slug>/` atomically, and return (name, path).

    The number is code's decision, not the model's: the model used to supply it
    and a wrong guess aborted `nb write` outright, after the ask had been paid
    for. The model owns the slug, which is judgement; the number is bookkeeping.

    `mkdir` IS the allocator. Reading the directory and then creating is a
    read-then-write race -- two runs compute the same max and both believe they
    own it -- whereas `mkdir` fails with `EEXIST` and the loser simply takes the
    next number. That needs no lock, no coordinator, and no knowledge that
    another run exists, which is why it beats having a coordinator assign
    numbers: a coordinator that guesses wrong can waste a whole run, and this
    cannot.
    """
    # `mkdir chapters/NN-slug` is NOT enough: it guards the NAME, and it is the
    # NUMBER that must be unique -- two runs proposing different slugs both
    # succeed at the same number. Measured: eight concurrent allocations
    # produced three chapters numbered 13.
    #
    # So reserve the NUMBER, which is the thing being allocated. The marker
    # lives under `_scratch/` rather than in `chapters/`, because `chapters_of`
    # lists every directory it finds and a reservation is not a chapter. It is
    # held only until the real directory exists, after which the directory
    # itself is what makes the number visible to the next allocator.
    held = notebook.scratch / ".alloc"
    held.mkdir(parents=True, exist_ok=True)
    used = [int(c[:2]) for c in notebook.chapters() if c[:2].isdigit()]
    n = int(start) if start is not None else max(used, default=0) + 1
    for _ in range(100):
        marker = held / f"{n:02d}"
        try:
            marker.mkdir()
        except FileExistsError:     # another run is mid-allocation on this one
            n += 1
            continue
        try:
            # Re-read while HOLDING the number, not before. The starting guess
            # came from a scan every concurrent run made at the same moment, so
            # on its own it is stale by construction; checking here is what
            # makes the marker mean anything, because every allocator for this
            # number is serialised behind it. It is also what makes an explicit
            # `number` safe to pass -- a wrong one walks forward instead of
            # landing on top of an existing chapter.
            if any(c.startswith(f"{n:02d}-") for c in notebook.chapters()):
                n += 1
                continue
            name = f"{n:02d}-{slug}"
            try:
                (notebook.chapters_dir / name).mkdir(parents=True)
            except FileExistsError:
                n += 1
                continue
            return name, notebook.chapters_dir / name
        finally:
            marker.rmdir()
    raise RuntimeError(f"no free chapter number for {slug!r} below {n}")


def _claim(notebook, slug):
    """
    Take over an untouched scaffold chapter atomically, or return None.

    `os.rename` on a directory is atomic, so it is the claim: the winner gets
    the directory, the loser's rename raises and it falls through to allocating
    a fresh number. The previous version called `claimable_stub()` and then
    `rmtree`, which meant two runs could both decide the same stub was theirs
    and the loser died on an unhandled `FileNotFoundError`.

    Rename first, rewrite the templated files after -- `_model.qmd` and
    `index.qmd` bake the chapter path in, so the contents are only valid once
    the directory has its final name.
    """
    stub = notebook.claimable_stub()
    if stub is None:
        return None
    name = f"{stub[:2]}-{slug}"
    target = notebook.chapters_dir / name
    try:
        os.rename(notebook.chapters_dir / stub, target)
    except OSError:
        return None                 # someone else claimed it, or it moved
    # The stub's index may already have been rendered and frozen. Left behind is
    # a freeze for a chapter that no longer exists, which nothing ever collects.
    shutil.rmtree(notebook.freeze / stub, ignore_errors=True)
    return stub, name, target


def _fork_sources(notebook, parent):
    """
    A parent chapter's `_model.py` and `_analysis.py` AT THE LAST COMMIT.

    From `git show`, never the working tree, for two reasons that are really
    one. A fork taken while the parent is dirty copies another agent's
    unfinished work -- which is how parallel chapter work would corrupt itself.
    And rule 31 makes the copy declare the commit it was taken at, so reading
    the tree would make that header a lie even single-threaded.

    The CODE shells to git, never the agent: `shell.py` keeps `git show` off
    the allowlist because the first run of this system spent eight turns on git
    archaeology. This is the same bargain check.py already makes.
    """
    import subprocess
    repo = notebook.repo
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                          capture_output=True, text=True)
    ref = head.stdout.strip() or "HEAD"
    out = {}
    for fname in ("_model.py", "_analysis.py"):
        rel = (notebook.chapters_dir / parent / fname).relative_to(repo)
        r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=repo,
                           capture_output=True, text=True)
        out[fname] = r.stdout if r.returncode == 0 else None
    return ref, out


def create_chapter(notebook, name, title, defines="", claim=True,
                   number=None, fork_from=""):
    """
    Create `chapters/<name>/` with index.qmd, _model.qmd, _model.py, _analysis.py.

    `_analysis.py` starts EMPTY by design: chapter-shared helpers arrive by
    promotion from an entry that needed them a second time, never by
    anticipation.

    With `claim`, an untouched scaffold chapter is taken over rather than left
    beside the new one -- see `Notebook.claimable_stub`. Both paths allocate
    ATOMICALLY (`rename` to claim, `mkdir` to create), so two concurrent runs
    cannot end up believing they own the same directory.

    `number` forces a starting number rather than deriving one. It is a hint,
    not a demand: allocation still walks past a collision, so a caller that
    guesses wrong costs nothing.
    """
    m = SLUG.match(name)
    if not m:
        return name, (f"rejected: {name!r}. Chapter directories are "
                      f"NN-kebab-case, e.g. '05-boom-structure'.")
    slug = m.group("slug")

    stub = None
    claimed = _claim(notebook, slug) if claim else None
    if claimed:
        stub, name, target = claimed
    else:
        name, target = _allocate(notebook, slug, start=number)
    if not NAME.match(name):
        return name, f"rejected: {name!r} is not NN-kebab-case"

    sub = lambda s: s.replace("__CHAPTER__", name).replace("__TITLE__", title) \
        .replace("__WHAT_DEFINES_THE_CHAPTER__", defines or PLACEHOLDER)

    (target / "_model.qmd").write_text(sub((SCAFFOLD / "_model.qmd.tmpl").read_text()))
    (target / "index.qmd").write_text(sub((SCAFFOLD / "index.qmd.tmpl").read_text()))
    forked = ""
    if fork_from:
        ref, src = _fork_sources(notebook, fork_from)
        if src.get("_model.py"):
            header = (f"# Forked from chapters/{fork_from}/_model.py at {ref}.\n"
                      f"#\n"
                      f"# Differences, all deliberate:\n"
                      f"#   * TODO: one line per change you make below.\n"
                      f"#\n"
                      f"# Nothing else differs. An empty `diff` against the "
                      f"parent everywhere else\n# is the positive check that "
                      f"says so.\n")
            (target / "_model.py").write_text(header + src["_model.py"])
            (target / "_analysis.py").write_text(src.get("_analysis.py") or "")
            forked = (f"\n\n_model.py and _analysis.py were COPIED from "
                      f"chapters/{fork_from}/ at commit {ref} -- from the "
                      f"commit, not the working tree, so nothing half-finished "
                      f"came across. The rule 31 header is already there: "
                      f"replace its TODO line with one line per deliberate "
                      f"difference as you make them, and change nothing you "
                      f"did not mean to.")
    if not forked:
        (target / "_model.py").write_text((SCAFFOLD / "_model.py.tmpl").read_text())
        (target / "_analysis.py").write_text("")

    what = (f"claimed the empty scaffold chapters/{stub}/ as chapters/{name}/"
            if stub else f"created chapters/{name}/")
    return name, (
            f"{what} with index.qmd, _model.qmd, _model.py and an empty "
            f"_analysis.py.{forked}\n\n"
            f"If you build this chapter's _model.py by COPYING an earlier "
            f"chapter's, say so at the top of the file before you render "
            f"anything (rule 31): \"# Forked from chapters/NN-name/_model.py "
            f"at <commit>.\" then \"# Differences:\" and one line per "
            f"deliberate change. `diff` against the parent is then the review, "
            f"and an empty diff everywhere else is the positive check. Write it "
            f"FIRST -- adding it later edits _model.py after the chapter is "
            f"frozen, which costs a full re-prove to clear rule 12.\n\n"
            f"Put the VEHICLE in chapters/{name}/_model.py -- rule 19 requires "
            f"it, and the chapter index renders that file, so it is where a "
            f"reader looks for the aircraft. Where the vehicle is parametric, "
            f"_model.py holds a function taking the design variables and "
            f"returning the Airplane; the entry calls it. Do not restate the "
            f"geometry in the entry cell.\n\n"
            f"Then FILL chapters/{name}/index.qmd with edit_file -- not only "
            f"the sentence at the top, but both callouts, which ship as "
            f"template placeholders and are a lint failure if left (rule 24). "
            f"DELETE a callout that has nothing to go in it -- a box saying "
            f"\"None.\" is furniture, and rule 32 refuses it. "
            f"EDIT it, never write_file over it: it already carries a `## The "
            f"model` block that renders _model.py and _analysis.py, and a "
            f"chapter whose index does not show its aircraft is rule 30.\n\n"
            f"Date the callouts, and attribute them honestly: \"Asked of the "
            f"user\" covers only what was actually put to them, which includes "
            f"any Specified answer given during the probe. What this chapter "
            f"inherits from an earlier one is stated without claiming anybody "
            f"was asked.\n\n"
            f"The test for what goes there: IS IT TRUE OF EVERY ENTRY THIS "
            f"CHAPTER WILL HAVE? The section, the objective, the fixed "
            f"dimensions, what is left out -- those are the chapter's, and they "
            f"go in index.qmd, dated, and must NOT be repeated in entry prose. "
            f"A number this one question produced is the entry's, and stays "
            f"there. An index left empty makes every later entry restate the "
            f"same commitments or silently inherit them from an entry that can "
            f"be superseded.")

"""
create_chapter -- scaffold a new chapter, from the template.

The agent triggers it but does not author it: the template is META, outside the
writable set. What the agent gets afterwards is an ordinary chapter directory
inside `chapters/`, which it then fills through the normal file tools.

A new NOTEBOOK is not offered. That wants a fresh session, which is a process
decision rather than the agent's.
"""

import contextlib
import os
import re
import shutil
import time

from ..config import SCAFFOLD
from ..log import say

NAME = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")

# How long a number reservation may be held before it is a corpse.
# An allocation is two `mkdir`s and a directory listing; a minute is
# four orders of magnitude of slack.
ALLOC_STALE = 60.0

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
            # ...or a run that was SIGKILLed while holding it. The reservation
            # is released in a `finally`, which a hard kill does not run, and
            # the leaked directory then skipped that number for ever -- silent,
            # permanent, and indistinguishable from contention. An allocation
            # is milliseconds, so anything older than ALLOC_STALE is a corpse.
            try:
                age = time.time() - marker.stat().st_mtime
            except OSError:
                age = 0.0
            if age > ALLOC_STALE:
                with contextlib.suppress(OSError):
                    marker.rmdir()
                continue            # retry THIS number, now unheld
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


def _sidebar_add(notebook, name):
    """
    Name the new chapter in `_quarto.yml`'s sidebar, keeping the list sorted.

    The sidebar names each chapter rather than using `- auto: "chapters"`,
    which would need no maintenance but wraps every chapter in a redundant
    "Chapters" heading. The cost is this function, and the risk it carries is
    that a chapter missing from the list is INVISIBLE -- so rule 38 checks it,
    turning a silent omission into a lint failure.

    Rewrites the whole block sorted rather than appending: allocation can walk
    past a collision, a claimed stub is renamed, and appending would put those
    out of order. Never raises -- a sidebar line is not worth failing a chapter
    that has already been created on disk, and rule 38 will say so.
    """
    cfg = notebook.root / "_quarto.yml"
    try:
        lines = cfg.read_text().splitlines(keepends=True)
    except OSError:
        return
    entry = f'      - auto: "chapters/{name}"\n'
    if entry in lines:
        return
    idx = [i for i, l in enumerate(lines)
           if l.startswith('      - auto: "chapters/')]
    if idx:
        block = sorted(set(lines[i] for i in idx) | {entry})
        out = [l for i, l in enumerate(lines) if i not in set(idx[1:])]
        out[out.index(lines[idx[0]])] = "".join(block)
    else:
        # First chapter in a fresh notebook: the scaffold leaves the marker
        # comment and no entries, so anchor on the Overview item above it.
        anchor = next((i for i, l in enumerate(lines)
                       if l.strip() == "href: index.qmd"), None)
        if anchor is None:
            return
        while anchor + 1 < len(lines) and lines[anchor + 1].lstrip().startswith("#"):
            anchor += 1
        out = lines[:anchor + 1] + [entry] + lines[anchor + 1:]
    try:
        cfg.write_text("".join(out))
    except OSError:
        pass


def create_chapter(notebook, name, title, defines="", claim=True,
                   number=None, fork_from="", supersedes=()):
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

    # The number is the chapter's place in the sidebar and the front of its
    # title, so both are derived from the directory name that allocation just
    # settled -- never from the caller's guess, which `_allocate` may have
    # walked past. `order` is what stops the sidebar falling back to readdir
    # order (rule 33). The title used to carry the number too, as insurance
    # against a mis-sorted sidebar; `order:` sorts it, breadcrumbs name the
    # chapter on every entry page, and the number was being paid for in the
    # narrowest column on the page. A title that arrives numbered is stripped,
    # so an agent copying an older one does not reintroduce it.
    n = int(name[:2])
    numbered = title.split(" · ", 1)[1] if " · " in title else title
    sub = lambda s: (s.replace("__CHAPTER__", name)
                      .replace("__TITLE__", numbered)
                      .replace("__ORDER__", str(n))
                      .replace("__WHAT_DEFINES_THE_CHAPTER__", defines or PLACEHOLDER))

    (target / "_model.qmd").write_text(sub((SCAFFOLD / "_model.qmd.tmpl").read_text()))
    (target / "index.qmd").write_text(sub((SCAFFOLD / "index.qmd.tmpl").read_text()))
    # The chapter's standing commitments, as data. The index RENDERS this; it
    # is not markdown any more, because a superseded item has to be movable and
    # a Quarto cell cannot annotate markup already on the page.
    (target / "_inputs.yml").write_text((SCAFFOLD / "_inputs.yml.tmpl").read_text())
    forked = ""
    if fork_from:
        ref, src = _fork_sources(notebook, fork_from)
        if src.get("_model.py"):
            # The provenance goes BESIDE the model, not inside it. A header in
            # `_model.py` would make every later correction dirty the file
            # under rule 12 and re-prove the whole chapter -- so the record
            # most likely to need editing would be the most expensive to edit.
            # `_fork.yml` costs nothing to correct, for ever.
            (target / "_fork.yml").write_text(
                f"# What this chapter changed, and from what. Read by rule 31,\n"
                f"# by the chapter index, and by the lineage diagram on the\n"
                f"# book index -- one source, three readers.\n"
                f"parent: {fork_from}\n"
                f"at: {ref}\n"
                # Counted HERE because here is the only place it is known
                # exactly. Afterwards it can only be inferred from filename
                # dates, which are day-granular, and the five forks that
                # predate this field all had to be guessed that way.
                f"at_entry: {len(notebook.entries(fork_from))}\n"
                f'summary: "TODO: what the design BECAME, a few words"\n'
                f"changes:\n"
                f"  - TODO: one line per deliberate difference, as you make it\n"
                # OPTIONAL, and the only forward link the record has. A chapter
                # index is append-only and true as of its date: without this,
                # the parent goes on declaring what this chapter replaced, for
                # ever, with nothing on either page to say so.
                f"# Items from an EARLIER chapter that this one REPLACES, as\n"
                f"# `<chapter>: <id>`, where the id is the handle in that\n"
                f"# chapter's _inputs.yml. Naming one moves it into that\n"
                f"# page's Superseded callout -- the only forward link an\n"
                f"# append-only record has. Rule 31 refuses an unknown id.\n"
                f"supersedes:\n"
                # SEEDED from what the user struck at the new-chapter gate.
                # Striking "foam 5 mm" for a 3 mm fork IS declaring that this
                # chapter supersedes it; recording that fact twice, in two
                # formats, by two actors, with nothing checking they agree, is
                # what the two mechanisms were doing before.
                + "".join(f"  - {c}: {i}\n" for c, i in supersedes))
            (target / "_model.py").write_text(src["_model.py"])
            (target / "_analysis.py").write_text(src.get("_analysis.py") or "")
            forked = (f"\n\n_model.py and _analysis.py were COPIED from "
                      f"chapters/{fork_from}/ at commit {ref} -- from the "
                      f"commit, not the working tree, so nothing half-finished "
                      f"came across. chapters/{name}/_fork.yml is already "
                      f"written with the parent and the commit: replace its "
                      f"TODO line with one line per deliberate difference as "
                      f"you make them, and change nothing you did not mean to. "
                      f"Rule 31 reads that file, and the arrow on the book "
                      f"index is drawn from it: your `summary:` labels the "
                      f"arrow into this chapter, so write what the design "
                      f"BECAME rather than `from → to`.")
    if not forked:
        (target / "_model.py").write_text((SCAFFOLD / "_model.py.tmpl").read_text())
        (target / "_analysis.py").write_text("")

    # The book index draws the chapter graph from these files, and rule 12
    # cannot protect it: rule 12 fires on a dirty `_model.py` against THAT
    # chapter's freeze, and the root index belongs to no chapter. So a new
    # chapter would leave the front page serving an N-1 node diagram from its
    # own freeze, silently. Deleting the freeze here makes the next render
    # rebuild it, by construction rather than by a rule.
    _index_freeze = notebook.root / "_freeze" / "index"
    _had = _index_freeze.exists()
    shutil.rmtree(_index_freeze, ignore_errors=True)
    # Said out loud, because a deleted freeze is work the NEXT render pays for
    # and nothing connected the two: the book index re-executing was the one
    # unexplained page in a later render's count.
    say(f"  freeze    _freeze/index/ {'deleted' if _had else 'absent'} — "
        f"create_chapter; the book index re-executes on the next render")
    _sidebar_add(notebook, name)

    what = (f"claimed the empty scaffold chapters/{stub}/ as chapters/{name}/"
            if stub else f"created chapters/{name}/")
    return name, (
            f"{what} with index.qmd, _model.qmd, _model.py and an empty "
            f"_analysis.py.{forked}\n\n"
            f"If you build this chapter's _model.py by COPYING an earlier "
            f"chapter's, declare it in chapters/{name}/_fork.yml before you "
            f"render anything (rule 31): `parent: NN-name`, `at: <commit>`, "
            f"and a `changes:` list with one line per deliberate difference. "
            f"`diff` against the parent is then the review, and an empty diff "
            f"everywhere else is the positive check. The file is beside the "
            f"model rather than inside it precisely so writing it later costs "
            f"nothing -- editing _model.py after the chapter is frozen costs a "
            f"full re-prove to clear rule 12.\n\n"
            f"If this chapter REPLACES something an earlier chapter's index "
            f"declares -- a foam thickness, an airfoil, an assumption it makes "
            f"false -- list it under `supersedes:` as `NN-name: <the item>`. "
            f"That is the only forward link the notebook has: without it the "
            f"earlier page goes on declaring what you just replaced, and a "
            f"reader landing there cannot tell. Both pages then show the link, "
            f"and a fork below you stops inheriting the dead version. Delete "
            f"the block if this chapter replaces nothing.\n\n"
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

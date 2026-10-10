"""
Everything that happens to an entry after the model stops typing.

NOT A PHASE ANY MORE. This was `nb write`, the second half of a two-process run
reading `proposal.json`; the run does not stop in the middle now, so the loop
and the gates live together in `cli/run.py` and what is left here is the
machinery they call -- stem allocation, the ceiling read, the freeze refreshes,
the commit, and the rendered prose that gets printed at the end.

The name survives because every one of these is about the WRITTEN entry rather
than about the question, and because `nb write` is in old logs, old commit
messages and muscle memory.
"""

import json
import os
import pathlib
import re
import subprocess
import time

from ..config import Notebook
from ..tools import verifiers
from ..process import runstate
from ..process.log import tell

def _stem(notebook, chapter, title, today):
    """
    `YYYY-MM-DD-NN-slug`; NN counts within the day so same-day entries sort.

    A file already carrying this slug for today is REUSED rather than numbered
    past. That is the resume case: a run that wrote the entry and then failed
    at the render left it on disk, and counting it as a sibling would write
    `-02-` beside it and orphan the first, each time round.
    """
    slug = "".join(c if c.isalnum() else "-" for c in title.lower())
    slug = "-".join(p for p in slug.split("-") if p)[:70].rstrip("-")
    existing = [p.name for p in notebook.entries(chapter)]
    mine = [e for e in existing if e.startswith(today) and e[14:] == f"{slug}.qmd"]
    if mine:
        return mine[0][:-len(".qmd")]
    n = sum(1 for e in existing if e.startswith(today)) + 1
    return f"{today}-{n:02d}-{slug}"


def frozen_markdown(notebook, chapter, stem):
    """
    The entry's rendered markdown, with every inline expression resolved.

    The one place the finished entry can be read: rule 1 forces the numbers in
    prose to be `{python} …`, so the SOURCE contains none of the entry's actual
    claims. Three readers now -- the render cost, the prose, and the one-line
    answer recorded for a coordinator -- where there were two copies of the
    same four lines.
    """
    p = notebook.freeze / chapter / stem / "execute-results" / "html.json"
    try:
        return json.loads(p.read_text())["result"]["markdown"]
    except (OSError, ValueError, KeyError):
        return None


def _render_cost(notebook, chapter, stem):
    """
    (solves, seconds) from the entry's own footer line, or None.

    Read back off the freeze rather than timed here, so the number recorded is
    the one the published page shows -- footer() prints
    `[Rendered in 2.4 s (limit 20 s) · 1 aero solve …]` and rule 17 judges that
    same line, through the same regex in `lint`. Two sources for one quantity is
    how they come to disagree.
    """
    md = frozen_markdown(notebook, chapter, stem)
    if md is None:
        return None
    from ..contract import shared
    secs = shared.RUNTIME_SECONDS.search(md)
    if not secs:
        return None
    solves = shared.RUNTIME_SOLVES.search(md)
    return int(solves.group(1)) if solves else 0, float(secs.group(1))


def _why_and_diff(filename, fn, before, after, note):
    """
    One changed function, as the model explained it and as the source shows it.

    The note is the model's account and the diff is the evidence, in that order
    and visibly separated -- a reason nobody can check is worth reading and
    worth doubting. `guards.bodies()` stores `ast.unparse` output, so the diff
    is of normalised source: comments and original spacing are gone, which
    makes it a poor patch and a good summary of what actually moved.
    """
    import difflib
    head = f"\n  {filename}:{fn}()"
    said = (f"\n      said: {note}" if note else
            "\n      said: (nothing — declare_refactor was not called)")
    body = "\n".join(
        f"      {l.rstrip()}" for l in difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            lineterm="", n=1)
        if not l.startswith(("---", "+++")))
    return f"{head}{said}\n{body}"


def _touched(notebook, chapter, *names):
    """Which of `names` in this chapter git sees as changed."""
    repo = notebook.root.parent
    out = []
    for name in names:
        f = notebook.chapters_dir / chapter / name
        if not f.exists():
            continue
        rel = str(f.relative_to(repo))
        if subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=repo,
                          capture_output=True, text=True).stdout.strip():
            out.append(rel)
    return out


def _ceiling_problem(notebook, entry_path, granted):
    """
    The entry declares an ENTRY_CEILING other than the one granted, or None.

    A SOURCE READ. Nothing renders, nothing solves -- which is why it now runs
    beside the lint gate instead of beside the commit. It used to sit in the
    commit block, after the entry had been rendered and after a moved shared
    function had re-proved every sibling, so a run could pay for minutes of
    solves and then be refused over a literal in the first cell. Measured:
    3 of 33 write runs ended `ceiling_changed`, each having paid for the whole
    phase first.

    Repairable, too, and that is the other half. The model wrote the wrong
    number and can write the right one in a turn, so this is handed back the
    way a lint violation is handed back rather than ending the run. The check
    before the commit stays as the guarantee -- the same relationship lint has
    with its own tool: one lets the loop fix it, the other is what makes it
    true.
    """
    if granted is None:
        return None
    from ..contract import shared
    _, declared = shared.limits_of(notebook.root, entry_path)
    if declared == granted:
        return None
    return (f"ENTRY_CEILING is {declared}, but {granted:.0f} s was granted at "
            f"the prompt. The budget is the user's to set, not yours: write "
            f"ENTRY_CEILING = {granted:.1f} in the entry's first cell. If the "
            f"work genuinely needs more, ask for it with `ask_specified` -- "
            f"that stops and asks a person, and the entry records the answer.")


def _render_page(notebook, page, why, stale_note):
    """
    Render one page targeted, warn if it did not, return its freeze or None.

    THE RECIPE THREE CALLERS SHARE, and it has one subtlety worth having in one
    place: a targeted render IGNORES the freeze by definition, so nothing is
    deleted first. `_refresh_root_index` used to `rmtree` and then render,
    ignoring the result -- a failed render left no freeze, `_commit` skips a
    path that does not exist, and rule 40's "no freeze means no finding" escape
    meant nothing ever said so. A failure now leaves the OLD freeze in place,
    stale, where rule 40 can see it.

    `page` is relative to the notebook root; the freeze path is derived from it,
    since Quarto's layout is `_freeze/<page without suffix>/`.
    """
    out = verifiers.render(notebook, page, why=why)
    if "FAILED" in str(out):
        tell(f"  {stale_note}")
        return None
    freeze = notebook.root / "_freeze" / pathlib.Path(page).with_suffix("")
    return freeze if freeze.exists() else None


def _refresh_index_freeze(notebook, chapter):
    """
    Drop the chapter index's freeze when what it renders has moved.

    Quarto's freeze tracks the PAGE, not its includes -- so a chapter index,
    which execs `_model.py` and prints its source, goes on showing the version
    it was frozen against forever. Rule 19 makes that live: `_model.py` now
    changes on every new-chapter run.

    Scoped to the one index, and only when git says an input actually changed.
    `check.py` solves the same problem by deleting a whole chapter's freeze and
    re-solving it, which is right when proving a refactor moved nothing and far
    too expensive here.

    RENDERED, not merely deleted -- the same correction `_refresh_root_index`
    already carries. Deleting left `_commit` nothing to commit (it adds this
    freeze only `if it exists`) and `site()` rebuilt it AFTER the commit, so
    the chapter index freeze was never committed at all: observed on the first
    X-Wing entry, where `_freeze/chapters/01-first-chapter/index/` came out of
    the run untracked. A targeted render ignores the freeze by definition, so
    there is nothing to delete first, and an index costs RENDER_INDEX because
    it prints source rather than solving.
    """
    if not _touched(notebook, chapter, "_model.py", "_analysis.py",
                    "_inputs.yml", "_fork.yml", "_active.yml"):
        return
    _render_page(
        notebook, f"chapters/{chapter}/index.qmd",
        "the chapter index renders files this run changed",
        f"index     chapters/{chapter}/index.qmd did NOT rebuild — its "
        f"freeze is a version behind.")


def _refresh_active(notebook):
    """
    Rewrite every chapter's `_active.yml`, re-render the indexes that moved,
    and return the paths the commit has to carry.

    WHOLE-NOTEBOOK, and NOT because a new entry moves what a descendant
    inherits -- it cannot. Each fork is frozen at its `at_entry` cutoff, so an
    entry written afterwards was never part of what the child was built on.
    This said the opposite, and it was a confident wrong reason for a right
    thing.

    The right reason is that the file which goes stale is never the one this
    run wrote: a promotion into an ancestor's `_inputs.yml`, an added
    `overwrites:`, or a refactor touching a pre-cutoff entry all move a
    DESCENDANT's copy. Those are rare, the sweep is a YAML read per chapter and
    solves nothing, and a stale `_active.yml` is worse than none -- it is a
    confident list of the wrong commitments.

    Rendered, not merely invalidated, for the reason `_refresh_root_index`
    spells out at length: a freeze deleted here and rebuilt by `site()` after
    the commit is a freeze that never gets committed.

    A failed render is reported and not fatal. The page is one tick behind; the
    entry that this run actually wrote is unaffected, and rule 40 will say so.
    """
    from ..domain.inputs import refresh_active
    moved = refresh_active(notebook)
    if not moved:
        return []
    paths = []
    for c in moved:
        paths.append(notebook.chapters_dir / c / "_active.yml")
        freeze = _render_page(
            notebook, f"chapters/{c}/index.qmd",
            "what this chapter maintains changed",
            f"index     chapters/{c}/index.qmd did NOT rebuild — its "
            f"maintained list is a version behind.")
        if freeze:
            paths.append(freeze)
    tell(f"  inherited {len(moved)} chapter index"
         f"{'' if len(moved) == 1 else 'es'} refreshed")
    return paths


def _refresh_root_index(notebook):
    """
    Redraw the notebook's front page, BEFORE the entry is committed.

    The lineage diagram counts each chapter's entries, so committing an entry
    changes what that page should show -- and the root index belongs to no
    chapter, so rule 12 cannot notice. `create_chapter` already deletes this
    freeze for the case where a chapter appears; this is the same failure for
    the case where an ENTRY appears, which is every run.

    Before the commit, and rendered rather than merely invalidated. `site()`
    runs after the commit on purpose -- so an unrelated broken page cannot
    block an entry that passed on its own terms -- and a freeze deleted here
    but rebuilt there would leave the new diagram dirty in the tree and the
    committed one a tick behind, for ever.

    TARGETED, which is both cheaper and more correct: a targeted render ignores
    the freeze, so the page is guaranteed to re-execute. Measured at 10 s
    against 50 s for a project render, and it rewrites exactly one freeze -- it
    does not re-solve the notebook.

    NOTHING IS DELETED FIRST, and that is the fix to a hole this opened. It
    used to `rmtree` the freeze and then render, ignoring the render's result:
    if that render failed, the freeze was gone, `_commit` skipped it (it
    commits the path only `if root_freeze.exists()`), and rule 40's "no freeze
    means no finding" escape meant nothing ever said so -- the one failure the
    rule exists to catch, let through by the code that calls it. The delete was
    never needed: a targeted render ignores the freeze by definition, which is
    the property this function already relies on. A failed render now leaves
    the OLD freeze in place, stale, where rule 40 can see it.
    """
    if not (notebook.root / "index.qmd").exists():
        return
    if _render_page(
            notebook, "index.qmd",
            "the front page counts entries, and one was just added",
            "front     the lineage diagram did NOT rebuild — the front page "
            "is a tick behind.") is None:
        tell("            The entry is unaffected. Rule 40 will report it; "
             "`quarto render index.qmd` clears it.")


# EVERY fenced block, not just the python ones. The rendered markdown carries
# two kinds -- the echoed source, which Quarto tags "``` {.python .cell-code}",
# and captured STDOUT, which is a bare "```" fence. The first version matched on
# "python" and let sixty lines of IPOPT convergence table through ahead of the
# answer. Nothing a reader wants is inside a fence: the hero, the prose, the
# callouts and the tables are all outside them.
CODE_CELL = re.compile(r"^```+[^\n]*\n.*?^```+[ \t]*$", re.S | re.M)


def rendered_prose(notebook, chapter, stem):
    """
    The entry as it actually rendered, with every inline expression resolved.

    Rule 1 forces the numbers in prose to be `{python} …` expressions, so the
    SOURCE contains none of the entry's actual claims -- they exist only in the
    freeze. This is therefore the one place the finished entry can be read, and
    until now nothing ever showed it to a human: the only reader of the freeze
    was `verify`, and `verify` was a model.

    Code cells stripped, which is most of the bytes and none of the argument:
    measured 5,624 tokens full against 851 without.
    """
    md = frozen_markdown(notebook, chapter, stem)
    if md is None:
        return None
    md = CODE_CELL.sub("", md)
    # Quarto writes a figure's path relative to the chapter directory, so it
    # resolves nowhere from a terminal and nowhere at all for a coordinator
    # reading this prose off a pipe. The same PNG sits under the freeze, which
    # exists the moment the entry renders -- before this runs, and whether or
    # not a site was ever built. Rewriting it here keeps the figure inline,
    # where the argument put it, and keeps its caption, which is usually the
    # densest sentence written about it.
    md = md.replace(f"]({stem}_files/", f"]({notebook.freeze / chapter / stem}/")
    # Quarto's cell wrappers and anchors carry nothing a reader wants. The
    # attributes have to go with the anchor: an image carries its measured
    # `{#fig-x width=901 height=458}`, and stripping the id alone left the
    # dimensions sitting in the prose.
    md = re.sub(r"^:::+.*$", "", md, flags=re.M)
    md = re.sub(r"\{#[\w-]+[^}]*\}", "", md)
    return _readable(md) or None


# Quarto markup that means nothing outside a rendered page.
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
SPAN = re.compile(r"\[([^\]]*)\]\{\.[\w-]+\}")     # [12.7°]{.hero-value}
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HERO = re.compile(r"\[([^\]]*)\]\{\.hero-value\}\s*\n\[([^\]]*)\]\{\.hero-label\}")
# Quarto escapes whatever pandoc might read as markup, and the set is wider
# than it first appears: `\.` in a decimal, but also `\+` in a derivative sign,
# which left C_m_alpha = \+0.39 on screen. Any backslash before punctuation is
# an escape here, because prose has no other reason to carry one.
ESCAPED = re.compile(r"\\([^\w\s])")                 # 0\.10 -> 0.10, \+ -> +


def _readable(md, width=76):
    r"""
    The rendered entry as something a person can read in a terminal.

    The freeze holds Quarto markdown, and printing it raw put `---` frontmatter,
    `[12\.7°]{.hero-value}` spans, escaped decimals and `{.runtime}` in front of
    the reader -- the answer was in there, but it had to be dug out.

    A presentation layer rather than a change to what is stored: the freeze is
    untouched, and the same cleanup serves a coordinator reading this off a
    pipe, which is no better served by span syntax than a person is.

    Figures keep their caption and their absolute path, on separate lines --
    the path is long enough that inlining it buried the sentence that explains
    what the figure shows.
    """
    import textwrap
    title = ""
    m = re.search(r'^title:\s*"(.+)"$', md[:400], re.M)
    if m:
        title = m.group(1)
    # THE SUBTITLE COMES WITH THE TITLE, before the block is dropped. It is the
    # justification the question arrived with, and a coordinator reading its own
    # run back off `run.json` should see the reason beside the question -- the
    # alternative is reading the `.qmd` to find a line it wrote itself.
    sub = re.search(r'^subtitle:\s*"(.+)"$', md[:600], re.M)
    md = FRONTMATTER.sub("", md)
    # The hero pair is one fact -- a number and what it measures -- written as
    # two spans on two lines so the page can style them. Joined before the
    # spans are stripped, which is the only point where they are still
    # distinguishable from ordinary prose.
    md = HERO.sub(lambda m: f"{m.group(1)}  {m.group(2)}", md)
    md = SPAN.sub(r"\1", md)
    md = ESCAPED.sub(r"\1", md)
    md = md.replace("**", "")

    out = [title, ""] if title else []
    if sub:
        out += [sub.group(1), ""]
    for line in md.splitlines():
        line = line.rstrip()
        if not line:
            continue
        img = IMAGE.match(line.strip())
        if img:
            cap, path = img.group(1), img.group(2)
            out.append("")
            out += textwrap.wrap(f"figure  {cap}", width=width,
                                 subsequent_indent="        ")
            out.append(f"        {path}")
            continue
        if line.startswith("#"):
            # A callout heading is a LABEL for what follows, not a section of
            # its own. Rendered as a bare line it competed with the answer --
            # "Specified" in the same weight as the sentence the entry exists
            # for. Lower-cased and indented, it reads as the caption it is.
            out += ["", f"  {line.lstrip('# ').lower()}"]
            continue
        if line.startswith("Answer."):
            if out and out[-1]:
                out.append("")
            line = line[len("Answer."):].lstrip()
            out += ["ANSWER", ""]
        indent = "  " if out and out[-1].startswith("  ") else ""
        out += textwrap.wrap(line, width=width, initial_indent=indent,
                             subsequent_indent=indent) or [""]
    return "\n".join(out).strip()


def answer_line(notebook, chapter, stem):
    """
    The entry's hero value and what it measures, as one line, or None.

    WHAT THE RUN CONCLUDED, for whoever is reading `run.json` rather than
    watching. `outcome: committed` and a sha say the work happened; they do not
    say it came out at 5.38. A coordinator deciding what to ask next needs the
    answer, and until now the only place it existed in words was the prose
    printed into `status.log` -- a timestamped text file nothing parses.

    The hero pair is one fact written as two spans so the page can style them,
    which is why it is joined here before the spans are stripped: after `SPAN`
    runs they are indistinguishable from ordinary prose.

    None for an entry with no hero, which is a real and legitimate state -- an
    entry whose answer is a drawing, or a comparison, has no single number.
    """
    md = frozen_markdown(notebook, chapter, stem)
    m = HERO.search(md) if md else None
    if not m:
        return None
    clean = lambda t: ESCAPED.sub(r"\1", t).replace("**", "").strip()
    value, label = clean(m.group(1)), clean(m.group(2))
    return f"{value} — {label}" if label else value or None


def _commit_with_lock_retry(repo, title, paths, attempts=3):
    """
    `git commit -m <title> -- <paths>`, retried past a held index.lock.

    Git does not queue on `.git/index.lock`; it fails immediately. The window is
    small -- a commit is milliseconds at the end of a run measured in minutes --
    but it is a loud, harmless, retryable failure, which is the easy kind.
    """
    for attempt in range(attempts):
        out = subprocess.run(["git", "commit", "-m", title, "--"] + paths,
                             cwd=repo, capture_output=True, text=True)
        if out.returncode == 0 or "index.lock" not in (out.stdout + out.stderr):
            return out
        time.sleep(0.5 * (attempt + 1))
    return out


def _commit(notebook, chapter, stem, entry_path, title, extra_paths=()):
    """
    Commit exactly what this run produced, by path.

    Never `git add -A`. The working tree carries untracked Quarto output --
    `chapters/**/*.html`, `site_libs/` -- from any `quarto preview` or render
    that happened to be running, and a blanket add sweeps it into history.

    `extra_paths` exists for an accepted refactor. `check` deletes and
    re-renders EVERY page that reaches the changed function, so the siblings'
    frozen output on disk no longer matches what is committed -- and committing
    only this entry's freeze would leave the repository in the exact state the
    freeze exists to prevent, a committed freeze that does not correspond to the
    committed code.
    """
    repo = notebook.root.parent
    rel = lambda p: str(pathlib.Path(p).relative_to(repo))

    paths = [rel(entry_path)]
    paths += [rel(p) for p in extra_paths if pathlib.Path(p).exists()]
    freeze = notebook.freeze / chapter / stem
    if freeze.exists():
        paths.append(rel(freeze))
    # The chapter index's own freeze, for the same reason: `_refresh_index_freeze`
    # drops it whenever what it renders moved, so a run that created or changed
    # the chapter leaves a rebuilt one on disk that nothing else commits.
    index_freeze = notebook.freeze / chapter / "index"
    if index_freeze.exists():
        paths.append(rel(index_freeze))
    # And the ROOT index's, which nothing committed before the front page
    # started counting entries. Without it the diagram in git disagrees with
    # the entries in git -- and a new-chapter run already left it dirty, since
    # `create_chapter` deletes it and only `site()` rebuilt it, after the
    # commit.
    root_freeze = notebook.root / "_freeze" / "index"
    if root_freeze.exists():
        paths.append(rel(root_freeze))
    # Shared machinery the run may have touched -- rule 2 promotion lands here.
    # index.qmd and _model.qmd are in the list for a NEW chapter: they are
    # scaffolded, not written by the model, so they were missing from every
    # commit that created one -- leaving a chapter in history with an entry but
    # no index, and a fresh clone with nothing to render the aircraft from.
    # `_inputs.yml` and `_fork.yml` joined the list when the chapter index
    # stopped carrying its callouts and started RENDERING them. Without them
    # the first X-Wing commit carried the entry, `_model.py` and the freezes
    # while the SOURCE of the chapter's Specified and Assumed items stayed
    # uncommitted in the working tree -- the exact invariant the note above
    # states: the committed freeze stops matching the committed code.
    # `_active.yml` is here as well as in `_refresh_active`'s return, and the
    # overlap is the point: a run that CREATES a chapter has the file written
    # by `create_chapter`, so the refresh finds it already correct, returns it
    # in no list, and the new chapter would be committed with a rendered
    # inherited callout whose source was never added.
    for name in ("_analysis.py", "_model.py", "index.qmd", "_model.qmd",
                 "_inputs.yml", "_fork.yml", "_active.yml"):
        f = notebook.chapters_dir / chapter / name
        if f.exists():
            changed = subprocess.run(
                ["git", "status", "--porcelain", "--", rel(f)],
                cwd=repo, capture_output=True, text=True).stdout.strip()
            if changed:
                paths.append(rel(f))

    # THE SIDEBAR, which is notebook-level and which creating a chapter edits.
    # `create_chapter` calls `_sidebar_add` to put `- auto: "chapters/NN-name"`
    # into `_quarto.yml`, and this list covered only the six files INSIDE a
    # chapter -- so every fork committed the chapter and left its navigation
    # entry dirty in the working tree. A fresh clone would then render the
    # chapter with no way to reach it, which is the state rule 38 exists to
    # call loud rather than invisible.
    #
    # Same shape as the `_inputs.yml`/`_fork.yml` omission before it: the
    # commit knew about a chapter's own files and missed the one a chapter
    # creation writes somewhere else.
    cfg = notebook.root / "_quarto.yml"
    if cfg.exists() and subprocess.run(
            ["git", "status", "--porcelain", "--", rel(cfg)],
            cwd=repo, capture_output=True, text=True).stdout.strip():
        paths.append(rel(cfg))

    add = subprocess.run(["git", "add", "--"] + paths, cwd=repo,
                         capture_output=True, text=True)
    if add.returncode != 0:
        return None, f"git add failed: {add.stderr.strip()[:200]}"

    # PATHSPEC, not a bare commit. `git commit -m <title>` commits the whole
    # INDEX, so a second run that has staged its own entry in the meantime gets
    # swept into this one -- verified: A's commit contained both A's and B's
    # files, under A's message, and B was then left with nothing to commit. A
    # pathspec-limited commit takes working-tree content for exactly these paths
    # and ignores the rest of the index, so two runs cannot contaminate each
    # other. The `git add` above still matters: it is what makes a NEW file
    # known to git, which `commit -- <path>` alone does not do.
    out = _commit_with_lock_retry(repo, title, paths)
    if out.returncode != 0:
        return None, f"git commit failed: {(out.stdout + out.stderr).strip()[:200]}"
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    return sha, ", ".join(paths)


def _resolve(notebook_path, run_id):
    """
    (notebook, refusal) -- which run this resumes, or why it will not guess.

    With no id, `Notebook` picks the most recently TOUCHED run directory, which
    is exactly right for one agent ("the run I was just in") and a coin toss for
    several: the freshest directory may belong to an agent still working, and
    resuming into it means two processes writing one run's log and state.

    So the same rule `nb answer` and `nb stop` already follow -- name the run
    when more than one is live -- plus a flat refusal to resume a run that is
    still going, however it was chosen. Guessing here is silent, and the thing
    it corrupts is the telemetry you would use to notice.
    """
    notebook = Notebook(notebook_path, run_id=run_id)
    live = []
    for d in notebook.runs():
        state = runstate.read(d)
        # OUR OWN pid is not someone else's run. `ask` continues into `write`
        # inside one process, handing it the run id it has been writing all
        # along -- so without this the phase would refuse to run the moment it
        # was reached the normal way.
        # No pid comparison any more. It was here because a resume reads the
        # run it is about to take over and would have called itself live;
        # the lock answers that directly -- we have not taken it yet, and the
        # process that did is gone.
        if state and runstate.alive(d) is True:
            live.append((d.name, state))

    if run_id is None and len(live) > 1:
        lines = [f"  {len(live)} runs are live — name the one to resume:"]
        lines += [f"    {name}  {st.get('chapter') or '—'}  "
                  f"{st.get('phase', '?')} turn {st.get('turn', '?')}"
                  for name, st in live]
        return notebook, lines

    if run_id is not None and run_id not in {d.name for d in notebook.runs()}:
        return notebook, [f"  no such run: {run_id}"]

    if any(name == notebook.run_id for name, _ in live):
        return notebook, [
            f"  {notebook.run_id} is still running — resuming it would put two "
            f"processes in one run.",
            f"  Wait for it, or stop it: nb stop {notebook.root.name} "
            f"{notebook.run_id}"]
    return notebook, None


# `+/-2%`, `+/- 2 %`, `±5%`. The tolerance is what turns a published figure
# into something a gate can check; a target row without one is a figure
# somebody wrote down and did not commit to.
TOLERANCE = __import__("re").compile(r"[+±]\s*/?-?\s*([\d.]+)\s*%")


def targets_unreported(notebook, entry_path, targets):
    """
    One line naming the targets the entry never mentions, or "".

    THE GATE IS ON REPORTING, NOT ON PASSING, and that is deliberate. A
    reconstruction that misses a target is a finding -- "wing area is 7.3%
    under, and the vertical stab is the likely cause" is exactly the entry
    worth having. A reconstruction that misses one SILENTLY is the failure:
    the model converges on what it can hit, writes a confident entry, and the
    target nobody mentioned is the one that was wrong.

    So this refuses an entry that does not name every target, and never
    refuses one for the value it reports. Loosening a tolerance to pass is
    then pointless, because passing was never the bar.

    MATCHED ON THE QUANTITY'S NAME, never on its value. Rule 1 means every
    number in prose is a `{python}` expression, so the digits are not in the
    source at all -- the first version of this matched on the HANDLE's words,
    which for `length-482-mm` meant requiring the literal "482". No
    rule-compliant entry can satisfy that, and it refused a correct
    reconstruction with "7 target(s) the entry never mentions". `cg-38-mm`
    was worse: after dropping short tokens it had no words left and could
    never match anything.

    So the label is taken from the TEXT, before the colon -- `**Wing area**:
    7.42 dm2, +/-3%` gives "wing area" -- which is what a reader writes and
    what the prose actually contains.
    """
    if not targets:
        return ""
    try:
        body = entry_path.read_text().lower()
    except OSError:
        return ""
    missing = []
    for _handle, text, _given in targets:
        label = text.split(":")[0]
        words = [w for w in re.findall(r"[a-z]+", label.lower()) if len(w) > 1]
        if words and all(w in body for w in words):
            continue
        missing.append(label.strip("* "))
    if not missing:
        return ""
    return (f"{len(missing)} target(s) the entry never mentions: "
            + "; ".join(missing)
            + ". Report every target with its error, including the ones that "
              "passed -- a target that misses is a finding, a target nobody "
              "names is a hole.")


# =============================================================================
# THE TARGET BASELINE -- `_reference/targets.lock`, beside the assets.
#
# RENDERING RECOMPUTES; IT DOES NOT ASSERT. Rule 12 keeps a committed page's
# freeze no older than its model and the refactor gate re-renders every
# sibling that reaches a changed function, so the numbers are always current.
# But push wing area from 0.01% error to 15% and the entry renders perfectly
# happily: the chart draws a longer bar, the prose reads 15% because rule 1
# made it an inline expression, and nothing fails. Somebody has to look.
#
# WHY NOT SIMPLY FAIL WHEN A TARGET MISSES. Because the same signature means
# opposite things at different moments:
#
#     first reconstruction   a miss is a FINDING    -- "area is 7% under,
#                                                      the stab is the cause"
#     after it is accepted   a miss is a REGRESSION -- something drifted
#
# The retired frozen-corpus sweep solved exactly this shape for lint: it
# recorded the expected count per notebook and failed when one moved, requiring
# the baseline to be updated in the same commit that justifies it. So: no
# baseline means a miss is a finding; a baseline means a WORSENING is a
# regression.
#
# Nothing has drifted yet. This is built because the mechanism was already
# in the repo and the next person should not have to rediscover it, and it
# is inert until a baseline is written.
BASELINE = "targets.lock"
BASELINE_SLACK = 1.25     # a quarter worse before it counts as drift


def _baseline_path(notebook):
    from ..tools.figures import REFERENCE_DIR
    return notebook.root / REFERENCE_DIR / BASELINE


def read_baseline(notebook):
    """{handle: accepted error %}, or {} when none has been recorded."""
    import json
    try:
        return json.loads(_baseline_path(notebook).read_text())
    except (OSError, ValueError):
        return {}


def write_baseline(notebook, errors):
    """Record the accepted error per target. Called once, by hand or on commit."""
    import json
    p = _baseline_path(notebook)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(errors, indent=2, sort_keys=True) + "\n")
    return p


def targets_drifted(notebook, errors):
    """
    One line naming targets that got WORSE than the baseline, or "".

    `errors` is {handle: error %} as the run just computed them. Silent when
    there is no baseline, which is the first reconstruction and the case
    where a miss is a finding rather than a fault.
    """
    base = read_baseline(notebook)
    if not base or not errors:
        return ""
    worse = []
    for handle, was in base.items():
        now = errors.get(handle)
        if now is None:
            continue
        if abs(now) > max(abs(was) * BASELINE_SLACK, abs(was) + 0.1):
            worse.append(f"{handle} {was:.2f}% -> {now:.2f}%")
    if not worse:
        return ""
    return ("target(s) worse than the recorded baseline: " + "; ".join(worse)
            + f". Either the change is wrong, or {BASELINE} needs updating in "
              "the same commit that justifies it.")


#: What DRAWS a comparison against a photograph, as opposed to a drawing of
#: the model. `plot_photo_comparisons` is the older spelling and is still the
#: only one in the notebooks that have not taken a new `_notebook.py`.
_COMPARES = ("compare_to_photo", "show_comparison", "plot_photo_comparisons")

#: The verdicts the note prints when the picture cannot be read. Keyed on the
#: note's own wording, as rule 45's check is, so the two move together.
_POSE_BAD = ("POSE NOT CONVERGED", "Pose: DOUBTFUL", "pose doubtful")


def shape_check(notebook, chapter, stem):
    """
    Whether the entry checked its shape against a photograph. -> dict.

    THE GAP THIS CLOSES. A coordinator reads `answer`, `prose`, `outcome` and
    `findings`, and is told never to parse `status.log`. So when a run fitted
    every camera DOUBTFUL, gave up on `fit_geometry` and fell back to a
    three-view, all four fields looked healthy and nothing in the record said
    the shape had gone unchecked -- while the entry's headline read "0.01%,
    maximum error across all targets", which was the model compared with
    itself.

    DELIBERATELY NOT A PARSE OF THE PROSE. An earlier version read elevations
    and residuals out of the rendered page, and there is no wording to rely on:
    three notebooks here express the same fact three ways -- `camera 36° ABOVE`,
    `elev 23.9° azim 225.7°`, and `at camera elevation [23.9 deg]{.key}` with
    Quarto spans through it. Extracting numbers from that is the brittle
    text-matching this system refuses to do to `status.log`, and it failed
    silently on two notebooks of three while looking like it worked.

    So it reports only what can be known for certain: whether the entry CALLS
    a photograph comparison, read from its source, and whether the rendered
    page carries a verdict saying the picture cannot be read. `drawn: False`
    is the finding that matters -- the page makes no claim against a
    photograph at all, whatever its prose says.
    """
    try:
        src = (notebook.root / "chapters" / chapter / f"{stem}.qmd").read_text()
    except OSError:
        return None
    drawn = any(n in src for n in _COMPARES)
    md = frozen_markdown(notebook, chapter, stem)
    # Code cells stripped: an entry that PARSES a pose note carries the note's
    # own wording in a regex literal, which is not a result.
    page = CODE_CELL.sub("", md) if md else ""
    bad = sorted({w for w in _POSE_BAD if w.lower() in page.lower()})
    return {"drawn": drawn, "doubtful": bool(bad), "verdicts": bad}

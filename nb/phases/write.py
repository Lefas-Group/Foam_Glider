"""
`nb resume` (`nb write`) -- turn an approved proposal into a committed entry.

Lint is both a tool and a mandatory step. The tool lets the loop fix violations
in place; the step after the loop is the guarantee, because without it the model
can simply decline to call the tool and declare itself done.
"""

import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

from ..config import (MAX_LINT_ATTEMPTS, MAX_RENDER_FIXES, MAX_TURNS,
                      PROBE_POOL, Notebook)
from ..loop import Refactor, Stopped, run
from ..schema import Proposal
from ..session import Session
from ..preflight import check as preflight
from ..tools import guards, verifiers
from ..tools.interact import ask_stuck
from ..tools.scaffold import create_chapter
from .. import metrics
from .view import site
from .common import setup, report, spoken_calls
from ..log import detach_output, open_log, say, tell
from .. import runstate

BRIEF = """\
You are in the WRITE phase. The proposal below was approved. Write the entry.

{proposal}

The probe that produced this is gone -- everything you need is above.

`handoff` is a note to the human about things nobody asked about. Do NOT put it
in the entry: an entry answers the question asked and stops.

1. Create the entry at `{chapter}/{stem}.qmd`. Use `write_file` for the initial
   version, then `edit_file` for every change after that. The entry is the ONLY
   file you create: `index.qmd`, `_model.py` and `_analysis.py` already exist,
   scaffolded, so `edit_file` them. A `write_file` over `index.qmd` silently
   drops the `## The model` block it ships with, which is the only place a
   reader sees the aircraft (rule 30).
   Its FIRST code cell must open with exactly these two lines (rule 28):

       ENTRY_CEILING = {ceiling}   # s for this render, granted by the user
       SOLVE_BUDGET = {solve}     # s for any one solve
       PROBE_POOL = {pool}        # s granted for the probe
       PROBE_SPENT = {spent}      # s the probe actually used

   `render_cost_s` in the proposal is what the probe's solves actually cost,
   timed, not estimated -- size SOLVE_BUDGET from it. A 0.0 means the probe ran
   no solves at all, so it tells you nothing about what this entry will cost;
   it does not mean free.

   ENTRY_CEILING is not yours to choose -- it is what the user granted at the
   prompt, the commit is refused if you change it, and it is the execution time
   the render is killed at, directly and with no slack. SOLVE_BUDGET is yours:
   pick what one solve needs, knowing it cannot outlive the render that
   contains it. Record both in the entry's `## Specified` callout as inline
   `footer()` prints all four at the foot of the page, so they do NOT go in the
   `## Specified` callout -- that callout is for what the DESIGN was committed
   to, and budgets in it crowd out the thing it exists for (rule 18).

   OMIT a callout that would be empty. A box containing the word "None." is
   furniture: it takes a heading and four lines to say that nothing happened,
   and a reader scanning for what was assumed has to read it to find that out.
   No Specified inputs and no Assumptions means neither callout appears.
   If the work genuinely cannot fit, ask for more with `ask_specified` rather
   than writing a different number.
2. Its code must recompute the answer, not restate it. Every number in prose is
   an inline `{{python}}` expression, never typed out (rule 1).
3. Call `lint` with chapter `{chapter}` and fix what it reports. Each message
   names its own fix. Lint runs again after you stop regardless, so there is
   nothing to gain by stopping early.
4. If your entry repeats three or more consecutive code lines from a sibling
   (rule 2), promote them to `{chapter}/_analysis.py` and call from there --
   change only YOUR entry, never the earlier one -- then pass the promoted
   function to `footer(...)` (rule 13).
5. The vehicle lives in `{chapter}/_model.py`, never in the entry cell (rule
   19). If that file is still the bare scaffold, fill it: the aircraft, its
   operating conditions, its derived quantities. A parametric vehicle is a
   FUNCTION there taking the design variables and returning the `Airplane`;
   the entry calls it.

   HOW THE CHAPTER COMPOSES, because nothing else will tell you and a brand new
   chapter has no sibling to copy: `_model.qmd` EXECS both `_model.py` and
   `_analysis.py` into the page namespace. Every name in them is already in
   scope -- in your entry cell, and in each other. They are not modules and are
   not importable; `from _analysis import solve_it` raises ModuleNotFoundError
   at render and is rule 29. Call the name directly.

   A number taken from ANOTHER chapter is assigned in your code cell with a
   comment naming the entry it came from, and your prose names and links that
   entry: [its title](YYYY-MM-DD-NN-slug.qmd). There is no mechanism that
   recomputes it, so the link is the only trail back when someone asks where
   0.36 came from -- and the only warning anyone gets if that chapter is
   re-rendered and the number moves.

   Comments in those two files explain the MODEL, not your reasoning about
   where to put things. They are rendered verbatim by the chapter index.

   `_analysis.py` IS YOURS TO EDIT. Adding a function to it is free and is how
   a chapter grows; `_model.py` is the guarded one, and a write to it is
   refused once the chapter has entries. Rule 2 tells you to promote repeated
   code INTO _analysis.py -- it has been read backwards, as a ban on touching
   it, which leaves each entry carrying its own copy of the same workaround.

   If you EDIT a function that was already in either file -- as opposed to
   adding a new one -- call `declare_refactor` with one line saying what
   changed and why. Editing one means every sibling entry that reaches it gets
   re-solved to prove its answers held, and the user decides whether to accept
   that; they are shown your line beside the diff. Adding a function needs
   nothing, which is the cheaper path when it is available.

6. A helper that solves takes `verbose=False` and passes it to `opti.solve()`
   (rule 23). IPOPT prints a sixty-line convergence table otherwise, and an
   entry that publishes one has buried its answer under the working. Keep it a
   PARAMETER rather than hard-coding False, so a probe can still turn it on.

7. Anything true of EVERY entry in `{chapter}` belongs in its index.qmd, not in
   your entry -- the section, the objective, the fixed dimensions, what is left
   out. Your entry keeps what THIS question produced. If the index still holds
   template placeholders, fill them (rule 24).

   Attribute each item to where it actually came from. "Asked of the user,
   {today}:" covers ONLY what was put to them and answered -- which includes
   any `ask_specified` answer from the probe that produced this proposal, and
   that answer belongs in a Specified callout, because it is usually the reason
   the chapter exists at all. Commitments inherited from an earlier chapter, or
   read out of the question, are stated without a claim that anyone was asked.

8. The title in the proposal is the entry's title (rule 26): one question, at
   most 18 words, ending in `?`. It is also the filename, so a brief pasted in
   whole gives a 70-character stem nobody can read.

Today is {today}, so the entry stem is already dated for you. Stop when lint is
clean; rendering and committing are handled after you finish.
"""


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


def _render_cost(notebook, chapter, stem):
    """
    (solves, seconds) from the entry's own footer line, or None.

    Read back off the freeze rather than timed here, so the number recorded is
    the one the published page shows -- footer() prints
    `[Rendered in 2.4 s (limit 20 s) · 1 aero solve …]` and rule 17 judges that
    same line, through the same regex in `lint`. Two sources for one quantity is
    how they come to disagree.
    """
    import re
    p = (notebook.freeze / chapter / stem / "execute-results" / "html.json")
    try:
        md = json.loads(p.read_text())["result"]["markdown"]
    except (OSError, ValueError, KeyError):
        return None
    import lint
    secs = lint.RUNTIME_SECONDS.search(md)
    if not secs:
        return None
    solves = lint.RUNTIME_SOLVES.search(md)
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
    import lint
    _, declared = lint.limits_of(notebook.root, entry_path)
    if declared == granted:
        return None
    return (f"ENTRY_CEILING is {declared}, but {granted:.0f} s was granted at "
            f"the prompt. The budget is the user's to set, not yours: write "
            f"ENTRY_CEILING = {granted:.1f} in the entry's first cell. If the "
            f"work genuinely needs more, ask for it with `ask_specified` -- "
            f"that stops and asks a person, and the entry records the answer.")


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
    """
    if not _touched(notebook, chapter, "_model.py", "_analysis.py"):
        return
    shutil.rmtree(notebook.freeze / chapter / "index", ignore_errors=True)


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
    out = verifiers.render(
        notebook, "index.qmd",
        why="the front page counts entries, and one was just added")
    if "FAILED" in str(out):
        tell("  front     the lineage diagram did NOT rebuild — the front page "
             "is a tick behind.")
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
    f = notebook.freeze / chapter / stem / "execute-results" / "html.json"
    try:
        md = json.loads(f.read_text())["result"]["markdown"]
    except (OSError, ValueError, KeyError):
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
    for name in ("_analysis.py", "_model.py", "index.qmd", "_model.qmd"):
        f = notebook.chapters_dir / chapter / name
        if f.exists():
            changed = subprocess.run(
                ["git", "status", "--porcelain", "--", rel(f)],
                cwd=repo, capture_output=True, text=True).stdout.strip()
            if changed:
                paths.append(rel(f))

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


def _seal(notebook, sha, stem):
    """Record on the proposal that it has been spent, and on what."""
    try:
        raw = json.loads(notebook.proposal_path.read_text())
        raw["committed"] = {"sha": sha, "entry": stem,
                            "at": datetime.datetime.now().isoformat(timespec="seconds")}
        notebook.proposal_path.write_text(json.dumps(raw, indent=2))
    except (OSError, ValueError):
        # A proposal that cannot be sealed is not worth failing a commit that
        # has already happened. The worst case is the duplicate this prevents,
        # which is visible and revertible; losing the commit is neither.
        pass


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
        if (state and runstate.alive(state) is True
                and state.get("pid") != os.getpid()):
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


def main(notebook_path, verbose=True, allow_refactor=False,
         accept_refactor=False, header=True, run_id=None,
         quiet=False, answers=None):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            tell(f"  {b}")
        return 1

    notebook, refuse = _resolve(notebook_path, run_id)
    if refuse:
        for line in refuse:
            tell(line)
        return 2
    runstate.write(notebook, phase="write")
    # Always through the mailbox, exactly as `ask` is: one conversation
    # mechanism, and a question that outlives the terminal it was asked from.
    from ..mailbox import Mailbox
    from ..tools.interact import use_mailbox
    use_mailbox(Mailbox(notebook, answers=answers))
    # Only when this process is not ALREADY detached. `ask` calls straight
    # into here after forking itself, and a second fork would change the pid
    # mid-question for nothing. A bare `nb resume` reaches this with
    # `detached()` false and forks properly.
    from ..log import detached
    if not detached():
        if quiet:
            tell(f"  run       {notebook.run_id}")
            tell(f"  detail    uv run --group nb python -m nb watch "
                 f"{notebook.root.name} {notebook.run_id}")
        from ..detach import detach_process
        board = None
        if not quiet:
            from .board import follow
            board = lambda: follow(notebook, only=notebook.run_id)
        detach_process(notebook, parent=board)
    detach_output()
    # Before open_log, deliberately: there is no run to log against, and the
    # log's separator wants a title that only the proposal can supply.
    if not notebook.proposal_path.exists():
        tell(f"  no proposal at {notebook.proposal_path}. Run `nb ask` first.")
        return 1
    raw = json.loads(notebook.proposal_path.read_text())
    if raw.get("committed"):
        done = raw["committed"]
        tell(f"  {notebook.run_id} is already committed as {done['sha']} "
             f"({done.get('at', '')}).")
        tell("  Resuming would write a second copy of the same entry under "
             "today's date.")
        tell(f"  To ask something else:  nb ask {notebook.root.name} "
             f'"<question>"')
        tell(f"  To undo it:             git revert {done['sha']}")
        return 2
    # What `ask` had left of the pool when it stopped. Read out BEFORE
    # validation so they never become Proposal fields, and so never appear in
    # the `propose` tool schema as something the model is invited to fill in.
    # `raw` keeps them, because it is what gets written back on a resume.
    pool = raw.get("_pool_left", PROBE_POOL)
    ceiling = raw.get("_render_ceiling")
    pool_total = raw.get("_pool_total")
    # Assumptions the user corrected at the gate. The proposal's `findings` were
    # computed under the OLD values, so the model has to be told which numbers
    # moved -- the entry recomputes at render time, which is why a corrected
    # value needs no fresh probe, only this line.
    corrections = raw.get("_corrections") or []
    # What a NEW chapter carries forward, as the user reviewed it at the gate.
    # `_inherited` survived; `_struck` is what they said this fork BREAKS --
    # which is the only part no computation could have worked out, and the
    # reason the review is a question rather than a lookup. Both were persisted
    # and read by nothing, so striking an item moved a log line and changed
    # nothing about the chapter that got written.
    inherited_kept = raw.get("_inherited") or []
    inherited_struck = raw.get("_struck") or []
    proposal = Proposal.model_validate(
        {k: v for k, v in raw.items() if not k.startswith("_")})
    open_log(notebook, "write", proposal.title)

    if header:
        # ONE line, and only the one a reader can act on. The notebook name is
        # what they just typed, and the entry title is the first line of the
        # finished prose printed at the end -- both were saying it twice.
        tell(f"  detail    uv run --group nb python -m nb watch {notebook.root.name}")
    say(f"  notebook  {notebook.root.name}")
    say(f"  entry     {proposal.title}")

    chapter_msg = None
    # RESUMED, not created again. A run that scaffolded a chapter and then died
    # -- at the render, say -- leaves a chapter that is no longer claimable,
    # because its index is filled in. Re-running `nb write` then allocated the
    # NEXT number and wrote a duplicate beside it. The resolved name is written
    # back to the proposal below, so on the second pass this is simply true.
    already = (notebook.chapters_dir / proposal.chapter).is_dir()
    if already:
        say(f"  chapter   resuming into existing chapters/{proposal.chapter}/")
    # Either route can be the first entry in a scaffold chapter: `propose`
    # refuses to hand one over without a chapter_title, so by here we have a
    # name for it and the claim is the same operation as creating one.
    elif proposal.route == "new_chapter" or (
            proposal.chapter == notebook.claimable_stub()):
        # chapter_title, not proposal.title: the chapter is named for what it
        # holds ("Flight path"), not for whichever question happened to create it.
        # The returned name is authoritative: create_chapter owns the number, and
        # may have claimed an empty scaffold chapter instead of adding a sibling.
        proposal.chapter, chapter_msg = create_chapter(
            notebook, proposal.chapter,
            proposal.chapter_title or proposal.title, proposal.chapter_defines,
            fork_from=proposal.forked_from)
        tell(f"  chapter   {chapter_msg.splitlines()[0]}")
        if chapter_msg.startswith("rejected"):
            return 1
        # Record the NUMBER create_chapter allocated, immediately. Everything
        # after this can fail, and the proposal on disk is what a resume reads.
        raw["chapter"] = proposal.chapter
        notebook.proposal_path.write_text(json.dumps(raw, indent=2))

    # ONE WRITER PER CHAPTER, claimed as soon as the name is settled and held
    # until this process exits -- which is why there is no `with` here: the
    # claim has to outlive the try/finally below, because the commit happens
    # after it. See `locks.claim_chapter` for the run this is named after.
    #
    # Refused rather than queued, and refused HERE, before a turn is spent: the
    # proposal is sealed on disk, so the answer is to resume when the other run
    # is done, and a run that waited half an hour for a lock would look exactly
    # like the wedge the stuck detector exists to catch.
    from ..locks import claim_chapter
    holder = claim_chapter(notebook, proposal.chapter)
    if holder:
        tell(f"\n  {'─' * 70}\n  CHAPTER IS BEING WRITTEN — nothing started\n"
             f"  {'─' * 70}\n"
             f"  chapter   {proposal.chapter}\n"
             f"  held by   pid {holder}\n\n"
             f"  Two agents in one chapter edit the same _analysis.py and the "
             f"refactor gate\n  then blames whichever asks first. The proposal "
             f"is on disk; when that run ends:\n"
             f"    uv run --group nb python -m nb resume {notebook.root.name} "
             f"{notebook.run_id}\n")
        # Its own row, built here because the phase's `run_metrics` does not
        # exist yet -- the claim deliberately comes before `_stem`, which
        # allocates this entry's number by counting the chapter's files and
        # would otherwise count them while another run was adding one.
        refused = metrics.Run(notebook, "write", proposal.title)
        refused.set(chapter=proposal.chapter)
        refused.close("chapter_locked")
        return 2

    today = datetime.date.today().isoformat()
    stem = _stem(notebook, proposal.chapter, proposal.title, today)
    # THE SEAL IS NOT THE ONLY EVIDENCE. `_seal` swallows every error by design
    # ("a proposal that cannot be sealed is not worth failing a commit that has
    # already happened"), so an unsealed proposal is not proof the entry was
    # never written -- and one run in the record committed with its proposal
    # unsealed, leaving it armed to write a second copy under a later date.
    # `_stem` reuses a same-day file, which covers a resume on the same day and
    # nothing else. This covers the rest: the chapter already holds this
    # question under another date.
    # [14:] is the SLUG: `YYYY-MM-DD-NN-slug` is 10 date characters, a dash, the
    # two-digit within-day counter and a dash. `_stem` indexes it the same way,
    # and comparing from [11:] instead would carry that counter into the test --
    # so a duplicate that happened to be the second entry of its day would not
    # match the first entry of another.
    twin = next((e for e in notebook.entries(proposal.chapter)
                 if e.stem[14:] == stem[14:] and e.stem != stem), None)
    if twin:
        tell(f"\n  {'─' * 70}\n  ALREADY WRITTEN — nothing started\n"
             f"  {'─' * 70}\n"
             f"  This question is already an entry in chapters/{proposal.chapter}/:\n"
             f"    {twin.name}\n\n"
             f"  Writing would put a second copy under today's date. If the "
             f"existing entry is\n  wrong, the fix is a NEW question that "
             f"supersedes it, never a duplicate:\n"
             f"    uv run --group nb python -m nb ask {notebook.root.name} "
             f'"<question>"\n')
        dup = metrics.Run(notebook, "write", proposal.title)
        dup.set(chapter=proposal.chapter, entry_stem=twin.stem)
        dup.close("already_written")
        return 2
    # title, not question: on a split ask the model keeps the whole original
    # in `question` and puts this entry's own question in `title`, so a row
    # keyed on `question` would label every entry of a multi-part ask the same.
    run_metrics = metrics.Run(notebook, "write", proposal.title)
    run_metrics.set(chapter=proposal.chapter, entry_stem=stem)
    session = Session(notebook, proposal.question, proposal.chapter,
                      metrics=run_metrics, probe_pool=pool)
    session.render_ceiling = ceiling
    # Accepting implies allowing: you cannot accept a diff you were never
    # permitted to produce.
    allow_refactor = allow_refactor or accept_refactor
    session.allow_refactor = allow_refactor
    accepted = []
    # Snapshot the shared modules BEFORE the loop. Adding an `_analysis.py`
    # helper is safe -- rule 2 promotion leaves siblings untouched -- but
    # changing the body of one a sibling already calls is a refactor, and the
    # difference is only visible by comparing.
    _chapter_dir = notebook.chapters_dir / proposal.chapter
    _before = {n: guards.bodies(_chapter_dir / n)
               for n in ("_model.py", "_analysis.py")}
    # SIBLINGS, which this entry is not one of. On a fresh run the entry does
    # not exist yet and the count is right either way; on a RESUME it is already
    # on disk from the failed attempt, and counting it meant a run that fixed
    # its own _analysis.py was told it had moved a sibling's answers -- then
    # gated on a baseline that cannot exist, because the page is not in HEAD.
    _siblings = len([e for e in notebook.entries(proposal.chapter)
                     if e.stem != stem])

    fs, handlers, make_config = setup(session, phase="write")
    try:
        if allow_refactor:
            tell("  refactor  allowed — _model.py is writable, and the chapter "
                  "will be re-proved before commit")
        import lint as _lint
        _default_solve, _default_ceiling = _lint._defaults(notebook.root)
        brief = BRIEF.format(
            proposal=json.dumps(proposal.model_dump(), indent=2),
            chapter=proposal.chapter, stem=stem, today=today,
            ceiling=f"{(ceiling if ceiling is not None else _default_ceiling or 200.0):.1f}",
            solve=f"{(_default_solve or 60.0):.1f}",
            # What the PROBE cost, for the footer. The page cannot derive these
            # -- they belong to the `nb ask` run, not to the render -- so they
            # are declared as literals and frozen with the entry.
            pool=f"{(pool_total or pool or 0.0):.1f}",
            spent=f"{max(0.0, (pool_total or pool or 0.0) - (pool or 0.0)):.1f}")
        contents = [{"role": "user", "parts": [{"text": brief}]}]
        # ITS OWN TURN, not folded into the brief: it is the user speaking, and
        # it contradicts something the brief quotes as fact. Buried inside the
        # proposal dump it reads as one more field.
        if corrections:
            contents.append({"role": "user", "parts": [{"text":
                "The user CORRECTED these assumptions at the gate, AFTER the "
                "probe ran:\n\n"
                + "\n".join(f"  {c['name']}: {c['was']} -> {c['now']}"
                             for c in corrections)
                + "\n\nUse the corrected values. The proposal's `findings` and "
                  "`working_code` above were computed under the old ones, so "
                  "treat any number in them that depends on these as stale: the "
                  "entry recomputes at render time, which is what makes the "
                  "corrected value safe to use without probing again. Record "
                  "each of these in the entry's `## Specified` callout -- the "
                  "user answered it, so they own it."}]})
        # The scaffolder's own message -- which is the only place that says where
        # the vehicle goes. It used to be printed to the terminal and nowhere
        # else, so the model never saw it and wrote the vehicle into the entry.
        if chapter_msg:
            contents.append({"role": "user", "parts": [{"text": chapter_msg}]})
        # The inheritance review, for the index this run is about to fill in.
        if inherited_kept or inherited_struck:
            lines = ["The user reviewed what this new chapter inherits, at the "
                     "gate. NEAREST ANCESTOR FIRST: where two items name the "
                     "same quantity, the one listed earlier is the one in "
                     "force, because the chapter that declared it revisited "
                     "the subject later."]
            if inherited_kept:
                lines += ["", "STILL TRUE, inherited — do NOT restate these in "
                              "this chapter's index or in entry prose. They are "
                              "already stated one level up, and repeating them "
                              "is what rule 24's `chapter_defines` and the "
                              "Specified/Assumed callouts exist to prevent:"]
                lines += [f"  [{i['kind']}] {i['item']}   (from {i['from']})"
                          for i in inherited_kept]
            if inherited_struck:
                lines += ["", "STRUCK — the user says this fork BREAKS these, so "
                              "they do NOT carry forward. Where this chapter "
                              "needs its own value for one of them, that value "
                              "is NEW and belongs in this chapter's index, "
                              "stated without claiming anybody was asked unless "
                              "they were:"]
                lines += [f"  [{i['kind']}] {i['item']}   (was from {i['from']})"
                          for i in inherited_struck]
            contents.append({"role": "user",
                             "parts": [{"text": "\n".join(lines)}]})

        def on_turn(n, resp, turn):
            run_metrics.turn(resp)
            if verbose:
                say()          # one blank line per turn, so a turn and its
                               # reasoning read as one block
                calls = spoken_calls(turn)
                say(report(resp, f"turn {n + 1}") +
                    (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))
            runstate.write(notebook, turn=n + 1, chapter=proposal.chapter)

        first_pass = None

        def loop_once():
            run(contents, make_config(), handlers,
                transcript=notebook.transcript_path, max_turns=MAX_TURNS,
                on_turn=on_turn,
                on_stuck=lambda found: ask_stuck(found, "write"),
                should_stop=lambda: runstate.stop_requested(notebook))

        # --- lint, which is mandatory whatever the loop believes ------------
        # ASKED BEFORE THE LOOP, not after. A resumed run often has nothing for
        # the model to do -- `--accept-refactor` re-enters with the entry
        # already on disk, already clean and already verified -- and the loop
        # ran anyway, costing 16 turns to re-read _model.py, _analysis.py and
        # index.qmd and arrive back where it started. Measured on the
        # launch-speed entry. Everything downstream still gates the entry, and
        # a build failure re-enters the loop exactly as before.
        entry_path = notebook.chapters_dir / proposal.chapter / f"{stem}.qmd"
        clean, problems = verifiers.is_clean(notebook, proposal.chapter)
        if entry_path.exists() and clean:
            first_pass = 0
            run_metrics.set(first_pass_violations=0)
            say("  lint      clean before the loop — the entry is already "
                "written, so nothing was asked of the model")
        else:
            for attempt in range(MAX_LINT_ATTEMPTS):
                loop_once()
                clean, problems = verifiers.is_clean(notebook, proposal.chapter)
                if first_pass is None:
                    # The eval metric: violations before any correction round.
                    first_pass = len(problems)
                    run_metrics.set(first_pass_violations=first_pass)
                # NOT `report` -- that name is imported from .common and read
                # by on_turn, which closes over this scope; binding it here
                # made every turn line raise NameError.
                (say if clean else tell)(
                    f"  lint      "
                    f"{'clean' if clean else f'{len(problems)} blocking'}"
                    f" (attempt {attempt + 1})")
                if clean:
                    break
                contents.append({"role": "user", "parts": [{"text":
                    "Lint is not clean. Fix every one of these, then stop:\n\n"
                    + "\n".join(f"  {p}" for p in problems)}]})
            else:
                tell(f"  lint      still failing after {MAX_LINT_ATTEMPTS} "
                     f"attempts. Nothing committed; the entry is on disk to "
                     f"fix by hand.")
                run_metrics.close("lint_failed")
                return 1

        # --- the granted ceiling, BEFORE anything is paid for ---------------
        # Source only, so it costs nothing here and everything at the commit.
        note = _ceiling_problem(notebook, entry_path, ceiling)
        if note:
            tell(f"  ceiling   {note.splitlines()[0]} — handing it back")
            contents.append({"role": "user", "parts": [{"text":
                note + "\n\nFix that and stop."}]})
            loop_once()
            clean, problems = verifiers.is_clean(notebook, proposal.chapter)
            if not clean:
                tell(f"  lint      {len(problems)} blocking after the ceiling "
                     f"fix; stopping. The entry is on disk.")
                run_metrics.close("lint_failed")
                return 1

        # --- the entry must BUILD before it is committed --------------------
        _refresh_index_freeze(notebook, proposal.chapter)
        # This was the render half of the verify block. Verify is gone -- 32
        # write runs, zero findings -- but this is not: lint has passed by here,
        # and nothing else would notice a page that does not execute. It was
        # removed on no evidence the first time it was written out of the loop,
        # which is why it is extracted and proved before the model call it sat
        # next to was deleted.
        renders = 0
        while True:
            note = verifiers.build_entry(
                notebook, proposal.chapter, stem, entry_path, session=session)
            if note is None:
                break
            # A page that does not BUILD is a code error with a traceback
            # naming the line, which the model fixes in a turn. A missing
            # freeze after a successful render is nothing it can act on, and
            # ends the run.
            buildable = note.startswith(verifiers.BUILD_FAILED)
            if not buildable or renders >= MAX_RENDER_FIXES:
                tell(f"  build     could not run — {note}")
                run_metrics.close("build_failed")
                return 1
            renders += 1
            run_metrics.set(render_fixes=renders)
            tell(f"  render    FAILED — handing the error back "
                  f"(attempt {renders} of {MAX_RENDER_FIXES})")
            say(note)
            contents.append({"role": "user", "parts": [{"text":
                "The page does not build. Quarto reported:\n\n" + note
                + "\n\nFix the cause and stop. The chapter's _model.py and "
                  "_analysis.py are exec'd into the page namespace by "
                  "_model.qmd, so their names are already in scope — "
                  "importing them is what raises ModuleNotFoundError."}]})
            loop_once()
            clean, problems = verifiers.is_clean(notebook, proposal.chapter)
            if not clean:
                tell(f"  lint      {len(problems)} blocking after the render "
                      f"fix; stopping. The entry is on disk.")
                run_metrics.close("lint_failed")
                return 1

        # What the RENDER cost, from the page it just produced. `ask` records
        # its probes, but the entry's own solves -- the expensive ones, and the
        # ones rule 17 judges -- were unrecorded, so every write row read 0.0
        # even after the counter started working.
        _cost = _render_cost(notebook, proposal.chapter, stem)
        if _cost:
            run_metrics.set(solves=_cost[0], solve_seconds=_cost[1])


        # --- the chapter's shared machinery moved: prove it moved nothing ---
        # Adding an `_analysis.py` helper is additive and safe; changing the
        # body of one a sibling already calls is a refactor, and Quarto's freeze
        # tracks the page rather than its includes, so nothing else would ever
        # notice. `check` deletes the freeze, re-renders and diffs -- expensive,
        # which is why it runs only when a body actually moved and the chapter
        # actually has siblings to break.
        moved, evidence = [], []
        if _siblings:
            for name in ("_model.py", "_analysis.py"):
                after = guards.bodies(_chapter_dir / name)
                for fn in guards.changed_bodies(_before[name], after):
                    moved.append(f"{name}:{fn}")
                    evidence.append(_why_and_diff(
                        name, fn, _before[name][fn], after[fn],
                        session.refactor_notes.get(fn)))
        if moved:
            tell(f"  check     {', '.join(moved)} changed — re-proving "
                  f"{_siblings} sibling entr"
                  f"{'y' if _siblings == 1 else 'ies'}")
            out = verifiers.check(notebook, proposal.chapter)
            # `check` reports its own exit code in the first line; non-zero
            # means the diff was not empty, which IS the finding.
            if not str(out).startswith("check exit=0"):
                # The diff prints EITHER WAY. Accepting is meant to be loud:
                # `refactoring.md` holds that a refactor which moves anything
                # wants superseding rather than silent updating, and accepting
                # overrides that judgement, so the evidence goes on the record
                # rather than being swallowed by a flag.
                tell(f"\n  {'─' * 70}\n  REFACTOR CHANGED THE ANSWERS"
                     f"{' — ACCEPTED' if accept_refactor else ' — not committed'}"
                     f"\n  {'─' * 70}")
                # WHAT changed, before what it did to the answers. The gate used
                # to print only the function's name, so judging it meant leaving
                # the terminal and running `git diff` -- on the one decision the
                # system explicitly hands to a human.
                for block in evidence:
                    tell(block)
                tell(f"{out}\n")
                if not accept_refactor:
                    tell(f"  The entry and the changed machinery are on disk. "
                         f"Either the change is wrong, or the entries it moved\n"
                         f"  need superseding rather than silently updating. If "
                         f"the diff is presentation only and you have read it:\n"
                         f"    uv run --group nb python -m nb resume "
                         f"{notebook.root.name} --accept-refactor\n")
                    run_metrics.close("refactor_moved_answers")
                    return 1
                accepted = moved
            else:
                tell("  check     clean — the refactor moved nothing")
    except Stopped as e:
        # Asked to stop. The entry stays exactly where it is: a stop is "spend
        # nothing more on this", not "undo it" -- deciding what to keep is the
        # caller's, and `nb clean` will not touch a run whose chapter is dirty.
        run_metrics.close("stopped")
        tell(f"\n  {e}. The entry is on disk at\n  {entry_path}")
        return 1
    except RuntimeError as e:
        # Out of turns. `ask` has caught this since it was written; `write` did
        # not, so the loop's RuntimeError left the phase with no metrics row, no
        # message, and a `run.json` whose last write said turn 40 -- which the
        # board rendered as `done`. Measured on a run that spent thirty turns
        # chasing a tool it did not have.
        #
        # Unlike `ask`, the entry IS on disk here, and it is often nearly
        # finished. So this says where it is rather than "nothing was written".
        run_metrics.close("max_turns")
        tell(f"\n  {'─' * 70}\n  OUT OF TURNS — nothing committed\n"
             f"  {'─' * 70}\n"
             f"  {e}\n"
             f"  entry     {entry_path}\n\n"
             f"  It is on disk and unlinted. To pick it up:\n"
             f"    uv run --group nb python -m nb resume {notebook.root.name}\n")
        return 1
    except SystemExit:
        # A prompt that hit EOF, or a mailbox question that went an hour
        # unanswered. `ask` has recorded this since it was written; `write` did
        # not, so a detached run nobody answered exited with no metrics row and
        # no `outcome` -- which the board draws as `died`, the one state it
        # exists to keep separate from an ending the system chose. The entry is
        # usually on disk by here, so say where, as OUT OF TURNS does.
        run_metrics.close("no_answer")
        tell(f"\n  {'─' * 70}\n  NO ANSWER — nothing committed\n"
             f"  {'─' * 70}\n"
             f"  entry     {entry_path}\n\n"
             f"  Answer the question in the run directory, then:\n"
             f"    uv run --group nb python -m nb resume {notebook.root.name} "
             f"{notebook.run_id}\n")
        raise
    except Refactor as r:
        # The agent tried to change the vehicle, was refused, and said why.
        # Ending here is the point: re-proving a chapter is minutes of solves,
        # and whether to spend them is not the agent's call.
        run_metrics.close("needs_refactor")
        tell(f"\n  {'─' * 70}\n  REFACTOR NEEDED — nothing committed\n"
             f"  {'─' * 70}\n"
             f"  chapter   {r.chapter}  ({r.entries} entr"
             f"{'y' if r.entries == 1 else 'ies'} would be re-proved)\n"
             f"  why       {r.why}\n\n  If that is right:\n"
             f"    uv run --group nb python -m nb resume "
             f"{notebook.root.name} --allow-refactor\n")
        return 2
    finally:
        fs.stop()

    # --- commit ------------------------------------------------------------
    # An accepted refactor re-rendered every page reaching the changed function,
    # so the whole chapter's freeze goes in -- siblings and the chapter index --
    # or the committed freeze stops matching the committed code.
    title = proposal.title
    # Rule 26 lets the title be a rephrasing, so the words actually used to ask
    # have to survive somewhere that cannot be edited later. `proposal.json` is
    # overwritten by the next run; the commit is not.
    if proposal.question and proposal.question.strip() != title.strip():
        title += f"\n\nAsked: {proposal.question.strip()}"
    # The render ceiling was GRANTED, not negotiated. Refuse to commit an entry
    # that awarded itself a different one -- otherwise the number typed at the
    # prompt is decoration, and the run's real spend is whatever the agent felt
    # like.
    #
    # THE GUARANTEE, not the gate. The gate is beside the lint loop above,
    # where the entry has not yet been rendered and the model can still fix it;
    # reaching here means it was handed back and came out wrong anyway.
    note = _ceiling_problem(notebook, entry_path, ceiling)
    if note:
        tell(f"  Not committed: {note}")
        run_metrics.close("ceiling_changed")
        return 1

    extra = ()
    # WHENEVER THE GATE RAN, not only when its finding was accepted. `check`
    # re-renders every sibling that reaches the changed function, which
    # rewrites their freezes whatever the verdict -- so a refactor that came
    # back "moved nothing" left them rebuilt and UNCOMMITTED beside a
    # committed `_analysis.py`. The comment above states the invariant this
    # broke: the committed freeze stops matching the committed code. Nothing
    # wrong ever shipped, because the gate had just proved the values
    # identical, but the repo stopped carrying that proof -- and the orphans
    # sat in the working tree waiting to be swept into an unrelated commit,
    # which has happened here once already.
    if moved and _siblings:
        extra = (notebook.freeze / proposal.chapter,)
    if accepted:
        title += ("\n\nAccepted refactor: " + ", ".join(accepted) +
                  f". {_siblings} sibling entr"
                  f"{'y' if _siblings == 1 else 'ies'} re-proved and re-frozen.")
    _refresh_root_index(notebook)
    sha, detail = _commit(notebook, proposal.chapter, stem, entry_path,
                          title, extra_paths=extra)
    if sha is None:
        tell(f"  commit    FAILED — {detail}")
        run_metrics.close("commit_failed")
        return 1
    # Held back until AFTER the entry prints. On its own above the block it
    # read as a stray line with nothing to attach to; below it, beside the page
    # path, it is the provenance of the thing just read.
    # SEAL THE PROPOSAL. It stays on disk -- it is the record of what was
    # approved, and a coordinator reads it -- but it is now spent, and
    # `nb resume` refuses a spent one. Unsealed, resuming a finished run
    # re-executed the whole entry and wrote a SECOND copy of it under today's
    # date: a duplicate that lints, renders and would have committed. Every
    # other ending leaves the proposal unsealed, which is what makes them
    # resumable.
    _seal(notebook, sha, stem)
    n_paths = len(detail.split(", "))
    committed = f"  commit    {sha} · {n_paths} file{'s' if n_paths != 1 else ''}"
    say(f"  commit    {sha}  ({detail})")
    say(f"  first-pass violations: {first_pass}")
    if session.probe_pool:
        # The QUESTION's total against the grant, not this phase's slice against
        # what was left of it: "4 s of 272 s" made the run look like it had been
        # given a budget nobody chose.
        total = pool_total or session.probe_pool
        spent = total - (session.probe_left or 0.0)
        say(f"  budget    {spent:.0f} s of {total:.0f} s probe pool used")
    run_metrics.close("committed_refactor" if accepted else "committed")

    # The entry itself, with real numbers. Conversation, not telemetry: it is
    # the thing to read, and with no gate before it this is where a reader --
    # human or coordinating agent -- first sees what was actually claimed.
    prose = rendered_prose(notebook, proposal.chapter, stem)
    if prose:
        tell(f"\n{'─' * 72}\n{prose}\n{'─' * 72}")
    tell(committed)

    # After the commit, never before: a project render touches every page in the
    # notebook, and an unrelated broken one must not be able to block an entry
    # that has already passed lint and built on its own terms.
    site(notebook, page=notebook.root / "_site" / "chapters"
                        / proposal.chapter / f"{stem}.html")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

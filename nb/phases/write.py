"""
Everything that happens to an entry after the model stops typing.

NOT A PHASE ANY MORE. This was `nb write`, the second half of a two-process run
reading `proposal.json`; the run does not stop in the middle now, so the loop
and the gates live together in `phases/run.py` and what is left here is the
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
from .. import runstate
from ..log import tell

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
                    "_inputs.yml", "_fork.yml"):
        return
    out = verifiers.render(
        notebook, str((notebook.chapters_dir / chapter / "index.qmd")
                      .relative_to(notebook.root)),
        why="the chapter index renders files this run changed")
    if "FAILED" in str(out):
        tell(f"  index     chapters/{chapter}/index.qmd did NOT rebuild — its "
             f"freeze is a version behind.")


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
    # `_inputs.yml` and `_fork.yml` joined the list when the chapter index
    # stopped carrying its callouts and started RENDERING them. Without them
    # the first X-Wing commit carried the entry, `_model.py` and the freezes
    # while the SOURCE of the chapter's Specified and Assumed items stayed
    # uncommitted in the working tree -- the exact invariant the note above
    # states: the committed freeze stops matching the committed code.
    for name in ("_analysis.py", "_model.py", "index.qmd", "_model.qmd",
                 "_inputs.yml", "_fork.yml"):
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

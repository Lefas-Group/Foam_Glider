"""
`nb ask` -- one question, one conversation, from probe to commit.

There used to be two phases with a gate between them, and `proposal.json` in
the middle. The gate is gone. It was not mainly a document: it was the single
point where a run committed to a chapter, a title and a set of inputs, and it
enforced four refusals there. Those refusals still exist -- they moved to
`fork_chapter` and `open_entry`, where each becomes true at the moment the
model decides it rather than as a field filled in afterwards.

WHAT THE STOP COST, measured across the ten runs still on disk: seven of ten
went ask -> write in ONE process, milliseconds apart, writing a file to disk
and reading it straight back. The three that crossed a process boundary crossed
it because the system deliberately stopped -- a new chapter, a refactor --
never because anything crashed. On the X-Wing run that stop was five minutes of
human round-trip on a run whose compute was sixteen, plus four failed pastes of
the resume command.

WHAT IT COSTS TO MERGE, stated plainly: a conversation re-sends its whole
history every turn, so prompt tokens grow with the square of the turn count
rather than the sum of two halves. One 25-turn conversation is plausibly more
expensive than a 10-turn and a 15-turn one -- the README's "$0.404 split against
$0.429 merged" measured roughly that. Tool surface and latency down,
conversation cost up; `nb eval` is where it shows, and much beyond ~25% is a
bug rather than the trade.

`nb resume` survives as the crash path and the two approvals, not as the
routine one. It re-enters with the entry on disk, and `is_clean`
short-circuits the loop exactly as `--accept-refactor` already did.
"""

import datetime
import sys

from ..config import MAX_LINT_ATTEMPTS, MAX_RENDER_FIXES, MAX_TURNS, PROBE_POOL
from ..agent.loop import Stopped, run as drive
from ..agent.session import Session
from ..preflight import check as preflight
from ..tools import guards, kernel, verifiers
from ..tools.interact import ask_pool, ask_render_ceiling, ask_stuck
from ..agent import briefs
from ..process import desktop, metrics, runstate, serve
from .view import site
from ..agent.setup import setup, report, spoken_calls
from ..build.publish import (_ceiling_problem, _commit, _refresh_active,
                    targets_unreported,
                    _refresh_index_freeze,
                    _refresh_root_index, _render_cost, _resolve, _why_and_diff,
                    answer_line, rendered_prose)
from ..process.log import detach_output, detached, open_log, say, tell


# The rendered entry, capped, for `run.json`. Measured at 616 characters on a
# real entry; the cap is for the pathological one, not the normal one. `run.json`
# is polled twice a second by the board, so it stays a document you can read in
# one go rather than a place to put everything.
PROSE_CAP = 4000

# WHERE THE DETAIL IS, said once rather than guessed at. A reader of `run.json`
# should not have to sift the model's reasoning to find out what happened --
# `answer`, `prose` and `findings` are there so it never has to. This says where
# to look on the occasions it wants to.
DETAIL = {
    "log": "status.log — every turn, stamped. The model's reasoning is in the "
           "lines beginning `│`; nothing else needs reading.",
    "turns": "transcript.jsonl — one line per model turn (role: model) and one "
             "per batch of tool results (role: tool), in order. `thought` "
             "parts are the reasoning; skip them unless you want it.",
    "probe": "kernel.log — the probe kernel's own stdout, which is startup "
             "chatter and, if one happened, a crash. Probe OUTPUT is in "
             "transcript.jsonl with the turn that asked for it.",
}


def _start(notebook, quiet, answers, watch=True):
    """Mailbox, fork, log redirection -- identical for a fresh run and a resume."""
    from ..process.mailbox import Mailbox
    from ..tools.interact import use_mailbox
    use_mailbox(Mailbox(notebook, answers=answers))
    # Only when this process is not ALREADY detached. A bare `nb resume`
    # reaches this with `detached()` false and forks properly; a run that
    # forked itself must not fork again mid-question.
    if not detached():
        if quiet:
            # Nothing will be drawn over, so say where the run went. Printed
            # BEFORE detaching, because every later `tell` goes only to the log.
            tell(f"  run       {notebook.run_id}")
            # A WINDOW PER RUN, opened from the PARENT. This is the last moment
            # a process here still has the terminal -- everything after the fork
            # below is a daemon, and a daemon spawning a terminal would make
            # that window's parent a process nobody can see.
            #
            # `--all` so the window carries the run from its first line rather
            # than from whenever it happened to open, and `--until-done` so the
            # watcher stops: one of these per `nb ask` would otherwise pile up
            # forever, since `follow()` is a `while True`.
            #
            # `--close-window` IS THE SEPARATE HALF, and only this caller sends
            # it. Stopping the watcher is enough everywhere the terminal owns
            # the command it was given -- tmux, `gnome-terminal -- …`, `xterm
            # -e …` all exit with it -- but Terminal.app keeps the window, so
            # on macOS the watcher has to close it by hand. Someone who types
            # `nb watch --until-done` in a terminal of their own gets the stop
            # without having their window pulled out from under them.
            if watch:
                desktop.terminal(
                    [sys.executable, "-m", "nb", "watch", notebook.root.name,
                     notebook.run_id, "--all", "--until-done",
                     "--close-window"],
                    cwd=notebook.repo, what="this run")
            tell("  detail:")
            tell(f"    uv run --group nb python -m nb watch "
                 f"{notebook.root.name} {notebook.run_id}")
        # AND THEN LEAVE THE SESSION. Before `setup()`, which starts the MCP
        # filesystem subprocess, and before the metrics connection: `fork` past
        # either is how a daemon inherits something it cannot use.
        #
        # The board runs in the ORIGINAL process, which is the one still
        # holding the terminal. To whoever typed the command nothing looks
        # different -- a question appears, they answer it -- but there is one
        # mechanism underneath, and closing the window no longer kills the run.
        from ..process.detach import detach_process
        board = None
        if not quiet:
            from .board import follow
            board = lambda: follow(notebook, only=notebook.run_id)
        detach_process(notebook, parent=board)
    # IN THE CHILD, and before anything else can happen: `detach_process`
    # never returns in the parents. Everything that asks whether this run is
    # still going asks whether this lock is still held, so it has to be taken
    # before the run can be asked about -- which means before its first
    # question, its first turn and its first `run.json` the board will read.
    # THE LOCK BEFORE THE STATE, and that order is load-bearing. `alive()`
    # reads "no lock file" as dead, which is right for a run that never started
    # and wrong for one that is starting: the board runs in the PARENT and
    # begins polling the instant the fork returns, so a `run.json` written
    # before the child takes its lock is a run the board reads as dead,
    # announces as "died without a word", and leaves. Observed on the first
    # live run after the board learned to announce endings.
    #
    # Writing the state second closes it with no timing guess: until the lock
    # exists there is no `run.json` either, `_runs` skips the directory, and
    # the board's "all my runs have ended" test requires a non-empty list.
    runstate.hold(notebook)
    runstate.write(notebook, detail=DETAIL)
    detach_output()


def main(notebook_path, question, verbose=True,
         pool=None, ceiling=None, run_id=None, quiet=False,
         answers=None, chapter=None, watch=True, kind="run"):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            tell(f"  {b}")
        return 1

    from ..config import Notebook, new_run_id
    notebook = Notebook(notebook_path, run_id=run_id or new_run_id())
    # THE CHAPTER IS SETTLED BEFORE THE FIRST TOKEN, which is the whole point
    # of requiring it. Everything that used to happen inside `open_chapter` on
    # turn 1 -- validating the name, claiming the lock, snapshotting the shared
    # modules -- happens here instead, where it costs nothing and cannot fail
    # halfway through a conversation. A collision now costs zero tokens rather
    # than a turn plus a 10k prefix.
    known = notebook.chapters()
    if chapter not in known:
        tell(f"  no chapter {chapter!r} in {notebook.root.name}.")
        tell(f"  It has: {', '.join(known) if known else '(none)'}")
        return 2
    _start(notebook, quiet, answers, watch)   # forks; takes the lock first
    # `watch` RIDES IN run.json rather than down four signatures. `_finish`
    # runs in the daemon and wants it too, to decide whether to open the
    # committed page; threading it through `_execute` would touch both of that
    # function's callers for a flag neither of them cares about. A `nb resume`
    # then inherits what the original `nb ask` was told, which is correct.
    runstate.write(notebook, phase="run", question=question,
                   chapter=chapter, turn=0, waiting_on=None, watch=watch)
    open_log(notebook, "run", question)
    run_metrics = metrics.Run(notebook, "run", question)

    # Asked once, here, and the number bounds the WHOLE question rather than
    # one half of it. `--pool` and `--ceiling` skip the prompt entirely: a
    # caller who already knows the numbers -- a coordinator, a script, anyone
    # re-running a question -- was being asked them twice a run for no decision.
    if pool is None:
        pool = ask_pool(PROBE_POOL)
    # Granted before anything is built, so the agent designs within it rather
    # than discovering it at render time. `shared._defaults` is the ONLY source
    # of the default, flag or no flag: a second copy of this number in
    # `config.py` disagreed with the notebook once -- 20 s against 200 s -- so
    # the flag overrides the ANSWER and never the source of the default.
    if ceiling is None:
        from ..contract import shared
        _, default_ceiling = shared._defaults(notebook.root)
        ceiling = ask_render_ceiling(
            default_ceiling or 200.0,
            "declared by this notebook's _notebook.py" if default_ceiling
            else "no notebook default; nb's fallback")

    session = Session(notebook, question, chapter=chapter,
                      metrics=run_metrics, probe_pool=pool)
    session.render_ceiling = ceiling
    # Read by the targets gate before the commit, and by nothing else.
    session.kind = kind
    run_metrics.set(chapter=chapter)

    # ONE WRITER PER CHAPTER, claimed before a single token is spent. Refused
    # rather than queued: two agents in one chapter edit the same
    # `_analysis.py` and the refactor gate then blames whichever asks first.
    from ..process.locks import claim_chapter
    holder = claim_chapter(notebook, chapter)
    if holder:
        tell(f"\n  {'─' * 70}\n  CHAPTER IS BEING WRITTEN — nothing started\n"
             f"  {'─' * 70}\n"
             f"  chapter   {chapter}\n  held by   pid {holder}\n\n"
             f"  Different chapters run side by side; they meet only at the "
             f"render, which is locked.\n  When that run ends, ask again.\n")
        run_metrics.close("chapter_locked")
        return 2
    # The baseline the refactor gate compares against, taken before the model
    # may write anything. Free -- two AST parses.
    session.before_bodies = {
        n: guards.bodies(notebook.chapters_dir / chapter / n)
        for n in ("_model.py", "_analysis.py")}
    session.siblings = len(notebook.entries(chapter))

    say(f"  notebook  {notebook.root.name}")
    say(f"  chapter   {chapter}")
    fs, handlers, make_config = setup(session)
    notebook.run.mkdir(parents=True, exist_ok=True)
    notebook.transcript_path.write_text("")

    # WHICH BRIEF OPENS THE CONVERSATION, and the only difference between
    # `nb ask` and `nb reconstruct`. Everything below -- the loop, the prompt,
    # lint, the ceiling, the commit -- is shared, which is the whole reason a
    # third mode is cheap rather than a second system.
    if kind == "reconstruct":
        text = briefs.RECONSTRUCT.format(
            chapter=chapter, question=question,
            targets=_targets_brief(notebook))
    else:
        text = briefs.BRIEF.format(
            question=question, max_turns=MAX_TURNS, chapter=chapter)
    contents = [{"role": "user", "parts": [{"text": text}]}]
    return _execute(notebook, session, contents, run_metrics, fs, handlers,
                    make_config, verbose, accept_refactor=False)


def _targets_brief(notebook):
    """
    The brief's `targets:` rows, formatted for the reconstruct brief, plus a
    warning when there are none.

    AN EMPTY `targets:` BLOCK IS VALID and is not an error. It means the run
    is gated on the eye at the prompt alone -- build it and show me -- which
    is exactly what shape-first work wants: an X-Wing, an aircraft shaped like
    a pig, anything with no published spec sheet to converge on. The same
    command covers that, geometry-only, and the full sheet, with no mode flag;
    the block is what says which.
    """
    from ..contract import shared
    rows = shared.notebook_targets(notebook.root)
    if not rows:
        return ("There are NO target rows in the brief, which is allowed: "
                "nothing is published for this aircraft, or nobody chose to "
                "pin it. Build what the brief describes and show it. The "
                "three-view at the prompt is then the only check there is, so "
                "it matters more, not less.")
    out = ["The targets, from the brief:"]
    out += [f"  - {t}" for _h, t in rows]
    out.append("")
    out.append("Each is a PUBLISHED FACT about the real aircraft. Reproduce "
               "every one inside its tolerance, or say which you could not "
               "and by how much.")
    return "\n".join(out)


def reconstruct(notebook_path, chapter=None, pool=None, ceiling=None,
                run_id=None, verbose=True, quiet=False, answers=None,
                watch=True):
    """
    Build a chapter's vehicle and prove it reproduces the brief's targets.

    THE THIRD BRIEF into `_execute`, after `ask` and `resume`, and it shares
    everything but its opening text and what it is gated on. Reconstruction is
    converge-to-tolerance where the ordinary contract is built for answering a
    question once -- rule 5 bans a `range()` loop around a solve, rule 6 caps
    prose at 100 words -- so it gets its own brief and the targets gate, and
    nothing else is duplicated.

    It produces ONE ORDINARY ENTRY in a chapter that already exists. `nb new`
    makes the chapter; this writes its first entry and leaves `_model.py` as
    the vehicle. Nothing new is created, and the entry obeys the contract
    unchanged: a question, a hero, and the two visuals rule 14 allows when one
    of them draws the aircraft.

    A BIGGER DEFAULT BUDGET than `ask`. The shape loop runs inside this run --
    reject at the prompt, rebuild, render, prompt again -- so five rejections
    is five rebuilds out of one pool. Once per chapter, so it can afford it.
    """
    question = ("Can we reconstruct this chapter's aircraft within the "
                "tolerances the brief states?")
    # A BIGGER DEFAULT POOL than `ask`, because the shape loop spends it:
    # reject at the prompt, rebuild, re-render, prompt again. Only applied
    # when the caller named nothing, so `--pool` still wins.
    return main(notebook_path, question, verbose=verbose,
                pool=pool if pool is not None else PROBE_POOL * 2,
                ceiling=ceiling, run_id=run_id, quiet=quiet,
                answers=answers, chapter=chapter, watch=watch,
                kind="reconstruct")


def _disk_state(notebook, chapter, stem):
    """
    What the chapter actually holds, for the resume brief.

    THE BRIEF USED TO ASSERT IT. "Its entry is already on disk at
    `{chapter}/{stem}.qmd` -- you wrote it in an earlier process" was true for
    the case the resume path was built for, and false for the other one: a run
    that hit the turn cap having ALLOCATED a stem and never written the file.

    Measured on `20261002-100435-b81e`. The resumed run believed the entry
    existed, read for it, got ENOENT, and spent the next nine tool calls
    orienting -- `list_directory .`, `list_directory 01-…`, `search_files *`,
    `search_files **/*` -- before tripping the NO PROGRESS detector and
    needing a human to say "write the entry". Nothing was wrong with the
    chapter. It had simply been told something untrue about it and believed it
    over what the tools kept returning.

    So: look, and say. Sizes rather than contents -- the files are readable and
    `_model.py` is quoted in the prefix already; what the run cannot infer is
    which of them exist and whether its own entry is among them.
    """
    d = notebook.chapters_dir / chapter
    entry = d / f"{stem}.qmd"
    rows = []
    if entry.exists():
        n = len(entry.read_text().splitlines())
        rows.append(f"- `{chapter}/{stem}.qmd` EXISTS, {n} lines. This is your "
                    f"entry. Read it first: it is the record of what you "
                    f"decided.")
    else:
        rows.append(f"- `{chapter}/{stem}.qmd` DOES NOT EXIST. The name is "
                    f"reserved for you and nothing has been written to it. "
                    f"Writing it is the job -- do not go looking for it.")
    for name in ("_model.py", "_analysis.py"):
        f = d / name
        try:
            body = f.read_text()
        except OSError:
            rows.append(f"- `{chapter}/{name}` is missing.")
            continue
        lines = [ln for ln in body.splitlines() if ln.strip()]
        defs = [ln.split("(")[0].removeprefix("def ").strip()
                for ln in lines if ln.startswith("def ")]
        rows.append(
            f"- `{chapter}/{name}`: {len(lines)} non-blank lines"
            + (f", defines {', '.join(f'`{n}()`' for n in defs)}" if defs
               else ", no functions defined")
            + ("." if lines else " — still the empty scaffold."))
    others = sorted(p.name for p in d.glob("20*.qmd") if p.stem != stem)
    if others:
        rows.append(f"- sibling entries already committed here: "
                    f"{', '.join(f'`{o}`' for o in others)}.")
    return "\n".join(rows)


def resume(notebook_path, run_id=None, allow_refactor=False,
           accept_refactor=False, header=True, quiet=False, answers=None):
    """
    Pick up a run that stopped with work on disk.

    WHAT IS LOST, stated rather than hidden: a resumed run has no conversation.
    It used to rebuild a brief from the proposal; it now gets the entry it
    already wrote, plus what `run.json` recorded, plus whatever the gate is
    complaining about. For the common case -- entry written, lint clean -- the
    two are identical, because the loop is skipped either way.
    """
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

    state = runstate.read(notebook)
    done = state.get("committed")
    if done:
        tell(f"  {notebook.run_id} is already committed as {done['sha']} "
             f"({done.get('at', '')}).")
        tell("  Resuming would write a second copy of the same entry under "
             "today's date.")
        tell(f"  To ask something else:  nb ask {notebook.root.name} "
             f'"<question>"')
        tell(f"  To undo it:             git revert {done['sha']}")
        return 2
    chapter, stem = state.get("chapter"), state.get("stem")
    if not (chapter and stem):
        # NOTHING TO RESUME is a real outcome, not an error. A run that never
        # reached `open_entry` has no filename, no claimed chapter and no
        # partial page -- there is nothing on disk to carry forward, and the
        # honest answer is to ask again rather than to invent a starting point.
        tell(f"  {notebook.run_id} never opened an entry, so there is nothing "
             f"on disk to resume.")
        tell(f"  Ask it again:  uv run --group nb python -m nb ask "
             f"{notebook.root.name} \"{state.get('question', '<question>')}\"")
        return 2

    _start(notebook, quiet, answers)
    # Clear the PREVIOUS ending before doing anything else. `runstate.write`
    # merges, so `outcome` survives a resume unless it is explicitly overwritten
    # -- and `nb listen` calls a run `ends` on nothing more than a truthy
    # `outcome`, gated by an `updated > since` watermark that this process bumps
    # on its very first write. The result was that every resumed run reported
    # its own PREVIOUS outcome the instant it started, while alive and working;
    # seen three times in one afternoon, each costing a manual pid check to tell
    # the replay from a real ending. `failure` and `answer` go with it: they
    # describe the attempt that just ended, not this one.
    runstate.write(notebook, phase="run", outcome=None,
                   failure=None, answer=None)
    title = state.get("title") or stem[14:].replace("-", " ")
    question = state.get("question") or title
    open_log(notebook, "resume", title)
    if header:
        tell("  detail:")
        tell(f"    uv run --group nb python -m nb watch {notebook.root.name}")
    say(f"  notebook  {notebook.root.name}")
    say(f"  entry     {title}")

    run_metrics = metrics.Run(notebook, "resume", question)
    run_metrics.set(chapter=chapter, entry_stem=stem)
    pool = state.get("pool_left")
    session = Session(notebook, question, chapter,
                      metrics=run_metrics,
                      probe_pool=pool if pool is not None else 0.0)
    session.render_ceiling = state.get("ceiling")
    session.pool_total = state.get("pool_total")
    # Accepting implies allowing: you cannot accept a diff you were never
    # permitted to produce.
    session.allow_refactor = allow_refactor or accept_refactor
    session.stem, session.entry_title = stem, title
    session.entry_path = notebook.chapters_dir / chapter / f"{stem}.qmd"
    session.before_bodies = {
        n: guards.bodies(notebook.chapters_dir / chapter / n)
        for n in ("_model.py", "_analysis.py")}
    session.siblings = len([e for e in notebook.entries(chapter)
                            if e.stem != stem])

    # ONE WRITER PER CHAPTER, re-claimed by the process taking over. Refused
    # rather than queued: the entry is on disk, so the answer is to resume when
    # the other run is done.
    from ..process.locks import claim_chapter
    holder = claim_chapter(notebook, chapter)
    if holder:
        tell(f"\n  {'─' * 70}\n  CHAPTER IS BEING WRITTEN — nothing started\n"
             f"  {'─' * 70}\n"
             f"  chapter   {chapter}\n  held by   pid {holder}\n\n"
             f"  When that run ends:\n"
             f"    uv run --group nb python -m nb resume {notebook.root.name} "
             f"{notebook.run_id}\n")
        run_metrics.close("chapter_locked")
        return 2

    fs, handlers, make_config = setup(session)
    why = ("`--allow-refactor` is set, so this chapter's `_model.py` is "
           "writable and the chapter will be re-proved before the commit."
           if session.allow_refactor else
           "Run `lint` with chapter " + chapter + " and fix what it reports.")
    contents = [{"role": "user", "parts": [{"text": briefs.RESUME.format(
        question=question, why=why,
        state=_disk_state(notebook, chapter, stem))}]}]
    return _execute(notebook, session, contents, run_metrics, fs, handlers,
                    make_config, verbose=True, accept_refactor=accept_refactor)


def _execute(notebook, session, contents, run_metrics, fs, handlers,
             make_config, verbose, accept_refactor):
    """
    The loop, then every gate, in one process.

    Lint is both a tool and a mandatory step. The tool lets the loop fix
    violations in place; the step after the loop is the guarantee, because
    without it the model can simply decline to call the tool and declare itself
    done. The same shape holds for the ceiling and for the refactor gate.
    """
    if session.allow_refactor:
        tell("  refactor  allowed — _model.py is writable, and the chapter "
             "will be re-proved before commit")

    def on_turn(n, resp, turn):
        run_metrics.turn(resp)
        if verbose:
            say()          # one blank line per turn, so a turn and its
                           # reasoning read as one block
            calls = spoken_calls(turn)
            say(report(resp, f"turn {n + 1}") +
                (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))
        runstate.write(notebook, turn=n + 1, chapter=session.chapter)

    # ONE BUDGET OF TURNS for the whole question, drawn down across probing and
    # writing alike. It used to be MAX_TURNS each side of a boundary that no
    # longer exists, which would silently double it.
    spent = [0]

    def loop_once():
        left = MAX_TURNS - spent[0]
        if left <= 0:
            raise RuntimeError(f"max turns ({MAX_TURNS}) exceeded")
        before = len(contents)
        try:
            drive(contents, make_config(), handlers,
                  transcript=notebook.transcript_path, max_turns=left,
                  on_turn=lambda n, r, t: on_turn(spent[0] + n, r, t),
                  on_stuck=lambda found: ask_stuck(found, "run"),
                  should_stop=lambda: runstate.stop_requested(notebook))
        finally:
            # Model turns only: `contents` also gains a user turn per tool
            # response and per nudge, and counting those would retire the
            # budget at roughly twice the rate.
            spent[0] += sum(1 for c in contents[before:]
                            if getattr(c, "role", None) == "model")

    def problems_now():
        """`(clean, [(rule, message)])` -- lint, plus the one thing lint cannot
        see: no entry file at all."""
        clean, problems = verifiers.is_clean(notebook, session.chapter)
        if not session.entry_path.exists():
            return False, [
                (None, f"chapters/{session.chapter}/{session.stem}.qmd does "
                       f"not exist. You opened the entry and never wrote it "
                       f"-- `write_file` it, then lint.")] + list(problems)
        return clean, problems

    def blocked(problems):
        """Record WHICH rules stopped the run, for whoever reads run.json."""
        runstate.write(notebook, findings=[
            {"rule": r, "message": m} for r, m in problems])

    first_pass = None
    try:
        # ASKED BEFORE THE LOOP, on a resume. A resumed run often has nothing
        # for the model to do -- `--accept-refactor` re-enters with the entry
        # already on disk, already clean and already verified -- and the loop
        # ran anyway, costing 16 turns to re-read _model.py, _analysis.py and
        # index.qmd and arrive back where it started. Everything downstream
        # still gates the entry, and a build failure re-enters the loop exactly
        # as before.
        clean = False
        if session.entry_path is not None and session.entry_path.exists():
            clean, problems = problems_now()
        if clean:
            first_pass = 0
            run_metrics.set(first_pass_violations=0)
            say("  lint      clean before the loop — the entry is already "
                "written, so nothing was asked of the model")
        else:
            for attempt in range(MAX_LINT_ATTEMPTS):
                loop_once()
                # THE LOOP ENDED WITHOUT AN ENTRY. `drive` returns as soon as a
                # turn calls no tool, so this is the same outcome shape the old
                # `no_proposal` had: a real ending the system chose, recorded
                # as one, rather than a crash.
                if session.entry_path is None:
                    run_metrics.set(chapter=session.chapter)
                    run_metrics.close("no_entry")
                    tell("\n  The loop ended without opening an entry. Nothing "
                         "was committed.")
                    tell(f"  chapters/{session.chapter} is otherwise untouched.")
                    return 1
                clean, problems = problems_now()
                if first_pass is None:
                    # The eval metric: violations before any correction round.
                    first_pass = len(problems)
                    run_metrics.set(first_pass_violations=first_pass)
                (say if clean else tell)(
                    f"  lint      "
                    f"{'clean' if clean else f'{len(problems)} blocking'}"
                    f" (attempt {attempt + 1})")
                if clean:
                    break
                contents.append({"role": "user", "parts": [{"text":
                    "Lint is not clean. Fix every one of these, then stop:\n\n"
                    + "\n".join(f"  {m}" for _, m in problems)}]})
            else:
                tell(f"  lint      still failing after {MAX_LINT_ATTEMPTS} "
                     f"attempts. Nothing committed; the entry is on disk to "
                     f"fix by hand.")
                blocked(problems)
                run_metrics.close("lint_failed")
                return 1

        chapter, stem = session.chapter, session.stem
        entry_path = session.entry_path

        # --- the granted ceiling, BEFORE anything is paid for ---------------
        # Source only, so it costs nothing here and everything at the commit.
        note = _ceiling_problem(notebook, entry_path, session.render_ceiling)
        if note:
            tell(f"  ceiling   {note.splitlines()[0]} — handing it back")
            contents.append({"role": "user", "parts": [{"text":
                note + "\n\nFix that and stop."}]})
            loop_once()
            clean, problems = problems_now()
            if not clean:
                tell(f"  lint      {len(problems)} blocking after the ceiling "
                     f"fix; stopping. The entry is on disk.")
                blocked(problems)
                run_metrics.close("lint_failed")
                return 1

        # --- the entry must BUILD before it is committed --------------------
        _refresh_index_freeze(notebook, chapter)
        renders = 0
        while True:
            note = verifiers.build_entry(notebook, chapter, stem, entry_path,
                                         session=session)
            if note is None:
                break
            # A page that does not BUILD is a code error with a traceback
            # naming the line, which the model fixes in a turn. A missing
            # freeze after a successful render is nothing it can act on, and
            # ends the run.
            buildable = note.startswith(verifiers.BUILD_FAILED)
            if not buildable or renders >= MAX_RENDER_FIXES:
                tell(f"  build     could not run — {note}")
                runstate.write(notebook, failure=note[:2000])
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
            clean, problems = problems_now()
            if not clean:
                tell(f"  lint      {len(problems)} blocking after the render "
                     f"fix; stopping. The entry is on disk.")
                blocked(problems)
                run_metrics.close("lint_failed")
                return 1

        # What the RENDER cost, from the page it just produced -- the
        # expensive solves, and the ones rule 17 judges.
        cost = _render_cost(notebook, chapter, stem)
        if cost:
            run_metrics.set(solves=cost[0], solve_seconds=cost[1])

        # --- the chapter's shared machinery moved: prove it moved nothing ---
        # Adding an `_analysis.py` helper is additive and safe; changing the
        # body of one a sibling already calls is a refactor, and Quarto's
        # freeze tracks the page rather than its includes, so nothing else
        # would ever notice. `check` deletes the freeze, re-renders and diffs.
        moved, evidence, accepted = [], [], []
        chapter_dir = notebook.chapters_dir / chapter
        if session.siblings:
            for name in ("_model.py", "_analysis.py"):
                after = guards.bodies(chapter_dir / name)
                before = session.before_bodies.get(name, {})
                for fn in guards.changed_bodies(before, after):
                    moved.append(f"{name}:{fn}")
                    evidence.append(_why_and_diff(
                        name, fn, before[fn], after[fn],
                        session.refactor_notes.get(fn)))
        if moved:
            tell(f"  check     {', '.join(moved)} changed — re-proving "
                 f"{session.siblings} sibling entr"
                 f"{'y' if session.siblings == 1 else 'ies'}")
            out = verifiers.check(notebook, chapter)
            # `check` reports its own exit code in the first line; non-zero
            # means the diff was not empty, which IS the finding.
            if not str(out).startswith("check exit=0"):
                # The diff prints EITHER WAY. Accepting is meant to be loud:
                # `refactoring.md` holds that a refactor which moves anything
                # wants superseding rather than silent updating.
                tell(f"\n  {'─' * 70}\n  REFACTOR CHANGED THE ANSWERS"
                     f"{' — ACCEPTED' if accept_refactor else ' — not committed'}"
                     f"\n  {'─' * 70}")
                for block in evidence:
                    tell(block)
                tell(f"{out}\n")
                if not accept_refactor:
                    tell(f"  The entry and the changed machinery are on disk. "
                         f"Either the change is wrong, or the entries it moved\n"
                         f"  need superseding rather than silently updating. If "
                         f"the diff is presentation only and you have read it:\n"
                         f"    uv run --group nb python -m nb resume "
                         f"{notebook.root.name} {notebook.run_id} "
                         f"--accept-refactor\n")
                    run_metrics.close("refactor_moved_answers")
                    return 1
                accepted = moved
            else:
                tell("  check     clean — the refactor moved nothing")
    except Stopped as e:
        # Asked to stop. Whatever is on disk stays exactly where it is: a stop
        # is "spend nothing more on this", not "undo it".
        run_metrics.close("stopped")
        tell(f"\n  {e}. " + (f"The entry is on disk at\n  {session.entry_path}"
                             if session.entry_path else "Nothing was written."))
        return 1
    except RuntimeError as e:
        run_metrics.close("max_turns")
        if session.entry_path is None:
            tell(f"\n  {e}. Nothing was written.")
            return 1
        tell(f"\n  {'─' * 70}\n  OUT OF TURNS — nothing committed\n"
             f"  {'─' * 70}\n  {e}\n"
             f"  entry     {session.entry_path}\n\n"
             f"  It is on disk and unlinted. To pick it up:\n"
             f"    uv run --group nb python -m nb resume {notebook.root.name} "
             f"{notebook.run_id}\n")
        return 1
    except SystemExit:
        # A mailbox question that went an hour unanswered, or a prompt that hit
        # EOF. Recorded before it propagates: a run that vanishes without an
        # outcome is drawn as `died`, the one state the board exists to keep
        # separate from an ending the system chose.
        run_metrics.close("no_answer")
        tell(f"\n  {'─' * 70}\n  NO ANSWER — nothing committed\n"
             f"  {'─' * 70}\n"
             + (f"  entry     {session.entry_path}\n" if session.entry_path
                else "")
             + f"\n  Answer the question in the run directory, then:\n"
               f"    uv run --group nb python -m nb resume "
               f"{notebook.root.name} {notebook.run_id}\n")
        raise
    finally:
        fs.stop()
        # The run's probe kernel, which outlives any single probe by design and
        # so has to be ended by the run. In `finally` beside `fs.stop()`: an
        # abandoned kernel holds a python process and the chapter's memory for
        # as long as the terminal lives, and the paths out of here include
        # KeyboardInterrupt and a raise from `_execute` itself.
        kernel.shutdown(notebook)

    return _finish(notebook, session, run_metrics, first_pass, moved,
                   accepted)


def _finish(notebook, session, run_metrics, first_pass, moved, accepted):
    """Commit what passed every gate, then say what it says."""
    chapter, stem = session.chapter, session.stem
    title = session.entry_title
    # Rule 26 lets the title be a rephrasing, so the words actually used to ask
    # have to survive somewhere that cannot be edited later. `run.json` is
    # overwritten by the next run; the commit is not.
    if session.question and session.question.strip() != title.strip():
        title += f"\n\nAsked: {session.question.strip()}"

    # THE GUARANTEE, not the gate. The gate is beside the lint loop, where the
    # entry has not yet been rendered and the model can still fix it; reaching
    # here means it was handed back and came out wrong anyway. The render
    # ceiling was GRANTED, not negotiated -- otherwise the number typed at the
    # prompt is decoration.
    note = _ceiling_problem(notebook, session.entry_path,
                            session.render_ceiling)
    if note:
        tell(f"  Not committed: {note}")
        run_metrics.close("ceiling_changed")
        return 1

    # THE TARGETS GATE, and the only new gate in this system. It runs for a
    # reconstruct run only -- an ordinary question is not held to the brief's
    # targets, which belong to the chapter's vehicle rather than to every
    # entry about it. Like the ceiling above it this is the guarantee rather
    # than the teaching: the brief already says to report every target.
    if getattr(session, "kind", "run") == "reconstruct":
        from ..contract import shared
        note = targets_unreported(notebook, session.entry_path,
                                  shared.notebook_targets(notebook.root))
        if note:
            tell(f"  Not committed: {note}")
            run_metrics.close("targets_unreported")
            return 1

    extra = ()
    # WHENEVER THE GATE RAN, not only when its finding was accepted. `check`
    # re-renders every sibling that reaches the changed function, which
    # rewrites their freezes whatever the verdict -- so a refactor that came
    # back "moved nothing" left them rebuilt and UNCOMMITTED beside a committed
    # `_analysis.py`, which is the exact invariant the freeze exists to keep:
    # the committed freeze stops matching the committed code.
    if moved and session.siblings:
        extra = (notebook.freeze / chapter,)
    if accepted:
        title += ("\n\nAccepted refactor: " + ", ".join(accepted) +
                  f". {session.siblings} sibling entr"
                  f"{'y' if session.siblings == 1 else 'ies'} re-proved and "
                  f"re-frozen.")
    # BEFORE the front page and before the commit, because both read it: an
    # entry added here can change what any descendant chapter inherits, and
    # every `_active.yml` it moved has to ride THIS commit or the tree carries
    # a rendered page whose source is uncommitted.
    extra = tuple(extra) + tuple(_refresh_active(notebook))
    _refresh_root_index(notebook)
    sha, detail = _commit(notebook, chapter, stem, session.entry_path, title,
                          extra_paths=extra)
    if sha is None:
        tell(f"  commit    FAILED — {detail}")
        run_metrics.close("commit_failed")
        return 1
    # SPENT, and recorded where the resume path reads it. `nb resume` refuses a
    # committed run: unsealed, resuming a finished one re-executed the whole
    # entry and wrote a SECOND copy of it under today's date -- a duplicate
    # that lints, renders and would have committed. Every other ending leaves
    # this unset, which is what makes them resumable.
    #
    # AND WHAT THE ENTRY CONCLUDED, beside it. `outcome: committed` and a sha
    # say the work happened; they do not say it came out at 5.38, and a reader
    # deciding what to ask next needs the answer rather than the bookkeeping.
    # Until now the only place that existed in words was the prose printed into
    # `status.log` -- a timestamped text file nothing parses, interleaved with
    # the model's reasoning. Both are read off the FREEZE, so they are the
    # numbers the published page shows.
    prose = rendered_prose(notebook, chapter, stem)
    runstate.write(notebook, committed={
        "sha": sha, "entry": stem,
        "at": datetime.datetime.now().isoformat(timespec="seconds")},
        answer=answer_line(notebook, chapter, stem),
        prose=(prose[:PROSE_CAP] if prose else None))
    n_paths = len(detail.split(", "))
    committed = f"  commit    {sha} · {n_paths} file{'s' if n_paths != 1 else ''}"
    say(f"  commit    {sha}  ({detail})")
    say(f"  first-pass violations: {first_pass}")
    if session.probe_pool or session.pool_total:
        # The QUESTION's total against the grant, not one phase's slice of it.
        total = session.pool_total or session.probe_pool
        spent = total - (session.probe_left or 0.0)
        say(f"  budget    {spent:.0f} s of {total:.0f} s probe pool used")
    run_metrics.close("committed_refactor" if accepted else "committed")

    # The entry itself, with real numbers. Conversation, not telemetry: it is
    # the thing to read, and with no gate before it this is where a reader
    # watching the log first sees what was actually claimed. A reader who is
    # not watching gets it from `run.json`, above.
    if prose:
        tell(f"\n{'─' * 72}\n{prose}\n{'─' * 72}")
    tell(committed)

    # After the commit, never before: a project render touches every page in
    # the notebook, and an unrelated broken one must not be able to block an
    # entry that has already passed lint and built on its own terms.
    page = notebook.root / "_site" / "chapters" / chapter / f"{stem}.html"
    site(notebook, page=page)

    # AND PUT IT IN FRONT OF SOMEONE. The same gate as the watcher window, so
    # `--no-watch` means "this run opens nothing" rather than suppressing one
    # of the two. Last, because a page is worth nothing if the commit did not
    # happen, and `site()` is what writes the one being pointed at.
    #
    # A MARKER, NOT A BROWSER CALL. Opening the page would be another tab every
    # time, and no browser dedupes a URL it already has. `nb open` serves the
    # site with a few lines of injected JavaScript polling for this file, so
    # writing it sends whatever tab is open to the new entry -- and writing it
    # when no server is running is simply read by nobody.
    if (runstate.read(notebook) or {}).get("watch", True):
        serve.record(notebook, f"chapters/{chapter}/{stem}.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], " ".join(sys.argv[2:])))

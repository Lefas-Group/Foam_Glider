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
from ..loop import Stopped, run as drive
from ..session import Session
from ..preflight import check as preflight
from ..tools import guards, verifiers
from ..tools.interact import ask_pool, ask_render_ceiling, ask_stuck
from .. import briefs, metrics, runstate
from .view import site
from .common import setup, report, spoken_calls
from .write import (_ceiling_problem, _commit, _refresh_index_freeze,
                    _refresh_root_index, _render_cost, _resolve, _why_and_diff,
                    rendered_prose)
from ..log import detach_output, detached, open_log, say, tell


def _start(notebook, quiet, answers):
    """Mailbox, fork, log redirection -- identical for a fresh run and a resume."""
    from ..mailbox import Mailbox
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
        from ..detach import detach_process
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
    runstate.hold(notebook)
    detach_output()


def main(notebook_path, question, verbose=True,
         pool=None, ceiling=None, run_id=None, quiet=False,
         answers=None, chapter=None):
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
    runstate.write(notebook, phase="run", question=question,
                   chapter=chapter, turn=0, waiting_on=None)
    _start(notebook, quiet, answers)
    open_log(notebook, "run", question)
    run_metrics = metrics.Run(notebook, "run", question)

    # Asked once, here, and the number bounds the WHOLE question rather than
    # one half of it. `--pool` and `--ceiling` skip the prompt entirely: a
    # caller who already knows the numbers -- a coordinator, a script, anyone
    # re-running a question -- was being asked them twice a run for no decision.
    if pool is None:
        pool = ask_pool(PROBE_POOL)
    # Granted before anything is built, so the agent designs within it rather
    # than discovering it at render time. `lint._defaults` is the ONLY source
    # of the default, flag or no flag: a second copy of this number in
    # `config.py` disagreed with the notebook once -- 20 s against 200 s -- so
    # the flag overrides the ANSWER and never the source of the default.
    if ceiling is None:
        import lint
        _, default_ceiling = lint._defaults(notebook.root)
        ceiling = ask_render_ceiling(
            default_ceiling or 200.0,
            "declared by this notebook's _notebook.py" if default_ceiling
            else "no notebook default; nb's fallback")

    session = Session(notebook, question, chapter=chapter,
                      metrics=run_metrics, probe_pool=pool)
    session.render_ceiling = ceiling
    run_metrics.set(chapter=chapter)

    # ONE WRITER PER CHAPTER, claimed before a single token is spent. Refused
    # rather than queued: two agents in one chapter edit the same
    # `_analysis.py` and the refactor gate then blames whichever asks first.
    from ..locks import claim_chapter
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

    contents = [{"role": "user", "parts": [{"text": briefs.BRIEF.format(
        question=question, max_turns=MAX_TURNS, chapter=chapter)}]}]
    return _execute(notebook, session, contents, run_metrics, fs, handlers,
                    make_config, verbose, accept_refactor=False)


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

    runstate.write(notebook, phase="run")
    _start(notebook, quiet, answers)
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
    from ..locks import claim_chapter
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
        chapter=chapter, stem=stem, question=question, why=why)}]}]
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
        """Lint, plus the one thing lint cannot see: no entry file at all."""
        clean, problems = verifiers.is_clean(notebook, session.chapter)
        if not session.entry_path.exists():
            return False, [f"chapters/{session.chapter}/{session.stem}.qmd does "
                           f"not exist. You opened the entry and never wrote "
                           f"it -- `write_file` it, then lint."] + list(problems)
        return clean, problems

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
                    + "\n".join(f"  {p}" for p in problems)}]})
            else:
                tell(f"  lint      still failing after {MAX_LINT_ATTEMPTS} "
                     f"attempts. Nothing committed; the entry is on disk to "
                     f"fix by hand.")
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
    runstate.write(notebook, committed={
        "sha": sha, "entry": stem,
        "at": datetime.datetime.now().isoformat(timespec="seconds")})
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
    # the thing to read, and with no gate before it this is where a reader --
    # human or coordinating agent -- first sees what was actually claimed.
    prose = rendered_prose(notebook, chapter, stem)
    if prose:
        tell(f"\n{'─' * 72}\n{prose}\n{'─' * 72}")
    tell(committed)

    # After the commit, never before: a project render touches every page in
    # the notebook, and an unrelated broken one must not be able to block an
    # entry that has already passed lint and built on its own terms.
    site(notebook, page=notebook.root / "_site" / "chapters" / chapter
                        / f"{stem}.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], " ".join(sys.argv[2:])))

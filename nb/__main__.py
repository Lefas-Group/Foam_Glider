"""
    nb new   <notebook> [title]              scaffold a notebook, then prove it
             [--spec "…"] [--assume "…"]      …the brief, repeatable
             [--chapter-title "…"]            …name the first chapter
    nb ask   <notebook> --chapter NN-name    probe, write, render, commit
             "<question>"                      …the chapter is REQUIRED
             [--pool N] [--ceiling N]         …budgets, instead of being asked
             [--quiet] [--answers f.json]     …no board on this terminal;
                                              …replies keyed by question name:
                                              …a quantity, or a chapter name
    nb resume <notebook> [run]               resume: a gate, a refactor, a
             [--allow-refactor]               …run that died with work on disk
             [--accept-refactor]              …committing a diff you have read
    nb view  <notebook> [--force]            render the whole site
    nb eval  <notebook>                      what each model actually did
    nb board <notebook>                      N agents, one terminal
    nb answer <notebook> [run] "<value>"     reply to a waiting run
    nb stop  <notebook> [run] ["why"]        ask a run to stop, and record it
    nb watch <notebook> [run] [--all]        follow the detail, live
    nb clean <notebook> [run] [--keep N]     drop spent run directories
             [--yes]                          …a named run, or all but the last N

The terminal carries the conversation only -- the questions, the milestones, the
finished entry. Every turn, the model's reasoning and the probe budgets go to
`<notebook>/_scratch/run/status.log`; `nb watch` follows it from another tab.
There is no flag: an option everyone sets the same way is a default in disguise.

`ask` runs a question through to a commit in ONE conversation -- probe, chapter,
entry, lint, render, commit. It used to be two, with `proposal.json` between
them, and the boundary bought nothing: seven of ten recorded runs crossed it
inside a single process, milliseconds apart.

It still stops for two things, both of them decisions about structure or spend
rather than approvals of output: a NEW CHAPTER, which later entries build on,
and a refused edit to a chapter's `_model.py`, which would mean re-solving every
sibling to prove the answers did not move. Both are now questions the run waits
on rather than exits for, so answering one costs a keystroke instead of a second
command. Walk away from either and it ends exactly as it used to: the question
on disk, the work on disk, `nb resume` to pick it up.

There is no gate on the finished entry, because by then lint and the render
have all passed and an entry that turns out wrong is corrected by the next
entry, which states the old value, the new one and why they differ. The record
is append-only: nothing is edited after it is committed. The rendered prose,
with its real numbers, is printed when the entry commits.
"""

import sys

USAGE = __doc__.strip()


def _answers(argv):
    """`--answers file.json`: replies supplied up front, so the board is not
    interrupted for anything already decided."""
    if "--answers" not in argv:
        return None
    i = argv.index("--answers")
    if i + 1 >= len(argv):
        return None
    import json
    import pathlib
    try:
        return json.loads(pathlib.Path(argv[i + 1]).read_text())
    except (OSError, ValueError) as e:
        print(f"  --answers: {e}")
        return None


def _repeated(argv, flag):
    """Every `--flag value` pair, in order. A brief is a list, not a setting."""
    return [argv[i + 1] for i, a in enumerate(argv)
            if a == flag and i + 1 < len(argv)]


def _free(argv, flags):
    """Words that are neither a flag nor a flag's value."""
    taken = {i + 1 for i, a in enumerate(argv) if a in flags}
    return [a for i, a in enumerate(argv)
            if i not in taken and not a.startswith("--")]


def _opt(argv, flag, number=True):
    """`--flag value`, or None. A budget nobody set is asked for, as before."""
    if flag not in argv:
        return None
    i = argv.index(flag) + 1
    if i >= len(argv):
        return None
    if not number:
        return argv[i]
    try:
        v = float(argv[i])
    except ValueError:
        return None
    return v if v > 0 else None


def main(argv):
    # A run is minutes long and prints one line per turn. Block-buffered to a
    # file or a pipe that is a silent hang, which is indistinguishable from a
    # stuck probe at exactly the moment you want to tell them apart.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "new":
        if not rest:
            print(USAGE)
            return 2
        from .phases.new import main as new
        # THE BRIEF, on the command line. It was always a hand-edit afterwards,
        # and the prefix is built once at `nb ask` -- so forgetting meant a
        # first run with no notebook level in front of the model at all.
        specs, assumes = _repeated(rest, "--spec"), _repeated(rest, "--assume")
        chapter_title = _opt(rest, "--chapter-title", number=False)
        title = " ".join(_free(rest[1:], ("--spec", "--assume",
                                          "--chapter-title"))) or None
        return new(rest[0], title, specs=specs, assumes=assumes,
                   **({"chapter_title": chapter_title} if chapter_title else {}))

    if cmd == "ask":
        if len(rest) < 2:
            print(USAGE)
            return 2
        from .phases.run import main as ask
        # `--detach` is kept as an alias: every run detaches now, and what
        # the flag used to buy -- no board drawn on this terminal -- is what
        # `--quiet` means. It is in old scripts and old muscle memory.
        quiet = "--quiet" in rest or "--detach" in rest
        answers = _answers(rest)
        pool, ceiling = _opt(rest, "--pool"), _opt(rest, "--ceiling")
        # REQUIRED, and refused here rather than after preflight and a fork.
        # A question is about an aircraft, and the aircraft is the chapter: the
        # model used to work it out from six chapters' worth of context, which
        # cost a turn on every run and made the fork criterion a six-way
        # classification instead of one comparison. Naming it is the caller's
        # half of the question.
        chapter = _opt(rest, "--chapter", number=False)
        if not chapter:
            from .config import Notebook
            try:
                known = Notebook(rest[0]).chapters()
            except Exception:
                known = []
            print(f"  --chapter is required: a question is about an aircraft, "
                  f"and the aircraft is the chapter.")
            print(f"  {rest[0]} has: {', '.join(known) if known else '(none)'}")
            print(f"\n  If this question needs a chapter that does not exist "
                  f"yet, name the one it\n  comes FROM — the run stops and asks "
                  f"before creating anything.")
            return 2
        # Everything that is not a flag or a flag's value is the question.
        taken = set()
        for f in ("--pool", "--ceiling", "--chapter", "--answers"):
            if f in rest:
                taken.add(rest.index(f) + 1)
        words = [r for i, r in enumerate(rest)
                 if i and i not in taken and not r.startswith("--")
                 and not r.endswith(".json")]
        return ask(rest[0], " ".join(words), quiet=quiet, answers=answers,
                   pool=pool, ceiling=ceiling, chapter=chapter)

    # `resume` is the crash path and the two approvals now, not the routine
    # one: a run that is answered at the keyboard never comes back here. `write`
    # stays as an alias, since it is in old logs, old commit messages and
    # muscle memory.
    if cmd in ("resume", "write"):
        if not rest:
            print(USAGE)
            return 2
        from .phases.run import resume as write
        args = [r for r in rest[1:] if not r.startswith("--")]
        return write(rest[0],
                     run_id=args[0] if args else None,
                     allow_refactor="--allow-refactor" in rest,
                     accept_refactor="--accept-refactor" in rest,
                     quiet="--quiet" in rest or "--detach" in rest,
                     answers=_answers(rest))

    if cmd == "watch":
        if not rest:
            print(USAGE)
            return 2
        from .phases.watch import main as watch
        return watch(rest)

    if cmd == "board":
        if not rest:
            print(USAGE)
            return 2
        from .phases.board import main as board
        return board(rest)

    if cmd == "answer":
        if len(rest) < 2:
            print(USAGE)
            return 2
        from .phases.answer import main as answer
        return answer(rest)

    if cmd == "stop":
        if not rest:
            print(USAGE)
            return 2
        from .phases.stop import main as stop
        return stop(rest)

    if cmd == "clean":
        if not rest:
            print(USAGE)
            return 2
        from .phases.clean import main as clean
        return clean(rest)

    if cmd == "eval":
        if not rest:
            print(USAGE)
            return 2
        from .phases.eval import main as evaluate
        return evaluate(rest)

    if cmd == "view":
        if not rest:
            print(USAGE)
            return 2
        from .phases.view import main as view
        return view(rest)

    print(f"unknown command {cmd!r}\n\n{USAGE}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

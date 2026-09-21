"""
    nb new   <notebook> [title]              scaffold a notebook, then prove it
    nb ask   <notebook> "<question>"         probe, write, render, commit
             [--pool N] [--ceiling N]         …budgets, instead of being asked
             [--chapter NN-name]              …route here, do not go looking
             [--quiet] [--answers f.json]     …no board on this terminal
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

`ask` runs a question through to a commit. It stops for two things, both of them
decisions about structure or spend rather than approvals of output: a NEW
CHAPTER, which later entries build on, and a refused edit to a chapter's
`_model.py`, which would mean re-solving every sibling to prove the answers did
not move. `nb write` resumes from `proposal.json` in either case.

There is no gate on the finished entry, because by then lint and the render
have all passed and an entry that turns out wrong is corrected by the next entry
-- `superseded_by()` exists for exactly that, and the record is append-only. The
rendered prose, with its real numbers, is printed when the entry commits.

`ask` and `write` remain separate conversations inside one process: the write
phase starts fresh from the proposal, which costs ~6% less than carrying the
probe history forward and is what the two stops resume from.
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
        return new(rest[0], " ".join(rest[1:]) or None)

    if cmd == "ask":
        if len(rest) < 2:
            print(USAGE)
            return 2
        from .phases.ask import main as ask
        # `--detach` is kept as an alias: every run detaches now, and what
        # the flag used to buy -- no board drawn on this terminal -- is what
        # `--quiet` means. It is in old scripts and old muscle memory.
        quiet = "--quiet" in rest or "--detach" in rest
        answers = _answers(rest)
        pool, ceiling, chapter = _opt(rest, "--pool"), _opt(rest, "--ceiling"), \
            _opt(rest, "--chapter", number=False)
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

    # `resume` is what every one of its four uses is -- a gate approved, a
    # refactor allowed, a diff accepted, or a run that died with its entry
    # finished. `write` is the phase's name internally and stays as an alias,
    # since it is in old logs, old commit messages and muscle memory.
    if cmd in ("resume", "write"):
        if not rest:
            print(USAGE)
            return 2
        from .phases.write import main as write
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

"""
`nb coordinate <notebook> ["<direction>"]` -- the coordinator, as an agent.

THE SAME ROLE A PERSON PLAYS AT THE BOARD, and deliberately nothing more. It
decides what to ask, answers what the runs ask back, escalates what it may not
decide, and narrates to the board. It writes no entry and holds no chapter
lock, so it changes nothing about how a run behaves -- `process/mailbox.py`
anticipated this exactly: an answer is a file, and the run cannot tell who
wrote it.

A DIFFERENT MODEL FROM THE RUNS, on purpose. `config.COORD_MODEL` is pro while
`config.MODEL` is flash, which puts them on separate daily quotas: a busy
afternoon of runs cannot starve the thing that decides what to run next.

IT RUNS IN THE FOREGROUND, which is what makes it the HEADLESS entry: a cron
job or a script has no terminal to hand a board and must not be given one.
`nb designer` is the other door -- same session, forked into the background
with the board in front of it -- and it calls `coordinate()` here rather than
reimplementing any of this.

A blocking tool call costs no turn and no tokens, so `wait` simply does not
return until something happens -- which is the whole reason this is an agent
loop rather than the polling the Claude Code skill is obliged to do. Detached,
that silence is indistinguishable from a hang, which is why this opens a
`status.log` for the reserved id: `nb watch <nb> coordinator` follows it.

COLD START IS THE NORMAL ENTRY. There is no transcript to resume: the
programme's state is the manifest, the notes and the mailbox, and
`coord/prefix.py` rebuilds from those every time. Run it again after it
finishes and it picks the programme up.
"""

import pathlib
import shutil
import sys
import tempfile

from google.genai import types

from ..agent.client import config as make_config, usage
from ..agent.loop import Stopped, run as drive
from ..config import COORD_MODEL, MAX_TURNS, Notebook
from ..coord import prefix, tools
from ..coord.session import Coordination
from ..process import coordinator
from ..process.log import close_log, open_log, say, tell


def _opt(argv, flag, number=False):
    if flag not in argv:
        return None
    i = argv.index(flag) + 1
    if i >= len(argv):
        return None
    if not number:
        return argv[i]
    try:
        return float(argv[i])
    except ValueError:
        return None


def _turns(session):
    """
    An `on_turn` bound to this session: one log line, and a heartbeat.

    THE HEARTBEAT IS WHY THIS IS A CLOSURE. `run.json`'s `updated` was stamped
    only by `note`, `post` and `reply`, so a coordinator ten turns into
    research looked exactly as stale as a dead one and the board had nothing
    to show but `nothing running`. Touched here, `updated` means "start of the
    current turn" -- which is what it means for a run, so the board's status
    line needs no special case for the elapsed time it prints.

    `session.notebook`, not a notebook captured at launch: a setup session
    starts with none and `new` adopts one mid-flight, and those are precisely
    the sessions where a person is watching the board for signs of life.
    """
    def on_turn(n, resp, turn):
        calls = [p.function_call for p in (turn.parts or []) if p.function_call]
        named = ", ".join(_what(c) for c in calls) or "(no tool call)"
        # Thinking is shown because it is the cost: THINKING_LEVEL is HIGH and
        # the coordinator runs on pro, so a turn that looks cheap in output
        # tokens usually is not.
        p_tok, c_tok, o_tok, t_tok = usage(resp)
        tell(f"  turn {n + 1}  {named}"
             f"   [{p_tok} in, {c_tok} cached, {o_tok} out, {t_tok} thinking]")
        if session.notebook is not None:
            coordinator.touch(session.notebook, turn=n + 1)
    return on_turn


#: Which argument says WHAT a call is acting on. Mirrors `agent/setup.py`:
#: `-> wait` eight times says only that it is waiting; `-> answer <run>` says
#: whether it is going in circles.
_SUBJECT = {"ask": "chapter", "answer": "run", "read_run": "run",
            "stop": "run", "escalate": "name", "direction": "text",
            "note": "text", "finish": "summary"}


def _what(call):
    key = _SUBJECT.get(call.name)
    arg = (dict(call.args or {}).get(key) if key else None)
    if not arg:
        return call.name
    arg = " ".join(str(arg).split())
    return f"{call.name} {arg[:60]}"


def _seed(notebook):
    """
    The opening user turn, when no direction was carried on the command line.

    THE SEED IS NOT THE DIRECTION, and saying so is the whole job of this
    function. Under `nb designer` the direction is a question on the board and
    the answer has not arrived yet -- and the placeholder that used to stand
    here, "Pick up this programme where it stands and carry it forward", read
    as an instruction the model could act on. Measured on ft-warthog: turn 1
    pinned those exact words as the programme's direction, six seconds before
    the person finished typing theirs, so the direction on the board was a
    sentence no human wrote and the real one was never recorded.
    """
    from ..process import mailbox
    if notebook is not None and mailbox.pending(
            coordinator.mailbox_for(notebook).run):
        return ("A question is outstanding with the user on the board and no "
                "reply has arrived yet. Call `wait` FIRST, before anything "
                "else. These words are not the direction -- theirs are, and "
                "`wait` is how you get them.")
    return ("Pick up this programme where it stands and carry it forward. "
            "Read the manifest first.")


def _transcript(session):
    """Where this session's turns go. A temp file until there is a notebook."""
    if session.notebook is not None:
        d = coordinator.mailbox_for(session.notebook).run
        d.mkdir(parents=True, exist_ok=True)
        return d / "transcript.jsonl"
    fh = tempfile.NamedTemporaryFile(prefix="nb-coord-", suffix=".jsonl",
                                     delete=False)
    fh.close()
    return pathlib.Path(fh.name)


def _file_transcript(session, tpath):
    """
    Move a setup session's transcript under the notebook it created.

    AFTER the loop, not during: `loop.py` reopens the path on every turn, so
    moving it mid-session would simply recreate it at the old location and
    split the record in two.
    """
    if session.notebook is None or tpath is None:
        return tpath
    dest = coordinator.mailbox_for(session.notebook).run / "transcript.jsonl"
    if tpath == dest:
        return tpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    if tpath.exists():
        shutil.move(str(tpath), dest)
    return dest


def coordinate(name, direction="", max_turns=MAX_TURNS, banner=True):
    """One coordinating session, with its log closed on every exit path."""
    try:
        return _session(name, direction, max_turns, banner)
    finally:
        # FIVE WAYS OUT of the session below -- finished, stopped, turn cap,
        # transport failure, and the silent one where the model simply stops
        # calling tools. A log left open on any of them is a `nb watch` that
        # never sees the end.
        close_log()


def _session(name, direction, max_turns, banner):
    """
    The session itself. -> exit code.

    SEPARATE FROM `main` so `nb designer` can run it in the forked child
    without rebuilding an argv to re-parse. The split is the same one
    `cli/run.py` makes between its flag handling and `_execute`: argv belongs
    to the command, the session does not.

    `banner` is off in the child, where stdout is `stderr.log` and the person
    is looking at the board instead.
    """
    # A NOTEBOOK THAT DOES NOT EXIST YET IS THE OTHER BRANCH, not an error.
    # Setting an aircraft up is this command's job too, and the research that
    # fills the brief has to happen BEFORE `nb new` creates the directory the
    # brief goes into -- so the session starts without a notebook and `new`
    # hands it one. `Notebook()` raises on a directory with no `chapters/`,
    # which is exactly the test for "not scaffolded yet".
    try:
        notebook = Notebook(name)
    except SystemExit:
        notebook = None
    session = Coordination(notebook, direction=direction,
                           model=COORD_MODEL, wanted=name)
    text = prefix.build(notebook, direction=direction, name=name)
    tool_list, handlers = tools.build(session)

    # ITS OWN status.log, like a run's. Detached behind `nb designer` the
    # terminal belongs to the board, so without this the coordinator's only
    # voice is `nb note` -- and a `wait` that blocks for twenty minutes reads
    # exactly like a process that has died. `nb watch <nb> coordinator`
    # follows it.
    if notebook is not None:
        open_log(coordinator.mailbox_for(notebook), "coordinate",
                 direction or "(picking the programme up)")
    where = notebook.root.name if notebook else f"{name} (new)"
    if banner:
        tell(f"coordinating {where} on {COORD_MODEL}")
        if direction:
            tell(f'  direction: "{" ".join(direction.split())[:160]}"')
        tell(f"  board:  uv run --group nb python -m nb board {name}")
    else:
        say(f"coordinating {where} on {COORD_MODEL}")

    contents = [{"role": "user", "parts": [{"text":
        direction or _seed(notebook)}]}]
    # REQUIRED because `tools` carries a built-in tool (google_search) beside
    # the function declarations; without it the API refuses the pair outright.
    # See `agent/client.py::config`.
    cfg = make_config(tools=tool_list, system_instruction=text,
                      tool_config=types.ToolConfig(
                          include_server_side_tool_invocations=True))

    # THE TRANSCRIPT PATH IS FIXED BEFORE THE FIRST TURN, which is a problem
    # when the notebook does not exist yet: resolved to None at launch, a
    # whole aircraft-setup session leaves no record -- and those are the
    # sessions most worth reading back, because they are where the brief and
    # the photographs get chosen. So setup writes to a temp file and it is
    # filed under the notebook once there is one, below.
    tpath = _transcript(session)
    try:
        drive(contents, cfg, handlers, transcript=tpath,
              max_turns=max_turns, on_turn=_turns(session),
              model=COORD_MODEL)
    except Stopped as stop:
        _file_transcript(session, tpath)
        tell(f"  stopped: {stop}")
        return 1
    except RuntimeError as exc:
        # `max turns exceeded` is the loop's one RuntimeError, and it is a
        # DIAGNOSTIC rather than a crash: the programme is on disk either way,
        # and starting again picks it up from the manifest.
        _file_transcript(session, tpath)
        tell(f"  {exc}")
        if session.notebook:
            coordinator.note(session.notebook,
                             f"Session ended on its turn cap ({exc}).")
        return 1
    except Exception as exc:
        # A DROPPED NETWORK IS NOT A CRASH HERE, and it reached the terminal as
        # a forty-line httpx traceback. `client.py` retries six times over
        # ~31 s, which is the right patience for a blip and no help at all for
        # an outage lasting minutes -- measured, one took down both this loop
        # and the run it was watching.
        #
        # Nothing is lost that matters: the programme's state is the manifest,
        # the notes and the mailbox, and a cold start rebuilds from those. So
        # say that, in one line, instead of printing a stack from inside
        # httpcore. Re-raised only if there is no notebook to say it about.
        if session.notebook is None:
            raise
        _file_transcript(session, tpath)
        kind = type(exc).__name__
        tell(f"  the session ended on a {kind}: "
             f"{' '.join(str(exc).split())[:160]}")
        coordinator.note(session.notebook,
                         f"Session ended on a {kind}. The programme is on "
                         f"disk; restart to pick it up.")
        tell(f"  restart:  uv run --group nb python -m nb coordinate "
             f"{name}")
        return 1

    _file_transcript(session, tpath)
    if session.finished:
        tell("")
        for line in session.summary.splitlines():
            tell(f"  {line}")
        return 0

    # The loop ends when the model stops calling tools. Reaching here without
    # `finish` means it stopped talking rather than deciding to stop, which is
    # worth seeing: `finish` is what checks no run was left running, and
    # nothing has checked that.
    tell("  ended without calling `finish` — no summary was written, and "
         "nothing checked whether a run is still going.")
    tell(f"  check:  uv run --group nb python -m nb board {name}")
    return 0



def main(argv):
    """`nb coordinate <notebook> ["<what to do>"] [--max-turns N]`."""
    if not argv:
        tell('usage: uv run --group nb python -m nb coordinate <notebook> '
             '["<what to do>"] [--max-turns N]')
        return 2
    # THE DIRECTION IS ONE QUOTED ARGUMENT, like `nb ask`'s question, and for
    # the reason `nb new` records: "everything that is not a flag" swept a
    # trailing shell comment into a site heading there, and here it swept the
    # VALUE of `--max-turns` into the direction -- `nb coordinate x "…"
    # --max-turns 6` recorded the direction as "… 6" on the board, pinned, for
    # ever. A flag's value is not prose.
    direction = (argv[1] if len(argv) > 1 and not argv[1].startswith("--")
                 else "")
    return coordinate(argv[0], direction=direction,
                      max_turns=int(_opt(argv, "--max-turns", number=True)
                                    or MAX_TURNS))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

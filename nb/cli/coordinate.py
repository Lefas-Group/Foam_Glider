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

IT RUNS IN THE FOREGROUND and holds no terminal hostage while it waits. A
blocking tool call costs no turn and no tokens, so `wait` simply does not
return until something happens -- which is the whole reason this is an agent
loop rather than the polling the Claude Code skill is obliged to do.

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
from ..process.log import tell


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


def _on_turn(n, resp, turn):
    """One line per turn, then the reasoning behind it -- as `nb watch` does."""
    calls = [p.function_call for p in (turn.parts or []) if p.function_call]
    named = ", ".join(_what(c) for c in calls) or "(no tool call)"
    # Thinking is shown because it is the cost: THINKING_LEVEL is HIGH and
    # the coordinator runs on pro, so a turn that looks cheap in output
    # tokens usually is not.
    p_tok, c_tok, o_tok, t_tok = usage(resp)
    tell(f"  turn {n + 1}  {named}"
         f"   [{p_tok} in, {c_tok} cached, {o_tok} out, {t_tok} thinking]")


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


def main(argv):
    if not argv:
        tell('usage: uv run --group nb python -m nb coordinate <notebook> '
             '["<what to do>"] [--max-turns N]')
        return 2
    # A NOTEBOOK THAT DOES NOT EXIST YET IS THE OTHER BRANCH, not an error.
    # Setting an aircraft up is this command's job too, and the research that
    # fills the brief has to happen BEFORE `nb new` creates the directory the
    # brief goes into -- so the session starts without a notebook and `new`
    # hands it one. `Notebook()` raises on a directory with no `chapters/`,
    # which is exactly the test for "not scaffolded yet".
    try:
        notebook = Notebook(argv[0])
    except SystemExit:
        notebook = None
    # THE DIRECTION IS ONE QUOTED ARGUMENT, like `nb ask`'s question, and for
    # the reason `nb new` records: "everything that is not a flag" swept a
    # trailing shell comment into a site heading there, and here it swept the
    # VALUE of `--max-turns` into the direction -- `nb coordinate x "…"
    # --max-turns 6` recorded the direction as "… 6" on the board, pinned,
    # for ever. A flag's value is not prose.
    direction = (argv[1] if len(argv) > 1 and not argv[1].startswith("--")
                 else "")
    max_turns = int(_opt(argv, "--max-turns", number=True) or MAX_TURNS)

    session = Coordination(notebook, direction=direction,
                           model=COORD_MODEL, wanted=argv[0])
    text = prefix.build(notebook, direction=direction, name=argv[0])
    tool_list, handlers = tools.build(session)

    where = notebook.root.name if notebook else f"{argv[0]} (new)"
    tell(f"coordinating {where} on {COORD_MODEL}")
    if direction:
        tell(f'  direction: "{" ".join(direction.split())[:160]}"')
    tell(f"  board:  uv run --group nb python -m nb board {argv[0]}")

    contents = [{"role": "user", "parts": [{"text":
        (direction or "Pick up this programme where it stands and carry it "
                      "forward. Read the manifest first.")}]}]
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
              max_turns=max_turns, on_turn=_on_turn, model=COORD_MODEL)
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
    except Exception as exc:                                # noqa: BLE001
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
             f"{argv[0]}")
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
    tell(f"  check:  uv run --group nb python -m nb board {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

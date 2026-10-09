"""
The coordinator's tool surface.

TYPED, AND NO SHELL. `nb/tools/__init__.py` spent five paragraphs deleting
`bash` from the run agent, with measurements, and the argument carries up here
unchanged: an allowlisted escape hatch becomes the fourth most-used tool and
every call through it is uninstrumented. So there is no `bash` and no free
Python. Everything below wraps a function that already exists.

ONE EXCEPTION, and it is forced. `ask` shells out, because `cli/run.py::_start`
double-forks through `process/detach.py` -- calling it in-process would fork
the coordinator itself and leave two loops sharing one conversation. A fixed
argv through `subprocess.run` is not an escape hatch: the model supplies a
chapter, a question and a reason, never a command.

WHY `wait` REFUSES. `cli/listen.py` re-reports a standing question on every
call deliberately, because for a person a question nobody has answered is
pressure that should not be suppressed. In a tool loop that is a spin: wait
returns at once, the model learns nothing new, it waits again. So the rule
inverts here -- having been told about a question once, the model is refused a
blocking wait until it has acted on it. `session.Coordination.reported` holds
that, and `answer`/`stop` clear it.
"""

import pathlib
import re
import subprocess
import sys
import time

from google.genai import types

from . import research
from ..cli import listen
from ..config import Notebook
from ..process import coordinator, mailbox, runstate

#: How long one `wait` blocks before returning empty-handed. Long, because a
#: blocking tool call costs no turn and no tokens -- the handler is just a
#: function that has not returned yet -- so the only thing a short timeout buys
#: is a wasted turn reporting that nothing happened. `cli/listen.py` uses the
#: same two hours for the same reason.
WAIT_TIMEOUT = 7200.0
POLL = 2.0

#: `nb ask --quiet` prints `  run       <id>` before it detaches.
RUN_LINE = re.compile(r"^\s*run\s+(\S+)\s*$", re.M)

S = {"type": "string"}
N = {"type": "number"}


def _decl(name, description, properties=None, required=()):
    return types.FunctionDeclaration(
        name=name, description=description,
        parameters_json_schema={"type": "object",
                                "properties": properties or {},
                                "required": list(required)})


def declarations():
    return [
        _decl("direction",
              "Record what the user asked for, in their terms. The board pins "
              "the newest one above everything and it starts the programme's "
              "history. Call this BEFORE the first ask, so nothing in the "
              "programme predates the reason for it.",
              {"text": S}, ["text"]),

        _decl("ask",
              "Put ONE question to a run: it probes, writes an entry, lints, "
              "renders and commits, then ends. Returns at once with a run id; "
              "the work happens in the background and you learn about it from "
              "`wait`. One question per call, and one run per chapter at a "
              "time -- a second in the same chapter is refused by a lock. "
              "Several at once in DIFFERENT chapters is normal and costs you "
              "nothing extra, because `wait` returns on whichever moves first.",
              {"chapter": dict(S, description=(
                   "The chapter directory, e.g. `01-little-piggy-airframe`. "
                   "Required: a chapter is a vehicle, so pick the one whose "
                   "`_model.py` the question is about.")),
               "question": dict(S, description=(
                   "The question, ending in a question mark. One question -- a "
                   "run refuses a second folded in.")),
               "why": dict(S, description=(
                   "WHY THIS QUESTION, NOW -- 40 words maximum, and the run is "
                   "refused if it rewords it. This renders under the question "
                   "as the entry's subtitle, verbatim and for ever. Write it "
                   "for somebody reading the notebook in a month: what the "
                   "last run found that makes this the next question, or which "
                   "decision is waiting on it. The reason, never the method.")),
               "pool": dict(N, description="Probe seconds. Default 200."),
               "ceiling": dict(N, description="Render seconds. Default 90.")},
              ["chapter", "question", "why"]),

        _decl("new",
              "Scaffold a NEW aircraft: a directory, a first chapter, and the "
              "brief. Do this only after you have researched the aircraft, "
              "because the brief is what the runs are given and nothing later "
              "overwrites it. The DIRECTORY IS ALREADY CHOSEN -- it is the one "
              "named when this session started -- so you supply the first "
              "chapter and the brief, nothing else. Returns with the notebook "
              "open; `reconstruct` comes next, after photographs.",
              {"chapter_title": dict(S, description="e.g. `Mighty Mini airframe`."),
               "defines": dict(S, description=(
                   "What this chapter settles, in a phrase -- the geometry "
                   "everything later forks from.")),
               "spec": {"type": "array", "items": S, "description": (
                   "The brief's PUBLISHED FACTS, one per row, each about ten "
                   "words: `**Wingspan**: 736 mm (29 in).` Every linear "
                   "dimension the manufacturer prints goes HERE, because it "
                   "SETS the model's scale -- with span free, size trades "
                   "against camera distance and the silhouette fit goes "
                   "degenerate.")},
               "assume": {"type": "array", "items": S, "description": (
                   "What is assumed ABOUT THE AIRCRAFT, never an instruction "
                   "to the run. These render verbatim on the front page and "
                   "every chapter, for ever. The test: could this sentence be "
                   "true or false of the real aeroplane? "
                   "`**Airfoil**: flat foam plate, a declared stand-in.` is a "
                   "fact. `Never pixel-measure a photograph` is a directive "
                   "and does not belong in a brief at all.")},
               "target": {"type": "array", "items": S, "description": (
                   "What the geometry must PRODUCE and no constant can be "
                   "typed as: wing area, wing loading, aspect ratio, a dry "
                   "mass that falls out of area times areal density, CG. "
                   "NEVER a published dimension -- a span typed here is a "
                   "number the run solves backwards to hit, and the entry "
                   "then reports the model agreeing with itself.")}},
              ["chapter_title", "defines"]),

        _decl("search",
              "Search the web. Use it to find an aircraft's published "
              "specifications and its photographs. It finds PAGES reliably "
              "and reads figures off them unreliably, so treat a result as a "
              "pointer: `fetch` the page and read the number yourself.",
              {"query": S}, ["query"]),

        _decl("fetch",
              "Download one URL into this session's scratch. A web page comes "
              "back as text you can read immediately; an image or PDF is "
              "saved and read with `read_image` or `read_plan_page`. Fetching "
              "is also what licenses `source` to cite that URL.",
              {"url": S}, ["url"]),

        _decl("read_image",
              "Look at a fetched image. Use this on every candidate "
              "photograph before adding it: you are choosing camera ANGLES, "
              "and you cannot do that from a filename.",
              {"file": S}, ["file"]),

        _decl("read_plan_page",
              "Rasterise one page of a fetched PDF and look at it. Page one "
              "of a plan sheet is usually the specification table -- read the "
              "figures off it and put them in the brief. Do NOT measure the "
              "drawing.",
              {"file": S, "page": N, "dpi": N}, ["file"]),

        _decl("source",
              "Record what a page gave you in `_reference/SOURCES.txt`, which "
              "renders nowhere and is read by whoever comes next. Record the "
              "ABSENCES too -- `wing area and wing loading are not published` "
              "is a result, and an unknown you name is one the run declares "
              "rather than invents. Refused unless you fetched the URL.",
              {"url": S, "text": S}, ["url", "text"]),

        _decl("add_photo",
              "Put a fetched image into `_reference/` as a reference "
              "photograph, with the description the run will read as fact. "
              "MAXIMISE ANGULAR SPREAD: each camera position pins down only "
              "what it happens to show, and shape faults survive in exactly "
              "the directions nobody photographed. Two frames from one shoot "
              "are ONE photograph. REFUSE a frame held in somebody's hands "
              "-- the segmentation model keeps the hand and no number catches "
              "it -- a video thumbnail, a build shot, or any angle you "
              "already have.",
              {"name": dict(S, description="A short slug, e.g. `nose-on`."),
               "file": dict(S, description="The fetched file."),
               "description": dict(S, description=(
                   "Where the CAMERA is and what the frame shows -- `from "
                   "below and ahead, port side, undercarriage visible`. The "
                   "run reads this as fact and nothing checks it, so a frame "
                   "you call `belly` that is actually from above will be "
                   "described wrongly in committed prose. If this sentence "
                   "opens the same way as one you have already written, you "
                   "have the same viewpoint twice -- drop it."))},
              ["name", "file", "description"]),

        _decl("mask",
              "Cut the subject silhouette out of every reference photograph "
              "that has no mask, with a pinned segmentation model. About a "
              "minute a photograph. No thresholds, no parameters -- and when "
              "it is wrong there is deliberately nothing to tune.",
              {"names": {"type": "array", "items": S, "description":
                         "Specific photographs. Omit for all unmasked ones."}}),

        _decl("reference",
              "Check the whole reference set: every photograph, whether each "
              "has a mask the same pixel size as its image, each mask's "
              "roughness and noise, and the PAIRWISE VIEWPOINT SPREAD. This "
              "is the pre-flight before reconstructing -- it must be clean.",
              {}),

        _decl("overlay",
              "Look at a mask drawn over its photograph, interior tinted. "
              "DO THIS FOR EVERY MASK: the segmentation model reports nothing "
              "when it is wrong, and its characteristic failure -- taking in "
              "the hand holding the aeroplane -- produces a perfectly clean "
              "boundary that no number can catch. Judge the FILL, not the "
              "edge: a mask that dropped a whole shaded underside still draws "
              "a convincing line along the lit/shadow crease.",
              {"name": S}, ["name"]),

        _decl("reconstruct",
              "Build a chapter's aircraft and prove it reproduces the brief's "
              "targets. ONCE PER CHAPTER, and before any `ask` against it: it "
              "writes the chapter's first entry and leaves `_model.py` as the "
              "vehicle every later question probes. A chapter whose "
              "`_model.py` is still an empty stub has nothing for `ask` to ask "
              "about, so start here. It takes no question -- the question is "
              "always whether the reconstruction holds -- and carries its own "
              "standing reason, so `why` is only for a reconstruction being "
              "REDONE. Bigger budget than `ask`, because the rebuild loop runs "
              "inside it.",
              {"chapter": S,
               "why": dict(S, description=(
                   "Only when redoing one. Leave empty the first time; the "
                   "standing reason is better than anything you would type.")),
               "pool": N, "ceiling": N},
              ["chapter"]),

        _decl("wait",
              "Block until a run needs you -- it asks a question, reaches an "
              "outcome, or dies -- or until the user answers something you "
              "escalated. THIS IS FREE: a blocking call costs no turn and no "
              "tokens, so call it and wait rather than checking repeatedly. "
              "Returns as soon as anything happens.",
              {"timeout_s": dict(N, description=(
                  "Seconds to block. Default two hours; there is rarely a "
                  "reason to shorten it."))}),

        _decl("answer",
              "Reply to a run that is waiting on a question. Always name the "
              "run: a run you answered a second ago still looks like the only "
              "one waiting until it consumes the reply, and a second bare "
              "answer overwrites the first.",
              {"run": S,
               "value": dict(S, description=(
                   "The reply. The exact syntax for this question's kind is in "
                   "the `how` field `wait` gave you -- for assumptions, `\"\"` "
                   "accepts all, `1: 0.85` corrects one, `1: redo - why` sends "
                   "it back.")),
               "by": dict(S, description=(
                   "`coordinator` when the decision is YOURS -- a chapter you "
                   "approved, an assumption you accepted. `user` only when you "
                   "are relaying what the user actually said, because then "
                   "they are the author and the record must say so. Defaults "
                   "to coordinator."))},
              ["run", "value"]),

        _decl("read_run",
              "Everything a finished run produced: its headline answer, the "
              "rendered entry, the outcome, any lint findings, and every "
              "question it was asked. This is the whole record -- the model's "
              "reasoning is deliberately elsewhere and you do not need it.",
              {"run": S}, ["run"]),

        _decl("board",
              "Every run in this notebook and what it is doing: which chapters "
              "are busy, who is waiting on what, what has finished. Read this "
              "before routing a question, because a chapter with a live run "
              "will refuse a second.",
              {}),

        _decl("manifest",
              "The notebook as the runs see it: every chapter, what it "
              "defines, its specifications and assumptions, and every entry "
              "with the answer it reached. This is how you avoid asking what "
              "has already been answered.",
              {}),

        _decl("note",
              "One line of your reasoning, for the board. The runs publish "
              "themselves; you do not, so this is the user's only view of why "
              "you did what you did. Note what you asked and why, what a "
              "finished run changed, and what you chose next.",
              {"text": S}, ["text"]),

        _decl("escalate",
              "Put a question to the USER, on the board where they are "
              "sitting. Returns at once; the answer arrives through `wait`. "
              "Use this for anything the user's direction does not settle -- "
              "above all a Specified input, which is one where a different "
              "answer changes WHAT IS BEING BUILT. Never guess one of those.",
              {"name": dict(S, description="The quantity or decision, short."),
               "prompt": dict(S, description="The question, in the user's terms."),
               "why": dict(S, description="Why the run is stuck without it.")},
              ["name", "prompt"]),

        _decl("stop",
              "Ask a run to stop. Cooperative, frees a run blocked on a "
              "question at once, and reverts nothing it has already done.",
              {"run": S, "why": S}, ["run"]),

        _decl("resume",
              "Pick up a run that died with work on disk. Only when its "
              "`stem` is set -- that is the entry it had already opened. With "
              "`stem` null it got nowhere and there is nothing to resume; "
              "`clean` it and start again.",
              {"run": S}, ["run"]),

        _decl("clean",
              "Drop a spent run directory. Use it on a run that died having "
              "written nothing, so it stops being reported as outstanding "
              "work. Refuses if the run's chapter has uncommitted changes.",
              {"run": S}, ["run"]),

        _decl("finish",
              "End the session: you have done what the direction asked. "
              "Writes your summary to the board and returns control to the "
              "user. REFUSED while any run you launched is still going -- "
              "walking away from a live run leaves its questions unanswered "
              "and they default silently.",
              {"summary": dict(S, description=(
                  "What you did and what you found, for the user to read."))},
              ["summary"]),
    ]


# =============================================================================
# Handlers


def _runs_dir(notebook, run_id):
    return notebook.scratch / "runs" / run_id


def _launch(session, argv, chapter, pool=None, ceiling=None):
    """
    Start a detached run and hand back its id.

    SHARED by `ask` and `reconstruct` because they differ only in their argv:
    both go through `cli/run.py::_start`, which double-forks, which is why
    neither can be called in-process.
    """
    nb = session.notebook
    if pool:
        argv += ["--pool", str(int(pool))]
    if ceiling:
        argv += ["--ceiling", str(int(ceiling))]
    # cwd is the REPO, not the notebook: `nb` is addressed by directory name
    # from the root, and `Notebook.repo` is the one place that knows which.
    got = subprocess.run(argv, cwd=nb.repo, capture_output=True, text=True,
                         timeout=300, check=False)
    out = (got.stdout or "") + (got.stderr or "")
    # A NON-ZERO EXIT MEANS NOTHING STARTED -- 2 for bad arguments, 1 for a
    # failed preflight. Everything after the launch (the chapter lock
    # included) is reported in `run.json`, not here.
    if got.returncode != 0:
        return {"launched": False, "exit": got.returncode,
                "output": out.strip()[-1500:]}
    found = RUN_LINE.search(out)
    if not found:
        return {"launched": False, "error": "no run id in the launch output",
                "output": out.strip()[-1500:]}
    run_id = found.group(1)
    session.launched.append(run_id)
    return {"launched": True, "run": run_id, "chapter": chapter,
            "note": "Running in the background. Call `wait` for what it does next."}


def _ask(session, chapter, question, why, pool=None, ceiling=None):
    return _launch(session, [
        sys.executable, "-m", "nb", "ask", session.notebook.root.name,
        "--chapter", str(chapter), str(question), "--why", str(why),
        "--quiet"], chapter, pool, ceiling)


def _reconstruct(session, chapter, why="", pool=None, ceiling=None):
    argv = [sys.executable, "-m", "nb", "reconstruct",
            session.notebook.root.name, "--chapter", str(chapter), "--quiet"]
    # `--why` OVERRIDES a standing reason, so passing an empty one would
    # replace a good sentence with nothing. Only send it when there is one.
    if str(why).strip():
        argv += ["--why", str(why)]
    return _launch(session, argv, chapter, pool, ceiling)


def _question_payload(run_id, state, q):
    due = listen._deadline(q)
    left = None if due is None else max(0.0, due - time.time())
    return {"event": "asks", "run": run_id,
            "chapter": state.get("chapter"),
            "kind": q.get("kind"), "name": q.get("name"),
            "prompt": q.get("prompt"), "why": q.get("why"),
            "how": q.get("how"), "options": q.get("options"),
            "seconds_left": None if left is None else round(left),
            "then": ("takes its default" if q.get("default") is not None
                     else "the run stops, question on disk")}


def _wait(session, timeout_s=None):
    nb = session.notebook
    # STANDING QUESTIONS FIRST, and this is the refusal the docstring explains.
    # Blocking here would return instantly (listen re-reports them by design)
    # and the model would wait again -- a spin that burns a turn a second.
    standing = []
    for d in nb.runs():
        if coordinator.is_coordinator(d.name):
            continue
        q = mailbox.pending(d)
        if q and runstate.alive(d) is not False \
                and session.seen(d.name, q.get("asked_at")):
            standing.append(_question_payload(d.name, runstate.read(d), q))
    if standing:
        return {"refused": ("you have already been told about these questions "
                            "and nothing will change until you act. Answer, "
                            "stop or resume each one, then wait again."),
                "standing": standing}

    state = coordinator.touch(nb)
    since = float(state.get("listened_at") or time.time())
    span = float(timeout_s or WAIT_TIMEOUT)
    began = time.time()
    deadline = began + span
    was_alive = set()
    while True:
        scan_at, events = listen.scan(nb, since, was_alive)
        fresh = [e for e in events
                 if not (e[0] == "asks"
                         and session.seen(e[1].name, (e[3] or {}).get("asked_at")))
                 and not (e[0] == "died" and e[1].name in session.reported_dead)]
        # The human half. `reply` CONSUMES the answer, so it is called once per
        # pass and only when there is a question outstanding to consume.
        human = None
        if state.get("waiting_on"):
            got = coordinator.reply(nb)
            if got is not None:
                human = {"event": "user_answered",
                         "name": state.get("waiting_on"), "value": got}
        if fresh or human:
            coordinator.touch(nb, listened_at=scan_at)
            out = []
            for kind, d, st, q in fresh:
                if kind == "asks":
                    session.mark(d.name, (q or {}).get("asked_at"))
                    out.append(_question_payload(d.name, st, q))
                elif kind == "ends":
                    out.append({"event": "ends", "run": d.name,
                                "chapter": st.get("chapter"),
                                "outcome": st.get("outcome"),
                                "answer": st.get("answer")})
                else:
                    session.reported_dead.add(d.name)
                    out.append({"event": "died", "run": d.name,
                                "chapter": st.get("chapter"),
                                "turn": st.get("turn"),
                                "stem": st.get("stem"),
                                "note": ("no outcome. `resume` picks it up if "
                                         "`stem` is set; if it is null nothing "
                                         "is on disk and `clean` drops it.")})
            if human:
                out.append(human)
            return {"events": out}
        if time.time() >= deadline:
            coordinator.touch(nb, listened_at=scan_at)
            return {"events": [], "waited_s": round(time.time() - began),
                    "note": "nothing happened. Wait again, or finish."}
        time.sleep(POLL)


def _answer(session, run, value, by="coordinator"):
    nb = session.notebook
    d = _runs_dir(nb, run)
    q = mailbox.pending(d)
    if not q:
        return {"error": f"run {run} is not waiting for an answer."}
    if not coordinator.is_coordinator(run) and runstate.alive(d) is False:
        return {"error": f"run {run} is not running -- its question outlived "
                         f"it. Nothing would read the answer."}
    mailbox.answer(Notebook(nb.root, run_id=run), str(value),
                   by=(by or "coordinator"), replying_to=q.get("asked_at"))
    session.acted(run)
    return {"answered": q.get("name"), "run": run, "value": str(value),
            "by": by or "coordinator"}


def _read_run(session, run):
    d = _runs_dir(session.notebook, run)
    state = runstate.read(d)
    if not state:
        return {"error": f"no run {run} in this notebook."}
    keep = ("run", "chapter", "question", "outcome", "answer", "prose",
            "findings", "failure", "answered", "committed", "turn", "stem")
    return {k: state[k] for k in keep if k in state}


def _board(session):
    """
    The runs, plus your own outstanding escalation -- kept apart deliberately.

    `board._runs` enumerates `runs/` and the coordinator's reserved id lives
    there too, so it arrives in the same list as the real runs. Left there it
    reads as a run with no chapter that is never alive, which is exactly the
    row a model would try to `answer`. It is not a run; it is the question YOU
    asked the user, so it belongs in its own field.
    """
    from ..cli import board as board_mod
    out, escalation = [], None
    for st in board_mod._runs(session.notebook):
        q = st.get("question")
        if coordinator.is_coordinator(st.get("run")):
            if q:
                escalation = {"name": q.get("name"), "prompt": q.get("prompt"),
                              "asked_at": q.get("asked_at")}
            continue
        out.append({"run": st.get("run"), "chapter": st.get("chapter"),
                    "alive": st.get("alive"), "outcome": st.get("outcome"),
                    "asked": st.get("asked"), "answer": st.get("answer"),
                    "waiting_on": (q or {}).get("name")})
    busy = sorted({r["chapter"] for r in out if r["alive"] and r["chapter"]})
    return {"runs": out, "chapters_busy": busy,
            "your_escalation_awaiting_user": escalation}


def _manifest(session):
    from ..domain import manifest
    return {"manifest": manifest.build(session.notebook)}


def _note(session, text):
    got = coordinator.note(session.notebook, text)
    return {"noted": got} if got else {"error": "empty note"}


def _escalate(session, name, prompt, why=""):
    q = coordinator.post(session.notebook, name, prompt=prompt, why=why)
    return {"escalated": name, "asked_at": q["asked_at"],
            "note": "On the board. The answer arrives through `wait`."}


def _stop(session, run, why=""):
    nb = session.notebook
    runstate.request_stop(Notebook(nb.root, run_id=run), why=why,
                          by="coordinator")
    session.acted(run)
    return {"stopping": run, "why": why}


def _settled(session, run):
    """
    This death has been dealt with -- stop reporting it.

    NOT `acted()`, which is the opposite: that clears `reported_dead` so the
    next `wait` reports the run again, which is right after `answer` (the
    question is gone, a new one should block) and exactly wrong here. Both
    `clean` and `resume` can legitimately FAIL -- a dirty chapter, a null
    `stem` -- and neither failure is something the model can fix. Re-arming
    the report on failure puts `wait` straight back into the instant-return
    loop the suppression exists to prevent.
    """
    session.reported.pop(run, None)
    session.reported_dead.add(run)


def _resume(session, run):
    got = _nb_cmd(session, ["resume", str(run)])
    _settled(session, run)
    got["note"] = ("Resumed in the background if it had work on disk. `wait` "
                   "for what it does next.")
    return got


def _clean(session, run):
    got = _nb_cmd(session, ["clean", str(run), "--yes"], timeout=120)
    # SETTLED EITHER WAY. `nb clean` refuses a run whose chapter is dirty, and
    # that refusal is not something the model can fix -- committing is not its
    # job.
    _settled(session, run)
    return got


def _finish(session, summary):
    nb = session.notebook
    live = [r for r in session.launched
            if runstate.alive(_runs_dir(nb, r)) is not False
            and not runstate.read(_runs_dir(nb, r)).get("outcome")]
    if live:
        return {"refused": ("these runs are still going. Walking away leaves "
                            "their questions unanswered and they default "
                            "silently -- `wait` for them, or `stop` them."),
                "live": live}
    coordinator.note(nb, summary, kind="note")
    session.finished = True
    # KEPT, because the board is not the only reader. Whoever typed
    # `nb coordinate` is sitting at a terminal waiting for the session to end,
    # and a summary that goes only to the board makes them open the board to
    # find out what just happened in front of them.
    session.summary = summary
    return {"finished": True, "summary": summary,
            "note": "Session over. Stop calling tools now."}


def _direction(session, text):
    """
    Record the direction -- buffering it when there is no notebook yet.

    NOT GUARDED, unlike everything else that needs a notebook, because the
    model is RIGHT to call this first and the doctrine tells it to. Observed
    live twice: setting an aircraft up, turn 1 was `direction`, and refusing
    it spent a turn teaching the model that the one thing it was told to do
    first cannot be done. Setup is the case where the programme's reason
    genuinely precedes the place that stores it, so it is held and `adopt`
    writes it -- the same shape as `source`.
    """
    if session.notebook is None:
        session.direction = " ".join(str(text).split())
        return {"direction": session.direction,
                "note": "held until `new` creates the notebook, then pinned."}
    return {"direction": coordinator.direction(session.notebook, text)}


def _scaffolded(notebook):
    """
    True when `nb new` has actually run here.

    `Notebook()` only requires a `chapters/` directory, which `nb designer`
    creates to give the board somewhere to live before the aircraft exists.
    `_notebook.py` is the file `new` copies in, and rule 11 holds it
    byte-identical to the scaffold, so its presence is the one unambiguous
    marker that a notebook is real.
    """
    return notebook is not None and (notebook.root / "_notebook.py").exists()


def _needs_notebook(session):
    if not _scaffolded(session.notebook):
        return {"error": "there is no notebook yet. Call `new` first -- and "
                         "research the aircraft before you do, because the "
                         "brief is what `new` takes and nothing overwrites it."}
    return None


def _new(session, chapter_title, defines, spec=(), assume=(), target=()):
    """
    Scaffold the aircraft and ADOPT it as this session's notebook.

    The adoption is the part that matters. `nb coordinate` on a directory that
    does not exist yet runs with `session.notebook is None`, because the
    research that fills `--spec` has to happen before the directory exists --
    so this is the moment the session acquires the thing every other tool
    needs.
    """
    import contextlib
    import io
    import shutil

    from ..cli import new as new_mod

    # SCAFFOLDED, not merely addressable. This tested `session.notebook is
    # not None`, which was right when the only way in was `nb coordinate` on a
    # directory that did not exist -- and wrong the moment `nb designer`
    # arrived, because that creates `chapters/` to host the board BEFORE any
    # aircraft exists, and `Notebook()` accepts any root with a `chapters/`.
    #
    # Measured on ft-warthog: the session opened with a notebook object over an
    # empty skeleton, `new` refused with "one aircraft", the manifest was empty
    # so there was no chapter name either, and the coordinator escalated to the
    # user from a dead end it could not get out of. `_notebook.py` is what
    # `nb new` actually produces (`cli/new.py::COPIED_VERBATIM`), so it is the
    # honest test for "has this been scaffolded".
    if session.notebook is not None and _scaffolded(session.notebook):
        return {"error": f"this session already holds "
                         f"{session.notebook.root.name}. One aircraft."}
    # THE DIRECTORY IS NOT THE MODEL'S TO CHOOSE. It was `directory`, a tool
    # argument, and the model duly chose its own: launched as `nb coordinate
    # little-piggy`, it created `ft-little-piggy`. The user named the notebook
    # when they started the session -- a second name supplied here could only
    # ever disagree with the one on the command line, which is the same
    # argument `cli/new.py` makes for deriving the title from the directory
    # rather than taking it twice.
    directory = session.wanted
    if not directory:
        return {"error": "this session has no directory to create."}

    existed = pathlib.Path(directory).exists()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = new_mod.main(str(directory), chapter_title=str(chapter_title),
                            defines=str(defines), specs=list(spec or ()),
                            assumes=list(assume or ()),
                            targets=list(target or ()))
    text = out.getvalue().strip()
    if code != 0:
        # CLEAN UP A HALF-BUILT SCAFFOLD, because the name is now fixed.
        # `nb new` returns non-zero when the scaffold does not lint, preflight
        # AND render -- all of which happen after the directory is created --
        # so a failure leaves it behind, and the next attempt at the same name
        # is refused with "exists and is not empty". Observed live: the first
        # `new` failed that way, the model could not reuse the name, and it
        # invented `-2`. With the name pinned there is no `-2` to escape to,
        # so the failure has to be made retryable instead.
        #
        # Only what THIS call created: a directory that was already there is
        # somebody else's, and removing it is not a scaffolding failure's to do.
        if not existed:
            shutil.rmtree(directory, ignore_errors=True)
        session.new_failures += 1
        # DO NOT INVITE A RETRY THE MODEL CANNOT WIN. This used to end "fix
        # the brief and call `new` again with the same name", and a model
        # reading `exit: 1` with no diagnosis it could act on did exactly
        # that: measured on the FT A-10 Warthog, 49 of 80 turns were `new`,
        # failing identically every time, and the session hit its cap having
        # produced one file.
        #
        # The second failure is therefore terminal advice rather than
        # encouragement. `new` is not a tool whose output the model can debug
        # -- a non-zero exit here is a scaffold, a lint or a render problem in
        # `nb`, none of which a coordinator can reach.
        if session.new_failures >= 2:
            return {"created": False, "exit": code, "output": text[-2000:],
                    "refused": (
                        f"`new` has now failed {session.new_failures} times "
                        f"with the same error. It will not succeed on a "
                        f"third attempt: this is a fault in `nb`, not in your "
                        f"arguments, and nothing you can change from here "
                        f"fixes it. STOP CALLING IT. `escalate` the output "
                        f"below to the user and `wait`, or `finish` and say "
                        f"what you got as far as.")}
        return {"created": False, "exit": code, "output": text[-2000:],
                "note": ("Nothing was left behind. If the output above names "
                         "something in your arguments, fix it and try once "
                         "more; if it does not, escalate rather than "
                         "retrying — a second identical failure is a fault "
                         "in `nb`.")}
    session.adopt(Notebook(directory))
    return {"created": True, "notebook": session.notebook.root.name,
            "output": text[-1500:],
            "note": ("Scaffolded and rendered. Photographs next: search, "
                     "fetch, look, add_photo, mask, overlay, reference.")}


def _nb_cmd(session, args, timeout=1800):
    """One `nb` subcommand as a subprocess, for its TEXT report."""
    nb = session.notebook
    got = subprocess.run(
        [sys.executable, "-m", "nb", *args[:1], nb.root.name, *args[1:]],
        cwd=nb.repo, capture_output=True, text=True, timeout=timeout,
        check=False)
    return {"exit": got.returncode,
            "report": ((got.stdout or "") + (got.stderr or "")).strip()[-6000:]}


def _mask(session, names=()):
    return _nb_cmd(session, ["mask", *[str(n) for n in (names or ())]])


def _reference(session):
    got = _nb_cmd(session, ["reference"], timeout=300)
    got["clean"] = got["exit"] == 0
    return got


def _overlay(session, name):
    from ..tools import masks
    try:
        path = masks.overlay(session.notebook, str(name))
    except (SystemExit, OSError, ValueError) as exc:
        return {"error": f"{exc}"}
    return {"_image": pathlib.Path(path).read_bytes(),
            "mime_type": "image/png", "name": pathlib.Path(path).name}


def build(session):
    """(tools, handlers) -- one sorted list, one dispatch table."""
    def guarded(fn):
        """
        Refuse in words rather than raising, before a notebook exists.

        Applied to everything that touches one. Without it these reach
        `session.notebook.root` and raise AttributeError, which `loop.py`
        hands back as a tool error -- and it is explicit about what that does:
        "a model told its tool does not exist stops using it and starts
        looking for another. That is the shape of the worst run this system
        has had." A sentence naming `new` costs one turn; a confusing
        traceback costs the session.
        """
        def call(**kw):
            bad = _needs_notebook(session)
            return bad if bad else fn(**kw)
        return call

    handlers = {
        "direction": lambda text: _direction(session, text),
        "ask": guarded(lambda chapter, question, why, pool=None, ceiling=None:
                       _ask(session, chapter, question, why, pool, ceiling)),
        "wait": guarded(lambda timeout_s=None: _wait(session, timeout_s)),
        "answer": guarded(lambda run, value, by="coordinator":
                          _answer(session, run, value, by)),
        "read_run": guarded(lambda run: _read_run(session, run)),
        "board": guarded(lambda: _board(session)),
        "manifest": guarded(lambda: _manifest(session)),
        "note": guarded(lambda text: _note(session, text)),
        "escalate": guarded(lambda name, prompt, why="":
                            _escalate(session, name, prompt, why)),
        "stop": guarded(lambda run, why="": _stop(session, run, why)),
        "resume": guarded(lambda run: _resume(session, run)),
        "clean": guarded(lambda run: _clean(session, run)),
        "finish": guarded(lambda summary: _finish(session, summary)),

        # Setup and research. `new` is the one that may run without a
        # notebook; `fetch`, `read_image` and `read_plan_page` work before one
        # exists because that is when the research happens.
        "new": lambda chapter_title, defines, spec=(), assume=(), target=():
            _new(session, chapter_title, defines, spec, assume, target),
        "fetch": lambda url: research.fetch(session, url),
        "read_image": lambda file: research.read_image(session, file),
        "read_plan_page": lambda file, page=1, dpi=150: research.read_plan_page(
            session, file, page, dpi),
        "source": lambda url, text: research.source(session, url, text),
        "add_photo": guarded(lambda name, file, description:
                             research.add_photo(session, name, file, description)),
        "mask": guarded(lambda names=(): _mask(session, names)),
        "reference": guarded(lambda: _reference(session)),
        "overlay": guarded(lambda name: _overlay(session, name)),
        "reconstruct": guarded(lambda chapter, why="", pool=None, ceiling=None:
                               _reconstruct(session, chapter, why, pool, ceiling)),
    }
    decls = sorted(declarations(), key=lambda d: d.name)
    # `search` IS SERVER-SIDE and has no handler, so it is declared here and
    # excluded from the parity check below rather than faked with a stub that
    # could never be called.
    missing = ({d.name for d in decls} - {"search"}) ^ set(handlers)
    if missing:                                   # pragma: no cover
        raise SystemExit(f"coordinator tools out of step: {sorted(missing)}")
    native = [d for d in decls if d.name != "search"]
    return ([types.Tool(function_declarations=native),
             types.Tool(google_search=types.GoogleSearch())], handlers)

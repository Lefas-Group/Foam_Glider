"""
Noticing that a run has stopped getting anywhere.

`MAX_TURNS` is a deadline, not a detector: it converts "stuck" into "dead"
dozens of turns late, and with several agents running detached nobody is reading
any one transcript, so a wedged run is invisible by construction. That is not a
terminal-versus-web problem -- it is that attention is the resource the whole
parallel design is spending, so something automated has to be watching.

WHAT THE SIGNAL IS
------------------
The obvious rule -- "the same tool call N times running" -- catches nothing.
Measured against the run this module exists because of, no two of its 28 calls
were identical:

    check.py · find . -name check.py · list_directory . · git status
    ls -la glider-notebook/check.py · git ls-files | grep check.py · git log
    tools/check.py · bin/check.py · scripts/check.py · search_files **/*check.py

It was being inventive, energetically, in a closed room. Varying inputs are the
NORMAL shape of a stuck agent, because that variation is what makes it feel like
progress from the inside.

Hashing outputs instead was the next idea and is also wrong here: those calls
failed with the attempted path IN the error, so the bytes differed every time.
(It would also have to normalise the way `freezediff` does, since two renders of
identical code never match -- `footer()`'s runtime line sees to that.)

What actually separates the two cases is much simpler: **did anything happen?**
A run that has neither written a file nor learned anything new for eight turns
is stuck, however varied its reading has been.

THE NUMBER
----------
Calibrated, not guessed -- the same discipline the lint rules are held to, for
the same reason: a false positive interrupts a working run, and you only need a
few before you stop reading the interruptions.

Longest run of consecutive turns with no productive call, across every
transcript on disk:

    stuck run (the one that died on max turns)        26
    healthy: 3 runs                                    4, 2, 0

Eight sits at twice the observed healthy maximum and a third of the pathological
one. The corpus is four runs and short, so this will want revisiting once there
are more -- widen it if a real run is ever interrupted, and record why.

WHAT IT DOES NOT CATCH
----------------------
A run that edits a file every single turn and still goes nowhere. That is
`MAX_TURNS`'s job and the reason it stays: this detector answers "is it making
progress?", the turn cap answers "is it worth continuing?", and those come apart
for an agent that improves something measurably every turn but would need two
hundred turns to finish.
"""

# A call that changes the world or brings back something new. Reading, listing,
# searching and shelling are how an agent ORIENTS -- all legitimate, none of them
# evidence that the run is advancing. `lint` and `render` are deliberately absent
# for the same reason: re-linting unchanged source is the loop, not the exit.
#
# AND IT MUST HAVE WORKED. `loop.py` turns every handler exception into
# `{"error": ...}` and hands it straight back, so a tool that fails persistently
# -- a schema the model cannot satisfy, a bug in a verifier -- is called every
# turn, resets the counter every turn, and burns the whole cap. A call that
# errored produced nothing; counting it as progress is how a detector goes blind
# to exactly the failure it was built for, wearing a different tool's name.
# NOTE `create_chapter` is deliberately absent: it is not a tool. Chapter
# creation goes through `open_chapter`, which calls the handler directly, so a
# name here that no model can emit is a line that looks like coverage and is
# not -- see `tools/__init__.py`.
PRODUCTIVE = frozenset({
    "write_file", "edit_file",                       # the entry moved
    "probe",                                         # something was measured
    "fork_chapter", "declare_input", "open_entry",   # the run advanced
    "ask_specified",
    "declare_refactor",                              # a commitment was made
})

BARREN_LIMIT = 8


def failed(out):
    """
    Did this tool call come back empty-handed?

    Three shapes, because three layers produce them: the loop's catch-all wraps
    an exception as {"error": ...}; a tool can answer with one itself; and
    A refused tool answers with a plain "rejected:" string rather
    than raising, since that is guidance rather than a fault.
    """
    if isinstance(out, dict):
        return "error" in out
    text = str(out or "")
    return text.startswith("rejected:") or text.startswith("error:")


class Stuck:
    """What the detector saw. Carries its own evidence so the question can."""

    def __init__(self, turns, calls):
        self.turns = turns
        self.calls = calls

    def summary(self):
        counts = {}
        for name, _ in self.calls:
            counts[name] = counts.get(name, 0) + 1
        return ", ".join(f"{n}×{c}" for n, c in
                         sorted(counts.items(), key=lambda kv: -kv[1]))

    def evidence(self, keep=4):
        """The last few calls, verbatim enough to recognise the rut."""
        return [f"{n}({a})" if a else n for n, a in self.calls[-keep:]]

    def __str__(self):
        return (f"no progress in {self.turns} turns — {self.summary()}; "
                f"last: {' · '.join(self.evidence())}")


def _arg_summary(call, width=60):
    args = dict(getattr(call, "args", None) or {})
    for key in ("command", "path", "pattern", "chapter", "name", "question"):
        if key in args:
            return str(args[key])[:width]
    return ", ".join(f"{k}={str(v)[:20]}" for k, v in list(args.items())[:2])


class Detector:
    """
    One per run. `turn()` is handed each turn's calls and answers with a `Stuck`
    the first time the streak reaches the limit.

    It resets on firing, not only on progress: a run that is allowed to continue
    gets another full `limit` turns before it is interrupted again. Asking the
    same question every turn from turn 8 to turn 60 would be its own kind of
    broken.
    """

    def __init__(self, limit=BARREN_LIMIT):
        self.limit = limit
        self.barren = 0
        self.calls = []

    def turn(self, results):
        """
        `results` is [(call, output)] for the turn, in call order.

        Progress is one productive call that did NOT come back an error. An
        errored call still goes into the evidence, because "open_entry failed eight
        times" is precisely what the person answering needs to see.
        """
        advanced = any(c.name in PRODUCTIVE and not failed(out)
                       for c, out in results)
        if not results or advanced:
            self.barren = 0
            self.calls = []
            return None
        self.barren += 1
        self.calls.extend(
            (c.name + (" !" if failed(out) else ""), _arg_summary(c))
            for c, out in results)
        if self.barren < self.limit:
            return None
        found = Stuck(self.barren, list(self.calls))
        self.barren = 0
        self.calls = []
        return found


# How long to hold a run while asking whether it is really stuck. Short on
# purpose: unlike a budget, this question has a safe answer, so silence should
# cost five minutes rather than an hour. A detached run with nobody watching
# carries on; a person at the board gets a real chance to stop it.
ASK_WAIT = 300.0


def escalate(found, phase, asker):
    """
    Put the detector's finding to whoever is at the gate, and turn the reply
    into something the model can act on.

    `asker(why, options, default)` does the routing -- mailbox when detached,
    terminal when not -- so this function knows nothing about either.

    Returns the text to inject as a user turn, or raises SystemExit to end the
    run. Injecting rather than merely logging is the point: the model cannot see
    its own rut -- from the inside every one of those turns was a fresh idea --
    and an outside view stated plainly is the one thing it is missing.
    """
    reply = (asker(
        why=(f"{found.turns} turns without writing anything or measuring "
             f"anything: {found.summary()}\n  last: "
             f"{' · '.join(found.evidence())}"),
        options="continue (default) · stop · or type advice to pass to the agent",
        default="continue") or "continue").strip()

    if reply.lower() in ("stop", "kill", "abort"):
        raise SystemExit(
            f"\n  stopped: {found}\n"
            f"  The {phase} phase was told to stop rather than continue.")

    note = ("" if reply.lower() in ("continue", "carry on", "yes", "")
            else f"\n\nFrom the person watching this run: {reply}")
    return (
        f"STOP. You have spent {found.turns} turns without writing anything or "
        f"measuring anything: {found.summary()}. From inside, each of those felt "
        f"like a new idea; from outside they are one idea repeated.\n\n"
        f"Most often this means you are looking for something that is not there, "
        f"or re-running a check that cannot change until you change something "
        f"first. Do not try another variation of the same thing.\n\n"
        f"Say in one line what you are actually blocked on, then either act on "
        f"what you already know or end the phase and report it."
        f"{note}")

"""
The tool registry.

Sorted, because MCP servers do not guarantee stable tool ordering across restarts
and tools render at prefix position 0 -- an unsorted merge silently breaks the
byte-prefix match that caching depends on, every time the server comes up in a
different order.

ONE LIST, because there is one conversation. It was per-phase, and the reason
was `propose`: 6,676 of 15,053 characters -- 44% of the whole tool surface --
which was dead weight on every write turn, so `PHASE_OMITS` existed to stop
paying for it twice. `propose` is gone and so is the mechanism that worked
around it. Filtering the list mid-run was never free anyway: tools render at
prefix position 0, so a list that changes at a transition invalidates the cached
prefix from that point, and at a measured 67% implicit hit rate that is re-paying
full rate for the whole accumulated history to save a few hundred tokens.

**`request_refactor` is gone.** It asked the model to predict that it needed a
refactor and declare it, after a `_model.py` write was refused -- and it was
never once called in 75 recorded runs, because the guard it hung off has never
fired. `guards.py` now SEES the refactor happen and asks on the model's behalf,
at the moment the body moves, so there is nothing left to predict. The same
correction `render_cost_s` got: stop asking, start measuring.

`check` has no declaration AND its handler refuses. A full chapter check
re-solves every entry, which is minutes inside a loop -- measured, one run
called it five times through `bash` and spent thirteen of its twenty-seven
minutes learning what the phase was about to tell it anyway.

The handler used to run it, on the reasoning that "a model that somehow names it
gets a real answer rather than a KeyError". That was borrowed from `loop.py`,
where the hazard is telling a model that a tool it SHOULD use does not exist.
`check` is one it should never use, so the borrowed argument pointed the wrong
way -- and `references/refactoring.md` had been telling the model "there is no
`check` tool" while the handler sat wired and callable. One of those had to
become true.

It REFUSES rather than being deleted, because a bare "no such tool" teaches
nothing: `loop.py` has the failure that comes of a model looking for another
tool when one is denied. The refusal says what the phase does instead. Nothing
internal is affected -- the refactor gate calls `verifiers.check` directly.

**`bash` is gone, and it is not coming back as a convenience.** It was an
allowlisted escape hatch and became the fourth most-used tool: 37 calls across
8 runs. Replayed against the allowlist as it stood at the end, 17 would still
have run, and every category of those had a better-instrumented equivalent --
`uv run python` is `probe` without the chapter loaded, the solve budget armed,
a wall-clock grant or a watchdog; `grep`/`ls`/`cat` are the file tools without
path confinement in a separate process; and `uv run quarto render`, four of the
seventeen, is `render` WITHOUT THE RENDER LOCK OR THE DEADLINE -- which is the
one cross-run mutual-exclusion mechanism in the system, and a race there
presents as a bug in an entry that is correct.

It was never a security boundary and never claimed to be: `probe` runs
arbitrary Python by design, so removing this changes nothing about what a run
CAN do -- only about what it can do UNINSTRUMENTED. The cwd was its own
footgun: `bash` ran in the repo root while the file tools are relative to
`<notebook>/chapters/`, so `rm chapters/test*.py` silently removed nothing and
left three scratch files behind.

What is genuinely lost is `git status` and `git diff` -- 3 of the 37. The
record is append-only and the refactor gate already prints the diff of exactly
the functions that moved, so this is not being replaced on anticipation. If a
run stalls for want of it, `git_diff(path)` is a two-line tool to add then.

**`create_chapter` is deliberately NOT here.** `open_chapter` is a declaration
of intent that the system acts on, and the system does the creating. A
`create_chapter` tool could only ever return `rejected: already exists`, and it
made ownership ambiguous on the one path that is structurally irreversible -- an
entry is a `git revert`, a chapter is something later entries build on.

**The three new declarations are POINTERS, not doctrine.** Weighed, `propose`
was mostly not a schema: `figures` (239 tok), `route` (186), `forked_from` (157)
and `title` (134) were 57% of all its field descriptions, and all four restated
things already in `system_instruction.md`, which is shared and cached once.
There is a second reason beyond tokens: duplicated doctrine drifts and nothing
catches it -- `route`'s description still described the OLD fork criterion long
after `references/forking.md` had changed. A pointer cannot go stale.
"""

from google.genai import types

from . import api, figures, guards, interact, probe, refs, verifiers


def _decl(name, description, properties=None, required=()):
    schema = {"type": "object",
              "properties": properties or {},
              "required": list(required)}
    return types.FunctionDeclaration(
        name=name, description=description, parameters_json_schema=schema)


S = {"type": "string"}
N = {"type": "number"}
B = {"type": "boolean"}


def native_declarations():
    return [
        _decl("probe",
              "Run a question against the chapter's model in the scratch sandbox. "
              "Pass PYTHON, not prose: the chapter is already imported and the "
              "solve budget is already armed, so write only the question itself. "
              "Returns stdout and any traceback. Call aero_report() at the end to "
              "record what the solves cost.",
              {"question": dict(S, description="Python. The chapter's names are "
                                               "in scope; do not import it."),
               "chapter": dict(S, description="Chapter directory name"),
               "budget_s": dict(N, description=(
                   "Seconds of wall clock this probe may take, drawn from the "
                   "run's pool. Budget it: a single solve wants tens, a "
                   "multistart hundreds. Enforced to about 15 s, so anything "
                   "under ~20 buys nothing over 20. Asking for more than "
                   "remains grants what remains, and the result says how much "
                   "is left. Omitted takes the whole remaining pool, which "
                   "wastes it."))},
              ["question", "chapter", "budget_s"]),

        _decl("lint",
              "Run the lint contract over a chapter without rendering. Returns "
              "the violations verbatim; each message names its own fix. The "
              "rules are listed in your instructions -- this reports which of "
              "them this chapter breaks.",
              {"chapter": S}, ["chapter"]),

        _decl("render",
              "quarto render. Target the ONE entry you are iterating on. A "
              "target is not a filter over the freeze -- quarto honours the "
              "freeze on a whole-notebook render ONLY, so naming a CHAPTER "
              "re-executes every page in it, which is usually slower than "
              "rendering the whole notebook. Measured: `render "
              "chapters/01-foam-glider` ran 5 pages in 110 s; `render` with no "
              "target ran none, all cached.",
              {"target": dict(S, description=(
                  "Path relative to the notebook root. One .qmd while "
                  "iterating; empty for the whole notebook. A chapter "
                  "directory is almost never what you want"))}),

        _decl("api_search",
              "Search the INSTALLED AeroSandbox by name and full docstring, "
              "across functions, classes and methods. Ask this before writing any "
              "geometry or aerodynamic calculation: areas, spans, aspect ratios, "
              "chords, volumes, wetted areas, stability derivatives and neutral "
              "points all exist already.",
              {"query": S, "kind": dict(S, enum=["all", "function", "class", "method"])},
              ["query"]),

        _decl("api_list",
              "Browse the installed AeroSandbox by AREA, when you do not yet "
              "know the name to search for. With no `area` it returns the "
              "index -- every area with a count -- and naming one returns the "
              "paths, summaries and constructor parameters in it. Use it "
              "BEFORE writing anything geometric or aerodynamic: 46 classes "
              "and 291 functions already exist.",
              {"kind": dict(S, enum=["classes", "functions"]),
               "area": dict(S, description=(
                   "e.g. geometry, aerodynamics, dynamics, weights, "
                   "structures, atmosphere, numpy, library/aerodynamics. "
                   "Omit for the index"))},
              ["kind"]),

        _decl("api_signature",
              "Signature and docstring for a dotted path; set methods=true for "
              "every method of a class.",
              {"path": dict(S, description="e.g. aerosandbox.Airplane"), "methods": B},
              ["path"]),

        _decl("read_reference",
              "Read one reference document.\n" + refs.describe(),
              {"name": dict(S, enum=refs.names())}, ["name"]),

        _decl("read_figure",
              "A rendered figure as an image, so prose can be checked against "
              "what actually rendered rather than against the conversation.",
              {"chapter": S, "stem": dict(S, description="Entry stem, no .qmd"),
               "name": dict(S, description="PNG filename; omit for the first")},
              ["chapter", "stem"]),

        _decl("ask_specified",
              "Ask the user for a Specified input -- one where a different answer "
              "changes WHAT WE ARE BUILDING, not how accurately we modelled it. "
              "Ask the moment you find one; do not save it for the end, and "
              "never sweep a range instead of asking. Blocks until they answer.",
              {"name": dict(S, description="The quantity, e.g. 'static margin'"),
               "why": dict(S, description="Why it changes what we are building "
                                          "-- TEN WORDS at most, rule 8"),
               "kind": dict(S, enum=["specified", "unknown", "derivable"],
                            description="Classify it before asking. Only "
                                        "'specified' may be asked: 'derivable' "
                                        "you compute, 'unknown' you assume and "
                                        "flag."),
               "options": dict(S, description="Plausible values, if that helps"),
               "replaces": dict(S, description=(
                   "The id of an item this chapter ALREADY declares, when your "
                   "question changes it rather than adding something new. The "
                   "ids are listed after your first probe and in the chapter "
                   "context above. Naming it puts the value in force into the "
                   "question, which is what the user needs to answer it."))},
              ["name", "why", "kind"]),

        _decl("fork_chapter",
              "This question needs a chapter that does not exist yet. The "
              "parent is the chapter you are already in -- you do not name it. "
              "STOPS THE RUN for the user's approval, then scaffolds the "
              "chapter and copies the parent's _model.py for you. The test for "
              "needing one is whether `_model.py` would differ from the one in "
              "front of you -- see the Scope section of your instructions. Do "
              "not call it for a new objective, different bounds, a finer "
              "sweep or any new measurement of the same aircraft.",
              {"name": dict(S, description=(
                  "Directory name for the new chapter, NN-kebab-case. The "
                  "number is reallocated if it clashes")),
               "title": dict(S, description=(
                   "The CHAPTER's name, two or three words in the style of "
                   "'Flight path' — not this question")),
               "defines": dict(S, description=(
                   "What defines it: the aero method, the section, what is "
                   "left out. It goes in index.qmd and is the one place those "
                   "are stated"))},
              ["name", "title", "defines"]),

        _decl("declare_input",
              "Record one input this question needed that was not already "
              "fixed. Call it the MOMENT you assume or decide something, not "
              "at the end: four of eight recorded runs finished having declared "
              "nothing at all. Declaring the same quantity twice corrects it.",
              {"name": dict(S, description="The quantity, e.g. 'static margin'"),
               "value": dict(S, description="The value used"),
               "source": dict(S, enum=["asked", "decided", "guessed"],
                              description=(
                   "asked: a different answer changes WHAT WE ARE BUILDING and "
                   "you put it through ask_specified. decided: you asked, they "
                   "handed it back, and you chose. guessed: nobody knows, a "
                   "different answer changes HOW ACCURATELY it is modelled. If "
                   "the model or the plans already contain it, it is none of "
                   "these: compute it")),
               "why": dict(S, description="TEN WORDS at most -- rule 8 counts them")},
              ["name", "source", "why"]),

        _decl("open_entry",
              "Probing is over: this is the question the entry answers. Puts "
              "your assumptions to the user, allocates the filename and hands "
              "back the instructions for writing. Call it once the question is "
              "answered -- not before, and not with a second question folded "
              "in. ONE question, one entry.",
              {"title": dict(S, description=(
                  "The question THIS entry answers: ONE question ending in "
                  "'?', 18 words at most (rule 26), about eight is right. "
                  "REPHRASE the ask -- strip what holds for the whole chapter. "
                  "It becomes the title, the sidebar text and the filename")),
               "inputs_none_because": dict(S, description=(
                   "ONLY when you have declared no inputs at all: one line "
                   "saying why. Inheriting everything the chapter declares is "
                   "a perfectly good reason; say so. An empty list with no "
                   "claim is refused"))},
              ["title"]),
        _decl("declare_refactor",
              "Say why you changed a function that was already in _model.py "
              "or _analysis.py. This is the PROCEDURE for editing shared code, "
              "not a reason to avoid it: _analysis.py is yours to improve, "
              "adding a function needs nothing at all, and editing one needs "
              "only this one line. It is shown to the user beside the diff "
              "when the chapter is re-proved. Copying logic into your entry to "
              "avoid calling this leaves every later entry to copy it again.",
              {"function": dict(S, description="The function you changed"),
               "why": dict(S, description=(
                   "What changed and why, in one line"))},
              ("function", "why")),
    ]


def build(session, fs):
    """(tools, handlers) -- one sorted list, one dispatch table."""
    nb = session.notebook
    decls = sorted(native_declarations() + fs.declarations(),
                   key=lambda d: d.name)

    handlers = dict(fs.handlers())
    handlers.update({
        "probe": lambda question, chapter=None, budget_s=None: probe.run_probe(
            nb, chapter or session.chapter, question, session, budget_s),
        "lint": lambda chapter: verifiers.lint_chapter(nb, chapter, session),
        "render": lambda target="": verifiers.render(
            nb, target, why="the agent asked", session=session),
        "check": lambda chapter="", force_all=False: {"error": (
            "refused: re-proving a chapter is the run's job, not a turn's. It "
            "deletes the freeze and re-solves every entry that reaches what you "
            "changed -- minutes -- and the run does it once, automatically, "
            "after lint passes and the entry builds, then shows you every "
            "answer that moved and names the figures whose bytes changed. "
            "There is nothing here for you to run. Carry on with the entry.")},
        "api_search": lambda query, kind="all": api.api_search(query, kind),
        "api_list": lambda kind, area="": api.api_list(kind, area),
        "api_signature": lambda path, methods=False: api.api_signature(path, methods),
        "read_reference": lambda name: refs.read_reference(name),
        "read_figure": lambda chapter, stem, name="": figures.read_figure(
            nb, chapter, stem, name),
        "ask_specified": lambda name, why, kind="specified", options="",
                                replaces="": (
            interact.ask_specified(session, name, why, kind, options, replaces)),
        "fork_chapter": lambda name, title, defines: (
            interact.fork_chapter(session, name, title, defines)),
        "declare_input": lambda name, source, why, value="": (
            interact.declare_input(session, name, value, source, why)),
        "open_entry": lambda title, inputs_none_because="": (
            interact.open_entry(session, title, inputs_none_because)),
        "declare_refactor": lambda function, why: interact.declare_refactor(
            session, function, why),
    })
    handlers = guards.wrap_writes(handlers, session)
    return [types.Tool(function_declarations=decls)], handlers

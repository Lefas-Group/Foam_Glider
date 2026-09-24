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

`check` has no declaration at all: a full chapter check re-solves every entry,
which is minutes inside a loop, and its own description told the model not to use
it. The handler remains -- the refactor gate runs it, and a model that somehow
names it gets a real answer rather than a KeyError.

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

from . import api, figures, guards, interact, probe, refs, shell, verifiers


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

        _decl("bash",
              "Run an allowlisted command: uv run quarto, uv run python, git "
              "status, git diff. The escape hatch, not the default path.\n"
              "IT RUNS IN THE REPO ROOT, which is the PARENT of the notebook -- "
              "not where the file tools write. A path you gave write_file is "
              "relative to <notebook>/chapters/, so the same string means a "
              "different file here: `rm chapters/x.py` from bash silently "
              "removes nothing, because the file is at "
              "<notebook>/chapters/x.py. Do not use this to run scratch code "
              "-- that is `probe`, which runs in the run directory with the "
              "chapter already loaded and writes nothing into the notebook.",
              {"command": S}, ["command"]),

        _decl("open_chapter",
              "Settle which chapter this question belongs to. FIRST -- no file "
              "may be written until it has run. An EXISTING chapter is opened "
              "and claimed. A NEW one stops the run for the user's approval, "
              "then is scaffolded for you, so `title` and `defines` are "
              "required for it. The test for needing one is whether `_model.py` "
              "would differ -- see the Scope section of your instructions.",
              {"chapter": dict(S, description=(
                  "Chapter directory name, e.g. '04-chosen-throw'. For a new "
                  "one, NN-kebab-case; the number is reallocated if it clashes")),
               "title": dict(S, description=(
                   "New chapters only. The CHAPTER's name, two or three words "
                   "in the style of 'Flight path' — not this question")),
               "defines": dict(S, description=(
                   "New chapters only. What defines the chapter: the aero "
                   "method, the section, what is left out. It goes in "
                   "index.qmd and is the one place those are stated")),
               "forked_from": dict(S, description=(
                   "New chapters only, and only when this vehicle is a COPY of "
                   "an existing one: the chapter directory it comes from. The "
                   "copy is made for you, from the last commit, with _fork.yml "
                   "written. Empty for a genuinely new aircraft"))},
              ["chapter"]),

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
        _decl("request_refactor",
              "Declare that this entry cannot be written without changing the "
              "chapter's _model.py, after a write to it was refused. ENDS THE "
              "RUN: every existing entry in the chapter would have to be "
              "re-solved to prove its answers did not move, and that is the "
              "user's call. Use it only when the vehicle is genuinely wrong or "
              "missing something the question needs -- not to restructure code "
              "you would rather have written differently.",
              {"chapter": S, "why": dict(S, description=(
                  "What must change and why the entry cannot be written "
                  "without it"))},
              ("chapter", "why")),
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
        "check": lambda chapter="", force_all=False: verifiers.check(
            nb, chapter, force_all),
        "api_search": lambda query, kind="all": api.api_search(query, kind),
        "api_signature": lambda path, methods=False: api.api_signature(path, methods),
        "read_reference": lambda name: refs.read_reference(name),
        "read_figure": lambda chapter, stem, name="": figures.read_figure(
            nb, chapter, stem, name),
        "ask_specified": lambda name, why, kind="specified", options="",
                                replaces="": (
            interact.ask_specified(session, name, why, kind, options, replaces)),
        "bash": lambda command: shell.bash(nb, command),
        "open_chapter": lambda chapter, title="", defines="", forked_from="": (
            interact.open_chapter(session, chapter, title, defines, forked_from)),
        "declare_input": lambda name, source, why, value="": (
            interact.declare_input(session, name, value, source, why)),
        "open_entry": lambda title, inputs_none_because="": (
            interact.open_entry(session, title, inputs_none_because)),
        "request_refactor": lambda chapter, why: interact.request_refactor(
            session, chapter, why),
        "declare_refactor": lambda function, why: interact.declare_refactor(
            session, function, why),
    })
    handlers = guards.wrap_writes(handlers, session)
    return [types.Tool(function_declarations=decls)], handlers

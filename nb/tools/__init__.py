"""
The tool registry.

Sorted, because MCP servers do not guarantee stable tool ordering across restarts
and tools render at prefix position 0 -- an unsorted merge silently breaks the
byte-prefix match that caching depends on, every time the server comes up in a
different order.

The list is now PER PHASE. It used to be shared so that both phases hit one
explicit cache object; with that cache deleted there is no such constraint, and
`propose` -- 1,014 tokens, the largest declaration by a wide margin, larger than
the next six combined -- was dead weight on every write turn. `check` is gone
from both: a full chapter check re-solves every entry, which is minutes inside a
loop, and its own description told the model not to use it. Both handlers remain;
only their declarations are conditional.

**`create_chapter` is deliberately NOT here.** Chapter creation is
proposal-driven: `write.py` scaffolds from the approved `chapter_title` and
`chapter_defines` BEFORE the model's first turn. Leaving it in the tool list gave
the agent a tool that could only ever return `rejected: already exists`, and made
ownership ambiguous on the one path that is structurally irreversible -- an entry
is a `git revert`, a chapter is something later entries build on. The handler
still exists; only `write.py` calls it.
"""

from google.genai import types

from . import api, figures, guards, interact, probe, refs, shell, verifiers
from ..schema import Proposal


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
              "Run the 26-rule lint contract over a chapter without rendering. "
              "Returns the violations verbatim; each message names its own fix.",
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

        _decl("check",
              "The full gate: lint, discard invalidated freezes, render, lint "
              "again, then diff rendered values and figures against git. Run this "
              "after changing _model.py or _analysis.py -- it is what proves the "
              "change moved nothing. SLOW and rarely what you want while "
              "iterating: it renders the WHOLE notebook (only freeze deletion is "
              "scoped by chapter), so on a notebook with expensive chapters it "
              "can cost many minutes. Use `render` on a single entry instead, and "
              "`lint` to check the rules.",
              {"chapter": S, "force_all": B}),

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
              "Ask the moment you find one; do not save it for the proposal, and "
              "never sweep a range instead of asking. Blocks until they answer.",
              {"name": dict(S, description="The quantity, e.g. 'static margin'"),
               "why": dict(S, description="Why it changes what we are building "
                                          "-- TEN WORDS at most, rule 8"),
               "kind": dict(S, enum=["specified", "unknown", "derivable"],
                            description="Classify it before asking. Only "
                                        "'specified' may be asked: 'derivable' "
                                        "you compute, 'unknown' you assume and "
                                        "flag."),
               "options": dict(S, description="Plausible values, if that helps")},
              ["name", "why", "kind"]),

        _decl("consult",
              "Ask the user for open-ended guidance -- not a Specified input and "
              "not a route decision. Use sparingly.",
              {"question": S, "why": S}, ["question", "why"]),

        _decl("bash",
              "Run an allowlisted command: uv run quarto, uv run python, "
              "git show/status/diff/log. The escape hatch, not the default path.",
              {"command": S}, ["command"]),

        types.FunctionDeclaration(
            name="propose",
            description=(
                "Propose the entry and END the run. Everything the write phase "
                "needs goes here: it does not get this conversation. Call it once "
                "the question is answered -- not before, and not with a second "
                "question folded in."),
            parameters_json_schema=Proposal.model_json_schema()),
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


# Declarations a phase does not need. The handler stays wired either way, so a
# model that somehow names one still gets a real answer rather than a KeyError.
PHASE_OMITS = {
    "write": ("propose",),      # the proposal is already approved and in the brief
    "ask": ("declare_refactor",),   # the probe phase writes no chapter files
}


def build(session, fs, phase=None):
    """(tools, handlers) -- one sorted list, one dispatch table."""
    nb = session.notebook
    omit = set(PHASE_OMITS.get(phase, ())) | {"check"}
    decls = sorted((d for d in native_declarations() + fs.declarations()
                    if d.name not in omit), key=lambda d: d.name)

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
        "ask_specified": lambda name, why, kind="specified", options="": (
            interact.ask_specified(session, name, why, kind, options)),
        "consult": lambda question, why: interact.consult(session, question, why),
        "bash": lambda command: shell.bash(nb, command),
        "propose": lambda **kw: interact.propose(session, **kw),
        "request_refactor": lambda chapter, why: interact.request_refactor(
            session, chapter, why),
        "declare_refactor": lambda function, why: interact.declare_refactor(
            session, function, why),
    })
    handlers = guards.wrap_writes(handlers, session)
    return [types.Tool(function_declarations=decls)], handlers

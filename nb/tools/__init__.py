"""
The tool registry.

One frozen, sorted list shared by both phases. Sorted after merging, because MCP
servers do not guarantee stable tool ordering across restarts and tools render at
prefix position 0 -- an unsorted merge would silently discard the cache every
time the server came up in a different order.

Both phases share the list so they share the cache. `propose` is reachable from
the write phase and simply has nothing to do there; the alternative is two
prefixes and two cache objects to save a few hundred tokens that are cached
anyway.

**`create_chapter` is deliberately NOT here.** Chapter creation is
proposal-driven: `write.py` scaffolds from the approved `chapter_title` and
`chapter_defines` BEFORE the model's first turn. Leaving it in the tool list gave
the agent a tool that could only ever return `rejected: already exists`, and made
ownership ambiguous on the one path that is structurally irreversible -- an entry
is a `git revert`, a chapter is something later entries build on. The handler
still exists; only `write.py` calls it.
"""

from google.genai import types

from . import api, figures, interact, probe, refs, shell, verifiers
from ..schema import Proposal


def _decl(name, description, properties=None, required=()):
    schema = {"type": "object",
              "properties": properties or {},
              "required": list(required)}
    return types.FunctionDeclaration(
        name=name, description=description, parameters_json_schema=schema)


S = {"type": "string"}
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
               "chapter": dict(S, description="Chapter directory name")},
              ["question", "chapter"]),

        _decl("lint",
              "Run the 19-rule lint contract over a chapter without rendering. "
              "Returns the violations verbatim; each message names its own fix.",
              {"chapter": S}, ["chapter"]),

        _decl("render",
              "quarto render. Target a single entry path while iterating; the "
              "whole notebook is slow.",
              {"target": dict(S, description="Path relative to the notebook root")}),

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
               "why": dict(S, description="Why it changes what we are building"),
               "options": dict(S, description="Plausible values, if that helps")},
              ["name", "why"]),

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
    ]


def build(session, fs):
    """(tools, handlers) -- one sorted list, one dispatch table."""
    nb = session.notebook
    decls = sorted(native_declarations() + fs.declarations(), key=lambda d: d.name)

    handlers = dict(fs.handlers())
    handlers.update({
        "probe": lambda question, chapter=None: probe.run_probe(
            nb, chapter or session.chapter, question, session),
        "lint": lambda chapter: verifiers.lint_chapter(nb, chapter),
        "render": lambda target="": verifiers.render(nb, target),
        "check": lambda chapter="", force_all=False: verifiers.check(
            nb, chapter, force_all),
        "api_search": lambda query, kind="all": api.api_search(query, kind),
        "api_signature": lambda path, methods=False: api.api_signature(path, methods),
        "read_reference": lambda name: refs.read_reference(name),
        "read_figure": lambda chapter, stem, name="": figures.read_figure(
            nb, chapter, stem, name),
        "ask_specified": lambda name, why, options="": interact.ask_specified(
            session, name, why, options),
        "consult": lambda question, why: interact.consult(session, question, why),
        "bash": lambda command: shell.bash(nb, command),
        "propose": lambda **kw: interact.propose(session, **kw),
    })
    return [types.Tool(function_declarations=decls)], handlers

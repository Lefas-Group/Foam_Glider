"""
The structured payloads the model produces.

Pydantic earns its place twice here: `model_json_schema()` is the tool
declaration, and `model_validate()` is the check on the way back in. A malformed
`propose` therefore comes back as a message the model can read and fix, rather
than a KeyError inside a handler.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Input(BaseModel):
    """One input the question needed that was not already fixed."""

    name: str = Field(description="The quantity, e.g. 'static margin'")
    kind: Literal["derivable", "specified", "unknown"] = Field(
        description=(
            "derivable: the model or the plans already contain it -- compute it, "
            "never declare it. specified: a different answer changes WHAT WE ARE "
            "BUILDING -- ask via ask_specified. unknown: a different answer "
            "changes HOW ACCURATELY WE MODELLED IT -- assume and say what it costs."
        ))
    value: Optional[str] = Field(default=None, description="The value used")
    owner: Literal["user", "agent", "assumed"] = Field(
        description=(
            "user: they answered. agent: they delegated it and you answered, so "
            "say why. assumed: nobody knows -- only valid for kind=unknown."
        ))
    why: str = Field(description="Ten words at most -- lint rule 8 counts them")

    @model_validator(mode="after")
    def _discipline(self):
        if self.kind == "derivable":
            raise ValueError(
                f"'{self.name}' is derivable -- compute it, don't declare it.")
        if self.kind == "specified" and self.owner == "assumed":
            raise ValueError(
                f"'{self.name}' is Specified but owner is 'assumed'. A Specified "
                f"input is asked, every time -- use ask_specified. If you answered "
                f"it yourself because it was a one-sentence call, owner is 'agent'.")
        if len(self.why.split()) > 10:
            raise ValueError(
                f"'{self.name}': why is {len(self.why.split())} words, budget is 10.")
        return self


class Proposal(BaseModel):
    """
    What `nb ask` hands to the gate, and `nb write` reads back.

    Everything `nb write` needs is here: it does not get the probe transcript,
    because the entry's own code cells re-run the computation at render time.
    """

    title: str = Field(
        description=(
            "The question THIS entry answers, phrased as ONE question ending "
            "in '?', 18 words at most (rule 26) — aim for about eight. "
            "REPHRASE the ask: strip anything that holds for the whole chapter, "
            "because that lives in its index.qmd, and turn a brief into a "
            "question. 'optimise a glider for trimmed glide. It is constructed "
            "of foam 5mm thick…' is a brief; 'Which planform gives the lowest "
            "sink rate?' is its question. It becomes the entry title, the "
            "sidebar text and the filename."))
    question: str = Field(
        description=("What was actually asked, verbatim. Never edited — the "
                     "title may be rephrased, so this is the record of the "
                     "request, and it is what the commit message carries."))
    chapter: str = Field(description="Chapter directory name, e.g. '04-chosen-throw'")
    route: Literal["entry", "new_chapter"] = Field(
        description=(
            "entry: the same model as an existing chapter. new_chapter: a "
            "different model, fidelity or vehicle -- confirm via ask_specified "
            "first, since it decides whether both answers are kept."))
    rationale: str = Field(
        description="One line: what is held constant between arms, and what differs")
    findings: str = Field(
        description="The answer, and what the probe actually established")
    working_code: str = Field(
        description="The probe code that produced the answer, ready to adapt")
    figures: list[str] = Field(
        default_factory=list,
        description=(
            "Caption per intended visual, 50 words each. ONE visual or none -- "
            "a table counts as a figure. Prefer none, then a table, then a plot."))
    render_cost_s: float = Field(
        description="Solve seconds from aero_report(), never a guess")
    inputs: list[Input] = Field(default_factory=list)
    queue: list[str] = Field(
        default_factory=list,
        description=(
            "Further distinct questions in the same ask, one entry each. Facets "
            "of a SINGLE comparison (cost, fidelity, applicability) are one "
            "question, not three."))
    chapter_title: str = Field(
        default="",
        description=(
            "Only for route='new_chapter'. The CHAPTER's name, two or three "
            "words in the style of 'Flight path' or 'Chosen throw' — not the "
            "entry's question."))
    chapter_defines: str = Field(
        default="",
        description=(
            "Only for route='new_chapter'. What defines this chapter: the aero "
            "method, the section, what is left out. It goes in index.qmd and is "
            "the one place those assumptions are stated — entry prose must not "
            "repeat them."))
    handoff: str = Field(
        default="",
        description=(
            "Notes for the HUMAN, not for the page: anything you noticed that "
            "was not asked about, and would make a good next question. This is "
            "the skill's 'interesting things go in chat, never into the "
            "notebook' — it is read by a person and never copied into the entry."))

    @model_validator(mode="after")
    def _new_chapter_is_described(self):
        if self.route == "new_chapter" and not self.chapter_title.strip():
            raise ValueError(
                "route='new_chapter' needs chapter_title: the chapter's own "
                "name ('Flight path'), not the entry's question. Without it the "
                "chapter would be titled after one question it happens to hold.")
        if self.route == "new_chapter" and not self.chapter_defines.strip():
            raise ValueError(
                "route='new_chapter' needs chapter_defines: the aero method, the "
                "section, what is left out. index.qmd is the one place those "
                "assumptions are stated.")
        return self

    @field_validator("figures")
    @classmethod
    def _one_visual(cls, v):
        if len(v) > 1:
            raise ValueError(
                f"{len(v)} figures proposed; rule 14 allows one visual per entry "
                f"(a table counts as a figure). Choose the one that carries the "
                f"answer and drop the rest.")
        return v


class VerifyResult(BaseModel):
    """
    The fresh-context check of prose against what actually rendered.

    Deliberately narrow. `verify` is not a second reviewer with opinions about
    the entry -- lint already owns the rules, and the gate already owned the
    scope. It answers one question: does the page say anything the rendered
    output does not support?
    """

    ok: bool = Field(description="True when the prose is supported by the output")
    findings: list[str] = Field(
        default_factory=list,
        description=(
            "One per contradiction, each naming the claim and what the output "
            "actually shows. Empty when ok. Do not report style, wording, rule "
            "violations, or things you would have done differently."))

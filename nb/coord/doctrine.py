"""
The coordinator's doctrine pages, and who reads which.

ONE SOURCE, TWO READERS. The Gemini coordinator reads these as its cached
prefix; the Claude Code skill reads the same files through `nb doctrine`. That
is the whole point of the split -- `.claude/skills/coordinate-design/SKILL.md`
used to hold the doctrine as well as the harness instructions, and a second
coordinator meant a second copy. Two copies of a lesson learned from a wrong
taper ratio is one copy that will still be wrong next year.

MIRRORS `tools/refs.py`, including the rule that matters: a page IN THE PREFIX
is removed from any lookup enum, because offering both buys a wasted turn. The
coordinator has one tool list and one prefix, so today every page is in it and
there is no lookup tool at all. The structure is here for when that stops being
true.

The `audience` field is what `nb doctrine --setup` and `--coordinate` group on,
so Claude reads exactly the set the Gemini prefix carries -- regroup here and
both move together.
"""

import pathlib

DIR = pathlib.Path(__file__).parent.parent / "references" / "coordinator"

#: name -> (title, situation, audiences). `situation` says WHEN to read it,
#: per `refs.py`: a description of the moment, not a summary of the contents.
PAGES = {
    "programme.md": (
        "Running a design programme",
        "Always. The boundary of the role, how a question is chosen and "
        "justified, and how a session ends.",
        ("setup", "coordinate")),
    "sources.md": (
        "Find what the aircraft is made of, before you build it",
        "Before `new`, and whenever a run declares a number it guessed. "
        "Research, SOURCES.txt, and the materials every target rests on.",
        ("setup", "coordinate")),
    "the-brief.md": (
        "Specified, Target, Assumed: what goes in a brief",
        "Writing a brief, and every time you judge whether a figure is an "
        "input or something the geometry must produce.",
        ("setup", "coordinate")),
    # BOTH AUDIENCES NOW. It was `setup` only, on the reasonable view that
    # photographs are collected once and then done with. They are not: the
    # assumptions prompt puts the overlays a run has drawn in front of the
    # coordinator, and judging them is a `coordinate` act using exactly this
    # page's eye. Measured on the FT A-10 Warthog, 2026-10-10 -- the prompt
    # listed four overlays including the three-panel one, and the
    # coordinator's reasoning for accepting ran entirely on whether 400 g
    # was a plausible battery. It never opened an image. This page says "the
    # overlay is the only real check" and was not in front of it.
    "reference-photographs.md": (
        "Choosing, cutting and checking reference photographs",
        "Collecting photographs, any time a mask changes, and before "
        "answering an assumptions prompt that lists overlays. Angular "
        "spread, and why the overlay is the only real check.",
        ("setup", "coordinate")),
    # BOTH AUDIENCES, and the `coordinate` half is the one that earns it. The
    # setup case is obvious -- it says what to do instead of searching. What
    # outlives setup is the consequence: with nothing published, every
    # external check the reconstruction has is a silhouette, so the overlays
    # in an assumptions prompt are not corroboration, they are the whole
    # verification. That is a judgement made long after the aircraft was set
    # up, by a session that may never have seen the intake.
    "an-unpublished-aircraft.md": (
        "An aircraft nobody published",
        "When `_reference/INTAKE.yml` exists -- the user built this aircraft "
        "and supplied its photographs and figures themselves. What to "
        "research instead, why an empty `targets:` block is honest, and why a "
        "reshoot is worth asking for.",
        ("setup", "coordinate")),
    "judging-a-run.md": (
        "Judging what a run asks you",
        "Every question a run puts to you: the kinds, the reply syntax, "
        "Specified inputs, and the assumptions prompt.",
        ("coordinate",)),
}


def path(name):
    return DIR / name


def read(name):
    return path(name).read_text()


def pages(audience=None):
    """Page names for one audience, in reading order."""
    return [n for n, (_, _, who) in PAGES.items()
            if audience is None or audience in who]


def text(audience=None):
    """The pages concatenated, which is what a prefix embeds."""
    return "\n\n".join(read(n) for n in pages(audience))


def problems():
    """
    Registry and directory disagreeing -- for `preflight`.

    A page on disk that nothing lists is a page neither coordinator reads, and
    a listed page that is missing is an import error at the worst moment.
    `tools/refs.py` keeps this invariant in a comment; here it is a check,
    because `preflight.py` already learned that a hand-kept copy goes stale.
    """
    found = {p.name for p in DIR.glob("*.md")} if DIR.is_dir() else set()
    listed = set(PAGES)
    out = []
    for missing in sorted(listed - found):
        out.append(f"doctrine: {missing} is listed in PAGES and not on disk")
    for orphan in sorted(found - listed):
        out.append(f"doctrine: {orphan} is on disk and not in PAGES")
    for name, (_, _, who) in PAGES.items():
        if not who:
            out.append(f"doctrine: {name} is assigned to no audience")
    return out

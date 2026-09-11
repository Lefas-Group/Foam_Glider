# `nb` — the design-notebook agent

Produces Quarto lab-notebook entries for aircraft design work. Distilled from the
`design-notebook` Claude Code skill (`.claude/skills/design-notebook/`), and runs
without it, on Gemini.

Design and rationale: `../agentic-notebook-spec.md`.

## Use

```bash
uv run --group nb python -m nb ask optimised-glider-notebook "why is the tail so big?"
#   probes the chapter's model, asks about anything Specified, then writes
#   _scratch/run/proposal.json and STOPS.

#   read the proposal, edit it if you like, then:

uv run --group nb python -m nb write optimised-glider-notebook
#   writes the entry, fixes it against the 18-rule lint contract, and stops
#   before rendering.
```

Needs `GEMINI_API_KEY`, plus `quarto`, `git` and `npx` on `PATH`.

Render and commit stay manual:

```bash
uv run python nb/vendor/check.py optimised-glider-notebook 01-duration-glider
```

## Why two commands

The gate between them is a **process boundary**, not a checkpoint. Every run
stops at exactly one place — after the proposal, before anything is written to
the notebook — and the process exits there. Nothing ever has to survive a pause
it did not choose, which is why there is no orchestration framework here and no
checkpointer. `proposal.json` is the whole handoff; the two phases share no
conversation state, because the entry's code cells recompute the answer at render
time anyway.

## Layout

    vendor/      copied from the skill; canonical from here on. lint.py and
                 friends, plus notebook.py and probe_base.py, which must sit
                 BESIDE lint.py because rule 11 resolves them relative to
                 __file__.
    tools/       one handler per tool. mcp_fs.py is the only thing still
                 speaking MCP.
    phases/      ask.py and write.py.
    prefix.py    assembles the cached prefix: system instruction, chapter
                 manifest, every index.qmd, every _model.py name.
    loop.py      the agent loop. Append the whole Content, always.

## Two things that will bite

**Append `resp.candidates[0].content` whole.** Model turns carry thought
signatures, and the first `function_call` part of each step must carry its
signature back byte-identically or the next request 400s. Rebuilding a turn from
name and args drops it — verified, with a negative control.

**The prefix is a byte-exact prefix match.** Anything volatile in the system
instruction — a date, a path, an unsorted dict — invalidates the whole thing
silently. Check `usage_metadata.cached_content_token_count`; zero across repeated
calls means something is varying.

## Diverging from the skill

`vendor/` is now the canonical copy. The skill is its ancestor and the two are
expected to drift apart; there is deliberately no drift check between them,
because that would reintroduce the coupling this removes.

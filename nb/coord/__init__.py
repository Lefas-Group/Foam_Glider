"""
The coordinator agent: the half of the programme that decides what to ask.

`nb/agent/` is the RUN -- one question, one entry, sandboxed to `chapters/`,
no network. This is the other role, and it is a different agent on a different
model with a different tool surface, sharing that package's loop, client and
stuck detector rather than reimplementing them.

WHY IT FITS WITHOUT A NEW PROTOCOL. `process/coordinator.py` already models a
coordinator as a participant in the run mailbox at a reserved id, holding no
lock, with all its state on disk; `process/mailbox.py` says the file-based
question protocol exists so the answerer can be "now themselves, later a
coordinator agent"; `cli/board.py` calls that independence "the whole design --
it is what lets a coordinator agent replace the person here without the agents
changing". Nothing here changes any of that. It writes the same `answer.json`
a person typing `nb answer` would.

WHAT IT MAY NOT DO. It never writes an entry, edits a chapter or touches a
`_model.py` -- a second writer in a chapter is refused by a lock, and the whole
point of the role is that the run publishes and the coordinator decides. So
none of `nb/tools/` is reachable from here, and nothing here is registered
there. The reverse matters more once research lands: the run has no network and
must keep none, which is a test rather than a convention now that both agents
live in one package.

The Claude Code skill at `.claude/skills/coordinate-design/` does the same job
through the same CLI. Two coordinators, one notebook format, and the doctrine
they share is the thing to keep in one place.
"""

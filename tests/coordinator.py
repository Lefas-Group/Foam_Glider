"""
The invariants that keep the two agents apart.

    uv run --group nb python tests/coordinator.py

`nb/coord/` and `nb/tools/` are two tool surfaces for two agents that share one
package, and the thing that makes the system trustworthy is that they are NOT
the same surface. The run writes entries and has no network; the coordinator
has the network and writes no entry. Both halves of that were a convention
until this file, and a convention between two packages in one repo is a
convention that gets broken by a convenient import.

Not pytest, because nothing else here is: `characterize.py` is a script with a
`--check` mode and this follows it.
"""

import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: What the coordinator may do and the run may not. A run that could reach any
#: of these could research its own aircraft, and then an invented dimension and
#: a looked-up one would be indistinguishable in the finished entry -- which is
#: the whole reason the brief exists.
NETWORKED = {"search", "fetch", "read_image", "read_plan_page", "add_photo",
             "source", "new", "mask", "overlay", "reference"}

#: What the run may do and the coordinator may not. The coordinator never
#: writes an entry, and a second writer in a chapter is refused by a lock
#: anyway -- this catches the import that would make it possible, not the lock.
AUTHORING = {"probe", "lint", "render", "open_entry", "declare_input",
             "fork_chapter", "ask_specified", "write_file", "edit_file"}


def _run_agent_tools():
    from nb.agent.session import Session
    from nb.config import Notebook
    from nb.tools import native_declarations
    from nb.tools.mcp_fs import FileSystem
    names = {d.name for d in native_declarations()}
    # The filesystem server's exposed set, without starting a subprocess.
    names |= set(FileSystem.EXPOSED) if hasattr(FileSystem, "EXPOSED") else set()
    from nb.tools import mcp_fs
    names |= set(getattr(mcp_fs, "EXPOSED", ()))
    del Session, Notebook
    return names


def _coordinator_tools():
    from nb.coord import tools
    from nb.coord.session import Coordination
    _, handlers = tools.build(Coordination(None, wanted="zz"))
    return {d.name for d in tools.declarations()} | set(handlers)


def main(argv):
    bad = []
    run, coord = _run_agent_tools(), _coordinator_tools()

    leaked = sorted(run & NETWORKED)
    if leaked:
        bad.append(f"the RUN can reach {leaked} — it must have no network and "
                   f"must not cut the masks it is measured against")

    authoring = sorted(coord & AUTHORING)
    if authoring:
        bad.append(f"the COORDINATOR can reach {authoring} — it decides what "
                   f"to ask; the run writes")

    # Parity: a declaration with no handler is a tool the model will call and
    # get "no such tool" for, which `agent/loop.py` records as the shape of the
    # worst run this system has had. `search` is server-side and has neither.
    from nb.coord import tools
    from nb.coord.session import Coordination
    decls = {d.name for d in tools.declarations()} - {"search"}
    _, handlers = tools.build(Coordination(None, wanted="zz"))
    for missing in sorted(decls - set(handlers)):
        bad.append(f"coordinator declares {missing!r} with no handler")
    for orphan in sorted(set(handlers) - decls):
        bad.append(f"coordinator handles {orphan!r} with no declaration")

    # Every notebook-dependent tool must REFUSE in words before `new`, never
    # raise: a traceback teaches the model the tool does not work, and it goes
    # looking for another one.
    free = {"new", "fetch", "read_image", "read_plan_page", "source",
            "direction"}
    args = {"chapter": "x", "question": "y?", "why": "z", "run": "r",
            "value": "v", "text": "t", "name": "n", "prompt": "p",
            "summary": "s", "file": "f", "description": "d" * 60}
    for name in sorted(set(handlers) - free):
        fn = handlers[name]
        try:
            got = fn(**{k: v for k, v in args.items()})
        except TypeError:
            try:
                got = fn()
            except Exception as exc:                        # noqa: BLE001
                bad.append(f"{name} raised before `new`: {type(exc).__name__}")
                continue
        except Exception as exc:                            # noqa: BLE001
            bad.append(f"{name} raised before `new`: {type(exc).__name__}")
            continue
        if "no notebook yet" not in str((got or {}).get("error", "")):
            bad.append(f"{name} did not refuse cleanly before `new`: "
                       f"{str(got)[:70]}")

    for line in bad:
        print(f"  {line}")
    print(f"  {len(run)} run tools, {len(coord)} coordinator tools, "
          f"{len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

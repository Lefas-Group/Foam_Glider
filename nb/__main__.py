"""
    nb new   <notebook> [title]          scaffold a notebook, then prove it
    nb ask   <notebook> "<question>"     probe, then propose and stop
    nb write <notebook>                  write the approved proposal

Two commands, because the gate between them is a process boundary: `ask` exits
where a human decides, and `write` picks up from `proposal.json`. The two share
no conversation state -- the entry's own code cells recompute the answer at
render time, so the write phase needs the finding and the working code, not the
transcript.
"""

import sys

USAGE = __doc__.strip()


def main(argv):
    # A run is minutes long and prints one line per turn. Block-buffered to a
    # file or a pipe that is a silent hang, which is indistinguishable from a
    # stuck probe at exactly the moment you want to tell them apart.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "new":
        if not rest:
            print(USAGE)
            return 2
        from .phases.new import main as new
        return new(rest[0], " ".join(rest[1:]) or None)

    if cmd == "ask":
        if len(rest) < 2:
            print(USAGE)
            return 2
        from .phases.ask import main as ask
        return ask(rest[0], " ".join(rest[1:]))

    if cmd == "write":
        if not rest:
            print(USAGE)
            return 2
        from .phases.write import main as write
        return write(rest[0])

    print(f"unknown command {cmd!r}\n\n{USAGE}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

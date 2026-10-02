"""
A static server for a notebook's `_site`, so one browser tab can follow a whole
programme.

THE PROBLEM THIS SOLVES IS TAB ACCUMULATION, and it solves it by removing the
need to open anything twice rather than by detecting that something is already
open. Asking a browser "do you already have this URL?" needs an API the browser
exposes to other processes: macOS has one (AppleScript, for Chrome-family and
Safari), Linux has no standard equivalent, Windows has none for Chrome or Edge.
Measured before this existed: `webbrowser.open(url, new=0)` took Chrome from 21
tabs to 22 to 23 on the same URL. There is no portable answer.

A page that refreshes itself needs no answer. The server appends a few lines of
JavaScript to each HTML page it serves; that script holds an EventSource open
and reloads when the site changes, or navigates when a run says where to go.
One tab, opened once, current forever -- on any OS and any browser.

SERVER-SENT EVENTS, NOT POLLING, and the first cut got this wrong. A
`setInterval` poll is throttled to about once a MINUTE in a background tab --
which is every tab here, since the work happens in an editor -- so a committed
entry took up to a minute to show and the "is anyone watching?" check, which
allowed three seconds of silence, answered no for a tab that was plainly open.
Measured: `watching` reported False against a tab sitting on the page. An open
connection is not a timer, so none of that applies, and "is anyone watching"
stops being a heuristic about silence and becomes a count of connections.

THIS IS NOT `quarto preview`. It serves files that are already built and
executes nothing. `cli/view.py` guards a project render behind `--force`
precisely because a render re-executes any entry whose freeze is missing, which
is minutes of aero solves; none of that is in reach here.

THE INJECTION IS AT SERVE TIME, never on disk. `_site/` is committed, and a
polling script baked into it would be published with the notebook and would be
one more thing `check` sees change. The files on disk stay exactly as Quarto
wrote them.

Bound to 127.0.0.1. This is a view of one person's working directory and has no
business being reachable from anywhere else.
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# How often the SERVER looks for a change to push. The browser is not timing
# anything now -- it holds a connection and waits -- so this is the only clock,
# and a second is far below what a render takes and far above what a stat of
# `_site` costs.
TICK_S = 1.0

LIVE = "live.json"          # where a run says "go here next"
SERVER = "serve.json"       # where a running server records its port and pid

# Appended to every HTML page served. Deliberately small and dependency-free.
#
# TWO SIGNALS, NOT ONE. `stamp` is the newest mtime under `_site` and means
# "something was rebuilt -- reload what you are looking at". `goto` is a run
# saying where the answer it just committed lives, and means "show this
# instead". The script records whichever `goto` it arrived with, so landing on
# a page never re-triggers the navigation that brought you there, and a tab
# opened later does not jump to an entry from an hour ago.
SCRIPT = """
<script>
(function () {
  var seen = null, stamp = null;
  var src = new EventSource("/_nb/events");
  src.onmessage = function (e) {
    var s = JSON.parse(e.data);
    if (seen === null) { seen = s.goto_id; stamp = s.stamp; return; }
    if (s.goto_id !== seen && s.goto) { seen = s.goto_id; location.href = "/" + s.goto; return; }
    if (s.stamp !== stamp) { stamp = s.stamp; location.reload(); }
  };
})();
</script>
"""


def _newest(root):
    """The newest mtime under `_site`, as the whole site's version."""
    newest = 0.0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            try:
                newest = max(newest, os.stat(os.path.join(dirpath, f)).st_mtime)
            except OSError:
                continue
    return newest


# HOW MANY TABS ARE SHOWING THIS SITE. An open EventSource is a held
# connection, so this is a count rather than a guess about how long it has been
# since someone said something -- which is what it was when the page polled,
# and which answered "nobody" for a tab that was plainly open because Chrome
# throttles timers in background tabs.
#
# `nb open` asks this, and declines to open a second tab for a site someone is
# already looking at: the portable answer to "is it already open?" that no
# browser will give you.
_WATCHERS = 0
_WATCHERS_LOCK = threading.Lock()


class _Handler(SimpleHTTPRequestHandler):
    """Static files, plus two endpoints and one injected script."""

    notebook_scratch = None          # set by `_serve`

    def log_message(self, *args):
        pass                          # a view, not a thing with a request log

    def do_GET(self):                 # noqa: N802 -- the stdlib's spelling
        if self.path.startswith("/_nb/live"):
            return self._live()
        if self.path.startswith("/_nb/watching"):
            return self._json({"watching": _WATCHERS > 0})
        if self.path.startswith("/_nb/events"):
            return self._events()
        return super().do_GET()

    def _json(self, got):
        body = json.dumps(got).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _live(self):
        self._json(self._state())

    def _events(self):
        """
        Hold the connection open and push when something moves.

        One thread per tab, which `ThreadingHTTPServer` already gives us and
        which is the right shape for the one or two that will ever exist. The
        first message is the current state, so a page that has just loaded
        learns where it stands without acting on it.
        """
        global _WATCHERS
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        with _WATCHERS_LOCK:
            _WATCHERS += 1
        last = None
        try:
            while True:
                now = self._state()
                if now != last:
                    self.wfile.write(f"data: {json.dumps(now)}\n\n".encode())
                    last = now
                else:
                    # A HEARTBEAT, AND THE ONLY WAY A DEAD TAB IS NOTICED.
                    # Writing only on change means a quiet server never writes,
                    # never discovers the socket is gone, and counts a closed
                    # tab as a watcher forever -- after which `nb open` refuses
                    # to open the tab it should. Seen exactly that: `watching`
                    # True with no tab in the browser.
                    #
                    # A `:` line is an SSE comment. EventSource ignores it, so
                    # this costs the page nothing and buys the write that
                    # fails.
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                time.sleep(TICK_S)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass                      # the tab went away, which is not an error
        finally:
            with _WATCHERS_LOCK:
                _WATCHERS -= 1

    def _state(self):
        got = {"stamp": _newest(self.directory), "goto_id": 0, "goto": None}
        try:
            got.update(json.loads((self.notebook_scratch / LIVE).read_text()))
        except (OSError, ValueError):
            pass                      # no run has said anything yet
        return got

    def send_head(self):
        """
        HTML gets the script appended; everything else is served untouched.

        Done here rather than in `do_GET` so that the Content-Length header
        matches what is actually sent -- `SimpleHTTPRequestHandler` sends the
        file's size from `os.fstat`, and appending after that would hang the
        browser waiting for bytes that never come.
        """
        path = self.translate_path(self.path)
        # A DIRECTORY IS `index.html`, and resolving that here is the whole of
        # why the first cut injected nothing into the front page: for "/",
        # `translate_path` returns the directory, the `.html` test failed, and
        # the stdlib found `index.html` for itself -- after the only chance to
        # append anything had gone.
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if not path.endswith(".html") or not os.path.isfile(path):
            return super().send_head()
        try:
            body = pathlib.Path(path).read_bytes()
        except OSError:
            return super().send_head()
        if b"</body>" in body:
            body = body.replace(b"</body>", SCRIPT.encode() + b"</body>", 1)
        else:
            body += SCRIPT.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        import io
        return io.BytesIO(body)


def record(notebook, site_relative_path):
    """
    Tell whatever tab is open to go and look at this.

    Called when a run commits. The id increments so the page can tell a NEW
    instruction from the one it already followed; without it, every poll after a
    commit would navigate again and the tab would be pinned to that entry.
    """
    p = notebook.scratch / LIVE
    try:
        was = json.loads(p.read_text()).get("goto_id", 0)
    except (OSError, ValueError):
        was = 0
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"goto_id": was + 1,
                                 "goto": str(site_relative_path)}))
    except OSError:
        pass                          # a view failing is not a run failing


def running(notebook):
    """The port a live server for this notebook is on, or None."""
    try:
        state = json.loads((notebook.scratch / SERVER).read_text())
    except (OSError, ValueError):
        return None
    port = state.get("port")
    if not port:
        return None
    try:
        # `/_nb/watching`, which is a plain request. It mattered more when the
        # page polled `/_nb/live`: the health check hit the same endpoint, the
        # server counted it as a tab, and `nb open` then never opened one --
        # caught by a first open reporting "already open" with no tab in sight.
        # A watcher is a held connection now, so a request cannot be mistaken
        # for one, but asking a question that means "are you there" is still
        # the right call to make here.
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/_nb/watching", timeout=1) as r:
            if r.status == 200:
                return port
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return None                       # recorded but gone; a fresh one is due


def watching(notebook, port):
    """True when a tab is currently polling this notebook's site."""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/_nb/watching", timeout=1) as r:
            return bool(json.loads(r.read()).get("watching"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def start(notebook):
    """The port for this notebook's site, starting a server if need be."""
    port = running(notebook)
    if port:
        return port
    # A SEPARATE SESSION, like a run: this outlives the command that asked for
    # it, and must not die when its terminal closes.
    subprocess.Popen(
        [sys.executable, "-m", "nb.process.serve", str(notebook.root)],
        cwd=str(notebook.repo), start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):              # ~5 s, generously
        port = running(notebook)
        if port:
            return port
        time.sleep(0.05)
    return None


def stop(notebook):
    """Shut a running server down. Returns whether there was one."""
    try:
        state = json.loads((notebook.scratch / SERVER).read_text())
        os.kill(state["pid"], 15)
        (notebook.scratch / SERVER).unlink(missing_ok=True)
        return True
    except (OSError, ValueError, KeyError):
        return False


def _serve(notebook):
    site = notebook.root / "_site"
    _Handler.notebook_scratch = notebook.scratch
    handler = partial(_Handler, directory=str(site))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    notebook.scratch.mkdir(parents=True, exist_ok=True)
    (notebook.scratch / SERVER).write_text(
        json.dumps({"port": port, "pid": os.getpid()}))
    threading.Thread(target=httpd.serve_forever, daemon=False).start()
    return port


def main(argv):
    if not argv:
        print("usage: python -m nb.process.serve <notebook-root>")
        return 2
    from ..config import Notebook
    _serve(Notebook(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

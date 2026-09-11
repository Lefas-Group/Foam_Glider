"""
The MCP filesystem server, wrapped for a synchronous caller.

This is the only thing left that needs MCP. `library_explorer` went over stdio
in the skill because Claude Code had no other way in; here it is imported.

Why a server at all rather than a handful of pathlib calls: the directory
boundary is then enforced in a DIFFERENT PROCESS. A bug in this code cannot
widen it, which is exactly the property that hand-rolled path confinement fails
to give -- and failed to give in an earlier draft of this system, where a glob
allowlist ran against the model's raw string and `../../` walked straight
through it.

The server is async and the loop is not, so it runs on its own event loop in a
background thread and calls are submitted across.
"""

import asyncio
import pathlib
import threading

from google.genai import types

from ..text import head

# Six of fourteen. The rest stay out of the prefix -- tools sit at position 0,
# and every declaration is paid for on every request until the cache covers it.
EXPOSED = ("read_text_file", "read_media_file", "list_directory",
           "search_files", "edit_file", "write_file")

# The server's own descriptions are written for a general audience. These say
# what the tool is for HERE, which is what changes whether it gets reached for.
NOTES = {
    "read_text_file": " Use head/tail to read a slice rather than a whole file.",
    "read_media_file": " Rendered figures are PNGs; prefer the read_figure tool.",
    "edit_file": " The default path for changing an existing file. Set dryRun to"
                 " preview a diff first.",
    "write_file": " Creation only -- a full overwrite. Use edit_file to modify.",
}


class FileSystem:
    def __init__(self, allowed_dir):
        self.allowed = pathlib.Path(allowed_dir).resolve()
        self._loop = None
        self._thread = None
        self._session = None
        self._tools = []
        self._ready = threading.Event()
        self._stop = None

    # -------------------------------------------------------------- lifecycle

    def start(self, timeout=120):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("MCP filesystem server did not start")
        if isinstance(self._error, Exception):
            raise self._error
        return self

    _error = None

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:      # surfaced to start()
            self._error = e
            self._ready.set()

    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", str(self.allowed)])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                self._session = session
                self._tools = (await session.list_tools()).tools
                self._stop = asyncio.Event()
                self._ready.set()
                await self._stop.wait()

    def stop(self):
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=10)

    # ------------------------------------------------------------ declarations

    def declarations(self):
        out = []
        for t in self._tools:
            if t.name not in EXPOSED:
                continue
            out.append(types.FunctionDeclaration(
                name=t.name,
                description=(t.description or "").strip() + NOTES.get(t.name, ""),
                parameters_json_schema=t.inputSchema))
        return out

    # -------------------------------------------------------------- calling

    def _abs(self, value):
        """
        Let the model use notebook-relative paths.

        The server takes absolute paths inside its allowed root. Making the model
        write them out would spend tokens on a prefix it cannot get wrong anyway,
        since anything outside the root is refused by the server regardless.
        """
        p = pathlib.Path(value)
        if p.is_absolute():
            return str(p)
        s = str(value).lstrip("/")
        for prefix in ("chapters/", f"{self.allowed.name}/"):
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        return str(self.allowed / s)

    def call(self, name, args):
        args = dict(args)
        for k in ("path", "source", "destination"):
            if k in args and isinstance(args[k], str):
                args[k] = self._abs(args[k])
        if "paths" in args and isinstance(args["paths"], list):
            args["paths"] = [self._abs(p) for p in args["paths"]]

        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, args), self._loop)
        res = fut.result(timeout=180)

        parts = []
        for c in res.content:
            text = getattr(c, "text", None)
            if text is not None:
                parts.append(text)
            elif getattr(c, "data", None) is not None:
                parts.append(f"[{getattr(c, 'mimeType', 'binary')}, "
                             f"{len(c.data)} b64 chars]")
        out = "\n".join(parts) if parts else "(no content)"
        if getattr(res, "isError", False):
            return f"error: {out}"
        return head(out)

    def handlers(self):
        return {t.name: (lambda n: lambda **kw: self.call(n, kw))(t.name)
                for t in self._tools if t.name in EXPOSED}

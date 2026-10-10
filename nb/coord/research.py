"""
Finding things out: the half of the job the run agent is forbidden.

THE ASYMMETRY IS THE POINT, and it is not new. The run has no network and is
sandboxed to `chapters/`, so every dimension the brief does not supply it
supplies from memory -- and an invented chord looks exactly like a measured one
in the finished entry. The coordinator exists partly to close that: "a row that
states the number is worth five that state its absence."

NOTHING HERE IS REGISTERED IN `nb/tools/__init__.py`, and that is now a test
rather than a convention, because both agents live in one package.

WHY `source` REQUIRES A PRIOR `fetch`. Measured 2026-10-08, settling whether
`google_search` could sit beside function declarations: asked for the Little
Piggy's published wingspan, grounding found the right Flite Test pages and
answered that the wingspan was not prominently published -- while the store
page prints `29 in (736.6 mm)`, which is what `SOURCES.txt` already records.
Grounding is good at finding a page and unreliable at reading a figure off it.
So a citation may not be recalled; it has to come from bytes this session
actually received. The ledger below is that precondition, and it is deliberately
per-session: a page read by a previous run of `nb coordinate` proves nothing
about what this one read.

NO MODEL-SUPPLIED PATHS. `tools/mcp_fs.py` puts the filesystem boundary in
another process because "a glob allowlist ran against the model's raw string
and `../../` walked straight through it". Rather than defend a path here, there
is no path: `fetch` writes under a generated name in the session's scratch, and
`add_photo` takes a bare slug and computes the destination. There is nothing to
traverse.
"""

import hashlib
import pathlib
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from ..tools import figures

#: Deliberately modest. A plan sheet is a few MB; anything far past that is
#: not a reference photograph and should not be pulled into a notebook
#: unnoticed.
MAX_BYTES = 40 * 1024 * 1024
TIMEOUT = 60

#: A browser-ish agent, because several of the stores these aircraft come from
#: return 403 to the stdlib default.
AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

#: What a reference photograph may be. `figures._SUFFIXES` is the authority on
#: what the notebook will later pick up, and a mask is written as PNG beside
#: whatever this saved, so the source format only has to be readable by PIL.
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png",
               "image/webp": ".webp", "image/gif": ".png"}


def _norm(url):
    """A URL compared the way a person would: scheme and host case-folded."""
    got = urllib.parse.urlsplit(str(url).strip())
    return urllib.parse.urlunsplit(
        (got.scheme.lower(), got.netloc.lower(), got.path, got.query, ""))


def fetch(session, url):
    """
    Pull one URL into the session's scratch and record it in the ledger.

    Returns the local path as a plain name, never a path the model composes
    with. The ledger entry is what later lets `source` cite this URL.
    """
    try:
        req = urllib.request.Request(str(url), headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as got:
            ctype = (got.headers.get_content_type() or "").lower()
            body = got.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "url": str(url)}
    if len(body) > MAX_BYTES:
        return {"error": f"larger than {MAX_BYTES // 1024 // 1024} MB", "url": str(url)}

    digest = hashlib.sha256(body).hexdigest()
    ext = IMAGE_TYPES.get(ctype) or (".pdf" if ctype == "application/pdf"
                                     else ".html" if "html" in ctype else ".bin")
    name = f"{digest[:12]}{ext}"
    path = _scratch(session) / name
    path.write_bytes(body)
    session.fetched[_norm(url)] = {"sha256": digest, "bytes": len(body),
                                   "at": time.time(), "file": name,
                                   "content_type": ctype}
    out = {"url": str(url), "file": name, "content_type": ctype,
           "bytes": len(body)}
    # TEXT COMES BACK IN THE RESULT; bytes do not. An HTML page is what the
    # model has to read a specification off, and sending it to a file it then
    # cannot open would be a tool that only pretends to fetch. An image is the
    # opposite case -- `figures.py` measured a PNG through a function response
    # at ~23k tokens against 1,298 as an inline part -- so those stay on disk
    # and `read_image` brings them back properly.
    if "html" in ctype or ctype.startswith("text/"):
        out["text"] = _readable(body)
    return out


def _readable(body):
    """
    The page as prose: scripts, styles and tags stripped, whitespace collapsed.

    Crude on purpose. The job is to let a specification table be read, not to
    render the page, and a dependency that renders it properly would be a
    dependency carried for one command.
    """
    text = body.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                    ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(ent, ch)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:30000]


def _scratch(session):
    d = session.scratch_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_image(session, file):
    """One fetched image, as an inline part the model can actually see."""
    path = _scratch(session) / pathlib.Path(str(file)).name
    if not path.exists():
        have = sorted(p.name for p in _scratch(session).iterdir())
        return {"error": f"no fetched file {file!r}.", "fetched": have}
    kind = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp"}.get(path.suffix.lower())
    if not kind:
        return {"error": f"{path.suffix} is not an image. "
                         f"For a plan sheet use `read_plan_page`."}
    return {"_image": path.read_bytes(), "mime_type": kind, "name": path.name}


def read_plan_page(session, file, page=1, dpi=150):
    """
    One page of a fetched PDF, rasterised, as an inline image.

    `pdftoppm` rather than a Python PDF library: it is already relied on for
    this job, and page one of a plan sheet is a specification table whose
    numbers are the point -- 150 dpi is what makes them legible.
    """
    src = _scratch(session) / pathlib.Path(str(file)).name
    if not src.exists():
        return {"error": f"no fetched file {file!r}."}
    stem = _scratch(session) / f"{src.stem}-p{int(page)}"
    try:
        subprocess.run(["pdftoppm", "-png", "-r", str(int(dpi)),
                        "-f", str(int(page)), "-l", str(int(page)),
                        str(src), str(stem)],
                       capture_output=True, check=True, timeout=120)
    except FileNotFoundError:
        return {"error": "pdftoppm is not installed (brew install poppler)."}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {"error": f"pdftoppm failed: {exc}"}
    made = sorted(_scratch(session).glob(f"{stem.name}*.png"))
    if not made:
        return {"error": f"page {page} produced nothing; is the PDF that long?"}
    return {"_image": made[0].read_bytes(), "mime_type": "image/png",
            "name": made[0].name}


def write_sources(root, rows):
    """
    Append `(origin, text)` rows to `_reference/SOURCES.txt`.

    A ROOT PATH RATHER THAN A NOTEBOOK, because both things that write this
    file can run before there is one. `source` buffers rows until `new` creates
    the directory, and `nb intake` writes a measurement into a directory that
    is not a notebook yet and may never become one.

    And an ORIGIN rather than a URL. Everything the coordinator records here
    came off a page, and the ledger in `source` holds it to that -- but a
    figure read off a tape measure has no URL and is the better number. This
    file says where each line came from; it does not insist that be a link.
    """
    path = pathlib.Path(root) / figures.REFERENCE_DIR / "SOURCES.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = path.read_text() if path.exists() else ""
    for origin, body in rows:
        sep = "" if (not prior or prior.endswith("\n\n")) else (
            "\n" if prior.endswith("\n") else "\n\n")
        prior = f"{prior}{sep}{origin}\n  {body}\n"
    path.write_text(prior)
    return path


def source(session, url, text):
    """
    Append to `_reference/SOURCES.txt` -- refused unless the URL was fetched.

    The refusal carries the ledger, because "you did not fetch that" without
    saying what WAS fetched is a dead end: the usual cause is a near-miss on
    the URL, not a fabrication.
    """
    key = _norm(url)
    if key not in session.fetched:
        return {"refused": (f"nothing was fetched from {key}. SOURCES.txt "
                            f"records what a page SAID, so fetch it first -- "
                            f"a figure recalled rather than read is the one "
                            f"mistake this file exists to prevent."),
                "fetched_this_session": sorted(session.fetched)}
    body = " ".join(str(text).split())
    if not body:
        return {"error": "say what the page gave you, or what it failed to."}
    # BUFFERED BEFORE THERE IS A NOTEBOOK, because the research that fills the
    # brief necessarily precedes the `new` that creates the directory the
    # brief lives in. Telling the model to research first and then refusing to
    # record what it found would be an order it cannot obey; `adopt` flushes
    # these the moment the directory exists.
    nb = session.notebook
    if nb is None:
        session.pending_sources.append((str(url), body))
        return {"recorded": str(url), "pending": len(session.pending_sources),
                "note": "held until `new` creates the notebook, then written."}
    path = nb.root / figures.REFERENCE_DIR / "SOURCES.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_sources(nb.root, [(str(url), body)])
    return {"recorded": str(url), "file": str(path.relative_to(nb.repo))}


def add_photo(session, name, file, description):
    """
    Put a fetched image into `_reference/` as a described reference photograph.

    THE FETCH LEDGER IS THIS FUNCTION'S HALF, and the only half it keeps.
    Resolving the name inside the session scratch is what makes the filesystem
    boundary hold -- `tools/mcp_fs.py` put that boundary in another process
    because "a glob allowlist ran against the model's raw string and `../../`
    walked straight through it", and the answer here is that there is no path
    to traverse. What a reference photograph IS, once the bytes are trusted,
    belongs to `figures.install_photo`: the same rules have to govern a frame
    the user shot and named in their own shell through `nb intake`.
    """
    nb = session.notebook
    if nb is None:
        return {"error": "no notebook yet -- call `new` first."}
    src = _scratch(session) / pathlib.Path(str(file)).name
    if not src.exists():
        have = sorted(p.name for p in _scratch(session).iterdir())
        return {"error": f"no fetched file {file!r}. `fetch` it first.",
                "fetched": have}
    got = figures.install_photo(nb.root / figures.REFERENCE_DIR,
                                name, src, description)
    if "error" in got:
        # NO `force` IN THIS DOOR, deliberately. Replacing a frame invalidates
        # a mask that committed numbers may rest on, and `cli/mask.py` is
        # explicit that only a person can know whether they do. A coordinator
        # that wants a different photograph adds it under a different name.
        if got.get("taken"):
            got["error"] += (" Add this frame under a different name, or "
                             "`escalate` if the one on disk is wrong.")
        return got
    return {"added": got["installed"], "image": got["image"],
            "normalised": got["how"], "note": (
                "Described, not yet masked. `mask` cuts it, then LOOK at the "
                "overlay.")}

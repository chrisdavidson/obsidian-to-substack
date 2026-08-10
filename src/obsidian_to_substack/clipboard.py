"""Put the article on the system clipboard as rich text, per platform.

Substack has no API, so publishing ends in a paste. `--copy` exists to make
that paste carry formatting rather than raw markup, which means writing HTML to
the clipboard rather than text -- and every operating system does that
differently.

Each platform gets its native tool. No clipboard library is used: the only
Python package covering HTML on all three is `jaraco.clipboard`, which wraps
`richxerox` and `jaraco.windows` to do it, and taking it would add three
transitive dependencies to a deliberately short stack AND replace the Linux
path, which is the one path here that is actually known to work.

**What is and is not verified.** The Linux path has been exercised against a
real Substack composer many times. The macOS and Windows paths have not been
run on their target platforms at all -- there is no such machine on the author's
side. This is a harder version of the project's standing verification split:
Substack's rendering needs a human to paste and report, and the author can be
that human, but for these two backends there is nobody. Their tests prove the
right bytes reach the right tool. They do not prove a clipboard was written.
Treat them as untested until somebody reports otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LINUX = "linux"
DARWIN = "darwin"
WINDOWS = "windows"


def current_platform() -> str | None:
    """Which backend this machine gets, or None if nobody has built one.

    Returns None rather than falling back to a default. A backend guessed
    wrong writes nothing and reports success, which on a publishing tool means
    the author pastes whatever was on the clipboard before -- fail closed, and
    let the caller say so out loud.

    Pure: reads `sys.platform` and returns a new value, mutating nothing.
    """
    platform = sys.platform
    if platform.startswith("linux"):
        return LINUX
    if platform == "darwin":
        return DARWIN
    if platform in ("win32", "cygwin", "msys"):
        return WINDOWS
    return None


def ensure_backend() -> None:
    """Exit non-zero unless this platform has a working clipboard tool.

    Separate from `copy_html` so the caller can check before doing the work of
    reading the article and inlining its images. That ordering is not cosmetic:
    a missing tool used to be reported before anything was read, and folding
    the check into the copy would have made a missing `xclip` surface as a file
    error from a later stage instead.
    """
    platform = current_platform()

    if platform is None:
        print(
            f"Error: --copy has no clipboard backend for '{sys.platform}'.\n"
            f"       Supported: Linux (xclip), macOS (osascript), Windows "
            f"(PowerShell).\n"
            f"       Paste article.html by hand instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    if platform == LINUX and not shutil.which("xclip"):
        print(
            "Error: xclip is required for --copy. Install it with:\n"
            "  sudo apt install xclip",
            file=sys.stderr,
        )
        sys.exit(1)

    if platform == DARWIN and not shutil.which("osascript"):
        print(
            "Error: osascript is required for --copy on macOS. It ships with\n"
            "       macOS, so a missing one means PATH is wrong.",
            file=sys.stderr,
        )
        sys.exit(1)

    if platform == WINDOWS and _powershell() is None:
        print(
            "Error: PowerShell is required for --copy on Windows and was not\n"
            "       found on PATH. Paste article.html by hand instead.",
            file=sys.stderr,
        )
        sys.exit(1)


def copy_html(html_content: str) -> None:
    """Put `html_content` on the clipboard as rich text. Fatal on failure.

    A failed body copy is a wasted run -- the author pastes stale content and
    may not notice -- so this exits non-zero rather than warning. That
    asymmetry against `copy_title` is deliberate; see there.
    """
    ensure_backend()
    platform = current_platform()

    if platform == LINUX:
        _copy_html_linux(html_content)
    elif platform == DARWIN:
        _copy_html_macos(html_content)
    elif platform == WINDOWS:
        _copy_html_windows(html_content)
    else:
        print(
            f"Error: --copy has no clipboard backend for '{sys.platform}'.\n"
            f"       Supported: Linux (xclip), macOS (osascript), Windows "
            f"(PowerShell).\n"
            f"       Paste article.html by hand instead.",
            file=sys.stderr,
        )
        sys.exit(1)


def copy_title(title: str) -> None:
    """Hand the resolved title over for Substack's title field.

    Substack does not hoist a leading H1 into its title field -- probed
    directly on 2026-08-08, the heading lands in the body and the title bar
    stays empty. So the title has to be placed by hand, and the question is
    only whether the tool can help.

    On X11 it can: PRIMARY is a second selection independent of CLIPBOARD, so
    one run hands over both -- Ctrl+V for the body, middle-click for the title.

    On macOS and Windows there is exactly one clipboard, and it already holds
    the body. Writing the title there would destroy the payload `copy_html`
    just placed, which is worse than doing nothing, so those platforms print
    and stop. Author's call, 2026-08-10.

    Failure is deliberately non-fatal everywhere: a missing title is an
    inconvenience, a lost body is a wasted run.
    """
    if not title:
        return

    platform = current_platform()

    if platform == LINUX:
        _copy_title_linux(title)
        return

    if platform in (DARWIN, WINDOWS):
        print(
            "  Title above — copy it by hand "
            "(this platform has only one clipboard)"
        )


# --------------------------------------------------------------------------
# Linux / X11 -- xclip. Unchanged behaviour; moved here verbatim.
# --------------------------------------------------------------------------


def _copy_html_linux(html_content: str) -> None:
    if not shutil.which("xclip"):
        print(
            "Error: xclip is required for --copy. Install it with:\n"
            "  sudo apt install xclip",
            file=sys.stderr,
        )
        sys.exit(1)

    failure = _run_xclip(
        ["xclip", "-selection", "clipboard", "-t", "text/html"],
        html_content.encode("utf-8"),
    )
    if failure is not None:
        print(f"Error: clipboard copy failed: {failure}", file=sys.stderr)
        sys.exit(1)

    print("  Body on the clipboard — Ctrl+V into Substack's body")


def _copy_title_linux(title: str) -> None:
    if not shutil.which("xclip"):
        return

    failure = _run_xclip(["xclip", "-selection", "primary"], title.encode("utf-8"))
    if failure is not None:
        print(
            f"Warning: could not put the title on the primary selection: {failure}\n"
            f"         Copy it from the Title line above instead.",
            file=sys.stderr,
        )
        return

    print("  Title on the primary selection — middle-click into the title field")


def _run_xclip(argv: list[str], payload: bytes) -> str | None:
    """Hand `payload` to xclip. Returns None on success, else the error text.

    xclip must not inherit our stdout/stderr. An X11 selection is owned by a
    live process: xclip forks a background child to serve the selection and the
    parent exits immediately. That child keeps any inherited descriptor open
    for as long as it owns the selection, so when our output is a pipe the
    reader never sees EOF and the caller stalls indefinitely -- even though this
    process has already exited. A terminal has no EOF to wait for, which is why
    this only bites scripted use.

    stderr goes to a temp file rather than DEVNULL so xclip's own diagnostics
    survive, and rather than PIPE because reading a pipe to EOF would
    reintroduce the very stall being avoided.
    """
    with tempfile.TemporaryFile() as err_file:
        try:
            subprocess.run(
                argv,
                input=payload,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=err_file,
            )
        except subprocess.CalledProcessError as exc:
            err_file.seek(0)
            detail = err_file.read().decode("utf-8", "replace").strip()
            return detail or str(exc)

    return None


# --------------------------------------------------------------------------
# macOS -- osascript
# --------------------------------------------------------------------------

# AppleScript takes raw four-character type codes between guillemets, which is
# the only way to reach the HTML clipboard flavour from the command line. The
# data is hex, so the script itself stays ASCII apart from the guillemets.
#
# `text:" "` is not decoration. Setting the HTML flavour alone leaves some
# paste targets with nothing to fall back on and they take the clipboard as
# empty; a single-space plain-text flavour alongside it fixes that. Do not
# "tidy" it away.
_MACOS_SCRIPT = 'set the clipboard to {{text:" ", «class HTML»:«data HTML{hex}»}}'


def _copy_html_macos(html_content: str) -> None:
    if not shutil.which("osascript"):
        print(
            "Error: osascript is required for --copy on macOS. It ships with\n"
            "       macOS, so a missing one means PATH is wrong.",
            file=sys.stderr,
        )
        sys.exit(1)

    script = _MACOS_SCRIPT.format(hex=html_content.encode("utf-8").hex())

    # The script goes in on stdin. An article carries its images inlined as
    # base64 data URIs, so as an argv entry it would exceed the argument
    # length limit on any real post.
    try:
        subprocess.run(
            ["osascript", "-"],
            input=script.encode("utf-8"),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
        print(f"Error: clipboard copy failed: {detail or exc}", file=sys.stderr)
        sys.exit(1)

    print("  Body on the clipboard — Cmd+V into Substack's body")


# --------------------------------------------------------------------------
# Windows -- CF_HTML via PowerShell
# --------------------------------------------------------------------------

# CF_HTML's header is a fixed-width ASCII block whose numbers are BYTE offsets
# into the UTF-8 payload. The widths are padded so that filling the numbers in
# cannot change the offsets they describe.
_CF_HTML_HEADER = (
    "Version:0.9\r\n"
    "StartHTML:{start_html:010d}\r\n"
    "EndHTML:{end_html:010d}\r\n"
    "StartFragment:{start_fragment:010d}\r\n"
    "EndFragment:{end_fragment:010d}\r\n"
)
_CF_HTML_PREFIX = "<html><body><!--StartFragment-->"
_CF_HTML_SUFFIX = "<!--EndFragment--></body></html>"


def ascii_escape(html_content: str) -> str:
    """Replace every non-ASCII character with an HTML numeric reference.

    This exists to defuse the bug that rules out `Set-Clipboard -AsHtml`.
    CF_HTML offsets are byte counts into UTF-8, and the whole family of
    failures here -- PowerShell's closed-won't-fix corruption, .NET's
    UTF-16-to-UTF-8 round trip, `len(str)` used where `len(bytes)` was meant --
    comes from character counts and byte counts disagreeing.

    With a pure-ASCII payload they cannot disagree. An em dash travels as
    `&#8212;`, which every rich-text target already understands, and the
    arithmetic downstream becomes impossible to get wrong rather than merely
    written carefully.

    Pure: returns a new string, never mutates the input.
    """
    return "".join(
        char if ord(char) < 128 else f"&#{ord(char)};" for char in html_content
    )


def build_cf_html(fragment: str) -> str:
    """Wrap `fragment` in the CF_HTML clipboard format Windows expects.

    The header is written twice: once with zeroed offsets to measure the real
    byte positions, then again with the measured values. Padding the fields to
    a fixed width is what makes that stable -- the second render is the same
    length as the first, so the offsets it reports are still true of itself.

    Pure: returns a new string, never mutates the input.
    """
    body = _CF_HTML_PREFIX + ascii_escape(fragment) + _CF_HTML_SUFFIX

    header_length = len(
        _CF_HTML_HEADER.format(
            start_html=0, end_html=0, start_fragment=0, end_fragment=0
        ).encode("utf-8")
    )

    prefix_length = len(_CF_HTML_PREFIX.encode("utf-8"))
    body_length = len(body.encode("utf-8"))
    fragment_length = body_length - prefix_length - len(_CF_HTML_SUFFIX.encode("utf-8"))

    return (
        _CF_HTML_HEADER.format(
            start_html=header_length,
            end_html=header_length + body_length,
            start_fragment=header_length + prefix_length,
            end_fragment=header_length + prefix_length + fragment_length,
        )
        + body
    )


def _powershell() -> str | None:
    """Windows PowerShell first, then PowerShell 7.

    Order matters. `powershell.exe` ships with Windows so it is always there,
    and it defaults to the single-threaded apartment the clipboard API
    requires. `pwsh` is the fallback for a machine that has dropped the
    built-in.
    """
    for candidate in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _copy_html_windows(html_content: str) -> None:
    shell = _powershell()
    if shell is None:
        print(
            "Error: PowerShell is required for --copy on Windows and was not\n"
            "       found on PATH. Paste article.html by hand instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = build_cf_html(html_content)

    # Why not `Set-Clipboard -AsHtml`: it corrupts non-ASCII text, and the
    # upstream bug is closed WON'T FIX. This pipeline converts ` -- ` into a
    # real em dash and runs markdown's `smarty` extension, so a corpus article
    # without a single non-ASCII character does not exist -- the broken case is
    # the only case. Do not simplify back to it.
    #
    # .NET does not synthesize the CF_HTML descriptor either; the caller
    # supplies it, which is what build_cf_html is for. Getting that backwards
    # pastes the header into the post as visible text.
    #
    # The payload goes via a file rather than the command line for the same
    # reason as macOS: an article with inlined base64 images is far past any
    # command-length limit.
    handle, path = tempfile.mkstemp(suffix=".html", text=False)
    try:
        with os.fdopen(handle, "wb") as payload_file:
            payload_file.write(payload.encode("ascii"))

        # The path travels in the environment, never spliced into the command.
        # A PowerShell single-quoted string ends at the first quote inside it,
        # and a Windows temp path runs through the user's profile directory --
        # `C:\Users\O'Brien\AppData\Local\Temp\...` is an ordinary name. Escaping
        # by doubling the quote would work and would also be one careful step
        # away from breaking, on the one platform where nobody is watching.
        command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$html = [IO.File]::ReadAllText("
            "$env:OTS_CLIPBOARD_PAYLOAD, [Text.Encoding]::UTF8); "
            "[System.Windows.Forms.Clipboard]::SetText("
            "$html, [System.Windows.Forms.TextDataFormat]::Html)"
        )

        try:
            subprocess.run(
                [shell, "-NoProfile", "-NonInteractive", "-Command", command],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env={**os.environ, "OTS_CLIPBOARD_PAYLOAD": path},
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
            print(f"Error: clipboard copy failed: {detail or exc}", file=sys.stderr)
            sys.exit(1)
    finally:
        Path(path).unlink(missing_ok=True)

    print("  Body on the clipboard — Ctrl+V into Substack's body")

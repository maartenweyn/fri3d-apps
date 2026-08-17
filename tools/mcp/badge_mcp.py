#!/usr/bin/env python3
"""MCP server that exposes the Fri3d badge over USB serial.

This runs on the Mac, which is the only machine that actually sees
/dev/cu.usbmodem*, so an agent working in a sandbox can talk to the badge
directly instead of asking a human to copy output back and forth.

Everything goes through mpremote. A serial port takes one client at a time,
so close the Fri3d-IDE tab and any open REPL before using these tools.
"""

import os
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO = Path(os.environ.get("FRI3D_REPO", Path(__file__).resolve().parents[2]))
MPREMOTE = os.environ.get("MPREMOTE") or shutil.which("mpremote") or "mpremote"
DEFAULT_APP = os.environ.get("FRI3D_APP", "be.fri3d.pomodoro")
DEFAULT_TIMEOUT = 60

mcp = FastMCP("fri3d-badge")


class BadgeError(RuntimeError):
    pass


def _run(args, timeout=DEFAULT_TIMEOUT):
    cmd = [MPREMOTE] + args
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                              text=True, timeout=timeout)
    except FileNotFoundError:
        raise BadgeError(
            "mpremote not found at %r. Install it with:\n"
            "    pip3 install --user mpremote\n"
            "or point the MPREMOTE environment variable at it." % MPREMOTE)
    except subprocess.TimeoutExpired:
        raise BadgeError("timed out after %s s: %s" % (timeout, " ".join(cmd)))

    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        low = output.lower()
        hint = ""
        if ("no device" in low or "could not open" in low
                or "failed to access" in low or "resource busy" in low):
            hint = ("\n\nThe badge may be unplugged, or another program is "
                    "holding the serial port: close the Fri3d-IDE tab and any "
                    "open REPL, then try again.")
        raise BadgeError("mpremote exited %d\n\n%s%s"
                         % (proc.returncode, output or "<no output>", hint))
    return output or "<no output>"


def _repo_path(relative):
    path = (REPO / relative).resolve()
    if path != REPO and REPO not in path.parents:
        raise BadgeError("path escapes the repository: %s" % relative)
    if not path.exists():
        raise BadgeError("no such file in the repository: %s" % path)
    return path


def _rmtree_code(remote_path):
    return (
        "import os\n"
        "def rmtree(p):\n"
        "    try:\n"
        "        mode = os.stat(p)[0]\n"
        "    except OSError:\n"
        "        print('not present:', p)\n"
        "        return\n"
        "    if mode & 0x4000:\n"
        "        for e in os.listdir(p):\n"
        "            rmtree(p + '/' + e)\n"
        "        os.rmdir(p)\n"
        "    else:\n"
        "        os.remove(p)\n"
        "rmtree(%r)\n"
        "print('removed', %r)\n" % (remote_path, remote_path))


# --------------------------------------------------------------------------- tools

@mcp.tool()
def badge_ports() -> str:
    """List the serial ports mpremote can see. Run this first when something fails."""
    return _run(["connect", "list"], timeout=20)


@mcp.tool()
def badge_exec(code: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run MicroPython source on the badge and return everything it prints.

    This is the workhorse: use it to inspect modules, poke at hardware, or
    reproduce an error with a full traceback.
    """
    return _run(["exec", code], timeout=timeout)


@mcp.tool()
def badge_run_file(path: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run a .py file from the repository on the badge, for example tools/probe.py."""
    return _run(["run", str(_repo_path(path))], timeout=timeout)


@mcp.tool()
def badge_ls(path: str = "/apps") -> str:
    """List a directory on the badge, with a type marker and file sizes."""
    code = (
        "import os\n"
        "p = %r\n"
        "try:\n"
        "    names = sorted(os.listdir(p))\n"
        "except OSError as e:\n"
        "    print('cannot list', p, e)\n"
        "else:\n"
        "    for n in names:\n"
        "        st = os.stat(p + '/' + n)\n"
        "        print(('d' if st[0] & 0x4000 else '-'), '%%-24s' %% n, st[6])\n"
        % path)
    return _run(["exec", code])


@mcp.tool()
def badge_read(path: str, max_bytes: int = 20000) -> str:
    """Read a text file off the badge."""
    code = (
        "with open(%r) as f:\n"
        "    data = f.read(%d)\n"
        "print(data)\n" % (path, max_bytes))
    return _run(["exec", code])


@mcp.tool()
def badge_install(app: str = DEFAULT_APP, clean: bool = True) -> str:
    """Copy an app folder from the repository into /apps and refresh the launcher.

    With clean=True the app is removed from the badge first, which also clears
    out any stale files a previous install left behind.
    """
    source = _repo_path(app)
    if not source.is_dir():
        raise BadgeError("%s is not a folder" % source)
    stale = [p.name for p in source.iterdir() if p.name == "__pycache__"]
    if stale:
        raise BadgeError(
            "%s contains __pycache__; remove it before installing, it would be "
            "copied onto the badge and can shadow your .py files" % app)

    log = []
    if clean:
        log.append(_run(["exec", _rmtree_code("/apps/" + app)]))
    try:
        _run(["mkdir", ":/apps"], timeout=20)
    except BadgeError:
        pass  # already exists
    log.append(_run(["fs", "cp", "-r", str(source), ":/apps/"], timeout=180))
    log.append(badge_refresh())
    return "\n".join(log)


@mcp.tool()
def badge_uninstall(app: str) -> str:
    """Remove one app from /apps on the badge."""
    return _run(["exec", _rmtree_code("/apps/" + app)])


@mcp.tool()
def badge_wipe() -> str:
    """Remove every user-installed app from /apps. Built-in apps are untouched."""
    return _run(["run", str(_repo_path("tools/wipe_apps.py"))], timeout=120)


@mcp.tool()
def badge_refresh() -> str:
    """Rescan /apps so the launcher notices newly installed apps."""
    code = (
        "from mpos import AppManager\n"
        "AppManager.refresh_apps()\n"
        "print('launcher sees:', sorted(a.fullname for a in AppManager.get_app_list()))\n")
    return _run(["exec", code])


@mcp.tool()
def badge_start_app(app: str = DEFAULT_APP) -> str:
    """Launch an app on the badge, as the launcher would."""
    code = ("from mpos import AppManager\n"
            "AppManager.start_app(%r)\n"
            "print('started', %r)\n" % (app, app))
    return _run(["exec", code])


@mcp.tool()
def badge_reset() -> str:
    """Reboot the badge. App discovery also runs at boot."""
    return _run(["reset"], timeout=20)


@mcp.tool()
def badge_diag(app: str = DEFAULT_APP) -> str:
    """Full diagnosis of why an app will not load: files, manifest, frameworks,
    lvgl symbols, then import and construct each activity with a real traceback."""
    return _run(["exec", "APP_ID=%r" % app, "run", str(_repo_path("tools/diag.py"))],
                timeout=120)


if __name__ == "__main__":
    mcp.run()

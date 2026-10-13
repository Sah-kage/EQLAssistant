"""Paths and process helpers that work both from source and as a PyInstaller .exe."""
import os
import subprocess
import sys

FROZEN = getattr(sys, "frozen", False)
ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
ICON = os.path.join(ROOT, "assets", "icon.ico")      # the wizard


def set_app_id():
    """Windows: give the app its own taskbar identity, so the taskbar shows the wizard
    icon instead of Python's when running from source."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EQLAssistant.App")
        except Exception:
            pass

_overlay_procs = {}
OVERLAY_KINDS = ("dps", "motes", "crawl")


def open_overlay_window(url, kind="dps"):
    """Start an always-on-top overlay window ("dps", "motes" or "crawl") as its own process."""
    p = _overlay_procs.get(kind)
    if p is not None and p.poll() is None:
        return
    if FROZEN:
        cmd = [sys.executable, "--overlay-only", "--kind", kind, "--url", url]
    else:
        exe = sys.executable
        if sys.platform == "win32" and exe.lower().endswith("python.exe"):
            alt = exe[:-10] + "pythonw.exe"
            exe = alt if os.path.exists(alt) else exe
        cmd = [exe, os.path.join(ROOT, "main.py"), "--overlay-only", "--kind", kind, "--url", url]
    flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
    _overlay_procs[kind] = subprocess.Popen(cmd, creationflags=flags, close_fds=True)


def overlay_running(kind):
    p = _overlay_procs.get(kind)
    return p is not None and p.poll() is None


def close_overlay_window(kind=None):
    for k, p in list(_overlay_procs.items()):
        if (kind is None or k == kind) and p.poll() is None:
            p.terminate()


def log_path():
    from .core import data_dir
    return os.path.join(data_dir(), "eqlassistant.log")


def log(msg):
    """Startup / window problems go to EQLAssistant's data folder (the .exe has no console)."""
    import time as _t
    try:
        p = log_path()
        if os.path.exists(p) and os.path.getsize(p) > 512 * 1024:
            os.replace(p, p + ".old")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(_t.strftime("%Y-%m-%d %H:%M:%S ") + str(msg).rstrip() + "\n")
    except Exception:
        pass


def notify(msg, title="EQL Assistant"):
    """Show a message even when there is no console window (windowed .exe)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, title, 0x40)
            return
        except Exception:
            pass
    print(msg)

"""Logging and crash reports.

Everything goes to the "logs" folder in EQL Assistant's data folder
(%APPDATA%\\EQLAssistant\\logs):

  eqlassistant.log           the running log (verbose by default: Settings > Logging), rotated at 2 MB, 5 kept
  crash-YYYYMMDD-HHMMSS.txt  one report per crash or failed start, with everything needed to see why:
                             what the app was doing, the full error, the version, Windows, Python and
                             library versions, the settings (nothing secret), and the last log lines
  native-crash.log           Python's fault handler output, for hard crashes inside Windows / the app
                             window's browser engine that Python can't catch

A crash that kills the process outright (power cut, killed in Task Manager, a native crash) leaves
the "running" marker behind; the next start notices and writes a crash report for the last session.
"""
import collections
import faulthandler
import json
import logging
import logging.handlers
import os
import platform
import sys
import threading
import time
import traceback

LOGGER = logging.getLogger("eqla")
LOGGER.addHandler(logging.NullHandler())          # silent until setup() (e.g. in tests)
_recent = collections.deque(maxlen=400)          # the last log lines, for crash reports
_state = {"dir": None, "stage": "starting", "fault_fh": None, "configured": False}
_lock = threading.Lock()


class _Recent(logging.Handler):
    def emit(self, record):
        try:
            _recent.append(self.format(record))
        except Exception:
            pass


FMT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"


def log_dir():
    if _state["dir"]:
        return _state["dir"]
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = os.path.join(base, "EQLAssistant", "logs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        import tempfile
        d = os.path.join(tempfile.gettempdir(), "EQLAssistant-logs")
        os.makedirs(d, exist_ok=True)
    _state["dir"] = d
    return d


def log_path():
    return os.path.join(log_dir(), "eqlassistant.log")


def setup(verbose=True, process="app", folder=None):
    """Start logging to the log file. Safe to call more than once (later calls change the level)."""
    with _lock:
        if folder:
            _state["dir"] = folder
            os.makedirs(folder, exist_ok=True)
        level = logging.DEBUG if verbose else logging.INFO
        if not _state["configured"]:
            fmt = logging.Formatter(FMT)
            name = "eqlassistant.log" if process == "app" else f"overlay-{process}.log"
            try:
                fh = logging.handlers.RotatingFileHandler(os.path.join(log_dir(), name), maxBytes=2 * 1024 * 1024,
                                                          backupCount=5, encoding="utf-8", delay=True)
                fh.setFormatter(fmt)
                LOGGER.addHandler(fh)
            except OSError:
                pass
            rec = _Recent()
            rec.setFormatter(fmt)
            LOGGER.addHandler(rec)
            if sys.stderr and not getattr(sys, "frozen", False):
                sh = logging.StreamHandler()
                sh.setFormatter(fmt)
                sh.setLevel(logging.INFO)
                LOGGER.addHandler(sh)
            LOGGER.propagate = False
            _install_hooks(process)
            _state["configured"] = True
        LOGGER.setLevel(level)
    return LOGGER


def set_verbose(on):
    LOGGER.setLevel(logging.DEBUG if on else logging.INFO)
    LOGGER.info("verbose logging %s", "on" if on else "off")


def stage(what):
    """What the app is doing right now (shown in crash reports)."""
    _state["stage"] = what
    LOGGER.debug("stage: %s", what)


def get(name):
    return LOGGER.getChild(name)


# ----------------------------------------------------------------------------- hooks
def _install_hooks(process):
    def excepthook(et, ev, tb):
        if issubclass(et, KeyboardInterrupt):
            return sys.__excepthook__(et, ev, tb)
        crash_report("Unhandled error", exc=(et, ev, tb), process=process)
        sys.__excepthook__(et, ev, tb)
    sys.excepthook = excepthook

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        crash_report(f"Unhandled error in background thread {name!r}",
                     exc=(args.exc_type, args.exc_value, args.exc_traceback), process=process, fatal=False)
    threading.excepthook = thread_hook

    # Native crashes (inside Windows, the app window's browser engine...): Python's fault handler
    try:
        fh = open(os.path.join(log_dir(), "native-crash.log" if process == "app" else f"native-crash-{process}.log"),
                  "a", encoding="utf-8")
        fh.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {process} started (pid {os.getpid()}) ===\n")
        fh.flush()
        faulthandler.enable(file=fh, all_threads=True)
        _state["fault_fh"] = fh
    except Exception:
        pass


# ----------------------------------------------------------------------------- crash reports
def system_info():
    from . import __version__
    info = {
        "EQL Assistant": __version__,
        "Running as": "EQLAssistant.exe" if getattr(sys, "frozen", False) else "from source (python main.py)",
        "Program": sys.executable,
        "Arguments": " ".join(sys.argv[1:]) or "(none)",
        "Windows / OS": f"{platform.platform()} ({platform.machine()})",
        "Python": sys.version.split()[0],
        "Process id": os.getpid(),
        "Data folder": os.path.dirname(log_dir()),
        "Time": time.strftime("%Y-%m-%d %H:%M:%S %z"),
    }
    for mod in ("webview", "PIL"):
        try:
            m = __import__(mod)
            info[f"{mod} version"] = getattr(m, "__version__", "?")
        except Exception as e:
            info[f"{mod} version"] = f"not available ({e.__class__.__name__}: {e})"
    try:
        from .gui import webview2_installed
        info["Edge WebView2 Runtime"] = "installed" if webview2_installed() else "NOT FOUND (the app window needs it)"
    except Exception:
        pass
    return info


SECRET_WORDS = ("password", "secret", "token", "key")


def _settings():
    """config.json without anything secret, for the report."""
    try:
        p = os.path.join(os.path.dirname(log_dir()), "config.json")
        with open(p, encoding="utf-8") as fh:
            cfg = json.load(fh)
        clean = {k: ("(hidden)" if any(w in k.lower() for w in SECRET_WORDS) else v) for k, v in cfg.items()}
        clean.pop("timers", None)
        return json.dumps(clean, indent=1, default=str)[:6000]
    except Exception as e:
        return f"(couldn't read config.json: {e})"


def crash_report(what, detail="", exc=None, process="app", fatal=True, extra=None):
    """Write a crash / failed-start report and return its path."""
    try:
        if exc is None and sys.exc_info()[0] is not None:
            exc = sys.exc_info()
        tb = "".join(traceback.format_exception(*exc)) if exc else "(no Python error: see the details above)"
        LOGGER.error("%s%s\n%s", what, f": {detail}" if detail else "", tb if exc else "")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(log_dir(), f"crash-{stamp}{'' if process == 'app' else '-' + process}.txt")
        lines = [
            "EQL Assistant crash report",
            "==========================",
            f"What happened : {what}",
            f"Fatal         : {'yes, the app closed / could not start' if fatal else 'no, the app kept running'}",
            f"While         : {_state['stage']}",
            f"Process       : {process}",
        ]
        if detail:
            lines += ["", "Details", "-------", str(detail).rstrip()]
        lines += ["", "Error", "-----", tb.rstrip(), "", "System", "------"]
        lines += [f"{k:<22}: {v}" for k, v in system_info().items()]
        if extra:
            lines += ["", "More", "----"] + [f"{k:<22}: {v}" for k, v in extra.items()]
        lines += ["", "Settings (config.json, secrets hidden)", "--------------------------------------", _settings()]
        lines += ["", "Threads at the time", "-------------------"]
        for th in threading.enumerate():
            lines.append(f"  {th.name} (daemon={th.daemon}, alive={th.is_alive()})")
        lines += ["", f"Last {len(_recent)} log lines", "-------------------"] + list(_recent)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(str(x) for x in lines) + "\n")
        _prune()
        return path
    except Exception:
        return None


def _prune(keep=30):
    try:
        reps = sorted(f for f in os.listdir(log_dir()) if f.startswith("crash-"))
        for f in reps[:-keep]:
            os.remove(os.path.join(log_dir(), f))
    except OSError:
        pass


def crash_reports():
    try:
        return sorted((f for f in os.listdir(log_dir()) if f.startswith("crash-")), reverse=True)
    except OSError:
        return []


# ----------------------------------------------------------------------------- "did the last run end properly?"
def _marker():
    return os.path.join(log_dir(), "running.json")


def session_started():
    """Call once at start. Returns the crash report path if the last session never closed properly."""
    report = None
    try:
        with open(_marker(), encoding="utf-8") as fh:
            last = json.load(fh)
    except (OSError, ValueError):
        last = None
    if last:
        native = ""
        try:
            with open(os.path.join(log_dir(), "native-crash.log"), encoding="utf-8", errors="replace") as fh:
                native = fh.read()[-8000:]
        except OSError:
            pass
        prev = ""
        try:
            with open(log_path(), encoding="utf-8", errors="replace") as fh:
                prev = "".join(fh.readlines()[-150:])
        except OSError:
            pass
        report = crash_report(
            "The last session of EQL Assistant ended without closing properly (crashed, was killed, or the PC "
            "shut down)",
            detail=f"It started {last.get('started')} (version {last.get('version')}, pid {last.get('pid')}) and was "
                   f"last doing: {last.get('stage', '?')}.\n\nWhat Python's fault handler caught (native-crash.log, "
                   f"last part):\n{native or '(nothing)'}\n\nThe last lines of that session's log:\n{prev or '(none)'}",
            fatal=False)
    try:
        from . import __version__
        with open(_marker(), "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S"), "version": __version__,
                       "stage": _state["stage"]}, fh)
    except OSError:
        pass
    return report


def session_note(stage_text):
    """Keep the marker's 'last doing' up to date (cheap; called at a few milestones)."""
    stage(stage_text)
    try:
        with open(_marker(), encoding="utf-8") as fh:
            d = json.load(fh)
        d["stage"] = stage_text
        with open(_marker(), "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except (OSError, ValueError):
        pass


def session_ended():
    LOGGER.info("EQL Assistant closed normally")
    try:
        os.remove(_marker())
    except OSError:
        pass

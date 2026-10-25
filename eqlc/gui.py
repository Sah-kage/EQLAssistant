"""Native desktop window for the dashboard (pywebview + Windows' built-in Edge WebView2).

If pywebview isn't installed or can't start, main.py falls back to the browser.
"""
import os
import sys


WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
_WEBVIEW2_KEY = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def available():
    try:
        import webview  # noqa: F401
        return True
    except Exception as e:
        from .launch import log
        log(f"app window library not available: {e!r}")
        return False


def webview2_installed():
    """The app window needs Microsoft's Edge WebView2 Runtime (built into Windows 11 and most
    up-to-date Windows 10 PCs). Without it the window can't open."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
    except ImportError:
        return True
    places = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + _WEBVIEW2_KEY[8:]),
              (winreg.HKEY_LOCAL_MACHINE, _WEBVIEW2_KEY),
              (winreg.HKEY_CURRENT_USER, _WEBVIEW2_KEY)]
    for root, key in places:
        try:
            with winreg.OpenKey(root, key) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def _marker(app):
    return os.path.join(app.ddir, "window_starting")


def crashed_last_time(app):
    """True if the last attempt to open the app window never got as far as showing it
    (e.g. the program closed straight away). Then we use the web browser instead."""
    return os.path.exists(_marker(app))


class Api:
    """Functions the dashboard can call from JavaScript (window.pywebview.api.*)."""

    def __init__(self, app):
        self._app = app
        self._window = None

    def pick_folder(self, start=""):
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if kind is None:
            kind = getattr(webview, "FOLDER_DIALOG", 20)
        start = start if start and os.path.isdir(start) else ""
        res = self._window.create_file_dialog(kind, directory=start)
        if not res:
            return ""
        return res[0] if isinstance(res, (list, tuple)) else str(res)

    def open_folder(self, path):
        if path and os.path.isdir(path) and sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - opens Explorer on the user's own folder
        return True


def _set_window_icon(win):
    """Put the wizard on the title bar and taskbar button (Windows / WinForms backend)."""
    from .launch import ICON
    if sys.platform != "win32" or not os.path.exists(ICON):
        return
    try:
        import clr  # pythonnet, which pywebview uses on Windows
        clr.AddReference("System.Drawing")
        from System import Action
        from System.Drawing import Icon
        form = win.native
        if form is None:
            return
        icon = Icon(ICON)

        def apply():
            form.Icon = icon
        if getattr(form, "InvokeRequired", False):
            form.Invoke(Action(apply))
        else:
            apply()
    except Exception:
        pass


def run(app, url, on_close=None):
    """Open the app window and block until it is closed. Returns False if it couldn't start."""
    try:
        import webview
    except Exception:
        return False
    from .launch import log
    api = Api(app)
    shown = {"ok": False}
    marker = _marker(app)
    try:
        with open(marker, "w") as fh:
            fh.write("starting")
    except OSError:
        pass

    def on_shown():
        shown["ok"] = True
        try:
            os.remove(marker)
        except OSError:
            pass
        _set_window_icon(win)
    try:
        win = webview.create_window(
            "EQL Assistant", url, js_api=api,
            width=1320, height=860, min_size=(960, 620), background_color="#0e1013")
        api._window = win
        app.gui_window = win
        if on_close:
            win.events.closed += on_close
        win.events.shown += on_shown
        storage = os.path.join(app.ddir, "webview")
        os.makedirs(storage, exist_ok=True)
        from .launch import ICON
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True       # "Download a copy" of a crawl proof
        except Exception:
            pass
        # Windows: only Edge WebView2. Without this pywebview may fall back to the old
        # Internet Explorer engine, which can't run the app's page.
        gui_name = "edgechromium" if sys.platform == "win32" else None
        try:
            webview.start(gui=gui_name, private_mode=False, storage_path=storage, icon=ICON)
        except TypeError:                     # older pywebview without icon=
            webview.start(gui=gui_name, private_mode=False, storage_path=storage)
        if not shown["ok"]:
            log("app window closed without ever showing; falling back to the web browser")
            app.window_error = ("The app window closed before it ever showed. This usually means the Microsoft Edge "
                                "WebView2 Runtime is missing or broken.")
            return False
        return True
    except Exception as e:  # e.g. WebView2 runtime missing
        import traceback
        app.window_error = traceback.format_exc()
        log("app window failed: " + app.window_error)
        app.status = f"app window failed ({e}); using browser"
        return False
    finally:
        # Got this far (shown or failed cleanly), so the program didn't crash: clear the marker.
        try:
            os.remove(marker)
        except OSError:
            pass

"""Native desktop window for the dashboard (pywebview + Windows' built-in Edge WebView2).

If pywebview isn't installed or can't start, main.py falls back to the browser.
"""
import os
import sys


def available():
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


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
    api = Api(app)
    try:
        win = webview.create_window(
            "EQL Assistant", url, js_api=api,
            width=1320, height=860, min_size=(960, 620), background_color="#0e1013")
        api._window = win
        app.gui_window = win
        if on_close:
            win.events.closed += on_close
        win.events.shown += lambda: _set_window_icon(win)
        storage = os.path.join(app.ddir, "webview")
        os.makedirs(storage, exist_ok=True)
        from .launch import ICON
        try:
            webview.start(private_mode=False, storage_path=storage, icon=ICON)
        except TypeError:                     # older pywebview without icon=
            webview.start(private_mode=False, storage_path=storage)
        return True
    except Exception as e:  # e.g. WebView2 runtime missing
        app.status = f"app window failed ({e}); using browser"
        return False

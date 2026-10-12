"""EQL Assistant - DPS parser, overlay and Plane of Sky tracker for EverQuest Legends.

Usage (from source or as EQLAssistant.exe):
    main.py                       open the app window and the in-game overlay
    main.py --log-dir "C:\\...\\Logs"
    main.py --no-overlay          don't open the in-game overlay window
    main.py --browser             use your web browser instead of the app window
    main.py --overlay-only        just the overlay window (app must already be running)
"""
import argparse
import sys
import threading
import time
import urllib.request
import webbrowser


def main():
    ap = argparse.ArgumentParser(description="EQL Assistant")
    ap.add_argument("--log-dir", help="EverQuest Legends Logs folder")
    ap.add_argument("--port", type=int)
    ap.add_argument("--no-overlay", action="store_true", help="don't open the in-game overlay window")
    ap.add_argument("--browser", action="store_true", help="use the web browser instead of the app window")
    ap.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--overlay-only", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--url", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--kind", default="dps", help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.overlay_only:
        import overlay_window
        overlay_window.run(a.url or f"http://127.0.0.1:{a.port or 7377}", a.kind)
        return

    from eqlc import gui
    from eqlc.core import App
    from eqlc.launch import close_overlay_window, notify, open_overlay_window, set_app_id
    set_app_id()
    from eqlc.server import serve

    app = App(log_dir=a.log_dir)
    if a.port:
        app.cfg["port"] = a.port
    if a.log_dir:
        app.save_cfg()
    url = f"http://127.0.0.1:{app.cfg['port']}"

    try:
        srv = serve(app)
    except OSError:
        try:
            urllib.request.urlopen(url + "/api/settings", timeout=2)
            notify("EQL Assistant is already running.\n\nLook for its window on the taskbar.")
        except Exception:
            notify(f"Port {app.cfg['port']} is being used by another program.\n"
                   f"Start EQL Assistant with --port 7378 to use a different one.")
        sys.exit(1)

    print("=" * 60)
    print(f" EQL Assistant running at {url}")
    print(f" Log folder: {app.cfg['log_dir'] or '(not set - choose it in Settings)'}")
    print("=" * 60)

    app.start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not a.no_overlay:
        if app.cfg.get("overlay_on_start", True):
            open_overlay_window(url, "dps")
        if app.cfg.get("motes_window_on_start", True):
            open_overlay_window(url, "motes")
        if app.cfg.get("crawl_window_on_start", True):
            open_overlay_window(url, "crawl")

    def shutdown():
        close_overlay_window()
        app.stop()
        srv.shutdown()

    # Preferred: a real desktop window. Blocks until the user closes it.
    if not a.browser and not a.no_browser and gui.available():
        if gui.run(app, url):
            shutdown()
            return

    # Fallback: dashboard in the web browser, console keeps the app alive.
    if not a.no_browser:
        webbrowser.open(url)
    try:
        while True:                     # sleep loop so Ctrl+C works on Windows
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()

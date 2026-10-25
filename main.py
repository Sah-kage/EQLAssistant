"""EQL Assistant - DPS parser, overlay and Plane of Sky tracker for EverQuest Legends.

Usage (from source or as EQLAssistant.exe):
    main.py                       open the app window and the in-game overlay
    main.py --log-dir "C:\\...\\Logs"
    main.py --no-overlay          don't open the in-game overlay window
    main.py --browser             use your web browser instead of the app window
    main.py --overlay-only        just the overlay window (app must already be running)
"""
import argparse
import os
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
    from eqlc import logs

    if a.overlay_only:
        logs.setup(verbose=_verbose_setting(), process=a.kind)
        logs.LOGGER.info("overlay window %s starting (%s)", a.kind, a.url)
        import overlay_window
        try:
            overlay_window.run(a.url or f"http://127.0.0.1:{a.port or 7377}", a.kind)
        except Exception:
            logs.crash_report(f"The {a.kind} overlay window crashed", process=a.kind)
            raise SystemExit(1)
        logs.LOGGER.info("overlay window %s closed", a.kind)
        return

    logs.setup(verbose=_verbose_setting())
    logs.stage("starting")
    log_ = logs.LOGGER
    log_.info("=" * 70)
    log_.info("EQL Assistant starting")
    for k, v in logs.system_info().items():
        log_.info("  %-22s %s", k + ":", v)
    last = logs.session_started()
    if last:
        log_.warning("the last session didn't close properly; report: %s", last)

    from eqlc import gui
    from eqlc.core import App
    from eqlc.launch import close_overlay_window, log, log_path, notify, open_overlay_window, set_app_id
    set_app_id()
    from eqlc.server import serve

    logs.stage("loading settings and saved data")
    app = App(log_dir=a.log_dir)
    app.last_crash = last
    logs.set_verbose(app.cfg.get("verbose_logging", True))
    if a.port:
        app.cfg["port"] = a.port
    if a.log_dir:
        app.save_cfg()
    url = f"http://127.0.0.1:{app.cfg['port']}"
    log_.info("data folder %s, log folder %s, %s character log(s), port %s", app.ddir, app.cfg["log_dir"] or "(not set)",
              len(app.log_chars()), app.cfg["port"])

    logs.stage(f"starting the dashboard server on port {app.cfg['port']}")
    try:
        srv = serve(app)
    except OSError as e:
        try:
            urllib.request.urlopen(url + "/api/settings", timeout=2)
            log_.info("another EQL Assistant is already running on %s; this one closes", url)
            notify("EQL Assistant is already running.\n\nLook for its window on the taskbar.")
            logs.session_ended()
        except Exception:
            rep = logs.crash_report("EQL Assistant couldn't start: its port is in use",
                                    detail=f"Port {app.cfg['port']} on 127.0.0.1 is used by another program ({e}).")
            notify(f"Port {app.cfg['port']} is being used by another program.\n"
                   f"Start EQL Assistant with --port 7378 to use a different one.\n\nDetails: {rep}")
            logs.session_ended()
        sys.exit(1)

    print("=" * 60)
    print(f" EQL Assistant running at {url}")
    print(f" Log folder: {app.cfg['log_dir'] or '(not set - choose it in Settings)'}")
    print("=" * 60)

    app.start()
    app.updates.start()                    # looks for a newer version on GitHub
    threading.Thread(target=srv.serve_forever, daemon=True, name="dashboard-server").start()
    log_.info("dashboard running at %s", url)
    if not a.no_overlay:
        if app.cfg.get("overlay_on_start", True):
            open_overlay_window(url, "dps")
        if app.cfg.get("motes_window_on_start", True):
            open_overlay_window(url, "motes")
        if app.cfg.get("crawl_window_on_start", True):
            open_overlay_window(url, "crawl")

    def shutdown():
        logs.stage("closing")
        close_overlay_window()
        app.stop()
        srv.shutdown()
        logs.session_ended()

    # Preferred: a real desktop window. Blocks until the user closes it.
    use_window = not a.browser and not a.no_browser and not app.cfg.get("use_browser")
    no_webview2 = use_window and not gui.webview2_installed()
    if no_webview2:
        log("Edge WebView2 Runtime not found in the registry; trying the app window anyway")
    if use_window and gui.crashed_last_time(app):
        # the last start closed while opening the window (crashed): use the browser from now on
        log("app window crashed last time; switching to the web browser")
        try:
            os.remove(os.path.join(app.ddir, "window_starting"))
        except OSError:
            pass
        app.cfg["use_browser"] = True
        app.save_cfg()
        notify("EQL Assistant closed while opening its app window last time, so it will use your web browser "
               "from now on. Everything works the same there.\n\n"
               "To try the app window again, untick \"Open in my web browser\" in Settings." +
               (f"\n\nThe app window needs the Microsoft Edge WebView2 Runtime (free from Microsoft):\n"
                f"{gui.WEBVIEW2_URL}" if no_webview2 else ""))
        use_window = False
    if use_window and gui.available():
        logs.session_note("opening the app window")
        if gui.run(app, url):
            shutdown()
            return
        rep = logs.crash_report("The app window couldn't open, so EQL Assistant switched to the web browser",
                                detail=getattr(app, "window_error", "") or "The window closed without ever showing.",
                                fatal=False)
        log_.warning("app window failed; report %s", rep)
        app.cfg["use_browser"] = True          # don't keep trying (and failing) every start
        app.save_cfg()
        notify("EQL Assistant couldn't open its own window, so it's opening in your web browser instead. "
               "Everything works the same there, and it will use the browser from now on "
               "(untick \"Open in my web browser\" in Settings to try the app window again).\n\n" +
               ("The app window needs the Microsoft Edge WebView2 Runtime, which doesn't seem to be installed. "
                f"It's free from Microsoft:\n{gui.WEBVIEW2_URL}\n\n" if no_webview2 else "") +
               f"Details are in {log_path()}")

    # Fallback: dashboard in the web browser, console keeps the app alive.
    logs.session_note("running in the web browser")
    if not a.no_browser:
        log_.info("opening the dashboard in the web browser")
        webbrowser.open(url)
    try:
        while True:                     # sleep loop so Ctrl+C works on Windows
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


def _verbose_setting():
    """Settings > Logging > verbose (on unless turned off), read before anything else starts."""
    import json
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
        with open(os.path.join(base, "EQLAssistant", "config.json"), encoding="utf-8") as fh:
            return bool(json.load(fh).get("verbose_logging", True))
    except Exception:
        return True


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:                   # the .exe has no console: never fail silently
        import traceback
        err = traceback.format_exc()
        try:
            from eqlc import logs
            from eqlc.launch import notify
            logs.setup()
            rep = logs.crash_report("EQL Assistant crashed" if logs._state["stage"] != "starting"
                                    else "EQL Assistant failed to start")
            notify("EQL Assistant hit a problem and had to close.\n\n"
                   f"A crash report with the full details was saved to:\n{rep}\n\n"
                   "Please send that file to the developer. Starting with --browser may get you going meanwhile.")
            logs.session_ended()
        except Exception:
            print(err)
        sys.exit(1)

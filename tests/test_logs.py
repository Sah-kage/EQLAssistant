"""Logging and crash reports.  Run: python -m unittest discover tests"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from eqlc import logs   # noqa: E402


class CrashReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = logs._state["dir"]
        logs._state["dir"] = os.path.join(self.tmp, "logs")
        os.makedirs(logs._state["dir"])

    def tearDown(self):
        logs._state["dir"] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_report_has_everything(self):
        with open(os.path.join(self.tmp, "config.json"), "w") as fh:
            json.dump({"log_dir": "C:/EQ/Logs", "leaderboard_url": "https://x", "secret_key": "abc"}, fh)
        logs._recent.append("2026-10-25 21:00:00 INFO earlier line")
        logs.stage("reading the logs")
        try:
            {}["missing"]
        except KeyError:
            path = logs.crash_report("Test crash", detail="extra words")
        text = open(path, encoding="utf-8").read()
        for part in ("What happened : Test crash", "While         : reading the logs", "extra words",
                     "KeyError: 'missing'", "EQL Assistant", "Windows / OS", "Python", "C:/EQ/Logs",
                     "earlier line", "Threads at the time"):
            self.assertIn(part, text)
        self.assertNotIn("abc", text)                                   # secrets hidden
        self.assertIn(os.path.basename(path), logs.crash_reports())

    def test_unclean_last_session(self):
        self.assertIsNone(logs.session_started())                      # first start: nothing to report
        rep = logs.session_started()                                   # marker left behind = didn't close
        self.assertTrue(rep and "ended without closing properly" in open(rep, encoding="utf-8").read())
        logs.session_ended()
        self.assertIsNone(logs.session_started())
        logs.session_ended()

    def test_background_thread_crash(self):
        hook = threading.excepthook
        try:
            logs._install_hooks("test")
            t = threading.Thread(target=lambda: 1 / 0, name="worker")
            t.start()
            t.join()
            reps = logs.crash_reports()
            self.assertTrue(reps)
            text = open(os.path.join(logs.log_dir(), reps[0]), encoding="utf-8").read()
            self.assertIn("background thread 'worker'", text)
            self.assertIn("ZeroDivisionError", text)
            self.assertIn("no, the app kept running", text)
        finally:
            threading.excepthook = hook
            sys.excepthook = sys.__excepthook__


class StartupTests(unittest.TestCase):
    """Runs main.py for real, with its data in a temporary folder."""
    def run_main(self, cfg, *args):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        d = os.path.join(tmp, "EQLAssistant")
        os.makedirs(d)
        with open(os.path.join(d, "config.json"), "w") as fh:
            json.dump(cfg, fh)
        env = dict(os.environ, APPDATA=tmp)
        p = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"), "--browser", "--no-overlay", *args],
                           env=env, capture_output=True, text=True, timeout=60, cwd=tmp)
        logdir = os.path.join(d, "logs")
        reps = sorted(f for f in os.listdir(logdir) if f.startswith("crash-")) if os.path.isdir(logdir) else []
        return p, logdir, [open(os.path.join(logdir, r), encoding="utf-8").read() for r in reps]

    def test_port_in_use(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        self.addCleanup(s.close)
        port = s.getsockname()[1]
        p, logdir, reps = self.run_main({"port": port, "log_dir": ""})
        self.assertEqual(p.returncode, 1)
        self.assertEqual(len(reps), 1, p.stdout + p.stderr)
        self.assertIn("couldn't start: its port is in use", reps[0])
        log = open(os.path.join(logdir, "eqlassistant.log"), encoding="utf-8").read()
        self.assertIn("EQL Assistant starting", log)
        self.assertIn("DEBUG", log)                                     # verbose by default
        self.assertFalse(os.path.exists(os.path.join(logdir, "running.json")))

    def test_failed_start(self):
        p, logdir, reps = self.run_main({"port": "not a number"})
        self.assertEqual(p.returncode, 1)
        self.assertEqual(len(reps), 1, p.stdout + p.stderr)
        self.assertIn("EQL Assistant", reps[0])
        self.assertIn("ValueError", reps[0])
        self.assertIn("starting the dashboard server", reps[0])         # what it was doing
        self.assertIn("crash report with the full details", p.stdout)   # the message box text

    def test_quiet_logging(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        self.addCleanup(s.close)
        p, logdir, reps = self.run_main({"port": s.getsockname()[1], "verbose_logging": False})
        log = open(os.path.join(logdir, "eqlassistant.log"), encoding="utf-8").read()
        self.assertNotIn(" DEBUG ", log)
        self.assertEqual(len(reps), 1)                                  # crash reports still written


if __name__ == "__main__":
    unittest.main()

"""Checks GitHub for a newer EQL Assistant release.

Asks https://api.github.com/repos/Sah-kage/EQLAssistant/releases/latest when the app
starts and every few hours after, compares its version with this one, and the dashboard
shows a banner with a Download button when there's a newer one. Nothing is downloaded or
installed by itself: Download opens the new EQLAssistant.exe in your web browser.
"""
import json
import re
import threading
import time
import urllib.request

REPO = "Sah-kage/EQLAssistant"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases"
EVERY = 6 * 3600            # check again this often while the app is running
TIMEOUT = 10


def parse_version(v):
    """'v1.6.4' / '1.6.4' -> (1, 6, 4); anything odd -> ()."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", str(v or ""))
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def whats_new(body):
    """The "What's new" part of a release's notes (the release workflow writes the commit message there)."""
    text = str(body or "").replace("\r\n", "\n")
    m = re.search(r"##\s*What's new\s*\n(.*?)(?:\n##\s|\Z)", text, re.S | re.I)
    text = (m.group(1) if m else text).strip()
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)          # plain text: drop **bold**
    return text[:3000]


def _fetch(opener=None):
    from . import __version__
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"EQLAssistant/{__version__}"})
    with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


class Updates:
    def __init__(self, cfg, save_cfg=lambda: None, opener=None):
        self.cfg = cfg
        self.save_cfg = save_cfg
        self.opener = opener
        self.state = {"checked": None, "latest": None, "available": False, "url": RELEASES, "download": None,
                      "notes": "", "published": None, "error": None, "checking": False}
        self._lock = threading.Lock()

    def check(self):
        """Ask GitHub now. Returns the view."""
        from . import __version__
        with self._lock:
            self.state["checking"] = True
        try:
            rel = _fetch(self.opener)
            tag = rel.get("tag_name") or rel.get("name") or ""
            exe = next((a.get("browser_download_url") for a in rel.get("assets") or []
                        if str(a.get("name", "")).lower().endswith(".exe")), None)
            url = rel.get("html_url") or RELEASES
            ok_url = lambda u: isinstance(u, str) and u.startswith(f"https://github.com/{REPO}/")
            with self._lock:
                self.state.update(latest=tag.lstrip("v"), available=newer(tag, __version__),
                                  url=url if ok_url(url) else RELEASES, download=exe if ok_url(exe) else None,
                                  notes=whats_new(rel.get("body")), published=rel.get("published_at"),
                                  error=None)
        except Exception as e:                       # offline, GitHub down, rate limited...
            with self._lock:
                self.state["error"] = f"Couldn't check for updates: {getattr(e, 'reason', e)}"
        finally:
            with self._lock:
                self.state.update(checking=False, checked=time.time())
        return self.view()

    def view(self):
        from . import __version__
        with self._lock:
            v = dict(self.state)
        v["current"] = __version__
        v["enabled"] = bool(self.cfg.get("check_updates", True))
        v["dismissed"] = v["available"] and self.cfg.get("update_dismissed") == v["latest"]
        return v

    def dismiss(self, version):
        self.cfg["update_dismissed"] = version
        self.save_cfg()

    def open(self, which="download"):
        """Open the download (or the release page) in the web browser. Only ever this project's GitHub pages."""
        import webbrowser
        v = self.view()
        url = (v["download"] if which == "download" else None) or v["url"] or RELEASES
        if not url.startswith(f"https://github.com/{REPO}/"):
            url = RELEASES
        webbrowser.open(url)
        return url

    def start(self):
        def loop():
            time.sleep(3)                            # let the app start first
            while True:
                if self.cfg.get("check_updates", True):
                    self.check()
                time.sleep(EVERY)
        threading.Thread(target=loop, daemon=True).start()

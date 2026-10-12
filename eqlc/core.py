"""Config, saved state, and the log watcher thread that feeds the trackers."""
import glob
import json
import os
import re
import threading
import time

from .fights import FightTracker
from .motes import MoteCounter
from .timers import Timers
from .crawls import Crawls
from .factions import Factions
from .quests import Quests
from .raids import Raids
from .races import Races
from .parser import parse_line
from .sky import SkyTracker, REWARD_RE as _sky_reward_re, reward_in_line

DEFAULTS = {
    "log_dir": "",
    "character": "",          # blank = follow most recently active log
    "fight_timeout": 10,
    "min_fight_secs": 5,
    "avg_fights": 10,
    "include_pets": False,
    "pet_names": [],
    "backfill_mb": 8,
    "overlay_on_start": True,     # open the in-game DPS overlay when the app starts
    "motes_window_on_start": True,  # open the in-game motes window when the app starts
    "crawl_window_on_start": True,  # open the in-game dungeon crawl timer window when the app starts
    "timers": [],                 # [{"mob", "minutes", "variance", "zone"}] respawn timer rules
    "crawl_on_overlay": True,     # show the live dungeon crawl timer on the DPS overlay
    "timers_on_overlay": True,    # show respawn timers on the DPS overlay
    "overlay_look": {},           # kind -> {"alpha", "locked", "scale", "rev"} (Overlays tab / right-click)
    "raid_eras": ["Classic"],     # which raid boss lists to show (Classic, Kunark, Velious)
    "raid_extra_bosses": [],      # your own additions to the raid boss list
    "raid_reset_weekday": 1,      # 0=Mon .. 6=Sun  (EQL: Tuesday)
    "raid_reset_hour": 8,         # Pacific time    (EQL: 8am)
    "port": 7377,
}

LOG_RE = re.compile(r"^eqlog_(?P<char>[^_]+)_(?P<server>.+)\.txt$", re.I)

GUESS_DIRS = [
    r"C:\Users\Public\Daybreak Game Company\Installed Games\EverQuest Legends\Logs",
    r"C:\Program Files\EverQuest Legends\Logs",
    r"C:\Program Files (x86)\EverQuest Legends\Logs",
    r"C:\EverQuest Legends\Logs",
    r"C:\Games\EverQuest Legends\Logs",
    os.path.expanduser(r"~\EverQuest Legends\Logs"),
]


HISTORY_KINDS = {"crawls", "raids", "factions", "ledger", "sky"}
_HIST_WORDS = ("You have entered", "Dungeon Crawl", "instance charge", "instance recharge",
               "slain", " died.", "eward Chest", "eward chest", "s now available to you", "ote", "You gain ", "faction standing", "looted", "receive",
               " regards you", " upon you", " considers you", " judges you", " your way", " at you")


def _history_relevant(line):
    return any(w in line for w in _HIST_WORDS) or bool(_sky_reward_re.search(line))


_crawl_relevant = _history_relevant


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = os.path.join(base, "EQLAssistant")
    old = os.path.join(base, "EQLCompanion")        # the app's earlier name: carry the data over
    if not os.path.exists(d) and os.path.isdir(old):
        try:
            os.rename(old, d)
        except OSError:
            import shutil
            shutil.copytree(old, d, dirs_exist_ok=True)
    os.makedirs(d, exist_ok=True)
    return d


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


class App:
    def __init__(self, log_dir=None, ddir=None):
        self.ddir = ddir or data_dir()
        os.makedirs(self.ddir, exist_ok=True)
        self.cfg_path = os.path.join(self.ddir, "config.json")
        self.state_path = os.path.join(self.ddir, "state.json")
        self.cfg = dict(DEFAULTS)
        self.cfg.update(_load(self.cfg_path, {}))
        self.cfg.pop("motes_reset_hours", None)         # motes are per session now
        if log_dir:
            self.cfg["log_dir"] = log_dir
        if not self.cfg["log_dir"]:
            for g in GUESS_DIRS:
                if os.path.isdir(g):
                    self.cfg["log_dir"] = g
                    break
        self.state = _load(self.state_path, {})
        self.state.setdefault("offsets", {})
        self.sky = SkyTracker(self.state)
        self.motes = MoteCounter(self.state, self.cfg)
        self.timers = Timers(self.state, self.cfg)
        self.crawls = Crawls(self.state)
        self.factions = Factions(self.state)
        self.raids = Raids(self.state, self.cfg)
        self.quests = Quests(self.state, self.sky)
        self.races = Races(self.state, self.factions)
        self.zone_info = {}
        self.state.setdefault("crawl_scanned", {})
        self.state.setdefault("history_scan", {})
        self.scan_status = ""
        self.trackers = {}          # char -> FightTracker
        self.files = {}             # path -> {"pos", "char"}
        self.active_char = None
        self.zone = {}
        self.lock = threading.RLock()
        self.status = "starting"
        self._last_save = time.time()
        self._inv_mtimes = {}
        self._stop = False

    # -- config -----------------------------------------------------------
    def save_cfg(self):
        _save(self.cfg_path, self.cfg)

    def update_cfg(self, new):
        with self.lock:
            dir_changed = new.get("log_dir", self.cfg["log_dir"]) != self.cfg["log_dir"]
            for k, v in new.items():
                if k in DEFAULTS:
                    self.cfg[k] = type(DEFAULTS[k])(v) if not isinstance(DEFAULTS[k], list) else v
            self.save_cfg()
            if dir_changed:
                self.files.clear()
                self.trackers.clear()

    # -- overlays ------------------------------------------------------------
    OVERLAY_ON_KEY = {"dps": "overlay_on_start", "motes": "motes_window_on_start", "crawl": "crawl_window_on_start"}
    LOOK_DEFAULT = {"alpha": 0.85, "locked": False, "scale": 1.0, "rev": 0}

    def overlay_look(self, kind):
        return dict(self.LOOK_DEFAULT, **self.cfg.get("overlay_look", {}).get(kind, {}))

    def set_overlay(self, kind, body):
        """Change one overlay from the Overlays tab or its right-click menu. Returns its new look."""
        if kind not in self.OVERLAY_ON_KEY:
            raise ValueError("unknown overlay")
        with self.lock:
            look = self.overlay_look(kind)
            if "alpha" in body:
                look["alpha"] = min(1.0, max(0.2, float(body["alpha"])))
            if "locked" in body:
                look["locked"] = bool(body["locked"])
            if "scale" in body:
                look["scale"] = round(min(2.5, max(0.6, float(body["scale"]))), 2)
            if body.get("reset"):
                look.update(scale=1.0, rev=look["rev"] + 1)     # overlay moves back to its default spot
            self.cfg.setdefault("overlay_look", {})[kind] = look
            if "on" in body:
                self.cfg[self.OVERLAY_ON_KEY[kind]] = bool(body["on"])
            for k in ("crawl_on_overlay", "timers_on_overlay"):
                if k in body:
                    self.cfg[k] = bool(body[k])
            self.save_cfg()
            return look

    def tracker(self, char):
        t = self.trackers.get(char)
        if t is None:
            t = self.trackers[char] = FightTracker(self.cfg)
        return t

    def char(self):
        return self.cfg.get("character") or self.active_char

    # -- log reading --------------------------------------------------------
    def _open_file(self, path, char):
        size = os.path.getsize(path)
        sky_pos = self.state["offsets"].get(path, 0)
        if sky_pos > size:          # file was rotated/truncated
            sky_pos = 0
        dps_pos = max(0, size - int(self.cfg["backfill_mb"] * 1024 * 1024))
        start = min(sky_pos, dps_pos)
        done = set(self.state["history_scan"].get(path, []))
        if self.state["crawl_scanned"].get(path):
            done.add("crawls")
        need = sorted(HISTORY_KINDS - done)
        self.state["history_scan"][path] = sorted(HISTORY_KINDS)
        if sky_pos > 0 and need:
            # First run with these trackers: look back through older log history once.
            threading.Thread(target=self.scan_history, args=(path, char, sky_pos, need), daemon=True).start()
        self.files[path] = {"pos": start, "char": char, "sky_from": sky_pos, "dps_from": dps_pos,
                            # saved offsets sit on a line boundary; the tail
                            # backfill offset usually lands mid-line
                            "skip_partial": start > 0 and start == dps_pos and dps_pos < sky_pos}

    def _read_new(self, path, info):
        try:
            size = os.path.getsize(path)
        except OSError:
            return 0
        if size < info["pos"]:
            info.update(pos=0, sky_from=0, dps_from=0, skip_partial=False)
        if size == info["pos"]:
            return 0
        char = info["char"]
        tr = self.tracker(char)
        n = 0
        with open(path, "rb") as fh:
            fh.seek(info["pos"])
            while True:
                chunk = fh.read(4 * 1024 * 1024)
                if not chunk:
                    break
                last_nl = chunk.rfind(b"\n")
                if last_nl < 0:
                    if len(chunk) < 4 * 1024 * 1024:
                        break        # partial line still being written
                    last_nl = len(chunk) - 1
                block = chunk[: last_nl + 1]
                base = info["pos"]
                info["pos"] += len(block)
                fh.seek(info["pos"])
                lines = block.split(b"\n")
                if info["skip_partial"]:
                    off = len(lines[0]) + 1
                    base += off
                    lines = lines[1:]
                    info["skip_partial"] = False
                pos = base
                with self.lock:
                    for raw in lines:
                        lpos = pos
                        pos += len(raw) + 1
                        if not raw:
                            continue
                        line = raw.decode("cp1252", errors="replace").rstrip("\r")
                        sky_ok = lpos >= info["sky_from"]
                        dps_ok = lpos >= info["dps_from"]
                        if not dps_ok:
                            # quick filter: only sky / motes / crawl lines need parsing here
                            if not (sky_ok and _history_relevant(line)) and \
                                    not ("looted" in line or "receive" in line or " you " in line):
                                continue
                        r = parse_line(line)
                        if not r:
                            continue
                        t, ev = r
                        if sky_ok:
                            self.motes.process_line(char, t, line)
                            self.sky.process_line(char, t, line)
                            self.crawls.process(char, t, ev, line)
                            if ev:
                                et = ev["type"]
                                if et in ("faction", "con", "death"):
                                    self.factions.process(char, t, ev)
                                if et == "death":
                                    self.raids.process(char, t, ev, self.zone_info.get(char))
                                elif et in ("loot", "receive"):
                                    self.quests.process(char, t, ev)
                        if not ev:
                            continue
                        n += 1
                        typ = ev["type"]
                        if typ in ("loot", "receive"):
                            if sky_ok:
                                self.sky.process(char, t, ev)
                        elif typ == "zone":
                            self.zone[char] = ev["zone"]
                            self.zone_info[char] = ev
                            if not sky_ok:
                                self.crawls.where[char] = ev      # older lines: just remember where you are
                        elif typ in ("crawl", "xp", "faction", "con"):
                            pass
                        elif dps_ok:
                            tr.process(t, ev)
                            if typ == "death":
                                self.timers.process(char, t, ev, self.zone.get(char))
                    self.state["offsets"][path] = info["pos"]
        return n

    def scan_history(self, path, char, upto=None, kinds=("crawls", "raids")):
        """Read a log (up to byte `upto`) for crawls / raid kills / factions / looted items, then merge.

        Crawls and raid kills are de-duplicated, so they can be rescanned any time.
        Factions and the item ledger are additive, so they're only scanned once per log.
        """
        kinds = set(kinds)
        tmp_c, tmp_r, tmp_f = Crawls({}), Raids({}, self.cfg), Factions({})
        tmp_led = []
        tmp_sky = []
        zone = None
        name = os.path.basename(path)
        self.scan_status = f"Scanning {name} history…"
        try:
            with open(path, "rb") as fh:
                done = 0
                for raw in fh:
                    done += len(raw)
                    if upto is not None and done > upto:
                        break
                    line = raw.decode("cp1252", errors="replace").rstrip("\r\n")
                    if not _history_relevant(line):
                        continue
                    r = parse_line(line)
                    if not r:
                        continue
                    t, ev = r
                    if "crawls" in kinds:
                        tmp_c.process(char, t, ev, line)
                    if "sky" in kinds:
                        qid = reward_in_line(line)
                        if qid:
                            tmp_sky.append((t, qid))
                    if not ev:
                        continue
                    et = ev["type"]
                    if et == "zone":
                        zone = ev
                    elif et == "death" and "raids" in kinds:
                        tmp_r.process(char, t, ev, zone)
                    if "factions" in kinds and et in ("faction", "con", "death"):
                        tmp_f.process(char, t, ev)
                    if "ledger" in kinds and (et == "receive" or (et == "loot" and ev.get("who") == "You")):
                        tmp_led.append([t, ev["item"], ev.get("qty", 1) if et == "loot" else 1])
            tmp_c.tick(time.time())
            found = [r for r in tmp_c.runs if r["status"] != "active"]
            with self.lock:
                added = self.crawls.merge(found) if "crawls" in kinds else 0
                raids_added = self.raids.merge(tmp_r.kills) if "raids" in kinds else 0
                if "factions" in kinds:
                    self.factions.merge_from(tmp_f)
                for st, qid in tmp_sky:                 # Sky test rewards you got before the app was watching
                    self.sky.mark_done(char, qid, st, "history")
                if "ledger" in kinds and tmp_led:
                    led = self.quests.ledger.setdefault(char, [])
                    led[:0] = tmp_led
                    led.sort(key=lambda e: e[0])
                    del led[: max(0, len(led) - 25000)]
                    self.quests.dirty = True
            n_done = sum(1 for r in found if r["status"] == "done")
            self.scan_status = (f"{name}: found {n_done} completed crawl{'s' if n_done != 1 else ''} ({added} new), "
                                f"{len(tmp_r.kills)} raid boss kill{'s' if len(tmp_r.kills) != 1 else ''} ({raids_added} new)")
        except OSError as e:
            self.scan_status = f"Couldn't scan {name}: {e}"
        return self.scan_status

    def scan_crawl_history(self, path, char, upto=None):
        return self.scan_history(path, char, upto, ("crawls", "raids"))

    def rescan_crawls(self):
        """Settings button: rescan every log file's full history for crawls."""
        d = self.cfg["log_dir"]
        for p in glob.glob(os.path.join(d, "eqlog_*.txt")) if d else []:
            m = LOG_RE.match(os.path.basename(p))
            if m:
                info = self.files.get(p)
                self.scan_history(p, m.group("char"), info["sky_from"] if info else None, ("crawls", "raids"))

    def import_inventory(self, text, filename="", char=None, mtime=None):
        """An inventory export the player picked in the app (Import inventory...)."""
        from .inventory import char_from_filename
        char = char_from_filename(filename) or char or self.char()
        if not char:
            raise ValueError("pick a character first (or keep the file's name, e.g. Name_server-Inventory.txt)")
        if "\t" not in text:
            raise ValueError("that doesn't look like an inventory export (expected tab-separated lines)")
        known = {c.lower(): c for c in set(self.sky.characters()) | set(self.trackers) |
                 {i["char"] for i in self.files.values()}}
        char = known.get(char.lower(), char)
        with self.lock:
            res = self.sky.load_inventory_text(char, text, mtime, filename or "imported file")
            self.quests.dirty = True
        self.save_state(force=True)
        return res

    def _check_inventory(self, char, log_path):
        root = os.path.dirname(os.path.dirname(log_path))
        for p in glob.glob(os.path.join(root, f"{char}_*-Inventory.txt")) + \
                glob.glob(os.path.join(root, f"{char}-Inventory.txt")):
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if self._inv_mtimes.get(p) != mt:
                self._inv_mtimes[p] = mt
                with self.lock:
                    self.sky.load_inventory(char, p)

    def poll(self):
        d = self.cfg["log_dir"]
        if not d or not os.path.isdir(d):
            self.status = "Log folder not set or not found - open Settings"
            return
        logs = []
        for p in glob.glob(os.path.join(d, "eqlog_*.txt")):
            m = LOG_RE.match(os.path.basename(p))
            if m:
                logs.append((os.path.getmtime(p), p, m.group("char")))
        if not logs:
            self.status = "No eqlog_*.txt files yet - type /log in game"
            return
        logs.sort(reverse=True)
        self.active_char = logs[0][2]
        for _, p, char in logs:
            if p not in self.files:
                self._open_file(p, char)
            self._read_new(p, self.files[p])
            self._check_inventory(char, p)
        with self.lock:
            for tr in self.trackers.values():
                tr.tick()
            for c in {info["char"] for info in self.files.values()}:
                self.motes.tick(c)
            self.crawls.tick()
        self.status = "ok"

    def save_state(self, force=False):
        self.timers.prune()
        dirty = (self.sky.dirty or self.motes.dirty or self.timers.dirty or self.crawls.dirty or
                 self.factions.dirty or self.raids.dirty or self.quests.dirty or self.races.dirty)
        if force or (dirty and time.time() - self._last_save > 5):
            with self.lock:
                _save(self.state_path, self.state)
                self.sky.dirty = False
                self.motes.dirty = False
                self.timers.dirty = False
                self.crawls.dirty = False
                self.factions.dirty = self.raids.dirty = self.quests.dirty = self.races.dirty = False
            self._last_save = time.time()

    def run(self):
        while not self._stop:
            try:
                self.poll()
                self.save_state()
            except Exception as e:      # keep the watcher alive
                self.status = f"error: {e}"
            time.sleep(0.25)

    def start(self):
        th = threading.Thread(target=self.run, daemon=True)
        th.start()
        return th

    def stop(self):
        self._stop = True
        self.save_state(force=True)

    def quit(self):
        """Quit button: save, close the overlay and app window, then exit."""
        import time as _t
        from .launch import close_overlay_window
        self.stop()
        close_overlay_window()
        try:
            import webview
            for w in list(webview.windows):
                w.destroy()
        except Exception:
            pass
        _t.sleep(0.5)
        os._exit(0)

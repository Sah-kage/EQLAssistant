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
from .integrity import FileWatch
from .factions import Factions
from .quests import Quests
from .raids import Raids
from .races import Races
from .deaths import DeathRecap
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
    "use_browser": False,         # open the dashboard in the web browser instead of the app window
    "crawl_on_overlay": True,     # show the live dungeon crawl timer on the DPS overlay
    "timers_on_overlay": True,    # show respawn timers on the DPS overlay
    "overlay_look": {},           # kind -> {"alpha", "locked", "scale", "rev"} (Overlays tab / right-click)
    "raid_eras": ["Classic"],     # which raid boss lists to show (Classic, Kunark, Velious)
    "raid_extra_bosses": [],      # your own additions to the raid boss list
    "raid_reset_weekday": 1,      # 0=Mon .. 6=Sun  (EQL: Tuesday)
    "raid_reset_hour": 8,         # Pacific time    (EQL: 8am)
    "port": 7377,
    "check_updates": True,         # look for a newer EQL Assistant on GitHub (start, then every 6 hours)
    "update_dismissed": "",        # a version the player said "not now" to
    "leaderboard_url": "",        # EQL Crawl Times site that finished crawls are sent to
    "leaderboard_auto": True,     # send verified crawls there automatically when they finish
    "leaderboard_classes": {},    # character id -> your three classes (sent with each run)
    "leaderboard_classes_at": {}, # character id -> when they were picked (a newer /who wins: loadouts change)
}

LOG_RE = re.compile(r"^eqlog_(?P<char>[^_]+)_(?P<server>.+)\.txt$", re.I)


def char_id(m):
    """Every character is tracked per server: eqlog_Sahkage_rivervale.txt -> "Sahkage_rivervale".
    Sahkage_rivervale and Sahkage_paineel share nothing."""
    return f"{m.group('char')}_{m.group('server').lower()}"


def split_char(cid):
    """'Sahkage_rivervale' -> ('Sahkage', 'rivervale'); a bare name -> (name, '')."""
    name, _, server = (cid or "").partition("_")
    return name, server

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
               "slain", " died.", "eward Chest", "eward chest", "s now available to you", "ote", "You gain ", "faction standing", "looted", "receive", "Wind Rune",
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
        self.migrate_per_server()
        self.sky = SkyTracker(self.state)
        self.motes = MoteCounter(self.state, self.cfg)
        self.timers = Timers(self.state, self.cfg)
        self.crawls = Crawls(self.state, proof_dir=self.ddir)
        self.crawls.is_pet = lambda char, name: (name in self.cfg.get("pet_names", []) or
                                                 name in self.tracker(char).pets())
        self.crawls.saved_classes = lambda char: self.my_classes(char)
        self._submitting = set()
        self.watch = FileWatch()
        self.factions = Factions(self.state)
        self.raids = Raids(self.state, self.cfg)
        self.quests = Quests(self.state, self.sky)
        self.races = Races(self.state, self.factions)
        self.deaths = DeathRecap(self.state)
        from .exalts import Exalts
        self.exalts = Exalts(self.state, self.sky, lambda char: self.my_classes(char))
        from .updates import Updates
        self.updates = Updates(self.cfg, self.save_cfg)
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

    # -- crawl proofs ------------------------------------------------------------
    def _proof(self, r):
        from . import __version__
        from . import integrity as I
        lines = []
        try:
            with open(I.proof_path(self.ddir, r["id"]), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            pass
        summary = self.crawls._summary(r, time.time())
        return I.build_proof(r, summary, lines, __version__), summary

    def export_proof(self, run_id):
        """Write a proof file for one crawl run (its verdict, checks, hash chain and raw lines)."""
        from . import integrity as I
        r = self.crawls._get(run_id)
        if not r:
            raise ValueError("No such run")
        if r["status"] == "active":
            raise ValueError("Finish the run first")
        doc, summary = self._proof(r)
        out_dir = os.path.join(self.ddir, "Proofs")
        os.makedirs(out_dir, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(r["start"]))
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{r['char']}_{r['zone']}_{summary.get('tier_label') or ''}_{stamp}")
        path = os.path.join(out_dir, name.strip("_") + ".eqlproof.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(I.dumps(doc))
        return {"path": path, "folder": out_dir, "name": os.path.basename(path), "verdict": doc["verdict"],
                "text": I.dumps(doc)}

    # -- leaderboard -----------------------------------------------------------------
    def class_info(self, char):
        """Your classes for a character and where they came from.

        Picked in Settings, unless a /who typed after that shows a different set (you changed loadout).
        {"classes": [3] or None, "source": "settings" | "who" | None, "who": last /who, "warning": str | None}"""
        saved = (self.cfg.get("leaderboard_classes") or {}).get(char)
        saved = list(saved) if saved and len(saved) == 3 else None
        at = (self.cfg.get("leaderboard_classes_at") or {}).get(char, 0)
        name, server = split_char(char)
        w = self.crawls.classes.who(server or "-", name)
        info = {"classes": saved, "source": "settings" if saved else None, "warning": None,
                "who": {k: w.get(k) for k in ("classes", "level", "t", "raw")} if w else None,
                "unread": self.crawls.classes.unread(server or "-")}
        if w and w["classes"]:
            newer = w["t"] > at
            if len(w["classes"]) >= 3 and (not saved or (newer and w["classes"][:3] != saved)):
                info.update(classes=list(w["classes"][:3]), source="who")
            elif saved and newer and not set(w["classes"]) <= set(saved):
                info["warning"] = (f"Your last /who shows {'/'.join(w['classes'])}, which isn't in the classes picked "
                                   f"here. If you changed loadout, pick your classes again.")
        return info

    def my_classes(self, char):
        """Your three classes for a character: picked in Settings, or a newer /who that lists all three."""
        return self.class_info(char)["classes"]

    def set_my_classes(self, char, classes):
        from .classes_data import CLASSES
        classes = [c for c in classes if c in CLASSES]
        if len(classes) != 3 or len(set(classes)) != 3:
            raise ValueError("Pick three different classes")
        if not char:
            raise ValueError("No character")
        with self.lock:
            self.cfg.setdefault("leaderboard_classes", {})[char] = classes
            self.cfg.setdefault("leaderboard_classes_at", {})[char] = time.time()
            self.save_cfg()

    def submittable(self, r):
        """None if this run can go to the leaderboard, else why not."""
        from . import integrity as I
        if r["status"] != "done":
            return "The run isn't finished."
        if not r.get("start_known"):
            return "The run's start time isn't known."
        v = I.verdict(r)
        if v["status"] == "suspicious":
            return "The log checks flagged this run as suspicious."
        if (r.get("proof") or {}).get("history") or not os.path.exists(I.proof_path(self.ddir, r["id"])):
            return "This run was read from older log lines, so there's no proof the site can check."
        return None

    def build_submission(self, r, classes=None, video=""):
        from . import leaderboard as L
        from . import snapshot as S
        why = self.submittable(r)
        if why:
            raise ValueError(why)
        name0 = split_char(r["char"])[0]
        classes = list((r.get("class_fix") or {}).get(name0) or classes or self.my_classes(r["char"]) or [])
        if len(classes) != 3:
            raise ValueError("Pick your three classes first (Settings, or Submit to leaderboard…).")
        name, server = split_char(r["char"])
        proof, summary = self._proof(r)
        group = self.crawls.group(r)
        png = S.load(self.ddir, r["id"])
        if png is None:
            png = S.render(summary, name)
            if png:
                with open(S.path(self.ddir, r["id"]), "wb") as fh:
                    fh.write(png)
        run = {k: summary.get(k) for k in ("zone", "tier_label", "level", "duration", "party", "kills", "deaths",
                                           "start", "end", "stopped")}
        run["tier"] = run.pop("tier_label")
        edits = r.get("class_edits") or {}
        body = L.payload(proof, server, classes, video, summary["party"],
                         [dict({k: g.get(k) for k in ("name", "classes", "source", "sure", "you", "level")},
                               edited=g["name"] in edits) for g in group],
                         run, png, f"{name}-run-{r['id']}.png")
        # classes changed by hand are flagged, with what the log showed, so the site can show the run as edited
        body["edited"] = bool(edits)
        body["edits"] = [dict(e, name=n, you=n == name0) for n, e in sorted(edits.items())]
        prev = r.get("submitted")
        body["resubmit_of"] = prev.get("id") if prev else None
        body["submission"] = len(r.get("submissions") or ([1] if prev else [])) + 1
        return body

    def submit_run(self, run_id, classes=None, video="", auto=False):
        """Send one finished run to the leaderboard. Returns the site's reply; raises ValueError."""
        from . import __version__
        from . import leaderboard as L
        with self.lock:
            r = self.crawls._get(run_id)
            if not r:
                raise ValueError("No such run")
            if r.get("submitted") and not r.get("changed_since_sent"):
                raise ValueError("This run was already sent to the leaderboard. Edit its classes to send it again.")
            if auto and r.get("submitted"):
                raise ValueError("Edited runs are only sent again by hand.")
            if classes:
                me = split_char(r["char"])[0]
                if not self.my_classes(r["char"]):
                    self.set_my_classes(r["char"], classes)       # first time: remember them for this character
                self.crawls.set_classes(r["id"], me, classes)     # different from what was detected: an edit
            body = self.build_submission(r, classes, video)
            url = self.cfg.get("leaderboard_url", "")
        try:
            reply = L.submit(url, body, __version__)
        except ValueError as e:
            with self.lock:
                r["submit_error"] = {"at": time.time(), "msg": str(e), "auto": auto}
                self.crawls.dirty = True
            raise
        with self.lock:
            r["submitted"] = {"at": time.time(), "id": reply.get("id"), "auto": auto,
                              "message": reply.get("message") or "", "duplicate": bool(reply.get("duplicate")),
                              "url": reply.get("url") or "", "edited": body["edited"],
                              "edits": body["edits"], "resubmit_of": body["resubmit_of"]}
            r.setdefault("submissions", []).append(dict(r["submitted"], classes=body["classes"]))
            r.pop("submit_error", None)
            r.pop("changed_since_sent", None)
            if body["edited"] and not reply.get("edited"):
                # The site didn't confirm the edit (a leaderboard site from before edited runs):
                # say so, and allow sending it again once the site is updated.
                r["submitted"]["site_missed_edit"] = True
                r["changed_since_sent"] = True
            self.crawls.dirty = True
        return reply

    SNAP_WAIT = 8          # seconds to wait for the crawl window's picture before sending without it

    def auto_submit(self, now=None):
        """Send newly finished, verified runs by themselves (Settings: submit automatically)."""
        from . import integrity as I
        from . import snapshot as S
        if not self.cfg.get("leaderboard_auto") or not self.cfg.get("leaderboard_url"):
            return
        now = time.time() if now is None else now
        for r in reversed(self.crawls.runs[-20:]):
            if (r["status"] != "done" or r.get("submitted") or r.get("auto_tried") or r["id"] in self._submitting
                    or not r.get("end") or now - r["end"] > 30 * 60):
                continue
            mine = (r.get("class_fix") or {}).get(split_char(r["char"])[0])
            if I.verdict(r)["status"] != "verified" or not (mine and len(mine) == 3 or self.my_classes(r["char"])):
                continue
            if now - r["end"] < self.SNAP_WAIT and not S.exists(self.ddir, r["id"]):
                continue
            r["auto_tried"] = now
            self.crawls.dirty = True
            self._submitting.add(r["id"])

            def go(rid=r["id"]):
                try:
                    self.submit_run(rid, auto=True)
                except Exception as e:          # noqa: BLE001 - shown on the run
                    from .launch import log
                    log(f"auto submit of run {rid} failed: {e}")
                finally:
                    self._submitting.discard(rid)
            threading.Thread(target=go, daemon=True).start()

    def tracker(self, char):
        t = self.trackers.get(char)
        if t is None:
            t = self.trackers[char] = FightTracker(self.cfg)
        return t

    def char(self):
        pick = self.cfg.get("character")
        if pick and pick not in {c for _, _, c in self.log_chars()}:
            pick = None                                   # its log was deleted: follow the active log
        return pick or self.active_char

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
        char = info["char"]
        changed = self.watch.check(path, info["pos"])
        if changed:                                   # the log shrank, or lines already read were changed
            with self.lock:
                self.crawls.file_event(char, changed)
        if size < info["pos"]:
            info.update(pos=0, sky_from=0, dps_from=0, skip_partial=False)
        if size == info["pos"]:
            self.watch.remember(path, info["pos"])
            info["live"] = True
            return 0
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
                # Lines read here as the game writes them get a time of arrival, for the crawl
                # integrity checks. The first read of a file this session is catching up: not live.
                meta = {"now": time.time(), "mono": time.monotonic()} if info.get("live") else None
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
                        if dps_ok:
                            self.deaths.process(char, t, ev, line, self.zone.get(char))
                        if sky_ok:
                            self.motes.process_line(char, t, line)
                            self.sky.process_line(char, t, line)
                            self.crawls.process(char, t, ev, line, meta)
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
        self.watch.remember(path, info["pos"])
        info["live"] = True              # caught up: from now on lines arrive as the game writes them
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

    # -- one character per server -------------------------------------------------
    def log_chars(self):
        """[(mtime, path, char id)] for every eqlog_Name_server.txt, newest first."""
        d = self.cfg.get("log_dir")
        out = []
        for p in glob.glob(os.path.join(d, "eqlog_*.txt")) if d and os.path.isdir(d) else []:
            m = LOG_RE.match(os.path.basename(p))
            if m:
                try:
                    out.append((os.path.getmtime(p), p, char_id(m)))
                except OSError:
                    continue
        return sorted(out, reverse=True)

    def characters(self):
        """Every character with a log file in the Logs folder, one per name + server.
        A character whose log was deleted isn't listed (its saved data is kept, and comes back with the log)."""
        return sorted({c for _, _, c in self.log_chars()})

    def migrate_per_server(self):
        """Older versions keyed everything by character name only. Move each name's data to that
        name's character on the server it was most recently played on (Name_server)."""
        st = self.state
        if st.get("per_server"):
            return
        ids = {}
        for _, _, cid in self.log_chars():
            ids.setdefault(split_char(cid)[0].lower(), cid)        # newest log wins
        if not ids:
            st["per_server"] = 1 if not any(st.get(k) for k in ("sky", "quests", "factions", "ledger", "raid_kills")) else 0
            return
        to = lambda name: name if "_" in (name or "") else ids.get((name or "").lower(), name)
        for key in ("sky", "quests", "factions", "ledger"):
            sec = st.get(key)
            if isinstance(sec, dict):
                st[key] = {to(k): v for k, v in sec.items()}
        cr = st.get("crawls") or {}
        for r in cr.get("runs", []):
            r["char"] = to(r["char"])
        if isinstance(cr.get("active"), dict):
            cr["active"] = {to(k): v for k, v in cr["active"].items()}
        for k in st.get("raid_kills", []):
            k["char"] = to(k["char"])
        for g in st.get("group_drops", []):
            if g.get("seen_by"):
                g["seen_by"] = to(g["seen_by"])
        for a in st.get("timers_active", []):
            if a.get("char"):
                a["char"] = to(a["char"])
        races = st.get("races")
        if isinstance(races, dict) and "unlocked" in races:            # was one list for everything
            newest = self.log_chars()[0][2]
            st["races"] = {"by_server": {split_char(newest)[1]: races}}
        custom = st.get("custom_quests")
        if isinstance(custom, list) and custom:                       # custom quests now belong to a character
            newest = self.log_chars()[0][2]
            st["custom_quests"] = {newest: custom}
        if self.cfg.get("character") and "_" not in self.cfg["character"]:
            self.cfg["character"] = ids.get(self.cfg["character"].lower(), "")
            self.save_cfg()
        st["per_server"] = 1

    def scan_crawl_history(self, path, char, upto=None):
        return self.scan_history(path, char, upto, ("crawls", "raids"))

    def rescan_crawls(self):
        """Settings button: rescan every log file's full history for crawls."""
        d = self.cfg["log_dir"]
        for p in glob.glob(os.path.join(d, "eqlog_*.txt")) if d else []:
            m = LOG_RE.match(os.path.basename(p))
            if m:
                info = self.files.get(p)
                self.scan_history(p, char_id(m), info["sky_from"] if info else None, ("crawls", "raids"))

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
        if "_" not in char:            # file named Name-Inventory.txt: which server?
            same = sorted(c for c in known.values() if c.lower().startswith(char.lower() + "_"))
            cur = self.char()
            if cur and cur.lower().startswith(char.lower() + "_"):
                char = cur
            elif len(same) == 1:
                char = same[0]
            else:
                raise ValueError("that file doesn't say which server it's from. Pick the character at the top "
                                 "of the app and keep the file name as Name_server-Inventory.txt")
        with self.lock:
            res = self.sky.load_inventory_text(char, text, mtime, filename or "imported file")
            self.quests.dirty = True
        self.save_state(force=True)
        return res

    def _check_inventory(self, char, log_path):
        root = os.path.dirname(os.path.dirname(log_path))
        for p in glob.glob(os.path.join(root, f"{char}-Inventory.txt")):      # Name_server-Inventory.txt
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
        if not self.state.get("per_server"):
            with self.lock:
                self.migrate_per_server()
        logs = self.log_chars()
        if not logs:
            self.files.clear()
            self.active_char = None
            self.status = "No eqlog_*.txt files yet - type /log in game"
            return
        self.active_char = logs[0][2]
        here = {p for _, p, _ in logs}
        for p in [p for p in self.files if p not in here]:     # log deleted (or moved): stop watching it
            with self.lock:
                info = self.files.pop(p)
                if info["char"] not in {c for _, _, c in logs}:
                    self.trackers.pop(info["char"], None)
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
            self.auto_submit()
        self.status = "ok"

    def save_state(self, force=False):
        self.timers.prune()
        dirty = (self.sky.dirty or self.motes.dirty or self.timers.dirty or self.crawls.dirty or
                 self.factions.dirty or self.raids.dirty or self.quests.dirty or self.races.dirty or self.deaths.dirty
                 or self.exalts.dirty)
        if force or (dirty and time.time() - self._last_save > 5):
            with self.lock:
                _save(self.state_path, self.state)
                self.sky.dirty = False
                self.motes.dirty = False
                self.timers.dirty = False
                self.crawls.dirty = False
                self.factions.dirty = self.raids.dirty = self.quests.dirty = self.races.dirty = False
                self.deaths.dirty = False
                self.exalts.dirty = False
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

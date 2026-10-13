"""Mob respawn timers.

You list mobs and their respawn time (Settings -> Timers). When the log shows
one of them die ("You have slain X!", "X has been slain by Y!", "X died."),
a countdown starts. Optional variance gives a spawn window
("spawns 20-25 min after death"). Mob names are case-insensitive and may use
* as a wildcard, e.g. "a spiroc *". An optional zone limits a rule to one zone.
"""
import fnmatch
import itertools
import time

SHOW_UP_FOR = 10 * 60      # keep showing "UP" this long after the window ends
MAX_ACTIVE = 60


class Timers:
    def __init__(self, state, cfg):
        self.active = state.setdefault("timers_active", [])
        self.cfg = cfg
        self.dirty = False
        self._ids = itertools.count(int(time.time() * 1000))

    def rules(self):
        return [r for r in self.cfg.get("timers", []) if r.get("mob") and float(r.get("minutes") or 0) > 0]

    def match(self, mob, zone=None):
        m = mob.lower()
        for r in self.rules():
            pat = r["mob"].strip().lower()
            if not (m == pat or ("*" in pat and fnmatch.fnmatchcase(m, pat))):
                continue
            rz = (r.get("zone") or "").strip().lower()
            if rz and zone and rz not in zone.lower():
                continue
            return r
        return None

    def _add(self, mob, rule, t, zone, char, manual=False):
        respawn = float(rule["minutes"]) * 60
        var = float(rule.get("variance") or 0) * 60
        spawn = t + respawn
        end = spawn + var
        if end + SHOW_UP_FOR < time.time():
            return None                         # long expired (old log lines)
        for a in self.active:                   # same kill seen twice (restart / two log lines)
            if a["mob"] == mob and abs(a["killed_at"] - t) <= 3:
                return None
        a = {"id": next(self._ids), "mob": mob, "rule": rule["mob"], "killed_at": t,
             "spawn_at": spawn, "window_end": end, "zone": zone, "char": char, "manual": manual}
        self.active.append(a)
        self.active.sort(key=lambda x: x["spawn_at"])
        del self.active[MAX_ACTIVE:]
        self.dirty = True
        return a

    def process(self, char, t, ev, zone=None):
        if ev.get("type") != "death":
            return None
        mob = ev["tgt"]
        if mob in ("You", "YOU"):
            return None
        rule = self.match(mob, zone)
        return self._add(mob, rule, t, zone, char) if rule else None

    def start_manual(self, mob, minutes=None, variance=None, char=None):
        rule = self.match(mob) or {"mob": mob, "minutes": minutes or 0, "variance": variance or 0}
        if minutes:
            rule = dict(rule, minutes=minutes, variance=variance if variance is not None else rule.get("variance", 0))
        if float(rule.get("minutes") or 0) <= 0:
            return None
        return self._add(mob, rule, time.time(), None, char, manual=True)

    def remove(self, tid=None, char=None):
        before = len(self.active)
        if tid is None:
            self.active[:] = [a for a in self.active if char and a.get("char") not in (None, char)]
        else:
            self.active[:] = [a for a in self.active if a["id"] != tid]
        self.dirty = self.dirty or len(self.active) != before

    def prune(self, now=None):
        now = now or time.time()
        keep = [a for a in self.active if now < a["window_end"] + SHOW_UP_FOR]
        if len(keep) != len(self.active):
            self.active[:] = keep
            self.dirty = True

    def view(self, char=None, now=None):
        """Running timers for one character (each server's characters are kept apart)."""
        now = now or time.time()
        self.prune(now)
        out = []
        for a in self.active:
            if char and a.get("char") not in (None, char):
                continue
            rem = a["spawn_at"] - now
            if rem > 0:
                state = "waiting"
            elif now < a["window_end"]:
                state = "window"
            else:
                state = "up"
            out.append({"id": a["id"], "mob": a["mob"], "zone": a.get("zone"), "char": a.get("char"),
                        "killed_at": a["killed_at"], "spawn_at": a["spawn_at"], "window_end": a["window_end"],
                        "remaining": round(rem), "window_left": round(a["window_end"] - now),
                        "state": state, "manual": a.get("manual", False)})
        # soonest first, but things that are already up go last
        out.sort(key=lambda x: (x["state"] == "up", x["spawn_at"]))
        return out

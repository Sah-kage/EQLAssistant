"""Raid bosses killed since the weekly reset.

EQ Legends raid lockouts reset on Tuesdays at 8am Pacific (eqlwiki.com,
Category:Raid Encounters). After the first kill a raid can be cleared again
every 18 hours for one extra loot piece per boss on that difficulty.

A kill is counted when the log shows the boss die: "You have slain X!",
"X has been slain by Y!" or "X died." (so you need to be in the zone).
"""
import calendar
import time
from datetime import datetime, timedelta, timezone

REPEAT_HOURS = 18

# (era, group, [(boss, mini?)], note)
BOSSES = [
    ("Classic", "Nagafen's Lair", [("Lord Nagafen", False)], ""),
    ("Classic", "Permafrost", [("Lady Vox", False)], ""),
    ("Classic", "Kedge Keep", [("Phinigel Autropos", False)], ""),
    ("Classic", "The Hole", [("Master Yael", False)], ""),
    ("Classic", "Plane of Fear", [("Dread", True), ("Fright", True), ("Terror", True), ("Dracoliche", False),
                                  ("Cazic Thule", False)], ""),
    ("Classic", "Plane of Hate", [("Ashenbone Broodmaster", True), ("Avatar of Abhorrence", True),
                                  ("Coercer T`vala", True), ("Grandmaster R`Tal", True), ("High Priest M`kari", True),
                                  ("Lord of Ire", True), ("Lord of Loathing", True), ("Magi P`Tasa", True),
                                  ("Maestro of Rancor", False), ("Innoruuk", False)], ""),
    ("Kunark", "World and zone targets", [("Venril Sathir", False)], ""),
    ("Kunark", "Chardok royals", [("Prince Selrach Di'zok", False), ("Overking Bathezid", False),
                                  ("Queen Velazul Di'zok", False)], ""),
    ("Kunark", "Dragons", [("Faydedar", False), ("Severilous", False), ("Talendor", False), ("Gorenaire", False),
                           ("Trakanon", False)], ""),
    ("Kunark", "Veeshan's Peak", [("Silverwing", False), ("Xygoz", False), ("Phara Dar", False), ("Druushk", False),
                                  ("Nexona", False), ("Hoshkar", False)], ""),
    ("Velious", "Dragons", [("Kelorek`Dar", False), ("Wuoshi", False), ("Klandicar", False), ("Zlandicar", False),
                            ("Lord Yelinak", False), ("Sontalak", False)], ""),
    ("Velious", "Giants and gods", [("Velketor the Sorcerer", False), ("Statue of Rallos Zek", False),
                                    ("Derakor the Vindicator", False), ("King Tormax", False),
                                    ("Dain Frostreaver IV", False), ("Tunare", False), ("Avatar of War", False)], ""),
    ("Velious", "Temple of Veeshan", [("Telkorenar", False), ("Gozzrem", False), ("Lendiniara the Keeper", False),
                                      ("Dozekar the Cursed", False), ("Cekenar", False), ("Jorlleag", False),
                                      ("Ikatiar the Venom", False), ("Lady Mirenilla", False), ("Lady Nevederia", False),
                                      ("Lord Feshlak", False), ("Lord Koi'Doken", False), ("Sevalak", False),
                                      ("Aaryonar", False), ("Zlexak", False), ("Dagarn the Destroyer", False),
                                      ("Eashen of the Sky", False), ("Lord Kreizenn", False), ("Vulak`Aerr", False),
                                      ("Lord Vyemm", False)], ""),
    ("Velious", "Sleeper's Tomb", [("Kerafyrm", False), ("The Progenitor", False), ("The Final Arbiter", False),
                                   ("Master of the Guard", False), ("Hraashna the Warder", False),
                                   ("Nanzata the Warder", False), ("Tukaarak the Warder", False),
                                   ("Ventani the Warder", False)], ""),
]
ERAS = ["Classic", "Kunark", "Velious"]


def _k(s):
    return (s or "").lower().replace("`", "'").strip()


# ----------------------------------------------------------------- reset time
def _nth_sunday(year, month, n):
    first = datetime(year, month, 1)
    first_sun = 1 + (6 - first.weekday()) % 7
    return first_sun + 7 * (n - 1)


def pacific_offset(utc_ts):
    """Hours to add to UTC for US Pacific time at this moment (DST-aware, US rules since 2007)."""
    d = datetime.fromtimestamp(utc_ts, timezone.utc)
    y = d.year
    dst_start = datetime(y, 3, _nth_sunday(y, 3, 2), 10, tzinfo=timezone.utc)   # 2am PST
    dst_end = datetime(y, 11, _nth_sunday(y, 11, 1), 9, tzinfo=timezone.utc)    # 2am PDT
    return -7 if dst_start <= d < dst_end else -8


def last_reset(now=None, weekday=1, hour=8):
    """Most recent reset (weekday 0=Mon..6=Sun, `hour` Pacific) at or before `now` (UTC timestamp)."""
    now = time.time() if now is None else now
    local = datetime.fromtimestamp(now, timezone.utc) + timedelta(hours=pacific_offset(now))
    for back in range(0, 8):
        day = (local - timedelta(days=back)).date()
        if day.weekday() != weekday:
            continue
        naive = datetime(day.year, day.month, day.day, hour)
        guess = calendar.timegm(naive.timetuple()) + 8 * 3600         # assume PST, then correct
        ts = calendar.timegm(naive.timetuple()) - pacific_offset(guess) * 3600
        if ts <= now:
            return ts
    return now - 7 * 86400


def next_reset(now=None, weekday=1, hour=8):
    lr = last_reset(now, weekday, hour)
    return last_reset(lr + 7 * 86400 + 3 * 3600, weekday, hour)   # +3h margin covers a DST change


# ----------------------------------------------------------------- tracker
class Raids:
    def __init__(self, state, cfg):
        self.kills = state.setdefault("raid_kills", [])
        self.cfg = cfg
        self.dirty = False

    def boss_index(self):
        idx = {}
        for era, group, bosses, _ in BOSSES:
            for name, mini in bosses:
                idx[_k(name)] = name
        for name in self.cfg.get("raid_extra_bosses", []):
            if name.strip():
                idx[_k(name)] = name.strip()
        return idx

    def process(self, char, t, ev, zone=None):
        if ev.get("type") != "death":
            return None
        name = self.boss_index().get(_k(ev["tgt"]))
        if not name:
            return None
        for k in reversed(self.kills[-50:]):      # same kill seen twice (two log lines / rescan)
            if k["char"] == char and k["boss"] == name and abs(k["t"] - t) <= 5:
                return None
        rec = {"t": t, "boss": name, "killer": ev.get("src") or "", "char": char,
               "zone": zone.get("zone") if zone else None, "level": zone.get("level") if zone else None,
               "raw": zone.get("raw") if zone else None}
        self.kills.append(rec)
        self.kills.sort(key=lambda k: k["t"])
        del self.kills[:-5000]
        self.dirty = True
        return rec

    def merge(self, kills):
        have = {(k["char"], k["boss"], round(k["t"])) for k in self.kills}
        added = 0
        for k in kills:
            if (k["char"], k["boss"], round(k["t"])) not in have:
                self.kills.append(k)
                added += 1
        if added:
            self.kills.sort(key=lambda k: k["t"])
            self.dirty = True
        return added

    def delete(self, char, t, boss):
        before = len(self.kills)
        self.kills[:] = [k for k in self.kills if not (k["char"] == char and k["boss"] == boss and abs(k["t"] - t) < 1)]
        self.dirty = self.dirty or len(self.kills) != before

    def view(self, char, week=0, now=None):
        now = time.time() if now is None else now
        wd, hr = int(self.cfg.get("raid_reset_weekday", 1)), int(self.cfg.get("raid_reset_hour", 8))
        start = last_reset(now, wd, hr)
        for _ in range(int(week)):
            start = last_reset(start - 3600, wd, hr)
        end = next_reset(start + 60, wd, hr)
        mine = [k for k in self.kills if k["char"] == char]
        inweek = [k for k in mine if start <= k["t"] < end]
        eras = self.cfg.get("raid_eras", ["Classic"])
        groups = []
        all_names = set()
        extra = [n.strip() for n in self.cfg.get("raid_extra_bosses", []) if n.strip()]
        table = [(e, g, b, n) for e, g, b, n in BOSSES if e in eras]
        if extra:
            table.append(("Custom", "Your bosses", [(n, False) for n in extra], ""))
        for era, group, bosses, note in table:
            rows = []
            for name, mini in bosses:
                all_names.add(name)
                ks = [k for k in inweek if k["boss"] == name]
                last_any = next((k for k in reversed(mine) if k["boss"] == name), None)
                repeat = None
                if ks and week == 0:
                    ready = ks[-1]["t"] + REPEAT_HOURS * 3600
                    repeat = ready if ready > now else 0
                rows.append({"boss": name, "mini": mini, "killed": bool(ks),
                             "kills": [{"t": k["t"], "killer": k["killer"], "level": k["level"], "zone": k["zone"]}
                                       for k in ks],
                             "levels": sorted({k["level"] for k in ks if k["level"] is not None}),
                             "repeat_at": repeat, "last_ever": last_any["t"] if last_any else None})
            groups.append({"era": era, "group": group, "note": note, "bosses": rows,
                           "done": sum(r["killed"] for r in rows), "total": len(rows)})
        unlisted = sorted({k["boss"] for k in inweek} - all_names)
        return {"char": char, "week": int(week), "start": start, "end": end, "now": now,
                "next_reset": next_reset(now, wd, hr), "groups": groups, "eras": ERAS, "shown_eras": eras,
                "kills_this_week": len(inweek), "unlisted": unlisted,
                "log": [dict(k) for k in reversed(inweek)][:200]}

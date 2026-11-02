"""Buffs and debuffs you cast, with how long each one has left and who it's on.

How a timer is made, from the log:

  "You begin casting Spirit of Wolf."                    you start casting (also "You begin singing ...")
  "Bobbin is surrounded by a brief lupine aura."         it lands on Bobbin: the spell's "cast on other" text
  "You feel the spirit of wolf enter you."               ... or on you: its "cast on you" text

The duration comes from the spell's duration formula and your level, as the
server works it out (ticks of 6 seconds, capped at the spell's longest
duration). A group spell gives one timer per person it lands on. A timer goes
away when it runs out, when the log says it wore off ("Your Tashan spell has
worn off of a gnoll.", or the spell's own fade text on you), or when the mob it
was on dies. Fizzles, interruptions, resists and "did not take hold" give no
timer.

Spell data: the game's own spell file (spells_us.txt / spells_en.txt next to
the Logs folder) when it's there, otherwise the built-in classic list
(spells_data.py). Spells neither knows can be given a duration by hand.
"""
import itertools
import os
import re
import time

from .logs import get as _get_log

LOG = _get_log("buffs")

TICK = 6                     # seconds per buff tick
LAND_WINDOW = 12             # seconds after a cast finishes that its landing line can still come
FADED_SHOW = 8               # a timer that ran out / wore off stays (dimmed) this long
DEFAULT_LEVEL = 60
PERMANENT = 0xFFFE
MAX_TIMERS = 120
SINGLE_TARGETS = {5, 6, 9, 10, 11, 13, 14, 16, 17, 18, 38, 46}   # one target: done after the first landing

_WORN_RE = re.compile(r"^Your (?P<spell>.+?) spell has worn off(?: of (?P<tgt>.+?))?[.!]$")
_LEVEL_RE = re.compile(r"Welcome to level (?P<lvl>\d+)", re.I)
_CAST_RE = re.compile(r"^You begin (?:casting|singing) (?P<spell>.+?)\.$")


def norm(s):
    return (s or "").replace("`", "'").strip().lower()


def duration_ticks(formula, duration, level):
    """Ticks a buff lasts for a caster of this level (EQMacEmu CalcBuffDuration_formula)."""
    level = max(1, int(level or 1))
    if formula >= 200:
        return formula
    if formula == 0:
        return 0
    if formula == 50:
        return PERMANENT
    calc = {1: level // 2, 2: 6 if level <= 1 else level // 2 + 5, 3: level * 30, 4: 50, 5: 2, 6: level // 2 + 2,
            7: level, 8: level + 10, 9: level * 2 + 10, 10: level * 3 + 10, 11: level * 30 + 90,
            12: max(1, level // 4)}.get(formula)
    if calc is None:
        return duration or 0
    if formula in (4, 5, 6, 7, 12):                      # fixed values: capped only if the spell sets a duration
        return min(calc, duration) if duration else calc
    return max(1, calc) if calc < duration else duration


# ----------------------------------------------------------------------------- spell data
class SpellBook:
    """name -> versions. Each version: dict(formula, duration, good, tt, cast_ms, you, other, fades, player)."""

    def __init__(self):
        self.by_name = {}
        self.source = "built-in"
        self.file = None
        self.mtime = None
        self._load_builtin()

    def _load_builtin(self):
        from .spells_data import SPELLS
        self.by_name = {}
        for name, vers in SPELLS.items():
            self.by_name[norm(name)] = [self._v(name, *v) for v in vers]
        self.source, self.file, self.mtime = "built-in", None, None

    @staticmethod
    def _v(name, f, d, good, tt, ct, you, other, fades, player):
        return {"name": name, "formula": int(f), "duration": int(d), "good": bool(int(good)), "tt": int(tt),
                "cast_ms": int(ct), "you": you or "", "other": other or "", "fades": fades or "",
                "player": bool(player)}

    def get(self, name):
        return self.by_name.get(norm(name)) or []

    # -- the game's own spell file ------------------------------------------------
    @staticmethod
    def find_file(log_dir):
        """spells_us.txt / spells_en.txt in the game folder (the Logs folder's parent), or None."""
        if not log_dir:
            return None
        here = os.path.abspath(log_dir)
        for d in (os.path.dirname(here), here, os.path.dirname(os.path.dirname(here))):
            for n in ("spells_us.txt", "spells_en.txt"):
                p = os.path.join(d, n)
                if os.path.isfile(p):
                    return p
        return None

    def use_game_file(self, log_dir):
        """Read the game's spell file if there is one (and it changed). Returns True if it's in use."""
        p = self.find_file(log_dir)
        if not p:
            if self.source != "built-in":
                self._load_builtin()
            return False
        try:
            mt = os.path.getmtime(p)
        except OSError:
            return False
        if p == self.file and mt == self.mtime:
            return True
        try:
            got = self.parse_file(p)
        except Exception as e:                      # odd format: keep the built-in list
            LOG.warning("couldn't read the game's spell file %s: %r", p, e)
            got = None
        if not got:
            self._load_builtin()
            return False
        self.by_name, self.source, self.file, self.mtime = got, "game", p, mt
        LOG.info("buff timers use the game's spell file %s (%d spells that last)", p, len(got))
        return True

    @classmethod
    def parse_file(cls, path):
        """'^'-separated spell file in the classic column order (id^name^...^buffdurationformula^buffduration^...)."""
        out, rows, bad = {}, 0, 0
        with open(path, encoding="cp1252", errors="replace") as fh:
            for line in fh:
                f = line.rstrip("\r\n").split("^")
                if len(f) < 105 or not f[0].strip().isdigit():
                    bad += 1
                    continue
                rows += 1
                try:
                    formula, dur = int(f[16]), int(f[17])
                    good, tt, ct = int(f[83]), int(f[98]), int(f[13])
                    lv = [int(x) for x in f[104:119]]
                except ValueError:
                    bad += 1
                    continue
                if formula == 0 or not f[1].strip():
                    continue
                v = cls._v(f[1].strip(), formula, dur, 1 if good else 0, tt, ct, f[6].strip(), f[7].rstrip(),
                           f[8].strip(), any(x < 255 for x in lv))
                lst = out.setdefault(norm(v["name"]), [])
                if not any(all(x[k] == v[k] for k in ("formula", "duration", "you", "other", "fades")) for x in lst):
                    lst.append(v)
        if rows < 200 or bad > rows:                # not the format we know
            return None
        for lst in out.values():
            lst.sort(key=lambda v: not v["player"])
        return out


# ----------------------------------------------------------------------------- timers
class Buffs:
    def __init__(self, state, book=None):
        root = state.setdefault("buffs", {})
        self.custom = root.setdefault("custom", {})          # spell (lower case) -> {"name", "secs", "good"}
        self.levels = root.setdefault("levels", {})          # char -> level seen in the log ("Welcome to level")
        self.timers = root.setdefault("timers", {})          # char -> [timer, ...]
        self.book = book or SpellBook()
        self.pending = {}                                     # char -> the cast in progress
        self.recent = {}                                      # char -> [{"t", "what", "spell"}] resists etc.
        self.level_of = lambda char: None                     # set by the app: level from /who or Settings
        self.dirty = False
        ids = [x["id"] for lst in self.timers.values() for x in lst]
        self._ids = itertools.count(max(ids + [int(time.time() * 1000)]) + 1)

    # -- level --------------------------------------------------------------------
    def level(self, char):
        lv = self.level_of(char)
        if lv:
            return int(lv), "set"
        lv = self.levels.get(char)
        if lv:
            return int(lv), "log"
        return DEFAULT_LEVEL, "default"

    # -- feeding --------------------------------------------------------------------
    def process(self, char, t, ev, line):
        msg = line.split("] ", 1)[-1] if line and line.startswith("[") else (line or "")
        if not msg:
            return
        typ = ev["type"] if ev else None
        if typ == "spell":
            sub = ev.get("sub")
            if sub == "cast":
                self._cast(char, t, ev["spell"])
            elif sub in ("fizzle", "interrupt", "nohold", "resist", "immune"):
                p = self.pending.pop(char, None)
                if p and p.get("provisional"):
                    self._drop(char, p["provisional"])
                if p and sub in ("resist", "immune", "nohold"):
                    what = {"resist": "resisted", "immune": "immune", "nohold": "did not take hold"}[sub]
                    self._note(char, t, what, ev.get("spell") or p["spell"])
            return
        if typ == "death" and ev.get("tgt") not in ("You", "YOU"):
            self._died(char, t, ev["tgt"])
        elif typ == "zone":
            self._zoned(char, t)
        if "Welcome to level" in msg:
            m = _LEVEL_RE.search(msg)
            if m:
                self.levels[char] = int(m.group("lvl"))
                self.dirty = True
            return
        if msg.startswith("Your ") and " worn off" in msg:
            m = _WORN_RE.match(msg)
            if m:
                self._worn(char, t, m.group("spell"), m.group("tgt"))
                return
        p = self.pending.get(char)
        if p:
            if t > p["until"]:
                self.pending.pop(char, None)
            elif self._landed(char, t, p, msg):
                return
        self._faded_on_me(char, t, msg)

    def _cast(self, char, t, spell):
        vers = self.book.get(spell)
        cast_ms = max((v["cast_ms"] for v in vers), default=0)
        p = {"spell": spell, "t": t, "vers": vers, "until": t + cast_ms / 1000 + LAND_WINDOW, "landed": 0}
        old = self.pending.get(char)
        if old and old.get("provisional") and not old["landed"]:
            pass                                   # a new cast without a fizzle line: the old one went off
        c = self.custom.get(norm(spell))
        if not vers and c:
            # a spell the data doesn't know, with a duration set by hand: the log can't show who it landed on
            p["provisional"] = self._add(char, t + cast_ms / 1000, spell, None, c["secs"], c.get("good", True),
                                         "set by hand", replace=False)     # an interrupted recast keeps the old one
        self.pending[char] = p

    def _landed(self, char, t, p, msg):
        for v in p["vers"]:
            tgt = None
            if v["you"] and msg == v["you"]:
                tgt = "You"
            elif v["other"] and msg.endswith(v["other"]) and len(msg) > len(v["other"]):
                tgt = msg[: -len(v["other"])].strip()
                if not tgt or len(tgt) > 60:
                    continue
            if tgt is None:
                continue
            c = self.custom.get(norm(v["name"]))
            if c:
                secs, how = c["secs"], "set by hand"
            else:
                lvl, _ = self.level(char)
                ticks = duration_ticks(v["formula"], v["duration"], lvl)
                if ticks <= 0:
                    return True
                secs, how = (None, "permanent") if ticks >= PERMANENT else (ticks * TICK, f"level {lvl}")
            self._add(char, t, v["name"], tgt, secs, v["good"], how, fades=v["fades"] if tgt == "You" else "")
            p["landed"] += 1
            if v["tt"] in SINGLE_TARGETS:
                self.pending.pop(char, None)
            return True
        return False

    def _add(self, char, t, spell, tgt, secs, good, how, fades="", replace=True):
        lst = self.timers.setdefault(char, [])
        key = (norm(spell), norm(tgt))
        if replace:
            lst[:] = [x for x in lst if (norm(x["spell"]), norm(x["target"])) != key]     # cast again: starts over
        x = {"id": next(self._ids), "spell": spell, "target": tgt, "start": t,
             "ends": t + secs if secs is not None else None, "secs": secs, "good": bool(good), "how": how,
             "fades": fades, "ended": None, "why": None}
        lst.append(x)
        del lst[: max(0, len(lst) - MAX_TIMERS)]
        LOG.debug("buff timer: %s on %s for %ss (%s)", spell, tgt or "?", secs, how)
        self.dirty = True
        return x["id"]

    def _drop(self, char, tid):
        lst = self.timers.get(char, [])
        lst[:] = [x for x in lst if x["id"] != tid]
        self.dirty = True

    def _end(self, x, t, why):
        if x["ended"] is None:
            x["ended"], x["why"] = t, why
            self.dirty = True

    def _live(self, char, t):
        return [x for x in self.timers.get(char, []) if x["ended"] is None and (x["ends"] is None or x["ends"] > t)]

    def _worn(self, char, t, spell, tgt):
        cands = [x for x in self._live(char, t) if norm(x["spell"]) == norm(spell)
                 and (tgt is None or norm(x["target"]) == norm(tgt))]
        if cands:
            self._end(min(cands, key=lambda x: x["ends"] or float("inf")), t, "wore off")

    def _faded_on_me(self, char, t, msg):
        if not msg or msg.startswith(("You begin", "You have")):
            return
        for x in self._live(char, t):
            if x["target"] == "You" and x["fades"] and msg == x["fades"]:
                self._end(x, t, "wore off")
                return

    def _died(self, char, t, who):
        for x in self._live(char, t):
            if x["target"] and norm(x["target"]) == norm(who):
                self._end(x, t, "died")

    def _zoned(self, char, t):
        # debuffs on mobs don't follow you into another zone
        for x in self._live(char, t):
            if not x["good"] and x["target"] != "You":
                self._end(x, t, "left the zone")

    def _note(self, char, t, what, spell):
        lst = self.recent.setdefault(char, [])
        lst.append({"t": t, "what": what, "spell": spell})
        del lst[:-5]

    # -- by hand ------------------------------------------------------------------------
    def clear(self, char, tid=None):
        if tid is None:
            self.timers[char] = []
        else:
            self._drop(char, tid)
        self.dirty = True

    def set_custom(self, spell, secs, good=True):
        k = norm(spell)
        if not k:
            raise ValueError("spell name needed")
        if secs is None or secs <= 0:
            self.custom.pop(k, None)
        else:
            self.custom[k] = {"name": spell.strip(), "secs": int(secs), "good": bool(good)}
        self.dirty = True

    # -- views --------------------------------------------------------------------------
    def _row(self, x, now):
        left = None if x["ends"] is None else max(0, round(x["ends"] - now))
        done = x["ended"] is not None or (x["ends"] is not None and x["ends"] <= now)
        return {"id": x["id"], "spell": x["spell"], "target": x["target"], "good": x["good"], "start": x["start"],
                "secs": x["secs"], "left": 0 if done else left, "how": x["how"],
                "done": done, "why": x["why"] or ("ran out" if done else None),
                "pct": None if not x["secs"] or left is None else round(100 * (0 if done else left) / x["secs"], 1)}

    def view(self, char, now=None, keep_done=FADED_SHOW):
        now = time.time() if now is None else now
        rows, seen = [], set()
        for x in reversed(self.timers.get(char, [])):              # newest first: a recast hides the older timer
            end = x["ended"] if x["ended"] is not None else x["ends"]
            key = (norm(x["spell"]), norm(x["target"]))
            if (end is not None and end <= now - keep_done) or key in seen:
                continue
            seen.add(key)
            rows.append(self._row(x, now))
        rows.reverse()
        lvl, lvl_from = self.level(char)
        return {"char": char, "level": lvl, "level_from": lvl_from,
                "buffs": [r for r in rows if r["good"]], "debuffs": [r for r in rows if not r["good"]],
                "recent": [r for r in self.recent.get(char, []) if now - r["t"] <= 30],
                "casting": (self.pending[char]["spell"] if char in self.pending and now <= self.pending[char]["until"]
                            else None),
                "source": self.book.source, "file": self.book.file,
                "custom": sorted(self.custom.values(), key=lambda c: c["name"].lower())}

    def prune(self, now=None):
        """Forget timers that ended a while ago (keeps the saved state small)."""
        now = time.time() if now is None else now
        for char, lst in self.timers.items():
            keep = [x for x in lst if ((x["ended"] if x["ended"] is not None else x["ends"]) or now + 1) > now - 3600]
            if len(keep) != len(lst):
                lst[:] = keep
                self.dirty = True

    def lookup(self, spell, char=None):
        """Duration of a spell at your level, for the tab's 'look up a spell' box."""
        lvl = self.level(char)[0] if char else DEFAULT_LEVEL
        out, seen = [], set()
        for v in self.book.get(spell):
            ticks = duration_ticks(v["formula"], v["duration"], lvl)
            sig = (v["formula"], v["duration"], v["you"], v["other"], v["good"])
            if sig in seen:
                continue
            seen.add(sig)
            out.append({"name": v["name"], "good": v["good"], "secs": None if ticks >= PERMANENT else ticks * TICK,
                        "max_secs": None if ticks >= PERMANENT else duration_ticks(v["formula"], v["duration"], 65) * TICK,
                        "you": v["you"], "other": v["other"], "player": v["player"]})
        c = self.custom.get(norm(spell))
        return {"spell": spell, "level": lvl, "versions": out, "custom": c}

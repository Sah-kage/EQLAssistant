"""Death recap: everything that hit you in the moments before you died, and what killed you.

The app keeps a short rolling record of what happens to you: hits and misses,
spell and damage-over-time damage, heals you received, resisted spells, and
stuns and the like. When the log says you died ("You have been slain by X!",
"You died."), the last WINDOW seconds of that record (since your previous death
at most) are saved as a recap:

  killed by     the name on the death line, or whoever hit you last
  killing blow  the last hit before you died
  by source     damage per attacker: total, hits, biggest hit, melee / spell / DoT, misses
  timeline      every event with how long before the death it happened

The log has no hit point numbers, so the recap shows damage and heals, not
your health bar.
"""
import itertools
import re
import time
from collections import deque

from .parser import MELEE_RE

WINDOW = 60          # seconds of history kept in a recap
KEEP = 100           # recaps kept per character
MAX_EVENTS = 400

_YOU = ("YOU", "You", "you")
_HEAL_RE = re.compile(r"^(?P<src>.+?) (?:has )?healed you for (?P<amt>\d+)(?: \((?P<full>\d+)\))? hit points?"
                      r"(?: by (?P<spell>.+?))?[.!]")
_SELF_HEAL_RE = re.compile(r"^You (?:have )?healed (?:yourself|you) for (?P<amt>\d+)(?: \((?P<full>\d+)\))? hit points?"
                           r"(?: by (?P<spell>.+?))?[.!]")
_NONMELEE_YOU_RE = re.compile(r"^You were hit by non-melee for (?P<amt>\d+)(?: points? of)? damage[.!]")
_STATUS_RE = re.compile(r"^You (?:are|have been|feel) (?P<what>stunned|knocked unconscious|feared|"
                        r"mesmerized|rooted|snared|silenced|charmed)\b", re.I)
_CAST_RE = re.compile(r"^(?P<src>.+?) begins (?:casting|to cast) (?P<spell>.+?)[.!]$")


def _msg(line):
    return line.split("] ", 1)[-1] if line and line.startswith("[") else (line or "")


class DeathRecap:
    def __init__(self, state):
        root = state.setdefault("deaths", {})
        self.by_char = root.setdefault("by_char", {})       # char -> [recap, ...] (oldest first)
        self.recent = {}                                   # char -> deque of events (not saved)
        self.last_death = {}                               # char -> time of the last death seen
        self.dirty = False
        ids = [d["id"] for lst in self.by_char.values() for d in lst]
        self._ids = itertools.count(max(ids + [int(time.time() * 1000)]) + 1)

    # -- feeding ------------------------------------------------------------------
    def _add(self, char, e):
        q = self.recent.get(char)
        if q is None:
            q = self.recent[char] = deque(maxlen=MAX_EVENTS)
        q.append(e)
        while q and q[0]["t"] < e["t"] - WINDOW:
            q.popleft()

    def process(self, char, t, ev, line=None, zone=None):
        typ = ev["type"] if ev else None
        if typ == "death" and ev.get("tgt") in _YOU:
            self._died(char, t, ev.get("src"), zone)
            return
        e = None
        if typ == "dmg" and ev.get("tgt") in _YOU:
            verb = None
            if ev.get("kind") == "melee" and line:
                m = MELEE_RE.match(_msg(line))
                verb = m.group("verb") if m else None
            e = {"k": "hit", "src": ev.get("src") or "Unknown", "amt": ev["amt"], "kind": ev.get("kind"),
                 "spell": ev.get("spell"), "verb": verb, "crit": bool(ev.get("crit"))}
        elif typ == "avoid" and ev.get("tgt") in _YOU:
            e = {"k": "avoid", "src": ev.get("src"), "verb": ev.get("verb"), "outcome": ev.get("outcome")}
        elif typ == "spell" and ev.get("sub") == "you_resisted":
            e = {"k": "resist", "spell": ev.get("spell")}
        elif ev is None and line:
            msg = _msg(line)
            if " healed " in msg:
                m = _SELF_HEAL_RE.match(msg) or _HEAL_RE.match(msg)
                if m:
                    src = m.groupdict().get("src") or "You"
                    e = {"k": "heal", "src": "You" if src in _YOU else src, "amt": int(m.group("amt")),
                         "spell": m.group("spell")}
            elif msg.startswith("You were hit by non-melee"):
                m = _NONMELEE_YOU_RE.match(msg)
                if m:
                    e = {"k": "hit", "src": "Unknown", "amt": int(m.group("amt")), "kind": "spell", "spell": None,
                         "verb": None, "crit": False}
            elif msg.startswith("You "):
                m = _STATUS_RE.match(msg)
                if m:
                    e = {"k": "status", "what": m.group("what").lower()}
            elif " begins " in msg:
                m = _CAST_RE.match(msg)
                if m and m.group("src") not in _YOU and m.group("spell") not in ("a spell",):
                    e = {"k": "cast", "src": m.group("src"), "spell": m.group("spell")}
        if e:
            e["t"] = t
            self._add(char, e)

    def _died(self, char, t, killer, zone):
        lst = self.by_char.setdefault(char, [])
        if self.last_death.get(char) == t:
            # "You died." and "You have been slain by X!" for the same death: keep the named killer
            if killer and lst and lst[-1]["t"] == t and lst[-1].get("killer_from") != "log":
                lst[-1].update(killer=killer, killer_from="log")
                self.dirty = True
            return
        self.last_death[char] = t
        since = t - WINDOW
        evs = [e for e in self.recent.get(char, ()) if e["t"] >= since]   # (cleared at each death)
        self.recent[char] = deque(maxlen=MAX_EVENTS)
        hits = [e for e in evs if e["k"] == "hit"]
        blow = hits[-1] if hits else None
        killer_from = "log" if killer else ("last hit" if blow else None)
        if not killer:
            killer = blow["src"] if blow else None
        src = {}
        for e in evs:
            if e["k"] not in ("hit", "avoid") or not e.get("src"):
                continue
            s = src.setdefault(e["src"], {"name": e["src"], "total": 0, "hits": 0, "max": 0, "melee": 0, "spell": 0,
                                          "dot": 0, "crits": 0, "avoided": 0, "spells": {}})
            if e["k"] == "avoid":
                s["avoided"] += 1
                continue
            s["total"] += e["amt"]
            s["hits"] += 1
            s["max"] = max(s["max"], e["amt"])
            s["crits"] += e.get("crit", False)
            kind = e.get("kind") if e.get("kind") in ("melee", "dot") else "spell"
            s[kind] += e["amt"]
            if e.get("spell"):
                s["spells"][e["spell"]] = s["spells"].get(e["spell"], 0) + e["amt"]
        total = sum(e["amt"] for e in hits)
        rows = sorted(src.values(), key=lambda s: -s["total"])
        for s in rows:
            s["pct"] = round(100 * s["total"] / total, 1) if total else 0
        heals = [e for e in evs if e["k"] == "heal"]
        recap = {
            "id": next(self._ids), "t": t, "zone": zone, "killer": killer, "killer_from": killer_from,
            "blow": dict(blow, ago=round(t - blow["t"])) if blow else None,
            "window": round(t - evs[0]["t"]) if evs else 0, "first": evs[0]["t"] if evs else t,
            "total": total, "hits": len(hits),
            "last5": sum(e["amt"] for e in hits if t - e["t"] <= 5),
            "last10": sum(e["amt"] for e in hits if t - e["t"] <= 10),
            "healed": sum(e["amt"] for e in heals), "heals": len(heals),
            "avoided": sum(1 for e in evs if e["k"] == "avoid"),
            "resisted": sum(1 for e in evs if e["k"] == "resist"),
            "sources": rows,
            "events": [dict(e, ago=round(t - e["t"])) for e in evs][-MAX_EVENTS:],
        }
        lst.append(recap)
        del lst[: max(0, len(lst) - KEEP)]
        self.dirty = True

    # -- views ----------------------------------------------------------------------
    def view(self, char):
        lst = self.by_char.get(char, [])
        rows = [{k: d[k] for k in ("id", "t", "zone", "killer", "total", "hits", "last10", "healed", "window")}
                | {"blow": d["blow"]["amt"] if d["blow"] else None} for d in reversed(lst)]
        killers = {}
        for d in lst:
            if d["killer"]:
                killers[d["killer"]] = killers.get(d["killer"], 0) + 1
        return {"char": char, "deaths": rows,
                "killers": sorted(({"name": k, "n": n} for k, n in killers.items()), key=lambda x: -x["n"])[:10],
                "latest": lst[-1]["id"] if lst else None}

    def get(self, char, rid):
        for d in self.by_char.get(char, []):
            if d["id"] == rid:
                return d
        return None

    def delete(self, char, rid):
        lst = self.by_char.get(char, [])
        self.by_char[char] = [d for d in lst if d["id"] != rid]
        self.dirty = True

    def clear(self, char):
        self.by_char[char] = []
        self.dirty = True

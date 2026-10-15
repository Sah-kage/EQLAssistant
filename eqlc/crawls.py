"""Dungeon Crawl runs: how long each crawl took, plus what you got from it.

How a run is timed:
  "<ZONE NAME> is now available to you."  - the run is set up for that zone (timer not running yet)
  start  = the first kill inside that zone's instance
  end    = the first line containing "from Reward Chest" (looting the reward chest)
Fallbacks, for runs where those lines are missing:
  - entering an instanced zone with no "available" line starts a run whose start
    time isn't trusted (shown, but never used for personal bests);
  - "You have completed the Dungeon Crawl..." with no chest loot afterwards ends
    the run at that line once you leave or start the next crawl.
Porting out (Gate, Succor, etc. drop you out of the instance) and coming back
into the same instance continues the same run; the time you spent outside is
shown separately. A run that never completes (a normal farming instance, or an
abandoned crawl) is kept as "not completed" once you've been gone for
`grace` minutes, and can be hidden or deleted.
"""
import itertools
import os
import re
import time

from . import integrity as I
from .classes import ClassSpotter

from .motes import mote_matches

GRACE = 30 * 60          # outside the instance this long without returning = run abandoned
MAX_RUN = 12 * 3600      # nothing realistic takes longer than this
AFTER_DONE = 120         # chest loot / XP / refund lines within this long after completion
MAX_RUNS = 1000
TIER_NAMES = {0: "Base", 1: "Awakened", 2: "Adaptive", 3: "Fused", 4: "Refined"}


_PLAYER = re.compile(r"^[A-Z][a-z]{2,14}$")          # EQ player names: one capitalised word
_GROUP_LINE = re.compile(r"^(?P<who>[A-Z][a-z]{2,14}) (?:tells the group|tells the raid|has joined the group|"
                         r"has joined the raid|is now the leader of your group)", re.I)


# your pet talking to you: "Gobaner tells you, 'Attacking a ghoul Master.'"
_PET_LINE = re.compile(r"^(?P<who>[A-Z][a-z]{2,14}) (?:tells you|says),? '.*\bmaster\b", re.I)


# Charm spells (EQLWiki): Charm / Beguile / Allure ... say "Someone has been charmed.";
# Dominate Undead and the like say "Someone moans.", Charm Animals "Someone blinks."
_CHARMED = re.compile(r"^(?P<who>[A-Z][a-z]{2,14}) has been charmed\.?$")
_CHARM_LAND = re.compile(r"^(?P<who>[A-Z][a-z]{2,14}) (?:moans|blinks)\.$")
_CHARM_WORDS = ("charm", "beguile", "dominate", "cajol", "thrall", "befriend", "allure", "dictate", "agacerie",
                "call of karana", "tunare's request", "whispers")


def looks_like_mob(name):
    n = (name or "").strip()
    return n.lower().startswith(("a ", "an ", "the ")) or " " in n or "`" in n


def players_of(r, npcs=()):
    """The other players in a run. Names that turned out to be NPCs (a charmed mob, a pet) are left out,
    unless something only a player does (group chat, looting, /who) showed them to be a player."""
    sure = set(r.get("confirmed") or ())
    bad = set(r.get("npcs") or ()) | set(npcs)
    return sorted(n for n in (r.get("players") or {}) if n in sure or n not in bad)


def party(r, npcs=()):
    """'solo' or 'group' for a run: the instance name says so, or other players took part."""
    mode = (r.get("mode") or "").lower()
    if mode in ("solo", "group"):
        return mode
    return "group" if players_of(r, npcs) else "solo"


def same_zone(a, b):
    """'Lower Guk', 'The Lower Guk' and 'lower guk' are the same zone."""
    def norm(s):
        s = (s or "").lower().replace("`", "'").strip()
        s = s[4:] if s.startswith("the ") else s
        return "".join(ch for ch in s if ch.isalnum())
    return bool(a) and bool(b) and norm(a) == norm(b)


def tier_label(level, tier=""):
    if level is None:
        return tier or "?"
    return f"D{level}" + (f" {tier}" if tier else (f" {TIER_NAMES[level]}" if level in TIER_NAMES and level else ""))


class Crawls:
    def __init__(self, state, proof_dir=None):
        self.proof_dir = proof_dir                     # where each run's raw lines are kept (live runs only)
        self.is_pet = lambda char, name: False         # set by the app: pets don't make a run "multiplayer"
        self.pets = {}                                 # char -> pet names heard calling you "Master"
        self._charming = {}                            # char -> when you last started casting a charm spell
        self.saved_classes = lambda char: None         # set by the app: your three classes from Settings / who
        self._meta = None
        s = state.setdefault("crawls", {})
        self.npcs = s.setdefault("npcs", {})           # char -> {name: time}: one-word names seen acting as NPCs
        self.runs = s.setdefault("runs", [])
        self.active = s.setdefault("active", {})     # char -> run id
        self.where = {}                                # char -> last zone event (not saved)
        self.classes = ClassSpotter(state)             # who is what class (from /who and spells seen)
        self.dirty = False
        self._ids = itertools.count(max([r["id"] for r in self.runs] + [int(time.time() * 1000)]) + 1)

    # -- helpers ----------------------------------------------------------------
    def _get(self, rid):
        for r in reversed(self.runs):
            if r["id"] == rid:
                return r
        return None

    def current(self, char):
        rid = self.active.get(char)
        return self._get(rid) if rid else None

    def _new(self, char, z, t, start_known=True):
        r = {"id": next(self._ids), "char": char, "zone": z["zone"], "raw": z["raw"], "tier": z["tier"],
             "level": z["level"], "mode": z["mode"], "inst_id": z["inst_id"],
             "start": t, "start_known": start_known, "end": None, "status": "active",
             "left_at": None, "outside": 0.0, "exits": 0, "last": t,
             "kills": 0, "deaths": 0, "first_kill": None, "motes": {}, "xp": 0.0,
             "chest": {}, "reward_xp": False, "refund": None, "notes": [],
             "entered": bool(z.get("inst")) and not z.get("from_available"), "completed_at": None,
             "offered": t, "waiting_kill": True, "proof": I.new_proof(history=self._meta is None)}
        self.runs.append(r)
        if len(self.runs) > MAX_RUNS:
            del self.runs[: len(self.runs) - MAX_RUNS]
        self.active[char] = r["id"]
        self.dirty = True
        return r

    def _close(self, char, r, status, t):
        if r["status"] == "active":
            if status == "left" and r.get("completed_at"):
                status = "done"                          # finished, but the chest was never looted
                r["end"] = r["completed_at"]
            r["status"] = status
            if status == "left":
                r["end"] = r["left_at"] or r["last"] or t
        if self.active.get(char) == r["id"]:
            del self.active[char]
        self.dirty = True

    def _inside(self, char):
        """The run you're physically in right now (not ported out), if any."""
        r = self.current(char)
        if not r or r["status"] != "active" or r["left_at"] is not None:
            return None
        if r.get("entered", True):
            return r
        here = self.where.get(char)
        if here is None or same_zone(here.get("zone"), r["zone"]):
            # no zone-in line seen since the crawl was offered (or it named the crawl zone):
            # you're in it, so take kills
            r["entered"] = True
            return r
        return None

    def _recent(self, char, t):
        """Active run, or one that completed moments ago (for chest/XP/refund lines)."""
        r = self.current(char)
        if r:
            return r
        for r in reversed(self.runs):
            if r["char"] == char and r["status"] == "done" and r["end"] and 0 <= t - r["end"] <= AFTER_DONE:
                return r
            if r["char"] == char:
                break
        return None

    def _expire(self, char, t):
        r = self.current(char)
        if not r or r["status"] != "active":
            return
        never_went = not r.get("entered", True) and t - r["start"] > GRACE
        if never_went:                                   # instance offered but you never went in
            self.runs.remove(r)
            self.active.pop(char, None)
            self.dirty = True
        elif (r["left_at"] is not None and t - r["left_at"] > GRACE) or t - r["start"] > MAX_RUN:
            self._close(char, r, "left", t)

    # -- events ----------------------------------------------------------------------
    def process(self, char, t, ev, line=None, meta=None):
        """Feed every parsed log event (only once per line).

        meta = {"now": wall clock, "mono": monotonic clock} when the line is read live
        as the game writes it; None for older lines (history scans, catching up)."""
        self._meta = meta
        self._expire(char, t)
        before = self.current(char)
        other = self.classes.feed(char, t, line)
        if self.classes.dirty:
            self.classes.dirty, self.dirty = False, True
        if other:
            r = self._inside(char)
            if r:
                self._note_player(char, r, other)      # someone casting / healing in your instance
        self._process(char, t, ev, line)
        after = self.current(char)
        if line:
            for r in {id(x): x for x in (before, after) if x}.values():
                if r["status"] == "active" or (r["status"] == "done" and r.get("end") == t and r is before):
                    self._feed(r, t, line, meta)

    def _feed(self, r, t, line, meta):
        p = r.get("proof")
        if p is None:
            return
        I.feed(p, t, line, meta)
        if self.proof_dir and meta is not None:
            try:
                with open(I.proof_path(self.proof_dir, r["id"]), "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass

    def file_event(self, char, kind, now=None):
        """The log file shrank or already-read lines changed: flag the run in progress."""
        r = self.current(char)
        if r and r.get("proof") is not None:
            r["proof"]["file_events"].append({"kind": kind, "t": time.time() if now is None else now})
            self.dirty = True

    def _note_player(self, char, r, name, sure=False):
        """Another player took part in this run (so it's multiplayer).

        sure: something only a player does (group chat, joining the group, looting, /who).
        Otherwise (hitting, killing, casting) it may be a charmed mob or a pet with a one-word name."""
        if (not name or name in ("You", "YOU") or not _PLAYER.match(name) or self.is_pet(char, name)
                or name in self.pets.get(char, ())):
            return
        if name.lower() in (char or "").lower().split("_")[:1]:
            return
        if not sure:
            me, _, server = (char or "").partition("_")
            sure = self.classes.who(server or "-", name) is not None
        pl = r.setdefault("players", {})
        if name not in pl:
            self.dirty = True
        pl[name] = pl.get(name, 0) + 1
        if sure and name not in r.setdefault("confirmed", []):
            r["confirmed"].append(name)
            self.dirty = True
        if name in self.npcs.get(char, {}) and name not in r.setdefault("npcs", []):
            r["npcs"].append(name)                       # seen acting as an NPC before (e.g. you fought it)

    def _is_npc(self, char, name, t=None):
        """Evidence that a one-word name is an NPC: a charmed mob, a pet, a named mob."""
        if not name or not _PLAYER.match(name):
            return
        known = self.npcs.setdefault(char, {})
        if name not in known:
            if len(known) >= 500:
                del known[min(known, key=known.get)]
            self.dirty = True
        known[name] = t or time.time()
        r = self.current(char)
        if r and name in (r.get("players") or {}) and name not in r.setdefault("npcs", []):
            r["npcs"].append(name)
            self.dirty = True

    def _confirmed(self, r):
        return set(r.get("confirmed") or ())

    def _npc_signals(self, char, t, ev):
        """Charmed mobs hit and kill mobs like players do. Tell them apart by what else they do:
        you hit them, they hit you, they hit or get hit by a known player, you killed them."""
        typ = ev["type"] if ev else None
        if typ not in ("dmg", "avoid", "death"):
            return
        src, tgt = ev.get("src"), ev.get("tgt")
        r = self.current(char)
        sure = self._confirmed(r) if r else set()
        if typ == "death":
            if src == "You" and tgt not in sure:
                self._is_npc(char, tgt, t)               # "You have slain Gorgalosk!"
            return
        if src == "You" and tgt not in ("You", "YOU") and tgt not in sure:
            self._is_npc(char, tgt, t)                   # you hit it
        elif tgt in ("You", "YOU") and src not in sure:
            self._is_npc(char, src, t)                   # it hit you (a charm breaking)
        elif src in sure and tgt not in sure:
            self._is_npc(char, tgt, t)                   # a group member hit it
        elif tgt in sure and src not in sure:
            self._is_npc(char, src, t)                   # it hit a group member

    def set_player(self, char, name, is_player):
        """'Not a player' / 'Is a player' buttons: fixes every run of this character."""
        if is_player:
            self.npcs.get(char, {}).pop(name, None)
        else:
            self._is_npc(char, name)
        for r in self.runs:
            if r["char"] != char or name not in (r.get("players") or {}):
                continue
            conf, bad = r.setdefault("confirmed", []), r.setdefault("npcs", [])
            if is_player:
                if name in bad:
                    bad.remove(name)
                if name not in conf:
                    conf.append(name)
            else:
                if name in conf:
                    conf.remove(name)
                if name not in bad:
                    bad.append(name)
        self.dirty = True

    def _party_signals(self, char, t, ev, line):
        if line and "aster" in line:
            m = _PET_LINE.match(line.split("] ", 1)[-1])
            if m:
                pet = m.group("who").capitalize()
                self.pets.setdefault(char, set()).add(pet)
                self._is_npc(char, pet, t)                 # your pet (or a mob you charmed)
                for r in (self.current(char),):
                    if r and pet in (r.get("players") or {}):
                        del r["players"][pet]          # it was your pet all along
                        self.dirty = True
                return
        self._npc_signals(char, t, ev)
        if ev and ev.get("type") == "spell" and ev.get("sub") == "cast" and \
                any(w in (ev.get("spell") or "").lower() for w in _CHARM_WORDS):
            self._charming[char] = t
        if line and (" charmed" in line or line.endswith(("moans.", "blinks."))):
            msg = line.split("] ", 1)[-1]
            m = _CHARMED.match(msg)
            if not m and t - self._charming.get(char, -1e9) <= 15:
                m = _CHARM_LAND.match(msg)                       # your undead / animal charm landing
            if m:
                self._is_npc(char, m.group("who"), t)
                return
        r = self.current(char)
        if not r or r["status"] != "active":
            return
        typ = ev["type"] if ev else None
        if typ in ("dmg", "avoid"):
            if ev.get("tgt") not in ("You", "YOU") and looks_like_mob(ev.get("tgt")):
                self._note_player(char, r, ev.get("src"))           # a player hitting a mob
        elif typ == "death" and ev.get("src") and looks_like_mob(ev.get("tgt")):
            self._note_player(char, r, ev["src"])                   # "a ghoul has been slain by Bobbin!"
        elif typ == "loot" and ev.get("who") not in (None, "You"):
            self._note_player(char, r, ev["who"], sure=True)        # "--Bobbin has looted ...--"
        elif line:
            m = _GROUP_LINE.match(line.split("] ", 1)[-1])
            if m:
                self._note_player(char, r, m.group("who").capitalize(), sure=True)

    def _process(self, char, t, ev, line=None):
        self._party_signals(char, t, ev, line)
        typ = ev["type"] if ev else None
        if line and "from reward chest" in line.lower():
            self._chest(char, t)
        if typ == "zone":
            self._zone(char, t, ev)
        elif typ == "crawl":
            self._crawl(char, t, ev)
        elif typ == "death":
            r = self._inside(char)
            if r:
                r["last"] = t
                if ev["tgt"] in ("You", "YOU"):
                    r["deaths"] += 1
                else:
                    r["kills"] += 1
                    r["first_kill"] = r["first_kill"] or t
                    if r.get("waiting_kill"):
                        # the timer starts on the first kill; anything before it doesn't count
                        r.update(start=t, waiting_kill=False, outside=0.0, exits=0)
                        if r.get("proof") is not None:
                            I.mark(r["proof"], "start", t, self._meta)
                self.dirty = True
        elif typ == "xp":
            r = self._inside(char) or self._recent(char, t)
            if r and ev.get("pct"):
                r["xp"] = round(r["xp"] + ev["pct"], 3)
                self.dirty = True
        elif typ == "loot" and ev.get("who") == "You":
            src = (ev.get("corpse") or "").lower()
            r = self._recent(char, t) if src == "reward chest" else None
            if r:
                r["chest"][ev["item"]] = r["chest"].get(ev["item"], 0) + ev.get("qty", 1)
                self.dirty = True
        if line and "mote" in line.lower():
            r = self._inside(char) or (self._recent(char, t) if "Reward Chest" in line else None)
            if r:
                for tier, q in mote_matches(line):
                    r["motes"][tier] = r["motes"].get(tier, 0) + q
                self.dirty = True

    def _start(self, char, t, ev):
        """'<ZONE NAME> is now available to you.' - a new crawl starts now."""
        r = self.current(char)
        if (r and r["status"] == "active" and not r["start_known"] and r["left_at"] is None
                and same_zone(r["zone"], ev["zone"])):
            # you zoned in before the "available" line: same run, timed from the first kill after it
            r.update(start=t, offered=t, start_known=True, kills=0, deaths=0, first_kill=None, xp=0.0, motes={},
                     waiting_kill=True, entered=True)
            self.dirty = True
            return
        if r:
            if r["left_at"] is None:
                r["left_at"] = t
            self._close(char, r, "left", t)
        prev = next((x for x in reversed(self.runs) if x["char"] == char), None)
        r = self._new(char, dict(ev, from_available=True), t)
        here = self.where.get(char)
        just_done_here = prev is not None and here is not None and prev["raw"] == here.get("raw") and prev["status"] != "active"
        if here and same_zone(here.get("zone"), ev["zone"]) and not just_done_here:
            r["entered"] = True                          # already standing in it
            for k in ("raw", "tier", "level", "mode", "inst_id"):
                if here.get(k) not in (None, "") and not r.get(k):
                    r[k] = here[k]

    def _chest(self, char, t):
        """First 'from Reward Chest' line ends the run."""
        r = self.current(char)
        if not r:
            if self._recent(char, t):
                return                                   # more chest loot from a run that already ended
            z = self.where.get(char) or {"zone": "Unknown zone", "raw": "", "tier": "", "level": None,
                                          "mode": "", "inst_id": ""}
            r = self._new(char, z, t, start_known=False)
        if r.get("waiting_kill"):
            r["waiting_kill"] = False
            r["start_known"] = False                     # no kill seen, so no real start time
        if r.get("proof") is not None:
            I.mark(r["proof"], "end", t, self._meta)
        if r["left_at"] is not None:
            r["outside"] += max(0.0, t - r["left_at"])
            r["left_at"] = None
        r["end"] = t
        r["last"] = t
        r["status"] = "done"
        self.active.pop(char, None)
        self.dirty = True

    def _zone(self, char, t, z):
        self.where[char] = z
        r = self.current(char)
        if (r and r["status"] == "active" and not r.get("entered", True)
                and (z["inst"] or same_zone(z["zone"], r["zone"]))):
            # first time into the instance that was just offered: take its full name / tier
            for k in ("zone", "raw", "tier", "level", "mode", "inst_id"):
                if z.get(k) not in (None, ""):
                    r[k] = z[k]
            r["entered"] = True
            r["last"] = t
            self.dirty = True
            return
        if not z["inst"] and r and not r.get("entered", True):
            return                                        # still on the way to the crawl
        if r and r["status"] == "active" and (r["raw"] == z["raw"] or (
                same_zone(r["zone"], z["zone"]) and not (r["inst_id"] and z["inst_id"] and r["inst_id"] != z["inst_id"]))):
            if z["inst"] and not r["inst_id"] and not r["tier"]:     # learn the instance number / difficulty
                for k in ("zone", "raw", "tier", "level", "mode", "inst_id"):
                    if z.get(k) not in (None, ""):
                        r[k] = z[k]
            if r["left_at"] is not None:                  # back into the same instance
                r["outside"] += max(0.0, t - r["left_at"])
                r["left_at"] = None
            r["last"] = t
            self.dirty = True
            return
        if z["inst"]:
            if r:
                if r["left_at"] is None:
                    r["left_at"] = t
                self._close(char, r, "left", t)
            self._new(char, z, t, start_known=False)    # no "is now available" line seen
        elif r and r["status"] == "active" and r["left_at"] is None:
            r["left_at"] = t                              # ported/zoned out; may come back
            r["exits"] += 1
            self.dirty = True

    def _crawl(self, char, t, ev):
        sub = ev["sub"]
        if sub == "start":
            self._start(char, t, ev)
            return
        if sub == "done":
            # Not the end any more (the chest is), but remembered as a fallback end time.
            r = self.current(char)
            if r and not r.get("completed_at"):
                r["completed_at"] = t
                r["last"] = t
                self.dirty = True
            return
        r = self._recent(char, t)
        if not r:
            return
        if sub == "xp":
            r["reward_xp"] = True
        elif sub == "refund":
            r["refund"] = True
        elif sub == "charge_note":
            r["refund"] = False if r["refund"] is None else r["refund"]
            r["notes"].append(ev["text"])
        else:
            r["notes"].append(ev["text"])
        del r["notes"][:-6]
        self.dirty = True

    def tick(self, now=None):
        now = time.time() if now is None else now
        for char in list(self.active):
            self._expire(char, now)

    # -- manual edits ------------------------------------------------------------------
    def restart(self, char, now=None):
        """'Restart timer': the run starts now (e.g. you entered early and buffed for ages)."""
        r = self.current(char)
        if not r:
            z = self.where.get(char)
            if not z:
                return None
            r = self._new(char, z, time.time() if now is None else now)
            r["waiting_kill"] = False
            r["proof"]["manual_start"] = True
        else:
            r.update(start=time.time() if now is None else now, start_known=True, outside=0.0, exits=0,
                     kills=0, deaths=0, first_kill=None, motes={}, xp=0.0, left_at=None, waiting_kill=False)
            if r.get("proof") is not None:
                r["proof"]["manual_start"] = True
        self.dirty = True
        return r

    def stop(self, char, now=None):
        """'Stop timer': end the current run now (e.g. the Reward Chest line didn't show)."""
        r = self.current(char)
        if not r:
            return None
        now = time.time() if now is None else now
        if r.get("waiting_kill"):                      # nothing killed yet: no real time to keep
            r.update(waiting_kill=False, start_known=False, start=now)
        if r["left_at"] is not None:
            r["outside"] += max(0.0, now - r["left_at"])
            r["left_at"] = None
        r.update(end=now, last=now, status="done", stopped=True)
        if r.get("proof") is not None:
            r["proof"]["manual_stop"] = True
        self.active.pop(char, None)
        self.dirty = True
        return r

    def reset(self, char, now=None):
        """'Reset timer': back to 0:00, waiting for the next first kill in this zone."""
        now = time.time() if now is None else now
        r = self.current(char)
        if not r:
            z = self.where.get(char)
            if not z or not z.get("inst"):
                return None
            r = self._new(char, z, now)
            r["entered"] = True
        r.update(start=now, offered=now, start_known=True, waiting_kill=True, end=None, outside=0.0, exits=0,
                 kills=0, deaths=0, first_kill=None, motes={}, xp=0.0, chest={}, players={}, left_at=None,
                 completed_at=None, proof=I.new_proof(history=False))
        r["proof"]["manual_reset"] = True
        if self.proof_dir:
            try:
                os.remove(I.proof_path(self.proof_dir, r["id"]))
            except OSError:
                pass
        self.dirty = True
        return r

    def discard_current(self, char):
        """'Not a crawl': drop the active run (e.g. a normal farming instance)."""
        r = self.current(char)
        if r:
            self.runs.remove(r)
            self.active.pop(char, None)
            self.dirty = True

    def delete(self, rid):
        r = self._get(rid)
        if r:
            self.runs.remove(r)
            for c, a in list(self.active.items()):
                if a == rid:
                    del self.active[c]
            self.dirty = True

    def merge(self, other_runs):
        """Add runs found by a history rescan, skipping ones we already have."""
        def key(r):
            return (r["char"], r["raw"], round(r["end"] or r["start"]))
        have = {key(r) for r in self.runs}
        added = 0
        for r in other_runs:
            if r["status"] == "active" or key(r) in have:
                continue
            r = dict(r, id=next(self._ids))
            self.runs.append(r)
            have.add(key(r))
            added += 1
        if added:
            self.runs.sort(key=lambda r: r["start"])
            del self.runs[: max(0, len(self.runs) - MAX_RUNS)]
            self.dirty = True
        return added

    # -- views ------------------------------------------------------------------------
    def group(self, r):
        """You and the other players in a run, with their classes as far as the log shows."""
        return self.classes.group(r["char"], self.players(r), self.saved_classes(r["char"]))

    def _snap(self, r):
        if not self.proof_dir:
            return False
        from . import snapshot as S
        return S.exists(self.proof_dir, r["id"])

    def _npcs(self, r):
        return self.npcs.get(r["char"], {})

    def party(self, r):
        return party(r, self._npcs(r))

    def players(self, r):
        return players_of(r, self._npcs(r))

    def _bucket(self, r):
        """Personal bests are kept per zone, difficulty and solo / multiplayer."""
        return (r["zone"], r["level"], self.party(r))

    def _summary(self, r, now, fights=()):
        end = r["end"] if r["status"] != "active" else now
        waiting = r["status"] == "active" and r.get("waiting_kill")
        dur = 0.0 if waiting else max(0.0, end - r["start"])
        outside = 0.0 if waiting else r["outside"] + ((now - r["left_at"]) if r["status"] == "active" and r["left_at"] else 0)
        combat = None
        if fights:
            combat = 0.0
            for f in fights:
                a, b = max(f.start, r["start"]), min(f.last, end)
                if b > a:
                    combat += b - a
        motes = sum(r["motes"].values())
        hours = dur / 3600 if dur else 0
        return {
            "id": r["id"], "char": r["char"], "zone": r["zone"], "raw": r["raw"], "mode": r["mode"],
            "level": r["level"], "tier": r["tier"], "tier_label": tier_label(r["level"], r["tier"]),
            "start": r["start"], "end": r["end"], "status": r["status"], "start_known": r["start_known"],
            "duration": round(dur), "inside": round(max(0.0, dur - outside)), "outside": round(outside),
            "exits": r["exits"], "entered": r.get("entered", True), "away_now": r["status"] == "active" and r["left_at"] is not None,
            "to_first_kill": round(r["first_kill"] - r.get("offered", r["start"])) if r["first_kill"] else None,
            "waiting_kill": bool(waiting), "offered": r.get("offered", r["start"]),
            "proof": I.verdict(r),
            "party": self.party(r), "players": self.players(r),
            "left_out": sorted(set(r.get("players") or {}) - set(self.players(r))), "stopped": bool(r.get("stopped")),
            "combat": round(combat) if combat is not None else None,
            "kills": r["kills"], "deaths": r["deaths"],
            "motes": motes, "motes_tiers": r["motes"], "motes_per_hour": round(motes / hours, 1) if hours > 0.01 else None,
            "xp": r["xp"], "reward_xp": r["reward_xp"], "refund": r["refund"],
            "chest": [{"item": k, "qty": v} for k, v in sorted(r["chest"].items())], "notes": r["notes"],
            "group": self.group(r), "submitted": r.get("submitted"), "submit_error": r.get("submit_error"),
            "snapshot": self._snap(r) if r["status"] == "done" else False,
        }

    def bests(self, char=None):
        out = {}
        for r in self.runs:
            if r["status"] != "done" or not r["start_known"] or (char and r["char"] != char):
                continue
            d = r["end"] - r["start"]
            b = out.setdefault(self._bucket(r), {"zone": r["zone"], "level": r["level"], "party": self.party(r),
                                                 "tier_label": tier_label(r["level"], r["tier"]),
                                                 "runs": 0, "best": None, "best_id": None, "total": 0.0,
                                                 "last": None, "last_at": 0})
            b["runs"] += 1
            b["total"] += d
            if b["best"] is None or d < b["best"]:
                b["best"], b["best_id"] = d, r["id"]
            if r["end"] > b["last_at"]:
                b["last"], b["last_at"] = d, r["end"]
        rows = []
        for b in out.values():
            rows.append({"zone": b["zone"], "level": b["level"], "party": b["party"],
                         "tier_label": b["tier_label"], "runs": b["runs"],
                         "best": round(b["best"]), "best_id": b["best_id"], "avg": round(b["total"] / b["runs"]),
                         "last": round(b["last"]), "last_at": b["last_at"]})
        return sorted(rows, key=lambda x: (-x["last_at"]))

    def pb_for(self, r):
        best = None
        for o in self.runs:
            if o is r or o["status"] != "done" or not o["start_known"] or o["char"] != r["char"]:
                continue
            if self._bucket(o) == self._bucket(r):
                d = o["end"] - o["start"]
                best = d if best is None or d < best else best
        return best

    def view(self, char, fights=(), now=None):
        now = time.time() if now is None else now
        runs = [r for r in self.runs if r["char"] == char]
        cur = self.current(char)
        current = None
        if cur:
            current = self._summary(cur, now, fights)
            pb = self.pb_for(cur)
            current["pb"] = round(pb) if pb is not None else None
        last_done = next((r for r in reversed(runs) if r["status"] == "done"), None)
        just_done = None
        if last_done and now - last_done["end"] <= 10 * 60:
            just_done = self._summary(last_done, now, fights)
            pb = self.pb_for(last_done)
            just_done["pb"] = round(pb) if pb is not None else None
            just_done["new_pb"] = last_done["start_known"] and (pb is None or just_done["duration"] < pb)
        hist = []
        bests = {(b["zone"], b["level"], b["party"]): b["best_id"] for b in self.bests(char)}
        best_d = {(b["zone"], b["level"], b["party"]): b["best"] for b in self.bests(char)}
        for r in reversed(runs[-300:]):
            s = self._summary(r, now, fights)
            s["is_best"] = bests.get(self._bucket(r)) == r["id"]
            bd = best_d.get(self._bucket(r))
            s["vs_best"] = (s["duration"] - bd) if (bd is not None and r["status"] == "done" and r["start_known"]) else None
            hist.append(s)
        return {"char": char, "current": current, "just_done": just_done, "runs": hist, "bests": self.bests(char),
                "where": self.where.get(char)}

    def overlay(self, char, now=None):
        now = time.time() if now is None else now
        cur = self.current(char)
        if cur:
            s = self._summary(cur, now)
            pb = self.pb_for(cur)
            state = "away" if s["away_now"] else ("waiting" if not s["entered"] else
                                                  ("ready" if s["waiting_kill"] else "active"))
            return {"state": state,
                    "zone": s["zone"], "tier_label": s["tier_label"], "start_known": s["start_known"],
                    "elapsed": s["duration"], "pb": round(pb) if pb is not None else None, "kills": s["kills"],
                    "deaths": s["deaths"], "motes": s["motes"], "party": s["party"], "players": s["players"]}
        for r in reversed(self.runs):
            if r["char"] != char:
                continue
            if r["status"] == "done" and now - r["end"] <= 5 * 60:
                pb = self.pb_for(r)
                d = round(r["end"] - r["start"])
                return {"state": "done", "id": r["id"], "snap": self._snap(r), "zone": r["zone"], "tier_label": tier_label(r["level"], r["tier"]),
                        "elapsed": d, "pb": round(pb) if pb is not None else None,
                        "new_pb": r["start_known"] and (pb is None or d < pb), "kills": r["kills"],
                        "deaths": r["deaths"], "motes": sum(r["motes"].values()), "start_known": r["start_known"],
                        "party": self.party(r), "players": self.players(r)}
            break
        return None

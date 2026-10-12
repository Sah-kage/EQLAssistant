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
import time

from .motes import mote_matches

GRACE = 30 * 60          # outside the instance this long without returning = run abandoned
MAX_RUN = 12 * 3600      # nothing realistic takes longer than this
AFTER_DONE = 120         # chest loot / XP / refund lines within this long after completion
MAX_RUNS = 1000
TIER_NAMES = {0: "Base", 1: "Awakened", 2: "Adaptive", 3: "Fused", 4: "Refined"}


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
    def __init__(self, state):
        s = state.setdefault("crawls", {})
        self.runs = s.setdefault("runs", [])
        self.active = s.setdefault("active", {})     # char -> run id
        self.where = {}                                # char -> last zone event (not saved)
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
             "offered": t, "waiting_kill": True}
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
    def process(self, char, t, ev, line=None):
        """Feed every parsed log event (only once per line)."""
        self._expire(char, t)
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
        else:
            r.update(start=time.time() if now is None else now, start_known=True, outside=0.0, exits=0,
                     kills=0, deaths=0, first_kill=None, motes={}, xp=0.0, left_at=None, waiting_kill=False)
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
    @staticmethod
    def _bucket(r):
        return (r["zone"], r["level"])

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
            "combat": round(combat) if combat is not None else None,
            "kills": r["kills"], "deaths": r["deaths"],
            "motes": motes, "motes_tiers": r["motes"], "motes_per_hour": round(motes / hours, 1) if hours > 0.01 else None,
            "xp": r["xp"], "reward_xp": r["reward_xp"], "refund": r["refund"],
            "chest": [{"item": k, "qty": v} for k, v in sorted(r["chest"].items())], "notes": r["notes"],
        }

    def bests(self, char=None):
        out = {}
        for r in self.runs:
            if r["status"] != "done" or not r["start_known"] or (char and r["char"] != char):
                continue
            d = r["end"] - r["start"]
            b = out.setdefault(self._bucket(r), {"zone": r["zone"], "level": r["level"],
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
            rows.append({"zone": b["zone"], "level": b["level"], "tier_label": b["tier_label"], "runs": b["runs"],
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
        bests = {(b["zone"], b["level"]): b["best_id"] for b in self.bests(char)}
        best_d = {(b["zone"], b["level"]): b["best"] for b in self.bests(char)}
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
                    "deaths": s["deaths"], "motes": s["motes"]}
        for r in reversed(self.runs):
            if r["char"] != char:
                continue
            if r["status"] == "done" and now - r["end"] <= 5 * 60:
                pb = self.pb_for(r)
                d = round(r["end"] - r["start"])
                return {"state": "done", "zone": r["zone"], "tier_label": tier_label(r["level"], r["tier"]),
                        "elapsed": d, "pb": round(pb) if pb is not None else None,
                        "new_pb": r["start_known"] and (pb is None or d < pb), "kills": r["kills"],
                        "deaths": r["deaths"], "motes": sum(r["motes"].values()), "start_known": r["start_known"]}
            break
        return None

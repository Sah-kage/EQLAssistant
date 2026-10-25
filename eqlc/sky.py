"""Plane of Sky drop / turn-in tracking per character."""
import os
import re
import time

from . import sky_data as D


def _k(s):
    return s.lower().replace("`", "'").strip()


def build_db():
    classes = []
    items = {}      # key -> {"name", "source", "uses": [quest ids]}
    rewards = {}    # key -> quest id
    for cls, (abbr, npc, quests) in D.CLASSES.items():
        qs = []
        for qname, trig, reward, rune, its in quests:
            qid = f"{abbr}:{qname}"
            req = [{"name": f"Wind Rune {rune}", "source": D.SOURCES["rune"]}]
            for it in its:
                name, src = it.split("@")
                req.append({"name": name, "source": D.SOURCES[src]})
            for r in req:
                e = items.setdefault(_k(r["name"]), {"name": r["name"], "source": r["source"], "uses": []})
                e["uses"].append(qid)
            rewards[_k(reward)] = qid
            for extra in D.EXTRA_REWARDS.get((cls, qname), []):
                rewards[_k(extra)] = qid
            qs.append({"id": qid, "name": qname, "trigger": trig, "reward": reward, "items": req})
        classes.append({"name": cls, "abbr": abbr, "npc": npc, "quests": qs})
    return classes, items, rewards


CLASSES, ITEMS, REWARDS = build_db()
QUESTS = {q["id"]: q for c in CLASSES for q in c["quests"]}

# Any test reward named in a log line. Longest names first, so a longer name wins over a shorter one inside it.
REWARD_RE = re.compile(r"(?<![\w'])(" + "|".join(re.escape(n) for n in sorted(REWARDS, key=len, reverse=True))
                       + r")(?![\w'])", re.IGNORECASE)
# Lines that name an item without you getting it: chat, other people's loot, "you cannot ..." messages.
_NOT_MINE = re.compile(r"\b(tells|says|shouts|auctions|told you|out of character|has looted|"
                       r"you cannot|you can not|you do not|you don't|lore item)\b|, '", re.IGNORECASE)


# Wind runes go to the Currency tab, not your bags, so inventory exports don't list them.
RUNE_NAMES = {_k("Wind Rune " + r): "Wind Rune " + r for r in D.WIND_RUNES}
_RUNE = r"(?P<q>an?|\d+)\s+(?:x\s*)?(?P<name>wind runes?\s+[a-z]+)"
_CURRENCY_RES = [
    # "You receive 2 Wind Rune Azia." / "You have gained a Wind Rune Azia" / "You earned 1 Wind Rune Azia"
    re.compile(r"^you (?:receive|have received|gain|gained|have gained|earn|earned|have earned|"
               r"were awarded|are awarded|have been awarded|have been given|got|have found|found) " + _RUNE, re.I),
    # "Wind Rune Azia x2 has been added to your currency." / "2 Wind Rune Azia added to your alternate currency"
    re.compile(r"^(?:(?P<q>an?|\d+)\s+)?(?P<name>wind runes?\s+[a-z]+)(?:\s*\(?x\s*(?P<q2>\d+)\)?)?"
               r".*\b(?:added to|into) your (?:alternate )?currenc", re.I),
]


def rune_in_line(line):
    """(rune name, qty) if this line says a Wind Rune went into your currency, else None.
    Plain "--You have looted ...--" lines are counted as loot already, so they're skipped here."""
    msg = line.split("] ", 1)[-1].strip()
    low = msg.lower()
    if "wind rune" not in low or low.startswith("--") or _NOT_MINE.search(msg):
        return None
    for rx in _CURRENCY_RES:
        m = rx.search(msg)
        if not m:
            continue
        words = m.group("name").split()
        key = _k("Wind Rune " + words[-1])
        if key not in RUNE_NAMES:
            return None
        q = m.group("q") or (m.groupdict().get("q2"))
        qty = int(q) if q and q.isdigit() else 1
        return RUNE_NAMES[key], qty
    return None


def reward_in_line(line):
    """Quest id whose reward this log line says you received, else None.

    Catches "You receive X from Y.", "Y gives you X", "You have been given X",
    "--You have looted X--", "X has been added to your inventory" and the like,
    while ignoring chat and other people's loot.
    """
    m = REWARD_RE.search(line)
    if not m:
        return None
    msg = line.split("] ", 1)[-1].lower()
    if "you" not in msg:
        return None
    if not msg.startswith(("you receive", "you have received", "--you have looted")) and _NOT_MINE.search(msg):
        return None
    return REWARDS.get(_k(m.group(1)))


def _blank():
    return {"loot": [], "done": {}, "unlocked": [], "inventory": None}


class SkyTracker:
    """State lives in a plain dict so it can be saved to JSON."""

    def __init__(self, state):
        self.s = state.setdefault("sky", {})
        self.group_drops = state.setdefault("group_drops", [])
        self.dirty = False

    def char(self, name):
        c = self.s.get(name)
        if c is None:
            c = self.s[name] = _blank()
        return c

    def characters(self):
        return sorted(self.s)

    # -- log events -----------------------------------------------------
    def process(self, char, t, ev):
        typ = ev["type"]
        if typ == "loot":
            key = _k(ev["item"])
            if key not in ITEMS and key not in REWARDS:
                return
            rec = {"t": t, "item": ITEMS.get(key, {"name": ev["item"]})["name"],
                   "qty": ev.get("qty", 1), "corpse": ev.get("corpse")}
            if ev["who"] == "You":
                c = self.char(char)
                sig = (t, rec["item"])
                if any((l["t"], l["item"]) == sig for l in c["loot"][-30:]):
                    return
                c["loot"].append(rec)
                self.dirty = True
            else:
                rec["who"] = ev["who"]
                rec["seen_by"] = char
                self.group_drops.append(rec)
                del self.group_drops[:-500]
                self.dirty = True
        elif typ == "receive":
            qid = REWARDS.get(_k(ev["item"]))
            if qid:
                self.mark_done(char, qid, t, "log")

    def process_line(self, char, t, line):
        """Any new log line showing you got a Sky test reward marks that test done,
        and Wind Runes going into your currency are counted."""
        qid = reward_in_line(line)
        if qid:
            self.mark_done(char, qid, t, "log")
        rune = rune_in_line(line)
        if rune:
            self.add_currency_rune(char, t, *rune)
        return qid

    def add_currency_rune(self, char, t, name, qty):
        c = self.char(char)
        # the same pickup can show as a loot line and a currency line: count it once
        for l in c["loot"][-10:]:
            if l["item"] == name and abs(l["t"] - t) <= 2 and l.get("corpse") != "currency":
                return False
        c["loot"].append({"t": t, "item": name, "qty": qty, "corpse": "currency"})
        self.dirty = True
        return True

    def set_currency(self, char, counts, t=None):
        """Wind Rune counts copied from the in-game Currency tab: the true count from now on."""
        c = self.char(char)
        clean = {}
        for name, n in (counts or {}).items():
            k = _k(name if name.lower().startswith("wind rune") else "Wind Rune " + name)
            if k in RUNE_NAMES:
                try:
                    clean[k] = max(0, int(n))
                except (TypeError, ValueError):
                    continue
        c["currency"] = {"t": time.time() if t is None else t, "counts": clean}
        self.dirty = True

    def mark_done(self, char, qid, t, how):
        c = self.char(char)
        if qid in c["done"]:
            return False
        c["done"][qid] = {"t": t, "how": how}
        self.dirty = True
        return True

    # -- inventory export (/outputfile inventory) -------------------------
    def load_inventory(self, char, path):
        """Read an export the game wrote next to the logs."""
        try:
            with open(path, encoding="cp1252", errors="replace") as fh:
                text = fh.read()
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        return self.load_inventory_text(char, text, mtime, path)

    def load_inventory_text(self, char, text, t=None, source=""):
        """Use an inventory export (read from disk or imported in the app) as the true
        count of what this character holds, and tick every test whose reward they own."""
        from .inventory import parse
        from .exalts import exaltations
        inv = parse(text)
        t = time.time() if t is None else t
        c = self.char(char)
        c["inventory"] = {"t": t, "path": source,
                          "counts": {_k(k): v for k, v in inv["counts"].items()},
                          "owned": sorted({_k(k) for k in inv["owned"]}),
                          "where": {_k(k): v for k, v in inv["where"].items()},
                          "items": inv["items"], "exalts": exaltations(text)}
        ticked = []
        for k in c["inventory"]["owned"]:
            qid = REWARDS.get(k)
            if qid and qid not in c["done"]:
                c["done"][qid] = {"t": t, "how": "inventory"}
                ticked.append(qid)
        self.dirty = True
        return {"char": char, "items": inv["items"], "distinct": len(inv["owned"]), "sky_ticked": ticked}

    # -- manual edits -----------------------------------------------------
    def set_done(self, char, qid, done):
        c = self.char(char)
        if done:
            c["done"][qid] = {"t": time.time(), "how": "manual"}
        else:
            c["done"].pop(qid, None)
        self.dirty = True

    def set_unlocked(self, char, cls, unlocked):
        c = self.char(char)
        s = set(c["unlocked"])
        (s.add if unlocked else s.discard)(cls)
        c["unlocked"] = sorted(s)
        self.dirty = True

    def adjust(self, char, item, delta):
        """Manual +/- for an item count (e.g. drops looted before logging was on)."""
        c = self.char(char)
        key = _k(item)
        if key not in ITEMS:
            return
        c["loot"].append({"t": time.time(), "item": ITEMS[key]["name"], "qty": delta, "corpse": "manual"})
        self.dirty = True

    # -- view ---------------------------------------------------------------
    def _since(self, c, k):
        """Starting point for item k: (time, count). Wind runes come from the Currency tab
        (typed in by you), everything else from the latest inventory export."""
        inv = c.get("inventory")
        if k in RUNE_NAMES:
            cur = c.get("currency")
            if cur:
                return cur["t"], cur["counts"].get(k, 0)
            if inv and k in inv["counts"]:
                return inv["t"], inv["counts"][k]
            return 0, 0
        if inv:
            return inv["t"], inv["counts"].get(k, 0)
        return 0, 0

    def held_counts(self, char):
        c = self.char(char)
        keys = set(ITEMS)
        held = {}
        for k in keys:
            since, n = self._since(c, k)
            held[k] = [since, n]
        # in time order: loot adds, a turn-in uses one of each item it needs (only what you had then)
        events = []
        for l in c["loot"]:
            k = _k(l["item"])
            if k in held and l["t"] > held[k][0]:
                events.append((l["t"], 1, k, l["qty"]))
        for qid, d in c["done"].items():
            if qid not in QUESTS:                 # a test EQLWiki no longer lists
                continue
            # Only turn-ins seen in the log consume items. Manual ticks mean
            # "already done", usually from before tracking started.
            if d["how"] != "log":
                continue
            for it in QUESTS[qid]["items"]:
                k = _k(it["name"])
                if k in held and d["t"] > held[k][0]:
                    events.append((d["t"], 0, k, -1))
        for _, kind, k, q in sorted(events, key=lambda e: (e[0], e[1])):
            held[k][1] = held[k][1] + q if kind else max(0, held[k][1] - 1)
        return {k: max(0, v[1]) for k, v in held.items() if v[1]}

    def view(self, char):
        c = self.char(char)
        held = self.held_counts(char)
        where = (c.get("inventory") or {}).get("where") or {}
        out_classes = []
        need = {}
        uses = {}                                   # item key -> {"name", "source", "for": [quests]}
        tot_done = tot = 0
        for cls in CLASSES:
            qs = []
            ndone = 0
            for q in cls["quests"]:
                done = c["done"].get(q["id"])
                items = []
                for it in q["items"]:
                    h = held.get(_k(it["name"]), 0)
                    items.append({"name": it["name"], "source": it["source"], "held": h,
                                  "where": where.get(_k(it["name"]), [])})
                    u = uses.setdefault(_k(it["name"]), {"name": it["name"], "source": it["source"], "for": []})
                    u["for"].append(f"{cls['abbr']} {q['name']}")
                    if not done:
                        e = need.setdefault(_k(it["name"]), {"name": it["name"], "source": it["source"],
                                                             "need": 0, "held": h, "for": []})
                        e["need"] += 1
                        e["for"].append(f"{cls['abbr']} {q['name']}")
                have_all = all(i["held"] > 0 for i in items)
                ready = not done and have_all
                ndone += bool(done)
                qs.append({"id": q["id"], "name": q["name"], "trigger": q["trigger"], "reward": q["reward"],
                           "done": bool(done), "how": done["how"] if done else None,
                           "ready": ready, "again": bool(done) and have_all, "items": items})
            tot += len(qs)
            tot_done += ndone
            unlocked = cls["name"] in c["unlocked"] or ndone == len(qs)
            out_classes.append({"name": cls["name"], "abbr": cls["abbr"], "npc": cls["npc"],
                                "wiki": D.PAGES.get(cls["name"], ""),
                                "done": ndone, "total": len(qs), "unlocked": unlocked,
                                "manual_unlock": cls["name"] in c["unlocked"], "quests": qs})
        shopping = sorted(need.values(), key=lambda e: (e["held"] >= e["need"], e["source"], e["name"]))
        # items you hold that no quest still needs (every quest using them is done), or more than are still needed
        spare = []
        for k, u in uses.items():
            h = held.get(k, 0)
            n = need[k]["need"] if k in need else 0
            if h > n:
                spare.append({"name": u["name"], "source": u["source"], "held": h, "need": n, "spare": h - n,
                              "for": u["for"], "where": where.get(k, [])})
        spare.sort(key=lambda e: (e["need"] > 0, e["source"], e["name"]))
        drops = sorted(c["loot"], key=lambda l: -l["t"])[:300]
        group = [g for g in self.group_drops if g.get("seen_by") == char][-200:][::-1]
        inv = c.get("inventory")
        cur = c.get("currency")
        runes = [{"name": RUNE_NAMES[k], "held": held.get(k, 0)} for k in RUNE_NAMES]
        return {"char": char, "classes": out_classes, "shopping": shopping, "spare": spare, "drops": drops,
                "runes": runes, "currency_time": cur["t"] if cur else None,
                "group_drops": group, "done": tot_done, "total": tot,
                "inventory_time": inv["t"] if inv else None,
                "inventory": {"t": inv["t"], "source": os.path.basename(inv.get("path") or "") or "imported file",
                              "items": inv.get("items") or sum(inv["counts"].values())} if inv else None}

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
        """Any new log line showing you got a Sky test reward marks that test done."""
        qid = reward_in_line(line)
        if qid:
            self.mark_done(char, qid, t, "log")
        return qid

    def mark_done(self, char, qid, t, how):
        c = self.char(char)
        if qid in c["done"]:
            return False
        c["done"][qid] = {"t": t, "how": how}
        self.dirty = True
        return True

    # -- inventory export (/outputfile inventory) -------------------------
    def load_inventory(self, char, path):
        counts = {}
        try:
            with open(path, encoding="cp1252", errors="replace") as fh:
                header = fh.readline().rstrip("\n").split("\t")
                try:
                    ni = header.index("Name")
                    ci = header.index("Count")
                except ValueError:
                    ni, ci = 1, 3
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) <= max(ni, ci):
                        continue
                    name = parts[ni].strip()
                    if not name or name == "Empty":
                        continue
                    try:
                        n = int(parts[ci] or 1)
                    except ValueError:
                        n = 1
                    k = _k(name)
                    counts[k] = counts.get(k, 0) + max(1, n)
        except OSError:
            return
        c = self.char(char)
        c["inventory"] = {"t": os.path.getmtime(path), "counts": counts, "path": path}
        for k in counts:
            qid = REWARDS.get(k)
            if qid and qid not in c["done"]:
                c["done"][qid] = {"t": c["inventory"]["t"], "how": "inventory"}
        self.dirty = True

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
    def held_counts(self, char):
        c = self.char(char)
        inv = c.get("inventory")
        since = inv["t"] if inv else 0
        held = dict(inv["counts"]) if inv else {}
        for l in c["loot"]:
            if l["t"] > since:
                k = _k(l["item"])
                held[k] = held.get(k, 0) + l["qty"]
        for qid, d in c["done"].items():
            # Only turn-ins seen in the log consume items. Manual ticks mean
            # "already done", usually from before tracking started.
            if d["t"] > since and d["how"] == "log":
                for it in QUESTS[qid]["items"]:
                    k = _k(it["name"])
                    if k in held:
                        held[k] -= 1
        return {k: max(0, v) for k, v in held.items() if k in ITEMS}

    def view(self, char):
        c = self.char(char)
        held = self.held_counts(char)
        out_classes = []
        need = {}
        tot_done = tot = 0
        for cls in CLASSES:
            qs = []
            ndone = 0
            for q in cls["quests"]:
                done = c["done"].get(q["id"])
                items = []
                for it in q["items"]:
                    h = held.get(_k(it["name"]), 0)
                    items.append({"name": it["name"], "source": it["source"], "held": h})
                    if not done:
                        e = need.setdefault(_k(it["name"]), {"name": it["name"], "source": it["source"],
                                                             "need": 0, "held": h, "for": []})
                        e["need"] += 1
                        e["for"].append(f"{cls['abbr']} {q['name']}")
                ready = not done and all(i["held"] > 0 for i in items)
                ndone += bool(done)
                qs.append({"id": q["id"], "name": q["name"], "trigger": q["trigger"], "reward": q["reward"],
                           "done": bool(done), "how": done["how"] if done else None,
                           "ready": ready, "items": items})
            tot += len(qs)
            tot_done += ndone
            unlocked = cls["name"] in c["unlocked"] or ndone == len(qs)
            out_classes.append({"name": cls["name"], "abbr": cls["abbr"], "npc": cls["npc"],
                                "done": ndone, "total": len(qs), "unlocked": unlocked,
                                "manual_unlock": cls["name"] in c["unlocked"], "quests": qs})
        shopping = sorted(need.values(), key=lambda e: (e["held"] >= e["need"], e["source"], e["name"]))
        drops = sorted(c["loot"], key=lambda l: -l["t"])[:300]
        group = [g for g in self.group_drops if g.get("seen_by") == char][-200:][::-1]
        inv = c.get("inventory")
        return {"char": char, "classes": out_classes, "shopping": shopping, "drops": drops,
                "group_drops": group, "done": tot_done, "total": tot,
                "inventory_time": inv["t"] if inv else None}

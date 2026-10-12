"""Race unlock tracker (data in races_data.py, from EQLWiki).

Race unlocks are achievements, so they're tracked for the account, not per
character. Faction progress comes from the Factions tracker: a faction counts
as maxed once any of your characters' logs say "Your faction standing with X
could not possibly get any better." A race whose factions are all maxed (by
one character - personal faction) is shown as unlocked; you can also tick a
race yourself (you started as it, or used a Race Unlock Token).
"""
import re
import time

from . import races_data as D


def fkey(name):
    """Faction names as the wiki and the log write them: 'The Freeport Militia' = 'Freeport Militia',
    'King Ak'Anon (Faction)' = 'King Ak`Anon'."""
    s = (name or "").lower().replace("`", "'")
    s = re.sub(r"\(faction\)", "", s).strip()
    if s.startswith("the "):
        s = s[4:]
    return re.sub(r"[^a-z0-9]", "", s)


class Races:
    def __init__(self, state, factions):
        self.s = state.setdefault("races", {"unlocked": {}, "task": {}})
        self.s.setdefault("unlocked", {})
        self.s.setdefault("task", {})
        self.factions = factions
        self.dirty = False

    def set_unlocked(self, race, on):
        if not any(r["name"] == race for r in D.RACES):
            raise ValueError("unknown race")
        if on:
            self.s["unlocked"][race] = {"t": time.time(), "how": "manual"}
        else:
            self.s["unlocked"].pop(race, None)
        self.dirty = True

    def set_step(self, step, on):
        if on:
            self.s["task"][step] = time.time()
        else:
            self.s["task"].pop(step, None)
        self.dirty = True

    # -- faction status --------------------------------------------------------
    def _faction_index(self):
        """faction key -> {char: row} from every character's faction tracking."""
        idx = {}
        for char in list(self.factions.s):
            for row in self.factions.view(char)["factions"]:
                idx.setdefault(fkey(row["name"]), {})[char] = row
        return idx

    @staticmethod
    def _req(name, idx, char):
        rows = idx.get(fkey(name), {})
        maxed_by = sorted(c for c, r in rows.items() if r["maxed"] == "better")
        mine = rows.get(char)
        return {"faction": name, "done": bool(maxed_by), "maxed_by": maxed_by,
                "seen": bool(rows),
                "estimate": mine["estimate"] if mine else None, "tier": mine["tier"] if mine else None,
                "net": mine["net"] if mine else None, "last": mine["last"] if mine else None}

    # -- view --------------------------------------------------------------------
    def view(self, char):
        idx = self._faction_index()
        out, by_name = [], {}
        for r in D.RACES:
            u = r["unlock"]
            row = {"name": r["name"], "wiki": r["wiki"], "city": r["city"], "classes": r["classes"],
                   "tip": r.get("tip", ""), "kind": next(iter(u)), "groups": [], "steps": None}
            if "factions" in u:
                row["groups"] = [{"label": "", "reqs": [self._req(f, idx, char) for f in u["factions"]]}]
            elif "options" in u:
                row["groups"] = [{"label": lbl, "reqs": [self._req(f, idx, char) for f in fs]}
                                 for lbl, fs in u["options"].items()]
            elif "task" in u:
                t = u["task"]
                row["task"] = {"name": t["name"], "wiki": t["wiki"], "start": t["start"], "note": t["note"]}
                row["steps"] = [{"name": n, "info": i, "done": n in self.s["task"]} for n, i in t["steps"]]
            elif "any_race" in u:
                row["needs_race"] = u["any_race"]
            for g in row["groups"]:
                g["done"] = sum(q["done"] for q in g["reqs"])
                g["total"] = len(g["reqs"])
                g["complete"] = g["done"] == g["total"]
            out.append(row)
            by_name[r["name"]] = row
        # unlocked: ticked, all factions maxed, task finished, or (Half-Elf) a parent race unlocked
        for row in out:
            man = self.s["unlocked"].get(row["name"])
            how = "manual" if man else None
            if not how and row["groups"] and any(g["complete"] for g in row["groups"]):
                how = "factions maxed"
            if not how and row["steps"] and all(s["done"] for s in row["steps"]):
                how = "task done"
            row["unlocked"] = bool(how)
            row["how"] = how
        for row in out:
            if row.get("needs_race") and not row["unlocked"]:
                via = [n for n in row["needs_race"] if by_name[n]["unlocked"]]
                if via:
                    row["unlocked"], row["how"] = True, f"{via[0]} unlocked"
            # progress 0..1 for the bar
            if row["groups"]:
                best = max(row["groups"], key=lambda g: g["done"] / g["total"])
                row["progress"] = [best["done"], best["total"]]
            elif row["steps"]:
                row["progress"] = [sum(s["done"] for s in row["steps"]), len(row["steps"])]
            else:
                row["progress"] = [1 if row["unlocked"] else 0, 1]
        return {"char": char, "races": out, "unlocked": sum(r["unlocked"] for r in out), "total": len(out),
                "guide": D.GUIDE}

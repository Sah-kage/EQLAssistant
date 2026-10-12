"""Faction standings from the log.

EQ Legends logs the exact change:
    Your faction standing with Guards of Qeynos has been adjusted by -3.
    Your faction standing with Merchants of Qeynos could not possibly get any better.
The log never shows your absolute standing, so per faction we track the net
change since tracking began. If you enter your current value once (e.g. from
the in-game faction window), the app keeps an estimated value and standing
tier from then on.

/consider lines ("a guard regards you indifferently -- ...") do show a tier, so
the last con of each NPC is kept too.
"""
import re
import time

# Classic EQ standing thresholds (approximate; EQL hasn't published its own).
TIERS = [(1100, "Ally"), (750, "Warmly"), (500, "Kindly"), (100, "Amiably"), (0, "Indifferently"),
         (-100, "Apprehensively"), (-700, "Dubiously"), (-1000, "Threateningly"), (-10 ** 9, "Ready to attack")]

CON_RE = re.compile(
    r"^(?P<npc>.+?) (?:"
    r"regards you as an ally|looks upon you warmly|kindly considers you|judges you amiably|"
    r"regards you indifferently|looks your way apprehensively|glowers at you dubiously|"
    r"glares at you threateningly|scowls at you, ready to attack)"
    r"(?P<rest> -- .*)?$")
CON_TIER = [("as an ally", "Ally", 4), ("warmly", "Warmly", 3), ("kindly", "Kindly", 2), ("amiably", "Amiably", 1),
            ("indifferently", "Indifferently", 0), ("apprehensively", "Apprehensively", -1),
            ("dubiously", "Dubiously", -2), ("threateningly", "Threateningly", -3), ("ready to attack", "Ready to attack", -4)]

MAX_EVENTS = 60      # recent changes kept per faction
MAX_CONS = 400


def tier_for(value):
    for floor, name in TIERS:
        if value >= floor:
            return name
    return TIERS[-1][1]


def parse_con(msg):
    m = CON_RE.match(msg)
    if not m:
        return None
    for frag, name, rank in CON_TIER:
        if frag in msg[: len(m.group("npc")) + 40]:
            return {"type": "con", "npc": m.group("npc"), "tier": name, "rank": rank}
    return None


class Factions:
    def __init__(self, state):
        self.s = state.setdefault("factions", {})
        self.dirty = False
        self.last_kill = {}     # char -> (t, mob) just before faction hits
        self.last_give = {}     # char -> (t, npc) from "X says"/hand-ins (best effort)

    def char(self, char):
        c = self.s.get(char)
        if c is None:
            c = self.s[char] = {"f": {}, "cons": {}}
        return c

    def process(self, char, t, ev):
        typ = ev["type"]
        if typ == "death" and ev.get("tgt") not in ("You", "YOU"):
            self.last_kill[char] = (t, ev["tgt"])
            return
        if typ == "con":
            c = self.char(char)
            c["cons"][ev["npc"]] = {"tier": ev["tier"], "rank": ev["rank"], "t": t}
            if len(c["cons"]) > MAX_CONS:
                for k in sorted(c["cons"], key=lambda k: c["cons"][k]["t"])[: len(c["cons"]) - MAX_CONS]:
                    del c["cons"][k]
            self.dirty = True
            return
        if typ != "faction":
            return
        c = self.char(char)
        f = c["f"].get(ev["name"])
        if f is None:
            f = c["f"][ev["name"]] = {"net": 0, "ups": 0, "downs": 0, "hits": 0, "first": t, "last": t,
                                      "maxed": None, "base": None, "base_t": None, "since_base": 0,
                                      "events": [], "causes": {}}
        cause = None
        lk = self.last_kill.get(char)
        if lk and 0 <= t - lk[0] <= 3:
            cause = "killed " + lk[1]
        amt = ev.get("amt")
        if amt is not None:
            f["net"] += amt
            f["hits"] += 1
            if amt > 0:
                f["ups"] += amt
            else:
                f["downs"] += amt
            if f["base"] is not None and t >= f["base_t"]:
                f["since_base"] += amt
            if f["maxed"] and ((amt > 0 and f["maxed"] == "worse") or (amt < 0 and f["maxed"] == "better")):
                f["maxed"] = None
        else:
            f["maxed"] = ev["cap"]
        f["last"] = max(f["last"], t)
        f["events"].append([t, amt, ev.get("cap"), cause])
        del f["events"][:-MAX_EVENTS]
        if cause and amt is not None:
            mob = cause[7:]
            cz = f["causes"].setdefault(mob, [0, 0])
            cz[0] += 1
            cz[1] += amt
            if len(f["causes"]) > 40:
                for k in sorted(f["causes"], key=lambda k: abs(f["causes"][k][1]))[: len(f["causes"]) - 40]:
                    del f["causes"][k]
        self.dirty = True

    def merge_from(self, other):
        """Fold in older history found by a log scan (only ever run once per log file)."""
        for char, oc in other.s.items():
            c = self.char(char)
            for name, of in oc["f"].items():
                f = c["f"].get(name)
                if f is None:
                    c["f"][name] = of
                    continue
                for k in ("net", "ups", "downs", "hits"):
                    f[k] += of[k]
                f["first"] = min(f["first"], of["first"])
                if of["last"] > f["last"]:
                    f["last"], f["maxed"] = of["last"], of["maxed"]
                f["events"] = sorted(of["events"] + f["events"], key=lambda e: e[0])[-MAX_EVENTS:]
                for mob, (h, a) in of["causes"].items():
                    cz = f["causes"].setdefault(mob, [0, 0])
                    cz[0] += h
                    cz[1] += a
            for npc, con in oc["cons"].items():
                if npc not in c["cons"] or c["cons"][npc]["t"] < con["t"]:
                    c["cons"][npc] = con
        self.dirty = True

    def set_base(self, char, name, value, now=None):
        f = self.char(char)["f"].get(name)
        if f is None:
            f = self.char(char)["f"][name] = {"net": 0, "ups": 0, "downs": 0, "hits": 0, "first": time.time(),
                                              "last": time.time(), "maxed": None, "base": None, "base_t": None,
                                              "since_base": 0, "events": [], "causes": {}}
        if value is None or value == "":
            f["base"] = f["base_t"] = None
            f["since_base"] = 0
        else:
            f["base"] = int(value)
            f["base_t"] = time.time() if now is None else now
            f["since_base"] = 0
        self.dirty = True

    def view(self, char, now=None):
        now = time.time() if now is None else now
        c = self.char(char)
        day = now - 86400
        rows = []
        for name, f in c["f"].items():
            today = sum(e[1] for e in f["events"] if e[1] is not None and e[0] >= day)
            est = (f["base"] + f["since_base"]) if f["base"] is not None else None
            if est is not None and f["maxed"] == "better":
                est = max(est, 1100)
            causes = sorted(f["causes"].items(), key=lambda kv: -abs(kv[1][1]))[:5]
            rows.append({"name": name, "net": f["net"], "ups": f["ups"], "downs": f["downs"], "hits": f["hits"],
                         "today": today, "first": f["first"], "last": f["last"], "maxed": f["maxed"],
                         "base": f["base"], "base_t": f["base_t"], "estimate": est,
                         "tier": tier_for(est) if est is not None else ("Ally" if f["maxed"] == "better" else
                                                                         "Ready to attack" if f["maxed"] == "worse" else None),
                         "events": [{"t": e[0], "amt": e[1], "cap": e[2], "cause": e[3]} for e in reversed(f["events"][-20:])],
                         "causes": [{"mob": k, "hits": v[0], "amt": v[1]} for k, v in causes]})
        rows.sort(key=lambda r: -r["last"])
        cons = sorted(({"npc": k, **v} for k, v in c["cons"].items()), key=lambda r: -r["t"])[:150]
        return {"char": char, "factions": rows, "cons": cons,
                "tiers": [{"min": a, "name": b} for a, b in TIERS[:-1]]}

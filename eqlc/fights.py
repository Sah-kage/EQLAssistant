"""Groups damage events into fights (encounters) and keeps per-combatant stats.

A fight starts on the first damage event and ends when every mob that took
damage has died, or when no damage happens for `timeout` seconds.
"""
import time
from collections import Counter, deque

SPELL_KEYS = ("casts", "landed", "ticks", "resists", "fizzles", "interrupts", "damage")

ARTICLES = ("a ", "an ", "the ")


def looks_like_mob(name):
    n = name.lower()
    return n.startswith(ARTICLES) or name[:1].islower() or "`s pet" in n or "'s pet" in n


class Stats:
    __slots__ = ("total", "hits", "max", "crits", "first", "last", "kinds", "spells")

    def __init__(self, t):
        self.total = 0
        self.hits = 0
        self.max = 0
        self.crits = 0
        self.first = t
        self.last = t
        self.kinds = {}
        self.spells = {}

    def add(self, t, amt, kind, spell, crit):
        self.total += amt
        self.hits += 1
        if amt > self.max:
            self.max = amt
        if crit:
            self.crits += 1
        self.last = t
        self.kinds[kind] = self.kinds.get(kind, 0) + amt
        if spell:
            self.spells[spell] = self.spells.get(spell, 0) + amt

    def dict(self, fight_dur):
        active = max(1.0, self.last - self.first + 1)
        return {"total": self.total, "hits": self.hits, "max": self.max, "crits": self.crits,
                "avg": round(self.total / self.hits) if self.hits else 0,
                "dps": round(self.total / fight_dur, 1), "sdps": round(self.total / active, 1),
                "active": round(active), "kinds": self.kinds,
                "spells": dict(sorted(self.spells.items(), key=lambda kv: -kv[1])[:15])}


def friend_type(name, pets=()):
    if name == "You":
        return "you"
    n = name.lower()
    if name in pets or n.endswith(("`s pet", "'s pet", "`s warder", "'s warder")):
        return "pet"
    return "player"


class Fight:
    def __init__(self, fid, t):
        self.id = fid
        self.start = t
        self.last = t
        self.out = {}        # friendly source -> Stats (damage dealt to NPCs)
        self.inc = {}        # NPC source -> Stats (damage dealt to you)
        self.npc = {}        # NPC source -> Stats (damage dealt to anyone on your side)
        self.npc_tgts = {}   # NPC -> {friendly target: damage}
        self.taken = {}      # friendly -> damage taken from NPCs
        self.mobs = {}       # NPC -> damage taken
        self.dead = set()
        self.events = []     # (t, side, src, tgt, amt, kind, spell, crit) for the combat log
        # outcome counts (hit / miss / dodge / parry / block / riposte / absorb / invulnerable)
        self.swings = {}     # friendly attacker -> Counter of their melee outcomes
        self.swings_vs = {}  # NPC -> Counter of outcomes of friendly swings against it
        self.npc_swings = {} # NPC attacker -> Counter of its melee outcomes vs your side
        self.defense = {}    # friendly -> Counter of NPC swings they received
        # your spells (only your own casts/resists are in the log)
        self.spells = {}     # spell -> {casts, landed, ticks, resists, fizzles, interrupts, damage}
        self.resisted_by = {}   # NPC -> {spell: times it resisted you}
        self.you_resisted = {}  # NPC spell -> times you resisted it
        self.spell_misc = Counter()  # immune / nohold
        self.done = False

    @property
    def duration(self):
        return max(1.0, self.last - self.start + 1)

    def you_damage(self, pets=()):
        tot = 0
        for name, st in self.out.items():
            if name == "You" or name in pets:
                tot += st.total
        return tot

    def summary(self, pets=()):
        dur = self.duration
        you = self.you_damage(pets)
        total = sum(s.total for s in self.out.values())
        name = max(self.mobs, key=self.mobs.get) if self.mobs else "?"
        extra = len(self.mobs) - 1
        return {"id": self.id, "start": self.start, "end": self.last, "duration": round(dur),
                "name": name + (f" (+{extra})" if extra > 0 else ""),
                "you": you, "dps": round(you / dur, 1), "total": total,
                "raid_dps": round(total / dur, 1), "done": self.done,
                "taken": sum(s.total for s in self.inc.values())}

    def detail(self, pets=(), pet_names=()):
        d = self.summary(pets)
        known_pets = set(pets) | set(pet_names)
        dur = self.duration
        total = d["total"] or 1
        rows = []
        for name, st in sorted(self.out.items(), key=lambda kv: -kv[1].total):
            r = st.dict(dur)
            r["name"] = name
            r["type"] = friend_type(name, known_pets)
            r["pct"] = round(100 * st.total / total, 1)
            r["taken"] = self.taken.get(name, 0)
            sw = self.swings.get(name)
            r["swings"] = sum(sw.values()) if sw else 0
            r["acc"] = round(100 * sw["hit"] / r["swings"]) if r["swings"] else None
            rows.append(r)
        # friendlies that only took damage (e.g. a healer who never attacked)
        for name, tk in sorted(self.taken.items(), key=lambda kv: -kv[1]):
            if name not in self.out:
                rows.append({"name": name, "type": friend_type(name, known_pets), "total": 0, "pct": 0, "dps": 0,
                             "sdps": 0, "hits": 0, "avg": 0, "max": 0, "crits": 0, "kinds": {},
                             "spells": {}, "active": 0, "taken": tk})
        npc_total = sum(s.total for s in self.npc.values()) or 1
        npcs = []
        for name in sorted(set(self.mobs) | set(self.npc), key=lambda n: -(self.mobs.get(n, 0))):
            st = self.npc.get(name)
            r = st.dict(dur) if st else {"total": 0, "hits": 0, "max": 0, "dps": 0, "avg": 0, "crits": 0}
            tg = self.npc_tgts.get(name, {})
            vs = self.swings_vs.get(name)
            r["avoid"] = round(100 * (1 - vs["hit"] / sum(vs.values()))) if vs and sum(vs.values()) else None
            r.update(name=name, taken=self.mobs.get(name, 0), dead=name in self.dead,
                     pct=round(100 * r["total"] / npc_total, 1),
                     targets=[{"name": k, "dmg": v} for k, v in sorted(tg.items(), key=lambda kv: -kv[1])[:4]])
            npcs.append(r)
        d["players"] = rows
        d["npcs"] = npcs
        d["log"] = [{"t": round(e[0] - self.start), "side": e[1], "src": e[2], "tgt": e[3], "amt": e[4],
                     "kind": e[5], "spell": e[6], "crit": e[7]} for e in self.events[-2000:]]
        inc = []
        for name, st in sorted(self.inc.items(), key=lambda kv: -kv[1].total):
            r = st.dict(dur)
            r["name"] = name
            inc.append(r)
        d["combatants"] = rows
        d["incoming"] = inc
        d["mobs"] = [{"name": k, "taken": v, "dead": k in self.dead}
                     for k, v in sorted(self.mobs.items(), key=lambda kv: -kv[1])]
        return d


class FightTracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.fights = deque(maxlen=500)
        self.current = None
        self.next_id = 1
        self.enemies = {}
        self.friends = set()
        self.last_crit = {}
        self.last_cast = (0, None)      # (time, spell) of your last "You begin casting"
        self.last_target = None         # NPC you last attacked
        self.pending = deque(maxlen=40) # your spell events just before a fight starts

    # -- classification -------------------------------------------------
    def _side(self, src, tgt):
        """Return ('out', friend, mob) or ('in', mob, friend) or None."""
        if src in ("You", "YOU"):
            src = "You"
        if tgt in ("YOU", "You", "you"):
            return ("in", src, "You") if src != "You" else None
        if src == "You":
            return ("out", "You", tgt)
        if tgt in self.enemies:
            return ("out", src, tgt)
        if src in self.enemies:
            return ("in", src, tgt)
        if tgt in self.friends:
            return ("in", src, tgt)
        if src in self.friends:
            return ("out", src, tgt)
        if looks_like_mob(tgt) and not looks_like_mob(src):
            return ("out", src, tgt)
        if looks_like_mob(src) and not looks_like_mob(tgt):
            return ("in", src, tgt)
        return ("out", src, tgt)

    def _mark_enemy(self, name):
        self.enemies[name] = 1
        if len(self.enemies) > 4000:
            for k in list(self.enemies)[:2000]:
                del self.enemies[k]

    # -- processing -----------------------------------------------------
    def _close(self):
        if self.current:
            self.current.done = True
            self.fights.append(self.current)
            self.current = None

    def _fight_at(self, t):
        """The current fight, starting a new one if needed."""
        if self.current and t - self.current.last > self.cfg.get("fight_timeout", 10):
            self._close()
        if not self.current:
            self.current = Fight(self.next_id, t)
            self.next_id += 1
            # spells you started casting just before the first hit belong to this fight
            for pt, pev in list(self.pending):
                if t - pt <= 12:
                    self._spell(self.current, pt, pev)
            self.pending.clear()
        f = self.current
        f.last = max(f.last, t)
        return f

    def _recent_cast(self, t):
        ct, sp = self.last_cast
        return sp if sp and t - ct <= 20 else None

    def _spell_row(self, f, spell):
        return f.spells.get(spell) or f.spells.setdefault(spell, dict.fromkeys(SPELL_KEYS, 0))

    def _spell(self, f, t, ev):
        sub = ev["sub"]
        spell = ev.get("spell")
        if sub == "you_resisted":
            f.you_resisted[spell] = f.you_resisted.get(spell, 0) + 1
            f.events.append((t, "spell", ev.get("spell") or "", "You", 0, "you resisted", spell, False))
            return
        if sub in ("immune", "nohold"):
            f.spell_misc[sub] += 1
            f.events.append((t, "spell", "You", self.last_target or "", 0, sub, self._recent_cast(t), False))
            return
        if not spell:
            spell = self._recent_cast(t) or "Unknown spell"
        row = self._spell_row(f, spell)
        key = {"cast": "casts", "resist": "resists", "fizzle": "fizzles", "interrupt": "interrupts"}[sub]
        row[key] += 1
        if sub == "resist" and self.last_target:
            rb = f.resisted_by.setdefault(self.last_target, {})
            rb[spell] = rb.get(spell, 0) + 1
        f.events.append((t, "spell", "You", (self.last_target or "") if sub == "resist" else "", 0, sub, spell, False))

    def process(self, t, ev):
        typ = ev["type"]
        if typ == "spell":
            sub = ev["sub"]
            if sub == "cast":
                self.last_cast = (t, ev["spell"])
            in_fight = self.current and t - self.current.last <= self.cfg.get("fight_timeout", 10)
            if sub == "resist":                       # a resist means you attacked: counts as combat
                self._spell(self._fight_at(t), t, ev)
            elif in_fight:
                self._spell(self.current, t, ev)
            elif sub in ("cast", "fizzle", "interrupt"):
                self.pending.append((t, ev))
            return
        if typ == "avoid":
            side = self._side(ev["src"], ev["tgt"])
            if not side:
                return
            f = self._fight_at(t)
            direction, a, b = side
            o = ev["outcome"]
            if direction == "out":
                self._mark_enemy(b)
                self.friends.add(a)
                if a == "You":
                    self.last_target = b
                f.swings.setdefault(a, Counter())[o] += 1
                f.swings_vs.setdefault(b, Counter())[o] += 1
                f.mobs.setdefault(b, 0)
            else:
                self._mark_enemy(a)
                if b != "You":
                    self.friends.add(b)
                f.npc_swings.setdefault(a, Counter())[o] += 1
                f.defense.setdefault(b, Counter())[o] += 1
            if len(f.events) < 20000:
                f.events.append((t, "friend" if direction == "out" else "npc", a, b, 0, o, None, False))
            return
        if typ == "dmg":
            side = self._side(ev["src"], ev["tgt"])
            if not side:
                return
            f = self._fight_at(t)
            direction, a, b = side
            amt = ev["amt"]
            melee = ev["kind"] == "melee"
            if direction == "out" and a == "You":
                self.last_target = b
                if not melee:
                    # name the spell: classic "non-melee" lines don't say which spell it was
                    if not ev["spell"]:
                        ev = dict(ev, spell=self._recent_cast(t) or "Non-melee (spell unknown)")
                    row = self._spell_row(f, ev["spell"])
                    row["ticks" if ev["kind"] == "dot" else "landed"] += 1
                    row["damage"] += amt
            if melee:
                if direction == "out":
                    f.swings.setdefault(a, Counter())["hit"] += 1
                    f.swings_vs.setdefault(b, Counter())["hit"] += 1
                else:
                    f.npc_swings.setdefault(a, Counter())["hit"] += 1
                    f.defense.setdefault(b, Counter())["hit"] += 1
            if direction == "out":
                self._mark_enemy(b)
                self.friends.add(a)
                st = f.out.get(a) or f.out.setdefault(a, Stats(t))
                st.add(t, amt, ev["kind"], ev["spell"], ev["crit"])
                f.mobs[b] = f.mobs.get(b, 0) + amt
                if b in f.dead:
                    f.dead.discard(b)
            else:
                self._mark_enemy(a)
                if b != "You":
                    self.friends.add(b)
                st = f.npc.get(a) or f.npc.setdefault(a, Stats(t))
                st.add(t, amt, ev["kind"], ev["spell"], ev["crit"])
                tg = f.npc_tgts.setdefault(a, {})
                tg[b] = tg.get(b, 0) + amt
                f.taken[b] = f.taken.get(b, 0) + amt
                if b == "You":
                    st = f.inc.get(a) or f.inc.setdefault(a, Stats(t))
                    st.add(t, amt, ev["kind"], ev["spell"], ev["crit"])
            if len(f.events) < 20000:
                src = "You" if direction == "out" and a == "You" else a
                f.events.append((t, "friend" if direction == "out" else "npc", src, b, amt,
                                 ev["kind"], ev["spell"], ev["crit"]))
        elif typ == "crit":
            f = self.current
            src = "You" if ev["src"] in ("You", "YOU") else ev["src"]
            if f and src in f.out:
                f.out[src].crits += 1
        elif typ == "death":
            f = self.current
            tgt = ev["tgt"]
            if f and (tgt in f.mobs or tgt in f.taken or tgt in ("You", "YOU")):
                f.events.append((t, "death", ev.get("src") or "", tgt, 0, "death", None, False))
            if f and tgt in f.mobs:
                f.dead.add(tgt)
                f.last = max(f.last, t)
                if all(m in f.dead for m in f.mobs):
                    self._close()

    def tick(self, now=None):
        now = now or time.time()
        if self.current and now - self.current.last > self.cfg.get("fight_timeout", 10) + 1:
            self._close()

    # -- queries --------------------------------------------------------
    def pets(self):
        return set(self.cfg.get("pet_names", [])) if self.cfg.get("include_pets") else set()

    def valid(self, f):
        pets = self.pets()
        return f.you_damage(pets) > 0 and f.duration >= self.cfg.get("min_fight_secs", 5)

    def recent(self, n):
        out = []
        for f in reversed(self.fights):
            if self.valid(f):
                out.append(f)
                if len(out) >= n:
                    break
        return out

    def overlay(self):
        pets = self.pets()
        n = int(self.cfg.get("avg_fights", 10))
        last = self.recent(n)
        dps = [f.you_damage(pets) / f.duration for f in last]
        cur = None
        f = self.current
        if f:
            dur = max(1.0, max(f.last, min(time.time(), f.last + 2)) - f.start + 1)
            you = f.you_damage(pets)
            cur = {"dps": round(you / dur, 1), "dmg": you, "duration": round(dur),
                   "target": f.summary(pets)["name"], "active": True}
        elif last:
            s = last[0].summary(pets)
            cur = {"dps": s["dps"], "dmg": s["you"], "duration": s["duration"],
                   "target": s["name"], "active": False}
        return {"current": cur,
                "avg": round(sum(dps) / len(dps), 1) if dps else 0,
                "avg_n": len(dps), "avg_target": n,
                "history": [round(x, 1) for x in reversed(dps)],
                "best": round(max(dps), 1) if dps else 0}

    def list(self, limit=200):
        pets = self.pets()
        items = list(self.fights)
        if self.current:
            items.append(self.current)
        return [f.summary(pets) for f in reversed(items[-limit:])]

    def get(self, fid):
        pets = self.pets()
        names = self.cfg.get("pet_names", [])
        if self.current and self.current.id == fid:
            return self.current.detail(pets, names)
        for f in self.fights:
            if f.id == fid:
                return f.detail(pets, names)
        return None

    def find(self, fid):
        if self.current and self.current.id == fid:
            return self.current
        for f in self.fights:
            if f.id == fid:
                return f
        return None

    def latest(self):
        return self.current or (self.fights[-1] if self.fights else None)

    def breakdown(self, scope, name, side="friend"):
        """scope: a fight id, "latest", or "recent" (last N fights, as the overlay average)."""
        from .coach import breakdown
        if scope == "recent":
            fights = self.recent(int(self.cfg.get("avg_fights", 10)))
            if self.current:
                fights = [self.current] + fights
            label = f"Last {len(fights)} fights"
            fid = None
        else:
            f = self.latest() if scope == "latest" else self.find(int(scope))
            if not f:
                return None
            fights, label, fid = [f], "This fight", f.id
        b = breakdown(fights, name, side, self.cfg.get("pet_names", []))
        b.update(scope=scope, scope_label=label, fight_id=fid)
        return b

    def clear(self):
        self.fights.clear()
        self.current = None

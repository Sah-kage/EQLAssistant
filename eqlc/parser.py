"""Turns EverQuest log lines into simple event dicts.

Handles both the classic message style ("X was hit by non-melee for N points
of damage.") and the newer style ("You hit X for N points of fire damage by
Spell."), since EverQuest Legends is built on a modernised classic client.
"""
import re
from datetime import datetime

TS_RE = re.compile(r"^\[(\w{3} \w{3} [ \d]\d \d{2}:\d{2}:\d{2} \d{4})\] (.*?)\s*$")

_ts_cache = {}


def parse_ts(s):
    v = _ts_cache.get(s)
    if v is None:
        try:
            v = datetime.strptime(s, "%a %b %d %H:%M:%S %Y").timestamp()
        except ValueError:
            return None
        if len(_ts_cache) > 20000:
            _ts_cache.clear()
        _ts_cache[s] = v
    return v


VERBS = (r"hits?|slash(?:es)?|pierces?|crush(?:es)?|kicks?|bash(?:es)?|punch(?:es)?|"
         r"backstabs?|bites?|claws?|gores?|mauls?|smash(?:es)?|slices?|stabs?|strikes?|"
         r"stings?|rends?|shoots?|frenz(?:y|ies) on|slams?|tail rakes?|burns?|lashes|lash")

MELEE_RE = re.compile(
    rf"^(?P<src>.+?) (?P<verb>{VERBS}) (?P<tgt>.+?) for (?P<amt>\d+) points? of "
    rf"(?:(?P<kind>[a-z][a-z-]*) )?damage(?: by (?P<spell>.+?))?\.?(?:\s*\((?P<mods>[^)]*)\))?$")
NONMELEE_RE = re.compile(r"^(?P<tgt>.+?) was hit by non-melee for (?P<amt>\d+) points? of damage\.")
DOT_YOUR_RE = re.compile(r"^(?P<tgt>.+?) has taken (?P<amt>\d+) damage from your (?P<spell>.+?)\.")
DOT_BY_RE = re.compile(r"^(?P<tgt>.+?) has taken (?P<amt>\d+) damage from (?P<spell>.+?) by (?P<src>.+?)\.")
DOT_YOU_RE = re.compile(r"^You have taken (?P<amt>\d+) damage from (?P<spell>.+?)(?: by (?P<src>.+?))?\.")
SLAIN_YOU_RE = re.compile(r"^You have slain (?P<tgt>.+?)!")
SLAIN_ME_RE = re.compile(r"^You have been slain by (?P<src>.+?)!")
SLAIN_BY_RE = re.compile(r"^(?P<tgt>.+?) (?:has been|was) slain by (?P<src>.+?)!")
DIED_RE = re.compile(r"^(?P<tgt>.+?) died\.$")
CRIT_RE = re.compile(r"^(?P<src>.+?) (?:scores?|lands?|delivers?) a (?:critical hit|crippling blow|critical blast)!\s*\((?P<amt>\d+)\)")
LOOT_RE = re.compile(
    r"^--(?P<who>You|\S+) (?:have|has) looted (?:an? |the |some |(?P<qty>\d+) )?(?P<item>.+?)"
    r"(?: from (?P<corpse>.+?))?\.\s*--$")
RECEIVE_RE = re.compile(r"^You (?:receive|have received) (?:an? |the |\d+ )?(?P<item>.+?)(?: from (?P<frm>.+?))?[.!]$")
GIVES_RE = re.compile(r"^(?P<npc>.+?) (?:gives|hands) you (?:an? |the )?(?P<item>.+?)[.!]$")
ZONE_RE = re.compile(r"^You have entered (?P<zone>.+?)\.$")
NOT_A_ZONE_RE = re.compile(r"^(?:an area\b|the Arena\b)", re.I)   # "You have entered an area where levitation..."
ZONE_TIER_RE = re.compile(r"\s*\((?P<tier>[^)]+)\)\s*$")
ZONE_ID_RE = re.compile(r"\s+(?P<id>\d+)\s*$")
ZONE_MODE_RE = re.compile(r"\s+-\s+(?P<mode>Solo|Duo|Trio|Group|Raid|Party|Heroic|Event)(?:\s+(?P<id>\d+))?$", re.I)
# EQ Legends difficulty tiers, as shown in instanced zone names: "Lower Guk 4 (Refined)"
TIERS = {"awakened": 1, "adaptive": 2, "fused": 3, "refined": 4}

XP_RE = re.compile(r"^You gain (?:party )?experience(?: \(with a bonus\))?!(?: \((?P<pct>[0-9]+(?:\.[0-9]+)?)%\))?$")


def parse_zone(raw):
    """'The Castle of Mistmoore 4 (Refined)' -> base name, instance id, tier, mode.

    The number is an instance id and the brackets hold the difficulty tier
    (seen in real EQL logs). A ' - Solo' / ' - Group' suffix is the instance mode.
    """
    name = raw.strip()
    tier = ""
    m = ZONE_TIER_RE.search(name)
    if m:
        tier = m.group("tier").strip()
        name = name[:m.start()]
    inst_id = ""
    m = ZONE_ID_RE.search(name)
    if m:
        inst_id = m.group("id")
        name = name[:m.start()]
    mode = ""
    m = ZONE_MODE_RE.search(name)
    if m:
        mode = m.group("mode").capitalize()
        inst_id = inst_id or (m.group("id") or "")
        name = name[:m.start()]
    name = name.strip()
    level = TIERS.get(tier.lower())
    if level is None and re.fullmatch(r"D?\d", tier, re.I):
        level = int(tier[-1])
    inst = bool(inst_id or tier or mode)
    return {"type": "zone", "zone": name, "raw": raw.strip(), "tier": tier, "mode": mode,
            "inst_id": inst_id, "inst": inst, "level": level if level is not None else (0 if inst else None)}

# "<ZONE NAME> is now available to you." - the dungeon crawl timer starts here
AVAILABLE_RE = re.compile(r"^(?P<zone>.+?) [Ii]s now available to you[.!]?$")

# "You try to hit a gnoll, but miss!" / "a gnoll tries to bash YOU, but YOU parry!"
AVOID_RE = re.compile(r"^(?P<src>.+?) (?:try|tries) to (?P<verb>[a-z]+(?: on)?) (?P<tgt>.+?), but (?P<rest>.+?)[!.]$")
AVOID_WORDS = (("ripost", "riposte"), ("dodge", "dodge"), ("parr", "parry"), ("block", "block"),
               ("absorb", "absorb"), ("invulnerable", "invulnerable"), ("miss", "miss"))

CAST_RE = re.compile(r"^You begin (?:casting|singing) (?P<spell>.+?)\.$")
RESIST_RE = re.compile(r"^Your target resisted the (?P<spell>.+?) spell\.?$")
YOU_RESIST_RE = re.compile(r"^You resist the (?P<spell>.+?) spell!?$")
FIZZLE_RE = re.compile(r"^Your (?:(?P<spell>.+?) )?spell fizzles!$")
INTERRUPT_RE = re.compile(r"^Your (?:(?P<spell>.+?) )?(?:spell|casting) (?:is|has been) interrupted[.!]$")
IMMUNE_RE = re.compile(r"^Your target (?:is immune|cannot be)")
NOHOLD_RE = re.compile(r"^Your spell (?:did not take hold|would not have taken hold)")

# Real EQL wording (see eqdps): "...has been adjusted by -3." / "...could not possibly get any better."
FACTION_RE = re.compile(r"^Your faction standing with (?P<name>.+?) (?:has been adjusted by (?P<amt>[+-]?\d+)|"
                        r"could not possibly get any (?P<cap>better|worse))\.$")

SELF = {"You", "YOU", "you"}


def _clean_corpse(c):
    if not c:
        return None
    for suf in ("'s corpse", "`s corpse", " corpse"):
        if c.endswith(suf):
            return c[: -len(suf)]
    return c


def parse_line(line):
    """Return (timestamp, event) or (timestamp, None) or None if unparseable."""
    m = TS_RE.match(line)
    if not m:
        return None
    t = parse_ts(m.group(1))
    if t is None:
        return None
    msg = m.group(2)
    return t, parse_msg(msg)


def parse_msg(msg):
    c0 = msg[:2]
    if c0 == "--":
        m = LOOT_RE.match(msg)
        if m:
            return {"type": "loot", "who": m.group("who"), "item": m.group("item").strip(),
                    "qty": int(m.group("qty") or 1), "corpse": _clean_corpse(m.group("corpse"))}
        return None

    if " damage" in msg:
        m = NONMELEE_RE.match(msg)
        if m:
            return {"type": "dmg", "src": "You", "tgt": m.group("tgt"), "amt": int(m.group("amt")),
                    "kind": "spell", "spell": None, "crit": False}
        m = MELEE_RE.match(msg)
        if m:
            kind = (m.group("kind") or "").lower()
            spell = m.group("spell")
            kind = "spell" if (spell or kind not in ("", "physical")) else "melee"
            mods = (m.group("mods") or "").lower()
            return {"type": "dmg", "src": m.group("src"), "tgt": m.group("tgt"),
                    "amt": int(m.group("amt")), "kind": kind, "spell": spell,
                    "crit": "critical" in mods or "crippling" in mods}
        m = DOT_YOU_RE.match(msg)
        if m:
            return {"type": "dmg", "src": m.group("src") or "Unknown", "tgt": "YOU",
                    "amt": int(m.group("amt")), "kind": "dot", "spell": m.group("spell"), "crit": False}
        m = DOT_YOUR_RE.match(msg)
        if m:
            return {"type": "dmg", "src": "You", "tgt": m.group("tgt"), "amt": int(m.group("amt")),
                    "kind": "dot", "spell": m.group("spell"), "crit": False}
        m = DOT_BY_RE.match(msg)
        if m:
            return {"type": "dmg", "src": m.group("src"), "tgt": m.group("tgt"), "amt": int(m.group("amt")),
                    "kind": "dot", "spell": m.group("spell"), "crit": False}
        return None

    if ", but " in msg and (" try to " in msg or " tries to " in msg):
        m = AVOID_RE.match(msg)
        if m:
            rest = m.group("rest").lower()
            outcome = next((o for w, o in AVOID_WORDS if w in rest), None)
            if outcome:
                return {"type": "avoid", "src": m.group("src"), "tgt": m.group("tgt"),
                        "verb": m.group("verb"), "outcome": outcome}
        return None

    if msg.startswith("Your faction standing with "):
        m = FACTION_RE.match(msg)
        if m:
            return {"type": "faction", "name": m.group("name"),
                    "amt": int(m.group("amt")) if m.group("amt") else None, "cap": m.group("cap")}
        return None
    if " you" in msg and (" regards you " in msg or " upon you " in msg or " considers you" in msg or
                          " judges you " in msg or " your way " in msg or " at you" in msg):
        from .factions import parse_con
        c = parse_con(msg)
        if c:
            return c

    if "s now available to you" in msg:
        m = AVAILABLE_RE.match(msg)
        if m:
            z = parse_zone(m.group("zone"))
            z.update(type="crawl", sub="start", text=msg)
            return z
    if "Dungeon Crawl" in msg or "instance charge" in msg or "instance recharge" in msg:
        if msg.startswith("You have completed the Dungeon Crawl"):
            return {"type": "crawl", "sub": "done", "text": msg}
        if msg.startswith("You gained reward experience from the Dungeon Crawl"):
            return {"type": "crawl", "sub": "xp", "text": msg}
        if msg.startswith("You earned a refund of your instance charge"):
            return {"type": "crawl", "sub": "refund", "text": msg}
        if "instance charge" in msg or "instance recharge" in msg:
            # e.g. the "too easy to earn an instance recharge" notice (wording not documented yet)
            return {"type": "crawl", "sub": "charge_note", "text": msg}
        return {"type": "crawl", "sub": "note", "text": msg}

    if msg.startswith("You"):
        if msg.startswith("You gain "):
            m = XP_RE.match(msg)
            if m:
                return {"type": "xp", "pct": float(m.group("pct")) if m.group("pct") else None}
        if msg.startswith("You begin "):
            m = CAST_RE.match(msg)
            if m:
                return {"type": "spell", "sub": "cast", "spell": m.group("spell")}
        elif msg.startswith("Your target "):
            m = RESIST_RE.match(msg)
            if m:
                return {"type": "spell", "sub": "resist", "spell": m.group("spell")}
            if IMMUNE_RE.match(msg):
                return {"type": "spell", "sub": "immune", "spell": None}
        elif msg.startswith("Your "):
            m = FIZZLE_RE.match(msg)
            if m:
                return {"type": "spell", "sub": "fizzle", "spell": m.group("spell")}
            m = INTERRUPT_RE.match(msg)
            if m:
                return {"type": "spell", "sub": "interrupt", "spell": m.group("spell")}
            if NOHOLD_RE.match(msg):
                return {"type": "spell", "sub": "nohold", "spell": None}
        elif msg.startswith("You resist the "):
            m = YOU_RESIST_RE.match(msg)
            if m:
                return {"type": "spell", "sub": "you_resisted", "spell": m.group("spell")}

    if "slain" in msg:
        m = SLAIN_ME_RE.match(msg)
        if m:
            return {"type": "death", "tgt": "You", "src": m.group("src")}
        m = SLAIN_YOU_RE.match(msg)
        if m:
            return {"type": "death", "tgt": m.group("tgt"), "src": "You"}
        m = SLAIN_BY_RE.match(msg)
        if m:
            return {"type": "death", "tgt": m.group("tgt"), "src": m.group("src")}
        return None
    if msg.endswith(" died."):
        m = DIED_RE.match(msg)
        if m:
            return {"type": "death", "tgt": m.group("tgt"), "src": None}
    if "critical" in msg or "crippling" in msg:
        m = CRIT_RE.match(msg)
        if m:
            return {"type": "crit", "src": m.group("src"), "amt": int(m.group("amt"))}
        return None
    if msg.startswith("You have entered "):
        m = ZONE_RE.match(msg)
        if m and not NOT_A_ZONE_RE.match(m.group("zone")):
            return parse_zone(m.group("zone"))
        return None
    if msg.startswith("You receive") or msg.startswith("You have received"):
        m = RECEIVE_RE.match(msg)
        if m:
            return {"type": "receive", "item": m.group("item").strip(), "frm": m.group("frm")}
    if " you " in msg and (" gives you " in msg or " hands you " in msg):
        m = GIVES_RE.match(msg)
        if m:
            return {"type": "receive", "item": m.group("item").strip(), "frm": m.group("npc")}
    return None

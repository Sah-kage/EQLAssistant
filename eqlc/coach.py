"""Per-combatant breakdown (misses, avoidance, resists, ...) and improvement tips.

breakdown() merges one or more fights for one combatant. suggestions() turns
that into plain-language tips. Every tip is based only on what the log shows,
and states the numbers behind it so you can judge it yourself. Tips need a
minimum sample before they fire, so one unlucky fight doesn't trigger advice.
"""
from collections import Counter

from .fights import SPELL_KEYS, friend_type

OUTCOMES = ["hit", "miss", "dodge", "parry", "block", "riposte", "absorb", "invulnerable"]
FRONT_ONLY = ("parry", "block", "riposte")   # NPCs can only do these to attacks from the front


def _n(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def _merge_stats(dst, st):
    dst["total"] += st.total
    dst["hits"] += st.hits
    dst["crits"] += st.crits
    dst["max"] = max(dst["max"], st.max)
    dst["active"] += max(1.0, st.last - st.first + 1)
    for k, v in st.kinds.items():
        dst["kinds"][k] = dst["kinds"].get(k, 0) + v


def breakdown(fights, name, side="friend", pet_names=()):
    """Aggregate everything about `name` across `fights` (oldest first or any order)."""
    dmg = {"total": 0, "hits": 0, "crits": 0, "max": 0, "active": 0.0, "kinds": {}}
    out = Counter()          # their melee outcomes when attacking
    against = Counter()      # outcomes of attacks aimed at them
    spells = {}
    resisted_by = {}
    you_resisted = Counter()
    misc = Counter()
    taken = 0
    dealt_to = Counter()
    duration = 0.0
    n = 0
    for f in fights:
        if side == "friend":
            present = name in f.out or name in f.swings or name in f.taken or name in f.defense or \
                (name == "You" and (f.spells or f.you_resisted))
        else:
            present = name in f.mobs or name in f.npc or name in f.npc_swings
        if not present:
            continue
        n += 1
        duration += f.duration
        if side == "friend":
            if name in f.out:
                _merge_stats(dmg, f.out[name])
            out.update(f.swings.get(name, {}))
            against.update(f.defense.get(name, {}))
            taken += f.taken.get(name, 0)
            if name == "You":
                for sp, row in f.spells.items():
                    agg = spells.setdefault(sp, dict.fromkeys(SPELL_KEYS, 0))
                    for k in SPELL_KEYS:
                        agg[k] += row[k]
                for mob, d in f.resisted_by.items():
                    rb = resisted_by.setdefault(mob, Counter())
                    rb.update(d)
                you_resisted.update(f.you_resisted)
                misc.update(f.spell_misc)
        else:
            if name in f.npc:
                _merge_stats(dmg, f.npc[name])
            out.update(f.npc_swings.get(name, {}))
            against.update(f.swings_vs.get(name, {}))
            taken += f.mobs.get(name, 0)
            dealt_to.update(f.npc_tgts.get(name, {}))
            for sp, c in f.resisted_by.get(name, {}).items():
                resisted_by.setdefault("You", Counter())[sp] += c

    swings = sum(out.values())
    recv = sum(against.values())
    spell_rows = []
    for sp, r in sorted(spells.items(), key=lambda kv: -kv[1]["damage"]):
        completed = (r["casts"] - r["fizzles"] - r["interrupts"]) if r["casts"] else (r["resists"] + r["landed"])
        spell_rows.append(dict(r, name=sp, resist_pct=_pct(r["resists"], max(completed, r["resists"])),
                               fizzle_pct=_pct(r["fizzles"], r["casts"]),
                               interrupt_pct=_pct(r["interrupts"], r["casts"])))
    b = {
        "name": name, "side": side, "fights": n,
        "type": friend_type(name, pet_names) if side == "friend" else "npc",
        "duration": round(duration), "damage": dmg["total"],
        "dps": round(dmg["total"] / duration, 1) if duration else 0,
        "active_pct": _pct(min(dmg["active"], duration), duration) if dmg["total"] else None,
        "max_hit": dmg["max"], "crits": dmg["crits"], "hits": dmg["hits"],
        "crit_pct": _pct(dmg["crits"], dmg["hits"]),
        "kinds": dmg["kinds"],
        "melee": {"swings": swings, "counts": {o: out.get(o, 0) for o in OUTCOMES if out.get(o)},
                  "accuracy": _pct(out.get("hit", 0), swings)},
        "defense": {"attempts": recv, "counts": {o: against.get(o, 0) for o in OUTCOMES if against.get(o)},
                    "hit_pct": _pct(against.get("hit", 0), recv)},
        "taken": taken,
        "spells": spell_rows,
        "resisted_by": {k: dict(v) for k, v in resisted_by.items()},
        "you_resisted": dict(you_resisted),
        "misc": dict(misc),
        "dealt_to": [{"name": k, "dmg": v} for k, v in dealt_to.most_common(6)],
    }
    b["tips"] = suggestions(b)
    return b


def _tip(level, title, detail):
    return {"level": level, "title": title, "detail": detail}


def suggestions(b):
    """Rule-based tips. level: 'warn' (worth fixing), 'tip' (could help), 'good' (doing well)."""
    tips = []
    m = b["melee"]
    c = m["counts"]
    sw = m["swings"]

    if b["side"] == "npc":
        return _npc_tips(b)

    # ---- melee: misses
    if sw >= 30:
        miss = c.get("miss", 0)
        mp = _pct(miss, sw)
        if mp >= 25:
            tips.append(_tip("warn", f"Missing {mp:.0f}% of melee swings",
                             f"{miss} of {sw} swings missed outright. Misses come from your to-hit: check your "
                             f"weapon skills are maxed for your level (they rise slowly against easy mobs), "
                             f"look for Dexterity/accuracy upgrades, and expect more misses on mobs well above your level."))
        elif mp <= 12:
            tips.append(_tip("good", f"Good accuracy: only {mp:.0f}% misses", f"{miss} misses in {sw} swings."))

        # ---- front-only avoidance -> position
        front = sum(c.get(o, 0) for o in FRONT_ONLY)
        fp = _pct(front, sw)
        if fp >= 8 and b["type"] != "pet":
            parts = ", ".join(_n(c[o], {"parry": "parry", "block": "block", "riposte": "riposte"}[o]).replace("parrys", "parries") for o in FRONT_ONLY if c.get(o))
            tips.append(_tip("warn", f"{fp:.0f}% of your swings were parried, blocked or riposted",
                             f"{parts}. NPCs can only parry, block and riposte attacks from the front. "
                             f"Attack from behind (let the tank hold aggro, then move to the mob's back) "
                             f"to remove these entirely."))
        if c.get("riposte", 0) >= 3:
            tips.append(_tip("warn", f"Mobs riposted you {_n(c['riposte'], 'time')}",
                             "Each riposte is a free counter-attack that hits you. Fighting from behind stops ripostes."))
        dp = _pct(c.get("dodge", 0), sw)
        if dp >= 12:
            tips.append(_tip("tip", f"Mobs dodged {dp:.0f}% of your swings",
                             "Dodges happen from any side. Higher-level mobs dodge more; weapon skill and "
                             "offense help. If it's one mob type, it may just be a dodgy mob."))
        if c.get("absorb") or c.get("invulnerable"):
            tips.append(_tip("tip", "Some hits did nothing",
                             f"{c.get('absorb', 0)} absorbed by a rune/magical skin and {c.get('invulnerable', 0)} "
                             f"against an invulnerable target. Check whether the mob needs a debuff, a "
                             f"magic weapon, or a different damage type."))

    # ---- spells (yours only)
    for sp in b["spells"]:
        attempts = max((sp["casts"] - sp["fizzles"] - sp["interrupts"]) if sp["casts"] else 0,
                       sp["resists"] + sp["landed"])
        if attempts >= 5 and sp["resist_pct"] and sp["resist_pct"] >= 15:
            who = [m for m, d in b["resisted_by"].items() if d.get(sp["name"])]
            whom = f" Most resists came from {', '.join(who[:3])}." if who else ""
            tips.append(_tip("warn", f"{sp['name']} was resisted {sp['resist_pct']:.0f}% of the time",
                             f"{sp['resists']} resists out of about {attempts} completed casts.{whom} "
                             f"Try a resist debuff on the target first (for example Tashan's line for magic, "
                             f"or Malo for magic/fire/cold), or switch to a spell of a different resist type "
                             f"for that mob. Mobs of an element usually resist that element."))
        if sp["casts"] >= 5 and sp["interrupt_pct"] and sp["interrupt_pct"] >= 10:
            tips.append(_tip("warn", f"{sp['name']} was interrupted {_n(sp['interrupts'], 'time')} "
                                     f"({sp['interrupt_pct']:.0f}% of casts)",
                             "Getting hit while casting interrupts spells. Cast from further back, let the "
                             "tank establish aggro before casting, and keep Channeling skill up."))
        if sp["casts"] >= 10 and sp["fizzle_pct"] and sp["fizzle_pct"] >= 8:
            tips.append(_tip("tip", f"{sp['name']} fizzled {_n(sp['fizzles'], 'time')} ({sp['fizzle_pct']:.0f}%)",
                             "Fizzle chance drops as your skill in that spell's school rises, and is higher for "
                             "spells close to your level. Specializing in that school (if your class can) helps."))
    unknown = [s for s in b["spells"] if s["name"] in ("Unknown spell",)]
    if unknown and (unknown[0]["fizzles"] + unknown[0]["interrupts"]) >= 3:
        tips.append(_tip("tip", "Some fizzles/interrupts couldn't be matched to a spell",
                         "The game only names the spell sometimes. They're grouped under \"Unknown spell\"."))
    if b["misc"].get("immune", 0) >= 2:
        tips.append(_tip("tip", f"Target was immune {_n(b['misc']['immune'], 'time')}",
                         "Some mobs can't be slowed, snared, mezzed or stunned. Those casts were wasted mana."))
    if b["misc"].get("nohold", 0) >= 2:
        tips.append(_tip("tip", f"{b['misc']['nohold']} spells did not take hold",
                         "A stronger effect of the same type was already on the target (often a groupmate's buff "
                         "or debuff). Check before recasting."))

    # ---- uptime
    if b["damage"] and b["duration"] >= 20 and b["active_pct"] is not None:
        ap = b["active_pct"]
        if ap < 70:
            tips.append(_tip("warn", f"You were dealing damage for only {ap:.0f}% of the fight time",
                             "Gaps between your first and last hit are fine, but time before your first hit "
                             "and after your last is lost DPS. Engage as soon as the tank has aggro and keep "
                             "attacking or casting until the mob dies (watch your mana pacing)."))
        elif ap >= 90:
            tips.append(_tip("good", f"Great uptime: {ap:.0f}% of the fight", "You were attacking for almost the whole fight."))

    # ---- DoTs on short fights
    dot_dmg = b["kinds"].get("dot", 0)
    if b["fights"] and dot_dmg and b["damage"]:
        avg_len = b["duration"] / b["fights"]
        if avg_len < 30 and dot_dmg / b["damage"] > 0.25:
            tips.append(_tip("tip", f"DoTs on short fights (avg {avg_len:.0f}s)",
                             f"{100 * dot_dmg / b['damage']:.0f}% of your damage came from DoTs, but fights are "
                             f"short, so DoTs don't get to finish ticking. On quick kills, direct damage spells "
                             f"usually do more per mana."))

    # ---- damage taken
    if b["type"] in ("you", "player") and b["taken"] and b["damage"] and b["taken"] > 0.6 * b["damage"]:
        tips.append(_tip("tip", f"You took {b['taken']:,} damage while dealing {b['damage']:,}",
                         "If you're not the tank, that usually means you're pulling aggro. Let the tank get a few "
                         "hits in before going all-out, and watch the threat on burns."))
    d = b["defense"]
    if d["attempts"] >= 20 and b["type"] == "you":
        avoided = d["attempts"] - d["counts"].get("hit", 0)
        tips.append(_tip("good" if avoided / d["attempts"] >= 0.4 else "tip",
                         f"Mobs landed {d['hit_pct']:.0f}% of their attacks on you",
                         f"You avoided {avoided} of {d['attempts']} attacks (misses, dodges, parries, blocks, ripostes)."))

    # ---- resisting incoming spells
    if b["you_resisted"]:
        total = sum(b["you_resisted"].values())
        top = max(b["you_resisted"], key=b["you_resisted"].get)
        tips.append(_tip("good", f"You resisted {total} enemy spell{'s' if total != 1 else ''}",
                         f"Most often {top}. Your resist gear is paying off."))

    if not tips:
        tips.append(_tip("tip", "Not enough to go on yet",
                         "Tips appear once there's enough data (about 30 melee swings or 5 casts of a spell). "
                         "Try the \"Last 10 fights\" view for a bigger sample."))
    order = {"warn": 0, "tip": 1, "good": 2}
    return sorted(tips, key=lambda t: order[t["level"]])


def _npc_tips(b):
    tips = []
    vs = b["defense"]               # how your side's swings fared against this NPC
    c = vs["counts"]
    att = vs["attempts"]
    if att >= 20:
        avoid = att - c.get("hit", 0)
        ap = _pct(avoid, att)
        front = sum(c.get(o, 0) for o in FRONT_ONLY)
        if front and _pct(front, att) >= 8:
            tips.append(_tip("warn", f"It parried, blocked or riposted {_pct(front, att):.0f}% of your side's swings",
                             "Only possible from the front. Everyone except the tank should attack from behind."))
        if ap >= 35:
            tips.append(_tip("tip", f"It avoided {ap:.0f}% of attacks overall",
                             "A hard-to-hit mob. Accuracy and debuffs that lower its defense help most here."))
    resisted = b["resisted_by"].get("You", {})
    if sum(resisted.values()) >= 3:
        sp = max(resisted, key=resisted.get)
        tips.append(_tip("warn", f"It resisted your spells {_n(sum(resisted.values()), 'time')}",
                         f"Mostly {sp}. Try a different resist type against this mob, or debuff its resists first."))
    m = b["melee"]
    if m["swings"] >= 20 and m["accuracy"] is not None:
        tips.append(_tip("tip", f"It landed {m['accuracy']:.0f}% of its attacks on your side",
                         "Lower is better: slows, AC and avoidance on the tank bring this down."))
    if not tips:
        tips.append(_tip("tip", "Not enough to go on yet", "Fight it a little longer for useful numbers."))
    return tips

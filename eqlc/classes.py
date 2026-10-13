"""Works out the classes of you and your group members from the log.

Best first:
  1. /who            "[60 Paladin/Cleric/Wizard] Bobbin (Halfling) <Guild>" - exact.
  2. Settings        the three classes you picked for your own character (these win for you).
  3. What they do    spells they cast ("Bobbin begins casting Superior Healing.",
                     "Bobbin hit a ghoul for 320 points of cold damage by Ice Comet.",
                     "Bobbin healed you for 900 hit points by Superior Healing.",
                     "a ghoul has taken 40 damage from Clinging Darkness by Bobbin."),
                     songs, and melee skills (backstab, frenzy, bash, kick), checked
                     against EQLWiki's spell lists (classes_data.py). Each EQL character
                     has three classes, so up to three are picked: the fewest classes
                     that explain everything seen, preferring spells only one class has.

Everything is kept per server (Bobbin on rivervale is not Bobbin on paineel).
"""
import re
import time

from . import classes_data as D

MAX_NAMES = 500
MAX_SIGS = 80

_NAME = r"[A-Z][a-z]{2,14}"
WHO_RE = re.compile(r"\[(?P<lvl>\d+) (?P<cls>[A-Za-z' /,]+?)\] (?P<name>" + _NAME + r")\b")
CAST_RE = re.compile(r"^(?P<src>" + _NAME + r") begins (?:casting|to cast) (?P<spell>.+?)\.$")
SING_RE = re.compile(r"^(?P<src>" + _NAME + r") begins (?:singing|to sing)\b(?: (?P<spell>.+?))?\.$")
MY_CAST_RE = re.compile(r"^You begin (?:casting|singing) (?P<spell>.+?)\.$")
HEAL_RE = re.compile(r"^(?P<src>You|" + _NAME + r") (?:healed|heal) (?P<tgt>.+?) for (?P<amt>\d+)"
                     r"(?: \(\d+\))? hit points?(?: by (?P<spell>.+?))?\.")
BY_SPELL_RE = re.compile(r"^(?P<src>You|" + _NAME + r") (?:hit|hits) .+? for \d+ points? of [a-z ]*damage by "
                         r"(?P<spell>.+?)\.")
DOT_BY_RE = re.compile(r"^.+? has taken \d+ damage from (?P<spell>.+?) by (?P<src>" + _NAME + r")\.")
DOT_YOUR_RE = re.compile(r"^.+? has taken \d+ damage from your (?P<spell>.+?)\.")
SKILL_RE = re.compile(r"^(?P<src>You|" + _NAME + r") (?P<verb>backstabs?|frenz(?:y|ies) on|bash(?:es)?|kicks?) "
                      r".+? for \d+ points? of damage")
WARDER_RE = re.compile(r"^(?P<src>" + _NAME + r")`s warder\b")


def classes_from_who(text):
    """'Paladin/Cleric/Wizard' or 'Pal/Clr/Wiz' or 'Wizard' -> ['Paladin', 'Cleric', 'Wizard']."""
    out = []
    for part in re.split(r"[/,]", text or ""):
        c = D.ALIASES.get(part.strip().lower())
        if c and c not in out:
            out.append(c)
    return out


def sig_classes(sig):
    kind, _, what = sig.partition(":")
    if kind == "spell":
        return D.SPELL_CLASSES.get(D.spell_key(what), set())
    if kind == "skill":
        return D.ABILITIES.get(what, set())
    return set()


def guess(sigs, limit=3):
    """{signal: count} -> [{"class", "sure", "evidence": [...]}], at most `limit` classes.

    Greedy set cover: keep picking the class that explains the most still-unexplained
    signals (a spell only one class has counts more than a shared one)."""
    known = {s: sig_classes(s) for s in sigs}
    left = {s for s, cl in known.items() if cl}
    picks = []
    while left and len(picks) < limit:
        score = {}
        for s in left:
            cl = known[s]
            for c in cl:
                a, b = score.get(c, (0.0, 0))
                score[c] = (a + 1.0 / len(cl), b + sigs[s])
        best = max(score, key=lambda c: (score[c], c))
        covered = {s for s in left if best in known[s]}
        ev = sorted(covered, key=lambda s: (-sigs[s], s))
        alts = sorted(c for c in score if c != best and score[c][0] == score[best][0]
                      and {s for s in left if c in known[s]} == covered)
        picks.append({"class": best, "sure": any(len(known[s]) == 1 for s in covered), "alts": alts,
                      "evidence": [f"{s.partition(':')[2]}" + (f" ×{sigs[s]}" if sigs[s] > 1 else "") for s in ev[:6]]})
        left -= covered
    return picks


class ClassSpotter:
    def __init__(self, state):
        self.root = state.setdefault("classes", {})          # server -> {"who": {...}, "seen": {...}}
        self.dirty = False

    @staticmethod
    def _split(char):
        name, _, server = (char or "").partition("_")
        return name, (server or "-")

    def _srv(self, server):
        s = self.root.setdefault(server, {})
        s.setdefault("who", {})
        s.setdefault("seen", {})
        return s

    def _see(self, server, name, sig):
        seen = self._srv(server)["seen"]
        row = seen.get(name)
        if row is None:
            if len(seen) >= MAX_NAMES:                      # forget the least recently seen name
                old = min(seen, key=lambda n: seen[n].get("_t", 0))
                del seen[old]
            row = seen[name] = {}
        if sig not in row and len([k for k in row if k != "_t"]) >= MAX_SIGS:
            return
        row[sig] = row.get(sig, 0) + 1
        row["_t"] = time.time()
        self.dirty = True

    def feed(self, char, t, line):
        """Look at one log line. Returns the name of another player it shows doing something, if any."""
        if not line:
            return None
        msg = line.split("] ", 1)[-1] if line.startswith("[") else line
        me, server = self._split(char)
        if msg.lstrip().startswith(("[", "AFK", "LFG", "<LINKDEAD>")):
            m = WHO_RE.search(msg)
            if m:
                cls = classes_from_who(m.group("cls"))
                if cls:
                    self._srv(server)["who"][m.group("name")] = {"classes": cls, "level": int(m.group("lvl")),
                                                                 "t": t}
                    self.dirty = True
            return None
        if "`s warder" in msg:
            m = WARDER_RE.match(msg)
            if m:
                self._see(server, m.group("src"), "skill:warder")
                return m.group("src")
        sig = src = None
        if msg.startswith("You "):
            m = MY_CAST_RE.match(msg)
            if m:
                src, sig = "You", "spell:" + m.group("spell")
        if not sig and " begins " in msg:
            m = CAST_RE.match(msg)
            if m and m.group("spell") not in ("a spell",):
                src, sig = m.group("src"), "spell:" + m.group("spell")
            else:
                m = SING_RE.match(msg)
                if m:
                    src, sig = m.group("src"), ("spell:" + m.group("spell")) if m.group("spell") and \
                        m.group("spell") != "a song" else "skill:sing"
        if not sig and " hit points" in msg:
            m = HEAL_RE.match(msg)
            if m and m.group("spell"):
                src, sig = m.group("src"), "spell:" + m.group("spell")
        if not sig and " damage by " in msg:
            m = BY_SPELL_RE.match(msg)
            if m:
                src, sig = m.group("src"), "spell:" + m.group("spell")
        if not sig and " damage from " in msg:
            m = DOT_BY_RE.match(msg) or DOT_YOUR_RE.match(msg)
            if m:
                src = m.groupdict().get("src") or "You"
                sig = "spell:" + m.group("spell")
        if not sig and " points of damage" in msg:
            m = SKILL_RE.match(msg)
            if m:
                v = m.group("verb")
                skill = "backstab" if v.startswith("backstab") else "frenzy" if v.startswith("frenz") else \
                    "bash" if v.startswith("bash") else "kick"
                src, sig = m.group("src"), "skill:" + skill
        if not sig:
            return None
        if sig.startswith("spell:") and not sig_classes(sig):
            return src if src != "You" else None         # an unknown spell (item click, etc.): still a player
        name = me if src == "You" else src
        if name:
            self._see(server, name, sig)
        return None if src == "You" else src

    # -- answers -------------------------------------------------------------------
    def who(self, server, name):
        return self._srv(server)["who"].get(name)

    def classes_of(self, server, name, saved=None):
        """{"name", "classes": [...], "source": "who" | "settings" | "spells" | None, "sure": bool, "evidence"}."""
        w = self.who(server, name)
        if saved and len(saved) == 3:
            src = "who" if w and w["classes"][:3] == list(saved) else "settings"
            return {"name": name, "classes": list(saved), "source": src, "sure": True, "evidence": {}, "alts": {},
                    "level": w.get("level") if w else None}
        if w and len(w["classes"]) >= 3:
            return {"name": name, "classes": w["classes"][:3], "source": "who", "sure": True, "evidence": {},
                    "alts": {}, "level": w.get("level")}
        seen = {k: v for k, v in (self._srv(server)["seen"].get(name) or {}).items() if k != "_t"}
        picks = guess(seen)
        base = list(w["classes"]) if w else []
        out = list(base)
        ev, alts = {}, {}
        for p in picks:
            if len(out) >= 3:
                break
            if p["class"] not in out:
                out.append(p["class"])
                ev[p["class"]] = p["evidence"]
                if p["alts"]:
                    alts[p["class"]] = p["alts"]
        src = "who" if base and len(out) == len(base) else ("spells" if out else None)
        return {"name": name, "classes": out, "source": src, "sure": bool(out) and all(
            p["sure"] for p in picks if p["class"] in ev) and len(out) == 3, "evidence": ev, "alts": alts,
            "level": w.get("level") if w else None}

    def group(self, char, players, saved_me=None):
        """You plus the other players of a run, each with their classes (as far as the log shows)."""
        me, server = self._split(char)
        rows = [dict(self.classes_of(server, me, saved_me), you=True)]
        for p in sorted(players or ()):
            rows.append(dict(self.classes_of(server, p), you=False))
        return rows

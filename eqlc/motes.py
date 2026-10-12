"""Mote counter - same matching rules as scroll-bridge.js, split by tier.

Ported from scroll-bridge.js (MOTE_PATTERN / countMoteMatches):
    --you have looted a mote of lesser potential from a decaying skeleton
    --you have looted 4 motes of lesser potential from a decaying skeleton
"a"/"an" counts as 1, a number counts as that many. The tier word is
optional (no tier = "Potential"). Case-insensitive. The only change from the
bridge is that the tier word is captured so counts can be split; which lines
match, and the totals, are identical.

Counts cover this session only: motes looted since the app was opened.
They aren't saved, and there is no timed reset.
"""
import re
import time

MOTE_TIERS = ["lesser", "major", "greater", "superior", "grand", "ascendant", "infinite"]
PLAIN = "potential"          # "a mote of potential" with no tier word
TIER_ORDER = [PLAIN] + MOTE_TIERS
MOTE_PATTERN = re.compile(
    r"--you have looted (an?|\d+) motes? of (?:(" + "|".join(MOTE_TIERS) + r")\s+)?potential",
    re.IGNORECASE)


def mote_matches(text):
    """Yield (tier, qty) for every mote loot in text."""
    for m in MOTE_PATTERN.finditer(text):
        q = m.group(1)
        yield (m.group(2) or PLAIN).lower(), (int(q) if q.isdigit() else 1)


def count_mote_matches(text):
    return sum(q for _, q in mote_matches(text))


def tier_label(t):
    return "Potential (no tier)" if t == PLAIN else t.capitalize()


class MoteCounter:
    """Motes looted since the app was opened (per character, not saved)."""

    def __init__(self, state=None, cfg=None, now=None):
        if state is not None:
            state.pop("motes", None)              # older versions saved counts with a 12h reset
        self.session_start = time.time() if now is None else now
        self.s = {}
        self.dirty = False

    def get(self, char):
        m = self.s.get(char)
        if m is None:
            m = self.s[char] = {"count": 0, "tiers": {}, "start": self.session_start}
        return m

    def tick(self, char, now=None):
        pass                                       # no timed reset any more

    def process_line(self, char, t, line):
        """Called for every new log line (only lines not seen before)."""
        if "mote" not in line.lower():
            return 0
        m = self.get(char)
        if t < m["start"] - 1:                     # looted before the app was opened
            return 0
        n = 0
        for tier, q in mote_matches(line):
            m["tiers"][tier] = m["tiers"].get(tier, 0) + q
            n += q
        if n:
            m["count"] += n
            m["last"] = t
        return n

    def view(self, char, now=None):
        m = self.get(char)
        now = time.time() if now is None else now
        hours = max((now - m["start"]) / 3600, 1 / 60)
        tiers = [{"tier": t, "label": tier_label(t), "count": m["tiers"].get(t, 0),
                  "per_hour": round(m["tiers"].get(t, 0) / hours, 1)}
                 for t in TIER_ORDER if m["tiers"].get(t)]
        return {"count": m["count"], "per_hour": round(m["count"] / hours, 1),
                "since": m["start"], "last": m.get("last"), "tiers": tiers}

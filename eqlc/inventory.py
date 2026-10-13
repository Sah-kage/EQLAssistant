"""Reads EverQuest Legends inventory exports (/outputfile inventory).

The file is tab separated and has two sections:

    Location        Name                        ID      Count   Slots
    General 1-Slot3 Mystic Ash                  14246   57      10
    Bank13-Slot20   Glowing Sword Hilt          12197   1       10
    Primary-Slot8   SoulFire (Exaltation)       5504    1       10
    ...
    (blank line)
    KeyRing         Name                        ID
    Equipment       SoulFire +2                 5504
    Augmentation    Lute (Exaltation)           13011

Names can carry an upgrade level ("SoulFire +2") or "(Exaltation)" when the
item has been turned into an augment. Both still prove you own the item, so
they count when deciding whether a quest is done. Only plain items in your
bags, bank or worn slots count as items you can hand in.
"""
import re

_LEVEL = re.compile(r"\s+\+\d+$")
_EXALT = re.compile(r"\s*\(Exaltation\)$", re.IGNORECASE)
_FILE_CHAR = re.compile(r"^(?P<char>[^_\-.]+)(?:_[^-]*)?-Inventory", re.IGNORECASE)

WORN = {"Charm", "Ear", "Head", "Face", "Neck", "Shoulders", "Arms", "Back", "Wrist", "Range", "Hands",
        "Primary", "Secondary", "Fingers", "Chest", "Legs", "Feet", "Waist", "Ammo", "Power Source",
        "Any Slot", "Held"}


def base_name(name):
    """'SoulFire +2' / 'SoulFire (Exaltation)' -> 'SoulFire'."""
    name = (name or "").strip().rstrip("*")
    return _LEVEL.sub("", _EXALT.sub("", name)).strip()


def is_exaltation(name):
    return bool(_EXALT.search(name or ""))


def char_from_filename(fname):
    """'Sahkage_rivervale-Inventory.txt' -> 'Sahkage_rivervale' (characters are per server).
    'Sahkage-Inventory.txt' -> 'Sahkage' (server unknown)."""
    base = (fname or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    m = re.match(r"^(?P<char>[^_\-.]+)(?:_(?P<server>[^-]+))?-Inventory", base, re.IGNORECASE)
    if not m:
        return None
    name = m.group("char").capitalize()
    return f"{name}_{m.group('server').lower()}" if m.group("server") else name


def place(location):
    """'Bank13-Slot20' -> 'Bank', 'General 1-Slot3' -> 'Bags', 'Primary-Slot8' -> 'Worn'."""
    top = (location or "").split("-", 1)[0].strip()
    if top.startswith("SharedBank"):
        return "Shared bank"
    if top.startswith("Bank"):
        return "Bank"
    if top.startswith("General") or top == "Cursor":
        return "Bags"
    if top in WORN or re.sub(r"\d+$", "", top) in WORN:
        return "Worn"
    return top or "?"


def parse(text):
    """Return {"counts": {name: n}, "owned": [names], "where": {name: [places]}, "items": n}.

    counts - plain items you could hand in (bags, bank, worn), by base name
    owned  - every item you own in any form, incl. upgraded, Exaltation and key ring
    where  - which places each item is in (Bags, Bank, Worn, Shared bank, Key ring)
    Names are returned as written in the file (base name), not lower-cased.
    """
    counts, where, owned = {}, {}, set()
    section = None
    for raw in text.splitlines():
        parts = raw.rstrip("\r\n").split("\t")
        if not parts or not parts[0].strip():
            continue
        head = parts[0].strip()
        if head == "Location" and len(parts) > 1 and parts[1].strip() == "Name":
            section = "main"
            continue
        if head == "KeyRing" and len(parts) > 1 and parts[1].strip() == "Name":
            section = "keyring"
            continue
        if section is None:
            section = "main"            # file without a header line
        if len(parts) < 2:
            continue
        name = parts[1].strip()
        if not name or name == "Empty":
            continue
        base = base_name(name)
        owned.add(base)
        if section == "keyring":
            loc = "Key ring"
            where.setdefault(base, set()).add(loc)
            continue
        loc = place(head)
        where.setdefault(base, set()).add(loc)
        if is_exaltation(name):
            continue                    # an augment now; can't be handed in
        try:
            n = int(parts[3]) if len(parts) > 3 and parts[3].strip() else 1
        except ValueError:
            n = 1
        counts[base] = counts.get(base, 0) + max(1, n)
    return {"counts": counts, "owned": sorted(owned), "where": {k: sorted(v) for k, v in where.items()},
            "items": sum(counts.values())}

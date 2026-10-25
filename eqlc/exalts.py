"""Exaltations: every exaltation a character has, where it is, what slot it fits and who can use it.

Where they come from: the inventory export (/outputfile inventory, Name_server-Inventory.txt).
  - "Primary-Slot8   SoulFire (Exaltation)" is installed in the item worn in Primary.
    An item's exaltation slots are its sub-slots 7-10: 7 Focus, 8 Click, 9 Worn, 10 Proc
    (EQLWiki "Exaltations": Focus +1, Click +2, Worn +3, Proc +4).
  - "General 3-Slot1-Slot10 ..." is installed in the item in that bag slot.
  - "General 3-Slot15 ... (Exaltation)" is loose in a bag; the KeyRing section's
    "Augmentation"/"Activated" rows are exaltations kept on the key ring.

What slot and class: an exaltation keeps the slot and class restrictions of the item it was made
from (EQLWiki). The exaltation's ID is that item's ID, and its name is the item's name, so the
app reads the item's page on eqlwiki.com once ("Slot: FINGER", "Class: WAR PAL SHD", effects)
and remembers it.
"""
import html
import re
import threading
import time
import urllib.parse
import urllib.request

from . import classes_data as CD
from .inventory import base_name, is_exaltation

WIKI = "https://eqlwiki.com/"
SUBSLOT_KIND = {7: "Focus", 8: "Click", 9: "Worn", 10: "Proc"}
KINDS = ["Focus", "Click", "Worn", "Proc", "Ornamentation"]

# equipment slots, in the order the game lists them
SLOTS = ["Charm", "Ear", "Head", "Face", "Neck", "Shoulders", "Arms", "Back", "Wrist", "Range", "Hands",
         "Primary", "Secondary", "Fingers", "Chest", "Legs", "Feet", "Waist", "Ammo", "Power Source"]
_SLOT_WORD = {"CHARM": "Charm", "EAR": "Ear", "EARS": "Ear", "HEAD": "Head", "FACE": "Face", "NECK": "Neck",
              "SHOULDER": "Shoulders", "SHOULDERS": "Shoulders", "ARMS": "Arms", "ARM": "Arms", "BACK": "Back",
              "WRIST": "Wrist", "WRISTS": "Wrist", "RANGE": "Range", "RANGED": "Range", "HANDS": "Hands",
              "HAND": "Hands", "PRIMARY": "Primary", "SECONDARY": "Secondary", "FINGER": "Fingers",
              "FINGERS": "Fingers", "CHEST": "Chest", "LEGS": "Legs", "FEET": "Feet", "WAIST": "Waist",
              "AMMO": "Ammo", "POWER": "Power Source", "SOURCE": None}
_SUB = re.compile(r"^(?P<parent>.+)-Slot(?P<n>\d+)$")
_CLASS_ABBR = {"WAR": "Warrior", "CLR": "Cleric", "PAL": "Paladin", "RNG": "Ranger", "SHD": "Shadow Knight",
               "SK": "Shadow Knight", "DRU": "Druid", "MNK": "Monk", "BRD": "Bard", "ROG": "Rogue", "SHM": "Shaman",
               "NEC": "Necromancer", "WIZ": "Wizard", "MAG": "Magician", "ENC": "Enchanter", "BST": "Beastlord",
               "BER": "Berserker"}


def worn_slot(location):
    """'Fingers' / 'Ear' / 'Primary' -> slot name; 'General 3-Slot2' -> None."""
    top = (location or "").split("-", 1)[0].strip()
    top = re.sub(r"\d+$", "", top).strip()
    return top if top in SLOTS else None


def _rows(text):
    """(section, location, name, id, slots column) for every non-blank row of an export."""
    section = "main"
    for raw in text.splitlines():
        parts = raw.rstrip("\r\n").split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        head, name = parts[0].strip(), parts[1].strip()
        if name == "Name" and head in ("Location", "KeyRing"):
            section = "keyring" if head == "KeyRing" else "main"
            continue
        yield (section, head, name, parts[2].strip() if len(parts) > 2 else "",
               parts[4].strip() if len(parts) > 4 else "")


def _bags(rows):
    """Locations that hold a bag (or chest/kit): their sub-slots are bag slots, not exaltation slots.

    Decided only by what's inside, never by names or the Slots column (which can change between game
    versions): a bag has a slot numbered above 10, or holds an ordinary item (not an exaltation).
    A worn slot (Primary, Ear...) always holds an item."""
    bags = set()
    for section, head, name, _, _size in rows:
        if section != "main":
            continue
        m = _SUB.match(head)
        if not m:
            continue
        parent, n = m.group("parent"), int(m.group("n"))
        if worn_slot(parent) and "-" not in parent:
            continue
        ordinary = name and name != "Empty" and not is_exaltation(name) and "ornament" not in name.lower()
        if n > 10 or ordinary:          # an item's sub-slots only ever hold exaltations (or an ornamentation)
            bags.add(parent)
    return bags


def parse_export(text):
    """{"exalts": [...], "items": [...]} from an inventory export.

    exalts: every exaltation - {name, id, location, place, installed_in, installed_loc, kind}
    items:  every item (worn, in bags, bank or shared bank) with an exaltation installed -
            {name, location, place, slots: {Focus/Click/Worn/Proc: exaltation name, "" = empty, None = locked}}
            (the export lists only the exaltation slots an item has unlocked)"""
    rows = list(_rows(text))
    bags = _bags(rows)
    current = {}                        # location -> the item there (the latest one: "Ear"/"Fingers" come twice)
    items, exalts = [], []
    for section, head, name, iid, _ in rows:
        if section == "keyring":
            if is_exaltation(name):
                exalts.append({"name": base_name(name), "id": iid, "location": f"Key ring ({head})",
                               "place": "Key ring", "installed_in": None, "installed_loc": None,
                               "kind": "Click" if head.lower() == "activated" else None})
            continue
        m = _SUB.match(head)
        parent = m.group("parent") if m else None
        n = int(m.group("n")) if m else None
        in_item = parent is not None and parent not in bags and n in SUBSLOT_KIND and parent in current
        if in_item:                                     # one of an item's exaltation slots (empty or not)
            it = current[parent]
            it["slots"][SUBSLOT_KIND[n]] = base_name(name) if is_exaltation(name) else ""
        if name == "Empty" or not name:
            continue
        if not is_exaltation(name):
            if head not in bags:
                it = {"name": name, "location": head, "place": None,
                      "slots": {"Focus": None, "Click": None, "Worn": None, "Proc": None}}
                current[head] = it
                items.append(it)
            continue
        row = {"name": base_name(name), "id": iid, "location": head, "installed_in": None, "installed_loc": None,
               "kind": None}
        if in_item:
            row.update(installed_loc=parent, kind=SUBSLOT_KIND[n], installed_in=current[parent]["name"])
        exalts.append(row)
    for r in exalts:
        r["place"] = r.get("place") or _place(r)
    with_exalts = []
    for it in items:
        if any(v for v in it["slots"].values()):
            it["place"] = _place({"installed_loc": it["location"], "location": it["location"]})
            with_exalts.append(it)
    return {"exalts": exalts, "items": with_exalts}


def exaltations(text):
    """[{name, id, location, place, installed_in, installed_loc, kind}] from an inventory export."""
    return parse_export(text)["exalts"]


def _place(r):
    loc = r["installed_loc"] or r["location"]
    top = loc.split("-", 1)[0].strip()
    if r["installed_loc"] and worn_slot(loc):
        return "Worn"
    if top.startswith("SharedBank"):
        return "Shared bank"
    if top.startswith("Bank"):
        return "Bank"
    if top.startswith("General") or top == "Cursor":
        return "Bags"
    return "Worn" if worn_slot(loc) else top


# ----------------------------------------------------------------------------- EQLWiki item pages
def html_to_text(page):
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|dd|dt|table|pre)>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    lines = [re.sub(r"[ \t ]+", " ", html.unescape(x)).strip() for x in page.split("\n")]
    return "\n".join(x for x in lines if x)


def parse_item(text):
    """The item box of an EQLWiki item page -> {"slots", "classes", "effects": {kind: [names]}}.
    None when the text has no item box."""
    i = text.find("Slot:")
    if i < 0:
        i = text.find("Class:")
        if i < 0:
            return None
    box = text[max(0, i - 400): i + 1500]
    slots = []
    m = re.search(r"Slot:\s*([A-Z ,/]+)", box)
    if m:
        for w in re.split(r"[\s,/]+", m.group(1)):
            s = _SLOT_WORD.get(w.upper())
            if s and s not in slots:
                slots.append(s)
            elif w and w.upper() not in _SLOT_WORD:
                break
    classes = []
    m = re.search(r"Class:\s*([A-Za-z ]+)", box)
    if m:
        words = m.group(1).split()
        if words and words[0].upper() == "ALL":
            classes = ["ALL"]
        else:
            for w in words:
                c = _CLASS_ABBR.get(w.upper()) or CD.ALIASES.get(w.lower())
                if not c:
                    break
                if c not in classes:
                    classes.append(c)
    effects = {}
    for line in box.split("\n"):
        f = re.search(r"Focus(?: Effect)?:\s*(.+)", line)
        if f:
            effects.setdefault("Focus", []).append(f.group(1).strip())
            continue
        if re.search(r"(Instruments?|Singing|Percussion|Brass|Stringed|Wind)[^:]*:\s*\d", line):
            effects.setdefault("Focus", []).append(line.strip())
            continue
        e = re.search(r"Effect:\s*(.+?)\s*\(([^)]*)\)", line)
        if e:
            what = e.group(2).lower()
            kind = ("Proc" if "combat" in what else "Worn" if "worn" in what else
                    "Click" if any(w in what for w in ("any slot", "must equip", "casting", "inventory", "click"))
                    else None)
            if kind:
                effects.setdefault(kind, []).append(e.group(1).strip())
    if not slots and not classes:
        return None
    return {"slots": slots, "classes": classes, "effects": effects}


def title_variants(name):
    n = name.strip()
    out = []
    for v in (n.replace("`", "'"), n, n.replace("`", "")):
        if v and v not in out:
            out.append(v)
    return out


def fetch_item(name, opener=None):
    """Read an item's page on eqlwiki.com. Returns parse_item(...) plus "title"/"url", or {"missing": True}."""
    for t in title_variants(name):
        url = WIKI + urllib.parse.quote(t.replace(" ", "_"), safe="'_()")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (EQLAssistant item lookup)"})
        try:
            with (opener or urllib.request.urlopen)(req, timeout=15) as r:
                page = r.read().decode("utf-8", "replace")
        except Exception as e:                           # 404 = no page by that name: try the next spelling
            if getattr(e, "code", None) == 404:
                continue
            raise
        info = parse_item(html_to_text(page))
        if info:
            return dict(info, title=t, url=url)
    return {"missing": True}


# ----------------------------------------------------------------------------- the tab
class Exalts:
    def __init__(self, state, sky, my_classes=lambda char: None, opener=None):
        self.cache = state.setdefault("item_info", {})   # item name (lower) -> fetch_item() result + "t"
        self.sky = sky
        self.my_classes = my_classes
        self.opener = opener
        self.dirty = False
        self.busy = set()
        self.error = None
        self._lock = threading.Lock()

    @staticmethod
    def key(name):
        return name.lower().replace("`", "'").strip()

    def rows(self, char):
        inv = self.sky.char(char).get("inventory") or {}
        return inv.get("exalts"), inv.get("t")

    def items(self, char):
        """Items (worn, bags, bank, shared bank) with an exaltation installed, and what's in each slot."""
        inv = self.sky.char(char).get("inventory") or {}
        out = []
        for it in inv.get("exalt_items") or []:
            slots = {}
            for kind, name in it["slots"].items():
                if name:
                    info = self.cache.get(self.key(name)) or {}
                    eff = info.get("effects") or {}
                    slots[kind] = {"name": name, "effect": eff.get(kind) or [e for k in KINDS for e in eff.get(k, [])],
                                   "wiki": info.get("url") or (WIKI + name.replace("`", "'").replace(" ", "_"))}
                else:
                    slots[kind] = name                  # "" = empty slot, None = not unlocked
            out.append(dict(it, slots=slots, free=sum(1 for v in it["slots"].values() if v == "")))
        order = {"Worn": 0, "Bags": 1, "Bank": 2, "Shared bank": 3}
        return sorted(out, key=lambda i: (order.get(i["place"], 9), i["location"]))

    def lookup(self, names, force=False):
        """Read the items' EQLWiki pages in the background (once each, unless forced)."""
        todo = []
        with self._lock:
            for n in dict.fromkeys(names):
                k = self.key(n)
                if k in self.busy:
                    continue
                c = self.cache.get(k)
                if c and not force and (not c.get("failed") or time.time() - c.get("t", 0) < 3600):
                    continue
                self.busy.add(k)
                todo.append(n)
        if not todo:
            return 0

        def run():
            for n in todo:
                k = self.key(n)
                try:
                    info = fetch_item(n, self.opener)
                    self.error = None
                except Exception as e:                   # offline, wiki down...
                    info = {"failed": True}
                    self.error = f"Couldn't reach eqlwiki.com: {getattr(e, 'reason', e)}"
                info["t"] = time.time()
                with self._lock:
                    self.cache[k] = info
                    self.busy.discard(k)
                    self.dirty = True
                time.sleep(0.3)                          # be gentle with the wiki
        threading.Thread(target=run, daemon=True).start()
        return len(todo)

    def view(self, char, fetch=True):
        rows, t = self.rows(char)
        if rows is None:
            return {"char": char, "inventory": None, "slots": [], "count": 0}
        inv = self.sky.char(char).get("inventory") or {}
        stale = inv.get("exalt_v") != 2
        mine = self.my_classes(char) or []
        names = []
        out = []
        for r in rows:
            info = self.cache.get(self.key(r["name"])) or {}
            if not info:
                names.append(r["name"])
            slots = list(info.get("slots") or [])
            slot_from = "wiki" if slots else None
            if not slots and r["installed_loc"] and worn_slot(r["installed_loc"]):
                slots, slot_from = [worn_slot(r["installed_loc"])], "installed"
            kind = r["kind"]
            if not kind:
                eff = info.get("effects") or {}
                kinds = [k for k in KINDS if eff.get(k)]
                kind = kinds[0] if len(kinds) == 1 else None
            eff = info.get("effects") or {}
            # the effect this exaltation carries: the one of its type, else whatever the item has
            effect = eff.get(kind) if kind and eff.get(kind) else [e for k in KINDS for e in eff.get(k, [])]
            classes = info.get("classes") or []
            usable = None
            if classes and mine:
                usable = classes == ["ALL"] or bool(set(classes) & set(mine))
            out.append(dict(r, slots=slots, slot_from=slot_from, kind=kind, classes=classes, usable=usable, effect=effect,
                            effects=info.get("effects") or {}, wiki=info.get("url") or (WIKI + r["name"].replace("`", "'").replace(" ", "_")),
                            looked_up=bool(info) and not info.get("failed"), missing=bool(info.get("missing")),
                            busy=self.key(r["name"]) in self.busy))
        if fetch and names:
            self.lookup(names)
        # organised by slot: an exaltation that fits several slots is listed under each of them
        groups = {}
        for r in out:
            for s in (r["slots"] or ["Slot not known yet"]):
                groups.setdefault(s, []).append(dict(r, also=[x for x in r["slots"] if x != s]))
        order = SLOTS + ["Slot not known yet"]
        sections = [{"slot": s, "rows": sorted(groups[s], key=lambda r: (r["installed_in"] is None, KINDS.index(r["kind"])
                                                                          if r["kind"] in KINDS else 9, r["name"]))}
                    for s in sorted(groups, key=lambda s: order.index(s) if s in order else 99)]
        return {"char": char, "inventory": t, "sections": sections, "count": len(out), "items": self.items(char),
                "stale": stale,
                "installed": sum(1 for r in out if r["installed_in"]), "my_classes": mine,
                "pending": sum(1 for r in out if r["busy"] or not (r["looked_up"] or r["missing"])),
                "error": self.error}

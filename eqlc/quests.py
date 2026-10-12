"""Class quest checklists: built-in quests + your own, tracked per character.

An item counts as collected when:
  - you tick it yourself (needed for ground pick-ups, combines and hand-ins,
    which the log doesn't always show), or
  - you hold enough of it: from your latest /outputfile inventory export, plus
    anything looted or received ("You receive X") after that export.
Every item you loot or receive is recorded, so quests you add later still see
items you picked up earlier.
"""
import json
import time
import urllib.parse
import urllib.request

from . import quests_data as D

MAX_LEDGER = 25000
WIKI_API = "https://eqlwiki.com/api.php"


def _k(s):
    """Match key: case-insensitive, ` = ', and a leading a/an/the ignored
    ("A Spider Venom Sac" is logged as "--You have looted a Spider Venom Sac--")."""
    s = (s or "").lower().replace("`", "'").strip()
    for art in ("a ", "an ", "the "):
        if s.startswith(art):
            return s[len(art):]
    return s


class Quests:
    def __init__(self, state, sky):
        self.s = state.setdefault("quests", {})
        self.custom = state.setdefault("custom_quests", [])
        self.ledger = state.setdefault("ledger", {})
        self.sky = sky          # for the inventory export snapshot
        self.dirty = False

    # -- data ------------------------------------------------------------------
    def all_quests(self):
        return D.QUESTS + self.custom

    def get(self, qid):
        return next((q for q in self.all_quests() if q["id"] == qid), None)

    def char(self, char):
        c = self.s.get(char)
        if c is None:
            c = self.s[char] = {"ticks": {}, "done": {}, "classes": []}
        return c

    # -- log events --------------------------------------------------------------
    def process(self, char, t, ev):
        typ = ev["type"]
        if typ == "loot" and ev.get("who") == "You":
            item, qty = ev["item"], ev.get("qty", 1)
        elif typ == "receive":
            item, qty = ev["item"], 1
        else:
            return
        led = self.ledger.setdefault(char, [])
        led.append([t, item, qty])
        if len(led) > MAX_LEDGER:
            del led[: len(led) - MAX_LEDGER]
        self.dirty = True

    def held(self, char):
        """item key -> count you hold (best estimate)."""
        inv = self.sky.char(char).get("inventory") if char in self.sky.s else None
        since = inv["t"] if inv else 0
        counts = {}
        for k, v in (inv["counts"].items() if inv else ()):
            counts[_k(k)] = counts.get(_k(k), 0) + v
        for t, item, qty in self.ledger.get(char, []):
            if t > since:
                k = _k(item)
                counts[k] = counts.get(k, 0) + qty
        return counts, bool(inv)

    # -- edits -----------------------------------------------------------------
    def tick(self, char, qid, idx, on):
        c = self.char(char)
        ticks = c["ticks"].setdefault(qid, [])
        if on and idx not in ticks:
            ticks.append(idx)
        elif not on and idx in ticks:
            ticks.remove(idx)
        self.dirty = True

    def set_done(self, char, qid, on):
        c = self.char(char)
        if on:
            c["done"][qid] = time.time()
        else:
            c["done"].pop(qid, None)
        self.dirty = True

    def set_classes(self, char, classes):
        self.char(char)["classes"] = [x for x in classes if x in D.CLASSES]
        self.dirty = True

    def save_custom(self, q):
        """Add or replace a custom quest. q: {id?, name, cls[], reward, wiki, notes, items[{n,q,src,how,g}]}"""
        items = []
        for it in q.get("items", []):
            n = str(it.get("n", "")).strip()
            if not n:
                continue
            try:
                qty = max(1, int(it.get("q") or 1))
            except (TypeError, ValueError):
                qty = 1
            d = {"n": n, "q": qty, "src": str(it.get("src", "")).strip(), "how": it.get("how") or "drop"}
            if it.get("g"):
                d["g"] = str(it["g"]).strip()
            items.append(d)
        qid = q.get("id") or f"custom-{int(time.time() * 1000)}"
        clean = {"id": qid, "custom": True, "kind": "custom", "name": str(q.get("name", "")).strip() or "Untitled quest",
                 "cls": [x for x in q.get("cls", []) if x in D.CLASSES] or ["Any"],
                 "reward": str(q.get("reward", "")).strip(), "wiki": str(q.get("wiki", "")).strip(),
                 "notes": str(q.get("notes", "")).strip(), "giver": str(q.get("giver", "")).strip(), "items": items}
        for i, old in enumerate(self.custom):
            if old["id"] == qid:
                self.custom[i] = clean
                break
        else:
            self.custom.append(clean)
        self.dirty = True
        return clean

    def delete_custom(self, qid):
        self.custom[:] = [q for q in self.custom if q["id"] != qid]
        self.dirty = True

    # -- view ----------------------------------------------------------------------
    def view(self, char):
        c = self.char(char)
        held, has_inv = self.held(char)
        out = []
        for q in self.all_quests():
            ticks = set(c["ticks"].get(q["id"], []))
            items = []
            got = 0
            for i, it in enumerate(q["items"]):
                h = held.get(_k(it["n"]), 0)
                need = it.get("q", 1)
                manual = i in ticks
                ok = manual or h >= need
                got += ok
                items.append(dict(it, idx=i, held=h, manual=manual, ok=ok))
            reward_seen = bool(q.get("reward")) and held.get(_k(q["reward"]), 0) > 0
            done = q["id"] in c["done"] or reward_seen
            out.append({"id": q["id"], "name": q["name"], "cls": q["cls"], "kind": q.get("kind", ""),
                        "reward": q.get("reward", ""), "giver": q.get("giver", ""), "level": q.get("level", ""),
                        "wiki": q.get("wiki", ""), "notes": q.get("notes", ""), "custom": q.get("custom", False),
                        "era": q.get("era", ""), "banner": q.get("banner", ""),
                        "items": items, "got": got, "total": len(items), "done": done,
                        "done_how": "manual" if q["id"] in c["done"] else ("reward seen" if reward_seen else None)})
        return {"char": char, "quests": out, "classes": D.CLASSES, "my_classes": c["classes"],
                "has_inventory": has_inv,
                "categories": {cl: D.class_category(cl) for cl in D.CLASSES}}


# ---------------------------------------------------------------------------- wiki import
def _api(params, opener=None):
    params = dict(params, format="json", formatversion="2")
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "EQLAssistant/1.0 (quest importer)"})
    with (opener or urllib.request.urlopen)(req, timeout=15) as r:
        return json.load(r)


def page_title(text):
    """Accept a page title or any eqlwiki URL."""
    text = text.strip()
    if text.startswith("http"):
        u = urllib.parse.urlparse(text)
        qs = urllib.parse.parse_qs(u.query)
        if "title" in qs:
            text = qs["title"][0]
        else:
            text = urllib.parse.unquote(u.path.rsplit("/", 1)[-1])
    return text.replace("_", " ")


def import_from_wiki(page, opener=None):
    """Read a quest page from eqlwiki.com and return the item pages it links to.

    Uses the standard MediaWiki API: the page's links, then keeps only links
    whose pages are in Category:Items (NPCs, zones etc. are dropped). The
    reward and some hand-in items will be in the list too; untick what you
    don't need before saving.
    """
    title = page_title(page)
    p = _api({"action": "parse", "page": title, "prop": "links|categories|displaytitle", "redirects": 1}, opener)
    if "error" in p:
        raise ValueError(p["error"].get("info") or "Page not found")
    parse = p["parse"]
    links = [l["title"] for l in parse.get("links", []) if l.get("ns") == 0 and l.get("exists", True)]
    cats = [c.get("category", "").replace("_", " ") for c in parse.get("categories", [])]
    classes = [cl for cl in D.CLASSES if f"{cl} Quests" in cats or f"{cl.replace(' ', '')} Quests" in cats]
    items, seen = [], set()
    for i in range(0, len(links), 50):
        batch = links[i:i + 50]
        r = _api({"action": "query", "titles": "|".join(batch), "prop": "categories", "cllimit": "max",
                  "clcategories": "Category:Items|Category:Quest Items", "redirects": 1}, opener)
        for pg in r.get("query", {}).get("pages", []):
            if pg.get("categories") and pg["title"] not in seen:
                seen.add(pg["title"])
                quest_item = any(c["title"].endswith("Quest Items") for c in pg["categories"])
                items.append({"n": pg["title"], "quest_item": quest_item})
    order = {t: i for i, t in enumerate(links)}
    items.sort(key=lambda x: order.get(x["n"], 1e9))
    return {"title": parse.get("title", title), "url": D.WIKI + parse.get("title", title).replace(" ", "_"),
            "classes": classes, "items": items, "links": len(links)}

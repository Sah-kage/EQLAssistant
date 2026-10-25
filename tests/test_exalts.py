"""Exaltations tab.  Run: python -m unittest discover tests"""
import io
import os
import sys
import time
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eqlc import exalts as X            # noqa: E402
from eqlc.sky import SkyTracker          # noqa: E402

EXPORT = "\n".join("\t".join(r) for r in [
    ("Location", "Name", "ID", "Count", "Slots"),
    ("Ear", "Thunderforged Earring +5", "14568", "1", "10"),
    ("Ear-Slot8", "Thunderforged Earring (Exaltation)", "14568", "1", "10"),
    ("Ear", "Ivandyr's Hoop +5", "10082", "1", "10"),
    ("Ear-Slot9", "Fishbone Earring (Exaltation)", "10313", "1", "10"),
    ("Primary", "Aldryn, Blade of the Ocean +9", "27708", "1", "10"),
    ("Primary-Slot7", "Lyssa`s Darkwood Piccolo (Exaltation)", "11642", "1", "10"),
    ("Primary-Slot8", "SoulFire (Exaltation)", "5504", "1", "10"),
    ("Primary-Slot10", "Earthshaker (Exaltation)", "5667", "1", "10"),
    ("General 3", "Large Bag", "1", "1", "10"),
    ("General 3-Slot1", "Hierophant`s Crook +5", "11629", "1", "10"),
    ("General 3-Slot1-Slot10", "Hierophant`s Crook (Exaltation)", "11629", "1", "10"),
    ("General 3-Slot15", "Tobrin's Mystical Eyepatch (Exaltation)", "11052", "1", "10"),
    ("Bank13-Slot10", "Lyssa`s Darkwood Piccolo +1", "11642", "1", "10"),
    ("Bank13-Slot10-Slot7", "Lyssa`s Darkwood Piccolo (Exaltation)", "11642", "1", "10"),
]) + "\n\nKeyRing\tName\tID\t\nAugmentation\tLute (Exaltation)\t13011\nActivated\tDark Cloak of the Sky (Exaltation)\t27731\n" \
    "Equipment\tSoulFire +2\t5504\n"

PAGES = {   # what the item boxes on eqlwiki.com read like
    "SoulFire": "MAGIC ITEM LORE ITEM NO DROP<br>Slot: PRIMARY<br>Effect: Promised Renewal (Any Slot/Can Equip, Casting Time: Instant) at Level 40<br>Class: PAL<br>Race: ALL",
    "Fishbone_Earring": "<div>Slot: EAR<br>Effect: Enduring Breath (Worn)<br>Class: ALL<br>Race: ALL</div>",
    "Lyssa's_Darkwood_Piccolo": "<table><tr><td>Slot:</td><td>PRIMARY SECONDARY</td></tr><tr><td>Wind Instruments: 30%</td></tr><tr><td>Class: BRD</td></tr></table>",
    "Lute": "Slot: PRIMARY SECONDARY<br>Stringed Instruments: 20%<br>Class: BRD<br>Race: ALL",
    "Earthshaker": "Slot: PRIMARY<br>Effect: Earthquake (Combat) at Level 50<br>Class: WAR PAL SHD CLR<br>Race: ALL",
}


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


def opener(req, timeout=None):
    title = req.full_url.rsplit("/", 1)[-1]
    from urllib.parse import unquote
    page = PAGES.get(unquote(title))
    if page is None:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
    return Resp(("<html><body>" + page + "</body></html>").encode())


class ExaltTests(unittest.TestCase):
    def test_parse_export(self):
        rows = {(r["name"], r["location"]): r for r in X.exaltations(EXPORT)}
        self.assertEqual(len(rows), 10)
        r = rows[("Fishbone Earring", "Ear-Slot9")]
        self.assertEqual((r["installed_in"], r["kind"], r["place"]), ("Ivandyr's Hoop +5", "Worn", "Worn"))
        self.assertEqual(rows[("Thunderforged Earring", "Ear-Slot8")]["installed_in"], "Thunderforged Earring +5")
        self.assertEqual(rows[("SoulFire", "Primary-Slot8")]["kind"], "Click")
        self.assertEqual(rows[("Earthshaker", "Primary-Slot10")]["kind"], "Proc")
        r = rows[("Hierophant`s Crook", "General 3-Slot1-Slot10")]
        self.assertEqual((r["installed_in"], r["place"]), ("Hierophant`s Crook +5", "Bags"))
        r = rows[("Tobrin's Mystical Eyepatch", "General 3-Slot15")]
        self.assertEqual((r["installed_in"], r["kind"], r["place"]), (None, None, "Bags"))      # loose in a bag
        self.assertEqual(rows[("Lyssa`s Darkwood Piccolo", "Bank13-Slot10-Slot7")]["place"], "Bank")
        self.assertEqual(rows[("Lute", "Key ring (Augmentation)")]["place"], "Key ring")
        self.assertEqual(rows[("Dark Cloak of the Sky", "Key ring (Activated)")]["kind"], "Click")

    def test_items_with_exaltations(self):
        extra = EXPORT.replace("\n\nKeyRing", "\n" + "\n".join("\t".join(r) for r in [
            ("Bank7", "Dove Slippers +4", "20798", "1", "10"),            # an item straight in a bank slot
            ("Bank7-Slot7", "Empty", "0", "0", "0"),
            ("Bank7-Slot8", "Empty", "0", "0", "0"),
            ("Bank7-Slot9", "Fishbone Earring (Exaltation)", "10313", "1", "10"),
            ("Bank9", "Storage Trunk", "177752", "1", "50"),             # a bank chest: its slots hold items
            ("Bank9-Slot7", "Moonstone Ring (Exaltation)", "10150", "1", "10"),
            ("SharedBank2", "Belt of Virtue +3", "1", "1", "10"),
            ("SharedBank2-Slot7", "Brell's Girdle (Exaltation)", "2742", "1", "10"),
        ]) + "\n\nKeyRing")
        d = X.parse_export(extra)
        ex = {(r["name"], r["location"]): r for r in d["exalts"]}
        self.assertEqual(ex[("Fishbone Earring", "Bank7-Slot9")]["installed_in"], "Dove Slippers +4")
        self.assertEqual(ex[("Moonstone Ring", "Bank9-Slot7")]["installed_in"], None)     # loose in the chest
        self.assertEqual(ex[("Brell's Girdle", "SharedBank2-Slot7")]["place"], "Shared bank")
        items = {i["name"]: i for i in d["items"]}
        self.assertEqual(set(items), {"Thunderforged Earring +5", "Ivandyr's Hoop +5", "Aldryn, Blade of the Ocean +9",
                                      "Hierophant`s Crook +5", "Lyssa`s Darkwood Piccolo +1", "Dove Slippers +4",
                                      "Belt of Virtue +3"})
        a = items["Aldryn, Blade of the Ocean +9"]["slots"]
        self.assertEqual((a["Focus"], a["Click"], a["Worn"], a["Proc"]),
                         ("Lyssa`s Darkwood Piccolo", "SoulFire", None, "Earthshaker"))
        self.assertEqual(items["Dove Slippers +4"]["slots"], {"Focus": "", "Click": "", "Worn": "Fishbone Earring", "Proc": None})
        self.assertEqual((items["Dove Slippers +4"]["place"], items["Belt of Virtue +3"]["place"]), ("Bank", "Shared bank"))
        sky = SkyTracker({})
        sky.load_inventory_text("Me_x", extra, 1000)
        v = X.Exalts({}, sky, lambda c: None, opener).view("Me_x", fetch=False)
        dove = [i for i in v["items"] if i["name"] == "Dove Slippers +4"][0]
        self.assertEqual((dove["free"], dove["slots"]["Worn"]["name"]), (2, "Fishbone Earring"))
        self.assertEqual([i["place"] for i in v["items"]][:1], ["Worn"])                # worn first, then bags, bank

    def test_item_pages(self):
        p = X.parse_item(X.html_to_text(PAGES["Lyssa's_Darkwood_Piccolo"]))
        self.assertEqual((p["slots"], p["classes"], list(p["effects"])), (["Primary", "Secondary"], ["Bard"], ["Focus"]))
        self.assertEqual(X.parse_item(X.html_to_text(PAGES["Earthshaker"]))["classes"],
                         ["Warrior", "Paladin", "Shadow Knight", "Cleric"])
        self.assertIsNone(X.parse_item("Just some text about a quest."))
        info = X.fetch_item("Lyssa`s Darkwood Piccolo", opener)          # backtick -> apostrophe page name
        self.assertEqual(info["title"], "Lyssa's Darkwood Piccolo")
        self.assertTrue(X.fetch_item("Nothing Like This", opener)["missing"])

    def test_view_by_slot(self):
        sky = SkyTracker({})
        sky.load_inventory_text("Me_x", EXPORT, 1000)
        ex = X.Exalts({}, sky, lambda c: ["Bard", "Rogue", "Wizard"], opener)
        v = ex.view("Me_x")
        self.assertEqual(v["count"], 10)
        for _ in range(100):                                             # lookups run in the background
            if not ex.busy:
                break
            time.sleep(0.05)
        v = ex.view("Me_x")
        slots = [s["slot"] for s in v["sections"]]
        self.assertEqual(slots[:3], ["Ear", "Primary", "Secondary"])     # in equipment order
        prim = {(r["name"], r["location"]): r for r in v["sections"][1]["rows"]}
        sf = prim[("SoulFire", "Primary-Slot8")]
        self.assertEqual((sf["classes"], sf["usable"], sf["slot_from"]), (["Paladin"], False, "wiki"))
        self.assertEqual(sf["effect"], ["Promised Renewal"])
        self.assertEqual(prim[("Earthshaker", "Primary-Slot10")]["effect"], ["Earthquake"])
        pic = prim[("Lyssa`s Darkwood Piccolo", "Primary-Slot7")]
        self.assertEqual((pic["usable"], pic["also"], pic["effect"]), (True, ["Secondary"], ["Wind Instruments: 30%"]))
        sec = {r["name"] for r in v["sections"][2]["rows"]}
        self.assertIn("Lute", sec)                                       # fits Primary and Secondary: listed in both
        lute = [r for r in v["sections"][1]["rows"] if r["name"] == "Lute"][0]
        self.assertEqual(lute["kind"], "Focus")                         # from the item's effect: not installed
        ear = {r["name"]: r for r in v["sections"][0]["rows"]}
        self.assertEqual((ear["Fishbone Earring"]["classes"], ear["Fishbone Earring"]["effect"]), (["ALL"], ["Enduring Breath"]))
        self.assertEqual(ear["Thunderforged Earring"]["effect"], [])                   # no page: no effect known
        self.assertEqual(ear["Thunderforged Earring"]["slot_from"], "installed")      # not on the wiki: where it is
        unknown = [s for s in v["sections"] if s["slot"] == "Slot not known yet"][0]
        self.assertIn("Tobrin's Mystical Eyepatch", {r["name"] for r in unknown["rows"]})
        self.assertEqual(v["pending"], 0)


if __name__ == "__main__":
    unittest.main()

"""Run:  python -m unittest discover tests   (from the eql-assistant folder)"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.request
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eqlc.parser import parse_line, parse_msg  # noqa: E402
from eqlc.core import App                     # noqa: E402
from eqlc.server import serve                 # noqa: E402
from eqlc import sky                          # noqa: E402


class ParserTests(unittest.TestCase):
    def ev(self, msg):
        return parse_line(f"[Sun Oct 11 20:00:00 2026] {msg}")[1]

    def test_melee(self):
        e = self.ev("You slash a thunder spirit for 40 points of damage.")
        self.assertEqual((e["src"], e["tgt"], e["amt"], e["kind"]), ("You", "a thunder spirit", 40, "melee"))

    def test_modern_spell_and_crit(self):
        e = self.ev("You hit Gorgalosk for 300 points of fire damage by Ignite Blood.")
        self.assertEqual((e["kind"], e["spell"], e["amt"]), ("spell", "Ignite Blood", 300))
        e = self.ev("You crush Gorgalosk for 100 points of damage. (Critical)")
        self.assertTrue(e["crit"])

    def test_nonmelee_dot(self):
        self.assertEqual(self.ev("a bee was hit by non-melee for 80 points of damage.")["src"], "You")
        e = self.ev("a bee has taken 20 damage from your Engulfing Roots.")
        self.assertEqual((e["kind"], e["spell"]), ("dot", "Engulfing Roots"))

    def test_loot(self):
        e = self.ev("--You have looted a Light Woolen Mask from Gorgalosk's corpse.--")
        self.assertEqual((e["who"], e["item"], e["corpse"]), ("You", "Light Woolen Mask", "Gorgalosk"))
        e = self.ev("--Bobbin has looted an Efreeti War Horn.--")
        self.assertEqual((e["who"], e["item"]), ("Bobbin", "Efreeti War Horn"))

    def test_incoming(self):
        e = self.ev("Gorgalosk hits YOU for 150 points of damage.")
        self.assertEqual((e["src"], e["tgt"]), ("Gorgalosk", "YOU"))

    def test_db(self):
        self.assertEqual(len(sky.CLASSES), 16)
        self.assertEqual(sum(len(c["quests"]) for c in sky.CLASSES), 95)
        self.assertIn("feathered cape", sky.ITEMS)
        self.assertEqual(len(sky.ITEMS["feathered cape"]["uses"]), 2)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.logs = os.path.join(self.tmp, "Logs")
        os.makedirs(self.logs)
        shutil.copy(os.path.join(HERE, "sample_log.txt"), os.path.join(self.logs, "eqlog_Tester_legends.txt"))
        self.app = App(log_dir=self.logs, ddir=os.path.join(self.tmp, "data"))
        self.app.cfg["port"] = 7399

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fights_and_sky(self):
        self.app.poll()
        tr = self.app.tracker("Tester_legends")
        tr.tick(4e9)  # far future: closes the open fight
        fights = tr.list()
        self.assertEqual(len(fights), 3)
        spirit, gorga, gust = fights[2], fights[1], fights[0]
        # spirit: 40+60+120+80+20 = 320 over 20:00:05..20:00:14 -> 10s (ends at death)
        self.assertEqual(spirit["you"], 320)
        self.assertEqual(spirit["duration"], 10)
        self.assertEqual(spirit["dps"], 32.0)
        self.assertEqual(spirit["total"], 350)
        # gorga: 300+100+100 = 500 over 20:01:00..20:01:19 -> 20s
        self.assertEqual(gorga["you"], 500)
        self.assertEqual(gorga["dps"], 25.0)
        self.assertEqual(gorga["taken"], 150)
        d = tr.get(gorga["id"])
        you = [c for c in d["combatants"] if c["name"] == "You"][0]
        self.assertEqual(you["crits"], 1)
        self.assertEqual(you["spells"], {"Ignite Blood": 300})
        o = tr.overlay()
        self.assertEqual(o["avg_n"], 3)
        self.assertAlmostEqual(o["avg"], round((32 + 25 + 20) / 3, 1))

        v = self.app.sky.view("Tester_legends")
        brd = [c for c in v["classes"] if c["name"] == "Bard"][0]
        tone = brd["quests"][0]
        self.assertTrue(tone["done"])        # "You receive Mask of Song"
        self.assertEqual(brd["done"], 1)
        held = self.app.sky.held_counts("Tester_legends")
        self.assertEqual(held.get("light woolen mask", 0), 0)   # consumed by turn-in
        self.assertEqual(held.get("wind rune meda", 0), 0)
        self.assertEqual(len(v["drops"]), 2)
        self.assertEqual(v["group_drops"][0]["who"], "Bobbin")

    def test_sky_reward_seen_in_log_completes_test(self):
        from eqlc.sky import reward_in_line, QUESTS
        qid = reward_in_line("[Mon Oct 12 13:00:00 2026] You receive Amulet of the Fae from Nomaad.")
        self.assertEqual(QUESTS[qid]["name"], "Test of Wind")
        for line in ["Nomaad gives you Amulet of the Fae.", "You have been given an Amulet of the Fae.",
                     "--You have looted an Amulet of the Fae.--", "Amulet of the Fae has been added to your inventory.",
                     "You have received Amulet of the Fae."]:
            self.assertEqual(reward_in_line("[Mon Oct 12 13:00:00 2026] " + line), qid, line)
        for line in ["Bobbin tells the group, 'you got the Amulet of the Fae yet?'",
                     "--Bobbin has looted an Amulet of the Fae.--",
                     "You cannot equip Amulet of the Fae.", "You say, 'Amulet of the Fae please'",
                     "You have looted a Amulet of Woven Hair."]:
            self.assertIsNone(reward_in_line("[Mon Oct 12 13:00:00 2026] " + line), line)
        # live: a new line marks the test done
        path = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        self.app.poll()
        with open(path, "a") as fh:
            fh.write("[Mon Oct 12 13:00:00 2026] Nomaad gives you Amulet of the Fae.\n")
        self.app.poll()
        done = self.app.sky.char("Tester_legends")["done"]
        self.assertEqual(done[qid]["how"], "log")

    def test_sky_reward_in_old_history(self):
        from eqlc.sky import reward_in_line
        path = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        with open(path, "a") as fh:
            fh.write("[Sun Oct 04 20:00:00 2026] You receive Amulet of the Fae from Nomaad.\n")
        qid = reward_in_line("You receive Amulet of the Fae.")
        self.app.state["offsets"][path] = os.path.getsize(path)      # read before this version: history only
        self.app.state["history_scan"][path] = ["crawls", "raids", "factions", "ledger"]
        self.app.poll()
        for _ in range(50):
            if qid in self.app.sky.char("Tester_legends")["done"]:
                break
            time.sleep(0.05)
        self.assertEqual(self.app.sky.char("Tester_legends")["done"][qid]["how"], "history")

    def test_inventory_export_import(self):
        from eqlc.inventory import parse, char_from_filename, base_name
        text = ("Location\tName\tID\tCount\tSlots\n"
                "Primary\tAldryn, Blade of the Ocean +9\t27708\t1\t10\n"
                "Primary-Slot8\tSoulFire (Exaltation)\t5504\t1\t10\n"
                "General 1-Slot3\tMystic Ash\t14246\t57\t10\n"
                "General 2-Slot12\tStar Ruby\t10032\t13\t10\n"
                "Bank13-Slot20\tGlowing Sword Hilt\t12197\t1\t10\n"
                "Bank13-Slot30\tGlowing Sword Hilt\t12197\t1\t10\n"
                "Bank13-Slot21\tEmpty\t0\t0\t0\n"
                "General 4-Slot13\tTear of Quellious\t20805\t1\t10\n"
                "\n"
                "KeyRing\tName\tID\t\n"
                "Augmentation\tLute (Exaltation)\t13011\n"
                "Equipment\tWu's Fist of Mastery +7\t27715\n"
                "Equipment\tSoulFire +2\t5504\n")
        inv = parse(text)
        self.assertEqual(inv["counts"]["Glowing Sword Hilt"], 2)
        self.assertEqual(inv["counts"]["Mystic Ash"], 57)
        self.assertNotIn("SoulFire", inv["counts"])                 # augment / key ring: owned, not hand-in-able
        self.assertIn("SoulFire", inv["owned"])
        self.assertEqual(inv["where"]["Glowing Sword Hilt"], ["Bank"])
        self.assertEqual(inv["where"]["SoulFire"], ["Key ring", "Worn"])
        self.assertEqual((char_from_filename("Sahkage_rivervale-Inventory.txt"), base_name("Windstriker +10")),
                         ("Sahkage_rivervale", "Windstriker"))
        r = self.app.import_inventory(text, "Tester_legends-Inventory.txt", mtime=1000)
        self.assertEqual(r["char"], "Tester_legends")
        from eqlc.sky import QUESTS
        names = {QUESTS[q]["name"] for q in r["sky_ticked"]}
        self.assertTrue({"Test of Sacrifice", "Test of Fists"} <= names)     # Aldryn (worn) + Wu's Fist (key ring)
        v = {q["id"]: q for q in self.app.quests.view("Tester_legends")["quests"]}
        self.assertTrue(v["pal-soulfire"]["done"])                             # SoulFire on the key ring
        hilt = next(i for i in v["pal-soulfire"]["items"] if i["n"] == "Glowing Sword Hilt")
        self.assertEqual((hilt["held"], hilt["where"]), (2, ["Bank"]))
        with self.assertRaises(ValueError):
            self.app.import_inventory("not an export", "x.txt", char="Tester_legends")

    def test_sky_data_is_eqlwiki(self):
        from eqlc import sky_data
        self.assertEqual(len(sky_data.CLASSES), 16)
        self.assertEqual([t[0] for t in sky_data.CLASSES["Beastlord"][2]],
                         ["Test of Aviak", "Test of Azarack", "Test of Claw", "Test of Harpy", "Test of Wind"])
        self.assertTrue(all(u.startswith("https://eqlwiki.com/") for u in sky_data.PAGES.values()))

    def test_incremental_and_inventory(self):
        self.app.poll()
        path = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        with open(path, "a") as fh:
            fh.write("[Sun Oct 11 20:05:00 2026] --You have looted a Feathered Cape from Gorgalosk's corpse.--\n")
        self.app.poll()
        self.assertEqual(self.app.sky.held_counts("Tester_legends").get("feathered cape"), 1)
        mag = [c for c in self.app.sky.view("Tester_legends")["classes"] if c["name"] == "Magician"][0]
        self.assertEqual(mag["quests"][0]["items"][1]["held"], 1)
        # inventory export showing a reward -> quest done
        with open(os.path.join(self.tmp, "Tester_legends-Inventory.txt"), "w") as fh:
            fh.write("Location\tName\tID\tCount\tSlots\nGeneral1\tWind Rune Lena\t1\t2\t0\n"
                     "Waist\tGirdle of Faith\t2\t1\t0\n")
        self.app.poll()
        held = self.app.sky.held_counts("Tester_legends")
        self.assertEqual(held.get("wind rune lena"), 2)
        self.assertIn("PAL:Test of Spirit", self.app.sky.char("Tester_legends")["done"])
        # state persists
        self.app.save_state(force=True)
        app2 = App(log_dir=self.logs, ddir=self.app.ddir)
        self.assertIn("PAL:Test of Spirit", app2.sky.char("Tester_legends")["done"])
        app2.poll()   # resumes from saved offset: no duplicate loot
        self.assertEqual(len(app2.sky.char("Tester_legends")["loot"]), 3)

    def test_motes(self):
        path = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        with open(path, "a") as fh:     # looted before the app was opened: must NOT be counted
            fh.write("[Sun Oct 11 20:04:00 2026] --You have looted 9 Motes of Lesser Potential from a bat.--\n")
        self.app.motes.session_start = time.mktime((2026, 10, 11, 20, 5, 0, 0, 0, -1))
        self.app.poll()
        self.assertEqual(self.app.motes.view("Tester_legends")["count"], 0)
        with open(path, "a") as fh:
            fh.write("[Sun Oct 11 20:06:00 2026] --You have looted a Mote of Lesser Potential from a bat.--\n"
                     "[Sun Oct 11 20:06:01 2026] --You have looted 4 Motes of Major Potential from a bat.--\n"
                     "[Sun Oct 11 20:06:02 2026] --Bobbin has looted 3 Motes of Lesser Potential from a bat.--\n")
        self.app.poll()
        v = self.app.motes.view("Tester_legends")
        self.assertEqual(v["count"], 5)
        self.assertNotIn("reset_at", v)
        # a new session (app reopened) starts from 0, even with the same saved state
        self.app.save_state(force=True)
        app2 = App(log_dir=self.logs, ddir=self.app.ddir)
        app2.poll()
        self.assertEqual(app2.motes.view("Tester_legends")["count"], 0)
        self.assertNotIn("motes", app2.state)

    def test_mote_tiers(self):
        from eqlc.motes import MoteCounter
        mc = MoteCounter(now=0)
        for line in ("--You have looted 4 Motes of Lesser Potential from a bat.--",
                     "--You have looted a Mote of Major Potential from a bat.--",
                     "--You have looted a Mote of Potential from a bat.--",
                     "--You have looted 2 motes of lesser potential.--"):
            mc.process_line("A", 10, line)
        v = mc.view("A", now=3600)
        self.assertEqual(v["count"], 8)
        self.assertEqual(v["per_hour"], 8.0)
        self.assertEqual({t["tier"]: t["count"] for t in v["tiers"]}, {"potential": 1, "lesser": 6, "major": 1})
        self.assertEqual([t["tier"] for t in v["tiers"]], ["potential", "lesser", "major"])

    def test_data_dir_migrates_old_name(self):
        import tempfile
        from eqlc import core
        base = tempfile.mkdtemp()
        os.makedirs(os.path.join(base, "EQLCompanion"))
        with open(os.path.join(base, "EQLCompanion", "state.json"), "w") as fh:
            fh.write("{}")
        old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = base
        try:
            d = core.data_dir()
        finally:
            if old is None:
                os.environ.pop("APPDATA")
            else:
                os.environ["APPDATA"] = old
        self.assertEqual(os.path.basename(d), "EQLAssistant")
        self.assertTrue(os.path.exists(os.path.join(d, "state.json")))
        self.assertFalse(os.path.exists(os.path.join(base, "EQLCompanion")))

    def test_wind_runes_currency(self):
        from eqlc.sky import SkyTracker, rune_in_line
        T = "[Mon Oct 12 14:00:00 2026] "
        self.assertEqual(rune_in_line(T + "You receive 2 Wind Rune Azia."), ("Wind Rune Azia", 2))
        self.assertEqual(rune_in_line(T + "You have gained a Wind Rune Beza."), ("Wind Rune Beza", 1))
        self.assertEqual(rune_in_line(T + "Wind Rune Caza x3 has been added to your currency."), ("Wind Rune Caza", 3))
        self.assertEqual(rune_in_line(T + "1 Wind Rune Dena added to your alternate currency."), ("Wind Rune Dena", 1))
        for line in ["--You have looted a Wind Rune Azia from a spiroc.--",       # counted as loot already
                     "Bobbin tells the group, 'You receive 2 Wind Rune Azia'",
                     "You receive 2 Wind Rune Bogus."]:
            self.assertIsNone(rune_in_line(T + line), line)
        st = {}
        sky = SkyTracker(st)
        sky.process("A", 100, parse_msg("--You have looted a Wind Rune Azia from a spiroc.--"))
        sky.process_line("A", 101, T + "Wind Rune Azia has been added to your currency.")   # same pickup
        sky.process_line("A", 200, T + "You receive 2 Wind Rune Beza.")
        held = sky.held_counts("A")
        self.assertEqual((held.get("wind rune azia"), held.get("wind rune beza")), (1, 2))
        # an inventory export (which has no currency) doesn't wipe rune counts
        sky.load_inventory_text("A", "Location\tName\tID\tCount\tSlots\nGeneral 1\tBread\t1\t1\t10\n", 300, "x")
        self.assertEqual(sky.held_counts("A").get("wind rune beza"), 2)
        # counts typed from the Currency tab become the base; later pickups add on
        sky.set_currency("A", {"Wind Rune Beza": 5, "Kala": 1, "Nope": 3}, t=400)
        sky.process_line("A", 500, T + "You receive a Wind Rune Kala.")
        held = sky.held_counts("A")
        self.assertEqual((held.get("wind rune beza"), held.get("wind rune kala"), held.get("wind rune azia")), (5, 2, None))
        self.assertEqual(len(sky.view("A")["runes"]), 15)

    def test_race_unlocks(self):
        from eqlc.factions import Factions
        from eqlc.races import Races, fkey
        from eqlc import races_data
        self.assertEqual(len(races_data.RACES), 15)
        for r in races_data.RACES:
            self.assertTrue(r["wiki"].startswith("https://eqlwiki.com/"), r["name"])
        self.assertEqual(fkey("The Freeport Militia"), fkey("Freeport Militia"))
        self.assertEqual(fkey("King Ak'Anon (Faction)"), fkey("King Ak`Anon"))
        st = {}
        fa = Factions(st)
        races = Races(st, fa)
        for who, f in [("A", "Coalition of Tradefolk"), ("B", "Freeport Militia"), ("A", "Knights of Truth"),
                       ("A", "Da Bashers")]:
            fa.process(who, 100, parse_msg(f"Your faction standing with {f} could not possibly get any better."))
        fa.process("A", 101, parse_msg("Your faction standing with Grobb Merchants has been adjusted by 5."))
        v = {r["name"]: r for r in races.view("A")["races"]}
        self.assertTrue(v["Human"]["unlocked"])                       # Freeport set, maxed across two characters
        self.assertEqual(v["Human"]["how"], "factions maxed")
        self.assertTrue(v["Half-Elf"]["unlocked"])                    # via Human
        self.assertFalse(v["Troll"]["unlocked"])
        self.assertEqual(v["Troll"]["progress"], [1, 3])
        gm = next(q for q in v["Troll"]["groups"][0]["reqs"] if q["faction"] == "Grobb Merchants")
        self.assertEqual((gm["done"], gm["seen"], gm["net"]), (False, True, 5))
        # Kerran: task steps
        for s in [s[0] for s in races_data.RACES[11]["unlock"]["task"]["steps"]]:
            races.set_step("A", s, True)
        v = {r["name"]: r for r in races.view("A")["races"]}
        self.assertEqual((v["Kerran"]["unlocked"], v["Kerran"]["how"]), (True, "task done"))
        races.set_unlocked("A", "Ogre", True)
        self.assertEqual(races.view("A")["races"][12]["how"], "manual")
        with self.assertRaises(ValueError):
            races.set_unlocked("A", "Vah Shir", True)

    def test_characters_are_per_server(self):
        # the same name on two servers: two separate characters, sharing nothing
        p2 = os.path.join(self.logs, "eqlog_Tester_paineel.txt")
        with open(p2, "w") as fh:
            fh.write("[Sun Oct 11 20:00:00 2026] Welcome to EverQuest!\n")
        self.app.poll()
        p1 = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        with open(p2, "a") as fh:
            fh.write("[Sun Oct 11 20:06:00 2026] --You have looted a Feathered Cape from a harpy.--\n"
                     "[Sun Oct 11 20:06:01 2026] Your faction standing with Heretics has been adjusted by 5.\n")
        self.app.poll()
        self.assertEqual(self.app.sky.held_counts("Tester_paineel").get("feathered cape"), 1)
        self.assertIsNone(self.app.sky.held_counts("Tester_legends").get("feathered cape"))
        self.assertEqual([f["name"] for f in self.app.factions.view("Tester_paineel")["factions"]], ["Heretics"])
        self.assertNotIn("Heretics", [f["name"] for f in self.app.factions.view("Tester_legends")["factions"]])
        self.app.races.set_unlocked("Tester_paineel", "Ogre", True)
        races = lambda c: {r["name"]: r["unlocked"] for r in self.app.races.view(c)["races"]}
        self.assertTrue(races("Tester_paineel")["Ogre"])
        self.assertFalse(races("Tester_legends")["Ogre"])
        self.assertTrue(os.path.exists(p1))

    def test_migrate_to_per_server(self):
        from eqlc.core import App
        ddir = os.path.join(self.tmp, "old")
        os.makedirs(ddir)
        old = {"offsets": {}, "sky": {"Tester": {"loot": [], "done": {"WAR:Test of Skill": {"t": 1, "how": "manual"}},
                                                 "unlocked": [], "inventory": None}},
               "quests": {"Tester": {"ticks": {}, "done": {}, "classes": ["Wizard"]}},
               "crawls": {"runs": [{"id": 1, "char": "Tester", "zone": "Unrest", "raw": "", "status": "done"}],
                          "active": {}},
               "raid_kills": [{"t": 1, "boss": "Lord Nagafen", "char": "Tester"}],
               "races": {"unlocked": {"Ogre": {"t": 1, "how": "manual"}}, "task": {}},
               "custom_quests": [{"id": "custom-1", "name": "Mine", "items": []}]}
        with open(os.path.join(ddir, "state.json"), "w") as fh:
            json.dump(old, fh)
        app = App(log_dir=self.logs, ddir=ddir)
        st = app.state
        self.assertIn("Tester_legends", st["sky"])
        self.assertNotIn("Tester", st["sky"])
        self.assertEqual(st["quests"]["Tester_legends"]["classes"], ["Wizard"])
        self.assertEqual(st["crawls"]["runs"][0]["char"], "Tester_legends")
        self.assertEqual(st["raid_kills"][0]["char"], "Tester_legends")
        self.assertIn("Ogre", st["races"]["by_server"]["legends"]["unlocked"])
        self.assertEqual(st["custom_quests"]["Tester_legends"][0]["id"], "custom-1")
        self.assertEqual(st["per_server"], 1)

    def test_overlay_settings(self):
        app = self.app
        self.assertEqual(app.overlay_look("dps"), {"alpha": 0.85, "locked": False, "scale": 1.0, "rev": 0})
        look = app.set_overlay("motes", {"alpha": 0.05, "scale": 9, "locked": True, "on": False})
        self.assertEqual((look["alpha"], look["scale"], look["locked"]), (0.2, 2.5, True))     # clamped
        self.assertFalse(app.cfg["motes_window_on_start"])
        look = app.set_overlay("motes", {"reset": True, "timers_on_overlay": False})
        self.assertEqual((look["scale"], look["rev"]), (1.0, 1))
        self.assertFalse(app.cfg["timers_on_overlay"])
        app2 = App(log_dir=self.logs, ddir=app.ddir)                                     # saved
        self.assertEqual(app2.overlay_look("motes")["rev"], 1)
        self.assertNotIn("motes_reset_hours", app2.cfg)
        with self.assertRaises(ValueError):
            app.set_overlay("nope", {})

    def test_fight_deep_dive(self):
        from eqlc.fights import FightTracker
        tr = FightTracker({"fight_timeout": 10, "min_fight_secs": 0})
        lines = ["You begin casting Ice Comet.", "You hit a gnoll for 50 points of damage.",
                 "You try to hit a gnoll, but miss!", "You try to hit a gnoll, but a gnoll parries!",
                 "a gnoll tries to hit YOU, but YOU dodge!", "a gnoll hits YOU for 10 points of damage.",
                 "Your target resisted the Ice Comet spell.", "You begin casting Ice Comet.",
                 "a gnoll was hit by non-melee for 300 points of damage.", "Your spell fizzles!",
                 "Bobbin slashes a gnoll for 40 points of damage.", "You have slain a gnoll!"]
        for i, l in enumerate(lines):
            ev = parse_msg(l)
            if ev:
                tr.process(1000 + i, ev)
        d = tr.deep("latest")
        you = next(r for r in d["friends"] if r["name"] == "You")
        self.assertEqual((you["dmg"], you["hits"], you["melee"]["swings"], you["melee"]["hit_pct"]), (350, 2, 3, 33.3))
        self.assertEqual({o["outcome"]: o["pct"] for o in you["melee"]["outcomes"]}, {"hit": 33.3, "miss": 33.3, "parry": 33.3})
        self.assertEqual([(a["name"], a["pct"]) for a in you["abilities"]], [("Ice Comet", 85.7), ("Melee", 14.3)])
        st = d["spell_totals"]
        self.assertEqual((st["casts"], st["landed"], st["resists"], st["resist_pct"], st["fizzle_pct"]), (2, 1, 1, 50.0, 50.0))
        self.assertEqual(d["defence"][0]["hit_pct"], 50.0)
        self.assertEqual(d["resisted_by"][0]["npc"], "a gnoll")
        self.assertEqual(sum(d["timeline"]["friend"]), 390)
        self.assertEqual((d["counts"]["hit"], d["counts"]["avoid"], d["counts"]["death"]), (4, 3, 1))
        self.assertIsNone(tr.deep("999"))

    def test_players_npcs_split(self):
        from eqlc.fights import FightTracker
        tr = FightTracker({"fight_timeout": 10, "min_fight_secs": 0})
        evs = [
            (0, {"type": "dmg", "src": "You", "tgt": "Gorgalosk", "amt": 100, "kind": "melee", "spell": None, "crit": False}),
            (1, {"type": "dmg", "src": "Bobbin", "tgt": "Gorgalosk", "amt": 50, "kind": "melee", "spell": None, "crit": False}),
            (2, {"type": "dmg", "src": "Gorgalosk", "tgt": "Bobbin", "amt": 70, "kind": "melee", "spell": None, "crit": False}),
            (3, {"type": "dmg", "src": "Gorgalosk", "tgt": "YOU", "amt": 30, "kind": "melee", "spell": None, "crit": False}),
            (4, {"type": "dmg", "src": "Kabober", "tgt": "Gorgalosk", "amt": 20, "kind": "melee", "spell": None, "crit": False}),
            (5, {"type": "dmg", "src": "Clericguy", "tgt": "Gorgalosk", "amt": 0, "kind": "melee", "spell": None, "crit": False}),
        ]
        tr.cfg["pet_names"] = ["Kabober"]
        tr.cfg["include_pets"] = True
        for t, e in evs:
            tr.process(t, e)
        tr.process(6, {"type": "death", "tgt": "Gorgalosk", "src": "You"})
        d = tr.get(tr.list()[0]["id"])
        players = {p["name"]: p for p in d["players"]}
        self.assertEqual(players["You"]["type"], "you")
        self.assertEqual(players["Bobbin"]["type"], "player")
        self.assertEqual(players["Kabober"]["type"], "pet")
        self.assertEqual(players["Bobbin"]["taken"], 70)
        self.assertEqual(players["You"]["taken"], 30)
        npc = d["npcs"][0]
        self.assertEqual((npc["name"], npc["taken"], npc["total"], npc["dead"]), ("Gorgalosk", 170, 100, True))
        self.assertEqual(npc["targets"][0], {"name": "Bobbin", "dmg": 70})
        sides = [e["side"] for e in d["log"]]
        self.assertEqual(sides.count("npc"), 2)
        self.assertEqual(sides[-1], "death")

    def test_timers(self):
        from eqlc.timers import Timers
        now = time.time()
        cfg = {"timers": [{"mob": "Gorgalosk", "minutes": 20, "variance": 5, "zone": ""},
                          {"mob": "a spiroc *", "minutes": 6, "zone": "Plane of Sky"}]}
        tm = Timers({}, cfg)
        self.assertIsNotNone(tm.process("A", now - 60, {"type": "death", "tgt": "Gorgalosk", "src": "You"}))
        self.assertIsNone(tm.process("A", now - 59, {"type": "death", "tgt": "Gorgalosk", "src": "You"}))  # same kill
        self.assertIsNotNone(tm.process("A", now, {"type": "death", "tgt": "a spiroc walker"}, "Plane of Sky"))
        self.assertIsNone(tm.process("A", now, {"type": "death", "tgt": "a spiroc banisher"}, "East Freeport"))
        self.assertIsNone(tm.process("A", now, {"type": "death", "tgt": "a bat"}))
        self.assertIsNone(tm.process("A", now - 3600, {"type": "death", "tgt": "Gorgalosk"}))   # long expired
        v = tm.view(now=now)
        self.assertEqual([x["mob"] for x in v], ["a spiroc walker", "Gorgalosk"])
        g = v[1]
        self.assertEqual(g["state"], "waiting")
        self.assertAlmostEqual(g["remaining"], 19 * 60, delta=1)
        self.assertEqual([(x["mob"], x["state"]) for x in tm.view(now=now + 21 * 60)], [("Gorgalosk", "window")])
        self.assertEqual(tm.view(now=now + 26 * 60)[0]["state"], "up")   # spiroc gone by now; gorga up
        self.assertEqual(tm.view(now=now + 60 * 60), [])
        # manual start for a mob without a rule needs minutes
        self.assertIsNone(tm.start_manual("Noble Dojorn"))
        self.assertIsNotNone(tm.start_manual("Noble Dojorn", minutes=30))

    def test_timers_from_log(self):
        self.app.cfg["timers"] = [{"mob": "Gorgalosk", "minutes": 100000, "variance": 0, "zone": "Plane of Sky"}]
        self.app.poll()
        v = self.app.timers.view()
        self.assertEqual(len(v), 1)
        self.assertEqual((v[0]["mob"], v[0]["zone"], v[0]["char"]), ("Gorgalosk", "Plane of Sky", "Tester_legends"))

    def _feed(self, tr, lines, start=1000):
        for i, line in enumerate(lines):
            if isinstance(line, tuple):
                t, msg = line
            else:
                t, msg = start + i * 0.5, line
            ev = parse_msg(msg)
            if ev:
                tr.process(t, ev)

    def test_misses_resists_breakdown(self):
        from eqlc.fights import FightTracker
        tr = FightTracker({"fight_timeout": 10, "min_fight_secs": 0, "avg_fights": 10})
        lines = [(997, "You begin casting Ignite Blood.")]            # cast just before the fight starts
        lines += ["You slash a bat for 50 points of damage."] * 20
        lines += ["You try to slash a bat, but miss!"] * 12
        lines += ["You try to slash a bat, but a bat parries!"] * 4
        lines += ["You try to slash a bat, but a bat ripostes!"] * 4
        lines += ["Bobbin tries to crush a bat, but a bat dodges!", "Bobbin crushes a bat for 30 points of damage."]
        lines += ["a bat tries to hit YOU, but misses!", "a bat tries to hit YOU, but YOU dodge!",
                  "a bat hits YOU for 20 points of damage.", "You resist the Screech spell!"]
        for _ in range(6):
            lines += ["You begin casting Ignite Blood.", "Your target resisted the Ignite Blood spell."]
        for _ in range(4):
            lines += ["You begin casting Ignite Blood.", "a bat was hit by non-melee for 300 points of damage."]
        lines += ["You begin casting Ignite Blood.", "Your spell is interrupted.",
                  "You begin casting Ignite Blood.", "Your spell fizzles!"]
        self._feed(tr, lines)
        tr.process(1100, {"type": "death", "tgt": "a bat", "src": "You"})
        fid = tr.list()[0]["id"]
        b = tr.breakdown(fid, "You")
        self.assertEqual(b["melee"]["swings"], 40)
        self.assertEqual(b["melee"]["counts"], {"hit": 20, "miss": 12, "parry": 4, "riposte": 4})
        self.assertEqual(b["melee"]["accuracy"], 50.0)
        self.assertEqual(b["defense"]["counts"], {"hit": 1, "miss": 1, "dodge": 1})
        self.assertEqual(b["you_resisted"], {"Screech": 1})
        sp = {s["name"]: s for s in b["spells"]}["Ignite Blood"]
        # 1 pre-fight cast + 6 + 4 + 1 + 1 = 13 casts; non-melee lines named after the last cast
        self.assertEqual((sp["casts"], sp["resists"], sp["landed"], sp["interrupts"], sp["fizzles"], sp["damage"]),
                         (13, 6, 4, 1, 1, 1200))
        self.assertEqual(b["resisted_by"], {"a bat": {"Ignite Blood": 6}})
        titles = " | ".join(t["title"] for t in b["tips"])
        self.assertIn("Missing 30% of melee swings", titles)
        self.assertIn("parried, blocked or riposted", titles)
        self.assertIn("riposted you 4 times", titles)
        self.assertIn("Ignite Blood was resisted", titles)
        # warnings come first
        self.assertEqual(b["tips"][0]["level"], "warn")
        # NPC side
        n = tr.breakdown(fid, "a bat", "npc")
        self.assertEqual(n["defense"]["counts"]["hit"], 21)        # 20 yours + Bobbin's hit
        self.assertEqual(n["melee"]["counts"], {"hit": 1, "miss": 1, "dodge": 1})
        self.assertIn("resisted your spells 6 times", " | ".join(t["title"] for t in n["tips"]))
        # combat log carries misses and spell outcomes
        kinds = {e["kind"] for e in tr.get(fid)["log"]}
        self.assertTrue({"miss", "parry", "riposte", "resist", "fizzle", "interrupt"} <= kinds)
        # last-N scope works
        self.assertEqual(tr.breakdown("recent", "You")["fights"], 1)

    def test_good_tips(self):
        from eqlc.fights import FightTracker
        tr = FightTracker({"fight_timeout": 10, "min_fight_secs": 0})
        lines = [(1000 + i, "You slash a bat for 50 points of damage.") for i in range(40)]
        lines += [(1000.5 + i, "You try to slash a bat, but miss!") for i in range(3)]
        self._feed(tr, lines)
        b = tr.breakdown("latest", "You")
        levels = {t["title"]: t["level"] for t in b["tips"]}
        self.assertTrue(any(l == "good" and "accuracy" in t.lower() for t, l in levels.items()))
        self.assertTrue(any("uptime" in t.lower() for t in levels))

    def test_zone_parsing(self):
        z = parse_msg("You have entered The Castle of Mistmoore 4 (Refined).")
        self.assertEqual((z["zone"], z["inst_id"], z["tier"], z["level"], z["inst"]),
                         ("The Castle of Mistmoore", "4", "Refined", 4, True))
        self.assertIsNone(parse_msg("You have entered an area where levitation effects do not function."))
        self.assertFalse(parse_msg("You have entered Neriak - Commons.")["inst"])
        self.assertEqual(parse_msg("You have entered Neriak - Commons.")["zone"], "Neriak - Commons")
        self.assertEqual(parse_msg("You gain experience! (0.53%)"), {"type": "xp", "pct": 0.53})

    def _crawl_log(self, lines, t0=1_000_000):
        from eqlc.crawls import Crawls
        c = Crawls({})
        for dt_, msg in lines:
            c.process("A", t0 + dt_, parse_msg(msg), msg)
        return c

    def test_crawl_run(self):
        c = self._crawl_log([
            (-5, "You have entered Rathe Mountains."),
            (0, "Lower Guk Is now available to you."),               # zone captured, timer armed
            (10, "You have slain a rat!"),                            # not in the crawl yet: not counted
            (30, "You have entered Lower Guk 7 (Fused)."),
            (60, "You have slain a frogloth!"),                       # first kill: timer starts
            (61, "--You have looted 2 Motes of Lesser Potential from a frogloth's corpse.--"),
            (62, "You gain experience! (0.5%)"),
            (300, "a frogloth has been slain by Bobbin!"),
            (400, "You have entered Rathe Mountains."),               # gated out
            (520, "You have entered Lower Guk 7 (Fused)."),          # back in: same run
            (600, "You have been slain by a froglok tonger!"),
            (1500, "You have slain Frenzied Ghoul!"),
            (1501, "You have completed the Dungeon Crawl and earned reward loot!"),
            (1502, "You gained reward experience from the Dungeon Crawl!"),
            (1502, "You gain experience! (2.0%)"),
            (1503, "You earned a refund of your instance charge."),
            (1510, "--You have looted a Ghoulbane from Reward Chest.--"),    # timer ends
            (1511, "--You have looted 3 Motes of Greater Potential from Reward Chest.--"),
        ])
        v = c.view("A", now=1_000_000 + 2000)
        self.assertIsNone(v["current"])
        r = v["runs"][0]
        self.assertEqual((r["status"], r["zone"], r["level"], r["tier_label"], r["start_known"]),
                         ("done", "Lower Guk", 3, "D3 Fused", True))
        self.assertEqual((r["duration"], r["outside"], r["inside"], r["exits"]), (1450, 120, 1330, 1))
        self.assertEqual((r["kills"], r["deaths"], r["to_first_kill"]), (3, 1, 60))
        self.assertEqual(r["motes_tiers"], {"lesser": 2, "greater": 3})
        self.assertEqual(r["xp"], 2.5)
        self.assertTrue(r["reward_xp"])
        self.assertTrue(r["refund"])
        self.assertEqual(r["chest"], [{"item": "Ghoulbane", "qty": 1}, {"item": "Motes of Greater Potential", "qty": 3}])
        self.assertTrue(r["is_best"])
        self.assertEqual(v["bests"][0]["best"], 1450)

    def test_crawl_pb_and_abandon(self):
        c = self._crawl_log([
            (0, "Crushbone is now available to you."),
            (5, "You have entered Crushbone 3 (Refined)."),
            (10, "You have slain an orc pawn!"),
            (300, "Bobbin has looted a Rusty Axe from Reward Chest."),       # anyone's chest loot ends it
            (400, "Crushbone is now available to you."),
            (410, "You have entered Crushbone 4 (Refined)."),
            (420, "You have slain an orc pawn!"),
            (640, "--You have looted a Bone Chip from Reward Chest.--"),
            (700, "You have entered Crushbone 5 (Refined)."),         # farming: no "available" line
            (900, "You have entered Greater Faydark."),
            (900 + 31 * 60, "Befallen is now available to you."),     # >30 min later: Crushbone 5 abandoned
            (900 + 31 * 60 + 5, "You have entered Befallen 1 (Fused)."),
            (900 + 31 * 60 + 50, "This Dungeon Crawl was too easy to earn an instance recharge."),
        ])
        v = c.view("A", now=1_000_000 + 4000)
        st = [(r["zone"], r["status"], r["duration"], r["start_known"]) for r in v["runs"]]
        self.assertEqual(st[1:], [("Crushbone", "left", 200, False), ("Crushbone", "done", 220, True),
                                  ("Crushbone", "done", 290, True)])
        self.assertEqual(v["current"]["zone"], "Befallen")
        self.assertEqual(v["current"]["level"], 3)
        self.assertEqual(v["bests"][0]["zone"], "Crushbone")
        self.assertEqual((v["bests"][0]["best"], v["bests"][0]["avg"], v["bests"][0]["runs"]), (220, 255, 2))
        self.assertEqual([r["vs_best"] for r in v["runs"] if r["status"] == "done"], [0, 70])
        self.assertEqual(c._get(v["current"]["id"])["refund"], False)
        o = c.overlay("A", now=1_000_000 + 900 + 31 * 60 + 90)
        self.assertEqual((o["state"], o["zone"], o["elapsed"], o["pb"]), ("ready", "Befallen", 0, None))   # no kill yet
        c.process("A", 1_000_000 + 900 + 31 * 60 + 100, parse_msg("You have slain a skeleton!"))
        o = c.overlay("A", now=1_000_000 + 900 + 31 * 60 + 130)
        self.assertEqual((o["state"], o["elapsed"]), ("active", 30))

    def test_crawl_party_and_stop_reset(self):
        c = self._crawl_log([
            (0, "Unrest is now available to you."), (5, "You have entered Unrest 2 (Adaptive)."),
            (8, "Gobaner tells you, 'Attacking a ghoul Master.'"),          # your pet: not a player
            (10, "Gobaner hits a ghoul for 20 points of damage."),
            (12, "You have slain a ghoul!"),
            (60, "--You have looted a Gem from Reward Chest.--"),
            (100, "Unrest is now available to you."), (105, "You have entered Unrest 3 (Adaptive)."),
            (110, "Bobbin slashes a ghoul for 40 points of damage."),
            (112, "a ghoul has been slain by Bobbin!"),
            (150, "--You have looted a Gem from Reward Chest.--"),
        ])
        v = c.view("A", now=1_000_000 + 400)
        self.assertEqual([(r["party"], r["players"]) for r in v["runs"]], [("group", ["Bobbin"]), ("solo", [])])
        self.assertEqual(sorted((b["party"], b["best"]) for b in v["bests"]), [("group", 38), ("solo", 48)])
        self.assertTrue(all(r["is_best"] for r in v["runs"]))          # separate bests for solo and group
        # stop: ends the run now, kept but not "Logged live"
        c.process("A", 1_000_000 + 200, parse_msg("Unrest is now available to you."), "x")
        c.process("A", 1_000_000 + 210, parse_msg("You have slain a ghoul!"), "x")
        r = c.stop("A", now=1_000_000 + 250)
        self.assertEqual((r["status"], round(r["end"] - r["start"]), r["stopped"]), ("done", 40, True))
        self.assertTrue(any("stopped by hand" in x for x in c._summary(r, 1_000_000 + 300)["proof"]["reasons"]))
        self.assertIsNone(c.stop("A"))
        # reset: back to 0:00, waiting for the next first kill
        c.process("A", 1_000_000 + 300, parse_msg("Unrest is now available to you."), "x")
        c.process("A", 1_000_000 + 310, parse_msg("You have slain a ghoul!"), "x")
        c.reset("A", now=1_000_000 + 320)
        o = c.overlay("A", now=1_000_000 + 330)
        self.assertEqual((o["state"], o["elapsed"], o["kills"]), ("ready", 0, 0))
        c.process("A", 1_000_000 + 340, parse_msg("You have slain a ghoul!"), "x")
        self.assertEqual(c.overlay("A", now=1_000_000 + 360)["elapsed"], 20)

    def test_crawl_log_integrity(self):
        from eqlc.crawls import Crawls
        from eqlc import integrity as I
        T0 = 1_000_000

        def run(lines, lag=1.0, late_at=None, clock_skew=0.0, live=True, file_event=False):
            c = Crawls({})
            for dt_, msg in lines:
                t = T0 + dt_
                meta = None
                if live:
                    extra = 60 if late_at == dt_ else lag
                    meta = {"now": t + extra, "mono": 5000 + dt_ + (clock_skew if "Reward Chest" in msg else 0)}
                c.process("A", t, parse_msg(msg), msg, meta)
                if file_event and dt_ == 40:
                    c.file_event("A", "edited")
            return c, c.runs[-1]

        L = [(0, "Unrest is now available to you."), (10, "You have entered Unrest 2 (Adaptive)."),
             (20, "You have slain a ghoul!"), (40, "a ghoul has been slain by Bobbin!"),
             (300, "--You have looted a Gem from Reward Chest.--")]
        c, r = run(L)
        v = I.verdict(r)
        self.assertEqual(v["status"], "verified", v)
        self.assertEqual((r["proof"]["lines"], r["proof"]["late"]), (5, 0))
        self.assertEqual(c._summary(r, T0 + 400)["proof"]["status"], "verified")
        # a line written into the log a minute after its time stamp
        self.assertEqual(I.verdict(run(L, late_at=40)[1])["status"], "suspicious")
        # PC clock changed during the run: log says 280s, but 380s passed
        v = I.verdict(run(L, clock_skew=100)[1])
        self.assertEqual(v["status"], "suspicious")
        self.assertTrue(any("PC clock" in x for x in v["reasons"]))
        # log file edited while the run was going
        self.assertEqual(I.verdict(run(L, file_event=True)[1])["status"], "suspicious")
        # read from older logs: not witnessed
        self.assertEqual(I.verdict(run(L, live=False)[1])["status"], "unverified")
        # proof: the chain matches the lines; editing a line breaks it
        r = run(L)[1]
        doc = I.build_proof(r, {"duration": 280, "tier_label": "D2"}, [m for _, m in L], "test")
        doc["lines"] = ["[Mon Oct 12 13:00:%02d 2026] %s" % (i, m) for i, (_, m) in enumerate(L)]
        h = ""
        for ln in doc["lines"]:
            h = I.chain(h, ln)
        doc["chain"] = h
        doc["duration"] = 2                              # first kill at :02, chest at :04
        self.assertTrue(I.check_proof(doc)["ok"], I.check_proof(doc))
        bad = dict(doc, lines=doc["lines"][:-1] + ["[Mon Oct 12 13:00:03 2026] --You have looted a Gem from Reward Chest.--"])
        self.assertFalse(I.check_proof(bad)["ok"])
        self.assertFalse(I.check_proof({"format": "other"})["ok"])

    def test_file_watch(self):
        from eqlc.integrity import FileWatch
        path = os.path.join(self.tmp, "w.txt")
        with open(path, "w") as fh:
            fh.write("[Mon Oct 12 13:00:00 2026] one\n")
        w = FileWatch()
        w.remember(path, os.path.getsize(path))
        with open(path, "a") as fh:
            fh.write("[Mon Oct 12 13:00:01 2026] two\n")       # normal growth
        self.assertIsNone(w.check(path, 0))
        with open(path, "r+") as fh:
            fh.write("[Mon Oct 12 12:00:00 2026] one")          # rewrote something already read
        self.assertEqual(w.check(path, 0), "edited")
        with open(path, "w") as fh:
            fh.write("x\n")
        self.assertEqual(w.check(path, 0), "truncated")

    def test_crawl_fallbacks(self):
        # offered but never entered: dropped after 30 minutes
        c = self._crawl_log([(0, "Unrest is now available to you.")])
        self.assertEqual(c.overlay("A", now=1_000_000 + 60)["state"], "waiting")
        c.tick(1_000_000 + 31 * 60)
        self.assertEqual(c.view("A", now=1_000_000 + 31 * 60)["runs"], [])
        # completed but the chest was never looted: ends at the completion line once you leave
        c = self._crawl_log([
            (0, "Unrest is now available to you."),
            (20, "You have entered Unrest 2 (Adaptive)."),
            (30, "You have slain a ghoul!"),
            (500, "You have completed the Dungeon Crawl and earned reward loot!"),
            (520, "You have entered Ak'Anon."),
        ])
        c.tick(1_000_000 + 520 + 31 * 60)
        r = c.view("A", now=1_000_000 + 4000)["runs"][0]
        self.assertEqual((r["status"], r["duration"]), ("done", 470))
        # zone-in logged a moment before the "available" line: one run, timed from the "available" line
        c = self._crawl_log([
            (0, "You have entered Unrest 4 (Refined)."),
            (2, "Unrest 4 (Refined) is now available to you."),
            (10, "You have slain a ghoul!"),
            (100, "--You have looted a Gem from Reward Chest.--"),
        ])
        runs = c.view("A", now=1_000_000 + 200)["runs"]
        self.assertEqual([(r["duration"], r["start_known"], r["level"]) for r in runs], [(90, True, 4)])

    def test_crawl_kills_counted_in_real_world_orders(self):
        def kills(lines):
            c = self._crawl_log(lines)
            r = c.view("A", now=1_000_000 + 5000)["runs"][0]
            return r["kills"], r["status"], r["duration"]
        # zoned in long before the "available" line
        self.assertEqual(kills([(0, "You have entered Lower Guk 7 (Fused)."), (900, "Lower Guk is now available to you."),
                                (950, "You have slain a frogloth!"), (960, "a frogloth has been slain by Bobbin!"),
                                (1200, "--You have looted a Gem from Reward Chest.--")]), (2, "done", 250))
        # crawl zone-in line has no instance number / tier, and says "The ..."
        self.assertEqual(kills([(0, "You have entered Rathe Mountains."), (5, "Lower Guk is now available to you."),
                                (20, "You have entered The Lower Guk."), (60, "You have slain a frogloth!"),
                                (100, "--You have looted a Gem from Reward Chest.--")]), (1, "done", 40))
        # app opened mid-crawl: no zone line seen at all
        self.assertEqual(kills([(0, "Lower Guk is now available to you."), (30, "You have slain a frogloth!"),
                                (90, "--You have looted a Gem from Reward Chest.--")]), (1, "done", 60))
        # still outside in another zone: those kills don't start it
        self.assertEqual(kills([(0, "You have entered Rathe Mountains."), (5, "Lower Guk is now available to you."),
                                (10, "You have slain a griffon!"), (20, "You have entered Lower Guk 7 (Fused)."),
                                (40, "You have slain a frogloth!"),
                                (100, "--You have looted a Gem from Reward Chest.--")]), (1, "done", 60))

    def test_crawl_overlay_done_and_unknown_start(self):
        c = self._crawl_log([
            (0, "Unrest is now available to you."),
            (10, "You have entered Unrest 2 (Adaptive)."),
            (20, "You have slain a ghoul!"),
            (500, "--You have looted a Gem from Reward Chest.--"),
            (900, "Unrest is now available to you."),
            (905, "You have entered Unrest 3 (Adaptive)."),
            (925, "You have slain a ghoul!"),
            (1300, "--You have looted a Gem from Reward Chest.--"),
        ])
        o = c.overlay("A", now=1_000_000 + 1310)
        self.assertEqual((o["state"], o["elapsed"], o["pb"], o["new_pb"]), ("done", 375, 480, True))
        # chest loot with no start line seen: recorded, but not used for bests
        c2 = self._crawl_log([(10, "--You have looted a Gem from Reward Chest.--")])
        r = c2.view("A", now=1_000_000 + 20)["runs"][0]
        self.assertEqual((r["status"], r["start_known"]), ("done", False))
        self.assertEqual(c2.bests("A"), [])

    def test_crawl_history_rescan(self):
        path = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        with open(path, "w") as fh:
            fh.write("[Sun Oct 04 20:00:00 2026] Befallen Is now available to you.\n"
                     "[Sun Oct 04 20:00:20 2026] You have entered Befallen 9 (Fused).\n"
                     "[Sun Oct 04 20:00:30 2026] You have slain a skeleton!\n"
                     "[Sun Oct 04 20:12:00 2026] --You have looted a Bone Chip from Reward Chest.--\n")
        self.app.state["offsets"][path] = os.path.getsize(path)     # as if already read before the update
        self.app.poll()
        for _ in range(50):
            if any(r["status"] == "done" for r in self.app.crawls.runs):
                break
            time.sleep(0.05)
        runs = self.app.crawls.view("Tester_legends")["runs"]
        self.assertEqual([(r["zone"], r["duration"], r["kills"]) for r in runs], [("Befallen", 690, 1)])
        # rescanning again doesn't duplicate
        self.app.scan_crawl_history(path, "Tester_legends")
        self.assertEqual(len(self.app.crawls.view("Tester_legends")["runs"]), 1)

    def test_quests(self):
        from eqlc.quests import Quests
        from eqlc.sky import SkyTracker
        st = {}
        sky = SkyTracker(st)
        qs = Quests(st, sky)
        data = {q["id"]: q for q in qs.all_quests()}
        self.assertEqual({"enc-tashania", "pal-soulfire", "wiz-icecomet"} <= set(data), True)
        self.assertEqual(len([q for q in data.values() if q["kind"] == "epic"]), 15)   # no Beastlord epic on EQLWiki
        for q in data.values():                                      # built-in quests come from EQLWiki only
            self.assertTrue(q["wiki"].startswith("https://eqlwiki.com/"), q["id"])
        # every epic (and every Kunark-era quest) carries the pre-Kunark note; Classic ones don't
        for q in data.values():
            if q["kind"] == "epic" or q["era"] == "Kunark":
                self.assertEqual(q.get("banner"), "Not available pre-Kunark", q["id"])
            else:
                self.assertFalse(q.get("banner"), q["id"])
        names = {q["name"] for q in data.values()}
        for n in ["The Torrid Corruptor", "The Fiery Avenger", "Armor of Ro Quests", "Rogue Redemption",
                  "Trooper Scale Armor", "Rain Caller", "Robe of the Elements Quest"]:
            self.assertIn(n, names)
        self.assertGreater(len(data), 100)
        for q in data.values():                                   # data sanity
            self.assertTrue(q["items"] or q["kind"] == "epic", q["id"])
            self.assertTrue(set(q["cls"]) <= set(__import__("eqlc.quests_data").quests_data.CLASSES), q["id"])
            for it in q["items"]:
                self.assertIn(it["how"], ("drop", "forage", "buy", "craft", "collect", "quest", "turnin"), q["id"])
                self.assertGreaterEqual(it["q"], 1)
        for line in ["--You have looted a Glowing Sword Hilt from Xicotl's corpse.--",
                     "--You have looted 2 Drom's Champagne from a gnoll's corpse.--",
                     "You receive Testimony from Merko Quetalis."]:
            qs.process("A", 100, parse_msg(line))
        v = {q["id"]: q for q in qs.view("A")["quests"]}
        sf = {i["n"]: i for i in v["pal-soulfire"]["items"]}
        self.assertTrue(sf["Glowing Sword Hilt"]["ok"])
        self.assertTrue(sf["Testimony"]["ok"])
        self.assertEqual((sf["Drom's Champagne"]["held"], sf["Drom's Champagne"]["ok"]), (2, False))   # needs 4
        qs.tick("A", "pal-soulfire", sf["Drom's Champagne"]["idx"], True)
        v = {q["id"]: q for q in qs.view("A")["quests"]}
        self.assertEqual(v["pal-soulfire"]["got"], 3)       # hilt + testimony (log) + champagne (ticked)
        # an inventory export replaces earlier counts; later loot adds on top
        sky.char("A")["inventory"] = {"t": 200, "counts": {"glowing sword hilt": 0, "soulfire": 1}, "path": "x"}
        qs.process("A", 300, parse_msg("--You have looted a Spider Venom Sac from a spider's corpse.--"))
        v = {q["id"]: q for q in qs.view("A")["quests"]}
        sf = {i["n"]: i for i in v["pal-soulfire"]["items"]}
        self.assertFalse(sf["Glowing Sword Hilt"]["ok"])
        self.assertTrue(sf["A Spider Venom Sac"]["ok"])
        self.assertTrue(v["pal-soulfire"]["done"])                  # SoulFire (the reward) is in your inventory
        self.assertEqual(v["pal-soulfire"]["done_how"], "reward seen")
        # custom quest sees items looted before it was created
        cq = qs.save_custom("A", {"name": "My quest", "cls": ["Wizard", "Nope"], "items": [{"n": "Spider Venom Sac"}, {"n": "a spider venom sac", "q": "x"}, {"n": ""}]})
        self.assertEqual((cq["cls"], len(cq["items"]), cq["items"][1]["q"]), (["Wizard"], 2, 1))
        v = {q["id"]: q for q in qs.view("A")["quests"]}
        self.assertTrue(v[cq["id"]]["items"][1]["ok"])
        self.assertNotIn(cq["id"], {q["id"] for q in qs.view("A_otherserver")["quests"]})   # not shared
        self.assertEqual(v["war-epic"]["banner"], "Not available pre-Kunark")
        self.assertEqual(v["enc-tashania"]["banner"], "")

    def test_wiki_import(self):
        import io
        from eqlc.quests import import_from_wiki, page_title

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass

        def opener(req, timeout=None):
            url = req.full_url
            if "action=parse" in url:
                self.assertIn("page=Tarton%27s+Wheel", url)
                return Resp(json.dumps({"parse": {"title": "Tarton's Wheel", "links": [
                    {"ns": 0, "title": "Sulgar", "exists": True}, {"ns": 0, "title": "Rod of Azia", "exists": True},
                    {"ns": 0, "title": "Everfrost Peaks", "exists": True}, {"ns": 0, "title": "Spell: Ice Comet", "exists": True},
                    {"ns": 0, "title": "Missing Page", "exists": False}, {"ns": 14, "title": "Category:X"}],
                    "categories": [{"category": "Wizard_Quests"}, {"category": "Quests"}]}}).encode())
            self.assertIn("clcategories=Category%3AItems", url)
            return Resp(json.dumps({"query": {"pages": [
                {"title": "Sulgar"}, {"title": "Everfrost Peaks"},
                {"title": "Spell: Ice Comet", "categories": [{"ns": 14, "title": "Category:Items"}]},
                {"title": "Rod of Azia", "categories": [{"ns": 14, "title": "Category:Quest Items"}]}]}}).encode())

        r = import_from_wiki("https://eqlwiki.com/Tarton's_Wheel", opener)
        self.assertEqual(r["title"], "Tarton's Wheel")
        self.assertEqual(r["classes"], ["Wizard"])
        self.assertEqual([(i["n"], i["quest_item"]) for i in r["items"]], [("Rod of Azia", True), ("Spell: Ice Comet", False)])
        self.assertEqual(page_title("https://eqlwiki.com/index.php?title=Coin_of_Tash_(Tashania)&action=edit"), "Coin of Tash (Tashania)")
        for other in ("https://wiki.project1999.com/Coin_of_Tash", "wiki.project1999.com/Coin_of_Tash", "http://eqlwiki.com.evil.net/X"):
            with self.assertRaises(ValueError):
                page_title(other)

    def test_factions(self):
        from eqlc.factions import Factions, tier_for
        fa = Factions({})
        for t, msg in [(10, "You have slain a Qeynos guard!"),
                       (11, "Your faction standing with Guards of Qeynos has been adjusted by -20."),
                       (11, "Your faction standing with Bloodsabers has been adjusted by 5."),
                       (90, "Your faction standing with Guards of Qeynos has been adjusted by 3."),
                       (95, "Your faction standing with Bloodsabers could not possibly get any better."),
                       (96, "Captain Tillin glares at you threateningly -- he would probably win this fight.")]:
            fa.process("A", t, parse_msg(msg))
        v = {f["name"]: f for f in fa.view("A", now=100)["factions"]}
        g = v["Guards of Qeynos"]
        self.assertEqual((g["net"], g["ups"], g["downs"], g["hits"], g["today"]), (-17, 3, -20, 2, -17))
        self.assertEqual(g["causes"], [{"mob": "a Qeynos guard", "hits": 1, "amt": -20}])
        self.assertEqual(g["events"][0]["cause"], None)
        self.assertEqual(v["Bloodsabers"]["maxed"], "better")
        self.assertEqual(v["Bloodsabers"]["tier"], "Ally")
        fa.set_base("A", "Guards of Qeynos", 120, now=100)
        fa.process("A", 101, parse_msg("Your faction standing with Guards of Qeynos has been adjusted by -30."))
        g = {f["name"]: f for f in fa.view("A", now=102)["factions"]}["Guards of Qeynos"]
        self.assertEqual((g["estimate"], g["tier"]), (90, "Indifferently"))
        self.assertEqual(fa.view("A")["cons"][0]["tier"], "Threateningly")
        self.assertEqual([tier_for(v) for v in (1100, 1099, 0, -1, -101, -999, -1000, -1001)],
                         ["Ally", "Warmly", "Indifferently", "Apprehensively", "Dubiously", "Threateningly",
                          "Threateningly", "Ready to attack"])

    def test_raids(self):
        import calendar
        from datetime import datetime
        from eqlc.raids import Raids, BOSSES
        self.assertFalse([g for e, g, b, n in BOSSES if "Sky" in g])        # Plane of Sky isn't a raid target
        cfg = {"raid_eras": ["Classic"], "raid_extra_bosses": ["Quag Maelstrom"]}
        ra = Raids({}, cfg)
        ts = lambda s: calendar.timegm(datetime.strptime(s, "%Y-%m-%d %H:%M").timetuple())
        zone = parse_msg("You have entered Nagafen's Lair 12 (Fused).")
        self.assertIsNotNone(ra.process("A", ts("2026-10-07 20:00"), {"type": "death", "tgt": "Lord Nagafen", "src": "Bobbin"}, zone))
        self.assertIsNone(ra.process("A", ts("2026-10-07 20:00"), {"type": "death", "tgt": "Lord Nagafen", "src": None}, zone))  # dup
        ra.process("A", ts("2026-10-12 08:00"), {"type": "death", "tgt": "coercer t'vala", "src": "You"})        # backtick/case
        ra.process("A", ts("2026-10-12 08:30"), {"type": "death", "tgt": "Quag Maelstrom", "src": "You"})       # custom
        ra.process("A", ts("2026-10-06 14:00"), {"type": "death", "tgt": "Lady Vox", "src": "You"})             # before reset
        ra.process("A", ts("2026-10-12 08:00"), {"type": "death", "tgt": "a gnoll", "src": "You"})
        v = ra.view("A", now=ts("2026-10-12 09:22"))
        killed = {b["boss"]: b for g in v["groups"] for b in g["bosses"] if b["killed"]}
        self.assertEqual(set(killed), {"Lord Nagafen", "Coercer T`vala", "Quag Maelstrom"})
        self.assertEqual(killed["Lord Nagafen"]["levels"], [3])
        self.assertEqual(killed["Lord Nagafen"]["repeat_at"], 0)                    # 18h passed
        self.assertGreater(killed["Quag Maelstrom"]["repeat_at"], ts("2026-10-12 09:22"))
        self.assertEqual(v["start"], ts("2026-10-06 15:00"))
        self.assertEqual(v["next_reset"], ts("2026-10-13 15:00"))
        self.assertNotIn("Kunark", {g["era"] for g in v["groups"]})
        last = ra.view("A", week=1, now=ts("2026-10-12 09:22"))
        self.assertEqual([b["boss"] for g in last["groups"] for b in g["bosses"] if b["killed"]], ["Lady Vox"])

    def test_history_scan_all(self):
        path = os.path.join(self.logs, "eqlog_Tester_legends.txt")
        with open(path, "w") as fh:
            fh.write("[Sun Oct 04 20:00:00 2026] You have entered Nagafen's Lair 3 (Refined).\n"
                     "[Sun Oct 04 20:10:00 2026] Lord Nagafen has been slain by Bobbin!\n"
                     "[Sun Oct 04 20:10:01 2026] Your faction standing with Kobolds of Sol has been adjusted by 7.\n"
                     "[Sun Oct 04 20:11:00 2026] --You have looted a Glowing Sword Hilt from a chest.--\n")
        self.app.state["offsets"][path] = os.path.getsize(path)
        self.app.poll()
        for _ in range(60):
            if self.app.raids.kills and self.app.quests.ledger.get("Tester_legends"):
                break
            time.sleep(0.05)
        self.assertEqual([(k["boss"], k["level"]) for k in self.app.raids.kills], [("Lord Nagafen", 4)])
        self.assertEqual(self.app.factions.view("Tester_legends")["factions"][0]["net"], 7)
        self.assertEqual(self.app.quests.ledger["Tester_legends"][0][1], "Glowing Sword Hilt")
        # new lines are tracked live too
        with open(path, "a") as fh:
            fh.write("[Sun Oct 11 21:00:00 2026] Your faction standing with Kobolds of Sol has been adjusted by -2.\n")
        self.app.poll()
        self.assertEqual(self.app.factions.view("Tester_legends")["factions"][0]["net"], 5)
        # scanning is one-off per log for additive data
        self.app.files.clear()
        self.app.poll()
        time.sleep(0.3)
        self.assertEqual(self.app.factions.view("Tester_legends")["factions"][0]["net"], 5)

    def test_http(self):
        srv = serve(self.app)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            self.app.poll()
            base = "http://127.0.0.1:7399"
            for p in ("/api/overlay", "/api/fights", "/api/sky", "/api/settings", "/", "/app.js",
                      "/api/quests", "/api/factions", "/api/raids", "/api/raids?week=1", "/api/crawls", "/api/timers"):
                with urllib.request.urlopen(base + p) as r:
                    self.assertEqual(r.status, 200, p)
            req = urllib.request.Request(base + "/api/sky/done", method="POST",
                                         data=json.dumps({"char": "Tester_legends", "id": "WAR:Test of Skill", "done": True}).encode())
            with urllib.request.urlopen(req) as r:
                self.assertEqual(json.load(r)["ok"], True)
            with urllib.request.urlopen(base + "/api/sky?char=Tester_legends") as r:
                v = json.load(r)
            war = [c for c in v["classes"] if c["name"] == "Warrior"][0]
            self.assertEqual(war["done"], 1)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()

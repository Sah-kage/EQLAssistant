"""Buff / debuff timers.  Run: python -m unittest discover tests"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eqlc.parser import parse_msg                        # noqa: E402
from eqlc.buffs import Buffs, SpellBook, duration_ticks  # noqa: E402
from eqlc.core import App                                # noqa: E402

T0 = 1_000_000


def feed(b, lines, char="Me_x", t0=T0):
    for dt_, msg in lines:
        b.process(char, t0 + dt_, parse_msg(msg), msg)


def make(level=30):
    b = Buffs({})
    b.level_of = lambda char: level
    return b


class BuffTests(unittest.TestCase):
    def test_duration_formulas(self):
        self.assertEqual(duration_ticks(3, 360, 9), 270)          # Spirit of Wolf at 9: level x 30
        self.assertEqual(duration_ticks(3, 360, 30), 360)         # capped at its longest
        self.assertEqual(duration_ticks(11, 270, 1), 120)         # Courage: level x 30 + 90
        self.assertEqual(duration_ticks(11, 270, 9), 270)
        self.assertEqual(duration_ticks(9, 140, 30), 70)          # Tashan: level x 2 + 10
        self.assertEqual(duration_ticks(2, 8, 30), 8)             # Root
        self.assertEqual(duration_ticks(5, 3, 60), 2)             # fixed 2, capped by the spell's 3
        self.assertEqual(duration_ticks(3600, 0, 10), 3600)       # 200+: the formula is the duration

    def test_buff_on_other_self_and_group(self):
        b = make(9)
        feed(b, [(0, "You begin casting Spirit of Wolf."),
                 (4, "Bobbin is surrounded by a brief lupine aura."),
                 (10, "You begin casting Courage."),
                 (12, "You feel a rush of courage.")])
        v = b.view("Me_x", now=T0 + 20)
        got = {(r["spell"], r["target"]): r for r in v["buffs"]}
        self.assertEqual(got[("Spirit of Wolf", "Bobbin")]["secs"], 270 * 6)
        self.assertEqual(got[("Spirit of Wolf", "Bobbin")]["left"], 270 * 6 - 16)
        self.assertEqual(got[("Courage", "You")]["secs"], 270 * 6)
        # cast again on the same person: the timer starts over
        feed(b, [(100, "You begin casting Spirit of Wolf."), (104, "Bobbin is surrounded by a brief lupine aura.")])
        v = b.view("Me_x", now=T0 + 110)
        wolf = [r for r in v["buffs"] if r["spell"] == "Spirit of Wolf"]
        self.assertEqual((len(wolf), wolf[0]["left"]), (1, 270 * 6 - 6))
        # it runs out: shown as ended for a few seconds, then gone
        end = T0 + 104 + 270 * 6
        self.assertTrue([r for r in b.view("Me_x", now=end + 2)["buffs"] if r["spell"] == "Spirit of Wolf"][0]["done"])
        self.assertFalse([r for r in b.view("Me_x", now=end + 60)["buffs"] if r["spell"] == "Spirit of Wolf"])

    def test_group_spell_lands_on_several(self):
        b = make(60)
        vers = b.book.get("Pack Spirit")
        self.assertTrue(vers)
        other = vers[0]["other"]
        feed(b, [(0, "You begin casting Pack Spirit."), (14, vers[0]["you"]),
                 (14, "Bobbin" + other), (14, "Lanna" + other)])
        names = sorted(r["target"] for r in b.view("Me_x", now=T0 + 20)["buffs"])
        self.assertEqual(vers[0]["tt"], 41)                         # a group spell
        self.assertEqual(names, ["Bobbin", "Lanna", "You"])

    def test_debuffs_end_on_death_wear_off_and_resist(self):
        b = make(30)
        feed(b, [(0, "You begin casting Tashan."), (1, "A gnoll glances nervously about."),
                 (5, "You begin casting Malaise."), (8, "Your target resisted the Malaise spell."),
                 (10, "You begin casting Root."), (12, "Your Root spell fizzles!"),
                 (20, "You begin casting Snare."), (22, "An orc pawn has been ensnared.")])
        v = b.view("Me_x", now=T0 + 25)
        self.assertEqual(sorted((r["spell"], r["target"]) for r in v["debuffs"]),
                         [("Snare", "An orc pawn"), ("Tashan", "A gnoll")])
        self.assertEqual(v["recent"][0]["what"], "resisted")
        feed(b, [(30, "a gnoll has been slain by Bobbin!"), (31, "Your Snare spell has worn off of an orc pawn.")])
        v = b.view("Me_x", now=T0 + 32)
        self.assertEqual(sorted((r["spell"], r["why"]) for r in v["debuffs"]), [("Snare", "wore off"), ("Tashan", "died")])

    def test_buff_on_you_fades(self):
        b = make(30)
        feed(b, [(0, "You begin casting Spirit of Wolf."), (4, "You feel the spirit of wolf enter you."),
                 (60, "The spirit of wolf leaves you.")])
        r = b.view("Me_x", now=T0 + 61)["buffs"][0]
        self.assertEqual((r["done"], r["why"]), (True, "wore off"))

    def test_landing_only_counts_after_your_cast(self):
        b = make(30)
        feed(b, [(0, "Bobbin is surrounded by a brief lupine aura."),                     # someone else's spell
                 (5, "You begin casting Spirit of Wolf."), (60, "Bobbin is surrounded by a brief lupine aura.")])
        rows = b.view("Me_x", now=T0 + 61)["buffs"]                                      # too long after the cast:
        self.assertEqual([(r["spell"], r["target"]) for r in rows], [("Spirit of Wolf", None)])   # timed, no target
        self.assertEqual(b.view("Me_x", now=T0 + 61)["casts"][0]["result"],
                         "timed with no target (no landing message seen)")

    def test_level_from_log_and_custom_spell(self):
        b = Buffs({})
        feed(b, [(0, "You have gained a level! Welcome to level 12!")])
        self.assertEqual(b.level("Me_x"), (12, "log"))
        feed(b, [(1, "You begin casting Spirit of Wolf."), (5, "Bobbin is surrounded by a brief lupine aura.")])
        self.assertEqual(b.view("Me_x", now=T0 + 6)["buffs"][0]["secs"], 12 * 30 * 6)
        b.set_custom("Blessing of the Page", 1800)
        feed(b, [(10, "You begin casting Blessing of the Page.")])
        b.tick(now=T0 + 15)                                         # (the app calls this every second)
        r = [x for x in b.view("Me_x", now=T0 + 20)["buffs"] if x["spell"] == "Blessing of the Page"][0]
        self.assertEqual((r["secs"], r["target"]), (1800, None))
        feed(b, [(30, "You begin casting Blessing of the Page."), (31, "Your Blessing of the Page spell is interrupted.")])
        self.assertEqual(len([x for x in b.view("Me_x", now=T0 + 32)["buffs"] if x["spell"] == "Blessing of the Page"]), 1)

    def test_game_spell_file(self):
        tmp = tempfile.mkdtemp()
        try:
            logs = os.path.join(tmp, "Logs")
            os.makedirs(logs)
            self.assertIsNone(SpellBook.find_file(logs))
            rows = []
            for i in range(300):
                f = [""] * 200
                f[0], f[1] = str(1000 + i), f"Filler {i}"
                for k in (13, 16, 17, 83, 98):
                    f[k] = "0"
                for k in range(104, 119):
                    f[k] = "255"
                rows.append(f)
            f = rows[0]
            f[1], f[6], f[7], f[8] = "Legend Ward", "You feel warded.", " is warded.", "Your ward fades."
            f[13], f[16], f[17], f[83], f[98], f[110] = "3000", "3", "100", "1", "5", "20"
            with open(os.path.join(tmp, "spells_us.txt"), "w", encoding="cp1252") as fh:
                fh.write("\n".join("^".join(r) for r in rows) + "\n")
            book = SpellBook()
            self.assertTrue(book.use_game_file(logs))
            self.assertEqual(book.source, "game")
            b = Buffs({}, book=book)
            b.level_of = lambda c: 2
            feed(b, [(0, "You begin casting Legend Ward."), (3, "Bobbin is warded.")])
            self.assertEqual(b.view("Me_x", now=T0 + 4)["buffs"][0]["secs"], 60 * 6)
            self.assertTrue(book.get("Spirit of Wolf"))            # spells the game's file lacks: the built-in list
            os.remove(os.path.join(tmp, "spells_us.txt"))
            self.assertFalse(book.use_game_file(logs))
            self.assertTrue(book.get("Spirit of Wolf"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_landing_line_matched_loosely_and_casts_logged(self):
        b = make(30)
        feed(b, [(0, "You begin casting Spirit of Wolf."), (2, "Bobbin says, 'hi'"),
                 (3, "Something odd happens."),
                 (4, "bobbin is surrounded by a  brief lupine aura")])                     # case, spacing, no full stop
        v = b.view("Me_x", now=T0 + 5)
        self.assertEqual([(r["spell"], r["target"]) for r in v["buffs"]], [("Spirit of Wolf", "bobbin")])
        self.assertEqual((v["casts"][0]["result"], v["casts"][0]["after"]), ("landed on bobbin", ["Something odd happens."]))
        feed(b, [(10, "You begin casting Fire Bolt."), (14, "A gnoll was hit by non-melee for 50 points of damage.")])
        b.tick(now=T0 + 40)
        self.assertIn("not a spell that lasts", b.view("Me_x", now=T0 + 40)["casts"][0]["result"])
        feed(b, [(50, "You begin casting Root."), (51, "Your spell is interrupted.")])
        self.assertEqual(b.view("Me_x", now=T0 + 52)["casts"][0]["result"], "interrupted")

    def test_newer_spell_file_layout_is_not_used(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "Logs"))
            with open(os.path.join(tmp, "spells_us.txt"), "w") as fh:          # numbers where the messages would be
                for i in range(400):
                    fh.write("^".join([str(i), f"Spell {i}"] + [str((i * 7 + k) % 13) for k in range(230)]) + "\n")
            book = SpellBook()
            self.assertFalse(book.use_game_file(os.path.join(tmp, "Logs")))
            self.assertEqual(book.source, "built-in")
            self.assertIn("isn't in a layout", book.file_note)
            self.assertFalse(book.use_game_file(os.path.join(tmp, "Logs")))   # and stays that way
            self.assertTrue(book.get("Spirit of Wolf"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_app_overlay_and_http(self):
        tmp = tempfile.mkdtemp()
        try:
            logs = os.path.join(tmp, "Logs")
            os.makedirs(logs)
            now = time.time()
            stamp = lambda d: time.strftime("[%a %b %d %H:%M:%S %Y] ", time.localtime(now + d))
            with open(os.path.join(logs, "eqlog_Me_x.txt"), "w") as fh:
                for d, msg in [(-30, "You begin casting Spirit of Wolf."), (-26, "Bobbin is surrounded by a brief lupine aura."),
                               (-20, "You begin casting Tashan."), (-19, "A gnoll glances nervously about.")]:
                    fh.write(stamp(d) + msg + "\n")
            app = App(log_dir=logs, ddir=os.path.join(tmp, "data"))
            app.cfg["port"] = 7396
            app.cfg["buff_levels"] = {"Me_x": 20}
            app.poll()
            o = app.buffs_overlay("Me_x")
            self.assertEqual([(r["spell"], r["target"]) for r in o["rows"]],
                             [("Spirit of Wolf", "Bobbin"), ("Tashan", "A gnoll")])    # oldest first: grows downwards
            app.set_overlay("buffs", {"show": {"debuffs": False}, "alpha": 0.5})
            self.assertEqual([r["spell"] for r in app.buffs_overlay("Me_x")["rows"]], ["Spirit of Wolf"])
            self.assertEqual(app.overlay_look("buffs")["alpha"], 0.5)
            from eqlc.server import serve
            srv = serve(app)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen("http://127.0.0.1:7396/api/buffs?char=Me_x&lookup=spirit%20of%20wolf") as res:
                    v = json.load(res)
                self.assertEqual((v["level"], v["level_set"]), (20, 20))
                self.assertEqual(v["lookup"]["versions"][0]["secs"], 360 * 6)
                with urllib.request.urlopen("http://127.0.0.1:7396/api/overlay?kind=buffs&char=Me_x") as res:
                    self.assertEqual(len(json.load(res)["buffs"]["rows"]), 1)
                req = urllib.request.Request("http://127.0.0.1:7396/api/buffs/level", method="POST",
                                             data=json.dumps({"char": "Me_x", "level": 5}).encode())
                urllib.request.urlopen(req).close()
                self.assertEqual(app.buffs.level("Me_x"), (5, "set"))
                req = urllib.request.Request("http://127.0.0.1:7396/api/buffs/clear", method="POST",
                                             data=json.dumps({"char": "Me_x"}).encode())
                urllib.request.urlopen(req).close()
                self.assertEqual(app.buffs_overlay("Me_x")["rows"], [])
            finally:
                srv.shutdown()
                srv.server_close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

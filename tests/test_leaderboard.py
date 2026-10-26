"""Leaderboard submissions and class detection.  Run: python -m unittest discover tests"""
import base64
import gzip
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eqlc.parser import parse_msg                     # noqa: E402
from eqlc.core import App                             # noqa: E402
from eqlc.classes import ClassSpotter, classes_from_who, guess  # noqa: E402
from eqlc import classes_data as D                   # noqa: E402
from eqlc import snapshot as S                       # noqa: E402

T0 = time.time() - 600
RUN = [(0, "Unrest is now available to you."), (10, "You have entered Unrest 2 (Adaptive)."),
       (12, "Bobbin has joined the group."),
       (20, "You have slain a ghoul!"),
       (25, "Zed begins casting Superior Healing."),
       (26, "Zed healed you for 900 hit points by Superior Healing."),
       (30, "Zed hit a ghoul for 300 points of cold damage by Ice Comet."),
       (31, "Zed backstabs a ghoul for 120 points of damage."),
       (40, "a ghoul has been slain by Bobbin!"),
       (300, "--You have looted a Gem from Reward Chest.--")]


def feed(c, char, lines, t0=T0, live=True):
    for dt_, msg in lines:
        t = t0 + dt_
        meta = {"now": t + 1, "mono": 5000 + dt_} if live else None
        c.process(char, t, parse_msg(msg), msg, meta)


class ClassTests(unittest.TestCase):
    def test_eqlwiki_tables(self):
        self.assertEqual(len(D.CLASSES), 16)
        self.assertEqual(set(D.SPELLS_BY_CLASS) | {"Warrior", "Rogue", "Monk", "Berserker"}, set(D.CLASSES))
        self.assertEqual(D.SPELL_CLASSES["ice comet"], {"Wizard"})
        self.assertEqual(D.SPELL_CLASSES["lifetap"], {"Necromancer", "Shadow Knight"})

    def test_who(self):
        self.assertEqual(classes_from_who("Paladin/Cleric/Wizard"), ["Paladin", "Cleric", "Wizard"])
        self.assertEqual(classes_from_who("Pal/Clr/Wiz"), ["Paladin", "Cleric", "Wizard"])
        self.assertEqual(classes_from_who("Shadow Knight"), ["Shadow Knight"])
        s = ClassSpotter({})
        s.feed("Me_rivervale", 0, "[Mon Oct 12 20:00:00 2026] [60 Paladin/Cleric/Wizard] Bobbin (Halfling) <Guild>")
        s.feed("Me_rivervale", 0, "[Mon Oct 12 20:00:00 2026] AFK [55 Rogue] Tom (Gnome)")
        self.assertEqual(s.classes_of("rivervale", "Bobbin")["classes"], ["Paladin", "Cleric", "Wizard"])
        self.assertEqual(s.classes_of("rivervale", "Bobbin")["source"], "who")
        self.assertEqual(s.classes_of("rivervale", "Tom")["classes"], ["Rogue"])
        self.assertIsNone(s.who("paineel", "Bobbin"))              # nothing shared between servers

    def test_guess_from_spells(self):
        picks = guess({"spell:Ice Comet": 3, "spell:Superior Healing": 2, "skill:backstab": 1})
        names = [p["class"] for p in picks]
        self.assertEqual(names[:2], ["Wizard", "Rogue"])
        self.assertEqual(len(names), 3)
        self.assertIn(names[2], ("Cleric", "Druid", "Shaman", "Paladin"))
        self.assertTrue(picks[0]["sure"])
        # a /who with fewer than three classes is topped up from spells
        s = ClassSpotter({})
        s.feed("Me_x", 0, "[Mon Oct 12 20:00:00 2026] [60 Wizard] Zed (Gnome)")
        s.feed("Me_x", 0, "[Mon Oct 12 20:00:01 2026] Zed backstabs a ghoul for 120 points of damage.")
        self.assertEqual(s.classes_of("x", "Zed")["classes"], ["Wizard", "Rogue"])

    def test_own_classes_from_casts(self):
        s = ClassSpotter({})
        s.feed("Sahkage_rivervale", 0, "[Mon Oct 12 20:00:00 2026] You begin casting Ice Comet.")
        s.feed("Sahkage_rivervale", 0, "[Mon Oct 12 20:00:00 2026] Bobbin begins to sing a song.")
        self.assertEqual(s.classes_of("rivervale", "Sahkage")["classes"], ["Wizard"])
        self.assertEqual(s.classes_of("rivervale", "Bobbin")["classes"], ["Bard"])

    def test_run_group(self):
        from eqlc.crawls import Crawls
        c = Crawls({})
        feed(c, "Me_rivervale", RUN)
        r = c.runs[-1]
        s = c._summary(r, T0 + 400)
        self.assertEqual(s["party"], "group")
        self.assertEqual(s["players"], ["Bobbin", "Zed"])           # Zed noticed from his spells
        g = {m["name"]: m for m in s["group"]}
        self.assertTrue(g["Me"]["you"])
        self.assertEqual(g["Zed"]["classes"][:2], ["Wizard", "Rogue"])
        self.assertEqual(g["Zed"]["source"], "spells")
        self.assertEqual(g["Bobbin"]["classes"], [])


class CharmTests(unittest.TestCase):
    def run_of(self, lines, setup=()):
        from eqlc.crawls import Crawls
        c = Crawls({})
        feed(c, "Me_rivervale", list(setup), t0=T0 - 1000)
        feed(c, "Me_rivervale", [(0, "Unrest is now available to you."), (10, "You have entered Unrest 2 (Adaptive)."),
                                 (20, "You have slain a ghoul!")] + list(lines) +
             [(300, "--You have looted a Gem from Reward Chest.--")])
        return c, c._summary(c.runs[-1], T0 + 400)

    def test_charmed_mob_is_not_a_player(self):
        c, s = self.run_of([(30, "You begin casting Beguile."), (33, "Gorgalosk has been charmed."),
                            (40, "Gorgalosk hits a ghoul for 80 points of damage."),
                            (50, "a ghoul has been slain by Gorgalosk!")])
        self.assertEqual((s["party"], s["players"], s["left_out"]), ("solo", [], ["Gorgalosk"]))

    def test_undead_charm_landing(self):
        c, s = self.run_of([(30, "You begin casting Dominate Undead."), (33, "Rotfang moans."),
                            (40, "Rotfang bites a ghoul for 80 points of damage.")])
        self.assertEqual(s["players"], [])

    def test_your_pet_and_charm_break(self):
        c, s = self.run_of([(30, "Snarl hits a ghoul for 40 points of damage."),
                            (31, "Snarl tells you, 'Attacking a ghoul Master.'"),
                            (40, "Krakor slashes a ghoul for 50 points of damage."),
                            (90, "Krakor hits YOU for 120 points of damage.")])       # charm broke
        self.assertEqual((s["party"], s["players"]), ("solo", []))

    def test_mob_you_fought_before(self):
        c, s = self.run_of([(40, "Gorgalosk slashes a ghoul for 50 points of damage.")],
                           setup=[(0, "You slash Gorgalosk for 30 points of damage.")])
        self.assertEqual(s["players"], [])

    def test_real_players_stay(self):
        c, s = self.run_of([(12, "Bobbin has joined the group."), (40, "Bobbin hits a ghoul for 50 points of damage."),
                            (41, "Zed slashes a ghoul for 60 points of damage."),
                            (42, "--Zed has looted a Bone Chip.--"),
                            (50, "a ghoul hits Bobbin for 30 points of damage."),
                            (60, "Tom hits a ghoul for 10 points of damage.")])
        self.assertEqual((s["party"], s["players"]), ("group", ["Bobbin", "Tom", "Zed"]))

    def test_buttons(self):
        c, s = self.run_of([(40, "Tom hits a ghoul for 10 points of damage.")])
        r = c.runs[-1]
        c.set_player("Me_rivervale", "Tom", False)
        self.assertEqual(c._summary(r, T0 + 400)["players"], [])
        c.set_player("Me_rivervale", "Tom", True)
        self.assertEqual(c._summary(r, T0 + 400)["players"], ["Tom"])


class WhoAndLoadoutTests(unittest.TestCase):
    def test_who_formats(self):
        s = ClassSpotter({})
        lines = {"Aa": "[60 Wizard] Aaa (Gnome) <Guild>", "Bb": "[60 Pal Clr Wiz] Bbb (Gnome)",
                 "Cc": "[55 Shadow Knight Bard Rogue] Ccc (Troll)", "Dd": " AFK [60 Arch Mage] Ddd (Gnome)",
                 "Ee": "[60 Paladin / Cleric / Wizard] Eee (Human) ZONE: unrest"}
        for ln in lines.values():
            s.feed("Me_x", 0, "[Mon Oct 12 20:00:00 2026] " + ln)
        got = {n: s.who("x", n)["classes"] for n in ("Aaa", "Bbb", "Ccc", "Ddd", "Eee")}
        self.assertEqual(got, {"Aaa": ["Wizard"], "Bbb": ["Paladin", "Cleric", "Wizard"],
                               "Ccc": ["Shadow Knight", "Bard", "Rogue"], "Ddd": ["Magician"],
                               "Eee": ["Paladin", "Cleric", "Wizard"]})
        self.assertEqual(s.who("x", "aaa")["level"], 60)                      # names match whatever the case
        s.feed("Me_x", 0, "[Mon Oct 12 20:00:00 2026] [60 Stormcaller] Fff (Gnome)")
        s.feed("Me_x", 0, "[Mon Oct 12 20:00:00 2026] [ANONYMOUS] Ggg")
        self.assertEqual(s.unread("x"), ["[60 Stormcaller] Fff (Gnome)"])   # shown in Settings to report

    def test_loadout_history(self):
        s = ClassSpotter({})
        s.feed("Me_x", 1000, "[Mon Oct 12 20:00:00 2026] [60 Wizard/Cleric/Rogue] Bob (Gnome)")
        s.feed("Me_x", 90000, "[Mon Oct 12 20:00:00 2026] [60 Bard/Monk/Druid] Bob (Gnome)")
        self.assertEqual(s.classes_of("x", "Bob", at=1500)["classes"], ["Wizard", "Cleric", "Rogue"])
        self.assertEqual(s.classes_of("x", "Bob", at=95000)["classes"], ["Bard", "Monk", "Druid"])
        self.assertEqual(s.classes_of("x", "Bob")["classes"], ["Bard", "Monk", "Druid"])

    def test_settings_vs_who(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "Logs"))
            app = App(log_dir=os.path.join(tmp, "Logs"), ddir=os.path.join(tmp, "data"))
            ch = "Sahkage_rivervale"
            app.set_my_classes(ch, ["Wizard", "Cleric", "Rogue"])
            self.assertEqual(app.class_info(ch)["source"], "settings")
            app.set_my_classes(ch, ["Wizard", "Cleric", "Bard"])                # can be changed again
            self.assertEqual(app.my_classes(ch), ["Wizard", "Cleric", "Bard"])
            now = time.time() + 10
            app.crawls.classes.feed(ch, now, "[Mon Oct 12 20:00:00 2026] [60 Shaman] Sahkage (Troll)")
            info = app.class_info(ch)
            self.assertEqual(info["classes"], ["Wizard", "Cleric", "Bard"])
            self.assertIn("Shaman", info["warning"])                           # loadout changed?
            app.crawls.classes.feed(ch, now + 5, "[Mon Oct 12 20:00:00 2026] [60 Shaman/Monk/Druid] Sahkage (Troll)")
            self.assertEqual((app.my_classes(ch), app.class_info(ch)["source"]), (["Shaman", "Monk", "Druid"], "who"))
            time.sleep(0.01)
            app.set_my_classes(ch, ["Wizard", "Cleric", "Bard"])                # picked after the /who: wins
            app.cfg["leaderboard_classes_at"][ch] = now + 60
            self.assertEqual(app.my_classes(ch), ["Wizard", "Cleric", "Bard"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_fix(self):
        from eqlc.crawls import Crawls
        c = Crawls({})
        feed(c, "Me_rivervale", RUN)
        r = c.runs[-1]
        c.set_classes(r["id"], "Zed", ["Necromancer", "Rogue", "Wizard"])
        c.set_classes(r["id"], "Me", ["Bard", "Monk", "Druid"])
        g = {m["name"]: m for m in c._summary(r, T0 + 400)["group"]}
        self.assertEqual((g["Zed"]["classes"], g["Zed"]["source"]), (["Necromancer", "Rogue", "Wizard"], "run"))
        self.assertEqual(g["Me"]["classes"], ["Bard", "Monk", "Druid"])
        c.set_classes(r["id"], "Zed", [])
        self.assertEqual({m["name"]: m for m in c._summary(r, T0 + 400)["group"]}["Zed"]["source"], "spells")


class Site(BaseHTTPRequestHandler):
    got = []
    reply = {"ok": True, "id": 42, "message": "Thanks! Your run is waiting for review."}
    knows_edits = True

    def log_message(self, *a):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        got = json.loads(raw)
        Site.got.append((self.path, got))
        reply = dict(Site.reply)
        if got.get("edited") and Site.knows_edits:
            reply["edited"] = True                 # a site that stores edited runs says so
        body = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SubmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "Logs"))
        self.app = App(log_dir=os.path.join(self.tmp, "Logs"), ddir=os.path.join(self.tmp, "data"))
        self.site = ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.app.cfg["leaderboard_url"] = f"http://127.0.0.1:{self.site.server_address[1]}/"
        Site.got = []
        self.char = "Sahkage_rivervale"

    def tearDown(self):
        self.site.shutdown()
        self.site.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, n=1):
        for _ in range(100):
            if len(Site.got) >= n and not self.app._submitting:
                return
            time.sleep(0.05)

    def test_auto_submit(self):
        feed(self.app.crawls, self.char, [(-5, "[Mon Oct 12 19:59:00 2026] [60 Wizard/Cleric/Rogue] Sahkage (Gnome)")]
             + RUN)
        r = self.app.crawls.runs[-1]
        self.assertEqual(self.app.my_classes(self.char), ["Wizard", "Cleric", "Rogue"])     # from /who
        self.app.auto_submit()
        self._wait()
        self.assertEqual(len(Site.got), 1)
        path, body = Site.got[0]
        self.assertEqual(path, "/api.php?action=app_submit")
        self.assertEqual((body["format"], body["server"], body["classes"]),
                         ("eql-assistant-submission", "rivervale", ["Wizard", "Cleric", "Rogue"]))
        p = body["proof"]
        self.assertEqual((p["char"], p["server"], p["zone"], p["tier"], p["duration"]),
                         ("Sahkage", "rivervale", "Unrest", "D2 Adaptive", 280))
        self.assertEqual(p["verdict"]["status"], "verified")
        self.assertEqual(len(p["lines"]), len(RUN))
        self.assertEqual(body["party"], "group")
        self.assertEqual(body["run"]["tier"], "D2 Adaptive")
        g = {m["name"]: m for m in body["group"]}
        self.assertEqual(g["Sahkage"]["classes"], ["Wizard", "Cleric", "Rogue"])
        self.assertEqual(g["Zed"]["source"], "spells")
        try:
            import PIL  # noqa: F401
            png = base64.b64decode(body["screenshot"]["data"])
            self.assertTrue(png.startswith(S.PNG_MAGIC))
        except ImportError:
            self.assertNotIn("screenshot", body)
        self.assertEqual(r["submitted"]["id"], 42)
        self.assertTrue(r["submitted"]["auto"])
        self.app.auto_submit()                                       # never sent twice
        time.sleep(0.2)
        self.assertEqual(len(Site.got), 1)
        with self.assertRaises(ValueError):
            self.app.submit_run(r["id"])

    def test_auto_submit_rules(self):
        feed(self.app.crawls, self.char, RUN)
        r = self.app.crawls.runs[-1]
        self.app.auto_submit()
        time.sleep(0.2)
        self.assertEqual(Site.got, [])                               # no classes known yet
        self.app.set_my_classes(self.char, ["Wizard", "Cleric", "Rogue"])
        self.app.auto_submit(now=r["end"] + 1)
        time.sleep(0.2)
        self.assertEqual(Site.got, [])                               # waiting for the timer window's picture
        self.app.cfg["leaderboard_auto"] = False
        self.app.auto_submit()
        time.sleep(0.2)
        self.assertEqual(Site.got, [])
        # read from older logs: can't be sent at all
        feed(self.app.crawls, "Other_rivervale", RUN, live=False)
        old = self.app.crawls.runs[-1]
        self.app.set_my_classes("Other_rivervale", ["Wizard", "Cleric", "Rogue"])
        with self.assertRaises(ValueError) as e:
            self.app.submit_run(old["id"])
        self.assertIn("older log", str(e.exception))
        # the site says no: shown on the run, can be retried
        Site.reply = {"ok": False, "error": "Unknown dungeon"}
        try:
            with self.assertRaises(ValueError):
                self.app.submit_run(r["id"], video="https://youtu.be/x")
            self.assertEqual(r["submit_error"]["msg"], "Unknown dungeon")
        finally:
            Site.reply = {"ok": True, "id": 42, "message": "ok"}
        self.app.submit_run(r["id"])
        self.assertNotIn("submit_error", r)
        self.assertEqual(Site.got[-1][1]["video"], "")

    def test_edit_and_resubmit(self):
        feed(self.app.crawls, self.char, [(-5, "[Mon Oct 12 19:59:00 2026] [60 Wizard/Cleric/Rogue] Sahkage (Gnome)")]
             + RUN)
        r = self.app.crawls.runs[-1]
        self.app.submit_run(r["id"])
        first = Site.got[-1][1]
        self.assertEqual((first["edited"], first["edits"], first["resubmit_of"], first["submission"]),
                         (False, [], None, 1))
        with self.assertRaises(ValueError):                       # nothing changed: can't send again
            self.app.submit_run(r["id"])
        # fix a group member's classes after sending
        self.assertTrue(self.app.crawls.set_classes(r["id"], "Zed", ["Necromancer", "Rogue", "Wizard"]))
        self.assertTrue(r["changed_since_sent"])
        self.app.auto_submit()                                     # never resent by itself
        time.sleep(0.2)
        self.assertEqual(len(Site.got), 1)
        self.app.submit_run(r["id"], classes=["Wizard", "Cleric", "Bard"])       # and your own
        body = Site.got[-1][1]
        self.assertTrue(body["edited"])
        self.assertEqual((body["resubmit_of"], body["submission"], body["classes"]), (42, 2, ["Wizard", "Cleric", "Bard"]))
        edits = {e["name"]: e for e in body["edits"]}
        self.assertEqual((edits["Sahkage"]["from"], edits["Sahkage"]["to"], edits["Sahkage"]["you"]),
                         (["Wizard", "Cleric", "Rogue"], ["Wizard", "Cleric", "Bard"], True))
        self.assertEqual(edits["Zed"]["from_source"], "spells")
        self.assertTrue({g["name"]: g for g in body["group"]}["Zed"]["edited"])
        s = self.app.crawls._summary(r, time.time())
        self.assertEqual((s["submissions"], s["changed_since_sent"], s["submitted"]["edited"]), (2, False, True))
        # setting a class back to what the log shows removes the edit
        self.app.crawls.set_classes(r["id"], "Zed", [])
        self.assertNotIn("Zed", r["class_edits"])

    def test_old_site_misses_edit(self):
        feed(self.app.crawls, self.char, [(-5, "[Mon Oct 12 19:59:00 2026] [60 Wizard/Cleric/Rogue] Sahkage (Gnome)")]
             + RUN)
        r = self.app.crawls.runs[-1]
        self.app.crawls.set_classes(r["id"], "Zed", ["Necromancer", "Rogue", "Wizard"])
        Site.knows_edits = False
        try:
            self.app.submit_run(r["id"])
        finally:
            Site.knows_edits = True
        self.assertTrue(Site.got[-1][1]["edited"])
        self.assertTrue(r["submitted"]["site_missed_edit"] and r["changed_since_sent"])
        self.app.submit_run(r["id"])                               # site updated: send again, same classes
        self.assertEqual(Site.got[-1][1]["submission"], 2)
        self.assertNotIn("site_missed_edit", r["submitted"])
        self.assertFalse(r.get("changed_since_sent"))

    def test_difficulty_set_by_hand(self):
        lines = [(0, "Unrest is now available to you."), (20, "You have slain a ghoul!"),     # never zoned in: no tier
                 (300, "--You have looted a Gem from Reward Chest.--")]
        feed(self.app.crawls, self.char, lines)
        r = self.app.crawls.runs[-1]
        self.assertIsNone(r["level"])
        self.app.set_my_classes(self.char, ["Wizard", "Cleric", "Rogue"])
        with self.assertRaises(ValueError) as e:
            self.app.submit_run(r["id"])
        self.assertIn("difficulty", str(e.exception))
        with self.assertRaises(ValueError):
            self.app.crawls.set_level(r["id"], 7)
        self.app.crawls.set_level(r["id"], 2)
        s = self.app.crawls._summary(r, time.time())
        self.assertEqual((s["level"], s["tier_label"], s["level_by_hand"]), (2, "D2 Adaptive", True))
        self.assertEqual(s["proof"]["status"], "verified")                     # the time is still witnessed
        self.assertIn("difficulty was set by hand", " ".join(s["proof"]["reasons"]))
        self.app.crawls.set_level(r["id"], 3)                                  # changing your own pick is fine
        self.app.submit_run(r["id"])
        body = Site.got[-1][1]
        self.assertEqual((body["proof"]["tier"], body["run"]["tier"], body["run"]["tier_set_by_hand"]),
                         ("D3 Fused", "D3 Fused", True))
        self.assertTrue(any("by hand" in x for x in body["proof"]["verdict"]["reasons"]))
        self.app.crawls.set_level(r["id"], 2)                                  # after sending: can resend
        self.assertTrue(r["changed_since_sent"])
        # a difficulty the log shows can't be changed
        feed(self.app.crawls, self.char, RUN)
        with self.assertRaises(ValueError):
            self.app.crawls.set_level(self.app.crawls.runs[-1]["id"], 4)

    def test_snapshot_from_overlay(self):
        feed(self.app.crawls, self.char, RUN)
        r = self.app.crawls.runs[-1]
        ov = self.app.crawls.overlay(self.char, now=r["end"] + 5)
        self.assertEqual((ov["state"], ov["id"], ov["snap"]), ("done", r["id"], False))
        png = S.PNG_MAGIC + b"fake picture"
        with self.assertRaises(ValueError):
            S.save(self.app.ddir, r["id"], base64.b64encode(b"GIF89a").decode())
        S.save(self.app.ddir, r["id"], base64.b64encode(png).decode())
        self.assertTrue(self.app.crawls.overlay(self.char, now=r["end"] + 5)["snap"])
        self.app.set_my_classes(self.char, ["Wizard", "Cleric", "Rogue"])
        body = self.app.build_submission(r)
        self.assertEqual(base64.b64decode(body["screenshot"]["data"]), png)     # the window's own picture is used

    def test_render_card(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")
        png = S.render({"zone": "Unrest", "tier_label": "D2 Adaptive", "duration": 280, "kills": 2, "party": "group",
                        "players": ["Bobbin"], "end": T0}, "Sahkage")
        self.assertTrue(png.startswith(S.PNG_MAGIC))

    def test_endpoint(self):
        from eqlc.leaderboard import endpoint
        self.assertEqual(endpoint("crawl.example.com"), "https://crawl.example.com/api.php?action=app_submit")
        self.assertEqual(endpoint("https://x.com/eql/index.php"), "https://x.com/eql/api.php?action=app_submit")
        with self.assertRaises(ValueError):
            endpoint("http://x.com")
        with self.assertRaises(ValueError):
            endpoint("")

    def test_http_endpoints(self):
        from eqlc.server import serve
        self.app.cfg["port"] = 7398
        srv = serve(self.app)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            feed(self.app.crawls, self.char, RUN)
            r = self.app.crawls.runs[-1]
            base = "http://127.0.0.1:7398"

            def post(p, body):
                req = urllib.request.Request(base + p, method="POST", data=json.dumps(body).encode())
                try:
                    with urllib.request.urlopen(req) as res:
                        return json.load(res)
                except urllib.error.HTTPError as e:
                    return json.load(e)
            png = S.PNG_MAGIC + b"x"
            self.assertTrue(post("/api/crawls/snapshot", {"id": r["id"], "png": base64.b64encode(png).decode()})["ok"])
            with urllib.request.urlopen(f"{base}/api/crawls/snapshot?id={r['id']}") as res:
                self.assertEqual(res.read(), png)
            self.assertFalse(post("/api/classes/mine", {"char": self.char, "classes": ["Wizard", "Wizard", "Rogue"]})["ok"])
            self.assertTrue(post("/api/classes/mine", {"char": self.char, "classes": ["Wizard", "Cleric", "Rogue"]})["ok"])
            res = post("/api/crawls/submit", {"char": self.char, "id": r["id"]})
            self.assertTrue(res["ok"], res)
            with urllib.request.urlopen(f"{base}/api/settings?char={self.char}") as res:
                d = json.load(res)
            self.assertEqual(d["my_classes"], ["Wizard", "Cleric", "Rogue"])
            self.assertEqual(len(d["classes"]), 16)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()

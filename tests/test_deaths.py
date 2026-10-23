"""Death recap.  Run: python -m unittest discover tests"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eqlc.parser import parse_msg      # noqa: E402
from eqlc.deaths import DeathRecap     # noqa: E402
from eqlc.core import App              # noqa: E402

T0 = 1_000_000
FIGHT = [
    (-100, "a ghoul hits YOU for 99 points of damage."),                 # over a minute before: not in the recap
    (0, "a ghoul hits YOU for 120 points of damage."),
    (1, "a ghoul tries to bite YOU, but misses!"),
    (2, "Gorgalosk begins casting Fire Bolt."),
    (3, "Gorgalosk hit you for 400 points of fire damage by Fire Bolt."),
    (4, "You resist the Fire Bolt spell!"),
    (5, "Bobbin healed you for 300 (500) hit points by Light Healing."),
    (6, "You have taken 40 damage from Clinging Darkness by a ghoul."),
    (7, "You are stunned!"),
    (8, "Gorgalosk crushes YOU for 650 points of damage. (Critical)"),
    (8, "You have been slain by Gorgalosk!"),
    (8, "You died."),
]


def feed(d, lines, char="Me_x", t0=T0):
    for dt_, msg in lines:
        d.process(char, t0 + dt_, parse_msg(msg), msg, "Unrest")


class DeathTests(unittest.TestCase):
    def test_recap(self):
        d = DeathRecap({})
        feed(d, FIGHT)
        v = d.view("Me_x")
        self.assertEqual(len(v["deaths"]), 1)                      # "slain" + "died" are one death
        r = d.get("Me_x", v["latest"])
        self.assertEqual((r["killer"], r["killer_from"], r["zone"]), ("Gorgalosk", "log", "Unrest"))
        self.assertEqual((r["blow"]["src"], r["blow"]["amt"], r["blow"]["verb"], r["blow"]["crit"]),
                         ("Gorgalosk", 650, "crushes", True))
        self.assertEqual((r["total"], r["hits"], r["healed"], r["avoided"], r["resisted"]), (1210, 4, 300, 1, 1))
        self.assertEqual(r["last5"], 1090)
        src = {s["name"]: s for s in r["sources"]}
        self.assertEqual((src["Gorgalosk"]["total"], src["Gorgalosk"]["max"], src["Gorgalosk"]["spell"],
                          src["Gorgalosk"]["melee"]), (1050, 650, 400, 650))
        self.assertEqual((src["a ghoul"]["total"], src["a ghoul"]["dot"], src["a ghoul"]["avoided"]), (160, 40, 1))
        self.assertEqual(r["sources"][0]["name"], "Gorgalosk")
        kinds = [e["k"] for e in r["events"]]
        self.assertEqual(kinds, ["hit", "avoid", "cast", "hit", "resist", "heal", "hit", "status", "hit"])
        self.assertEqual(r["events"][0]["ago"], 8)

    def test_killer_from_last_hit_and_next_death(self):
        d = DeathRecap({})
        feed(d, [(0, "a ghoul hits YOU for 50 points of damage."), (2, "You died.")])
        feed(d, [(30, "a skeleton hits YOU for 70 points of damage."), (31, "You have been slain by a skeleton!")])
        v = d.view("Me_x")
        a, b = (d.get("Me_x", x["id"]) for x in reversed(v["deaths"]))
        self.assertEqual((a["killer"], a["killer_from"], a["total"]), ("a ghoul", "last hit", 50))
        self.assertEqual((b["killer"], b["total"]), ("a skeleton", 70))          # nothing from the first death
        self.assertEqual(v["killers"][0]["n"], 1)
        d.delete("Me_x", a["id"])
        self.assertEqual(len(d.view("Me_x")["deaths"]), 1)
        self.assertEqual(d.view("Other_x")["deaths"], [])                        # per character

    def test_app_and_http(self):
        tmp = tempfile.mkdtemp()
        try:
            logs = os.path.join(tmp, "Logs")
            os.makedirs(logs)
            with open(os.path.join(logs, "eqlog_Me_x.txt"), "w") as fh:
                for i, (dt_, msg) in enumerate(FIGHT[1:]):
                    fh.write(f"[Mon Oct 12 20:00:{10 + dt_:02d} 2026] {msg}\n")
            app = App(log_dir=logs, ddir=os.path.join(tmp, "data"))
            app.cfg["port"] = 7395
            app.poll()
            from eqlc.server import serve
            srv = serve(app)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen("http://127.0.0.1:7395/api/deaths?char=Me_x") as res:
                    v = json.load(res)
                self.assertEqual(v["deaths"][0]["killer"], "Gorgalosk")
                with urllib.request.urlopen(f"http://127.0.0.1:7395/api/deaths?char=Me_x&id={v['latest']}") as res:
                    self.assertEqual(json.load(res)["detail"]["total"], 1210)
                req = urllib.request.Request("http://127.0.0.1:7395/api/deaths/clear", method="POST",
                                             data=json.dumps({"char": "Me_x"}).encode())
                urllib.request.urlopen(req).close()
                self.assertEqual(app.deaths.view("Me_x")["deaths"], [])
            finally:
                srv.shutdown()
                srv.server_close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

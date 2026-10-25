"""Small local HTTP server: JSON API + static web UI (dashboard)."""
import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .launch import WEB, close_overlay_window, open_overlay_window, overlay_running


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _png(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=30")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, path):
            if path in ("", "/"):
                path = "/index.html"
            full = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
            if not full.startswith(WEB) or not os.path.isfile(full):
                self.send_error(404)
                return
            with open(full, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            p = u.path
            if not p.startswith("/api/"):
                return self._static(p)
            if p == "/api/update":
                return self._json(app.updates.view())
            if p == "/api/crawls/snapshot":
                from . import snapshot as S
                with app.lock:
                    try:
                        rid = int(q.get("id", 0))
                    except ValueError:
                        rid = 0
                    png = S.load(app.ddir, rid)
                    r = app.crawls._get(rid) if png is None else None
                    if r is not None and r["status"] == "done":
                        png = S.render(app.crawls._summary(r, time.time()), r["char"].partition("_")[0])
                if not png:
                    return self.send_error(404)
                return self._png(png)
            with app.lock:
                char = q.get("char") or app.char()
                if p == "/api/overlay":
                    o = app.tracker(char).overlay() if char else {"current": None, "avg": 0, "avg_n": 0,
                                                                  "history": [], "best": 0}
                    o.update(char=char, zone=app.zone.get(char), status=app.status,
                             motes=app.motes.view(char) if char else None,
                             timers=app.timers.view(char) if (q.get("kind") != "dps" or app.cfg.get("timers_on_overlay", True)) else [],
                             crawl=app.crawls.overlay(char) if char and (q.get("kind") != "dps" or app.cfg.get("crawl_on_overlay", True)) else None)
                    if q.get("kind") in app.OVERLAY_ON_KEY:
                        o["look"] = app.overlay_look(q["kind"])
                    return self._json(o)
                if p == "/api/overlays":
                    return self._json({"overlays": [
                        dict(app.overlay_look(k), kind=k, on=bool(app.cfg.get(key, True)), running=overlay_running(k))
                        for k, key in app.OVERLAY_ON_KEY.items()],
                        "crawl_on_overlay": app.cfg.get("crawl_on_overlay", True),
                        "timers_on_overlay": app.cfg.get("timers_on_overlay", True)})
                if p == "/api/fights":
                    lst = app.tracker(char).list(int(q.get("limit", 200))) if char else []
                    return self._json({"char": char, "fights": lst})
                if p == "/api/breakdown":
                    b = app.tracker(char).breakdown(q.get("scope", "latest"), q.get("name", "You"),
                                                    q.get("side", "friend")) if char else None
                    return self._json(b or {}, 200 if b else 404)
                if p == "/api/fight":
                    f = app.tracker(char).get(int(q.get("id", 0))) if char else None
                    return self._json(f or {}, 200 if f else 404)
                if p == "/api/fight/deep":
                    try:
                        f = app.tracker(char).deep(q.get("id", "latest")) if char else None
                    except ValueError:
                        f = None
                    return self._json(f or {}, 200 if f else 404)
                if p == "/api/quests":
                    return self._json(app.quests.view(char) if char else {"char": None})
                if p == "/api/factions":
                    return self._json(app.factions.view(char) if char else {"char": None})
                if p == "/api/exalts":
                    return self._json(app.exalts_view(char) if char else {"char": None})
                if p == "/api/deaths":
                    if not char:
                        return self._json({"char": None})
                    v = app.deaths.view(char)
                    if q.get("id"):
                        try:
                            v["detail"] = app.deaths.get(char, int(q["id"]))
                        except ValueError:
                            v["detail"] = None
                    return self._json(v)
                if p == "/api/races":
                    return self._json(app.races.view(char))
                if p == "/api/raids":
                    if not char:
                        return self._json({"char": None})
                    try:
                        week = max(0, min(52, int(q.get("week", 0))))
                    except ValueError:
                        week = 0
                    v = app.raids.view(char, week)
                    v["extra"] = app.cfg.get("raid_extra_bosses", [])
                    return self._json(v)
                if p == "/api/crawls":
                    if not char:
                        return self._json({"char": None})
                    tr = app.tracker(char)
                    fights = list(tr.fights) + ([tr.current] if tr.current else [])
                    v = app.crawls.view(char, fights)
                    v["scan_status"] = app.scan_status
                    return self._json(v)
                if p == "/api/timers":
                    return self._json({"rules": app.cfg.get("timers", []), "active": app.timers.view(char)})
                if p == "/api/sky":
                    chars = app.characters()
                    if not char:
                        return self._json({"char": None, "characters": chars})
                    v = app.sky.view(char)
                    v["characters"] = chars
                    return self._json(v)
                if p == "/api/settings":
                    from . import __version__
                    from .classes_data import CLASSES
                    return self._json({"cfg": app.cfg, "status": app.status, "active": app.active_char,
                                       "version": __version__, "classes": CLASSES,
                                       "my_classes": app.my_classes(char) if char else None, "char": char,
                                       "class_info": {c: app.class_info(c) for c in app.characters()},
                                       "characters": app.characters(),
                                       "data_dir": app.ddir})
            self.send_error(404)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            p = u.path
            if p == "/api/overlay/open":
                try:
                    kind = body.get("kind", "dps")
                    if kind in app.OVERLAY_ON_KEY:
                        app.set_overlay(kind, {"on": True})
                    open_overlay_window(f"http://127.0.0.1:{app.cfg['port']}", kind if kind in app.OVERLAY_ON_KEY else "dps")
                    return self._json({"ok": True})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 500)
            if p == "/api/overlays/set":
                kind = body.get("kind", "")
                try:
                    look = app.set_overlay(kind, body)
                    if "on" in body and not body.get("from_overlay"):
                        if body["on"]:
                            open_overlay_window(f"http://127.0.0.1:{app.cfg['port']}", kind)
                        else:
                            close_overlay_window(kind)
                    return self._json({"ok": True, "look": look, "running": overlay_running(kind)})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)
            if p == "/api/inventory/import":
                try:
                    mt = body.get("mtime")
                    res = app.import_inventory(str(body.get("text", "")), str(body.get("filename", "")),
                                               body.get("char") or None, float(mt) / 1000 if mt else None)
                    return self._json({"ok": True, **res})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)
            if p == "/api/focus":
                scope = str(body.get("scope", "latest"))
                name = str(body.get("name", "You"))
                side = "npc" if body.get("side") == "npc" else "friend"
                win = getattr(app, "gui_window", None)
                if win is not None:
                    try:
                        win.restore()
                        win.show()
                        win.evaluate_js(f"openBreakdown({json.dumps(scope)}, {json.dumps(name)}, {json.dumps(side)})")
                        win.on_top = True          # pop above the game for a moment, then behave normally
                        import threading
                        threading.Timer(0.6, lambda: setattr(win, "on_top", False)).start()
                    except Exception as e:
                        return self._json({"ok": False, "error": str(e)}, 500)
                else:
                    import webbrowser
                    from urllib.parse import quote
                    webbrowser.open(f"http://127.0.0.1:{app.cfg['port']}/#breakdown={quote(scope)}:{side}:{quote(name)}")
                return self._json({"ok": True})
            if p == "/api/quit":
                self._json({"ok": True})
                import threading
                threading.Thread(target=app.quit, daemon=True).start()
                return
            if p == "/api/quests/import":
                # network call to eqlwiki.com: done outside the app lock
                from .quests import import_from_wiki
                try:
                    return self._json({"ok": True, **import_from_wiki(str(body.get("page", "")))})
                except Exception as e:
                    return self._json({"ok": False, "error": f"Couldn't read that wiki page: {e}"}, 400)
            if p.startswith("/api/races/"):
                with app.lock:
                    try:
                        if p == "/api/races/unlock":
                            app.races.set_unlocked(body.get("char") or app.char(), str(body.get("race", "")),
                                                   bool(body.get("on")))
                        elif p == "/api/races/step":
                            app.races.set_step(body.get("char") or app.char(), str(body.get("step", "")),
                                               bool(body.get("on")))
                        else:
                            return self.send_error(404)
                    except ValueError as e:
                        return self._json({"ok": False, "error": str(e)}, 400)
                app.save_state(force=True)
                return self._json({"ok": True})
            if p.startswith(("/api/quests/", "/api/factions/", "/api/raids/")):
                with app.lock:
                    char = body.get("char") or app.char()
                    res = {"ok": True}
                    if p == "/api/quests/tick":
                        app.quests.tick(char, body["id"], int(body["idx"]), bool(body.get("on")))
                    elif p == "/api/quests/done":
                        app.quests.set_done(char, body["id"], bool(body.get("on")))
                    elif p == "/api/quests/classes":
                        app.quests.set_classes(char, body.get("classes", []))
                    elif p == "/api/quests/save":
                        res["quest"] = app.quests.save_custom(char, body.get("quest", {}))
                    elif p == "/api/quests/delete":
                        app.quests.delete_custom(char, body.get("id"))
                    elif p == "/api/factions/base":
                        v = body.get("value")
                        try:
                            v = None if v in (None, "") else int(v)
                        except (TypeError, ValueError):
                            return self._json({"ok": False, "error": "Enter a whole number"}, 400)
                        app.factions.set_base(char, body["name"], v)
                    elif p == "/api/raids/settings":
                        if "eras" in body:
                            app.cfg["raid_eras"] = [e for e in body["eras"] if e in ("Classic", "Kunark", "Velious")]
                        if "extra" in body:
                            app.cfg["raid_extra_bosses"] = [str(x).strip() for x in body["extra"] if str(x).strip()][:100]
                        app.save_cfg()
                    elif p == "/api/raids/delete":
                        app.raids.delete(char, float(body["t"]), body["boss"])
                    else:
                        return self.send_error(404)
                app.save_state(force=True)
                return self._json(res)
            if p == "/api/crawls/proof":
                with app.lock:
                    try:
                        res = app.export_proof(int(body.get("id")))
                    except (TypeError, ValueError) as e:
                        return self._json({"ok": False, "error": str(e) or "No such run"}, 400)
                return self._json(dict(res, ok=True))
            if p == "/api/crawls/snapshot":
                from . import snapshot as S
                with app.lock:
                    try:
                        rid = int(body.get("id"))
                        if not app.crawls._get(rid):
                            raise ValueError("No such run")
                        if S.exists(app.ddir, rid) and not body.get("replace"):
                            return self._json({"ok": True, "kept": True})
                        S.save(app.ddir, rid, body.get("png") or "")
                    except (TypeError, ValueError) as e:
                        return self._json({"ok": False, "error": str(e) or "bad picture"}, 400)
                return self._json({"ok": True})
            if p == "/api/crawls/submit":
                try:
                    reply = app.submit_run(int(body.get("id")), body.get("classes") or None,
                                           str(body.get("video") or "").strip())
                except (TypeError, ValueError) as e:
                    return self._json({"ok": False, "error": str(e) or "No such run"}, 400)
                app.save_state(force=True)
                return self._json({"ok": True, "message": reply.get("message") or "Sent to the leaderboard.",
                                   "duplicate": bool(reply.get("duplicate")), "id": reply.get("id")})
            if p.startswith("/api/update/"):
                if p == "/api/update/check":
                    return self._json(dict(app.updates.check(), ok=True))
                if p == "/api/update/dismiss":
                    app.updates.dismiss(str(body.get("version") or ""))
                    return self._json({"ok": True})
                if p == "/api/update/open":
                    return self._json({"ok": True, "url": app.updates.open(body.get("which") or "download")})
                return self.send_error(404)
            if p == "/api/crawls/classes":
                from .classes_data import CLASSES
                cl = [c for c in (body.get("classes") or []) if c in CLASSES]
                if cl and (len(cl) > 3 or len(set(cl)) != len(cl)):
                    return self._json({"ok": False, "error": "Pick up to three different classes"}, 400)
                with app.lock:
                    try:
                        app.crawls.set_classes(int(body.get("id")), str(body.get("name") or ""), cl)
                    except (TypeError, ValueError) as e:
                        return self._json({"ok": False, "error": str(e) or "No such run"}, 400)
                app.save_state(force=True)
                return self._json({"ok": True})
            if p == "/api/classes/mine":
                char = body.get("char") or app.char()
                try:
                    app.set_my_classes(char, body.get("classes") or [])
                except ValueError as e:
                    return self._json({"ok": False, "error": str(e)}, 400)
                return self._json({"ok": True, "classes": app.my_classes(char)})
            if p == "/api/crawls/verify":
                from .integrity import check_proof
                try:
                    doc = json.loads(body.get("text") or "")
                except ValueError:
                    return self._json({"ok": False, "problems": ["That isn't a proof file (not valid JSON)."]})
                return self._json(check_proof(doc))
            if p.startswith("/api/crawls/"):
                if p == "/api/crawls/rescan":
                    import threading
                    threading.Thread(target=app.rescan_crawls, daemon=True).start()
                    return self._json({"ok": True})
                with app.lock:
                    char = body.get("char") or app.char()
                    if p == "/api/crawls/restart":
                        if not app.crawls.restart(char):
                            return self._json({"ok": False, "error": "Enter a crawl instance first"}, 400)
                    elif p == "/api/crawls/stop":
                        if not app.crawls.stop(char):
                            return self._json({"ok": False, "error": "No crawl timer is running"}, 400)
                    elif p == "/api/crawls/reset":
                        if not app.crawls.reset(char):
                            return self._json({"ok": False, "error": "Enter a crawl instance first"}, 400)
                    elif p == "/api/crawls/discard":
                        app.crawls.discard_current(char)
                    elif p == "/api/crawls/player":
                        name = str(body.get("name") or "")
                        if not name:
                            return self._json({"ok": False, "error": "No name"}, 400)
                        app.crawls.set_player(char, name, bool(body.get("player")))
                    elif p == "/api/crawls/delete":
                        app.crawls.delete(body.get("id"))
                    else:
                        return self.send_error(404)
                app.save_state(force=True)
                return self._json({"ok": True})
            if p == "/api/exalts/refresh":
                with app.lock:
                    char = body.get("char") or app.char()
                    rows = app.exalts.rows(char)[0] or []
                n = app.exalts.lookup([r["name"] for r in rows], force=True)
                return self._json({"ok": True, "looking_up": n})
            if p in ("/api/deaths/delete", "/api/deaths/clear"):
                with app.lock:
                    char = body.get("char") or app.char()
                    if p.endswith("delete"):
                        app.deaths.delete(char, int(body.get("id") or 0))
                    else:
                        app.deaths.clear(char)
                app.save_state(force=True)
                return self._json({"ok": True})
            if p.startswith("/api/timers/"):
                with app.lock:
                    char = body.get("char") or app.char()
                    if p == "/api/timers/rules":
                        rules = []
                        for r in body.get("rules", []):
                            try:
                                mob = str(r.get("mob", "")).strip()
                                mins = float(r.get("minutes") or 0)
                            except (TypeError, ValueError):
                                continue
                            if mob and mins > 0:
                                rules.append({"mob": mob, "minutes": mins,
                                              "variance": max(0.0, float(r.get("variance") or 0)),
                                              "zone": str(r.get("zone") or "").strip()})
                        app.cfg["timers"] = rules
                        app.save_cfg()
                    elif p == "/api/timers/start":
                        a = app.timers.start_manual(str(body.get("mob", "")).strip(),
                                                    body.get("minutes"), body.get("variance"), char=char)
                        if not a:
                            return self._json({"ok": False, "error": "Unknown mob - add a rule or give minutes"}, 400)
                    elif p == "/api/timers/remove":
                        app.timers.remove(body.get("id"), char=char)
                    else:
                        return self.send_error(404)
                app.save_state(force=True)
                return self._json({"ok": True, "rules": app.cfg["timers"], "active": app.timers.view(char)})
            if p == "/api/settings":
                app.update_cfg(body)
                return self._json({"ok": True, "cfg": app.cfg})
            with app.lock:
                char = body.get("char") or app.char()
                if not char:
                    return self._json({"error": "no character"}, 400)
                if p == "/api/sky/done":
                    app.sky.set_done(char, body["id"], bool(body.get("done")))
                elif p == "/api/sky/unlock":
                    app.sky.set_unlocked(char, body["cls"], bool(body.get("unlocked")))
                elif p == "/api/sky/currency":
                    app.sky.set_currency(char, body.get("counts") or {})
                elif p == "/api/sky/adjust":
                    app.sky.adjust(char, body["item"], int(body.get("delta", 1)))
                elif p == "/api/fights/clear":
                    app.tracker(char).clear()
                else:
                    return self.send_error(404)
            app.save_state(force=True)
            return self._json({"ok": True})

    return H


def serve(app, host="127.0.0.1"):
    srv = ThreadingHTTPServer((host, int(app.cfg["port"])), make_handler(app))
    srv.daemon_threads = True
    return srv

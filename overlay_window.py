"""Always-on-top in-game overlay windows (Tkinter, ships with Python).

Two windows, each its own process:
    dps    current fight DPS, last-10 average, respawn timers
    motes  motes collected this session, split by tier
    crawl  dungeon crawl timer against your personal best

Opened by EQL Assistant (automatically or from the Overlays tab) and closed
when the app closes. Drag to move. Drag the corner grip (or Ctrl + mouse wheel)
to resize. Right-click for size / opacity / lock / close. Size, opacity, lock
and on/off are shared with the app's Overlays tab; each window remembers its
own position.
Double-click the DPS overlay to open your full breakdown for the latest fight.
Tip: run EverQuest Legends in borderless windowed mode so these stay on top.
"""
import json
import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request

BG = "#0d1117"
FG = "#e6edf3"
DIM = "#8b949e"
GOLD = "#e3b341"
GREEN = "#3fb950"
SKY = "#9ad7ff"
RED = "#f0776c"
FONT = "Segoe UI" if sys.platform == "win32" else "Helvetica"
PREFS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), "EQLAssistant")


def fmt(n):
    return f"{n:,.0f}" if n >= 100 else f"{n:,.1f}"


def char_label(c):
    """'Sahkage_rivervale' -> 'Sahkage (rivervale)': characters are per server."""
    name, _, server = (c or "").partition("_")
    return f"{name} ({server})" if server else name


def clock(secs):
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class OverlayBase:
    kind = "base"
    default_pos = (40, 40)
    MIN_SCALE, MAX_SCALE = 0.6, 2.5

    def __init__(self, url):
        self.base = url.rstrip("/")
        self.url = f"{self.base}/api/overlay?kind={self.kind}"
        self.prefs_file = os.path.join(PREFS_DIR, f"overlay_{self.kind}.json")
        self.root = r = tk.Tk()
        r.title(f"EQL {self.kind}")
        r.overrideredirect(True)
        try:
            from eqlc.launch import ICON
            if sys.platform == "win32" and os.path.exists(ICON):
                r.iconbitmap(default=ICON)
        except Exception:
            pass
        r.attributes("-topmost", True)
        self.prefs = self._load()
        self.alpha = self.prefs.get("alpha", 0.85)
        self.scale = self.prefs.get("scale", 1.0)
        self.locked = self.prefs.get("locked", False)
        self.rev = self.prefs.get("rev")
        r.attributes("-alpha", self.alpha)
        x, y = self.prefs.get("x", self.default_pos[0]), self.prefs.get("y", self.default_pos[1])
        r.geometry(f"+{x}+{y}")
        r.configure(bg=BG)
        self.fonts = {}
        self.frame = tk.Frame(r, bg=BG, padx=12, pady=8)
        self.frame.pack()
        self.m = tk.Menu(r, tearoff=0)
        sizes = tk.Menu(self.m, tearoff=0)
        for s in (0.75, 1.0, 1.25, 1.5, 2.0):
            sizes.add_command(label=f"{int(s * 100)}%", command=lambda s=s: self._set_scale(s, push=True))
        self.m.add_cascade(label="Size", menu=sizes)
        opac = tk.Menu(self.m, tearoff=0)
        for a in (1.0, 0.85, 0.7, 0.5, 0.35):
            opac.add_command(label=f"{int(a * 100)}%", command=lambda a=a: self._alpha(a, push=True))
        self.m.add_cascade(label="Opacity", menu=opac)
        self.m.add_separator()
        if self.kind == "dps":
            self.m.add_command(label="Open my fight breakdown  (double-click)", command=self._open_breakdown)
            self.m.add_separator()
        if self.kind == "crawl":
            self.m.add_command(label="End crawl now (can't be submitted)", command=lambda: self._post("/api/crawls/stop", {}))
            self.m.add_command(label="Reset timer (back to 0:00)", command=lambda: self._post("/api/crawls/reset", {}))
            self.m.add_separator()
        self.m.add_command(label="Lock / unlock position and size", command=self._toggle_lock)
        self.m.add_command(label="Reset size and position", command=self._reset)
        self.m.add_command(label="Turn off", command=self._turn_off)
        self._dx = self._dy = 0
        self._g0 = None
        self._connected = False
        self._fails = 0
        self.build(self.frame)
        self.bind_all_children(r)
        # resize grip, bottom-right corner
        self.grip = tk.Label(r, text="◢", bg=BG, fg="#3a4350", font=(FONT, 9), cursor="size_nw_se", bd=0, padx=0, pady=0)
        self.grip.bind("<ButtonPress-1>", self._grip_start)
        self.grip.bind("<B1-Motion>", self._grip_drag)
        self.grip.bind("<ButtonRelease-1>", self._grip_end)
        self.grip.bind("<Button-3>", self._menu)
        r.bind_all("<Control-MouseWheel>", self._wheel)
        self._apply_scale()
        self._show_grip()
        self.update()

    # -- helpers ---------------------------------------------------------------
    def font(self, size, bold=False):
        f = self.fonts.get((size, bold))
        if f is None:
            f = self.fonts[(size, bold)] = tkfont.Font(family=FONT, size=max(6, round(size * self.scale)),
                                                       weight="bold" if bold else "normal")
        return f

    def label(self, parent, text="", fg=FG, size=9, bold=False, **grid):
        w = tk.Label(parent, text=text, bg=BG, fg=fg, font=self.font(size, bold))
        if grid:
            pad = {k: grid[k] for k in ("padx", "pady") if k in grid}
            if pad:                              # keep spacing in proportion when resized
                w._pad = pad
                grid.update(self._scaled(pad))
            w.grid(**grid)
        return w

    def px(self, n):
        return max(1, round(n * self.scale)) if n else 0

    def bind_all_children(self, w):
        w.bind("<ButtonPress-1>", self._start)
        w.bind("<B1-Motion>", self._drag)
        w.bind("<ButtonRelease-1>", lambda e: self._save())
        w.bind("<Button-3>", self._menu)
        if self.kind == "dps":
            w.bind("<Double-Button-1>", lambda e: self._open_breakdown())
        for c in w.winfo_children():
            if not isinstance(c, tk.Menu) and c is not getattr(self, "grip", None):
                self.bind_all_children(c)

    def _load(self):
        files = [self.prefs_file]
        if self.kind == "dps":      # position saved by the earlier single-overlay version
            files.append(os.path.join(PREFS_DIR, "overlay_window.json"))
        for p in files:
            try:
                with open(p) as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                continue
        return {}

    def _save(self):
        self.prefs.update(x=self.root.winfo_x(), y=self.root.winfo_y(), locked=self.locked,
                          alpha=self.alpha, scale=self.scale, rev=self.rev)
        try:
            os.makedirs(PREFS_DIR, exist_ok=True)
            with open(self.prefs_file, "w") as fh:
                json.dump(self.prefs, fh)
        except OSError:
            pass

    def _post(self, path, body):
        try:
            req = urllib.request.Request(self.base + path, method="POST", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=2).close()
        except Exception:
            pass

    def _push(self, **look):
        """Tell the app, so the Overlays tab shows the same settings."""
        self._hold = time.time() + 1.5      # ignore the app's older copy until it has ours
        self._post("/api/overlays/set", dict(look, kind=self.kind))

    def _open_breakdown(self):
        """Bring up the app window on your breakdown for the latest fight."""
        self._post("/api/focus", {"scope": "latest", "name": "You"})

    # -- move ------------------------------------------------------------------
    def _start(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag(self, e):
        if not self.locked:
            self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _menu(self, e):
        self.m.tk_popup(e.x_root, e.y_root)

    # -- resize ----------------------------------------------------------------
    def _grip_start(self, e):
        self._g0 = (e.x_root, e.y_root, self.scale, max(40, self.root.winfo_width()), max(30, self.root.winfo_height()))
        return "break"

    def _grip_drag(self, e):
        if self.locked:
            return "break"
        x0, y0, s0, w0, h0 = self._g0
        grow = max((w0 + e.x_root - x0) / w0, (h0 + e.y_root - y0) / h0)
        s = s0 * grow
        if abs(s - self.scale) >= 0.03:
            self._set_scale(s)
        return "break"

    def _grip_end(self, e):
        self._g0 = None
        self._save()
        self._push(scale=self.scale)
        return "break"

    def _wheel(self, e):
        if not self.locked:
            self._set_scale(self.scale + (0.1 if e.delta > 0 else -0.1), push=True)

    def _set_scale(self, s, push=False):
        s = round(min(self.MAX_SCALE, max(self.MIN_SCALE, s)), 2)
        if s != self.scale:
            self.scale = s
            self._apply_scale()
        if push:
            self._save()
            self._push(scale=self.scale)

    def _apply_scale(self):
        for (size, bold), f in self.fonts.items():
            f.configure(size=max(6, round(size * self.scale)))
        self.frame.configure(padx=self.px(12), pady=self.px(8))
        self._rescale_pads(self.frame)
        self.on_scale()

    def _rescale_pads(self, w):
        for c in w.winfo_children():
            pad = getattr(c, "_pad", None)
            if pad and c.winfo_manager() == "grid":
                c.grid_configure(**self._scaled(pad))
            self._rescale_pads(c)

    def _scaled(self, pad):
        return {k: (tuple(self.px(x) if x else 0 for x in v) if isinstance(v, tuple) else self.px(v))
                for k, v in pad.items()}

    def _show_grip(self):
        if self.locked:
            self.grip.place_forget()
        else:
            self.grip.place(relx=1.0, rely=1.0, anchor="se")

    # -- menu actions ------------------------------------------------------------
    def _alpha(self, a, push=False):
        self.alpha = a
        self.root.attributes("-alpha", a)
        if push:
            self._save()
            self._push(alpha=a)

    def _toggle_lock(self):
        self.locked = not self.locked
        self._show_grip()
        self._save()
        self._push(locked=self.locked)

    def _reset(self):
        self._push(reset=True)            # the app bumps "rev"; we move when we see it

    def _move_home(self):
        self.root.geometry(f"+{self.default_pos[0]}+{self.default_pos[1]}")

    def _turn_off(self):
        self._post("/api/overlays/set", {"kind": self.kind, "on": False, "from_overlay": True})
        self.root.destroy()

    def _apply_look(self, look):
        if not look or time.time() < getattr(self, "_hold", 0):
            return
        changed = False
        if look.get("alpha") is not None and abs(look["alpha"] - self.alpha) > 0.001:
            self._alpha(look["alpha"])
            changed = True
        if look.get("locked") is not None and bool(look["locked"]) != self.locked:
            self.locked = bool(look["locked"])
            self._show_grip()
            changed = True
        if look.get("scale") and abs(look["scale"] - self.scale) > 0.001 and not self._resizing():
            self._set_scale(look["scale"])
            changed = True
        rev = look.get("rev", 0)
        if self.rev is None:
            self.rev = rev                 # first contact: just remember it
            changed = True
        elif rev != self.rev:
            self.rev = rev
            self._move_home()
            changed = True
        if changed:
            self.root.after(50, self._save)

    def _resizing(self):
        return getattr(self, "_g0", None) is not None

    def update(self):
        try:
            with urllib.request.urlopen(self.url, timeout=1) as resp:
                d = json.load(resp)
            self._apply_look(d.get("look"))
            self.render(d)
            self._connected, self._fails = True, 0
        except Exception:
            self._fails += 1
            self.waiting()
            # The app was closed: close this window too (after ~5 seconds).
            if self._connected and self._fails >= 10:
                self.root.destroy()
                return
        self.root.after(500, self.update)
        self.root.attributes("-topmost", True)    # stay above the game

    def run(self):
        self.root.mainloop()

    # -- override ----------------------------------------------------------------
    def build(self, f):
        pass

    def render(self, d):
        pass

    def waiting(self):
        pass

    def on_scale(self):
        pass


class DpsOverlay(OverlayBase):
    kind = "dps"
    default_pos = (40, 40)

    def build(self, f):
        self.title = self.label(f, "EQL ASSISTANT", DIM, 8, True, row=0, column=0, columnspan=2, sticky="w")
        self.label(f, "NOW", DIM, 9, row=1, column=0, sticky="w")
        self.cur = self.label(f, "—", GREEN, 22, True, row=1, column=1, sticky="e", padx=(16, 0))
        self.cur_sub = self.label(f, "", DIM, 8, row=2, column=0, columnspan=2, sticky="e")
        self.label(f, "AVG", DIM, 9, row=3, column=0, sticky="w")
        self.avg = self.label(f, "—", GOLD, 16, True, row=3, column=1, sticky="e", padx=(16, 0))
        self.spark = tk.Canvas(f, width=self.px(180), height=self.px(26), bg=BG, highlightthickness=0)
        self._spark_vals = []
        self.spark.grid(row=4, column=0, columnspan=2, pady=(4, 0))
        # dungeon crawl timer (only shown while a run is active or just finished)
        self.crawl_box = tk.Frame(f, bg=BG)
        self.crawl_box.grid(row=5, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.crawl_box.grid_columnconfigure(1, weight=1)
        self.crawl_head = self.label(self.crawl_box, "", DIM, 8, True, row=0, column=0, columnspan=2, sticky="w")
        self.crawl_time = self.label(self.crawl_box, "", GREEN, 16, True, row=1, column=0, sticky="w")
        self.crawl_pb = self.label(self.crawl_box, "", DIM, 8, row=1, column=1, sticky="e", padx=(12, 0))
        self.crawl_box.grid_remove()
        self.timer_box = tk.Frame(f, bg=BG)
        self.timer_box.grid(row=6, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self._timer_sig = None
        self._timer_rows = []

    def waiting(self):
        self.title.config(text="EQL ASSISTANT · waiting for app…")

    def render(self, d):
        self.title.config(text=char_label(d.get("char")).upper() if d.get("char") else "EQL ASSISTANT")
        c = d.get("current")
        if c:
            self.cur.config(text=fmt(c["dps"]), fg=GREEN if c["active"] else FG)
            tgt = c["target"] if len(c["target"]) < 26 else c["target"][:25] + "…"
            self.cur_sub.config(text=f"{tgt} · {clock(c['duration'])}" + ("" if c["active"] else " · last"))
        else:
            self.cur.config(text="—", fg=FG)
            self.cur_sub.config(text="no fights yet")
        self.avg.config(text=fmt(d["avg"]) if d.get("avg_n") else "—")
        self._spark(d.get("history", []))
        self._crawl(d.get("crawl"))
        self._timers(d.get("timers") or [])

    def _crawl(self, c):
        if not c:
            self.crawl_box.grid_remove()
            return
        self.crawl_box.grid()
        zone = c["zone"] if len(c["zone"]) < 22 else c["zone"][:21] + "…"
        lvl = c["tier_label"].split(" ")[0]
        if c["state"] == "done":
            self.crawl_head.config(text=f"CRAWL DONE · {zone} {lvl}", fg=GOLD if c.get("new_pb") else DIM)
            self.crawl_time.config(text=clock(c["elapsed"]), fg=GOLD if c.get("new_pb") else FG)
            if c.get("new_pb"):
                self.crawl_pb.config(text="NEW BEST!" if c["pb"] is None else f"NEW BEST  (was {clock(c['pb'])})", fg=GOLD)
            else:
                self.crawl_pb.config(text=f"best {clock(c['pb'])}" if c["pb"] is not None else "", fg=DIM)
            return
        away = c["state"] in ("away", "waiting", "ready")
        note = {"away": "  (outside)", "waiting": "  (not entered)", "ready": "  (first kill starts it)"}.get(c["state"], "")
        self.crawl_head.config(text=f"CRAWL · {zone} {lvl}" + note, fg=DIM)
        behind = c["pb"] is not None and c["elapsed"] > c["pb"]
        self.crawl_time.config(text=clock(c["elapsed"]), fg=GOLD if away else (RED if behind else GREEN))
        if c["pb"] is not None:
            diff = c["elapsed"] - c["pb"]
            self.crawl_pb.config(text=f"best {clock(c['pb'])}  " + (f"+{clock(diff)}" if diff > 0 else f"-{clock(-diff)}"),
                                 fg=RED if behind else DIM)
        else:
            self.crawl_pb.config(text=f"{c['kills']} kills", fg=DIM)

    def _timers(self, timers):
        timers = timers[:5]
        sig = [t["id"] for t in timers]
        if sig != self._timer_sig:          # rows changed: rebuild
            for w in self.timer_box.winfo_children():
                w.destroy()
            self._timer_rows = []
            if timers:
                self.label(self.timer_box, "RESPAWNS", DIM, 8, True, row=0, column=0, sticky="w")
            for i, t in enumerate(timers):
                name = t["mob"] if len(t["mob"]) < 22 else t["mob"][:21] + "…"
                a = self.label(self.timer_box, name, FG, 9, row=i + 1, column=0, sticky="w")
                b = self.label(self.timer_box, "", FG, 9, True, row=i + 1, column=1, sticky="e")
                self._timer_rows.append(b)
            self.timer_box.grid_columnconfigure(1, weight=1)
            self.bind_all_children(self.timer_box)
            self._timer_sig = sig
        for t, lbl in zip(timers, self._timer_rows):
            if t["state"] == "up":
                lbl.config(text="UP", fg=GREEN)
            elif t["state"] == "window":
                lbl.config(text=f"window {clock(t['window_left'])}", fg=GOLD)
            else:
                lbl.config(text=clock(t["remaining"]), fg=RED if t["remaining"] <= 60 else FG)

    def on_scale(self):
        self.spark.configure(width=self.px(180), height=self.px(26))
        self._spark(self._spark_vals)

    def _spark(self, vals):
        self._spark_vals = vals
        cv = self.spark
        cv.delete("all")
        if not vals:
            return
        w, h, n = self.px(180), self.px(26), len(vals)
        top = max(vals) or 1
        bw = w / max(n, 10)
        for i, v in enumerate(vals):
            x = i * bw
            bh = max(2, (v / top) * (h - 2))
            cv.create_rectangle(x + 1, h - bh, x + bw - 1, h, fill=GOLD if i == n - 1 else "#6e5a1f", width=0)


class MotesOverlay(OverlayBase):
    kind = "motes"
    default_pos = (40, 300)

    def build(self, f):
        self.title = self.label(f, "MOTES", DIM, 8, True, row=0, column=0, columnspan=3, sticky="w")
        self.total = self.label(f, "0", SKY, 22, True, row=1, column=0, columnspan=2, sticky="w")
        self.rate = self.label(f, "", DIM, 9, row=1, column=2, sticky="e", padx=(14, 0))
        self.rows = tk.Frame(f, bg=BG)
        self.rows.grid(row=2, column=0, columnspan=3, sticky="we", pady=(4, 0))
        self._sig = None
        self._cells = []

    def waiting(self):
        self.title.config(text="MOTES · waiting for app…")

    def render(self, d):
        m = d.get("motes")
        if not m:
            return
        self.title.config(text=f"MOTES · {char_label(d.get('char')).upper()}")
        self.total.config(text=f"{m['count']:,}")
        self.rate.config(text=f"{fmt(m['per_hour'])}/hr" if m["count"] else "")
        tiers = m["tiers"]
        sig = [t["tier"] for t in tiers]
        if sig != self._sig:
            for w in self.rows.winfo_children():
                w.destroy()
            self._cells = []
            for i, t in enumerate(tiers):
                name = self.label(self.rows, t["label"], FG, 9, row=i, column=0, sticky="w")
                cnt = self.label(self.rows, "", SKY, 10, True, row=i, column=1, sticky="e", padx=(18, 0))
                rate = self.label(self.rows, "", DIM, 8, row=i, column=2, sticky="e", padx=(10, 0))
                self._cells.append((cnt, rate))
            if not tiers:
                self.label(self.rows, "none yet this session", DIM, 8, row=0, column=0, sticky="w")
            self.rows.grid_columnconfigure(1, weight=1)
            self.bind_all_children(self.rows)
            self._sig = sig
        for t, (cnt, rate) in zip(tiers, self._cells):
            cnt.config(text=f"{t['count']:,}")
            rate.config(text=f"{fmt(t['per_hour'])}/hr")


class CrawlOverlay(OverlayBase):
    kind = "crawl"
    default_pos = (40, 520)
    _snapped = set()                    # runs this window already took a picture of

    def build(self, f):
        self.head = self.label(f, "DUNGEON CRAWL", DIM, 8, True, row=0, column=0, columnspan=2, sticky="w")
        self.zone = self.label(f, "", FG, 10, True, row=1, column=0, columnspan=2, sticky="w")
        self.big = self.label(f, "—", DIM, 26, True, row=2, column=0, columnspan=2, sticky="w")
        self.pb = self.label(f, "", DIM, 9, row=3, column=0, sticky="w")
        self.stats = self.label(f, "", DIM, 9, row=3, column=1, sticky="e", padx=(16, 0))
        f.grid_columnconfigure(1, weight=1)

    def waiting(self):
        self.head.config(text="DUNGEON CRAWL · waiting for app…")

    # -- picture of this window for the leaderboard ---------------------------------
    def _bbox(self):
        """This window on screen, in real pixels (Windows display scaling taken into account)."""
        r = self.root
        r.update_idletasks()
        box = (r.winfo_rootx(), r.winfo_rooty(), r.winfo_rootx() + r.winfo_width(), r.winfo_rooty() + r.winfo_height())
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                u = ctypes.windll.user32
                hwnd = u.GetAncestor(r.winfo_id(), 2) or r.winfo_id()
                rect = wintypes.RECT()
                u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
                old = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))     # per-monitor aware: real pixels
                try:
                    if u.GetWindowRect(hwnd, ctypes.byref(rect)):
                        box = (rect.left, rect.top, rect.right, rect.bottom)
                finally:
                    if old:
                        u.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
            except Exception:
                pass
        return box

    def _snapshot(self, rid):
        try:
            from PIL import ImageGrab
        except ImportError:
            return                      # the app draws a picture of the result instead
        alpha = self.alpha
        try:
            self.root.attributes("-alpha", 1.0)         # solid while the picture is taken
            self.root.attributes("-topmost", True)
            self.root.update()
        except tk.TclError:
            return

        def grab():
            try:
                import base64
                import io
                img = ImageGrab.grab(bbox=self._bbox(), all_screens=True)
                buf = io.BytesIO()
                img.save(buf, "PNG", optimize=True)
                self._post("/api/crawls/snapshot", {"id": rid, "png": base64.b64encode(buf.getvalue()).decode()})
            except Exception:
                pass
            finally:
                try:
                    self.root.attributes("-alpha", alpha)
                except tk.TclError:
                    pass
        self.root.after(250, grab)

    def render(self, d):
        c = d.get("crawl")
        if not c:
            self.head.config(text="DUNGEON CRAWL", fg=DIM)
            self.zone.config(text="No crawl running", fg=DIM)
            self.big.config(text="—", fg=DIM)
            self.pb.config(text="starts on the first kill after \"… is now available\"", fg=DIM)
            self.stats.config(text="")
            return
        zone = c["zone"] if len(c["zone"]) < 28 else c["zone"][:27] + "…"
        lvl = c["tier_label"] if c["tier_label"] != "?" else ""
        who = "SOLO" if c.get("party") != "group" else (
            f"MULTIPLAYER ({len(c.get('players') or []) + 1})" if c.get("players") else "MULTIPLAYER")
        self.zone.config(text=f"{zone}  {lvl}  · {who}".replace("   ·", "  ·").strip(), fg=FG)
        n = lambda k, w: f"{k} {w}" + ("" if k == 1 else "s")
        bits = [n(c["kills"], "kill")]
        if c.get("deaths"):
            bits.append(n(c["deaths"], "death"))
        if c.get("motes"):
            bits.append(f"{c['motes']} motes")
        self.stats.config(text=" · ".join(bits))
        pb = c.get("pb")
        if c["state"] == "done":
            if c.get("id") and not c.get("snap") and c["id"] not in self._snapped:
                self._snapped.add(c["id"])
                self.root.after(800, lambda rid=c["id"]: self._snapshot(rid))   # once the window shows the result
            new = c.get("new_pb")
            odd = c.get("stopped") or c.get("ended_by") == "removed"
            self.head.config(text="CRAWL ENDED BY HAND" if c.get("stopped") else
                             "CRAWL ENDED (REMOVED)" if odd else "CRAWL COMPLETE",
                             fg=DIM if odd else (GOLD if new else GREEN))
            self.big.config(text=clock(c["elapsed"]), fg=GOLD if new else FG)
            if new:
                self.pb.config(text="NEW BEST!" if pb is None else f"NEW BEST  (was {clock(pb)})", fg=GOLD)
            else:
                self.pb.config(text=f"best {clock(pb)}  +{clock(c['elapsed'] - pb)}" if pb is not None else "", fg=DIM)
            return
        if c["state"] == "ready":
            self.head.config(text="DUNGEON CRAWL  · READY", fg=GOLD)
            self.big.config(text="0:00", fg=GOLD)
            self.pb.config(text=(f"best {clock(pb)}  · " if pb is not None else "") + "starts on first kill", fg=DIM)
            return
        state = {"away": "  · OUTSIDE", "waiting": "  · NOT ENTERED YET"}.get(c["state"], "")
        self.head.config(text="DUNGEON CRAWL" + state, fg=GOLD if state else DIM)
        behind = pb is not None and c["elapsed"] > pb
        self.big.config(text=clock(c["elapsed"]), fg=GOLD if state else (RED if behind else GREEN))
        if pb is not None:
            diff = c["elapsed"] - pb
            self.pb.config(text=f"best {clock(pb)}  " + (f"+{clock(diff)}" if diff > 0 else f"-{clock(-diff)}"),
                           fg=RED if behind else DIM)
        else:
            self.pb.config(text="first timed run" if c.get("start_known", True) else "start not seen", fg=DIM)


KINDS = {"dps": DpsOverlay, "motes": MotesOverlay, "crawl": CrawlOverlay}


def run(url="http://127.0.0.1:7377", kind="dps"):
    KINDS.get(kind, DpsOverlay)(url).run()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7377",
        sys.argv[2] if len(sys.argv) > 2 else "dps")

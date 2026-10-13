"""Log integrity checks for dungeon crawl times ("was this run really logged by the game?").

A text log can always be edited by whoever owns the PC, so nothing here can
*prove* a run is genuine. What the app can do is act as a witness while you
play, and flag anything that doesn't look like the game writing the file live:

  live arrival   every line of a run must reach the app within LAG seconds of
                 the time stamped on it. Lines typed or pasted in later arrive late.
  order          time stamps must never go backwards.
  file changes   the log may only grow. If it shrinks, or bytes the app has
                 already read change, the run is flagged.
  clock check    the time between the run's first and last line is measured
                 with the PC's monotonic clock as they arrive, and must match
                 the time stamps (catches changing the Windows clock mid-run).
  app present    the start and the end must both be seen live, in the same
                 app session. Runs read from older logs are "not witnessed".

Each run also gets a hash chain over its raw lines (SHA-256, line by line) and
the lines are kept, so an exported proof can be re-checked: the chain must
match the lines, and the times must match the lines. The hashing is public
(this app is open source), so a proof file on its own is not tamper-proof -
it shows what the app witnessed. Use it together with video/screenshots.
"""
import hashlib
import json
import os
import time
import uuid

LAG = 15            # seconds a line may take to reach the app
CLOCK_SLACK = 5     # seconds of disagreement allowed between log times and the monotonic clock
SESSION = uuid.uuid4().hex[:12]     # this run of the app
VERSION = 1


def chain(prev, line):
    return hashlib.sha256((prev + "\n" + line).encode("utf-8", "replace")).hexdigest()


def new_proof(history=False):
    return {"v": VERSION, "history": history, "session": None if history else SESSION,
            "lines": 0, "late": 0, "max_lag": 0.0, "ooo": 0, "last_t": None, "chain": "",
            "start_lag": None, "start_mono": None, "start_session": None,
            "end_lag": None, "end_mono": None, "end_session": None,
            "file_events": []}


def feed(p, t, line, meta):
    """Account for one raw log line that belongs to an active run."""
    p["lines"] += 1
    p["chain"] = chain(p["chain"], line)
    if p["last_t"] is not None and t < p["last_t"] - 1:
        p["ooo"] += 1
    p["last_t"] = t if p["last_t"] is None else max(p["last_t"], t)
    if meta is None:
        p["history"] = True
        return
    lag = meta["now"] - t
    p["max_lag"] = round(max(p["max_lag"], lag), 1)
    if lag > LAG:
        p["late"] += 1


def mark(p, which, t, meta):
    """Record how the run's start / end line arrived."""
    if meta is None:
        p["history"] = True
        return
    p[which + "_lag"] = round(meta["now"] - t, 1)
    p[which + "_mono"] = meta["mono"]
    p[which + "_session"] = SESSION


def verdict(run):
    """{"status": verified | unverified | suspicious, "reasons": [...]} for a crawl run."""
    p = run.get("proof")
    if not p:
        return {"status": "unverified", "reasons": ["Recorded before this version of the app checked logs."]}
    if run["status"] == "active":
        return {"status": "pending", "reasons": ["Run still in progress."]}
    why, bad = [], False
    if p.get("history"):
        why.append("Read from older log lines: the app wasn't running and watching while this run was played.")
    if not run.get("start_known"):
        why.append("No \"is now available\" line before the run, so the start time isn't known.")
    if run["status"] != "done":
        why.append("The run never reached the Reward Chest.")
    if p.get("manual_start"):
        why.append("The timer was restarted by hand.")
    if p.get("manual_stop"):
        why.append("The timer was stopped by hand, not by the Reward Chest.")
    if not p.get("history"):
        if p["start_lag"] is None or p["start_mono"] is None:
            why.append("The first kill wasn't seen live.")
        elif p["start_lag"] > LAG:
            bad = True
            why.append(f"The first kill reached the app {p['start_lag']:.0f}s after its time stamp.")
        if run["status"] == "done":
            if p["end_lag"] is None:
                why.append("The Reward Chest line wasn't seen live.")
            elif p["end_lag"] > LAG:
                bad = True
                why.append(f"The Reward Chest line reached the app {p['end_lag']:.0f}s after its time stamp.")
        if p["start_session"] and p["end_session"] and p["start_session"] != p["end_session"]:
            why.append("The app was restarted during the run.")
        if p["late"]:
            bad = True
            why.append(f"{p['late']} line{'s' if p['late'] != 1 else ''} arrived more than {LAG}s after "
                       f"{'their' if p['late'] != 1 else 'its'} time stamp (written into the log later).")
        if p["ooo"]:
            bad = True
            why.append(f"Time stamps go backwards {p['ooo']} time{'s' if p['ooo'] != 1 else ''}.")
        if p["file_events"]:
            bad = True
            kinds = sorted({e["kind"] for e in p["file_events"]})
            why.append("The log file was " + " and ".join(kinds) + " while the run was going.")
        if (p["start_mono"] is not None and p["end_mono"] is not None and run.get("end")
                and p["start_session"] == p["end_session"]):
            wall = run["end"] - run["start"]
            mono = p["end_mono"] - p["start_mono"]
            if abs(wall - mono) > CLOCK_SLACK:
                bad = True
                why.append(f"The log says {wall:.0f}s but {mono:.0f}s actually passed (PC clock changed?).")
    if bad:
        return {"status": "suspicious", "reasons": why}
    if why:
        return {"status": "unverified", "reasons": why}
    return {"status": "verified", "reasons": ["Every line of this run was seen by the app as the game wrote it."]}


# ---------------------------------------------------------------------------- file watching
class FileWatch:
    """Notices a log file shrinking, or bytes already read being changed."""
    TAIL = 4096

    def __init__(self):
        self.tails = {}     # path -> (pos, sha1 of the bytes just before pos)

    def check(self, path, pos):
        """Call before reading new data. Returns None, "truncated" or "edited"."""
        prev = self.tails.get(path)
        if not prev:
            return None
        ppos, digest = prev
        try:
            size = os.path.getsize(path)
            if size < ppos:
                return "truncated"
            with open(path, "rb") as fh:
                start = max(0, ppos - self.TAIL)
                fh.seek(start)
                if hashlib.sha1(fh.read(ppos - start)).hexdigest() != digest:
                    return "edited"
        except OSError:
            return None
        return None

    def remember(self, path, pos):
        try:
            with open(path, "rb") as fh:
                start = max(0, pos - self.TAIL)
                fh.seek(start)
                self.tails[path] = (pos, hashlib.sha1(fh.read(pos - start)).hexdigest())
        except OSError:
            pass


# ---------------------------------------------------------------------------- proof files
def proof_path(ddir, run_id):
    d = os.path.join(ddir, "proofs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"run-{run_id}.log")


def build_proof(run, summary, lines, app_version):
    v = verdict(run)
    return {"format": "eql-assistant-crawl-proof", "format_version": VERSION, "app_version": app_version,
            "created": time.time(), "char": run["char"], "zone": run["zone"], "raw_zone": run["raw"],
            "tier": summary.get("tier_label"), "duration": summary.get("duration"),
            "start": run["start"], "end": run["end"], "kills": run["kills"], "deaths": run["deaths"],
            "verdict": v, "checks": {k: run["proof"].get(k) for k in
                                     ("lines", "late", "max_lag", "ooo", "start_lag", "end_lag", "file_events",
                                      "history")} if run.get("proof") else {},
            "chain": run.get("proof", {}).get("chain", ""), "lines": lines}


def check_proof(doc):
    """Re-check an exported proof: the hash chain and the times must match its lines."""
    from .parser import parse_line
    problems = []
    if not isinstance(doc, dict) or doc.get("format") != "eql-assistant-crawl-proof":
        return {"ok": False, "problems": ["Not an EQL Assistant crawl proof file."]}
    lines = doc.get("lines") or []
    h = ""
    for ln in lines:
        h = chain(h, ln)
    if h != doc.get("chain"):
        problems.append("The log lines don't match the proof's hash chain (the file was edited after export).")
    if doc.get("checks", {}).get("lines") not in (None, len(lines)):
        problems.append(f"The proof says {doc['checks']['lines']} lines but contains {len(lines)}.")
    times = []
    first_kill = chest = None
    for ln in lines:
        r = parse_line(ln)
        if not r:
            continue
        t, ev = r
        times.append(t)
        if first_kill is None and ev and ev.get("type") == "death" and ev.get("tgt") not in ("You", "YOU"):
            first_kill = t
        if chest is None and "from reward chest" in ln.lower():
            chest = t
    if any(b < a - 1 for a, b in zip(times, times[1:])):
        problems.append("Time stamps in the lines go backwards.")
    if first_kill is not None and chest is not None and doc.get("duration") is not None:
        d = round(chest - first_kill)
        if abs(d - doc["duration"]) > 2:
            problems.append(f"The lines give a duration of {d}s, but the proof claims {doc['duration']}s.")
    elif doc.get("verdict", {}).get("status") == "verified":
        problems.append("The lines don't contain both a first kill and a Reward Chest line.")
    return {"ok": not problems, "problems": problems, "verdict": doc.get("verdict"),
            "char": doc.get("char"), "zone": doc.get("zone"), "tier": doc.get("tier"),
            "duration": doc.get("duration"), "lines": len(lines)}


def dumps(doc):
    return json.dumps(doc, indent=1)

"""Sending finished dungeon crawls to an EQL Crawl Times leaderboard site.

POST <site>/api.php?action=app_submit, gzip'd JSON:
  format     "eql-assistant-submission"
  v          1 (fields below "proof" were added later; older sites ignore them)
  server     from the log file name (eqlog_Name_server.txt)
  classes    your three classes
  video      optional link
  proof      the run's proof (integrity.build_proof): character, dungeon, difficulty,
             time, verdict, hash chain and the raw log lines, so the site can re-check it
  party      "solo" or "group"
  group      everyone in the run: [{"name", "classes", "source", "sure", "you"}]
             source: "who" (from /who), "settings", "spells" (guessed from spells / skills seen)
  run        {"zone", "tier", "level", "duration", "party", "kills", "deaths", "start", "end"}
  screenshot {"type": "image/png", "name", "data": base64} of the crawl timer window
  edited     true when the player changed anyone's classes from what the app found
  edits      [{"name", "you", "from", "from_source", "to", "at"}]: what the log showed, and what it became
             (group entries carry "edited": true too)
  resubmit_of  the site's id of this run's previous submission (a correction), or null
  submission   1 for the first send of a run, 2+ for resubmissions
"""
import base64
import gzip
import json
import urllib.error
import urllib.parse
import urllib.request

FORMAT = "eql-assistant-submission"
TIMEOUT = 20


def endpoint(base_url):
    base = (base_url or "").strip()
    if not base:
        raise ValueError("Set the leaderboard address in Settings first.")
    if "://" not in base:
        base = "https://" + base
    u = urllib.parse.urlparse(base)
    local = u.hostname in ("localhost", "127.0.0.1", "::1")
    if u.scheme not in ("https", "http") or not u.netloc or (u.scheme == "http" and not local):
        raise ValueError("The leaderboard address must start with https://")
    path = u.path
    if path.endswith((".php", ".html")):
        path = path.rsplit("/", 1)[0]
    path = path.rstrip("/") + "/api.php"
    return urllib.parse.urlunparse((u.scheme, u.netloc, path, "", "action=app_submit", ""))


def payload(proof_doc, server, classes, video="", party="solo", group=(), run=None, png=None, png_name="crawl.png"):
    body = {"format": FORMAT, "v": 1, "server": server, "classes": list(classes), "video": video or "",
            "proof": proof_doc, "party": party, "group": list(group), "run": run or {}}
    if png:
        body["screenshot"] = {"type": "image/png", "name": png_name, "data": base64.b64encode(png).decode("ascii")}
    return body


def submit(base_url, body, app_version):
    """POST a payload. Returns the site's reply ({"ok": True, "id", "message", ...}).
    Raises ValueError with a message the player can read."""
    url = endpoint(base_url)
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=gzip.compress(raw, 6), method="POST", headers={
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Accept": "application/json",
        "User-Agent": f"EQLAssistant/{app_version}",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            reply = _json(res.read())
    except urllib.error.HTTPError as e:
        reply = _json(e.read())
        msg = reply.get("error") if isinstance(reply, dict) else None
        raise ValueError(msg or f"The leaderboard turned the run down (HTTP {e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ValueError(f"Couldn't reach the leaderboard at {urllib.parse.urlparse(url).netloc}: {reason}") from None
    if not isinstance(reply, dict) or not reply.get("ok"):
        raise ValueError((reply or {}).get("error") or "The leaderboard sent back an answer the app doesn't understand.")
    return reply


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return {}

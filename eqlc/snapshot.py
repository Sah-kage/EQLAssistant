"""Pictures of the crawl timer window for leaderboard submissions.

The crawl timer overlay takes a picture of itself when a run finishes and
sends it to the app (POST /api/crawls/snapshot). If the overlay wasn't open,
a picture of the same card is drawn here instead (needs Pillow).
"""
import base64
import os
import time

MAX_BYTES = 3 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

BG = (13, 17, 23)
FG = (230, 237, 243)
DIM = (139, 148, 158)
GOLD = (227, 179, 65)
GREEN = (63, 185, 80)


def path(ddir, run_id):
    d = os.path.join(ddir, "snapshots")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"run-{int(run_id)}.png")


def save(ddir, run_id, data_b64):
    try:
        png = base64.b64decode(data_b64, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Not a picture") from None
    if not png.startswith(PNG_MAGIC) or len(png) > MAX_BYTES:
        raise ValueError("Not a PNG picture (or too big)")
    p = path(ddir, run_id)
    with open(p, "wb") as fh:
        fh.write(png)
    return p


def load(ddir, run_id):
    try:
        with open(path(ddir, run_id), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def exists(ddir, run_id):
    return os.path.exists(path(ddir, run_id))


def clock(secs):
    secs = int(round(secs or 0))
    h, m, s = secs // 3600, secs // 60 % 60, secs % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _font(size, bold=False):
    from PIL import ImageFont
    names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else
             ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def render(summary, who=""):
    """Draw the finished-run card (like the crawl timer window). Returns PNG bytes, or None without Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    import io
    w, h = 420, 190
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    new = summary.get("new_pb")
    d.text((16, 12), "CRAWL COMPLETE", fill=GOLD if new else GREEN, font=_font(14, True))
    party = "SOLO" if summary.get("party") != "group" else f"GROUP ({len(summary.get('players') or []) + 1})"
    tier = summary.get("tier_label") or ""
    d.text((16, 36), f"{summary.get('zone', '')}  {tier if tier != '?' else ''}  · {party}", fill=FG,
           font=_font(17, True))
    d.text((16, 62), clock(summary.get("duration")), fill=GOLD if new else FG, font=_font(54, True))
    bits = [f"{summary.get('kills', 0)} kills"]
    if summary.get("deaths"):
        bits.append(f"{summary['deaths']} deaths")
    d.text((16, 136), " · ".join(bits), fill=DIM, font=_font(13))
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(summary.get("end") or time.time()))
    d.text((16, 160), f"{who}  ·  {stamp}  ·  EQL Assistant", fill=DIM, font=_font(12))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()

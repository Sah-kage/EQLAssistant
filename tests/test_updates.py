"""Update check.  Run: python -m unittest discover tests"""
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eqlc import updates as U          # noqa: E402
from eqlc import __version__           # noqa: E402


def release(tag, body="## What's new\nFix things (1.9.0)\n\n- **Deaths** tab\n\n## Download\nGet the exe."):
    return {"tag_name": tag, "html_url": f"https://github.com/Sah-kage/EQLAssistant/releases/tag/{tag}",
            "body": body, "published_at": "2026-10-24T20:00:00Z",
            "assets": [{"name": "EQLAssistant.exe",
                        "browser_download_url": f"https://github.com/Sah-kage/EQLAssistant/releases/download/{tag}/EQLAssistant.exe"},
                       {"name": "EQLAssistant.exe.sha256", "browser_download_url": "https://github.com/x"}]}


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


def opener_for(doc=None, fail=False):
    def op(req, timeout=None):
        if fail:
            raise OSError("no network")
        assert req.full_url == U.API
        return Resp(json.dumps(doc).encode())
    return op


class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(U.newer("v1.10.0", "1.9.9"))
        self.assertTrue(U.newer("1.6.5", "1.6.4"))
        self.assertTrue(U.newer("2", "1.9"))
        self.assertFalse(U.newer("v1.6.4", "1.6.4"))
        self.assertFalse(U.newer("1.6.0", "1.6"))
        self.assertFalse(U.newer("1.5.9", "1.6.0"))
        self.assertFalse(U.newer("nonsense", "1.0"))

    def test_newer_release(self):
        cfg = {}
        up = U.Updates(cfg, opener=opener_for(release("v99.0.0")))
        v = up.check()
        self.assertTrue(v["available"])
        self.assertEqual((v["latest"], v["current"]), ("99.0.0", __version__))
        self.assertTrue(v["download"].endswith("/v99.0.0/EQLAssistant.exe"))
        self.assertEqual(v["notes"], "Fix things (1.9.0)\n\n- Deaths tab")
        self.assertFalse(v["dismissed"])
        up.dismiss("99.0.0")
        self.assertTrue(up.view()["dismissed"])
        up.cfg["update_dismissed"] = "98.0.0"                          # an older "not now" doesn't hide a newer one
        self.assertFalse(up.view()["dismissed"])
        with mock.patch("webbrowser.open") as wb:
            self.assertTrue(up.open("download").endswith("EQLAssistant.exe"))
            self.assertTrue(up.open("page").endswith("/tag/v99.0.0"))
        self.assertEqual(wb.call_count, 2)

    def test_up_to_date_and_offline(self):
        up = U.Updates({}, opener=opener_for(release("v" + __version__)))
        self.assertFalse(up.check()["available"])
        up = U.Updates({}, opener=opener_for(fail=True))
        v = up.check()
        self.assertFalse(v["available"])
        self.assertIn("no network", v["error"])

    def test_only_opens_this_projects_pages(self):
        doc = release("v99.0.0")
        doc["html_url"] = "https://evil.example.com/x"
        doc["assets"][0]["browser_download_url"] = "https://evil.example.com/EQLAssistant.exe"
        up = U.Updates({}, opener=opener_for(doc))
        up.check()
        with mock.patch("webbrowser.open") as wb:
            self.assertEqual(up.open("download"), U.RELEASES)
        wb.assert_called_once_with(U.RELEASES)


if __name__ == "__main__":
    unittest.main()

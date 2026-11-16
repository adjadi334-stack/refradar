import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from refradar import web
from refradar.verify import CheckResult


def _fake_check(ref, timeout=8.0):
    return CheckResult(ref, "exists", "mocked registry answer")


class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        conn.close()
        return resp.status, body

    def _post(self, path, payload):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", path, body=json.dumps(payload),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        conn.close()
        return resp.status, body

    def test_page_is_motion_cockpit(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("RefRadar", body)
        self.assertIn("radarCanvas", body)
        self.assertIn("/api/scan-stream", body)
        self.assertIn("prefers-reduced-motion", body)

    def test_healthz(self):
        status, body = self._get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body, "ok")

    def test_scan_stream_ndjson(self):
        with mock.patch.object(web, "check_reference", side_effect=_fake_check):
            status, body = self._post("/api/scan-stream", {
                "text": "See DOI 10.1038/nature14539 and PMID 33301246."
            })
        self.assertEqual(status, 200)
        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[0]["total"], 2)
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 2)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["summary"]["total"], 2)
        self.assertEqual(len(events[-1]["results"]), 2)

    def test_scan_oneshot_still_works(self):
        def fake_all(refs, timeout=8.0, online=True):
            return [CheckResult(r, "exists", "mocked") for r in refs]

        with mock.patch.object(web, "check_references", side_effect=fake_all):
            status, body = self._post("/api/scan", {"text": "PMID 33301246"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["summary"]["total"], 1)
        self.assertEqual(data["references"][0]["verdict"], "exists")


if __name__ == "__main__":
    unittest.main()

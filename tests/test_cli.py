import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import refradar.verify as V
from refradar.cli import main


class TestCLI(unittest.TestCase):
    def test_check_text_offline_and_html_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "report.html"
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = main([
                    "check",
                    "--text",
                    "See [Attention Is All You Need](https://arxiv.org/abs/1706.03762) and ISBN 978-2-07-000000-0.",
                    "--no-net",
                    "--html",
                    str(html_path),
                ])
            self.assertEqual(rc, 0)
            self.assertIn("1706.03762", out.getvalue())
            self.assertTrue(html_path.is_file())
            html_content = html_path.read_text(encoding="utf-8")
            self.assertIn("Ref<span>Radar</span>", html_content)

    def test_check_json_and_fail_under(self):
        crossref = json.dumps({"message": {"title": ["Deep learning"]}}).encode()
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.object(V, "_http_get", return_value=(404, "", b"")):
            with redirect_stdout(out), redirect_stderr(err):
                rc = main([
                    "check",
                    "--text",
                    "Fake DOI 10.1234/fake.001",
                    "--json",
                    "--fail-under",
                    "80",
                ])
        self.assertEqual(rc, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["summary"]["score"], 0)
        self.assertEqual(payload["references"][0]["verdict"], "not_found")

        out2 = io.StringIO()
        with mock.patch.object(V, "_http_get", return_value=(200, "", crossref)):
            with redirect_stdout(out2):
                rc2 = main([
                    "check",
                    "--text",
                    "Real [Deep learning](https://doi.org/10.1038/nature14539)",
                    "--json",
                    "--fail-under",
                    "80",
                ])
        self.assertEqual(rc2, 0)
        payload2 = json.loads(out2.getvalue())
        self.assertEqual(payload2["summary"]["score"], 100)

    def test_no_references_returns_3(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["check", "--text", "Hello world with no citations at all."])
        self.assertEqual(rc, 3)

    def test_demo_offline(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["demo", "--no-net"])
        self.assertEqual(rc, 0)
        self.assertIn("demo/example-ai-output.md", out.getvalue())


if __name__ == "__main__":
    unittest.main()

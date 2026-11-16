import json
import unittest
from unittest import mock

import refradar.verify as V
from refradar.extract import Reference


def ref(kind, value, context=""):
    return Reference(kind=kind, value=value, raw=value, context=context, line=1)


def http_ok(payload_bytes, status=200, final_url=""):
    return (status, final_url, payload_bytes)


CROSSREF = json.dumps({"message": {"title": ["Deep learning"]}}).encode()
ARXIV = b"""<?xml version="1.0"?>
<response xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>1</opensearch:totalResults>
<entry><title>Attention Is All You Need</title></entry>
</response>"""
ARXIV_EMPTY = b"""<?xml version="1.0"?>
<response xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>0</opensearch:totalResults>
</response>"""
NCBI = json.dumps({"result": {"33301246": {"title": "A randomized study of things"}}}).encode()
NCBI_MISSING = json.dumps({"result": {"33301246": {"error": "cannot get document summary"}}}).encode()
OPENLIB = json.dumps({"ISBN:9780134685991": {"title": "The C++ Programming Language"}}).encode()
PAGE = b"<html><head><title>Bananas and botany</title></head><body>hi</body></html>"


class TestDoi(unittest.TestCase):
    def test_verified_with_matching_context(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(CROSSREF)):
            r = V.check_doi(ref("doi", "10.1038/nature14539", "Deep learning"), 1)
        self.assertEqual(r.verdict, "verified")
        self.assertEqual(r.found_title, "Deep learning")

    def test_mismatch_with_conflicting_context(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(CROSSREF)):
            r = V.check_doi(ref("doi", "10.1038/nature14539", "banana bread smoothie recipe"), 1)
        self.assertEqual(r.verdict, "mismatch")

    def test_exists_without_context(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(CROSSREF)):
            r = V.check_doi(ref("doi", "10.1038/nature14539"), 1)
        self.assertEqual(r.verdict, "exists")

    def test_not_found(self):
        with mock.patch.object(V, "_http_get", return_value=(404, "", b"")):
            r = V.check_doi(ref("doi", "10.1234/fake"), 1)
        self.assertEqual(r.verdict, "not_found")

    def test_unreachable(self):
        with mock.patch.object(V, "_http_get", return_value=(None, "", b"")):
            r = V.check_doi(ref("doi", "10.1038/x"), 1)
        self.assertEqual(r.verdict, "unreachable")


class TestArxiv(unittest.TestCase):
    def test_verified(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(ARXIV)):
            r = V.check_arxiv(ref("arxiv", "1706.03762", "Attention Is All You Need"), 1)
        self.assertEqual(r.verdict, "verified")

    def test_not_found(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(ARXIV_EMPTY)):
            r = V.check_arxiv(ref("arxiv", "9999.99999"), 1)
        self.assertEqual(r.verdict, "not_found")


class TestPubmed(unittest.TestCase):
    def test_exists(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(NCBI)):
            r = V.check_pmid(ref("pmid", "33301246"), 1)
        self.assertEqual(r.verdict, "exists")
        self.assertIn("randomized", r.found_title)

    def test_not_found(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(NCBI_MISSING)):
            r = V.check_pmid(ref("pmid", "33301246"), 1)
        self.assertEqual(r.verdict, "not_found")


class TestIsbn(unittest.TestCase):
    def test_invalid_checksum_never_hits_network(self):
        with mock.patch.object(V, "_http_get", side_effect=AssertionError("network called")):
            r = V.check_isbn(ref("isbn", "9782070000000"), 1)
        self.assertEqual(r.verdict, "invalid")

    def test_found(self):
        with mock.patch.object(V, "_http_get", return_value=http_ok(OPENLIB)):
            r = V.check_isbn(ref("isbn", "9780134685991"), 1)
        self.assertEqual(r.verdict, "exists")


class TestUrl(unittest.TestCase):
    def test_context_mismatch(self):
        with mock.patch.object(V, "_http_get",
                               return_value=http_ok(PAGE, final_url="https://example.org/x")):
            r = V.check_url(ref("url", "https://example.org/x", "quantum gravity unification theory"), 1)
        self.assertEqual(r.verdict, "mismatch")
        self.assertIn("Bananas", r.found_title)

    def test_dead_link(self):
        with mock.patch.object(V, "_http_get", return_value=(404, "", b"")):
            r = V.check_url(ref("url", "https://example.com/gone"), 1)
        self.assertEqual(r.verdict, "dead")

    def test_online_page_no_context(self):
        with mock.patch.object(V, "_http_get",
                               return_value=http_ok(PAGE, final_url="https://example.org/x")):
            r = V.check_url(ref("url", "https://example.org/x"), 1)
        self.assertEqual(r.verdict, "exists")


class TestScoreAndOfflineMode(unittest.TestCase):
    def test_offline_marks_unverifiable_and_score_is_none(self):
        refs = [ref("doi", "10.1038/nature14539")]
        results = V.check_references(refs, online=False)
        self.assertEqual(results[0].verdict, "unverifiable")
        self.assertIsNone(V.trust_score(results))

    def test_offline_still_flags_invalid_isbn_checksum(self):
        refs = [ref("isbn", "9782070000000"), ref("isbn", "9780134685991")]
        results = V.check_references(refs, online=False)
        self.assertEqual(results[0].verdict, "invalid")
        self.assertEqual(results[1].verdict, "unverifiable")

    def test_score_excludes_unreachable(self):
        results = [
            V.CheckResult(ref("doi", "10.1/a"), "verified", "", http_status=200),
            V.CheckResult(ref("doi", "10.1/b"), "unreachable", ""),
        ]
        self.assertEqual(V.trust_score(results), 100)

    def test_score_mixed(self):
        results = [
            V.CheckResult(ref("doi", "10.1/a"), "verified", "", http_status=200),
            V.CheckResult(ref("doi", "10.1/b"), "dead", "", http_status=404),
        ]
        self.assertEqual(V.trust_score(results), 50)

    def test_check_reference_never_raises(self):
        with mock.patch.dict(V._CHECKERS, {"doi": lambda r, t: 1 / 0}):
            r = V.check_reference(ref("doi", "10.1/x"))
        self.assertEqual(r.verdict, "unreachable")


if __name__ == "__main__":
    unittest.main()

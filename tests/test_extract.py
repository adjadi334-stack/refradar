import unittest

from refradar.extract import (
    extract_references,
    isbn_checksum_ok,
    similarity,
)


SAMPLE = """
See [Deep learning](https://arxiv.org/abs/1706.03762) and arXiv:2106.09685.
DOI 10.1038/nature14539 is canonical. Mirrored at https://doi.org/10.1038/nature14539.
PubMed: PMID 33301246 or https://pubmed.ncbi.nlm.nih.gov/33301246.
Book: ISBN 978-0-13-468599-1. Bad book: ISBN 978-2-07-000000-0.
Dead: https://example.com/nope. Unrelated: https://example.org/page.
"""


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.refs = extract_references(SAMPLE)
        self.by = {}
        for r in self.refs:
            self.by.setdefault(r.kind, []).append(r.value)

    def test_finds_arxiv_from_markdown_link(self):
        self.assertIn("1706.03762", self.by.get("arxiv", []))

    def test_finds_arxiv_bare_id(self):
        self.assertIn("2106.09685", self.by.get("arxiv", []))

    def test_finds_doi_inline_and_via_url_once(self):
        dois = self.by.get("doi", [])
        self.assertEqual(dois.count("10.1038/nature14539"), 1)  # deduplicated

    def test_finds_doi_with_dots_in_suffix(self):
        refs = extract_references("Published as DOI 10.1371/journal.pone.0000001.")
        dois = [r.value for r in refs if r.kind == "doi"]
        self.assertEqual(dois, ["10.1371/journal.pone.0000001"])

    def test_finds_pmid_inline_and_via_url(self):
        self.assertEqual(self.by.get("pmid", []).count("33301246"), 1)

    def test_finds_isbns(self):
        isbns = self.by.get("isbn", [])
        self.assertIn("9780134685991", isbns)
        self.assertIn("9782070000000", isbns)

    def test_finds_urls(self):
        urls = self.by.get("url", [])
        self.assertTrue(any("example.com" in u for u in urls))
        self.assertTrue(any("example.org" in u for u in urls))

    def test_markdown_link_keeps_context(self):
        md = [r for r in self.refs if r.value == "1706.03762"][0]
        self.assertEqual(md.context, "Deep learning")

    def test_line_numbers_are_one_based(self):
        for r in self.refs:
            self.assertGreaterEqual(r.line, 1)

    def test_deduplicates_everything(self):
        keys = [r.key() for r in self.refs]
        self.assertEqual(len(keys), len(set(keys)))


class TestIsbnChecksum(unittest.TestCase):
    def test_valid_isbn13(self):
        self.assertTrue(isbn_checksum_ok("978-0-13-468599-1"))

    def test_valid_isbn13_known(self):
        self.assertTrue(isbn_checksum_ok("9780306406157"))

    def test_invalid_isbn13(self):
        self.assertFalse(isbn_checksum_ok("978-2-07-000000-0"))

    def test_valid_isbn10(self):
        self.assertTrue(isbn_checksum_ok("0-306-40615-2"))

    def test_valid_isbn10_with_x(self):
        self.assertTrue(isbn_checksum_ok("0-8044-2957-X"))

    def test_invalid_length(self):
        self.assertFalse(isbn_checksum_ok("12345"))


class TestSimilarity(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(similarity("deep learning", "deep learning"), 1.0)

    def test_short_context_inside_long_title(self):
        self.assertGreaterEqual(
            similarity("attention is all you need",
                       "Attention is all you need: transformers for machine translation"),
            0.99)

    def test_unrelated(self):
        self.assertLess(similarity("banana bread recipe", "quantum chromodynamics lattice"), 0.1)

    def test_empty(self):
        self.assertEqual(similarity("", "anything"), 0.0)


if __name__ == "__main__":
    unittest.main()

"""Network verification of extracted references.

Every check goes through a single network choke point (_http_get) so tests
can run fully offline by monkeypatching it. Verdicts are honest: when a
network error occurs the reference is reported as "unreachable", never as
fake.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .extract import Reference, isbn_checksum_ok, similarity

MAX_BYTES = 256 * 1024
USER_AGENT = "RefRadar/1.0 (+https://github.com/refradar) citation checker"

VERDICT_LABEL = {
    "verified": "Verified",
    "exists": "Exists (no context to compare)",
    "partial": "Weak match",
    "mismatch": "MISMATCH (title differs)",
    "dead": "DEAD LINK (HTTP error)",
    "not_found": "NOT FOUND",
    "invalid": "INVALID (bad checksum)",
    "unreachable": "Unreachable (network/rate-limit)",
    "unverifiable": "Unverifiable",
}

_SCORES = {
    "verified": 100,
    "exists": 85,
    "partial": 55,
    "mismatch": 15,
    "dead": 0,
    "not_found": 0,
    "invalid": 0,
    # "unreachable" is excluded from the score
}


@dataclass
class CheckResult:
    ref: Reference
    verdict: str
    detail: str = ""
    found_title: str = ""
    http_status: Optional[int] = None
    similarity: Optional[float] = None

    @property
    def score(self) -> Optional[int]:
        return _SCORES.get(self.verdict)


# ----------------------------------------------------------- HTTP helper ---

def _http_get(url: str, timeout: float) -> Tuple[Optional[int], str, bytes]:
    """GET *url*; never raises. Returns (status|None, final_url, body)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/xml, text/html;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return getattr(resp, "status", 200) or 200, resp.geturl(), resp.read(MAX_BYTES)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(MAX_BYTES)
        except Exception:
            body = b""
        return exc.code, exc.geturl() or url, body
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, url, b""


# ------------------------------------------------------------- verifiers ---

def _title_verdict(ref: Reference, title: str) -> Tuple[str, Optional[float]]:
    """Compare the reference's own context with the title we found."""
    if ref.context and len(ref.context.split()) >= 2:
        sim = similarity(ref.context, title)
        if sim >= 0.45:
            return "verified", sim
        if sim >= 0.22:
            return "partial", sim
        return "mismatch", sim
    return "exists", None


def check_doi(ref: Reference, timeout: float) -> CheckResult:
    status, _, body = _http_get(f"https://api.crossref.org/works/{ref.value}", timeout)
    if status is None:
        return CheckResult(ref, "unreachable", "Crossref API unreachable")
    if status == 404:
        return CheckResult(ref, "not_found", "DOI not registered at Crossref")
    if status == 429:
        return CheckResult(ref, "unreachable", "Crossref rate limit reached (retry later)")
    if status >= 400:
        return CheckResult(ref, "unreachable", f"Crossref returned HTTP {status}", http_status=status)
    try:
        message = json.loads(body.decode("utf-8", "replace"))["message"]
        titles = message.get("title") or []
        title = titles[0].strip() if titles else ""
    except Exception:
        return CheckResult(ref, "unreachable", "Could not parse Crossref response", http_status=status)
    verdict, sim = _title_verdict(ref, title) if title else ("exists", None)
    return CheckResult(ref, verdict, f"DOI resolved via Crossref", found_title=title,
                       http_status=status, similarity=sim)


def check_arxiv(ref: Reference, timeout: float) -> CheckResult:
    status, _, body = _http_get(
        f"https://export.arxiv.org/api/query?id_list={ref.value}", timeout)
    if status is None:
        return CheckResult(ref, "unreachable", "arXiv API unreachable")
    if status >= 400:
        return CheckResult(ref, "unreachable", f"arXiv returned HTTP {status}", http_status=status)
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return CheckResult(ref, "unreachable", "Could not parse arXiv response", http_status=status)
    ns = {"atom": "http://www.w3.org/2005/Atom",
          "opensearch": "http://a9.com/-/spec/opensearch/1.1/"}
    total = root.findtext("opensearch:totalResults", default="0", namespaces=ns)
    if total.strip() == "0":
        return CheckResult(ref, "not_found", "No arXiv paper with this identifier", http_status=status)
    title = (root.findtext("atom:entry/atom:title", default="", namespaces=ns) or "").strip()
    title = re.sub(r"\s+", " ", title)
    verdict, sim = _title_verdict(ref, title) if title else ("exists", None)
    return CheckResult(ref, verdict, "Found on arXiv", found_title=title,
                       http_status=status, similarity=sim)


def check_pmid(ref: Reference, timeout: float) -> CheckResult:
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
           f"?db=pubmed&id={ref.value}&retmode=json")
    status, _, body = _http_get(url, timeout)
    if status is None:
        return CheckResult(ref, "unreachable", "NCBI E-utilities unreachable")
    if status >= 400:
        return CheckResult(ref, "unreachable", f"NCBI returned HTTP {status}", http_status=status)
    try:
        result = json.loads(body.decode("utf-8", "replace")).get("result", {})
        entry = result.get(ref.value)
        if not entry or entry.get("error"):
            return CheckResult(ref, "not_found", "No PubMed record with this ID", http_status=status)
        title = (entry.get("title") or "").strip()
    except Exception:
        return CheckResult(ref, "unreachable", "Could not parse NCBI response", http_status=status)
    verdict, sim = _title_verdict(ref, title) if title else ("exists", None)
    return CheckResult(ref, verdict, "Found in PubMed", found_title=title,
                       http_status=status, similarity=sim)


def check_isbn(ref: Reference, timeout: float) -> CheckResult:
    if not isbn_checksum_ok(ref.value):
        return CheckResult(ref, "invalid", "ISBN checksum is invalid — cannot exist as printed")
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{ref.value}&jscmd=data&format=json"
    status, _, body = _http_get(url, timeout)
    if status is None:
        return CheckResult(ref, "unreachable", "Open Library unreachable (checksum itself is valid)")
    if status >= 400:
        return CheckResult(ref, "unreachable", f"Open Library returned HTTP {status}", http_status=status)
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return CheckResult(ref, "unreachable", "Could not parse Open Library response", http_status=status)
    entry = data.get(f"ISBN:{ref.value}")
    if not entry:
        return CheckResult(ref, "not_found", "Checksum OK but no Open Library record",
                           http_status=status)
    title = (entry.get("title") or "").strip()
    verdict, sim = _title_verdict(ref, title) if title else ("exists", None)
    return CheckResult(ref, verdict, "Found in Open Library", found_title=title,
                       http_status=status, similarity=sim)


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _extract_title(body: bytes) -> str:
    m = _TITLE_RE.search(body.decode("utf-8", "replace"))
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()


def check_url(ref: Reference, timeout: float) -> CheckResult:
    status, final_url, body = _http_get(ref.value, timeout)
    if status is None:
        return CheckResult(ref, "unreachable", "Could not reach the server")
    if status >= 400:
        return CheckResult(ref, "dead", f"HTTP {status}", http_status=status)
    title = _extract_title(body)
    detail = f"HTTP {status}"
    if final_url and final_url.rstrip("/") != ref.value.rstrip("/"):
        detail += " (redirected)"
    if title:
        verdict, sim = _title_verdict(ref, title)
        if ref.context:
            return CheckResult(ref, verdict, detail, found_title=title,
                               http_status=status, similarity=sim)
        return CheckResult(ref, "exists", detail + " — page online", found_title=title,
                           http_status=status)
    return CheckResult(ref, "exists", detail + " — page online (no title found)",
                       http_status=status)


_CHECKERS = {
    "doi": check_doi,
    "arxiv": check_arxiv,
    "pmid": check_pmid,
    "isbn": check_isbn,
    "url": check_url,
}


def check_reference(ref: Reference, timeout: float = 8.0) -> CheckResult:
    checker = _CHECKERS.get(ref.kind)
    if checker is None:
        return CheckResult(ref, "unverifiable", "Unsupported reference type")
    try:
        return checker(ref, timeout)
    except Exception as exc:  # last-resort guard: never crash a scan
        return CheckResult(ref, "unreachable", f"Unexpected error: {exc.__class__.__name__}")


def check_references(refs: List[Reference], timeout: float = 8.0,
                     max_workers: int = 6, online: bool = True) -> List[CheckResult]:
    if not online:
        out: List[CheckResult] = []
        for r in refs:
            if r.kind == "isbn" and not isbn_checksum_ok(r.value):
                out.append(CheckResult(
                    r, "invalid", "ISBN checksum is invalid — cannot exist as printed"))
            else:
                out.append(CheckResult(
                    r, "unverifiable", "Offline mode (--no-net): extraction only"))
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda r: check_reference(r, timeout), refs))


# ------------------------------------------------------------------ score ---

def trust_score(results: List[CheckResult]) -> Optional[int]:
    scored = [r.score for r in results if r.score is not None]
    if not scored:
        return None
    return round(sum(scored) / len(scored))


def trust_label(score: Optional[int]) -> str:
    if score is None:
        return "Inconclusive"
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 40:
        return "Mixed — review the flagged references"
    return "Low trust — most references look fabricated or broken"

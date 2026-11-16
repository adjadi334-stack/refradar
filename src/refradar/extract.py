"""Extraction of verifiable references from raw text.

Pure standard library. No network access happens here — this module only
finds, normalizes, deduplicates and validates identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Reference:
    """A single verifiable reference found in a text."""
    kind: str                # "url" | "doi" | "arxiv" | "pmid" | "isbn"
    value: str               # normalized identifier / URL
    raw: str                 # exact text as found
    context: str = ""        # markdown link text / surrounding hint, if any
    line: int = 0            # 1-based line number where it was found

    def key(self) -> str:
        return f"{self.kind}:{self.value.lower()}"


# ---------------------------------------------------------------- regexes ---

MD_LINK_RE = re.compile(r"\[([^\]\n]{1,300})\]\(\s*(https?://[^)\s]+)\s*\)")
URL_RE = re.compile(r"https?://[^\s<>\)\]\"'`]+")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;!?)\]}\"'<>\u00bb]+)")
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
PMID_RE = re.compile(r"PMID:?\s*(\d{2,9})\b", re.IGNORECASE)
PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{2,9})")
DOI_URL_RE = re.compile(r"(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,9}/[^\s),;<>\"']+)", re.IGNORECASE)
ISBN_RE = re.compile(r"ISBN(?:-1[03])?[-:\s]*([0-9Xx][0-9Xx\-\s]{8,18}[0-9Xx])")

_TRAILING_PUNCT = ".,;:)]}\"'>»"


# ------------------------------------------------------------- ISBN utils ---

def _isbn_digits(candidate: str) -> str:
    return re.sub(r"[-\s]", "", candidate).upper()


def isbn_checksum_ok(isbn: str) -> bool:
    """Validate ISBN-10 or ISBN-13 checksum. Input may contain hyphens."""
    s = _isbn_digits(isbn)
    if len(s) == 10:
        total = 0
        for i, ch in enumerate(s):
            if ch == "X":
                if i != 9:
                    return False
                d = 10
            elif ch.isdigit():
                d = int(ch)
            else:
                return False
            total += d * (10 - i)
        return total % 11 == 0
    if len(s) == 13:
        if not s.isdigit():
            return False
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(s))
        return total % 10 == 0
    return False


# ------------------------------------------------------------ similarity ----

STOPWORDS = {
    # English
    "the", "and", "for", "with", "from", "that", "this", "into", "are", "was",
    "were", "their", "there", "has", "have", "been", "its", "not", "you", "all",
    # French
    "les", "des", "une", "dans", "pour", "avec", "sur", "est", "sont", "par",
    "aux", "une", "leur", "leurs", "entre", "vers", "sous", "plus", "comme",
}


def _tokens(text: str) -> set:
    return {
        tok
        for tok in re.findall(r"[a-z0-9\u00e0-\u00ff]+", text.lower())
        if tok not in STOPWORDS and len(tok) > 2
    }


def similarity(a: str, b: str) -> float:
    """Containment-aware token overlap in [0, 1].

    Uses max(Jaccard, |A∩B| / min(|A|, |B|)) so that a short markdown link
    text quoted from a longer paper title still scores as a match.
    """
    t1, t2 = _tokens(a), _tokens(b)
    if not t1 or not t2:
        return 0.0
    inter = len(t1 & t2)
    union = len(t1 | t2)
    jaccard = inter / union if union else 0.0
    containment = inter / min(len(t1), len(t2))
    return max(jaccard, containment)


# ------------------------------------------------------------ extraction ----

def _clean_url(url: str) -> str:
    return url.rstrip(_TRAILING_PUNCT)


def _clean_doi(doi: str) -> str:
    doi = doi.strip().rstrip(_TRAILING_PUNCT)
    # strip a trailing DOI fragment that is only closing punctuation
    return doi


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _add(refs: List[Reference], seen: set, ref: Reference) -> None:
    if ref.key() in seen:
        return
    seen.add(ref.key())
    refs.append(ref)


def extract_references(text: str) -> List[Reference]:
    """Find every verifiable reference in *text*. Order: by line of appearance."""
    refs: List[Reference] = []
    seen: set = set()
    md_spans: List[tuple] = []

    # 1) Markdown links carry the richest context (the visible text).
    for m in MD_LINK_RE.finditer(text):
        context, url = m.group(1).strip(), _clean_url(m.group(2))
        md_spans.append(m.span())
        _add(refs, seen, _classify_url(url, text, m.start(), raw=m.group(0), context=context))

    # 2) Bare URLs (skip ones already inside a markdown link).
    for m in URL_RE.finditer(text):
        start = m.start()
        if any(a <= start < b for a, b in md_spans):
            continue
        url = _clean_url(m.group(0))
        _add(refs, seen, _classify_url(url, text, start, raw=m.group(0), context=""))

    # 3) DOIs written inline (doi:10.xxxx/... or bare 10.xxxx/...).
    for m in DOI_URL_RE.finditer(text):
        doi = _clean_doi(m.group(1))
        _add(refs, seen, Reference("doi", doi.lower(), m.group(0), "", _line_of(text, m.start())))
    for m in DOI_RE.finditer(text):
        doi = _clean_doi(m.group(1))
        _add(refs, seen, Reference("doi", doi.lower(), m.group(0), "", _line_of(text, m.start())))

    # 4) arXiv identifiers.
    for m in ARXIV_RE.finditer(text):
        aid = m.group(1) + (m.group(2) or "")
        _add(refs, seen, Reference("arxiv", aid.lower(), m.group(0), "", _line_of(text, m.start())))
    for m in ARXIV_URL_RE.finditer(text):
        aid = m.group(1) + (m.group(2) or "")
        _add(refs, seen, Reference("arxiv", aid.lower(), m.group(0), "", _line_of(text, m.start())))

    # 5) PubMed identifiers.
    for m in PMID_RE.finditer(text):
        _add(refs, seen, Reference("pmid", m.group(1), m.group(0), "", _line_of(text, m.start())))
    for m in PUBMED_URL_RE.finditer(text):
        _add(refs, seen, Reference("pmid", m.group(1), m.group(0), "", _line_of(text, m.start())))

    # 6) ISBNs (validated offline by checksum).
    for m in ISBN_RE.finditer(text):
        cand = _isbn_digits(m.group(1))
        if len(cand) in (10, 13):
            _add(refs, seen, Reference("isbn", cand, m.group(0).strip(), "", _line_of(text, m.start())))

    refs.sort(key=lambda r: (r.line, r.kind, r.value))
    return refs


def _classify_url(url: str, text: str, pos: int, raw: str, context: str) -> Reference:
    """Turn a URL into a richer reference when it wraps a known identifier."""
    line = _line_of(text, pos)
    low = url.lower()

    m = DOI_URL_RE.search(low)
    if m:
        return Reference("doi", _clean_doi(m.group(1)).lower(), raw, context, line)

    m = ARXIV_URL_RE.search(low)
    if m:
        aid = m.group(1) + (m.group(2) or "")
        return Reference("arxiv", aid.lower(), raw, context, line)

    m = PUBMED_URL_RE.search(low)
    if m:
        return Reference("pmid", m.group(1), raw, context, line)

    return Reference("url", url, raw, context, line)

<p align="center">
  <img src="assets/logo.svg" alt="RefRadar" width="300">
</p>

<h1 align="center">RefRadar — the anti-hallucination checker for AI-generated references</h1>

<p align="center">
  <em>ChatGPT, Claude, Gemini and friends invent references.<br/>
  RefRadar finds them before they embarrass you.</em>
</p>

<p align="center">
  <strong>English</strong> · <a href="README.fr.md">Français</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-%E2%89%A5%203.10-3776ab.svg" alt="Python ≥ 3.10"></a>
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen.svg" alt="Zero dependencies">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version 1.0.0">
</p>

---

## The problem nobody had to explain to you

Ask any LLM for a bibliography and you'll get plausible-looking papers that don't exist:
realistic DOIs pointing at nothing, arXiv IDs from a parallel universe, URLs that 404,
ISBNs with broken checksums. If you publish, submit, or cite AI-assisted work, **you** are
responsible for every reference in it — and manually checking 40 citations against Crossref,
arXiv, NCBI and Open Library is a miserable afternoon.

Existing solutions are commercial fact-checking platforms or academic scripts glued together.
There was no small, free, local, open-source tool that just reads a document and tells you
*"these 5 references are fake or dead, here is the proof."*

That's RefRadar.

## What it does

| | |
|---|---|
| **Extracts** | URLs, DOIs, arXiv IDs, PubMed IDs, ISBNs (from inline text, markdown links and raw input) |
| **Verifies** | Does the DOI exist at Crossref? The paper on arXiv? The PMID in PubMed? The ISBN valid *and* registered? The URL alive? |
| **Cross-checks titles** | Compares the title the AI claims (your markdown link text / context) with the actual registered title — catches "right ID, wrong paper" inventions |
| **Scores** | A **Trust Score** /100 with a per-reference verdict: `Verified · Exists · Weak match · Mismatch · Not found · Dead link · Invalid ISBN · Unreachable` |
| **Reports** | Human-readable terminal output, CI-friendly exit codes (`--fail-under`), machine-readable JSON, self-contained offline HTML report |
| **Interfaces** | CLI (`refradar check`) **and** a local web app (`refradar web`) — a real-time telemetry cockpit: results stream in over NDJSON as each registry answers, with an interactive radar, live Trust Score gauge and expandable evidence drawers. Same engine, zero dependencies |

Everything is Python standard library only. `pip install .` and go. No API keys, no accounts,
no telemetry, no cloud.

## Demo

```console
$ python -m refradar demo

RefRadar scan of demo/example-ai-output.md
============================================================
[OK]   L3     ARXIV 1706.03762 — “Attention Is All You Need”
        → Found on arXiv
[MISS] L4     ARXIV 9999.99999 — “A later replication”
        → No arXiv paper with this identifier
[OK?]  L7     DOI   10.1038/nature14539
        → DOI resolved via Crossref — Deep learning
[MISS] L8     DOI   10.1234/refradar.fake.9.9.9
        → DOI not registered at Crossref
[OK?]  L11    PMID  33301246
        → Found in PubMed
[DEAD] L12    URL   https://example.com/definitely-not-a-real-study-refradar
        → HTTP 404
[OK?]  L15    ISBN  9780134685991
        → Found in Open Library
[BAD ] L16    ISBN  9782070000000
        → ISBN checksum is invalid — cannot exist as printed
------------------------------------------------------------
Summary: 8 reference(s) — 1 invalid, 1 not_found, 2 ok, 1 dead, 1 missing…
Trust score: 43/100 — Mixed — review the flagged references
```

*(Exact titles/statuses depend on the live APIs at scan time.)*

## Install

Requires Python ≥ 3.10. Zero runtime dependencies.

```bash
git clone https://github.com/adjadi334-stack/refradar.git   # or unzip the archive
cd refradar
pip install .            # installs the `refradar` command
```

No pip? Run it straight from the source tree:

```bash
PYTHONPATH=src python -m refradar demo
```

## Usage

### CLI

```bash
refradar check report.md                 # scan a file
refradar check chapter1.md chapter2.md   # several files
cat answer.txt | refradar check          # scan stdin (great with pipes)
refradar check --text "DOI 10.1038/nature14539"
refradar check report.md --html report.html   # + self-contained HTML report
refradar check report.md --json               # for scripting
refradar check report.md --no-net             # extraction only, no network calls
refradar check report.md --fail-under 80      # exit 1 below score 80 → CI gate
```

Exit codes: `0` ok · `1` below `--fail-under` · `3` nothing to scan · errors print to stderr.

### Web app (local, no install of anything else)

```bash
refradar web            # http://127.0.0.1:8787
refradar web --port 9000
```

Paste text → **Verify references** → get verdicts, a Trust Score and a downloadable
HTML report. Everything runs on your machine; the only outbound traffic is the
verification calls themselves (Crossref / arXiv / NCBI / Open Library / the URLs you cite).

### In CI (block hallucinated references in docs)

```yaml
- run: refradar check docs/**/*.md --fail-under 80
```

### ISBN checksum validation — fully offline

Even with no network, RefRadar validates ISBN-10/13 checksums locally and flags
structurally impossible identifiers instantly.

## How it works

1. **Extract** — regex + markdown-awareness pass finds identifiers (this step is offline).
2. **Classify & deduplicate** — `https://doi.org/10.1038/x`, bare `10.1038/x` and `doi:10.1038/x`
   all collapse into one canonical DOI reference. Line numbers and link-text context are kept.
3. **Verify** — each reference is checked against its authoritative registry:
   Crossref (DOIs) · arXiv API · NCBI E-utilities (PMIDs) · Open Library (ISBNs) · HTTP fetch (URLs).
4. **Title similarity** — when the citation gives a claimed title (markdown link text), it is compared
   to the registry title with containment-aware token overlap (Jaccard + capture ratio):
   `≥ 0.45` Verified · `0.22–0.45` Weak match · `< 0.22` Mismatch.
5. **Score** — `verified=100 · exists=85 · partial=55 · mismatch=15 · dead/not_found/invalid=0`;
   network-unreachable references are excluded from the average, never counted as fake.

## Limitations — read this before trusting it

- RefRadar **flags suspicion; it does not prove truth.** A real paper can support a false claim.
- URL checking tells you a page *responded*, not that it's *what the AI said it was* — prefer DOIs/PMIDs.
- Title matching is heuristic (language, subtitles, transliteration can differ). Treat `Weak match` as "look closer", not as guilt.
- Registry coverage: Crossref/DataCite-DOIs outside Crossref may show as unreachable; the ISBN chapter is best with Open Library.
- Rate limits: heavy scans of DOIs hit Crossref's public pool; use `--timeout` and retry later, or batch with `--fail-under` in CI.
- It cannot see paywalled content behind auth walls — the reference is checked against metadata, not full text.

## Roadmap

- [ ] DataCite + OpenAlex as DOI registries (wider coverage)
- [ ] Quoted-text grounding: does the cited work contain the quoted claim? (opt-in, retrieval-based)
- [ ] BibTeX/EndNote export of verified references
- [ ] Browser extension (scan the page you're reading)
- [ ] `--format sarif` for GitHub code scanning
- [ ] French legal citations (Légifrance / EUR-Lex APIs)

## Publishing this repository to GitHub

```bash
cd refradar
git init && git add . && git commit -m "RefRadar 1.0.0"
gh repo create refradar --public --source=. --push   # GitHub CLI
# …or create an empty repo on github.com, then:
git remote add origin git@github.com:adjadi334-stack/refradar.git
git branch -M main && git push -u origin main
```

Before pushing: ensure `pyproject.toml` and the READMEs point to your GitHub account,
and swap `assets/logo.svg` if you want your own branding.

## Contributing & license

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed; see [LICENSE](LICENSE).

*RefRadar flags suspicious references. It is a smoke detector, not a fire marshal.*

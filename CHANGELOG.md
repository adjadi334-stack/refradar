# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-16

### Added

- **Reference extraction**: Regex-based detection of URLs, DOIs, arXiv IDs, PubMed IDs (PMID), and ISBNs from plain text, Markdown links, and stdin.
- **Reference verification**: Automatic checks against authoritative registries — Crossref (DOIs), arXiv API (preprints), NCBI E-utilities (PMIDs), Open Library (ISBNs), and HTTP fetch (URLs).
- **Title cross-checking**: Compares the title claimed by the AI (Markdown link text) with the actual registered title using Jaccard similarity — catches "right ID, wrong paper" hallucinations.
- **Trust Score**: Per-scan score out of 100 with per-reference verdicts: `Verified`, `Exists`, `Weak match`, `Mismatch`, `Not found`, `Dead link`, `Invalid ISBN`, `Unreachable`.
- **CLI interface**: Command-line tool `refradar check` with support for files, stdin, `--text`, `--json`, `--html`, `--no-net`, and `--fail-under` for CI gating.
- **Web app**: Local browser-based telemetry cockpit (`refradar web`) with real-time NDJSON streaming, interactive radar chart, live Trust Score gauge, and expandable evidence drawers.
- **Offline ISBN validation**: ISBN-10/13 checksum verification works entirely without network access.
- **CI/CD integration**: GitHub Actions workflow running smoke tests on Python 3.10 through 3.13; `--fail-under` exit code for pipeline gates.
- **Zero dependencies**: Built entirely with Python standard library — no external packages required.
- **Documentation**: Bilingual README (English/French), CONTRIBUTING guide, bug report and feature request templates, PR template with checklist.
- **Demo**: Example file with real and fake references to demonstrate the tool out of the box.
- **Logo**: SVG logo in `assets/logo.svg`.

### Notes

- RefRadar flags suspicion; it does not prove truth. A real paper can support a false claim.
- URL checking confirms a page responded, not that it is what the AI said it was — prefer DOIs/PMIDs.
- Title matching is heuristic (language, subtitles, transliteration can differ).

[Unreleased]: https://github.com/adjadi334-stack/refradar/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/adjadi334-stack/refradar/releases/tag/v1.0.0

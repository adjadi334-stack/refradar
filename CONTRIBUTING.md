# Contributing to RefRadar

Thanks for helping make AI outputs more honest. A few ground rules:

## Setup

```bash
git clone <your fork>
cd refradar
pip install -e .
python -m unittest discover -s tests -v   # must stay green
```

## Principles

1. **Zero runtime dependencies.** The standard library is a feature — it keeps installs
   trivial everywhere (students, CI, sandboxes). Add dev-only tools freely, never runtime ones
   without a very strong argument.
2. **Never crash a scan.** A verifier may only produce a verdict, never an exception.
   Network failures are `unreachable`, not fake.
3. **Honest verdicts over confident ones.** If we can't tell, we say so (`unreachable`,
   `exists`) — we never pretend certainty we don't have.
4. **Registry of truth.** Each identifier type maps to one authoritative registry.
   New identifiers (e.g. OpenAlex, Handle.net, HAL for French research) are welcome.

## Adding a new reference type

1. Add a `Reference.kind` and its regex in `extract.py` (+ tests in `tests/test_extract.py`).
2. Add a `check_*` function in `verify.py` that goes **only** through `_http_get` (+ mocked tests).
3. Add the HTML badge text in `report.py`.
4. Document it in the README table — in both `README.md` and `README.fr.md`.

## Reporting false positives/negatives

Open an issue with the exact text scanned, the expected verdict, and the actual one.
Misclassification reports include a small reproducer in the issue template when possible.

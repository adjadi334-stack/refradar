"""Command line interface: `refradar check|web|demo`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .extract import extract_references
from .report import render_html, render_json, render_text
from .verify import check_references

MAX_INPUT_BYTES = 5 * 1024 * 1024


def _read_inputs(args) -> str:
    if args.text is not None:
        return args.text
    if args.files:
        chunks = []
        for name in args.files:
            path = Path(name)
            if not path.is_file():
                raise SystemExit(f"refradar: no such file: {name}")
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(chunks)
    if not sys.stdin.isatty():
        data = sys.stdin.read(MAX_INPUT_BYTES)
        if data:
            return data
    raise SystemExit("refradar: nothing to scan. Pass files, --text, or pipe input on stdin.\n"
                     "Example:  cat report.md | refradar check")


def cmd_check(args) -> int:
    source_desc = ", ".join(args.files) if args.files else ("stdin" if args.text is None else "--text")
    text = _read_inputs(args)
    refs = extract_references(text)
    if not refs:
        print("RefRadar: no verifiable references found "
              "(looked for URLs, DOIs, arXiv IDs, PubMed IDs and ISBNs).", file=sys.stderr)
        return 3
    results = check_references(refs, timeout=args.timeout, online=not args.no_net)

    if args.json:
        print(render_json(results))
    else:
        print(render_text(results, source_desc))

    if args.html:
        Path(args.html).write_text(render_html(results, source_desc), encoding="utf-8")
        print(f"HTML report written to {args.html}", file=sys.stderr)

    if args.fail_under is not None:
        from .verify import trust_score
        score = trust_score(results)
        if score is not None and score < args.fail_under:
            print(f"refradar: trust score {score} < required {args.fail_under}", file=sys.stderr)
            return 1
    return 0


def cmd_web(args) -> int:
    from .web import serve
    return serve(host=args.host, port=args.port)


def cmd_demo(args) -> int:
    sample = Path(__file__).resolve().parent.parent.parent / "demo" / "example-ai-output.md"
    text = sample.read_text(encoding="utf-8") if sample.is_file() else DEMO_FALLBACK
    refs = extract_references(text)
    results = check_references(refs, timeout=args.timeout, online=not args.no_net)
    print(render_text(results, "demo/example-ai-output.md"))
    if args.no_net:
        print("(offline demo — rerun without --no-net to actually verify the references)")
    return 0


DEMO_FALLBACK = (
    "See [Attention is all you need](https://arxiv.org/abs/1706.03762). "
    "A 2024 study (https://example.com/fake-paper) proved otherwise. "
    "DOI 10.1038/s41586-020-2649-2 // fake DOI 10.1038/s41586-0000-00000-x"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refradar",
        description="The anti-hallucination checker for AI-generated references.")
    parser.add_argument("--version", action="version", version=f"refradar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="scan text/files/stdin and verify references")
    p_check.add_argument("files", nargs="*", help="files to scan (UTF-8)")
    p_check.add_argument("--text", default=None, help="raw text to scan")
    p_check.add_argument("--json", action="store_true", help="print machine-readable JSON")
    p_check.add_argument("--html", metavar="FILE", default=None, help="also write a self-contained HTML report")
    p_check.add_argument("--no-net", action="store_true", help="extract only; no network calls")
    p_check.add_argument("--timeout", type=float, default=8.0, help="per-request timeout in seconds (default: 8)")
    p_check.add_argument("--fail-under", type=int, default=None, metavar="N",
                         help="exit 1 if the trust score is below N (useful in CI)")
    p_check.set_defaults(func=cmd_check)

    p_web = sub.add_parser("web", help="launch the local web app (default http://127.0.0.1:8787)")
    p_web.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=8787, help="port (default: 8787)")
    p_web.set_defaults(func=cmd_web)

    p_demo = sub.add_parser("demo", help="scan the bundled example (great first run)")
    p_demo.add_argument("--no-net", action="store_true", help="extract only; no network calls")
    p_demo.add_argument("--timeout", type=float, default=8.0)
    p_demo.set_defaults(func=cmd_demo)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

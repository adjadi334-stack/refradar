"""RefRadar — the anti-hallucination checker for AI-generated references.

RefRadar extracts verifiable references (URLs, DOIs, arXiv IDs, PubMed IDs,
ISBNs) from any text — typically AI-generated — and checks whether they
actually exist and whether their real title matches the context they are
cited in.

It flags suspicious references. It does not replace your own critical
judgement: always verify references that matter to you.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]

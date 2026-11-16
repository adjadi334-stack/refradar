"""Rendering of scan results: human text, JSON, self-contained animated HTML."""

from __future__ import annotations

import html
import json
from typing import List

from .verify import CheckResult, VERDICT_LABEL, trust_label, trust_score

_TEXT_ICON = {
    "verified": "[OK]  ",
    "exists": "[OK?] ",
    "partial": "[WARN]",
    "mismatch": "[FAKE]",
    "dead": "[DEAD]",
    "not_found": "[MISS]",
    "invalid": "[BAD ]",
    "unreachable": "[SKIP]",
    "unverifiable": "[SKIP]",
}

_HTML_BADGE = {
    "verified": ("verified", "Verified"),
    "exists": ("exists", "Exists"),
    "partial": ("partial", "Weak match"),
    "mismatch": ("bad", "Mismatch"),
    "dead": ("bad", "Dead link"),
    "not_found": ("bad", "Not found"),
    "invalid": ("bad", "Invalid ISBN"),
    "unreachable": ("skip", "Unreachable"),
    "unverifiable": ("skip", "Unverifiable"),
}

_VERDICT_COLOR = {
    "verified": "#34d399",
    "exists": "#67e8f9",
    "partial": "#fbbf24",
    "mismatch": "#fb7185",
    "dead": "#fb7185",
    "not_found": "#fb7185",
    "invalid": "#fb7185",
    "unreachable": "#94a3b8",
    "unverifiable": "#94a3b8",
}


def summarize(results: List[CheckResult]) -> dict:
    score = trust_score(results)
    counts: dict = {}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    return {
        "total": len(results),
        "score": score,
        "label": trust_label(score),
        "counts": counts,
    }


def result_to_dict(r: CheckResult, index: int = 0) -> dict:
    return {
        "index": index,
        "kind": r.ref.kind,
        "value": r.ref.value,
        "line": r.ref.line,
        "context": r.ref.context,
        "verdict": r.verdict,
        "verdict_label": VERDICT_LABEL.get(r.verdict, r.verdict),
        "detail": r.detail,
        "found_title": r.found_title,
        "http_status": r.http_status,
        "similarity": (round(r.similarity, 3) if r.similarity is not None else None),
    }


def to_dict(results: List[CheckResult]) -> dict:
    return {
        "summary": summarize(results),
        "references": [result_to_dict(r, i) for i, r in enumerate(results)],
    }


def render_text(results: List[CheckResult], source: str = "") -> str:
    s = summarize(results)
    lines = ["", f"RefRadar scan{' of ' + source if source else ''}", "=" * 60]
    for r in results:
        icon = _TEXT_ICON.get(r.verdict, "[????]")
        loc = f"L{r.ref.line:<4}" if r.ref.line else "    "
        ctx = f' — “{r.ref.context[:80]}”' if r.ref.context else ""
        lines.append(f"{icon} {loc} {r.ref.kind.upper():<5} {r.ref.value}{ctx}")
        if r.verdict == "mismatch" or (r.found_title and r.verdict != "verified"):
            lines.append(f"        → found: {r.found_title or '(no title)'}")
        if r.detail:
            lines.append(f"        → {r.detail}"
                         + (f" (title similarity: {r.similarity:.2f})" if r.similarity is not None else ""))
    counts = ", ".join(f"{v} {k}" for k, v in sorted(s["counts"].items()))
    lines += ["-" * 60,
              f"Summary: {s['total']} reference(s) — {counts or 'none'}",
              f"Trust score: {s['score'] if s['score'] is not None else 'n/a'}/100 — {s['label']}",
              ""]
    return "\n".join(lines)


def render_json(results: List[CheckResult]) -> str:
    return json.dumps(to_dict(results), ensure_ascii=False, indent=2)


_HTML_CSS = """
:root{
  --bg:#070708;--panel:rgba(255,255,255,.03);--line:rgba(255,255,255,.09);
  --text:#f4f2ec;--muted:#9a978f;--muted2:#6d6a63;
  --lime:#c9f24b;--emerald:#34d399;--amber:#fbbf24;--rose:#fb7185;
  --ease-spring:cubic-bezier(.22,1,.36,1);--ease-out:cubic-bezier(.16,1,.3,1);
}
*{box-sizing:border-box;margin:0;padding:0}
::selection{background:var(--lime);color:#0a0f05}
body{
  background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;
  font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Inter","SF Pro Display",system-ui,sans-serif;
  line-height:1.55;-webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(900px 460px at 12% -5%,rgba(201,242,75,.07),transparent 60%),
    radial-gradient(800px 460px at 90% 0%,rgba(103,232,249,.06),transparent 60%);
}
main{max-width:980px;margin:0 auto;padding:3rem 1.5rem 4rem;animation:rise .7s var(--ease-spring) both}
@keyframes rise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
.top{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;
  padding-bottom:1.2rem;border-bottom:1px solid var(--line);margin-bottom:2.6rem}
.brand{font-size:1.25rem;font-weight:800;letter-spacing:-.03em}
.brand span{color:var(--lime)}
.brand sup{font-size:.55rem;color:var(--muted);font-weight:400;margin-left:.15rem}
.top-meta{display:flex;gap:1.4rem;align-items:center;font-family:ui-monospace,Menlo,monospace;
  font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.eyebrow{display:flex;align-items:center;gap:.9rem;font-family:ui-monospace,Menlo,monospace;
  font-size:.74rem;letter-spacing:.22em;text-transform:uppercase;color:var(--muted)}
.eyebrow .rule{width:44px;height:1px;background:var(--lime);flex:none}
.hero-grid{display:grid;grid-template-columns:auto 1fr;gap:2.4rem;align-items:end;margin:1.2rem 0 2.4rem}
@media(max-width:680px){.hero-grid{grid-template-columns:1fr;gap:1.2rem}}
.score-big{display:flex;align-items:baseline;gap:.4rem}
.score-big b{font-size:clamp(4.5rem,12vw,7.5rem);font-weight:800;letter-spacing:-.05em;line-height:.9;
  font-variant-numeric:tabular-nums}
.score-big span{font-size:1.1rem;color:var(--muted);font-weight:600}
.score-bar{height:3px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden;margin-top:1rem;max-width:340px}
.score-bar i{display:block;height:100%;width:0;border-radius:99px;
  background:linear-gradient(90deg,var(--lime),var(--emerald));
  animation:fill 1.1s var(--ease-spring) .2s both}
@keyframes fill{to{width:var(--w,0%)}}
.hero-side .label{font-size:1.05rem;color:var(--muted);margin-bottom:1rem}
.hero-side .label b{color:var(--text)}
.kpis{display:flex;gap:2rem;flex-wrap:wrap;margin-bottom:1.1rem}
.kpi b{font-size:1.6rem;letter-spacing:-.03em;font-variant-numeric:tabular-nums;display:block;font-weight:750}
.kpi span{font-size:.68rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
.pills{display:flex;gap:.4rem;flex-wrap:wrap}
.badge{display:inline-flex;align-items:center;gap:.35rem;border-radius:999px;padding:.24rem .7rem;
  font-size:.72rem;font-weight:650;border:1px solid transparent;
  font-family:ui-monospace,"JetBrains Mono",Menlo,monospace;white-space:nowrap}
.verified{background:rgba(16,185,129,.14);color:#34d399;border-color:rgba(16,185,129,.3)}
.exists{background:rgba(56,189,248,.14);color:#7dd3fc;border-color:rgba(56,189,248,.3)}
.partial{background:rgba(245,158,11,.14);color:#fbbf24;border-color:rgba(245,158,11,.3)}
.bad{background:rgba(244,63,94,.15);color:#fda4af;border-color:rgba(244,63,94,.35)}
.skip{background:rgba(100,116,139,.16);color:#cbd5e1;border-color:rgba(148,163,184,.22)}
.list{display:flex;flex-direction:column;gap:.7rem}
.item{
  position:relative;background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(255,255,255,.012));
  border:1px solid var(--line);border-radius:18px;padding:1.05rem 1.15rem 1.05rem 1.45rem;
  display:grid;grid-template-columns:1fr auto;gap:1rem;align-items:start;overflow:hidden;
  transition:transform .4s var(--ease-spring),border-color .4s ease;
  animation:itemIn .55s var(--ease-spring) both;
}
.item::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--vc,#64748b)}
.item:hover{transform:translateY(-2px);border-color:rgba(201,242,75,.3)}
@keyframes itemIn{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}
@media(max-width:680px){.item{grid-template-columns:1fr}}
.meta{display:flex;gap:.45rem;align-items:center;flex-wrap:wrap;margin-bottom:.35rem}
.r-index{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:var(--muted2)}
.kind-chip{font-family:ui-monospace,Menlo,monospace;font-size:.66rem;font-weight:700;letter-spacing:.08em;
  border-radius:6px;padding:.14rem .45rem;background:rgba(255,255,255,.07);color:var(--text)}
.line-chip{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:var(--muted2)}
code{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.07);
  border-radius:7px;padding:.14rem .45rem;font-size:.8rem;word-break:break-all}
.found{color:var(--muted);font-size:.82rem;margin-top:.3rem}
.found strong{color:var(--text);font-weight:650}
.simbar{height:5px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:.55rem;max-width:340px}
.simbar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--lime),var(--emerald));
  width:0;animation:fill 1s var(--ease-out) .3s both}
.simlabel{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:var(--muted2);margin-top:.25rem}
footer{color:var(--muted2);font-size:.7rem;margin-top:3rem;padding-top:1.4rem;border-top:1px solid var(--line);
  text-align:center;font-family:ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;line-height:2}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.score-bar i,.simbar i{width:var(--w,0%)}}
"""


def render_html(results: List[CheckResult], source: str = "") -> str:
    s = summarize(results)
    score = s["score"]
    score_txt = str(score) if score is not None else "—"
    pct = 0 if score is None else max(0, min(100, score))

    counts_html = " ".join(
        f'<span class="badge {_HTML_BADGE.get(k, ("skip", k))[0]}">{html.escape(k)} · {v}</span>'
        for k, v in sorted(s["counts"].items())
    ) or '<span class="badge skip">no references found</span>'

    items = []
    for idx, r in enumerate(results):
        badge_cls, badge_txt = _HTML_BADGE.get(r.verdict, ("skip", r.verdict))
        ctx = f'<div class="found">Cited as: “{html.escape(r.ref.context)}”</div>' if r.ref.context else ""
        found = f'<div class="found">Registry title: <strong>{html.escape(r.found_title)}</strong></div>' if r.found_title else ""
        sim = ""
        if r.similarity is not None:
            sim = (f'<div class="simbar"><i style="--w:{round(r.similarity * 100)}%"></i></div>'
                   f'<div class="simlabel">title similarity {r.similarity:.2f}</div>')
        delay = min(idx * 45, 500)
        vc = _VERDICT_COLOR.get(r.verdict, "#64748b")
        items.append(
            f'<article class="item" style="--vc:{vc};animation-delay:{delay}ms">'
            f'<div><div class="meta"><span class="r-index">#{idx + 1:03d}</span>'
            f'<span class="kind-chip">{html.escape(r.ref.kind.upper())}</span>'
            f'<span class="line-chip">line {r.ref.line}</span></div>'
            f'<code>{html.escape(r.ref.value)}</code>{ctx}{found}'
            f'<div class="found">{html.escape(r.detail)}{sim}</div></div>'
            f'<div><span class="badge {badge_cls}">{badge_txt}</span></div>'
            f'</article>'
        )
    rows_html = "\n".join(items)
    src = html.escape(source) if source else "pasted text"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#070708">
<title>RefRadar — Citation Telemetry Report</title>
<style>{_HTML_CSS}</style></head><body><main>
<header class="top">
  <div class="brand">Ref<span>Radar</span><sup>®</sup></div>
  <div class="top-meta"><span>Citation telemetry report</span><span>Source: <code>{src}</code></span></div>
</header>
<p class="eyebrow"><span class="rule"></span>Trust score</p>
<section class="hero-grid">
  <div>
    <div class="score-big"><b>{score_txt}</b><span>/100</span></div>
    <div class="score-bar"><i style="--w:{pct}%"></i></div>
  </div>
  <div class="hero-side">
    <p class="label"><b>{html.escape(s['label'])}</b> — {s['total']} citation(s) interrogated across the registries.</p>
    <div class="kpis">
      <div class="kpi"><b>{s['total']}</b><span>Total</span></div>
      <div class="kpi"><b>{s['counts'].get('verified', 0) + s['counts'].get('exists', 0)}</b><span>Confirmed live</span></div>
      <div class="kpi"><b>{s['counts'].get('mismatch', 0) + s['counts'].get('not_found', 0) + s['counts'].get('dead', 0) + s['counts'].get('invalid', 0)}</b><span>Flagged / suspect</span></div>
    </div>
    <div class="pills">{counts_html}</div>
  </div>
</section>
<section class="list">
{rows_html}
</section>
<footer>RefRadar flags suspicious references — it cannot prove a source true. Always double-check references that matter. · MIT licensed</footer>
</main></body></html>"""

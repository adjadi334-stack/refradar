"""Local web app: `refradar web` then open http://127.0.0.1:8787

Everything is served from the Python standard library — no framework, no
build step, no external assets. Verification calls happen server-side when
you scan; the page itself works fully offline.

Endpoints:
  GET  /                  the Motion-Design cockpit (single-page app)
  GET  /report.html       last scan rendered as a self-contained HTML report
  GET  /healthz           liveness probe ("ok")
  POST /api/scan          one-shot JSON scan (backwards compatible)
  POST /api/scan-stream   NDJSON stream: one event per verified reference,
                          pushed the instant its registry answers
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import __version__
from .extract import extract_references
from .report import render_html, result_to_dict, summarize, to_dict
from .verify import CheckResult, check_reference, check_references

MAX_BODY = 1024 * 1024  # 1 MB of pasted text is plenty
DEFAULT_TIMEOUT = 8.0

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#070708">
<meta name="description" content="RefRadar — catch hallucinated references in AI-generated text. Live citation telemetry against Crossref, arXiv, PubMed, Open Library and the web.">
<title>RefRadar — Catch the hallucination</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='13' fill='none' stroke='%23c9f24b' stroke-width='2'/%3E%3Ccircle cx='16' cy='16' r='7' fill='none' stroke='%2367e8f9' stroke-width='2'/%3E%3Ccircle cx='22' cy='10' r='3' fill='%23fb7185'/%3E%3C/svg%3E">
<script>document.documentElement.className+=" js";window.__boot=setTimeout(function(){var p=document.getElementById("preloader");if(p){p.style.display="none";document.body.classList.add("loaded");}},4000);</script>
<style>
@property --mx{syntax:"<length>";inherits:false;initial-value:0px}
@property --my{syntax:"<length>";inherits:false;initial-value:0px}
:root{
  --bg:#070708;--panel:rgba(255,255,255,.03);--line:rgba(255,255,255,.09);
  --text:#f4f2ec;--muted:#9a978f;--muted2:#6d6a63;
  --lime:#c9f24b;--cyan:#67e8f9;--violet:#c4b5fd;--emerald:#34d399;--amber:#fbbf24;--rose:#fb7185;--pink:#f9a8d4;
  --ease-spring:cubic-bezier(.22,1,.36,1);--ease-out:cubic-bezier(.16,1,.3,1);
  --a1:rgba(201,242,75,.10);--a2:rgba(103,232,249,.10);--a3:rgba(196,181,253,.08);
}
body[data-mood="scanning"]{--a1:rgba(103,232,249,.16);--a2:rgba(201,242,75,.10);--a3:rgba(196,181,253,.12)}
body[data-mood="good"]{--a1:rgba(52,211,153,.16);--a2:rgba(201,242,75,.10);--a3:rgba(52,211,153,.08)}
body[data-mood="warn"]{--a1:rgba(251,191,36,.14);--a2:rgba(244,114,182,.08);--a3:rgba(251,191,36,.06)}
body[data-mood="bad"]{--a1:rgba(251,113,133,.16);--a2:rgba(196,181,253,.10);--a3:rgba(251,113,133,.08)}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;
  font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Inter","SF Pro Display",system-ui,sans-serif;
  line-height:1.55;-webkit-font-smoothing:antialiased}
::selection{background:var(--lime);color:#0a0f05}
::-webkit-scrollbar{width:10px}
::-webkit-scrollbar-track{background:#0a0a0c}
::-webkit-scrollbar-thumb{background:#26262b;border-radius:99px;border:2px solid #0a0a0c}
::-webkit-scrollbar-thumb:hover{background:#3a3a41}
:focus-visible{outline:2px solid var(--lime);outline-offset:3px;border-radius:6px}
.aurora{position:fixed;inset:-20%;z-index:0;pointer-events:none;filter:blur(70px);opacity:.9;
  background:
    radial-gradient(42% 34% at 18% 12%,var(--a1),transparent 70%),
    radial-gradient(38% 30% at 84% 8%,var(--a2),transparent 70%),
    radial-gradient(46% 38% at 55% 88%,var(--a3),transparent 70%);
  animation:drift 22s ease-in-out infinite alternate;transition:background 1.2s ease}
@keyframes drift{from{transform:translate3d(-2%,-1%,0) scale(1)}to{transform:translate3d(2%,2%,0) scale(1.06)}}
.grain{position:fixed;inset:0;z-index:1;pointer-events:none;opacity:.05;mix-blend-mode:overlay}
.progress{position:fixed;top:0;left:0;right:0;height:2px;z-index:120;background:rgba(255,255,255,.05)}
.progress i{display:block;height:100%;width:0%;background:linear-gradient(90deg,var(--lime),var(--emerald),var(--cyan));
  transition:width .45s var(--ease-out)}
/* ---------- preloader ---------- */
#preloader{position:fixed;inset:0;z-index:10000;background:#050506;display:flex;flex-direction:column;
  justify-content:space-between;padding:2rem;transition:transform .9s var(--ease-spring)}
#preloader.done{transform:translateY(-101%)}
.pl-brand{font-size:1.3rem;font-weight:800;letter-spacing:-.03em}
.pl-brand em{font-style:normal;color:var(--lime)}
.pl-mid{align-self:center;text-align:center}
.pl-word{font-size:clamp(2.6rem,9vw,5.5rem);font-weight:800;letter-spacing:-.05em;line-height:1;overflow:hidden}
.pl-word span{display:inline-block;animation:plUp .8s var(--ease-spring) both}
.pl-word em{font-style:normal;color:var(--lime)}
@keyframes plUp{from{transform:translateY(115%)}to{transform:none}}
.pl-bar{width:min(320px,60vw);height:2px;background:rgba(255,255,255,.12);margin:1.4rem auto 0;border-radius:99px;overflow:hidden}
.pl-bar i{display:block;height:100%;width:0;background:var(--lime)}
.pl-num{position:absolute;right:2rem;bottom:1.2rem;font-family:ui-monospace,Menlo,monospace;
  font-size:clamp(3rem,8vw,5.5rem);font-weight:700;letter-spacing:-.04em;line-height:1}
.pl-tag{position:absolute;left:2rem;bottom:2.2rem;font-family:ui-monospace,Menlo,monospace;
  font-size:.7rem;letter-spacing:.22em;text-transform:uppercase;color:var(--muted)}
/* ---------- custom cursor ---------- */
.cursor-dot,.cursor-ring{position:fixed;top:0;left:0;pointer-events:none;z-index:9999;border-radius:50%;display:none}
.cursor-dot{width:6px;height:6px;background:var(--lime)}
.cursor-ring{width:34px;height:34px}
.cursor-ring i{display:block;width:100%;height:100%;border-radius:50%;border:1px solid rgba(244,242,236,.55);
  transition:transform .35s var(--ease-spring),background .3s ease,border-color .3s ease}
.cursor-ring.is-hover i{transform:scale(1.9);background:rgba(244,242,236,.10);border-color:rgba(201,242,75,.8)}
html.has-cursor .cursor-dot,html.has-cursor .cursor-ring{display:block}
html.has-cursor body,html.has-cursor a,html.has-cursor button,html.has-cursor .result,
html.has-cursor canvas,html.has-cursor label{cursor:none}
html.cursor-text .cursor-dot,html.cursor-text .cursor-ring{opacity:0}
html.cursor-text textarea{cursor:text}
/* ---------- topbar ---------- */
.topbar{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;justify-content:space-between;align-items:center;
  padding:1rem 2rem;border-bottom:1px solid var(--line);background:rgba(7,7,8,.55);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.brand{font-size:1.15rem;font-weight:800;letter-spacing:-.03em;color:var(--text);text-decoration:none}
.brand em{font-style:normal;color:var(--lime)}
.brand sup{font-size:.55rem;color:var(--muted);margin-left:.15rem;font-weight:400}
.top-meta{display:flex;gap:1.4rem;align-items:center;font-family:ui-monospace,Menlo,monospace;
  font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.tm{display:inline-flex;align-items:center;gap:.5rem}
.tm .dot{width:7px;height:7px;border-radius:50%;background:var(--emerald);box-shadow:0 0 12px var(--emerald)}
body[data-mood="scanning"] .tm .dot{background:var(--cyan);box-shadow:0 0 12px var(--cyan);animation:pulse 1s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.5);opacity:.55}}
@media(max-width:720px){.hide-s{display:none}}
/* ---------- hero ---------- */
.hero{position:relative;padding:11rem 2rem 5.5rem;max-width:1240px;margin:0 auto;overflow:hidden}
.hero::before{content:"";position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(244,242,236,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(244,242,236,.045) 1px,transparent 1px);
  background-size:72px 72px;
  -webkit-mask-image:radial-gradient(70% 60% at 50% 28%,#000 30%,transparent 75%);
  mask-image:radial-gradient(70% 60% at 50% 28%,#000 30%,transparent 75%)}
.hero-watermark{position:absolute;top:1rem;right:-3%;font-size:24vw;font-weight:800;letter-spacing:-.05em;
  line-height:1;color:transparent;-webkit-text-stroke:1px rgba(244,242,236,.055);pointer-events:none;user-select:none;z-index:0}
.eyebrow{position:relative;z-index:1;display:flex;align-items:center;gap:.9rem;font-family:ui-monospace,Menlo,monospace;
  font-size:.74rem;letter-spacing:.22em;text-transform:uppercase;color:var(--muted)}
.eyebrow .rule{width:44px;height:1px;background:var(--lime);flex:none}
.headline{position:relative;z-index:1;font-size:clamp(3.4rem,10.5vw,9.5rem);font-weight:800;letter-spacing:-.045em;
  line-height:.94;margin:1.4rem 0 1.8rem}
.headline em{font-family:Georgia,"Times New Roman",serif;font-style:italic;font-weight:400;letter-spacing:-.02em;color:var(--lime)}
.headline .period{color:var(--lime)}
.line{display:block;overflow:hidden;padding-bottom:.09em;margin-bottom:-.09em}
.line>span{display:inline-block}
.js .line>span{transform:translateY(115%);transition:transform 1.1s var(--ease-spring)}
body.loaded .line>span{transform:none}
body.loaded .line:nth-child(2)>span{transition-delay:.12s}
.hero-sub{position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,560px) auto;gap:2rem;align-items:end}
.hero-sub p{color:var(--muted);font-size:1.05rem;line-height:1.7}
.hero-sub p b{color:var(--text);font-weight:650}
.hero-cta{display:flex;gap:.7rem;flex-wrap:wrap}
.hero-meta{position:relative;z-index:1;display:flex;gap:1rem;align-items:center;flex-wrap:wrap;margin-top:3rem;
  font-family:ui-monospace,Menlo,monospace;font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;color:var(--muted2)}
.hero-meta i{width:5px;height:5px;border-radius:50%;background:var(--lime);flex:none}
.scroll-hint{position:absolute;bottom:1.6rem;left:2rem;width:1px;height:52px;background:rgba(255,255,255,.15);overflow:hidden;z-index:1}
.scroll-hint span{position:absolute;left:0;top:-40%;width:100%;height:40%;background:var(--lime);animation:scrollDot 1.8s var(--ease-spring) infinite}
@keyframes scrollDot{to{top:110%}}
@media(max-width:860px){.hero-sub{grid-template-columns:1fr}.scroll-hint{display:none}}
/* ---------- marquee ---------- */
.marquee{position:relative;z-index:2;border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  overflow:hidden;padding:1.05rem 0;background:rgba(255,255,255,.015)}
.marquee-track{display:flex;width:max-content;animation:marquee 30s linear infinite}
.marquee:hover .marquee-track{animation-play-state:paused}
.mq{display:flex;align-items:center;gap:3.2rem;padding-right:3.2rem;font-family:ui-monospace,Menlo,monospace;
  font-size:.8rem;letter-spacing:.24em;text-transform:uppercase;white-space:nowrap;color:var(--text)}
.mq .out{color:transparent;-webkit-text-stroke:1px rgba(244,242,236,.55)}
.mq .sep{color:var(--lime);font-size:.7rem}
@keyframes marquee{to{transform:translateX(-50%)}}
/* ---------- deck ---------- */
.deck{position:relative;z-index:2;max-width:1240px;margin:0 auto;padding:4.5rem 2rem 2rem}
.section-head{display:flex;align-items:baseline;gap:1rem;margin:3.4rem 0 1.4rem}
.section-head:first-child{margin-top:0}
.sec-num{font-family:ui-monospace,Menlo,monospace;font-size:.8rem;color:var(--lime);letter-spacing:.1em}
.section-head h2{font-size:1.5rem;font-weight:750;letter-spacing:-.025em}
.sec-line{flex:1;height:1px;background:var(--line);align-self:center}
.sec-note{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;color:var(--muted2)}
.js [data-reveal]{opacity:0;transform:translateY(28px);transition:opacity .9s var(--ease-out),transform .9s var(--ease-spring);transition-delay:var(--d,0s)}
.js [data-reveal].in{opacity:1;transform:none}
.bento{display:grid;grid-template-columns:1.3fr .9fr;gap:1rem}
@media(max-width:980px){.bento{grid-template-columns:1fr}}
.card{position:relative;background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.015));
  border:1px solid var(--line);border-radius:20px;padding:1.4rem;overflow:hidden;
  box-shadow:0 24px 60px rgba(0,0,0,.35)}
.spot::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .4s ease;
  background:radial-gradient(320px circle at var(--mx,50%) var(--my,50%),rgba(201,242,75,.07),transparent 65%)}
.spot:hover::before{opacity:1}
.card-label{display:flex;align-items:center;gap:.6rem;font-family:ui-monospace,Menlo,monospace;font-size:.7rem;
  letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-bottom:1rem}
.card-label::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--lime);flex:none}
.editor-wrap{position:relative;border-radius:16px}
.editor-wrap::after{content:"";position:absolute;left:12%;right:12%;top:-1px;height:2px;border-radius:99px;
  background:linear-gradient(90deg,transparent,var(--lime),var(--emerald),transparent);
  background-size:200% 100%;opacity:0;transition:opacity .4s ease;animation:beam 2.4s linear infinite}
.editor-wrap:focus-within::after,.editor-wrap.scanning::after{opacity:1}
@keyframes beam{from{background-position:200% 0}to{background-position:-200% 0}}
textarea{width:100%;min-height:250px;resize:vertical;background:rgba(0,0,0,.45);border:1px solid var(--line);
  border-radius:16px;color:var(--text);font-family:ui-monospace,"JetBrains Mono",SFMono-Regular,Menlo,monospace;
  font-size:.84rem;line-height:1.65;padding:1rem;outline:none;transition:border-color .35s ease,box-shadow .35s ease}
textarea:focus{border-color:rgba(201,242,75,.55);box-shadow:0 0 0 4px rgba(201,242,75,.08),0 0 34px rgba(201,242,75,.08)}
textarea.shake{animation:shake .45s ease}
@keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-7px)}40%{transform:translateX(6px)}60%{transform:translateX(-4px)}80%{transform:translateX(3px)}}
.dropzone{position:absolute;inset:0;display:grid;place-items:center;border-radius:16px;z-index:3;
  background:rgba(5,6,8,.85);border:2px dashed rgba(201,242,75,.6);opacity:0;pointer-events:none;
  transition:opacity .3s ease,transform .3s var(--ease-spring);transform:scale(.98);text-align:center;padding:1rem}
.dropzone.show{opacity:1;pointer-events:auto;transform:scale(1)}
.dropzone b{font-size:1.05rem;display:block;margin-bottom:.2rem}
.dropzone span{color:var(--muted);font-size:.82rem}
.toolbar{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin-top:.9rem}
.btn{position:relative;display:inline-flex;align-items:center;gap:.5rem;border-radius:999px;border:1px solid var(--line);
  background:rgba(255,255,255,.04);color:var(--text);font:inherit;font-size:.85rem;font-weight:650;
  padding:.7rem 1.3rem;cursor:pointer;text-decoration:none;
  transition:transform .45s var(--ease-spring),box-shadow .35s ease,border-color .35s ease,background .35s ease,color .35s ease;
  will-change:transform;user-select:none}
.btn:hover{border-color:rgba(201,242,75,.5);box-shadow:0 10px 28px rgba(201,242,75,.12)}
.btn:active{transform:scale(.97)}
.btn:disabled{opacity:.55;cursor:wait}
.btn-primary{background:var(--lime);border-color:transparent;color:#0a0f05;font-weight:800}
.btn-primary:hover{box-shadow:0 14px 36px rgba(201,242,75,.28)}
.btn-primary .arr{transition:transform .35s var(--ease-spring)}
.btn-primary:hover .arr{transform:translateX(4px)}
.btn-ghost{background:transparent;color:var(--muted)}
.btn-ghost:hover{color:var(--text)}
.preset{font-size:.76rem;padding:.5rem .9rem;color:var(--muted)}
.preset:hover{color:var(--text)}
.counts{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.85rem;min-height:1.6rem}
.token-pill{font-family:ui-monospace,Menlo,monospace;font-size:.7rem;border-radius:999px;padding:.24rem .65rem;
  border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.04);color:var(--muted);
  animation:pop .35s var(--ease-spring) both}
.token-pill b{color:var(--text)}
@keyframes pop{from{opacity:0;transform:scale(.8)}to{opacity:1;transform:scale(1)}}
.hint{margin-left:auto;color:var(--muted2);font-size:.74rem}
kbd{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-bottom-width:2px;
  border-radius:6px;padding:.05rem .4rem;font-family:ui-monospace,Menlo,monospace;font-size:.7rem;color:var(--text)}
#status{font-size:.82rem;color:var(--muted);margin-top:.65rem;min-height:1.25rem}
#status b{color:var(--text)}
#radarCanvas{width:100%;aspect-ratio:1;display:block;border-radius:14px;background:rgba(0,0,0,.35);
  border:1px solid rgba(255,255,255,.05)}
.legend{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.7rem}
.legend span{font-family:ui-monospace,Menlo,monospace;font-size:.66rem;border-radius:999px;padding:.16rem .55rem;
  border:1px solid rgba(255,255,255,.09);color:var(--muted)}
#radarTip{position:fixed;z-index:50;pointer-events:none;background:rgba(8,9,12,.94);border:1px solid var(--line);
  border-radius:10px;padding:.45rem .65rem;font-size:.74rem;max-width:260px;opacity:0;transform:translateY(4px);
  transition:opacity .2s ease,transform .2s ease;box-shadow:0 16px 40px rgba(0,0,0,.5)}
#radarTip.show{opacity:1;transform:none}
#radarTip code{font-size:.72rem}
.score-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:980px){.score-row{grid-template-columns:1fr}}
.gauge-wrap{display:flex;align-items:center;gap:1.2rem}
.gauge{width:132px;height:132px;position:relative;display:grid;place-items:center;flex:none}
.gauge svg{transform:rotate(-90deg);width:132px;height:132px}
.gauge circle{fill:none;stroke-width:7;stroke-linecap:round}
.gauge .track{stroke:rgba(255,255,255,.07)}
.gauge .arc{stroke-dasharray:339.292;stroke-dashoffset:339.292;transition:stroke .6s ease}
.gauge-num{position:absolute;display:flex;flex-direction:column;align-items:center}
.gauge-num b{font-size:2.1rem;letter-spacing:-.04em;font-variant-numeric:tabular-nums;line-height:1;font-weight:800}
.gauge-num small{font-size:.6rem;color:var(--muted);text-transform:uppercase;letter-spacing:.14em;margin-top:.25rem}
.stats{display:flex;flex-direction:column;gap:.55rem;justify-content:center;flex:1}
.stats .row{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px dashed rgba(255,255,255,.08);padding-bottom:.4rem}
.stats .row:last-child{border-bottom:0}
.stats b{font-size:1.3rem;font-variant-numeric:tabular-nums;letter-spacing:-.02em;font-weight:750}
.stats span{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
.pills{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.2rem}
.badge{display:inline-flex;align-items:center;gap:.35rem;border-radius:999px;padding:.24rem .7rem;font-size:.72rem;
  font-weight:650;border:1px solid transparent;font-family:ui-monospace,"JetBrains Mono",Menlo,monospace;white-space:nowrap}
.verified{background:rgba(16,185,129,.14);color:#34d399;border-color:rgba(16,185,129,.3)}
.exists{background:rgba(56,189,248,.14);color:#7dd3fc;border-color:rgba(56,189,248,.3)}
.partial{background:rgba(245,158,11,.14);color:#fbbf24;border-color:rgba(245,158,11,.3)}
.bad{background:rgba(244,63,94,.15);color:#fda4af;border-color:rgba(244,63,94,.35)}
.skip{background:rgba(100,116,139,.16);color:#cbd5e1;border-color:rgba(148,163,184,.22)}
.filters{position:relative;display:inline-flex;gap:2px;padding:4px;border:1px solid var(--line);
  border-radius:999px;background:var(--panel);margin-bottom:1rem;flex-wrap:wrap}
.filter-ind{position:absolute;top:4px;bottom:4px;left:0;border-radius:999px;background:var(--lime);
  transition:transform .5s var(--ease-spring),width .5s var(--ease-spring);z-index:0}
.filter{position:relative;z-index:1;border:0;background:transparent;color:var(--muted);font:inherit;
  font-size:.78rem;font-weight:650;padding:.5rem 1rem;border-radius:999px;cursor:pointer;transition:color .3s ease}
.filter:hover{color:var(--text)}
.filter.active{color:#0a0f05}
#results{display:flex;flex-direction:column;gap:.7rem}
.empty{border:1px dashed rgba(255,255,255,.12);border-radius:18px;padding:2.4rem 1.2rem;text-align:center;color:var(--muted)}
.empty b{color:var(--text);display:block;font-size:1.02rem;margin-bottom:.25rem}
.result{position:relative;background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(255,255,255,.012));
  border:1px solid var(--line);border-radius:18px;padding:1.05rem 1.15rem 1.05rem 1.45rem;overflow:hidden;cursor:pointer;
  transition:transform .4s var(--ease-spring),border-color .4s ease,box-shadow .4s ease;
  animation:itemIn .55s var(--ease-spring) both}
.result::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--vc,#64748b)}
.result:hover,.result.is-hover{transform:translateY(-3px);border-color:rgba(201,242,75,.35);
  box-shadow:0 18px 44px rgba(0,0,0,.35)}
.result.is-hover{outline:2px solid rgba(201,242,75,.3);outline-offset:2px}
@keyframes itemIn{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}
.result.hidden{display:none}
.r-top{display:flex;gap:.7rem;align-items:flex-start;justify-content:space-between}
.r-main{min-width:0;flex:1}
.r-meta{display:flex;gap:.45rem;align-items:center;flex-wrap:wrap;margin-bottom:.35rem}
.r-index{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:var(--muted2)}
.kind-chip{font-family:ui-monospace,Menlo,monospace;font-size:.66rem;font-weight:700;letter-spacing:.08em;
  border-radius:6px;padding:.14rem .45rem;background:rgba(255,255,255,.07);color:var(--text)}
.line-chip{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:var(--muted2)}
code{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.07);border-radius:7px;
  padding:.14rem .45rem;font-size:.8rem;word-break:break-all}
.ctx{color:var(--muted);font-size:.82rem;margin-top:.3rem}
.ctx i{color:var(--text)}
.detail{color:var(--muted);font-size:.8rem;margin-top:.3rem}
.found{color:var(--muted);font-size:.8rem;margin-top:.3rem}
.found strong{color:var(--text);font-weight:650}
.simbar{height:5px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:.55rem;max-width:340px}
.simbar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--lime),var(--emerald));
  width:0%;transition:width .9s var(--ease-out)}
.simlabel{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:var(--muted2);margin-top:.25rem}
.drawer{display:grid;grid-template-rows:0fr;transition:grid-template-rows .55s var(--ease-spring)}
.drawer>div{overflow:hidden;min-height:0}
.result.open .drawer{grid-template-rows:1fr}
.drawer-inner{padding-top:.7rem;margin-top:.7rem;border-top:1px dashed rgba(255,255,255,.09);
  display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.6rem}
.dcell{background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:.55rem .7rem}
.dcell span{display:block;font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted2);margin-bottom:.15rem}
.dcell b{font-size:.8rem;font-weight:650;word-break:break-word}
.chev{flex:none;width:30px;height:30px;border-radius:50%;border:1px solid var(--line);display:grid;place-items:center;
  color:var(--muted);transition:transform .45s var(--ease-spring),color .3s ease,border-color .3s ease;background:rgba(255,255,255,.03)}
.result.open .chev{transform:rotate(180deg);color:var(--lime);border-color:rgba(201,242,75,.5)}
footer{position:relative;z-index:2;max-width:1240px;margin:5rem auto 0;padding:3.5rem 2rem 2.5rem;
  border-top:1px solid var(--line);text-align:center}
.foot-word{font-size:clamp(3.6rem,13vw,11rem);font-weight:800;letter-spacing:-.055em;line-height:1;
  color:transparent;-webkit-text-stroke:1px rgba(244,242,236,.16);transition:color 1s ease;user-select:none}
.foot-word:hover{color:var(--lime);-webkit-text-stroke-color:transparent}
.foot-note{margin-top:1.4rem;color:var(--muted2);font-family:ui-monospace,Menlo,monospace;
  font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;line-height:2.1}
#reportLink{display:none}
#reportLink.show{display:inline-flex}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
  html{scroll-behavior:auto}
  .js [data-reveal]{opacity:1!important;transform:none!important}
  .js .line>span{transform:none!important}
  .marquee-track{animation:none!important}
}
</style></head><body data-mood="idle">
<noscript><style>#preloader{display:none}</style></noscript>
<div id="preloader" aria-hidden="true">
  <div class="pl-brand">Ref<em>Radar</em></div>
  <div class="pl-mid">
    <div class="pl-word"><span>Ref<em>Radar</em></span></div>
    <div class="pl-bar"><i id="plBar"></i></div>
  </div>
  <div class="pl-tag">Citation telemetry</div>
  <div class="pl-num"><span id="plNum">0</span>%</div>
</div>
<div class="cursor-dot" aria-hidden="true"></div>
<div class="cursor-ring" aria-hidden="true"><i></i></div>
<div class="aurora" aria-hidden="true"></div>
<svg class="grain" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
  <filter id="grainF"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/></filter>
  <rect width="100%" height="100%" filter="url(#grainF)"/>
</svg>
<div class="progress" aria-hidden="true"><i id="progressFill"></i></div>
<header class="topbar">
  <a class="brand" href="#top">Ref<em>Radar</em><sup>®</sup></a>
  <nav class="top-meta">
    <span class="tm"><span class="dot"></span><span id="statusPill">idle</span></span>
    <span class="tm hide-s" id="clock">--:--:-- UTC</span>
    <span class="tm hide-s">v__VERSION__</span>
  </nav>
</header>
<main id="top">
<section class="hero">
  <div class="hero-watermark" aria-hidden="true">RADAR</div>
  <p class="eyebrow" data-reveal><span class="rule"></span><span id="eyebrowText">Citation telemetry — live verification</span></p>
  <h1 class="headline">
    <span class="line"><span>Catch the</span></span>
    <span class="line"><span><em>hallucination</em><span class="period">.</span></span></span>
  </h1>
  <div class="hero-sub" data-reveal style="--d:.15s">
    <p>Paste any AI-generated text. RefRadar interrogates <b>five public registries</b> — Crossref, arXiv, PubMed, Open Library and the live web — and streams back a verdict for every citation, <b>the instant each registry answers</b>.</p>
    <div class="hero-cta">
      <a class="btn btn-primary magnetic" href="#deck">Start scanning <span class="arr">→</span></a>
      <button class="btn btn-ghost magnetic" id="heroDemo">Load demo</button>
    </div>
  </div>
  <div class="hero-meta" data-reveal style="--d:.25s">
    <span>5 registries</span><i></i><span>real-time stream</span><i></i><span>zero dependencies</span><i></i><span>100% local</span>
  </div>
  <div class="scroll-hint" aria-hidden="true"><span></span></div>
</section>
<div class="marquee" aria-hidden="true">
  <div class="marquee-track">
    <span class="mq"><span>Verify every citation</span><span class="sep">✦</span><span class="out">Crossref</span><span class="sep">✦</span><span>arXiv</span><span class="sep">✦</span><span class="out">PubMed</span><span class="sep">✦</span><span>Open Library</span><span class="sep">✦</span><span class="out">Live web</span><span class="sep">✦</span><span>Zero dependencies</span><span class="sep">✦</span></span>
    <span class="mq"><span>Verify every citation</span><span class="sep">✦</span><span class="out">Crossref</span><span class="sep">✦</span><span>arXiv</span><span class="sep">✦</span><span class="out">PubMed</span><span class="sep">✦</span><span>Open Library</span><span class="sep">✦</span><span class="out">Live web</span><span class="sep">✦</span><span>Zero dependencies</span><span class="sep">✦</span></span>
  </div>
</div>
<section class="deck" id="deck">
  <div class="section-head" data-reveal>
    <span class="sec-num">01</span><h2>Input deck</h2><span class="sec-line"></span><span class="sec-note">paste · drop · type</span>
  </div>
  <div class="bento">
    <div class="card spot" data-reveal>
      <div class="card-label">Source text</div>
      <div class="editor-wrap" id="editorWrap">
        <textarea id="src" placeholder="Paste the AI-generated text here… or drop a .md / .txt file. Identifiers are counted live as you type."></textarea>
        <div class="dropzone" id="dropzone"><div><b>Drop to load</b><span>any UTF-8 text file — it lands in the editor</span></div></div>
      </div>
      <div class="toolbar">
        <button class="btn btn-primary magnetic" id="go">Verify references <span class="arr">→</span></button>
        <button class="btn btn-ghost magnetic" id="clear">Clear</button>
        <button class="btn preset" data-preset="thesis">AI Thesis Draft</button>
        <button class="btn preset" data-preset="medical">Medical Literature</button>
        <button class="btn preset" data-preset="clean">Clean Research</button>
        <span class="hint"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> to scan · <kbd>/</kbd> to focus</span>
      </div>
      <div class="counts" id="tokenCounts"></div>
      <div id="status" role="status"></div>
    </div>
    <div class="card spot" data-reveal style="--d:.08s">
      <div class="card-label">Telemetry — 5 orbits</div>
      <canvas id="radarCanvas" aria-label="Interactive radar of verification results"></canvas>
      <div class="legend">
        <span style="color:#67e8f9">● DOI</span><span style="color:#c4b5fd">● arXiv</span>
        <span style="color:#6ee7b7">● PMID</span><span style="color:#fcd34d">● ISBN</span>
        <span style="color:#f9a8d4">● URL</span>
      </div>
    </div>
  </div>
  <div class="section-head" data-reveal>
    <span class="sec-num">02</span><h2>Verdicts</h2><span class="sec-line"></span><span class="sec-note">trust score</span>
  </div>
  <div class="score-row">
    <div class="card spot gauge-wrap" data-reveal>
      <div class="gauge">
        <svg viewBox="0 0 120 120">
          <defs><linearGradient id="scoreGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#c9f24b"/><stop offset="1" stop-color="#34d399"/>
          </linearGradient></defs>
          <circle class="track" cx="60" cy="60" r="54"></circle>
          <circle class="arc" id="scoreArc" cx="60" cy="60" r="54" stroke="url(#scoreGrad)"></circle>
        </svg>
        <div class="gauge-num"><b id="scoreNum">—</b><small>Trust /100</small></div>
      </div>
      <div class="stats">
        <div class="row"><span>Total citations</span><b id="statTotal">0</b></div>
        <div class="row"><span>Confirmed live</span><b id="statGood" style="color:var(--emerald)">0</b></div>
        <div class="row"><span>Flagged / suspect</span><b id="statBad" style="color:var(--rose)">0</b></div>
      </div>
    </div>
    <div class="card spot" data-reveal style="--d:.08s">
      <div class="card-label">Verdict breakdown</div>
      <div class="pills" id="verdictPills"><span class="badge skip">no scan yet</span></div>
      <p class="detail" style="margin-top:.9rem">Hover a result card to locate its blip on the radar — or hover a blip to highlight its card. Click a card to inspect the registry evidence.</p>
      <div style="margin-top:.9rem"><a class="btn" id="reportLink" href="/report.html" target="_blank" rel="noopener">⬇ HTML report</a></div>
    </div>
  </div>
  <div class="section-head" data-reveal>
    <span class="sec-num">03</span><h2>Evidence</h2><span class="sec-line"></span><span class="sec-note">click a card to inspect</span>
  </div>
  <div data-reveal>
    <div class="filters" id="filters">
      <span class="filter-ind" id="filterInd"></span>
      <button class="filter active" data-filter="all">All</button>
      <button class="filter" data-filter="good">Confirmed</button>
      <button class="filter" data-filter="flagged">Flagged</button>
      <button class="filter" data-filter="unreachable">Unreachable</button>
    </div>
  </div>
  <section id="results">
    <div class="empty" id="emptyState"><b>No scan yet</b>Paste text above and hit <b style="display:inline">Verify references</b> — results stream in here, one per registry answer.</div>
  </section>
</section>
<footer>
  <div class="foot-word" aria-hidden="true">RefRadar</div>
  <p class="foot-note">RefRadar v__VERSION__ — runs locally · nothing you paste leaves your machine except verification requests to public APIs (Crossref, arXiv, NCBI, Open Library, target websites).<br>It flags suspicious references — it cannot prove a source true. Always verify what matters. · MIT licensed</p>
</footer>
</main>
<div id="radarTip"></div>
<input type="file" id="fileInput" accept=".txt,.md,.markdown,.text,text/plain" hidden>
<script>
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const REDUCED=matchMedia("(prefers-reduced-motion: reduce)").matches;
const BADGE={verified:["verified","Verified"],exists:["exists","Exists"],partial:["partial","Weak match"],
 mismatch:["bad","Mismatch"],dead:["bad","Dead link"],not_found:["bad","Not found"],
 invalid:["bad","Invalid ISBN"],unreachable:["skip","Unreachable"],unverifiable:["skip","Unverifiable"]};
const KIND_ORBIT={doi:0,arxiv:1,pmid:2,isbn:3,url:4};
const KIND_LABEL={doi:"DOI",arxiv:"arXiv",pmid:"PMID",isbn:"ISBN",url:"URL"};
const KIND_COLOR={doi:"#67e8f9",arxiv:"#c4b5fd",pmid:"#6ee7b7",isbn:"#fcd34d",url:"#f9a8d4"};
const VERDICT_COLOR={verified:"#34d399",exists:"#67e8f9",partial:"#fbbf24",mismatch:"#fb7185",
 dead:"#fb7185",not_found:"#fb7185",invalid:"#fb7185",unreachable:"#94a3b8",unverifiable:"#94a3b8"};
const SCORES={verified:100,exists:85,partial:55,mismatch:15,dead:0,not_found:0,invalid:0};
const GOOD=new Set(["verified","exists"]), FLAGGED=new Set(["mismatch","not_found","dead","invalid","partial"]);
const CIRC=339.292;
const PRESETS={
 thesis:"According to the seminal transformer paper [Attention Is All You Need](https://arxiv.org/abs/1706.03762), self-attention replaced recurrence. A later replication (https://arxiv.org/abs/9999.99999) refined it.\n\nThe deep learning review by LeCun, Bengio and Hinton (DOI 10.1038/nature14539) remains canonical. A 2024 mega-analysis, published as DOI 10.1234/refradar.fake.9.9.9, reportedly confirms these findings.\n\nClinically, evidence can be found in PubMed under PMID 33301246, while a contradictory preprint lives at https://example.com/definitely-not-a-real-study-refradar.\n\nBackground reading: ISBN 978-0-262-03384-8 (Introduction to Algorithms) and the often-cited ISBN 978-2-07-000000-0 (invalid checksum).",
 medical:"A randomized trial (PMID 33301246) showed strong efficacy. The protocol is registered at DOI 10.1038/nature14539. A related preprint on arXiv:1706.03762 discusses the mechanism. One citation points to https://example.com/no-such-guideline-2024 and another to PMID 99999999, which does not exist.",
 clean:"The transformer architecture was introduced in [Attention Is All You Need](https://arxiv.org/abs/1706.03762). Deep learning fundamentals are covered in DOI 10.1038/nature14539. Vaccine efficacy data: PMID 33301246. Background: ISBN 978-0-262-03384-8."
};
let blips=[], shockwaves=[], particles=[], resultsData=[], byIndex={}, totalRefs=0, hoverIndex=null;
let sweepAngle=-Math.PI/2, currentFilter="all", scanning=false;
let displayedScore=0, targetScore=null, scoreAnim=false;
const canvas=$("#radarCanvas"), ctx=canvas.getContext("2d"), tip=$("#radarTip");
const wm=$(".hero-watermark");
let CW=0, CH=0, CX=0, CY=0, CR=0;
/* ---------- preloader ---------- */
(function boot(){
  const pl=$("#preloader"); if(!pl)return;
  const t0=performance.now(), DUR=REDUCED?0:850;
  function finish(){
    clearTimeout(window.__boot);
    pl.classList.add("done");
    document.body.classList.add("loaded");
    setTimeout(()=>pl.remove(),1000);
  }
  function step(t){
    const p=DUR?Math.min(1,(t-t0)/DUR):1, v=Math.round(p*100);
    const n=$("#plNum"), b=$("#plBar");
    if(n)n.textContent=v; if(b)b.style.width=v+"%";
    if(p<1)requestAnimationFrame(step); else finish();
  }
  requestAnimationFrame(step);
})();
/* ---------- custom cursor ---------- */
if(matchMedia("(pointer: fine)").matches&&!REDUCED){
  document.documentElement.classList.add("has-cursor");
  const dot=$(".cursor-dot"), ring=$(".cursor-ring");
  let mx=innerWidth/2, my=innerHeight/2, rx=mx, ry=my;
  addEventListener("mousemove",e=>{
    mx=e.clientX; my=e.clientY;
    dot.style.transform="translate("+(mx-3)+"px,"+(my-3)+"px)";
    const t=e.target;
    document.documentElement.classList.toggle("cursor-text",!!(t.closest&&t.closest("textarea,input")));
    ring.classList.toggle("is-hover",!!(t.closest&&t.closest("a,button,.result,canvas,.filter")));
  });
  document.addEventListener("mouseleave",()=>{dot.style.opacity="0";ring.style.opacity="0";});
  document.addEventListener("mouseenter",()=>{dot.style.opacity="1";ring.style.opacity="1";});
  (function cl(){
    rx+=(mx-rx)*.16; ry+=(my-ry)*.16;
    ring.style.transform="translate("+(rx-17)+"px,"+(ry-17)+"px)";
    requestAnimationFrame(cl);
  })();
}
/* ---------- clock ---------- */
const clockEl=$("#clock");
function tickClock(){const d=new Date();clockEl.textContent=d.toUTCString().slice(17,25)+" UTC";}
tickClock(); setInterval(tickClock,1000);
/* ---------- text scramble ---------- */
const GLYPHS="!<>-_\\/[]{}=+*^?#01";
function scramble(el,final){
  if(!el)return;
  if(REDUCED){el.textContent=final;return;}
  let frame=0; const total=Math.max(10,final.length*2);
  clearInterval(el._scr);
  el._scr=setInterval(()=>{
    frame++;
    let out="";
    for(let i=0;i<final.length;i++){
      out+=(i<frame/2||final[i]===" ")?final[i]:GLYPHS[Math.floor(Math.random()*GLYPHS.length)];
    }
    el.textContent=out;
    if(frame>=total){clearInterval(el._scr);el.textContent=final;}
  },28);
}
scramble($("#eyebrowText"),"Citation telemetry — live verification");
/* ---------- scroll reveals ---------- */
const io=new IntersectionObserver(es=>es.forEach(e=>{
  if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target);}
}),{threshold:.12});
$$("[data-reveal]").forEach(el=>io.observe(el));
/* ---------- radar ---------- */
function resizeCanvas(){
  const r=canvas.getBoundingClientRect(), dpr=Math.min(window.devicePixelRatio||1,2);
  CW=Math.max(220,Math.floor(r.width)); CH=CW;
  canvas.width=CW*dpr; canvas.height=CH*dpr; canvas.style.height=CW+"px";
  ctx.setTransform(dpr,0,0,dpr,0,0);
  CX=CW/2; CY=CH/2; CR=Math.min(CW,CH)/2-26;
  drawRadar(0);
}
new ResizeObserver(resizeCanvas).observe(canvas);
window.addEventListener("resize",resizeCanvas);
function orbitRadius(kind){return CR*(0.20+0.16*(KIND_ORBIT[kind]??4));}
function blipXY(b){return [CX+Math.cos(b.angle)*b.radius, CY+Math.sin(b.angle)*b.radius];}
function seedParticles(){
  particles=[];
  for(let i=0;i<26;i++){
    const kind=["doi","arxiv","pmid","isbn","url"][i%5];
    particles.push({kind,angle:Math.random()*Math.PI*2,speed:(Math.random()*.25+.08)*(i%2?1:-1),f:0.92+Math.random()*.16});
  }
}
function drawRadar(dt){
  if(!CW)return;
  const now=performance.now();
  ctx.clearRect(0,0,CW,CH);
  const g=ctx.createRadialGradient(CX,CY,0,CX,CY,CR*1.3);
  g.addColorStop(0,"rgba(14,17,26,.95)"); g.addColorStop(1,"rgba(5,6,10,.35)");
  ctx.fillStyle=g; ctx.beginPath(); ctx.arc(CX,CY,CR*1.3,0,Math.PI*2); ctx.fill();
  ctx.strokeStyle="rgba(244,242,236,.07)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(CX-CR*1.28,CY); ctx.lineTo(CX+CR*1.28,CY);
  ctx.moveTo(CX,CY-CR*1.28); ctx.lineTo(CX,CY+CR*1.28); ctx.stroke();
  ctx.save(); ctx.setLineDash([3,7]); ctx.lineDashOffset=-now/90;
  ctx.strokeStyle="rgba(244,242,236,.16)";
  ctx.beginPath(); ctx.arc(CX,CY,CR*1.15,0,Math.PI*2); ctx.stroke(); ctx.restore();
  ctx.strokeStyle="rgba(244,242,236,.20)";
  for(let i=0;i<72;i++){
    const a=i/72*Math.PI*2, len=i%6===0?9:4, r1=CR*1.15+4;
    ctx.beginPath();
    ctx.moveTo(CX+Math.cos(a)*r1,CY+Math.sin(a)*r1);
    ctx.lineTo(CX+Math.cos(a)*(r1+len),CY+Math.sin(a)*(r1+len));
    ctx.stroke();
  }
  ["doi","arxiv","pmid","isbn","url"].forEach(k=>{
    const r=orbitRadius(k);
    ctx.strokeStyle="rgba(244,242,236,.13)"; ctx.beginPath(); ctx.arc(CX,CY,r,0,Math.PI*2); ctx.stroke();
    ctx.fillStyle=KIND_COLOR[k]; ctx.font="600 9px ui-monospace,Menlo,monospace"; ctx.textAlign="center";
    ctx.fillText(KIND_LABEL[k],CX,CY-r-6);
  });
  particles.forEach(p=>{
    if(!REDUCED)p.angle+=p.speed*dt/1000;
    const rr=orbitRadius(p.kind)*p.f;
    ctx.fillStyle="rgba(244,242,236,.30)";
    ctx.beginPath(); ctx.arc(CX+Math.cos(p.angle)*rr,CY+Math.sin(p.angle)*rr,1.3,0,Math.PI*2); ctx.fill();
  });
  if(!REDUCED){sweepAngle+=dt*0.0011; if(sweepAngle>Math.PI*2)sweepAngle-=Math.PI*2;}
  const sweepR=CR*1.15;
  if(ctx.createConicGradient){
    const cg=ctx.createConicGradient(sweepAngle,CX,CY);
    cg.addColorStop(0,"rgba(201,242,75,.20)"); cg.addColorStop(0.07,"rgba(201,242,75,.07)");
    cg.addColorStop(0.15,"rgba(201,242,75,0)"); cg.addColorStop(1,"rgba(201,242,75,0)");
    ctx.fillStyle=cg; ctx.beginPath(); ctx.moveTo(CX,CY); ctx.arc(CX,CY,sweepR,0,Math.PI*2); ctx.fill();
  }else{
    ctx.fillStyle="rgba(201,242,75,.08)"; ctx.beginPath(); ctx.moveTo(CX,CY);
    ctx.arc(CX,CY,sweepR,sweepAngle-0.5,sweepAngle); ctx.closePath(); ctx.fill();
  }
  ctx.strokeStyle="rgba(201,242,75,.8)"; ctx.lineWidth=1.4;
  ctx.beginPath(); ctx.moveTo(CX,CY); ctx.lineTo(CX+Math.cos(sweepAngle)*sweepR,CY+Math.sin(sweepAngle)*sweepR); ctx.stroke();
  const cp=REDUCED?0:Math.sin(now/520)*1.6;
  ctx.strokeStyle="rgba(244,242,236,.35)";
  ctx.beginPath(); ctx.arc(CX,CY,7+cp,0,Math.PI*2); ctx.stroke();
  ctx.fillStyle="rgba(244,242,236,.8)"; ctx.beginPath(); ctx.arc(CX,CY,2,0,Math.PI*2); ctx.fill();
  shockwaves=shockwaves.filter(s=>now-s.t0<950);
  shockwaves.forEach(s=>{
    const p=(now-s.t0)/950, r=6+p*46;
    ctx.strokeStyle=s.color; ctx.globalAlpha=(1-p)*.8; ctx.lineWidth=2*(1-p)+.5;
    ctx.beginPath(); ctx.arc(s.x,s.y,r,0,Math.PI*2); ctx.stroke();
    ctx.globalAlpha=(1-p)*.35; ctx.beginPath(); ctx.arc(s.x,s.y,r*.62,0,Math.PI*2); ctx.stroke();
    ctx.globalAlpha=1;
  });
  blips.forEach(b=>{
    const[x,y]=blipXY(b); b.x=x; b.y=y;
    const hot=b.index===hoverIndex, col=VERDICT_COLOR[b.verdict]||"#94a3b8";
    const base=hot?7:4.6;
    const pulse=REDUCED?1:1+Math.sin(now/380+b.index)*0.12;
    if(hot){
      const ph=(now/28)%12, hr=base+5+ph;
      ctx.strokeStyle=col; ctx.globalAlpha=Math.max(0,1-ph/12); ctx.lineWidth=1.2;
      ctx.beginPath(); ctx.arc(x,y,hr,0,Math.PI*2); ctx.stroke(); ctx.globalAlpha=1;
    }
    ctx.save(); ctx.shadowColor=col; ctx.shadowBlur=hot?22:12;
    ctx.fillStyle=col; ctx.beginPath(); ctx.arc(x,y,base*pulse,0,Math.PI*2); ctx.fill();
    ctx.restore();
    ctx.fillStyle="rgba(255,255,255,.92)"; ctx.beginPath(); ctx.arc(x,y,1.6,0,Math.PI*2); ctx.fill();
    if(hot){
      ctx.strokeStyle=col; ctx.lineWidth=1.4;
      ctx.beginPath(); ctx.arc(x,y,base+7,0,Math.PI*2); ctx.stroke();
      ctx.fillStyle="rgba(244,242,236,.95)"; ctx.font="600 10px ui-monospace,Menlo,monospace"; ctx.textAlign="center";
      ctx.fillText(KIND_LABEL[b.kind]+" #"+(b.index+1),x,y-base-12);
    }
  });
  ctx.fillStyle="rgba(154,151,143,.55)"; ctx.font="600 9px ui-monospace,Menlo,monospace"; ctx.textAlign="center";
  ctx.fillText("REFRADAR // LIVE TELEMETRY",CX,CH-8);
}
let lastT=performance.now();
function loop(t){
  const dt=Math.min(50,t-lastT); lastT=t;
  drawRadar(dt);
  if(wm&&!REDUCED)wm.style.transform="translateY("+((scrollY||0)*0.18)+"px)";
  requestAnimationFrame(loop);
}
canvas.addEventListener("mousemove",e=>{
  const r=canvas.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  let best=null, bd=1e9;
  blips.forEach(b=>{const d=Math.hypot((b.x??0)-mx,(b.y??0)-my); if(d<bd){bd=d;best=b;}});
  const next=(best&&bd<22)?best.index:null;
  if(next!==hoverIndex){
    hoverIndex=next;
    $$(".result").forEach(c=>c.classList.toggle("is-hover",Number(c.dataset.index)===next));
  }
  if(next!==null&&best){
    const res=byIndex[best.index];
    tip.innerHTML="<b>"+esc(KIND_LABEL[best.kind]||best.kind)+"</b> <code>"+esc(res?res.value:"")+"</code><br>"+esc(res?res.verdict_label||res.verdict:"");
    tip.style.left=(e.clientX+14)+"px"; tip.style.top=(e.clientY+14)+"px"; tip.classList.add("show");
  }else tip.classList.remove("show");
});
canvas.addEventListener("mouseleave",()=>{hoverIndex=null;tip.classList.remove("show");
  $$(".result").forEach(c=>c.classList.remove("is-hover"));});
canvas.addEventListener("click",()=>{
  if(hoverIndex===null)return;
  const card=document.querySelector('.result[data-index="'+hoverIndex+'"]');
  if(card){card.scrollIntoView({behavior:REDUCED?"auto":"smooth",block:"center"});card.classList.add("open");}
});
/* ---------- state / score ---------- */
function setMood(m){document.body.dataset.mood=m;scramble($("#statusPill"),m);}
function setStatus(html){$("#status").innerHTML=html;}
function setProgress(done,total){
  $("#progressFill").style.width=total?Math.round(done/total*100)+"%":(done?"100%":"0%");
}
function scoreColor(s){return s===null?"#64748b":s>=80?"#10b981":s>=45?"#f59e0b":"#f43f5e";}
function updateScoreRing(v){
  const arc=$("#scoreArc");
  arc.style.strokeDashoffset=String(CIRC*(1-Math.max(0,Math.min(100,v))/100));
  arc.setAttribute("stroke",v>=80?"url(#scoreGrad)":scoreColor(v));
  $("#scoreNum").textContent=String(Math.round(v));
}
function tweenScore(target){
  targetScore=target;
  if(!scoreAnim){scoreAnim=true;requestAnimationFrame(scoreStep);}
}
function scoreStep(){
  if(targetScore===null){scoreAnim=false;return;}
  displayedScore+=(targetScore-displayedScore)*0.09;
  if(Math.abs(targetScore-displayedScore)<0.6){displayedScore=targetScore;targetScore=null;scoreAnim=false;}
  updateScoreRing(displayedScore);
  if(scoreAnim)requestAnimationFrame(scoreStep);
}
function runningScore(){
  const vals=resultsData.map(r=>SCORES[r.verdict]).filter(v=>v!==undefined);
  return vals.length?Math.round(vals.reduce((a,b)=>a+b,0)/vals.length):null;
}
function refreshStats(){
  const total=resultsData.length;
  const good=resultsData.filter(r=>GOOD.has(r.verdict)).length;
  const bad=resultsData.filter(r=>FLAGGED.has(r.verdict)).length;
  $("#statTotal").textContent=String(total);
  $("#statGood").textContent=String(good);
  $("#statBad").textContent=String(bad);
  const counts={};
  resultsData.forEach(r=>{counts[r.verdict]=(counts[r.verdict]||0)+1;});
  const entries=Object.entries(counts).sort((a,b)=>b[1]-a[1]);
  $("#verdictPills").innerHTML=entries.length
    ? entries.map(([k,v])=>{const[cls,label]=BADGE[k]||["skip",k];
        return '<span class="badge '+cls+'">'+esc(label)+" · "+v+"</span>";}).join("")
    : '<span class="badge skip">no scan yet</span>';
  const rs=runningScore();
  if(rs!==null)tweenScore(rs);
}
/* ---------- results ---------- */
function cardHTML(r){
  const[cls,label]=BADGE[r.verdict]||["skip",r.verdict];
  const sim=r.similarity!==null&&r.similarity!==undefined
    ? '<div class="simbar"><i data-w="'+Math.round(r.similarity*100)+'"></i></div><div class="simlabel">title similarity '+r.similarity.toFixed(2)+"</div>":"";
  const ctxLine=r.context?'<div class="ctx">Cited as: <i>“'+esc(r.context)+'”</i></div>':"";
  const found=r.found_title?'<div class="found">Registry title: <strong>'+esc(r.found_title)+"</strong></div>":"";
  return '<article class="result spot" data-index="'+r.index+'" data-verdict="'+esc(r.verdict)+'" style="--vc:'+(VERDICT_COLOR[r.verdict]||"#64748b")+';animation-delay:'+Math.min(r.index*60,480)+'ms">'
   +'<div class="r-top"><div class="r-main">'
   +'<div class="r-meta"><span class="r-index">#'+String(r.index+1).padStart(3,"0")+'</span>'
   +'<span class="kind-chip" style="color:'+(KIND_COLOR[r.kind]||"#e2e8f0")+'">'+esc(KIND_LABEL[r.kind]||r.kind.toUpperCase())+'</span>'
   +'<span class="line-chip">line '+esc(r.line||"—")+'</span>'
   +'<span class="badge '+cls+'">'+esc(label)+'</span></div>'
   +'<code>'+esc(r.value)+"</code>"+ctxLine+found
   +'<div class="detail">'+esc(r.detail||"")+"</div>"+sim
   +'<div class="drawer"><div><div class="drawer-inner">'
   +'<div class="dcell"><span>Verdict</span><b>'+esc(r.verdict_label||r.verdict)+'</b></div>'
   +'<div class="dcell"><span>HTTP status</span><b>'+(r.http_status??"—")+'</b></div>'
   +'<div class="dcell"><span>Similarity</span><b>'+(r.similarity!==null&&r.similarity!==undefined?r.similarity.toFixed(3):"—")+'</b></div>'
   +'<div class="dcell"><span>Detail</span><b>'+esc(r.detail||"—")+'</b></div>'
   +"</div></div></div>"
   +'</div><span class="chev">▾</span></div></article>';
}
function applyFilter(){
  $$(".result").forEach(c=>{
    const v=c.dataset.verdict;
    const show=currentFilter==="all"
      ||(currentFilter==="good"&&GOOD.has(v))
      ||(currentFilter==="flagged"&&FLAGGED.has(v))
      ||(currentFilter==="unreachable"&&(v==="unreachable"||v==="unverifiable"));
    c.classList.toggle("hidden",!show);
  });
}
function addResult(r){
  resultsData.push(r); byIndex[r.index]=r;
  const angle=r.index*2.399963+0.6;
  const b={index:r.index,kind:r.kind,angle,radius:orbitRadius(r.kind)*(0.94+((r.index*37)%10)/10*0.12),verdict:r.verdict,x:0,y:0};
  blips.push(b);
  const[x,y]=blipXY(b); b.x=x; b.y=y;
  if(!REDUCED)shockwaves.push({x,y,t0:performance.now(),color:VERDICT_COLOR[r.verdict]||"#94a3b8"});
  const empty=$("#emptyState"); if(empty)empty.remove();
  const wrap=document.createElement("div");
  wrap.innerHTML=cardHTML(r);
  const card=wrap.firstElementChild;
  $("#results").appendChild(card);
  requestAnimationFrame(()=>{card.querySelectorAll(".simbar i").forEach(i=>{i.style.width=i.dataset.w+"%";});});
  applyFilter();
  refreshStats();
  setProgress(resultsData.length,totalRefs);
}
function resetResults(){
  resultsData=[]; byIndex={}; blips=[]; shockwaves=[]; totalRefs=0; hoverIndex=null;
  $("#results").innerHTML='<div class="empty" id="emptyState"><b>Scanning…</b>Waiting for the first registry answer.</div>';
  $("#verdictPills").innerHTML='<span class="badge skip">scanning…</span>';
  $("#statTotal").textContent="0"; $("#statGood").textContent="0"; $("#statBad").textContent="0";
  $("#reportLink").classList.remove("show");
  displayedScore=0; targetScore=null; updateScoreRing(0); $("#scoreNum").textContent="—";
  setProgress(0,0);
}
function finish(summary,elapsedMs){
  setMood(summary.score===null?"idle":summary.score>=80?"good":summary.score>=45?"warn":"bad");
  if(summary.score!==null)tweenScore(summary.score);
  setProgress(summary.total,summary.total);
  setStatus("Done in <b>"+(elapsedMs/1000).toFixed(1)+"s</b> — "+summary.total+" reference(s) · "+esc(summary.label||""));
  $("#reportLink").classList.add("show");
  refreshStats();
}
function handleEvent(ev){
  if(ev.type==="start"){
    totalRefs=ev.total||0;
    setStatus("Scanning <b>"+totalRefs+"</b> reference(s)…");
  }else if(ev.type==="result"){
    addResult(ev.result);
  }else if(ev.type==="done"){
    finish(ev.summary,ev.elapsed_ms||0);
  }
}
async function fallbackScan(text){
  const resp=await fetch("/api/scan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
  if(!resp.ok)throw new Error(await resp.text());
  const data=await resp.json();
  totalRefs=data.references.length;
  data.references.forEach(addResult);
  finish(data.summary,data.elapsed_ms||0);
}
async function scan(){
  if(scanning)return;
  const text=$("#src").value.trim();
  if(!text){
    const ta=$("#src"); ta.classList.remove("shake"); void ta.offsetWidth; ta.classList.add("shake");
    setStatus("Paste some text first — or load a preset."); ta.focus(); return;
  }
  scanning=true;
  $("#go").disabled=true; $("#editorWrap").classList.add("scanning");
  setMood("scanning"); resetResults();
  setStatus("Contacting registries…");
  try{
    const resp=await fetch("/api/scan-stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    if(!resp.ok||!resp.body)throw new Error(await resp.text());
    const reader=resp.body.getReader(), decoder=new TextDecoder();
    let buf="";
    for(;;){
      const{done,value}=await reader.read();
      if(done)break;
      buf+=decoder.decode(value,{stream:true});
      let nl;
      while((nl=buf.indexOf("\n"))>=0){
        const line=buf.slice(0,nl).trim(); buf=buf.slice(nl+1);
        if(line)handleEvent(JSON.parse(line));
      }
    }
    if(buf.trim())handleEvent(JSON.parse(buf.trim()));
  }catch(e){
    try{await fallbackScan(text);}
    catch(e2){setMood("bad");setStatus("Network error: "+esc(String(e2)));}
  }finally{
    scanning=false; $("#go").disabled=false; $("#editorWrap").classList.remove("scanning");
    if(document.body.dataset.mood==="scanning")setMood("idle");
  }
}
$("#go").addEventListener("click",scan);
$("#clear").addEventListener("click",()=>{$("#src").value="";resetResults();setMood("idle");setStatus("");updateCounts();$("#src").focus();});
$$(".preset").forEach(b=>b.addEventListener("click",()=>{
  $("#src").value=PRESETS[b.dataset.preset]||""; updateCounts(); $("#src").focus();
  setStatus("Preset loaded — hit <b>Verify references</b>.");
}));
$("#heroDemo").addEventListener("click",()=>{
  $("#src").value=PRESETS.thesis; updateCounts();
  document.getElementById("deck").scrollIntoView({behavior:REDUCED?"auto":"smooth"});
  setStatus("Demo loaded — hit <b>Verify references</b>.");
});
document.addEventListener("keydown",e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==="Enter"){e.preventDefault();scan();}
  if(e.key==="/"&&!/textarea|input/i.test(document.activeElement.tagName)){e.preventDefault();$("#src").focus();}
});
/* ---------- live token counter ---------- */
const TOKEN_RES=[
 ["url",/https?:\/\/[^\s<>\])"'`]+/g],
 ["doi",/\b10\.\d{4,9}\/[^\s,;!?)\]}"'<>]+/g],
 ["arxiv",/\b(?:arXiv:\s*)?\d{4}\.\d{4,5}\b/gi],
 ["pmid",/\bPMID:?\s*\d{2,9}\b/gi],
 ["isbn",/\bISBN(?:-1[03])?[-:\s]*[0-9Xx][0-9Xx\-\s]{8,18}[0-9Xx]\b/g]
];
function updateCounts(){
  const text=$("#src").value;
  $("#tokenCounts").innerHTML=TOKEN_RES.map(([kind,re])=>{
    const m=text.match(re); const n=m?m.length:0;
    return '<span class="token-pill" style="color:'+(KIND_COLOR[kind]||"")+'">'+KIND_LABEL[kind]+" <b>"+n+"</b></span>";
  }).join("");
}
let countTimer=null;
$("#src").addEventListener("input",()=>{clearTimeout(countTimer);countTimer=setTimeout(updateCounts,120);});
/* ---------- drag & drop ---------- */
const dz=$("#dropzone"), ta=$("#src");
["dragenter","dragover"].forEach(ev=>ta.addEventListener(ev,e=>{e.preventDefault();dz.classList.add("show");}));
["dragleave","drop"].forEach(ev=>ta.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove("show");}));
ta.addEventListener("drop",e=>{
  const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];
  if(!f)return;
  const rd=new FileReader();
  rd.onload=()=>{$("#src").value=String(rd.result||"");updateCounts();setStatus("Loaded <b>"+esc(f.name)+"</b> — hit Verify.");};
  rd.readAsText(f);
});
dz.addEventListener("click",()=>$("#fileInput").click());
$("#fileInput").addEventListener("change",e=>{
  const f=e.target.files&&e.target.files[0]; if(!f)return;
  const rd=new FileReader();
  rd.onload=()=>{$("#src").value=String(rd.result||"");updateCounts();};
  rd.readAsText(f); e.target.value="";
});
/* ---------- filters (sliding indicator) ---------- */
const fWrap=$("#filters"), fInd=$("#filterInd");
function moveInd(){
  const act=fWrap.querySelector(".filter.active"); if(!act)return;
  fInd.style.width=act.offsetWidth+"px";
  fInd.style.transform="translateX("+(act.offsetLeft-4)+"px)";
}
$$(".filter").forEach(b=>b.addEventListener("click",()=>{
  $$(".filter").forEach(x=>x.classList.remove("active")); b.classList.add("active");
  currentFilter=b.dataset.filter; applyFilter(); moveInd();
}));
window.addEventListener("resize",moveInd);
/* ---------- results interactions ---------- */
$("#results").addEventListener("click",e=>{
  const card=e.target.closest(".result"); if(!card)return;
  card.classList.toggle("open");
});
$("#results").addEventListener("mouseover",e=>{
  const card=e.target.closest(".result"); if(!card)return;
  hoverIndex=Number(card.dataset.index);
  $$(".result").forEach(c=>c.classList.toggle("is-hover",c===card));
});
$("#results").addEventListener("mouseleave",()=>{hoverIndex=null;
  $$(".result").forEach(c=>c.classList.remove("is-hover"));});
/* ---------- spotlight + magnetic ---------- */
document.addEventListener("mousemove",e=>{
  const el=e.target.closest&&e.target.closest(".spot"); if(!el)return;
  const r=el.getBoundingClientRect();
  el.style.setProperty("--mx",(e.clientX-r.left)+"px");
  el.style.setProperty("--my",(e.clientY-r.top)+"px");
});
if(!REDUCED&&matchMedia("(pointer: fine)").matches){
  $$(".magnetic").forEach(btn=>{
    btn.addEventListener("mousemove",e=>{
      const r=btn.getBoundingClientRect();
      const dx=e.clientX-(r.left+r.width/2), dy=e.clientY-(r.top+r.height/2);
      btn.style.transform="translate("+(dx*0.14)+"px,"+(dy*0.22)+"px)";
    });
    btn.addEventListener("mouseleave",()=>{btn.style.transform="";});
  });
}
/* ---------- init ---------- */
resizeCanvas(); seedParticles(); updateCounts(); updateScoreRing(0);
requestAnimationFrame(moveInd);
requestAnimationFrame(loop);
</script></body></html>""".replace("__VERSION__", __version__)

_LAST_REPORT_HTML = ""


def _parse_body(handler: BaseHTTPRequestHandler) -> tuple[str, float] | None:
    """Read and validate a JSON scan body. Sends a 400 on error."""
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = 0
    if length <= 0 or length > MAX_BODY:
        handler.send_response(400)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return None
    try:
        payload = json.loads(handler.rfile.read(length))
        text = str(payload["text"])
    except Exception:
        body = b'Body must be JSON: {"text": "..."}'
        handler.send_response(400)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return None
    try:
        timeout = float(payload.get("timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(1.0, min(30.0, timeout))
    return text, timeout


class Handler(BaseHTTPRequestHandler):
    server_version = f"RefRadar/{__version__}"

    def log_message(self, fmt, *args):  # keep the console clean
        pass

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global _LAST_REPORT_HTML
        path = urlsplit(self.path).path
        if path == "/" or path.startswith("/index"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/report.html":
            if _LAST_REPORT_HTML:
                self._send(200, _LAST_REPORT_HTML.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(404, b"No report yet - scan something first.", "text/plain; charset=utf-8")
        elif path == "/healthz":
            self._send(200, b"ok", "text/plain; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        global _LAST_REPORT_HTML
        path = urlsplit(self.path).path
        if path == "/api/scan":
            parsed = _parse_body(self)
            if parsed is None:
                return
            text, timeout = parsed
            started = time.time()
            refs = extract_references(text)
            results = check_references(refs, timeout=timeout, online=True)
            _LAST_REPORT_HTML = render_html(results, "web paste")
            data = to_dict(results)
            data["elapsed_ms"] = int((time.time() - started) * 1000)
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        elif path == "/api/scan-stream":
            self._handle_stream()
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _handle_stream(self):
        """NDJSON stream: start -> result* -> done, flushed per event."""
        global _LAST_REPORT_HTML
        parsed = _parse_body(self)
        if parsed is None:
            return
        text, timeout = parsed
        refs = extract_references(text)
        started = time.time()

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        def emit(obj: dict) -> None:
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

        try:
            emit({
                "type": "start",
                "total": len(refs),
                "references": [
                    {"index": i, "kind": r.kind, "value": r.value,
                     "line": r.line, "context": r.context}
                    for i, r in enumerate(refs)
                ],
            })
            by_index: dict[int, CheckResult] = {}
            if refs:
                with ThreadPoolExecutor(max_workers=min(6, len(refs))) as pool:
                    futures = {pool.submit(check_reference, r, timeout): i
                               for i, r in enumerate(refs)}
                    for fut in as_completed(futures):
                        idx = futures[fut]
                        try:
                            result = fut.result()
                        except Exception as exc:  # never break the stream
                            result = CheckResult(
                                refs[idx], "unreachable",
                                f"Unexpected error: {exc.__class__.__name__}")
                        by_index[idx] = result
                        emit({"type": "result", "result": result_to_dict(result, idx)})
            ordered = [by_index[i] for i in range(len(refs)) if i in by_index]
            _LAST_REPORT_HTML = render_html(ordered, "web paste")
            emit({
                "type": "done",
                "summary": summarize(ordered),
                "elapsed_ms": int((time.time() - started) * 1000),
                "results": [result_to_dict(r, i) for i, r in enumerate(ordered)],
            })
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away mid-stream; nothing to do


def serve(host: str = "127.0.0.1", port: int = 8787) -> int:
    httpd = ThreadingHTTPServer((host, port), Handler)
    shown = host if host != "0.0.0.0" else "127.0.0.1"
    print(f"RefRadar web app listening on http://{shown}:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
    return 0

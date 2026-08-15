"""
Flume desktop dashboard — HTML/CSS/JS for the macOS pywebview window.

Rendered by SharedDashboard.show() on macOS. Data + actions go through the
same `window.pywebview.api.*` (DashboardApi) bridge the Windows dashboard uses;
native events arrive via `window.VerbalNative(event, payload)`.

Fonts (Geist / JetBrains Mono) are embedded as @font-face data-URIs (see
app.fonts_css) so the WKWebView always renders the design's typefaces rather
than the system fallback.
"""
from app.fonts_css import web_font_css
from app.shared_css import pressed_css

# Every interactive element the dashboard renders (derived by walking the
# `onclick=`/`data-screen=` elements). Row containers (.hrow, .ncard, .meetrow,
# .sniprow, .lrow) and the scrubbers (.pbwave, .dropzone) are deliberately NOT
# here: a 3% scale reads as tactile on a 100px button and as a jolt on a
# full-width row, and the wave scrubber is a drag target, not a button.
_PRESSED_SELECTORS = [
    ".btn", ".chipbtn", ".roundbtn", ".playbtn", ".cbtn", ".ficon", ".navitem",
    ".filters .filt", ".devadd", ".cvimgx", ".fmtbtn", ".dictate", ".segbtn",
    ".toggle", ".tgtpill", ".dchip button", ".reprow button", ".sndots",
    ".snmenu button", ".snx", ".sndel", ".siGoogle", ".siCancel",
    ".mrActs button", ".link", ".chkbox", ".deadbar .dbbtn", ".deadside .dsbtn",
    ".devrm", ".npin", ".nmenu button", ".askNote .ax",
    ".sniptable th.th-trig",
    # meeting detail (MER-46)
    "#mtgDetail .btnS", "#mtgDetail .iconbtn", "#mtgDetail .aiCb", "#mtgDetail .hnTab",
    "#mtgDetail .hnRegen", "#mtgDetail .aiDel", "#mtgDetail .mmTs", "#mtgDetail .teaser",
    "#mtgDetail .mtgBack", "#mtgNotes .btnS", "#mtgNotes .iconbtn", "#mtgNotes .mtgBack",
]

# Line-icon SVGs (1.6 stroke), matching the Flume design.
_IC = {
    "home":   '<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "clock":  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "grid":   '<rect x="3" y="3" width="7" height="7" rx="1.2"/><rect x="14" y="3" width="7" height="7" rx="1.2"/><rect x="3" y="14" width="7" height="7" rx="1.2"/><rect x="14" y="14" width="7" height="7" rx="1.2"/>',
    "lines":  '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "mic":    '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M19 11v1a7 7 0 0 1-14 0v-1"/><path d="M12 19v3"/>',
    "copy":   '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    "send":   '<path d="M22 2 11 13"/><path d="m22 2-7 20-4-9-9-4z"/>',
    "gear":   '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9 2 2 0 1 1-2.7 2.7 1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0 1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.4 2 2 0 1 1-2.8-2.8 1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.4-1.9 2 2 0 1 1 2.8-2.8 1.7 1.7 0 0 0 1.9.3H8a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0 1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3 2 2 0 1 1 2.8 2.8 1.7 1.7 0 0 0-.3 1.9V10a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "sun":    '<circle cx="12" cy="12" r="3.2"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "play":   '<path d="M7 4v16l13-8z"/>',
    "plus":   '<path d="M12 5v14M5 12h14"/>',
    "edit":   '<path d="M17 3 21 7l-13 13H4v-4z"/><path d="m14 6 4 4"/>',
    "book":   '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19h15"/><path d="M9 7h6"/>',
    "bolt":   '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "phone":  '<rect x="6" y="2.5" width="12" height="19" rx="2.4"/><path d="M11 18.5h2"/>',
    # IDI-177: desktops/laptops used to render with the phone glyph.
    "laptop": '<rect x="3.5" y="4.5" width="17" height="11" rx="1.8"/><path d="M2 18.5h20"/>',
    "trash":  '<path d="M4 7h16"/><path d="M9.5 7V5.2A1.2 1.2 0 0 1 10.7 4h2.6a1.2 1.2 0 0 1 1.2 1.2V7"/><path d="M6.5 7l.9 12.1A1.6 1.6 0 0 0 9 20.6h6a1.6 1.6 0 0 0 1.6-1.5L17.5 7"/>',
    "meet":   '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.7-3 2.9-4.5 5.5-4.5s4.8 1.5 5.5 4.5"/><circle cx="17" cy="9" r="2.6"/><path d="M15.8 14.7c2.2.3 3.9 1.6 4.7 4.3"/>',
    "dots":   '<circle cx="5" cy="12" r=".9"/><circle cx="12" cy="12" r=".9"/><circle cx="19" cy="12" r=".9"/>',
    # Insights: a dictation pulse.
    "pulse":  '<path d="M3 12h3.5l2.5-6 4 12 2.5-6H21"/>',
}


def _svg(key):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{_IC[key]}</svg>'


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0e1012;--chrome:#0a0c0e;--card:#17191c;--tx:#f2f2f2;--mut:rgba(240,240,240,.55);--sub:rgba(240,240,240,.42);--acc:#C85A3E;--acc-soft:rgba(200,90,62,.14);--acc-bd:rgba(200,90,62,.35);--bd:rgba(240,240,240,.06);--bd2:rgba(240,240,240,.1);--on:#4ad15a;
  /* MER-46: the meeting detail view (ported from the meeting panel's 31e
     summary) is built on the wider Flume palette — same values as
     meeting_html.py's :root, which is the design system's source. */
  --tx2:rgba(240,240,240,.65);--dim:rgba(240,240,240,.45);--faint:rgba(240,240,240,.35);
  --raised:rgba(240,240,240,.06);--raised2:rgba(240,240,240,.09);
  --bd-faint:rgba(240,240,240,.04);--subtle-alt:rgba(255,255,255,.03);
  --acc-txt:#f0b39a;--acc-softer:rgba(200,90,62,.06);
  --ok:#4ad15a;--rec:#E05049;--rec-soft:#f0a5a0;
  --sp-terra:#D98A72;--sp-slate:#8FA7C2;--sp-sage:#A9BD98;--sp-ochre:#D9B36B}
html,body{height:100%}
body{background:var(--bg);font-family:'Geist',-apple-system,system-ui,sans-serif;color:var(--tx);-webkit-font-smoothing:antialiased;overflow:hidden}
.app{display:grid;grid-template-columns:196px minmax(0,1fr);grid-template-rows:100vh;height:100vh;overflow:hidden}
/* ── sign-in (two-pane) ── */
#signin{position:fixed;inset:0;z-index:50;background:var(--bg);display:grid;grid-template-columns:1fr 1fr}
#signin[hidden]{display:none}
.siLeft{padding:52px 56px;display:flex;flex-direction:column;border-right:1px solid var(--bd)}
.siBrand{display:flex;align-items:center;gap:12px;margin-bottom:auto}
.siLogo{width:44px;height:44px;border-radius:50%;background:#000;overflow:hidden;display:flex;align-items:center;justify-content:center;color:var(--acc);font:600 20px 'Geist'}
.siLogo img{width:100%;height:100%;object-fit:cover}
.siWord{font:700 18px 'Geist';letter-spacing:.04em}
.siHeadline{font:700 46px/1.05 'Geist';letter-spacing:-.02em;margin-bottom:20px}
.siHeadline .acc{color:var(--acc)}
.siLead{font:400 15px/1.6 'Geist';color:var(--mut);max-width:420px;margin-bottom:auto}
.siFoot{font:600 11px 'JetBrains Mono';letter-spacing:.14em;color:var(--sub)}
.siRight{padding:52px 56px;display:flex;flex-direction:column;justify-content:center;max-width:520px}
.siTitle{font:700 30px 'Geist';letter-spacing:-.01em;margin-bottom:8px}
.siSub{font:400 14px/1.5 'Geist';color:var(--mut);margin-bottom:26px;max-width:380px}
.siGoogle{display:flex;align-items:center;justify-content:center;gap:11px;background:#f2f2f2;color:#111;border:0;border-radius:14px;padding:16px;cursor:pointer;font:600 15px 'Geist';max-width:400px}
.siGoogle:hover{filter:brightness(.96)}.siGoogle:disabled{opacity:.6;cursor:default}
.siErr{display:flex;align-items:flex-start;gap:9px;margin-top:12px;max-width:400px;
  font:500 12.5px/1.5 'Geist';color:#f0a5a0}
.siErr[hidden]{display:none}
.siErr .ebang{flex:none;width:16px;height:16px;border-radius:50%;background:rgba(224,80,73,.16);
  color:#f0a5a0;display:flex;align-items:center;justify-content:center;font:700 10px 'Geist';margin-top:1px}
/* Neutral one-shot notice on the same pane (IDI-170) — "Your account has been
   deleted." is confirmation, not an error, so it must NOT read as red/failed. */
.siNote{display:flex;align-items:flex-start;gap:9px;margin-top:12px;max-width:400px;
  font:500 12.5px/1.5 'Geist';color:var(--mut)}
.siNote[hidden]{display:none}
.siNote .ntick{flex:none;width:16px;height:16px;border-radius:50%;background:rgba(242,242,242,.10);
  color:var(--tx);display:flex;align-items:center;justify-content:center;font:700 9px 'Geist';margin-top:1px}
.siCancel{background:0;border:0;color:var(--mut);cursor:pointer;font:500 13px 'Geist';
  padding:14px 0 0;text-align:left;max-width:400px}
.siCancel[hidden]{display:none}
.siCancel:hover{color:var(--tx)}
.siTerms{font:400 12px/1.5 'Geist';color:var(--sub);margin-top:8px;max-width:400px}
/* ── session-expired banner (IDI-166) — a dead refresh token keeps you
   "signed in" but breaks every JWT-only action, so say so out loud ── */
.deadbar{display:flex;align-items:center;gap:10px;background:rgba(224,80,73,.12);
  border:1px solid rgba(224,80,73,.34);border-radius:10px;padding:10px 12px;margin:0 0 16px}
.deadbar .dbtx{flex:1;min-width:0;font:500 12.5px/1.4 'Geist';color:#f0a5a0}
.deadbar .dbbtn{flex:none;border:0;border-radius:8px;background:#f2f2f2;color:#0e1012;
  cursor:pointer;font:600 12px 'Geist';padding:8px 12px}
.deadbar .dbbtn:hover{filter:brightness(.94)}
.deadside{margin:12px 0 0;padding:10px;border-radius:9px;background:rgba(224,80,73,.12);
  border:1px solid rgba(224,80,73,.34)}
.deadside[hidden]{display:none}
.deadside .dstx{font:500 11.5px/1.4 'Geist';color:#f0a5a0;margin-bottom:8px}
.deadside .dsbtn{width:100%;border:0;border-radius:7px;background:#f2f2f2;color:#0e1012;
  cursor:pointer;font:600 11.5px 'Geist';padding:7px 8px}
.deadside .dsbtn:hover{filter:brightness(.94)}
/* ── get-started wizard ── */
#getstarted{position:fixed;inset:0;z-index:50;background:var(--bg);overflow-y:auto;display:flex;justify-content:center}
#getstarted[hidden]{display:none}
.gsInner{width:100%;max-width:720px;padding:48px 40px}
.gsstep{font:600 11px 'JetBrains Mono';letter-spacing:.18em;color:var(--mut);margin-bottom:12px}
.gsbar{height:4px;border-radius:2px;background:rgba(240,240,240,.08);overflow:hidden;margin-bottom:30px}
.gsbar>i{display:block;height:100%;background:var(--acc);transition:width .3s}
.gstitle{font:700 30px 'Geist';letter-spacing:-.01em;margin-bottom:8px}
.gslead{font:400 14.5px/1.55 'Geist';color:var(--mut);margin-bottom:28px;max-width:520px}
.permrow{display:flex;align-items:center;gap:16px;background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:18px 20px;margin-bottom:12px}
.permrow.need{border-color:var(--acc-bd)}
.permicon{width:46px;height:46px;border-radius:12px;background:rgba(240,240,240,.06);display:flex;align-items:center;justify-content:center;flex:none;color:var(--tx)}
.permicon.ok{background:rgba(74,209,90,.16);color:var(--on)}
.permicon.need{background:var(--acc-soft);color:var(--acc)}
.permicon svg{width:22px;height:22px;stroke:currentColor}
.perminfo{flex:1;min-width:0}
.permname{font:600 15.5px 'Geist'}.permname .opt{font:500 12px 'Geist';color:var(--sub);margin-left:8px}
.permsub{font:400 12.5px 'Geist';color:var(--mut);margin-top:2px}
.permpill{font:600 12px 'Geist';color:var(--on);border:1px solid rgba(74,209,90,.4);border-radius:999px;padding:6px 12px;display:flex;align-items:center;gap:7px;flex:none}
.permpill .pdot{width:7px;height:7px;border-radius:50%;background:var(--on)}
.gsnav{display:flex;align-items:center;gap:10px;margin-top:26px}
.gsnav .grow{flex:1}
.acctav{width:38px;height:38px;border-radius:50%;background:var(--acc);color:#fff5ea;display:flex;align-items:center;justify-content:center;font:600 15px 'Geist';flex:none}
.sidebar{background:var(--chrome);border-right:1px solid var(--bd);display:flex;flex-direction:column;padding:18px 12px}
.brand{display:flex;align-items:center;gap:11px;padding:2px 6px 0}
.brandmark{color:var(--acc);font:600 20px 'Geist'}.brandname{font:700 15px 'Geist';letter-spacing:.02em}
.navhead{font:500 10px 'JetBrains Mono';color:var(--mut);letter-spacing:.14em;margin:24px 8px 8px}
.navitem{display:flex;align-items:center;gap:12px;padding:10px;border-radius:9px;background:transparent;border:0;color:var(--mut);cursor:pointer;text-align:left;font:500 13px 'Geist';width:100%}
.navitem .nico{width:18px;height:18px;display:flex}.navitem .nico svg{width:18px;height:18px}
.navitem:hover{background:rgba(240,240,240,.04)}
.navitem.active{background:rgba(240,240,240,.07);color:var(--tx);font-weight:600}
.nbadge{margin-left:auto;color:var(--acc);font:600 11px 'Geist'}
.filters .filt{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:8px;background:transparent;border:0;color:var(--mut);cursor:pointer;font:500 12.5px 'Geist';width:100%}
.filters .filt.active{color:var(--tx);font-weight:600}
.fcount{margin-left:auto;color:var(--sub);font:500 12px 'Geist'}
.devlist{display:flex;flex-direction:column;gap:12px;padding:2px 10px}
.devrow{display:flex;align-items:center;gap:10px;font:400 12.5px 'Geist';color:var(--tx)}.devrow.off{color:var(--mut)}
.ddot{width:7px;height:7px;border-radius:50%;background:var(--sub)}.ddot.on{background:var(--on)}
.sfooter{margin-top:auto;display:flex;align-items:center;gap:11px;padding:12px 6px 2px;border-top:1px solid var(--bd)}
.avatar{width:30px;height:30px;border-radius:50%;background:var(--acc);color:#fff5ea;display:flex;align-items:center;justify-content:center;font:600 13px 'Geist'}
.uname{font:600 13px 'Geist'}
.ficon{background:transparent;border:0;color:var(--mut);cursor:pointer;padding:4px;display:flex}.ficon svg{width:16px;height:16px}.ficon.push{margin-left:auto}.ficon:hover{color:var(--tx)}
.main{padding:24px 28px;height:100%;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain}
.screen[hidden]{display:none}
/* The visible screen fills the grid row; min-height:0 lets the inner .main be the
   real scroller (without this the height chain can collapse to content height and
   body{overflow:hidden} clips everything past the fold — e.g. after Meetings). */
.screen{height:100%;min-height:0;overflow:hidden}
.mhead{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:24px}
.eyebrow{font:400 11px 'Geist';color:var(--mut);margin-bottom:5px}
.title{font:600 24px 'Geist';letter-spacing:-.01em}
.statuspill{display:flex;align-items:center;gap:8px;padding:9px 15px;border-radius:999px;background:rgba(74,209,90,.10);border:1px solid rgba(74,209,90,.32);color:#8ee69a;font:600 12.5px 'Geist'}
.statuspill.rec{background:var(--acc-soft);border-color:var(--acc-bd);color:#f0b39a}
.sdot{width:7px;height:7px;border-radius:50%;background:currentColor}
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:28px}
.fcard{border-radius:18px;padding:16px 16px 18px;min-height:150px;display:flex;flex-direction:column}
.fcard.cream{background:#EADFCE;color:#2a1f18}.fcard.sage{background:#DDE4D3;color:#1e2418}.fcard.plum{background:#e6dae4;color:#221820}
.disc{width:38px;height:38px;border-radius:50%;background:#1a1512;color:#EADFCE;display:flex;align-items:center;justify-content:center;margin-bottom:auto}
.fcard.sage .disc{background:#1e2418;color:#DDE4D3}.fcard.plum .disc{background:#221820;color:#e6dae4}.disc svg{width:16px;height:16px}
.fnum{font:600 24px 'Geist';letter-spacing:-.02em;margin-top:20px}.flabel{font:600 14px 'Geist';margin-top:6px}.fsub{font:400 12px 'Geist';opacity:.62;margin-top:3px}
/* ── Insights ─────────────────────────────────────────────────────────────── */
.inshero{position:relative;background:var(--card);border:1px solid var(--bd);border-radius:20px;padding:24px 20px 20px;display:flex;flex-direction:column;align-items:center;margin-bottom:14px}
.inshero .hnum{font:600 62px 'Geist';letter-spacing:-.04em;line-height:1;margin-top:-78px}
.inshero .hnum.na{font-size:44px;color:var(--mut);margin-top:-66px}
.inshero .hunit{font:500 10.5px 'JetBrains Mono';letter-spacing:.2em;color:var(--mut);margin-top:5px}
.inshero .hbadge{margin-top:13px;font:600 12px 'Geist';color:#0e1012;background:#f2f2f2;border-radius:999px;padding:7px 16px}
.inshero .hsub{font:400 13px 'Geist';color:var(--tx2);margin-top:11px;text-align:center}
.inshero .hsub b{color:var(--tx)}
.insband{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:14px}
.itile{background:var(--card);border:1px solid var(--bd);border-radius:18px;padding:15px 17px;min-height:118px;display:flex;flex-direction:column;justify-content:flex-end}
.itile.cream{background:#EADFCE;border:0;color:#2a1f18}
.itile.sage{background:#DDE4D3;border:0;color:#1e2418}
.itile.plum{background:#e6dae4;border:0;color:#221820}
.itile .tk{font:500 9.5px 'JetBrains Mono';letter-spacing:.14em;text-transform:uppercase;color:var(--mut);margin-bottom:auto}
.itile.cream .tk{color:rgba(42,31,24,.55)}.itile.sage .tk{color:rgba(30,36,24,.55)}.itile.plum .tk{color:rgba(34,24,32,.55)}
.itile .tv{font:600 24px 'Geist';letter-spacing:-.03em;margin-top:16px}
.itile .ts{font:400 11px 'Geist';color:var(--sub);margin-top:4px}
.itile.cream .ts{color:rgba(42,31,24,.6)}.itile.sage .ts{color:rgba(30,36,24,.6)}.itile.plum .ts{color:rgba(34,24,32,.6)}
.itile .up{font:600 10.5px 'JetBrains Mono';margin-left:7px;vertical-align:3px;color:inherit;opacity:.7}
.inscard{background:var(--card);border:1px solid var(--bd);border-radius:18px;padding:18px 20px;margin-bottom:14px}
.inscard .chd{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--mut);text-transform:uppercase;margin-bottom:14px;display:flex;justify-content:space-between}
.inscard .chd .csub{letter-spacing:.02em;color:var(--sub);text-transform:none}
.inshm{display:grid;grid-auto-flow:column;gap:3px;justify-content:start}
.inshm i{border-radius:3px;background:#1f2225}
.inshm i.gl{box-shadow:0 0 6px rgba(200,90,62,.55)}
.inshmfoot{display:flex;justify-content:space-between;margin-top:12px;font:400 11px 'Geist';color:var(--sub)}
.inshmfoot b{color:var(--tx);font-weight:600}
.inshmleg{display:flex;align-items:center;gap:4px}
.inshmleg i{width:9px;height:9px;border-radius:2.5px;display:inline-block}
.inssplit{display:grid;grid-template-columns:1fr 1fr;gap:0;padding:18px 0}
.inssplit>div{padding:0 20px;min-width:0}
.inssplit>div:first-child{border-right:1px solid var(--bd-faint)}
.inssub{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--mut);text-transform:uppercase;margin-bottom:12px}
.insabar{margin-bottom:10px}
.insabar .arow{display:flex;justify-content:space-between;font:500 12px 'Geist';margin-bottom:5px;gap:10px}
.insabar .arow .an{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.insabar .arow .av{font:500 11px 'JetBrains Mono';color:var(--mut);flex:none}
.insabar .atr{height:7px;border-radius:4px;background:rgba(240,240,240,.05)}
.insabar .atr i{display:block;height:100%;border-radius:4px}
.inshours{display:flex;align-items:flex-end;gap:3px;height:64px}
.inshours i{flex:1;background:rgba(240,240,240,.14);border-radius:3px 3px 0 0;min-height:2px}
.inshours i.pk{background:var(--acc)}
.inshfoot{display:flex;justify-content:space-between;font:400 10px 'JetBrains Mono';color:var(--sub);margin-top:6px;letter-spacing:.06em}
.inspeak{font:400 11.5px 'Geist';color:var(--sub);margin-top:10px}
.inspeak b{color:var(--tx);font-weight:600}
.insempty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:80px 20px;text-align:center}
.insempty .bigmic{width:64px;height:64px;border-radius:50%;background:var(--acc-soft);border:1px solid var(--acc-bd);display:flex;align-items:center;justify-content:center;color:var(--acc);margin-bottom:18px}
.insempty .bigmic svg{width:26px;height:26px}
.insempty h2{font:700 20px 'Geist';letter-spacing:-.01em;margin-bottom:8px}
.insempty p{font:400 13px/1.55 'Geist';color:var(--mut);max-width:380px}
#insTip{position:fixed;z-index:80;pointer-events:none;background:#26282b;border:1px solid var(--bd2);border-radius:8px;padding:6px 9px;font:500 11px 'Geist';color:var(--tx);display:none;white-space:nowrap;box-shadow:0 6px 18px rgba(0,0,0,.4)}
#insTip .tmut{color:var(--mut)}
.sechead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:14px}.sechead h2{font:600 15px 'Geist'}
.link{font:500 12.5px 'Geist';color:var(--mut);cursor:pointer}
.rows{display:flex;flex-direction:column;gap:10px}
.lrow{display:flex;align-items:center;gap:16px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px}
.ltime{font:500 12px 'JetBrains Mono';color:var(--mut);letter-spacing:.04em;flex:none;width:64px}
.ltext{flex:1;font:400 13px 'Geist';color:rgba(240,240,240,.9);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tag{font:600 10.5px 'Geist';padding:6px 12px;border-radius:8px;flex:none}
.tag.iphone{background:var(--acc);color:#fff5ea}.tag.ipad{background:#4a6494;color:#eaf1ff}.tag.local{background:rgba(240,240,240,.09);color:var(--mut)}
.cbtn{width:34px;height:34px;border-radius:8px;background:transparent;border:0;color:var(--mut);cursor:pointer;display:flex;align-items:center;justify-content:center}.cbtn svg{width:16px;height:16px}.cbtn:hover{background:rgba(240,240,240,.06)}
.threepane{display:grid;grid-template-columns:1fr 1fr;height:100vh;padding:0;overflow:hidden}
.listcol{padding:24px 22px;overflow:auto;border-right:1px solid var(--bd)}
.searchbox{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:11px 14px;color:var(--mut);font:400 12.5px 'Geist';margin:16px 0 20px}.searchbox svg{width:16px;height:16px}.searchbox input{background:transparent;border:0;outline:0;color:var(--tx);font:400 12.5px 'Geist';flex:1}
.daylabel{font:500 10px 'JetBrains Mono';color:var(--mut);letter-spacing:.14em;margin:14px 0 10px}
.hrow{border-radius:14px;padding:14px;margin-bottom:10px;cursor:pointer}
.hrow.active{background:rgba(200,90,62,.06);border:1px solid var(--acc-bd)}.hrow:not(.active):hover{background:var(--card)}
.hrtop{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.htime{font:400 11px 'Geist';color:var(--mut)}
.htitle{font:600 14px 'Geist';margin-bottom:4px}
.hprev{font:400 12px 'Geist';color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.preview{padding:24px;display:flex;flex-direction:column;overflow:auto}
.pvhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.pvmeta{font:500 10px 'JetBrains Mono';color:var(--mut);letter-spacing:.14em}
.pvtagrow{display:flex;align-items:center;gap:10px;margin-bottom:14px}.pvsub{font:400 11px 'Geist';color:var(--mut)}
.transcript{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:16px;font:400 13.5px/1.55 'Geist';color:rgba(240,240,240,.92);flex:1;margin-bottom:14px}
.histedit{width:100%;resize:none;outline:0;-webkit-appearance:none}.histedit:focus{border-color:var(--acc-bd)}
.tag.fail{background:rgba(232,82,42,.18);color:var(--acc)}
.hrow.failed .htitle{color:var(--acc)}
.failbox{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:8px;padding:24px;background:var(--card);border:1px solid var(--bd);border-radius:16px;margin-bottom:14px}
.failicon{width:46px;height:46px;border-radius:50%;background:rgba(232,82,42,.16);color:var(--acc);display:flex;align-items:center;justify-content:center;font:600 22px 'Geist'}
.failtitle{font:600 15px 'Geist';color:var(--tx)}
.failsub{font:400 12.5px/1.5 'Geist';color:var(--mut);max-width:300px}
.playbar{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:12px 16px;margin-bottom:14px}
.playbtn{width:44px;height:44px;border-radius:50%;border:0;background:#f2f2f2;color:#0e1012;cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
.playbtn:hover{filter:brightness(.95)}.playbtn svg{width:17px;height:17px}
.pbcol{flex:1;min-width:0}
.pbwave{display:flex;align-items:center;gap:2.5px;height:26px;cursor:pointer}
.pbwave i{width:2.5px;border-radius:2px;background:rgba(240,240,240,.24);flex:none}
.pbwave i.on{background:var(--acc)}
.pbtime{display:flex;justify-content:space-between;margin-top:6px}
.pbtime span{font:500 10.5px 'JetBrains Mono';color:var(--mut)}
.pvactions{display:flex;gap:8px}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;border-radius:12px;padding:12px 14px;font:600 12.5px 'Geist';cursor:pointer;border:1px solid transparent}.btn svg{width:14px;height:14px}
.btn.ghost{background:transparent;border-color:var(--bd2);color:var(--tx);flex:1}
.btn.primary{background:#f2f2f2;color:#0e1012}
.empty{color:var(--sub);font:400 12.5px 'Geist';padding:40px 0;text-align:center}
.dropzone{display:flex;align-items:center;gap:16px;border:1px dashed var(--acc-bd);background:rgba(200,90,62,.05);border-radius:16px;padding:22px 20px;margin-bottom:22px}
.dzicon{width:52px;height:52px;border-radius:12px;background:var(--acc-soft);color:var(--acc);display:flex;align-items:center;justify-content:center}.dzicon svg{width:22px;height:22px}
.dztitle{font:600 15px 'Geist'}.dzsub{font:400 12px 'Geist';color:var(--mut);margin-top:4px}
.canvasArea{width:100%;min-height:220px;background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:16px;color:var(--tx);font:400 13px/1.5 'Geist';resize:vertical;outline:0}
.cvimgwrap{position:relative;display:inline-block;max-width:100%;margin-bottom:12px}
.cvimg{max-width:100%;max-height:300px;border-radius:14px;border:1px solid var(--bd);display:block}
.cvimgx{position:absolute;top:8px;right:8px;width:28px;height:28px;border-radius:50%;border:0;background:rgba(0,0,0,.6);color:#fff;cursor:pointer;font:600 13px 'Geist'}
.cvimgx:hover{background:rgba(0,0,0,.8)}
.cvmsg{font:500 11px 'JetBrains Mono';color:var(--mut);letter-spacing:.03em;margin-top:10px;min-height:14px}
.canvasBar{display:flex;gap:8px;align-items:center;margin-top:12px}
.chipbtn{background:var(--card);border:1px solid var(--bd2);color:var(--tx);border-radius:10px;padding:10px 16px;font:600 12.5px 'Geist';cursor:pointer}
.ncard{border-radius:14px;padding:14px;margin-bottom:10px;cursor:pointer}
.ncard.active{background:rgba(200,90,62,.06);border:1px solid var(--acc-bd)}.ncard:not(.active):hover{background:var(--card)}
.nctitle{font:600 14px 'Geist'}
.ncprev{font:400 12px 'Geist';color:var(--mut);margin:6px 0 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ncmeta{font:500 10px 'JetBrains Mono';color:var(--sub);letter-spacing:.1em}
.roundbtn{width:38px;height:38px;border-radius:50%;background:var(--acc-soft);color:var(--acc);border:0;cursor:pointer;display:flex;align-items:center;justify-content:center}.roundbtn svg{width:18px;height:18px}
.editor{padding:24px;display:flex;flex-direction:column;overflow:auto}
.edtitle{font:700 24px 'Geist';border:0;background:transparent;color:var(--tx);outline:0;margin-bottom:12px;width:100%}
.edbody{flex:1;border:0;background:transparent;color:rgba(240,240,240,.85);font:400 15px/1.6 'Geist';outline:0;resize:none;width:100%}
.notetoolbar{display:flex;align-items:center;gap:6px;margin-bottom:14px;flex-wrap:wrap}
.fmtbtn{width:32px;height:32px;border-radius:8px;border:1px solid var(--bd);background:transparent;color:var(--mut);cursor:pointer;display:flex;align-items:center;justify-content:center;font:600 14px 'Geist';line-height:1}
.fmtbtn:hover{color:var(--tx);background:rgba(240,240,240,.05)}
.fmtbtn i{font-style:italic}.fmtbtn u{text-decoration:underline}
.fmtsep{width:1px;height:20px;background:var(--bd);margin:0 4px}
.dictate{margin-left:auto;display:flex;align-items:center;gap:8px;border-radius:10px;border:1px solid var(--acc-bd);background:var(--acc-soft);color:var(--acc);cursor:pointer;padding:7px 13px;font:600 12.5px 'Geist'}
.dictate:hover{filter:brightness(1.05)}
.dictate.rec{background:var(--acc);color:#2a1710;border-color:var(--acc)}
.dictate svg{width:15px;height:15px;stroke:currentColor}
.dictate .pulse{width:8px;height:8px;border-radius:50%;background:currentColor;animation:npulse 1s ease-in-out infinite}
@keyframes npulse{0%,100%{opacity:1}50%{opacity:.25}}
.notesave{font:500 10.5px 'JetBrains Mono';color:var(--sub);letter-spacing:.04em;min-width:64px;text-align:right}
.notebody{flex:1;overflow-y:auto;border:0;background:transparent;color:rgba(240,240,240,.9);font:400 15px/1.7 'Geist';outline:0;width:100%;min-height:200px}
.notebody:empty:before{content:attr(data-ph);color:var(--sub)}
.notebody b,.notebody strong{font-weight:700;color:var(--tx)}
.notebody ul,.notebody ol{margin:6px 0 6px 20px}.notebody li{margin:3px 0}
.notebody ul.chk{list-style:none;margin-left:2px}.notebody ul.chk li{margin:4px 0}
.notebody h3{font:700 17px 'Geist';color:var(--tx);margin:12px 0 5px}
.notebody h4{font:700 14.5px 'Geist';color:var(--tx);margin:10px 0 4px}
.notebody h5{font:700 13px 'Geist';color:var(--tx);margin:8px 0 3px}
.notebody code{font:500 13px 'JetBrains Mono';background:rgba(240,240,240,.08);padding:1px 5px;border-radius:5px}
.notebody pre{background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:8px;padding:10px 12px;font:500 12.5px 'JetBrains Mono';white-space:pre-wrap;overflow-x:auto;margin:8px 0}
.dcards{display:flex;flex-direction:column;gap:12px;margin-bottom:18px}
/* Devices screen. The scroller is still `.main` (Hard Rule #23 — do NOT nest a
   second scroller here); the header just sticks to the top of it so the device
   count and "Pair a device" stay reachable with a long list. */
.dhead{position:sticky;top:0;z-index:5;background:var(--bg);padding:2px 0 14px;margin-bottom:10px}
.dgroup{margin-bottom:22px}
.dgrouphead{display:flex;align-items:center;gap:9px;margin-bottom:11px;font:600 10.5px 'Geist';letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.dgrouphead .ghdot{width:6px;height:6px;border-radius:50%;background:var(--mut);flex:none}
.dgrouphead .ghdot.on{background:#4ad15a;box-shadow:0 0 0 3px rgba(74,209,90,.16)}
.dgrouphead .gcount{font:500 10.5px 'JetBrains Mono';letter-spacing:.04em;color:var(--mut);opacity:.8}
.dgrouphead .gclean{margin-left:auto;border:1px solid var(--bd);background:transparent;color:var(--mut);border-radius:8px;padding:5px 10px;font:600 10px 'Geist';letter-spacing:.1em;text-transform:uppercase;cursor:pointer}
.dgrouphead .gclean:hover{color:#f0b39a;border-color:var(--acc-bd);background:var(--acc-soft)}
/* Offline rows recede so the live device is what the eye lands on. */
.dcard.off{opacity:.62}
.dcard.off:hover{opacity:1}
.tgtpill .tdot{display:inline-block;width:5px;height:5px;border-radius:50%;background:#4ad15a;margin-right:6px;vertical-align:middle}
.devhead{display:flex;align-items:center}
.devadd{margin-left:auto;width:20px;height:20px;border-radius:6px;border:0;background:rgba(240,240,240,.06);color:var(--mut);cursor:pointer;font:400 15px 'Geist';line-height:1;display:flex;align-items:center;justify-content:center}
.devadd:hover{background:rgba(200,90,62,.18);color:var(--acc)}
.pairpanel{display:flex;flex-direction:column;align-items:center;gap:12px;background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:26px 20px;margin-bottom:18px;text-align:center}
.qrwrap{width:196px;height:196px;background:#fff;border-radius:14px;padding:12px;display:flex;align-items:center;justify-content:center}
.qrwrap svg{width:100%;height:100%;display:block}
.pairtitle{font:600 15px 'Geist';color:var(--tx)}
.pairsub{font:400 12.5px/1.5 'Geist';color:var(--mut);max-width:280px}
.pairok{width:54px;height:54px;border-radius:50%;background:rgba(74,209,90,.16);color:var(--on);display:flex;align-items:center;justify-content:center;font:600 26px 'Geist'}
.tgtwrap{margin-bottom:18px}
.tgtlabel{font:600 10px 'JetBrains Mono';letter-spacing:.12em;color:var(--sub);margin-bottom:9px}
.tgtpills{display:flex;flex-wrap:wrap;gap:8px}
.tgtpill{border:1px solid var(--bd2);background:transparent;color:var(--mut);border-radius:999px;padding:7px 14px;cursor:pointer;font:500 12.5px 'Geist'}
.tgtpill:hover{color:var(--tx)}
.tgtpill.on{background:var(--acc-soft);border-color:var(--acc-bd);color:var(--acc)}
.dcard{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:14px}
.dtile{width:46px;height:46px;border-radius:10px;background:rgba(240,240,240,.06);color:var(--tx);display:flex;align-items:center;justify-content:center}.dtile svg{width:20px;height:20px}
.dinfo{flex:1}.dname{font:600 15px 'Geist';display:flex;align-items:center;gap:10px}
.defbadge{font:600 9.5px 'JetBrains Mono';color:#f0b39a;border:1px solid var(--acc-bd);background:var(--acc-soft);padding:3px 8px;border-radius:999px;letter-spacing:.08em}
.dmeta{font:400 12px 'Geist';color:var(--mut);margin-top:3px}
.statpill{display:flex;align-items:center;gap:7px;padding:7px 13px;border-radius:999px;font:600 10.5px 'Geist'}
.statpill.on{background:rgba(74,209,90,.10);border:1px solid rgba(74,209,90,.32);color:#8ee69a}
.statpill.offl{background:rgba(240,240,240,.05);border:1px solid var(--bd);color:var(--mut)}.statpill .pdot{width:6px;height:6px;border-radius:50%;background:currentColor}
.devrm{width:32px;height:32px;border-radius:9px;border:1px solid var(--bd);background:transparent;color:var(--mut);cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
.devrm svg{width:15px;height:15px}
.devrm:hover{color:#f0b39a;border-color:var(--acc-bd);background:var(--acc-soft)}
/* Settings — grouped rail (one group in view; see renderSettings). The pane, not
   #settingsMain, is the scroller now, so each group's scroll position is its own. */
#settingsMain.setshell{padding:0;overflow:hidden;display:grid;grid-template-columns:176px minmax(0,1fr)}
.setrail{border-right:1px solid var(--bd);padding:22px 10px;display:flex;flex-direction:column;gap:1px;overflow-y:auto;overscroll-behavior:contain}
.setrail .srl{font:600 10px 'JetBrains Mono';letter-spacing:.14em;text-transform:uppercase;color:var(--sub);padding:0 9px 10px}
.sritem{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;text-align:left;padding:8px 9px;border:0;border-radius:8px;background:none;color:var(--mut);font:500 12.5px 'Geist';cursor:pointer}
.sritem:hover{background:rgba(240,240,240,.05);color:var(--tx)}
.sritem.on{background:var(--acc-soft);color:var(--tx);box-shadow:inset 2px 0 0 var(--acc)}
.sritem:focus-visible{outline:2px solid var(--acc-bd);outline-offset:-2px}
.sritem em{font:500 10px 'JetBrains Mono';font-style:normal;color:var(--sub);flex:none}
.sritem.on em{color:var(--mut)}
.setpane{padding:24px 28px;min-width:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain}
.setpane .setlede{max-width:62ch;margin-bottom:0}
.setpane .ssection:first-of-type{margin-top:18px}
/* Meetings/Transform render their own <h3> heading; the pane already titles the
   group, so suppress theirs rather than editing those renderers. */
.setpane #meetSettings>h3:first-child,.setpane #tfSettings>h3:first-child{display:none}
.ssection{margin-top:26px}.ssection h3{font:600 12.5px 'Geist';margin-bottom:4px}.ssub{font:400 11px 'Geist';color:var(--mut);margin-bottom:14px}
.dlabel2{font:600 10px 'JetBrains Mono';letter-spacing:.1em;color:var(--sub);margin-bottom:9px}
.dictchips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.dchip{display:inline-flex;align-items:center;gap:7px;background:var(--acc-soft);color:var(--acc);border:1px solid var(--acc-bd);border-radius:999px;padding:5px 6px 5px 12px;font:500 12.5px 'Geist'}
.dchip button{background:0;border:0;color:var(--acc);cursor:pointer;font:600 11px 'Geist';opacity:.7;padding:0 2px}.dchip button:hover{opacity:1}
.dictadd{display:flex;gap:8px;align-items:center}
.dictadd{flex-wrap:wrap}
.dictadd input{flex:1;min-width:0;background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:8px;padding:9px 12px;color:var(--tx);font:400 12.5px 'Geist';outline:0}
.dictadd input:focus{border-color:var(--acc-bd)}
.reprows{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}
.reprow{display:flex;align-items:center;gap:10px;background:rgba(240,240,240,.04);border:1px solid var(--bd);border-radius:8px;padding:8px 12px}
.reprow .rfrom{color:var(--mut);font:400 12.5px 'Geist'}.reprow .rto{color:var(--tx);font:600 12.5px 'Geist'}
.reprow button{margin-left:auto;background:0;border:0;color:var(--mut);cursor:pointer;font:600 12px 'Geist'}.reprow button:hover{color:var(--acc)}
.rarrow{color:var(--sub);font:400 13px 'Geist'}
.dictgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;align-items:start}
.dictcol{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:18px}
.dcolhead{margin-bottom:14px}.dcolhead h3{font:600 14px 'Geist';margin-bottom:3px}
.dictcol .dictchips,.dictcol .reprows{max-height:340px;overflow-y:auto}
.scard{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px;margin-bottom:12px}
/* `.scard` is not a flex container, so every style="flex-direction:row" on one
   was inert and those cards silently stacked (account, delete, clear history).
   Use the class instead of re-inlining the lie. */
.scard.row{display:flex;flex-direction:row;align-items:center;gap:12px}
.scard.row .grow{flex:1;min-width:0}
/* .btn is a full-width flex block by default, which only shows once the card is
   a real row — pin the trailing action to its own content. */
.scard.row .btn{flex:none;width:auto;white-space:nowrap}
.sname{font:600 13.5px 'Geist';color:var(--tx)}
.sdesc{font:400 12px 'Geist';color:var(--mut)}
.sdanger{color:#f0b39a}
.btn.slim{width:auto;padding:5px 12px;margin-left:8px}
/* Meetings/Transform emit bare <select>s; without this they render as raw OS
   widgets next to the styled .field selects. Same treatment, one source. */
.setpane select{background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:8px;padding:7px 30px 7px 10px;color:var(--tx);font:400 12px 'Geist';outline:0;-webkit-appearance:none;appearance:none;cursor:pointer;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23f2f2f2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center}
.setpane select:focus{border-color:var(--acc-bd)}
.setpane select option{background:#17191c;color:#f2f2f2}
.setpane .field select{width:100%;padding:10px 34px 10px 12px;font-size:12.5px}
.field{margin-bottom:12px}.field label{display:block;font:600 10px 'JetBrains Mono';color:var(--mut);letter-spacing:.08em;margin-bottom:7px}
.field input,.field textarea,.field select{width:100%;background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:8px;padding:10px 12px;color:var(--tx);font:400 12.5px 'Geist';outline:0}
.field input:focus,.field textarea:focus,.field select:focus{border-color:var(--acc-bd)}
.field select{-webkit-appearance:none;appearance:none;cursor:pointer;padding-right:34px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23f2f2f2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
.field select option{background:#17191c;color:#f2f2f2}
.saverow{display:flex;align-items:center;gap:12px;margin-top:6px}
/* Models pane. A grouped selection list — one card, hairline dividers, a real
   selection mark. Two earlier drafts were wrong in opposite directions: a spec sheet
   with diagrams and legends (read as homework), then a rotating canvas blueprint
   (read as a screensaver). What is left is the thing itself, made well. */
.scard.tight{padding:0;gap:0;overflow:hidden}
.prow{position:relative;display:flex;align-items:center;gap:13px;padding:13px 15px;
  cursor:pointer;border-bottom:1px solid var(--hair);transition:background .12s}
.prow:last-child{border-bottom:none}
.prow:hover{background:rgba(244,243,241,.035)}
.prow.on{background:linear-gradient(90deg, rgba(200,90,62,.13), rgba(200,90,62,.05) 62%, transparent)}
.prow input{position:absolute;opacity:0;pointer-events:none}
/* The selection mark: an empty ring that fills and takes a tick. Clearer down a long
   list than a tinted background alone, and it survives the accent being subtle. */
.pr-mark{flex:none;width:17px;height:17px;border-radius:50%;border:1.5px solid var(--hair2);
  position:relative;transition:border-color .12s,background .12s}
.prow:hover .pr-mark{border-color:var(--ink3)}
.prow.on .pr-mark{border-color:var(--accent);background:var(--accent)}
.prow.on .pr-mark::after{content:"";position:absolute;left:5px;top:2px;width:4px;height:8px;
  border:solid #fff;border-width:0 1.6px 1.6px 0;transform:rotate(43deg)}
.pr-tx{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}
.pr-h{display:flex;align-items:baseline;gap:0}
.pr-tx b{font:600 13.5px Geist;color:var(--ink2);letter-spacing:-.005em}
.prow.on .pr-tx b{color:var(--ink)}
.pr-tx em{font:500 9px "JetBrains Mono",monospace;letter-spacing:.09em;text-transform:uppercase;
  font-style:normal;color:var(--accent);margin-left:8px}
.pr-tx i{font:400 12px Geist;font-style:normal;color:var(--ink3);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pr-v{font:500 8.5px "JetBrains Mono",monospace;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink3);border:1px solid var(--hair2);border-radius:4px;padding:2.5px 6px;flex:none}
.prow.on .pr-v{color:var(--ink2);border-color:rgba(200,90,62,.4)}
.pr-n{font:500 11px "JetBrains Mono",monospace;color:var(--ink3);flex:none;
  font-variant-numeric:tabular-nums;min-width:36px;text-align:right}
.prow.on .pr-n{color:var(--accent)}

.hotcard .hotrow{display:flex;align-items:center;justify-content:space-between;padding:14px 4px;border-bottom:1px solid var(--bd)}.hotcard .hotrow:last-child{border-bottom:0}
.kbs{display:flex;gap:6px}kbd{font:500 10.5px 'JetBrains Mono';background:rgba(240,240,240,.05);border:1px solid var(--bd2);border-radius:6px;padding:5px 9px;min-width:26px;text-align:center}
.toggle{width:40px;height:22px;border-radius:11px;background:rgba(240,240,240,.12);position:relative;cursor:pointer;border:0}
.toggle.on{background:var(--acc)}.toggle:after{content:'';position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;transition:transform .15s}.toggle.on:after{transform:translateX(18px)}
/* ── snippets ── */
.snactions{display:flex;align-items:center;gap:10px}
.snsearch{display:flex;align-items:center;gap:8px;background:rgba(240,240,240,.05);border:1px solid var(--bd2);border-radius:999px;padding:8px 14px}
.snsearch svg{width:14px;height:14px;color:var(--mut);flex:none}
.snsearch input{background:0;border:0;outline:0;color:var(--tx);font:400 12.5px 'Geist';width:130px}
.snnew{flex:none;padding:9px 16px}.snnew svg{width:13px;height:13px}
.snmeta{font:500 11px 'JetBrains Mono';color:var(--mut);letter-spacing:.04em;margin:-10px 0 18px}
.snbody{position:relative}
.sniptable{width:100%;border-collapse:collapse}
.sniptable thead th{text-align:left;font:600 10px 'JetBrains Mono';letter-spacing:.1em;color:var(--sub);padding:0 12px 10px;border-bottom:1px solid var(--bd);white-space:nowrap}
.sniptable th.th-trig{color:var(--acc);cursor:pointer}
.sniptable th.th-used{text-align:right}
.sniptable .scaret{opacity:.7;font-size:9px}
.sniprow{cursor:pointer;border-bottom:1px solid var(--bd)}
.sniprow:hover{background:rgba(240,240,240,.04)}
.sniprow.active{background:var(--acc-soft)}
.sniprow td{padding:12px;font:400 12.5px 'Geist';color:var(--tx);vertical-align:middle}
.sniprow .td-trig{font:500 12.5px 'JetBrains Mono';color:var(--acc);white-space:nowrap}
.sniprow .td-exp{color:var(--mut);max-width:320px}
.sniprow .td-label{color:var(--sub)}
.sniprow .td-used{text-align:right;font:500 12px 'JetBrains Mono';color:var(--mut);width:60px}
.sniprow.active .td-used{color:var(--acc)}
.sniprow .td-menu{width:40px;text-align:right;position:relative}
.sndots{background:0;border:0;color:var(--mut);cursor:pointer;font-size:16px;line-height:1;padding:2px 6px;border-radius:6px}
.sndots:hover{color:var(--tx);background:rgba(240,240,240,.06)}
.snmenu{position:absolute;top:32px;right:8px;z-index:10;background:var(--card);border:1px solid var(--bd2);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.4);padding:5px;min-width:120px;display:flex;flex-direction:column}
.snmenu button{background:0;border:0;text-align:left;color:var(--tx);cursor:pointer;font:500 12px 'Geist';padding:8px 12px;border-radius:6px}
.snmenu button:hover{background:rgba(240,240,240,.06)}
.snmenu button.del{color:#e5665a}
/* slide-in edit pane (no scrim) */
.snpane{position:fixed;top:0;right:0;height:100vh;width:390px;max-width:82vw;background:var(--chrome);border-left:1px solid var(--bd2);box-shadow:-24px 0 50px rgba(0,0,0,.35);padding:22px;display:flex;flex-direction:column;gap:16px;animation:snslide .18s ease-out;z-index:40;overflow-y:auto}
@keyframes snslide{from{transform:translateX(24px);opacity:.3}to{transform:translateX(0);opacity:1}}
.snpanehead{display:flex;align-items:center;justify-content:space-between}
.snpanehead h3{font:600 15px 'Geist'}
.snx{background:0;border:0;color:var(--mut);cursor:pointer;font-size:15px;padding:4px 8px;border-radius:6px}.snx:hover{color:var(--tx);background:rgba(240,240,240,.06)}
.snfield label{display:block;font:600 10px 'JetBrains Mono';color:var(--mut);letter-spacing:.08em;margin-bottom:7px}
.snfield input,.snfield textarea{width:100%;background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:8px;padding:10px 12px;color:var(--tx);font:400 12.5px 'Geist';outline:0}
.snfield input.sntrig{font:500 13px 'JetBrains Mono';border:0;border-bottom:1.5px solid var(--acc-bd);border-radius:0;background:0;padding:8px 2px}
.snfield input.sntrig:focus{border-bottom-color:var(--acc)}
.snfield textarea{min-height:120px;resize:vertical;font:400 12.5px/1.5 'Geist'}
.snfield input:focus,.snfield textarea:focus{border-color:var(--acc-bd)}
.snhelp{display:flex;align-items:center;justify-content:space-between;margin-top:7px;font:400 10.5px 'Geist';color:var(--sub)}
.sncount{font:500 10px 'JetBrains Mono';color:var(--sub);letter-spacing:.04em}
.snpanefoot{display:flex;align-items:center;gap:8px;margin-top:auto;padding-top:8px}
.sndel{background:0;border:0;color:#e5665a;cursor:pointer;font:600 12.5px 'Geist';padding:8px 4px}.sndel:hover{text-decoration:underline}
.snpanefoot .grow{flex:1}
/* empty state */
.snempty{padding:20px 0;max-width:560px}
.sneyebrow{font:600 11px 'JetBrains Mono';letter-spacing:.18em;color:var(--acc);margin-bottom:16px}
.snbig{font:600 26px/1.3 'Geist';letter-spacing:-.01em;margin-bottom:26px}
.snbig .snq{color:var(--acc);font-family:'JetBrains Mono'}
.snchips{display:flex;flex-wrap:wrap;gap:8px;margin-top:34px}
.snchips span{font:500 11.5px 'Geist';color:var(--mut);background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:999px;padding:7px 14px}
/* ── notes v2: search, checklists, segment playback, original view ── */
.notecount{font:500 10px 'JetBrains Mono';color:var(--sub);letter-spacing:.06em;margin:-12px 0 14px;min-height:12px}
.ncaudio{color:var(--acc)}.ncaudio svg{width:11px;height:11px;vertical-align:-1px}
.notebody ul.chk li{list-style:none;display:flex;align-items:flex-start;gap:6px}
.chkbox{flex:none;cursor:pointer;color:var(--mut);user-select:none;line-height:1.55}
.chkbox.on{color:var(--acc)}
.chkbox:focus{outline:2px solid var(--acc-bd);outline-offset:2px;border-radius:4px}
.chktext{flex:1;min-width:0}
.noteorig{flex:1;overflow-y:auto;white-space:pre-wrap;color:rgba(240,240,240,.72);font:400 14px/1.7 'Geist';border:1px solid var(--bd);border-radius:12px;padding:14px;background:rgba(240,240,240,.03);min-height:200px}
.segbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.segbtn{display:inline-flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--bd2);color:var(--tx);border-radius:999px;padding:7px 14px 7px 12px;cursor:pointer;font:500 12px 'Geist'}
.segbtn:hover{border-color:var(--acc-bd);color:var(--acc)}
.segbtn svg{width:14px;height:14px}
.fmtbtn.ftxt{width:auto;padding:0 10px;font:600 11.5px 'Geist'}
.fmtbtn.retry{color:var(--acc);border-color:var(--acc-bd)}
.fmtbtn.pinned{color:var(--acc);border-color:var(--acc-bd)}
.nflags .saverow{margin:0 0 12px}.nflags .saverow:last-child{margin-bottom:0}
/* ── notes v3: pins, grouped list, overflow menu, ask, styles ── */
.ngroup{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--sub);text-transform:uppercase;margin:16px 2px 8px}
.ngroup:first-child{margin-top:2px}
.ncard{position:relative}
.ncard .nctitle{padding-right:24px}
.npin{position:absolute;top:8px;right:8px;width:26px;height:26px;border-radius:8px;border:0;background:none;color:var(--sub);cursor:pointer;display:none;align-items:center;justify-content:center;font-size:13px;line-height:1}
.ncard:hover .npin{display:flex}
.npin:hover{color:var(--acc);background:rgba(240,240,240,.07)}
.npin.on{display:flex;color:var(--acc)}
.ncmeta{display:flex;align-items:center;gap:10px}
.ncprog{color:var(--acc);letter-spacing:.04em}
.ncprog.alldone{color:var(--on)}
mark.hl{background:rgba(200,90,62,.32);color:inherit;border-radius:3px;padding:0 1px}
.notemeta{font:500 10px 'JetBrains Mono';color:var(--sub);letter-spacing:.07em;margin:-6px 0 14px;min-height:12px}
.nmenuwrap{position:relative;display:inline-flex}
.nmenu{position:absolute;top:36px;right:0;z-index:30;min-width:200px;background:#1b1e22;border:1px solid var(--bd2);border-radius:12px;padding:6px;box-shadow:0 14px 36px rgba(0,0,0,.55)}
.nmenu[hidden]{display:none}
.nmenu button{display:flex;width:100%;align-items:center;gap:9px;padding:8px 10px;border:0;background:none;color:var(--tx);font:500 12px 'Geist';border-radius:8px;cursor:pointer;text-align:left}
.nmenu button:hover{background:rgba(240,240,240,.06)}
.nmenu button.danger{color:#f0b39a}
.nmenu button svg{width:13px;height:13px;flex:none;opacity:.7}
.nmenu .nmsep{height:1px;background:var(--bd);margin:5px 4px}
.nmenu .nmhead{font:500 9px 'JetBrains Mono';letter-spacing:.14em;color:var(--sub);text-transform:uppercase;padding:6px 10px 4px}
.notebody ul.chk li.done .chktext{color:var(--sub);text-decoration:line-through}
.nempty{display:flex;flex-direction:column;align-items:center;gap:10px;padding:40px 12px;text-align:center}
.nempty .disc{width:46px;height:46px;border-radius:50%;background:var(--acc-soft);color:var(--acc);display:flex;align-items:center;justify-content:center}
.nempty .disc svg{width:20px;height:20px}
.nempty .t{font:600 14px 'Geist'}
.nempty .s{font:400 12px/1.6 'Geist';color:var(--mut);max-width:270px}
.noteorig[contenteditable]{cursor:text}
.noteorig:focus{border-color:var(--acc-bd);outline:0}
.askNote{border:1px solid var(--acc-bd);background:var(--acc-softer);border-radius:12px;padding:12px 14px;margin:0 0 14px;position:relative}
.askNote .aq{font:600 11px 'JetBrains Mono';letter-spacing:.06em;color:var(--acc-txt);margin-bottom:6px;padding-right:20px}
.askNote .aa{font:400 12.5px/1.65 'Geist';color:var(--tx);white-space:pre-wrap}
.askNote .asrc{font:500 9.5px 'JetBrains Mono';letter-spacing:.08em;color:var(--sub);margin-top:8px}
.askNote .ax{position:absolute;top:8px;right:8px;width:22px;height:22px;border:0;background:none;color:var(--sub);cursor:pointer;font-size:13px;border-radius:6px}
.askNote .ax:hover{color:var(--tx);background:rgba(240,240,240,.07)}
/* ── Meetings (31a launcher card · 31f folder tabs) ── */
.mcard{display:flex;align-items:center;gap:14px;margin:18px 0 6px;padding:16px 18px;border-radius:12px;
  background:linear-gradient(160deg,#17191c,#1c1e22);border:1px solid var(--bd)}
.mctitle{font:600 13.5px 'Geist';color:var(--tx);display:flex;align-items:center;gap:8px}
.mcsub{font:400 12px/1.5 'Geist';color:var(--mut);margin-top:4px;max-width:520px}
.mcsub.mono{font-family:'JetBrains Mono',monospace;font-size:10.5px}
.mnew{font:600 9px 'JetBrains Mono';letter-spacing:.12em;color:var(--acc);
  background:var(--acc-soft);border-radius:6px;padding:2px 6px}
.mrec{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;flex:none;
  background:rgba(224,80,73,.14);border:1px solid rgba(224,80,73,.38);
  font:500 10px 'JetBrains Mono';letter-spacing:.14em;color:#f0a5a0}
.mdot{width:6px;height:6px;border-radius:50%;background:#E05049;animation:mcpulse 1.4s ease-in-out infinite}
@keyframes mcpulse{0%,100%{opacity:1}50%{opacity:.25}}
.mrecdot{display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;margin-right:6px}
/* Meetings page — MeetingCard v2 (33j): rows inside ONE parent card per group */
.meetlist{background:var(--card);border:1px solid var(--bd);border-radius:12px;
  padding:2px 16px;margin:6px 0 16px}
.meetrow{position:relative;display:block;padding:12px 0;cursor:pointer;
  border-top:1px solid rgba(240,240,240,.04)}
.meetrow:first-of-type{border-top:0}
.meetrowTop{display:flex;align-items:baseline;gap:9px;min-width:0}
.meetrowTitle{font:600 13.5px 'Geist';letter-spacing:-.01em;color:var(--tx);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.mrMeta{margin-left:auto;flex:none;font:500 10.5px 'JetBrains Mono';color:var(--mut);
  letter-spacing:.05em;font-variant-numeric:tabular-nums}
.mrPrev{font:400 12px 'Geist';color:var(--tx2);margin-top:3px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;max-width:60ch}
.mrFoot{display:flex;align-items:center;gap:16px;margin-top:7px;min-height:16px}
.mrChip{display:inline-flex;align-items:center;gap:6px;font:600 11px 'Geist';color:var(--tx2)}
.mrChip i{width:6px;height:6px;border-radius:50%;flex:none}
.mrMore{font:400 11px 'Geist';color:var(--dim)}
.mrAttrs{margin-left:auto;display:flex;gap:12px;font:500 10.5px 'JetBrains Mono';color:var(--mut)}
.mrAttrs .st{color:#D9B36B}
.mrActs{position:absolute;top:10px;right:0;display:flex;gap:2px;opacity:0;
  transition:opacity .12s ease;background:var(--card)}
.meetrow:hover .mrActs,.meetrow:focus-within .mrActs{opacity:1}
.mrActs button{width:26px;height:24px;display:inline-flex;align-items:center;justify-content:center;
  background:none;border:0;color:var(--dim);cursor:pointer;border-radius:6px;font:500 12px 'Geist'}
.mrActs button:hover{color:var(--tx)}
.mrActs button.del:hover{color:#e08a80}
.mrActs svg{width:12px;height:12px}
.newbar{position:absolute;left:-16px;top:16px;width:3px;height:12px;border-radius:2px;background:var(--acc)}
.newTag{font:500 9px 'JetBrains Mono';letter-spacing:.12em;color:#e5a18d;flex:none}
.pinG{font-size:10px;color:#D9B36B;flex:none;margin-right:2px}
.meetEmpty{display:flex;flex-direction:column;align-items:center;gap:10px;padding:56px 24px;
  text-align:center}
.meetEmptyDisc{width:56px;height:56px;border-radius:50%;background:var(--acc-soft);
  color:var(--acc);display:flex;align-items:center;justify-content:center}
.meetEmptyDisc svg{width:24px;height:24px}
.meetEmptyTitle{font:600 15px 'Geist';color:var(--tx)}
.meetEmptyBody{font:400 12px/1.6 'Geist';color:var(--mut);max-width:360px}
.mbadge{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:999px;
  font:500 9.5px 'JetBrains Mono';letter-spacing:.1em}
.mbadge i{width:5px;height:5px;border-radius:50%}
.mbadge.ready{background:rgba(74,209,90,.10);color:#8ee69a}.mbadge.ready i{background:#4ad15a}
.mbadge.denied{background:rgba(224,80,73,.14);color:#f0a5a0}.mbadge.denied i{background:#E05049}
.mbadge.pending{background:rgba(209,160,74,.12);color:#e6c890}.mbadge.pending i{background:#d1a04a}
/* Ask-your-meetings chat */
.askCard{background:linear-gradient(160deg,#17191c,#1c1e22);border:1px solid var(--bd);
  border-radius:12px;padding:14px 16px;margin:0 0 14px}
.askHead{font:500 10px 'JetBrains Mono';letter-spacing:.14em;color:var(--acc);
  text-transform:uppercase;margin-bottom:10px}
.askRow{display:flex;gap:8px}
.askRow input{flex:1;background:rgba(240,240,240,.05);border:1px solid var(--bd2);
  border-radius:10px;padding:9px 13px;font:400 12.5px 'Geist';color:var(--tx);outline:none}
.askRow input:focus{border-color:var(--acc-bd)}
.askRow input::placeholder{color:var(--sub)}
.askThread{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.askQ{align-self:flex-end;max-width:78%;background:var(--acc-soft);border-radius:12px 12px 4px 12px;
  padding:8px 12px;font:500 12px 'Geist';color:var(--tx)}
.askA{align-self:flex-start;max-width:88%;background:rgba(240,240,240,.05);
  border:1px solid var(--bd);border-radius:12px 12px 12px 4px;padding:10px 13px;
  font:400 12.5px/1.6 'Geist';color:var(--tx);white-space:pre-wrap}
.askA.err{color:#f0a5a0;border-color:rgba(224,80,73,.3)}
.askSrc{font:500 10px 'JetBrains Mono';color:var(--sub);margin-top:6px}
.askThink{display:inline-flex;gap:4px;padding:10px 13px}
.askThink i{width:5px;height:5px;border-radius:50%;background:var(--mut);
  animation:askdots 1.1s ease-in-out infinite}
.askThink i:nth-child(2){animation-delay:.15s}.askThink i:nth-child(3){animation-delay:.3s}
@keyframes askdots{0%,100%{opacity:.25;transform:translateY(0)}50%{opacity:1;transform:translateY(-3px)}}
/* ── toast (IDI-167) — the only failure surface for actions that have no
   inline status slot of their own (stop meeting, toggles, deletes) ── */
.toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,14px);z-index:80;
  background:var(--card);border:1px solid var(--bd2);border-radius:10px;padding:11px 16px;
  font:500 12.5px 'Geist';color:var(--tx);box-shadow:0 12px 34px rgba(0,0,0,.45);
  opacity:0;pointer-events:none;transition:opacity .16s ease,transform .16s ease;max-width:70vw}
.toast.on{opacity:1;transform:translate(-50%,0)}
.toast.err{border-color:rgba(224,80,73,.4);color:#f0a5a0}
/* ── meeting detail (31e), ported from the meeting panel (MER-46) ──────────────
   The panel is live-meeting-only now; reading a meeting happens here, inside the
   Meetings screen. Every rule is scoped to #mtgDetail because the panel's design
   vocabulary (.card/.eyebrow/.legend/.mono) overlaps the dashboard's own.
   Companion classes the ported markup leans on, from meeting_html.py's shared
   region: */
#mtgDetail .mono,#mtgNotes .mono{font-family:'JetBrains Mono',monospace}
#mtgDetail .eyebrow,#mtgNotes .eyebrow{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;
  text-transform:uppercase;color:var(--faint);margin:0}
#mtgDetail .eyebrow.accd,#mtgNotes .eyebrow.accd{color:var(--acc)}
#mtgDetail .btnS,#mtgNotes .btnS{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;
  border-radius:10px;background:transparent;border:1px solid var(--bd2);color:var(--tx);
  font:600 12px 'Geist';cursor:pointer}
#mtgDetail .btnS:hover,#mtgNotes .btnS:hover{background:var(--raised)}
#mtgDetail .btnS.mini,#mtgNotes .btnS.mini{padding:6px 10px;font:600 10.5px 'JetBrains Mono';
  letter-spacing:.08em}
#mtgDetail .iconbtn,#mtgNotes .iconbtn{width:28px;height:28px;border-radius:7px;background:none;
  color:var(--mut);display:inline-flex;align-items:center;justify-content:center;flex:none;
  border:0;cursor:pointer;transition:color .14s ease}
#mtgDetail .iconbtn:hover,#mtgNotes .iconbtn:hover{color:var(--tx)}
#mtgDetail .schip{display:inline-flex;align-items:center;gap:6px;font:600 11px 'Geist';
  color:var(--tx);flex:none}
#mtgDetail .schip::before{content:'';width:6px;height:6px;border-radius:50%;
  background:var(--faint);flex:none}
#mtgDetail .schip.c0::before{background:var(--sp-terra)}
#mtgDetail .schip.c1::before{background:var(--sp-slate)}
#mtgDetail .schip.c2::before{background:var(--sp-sage)}
#mtgDetail .schip.c3::before,#mtgDetail .schip.self::before{background:var(--sp-ochre)}
#mtgDetail .schip.unknown{color:var(--tx2)}
#mtgDetail .schip.unknown::before{background:var(--faint)}
#mtgDetail .mact{display:flex;gap:7px;align-items:center;flex:none}
#mtgNotes .ntTitle{font:600 15px 'Geist';letter-spacing:-.01em;color:var(--tx);flex:1;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ── PostMeetingSummary (31e) ── */
/* The WHOLE page scrolls (header sticky) — inner-only scroll made small
   windows unusable; expanded sections grow naturally into the page. */
#mtgDetail{display:none;flex-direction:column;height:100vh;padding:0 28px 24px;gap:12px;
  overflow-y:auto}
#mtgDetail.show{display:flex}
#mtgDetail .sumHead{display:flex;align-items:flex-start;gap:10px;flex:none;position:sticky;top:0;z-index:6;
  background:var(--bg);padding:18px 0 10px;border-bottom:1px solid var(--bd)}
#mtgDetail .sumHeadL{flex:1;min-width:0}
#mtgDetail .sumTitle{font:600 22px 'Geist';letter-spacing:-.02em;color:var(--tx);background:none;
  border:0;outline:none;width:100%}
#mtgDetail .sumMeta{display:flex;align-items:center;gap:8px;margin-top:5px;flex-wrap:wrap}
#mtgDetail .sumMeta .mono{font:500 10.5px 'JetBrains Mono';color:var(--dim)}
#mtgDetail .card{background:var(--raised);border:1px solid var(--bd);border-radius:12px;
  padding:12px 16px}
#mtgDetail .sumCards{flex:none;display:flex;flex-direction:column;gap:10px}
#mtgDetail .sumBody{font:400 12.5px/1.6 'Geist';color:var(--tx);margin-top:6px}
#mtgDetail .sumErr{font:400 12px 'Geist';color:var(--rec-soft);margin-top:6px}
#mtgDetail .twoCol{display:flex;gap:10px;align-items:stretch}
#mtgDetail .twoCol .colL{flex:1.4;min-width:0}
#mtgDetail .twoCol .colR{flex:1;display:flex;flex-direction:column;gap:8px;min-width:0}
#mtgDetail .legend{display:flex;gap:14px;margin-left:auto}
#mtgDetail .legend span{display:inline-flex;align-items:center;gap:6px;font:400 10.5px 'Geist';color:var(--dim)}
#mtgDetail .legend i{width:6px;height:6px;border-radius:50%}
#mtgDetail .legend .lu i{background:var(--sp-terra)}
#mtgDetail .legend .la i{background:var(--faint)}
#mtgDetail .cardHead{display:flex;align-items:center;gap:8px}
/* HybridNotesRenderer v2 (33i): dot rows, AI as an indented ↳ line, underline tabs */
#mtgDetail .hnTabs{display:flex;gap:12px;margin-left:12px}
#mtgDetail .hnTab{font:500 11px 'Geist';color:var(--dim);padding:0 1px 3px;border-bottom:1.5px solid transparent;
  transition:color .14s ease}
#mtgDetail .hnTab:hover{color:var(--tx2)}
#mtgDetail .hnTab.on{color:var(--tx);border-bottom-color:var(--acc)}
#mtgDetail .hnRow{position:relative;border-left:0;padding:0 40px 0 14px;margin-top:11px}
#mtgDetail .hnRegen{position:absolute;right:8px;top:1px;width:24px;height:22px;display:inline-flex;
  align-items:center;justify-content:center;color:var(--faint);opacity:0;transition:opacity .12s;
  border-radius:5px}
#mtgDetail .hnRow:hover .hnRegen{opacity:1}
#mtgDetail .hnRegen:hover{color:var(--acc-txt)}
#mtgDetail .hnRegen.busy{opacity:1;color:var(--acc);animation:mtgSpin 1s linear infinite}
@keyframes mtgSpin{to{transform:rotate(360deg)}}
#mtgDetail .hnRow::before{content:'';position:absolute;left:0;top:6px;width:6px;height:6px;border-radius:50%;
  background:var(--sp-terra)}
#mtgDetail .hnRow.noDot::before{display:none}
#mtgDetail .hnUser{font:400 12.5px/1.55 'Geist';color:var(--tx)}
#mtgDetail .hnAI{font:400 11.5px/1.55 'Geist';font-style:normal;color:var(--dim);margin-top:2px}
#mtgDetail .hnAI::before{content:'\\21B3  ';color:var(--faint)}
#mtgDetail #hnList.v-yours .hnAI{display:none}
#mtgDetail #hnList.v-ai .hnUser{opacity:.5}
#mtgDetail #hnList.v-ai .hnAI{color:var(--tx)}
#mtgDetail .dList{margin-top:8px;display:flex;flex-direction:column;gap:6px}
#mtgDetail .dItem{display:flex;gap:8px;font:400 12px/1.5 'Geist';color:var(--tx)}
#mtgDetail .dItem::before{content:'\\2014';color:var(--faint)}
/* ActionItemRow v2 (33c): rows inside ONE card, faint dividers, real checkbox */
#mtgDetail .aiRow{display:flex;align-items:center;gap:10px;padding:9px 0;margin-top:0;
  font:400 12.5px 'Geist';color:var(--tx);border-top:1px solid var(--bd-faint)}
#mtgDetail .aiRow:first-of-type{border-top:0}
#mtgDetail .aiRow.done{opacity:.55}
#mtgDetail .aiRow.done .aiTask{text-decoration:line-through;color:var(--dim)}
#mtgDetail .aiTask{flex:1;min-width:0}
#mtgDetail .aiCb{width:15px;height:15px;border-radius:4px;border:1.4px solid var(--dim);background:none;flex:none;
  display:inline-flex;align-items:center;justify-content:center;color:transparent;padding:0;
  transition:all .15s ease}
#mtgDetail .aiCb:hover{border-color:var(--tx2)}
#mtgDetail .aiRow.done .aiCb{background:var(--ok);border-color:var(--ok);color:#0a1f0d}
/* MarkedMomentCard v2 (33b): rows in the parent card, star + mono ts header */
#mtgDetail .mmRow{padding:11px 0;border-top:1px solid var(--bd-faint)}
#mtgDetail .mmRow:first-of-type{border-top:0}
#mtgDetail .mmHead{display:flex;align-items:center;gap:8px}
#mtgDetail .mmHead .star{color:var(--acc);display:inline-flex}
#mtgDetail .mmTs{font:500 11px 'JetBrains Mono';color:var(--acc-txt);letter-spacing:.06em;
  font-variant-numeric:tabular-nums;cursor:pointer}
#mtgDetail .mmTs:hover{text-decoration:underline}
#mtgDetail .mmEx{font:400 12.5px/1.6 'Geist';color:var(--tx);margin-top:5px}
#mtgDetail .mmEx b{color:var(--dim);font-weight:400}
#mtgDetail .mmRow{position:relative;padding-right:70px}
#mtgDetail .mmActs{position:absolute;top:9px;right:0;display:flex;gap:2px;opacity:0;transition:opacity .12s}
#mtgDetail .mmRow:hover .mmActs,#mtgDetail .mmRow:focus-within .mmActs{opacity:1}
#mtgDetail .mmNote{margin-top:9px;padding-top:9px;border-top:1px solid var(--bd-faint)}
#mtgDetail .mmNote .k{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--sp-ochre);
  text-transform:uppercase;margin-bottom:3px}
#mtgDetail .mmNote p{font:400 12px/1.55 'Geist';color:var(--tx);margin:0;cursor:text;border-radius:5px}
#mtgDetail .mmNote p:hover{background:var(--subtle-alt)}
#mtgDetail .mmNoteAdd{font:400 11px 'Geist';color:var(--faint);cursor:pointer;margin-top:7px;
  display:inline-block;opacity:0;transition:opacity .12s}
#mtgDetail .mmRow:hover .mmNoteAdd{opacity:1}
#mtgDetail .mmNoteAdd:hover{color:var(--acc-txt)}
#mtgDetail .mmNoteIn{width:100%;font:400 12px/1.55 'Geist';color:var(--tx);background:var(--raised);
  border:1px solid var(--acc-bd);border-radius:8px;padding:6px 9px;margin-top:6px;resize:vertical;
  min-height:38px;caret-color:var(--acc)}
/* summary header avatars (33d) */
#mtgDetail .avchip{display:inline-flex;align-items:center;gap:7px;font:600 11px 'Geist';color:var(--tx)}
#mtgDetail .av{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;
  justify-content:center;font:600 9.5px 'Geist';flex:none}
#mtgDetail .av.c0{background:rgba(217,138,114,.16);color:var(--sp-terra)}
#mtgDetail .av.c1{background:rgba(143,167,194,.16);color:var(--sp-slate)}
#mtgDetail .av.c2{background:rgba(169,189,152,.16);color:var(--sp-sage)}
#mtgDetail .av.c3,#mtgDetail .av.self{background:rgba(217,179,107,.16);color:var(--sp-ochre)}
#mtgDetail .av.self{box-shadow:0 0 0 1px var(--bg), 0 0 0 2.5px var(--sp-ochre)}
#mtgDetail .av.unknown{background:none;border:1px dashed var(--faint);color:var(--dim)}
#mtgDetail .avchip{position:relative}
#mtgDetail .avFp{position:absolute;left:14px;top:14px;width:9px;height:9px;border-radius:50%;
  background:var(--acc);border:2px solid var(--bg)}
#mtgDetail .fpBanner{display:flex;align-items:center;gap:9px;margin-top:8px;font:400 11.5px 'Geist';
  color:var(--tx2)}
#mtgDetail .fpBanner b{color:var(--tx);font-weight:600}
#mtgDetail .fpBanner .zap{color:var(--acc);display:inline-flex}
#mtgDetail .fpBanner .k{margin-left:auto;font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;
  color:var(--faint)}
/* transcript row action rail + inline edit (33a) */
#mtgDetail .exUtt{position:relative;padding-right:64px}
#mtgDetail .exUtt .xr{position:absolute;top:1px;right:2px;display:flex;gap:0;opacity:0;transition:opacity .12s}
#mtgDetail .exUtt:hover .xr,#mtgDetail .exUtt:focus-within .xr{opacity:1}
#mtgDetail .xr .iconbtn{width:24px;height:22px}
#mtgDetail .edTag{font:500 9px 'JetBrains Mono';letter-spacing:.08em;color:var(--faint);margin-left:6px}
#mtgDetail .txEditIn{width:100%;font:400 11.5px/1.55 'Geist';color:var(--tx);background:var(--raised);
  border:1px solid var(--acc-bd);border-radius:8px;padding:6px 9px;margin-top:4px;resize:vertical;
  min-height:44px;caret-color:var(--acc)}
/* action item edit/delete (33c) */
#mtgDetail .aiRow{padding-right:24px;position:relative}
#mtgDetail .aiDel{position:absolute;right:0;top:50%;transform:translateY(-50%);width:20px;height:20px;
  display:inline-flex;align-items:center;justify-content:center;color:var(--faint);opacity:0;
  transition:opacity .12s;border-radius:5px;font:500 12px 'Geist'}
#mtgDetail .aiRow:hover .aiDel,#mtgDetail .aiRow:focus-within .aiDel{opacity:1}
#mtgDetail .aiDel:hover{color:var(--rec-soft)}
#mtgDetail .aiTask{cursor:text;border-radius:5px}
#mtgDetail .aiTask:hover{background:var(--subtle-alt)}
#mtgDetail .aiEditIn{flex:1;min-width:0;font:400 12.5px 'Geist';color:var(--tx);background:var(--raised);
  border:1px solid var(--acc-bd);border-radius:6px;padding:4px 8px;caret-color:var(--acc)}
#mtgDetail .aiDue{font:500 9.5px 'JetBrains Mono';letter-spacing:.05em;color:var(--faint);flex:none}
#mtgDetail .aiDue.near{color:var(--acc-txt)}
#mtgDetail .teasers{display:flex;gap:8px;flex:none}
#mtgDetail .teaser{flex:1;display:flex;align-items:center;gap:8px;background:var(--raised);
  border:1px solid var(--bd);border-radius:10px;padding:9px 12px;cursor:pointer}
#mtgDetail .teaser .tl{font:400 11px 'Geist';color:var(--tx);flex:1}
#mtgDetail .teaser .eyebrow{margin-left:auto}
#mtgDetail .expandBox{display:none;flex-direction:column;gap:8px}
/* grows into the page scroll */
#mtgDetail .expandBox.show{display:flex}
#mtgDetail .skel{height:11px;border-radius:6px;background:var(--raised2);margin-top:8px;
  animation:mtgShimmer 1.6s ease-in-out infinite}
@keyframes mtgShimmer{0%,100%{opacity:.5}50%{opacity:1}}
#mtgDetail .exUtt{cursor:pointer;border-radius:8px;padding:4px 8px}
#mtgDetail .exUtt:hover{background:var(--raised)}
#mtgDetail .exUtt.playing{background:var(--acc-soft)}
/* ── Meeting Notes page (full-page view, MODE 'notes') ── */
#mtgNotes{display:none;flex-direction:column;height:100vh;overflow-y:auto;padding:0 28px 40px}
#mtgNotes.show{display:flex}
#mtgDetail .ntHead{display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:6;
  background:var(--bg);padding:16px 0 10px;border-bottom:1px solid var(--bd);flex:none}
#mtgDetail .ntBack{display:inline-flex;align-items:center;gap:6px;background:none;border:0;
  color:var(--tx2);font:600 12px 'Geist';cursor:pointer;padding:4px 8px;border-radius:8px}
#mtgDetail .ntBack:hover{color:var(--tx);background:var(--raised)}
#mtgDetail .ntTitle{font:600 15px 'Geist';letter-spacing:-.01em;color:var(--tx);flex:1;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#mtgDetail .ntBody{max-width:720px;width:100%;margin:18px auto 0;font:400 13.5px/1.75 'Geist';color:var(--tx)}
#mtgDetail .ntBody p{margin:0 0 14px}
#mtgDetail .ntBody .ctx{font:400 13.5px/1.7 'Geist';color:var(--tx2);border-left:2px solid var(--acc);
  padding:2px 0 2px 14px;margin:0 0 22px}
#mtgDetail .ntBody h2{font:600 11px 'JetBrains Mono';letter-spacing:.16em;text-transform:uppercase;
  color:var(--acc-txt);margin:26px 0 10px;padding-top:16px;border-top:1px solid var(--bd-faint)}
#mtgDetail .ntBody h2:first-child{border-top:0;padding-top:0;margin-top:0}
#mtgDetail .ntBody h3{font:600 13.5px 'Geist';color:var(--tx);margin:16px 0 6px}
#mtgDetail .ntBody ul,#mtgDetail .ntBody ol{margin:0 0 14px;padding-left:20px;display:flex;flex-direction:column;gap:7px}
#mtgDetail .ntBody li{padding-left:2px}
#mtgDetail .ntBody ul li::marker{color:var(--sp-terra)}
#mtgDetail .ntBody ol li::marker{color:var(--dim);font:500 11px 'JetBrains Mono'}
#mtgDetail .ntBody b,#mtgDetail .ntBody strong{font-weight:600;color:var(--tx)}
#mtgDetail .ntBody code{font:500 12px 'JetBrains Mono';background:var(--raised);border-radius:5px;padding:1px 6px}
#mtgDetail .ntTableWrap{overflow-x:auto;margin:6px 0 16px}
#mtgDetail .ntTable{border-collapse:collapse;width:100%;font:400 12.5px 'Geist'}
#mtgDetail .ntTable th{text-align:left;font:600 10px 'JetBrains Mono';letter-spacing:.1em;text-transform:uppercase;
  color:var(--acc-txt);padding:7px 12px 7px 0;border-bottom:1px solid var(--bd2);white-space:nowrap}
#mtgDetail .ntTable td{padding:7px 12px 7px 0;border-bottom:1px solid var(--bd-faint);color:var(--tx);vertical-align:top}
#mtgDetail .ntTable tr:last-child td{border-bottom:0}
#mtgDetail .ntTask{display:flex;align-items:flex-start;gap:9px;margin:0 0 8px}
#mtgDetail .ntTask .box{width:15px;height:15px;border-radius:4px;border:1.4px solid var(--dim);flex:none;
  margin-top:3px;display:inline-flex;align-items:center;justify-content:center;color:transparent}
#mtgDetail .ntTask.done .box{background:var(--ok);border-color:var(--ok);color:#0a1f0d}
#mtgDetail .ntTask.done span{text-decoration:line-through;color:var(--dim)}
#mtgDetail .ntSkel{max-width:720px;width:100%;margin:26px auto 0;display:flex;flex-direction:column;gap:12px}
#mtgDetail .ntSkel i{display:block;height:12px;border-radius:6px;background:var(--raised2);
  animation:mtgShimmer 1.6s ease-in-out infinite}
#mtgDetail .ntErr{max-width:720px;margin:30px auto;color:var(--rec-soft);font:400 13px 'Geist';text-align:center}
/* Host overrides — the detail view sits inside `.main`, which already owns the
   page padding and the scroll container, so it must not be a 100vh panel with a
   sticky header of its own (sticky inside a padded scrollport leaves content
   visible above the header). */
#mtgDetail{height:auto;min-height:0;padding:0;overflow:visible}
#mtgDetail .sumHead{position:static;padding:0 0 12px}
#mtgDetail .sumTitle{font-size:24px}
#mtgNotes{height:auto;padding:0;overflow:visible}
#mtgNotes .ntHead{position:static;padding:0 0 10px}
/* back-to-list affordance above the title */
#mtgDetail .mtgBack,#mtgNotes .mtgBack{display:inline-flex;align-items:center;gap:6px;
  background:none;border:0;color:var(--mut);font:600 12px 'Geist';cursor:pointer;
  padding:4px 8px 4px 0;margin-bottom:2px}
#mtgDetail .mtgBack:hover,#mtgNotes .mtgBack:hover{color:var(--tx)}
"""


def _nav(icon, label, sid, badge=""):
    b = f'<span class="nbadge" id="badge-{sid}">{badge}</span>' if badge != "" else ""
    return (f'<button class="navitem" data-screen="{sid}">'
            f'<span class="nico">{_svg(icon)}</span><span>{label}</span>{b}</button>')


def flume_html() -> str:
    sidebar = f"""
    <aside class="sidebar">
      <div class="brand"><span class="brandmark">✳</span><span class="brandname">FLUME</span></div>
      <div class="navhead">WORKSPACE</div>
      <nav id="wsnav">
        {_nav("home","Home","home")}
        {_nav("clock","History","history")}
        {_nav("grid","Canvas","canvas", badge="")}
        {_nav("lines","Notes","notes")}
        {_nav("meet","Meetings","meetings")}
        {_nav("pulse","Insights","insights")}
        {_nav("book","Dictionary","dictionary")}
        {_nav("bolt","Snippets","snippets")}
      </nav>
      <div class="navhead devhead">DEVICES<button class="devadd" onclick="show('devices')" title="Pair a device">+</button></div>
      <div class="devlist" id="sideDevices"></div>
      <div class="deadside" id="sideDead" hidden>
        <div class="dstx">Session expired — sign in again to sync.</div>
        <button class="dsbtn" onclick="reSignIn()">Sign in</button>
      </div>
      <div class="sfooter">
        <div class="avatar" id="avatarInitial">V</div><span class="uname" id="userName">You</span>
        <button class="ficon push" data-screen="settings" title="Settings">{_svg('gear')}</button>
        <button class="ficon" title="Theme">{_svg('sun')}</button>
      </div>
    </aside>"""

    from app.flume_popover_html import _mark_data_uri
    _mark = _mark_data_uri()
    _logo = f'<img src="{_mark}" alt="Flume"/>' if _mark else "✳"
    _googleg = ('<svg viewBox="0 0 48 48" width="17" height="17"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.6 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.2 13.4 17.6 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.1 5.3-4.6 6.9l7.1 5.5c4.1-3.8 6.5-9.4 6.5-16.9z"/><path fill="#FBBC05" d="M10.4 28.3c-.5-1.4-.7-2.9-.7-4.3s.3-2.9.7-4.3l-7.8-6.1C1 16.8 0 20.3 0 24s1 7.2 2.6 10.4l7.8-6.1z"/><path fill="#34A853" d="M24 48c6.2 0 11.5-2 15.3-5.5l-7.1-5.5c-2 1.4-4.6 2.2-8.2 2.2-6.4 0-11.8-3.9-13.6-9.3l-7.8 6.1C6.5 42.6 14.6 48 24 48z"/></svg>')
    body = f"""
    <div id="signin" hidden>
      <div class="siLeft">
        <div class="siBrand"><span class="siLogo">{_logo}</span><span class="siWord">FLUME</span></div>
        <div class="siHeadline">Speak on your phone.<br>Land on <span class="acc">your Mac.</span></div>
        <p class="siLead">Sign in once — Flume keeps your phone and computer in sync for voice typing, canvas, notes, and meeting transcripts.</p>
        <div class="siFoot">END-TO-END ENCRYPTED&nbsp;&nbsp;&middot;&nbsp;&nbsp;MAC + WINDOWS</div>
      </div>
      <div class="siRight">
        <h1 class="siTitle">Sign in</h1>
        <p class="siSub">Continue with Google — we'll match you across your devices.</p>
        <button class="siGoogle" id="siGoogleBtn" onclick="signInGoogle()">{_googleg}<span id="siGoogleLbl">Continue with Google</span></button>
        <div class="siErr" id="siErr" hidden><span class="ebang">!</span><span id="siErrTx"></span></div>
        <div class="siNote" id="siNote" hidden><span class="ntick">&#10003;</span><span id="siNoteTx"></span></div>
        <button class="siCancel" id="siCancelBtn" hidden onclick="cancelSignIn()">Cancel and try again</button>
        <p class="siTerms">By continuing you agree to our Terms and Privacy.</p>
      </div>
    </div>
    <div id="getstarted" hidden><div class="gsInner" id="gsInner"></div></div>
    <div class="app" id="appRoot">
      {sidebar}
      <section class="screen" id="scr-home"><div class="main" id="homeMain"></div></section>
      <section class="screen" id="scr-history" hidden><div class="threepane" id="historyMain"></div></section>
      <section class="screen" id="scr-canvas" hidden><div class="main" id="canvasMain"></div></section>
      <section class="screen" id="scr-notes" hidden><div class="threepane" id="notesMain"></div></section>
      <section class="screen" id="scr-meetings" hidden><div class="main" id="meetingsMain"></div></section>
      <section class="screen" id="scr-insights" hidden><div class="main" id="insightsMain"></div></section>
      <section class="screen" id="scr-dictionary" hidden><div class="main" id="dictionaryMain"></div></section>
      <section class="screen" id="scr-snippets" hidden><div class="main" id="snippetsMain"></div></section>
      <section class="screen" id="scr-devices" hidden><div class="main" id="devicesMain"></div></section>
      <section class="screen" id="scr-settings" hidden><div class="main" id="settingsMain"></div></section>
    </div>"""

    js = r"""
<script>
function api(name){ const a=[].slice.call(arguments,1);
  return (window.pywebview && window.pywebview.api && window.pywebview.api[name]) ? window.pywebview.api[name].apply(null,a) : Promise.resolve({ok:false}); }
let STATE=null, NOTES=[], CANVAS={content:'',image_url:null}, ACTIVE='home', SELH=0, SELN=null, EDITH=false;
let PAIR={active:false, starting:false, error:null, token:null, svg:'', ttl:0, claimedBy:null, pollTimer:null, tickTimer:null};
let DICT={vocabulary:[],replacements:[]}, DICT_LOADED=false;
let SNIPS=[], SNIPS_LOADED=false, SNIP_EDIT=null, SNIP_SEARCH='', SNIP_MENU=null, SNIP_SORT=1;
let FT={enabled:false,seen_count:0}, FT_LOADED=false;
let AL={enabled:false}, AL_LOADED=false;
let MEETS={meetings:[],active_id:null}, MEETS_LOADED=false, MSET=null, MSET_LOADED=false;
let MEET_QUERY='';   // Meetings page search filter (31f)
let retryErr='', retryBusy=false;
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const keyText = v => Array.isArray(v) ? v.join('\n') : (v==null?'':String(v));
const words = s => (s||'').trim()? (s||'').trim().split(/\s+/).length : 0;
function tagCls(app){ const a=(app||'').toLowerCase(); if(a.includes('pad')||a.includes('pc')||a.includes('win'))return 'ipad'; if(a.includes('local')||!app)return 'local'; return 'iphone'; }
function titleOf(t){ const w=(t||'').trim().split(/\s+/).slice(0,5).join(' '); return w||'Untitled'; }

// ── IDI-167: ONE in-flight guard for every mutating action ───────────────────
// `target` is either the DOM element that triggered the action (pass `this`
// from the inline handler) or a stable string key — use the key form when the
// handler re-renders its own button away, which would otherwise strand the
// flag on a detached node. `run` is a THUNK, not a promise: the whole point is
// that a second click while the first is in flight never calls the api at all,
// so the call must be created inside the guard. Always resolves (never
// rejects) so callers can keep using plain .then chains.
const BUSY = new Set();
function busyGuard(target, run){
  const key = (typeof target === 'string') ? target : null;
  const el  = key ? null : target;
  if(key ? BUSY.has(key) : (el && el.__busy)) return Promise.resolve({ok:false, busy:true});
  if(key) BUSY.add(key);
  else if(el){ el.__busy=true; try{ el.disabled=true; }catch(e){} el.style.opacity='.55'; }
  const done = ()=>{
    if(key) BUSY.delete(key);
    else if(el){ el.__busy=false; try{ el.disabled=false; }catch(e){} el.style.opacity=''; }
  };
  let p;
  try { p = run(); }
  catch(e){ done(); return Promise.resolve({ok:false, error:String(e)}); }
  if(!p || typeof p.then !== 'function'){ done(); return Promise.resolve(p); }
  return p.then(r=>{ done(); return r; }, e=>{ done(); return {ok:false, error:String(e)}; });
}

function show(id){
  ACTIVE=id;
  document.querySelectorAll('.screen').forEach(s=>s.hidden=(s.id!=='scr-'+id));
  document.querySelectorAll('#wsnav .navitem').forEach(b=>b.classList.toggle('active',b.dataset.screen===id));
  renderActive();
  // Meetings finish in a separate window — refresh the list whenever the user
  // lands somewhere that displays it (stale-list bug).
  if(id==='meetings' || id==='home') loadMeets();
  if(id==='insights') loadInsights();
}
function renderActive(){
  try {
    if(ACTIVE==='home') renderHome();
    else if(ACTIVE==='history') renderHistory();
    else if(ACTIVE==='canvas') renderCanvas();
    else if(ACTIVE==='notes') renderNotes();
    else if(ACTIVE==='meetings') renderMeetings();
    else if(ACTIVE==='insights') renderInsights();
    else if(ACTIVE==='dictionary') renderDictionary();
    else if(ACTIVE==='snippets') renderSnippets();
    else if(ACTIVE==='devices') renderDevices();
    else if(ACTIVE==='settings') renderSettings();
  } catch(e){
    const box = document.querySelector('#scr-'+ACTIVE+' .main') || document.querySelector('#scr-'+ACTIVE+' .threepane') || document.body;
    if(box) box.innerHTML = '<div class="main"><div class="empty">Could not render '+ACTIVE+': '+esc(e && (e.message||e.stack||String(e)))+'</div></div>';
  }
}
function renderSidebar(){
  if(!STATE) return;
  const name = (STATE.settings && STATE.settings.sync_device_name) || 'You';
  document.getElementById('userName').textContent = name;
  document.getElementById('avatarInitial').textContent = (name[0]||'V').toUpperCase();
  const devs = STATE.devices||[];
  document.getElementById('sideDevices').innerHTML = devs.length
    ? devs.map(d=>`<div class="devrow${d.online?'':' off'}"><span class="ddot${d.online?' on':''}"></span>${esc(d.device_name||'Device')}</div>`).join('')
    : `<div class="devrow"><span class="ddot on"></span>This Mac</div>`;
  renderDeadBanner();
}
function statusPill(){
  const rec = STATE && STATE.recording, proc = STATE && STATE.processing;
  const txt = rec? 'Listening…' : proc? 'Transcribing…' : 'Ready';
  return `<div class="statuspill${rec||proc?' rec':''}"><span class="sdot"></span>${txt}</div>`;
}

function loadMeets(){
  api('list_meetings').then(r=>{
    if(r && r.ok){ MEETS=r; if(ACTIVE==='home') renderHome(); if(ACTIVE==='meetings') renderMeetings(); }
  });
}
// Minimal failure surface (IDI-167). Several actions had NO way to report an
// error — they just looked like they had worked. Errors linger longer than
// confirmations because they need reading.
let _toastTimer=null;
function toast(msg, isErr){
  if(!msg) return;
  let el=document.getElementById('flumeToast');
  if(!el){ el=document.createElement('div'); el.id='flumeToast'; document.body.appendChild(el); }
  el.className='toast'+(isErr?' err':'')+' on';
  el.textContent=msg;
  if(_toastTimer) clearTimeout(_toastTimer);
  _toastTimer=setTimeout(()=>{ el.className='toast'+(isErr?' err':''); }, isErr?5000:2200);
}
// Stopping a meeting used to be fire-and-forget with a blind 800ms reload: a
// failure was invisible and a slow stop reloaded a stale list. Chain it.
function stopMeeting(btn){
  busyGuard(btn || 'stop_meeting', ()=>api('stop_meeting')).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ toast((r.error)||'Could not stop the meeting.', true); }
    loadMeets();
  });
}
let MCHAT=[];   // [{q, a, sources, err, pending}]
function renderAskThread(){
  const box=document.getElementById('askThread');
  if(!box) return;
  box.innerHTML = MCHAT.map(m=>{
    let a='';
    if(m.pending) a='<div class="askThink"><i></i><i></i><i></i></div>';
    else if(m.err) a=`<div class="askA err">${esc(m.err)}</div>`;
    else a=`<div class="askA">${esc(m.a)}${m.sources&&m.sources.length?`<div class="askSrc">FROM: ${esc(m.sources.join(' · '))}</div>`:''}</div>`;
    return `<div class="askQ">${esc(m.q)}</div>`+a;
  }).join('');
  box.scrollTop=box.scrollHeight;
}
function askMeetings(){
  const inp=document.getElementById('askInput');
  const q=(inp.value||'').trim();
  if(!q) return;
  inp.value='';
  const entry={q:q, pending:true};
  MCHAT.push(entry);
  if(MCHAT.length>6) MCHAT=MCHAT.slice(-6);
  renderAskThread();
  api('ask_meetings', q).then(r=>{
    entry.pending=false;
    if(r && r.ok){ entry.a=r.answer; entry.sources=r.sources||[]; }
    else { entry.err=(r&&r.error)||'Something went wrong — try again.'; }
    renderAskThread();
  });
}
function fmtDur(secs){
  secs=Math.max(0,Math.floor(secs||0));
  const m=Math.floor(secs/60), s=secs%60;
  return m+':'+String(s).padStart(2,'0');
}
function meetingLauncherCard(){
  // 31a — MeetingLauncherCard, or the ActiveMeetingCard variant while recording.
  if(MEETS.active_id){
    return `
    <div class="mcard">
      <div class="mrec"><span class="mdot"></span>REC</div>
      <div style="flex:1;min-width:0">
        <div class="mctitle">${esc(MEETS.active_title||'Meeting')}</div>
        <div class="mcsub mono">${fmtDur(MEETS.active_elapsed)} · recording</div></div>
      <button class="btn primary" style="flex:none" onclick="api('open_meeting_launcher')">Return to meeting</button>
      <button class="btn ghost" style="flex:none" onclick="stopMeeting(this)">Stop</button>
    </div>`;
  }
  const recent=(MEETS.meetings||[]).slice(0,3).map(m=>`
    <div class="lrow" style="cursor:pointer" onclick="api('open_meeting', ${esc(JSON.stringify(m.id))})">
      <span class="ltime">${fmtDur(m.duration_seconds)}</span>
      <span class="ltext">${esc(m.title||'Meeting')}</span>
      <span class="tag ${m.status==='failed'?'fail':'local'}">${esc(m.status||'')}</span></div>`).join('');
  return `
    <div class="mcard">
      <div style="flex:1;min-width:0">
        <div class="mctitle"><span class="mnew">NEW</span> Record a meeting</div>
        <div class="mcsub">Live transcript, your notes beside it, and an AI summary when you stop. No bot joins the call.</div>
        <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
          <button class="btn primary" style="flex:none" onclick="api('open_meeting_launcher')"><span class="mrecdot"></span>Start meeting</button>
          <button class="btn ghost" style="flex:none" onclick="show('settings')">Settings</button>
        </div></div>
    </div>
    ${recent?`<div class="sechead"><h2>Recent meetings</h2><span class="link" onclick="navTo('meetings')">See all →</span></div><div class="rows">${recent}</div>`:''}`;
}
function renderHome(){
  if(!STATE) return;
  const h = STATE.history||[];
  const name = (STATE.settings && STATE.settings.sync_device_name) || 'there';
  const rows = h.slice(0,3).map(e=>`
    <div class="lrow"><span class="ltime">${esc(e.ts||'')}</span>
      <span class="ltext">${esc(e.text)}</span>
      <span class="tag ${tagCls(e.app)}">${esc(e.app||'Local')}</span>
      <button class="cbtn" onclick="api('copy_text', ${esc(JSON.stringify(e.text))})">${SVG.copy}</button></div>`).join('')
    || '<div class="empty">Nothing yet — hold your hotkey to record.</div>';
  document.getElementById('homeMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Welcome back</div><h1 class="title">${esc(name)}</h1></div>${statusPill()}</div>
    <div class="features">
      <div class="fcard cream" style="cursor:pointer" onclick="show('insights')"><div class="disc">${SVG.mic}</div><div class="fnum">${STATE.daily_words||0}</div><div class="flabel">Words today</div><div class="fsub">${STATE.total_transcriptions||0} all time &middot; Insights &rarr;</div></div>
      <div class="fcard sage"><div class="disc">${SVG.grid}</div><div class="fnum">Canvas</div><div class="flabel">Shared clipboard</div><div class="fsub">${STATE.sync_connected?'Synced':'Local only'}</div></div>
      <div class="fcard plum"><div class="disc">${SVG.lines}</div><div class="fnum">${realNotes().length}</div><div class="flabel">Notes synced</div><div class="fsub">${STATE.total_words||0} words total</div></div>
    </div>
    ${meetingLauncherCard()}
    <div class="sechead"><h2>Recent</h2><span class="link" onclick="show('history')">Open history →</span></div>
    <div class="rows">${rows}</div>`;
  if(!MEETS_LOADED){ MEETS_LOADED=true; loadMeets(); }
}

// ── Insights ──────────────────────────────────────────────────────────────────
let INS=null, INS_REFRESHED=false;
const fmtN = n => (n==null?'—':Number(n).toLocaleString('en-US'));
const fmtK = n => n>=10000 ? (Math.round(n/100)/10)+'K' : fmtN(n);
function fmtMin(min){
  if(min==null) return '—';
  const h=Math.floor(min/60), m=Math.round(min%60);
  return h>0 ? h+'h '+String(m).padStart(2,'0')+'m' : m+'m';
}
function fmtHour(h){
  if(h==null) return '—';
  const ap=h<12?'AM':'PM'; const v=h%12===0?12:h%12;
  return v+' '+ap;
}
function fmtPct(p){
  if(p==null) return '';
  return p>=10 ? String(Math.round(p)) : String(p);
}
function loadInsights(){
  api('get_insights').then(r=>{
    if(r && r.ok){ INS=r; if(ACTIVE==='insights') renderInsights(); }
    // One cloud fold-in per dashboard session — incremental after the first.
    if(!INS_REFRESHED){
      INS_REFRESHED=true;
      api('refresh_insights').then(r2=>{
        if(r2 && r2.ok){ INS=r2; if(ACTIVE==='insights') renderInsights(); }
      });
    }
  });
}
function insTip(el, html){
  let tip=document.getElementById('insTip');
  if(!tip){ tip=document.createElement('div'); tip.id='insTip'; document.body.appendChild(tip); }
  if(!html){ tip.style.display='none'; return; }
  tip.innerHTML=html;
  const r=el.getBoundingClientRect();
  tip.style.display='block';
  const tw=tip.offsetWidth;
  tip.style.left=Math.max(6,Math.min(window.innerWidth-tw-6, r.left+r.width/2-tw/2))+'px';
  tip.style.top=Math.max(6,(r.top-tip.offsetHeight-8))+'px';
}
function copyRecap(btn){
  if(!INS) return;
  const L=[];
  L.push('My Verbal insights —');
  L.push(fmtN(INS.total_words)+' words dictated ('+fmtN(INS.total_dictations)+' dictations)');
  if(INS.wpm) L.push(INS.wpm+' words/min — top '+fmtPct(INS.wpm_percentile)+'% of typists');
  if(INS.saved_month_min) L.push(fmtMin(INS.saved_month_min)+' saved this month vs typing');
  if(INS.current_streak) L.push(INS.current_streak+'-day streak (best '+INS.best_streak+')');
  if(INS.apps && INS.apps.length) L.push('Most dictated into: '+INS.apps[0].name);
  busyGuard(btn||'copyRecap', ()=>api('copy_text', L.join('\n'))).then(()=>toast('Recap copied'));
}
function insGauge(wpm){
  // Semicircular gauge, 0..200 wpm, typist marker at 52.
  const W=260,H=138,cx=130,cy=128,r=104,sw=13;
  const P=(a)=>({x:cx+Math.cos(a)*r, y:cy+Math.sin(a)*r});
  const arc=(a0,a1,col)=>{
    const p0=P(a0),p1=P(a1);
    return '<path d="M '+p0.x+' '+p0.y+' A '+r+' '+r+' 0 '+((a1-a0)>Math.PI?1:0)+' 1 '+p1.x+' '+p1.y+'" stroke="'+col+'" stroke-width="'+sw+'" fill="none" stroke-linecap="round"/>';
  };
  let s='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'">';
  s+=arc(Math.PI, 2*Math.PI, 'rgba(240,240,240,.08)');
  if(wpm){
    s+=arc(Math.PI, Math.PI+Math.PI*Math.min(1,wpm/200), '#C85A3E');
    const t=P(Math.PI+Math.PI*(52/200));
    s+='<circle cx="'+t.x+'" cy="'+t.y+'" r="4" fill="#0e1012" stroke="rgba(240,240,240,.6)" stroke-width="1.5"><title>Average typist - 52 wpm</title></circle>';
  }
  return s+'</svg>';
}
function insHeatmap(){
  const box=document.getElementById('insHm');
  if(!box || !INS || !INS.series) return;
  const series=INS.series;
  // Pad so columns are real weeks (rows Sun..Sat).
  const first=new Date(series[0][0]+'T00:00:00');
  const pad=first.getDay();
  const cells=[]; for(let i=0;i<pad;i++) cells.push(null);
  series.forEach(d=>cells.push(d));
  // Size cells to fill the card width; drop the oldest weeks if they can't fit.
  const gap=3, avail=box.clientWidth||900;
  let weeks=Math.ceil(cells.length/7);
  let cell=Math.floor((avail-(weeks-1)*gap)/weeks);
  if(cell<10){ cell=10; const fitWeeks=Math.floor((avail+gap)/(cell+gap));
    const drop=(weeks-fitWeeks)*7; if(drop>0) cells.splice(0,drop); weeks=fitWeeks; }
  if(cell>16) cell=16;
  box.style.gridTemplateRows='repeat(7,'+cell+'px)';
  const mx=Math.max(1, ...cells.map(c=>c?c[1]:0));
  const steps=['#1f2225','#4a2d24','#7a4030','#a84b33','#C85A3E','#E88D6A'];
  const streak=INS.current_streak||0;
  const todayIdx=cells.length-1;
  let html='';
  cells.forEach((c,i)=>{
    if(!c){ html+='<i style="width:'+cell+'px;height:'+cell+'px;visibility:hidden"></i>'; return; }
    const w=c[1];
    let idx=0;
    if(w>0){ const f=w/mx; idx=f<.15?1:f<.35?2:f<.6?3:f<.85?4:5; }
    const inStreak=streak>1 && i>todayIdx-streak;
    const col=(inStreak && idx===0)?steps[1]:steps[idx];
    html+='<i style="width:'+cell+'px;height:'+cell+'px;background:'+col+'"'
        +(inStreak?' class="gl"':'')
        +' onmouseenter="insTip(this,\''+c[0]+' <span class=tmut>&middot;</span> '+fmtN(w)+' words\')"'
        +' onmouseleave="insTip(null)"></i>';
  });
  box.innerHTML=html;
}
function renderInsights(){
  const M=document.getElementById('insightsMain');
  if(!INS){ M.innerHTML='<div class="mhead"><div><div class="eyebrow">Insights</div><h1 class="title">How you flow</h1></div></div><div class="empty">Crunching your numbers…</div>'; return; }
  if(INS.empty){
    M.innerHTML=`
      <div class="mhead"><div><div class="eyebrow">Insights</div><h1 class="title">How you flow</h1></div></div>
      <div class="inscard insempty">
        <div class="bigmic">${SVG.mic}</div>
        <h2>Your story starts with a sentence</h2>
        <p>Hold your hotkey and dictate anything. Words, speed, streaks and the apps you speak into all start counting from your first take.</p>
      </div>`;
    return;
  }
  const wpm=INS.wpm;
  const speedX = wpm ? (Math.round(wpm/INS.typing_wpm*10)/10) : null;
  const novels = INS.total_words>=40000 ? (Math.round(INS.total_words/80000*10)/10) : null;
  const delta = INS.month_delta_pct;
  const deltaTag = (delta==null||delta===0) ? '' :
    `<span class="up">${delta>0?'&#9650;':'&#9660;'}${Math.abs(delta)}%</span>`;
  const savedAll = INS.saved_all_min ? ` &middot; ${fmtMin(INS.saved_all_min)} all time` : '';
  const apps=(INS.apps||[]);
  const appsTotal=apps.reduce((a,b)=>a+b.words,0)||1;
  const cols=['#C85A3E','#a84b33','#a84b33','#7a4030','#7a4030','#7a4030'];
  const appsHtml = apps.length ? apps.map((a,i)=>`
      <div class="insabar"><div class="arow"><span class="an">${esc(a.name)}</span><span class="av">${fmtK(a.words)} &middot; ${a.pct}%</span></div>
      <div class="atr"><i style="width:${Math.max(1,Math.round(a.words/appsTotal*100))}%;background:${cols[i]||cols[5]}"></i></div></div>`).join('')
    : '<div class="empty" style="padding:18px 0">App breakdown builds as you dictate on this device.</div>';
  const hrs=INS.hours||[]; const hmx=Math.max(1,...hrs);
  const hoursHtml=hrs.map((v,i)=>
    `<i style="height:${Math.max(3,Math.round(v/hmx*100))}%" class="${i===INS.peak_hour?'pk':''}"`
    +` onmouseenter="insTip(this,'${fmtHour(i)} <span class=tmut>&middot;</span> ${fmtN(v)} words')" onmouseleave="insTip(null)"></i>`).join('');
  const busiest=INS.busiest_day;
  const streakBits=[];
  if(INS.current_streak>1) streakBits.push(`&#128293; <b>${INS.current_streak}-day</b> streak`);
  if(busiest) streakBits.push(`busiest day <b>${esc(busiest[0])}</b> (<b>${fmtN(busiest[1].w)}</b> words)`);
  M.innerHTML=`
    <div class="mhead"><div><div class="eyebrow">Insights</div><h1 class="title">How you flow</h1></div>
      <button class="btn ghost" style="flex:none" onclick="copyRecap(this)">${SVG.copy}Copy recap</button></div>
    <div class="inshero">
      ${insGauge(wpm)}
      <div class="hnum${wpm?'':' na'}">${wpm?wpm:'&mdash;'}</div>
      <div class="hunit">WORDS PER MINUTE</div>
      ${wpm&&INS.wpm_percentile!=null?`<div class="hbadge">Top ${fmtPct(INS.wpm_percentile)}% of typists</div>`:''}
      <div class="hsub">${wpm
        ? `You speak <b>${speedX}&times;</b> faster than the average typist writes.`
        : 'A few more dictations and we&rsquo;ll clock your speaking speed.'}</div>
    </div>
    <div class="insband">
      <div class="itile cream"><div class="tk">Words dictated</div>
        <div class="tv">${fmtN(INS.total_words)}${deltaTag}</div>
        <div class="ts">${fmtN(INS.today_words)} today${novels?` &middot; &asymp; ${novels} novels`:` &middot; ${fmtN(INS.total_dictations)} dictations`}</div></div>
      <div class="itile sage"><div class="tk">Time saved</div>
        <div class="tv">${fmtMin(INS.saved_month_min)}</div>
        <div class="ts">last 30 days &middot; vs ${INS.typing_wpm} wpm typing${savedAll}</div></div>
      <div class="itile plum"><div class="tk">Streak</div>
        <div class="tv">${INS.current_streak} day${INS.current_streak===1?'':'s'}</div>
        <div class="ts">best ever &middot; ${INS.best_streak} days</div></div>
      <div class="itile"><div class="tk">Polished for you</div>
        <div class="tv">${fmtN(INS.polished_words)}</div>
        <div class="ts">words fixed &middot; ${INS.dict_rules} dictionary rule${INS.dict_rules===1?'':'s'}${INS.auto_rules?` (${INS.auto_rules} auto-learned)`:''}</div></div>
    </div>
    <div class="inscard">
      <div class="chd">Activity <span class="csub">day by day</span></div>
      <div class="inshm" id="insHm"></div>
      <div class="inshmfoot">
        <span>${streakBits.join(' &mdash; ')||'Every square is a day you dictated.'}</span>
        <span class="inshmleg">less <i style="background:#1f2225"></i><i style="background:#4a2d24"></i><i style="background:#7a4030"></i><i style="background:#a84b33"></i><i style="background:#C85A3E"></i><i style="background:#E88D6A"></i> more</span>
      </div>
    </div>
    <div class="inscard inssplit">
      <div>
        <div class="inssub">Where you dictate <span style="float:right;letter-spacing:.02em;text-transform:none;color:rgba(240,240,240,.42)">last 30 days</span></div>
        ${appsHtml}
      </div>
      <div>
        <div class="inssub">Your rhythm</div>
        <div class="inshours">${hoursHtml}</div>
        <div class="inshfoot"><span>12AM</span><span>6</span><span>NOON</span><span>6</span><span>11PM</span></div>
        <div class="inspeak">${INS.peak_hour!=null
          ? `Peak hour <b>${fmtHour(INS.peak_hour)}</b>${INS.morning_share!=null?` &mdash; mornings carry <b>${INS.morning_share}%</b> of your words`:''}`
          : 'Your daily pattern appears here as you dictate.'}</div>
      </div>
    </div>`;
  insHeatmap();
}

function renderHistory(){
  if(!STATE) return;
  const h = STATE.history||[];
  const list = h.map((e,i)=>{
    const failed = e.status==='failed';
    return `
    <div class="hrow${i===SELH?' active':''}${failed?' failed':''}" onclick="SELH=${i};EDITH=false;retryErr='';renderHistory()">
      <div class="hrtop"><span class="htime">${esc(e.ts||'')}</span><span class="tag ${failed?'fail':tagCls(e.app)}">${failed?'Failed':esc(e.app||'Local')}</span></div>
      <div class="htitle">${failed?'⚠ Transcription failed':esc(titleOf(e.text))}</div>
      <div class="hprev">${failed?'Audio saved — tap to retry':esc(e.text)}</div></div>`;
  }).join('') || '<div class="empty">No transcriptions yet.</div>';
  const sel = h[SELH];
  const audioBar = (sel && sel.has_audio) ? playbarHTML() : '';
  let prev;
  if(!sel){ prev = '<div class="empty">Select a transcription.</div>'; }
  else if(sel.status==='failed'){ prev = `
      <div class="pvhead"><span class="pvmeta">${esc(sel.ts||'')}</span></div>
      ${audioBar}
      <div class="failbox"><div class="failicon">⚠</div>
        <div class="failtitle">Transcription failed</div>
        <div class="failsub">${retryErr?esc(retryErr):'The network may have dropped. Your audio is saved — retry when you are back online.'}</div></div>
      <div class="pvactions">
        <button class="btn primary" style="flex:1.3" ${retryBusy?'disabled':''} onclick="retryRec(${esc(JSON.stringify(sel.id))})">${retryBusy?'Retrying…':'Retry transcription'}</button></div>`;
  }
  else if(EDITH){ prev = `
      <div class="pvhead"><span class="pvmeta">${esc(sel.ts||'')}</span></div>
      <textarea class="transcript histedit" id="histEdit">${esc(sel.text)}</textarea>
      <div class="pvactions"><button class="btn ghost" onclick="EDITH=false;renderHistory()">Cancel</button>
        <button class="btn primary" style="flex:1.3" onclick="saveHistEdit(${esc(JSON.stringify(sel.text))})">${SVG.copy}Save changes</button></div>`;
  } else {
    // A third action button used to sit beside Copy and Edit, calling the very
    // same copy_text — a re-inject that never re-injected. Dropped in IDI-167:
    // a real one would paste into the dashboard, which holds focus.
    prev = `
      <div class="pvhead"><span class="pvmeta">${esc(sel.ts||'')}</span></div>
      <div class="pvtagrow"><span class="tag ${tagCls(sel.app)}">${esc(sel.app||'Local')}</span><span class="pvsub">${words(sel.text)} words</span></div>
      ${audioBar}
      <div class="transcript">${esc(sel.text)}</div>
      <div class="pvactions"><button class="btn primary" style="flex:1.3" onclick="api('copy_text', ${esc(JSON.stringify(sel.text))})">${SVG.copy}Copy</button>
        <button class="btn ghost" onclick="EDITH=true;renderHistory()">${SVG.edit}Edit</button></div>`;
  }
  document.getElementById('historyMain').innerHTML = `
    <div class="listcol"><div class="eyebrow">${(STATE.total_transcriptions||0)} total</div><h1 class="title">History</h1>
      <div class="searchbox">${SVG.search}<input placeholder="Search transcriptions…" oninput="filterHist(this.value)"/></div>
      <div id="histList">${list}</div></div>
    <div class="preview">${prev}</div>`;
  if(sel && sel.has_audio) loadAudio(sel.id); else stopAudio();
}

const PB_WAVE=[6,10,16,9,18,7,13,17,6,11,15,8,13,19,8,17,10,13,6,11,16,9,14,7,12,18,8,15,10,13,6,12,16,9];
const SVG_PAUSE='<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" height="14" rx="1"/><rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>';
function playbarHTML(){
  return `<div class="playbar">
    <button class="playbtn" id="playBtn" onclick="togglePlay()">${SVG.play}</button>
    <div class="pbcol">
      <div class="pbwave" id="pbWave" onclick="seekWave(event)">${PB_WAVE.map(hh=>`<i style="height:${hh}px"></i>`).join('')}</div>
      <div class="pbtime"><span id="pbCur">0:00</span><span id="pbTot">0:00</span></div>
    </div>
  </div>`;
}
let AUDIO_ID=null;
function _audioEl(){
  let a=document.getElementById('histAudio');
  if(!a){ a=document.createElement('audio'); a.id='histAudio'; document.body.appendChild(a);
    a.addEventListener('timeupdate', updatePlayUI);
    a.addEventListener('loadedmetadata', updatePlayUI);
    a.addEventListener('ended', ()=>{ setPlayIcon(false); });
    a.addEventListener('play', ()=>setPlayIcon(true));
    a.addEventListener('pause', ()=>setPlayIcon(false));
  }
  return a;
}
function loadAudio(id){
  const a=_audioEl();
  if(AUDIO_ID===id && a.src){ updatePlayUI(); return; }
  AUDIO_ID=id; try{a.pause();}catch(e){} setPlayIcon(false);
  api('get_audio', id).then(r=>{
    if(AUDIO_ID!==id) return;
    if(r && r.ok && r.data_uri){ a.src=r.data_uri; a.load(); updatePlayUI(); }
  });
}
function stopAudio(){ const a=document.getElementById('histAudio'); if(a){ try{a.pause();}catch(e){} } AUDIO_ID=null; }
function togglePlay(){
  const a=_audioEl();
  if(!a.src){ if(AUDIO_ID) loadAudio(AUDIO_ID); return; }
  if(a.paused) a.play(); else a.pause();
}
function seekWave(ev){
  const a=document.getElementById('histAudio'); const w=document.getElementById('pbWave');
  if(!a||!w||!a.duration) return;
  const r=w.getBoundingClientRect(); const frac=Math.min(1,Math.max(0,(ev.clientX-r.left)/r.width));
  a.currentTime=frac*a.duration; updatePlayUI();
}
function setPlayIcon(p){ const b=document.getElementById('playBtn'); if(b) b.innerHTML = p?SVG_PAUSE:SVG.play; }
function fmtT(s){ s=Math.floor(s||0); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function updatePlayUI(){
  const a=document.getElementById('histAudio'); if(!a) return;
  const cur=document.getElementById('pbCur'), tot=document.getElementById('pbTot');
  if(cur) cur.textContent=fmtT(a.currentTime);
  if(tot) tot.textContent=fmtT(isFinite(a.duration)?a.duration:0);
  const wave=document.getElementById('pbWave');
  if(wave && a.duration){ const bars=wave.children; const n=Math.floor(bars.length*(a.currentTime/a.duration));
    for(let i=0;i<bars.length;i++) bars[i].classList.toggle('on', i<n); }
  setPlayIcon(!a.paused);
}
function filterHist(q){ q=(q||'').toLowerCase(); document.querySelectorAll('#histList .hrow').forEach((el,i)=>{
  const t=(STATE.history[i]&&STATE.history[i].text||'').toLowerCase(); el.style.display=t.includes(q)?'':'none'; }); }
function playRec(id){ api('play_recording', id); }
function retryRec(id){
  if(retryBusy) return;
  retryErr=''; retryBusy=true; renderHistory();
  api('retry_transcription', id).then(r=>{
    retryBusy=false;
    if(r && r.ok===false){ retryErr = r.error || 'Retry failed'; renderHistory(); }
    else load();
  }).catch(()=>{ retryBusy=false; retryErr='Retry failed'; renderHistory(); });
}
function saveHistEdit(oldText){
  const el=document.getElementById('histEdit'); if(!el) return;
  const nt=el.value;
  api('edit_text', oldText, nt).then(()=>{ EDITH=false; load(); });
}

const SVG_REFRESH='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>';
function renderCanvas(){
  const img = CANVAS.image_url
    ? `<div class="cvimgwrap"><img class="cvimg" src="${esc(CANVAS.image_url)}"/><button class="cvimgx" title="Remove image" onclick="clearCanvasImage()">✕</button></div>` : '';
  const from = CANVAS.from ? `<span class="pvsub" style="margin-left:auto">From ${esc(CANVAS.from)}</span>` : '';
  document.getElementById('canvasMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Shared clipboard</div><h1 class="title">Canvas</h1></div>
      <button class="roundbtn" title="Refresh" onclick="loadCanvas()">${SVG_REFRESH}</button></div>
    <div class="dropzone" onclick="pickCanvasImage()"><div class="dzicon">${SVG.grid}</div><div><div class="dztitle">Type below, or add an image</div><div class="dzsub">Paste an image (${IS_WINDOWS?'Ctrl+V':'⌘V'}), or click to choose a file · syncs to your devices</div></div></div>
    ${img}
    <textarea class="canvasArea" id="canvasArea" placeholder="Type or paste text here…" oninput="canvasDirty()">${esc(CANVAS.content||'')}</textarea>
    <div class="canvasBar">
      <button class="chipbtn" onclick="saveCanvas(this)">Save &amp; Sync</button>
      <button class="chipbtn" onclick="pickCanvasImage()">Add image…</button>
      <button class="chipbtn" onclick="pasteCanvasImage()">Paste image</button>
      <button class="chipbtn" onclick="clearCanvas(this)">Clear</button>${from}</div>
    <div class="cvmsg" id="cvMsg"></div>`;
}
function cvMsg(t){ const el=document.getElementById('cvMsg'); if(el) el.textContent=t||''; }
function canvasText(){ return (document.getElementById('canvasArea')||{}).value||CANVAS.content||''; }
function canvasDirty(){ const a=document.getElementById('canvasArea'); if(a) CANVAS.content=a.value; }
// Was: printed "Saved & synced" unconditionally, even when the write failed
// (IDI-167). Only claim success when the backend says so.
// IDI-173: a text save sends ONLY the text. It used to resend image_url on
// every keystroke-save, so two devices editing text/image raced each other into
// clearing the other's column.
function saveCanvas(btn){
  const v=canvasText();
  cvMsg('Saving…');
  busyGuard(btn || 'save_canvas', ()=>api('save_canvas', v)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ cvMsg((r.error)||'Could not save — check your connection.'); return; }
    CANVAS.content=v; cvMsg('Saved & synced');
  });
}
function loadCanvas(){ api('fetch_canvas').then(r=>{ if(r&&r.ok){ CANVAS={content:r.content||'',image_url:r.image_url||null,from:CANVAS.from}; if(ACTIVE==='canvas')renderCanvas(); } }); }
// An explicit clear — a real write of {content:'', image_url:null} that other
// devices APPLY (they used to falsy-drop the empty content and stay stale).
function clearCanvas(btn){
  busyGuard(btn || 'clear_canvas', ()=>api('clear_canvas')).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ cvMsg((r.error)||'Could not clear the canvas.'); return; }
    CANVAS={content:'',image_url:null}; if(ACTIVE==='canvas')renderCanvas();
  });
}
// Image-only removal: keeps the text, nulls the image explicitly.
function clearCanvasImage(){ const v=canvasText(); api('save_canvas', v, null).then(()=>{ CANVAS.image_url=null; CANVAS.content=v; if(ACTIVE==='canvas')renderCanvas(); }); }
function pickCanvasImage(){ cvMsg('Choose an image…'); api('canvas_add_image_file', canvasText()).then(applyCanvasImage); }
function pasteCanvasImage(){ cvMsg('Pasting image…'); api('canvas_paste_image', canvasText()).then(applyCanvasImage); }
function applyCanvasImage(r){
  if(r&&r.ok&&r.image_url){ CANVAS.image_url=r.image_url; CANVAS.content=canvasText(); if(ACTIVE==='canvas')renderCanvas(); }
  else if(r&&r.cancelled){ cvMsg(''); }
  else { cvMsg((r&&r.error)||'Could not add image'); }
}
// JS clipboard path (works on some WKWebView builds); native pasteCanvasImage is the reliable fallback.
function sendCanvasImage(dataUri){ const txt=canvasText(); api('save_canvas_image_data', dataUri, txt).then(applyCanvasImage); }

let NOTE_REC=false, _noteTimer=null, _rawTimer=null, NOTE_QUERY='', SHOW_ORIG=false, NOTE_SEG_ID=null;
let NOTE_ASK=null;   // {q, answer, sources} | {q, busy:true} | null — the ask-your-notes card
function strippedNote(n){ return (n.content||'').replace(/<[^>]*>/g,' ').replace(/&nbsp;/g,' ').replace(/\[( |x|X)\]/g,'').replace(/(^|\n)\s*(?:[-*]|\d+\.)\s+/g,'$1').replace(/[*#`>☑☐]/g,'').replace(/\s+/g,' ').trim(); }
function notePreview(n){ return strippedNote(n).slice(0,80); }
// When searching, center the preview on the first match so the hit is visible
// even deep inside a long note (Notes v3).
function noteSnippet(n,q){
  const s=strippedNote(n);
  if(!q) return s.slice(0,80);
  const j=s.toLowerCase().indexOf(q.toLowerCase());
  if(j<0) return s.slice(0,80);
  const st=Math.max(0, j-28);
  return (st>0?'…':'')+s.slice(st, st+90);
}
// Escape + wrap every match of q in <mark class="hl"> (Notes v3 search highlight).
function hlText(s,q){
  s=String(s==null?'':s);
  if(!q) return esc(s);
  const lc=s.toLowerCase(), ql=q.toLowerCase();
  let out='', i=0;
  for(;;){
    const j=lc.indexOf(ql,i);
    if(j<0){ out+=esc(s.slice(i)); break; }
    out+=esc(s.slice(i,j))+'<mark class="hl">'+esc(s.slice(j,j+q.length))+'</mark>';
    i=j+q.length;
  }
  return out;
}
function noteDateLabel(iso){
  try{
    const d=new Date(iso), now=new Date();
    const day=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime();
    const diff=Math.round((day(now)-day(d))/86400000);
    if(diff<=0) return d.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'});
    if(diff===1) return 'Yesterday';
    if(diff<7) return d.toLocaleDateString([], {weekday:'short'});
    return d.toLocaleDateString([], {month:'short', day:'numeric'});
  }catch(e){ return (iso||'').slice(0,10); }
}
function noteGroup(n){
  try{
    const d=new Date(n.updated_at), now=new Date();
    const day=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime();
    const diff=Math.round((day(now)-day(d))/86400000);
    if(diff<=0) return 'Today';
    if(diff<7) return 'This week';
    return 'Earlier';
  }catch(e){ return 'Earlier'; }
}
// Checklist progress {done,total} from either storage form (markdown task list
// or the rendered chkbox HTML) — null when the note has no checklist.
function chkProgress(n){
  const c=n.content||'';
  let total=0, done=0;
  if(isHtmlContent(c)){
    const m=c.match(/data-checked="[01]"/g)||[];
    total=m.length; done=m.filter(x=>x.indexOf('"1"')>=0).length;
  } else {
    const m=c.match(/^\s*[-*]\s+\[( |x|X)\]/gm)||[];
    total=m.length; done=m.filter(x=>/[xX]/.test(x)).length;
  }
  return total ? {done:done, total:total} : null;
}
function curNote(){ return NOTES.find(x=>x.id===SELN) || filteredNotes()[0] || NOTES[0] || null; }
function notesFlag(name){ return !(STATE&&STATE.settings) || STATE.settings[name]!==false; }
function isHtmlContent(s){ return /<(\w|\/)/.test(s||''); }
function noteBodyHtml(n){ const c=n.content||''; if(!c.trim()) return ''; return isHtmlContent(c) ? c : mdToHtml(c); }
function realNotes(){ return NOTES.filter(n=>String(n.id||'').indexOf('::conflict::')<0); }
function rankNote(n,q){
  if((n.title||'').toLowerCase().includes(q)) return 0;
  if((n.content||'').toLowerCase().includes(q) || (n.raw_content||'').toLowerCase().includes(q)) return 1;
  return 2;
}
function filteredNotes(){
  // Conflict copies are internal; never surface them in the notes list.
  let arr=realNotes();
  const q=(NOTE_QUERY||'').trim().toLowerCase();
  if(!q || !notesFlag('notes_search_enabled')) return arr;
  // Mirrors search_notes ranking (Agent A): title>content/raw, recency tiebreak.
  arr=arr.filter(n=>rankNote(n,q)<2);
  arr=arr.slice().sort((a,b)=>String(b.updated_at||'').localeCompare(String(a.updated_at||'')));
  arr.sort((a,b)=>rankNote(a,q)-rankNote(b,q));
  return arr;
}

function renderNotes(){
  const n = curNote();
  const searchBox = notesFlag('notes_search_enabled') ? `
      <div class="searchbox">${SVG.search}<input id="noteSearch" type="search" aria-label="Search notes" placeholder="Search or ask your notes…" value="${esc(NOTE_QUERY)}" oninput="noteSearchInput(this.value)" onkeydown="if(event.key==='Enter')askNotes()"/></div>
      <div class="notecount" id="noteCount" role="status" aria-live="polite"></div>
      <div id="noteAsk"></div>` : '';
  const editor = n ? noteEditorHtml(n) : '<div class="empty">Select or create a note.</div>';
  const all=realNotes();
  const weekAgo=Date.now()-7*86400000;
  const wk=all.filter(x=>{ const t=Date.parse(x.updated_at||''); return t && t>=weekAgo; }).length;
  document.getElementById('notesMain').innerHTML = `
    <div class="listcol"><div class="mhead"><div><div class="eyebrow">${all.length} notes${wk?` · ${wk} this week`:''}</div><h1 class="title">Notes</h1></div>
      <div style="display:flex;gap:8px">
        <button class="roundbtn" aria-label="Dictate a new note" title="Dictate a new note" onclick="dictateNewNote()">${SVG.mic}</button>
        <button class="roundbtn" aria-label="New note" title="New note" onclick="newNote()">${SVG.plus}</button>
      </div></div>
      ${searchBox}
      <div id="noteList"></div></div>
    <div class="editor">${editor}</div>`;
  renderNoteList();
  renderNoteAsk();
  if(n && !SHOW_ORIG){ const b=document.getElementById('noteBody'); if(b) b.innerHTML=noteBodyHtml(n); updateDictateBtn(); }
  updateSegIcons();
}

// ── 31f — Meetings page (dedicated sidebar destination) ──────────────────────
function meetGroup(m){
  try{
    const d=new Date(m.started_at), now=new Date();
    const day=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime();
    const diff=Math.round((day(now)-day(d))/86400000);
    if(diff<=0) return 'Today';
    if(diff<7) return 'This week';
    return 'Earlier';
  }catch(e){ return 'Earlier'; }
}
function renderMeetings(){
  // The Meetings screen is a two-level route: the list, or ONE meeting's detail
  // (which itself has a full-notes sub-page). MER-46 — this is where reading a
  // meeting happens now; the panel keeps only the live meeting.
  if(MVIEW==='detail' && MROW) return MSUBNOTES ? renderMeetNotes() : renderMeetDetail();
  const all=MEETS.meetings||[];
  const total=all.reduce((a,m)=>a+(m.duration_seconds||0),0);
  const activeBar = MEETS.active_id ? `
    <div class="mcard" style="margin:0 0 14px">
      <div class="mrec"><span class="mdot"></span>REC</div>
      <div style="flex:1;min-width:0">
        <div class="mctitle">${esc(MEETS.active_title||'Meeting')}</div>
        <div class="mcsub mono">${fmtDur(MEETS.active_elapsed)} · recording</div></div>
      <button class="btn primary" style="flex:none" onclick="api('open_meeting_launcher')">Return</button>
      <button class="btn ghost" style="flex:none" onclick="stopMeeting(this)">Stop</button>
    </div>` : '';
  document.getElementById('meetingsMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">${all.length} meetings · ${Math.round(total/60)} min captured</div><h1 class="title">Meetings</h1></div>
      <button class="btn primary" style="flex:none" onclick="api('open_meeting_launcher')"><span class="mrecdot"></span>New meeting</button></div>
    ${activeBar}
    <div class="askCard">
      <div class="askHead">Ask your meetings</div>
      <div class="askRow">
        <input id="askInput" placeholder="e.g. What did we decide about the launch? Who owns the wireframes?"
          onkeydown="if(event.key==='Enter')askMeetings()"/>
        <button class="btn primary" style="flex:none" onclick="askMeetings()">Ask</button>
      </div>
      <div class="askThread" id="askThread"></div>
    </div>
    <div class="searchbox">${SVG.search}<input id="meetSearch" type="search" aria-label="Search meetings" placeholder="Search meetings…" value="${esc(MEET_QUERY)}" oninput="MEET_QUERY=this.value;renderMeetRows()"/></div>
    <div class="rows" style="display:block" id="meetRows"></div>`;
  renderMeetRows();
  renderAskThread();
  if(!MEETS_LOADED){ MEETS_LOADED=true; loadMeets(); }
}
// Rows only — re-rendered on each search keystroke so the input keeps focus.
function renderMeetRows(){
  const box=document.getElementById('meetRows'); if(!box) return;
  const q=(MEET_QUERY||'').trim().toLowerCase();
  const all=MEETS.meetings||[];
  const ms=q?all.filter(m=>(m.title||'').toLowerCase().includes(q)):all;
  if(!ms.length){
    box.innerHTML = q
      ? `<div class="empty">No meetings match “${esc(q)}”.</div>`
      : `<div class="meetEmpty">
          <div class="meetEmptyDisc">${SVG.meet}</div>
          <div class="meetEmptyTitle">No meetings yet</div>
          <div class="meetEmptyBody">Start your first meeting from the button above or the menubar.
            Flume captures system audio and your mic silently — no bot joins the call.</div>
          <button class="btn primary" style="width:auto" onclick="api('open_meeting_launcher')">Start your first meeting</button>
        </div>`;
    return;
  }
  // 33j — group rows into ONE parent card per group (Today / This week / Earlier)
  const SPCOL={self:'#D9B36B'};
  const PAL=['#D98A72','#8FA7C2','#A9BD98','#D9B36B'];
  function spDot(sid,i){ return SPCOL[sid]||PAL[i%PAL.length]; }
  function rowHtml(m){
    const status = m.status==='failed' ? ' <span class="tag fail">failed</span>'
      : m.status==='processing' ? ' <span class="tag local">summarizing…</span>' : '';
    const prev = m.status==='processing' ? 'Summarizing…'
      : (m.summary||'').split('\n')[0] || ((m.utterances||0)+' segments'+(m.cloud?'':' · this Mac only'));
    const spk=m.speakers||{};
    const sids=Object.keys(spk);
    const chips=sids.slice(0,3).map((sid,i)=>
      `<span class="mrChip"><i style="background:${spDot(sid,i)}"></i>${esc(spk[sid]||sid)}</span>`).join('');
    const more=sids.length>3?`<span class="mrMore">+${sids.length-3}</span>`:'';
    const marks=(m.marked_moments||[]).length, acts=(m.action_items||[]).length;
    const attrs=[
      marks?`<span class="st">★ ${marks}</span>`:'',
      acts?`<span>✓ ${acts}</span>`:'',
      m.audio_url?'<span>▶</span>':''
    ].filter(Boolean).join('');
    const isNew = m.status==='ready' && (MEETS.opened||[]).indexOf(m.id)<0;
    return `
    <div class="meetrow" onclick="api('open_meeting', ${esc(JSON.stringify(m.id))})">
      ${isNew?'<span class="newbar"></span>':''}
      <div class="meetrowTop">${m.pinned?'<span class="pinG" title="Pinned">★</span>':''}<span class="meetrowTitle">${esc(m.title||'Meeting')}</span>${isNew?'<span class="newTag">NEW</span>':''}${status}
        <span class="mrMeta">${esc((m.started_at||'').slice(0,10))} · ${fmtDur(m.duration_seconds)}</span></div>
      <div class="mrPrev">${esc(prev)}</div>
      <div class="mrFoot">${chips}${more}<span class="mrAttrs">${attrs}</span></div>
      <div class="mrActs">
        <button title="${m.pinned?'Unpin':'Pin'}" onclick="event.stopPropagation();pinMeeting(${esc(JSON.stringify(m.id))}, ${m.pinned?'false':'true'}, this)">${m.pinned?'★':'☆'}</button>
        <button title="Open" onclick="event.stopPropagation();api('open_meeting', ${esc(JSON.stringify(m.id))})">${SVG.play}</button>
        <button class="del" title="Delete meeting"
          onclick="event.stopPropagation();deleteMeeting(${esc(JSON.stringify(m.id))}, ${esc(JSON.stringify(m.title||'Meeting'))}, this)">✕</button>
      </div>
    </div>`;
  }
  const pinned=ms.filter(m=>m.pinned), rest=ms.filter(m=>!m.pinned);
  let html='';
  if(pinned.length){
    html+=`<div class="eyebrow" style="margin:14px 0 0">PINNED</div><div class="meetlist">`+
      pinned.map(rowHtml).join('')+`</div>`;
  }
  let last='', open=false;
  rest.forEach(m=>{
    const g=meetGroup(m);
    if(g!==last){
      if(open) html+='</div>';
      html+=`<div class="eyebrow" style="margin:14px 0 0">${g.toUpperCase()}</div><div class="meetlist">`;
      open=true; last=g;
    }
    html+=rowHtml(m);
  });
  if(open) html+='</div>';
  box.innerHTML=html;
}
function pinMeeting(id, on, btn){
  busyGuard(btn || ('pin:'+id), ()=>api('set_meeting_pinned', id, on)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok){
      (MEETS.meetings||[]).forEach(m=>{ if(m.id===id) m.pinned=on; });
      renderMeetRows();
    } else if(r && r.ok===false){ toast((r.error)||'Could not update the pin.', true); }
  });
}
// Deleting a meeting is irreversible (row + transcript + audio) and was ONE
// click away. Confirm first, same shape as deleteAccount (IDI-167).
function deleteMeeting(id, title, btn){
  if(!confirm('Delete “'+(title||'this meeting')+'”?\n\nIts transcript, notes and recording are permanently removed. This cannot be undone.')) return;
  busyGuard(btn || ('delmeet:'+id), ()=>api('delete_meeting', id)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok){ MEETS.meetings=(MEETS.meetings||[]).filter(m=>m.id!==id); renderActive(); }
    else { toast((r&&r.error)||'Could not delete the meeting.', true); }
  });
}
// ── Meeting detail (31e) — ported from the meeting panel (MER-46) ─────────────
// The panel is live-meeting-only now, so reading a meeting happens HERE, in the
// window that already holds the list, the search box and Ask-your-meetings. One
// panel could only ever hold one mode, which is why a past meeting used to fight
// the live screen and got yanked back to the ambient bar on every focus change.
let MVIEW='list';          // Meetings screen: 'list' | 'detail'
let MROW=null;             // the meeting being read
let MSUBNOTES=false;       // detail sub-page: the full AI notes
let HNVIEW='merged';       // hybrid notes view: yours | merged | ai (33i)
let MAUDIO_SRC=null, MPLAYING=-1, MDEL_ARMED=null, MNOTES_BUSY=false;
const CHIP_CLASS={self:'self'};
function chipClass(sid){
  if(CHIP_CLASS[sid]) return CHIP_CLASS[sid];
  const n=parseInt(String(sid).replace(/[^0-9]/g,''),10)||1;
  return 'c'+((n-1)%4);
}
// Hours-aware. NOT fmtT(): that one belongs to the history player and is m:ss
// only, which would print a 75-minute meeting as "75:00".
function fmtMT(secs){
  secs=Math.max(0,Math.floor(secs||0));
  const h=Math.floor(secs/3600), m=Math.floor((secs%3600)/60), s=secs%60;
  const mm=(h? String(m).padStart(2,'0') : String(m)), ss=String(s).padStart(2,'0');
  return h? (h+':'+mm+':'+ss) : (mm+':'+ss);
}
function relDate(iso){
  try{
    const d=new Date(iso), now=new Date();
    const days=Math.round((now-d)/86400000);
    const hm=d.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'});
    if(days<=0) return 'Today '+hm;
    if(days===1) return 'Yesterday '+hm;
    return d.toLocaleDateString([], {month:'short', day:'numeric'})+' '+hm;
  }catch(e){ return ''; }
}
// Entry point for the `openMeeting` native event (Python side: open_meeting).
function openMeetingDetail(row){
  if(!row || !row.id) return;
  MROW=row; MVIEW='detail'; MSUBNOTES=false;
  MAUDIO_SRC=null; MPLAYING=-1; MDEL_ARMED=null;
  if(ACTIVE!=='meetings') show('meetings');   // show() renders the screen itself
  else renderMeetings();
}
function meetBack(){
  MVIEW='list'; MROW=null; MSUBNOTES=false;
  const a=document.getElementById('sumAudio');
  if(a){ try{ a.pause(); }catch(e){} }
  renderMeetings();
  loadMeets();      // pick up edits made in the detail (title, pins, deletes)
}
function mtgTitle(v){
  if(!MROW) return;
  const t=(v||'').trim();
  if(!t || t===MROW.title) return;
  MROW.title=t;
  (MEETS.meetings||[]).forEach(m=>{ if(m.id===MROW.id) m.title=t; });
  api('set_meeting_title_by_id', MROW.id, t).then(r=>{
    if(r && r.ok===false) toast((r.error)||'Could not rename the meeting.', true);
  });
}
// The shell: header + card frames. Content goes in via fillMeetDetail() so a
// re-render (an edited action item, a renamed speaker) never rebuilds the DOM
// under an expanded transcript or a focused input.
function renderMeetDetail(){
  const box=document.getElementById('meetingsMain'); if(!box) return;
  box.innerHTML = `
    <div id="mtgDetail" class="show">
      <div class="sumHead">
        <div class="sumHeadL">
          <button class="mtgBack" onclick="meetBack()">&#8249; All meetings</button>
          <span class="eyebrow" id="sumEyebrow">Meeting</span>
          <input class="sumTitle" id="sumTitle" value="" spellcheck="false"
                 onchange="mtgTitle(this.value)"/>
          <div class="sumMeta" id="sumMeta"></div>
        </div>
        <div class="mact">
          <button class="btnS mini" id="expTxtBtn" title="Export transcript as .txt" onclick="sumExport('txt')">TXT</button>
          <button class="btnS mini" id="expMdBtn" title="Export as Markdown" onclick="sumExport('md')">MD</button>
          <button class="iconbtn" id="sumDelBtn" title="Delete meeting" onclick="sumDelete()">${SVG.trash}</button>
          <button class="iconbtn" title="Copy summary to clipboard" onclick="sumShare(this)">${SVG.copy}</button>
          <button class="iconbtn" title="Regenerate summary" onclick="sumRegen()">${SVG_REFRESH}</button>
        </div>
      </div>
      <div class="sumCards">
        <div class="card" id="sumCard">
          <div class="cardHead"><span class="eyebrow accd">Summary</span></div>
          <div id="sumBody"></div>
        </div>
        <div class="twoCol">
          <div class="card colL" id="hnCard">
            <div class="cardHead"><span class="eyebrow">Notes</span>
              <span class="hnTabs">
                <button class="hnTab" data-hnv="yours" onclick="hnView('yours')">Yours</button>
                <button class="hnTab on" data-hnv="merged" onclick="hnView('merged')">Merged</button>
                <button class="hnTab" data-hnv="ai" onclick="hnView('ai')">AI</button>
              </span>
              <span class="legend"><span class="lu"><i></i>Your notes</span><span class="la"><i></i>AI additions</span></span>
              <button class="btnS mini" style="margin-left:10px" title="Full AI notes of this meeting" onclick="openNotes()">Open notes &#8599;</button>
            </div>
            <div id="hnBody"></div>
          </div>
          <div class="colR">
            <div class="card"><div class="cardHead"><span class="eyebrow accd">Decisions</span></div><div id="decBody"></div></div>
            <div class="card" style="flex:1"><div class="cardHead"><span class="eyebrow accd">Action items</span></div><div id="aiBody"></div></div>
          </div>
        </div>
        <div class="card expandBox" id="marksBox"></div>
        <div class="card expandBox" id="txBox"></div>
      </div>
      <div class="teasers">
        <div class="teaser" onclick="toggleBox('marksBox', renderMarksBox)">${SVG.bolt}<span class="tl" id="marksTeaseL">Marked moments</span><span class="eyebrow">Expand</span></div>
        <div class="teaser" onclick="toggleBox('txBox', renderTxBox)">${SVG.search}<span class="tl" id="txTeaseL">Full transcript</span><span class="eyebrow">Expand</span></div>
      </div>
      <audio id="sumAudio"></audio>
    </div>`;
  fillMeetDetail();
}
function fillMeetDetail(){
  const ROW=MROW;
  if(MVIEW!=='detail' || MSUBNOTES || !ROW) return;
  if(!document.getElementById('sumBody')) return;
  document.getElementById('sumEyebrow').textContent='Meeting · '+relDate(ROW.started_at);
  const t=document.getElementById('sumTitle');
  if(document.activeElement!==t) t.value=ROW.title||'';
  const spk=ROW.speakers||{};
  const rec=ROW.recognized||{};
  document.getElementById('sumMeta').innerHTML=
    '<span class="mono">'+fmtMT(ROW.duration_seconds)+'</span>'+
    Object.keys(spk).map(function(sid){
      // 33d avatar variant: initial disc (self ringed) + fingerprint corner dot
      const nm=spk[sid]||sid, cls=chipClass(sid);
      const init=esc((nm||'?').trim().charAt(0).toUpperCase()||'?');
      return '<span class="avchip" title="Double-click to rename" ondblclick="sumRename(\''+esc(sid)+'\', this)">'+
        '<span class="av '+cls+'">'+init+'</span>'+
        (rec[sid]?'<span class="avFp" title="Voice recognized"></span>':'')+
        '<span class="avNm">'+esc(nm)+'</span></span>';
    }).join('')+
    Object.keys(rec).map(function(sid){
      const r=rec[sid]||{};
      return '<span class="fpBanner" style="flex-basis:100%">'+
        '<span class="zap"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L4 14h6l-1 8 9-12h-6z"/></svg></span>'+
        'Voice recognized from '+(r.meetings||1)+' previous meeting'+((r.meetings||1)>1?'s':'')+
        ' — auto-named <b>'+esc(r.name||'')+'</b><span class="k">FINGERPRINT</span></span>';
    }).join('')+
    // MER-31: audio was reaped by the retention policy — transcript/summary/
    // notes are all still intact, only playback is gone. Never an error state.
    (ROW.audio_expired ? '<span style="flex-basis:100%;font:400 11.5px \'Geist\';color:var(--mut)">'+
      'Audio expired — notes and transcript kept</span>' : '');
  const skel='<div class="skel" style="width:88%"></div><div class="skel" style="width:70%"></div>';
  const proc = ROW.status==='processing';
  // Summary card
  const sb=document.getElementById('sumBody');
  if(proc) sb.innerHTML=skel;
  else if(ROW.status==='failed')
    sb.innerHTML='<div class="sumErr">Summary generation failed — the transcript is saved. '+
      '<button class="btnS" style="margin-left:8px" onclick="sumRegen()">Retry</button></div>';
  else sb.innerHTML='<div class="sumBody">'+esc(ROW.summary||'No speech was detected in this meeting.')+'</div>';
  // Hybrid notes (33i — dot rows, ↳ AI additions, Yours/Merged/AI views)
  const hn=document.getElementById('hnBody');
  const hybrid=ROW.hybrid_notes||[];
  if(proc) hn.innerHTML=skel;
  else if(!hybrid.length){
    const pad=(ROW.scratchpad||'').split('\n').filter(function(l){return l.trim();});
    hn.innerHTML = '<div id="hnList" class="v-'+HNVIEW+'">'+(pad.length
      ? pad.map(function(l){return '<div class="hnRow"><div class="hnUser">'+esc(l)+'</div></div>';}).join('')
      : (ROW.notes_md
          ? '<div class="ntBody" style="margin:4px 0 0;font-size:12.5px">'+mdRender(String(ROW.notes_md).split('\n').slice(0,7).join('\n'))+'</div>'+
            '<button class="btnS mini" style="margin-top:10px" onclick="openNotes()">Read the full notes &#8599;</button>'
          : '<div class="hnRow noDot"><div class="hnAI" style="margin-top:0">No notes were taken — open the full AI notes instead.</div></div>'+
            '<button class="btnS mini" style="margin-top:10px" onclick="openNotes()">Generate meeting notes &#8599;</button>'))+'</div>';
  } else {
    hn.innerHTML='<div id="hnList" class="v-'+HNVIEW+'">'+hybrid.map(function(h,i){
      return '<div class="hnRow"><div class="hnUser">'+esc(h.user_line)+'</div>'+
        (h.ai_addition?'<div class="hnAI" id="hnA'+i+'">'+esc(h.ai_addition)+'</div>':'<div class="hnAI" id="hnA'+i+'" style="display:none"></div>')+
        '<button class="hnRegen" id="hnR'+i+'" title="Regenerate AI addition" onclick="hnRegen('+i+')">'+
        '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg></button>'+
        '</div>';
    }).join('')+'</div>';
  }
  // Decisions
  const dec=document.getElementById('decBody');
  const ds=ROW.decisions||[];
  dec.innerHTML = proc ? skel : (ds.length
    ? '<div class="dList">'+ds.map(function(d){return '<div class="dItem">'+esc(d)+'</div>';}).join('')+'</div>'
    : '<div class="hnAI" style="margin-top:8px">No explicit decisions found.</div>');
  // Action items (33c — checkbox rows in one card, faint dividers)
  const ai=document.getElementById('aiBody');
  const items=ROW.action_items||[];
  ai.innerHTML = proc ? skel : (items.length
    ? items.map(function(it, i){
        const sid=it.owner, name=sid&&spk[sid]?spk[sid]:(sid||null);
        const chip=name?'<span class="schip '+chipClass(sid)+'">'+esc(name)+'</span>'
                       :'<span class="schip unknown">Unknown</span>';
        return '<div class="aiRow'+(it.done?' done':'')+'" id="aiR'+i+'">'+
          '<button class="aiCb" role="checkbox" aria-checked="'+(it.done?'true':'false')+'"'+
          ' aria-label="'+esc(it.task)+'" onclick="aiToggle('+i+')">'+
          '<svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>'+
          '</button>'+chip+
          '<span class="aiTask" id="aiTx'+i+'" title="Click to edit" onclick="aiEdit('+i+')">'+esc(it.task)+'</span>'+
          (it.edited?'<span class="edTag">edited</span>':'')+
          '<span class="aiDue'+(it.due?' near':'')+'">'+(it.due?esc(String(it.due).toUpperCase()):'—')+'</span>'+
          '<button class="aiDel" title="Remove item (AI got it wrong?)" onclick="aiDel('+i+')">✕</button></div>';
      }).join('')
    : '<div class="hnAI" style="margin-top:8px">No action items found.</div>');
  // Teasers
  document.getElementById('marksTeaseL').textContent=(ROW.marked_moments||[]).length+' marked moments';
  document.getElementById('txTeaseL').textContent=(ROW.transcript||[]).length+' transcript segments';
}
// ── the full AI notes sub-page (markdown-rendered) ────────────────────────────
function mdRender(md){
  const lines=String(md||'').replace(/\r/g,'').split('\n');
  let html='', list=null, first=true;
  function closeList(){ if(list){ html+='</'+list+'>'; list=null; } }
  function inline(t){
    t=esc(t);
    t=t.replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
    t=t.replace(/`([^`]+)`/g,'<code>$1</code>');
    return t;
  }
  function isTableRow(s){ return /^\|.*\|\s*$/.test(s); }
  function isDivider(s){ return /^\|?[\s:|-]+\|[\s:|-]*$/.test(s) && s.indexOf('-')>=0; }
  function cells(s){ return s.replace(/^\||\|$/g,'').split('|').map(function(c){return c.trim();}); }
  for(let i=0;i<lines.length;i++){
    const ln=lines[i];
    const t=ln.trim();
    if(!t){ closeList(); continue; }
    let m;
    // Markdown table: header row, |---| divider, then body rows.
    if(isTableRow(t) && i+1<lines.length && isDivider(lines[i+1].trim())){
      closeList();
      const head=cells(t);
      html+='<div class="ntTableWrap"><table class="ntTable"><thead><tr>'+
        head.map(function(c){return '<th>'+inline(c)+'</th>';}).join('')+'</tr></thead><tbody>';
      i+=2;
      while(i<lines.length && isTableRow(lines[i].trim())){
        const row=cells(lines[i].trim());
        html+='<tr>'+head.map(function(_,ci){return '<td>'+inline(row[ci]||'')+'</td>';}).join('')+'</tr>';
        i++;
      }
      i--;
      html+='</tbody></table></div>';
      first=false;
      continue;
    }
    if((m=t.match(/^##\s+(.+)$/))){ closeList(); html+='<h2>'+inline(m[1])+'</h2>'; first=false; }
    else if((m=t.match(/^###\s+(.+)$/))){ closeList(); html+='<h3>'+inline(m[1])+'</h3>'; }
    else if((m=t.match(/^- \[( |x|X)\]\s+(.+)$/))){
      closeList();
      const done=m[1].toLowerCase()==='x';
      html+='<div class="ntTask'+(done?' done':'')+'"><span class="box">'+
        '<svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>'+
        '</span><span>'+inline(m[2])+'</span></div>';
    }
    else if((m=t.match(/^[-*]\s+(.+)$/))){
      if(list!=='ul'){ closeList(); html+='<ul>'; list='ul'; }
      html+='<li>'+inline(m[1])+'</li>';
    }
    else if((m=t.match(/^\d+[.)]\s+(.+)$/))){
      if(list!=='ol'){ closeList(); html+='<ol>'; list='ol'; }
      html+='<li>'+inline(m[1])+'</li>';
    }
    else {
      closeList();
      html+= first ? '<p class="ctx">'+inline(t)+'</p>' : '<p>'+inline(t)+'</p>';
      first=false;
    }
  }
  closeList();
  return html;
}
function renderMeetNotes(){
  const box=document.getElementById('meetingsMain'); if(!box || !MROW) return;
  box.innerHTML = `
    <div id="mtgDetail" class="show">
      <div id="mtgNotes" class="show">
        <div class="ntHead">
          <button class="mtgBack" onclick="notesBack()">&#8249; Summary</button>
          <span class="ntTitle" id="ntTitle">${esc((MROW.title||'Meeting')+' — notes')}</span>
          <button class="btnS mini" title="Copy notes as Markdown" onclick="notesCopy(this)">Copy</button>
          <button class="iconbtn" title="Regenerate notes" onclick="openNotes(true)">${SVG_REFRESH}</button>
        </div>
        <div class="ntSkel" id="ntSkel" style="display:none"><i style="width:38%"></i><i style="width:92%"></i><i style="width:85%"></i><i style="width:60%"></i><i style="width:88%"></i><i style="width:74%"></i></div>
        <div class="ntErr" id="ntErr" style="display:none"></div>
        <div class="ntBody" id="ntBody"></div>
      </div>
    </div>`;
}
function notesBack(){ MSUBNOTES=false; renderMeetings(); }
function openNotes(regen){
  if(!MROW || MNOTES_BUSY) return;
  const ROW=MROW;
  MSUBNOTES=true;
  renderMeetNotes();
  const body=document.getElementById('ntBody'), skel=document.getElementById('ntSkel'),
        err=document.getElementById('ntErr');
  if(!body) return;
  err.style.display='none';
  if(ROW.notes_md && !regen){
    body.innerHTML=mdRender(ROW.notes_md); skel.style.display='none';
    return;
  }
  body.innerHTML=''; skel.style.display='flex';
  MNOTES_BUSY=true;
  api('get_meeting_notes', ROW.id, !!regen).then(function(r){
    MNOTES_BUSY=false;
    const sk=document.getElementById('ntSkel');
    if(sk) sk.style.display='none';
    if(!MSUBNOTES || MROW!==ROW) return;
    const b=document.getElementById('ntBody'), e=document.getElementById('ntErr');
    if(!b) return;
    if(r && r.ok){
      ROW.notes_md=r.notes_md;
      b.innerHTML=mdRender(r.notes_md);
    } else {
      e.textContent=(r&&r.error)||'Could not generate notes — try again.';
      e.style.display='block';
    }
  });
}
function notesCopy(btn){
  if(MROW && MROW.notes_md){ api('copy_text', MROW.notes_md); flashOk(btn); }
}
function hnView(v){
  HNVIEW=v;
  const tabs=document.querySelectorAll('#mtgDetail .hnTab');
  for(let i=0;i<tabs.length;i++) tabs[i].className='hnTab'+(tabs[i].dataset.hnv===v?' on':'');
  const l=document.getElementById('hnList'); if(l) l.className='v-'+v;
}
function aiToggle(i){
  const items=MROW&&MROW.action_items||[];
  if(!items[i]) return;
  items[i].done=!items[i].done;
  const r=document.getElementById('aiR'+i);
  if(r){
    r.classList.toggle('done', !!items[i].done);
    const cb=r.querySelector('.aiCb');
    if(cb) cb.setAttribute('aria-checked', items[i].done?'true':'false');
  }
  api('set_action_item_done', MROW.id, i, !!items[i].done);
}
function hnRegen(i){
  const notes=MROW&&MROW.hybrid_notes||[];
  if(!notes[i]) return;
  const btn=document.getElementById('hnR'+i);
  if(btn){ if(btn.classList.contains('busy')) return; btn.classList.add('busy'); }
  api('regenerate_hybrid', MROW.id, i).then(function(r){
    const b=document.getElementById('hnR'+i);
    if(b) b.classList.remove('busy');
    if(r && r.ok){
      notes[i].ai_addition=r.ai_addition||'';
      fillMeetDetail();
    } else {
      const a=document.getElementById('hnA'+i);
      if(a){ a.style.display=''; a.textContent='Could not regenerate — try again.'; }
    }
  });
}
function aiEdit(i){
  const items=MROW&&MROW.action_items||[];
  if(!items[i]) return;
  const span=document.getElementById('aiTx'+i);
  if(!span || span.dataset.editing) return;
  span.dataset.editing='1';
  const old=items[i].task||'';
  const inp=document.createElement('input');
  inp.className='aiEditIn'; inp.value=old;
  span.replaceWith(inp); inp.focus(); inp.select();
  inp.addEventListener('keydown', function(ev){
    ev.stopPropagation();
    if(ev.key==='Enter'){ commit(inp.value.trim()); }
    if(ev.key==='Escape'){ commit(null); }
  });
  inp.addEventListener('blur', function(){ commit(inp.value.trim()); });
  function commit(v){
    if(v!=null && v!=='' && v!==old){
      items[i].task=v; items[i].edited=true;
      api('set_action_item_text', MROW.id, i, v);
    }
    fillMeetDetail();
  }
}
function aiDel(i){
  const items=MROW&&MROW.action_items||[];
  if(i<0||i>=items.length) return;
  items.splice(i,1);
  fillMeetDetail();
  api('delete_action_item', MROW.id, i);
}
function toggleBox(id, renderFn){
  const el=document.getElementById(id);
  if(!el) return;
  const show=!el.classList.contains('show');
  el.className='card expandBox'+(show?' show':'');
  if(show){
    renderFn();
    setTimeout(function(){ try{ el.scrollIntoView({behavior:'smooth', block:'start'}); }catch(e){} }, 40);
  }
}
function renderMarksBox(){
  const el=document.getElementById('marksBox');
  if(!el) return;
  const ms=MROW&&MROW.marked_moments||[];
  el.innerHTML='<div class="cardHead"><span class="eyebrow accd">Marked moments</span></div>'+
    (ms.length?ms.map(function(m,i){
      return '<div class="mmRow"><div class="mmHead">'+
        '<span class="star"><svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" stroke="none"><path d="m12 3 2.7 5.6 6.3.9-4.5 4.3 1 6.2-5.5-3-5.5 3 1-6.2L3 9.5l6.3-.9z"/></svg></span>'+
        '<span class="mmTs" onclick="playAt('+m.t+',-1)" title="Play from here">'+fmtMT(m.t)+'</span></div>'+
        '<div class="mmEx">'+esc(m.label||'Marked moment')+'</div>'+
        (m.note
          ?'<div class="mmNote"><div class="k">Your note</div><p id="mmN'+i+'" title="Click to edit" onclick="mmNote('+i+')">'+esc(m.note)+'</p></div>'
          :'<span class="mmNoteAdd" id="mmN'+i+'" onclick="mmNote('+i+')">+ Add note</span>')+
        '<div class="mmActs">'+
          '<button class="iconbtn" style="width:24px;height:22px" title="Jump to transcript" onclick="mmJump('+m.t+')">'+
            '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h6"/></svg></button>'+
          '<button class="iconbtn" style="width:24px;height:22px" title="Delete mark" onclick="mmDel('+i+')">✕</button>'+
        '</div></div>';
    }).join(''):'<div class="hnAI">No marks.</div>');
}
function mmJump(t){
  const box=document.getElementById('txBox');
  if(!box) return;
  if(!box.classList.contains('show')) toggleBox('txBox', renderTxBox);
  const tx=MROW&&MROW.transcript||[];
  let best=0;
  for(let i=0;i<tx.length;i++){ if((tx[i].t0||0)<=t) best=i; }
  setTimeout(function(){
    const el=document.getElementById('exU'+best);
    if(el){ el.scrollIntoView({behavior:'smooth', block:'center'}); markPlaying(best);
      setTimeout(function(){ markPlaying(-1); }, 2200); }
  }, 120);
}
function mmNote(i){
  const ms=MROW&&MROW.marked_moments||[];
  if(!ms[i]) return;
  const el=document.getElementById('mmN'+i);
  if(!el || el.dataset.editing) return;
  el.dataset.editing='1';
  const old=ms[i].note||'';
  const ta=document.createElement('textarea');
  ta.className='mmNoteIn'; ta.value=old;
  ta.placeholder='Why does this moment matter?';
  el.replaceWith(ta); ta.focus();
  ta.addEventListener('keydown', function(ev){
    ev.stopPropagation();
    if(ev.key==='Enter' && !ev.shiftKey){ ev.preventDefault(); commit(ta.value); }
    if(ev.key==='Escape'){ commit(null); }
  });
  ta.addEventListener('blur', function(){ commit(ta.value); });
  function commit(v){
    if(v!=null && v.trim()!==old){
      if(v.trim()) ms[i].note=v.trim(); else delete ms[i].note;
      api('set_mark_note', MROW.id, i, v.trim());
    }
    renderMarksBox();
  }
}
function mmDel(i){
  const ms=MROW&&MROW.marked_moments||[];
  if(i<0||i>=ms.length) return;
  ms.splice(i,1);
  renderMarksBox();
  const lb=document.getElementById('marksTeaseL');
  if(lb) lb.textContent=ms.length+' marked moments';
  api('delete_marked_moment', MROW.id, i);
}
function renderTxBox(){
  const el=document.getElementById('txBox');
  if(!el) return;
  const tx=MROW&&MROW.transcript||[], spk=MROW&&MROW.speakers||{};
  el.innerHTML='<div class="cardHead"><span class="eyebrow">Full transcript</span></div>'+
    (tx.length?tx.map(function(u,i){
      return '<div class="exUtt" id="exU'+i+'" onclick="playAt('+u.t0+','+i+')">'+
        '<span class="schip '+chipClass(u.speaker)+'" title="Double-click to rename" '+
          'ondblclick="event.stopPropagation();sumRename(\''+esc(u.speaker)+'\', this)">'+esc(spk[u.speaker]||u.speaker)+'</span> '+
        '<span class="mono" style="color:var(--dim);font-size:10px">'+fmtMT(u.t0)+'</span> '+
        '<span id="exTx'+i+'" style="font:400 11.5px Geist;color:var(--tx2)">'+esc(u.text)+'</span>'+
        (u.edited?'<span class="edTag">edited</span>':'')+
        '<span class="xr">'+
          '<button class="iconbtn" title="Copy line" onclick="event.stopPropagation();txCopy('+i+',this)">'+
            '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/></svg></button>'+
          '<button class="iconbtn" title="Edit text" onclick="event.stopPropagation();txEdit('+i+')">'+
            '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3 21 7l-13 13H4v-4z"/><path d="m14 6 4 4"/></svg></button>'+
        '</span></div>';
    }).join(''):'<div class="hnAI">Empty transcript.</div>');
}
function txCopy(i, btn){
  const tx=MROW&&MROW.transcript||[];
  if(!tx[i]) return;
  api('copy_text', tx[i].text||'');
  flashOk(btn);
}
function txEdit(i){
  const tx=MROW&&MROW.transcript||[];
  if(!tx[i]) return;
  const span=document.getElementById('exTx'+i);
  if(!span || span.dataset.editing) return;
  span.dataset.editing='1';
  const old=tx[i].text||'';
  const ta=document.createElement('textarea');
  ta.className='txEditIn'; ta.value=old;
  span.replaceWith(ta); ta.focus();
  ta.addEventListener('click', function(ev){ ev.stopPropagation(); });
  ta.addEventListener('keydown', function(ev){
    ev.stopPropagation();
    if(ev.key==='Enter' && (ev.metaKey||ev.ctrlKey)){ commit(ta.value.trim()); }
    if(ev.key==='Escape'){ commit(null); }
  });
  ta.addEventListener('blur', function(){ commit(ta.value.trim()); });
  function commit(v){
    if(v!=null && v!=='' && v!==old){
      tx[i].text=v; tx[i].edited=true;
      api('set_transcript_text', MROW.id, i, v);
    }
    renderTxBox();
  }
}
function playAt(secs, idx){
  // MER-31: expired audio is a clean no-op, not an error — the banner in
  // fillMeetDetail() already told the user why; clicking a transcript line
  // just does nothing rather than surfacing a fetch failure.
  if(MROW && MROW.audio_expired) return;
  const a=document.getElementById('sumAudio');
  if(!a) return;
  function go(){ try{ a.currentTime=Math.max(0,secs); a.play(); markPlaying(idx); }catch(e){} }
  if(MAUDIO_SRC){ go(); return; }
  api('get_meeting_audio', MROW.id).then(function(r){
    if(r && r.ok && r.src){ MAUDIO_SRC=r.src; a.src=r.src; a.addEventListener('canplay', go, {once:true}); }
    else if(r && r.ok===false) toast((r.error)||'Could not load the recording.', true);
  });
}
function markPlaying(idx){
  if(MPLAYING>=0){ const p=document.getElementById('exU'+MPLAYING); if(p) p.className='exUtt'; }
  MPLAYING=idx;
  if(idx>=0){ const el=document.getElementById('exU'+idx); if(el) el.className='exUtt playing'; }
}
function flashOk(btn){
  // clipboard/actions must LOOK like they worked (33f feedback lesson)
  if(!btn || btn.dataset.flash) return;
  btn.dataset.flash='1';
  const orig=btn.innerHTML;
  btn.innerHTML='<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
  btn.style.color='var(--on)';
  setTimeout(function(){ btn.innerHTML=orig; btn.style.color=''; delete btn.dataset.flash; }, 1400);
}
function sumShare(btn){
  const ROW=MROW;
  if(!ROW || ROW.status==='processing') return;
  const parts=['# '+(ROW.title||'Meeting'), '', ROW.summary||''];
  if((ROW.decisions||[]).length) parts.push('', 'Decisions:', ROW.decisions.map(function(d){return '- '+d;}).join('\n'));
  if((ROW.action_items||[]).length) parts.push('', 'Action items:',
    ROW.action_items.map(function(it){
      const n=it.owner&&ROW.speakers&&ROW.speakers[it.owner]?ROW.speakers[it.owner]+': ':'';
      return '- '+n+it.task;
    }).join('\n'));
  api('copy_text', parts.join('\n'));
  flashOk(btn);
}
function sumExport(fmt){
  if(!MROW) return;
  const btn=document.getElementById(fmt==='txt'?'expTxtBtn':'expMdBtn');
  const orig=btn.textContent;
  btn.textContent='…';
  api('export_meeting', MROW.id, fmt).then(function(r){
    if(r && r.ok){ btn.textContent='Saved ✓'; }
    else if(r && r.cancelled){ btn.textContent=orig; return; }
    else { btn.textContent='Failed'; }
    setTimeout(function(){ btn.textContent=orig; }, 1800);
  });
}
function sumDelete(){
  if(!MROW) return;
  const id=MROW.id;
  const btn=document.getElementById('sumDelBtn');
  if(MDEL_ARMED!==id){
    // first click arms; second click within 2.5s deletes
    MDEL_ARMED=id;
    btn.innerHTML='<span style="font:600 10.5px Geist;color:var(--rec-soft);padding:0 4px">Delete?</span>';
    btn.style.width='auto'; btn.style.background='var(--acc-softer)';
    setTimeout(function(){
      if(MDEL_ARMED===id){ MDEL_ARMED=null; resetDelBtn(); }
    }, 2500);
    return;
  }
  MDEL_ARMED=null;
  btn.innerHTML='<span style="font:600 10.5px Geist;color:var(--rec-soft);padding:0 4px">…</span>';
  api('delete_meeting', id).then(function(r){
    if(r && r.ok){
      MEETS.meetings=(MEETS.meetings||[]).filter(function(m){return m.id!==id;});
      meetBack();
    } else {
      resetDelBtn();
      toast((r&&r.error)||'Could not delete the meeting.', true);
    }
  });
}
function resetDelBtn(){
  const btn=document.getElementById('sumDelBtn');
  if(!btn) return;
  btn.innerHTML=SVG.trash;
  btn.style.width=''; btn.style.background='';
}
function sumRename(sid, el){
  const ROW=MROW;
  if(!ROW || !ROW.speakers) return;
  if(el.querySelector('input')) return;
  const old=ROW.speakers[sid]||sid;
  const target=el.querySelector('.avNm')||el;
  const inp=document.createElement('input');
  inp.value=old;
  inp.style.cssText='width:90px;font:600 11px Geist;color:var(--tx);background:none;'+
    'border:0;border-bottom:1.5px solid var(--acc);outline:none;caret-color:var(--acc)';
  target.replaceWith(inp); inp.focus(); inp.select();
  inp.addEventListener('click', function(ev){ ev.stopPropagation(); });
  inp.addEventListener('keydown', function(ev){
    ev.stopPropagation();
    if(ev.key==='Enter') commit(inp.value.trim());
    if(ev.key==='Escape') commit(null);
  });
  inp.addEventListener('blur', function(){ commit(inp.value.trim()); });
  function commit(v){
    if(v && v!==old){
      ROW.speakers[sid]=v;
      api('set_speaker_name', ROW.id, sid, v).then(function(r){
        if(r && r.ok && r.learned) toast('⚡ Voice print saved for '+v);
      });
    }
    fillMeetDetail();
    const tb=document.getElementById('txBox');
    if(tb && tb.classList.contains('show')) renderTxBox();
  }
}
function sumRegen(){
  if(!MROW || MROW.status==='processing') return;   // no double-fire while running
  MROW.status='processing'; fillMeetDetail();
  api('retry_meeting_summary', MROW.id);
}
// A meeting that finishes (or is edited elsewhere) while its detail is open must
// refresh IN PLACE — the list-level `meetingsUpdated` event is not enough.
function refreshOpenMeeting(id, deleted){
  if(MVIEW!=='detail' || !MROW) return;
  if(deleted && deleted===MROW.id){ meetBack(); return; }   // deleted from the list
  if(id && id!==MROW.id) return;
  api('get_meeting', MROW.id).then(function(r){
    if(MVIEW!=='detail' || !MROW) return;
    if(r && r.ok && r.meeting && r.meeting.id===MROW.id){
      MROW=r.meeting;
      if(MSUBNOTES) return;      // don't yank the notes page out from under them
      fillMeetDetail();
    } else if(r && r.error==='not found'){
      meetBack();                // gone (deleted on another device) — only this
    }                            // exact error, never a transient fetch failure
  });
}
// List column only — re-rendered on every keystroke so the search input keeps focus.
function noteMetaBits(n,q){
  const bits=[`<span>${esc(noteDateLabel(n.updated_at))}</span>`];
  const prog=chkProgress(n);
  if(prog) bits.push(`<span class="ncprog${prog.done===prog.total?' alldone':''}" title="Checklist progress">&#9745; ${prog.done}/${prog.total}</span>`);
  const audio=(n.audio_segments||[]).length;
  if(audio) bits.push(`<span class="ncaudio" title="${audio} recording${audio===1?'':'s'}">${SVG.mic}${audio>1?' '+audio:''}</span>`);
  return bits.join('');
}
function noteRowHtml(n,q){
  return `<div class="ncard${(SELN===n.id)?' active':''}" onclick="selectNote(${esc(JSON.stringify(n.id))})">
    <button class="npin${n.is_pinned?' on':''}" title="${n.is_pinned?'Unpin':'Pin'}" aria-label="${n.is_pinned?'Unpin note':'Pin note'}" aria-pressed="${n.is_pinned?'true':'false'}" onclick="event.stopPropagation();togglePin(${esc(JSON.stringify(n.id))})">${n.is_pinned?'★':'☆'}</button>
    <div class="nctitle">${hlText(n.title||'Untitled',q)}</div>
    <div class="ncprev">${hlText(noteSnippet(n,q),q)||'Empty note'}</div>
    <div class="ncmeta">${noteMetaBits(n,q)}</div></div>`;
}
function renderNoteList(){
  const flist=filteredNotes();
  const q=(NOTE_QUERY||'').trim();
  const cnt=document.getElementById('noteCount');
  if(cnt) cnt.textContent = q ? (flist.length+' result'+(flist.length===1?'':'s')+' · Enter asks AI') : '';
  const listEl=document.getElementById('noteList'); if(!listEl) return;
  if(!flist.length){
    if(q){
      listEl.innerHTML = `<div class="nempty">
        <div class="t">No notes match “${esc(q)}”</div>
        <div class="s">Start a note with this as its title, or ask AI across all your notes.</div>
        <button class="btn primary" style="width:auto" onclick="newNoteFromSearch()">Create “${esc(q.slice(0,40))}”</button>
        <span class="link" onclick="askNotes()">Ask AI</span>
        <span class="link" onclick="clearNoteSearch()">Clear search</span></div>`;
    } else if(realNotes().length){
      listEl.innerHTML = '<div class="empty">No notes match.</div>';
    } else {
      listEl.innerHTML = `<div class="nempty">
        <div class="disc">${SVG.mic}</div>
        <div class="t">Speak your first note</div>
        <div class="s">Dictate a thought and Verbal turns it into a clean, titled note — checklists included.</div>
        <button class="btn primary" style="width:auto" onclick="dictateNewNote()">Dictate a note</button>
        <span class="link" onclick="newNote()">or start typing</span></div>`;
    }
    return;
  }
  // Searching → flat ranked results. Browsing → PINNED, then date groups.
  let html='';
  if(q){
    html=flist.map(n=>noteRowHtml(n,q)).join('');
  } else {
    const pinned=flist.filter(n=>n.is_pinned), rest=flist.filter(n=>!n.is_pinned);
    if(pinned.length) html+='<div class="ngroup">Pinned</div>'+pinned.map(n=>noteRowHtml(n,'')).join('');
    let last='';
    rest.forEach(n=>{
      const g=noteGroup(n);
      if(g!==last){ html+=`<div class="ngroup">${g}</div>`; last=g; }
      html+=noteRowHtml(n,'');
    });
  }
  listEl.innerHTML=html;
}
function noteSearchInput(v){ NOTE_QUERY=v; if(NOTE_ASK && !NOTE_ASK.busy){ NOTE_ASK=null; renderNoteAsk(); } renderNoteList(); }
function clearNoteSearch(){ NOTE_QUERY=''; NOTE_ASK=null; renderNoteAsk(); const i=document.getElementById('noteSearch'); if(i) i.value=''; renderNoteList(); const j=document.getElementById('noteSearch'); if(j) j.focus(); }
function togglePin(id){
  const n=NOTES.find(x=>x.id===id); if(!n) return;
  const on=!n.is_pinned;
  n.is_pinned=on;
  renderNoteList();
  const pb=document.getElementById('notePinBtn');
  const cur=curNote();
  if(pb && cur && cur.id===id){ pb.className='fmtbtn'+(on?' pinned':''); pb.title=on?'Unpin note':'Pin note'; pb.textContent=on?'★':'☆'; }
  api('set_note_pinned', id, on).then(r=>{
    if(!(r&&r.ok)){ n.is_pinned=!on; renderNoteList(); toast('Could not update the pin.', true); }
  });
}
// ── Ask your notes (Notes v3) — Enter in the search box or the Ask link ──────
function renderNoteAsk(){
  const box=document.getElementById('noteAsk'); if(!box) return;
  if(!NOTE_ASK){ box.innerHTML=''; return; }
  if(NOTE_ASK.busy){
    box.innerHTML=`<div class="askNote"><div class="aq">${esc(NOTE_ASK.q)}</div><div class="aa" style="color:var(--mut)">Thinking…</div></div>`;
    return;
  }
  const src=(NOTE_ASK.sources||[]).length?`<div class="asrc">FROM: ${esc(NOTE_ASK.sources.join(' · '))}</div>`:'';
  box.innerHTML=`<div class="askNote" role="status">
    <button class="ax" aria-label="Dismiss answer" onclick="NOTE_ASK=null;renderNoteAsk()">✕</button>
    <div class="aq">${esc(NOTE_ASK.q)}</div>
    <div class="aa">${esc(NOTE_ASK.answer||'')}</div>${src}</div>`;
}
function askNotes(){
  const q=(NOTE_QUERY||'').trim();
  if(!q || (NOTE_ASK&&NOTE_ASK.busy)) return;
  NOTE_ASK={q:q, busy:true};
  renderNoteAsk();
  busyGuard('asknotes', ()=>api('ask_notes', q)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok) NOTE_ASK={q:q, answer:r.answer, sources:r.sources||[]};
    else NOTE_ASK={q:q, answer:(r&&r.error)||'Could not get an answer — try again.', sources:[]};
    renderNoteAsk();
  });
}

function noteMetaText(n, plainOverride){
  const plain = (plainOverride!=null) ? plainOverride : strippedNote(n);
  const w = words(plain);
  const segs=(n.audio_segments||[]).length;
  const parts=[];
  try{
    const d=new Date(n.created_at||n.updated_at);
    if(!isNaN(d.getTime())){
      const opts={month:'short', day:'numeric'};
      if(d.getFullYear()!==new Date().getFullYear()) opts.year='numeric';
      parts.push('Created '+d.toLocaleDateString([], opts));
    }
  }catch(e){}
  parts.push(w+' word'+(w===1?'':'s'));
  if(segs) parts.push(segs+' recording'+(segs===1?'':'s'));
  return parts.join(' · ').toUpperCase();
}
function noteEditorHtml(n){
  const hasRaw = (n.raw_content!=null) && String(n.raw_content).trim()!=='';
  const failed = hasRaw && !String(n.content||'').trim();   // dictated but no formatted content yet
  const origBtn = hasRaw
    ? `<button class="fmtbtn ftxt" title="${SHOW_ORIG?'Show formatted note':'Show original transcript'}" onclick="toggleShowOrig()">${SHOW_ORIG?'Formatted':'Original'}</button>` : '';
  // In the transcript view the raw text is EDITABLE (fix a misheard word), and
  // one button re-runs the AI over the corrected transcript (Notes v3 — the
  // Cleft edit-then-regenerate pattern).
  const refmtOrig = (SHOW_ORIG && hasRaw)
    ? `<button class="fmtbtn ftxt retry" title="Run AI formatting over this transcript" onclick="retryFormatting()">Reformat from transcript</button>` : '';
  const retryBtn = (failed && !SHOW_ORIG)
    ? `<button class="fmtbtn ftxt retry" title="Retry AI formatting" onclick="retryFormatting()">Retry formatting</button>` : '';
  const body = SHOW_ORIG
    ? `<div class="noteorig" id="noteOrig" contenteditable="plaintext-only" role="textbox" aria-multiline="true" aria-label="Original transcript (editable)" oninput="rawChanged()">${esc(n.raw_content||'')}</div>`
    : `<div class="notebody" id="noteBody" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Note content" data-ph="Tap Dictate to speak, or start typing…" oninput="noteChanged()"></div>`;
  const styleMenu = `
      <span class="nmenuwrap">
        <button class="fmtbtn" title="Reformat with AI" aria-haspopup="true" onclick="toggleNoteMenu(event,'noteStyleMenu')">&#10024;</button>
        <div class="nmenu" id="noteStyleMenu" hidden>
          <div class="nmhead">Reformat with AI</div>
          <button onclick="formatNoteStyled('structured')">Auto-structure</button>
          <button onclick="formatNoteStyled('prose')">Flowing prose</button>
          <button onclick="formatNoteStyled('transcript')">Clean transcript only</button>
        </div></span>`;
  const moreMenu = `
      <span class="nmenuwrap">
        <button class="fmtbtn" title="More actions" aria-haspopup="true" onclick="toggleNoteMenu(event,'noteMoreMenu')">${SVG.dots}</button>
        <div class="nmenu" id="noteMoreMenu" hidden>
          <button onclick="noteCopy('txt')">${SVG.copy}Copy as text</button>
          <button onclick="noteCopy('md')">${SVG.copy}Copy as Markdown</button>
          <button onclick="noteExport('md')">Export as .md…</button>
          <button onclick="noteExport('txt')">Export as .txt…</button>
          <div class="nmsep"></div>
          <button class="danger" onclick="delNote(null)">${SVG.trash}Delete note</button>
        </div></span>`;
  return `
      <input class="edtitle" id="noteTitle" value="${esc(n.title||'')}" placeholder="Untitled note" aria-label="Note title" oninput="noteChanged()"/>
      <div class="notemeta" id="noteMeta">${esc(noteMetaText(n))}</div>
      ${noteSegBar(n)}
      <div class="notetoolbar">
        <button class="fmtbtn" title="Bold" onmousedown="fmt(event,'bold')"><b>B</b></button>
        <button class="fmtbtn" title="Italic" onmousedown="fmt(event,'italic')"><i>I</i></button>
        <button class="fmtbtn" title="Underline" onmousedown="fmt(event,'underline')"><u>U</u></button>
        <span class="fmtsep"></span>
        <button class="fmtbtn" title="Bullet list" onmousedown="fmt(event,'insertUnorderedList')">&bull;</button>
        ${styleMenu}
        ${origBtn}${refmtOrig}${retryBtn}
        <button class="fmtbtn${n.is_pinned?' pinned':''}" id="notePinBtn" title="${n.is_pinned?'Unpin note':'Pin note'}" aria-pressed="${n.is_pinned?'true':'false'}" onclick="togglePin(${esc(JSON.stringify(n.id))})">${n.is_pinned?'★':'☆'}</button>
        ${moreMenu}
        <button class="dictate" id="dictateBtn" onclick="toggleDictate()">${SVG.mic}Dictate</button>
        <span class="notesave" id="noteSaveState"></span>
      </div>
      ${body}`;
}
// Close any open note menu on an outside click (registered ONCE — this script
// runs a single time; the open buttons stopPropagation so they don't self-close).
document.addEventListener('click', ()=>{
  document.querySelectorAll('.nmenu').forEach(m=>{ if(!m.hidden) m.hidden=true; });
});
function toggleNoteMenu(ev, id){
  ev.stopPropagation();
  const m=document.getElementById(id); if(!m) return;
  const was=m.hidden;
  document.querySelectorAll('.nmenu').forEach(x=>{ x.hidden=true; });
  m.hidden=!was;
}
// Per-segment playback control at the top of a note (Feature 4). No control at all
// when the note has no audio segments (Decision 6).
function noteSegBar(n){
  const segs=(n.audio_segments||[]).filter(s=>s&&s.id);
  if(!segs.length) return '';
  const rows=segs.map((s,i)=>{
    const t=(s.created_at||'').slice(11,16);
    const lbl='Play recording'+(t?(' from '+t):(' '+(i+1)));
    return `<button class="segbtn" data-id="${esc(s.id)}" aria-label="${esc(lbl)}" onclick="noteSegPlay(this)"><span class="segic">${SVG.play}</span><span>${esc(lbl)}</span></button>`;
  }).join('');
  return `<div class="segbar" role="group" aria-label="Note recordings">${rows}</div>`;
}
let _noteAudio=null;
function _noteAudioEl(){
  let a=document.getElementById('noteAudio');
  if(!a){ a=document.createElement('audio'); a.id='noteAudio'; document.body.appendChild(a);
    a.addEventListener('play',updateSegIcons); a.addEventListener('pause',updateSegIcons); a.addEventListener('ended',updateSegIcons); }
  return a;
}
function updateSegIcons(){
  const a=document.getElementById('noteAudio');
  document.querySelectorAll('.segbtn').forEach(b=>{
    const playing = a && a.src && !a.paused && b.getAttribute('data-id')===NOTE_SEG_ID;
    const ic=b.querySelector('.segic'); if(ic) ic.innerHTML = playing?SVG_PAUSE:SVG.play;
  });
}
function noteSegPlay(btn){
  const id=btn.getAttribute('data-id'); if(!id) return;
  const a=_noteAudioEl();
  if(NOTE_SEG_ID===id && a.src){ if(a.paused) a.play().catch(()=>{}); else a.pause(); updateSegIcons(); return; }
  NOTE_SEG_ID=id; try{a.pause();}catch(e){}
  api('get_audio', id).then(r=>{
    if(NOTE_SEG_ID!==id) return;
    if(r&&r.ok&&r.data_uri){ a.src=r.data_uri; a.load(); a.play().catch(()=>{}); }
    else setSaveState('No audio');
    updateSegIcons();
  });
  updateSegIcons();
}
function stopNoteAudio(){ const a=document.getElementById('noteAudio'); if(a){ try{a.pause();}catch(e){} } NOTE_SEG_ID=null; }

function selectNote(id){ flushNoteSave(); flushRawSave(); stopNoteAudio(); SELN=id; NOTE_REC=false; SHOW_ORIG=false; renderNotes(); }
function newNote(title){
  flushNoteSave(); flushRawSave(); stopNoteAudio(); NOTE_QUERY=''; NOTE_ASK=null; SHOW_ORIG=false;
  return api('save_note', {title:(typeof title==='string')?title:'', content:''}).then(r=>{
    if(r&&r.ok){ NOTES=r.notes||NOTES; SELN=r.id||SELN; renderNotes();
      const b=document.getElementById('noteBody'); if(b) b.focus(); }
    return r;
  });
}
// Sub-second voice capture (Notes v3): ONE click from "I have a thought" to a
// recording note — create, select, start dictating.
function dictateNewNote(){
  newNote('').then(r=>{
    if(r&&r.ok&&!NOTE_REC) toggleDictate();
  });
}
// Empty search results offer "Create '<query>'" — the query becomes the title.
function newNoteFromSearch(){
  const t=(NOTE_QUERY||'').trim().slice(0,80);
  newNote(t);
}
function toggleShowOrig(){ flushNoteSave(); flushRawSave(); SHOW_ORIG=!SHOW_ORIG; renderNotes(); }
// ── editable original transcript (Notes v3) ──────────────────────────────────
// Typing in the transcript view persists raw_content (debounced) with
// no_cleanup so a format-failed note can never fire a surprise LLM call.
function rawChanged(){
  const n=curNote(); const o=document.getElementById('noteOrig');
  if(!n||!o) return;
  n.raw_content=o.innerText;
  setSaveState('Saving…');
  if(_rawTimer) clearTimeout(_rawTimer);
  _rawTimer=setTimeout(()=>{ _rawTimer=null; saveRawNow(n); }, 700);
}
function saveRawNow(n){
  const payload={id:n.id, title:n.title||'', content:n.content||'',
                 audio_segments:n.audio_segments||[], no_cleanup:true,
                 raw_content:n.raw_content!=null?n.raw_content:''};
  api('save_note', payload).then(r=>{
    if(r&&r.ok){ if(r.notes) NOTES=r.notes; setSaveState('Saved'); }
    else setSaveState('');
  });
}
function flushRawSave(){
  if(_rawTimer){ clearTimeout(_rawTimer); _rawTimer=null;
    const n=curNote(); if(n) saveRawNow(n); }
}
function fmt(ev, cmd){ ev.preventDefault(); if(SHOW_ORIG) return; const b=document.getElementById('noteBody'); if(b) b.focus(); document.execCommand(cmd,false,null); noteChanged(); }

// Interactive checklist checkbox (Decision 8): toggles the item and persists.
function toggleChk(ev, el){
  ev.preventDefault(); ev.stopPropagation();
  const on = el.getAttribute('data-checked')!=='1';
  el.setAttribute('data-checked', on?'1':'0');
  el.setAttribute('aria-checked', on?'true':'false');
  el.classList.toggle('on', on);
  el.textContent = on?'☑':'☐';
  const li=el.closest('li'); if(li) li.classList.toggle('done', on);
  noteChanged();
}
function chkKey(ev, el){ if(ev.key===' '||ev.key==='Enter'){ toggleChk(ev, el); } }

function noteChanged(){
  if(SHOW_ORIG) return;
  setSaveState('Saving…');
  // Live word count in the editor meta line.
  const n=curNote(), m=document.getElementById('noteMeta'), b=document.getElementById('noteBody');
  if(n&&m&&b) m.textContent=noteMetaText(n, b.innerText);
  if(_noteTimer) clearTimeout(_noteTimer);
  _noteTimer=setTimeout(saveCurrentNote, 700);
}
function setSaveState(s){ const el=document.getElementById('noteSaveState'); if(el) el.textContent=s; }
function saveCurrentNote(){
  _noteTimer=null;
  const n=curNote(); if(!n) return;
  const t=document.getElementById('noteTitle'), b=document.getElementById('noteBody');
  if(!t||!b) return;   // no editable body (e.g. viewing the original) — nothing to persist
  n.title=t.value; n.content=b.innerHTML;
  const payload={id:n.id, title:n.title, content:n.content};
  if(n.raw_content!=null) payload.raw_content=n.raw_content;
  if(n.audio_segments&&n.audio_segments.length) payload.audio_segments=n.audio_segments;
  api('save_note', payload).then(r=>{
    if(r&&r.ok){ if(r.id) n.id=r.id; if(r.notes) NOTES=r.notes; setSaveState('Saved'); updateListCard(n); }
    else setSaveState('');
  });
}
function flushNoteSave(){ if(_noteTimer){ clearTimeout(_noteTimer); _noteTimer=null; saveCurrentNote(); } }
function updateListCard(n){
  const card=document.querySelector('#notesMain .ncard.active'); if(!card) return;
  const t=card.querySelector('.nctitle'), p=card.querySelector('.ncprev'), m=card.querySelector('.ncmeta');
  if(t) t.textContent=n.title||'Untitled';
  if(p) p.textContent=notePreview(n)||'Empty note';
  if(m) m.innerHTML=noteMetaBits(n,'');
}
function delNote(btn){
  const n=curNote(); if(!n) return;
  if(!confirm('Delete “'+(n.title||'Untitled')+'”?\n\nThe note and its linked recordings are permanently removed. This cannot be undone.')) return;
  if(_noteTimer){ clearTimeout(_noteTimer); _noteTimer=null; }
  if(_rawTimer){ clearTimeout(_rawTimer); _rawTimer=null; }
  stopNoteAudio();
  busyGuard(btn || ('delnote:'+n.id), ()=>api('delete_note', n.id)).then(r=>{
    if(r && r.busy) return;
    if(!(r&&r.ok)){ alert((r&&r.error)||"Couldn't delete the note — please try again."); return; }
    NOTES=r.notes||NOTES.filter(x=>x.id!==n.id); SELN=null; SHOW_ORIG=false; renderNotes(); });
}

function updateDictateBtn(){
  const b=document.getElementById('dictateBtn'); if(!b) return;
  b.className='dictate'+(NOTE_REC?' rec':'');
  b.innerHTML = NOTE_REC ? '<span class="pulse"></span>Stop' : SVG.mic+'Dictate';
}
// Key-guarded, not element-guarded: updateDictateBtn() rewrites the button's
// contents on every state flip, so a flag parked on the node would be lost —
// and a double-click on Dictate used to fire two start/stop calls (IDI-167).
function toggleDictate(){
  const n=curNote();
  if(NOTE_REC){
    NOTE_REC=false; updateDictateBtn(); setSaveState('Transcribing…');
    busyGuard('note_dictate', ()=>api('note_dictate_stop', n?n.id:null)).then(r=>{
      if(r && r.busy) return;
      if(!(r&&r.ok)){ setSaveState('Mic error'); return; }
      if(!(r.text||'').trim() && !(r.raw_text||'').trim()){
        setSaveState('No speech');
        if(r.segment && n){ n.audio_segments=(n.audio_segments||[]).concat([r.segment]); renderNotes(); }
        return;
      }
      onDictation(r);
    });
  } else {
    busyGuard('note_dictate', ()=>api('note_dictate_start')).then(r=>{
      if(r && r.busy) return;
      if(r&&r.ok){ NOTE_REC=true; updateDictateBtn(); setSaveState('Listening…'); }
      else setSaveState((r&&r.error==='busy')?'Busy':'Mic error');
    });
  }
}
// A dictated segment arrived. Store both raw + cleaned (Decision 1), union the audio
// segment (Feature 4). On the FIRST dictation into an empty note we save with empty
// content so the server runs cleanup ONCE (title + structure, Decision 2); further
// dictation just appends the already-cleaned chunk without re-formatting.
function onDictation(r){
  const n=curNote(); if(!n) return;
  const rawSeg=((r.raw_text||r.text||'')).trim();
  const hadContent=!!String(n.content||'').trim();
  n.raw_content=((n.raw_content?n.raw_content+'\n':'')+rawSeg).trim();
  if(r.segment){ n.audio_segments=(n.audio_segments||[]).concat([r.segment]); }
  if(!hadContent){
    setSaveState('Formatting…'); SHOW_ORIG=false;
    api('save_note', {id:n.id, title:n.title||'', content:'', raw_content:n.raw_content,
                      audio_segments:n.audio_segments||[], run_cleanup:true}).then(r2=>{
      if(r2&&r2.ok){ if(r2.notes) NOTES=r2.notes; if(r2.id) SELN=r2.id; renderNotes(); setSaveState('Saved'); }
      else setSaveState('');
    });
  } else {
    const b=document.getElementById('noteBody');
    if(b){ b.focus();
      const sep=(b.innerText && !/\s$/.test(b.innerText))?' ':'';
      b.appendChild(document.createTextNode(sep+(r.text||rawSeg)+' '));
      const rng=document.createRange(); rng.selectNodeContents(b); rng.collapse(false);
      const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(rng);
    }
    // refresh the segment bar without wiping the freshly appended text
    const bar=document.querySelector('#notesMain .editor .segbar');
    const barHtml=noteSegBar(n);
    if(bar){ bar.outerHTML=barHtml; } else if(barHtml){ const tb=document.querySelector('#notesMain .notetoolbar'); if(tb) tb.insertAdjacentHTML('beforebegin', barHtml); }
    updateSegIcons();
    noteChanged();
  }
}
function mdToHtml(md){
  const e=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const attr=s=>e(s).replace(/"/g,'&quot;');
  const inl=s=>{ s=e(s);
    s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
    s=s.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');
    s=s.replace(/(^|[^*])\*([^*\s][^*]*?)\*/g,'$1<i>$2</i>');
    s=s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'$1');   // [text](url) -> text (no brackets)
    return s; };
  const lines=(md||'').split(/\r?\n/); const out=[]; let list=null, inCode=false;
  const closeList=()=>{ if(list){ out.push('</'+list+'>'); list=null; } };
  for(const ln of lines){
    if(/^\s*```/.test(ln)){ if(inCode){out.push('</pre>');inCode=false;} else {closeList();out.push('<pre>');inCode=true;} continue; }
    if(inCode){ out.push(e(ln)); continue; }
    let m;
    if(m=ln.match(/^\s*[-*]\s+\[( |x|X)\]\s+(.*)/)){ if(list!=='ul'){closeList();out.push('<ul class="chk">');list='ul';}
      const on=m[1].toLowerCase()==='x'; const lbl=attr(m[2].replace(/[*`]/g,''));
      out.push('<li'+(on?' class="done"':'')+'><span class="chkbox'+(on?' on':'')+'" role="checkbox" aria-checked="'+(on?'true':'false')+'" aria-label="'+lbl+'" tabindex="0" contenteditable="false" data-checked="'+(on?'1':'0')+'" onclick="toggleChk(event,this)" onkeydown="chkKey(event,this)">'+(on?'☑':'☐')+'</span> <span class="chktext">'+inl(m[2])+'</span></li>'); continue; }
    if(m=ln.match(/^\s*[-*]\s+(.*)/)){ if(list!=='ul'){closeList();out.push('<ul>');list='ul';} out.push('<li>'+inl(m[1])+'</li>'); continue; }
    if(m=ln.match(/^\s*\d+\.\s+(.*)/)){ if(list!=='ol'){closeList();out.push('<ol>');list='ol';} out.push('<li>'+inl(m[1])+'</li>'); continue; }
    closeList();
    if(m=ln.match(/^(#{1,6})\s+(.*)/)){ const lv=Math.min(m[1].length,3)+2; out.push('<h'+lv+'>'+inl(m[2])+'</h'+lv+'>'); continue; }
    out.push(ln.trim()===''?'<br>':'<div>'+inl(ln)+'</div>');
  }
  if(inCode) out.push('</pre>'); closeList();
  return out.join('');
}
// Explicit Reformat with a named style (Notes v3, replaces the bare ✨ button) —
// Decision 2 still holds: an LLM call happens ONLY on this explicit pick.
// Source: the raw transcript when one exists (the true source — a restyle
// should not compound earlier formatting), else the visible text.
function formatNoteStyled(style){
  const n=curNote(); if(!n) return;
  let source='';
  if((n.raw_content!=null) && String(n.raw_content).trim()!=='') source=String(n.raw_content);
  else { const b=document.getElementById('noteBody'); source=b?b.innerText:strippedNote(n); }
  if(!source.trim()) return;
  setSaveState('Formatting…');
  busyGuard('notefmt', ()=>api('format_note_with_ai', source, style||'structured')).then(r=>{
    if(r&&r.busy) return;
    if(r&&r.ok&&r.content){
      SHOW_ORIG=false;
      // Store MARKDOWN, not rendered HTML — mobile renders markdown natively,
      // and noteBodyHtml() converts for this editor anyway.
      n.content=r.content;
      if(r.title && !String(n.title||'').trim()) n.title=r.title;
      const payload={id:n.id, title:n.title||'', content:n.content,
                     audio_segments:n.audio_segments||[], no_cleanup:true};
      if(n.raw_content!=null) payload.raw_content=n.raw_content;
      api('save_note', payload).then(r2=>{
        if(r2&&r2.ok&&r2.notes) NOTES=r2.notes;
        renderNotes(); setSaveState('Saved');
      });
    } else setSaveState((r&&r.error)||'Format failed');
  });
}
// Retry formatting after a failed/absent cleanup (Decision 6), and "Reformat
// from transcript" in the editable-original view — both re-run the default
// style over raw_content and persist.
function retryFormatting(){
  const n=curNote(); if(!n || !String(n.raw_content||'').trim()) return;
  if(_rawTimer){ clearTimeout(_rawTimer); _rawTimer=null; }   // raw edits ride along below
  formatNoteStyled('structured');
}
// ── copy / export (Notes v3 — "export = trust") ───────────────────────────────
// The stored content is EITHER markdown (dictated/AI-formatted) or HTML (typed
// rich-text edits). htmlToMd walks the rendered DOM back to markdown so both
// forms export the same way.
function htmlToMd(html){
  const root=document.createElement('div'); root.innerHTML=html;
  const out=[];
  function inline(node){
    let s='';
    node.childNodes.forEach(ch=>{
      if(ch.nodeType===3){ s+=ch.textContent; return; }
      if(ch.nodeType!==1){ return; }
      const tag=ch.tagName.toLowerCase();
      if(tag==='b'||tag==='strong') s+='**'+inline(ch)+'**';
      else if(tag==='i'||tag==='em') s+='*'+inline(ch)+'*';
      else if(tag==='code') s+='`'+inline(ch)+'`';
      else if(tag==='br') s+='\n';
      else s+=inline(ch);
    });
    return s;
  }
  function block(node){
    node.childNodes.forEach(ch=>{
      if(ch.nodeType===3){ const t=ch.textContent.trim(); if(t) out.push(t); return; }
      if(ch.nodeType!==1){ return; }
      const tag=ch.tagName.toLowerCase();
      if(tag==='h3') out.push('# '+inline(ch).trim());
      else if(tag==='h4') out.push('## '+inline(ch).trim());
      else if(tag==='h5'||tag==='h6') out.push('### '+inline(ch).trim());
      else if(tag==='pre') out.push('```\n'+ch.innerText.replace(/\n+$/,'')+'\n```');
      else if(tag==='ul'||tag==='ol'){
        let i=1;
        ch.querySelectorAll(':scope > li').forEach(li=>{
          const box=li.querySelector('.chkbox');
          if(box){
            const on=box.getAttribute('data-checked')==='1';
            const txt=li.querySelector('.chktext');
            out.push('- ['+(on?'x':' ')+'] '+inline(txt||li).trim());
          }
          else if(tag==='ol') out.push((i++)+'. '+inline(li).trim());
          else out.push('- '+inline(li).trim());
        });
      }
      else if(tag==='div'||tag==='p') out.push(inline(ch).trim());
      else if(tag==='br') out.push('');
      else { const s=inline(ch).trim(); if(s) out.push(s); }
    });
  }
  block(root);
  return out.join('\n').replace(/\n{3,}/g,'\n\n').trim();
}
function noteAsMarkdown(n){
  const c=n.content||'';
  const body=isHtmlContent(c) ? htmlToMd(c) : c.trim();
  const title=(n.title||'').trim();
  return (title?('# '+title+'\n\n'):'')+body+'\n';
}
function noteAsText(n){
  const d=document.createElement('div'); d.innerHTML=noteBodyHtml(n);
  const title=(n.title||'').trim();
  const body=(d.innerText||'').replace(/☑|☐/g, m=>m==='☑'?'[x]':'[ ]').trim();
  return (title?title+'\n\n':'')+body+'\n';
}
function noteCopy(fmt){
  const n=curNote(); if(!n) return;
  api('copy_text', fmt==='md'?noteAsMarkdown(n):noteAsText(n));
  setSaveState('Copied');
  setTimeout(()=>setSaveState(''), 1400);
}
function noteExport(fmt){
  const n=curNote(); if(!n) return;
  const content=fmt==='md'?noteAsMarkdown(n):noteAsText(n);
  setSaveState('Exporting…');
  busyGuard('noteexp', ()=>api('export_note_text', n.title||'Note', content, fmt)).then(r=>{
    if(r&&r.busy) return;
    if(r&&r.ok) setSaveState('Saved to file');
    else if(r&&r.cancelled) setSaveState('');
    else setSaveState('Export failed');
    setTimeout(()=>setSaveState(''), 1800);
  });
}
function loadNotes(){ api('fetch_notes').then(r=>{ if(r&&r.ok){ NOTES=r.notes||r.data||[]; if(ACTIVE==='notes')renderNotes(); if(ACTIVE==='home')renderHome(); } }); }

function pairAreaHTML(){
  if(!PAIR.active) return '';
  if(PAIR.claimedBy){
    return '<div class="pairpanel"><div class="pairok">✓</div>'
      +'<div class="pairtitle">Paired with '+esc(PAIR.claimedBy)+'</div>'
      +'<div class="pairsub">That device now syncs with this account.</div>'
      +'<button class="btn primary" style="width:160px" onclick="stopPairing()">Done</button></div>';
  }
  if(!PAIR.svg){
    return '<div class="pairpanel"><div class="pairsub">Generating code…</div>'
      +'<button class="btn ghost" style="width:120px" onclick="stopPairing()">Cancel</button></div>';
  }
  return '<div class="pairpanel"><div class="qrwrap">'+PAIR.svg+'</div>'
    +'<div class="pairtitle">Scan to pair a device</div>'
    +'<div class="pairsub">Open Flume on your phone → Devices → Scan this code. '
    +'Expires in <span id="pairttl">'+PAIR.ttl+'</span>s.</div>'
    +'<button class="btn ghost" style="width:120px" onclick="stopPairing()">Cancel</button></div>';
}

// Every device rendered as a PHONE regardless of what it is (IDI-177) — a Mac
// in the list looked like an iPhone. Type comes from `device_type`, which the
// presence upsert already sets to the platform.
function deviceIcon(t){
  const k=String(t||'').toLowerCase();
  if(k==='ios'||k==='android'||k==='iphone'||k==='ipad') return SVG.phone;
  if(k==='mac'||k==='darwin'||k==='win'||k==='windows'||k==='linux') return SVG.laptop;
  return SVG.laptop;
}
// Supabase hands back "2026-07-21 20:14:09.554+00" — a space separator and a
// 2-digit offset. WebKit's Date.parse is strict and rejects both, so normalize
// to ISO first or every device reads "never seen".
function parseTs(iso){
  if(!iso) return 0;
  let s = String(iso).trim().replace(' ','T').replace(/([+-]\d\d)$/,'$1:00');
  const t = Date.parse(s);
  return isNaN(t) ? 0 : t;
}
function timeAgo(iso){
  const t = parseTs(iso);
  if(!t) return 'never seen';
  const sec = Math.max(0,(Date.now()-t)/1000);
  if(sec < 90) return 'seen moments ago';
  const m = Math.floor(sec/60);  if(m < 60) return 'seen '+m+(m===1?' min ago':' mins ago');
  const h = Math.floor(m/60);    if(h < 24) return 'seen '+h+(h===1?' hour ago':' hours ago');
  const d = Math.floor(h/24);    if(d < 7)  return 'seen '+d+(d===1?' day ago':' days ago');
  const w = Math.floor(d/7);     if(w < 5)  return 'seen '+w+(w===1?' week ago':' weeks ago');
  const mo = Math.floor(d/30);              return 'seen '+mo+(mo===1?' month ago':' months ago');
}
// `device_type` is the raw platform string. 'iphone' is a LEGACY value written by
// a pre-IDI-177 mobile build (current mobile writes Platform.OS === 'ios'); kept
// mapped so old rows still read as a real product name rather than 'Iphone'.
function deviceTypeLabel(t){
  const k = String(t||'').toLowerCase();
  if(k==='ios'||k==='iphone') return 'iPhone';
  if(k==='ipad') return 'iPad';
  if(k==='android') return 'Android';
  if(k==='win'||k==='windows') return 'Windows';
  if(k==='mac'||k==='darwin') return 'Mac';
  return k ? k.charAt(0).toUpperCase()+k.slice(1) : 'Device';
}
function deviceRow(d){
  return `<div class="dcard${d.online?'':' off'}"><div class="dtile">${deviceIcon(d.device_type)}</div>
      <div class="dinfo"><div class="dname">${esc(d.device_name||'Device')}</div>
      <div class="dmeta">${esc(deviceTypeLabel(d.device_type))} · ${d.online?'active now':esc(timeAgo(d.last_seen))}</div></div>
      <span class="statpill ${d.online?'on':'offl'}"><span class="pdot"></span>${d.online?'Online':'Offline'}</span>
      <button class="devrm" title="Remove from list"
        onclick='removeDevice(${JSON.stringify(d.device_id||"")}, this)'>${SVG.trash}</button></div>`;
}
function renderDevices(){
  const devs = (STATE&&STATE.devices)||[];
  // The list EXCLUDES this device (fetch_account_devices filters it out), so
  // every row here is removable — this device leaves the list by signing out.
  // PAIRED and ONLINE are different things and are grouped as such: paired ==
  // has a row on the account, online == heartbeat within PRESENCE_ONLINE_SEC.
  const online  = devs.filter(d=>d.online);
  const offline = devs.filter(d=>!d.online);
  const group = (label, on, rows, extra) => rows.length ? `<div class="dgroup">
      <div class="dgrouphead"><span class="ghdot${on?' on':''}"></span>${label}
        <span class="gcount">${rows.length}</span>${extra||''}</div>
      <div class="dcards">${rows.map(deviceRow).join('')}</div></div>` : '';
  const cleanBtn = offline.length
    ? `<button class="gclean" onclick="removeAllOffline(this)">Remove all offline</button>` : '';
  const cards = (group('Online now', true, online)
               + group('Paired, offline', false, offline, cleanBtn))
    || '<div class="empty">No other devices yet. Tap “Pair a device”.</div>';
  const pairErr = (!PAIR.active && PAIR.error)
    ? `<div class="pairsub" style="color:#f0b39a">${esc(PAIR.error)}</div>` : '';
  const pairBtn = PAIR.active ? '' :
    `${pairErr}<button class="btn primary" style="width:150px" onclick="startPairing()">${SVG.plus}Pair a device</button>`;
  const target = (STATE&&STATE.target_device_id)||'__all__';
  const opts = [{id:'__all__',name:'All devices',online:false}].concat(
    devs.map(d=>({id:d.device_id,name:d.device_name||'Device',online:!!d.online})));
  // A green dot on the live targets: picking a device that has been dark for
  // three weeks is almost never what you meant.
  const selector = devs.length ? `<div class="tgtwrap">
    <div class="tgtlabel">SEND MY TRANSCRIPTIONS TO</div>
    <div class="tgtpills">${opts.map(o=>`<button class="tgtpill${o.id===target?' on':''}" onclick='setTarget(${JSON.stringify(o.id)})'>${o.online?'<span class="tdot"></span>':''}${esc(o.name)}</button>`).join('')}</div>
  </div>` : '';
  const countLine = devs.length
    ? `${devs.length} paired · ${online.length} online now`
    : 'No other devices';
  document.getElementById('devicesMain').innerHTML = `
    <div class="mhead dhead"><div><div class="eyebrow">${countLine}</div><h1 class="title">Devices</h1></div>${pairBtn}</div>
    ${pairAreaHTML()}
    ${selector}
    ${cards}`;
}

// Bulk list-cleanup (manual by design — nothing auto-prunes, so a phone that is
// merely switched off never vanishes on its own). Same semantics as
// removeDevice: a list removal, not a revocation.
function removeAllOffline(btn){
  const devs = (STATE&&STATE.devices)||[];
  const n = devs.filter(d=>!d.online).length;
  if(!n) return;
  if(!confirm('Remove '+n+' offline device'+(n===1?'':'s')+' from this list? Each one reappears on its next heartbeat if it is still signed in.')) return;
  busyGuard(btn||'rmoffline', ()=>api('remove_offline_devices')).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ toast((r.error)||'Could not remove those devices.', true); return; }
    if(STATE) STATE.devices=(STATE.devices||[]).filter(d=>d.online);
    renderDevices();
    load();
  });
}

function setTarget(id){
  api('set_target_device', id).then(()=>{ if(STATE) STATE.target_device_id=id; renderDevices(); });
}

// IDI-177. Honest label: this deletes the `devices` row, it does not sign the
// other device out or revoke anything — it will reappear on its next heartbeat
// unless it has actually signed out.
function removeDevice(id, btn){
  if(!id) return;
  if(!confirm('Remove from list? The device keeps working until it signs out.')) return;
  busyGuard(btn || ('rmdev:'+id), ()=>api('remove_device', id)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ toast((r.error)||'Could not remove that device.', true); return; }
    if(STATE) STATE.devices=(STATE.devices||[]).filter(d=>d.device_id!==id);
    renderDevices();
    load();
  });
}

function clearPairTimers(){
  if(PAIR.pollTimer){ clearInterval(PAIR.pollTimer); PAIR.pollTimer=null; }
  if(PAIR.tickTimer){ clearInterval(PAIR.tickTimer); PAIR.tickTimer=null; }
}
function startPairing(){
  // Latch BEFORE the async call — the old pollTimer check was set only after
  // the RPC resolved, so a double-click created two rows and orphaned a
  // claimable token (IDI-157).
  if(PAIR.starting || PAIR.pollTimer) return;
  PAIR.starting=true;
  PAIR.active=true; PAIR.claimedBy=null; PAIR.svg=''; PAIR.error=null;
  if(ACTIVE!=='devices'){ show('devices'); } else { renderDevices(); }
  api('start_pairing').then(r=>{
    PAIR.starting=false;
    if(!r || !r.ok){
      PAIR.svg=''; PAIR.active=false;
      PAIR.error=(r&&r.error)||'Could not start pairing — check your connection.';
      renderDevices(); return;
    }
    PAIR.token=r.token; PAIR.svg=r.svg; PAIR.ttl=r.expires_in||120;
    renderDevices();
    PAIR.tickTimer=setInterval(()=>{
      PAIR.ttl--; const el=document.getElementById('pairttl');
      if(el) el.textContent=Math.max(0,PAIR.ttl);
      if(PAIR.ttl<=0) stopPairing();
    }, 1000);
    PAIR.pollTimer=setInterval(()=>{
      if(!PAIR.token) return;
      api('check_pairing', PAIR.token).then(p=>{
        if(p && p.ok && p.claimed){ PAIR.claimedBy=p.device_name||'device'; clearPairTimers(); renderDevices(); load(); }
      });
    }, 2000);
  });
}
function stopPairing(){
  clearPairTimers();
  // Revoke the token SERVER-side too — a QR photographed before Cancel stayed
  // claimable for the rest of its TTL when this was local-only (IDI-157).
  if(PAIR.token && !PAIR.claimedBy) api('cancel_pairing', PAIR.token);
  PAIR={active:false, starting:false, error:null, token:null, svg:'', ttl:0, claimedBy:null, pollTimer:null, tickTimer:null};
  if(ACTIVE==='devices') renderDevices();
}

// ── Settings: grouped rail ──────────────────────────────────────
// This screen used to be TWELVE headed sections stacked in one column - every
// setting the app has, flat, with nothing more important than anything else. It
// renders ONE group at a time behind a rail now. Two things fall out of that:
// each pane fits the window, so the page-length scroll (and the restore logic
// that kept clamping it back to Meetings) is gone; and the late-resolving
// Meetings/Transform panes only mount when you open them, so their "Loading..."
// stubs can no longer shift content under the cursor.
//
// SETTINGS_GROUP lives at module scope on purpose: a state heartbeat rebuilds
// this screen every ~30s and must not throw you back to the first group.
const SETTINGS_GROUPS=[
  {id:'account',    label:'Account',     lede:'Who you are signed in as — and what leaving takes with it.'},
  {id:'models',     label:'Models',      lede:'Which engine hears you, and how many trips it takes to get the words back.'},
  {id:'dictionary', label:'Dictionary',  lede:'Teach Flume names and terms so they transcribe correctly.'},
  {id:'transform',  label:'Transform',   lede:''},
  {id:'notes',      label:'Notes',       lede:'Individual Notes enhancements. Each is on by default.'},
  {id:'meetings',   label:'Meetings',    lede:''},
  {id:'shortcuts',  label:'Shortcuts',   lede:'Start dictating, or reshape a selection, from anywhere.'},
  {id:'data',       label:'Data & sync', lede:'Where your dictations live, and how to clear them.'},
];
let SETTINGS_GROUP='account';

// ── Pipeline / model choices ────────────────────────────────────────────────
// The pipeline is NOT stored as its own key. It is derived from the two flags the
// dictation code actually reads (speed_mode, chained_mode), so there is one source
// of truth and a stale third copy can never disagree with what runs.
// Numbers in the copy are measured, not estimated — see context/03-features.md.
// Pipeline choices. One line each: what it does for you, and what you wait.
// Deliberately NOT a spec sheet — this is a settings row you glance at and pick.
const PIPELINES=[
  {id:'hybrid', label:'Hybrid',          desc:'Starts working while you talk.',       wait:'1.0s'},
  {id:'one',    label:'One round trip',  desc:'Best all-round. Same words, sooner.',  wait:'1.3s', tag:'recommended'},
  {id:'two',    label:'Two round trips', desc:'The older, slower route.',             wait:'1.9s'},
  {id:'old',    label:'Original',        desc:'How Flume used to sound.',             wait:''},
];

// Models. Vendor + one honest line + the wait. Everything else lives in the docs.
const ASR_MODELS=[
  {id:'auto',                   vendor:'Groq',       name:'Automatic',
   desc:'Fast and good at everything.', wait:'1.0s', tag:'recommended'},
  {id:'whisper-large-v3-turbo', vendor:'Groq',       name:'Whisper turbo',
   desc:'Always the fast one, any language.', wait:'1.0s'},
  {id:'whisper-large-v3',       vendor:'Groq',       name:'Whisper large',
   desc:'Better for languages other than English.', wait:'1.1s'},
  {id:'eleven-scribe-v1',       vendor:'ElevenLabs', name:'Scribe',
   desc:'Most accurate on your voice.', wait:'1.8s'},
  {id:'aai-universal-2',        vendor:'AssemblyAI', name:'Universal-2',
   desc:'Best with Urdu mixed into English.', wait:'5s'},
  {id:'aai-universal-3-5-pro',  vendor:'AssemblyAI', name:'Universal-3.5',
   desc:'Strong English. Struggles with Urdu.', wait:'5s'},
];

function pickRow(o, group, current, onchange){
  const on = current===o.id;
  return `<label class="prow${on?' on':''}">
    <input type="radio" name="${group}" value="${o.id}" ${on?'checked':''} onchange="${onchange}('${o.id}')">
    <span class="pr-mark" aria-hidden="true"></span>
    <span class="pr-tx"><span class="pr-h"><b>${esc(o.name||o.label)}</b>${o.tag?`<em>${esc(o.tag)}</em>`:''}</span>
      <i>${esc(o.desc)}</i></span>
    ${o.vendor?`<span class="pr-v">${esc(o.vendor)}</span>`:''}
    <span class="pr-n">${esc(o.wait||'')}</span>
  </label>`;
}

function currentPipeline(){
  const s=(STATE&&STATE.settings)||{};
  if(s.hybrid_mode) return 'hybrid';          // implies speed+chained for its short branch
  if(!s.speed_mode) return 'old';
  return s.chained_mode ? 'one' : 'two';
}
function currentAsrModel(){
  const s=(STATE&&STATE.settings)||{};
  const m=s.asr_model||'auto';
  // ASR_MODELS holds objects keyed by .id (it was [value,label] pairs before the
  // card rewrite; probing o[0] here silently pinned every card to "auto").
  return ASR_MODELS.some(o=>o.id===m) ? m : 'auto';
}
// (asrModelNote/ASR_NOTES removed with the dropdown — each model card carries its
// own note now, so the caveat is visible on every option instead of only the picked one.)

// The base payload save_settings expects. It overwrites keys/model/sync fields
// unconditionally, so a partial save must resend them or they get wiped.
//
// recording_mode is deliberately NOT sent. It is absent from STATE.settings, so any
// value here would be a guess — and save_settings only falls back to the stored value
// when the field is MISSING. Sending 'toggle' as a default would silently flip a
// hold-to-talk user to toggle every time they changed pipeline. Omitting it is what
// toggleNoteFlag already does, for the same reason.
function settingsBase(){
  const s=(STATE&&STATE.settings)||{};
  return {
    groq_api_keys:s.groq_api_keys||[], gemini_api_keys:s.gemini_api_keys||[],
    whisper_model:(STATE&&STATE.model)||'base',
    sync_enabled:!!s.sync_enabled, sync_user_id:s.sync_user_id||'',
    sync_device_name:s.sync_device_name||'',
  };
}

function setPipeline(id){
  // hybrid_mode is written on EVERY choice, not just when turning it on — otherwise
  // switching away from hybrid would leave it set and silently keep streaming.
  const flags = id==='old'    ? {speed_mode:false, chained_mode:false, hybrid_mode:false}
              : id==='two'    ? {speed_mode:true,  chained_mode:false, hybrid_mode:false}
              : id==='hybrid' ? {speed_mode:true,  chained_mode:true,  hybrid_mode:true}
              :                 {speed_mode:true,  chained_mode:true,  hybrid_mode:false};
  if(STATE&&STATE.settings) Object.assign(STATE.settings, flags);
  api('save_settings', Object.assign(settingsBase(), flags));
  renderSettings();
  const m=document.getElementById('pipeMsg');
  if(m){ const p=PIPELINES.find(x=>x.id===id);
         m.textContent='Saved — now using “'+(p?p.label:id)+'”. Takes effect on your next dictation.'; }
}

function setAsrModel(v){
  if(STATE&&STATE.settings) STATE.settings.asr_model=v;
  api('save_settings', Object.assign(settingsBase(), {asr_model:v}));
  renderSettings();
}

function setSettingsGroup(id){
  if(SETTINGS_GROUP===id) return;
  SETTINGS_GROUP=id;
  renderSettings();
  const p=document.getElementById('setPane');
  if(p) p.scrollTop=0;              // a new group always starts at the top
}

// Rail badges answer the question you opened Settings to ask, without opening
// anything. Only state we hold LOCALLY - a badge fed by a late fetch would read
// as fact while still being a guess.
function settingsBadge(id){
  try{
    const s=(STATE&&STATE.settings)||{};
    if(id==='dictionary') return DICT.vocabulary.length+' · '+DICT.replacements.length;
    if(id==='data')       return s.sync_enabled?'on':'off';
    if(id==='notes'){
      const keys=['notes_search_enabled','notes_autotitle_enabled',
                  'notes_structure_detection_enabled','notes_audio_linkage_enabled'];
      return keys.filter(k=>s[k]!==false).length+' of 4';
    }
  }catch(e){}
  return '';
}

function renderSettings(){
  if(window.__HK_WAIT) return;                       // hotkey capture in progress
  const pane=document.getElementById('setPane');
  const keepScroll=pane?pane.scrollTop:0;
  const shell=document.getElementById('settingsMain');
  if(!shell) return;
  shell.classList.add('setshell');
  const g=SETTINGS_GROUPS.find(x=>x.id===SETTINGS_GROUP)||SETTINGS_GROUPS[0];
  const rail=SETTINGS_GROUPS.map(x=>{
    const b=settingsBadge(x.id);
    return '<button class="sritem '+(x.id===g.id?'on':'')+'" '+
           'onclick="setSettingsGroup(\''+x.id+'\')" '+
           'aria-current="'+(x.id===g.id?'page':'false')+'">'+
           '<span>'+esc(x.label)+'</span>'+(b?'<em>'+esc(b)+'</em>':'')+'</button>';
  }).join('');
  shell.innerHTML = `
    <nav class="setrail" aria-label="Settings groups"><div class="srl">Settings</div>${rail}</nav>
    <div class="setpane" id="setPane">
      <div class="eyebrow">Settings</div><h1 class="title">${esc(g.label)}</h1>
      ${g.lede?`<p class="ssub setlede">${esc(g.lede)}</p>`:''}
      ${settingsPane(g.id)}
    </div>`;
  if(!DICT_LOADED){ DICT_LOADED=true; loadDict(); }
  if(!FT_LOADED){ FT_LOADED=true; loadFiletag(); }
  if(!AL_LOADED){ AL_LOADED=true; loadAutolearn(); }
  loadMeetSettings();
  // Fill the async panes from cache synchronously so the pane is full height
  // before scrollTop is restored (they no-op when their group isn't mounted).
  renderMeetSettings(); renderTfSettings(); fillHotkeyLabels();
  const p2=document.getElementById('setPane');
  if(p2 && keepScroll) p2.scrollTop=keepScroll;
}

function settingsPane(id){
  const s=(STATE&&STATE.settings)||{};
  const model=(STATE&&STATE.model)||'base';
  const u=STATE&&STATE.user;

  if(id==='account'){
    // A dead session keeps `user` populated, so Settings would otherwise show a
    // perfectly healthy account while Delete account 401s (IDI-166).
    const deadBar=(STATE&&STATE.session_dead)?`
      <div class="deadbar">
        <span class="dbtx">Session expired. You're still signed in locally, but syncing and account changes need a fresh sign-in.</span>
        <button class="dbbtn" onclick="reSignIn()">Sign in again</button>
      </div>`:'';
    if(!u) return `
      <div class="ssection">
        <div class="scard"><div class="ssub" style="margin:0 0 10px">Sign in to sync across your devices.</div>
          <button class="btn primary" style="width:180px" onclick="api('sign_in_google')">Sign in with Google</button></div></div>`;
    return `
      <div class="ssection">
        ${deadBar}
        <div class="scard row">
          <div class="acctav">${esc((u.name||u.email||'?').slice(0,1).toUpperCase())}</div>
          <div class="grow"><div class="sname">${esc(u.name||'Signed in')}</div>
            <div class="sdesc">${esc(u.email||'')}</div></div>
          <button class="btn ghost" onclick="api('sign_out_account')">Sign out</button>
        </div>
      </div>
      <div class="ssection"><h3>Danger zone</h3>
        <div class="scard row">
          <div class="grow"><div class="sname sdanger">Delete account</div>
            <div class="sdesc">Permanently erases your account and all cloud data. Cannot be undone.</div></div>
          <button id="deleteAcctBtn" class="btn ghost sdanger" onclick="deleteAccount()">Delete account</button>
        </div></div>`;
  }

  if(id==='models') return `
    <div class="ssection"><h3>Speed</h3>
      <div class="scard tight">${PIPELINES.map(p=>pickRow(p,'pipe',currentPipeline(),'setPipeline')).join('')}</div>
      <div class="ssub" id="pipeMsg" style="margin:8px 0 0"></div>
    </div>

    <div class="ssection"><h3>Transcription model</h3>
      <div class="scard tight">${ASR_MODELS.map(m=>pickRow(m,'asrm',currentAsrModel(),'setAsrModel')).join('')}</div>
    </div>

    <div class="ssection"><h3>Language</h3>
      <div class="scard">
        <div class="field"><label>SPOKEN LANGUAGE</label><select id="spokenLang" onchange="setSpokenLang(this.value)">
          ${(LANGS.options||[["en","English"]]).map(o=>`<option value="${o[0]}" ${LANGS.value===o[0]?'selected':''}>${o[1]}</option>`).join('')}
        </select></div>
        <div class="field"><label>OFFLINE MODEL</label><select id="model">${['tiny','base','small','medium'].map(m=>`<option ${model===m?'selected':''}>${m}</option>`).join('')}</select>
          <span class="ssub" style="margin:4px 0 0">Used only when you're offline.</span></div>
        <button class="btn primary" style="flex:none;width:130px" onclick="saveSettings()">Save</button>
      </div></div>
    <div class="ssection"><h3>Auto-learn from corrections</h3>
      <p class="ssub">When you fix a misheard word right after dictating, Flume offers to remember it (marked <span style="opacity:.75">✨</span> in the dictionary). Works best in native text fields.</p>
      <div class="scard">
        <div class="saverow"><button class="toggle alToggleBtn ${AL.enabled?'on':''}" id="alToggleSettings" onclick="toggleAutolearn()"></button><span style="font:500 13px Geist">Enable auto-learn</span></div>
      </div></div>
    <div class="ssection"><h3>File tagging <span class="ssub" style="display:inline;margin:0">(Cursor, Windsurf, VS Code, Antigravity, Kiro)</span></h3>
      <p class="ssub">When you dictate inside a supported IDE, spoken file names become <b>@name.ext</b> tags.</p>
      <div class="scard">
        <div class="saverow"><button class="toggle ftToggleBtn ${FT.enabled?'on':''}" id="ftToggleSettings" onclick="toggleFiletag()"></button><span style="font:500 13px Geist">Enable file tagging</span></div>
        <div class="ssub" style="margin:10px 0 0">${FT.seen_count||0} file${FT.seen_count===1?'':'s'} remembered.</div>
      </div></div>`;

  if(id==='dictionary') return `
    <div class="ssection">
      <div class="scard row">
        <div class="grow"><div class="sname">${DICT.vocabulary.length} words · ${DICT.replacements.length} rules</div>
          <div class="sdesc">Manage your vocabulary, replacement rules and snippets</div></div>
        <button class="btn primary" style="width:150px" onclick="show('dictionary')">Open dictionary</button>
      </div></div>`;

  if(id==='transform')  return `<div class="ssection" id="tfSettings"><p class="ssub">Loading…</p></div>`;
  if(id==='meetings')   return `<div class="ssection" id="meetSettings"><p class="ssub">Loading…</p></div>`;

  if(id==='notes') return `
    <div class="ssection nflags">
      <div class="scard">
        <div class="saverow"><button class="toggle ${s.notes_search_enabled!==false?'on':''}" aria-label="Search across notes" onclick="toggleNoteFlag('notes_search_enabled',this)"></button><span style="font:500 13px Geist">Search across notes</span></div>
        <div class="saverow"><button class="toggle ${s.notes_autotitle_enabled!==false?'on':''}" aria-label="Auto-title dictated notes" onclick="toggleNoteFlag('notes_autotitle_enabled',this)"></button><span style="font:500 13px Geist">Auto-title dictated notes</span></div>
        <div class="saverow"><button class="toggle ${s.notes_structure_detection_enabled!==false?'on':''}" aria-label="Detect lists and checklists" onclick="toggleNoteFlag('notes_structure_detection_enabled',this)"></button><span style="font:500 13px Geist">Detect lists &amp; checklists</span></div>
        <div class="saverow"><button class="toggle ${s.notes_audio_linkage_enabled!==false?'on':''}" aria-label="Link source recordings" onclick="toggleNoteFlag('notes_audio_linkage_enabled',this)"></button><span style="font:500 13px Geist">Link source recordings to notes</span></div>
      </div></div>`;

  if(id==='shortcuts') return `
    <div class="ssection">
      <div class="scard hotcard">
        <div class="hotrow"><span>Dictation (hold to talk, tap to keep recording)</span><span class="kbs"><kbd id="dictKeyLbl">…</kbd></span>
          <button class="btn ghost slim" id="dictKeyBtn"
            onclick="pickHotkey('dict')">Change</button></div>
        <div class="hotrow"><span>Transform selection</span><span class="kbs"><kbd>${PL_KEYS.MOD_KBD}</kbd> + <kbd id="tfKeyLbl">…</kbd></span>
          <button class="btn ghost slim" id="tfKeyBtn"
            onclick="pickHotkey('tf')">Change</button></div>
        <div class="ssub" id="hotkeyMsg" style="margin:8px 0 0"></div>
      </div></div>`;

  if(id==='data') return `
    <div class="ssection"><h3>Cross-device sync</h3><p class="ssub">Use the same Account ID on every device to link them.</p>
      <div class="scard">
        <div class="saverow" style="margin-bottom:14px"><button class="toggle ${s.sync_enabled?'on':''}" id="syncToggle" onclick="this.classList.toggle('on')"></button><span style="font:500 13px Geist">Enable sync</span></div>
        <div class="field"><label>ACCOUNT ID</label><input id="userId" value="${esc(s.sync_user_id||'')}"/></div>
        <div class="field"><label>DEVICE NAME</label><input id="devName" value="${esc(s.sync_device_name||'This Mac')}"/></div>
        <button class="btn primary" style="flex:none;width:130px" onclick="saveSettings()">Save sync</button>
      </div></div>
    <div class="ssection"><h3>History</h3><p class="ssub">Your dictations are kept on this device and, when sync is on, in your account.</p>
      <div class="scard row">
        <div class="grow"><div class="sname">Clear history</div>
          <div class="sdesc">Removes every transcription from this device. You'll then be asked whether to clear your other devices too.</div></div>
        <button id="clearHistBtn" class="btn ghost sdanger" onclick="clearHistory(this)">Clear history</button>
      </div></div>`;

  return '';
}

// ── 31g — MeetingsSettingsPane ────────────────────────────────────────────────
function loadMeetSettings(){
  api('get_meeting_settings').then(r=>{
    if(r && r.ok){ MSET=r; renderMeetSettings(); }
  });
  // Language options don't change between fetches. Fetching them again on
  // every renderSettings() + then calling renderSettings() inside the
  // resolve callback creates an infinite bounce: renderSettings resets
  // innerHTML → loadMeetSettings fires → language resolves → renderSettings
  // → repeat. That was the "flickering between Meetings and Transform"
  // glitch. Fetch once, and after that just patch the <select> in place.
  if(!LANGS_LOADED){
    LANGS_LOADED=true;
    api('get_spoken_language').then(r=>{
      if(r && r.ok){
        LANGS={value:r.value, options:r.options};
        patchSpokenLangSelect();
      } else {
        LANGS_LOADED=false;  // let a retry happen next open
      }
    });
  } else {
    patchSpokenLangSelect();
  }
  api('get_transform_settings').then(r=>{
    if(r && r.ok){ TSET=r.settings||{}; TSET._tfLabel=r.hotkey_label; TSET._dictLabel=r.dictation_label; renderTfSettings(); fillHotkeyLabels(); }
  });
}

function patchSpokenLangSelect(){
  // Update just the <select> element instead of rebuilding the whole
  // Settings pane — no innerHTML churn, no scroll jump, no flicker.
  const sel = document.getElementById('spokenLang');
  if(!sel || !LANGS || !LANGS.options) return;
  const opts = LANGS.options.map(o =>
    `<option value="${esc(o[0])}" ${LANGS.value===o[0]?'selected':''}>${esc(o[1])}</option>`
  ).join('');
  if(sel.innerHTML !== opts) sel.innerHTML = opts;
  sel.value = LANGS.value || sel.value;
}
function meetBadge(st){
  const cls = st==='granted'?'ready':(st==='denied'?'denied':'pending');
  const lbl = st==='granted'?'READY':(st==='denied'?'DENIED':'PENDING');
  return `<span class="mbadge ${cls}"><i></i>${lbl}</span>`;
}
function renderMeetSettings(){
  const box=document.getElementById('meetSettings');
  if(!box || !MSET) return;
  const s=MSET.settings||{}, p=MSET.perms||{};
  const tgl=(key,label,sub)=>`
    <div class="saverow"><button class="toggle ${s[key]?'on':''}" aria-label="${label}"
      onclick="toggleMeetSetting('${key}',this)"></button>
      <span style="font:500 13px Geist">${label}</span>
      ${sub?`<span class="ssub" style="display:inline;margin:0 0 0 6px">${sub}</span>`:''}</div>`;
  const dd=(key,opts,labels)=>`
    <select onchange="setMeetSetting('${key}', parseInt(this.value))" style="margin-left:auto">
      ${opts.map((o,i)=>`<option value="${o}" ${s[key]===o?'selected':''}>${labels[i]}</option>`).join('')}</select>`;
  const ddStr=(key,opts,labels)=>`
    <select onchange="setMeetSetting('${key}', this.value)" style="margin-left:auto">
      ${opts.map((o,i)=>`<option value="${o}" ${(s[key]||'en')===o?'selected':''}>${labels[i]}</option>`).join('')}</select>`;
  box.innerHTML = `
    <h3>Meetings</h3><p class="ssub">Capture a meeting's system audio + your mic, live-transcribe it, and get an AI summary. Meeting text is never sent to analytics — ever.</p>
    <div class="scard">
      <div class="saverow" style="justify-content:space-between"><span style="font:500 13px Geist">System audio permission</span>${meetBadge(p.system_audio)}</div>
      <div class="saverow" style="justify-content:space-between"><span style="font:500 13px Geist">Microphone permission</span>${meetBadge(p.microphone)}</div>
      ${tgl('meetings_enabled','Enable meetings')}
      ${tgl('meetings_hud_enabled','Floating HUD when tabbed away')}
      ${tgl('meetings_speaker_labels','Speaker labeling')}
      <div class="saverow"><span style="font:500 13px Geist">Meeting notes language</span>
        ${ddStr('meetings_notes_language',['en','auto'],['Always English','Same as meeting'])}</div>
      ${tgl('meetings_keep_audio','Keep audio files')}
      <div class="saverow"><span style="font:500 13px Geist">Auto-delete audio after</span>
        ${dd('meetings_keep_audio_days',[7,30,90,0],['7 days','30 days','90 days','Never'])}</div>
      <div class="saverow"><span style="font:500 13px Geist">Max meeting length</span>
        ${dd('meetings_max_minutes',[30,60,120,180,360,0],['30 min','1 h','2 h','3 h','6 h','No limit'])}</div>
      ${tgl('meetings_sync_enabled','Sync meetings to other devices')}
      <div class="ssub" style="margin:10px 0 0">${MSET.count||0} meeting${MSET.count===1?'':'s'} · ${Math.round((MSET.total_seconds||0)/60)} min captured</div>
    </div>`;
}
function toggleMeetSetting(key, el){
  el.classList.toggle('on');
  const val = el.classList.contains('on');
  if(MSET && MSET.settings) MSET.settings[key]=val;
  api('set_meeting_setting', key, val);
}
function setMeetSetting(key, val){
  if(MSET && MSET.settings) MSET.settings[key]=val;
  api('set_meeting_setting', key, val);
}
let TSET=null;
let LANGS={value:'en', options:[["auto","Auto-detect"],["en","English"]]};
// Fetch language options only once per session — they don't change between
// calls. Preventing the re-fetch is what fixes the Settings-page flicker
// (was: language resolve → renderSettings() → language resolve …).
let LANGS_LOADED=false;
function setSpokenLang(v){
  LANGS.value=v;
  api('set_spoken_language', v);
}
function renderTfSettings(){
  const box=document.getElementById('tfSettings');
  if(!box || !TSET) return;
  const tgl=(key,label,sub)=>`
    <div class="saverow"><button class="toggle ${TSET[key]?'on':''}" aria-label="${label}"
      onclick="toggleTfSetting('${key}',this)"></button>
      <span style="font:500 13px Geist">${label}</span>
      ${sub?`<span class="ssub" style="display:inline;margin:0 0 0 6px">${sub}</span>`:''}</div>`;
  box.innerHTML = `
    <h3>Transform</h3><p class="ssub">Reshape text with an instruction — end a dictation with “…so Flume, make this formal”, or select text anywhere and press your Transform hotkey (see Hotkeys below) for an instant rewrite with preview.</p>
    <div class="scard">
      ${tgl('transform_enabled','Enable Transform')}
      ${tgl('transform_inline_enabled','Inline — “…so Flume, …” at the end of a dictation')}
      ${tgl('transform_selection_enabled','Selection — '+PL_KEYS.MOD_LABEL+' '+(TSET._tfLabel||'T')+' on highlighted text (preview before replace)')}
    </div>`;
}
function fillHotkeyLabels(){
  if(!TSET) return;
  const d=document.getElementById('dictKeyLbl'); if(d) d.textContent=TSET._dictLabel||PL_KEYS.DICT_DEFAULT;
  const t=document.getElementById('tfKeyLbl'); if(t) t.textContent=TSET._tfLabel||'T';
}
function pickHotkey(which){
  const btn=document.getElementById(which==='dict'?'dictKeyBtn':'tfKeyBtn');
  const msg=document.getElementById('hotkeyMsg');
  if(btn.dataset.wait) return;
  window.__HK_WAIT=true;                             // freeze settings rebuilds
  btn.dataset.wait='1'; btn.textContent='Press a key…';
  if(msg) msg.textContent = which==='dict' ? PL_KEYS.PICK_DICT_HINT : PL_KEYS.PICK_TF_HINT;
  api(which==='dict'?'set_dictation_hotkey':'set_transform_hotkey').then(r=>{
    window.__HK_WAIT=false;
    delete btn.dataset.wait; btn.textContent='Change';
    if(r && r.ok){
      if(which==='dict'){ TSET._dictLabel=r.label; } else { TSET._tfLabel=r.label; }
      fillHotkeyLabels();
      if(msg) msg.textContent='Saved — active immediately.';
    } else if(r && r.cancelled){ if(msg) msg.textContent='No key pressed — click Change and press a key within 20s.'; }
    else { if(msg) msg.textContent=(r&&r.error)||'Could not set that key.'; }
    setTimeout(()=>{ if(msg && msg.textContent==='Saved — active immediately.') msg.textContent=''; }, 2500);
  });
}
function toggleTfSetting(key, el){
  el.classList.toggle('on');
  const val = el.classList.contains('on');
  if(TSET) TSET[key]=val;
  api('set_transform_setting', key, val);
}

function renderDictionary(){
  const vocab = DICT.vocabulary.map((w,i)=>`<span class="dchip">${esc(w)}<button onclick="removeWord(${i})" title="Remove">✕</button></span>`).join('')
    || '<span class="ssub" style="margin:0">No words yet — add names, products, acronyms, anything Flume mishears.</span>';
  const reps = DICT.replacements.map((r,i)=>`<div class="reprow"><span class="rfrom">${esc(r.from)}</span><span class="rarrow">→</span><span class="rto">${esc(r.to)}${r.auto?' <span title="Auto-learned from a correction" style="opacity:.75">✨</span>':''}</span><button onclick="removeRep(${i})" title="Remove">✕</button></div>`).join('')
    || '<span class="ssub" style="margin:0">No rules yet — or edit a transcription in History and Flume learns one automatically.</span>';
  document.getElementById('dictionaryMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Transcription</div><h1 class="title">Dictionary</h1></div>
      <span class="notesave" id="dictState"></span></div>
    <div class="dictgrid">
      <div class="dictcol">
        <div class="dcolhead"><h3>Vocabulary</h3><p class="ssub">Words &amp; names Flume should recognize and spell correctly.</p></div>
        <div class="dictchips">${vocab}</div>
        <div class="dictadd"><input id="dictWord" placeholder="Add a word or name…" onkeydown="if(event.key==='Enter'){event.preventDefault();addWord();}"/><button class="btn primary" style="flex:none;width:80px" onclick="addWord()">Add</button></div>
      </div>
      <div class="dictcol">
        <div class="dcolhead"><h3>Replacement rules</h3><p class="ssub">Always rewrite a misheard word into the correct one.</p></div>
        <div class="reprows">${reps}</div>
        <div class="dictadd"><input id="repFrom" placeholder="heard…" style="flex:1"/><span class="rarrow">→</span><input id="repTo" placeholder="correct…" style="flex:1"/><button class="btn primary" style="flex:none;width:80px" onclick="addRep()">Add</button></div>
      </div>
    </div>
    <div class="ssection" style="margin-top:22px">
      <h3>Auto-learn from corrections</h3>
      <p class="ssub">When you fix a misheard word right after dictating, Flume offers to remember it. Auto-learned rules are marked <span style="opacity:.75">✨</span> above.</p>
      <div class="saverow"><button class="toggle alToggleBtn ${AL.enabled?'on':''}" id="alToggle" onclick="toggleAutolearn()"></button><span style="font:500 13px Geist">Enable auto-learn</span></div>
    </div>
    <div class="ssection" style="margin-top:22px">
      <h3>File tagging <span class="ssub" style="display:inline;margin:0">(Cursor, Windsurf, VS Code, Antigravity, Kiro)</span></h3>
      <p class="ssub">When you dictate inside a supported IDE, spoken file names become <b>@name.ext</b> tags.</p>
      <div class="saverow"><button class="toggle ftToggleBtn ${FT.enabled?'on':''}" id="ftToggle" onclick="toggleFiletag()"></button><span style="font:500 13px Geist">Enable file tagging</span></div>
      <p class="ssub" style="margin:10px 0 0">${FT.seen_count||0} file${FT.seen_count===1?'':'s'} remembered.</p>
    </div>`;
  if(!DICT_LOADED){ DICT_LOADED=true; loadDict(); }
  if(!FT_LOADED){ FT_LOADED=true; loadFiletag(); }
  if(!AL_LOADED){ AL_LOADED=true; loadAutolearn(); }
}
function loadAutolearn(){ api('get_autolearn_enabled').then(r=>{ if(r&&r.ok){ AL={enabled:!!r.enabled}; if(ACTIVE==='dictionary'||ACTIVE==='settings') dictReRender(); } }); }
// Optimistic flip, but REVERTED on failure (IDI-167). These used to keep the
// new position no matter what the backend said, so a failed write looked like
// a successful one until the next reload silently flipped it back.
function paintAL(){ document.querySelectorAll('.alToggleBtn').forEach(b=>b.classList.toggle('on',AL.enabled)); }
function toggleAutolearn(){
  const was=AL.enabled;
  AL.enabled=!was; paintAL();
  busyGuard('autolearn', ()=>api('set_autolearn_enabled', AL.enabled)).then(r=>{
    if(r && r.busy){ AL.enabled=was; paintAL(); return; }
    if(r&&r.ok){ AL.enabled=!!r.enabled; paintAL(); }
    else { AL.enabled=was; paintAL(); toast((r&&r.error)||'Could not change auto-learn.', true); }
  });
}
function loadFiletag(){ api('get_filetag_settings').then(r=>{ if(r&&r.ok){ FT={enabled:!!r.enabled,seen_count:r.seen_count||0}; if(ACTIVE==='dictionary'||ACTIVE==='settings') dictReRender(); } }); }
function paintFT(){ document.querySelectorAll('.ftToggleBtn').forEach(b=>b.classList.toggle('on',FT.enabled)); }
function toggleFiletag(){
  const was=FT.enabled;
  FT.enabled=!was; paintFT();
  busyGuard('filetag', ()=>api('set_filetag_enabled', FT.enabled)).then(r=>{
    if(r && r.busy){ FT.enabled=was; paintFT(); return; }
    if(r&&r.ok){ FT.enabled=!!r.enabled; paintFT(); }
    else { FT.enabled=was; paintFT(); toast((r&&r.error)||'Could not change file tagging.', true); }
  });
}
function dictReRender(){ if(ACTIVE==='dictionary') renderDictionary(); else if(ACTIVE==='settings') renderSettings(); }
function dictSetState(t){ const el=document.getElementById('dictState'); if(el) el.textContent=t||''; }
function loadDict(){ api('get_dictionary').then(r=>{ if(r&&r.ok){ DICT={vocabulary:r.vocabulary||[],replacements:r.replacements||[]}; dictReRender(); } }); }
// The dictionary mutators all edit DICT in place and then push the WHOLE list.
// So the guard has to sit in front of the mutation, not just the api call:
// a second click landing mid-save would otherwise re-index a spliced array
// (removeWord(2) twice deletes two different words) or get its write dropped
// and silently diverge from the server (IDI-167).
function dictBusy(){ return BUSY.has('dict'); }
function saveDict(){
  dictSetState('Saving…');
  return busyGuard('dict', ()=>api('save_dictionary', DICT.vocabulary, DICT.replacements)).then(r=>{
    if(r && r.busy) return r;
    // IDI-174: a save can succeed LOCALLY and still lose the cloud
    // compare-and-swap. `sync_error` is that case — say so rather than
    // printing "Saved" over a dictionary that never left this machine.
    if(r&&r.ok){ DICT={vocabulary:r.vocabulary||DICT.vocabulary,replacements:r.replacements||DICT.replacements};
      if(r.sync_error){ dictSetState('Saved on this device'); toast(r.sync_error, true); }
      else dictSetState('Saved'); }
    else { dictSetState('Not saved'); toast((r&&r.error)||'Could not save the dictionary.', true); }
    return r;
  });
}
function addWord(){ if(dictBusy())return; const el=document.getElementById('dictWord'); if(!el)return; const w=el.value.trim(); if(!w)return; if(!DICT.vocabulary.some(x=>x.toLowerCase()===w.toLowerCase())) DICT.vocabulary.push(w); dictReRender(); saveDict(); setTimeout(()=>{const n=document.getElementById('dictWord'); if(n)n.focus();},0); }
function removeWord(i){ if(dictBusy())return; DICT.vocabulary.splice(i,1); dictReRender(); saveDict(); }
function addRep(){ if(dictBusy())return; const f=document.getElementById('repFrom'),t=document.getElementById('repTo'); if(!f||!t)return; const frm=f.value.trim(),to=t.value.trim(); if(!frm||!to)return; DICT.replacements=DICT.replacements.filter(r=>r.from.toLowerCase()!==frm.toLowerCase()); DICT.replacements.push({from:frm,to:to}); dictReRender(); saveDict(); setTimeout(()=>{const n=document.getElementById('repFrom'); if(n)n.focus();},0); }
function removeRep(i){ if(dictBusy())return; DICT.replacements.splice(i,1); dictReRender(); saveDict(); }

// ── Snippets ──────────────────────────────────────────────────────────────
function loadSnips(){ api('fetch_snippets').then(r=>{ if(r&&r.ok){ SNIPS=r.snippets||[]; if(ACTIVE==='snippets') renderSnippets(); } }); }
function snipSearch(v){ SNIP_SEARCH=v; renderSnippets(); }
function snipSort(){ SNIP_SORT=-SNIP_SORT; renderSnippets(); }
function snipEmptyHtml(){
  return `
    <div class="mhead"><div><div class="eyebrow">Transcription</div><h1 class="title">Snippets</h1><p class="ssub" style="margin-top:6px">Say a phrase, get the full text.</p></div></div>
    <div class="snempty">
      <div class="sneyebrow">TRY ONE</div>
      <div class="snbig">Say <span class="snq">"my linkedin"</span> — get your full URL every time.</div>
      <button class="btn primary snnew" style="margin:0" onclick="openSnip('')">${SVG.plus}<span>Create your first snippet</span></button>
      <div class="snchips"><span>Calendar link</span><span>Email signature</span><span>Home address</span><span>Product blurb</span></div>
    </div>`;
}
function snipRowHtml(s){
  const prev=(s.expansion||'').replace(/\s+/g,' ').trim();
  const shown=prev.length>40? esc(prev.slice(0,40))+'…' : esc(prev);
  const active=SNIP_EDIT && SNIP_EDIT.id===s.id;
  const menu = SNIP_MENU===s.id
    ? `<div class="snmenu"><button onclick="event.stopPropagation();openSnip('${esc(s.id)}')">Edit</button><button class="del" onclick="event.stopPropagation();deleteSnip('${esc(s.id)}', this)">Delete</button></div>`
    : '';
  return `<tr class="sniprow${active?' active':''}" onclick="openSnip('${esc(s.id)}')">
    <td class="td-trig">${esc(s.trigger||'')}</td>
    <td class="td-exp">${shown}</td>
    <td class="td-label">${esc(s.label||s.trigger||'')}</td>
    <td class="td-used">${s.used||0}</td>
    <td class="td-menu"><button class="sndots" onclick="event.stopPropagation();toggleSnipMenu('${esc(s.id)}')">⋯</button>${menu}</td>
  </tr>`;
}
function snipPaneHtml(){
  const s=SNIP_EDIT||{id:'',trigger:'',expansion:'',label:''};
  const isNew=!s.id;
  const tlen=(s.trigger||'').length, elen=(s.expansion||'').length;
  return `<div class="snpane">
    <div class="snpanehead"><h3>${isNew?'New snippet':'Edit snippet'}</h3><button class="snx" onclick="closeSnip()">✕</button></div>
    <div class="snfield">
      <label>TRIGGER</label>
      <input class="sntrig" id="snipTrig" maxlength="40" placeholder="Say this to trigger…" value="${esc(s.trigger||'')}" oninput="snipEditField('trigger',this.value)"/>
      <div class="snhelp"><span>Say naturally, mid-sentence.</span><span class="sncount" id="snipTrigCount">${tlen}/40</span></div>
    </div>
    <div class="snfield">
      <label>EXPANSION</label>
      <textarea id="snipExp" maxlength="500" placeholder="What Flume should type instead…" oninput="snipEditField('expansion',this.value)">${esc(s.expansion||'')}</textarea>
      <div class="snhelp"><span></span><span class="sncount" id="snipExpCount">${elen} / 500</span></div>
    </div>
    <div class="snfield">
      <label>LABEL</label>
      <input id="snipLabel" placeholder="optional" value="${esc(s.label||'')}" oninput="snipEditField('label',this.value)"/>
    </div>
    <div class="snpanefoot">
      ${isNew?'':`<button class="sndel" onclick="deleteSnip('${esc(s.id)}', this)">Delete</button>`}
      <span class="grow"></span>
      <button class="btn ghost" style="flex:none" onclick="closeSnip()">Cancel</button>
      <button class="btn primary" style="flex:none" onclick="saveSnip(this)">Save</button>
    </div>
  </div>`;
}
function renderSnippets(){
  if(!SNIPS_LOADED){ SNIPS_LOADED=true; loadSnips(); }
  const main=document.getElementById('snippetsMain'); if(!main) return;
  const all=SNIPS||[];
  if(!all.length){ main.innerHTML = snipEmptyHtml() + (SNIP_EDIT!==null? snipPaneHtml() : ''); if(SNIP_EDIT!==null) setTimeout(()=>{const el=document.getElementById('snipTrig'); if(el)el.focus();},0); return; }
  const q=SNIP_SEARCH.trim().toLowerCase();
  let list = q ? all.filter(s=>((s.trigger||'')+' '+(s.label||'')+' '+(s.expansion||'')).toLowerCase().includes(q)) : all.slice();
  list.sort((a,b)=>(a.trigger||'').toLowerCase()<(b.trigger||'').toLowerCase()? -SNIP_SORT : SNIP_SORT);
  const totalUsed=all.reduce((a,s)=>a+(s.used||0),0);
  const rows = list.length ? list.map(snipRowHtml).join('') : `<tr><td colspan="5"><div class="empty">No snippets match "${esc(SNIP_SEARCH)}".</div></td></tr>`;
  const caret = SNIP_SORT>0 ? '▲' : '▼';
  main.innerHTML = `
    <div class="mhead">
      <div><div class="eyebrow">Transcription</div><h1 class="title">Snippets</h1><p class="ssub" style="margin-top:6px">Say a phrase, get the full text.</p></div>
      <div class="snactions">
        <div class="snsearch">${SVG.search}<input id="snipSearch" placeholder="Search" value="${esc(SNIP_SEARCH)}" oninput="snipSearch(this.value)"/></div>
        <button class="btn primary snnew" onclick="openSnip('')">${SVG.plus}<span>New</span></button>
      </div>
    </div>
    <div class="snmeta">${all.length} saved · used ${totalUsed} time${totalUsed===1?'':'s'}</div>
    <div class="snbody">
      <table class="sniptable">
        <thead><tr>
          <th class="th-trig" onclick="snipSort()">TRIGGER <span class="scaret">${caret}</span></th>
          <th>EXPANSION</th><th>LABEL</th><th class="th-used">USED</th><th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${SNIP_EDIT!==null? snipPaneHtml() : ''}`;
  if(q){ const el=document.getElementById('snipSearch'); if(el){ el.focus(); try{ el.setSelectionRange(el.value.length,el.value.length); }catch(e){} } }
}
function snipEditField(k,v){
  if(!SNIP_EDIT) return;
  SNIP_EDIT[k]=v;
  if(k==='trigger'){ const el=document.getElementById('snipTrigCount'); if(el) el.textContent=v.length+'/40'; }
  else if(k==='expansion'){ const el=document.getElementById('snipExpCount'); if(el) el.textContent=v.length+' / 500'; }
}
function openSnip(id){
  SNIP_MENU=null;
  if(id){ const s=(SNIPS||[]).find(x=>x.id===id); SNIP_EDIT = s ? {id:s.id,trigger:s.trigger||'',expansion:s.expansion||'',label:s.label||''} : {id:'',trigger:'',expansion:'',label:''}; }
  else SNIP_EDIT={id:'',trigger:'',expansion:'',label:''};
  renderSnippets();
  setTimeout(()=>{ const el=document.getElementById('snipTrig'); if(el) el.focus(); },0);
}
function closeSnip(){ SNIP_EDIT=null; renderSnippets(); }
function toggleSnipMenu(id){ SNIP_MENU = (SNIP_MENU===id? null : id); renderSnippets(); }
function saveSnip(btn){
  if(!SNIP_EDIT) return;
  const t=(SNIP_EDIT.trigger||'').trim(), e=(SNIP_EDIT.expansion||'').trim(), l=(SNIP_EDIT.label||'').trim();
  if(!t||!e) return;
  const isNew=!SNIP_EDIT.id;
  // Guarded: a double-click on New → Save used to create TWO snippets, because
  // add_snippet fired twice before SNIP_EDIT.id came back (IDI-167).
  busyGuard(btn || 'save_snippet', ()=> isNew
    ? api('add_snippet', {trigger:t, expansion:e, label:l})
    : api('update_snippet', {id:SNIP_EDIT.id, trigger:t, expansion:e, label:l})
  ).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ SNIPS=r.snippets||SNIPS; SNIP_EDIT=null; renderSnippets();
      if(r.sync_error) toast(r.sync_error, true); }
    else toast((r&&r.error)||'Could not save the snippet.', true);
  });
}
function deleteSnip(id, btn){
  if(!id) return;
  const s=(SNIPS||[]).find(x=>x.id===id);
  const name=(s&&(s.trigger||s.label))||'this snippet';
  if(!confirm('Delete the snippet “'+name+'”?\n\nThis cannot be undone.')) return;
  busyGuard(btn || ('delsnip:'+id), ()=>api('delete_snippet', id)).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ SNIPS=r.snippets||SNIPS; if(SNIP_EDIT&&SNIP_EDIT.id===id) SNIP_EDIT=null; SNIP_MENU=null; renderSnippets(); }
    else toast((r&&r.error)||'Could not delete the snippet.', true);
  });
}
function fieldVal(id, fallback){
  const el=document.getElementById(id);
  return el ? el.value : fallback;
}
function togOn(id, fallback){
  const el=document.getElementById(id);
  return el ? el.classList.contains('on') : fallback;
}
function saveSettings(){
  // Groq/Gemini keys are no longer entered in-app (Groq is served by the groq-proxy
  // Edge Function). Preserve whatever is already in state so we never clobber it.
  const s=(STATE&&STATE.settings)||{};
  api('save_settings', {
    groq_api_keys:s.groq_api_keys||[], gemini_api_keys:s.gemini_api_keys||[],
    // Only one settings group is mounted at a time now, so every field here may
    // legitimately be absent — read what is on screen and keep state for the rest.
    // Reading .value off a missing node threw, which killed the whole save.
    whisper_model:fieldVal('model', s.whisper_model||'base'),
    sync_enabled:togOn('syncToggle', !!s.sync_enabled),
    sync_user_id:fieldVal('userId', s.sync_user_id||''),
    sync_device_name:fieldVal('devName', s.sync_device_name||''),
  }).then(load);
}
// IDI-172: `clear_history` existed in the API but nothing ever called it. The
// two steps are deliberately SEPARATE questions — "clear my history" on this
// machine is a very different act from erasing it off the user's phone, and
// only the second one is unrecoverable for the other devices.
function clearHistory(btn){
  if(!confirm('Clear history on this device? Your transcriptions here will be removed.')) return;
  busyGuard(btn || 'clear_history', ()=>api('clear_history')).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ toast((r.error)||'Could not clear history.', true); return; }
    STATE = r; renderActive(); renderSidebar();
    toast('History cleared on this device.');
    const signedIn = !!(r && r.signed_in);
    if(!signedIn) return;
    if(!confirm('Also clear from your other devices? This deletes these transcriptions from your account, on every device. It cannot be undone.')) return;
    busyGuard('clear_history_cloud', ()=>api('clear_history_everywhere')).then(c=>{
      if(c && c.busy) return;
      if(c && c.ok===false){ toast((c.error)||'Could not clear your other devices.', true); return; }
      toast('Cleared from your other devices.');
    });
  });
}
// MER-32: two-step confirm (this is destructive and irreversible — server-side
// deletes every DB row + storage object + the auth user itself, then the local
// caches are wiped and the app returns to signed-out state, mirrored via load()).
async function deleteAccount(){
  if(!confirm('Delete your account? This permanently erases your account and ALL cloud data — history, notes, dictionary, meetings, recordings — on every device. This cannot be undone.')) return;
  if(!confirm('Are you absolutely sure? This is your last chance to cancel — confirming will delete everything permanently.')) return;
  const btn = document.getElementById('deleteAcctBtn');
  if(btn){ btn.disabled = true; btn.textContent = 'Deleting…'; }
  try {
    const r = await api('delete_account');
    if(r && r.ok){ await load(); }
    else {
      // A dead session is the one failure the user can actually fix, so offer
      // the fix instead of a dead-end alert (IDI-166).
      if(r && r.session_dead){
        if(confirm(((r.error)||'Your session expired.') + '\n\nSign in again now?')) reSignIn();
      } else {
        alert('Could not delete account: ' + ((r&&r.error)||'unknown error'));
      }
      if(btn){ btn.disabled=false; btn.textContent='Delete account'; }
    }
  } catch(e) {
    alert('Could not delete account: ' + e);
    if(btn){ btn.disabled=false; btn.textContent='Delete account'; }
  }
}
// Notes v2 feature flags (Decision 4). Toggle immediately; send a FULL settings
// payload built from the persisted STATE so a partial write never clobbers API keys
// or sync fields (save_settings only overwrites flags that are present).
function toggleNoteFlag(name, btn){
  btn.classList.toggle('on');
  const on=btn.classList.contains('on');
  const s=(STATE&&STATE.settings)||{};
  const payload={
    groq_api_keys:s.groq_api_keys||[], gemini_api_keys:s.gemini_api_keys||[],
    whisper_model:(STATE&&STATE.model)||'base',
    sync_enabled:!!s.sync_enabled, sync_user_id:s.sync_user_id||'', sync_device_name:s.sync_device_name||'',
    notes_search_enabled:s.notes_search_enabled!==false,
    notes_autotitle_enabled:s.notes_autotitle_enabled!==false,
    notes_structure_detection_enabled:s.notes_structure_detection_enabled!==false,
    notes_audio_linkage_enabled:s.notes_audio_linkage_enabled!==false,
  };
  payload[name]=on;
  if(STATE&&STATE.settings) STATE.settings[name]=on;
  api('save_settings', payload);
}

// Native → JS events
window.VerbalNative = function(event, payload){
  if(event==='recordingState'){ if(STATE) STATE.recording=payload.recording; if(ACTIVE==='home')renderHome(); if(ACTIVE==='canvas')renderCanvas(); }
  else if(event==='state'){ STATE=payload; applyAuthGate(); renderSidebar(); renderActive(); }
  else if(event==='selectTab'){ if(payload && payload.tab) show(payload.tab); }
  else if(event==='result'){ load(); }
  else if(event==='canvasRemote'){ CANVAS={content:payload.content||'', image_url:payload.image_url||null, from:payload.device_name}; if(ACTIVE==='canvas')renderCanvas(); }
  else if(event==='meetingsUpdated'){ loadMeets();
    refreshOpenMeeting(payload && payload.id, payload && payload.deleted); }
  // MER-46: open_meeting hands the row straight to the detail view. Buffered on
  // the Python side until `dashboard_page_ready`, so this also works when the
  // window was built by this very click (the meeting bar's handoff).
  else if(event==='openMeeting'){ openMeetingDetail(payload); }
};
document.addEventListener('paste', function(e){
  if(ACTIVE!=='canvas') return;
  const items=(e.clipboardData&&e.clipboardData.items)||[];
  for(let i=0;i<items.length;i++){
    if(items[i].type && items[i].type.indexOf('image')===0){
      const blob=items[i].getAsFile();
      if(blob){ const rd=new FileReader(); rd.onload=()=>sendCanvasImage(rd.result); rd.readAsDataURL(blob); e.preventDefault(); return; }
    }
  }
  // No image in the JS clipboard payload — if the user isn't typing text, try
  // the native clipboard (WKWebView often hides image data from JS).
  const inText = document.activeElement && document.activeElement.id==='canvasArea'
    && e.clipboardData && (e.clipboardData.getData('text')||'').length>0;
  if(!inText){ e.preventDefault(); pasteCanvasImage(); }
});

let WSTEP=1, PERMS={};
const WIZ_ICON={
  check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  mic:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>',
  speaker:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
  bell:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>',
  phone:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="20" rx="2.5"/><line x1="11" y1="18" x2="13" y2="18"/></svg>'
};
const PERM_META=[
  {key:'accessibility',name:'Accessibility',sub:'Lets Flume paste text into other apps.',icon:'check'},
  {key:'microphone',name:'Microphone',sub:'Captures your voice for dictation and meetings.',icon:'mic'},
  {key:'system_audio',name:'System audio',sub:'Records other participants in meetings.',icon:'speaker',optional:true},
  {key:'notifications',name:'Notifications',sub:'Alerts when a transcription finishes.',icon:'bell',optional:true}
];
function applyAuthGate(){
  const si=document.getElementById('signin'), gs=document.getElementById('getstarted'), app=document.getElementById('appRoot');
  if(!STATE){ if(si)si.hidden=true; if(gs)gs.hidden=true; if(app)app.style.display=''; return; }
  let mode='app';
  if(STATE.signed_in===false) mode='signin';
  else if(STATE.onboarded===false) mode='wizard';
  // A completed sign-in ends the attempt. Without this the flag stayed true
  // behind the hidden pane, and a later sign-out came back to a disabled
  // button with a Cancel next to it — the exact latch this ticket removes.
  if(STATE.signed_in) SIGNIN_BUSY=false;
  if(si) si.hidden = mode!=='signin';
  if(gs) gs.hidden = mode!=='wizard';
  if(app) app.style.display = mode==='app' ? '' : 'none';
  // The sign-in pane is DATA-DRIVEN (IDI-166): sign_in_google returns an
  // optimistic ok and the real outcome lands later as a pushed state carrying
  // `auth_error`. Rendering it here is what guarantees the user can always
  // retry — the old static pane left the button disabled forever on a
  // cancel/timeout and only an app restart recovered.
  if(mode==='signin') renderSignin();
  renderDeadBanner();
  if(mode==='wizard'){ if(!Object.keys(PERMS).length) loadPerms(); else renderWizard(); }
}
// True only between "user clicked" and "we heard back" — deliberately client
// side, because an in-flight OAuth flow has no server-side state we can poll.
let SIGNIN_BUSY=false;
function renderSignin(){
  const b=document.getElementById('siGoogleBtn'), lbl=document.getElementById('siGoogleLbl');
  const err=document.getElementById('siErr'), errtx=document.getElementById('siErrTx');
  const cancel=document.getElementById('siCancelBtn');
  const note=document.getElementById('siNote'), notetx=document.getElementById('siNoteTx');
  if(!b) return;
  const msg=(STATE&&STATE.auth_error)||'';
  // Non-error confirmation on the signed-out screen (IDI-170) — today only
  // "Your account has been deleted.", so the sign-in wall doesn't read as a
  // failed deletion. Suppressed the moment a real error exists, and cleared
  // when the next attempt starts.
  const notice=(!msg && !SIGNIN_BUSY && STATE && STATE.auth_notice) || '';
  if(msg) SIGNIN_BUSY=false;            // an error means the attempt is over
  b.disabled=SIGNIN_BUSY;
  if(lbl) lbl.textContent = SIGNIN_BUSY ? 'Waiting for your browser…'
                          : (msg ? 'Try again with Google' : 'Continue with Google');
  if(err) err.hidden=!msg;
  if(errtx) errtx.textContent=msg;
  if(note) note.hidden=!notice;
  if(notetx) notetx.textContent=notice;
  if(cancel) cancel.hidden=!SIGNIN_BUSY;
}
function signInGoogle(){
  if(SIGNIN_BUSY) return;
  SIGNIN_BUSY=true;
  if(STATE){ STATE.auth_error=''; STATE.auth_notice=''; }
  renderSignin();
  api('sign_in_google').then(r=>{
    if(!r || r.ok===false){
      SIGNIN_BUSY=false;
      if(STATE) STATE.auth_error=(r&&r.error)||'Sign-in is not available on this build.';
      renderSignin();
    }
  });
}
// Abandons the pending flow server-side too, which frees the OAuth callback
// port — without that, the retry can't bind and fails instantly.
function cancelSignIn(){
  SIGNIN_BUSY=false;
  if(STATE) STATE.auth_error='';
  renderSignin();
  api('cancel_sign_in');
}
// Sidebar / Settings "Session expired" banner. `signed_in` stays true after a
// dead refresh token (the identity survives, the tokens don't), so this is the
// only thing that tells the user why JWT-only actions are failing (IDI-166).
function renderDeadBanner(){
  const el=document.getElementById('sideDead');
  if(el) el.hidden = !(STATE && STATE.session_dead);
}
function reSignIn(){
  toast('Opening your browser to sign in…');
  api('sign_in_google');
}
window.__resetOnboarding=function(){ WSTEP=1; PERMS={}; load(); };
function loadPerms(){ api('get_permissions').then(r=>{ PERMS=(r&&r.ok&&r.perms)||{}; renderWizard(); }).catch(()=>renderWizard()); }
function reqPerm(which){ api('request_permission', which).then(r=>{ if(r&&r.ok&&r.perms){ PERMS=r.perms; renderWizard(); } setTimeout(loadPerms, 1500); }); }
function wizNext(){ if(WSTEP<3){ WSTEP++; renderWizard(); } else finishOnboarding(); }
function wizBack(){ if(WSTEP>1){ WSTEP--; renderWizard(); } }
function finishOnboarding(){ api('complete_onboarding').then(()=>{ if(STATE) STATE.onboarded=true; applyAuthGate(); load(); }); }
function renderWizard(){
  const el=document.getElementById('gsInner'); if(!el) return;
  const pct=Math.round(WSTEP/3*100);
  let content='';
  if(WSTEP===1){
    const rows=PERM_META.map(p=>{
      const ok=(PERMS[p.key]==='granted');
      const right = ok ? '<span class="permpill"><span class="pdot"></span>Granted</span>'
        : `<button class="btn ${p.optional?'ghost':'primary'}" style="flex:none;min-width:78px" onclick="reqPerm('${p.key}')">Grant</button>`;
      return `<div class="permrow${(!ok&&!p.optional)?' need':''}"><div class="permicon ${ok?'ok':(p.optional?'':'need')}">${WIZ_ICON[p.icon]}</div>
        <div class="perminfo"><div class="permname">${p.name}${p.optional?'<span class="opt">Optional</span>':''}</div><div class="permsub">${p.sub}</div></div>${right}</div>`;
    }).join('');
    content=`<div class="gstitle">A few permissions.</div><div class="gslead">Flume needs these to paste transcriptions and record meetings on this Mac.</div>${rows}`;
  } else if(WSTEP===2){
    // The wizard is only ever reachable when signed_in is true — applyAuthGate
    // gives the sign-in wall priority over the onboarded check — so STATE.user
    // is always populated here. The old `!STATE.user` "Sign in" fallback was
    // dead code and has been removed (IDI-166).
    const u=(STATE&&STATE.user)||{};
    content=`<div class="gstitle">Sync across your devices.</div>
      <div class="gslead">Signed in as ${esc(u.email||'your account')}. Your dictation, notes and canvas stay in sync everywhere you sign in.</div>
      <div class="permrow"><div class="permicon ok">${WIZ_ICON.phone}</div><div class="perminfo"><div class="permname">This Mac</div><div class="permsub">Synced to your account</div></div><span class="permpill"><span class="pdot"></span>Active</span></div>`;
  } else {
    content=`<div class="gstitle">You're all set.</div>
      <div class="gslead">Hold your hotkey anywhere to dictate — it lands in your clipboard and pastes automatically. Open Flume from the menu bar any time.</div>
      <div class="permrow"><div class="permicon ok">${WIZ_ICON.check}</div><div class="perminfo"><div class="permname">Ready to go</div><div class="permsub">Everything is configured.</div></div></div>`;
  }
  const back = WSTEP>1?`<button class="btn ghost" style="flex:none" onclick="wizBack()">Back</button>`:'';
  el.innerHTML=`<div class="gsstep">STEP ${WSTEP} OF 3</div><div class="gsbar"><i style="width:${pct}%"></i></div>${content}
    <div class="gsnav">${back}<span class="grow"></span><button class="btn primary" style="flex:none;min-width:160px" onclick="wizNext()">${WSTEP<3?'Continue':'Start using Flume'}</button></div>`;
}

let LOAD_STARTED=false;
async function load(){
  LOAD_STARTED=true;
  // MER-46 handshake. VerbalNative is installed by now (it is assigned at parse
  // time) and the bridge is live (pywebviewready fired, or the backstop ran), so
  // Python can flush the events it queued while the page loaded — that is how an
  // `openMeeting` survives being pushed into a window built a moment earlier.
  // Deliberately BEFORE the awaits: the flush must not wait on get_state.
  api('dashboard_page_ready');
  const r = await api('get_state');
  if(r && r.ok){ STATE=r; applyAuthGate(); renderSidebar(); }
  await new Promise(res=>{ api('fetch_notes').then(rn=>{ if(rn&&rn.ok)NOTES=rn.notes||rn.data||[]; res(); }); });
  loadCanvas();
  renderActive();
}
// Explicit navigation always lands on a screen's TOP level: clicking Meetings
// while reading one meeting goes back to the list (MER-46), where an
// openMeeting event (which sets the sub-route first) must not be reset.
function navTo(id){
  if(id==='meetings'){ MVIEW='list'; MROW=null; MSUBNOTES=false; }
  show(id);
}
document.querySelectorAll('[data-screen]').forEach(n=>n.onclick=()=>navTo(n.dataset.screen));
// The macOS bridge shim now dispatches a REAL pywebviewready at document-start
// (flume_web_dashboard._SHIM), so this is the normal path on both platforms.
window.addEventListener('pywebviewready', load);
// Backstop only, for a host that never fires the event. LOAD_STARTED (not
// STATE) is the guard: get_state is async, so a slow first response used to
// let the timer kick off a duplicate load.
setTimeout(()=>{ if(!LOAD_STARTED) load(); }, 400);
</script>"""

    # Inline the icon SVGs into a JS map the render functions reference as SVG.<name>
    svg_map = "<script>const SVG={" + ",".join(
        f'{k}:{_json_str(_svg(k))}' for k in _IC
    ) + "};</script>"

    # Platform-aware key glyphs. The Mac page uses ⌘⇧ / "Right ⌘"; on
    # Windows those Command symbols are meaningless — swap in Ctrl+Shift
    # and a sensible Right-Alt default. Injected as a JS constant BEFORE
    # the main script so every render function that references PL_KEYS
    # picks up the right labels.
    import sys as _sys
    _is_win = _sys.platform == "win32"
    _key_defs = {
        "mac": {
            "MOD_LABEL":        "⌘⇧",    # ⌘⇧
            "MOD_KBD":          "⌘⇧",
            "DICT_DEFAULT":     "Right ⌘",     # Right ⌘
            "PICK_DICT_HINT":   "Press the key you want (modifiers like Right ⌘ work too). Esc cancels.",
            "PICK_TF_HINT":     "Press one letter/key — it will trigger with ⌘⇧. Esc cancels.",
        },
        "win": {
            "MOD_LABEL":        "Ctrl+Shift",
            "MOD_KBD":          "Ctrl+Shift",
            "DICT_DEFAULT":     "Right Alt",
            "PICK_DICT_HINT":   "Press the key you want (modifiers like Right Alt work too). Esc cancels.",
            "PICK_TF_HINT":     "Press one letter/key — it will trigger with Ctrl+Shift. Esc cancels.",
        },
    }
    _pl = "win" if _is_win else "mac"
    platform_map = ("<script>const PL_KEYS=" +
                    _json_str(_key_defs[_pl]) +
                    f";const IS_WINDOWS={('true' if _is_win else 'false')};</script>")

    # Strip the leftover placeholder line from the JS.
    js = js.replace("const IC. = {}; // placeholder\n", "")

    # pressed_css goes LAST: a handful of hover rules here also set `filter`
    # (.siGoogle, .playbtn, .dictate), and at equal specificity source order
    # decides — so the press must be able to win while hovered.
    # platform_map defines PL_KEYS/IS_WINDOWS and must precede the body that
    # renders hotkey labels from them.
    return (f"<style>{web_font_css()}{_CSS}{pressed_css(_PRESSED_SELECTORS)}</style>"
            f"{svg_map}{platform_map}{body}{js}")


def _json_str(s: str) -> str:
    import json
    return json.dumps(s)

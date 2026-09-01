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
    ".insseg button", ".cvrcopy", ".cvmore",
    ".devrm", ".npin", ".ncdots", ".nmenu button", ".askNote .ax",
    ".pillbtn", ".scard", ".srow .splay", ".addpill", ".dictbar .dfab", ".hamb",
    ".nimpTab", ".nimpX", ".dictbar .dside",
    ".spkrow", ".playbar .pfab", ".pspeed", ".spkchip", ".npaneHead .hnTab",
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
    # Team (IDI-216): three figures — distinct from "meet", which is two.
    "team":   '<circle cx="8.5" cy="8" r="3"/><path d="M2.5 19c.6-3 2.8-4.6 6-4.6s5.4 1.6 6 4.6"/><circle cx="17.5" cy="7.5" r="2.4"/><path d="M16.4 13.2c2.4.2 4.1 1.7 5.1 4.6"/>',
    "arrow":  '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    "mail":   '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    # Used wherever the privacy contract is stated — the one place a padlock is
    # the honest glyph rather than decoration.
    "lock":   '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
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
/* ── update banner (IDI-224 follow-up) — a fixed overlay appended to body
   directly rather than the grid, so it floats above whichever screen is
   active without every screen template needing its own slot for it. ── */
#update-banner{position:fixed;top:14px;right:14px;z-index:80;display:flex;align-items:center;gap:10px;
  background:var(--card);border:1px solid var(--acc-bd);border-radius:12px;padding:10px 14px;
  box-shadow:0 8px 24px rgba(0,0,0,.4);font:500 13px 'Geist';color:var(--tx);max-width:380px}
#update-banner .ub-text{flex:1;line-height:1.4}
#update-banner .ub-text b{color:var(--acc-txt)}
#update-banner .ub-actions{display:flex;gap:8px;flex:none}
#update-banner button{font:600 12px 'Geist';border-radius:8px;padding:6px 12px;cursor:pointer;border:1px solid transparent}
#update-banner button.primary{background:var(--acc);color:#fff}
#update-banner button.ghost{background:transparent;border-color:var(--bd2);color:var(--mut)}
#update-banner .ub-bar{width:100%;height:4px;border-radius:2px;background:var(--bd2);overflow:hidden;margin-top:6px}
#update-banner .ub-bar>i{display:block;height:100%;background:var(--acc);transition:width .3s}
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
.devrow{display:flex;align-items:center;gap:10px;font:400 12.5px 'Geist';color:var(--tx);cursor:pointer;
  border-radius:8px;padding:4px 6px;margin:0 -6px;transition:background .12s ease}
.devrow:hover{background:rgba(240,240,240,.05)}
.devrow.off{color:var(--mut)}
.devrow .dtgt{margin-left:auto;color:var(--acc);font:600 9px 'JetBrains Mono';letter-spacing:.08em;opacity:.9}
.ddot{width:7px;height:7px;border-radius:50%;background:var(--sub)}.ddot.on{background:var(--on)}
.sfooter{margin-top:auto;display:flex;align-items:center;gap:11px;padding:12px 6px 2px;border-top:1px solid var(--bd)}
.avatar{flex:none;width:30px;height:30px;border-radius:50%;background:var(--acc);color:#fff5ea;display:flex;align-items:center;justify-content:center;font:600 13px 'Geist'}
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
.insabar .asub{font:400 10.5px 'Geist';color:var(--sub);margin-top:4px}
.insseg{float:right;display:inline-flex;gap:2px;background:rgba(240,240,240,.05);border-radius:7px;padding:2px}
.insseg button{border:0;background:transparent;color:var(--sub);font:600 9.5px 'Geist';letter-spacing:.02em;padding:3px 8px;border-radius:5px;cursor:pointer;text-transform:none}
.insseg button.on{background:rgba(240,240,240,.1);color:var(--tx)}
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
/* ── Canvas D1 (two-pane, 2026-08-17) ── */
.cvgrid{display:grid;grid-template-columns:7fr 6fr;gap:14px;align-items:start}
@media (max-width:980px){.cvgrid{grid-template-columns:1fr}}
.cvdevs{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.cvdevlab{font:500 11.5px 'Geist';color:var(--sub)}
.cvdev{display:flex;align-items:center;gap:6px;border:1px solid var(--bd2);border-radius:999px;padding:6px 11px;font:500 11.5px 'Geist';color:var(--tx2)}
.cvdev.muted{color:var(--sub);border-style:dashed}
.cvhint{font:400 11.5px 'Geist';color:var(--sub);margin-left:auto}
.cvlive{border-color:var(--acc-bd)}
.cvorg{display:flex;align-items:center;gap:9px;margin-bottom:10px}
.cvav{width:26px;height:26px;border-radius:13px;background:var(--acc-soft);border:1px solid var(--acc-bd);display:flex;align-items:center;justify-content:center;font:600 11px 'Geist';color:var(--acc-txt)}
.cvwho{font:600 12.5px 'Geist'}
.cvwhen{font:500 10px 'JetBrains Mono';letter-spacing:.06em;color:var(--sub)}
.cvlivetx{font:400 13.5px/1.65 'Geist';color:var(--tx2);white-space:pre-wrap;display:-webkit-box;-webkit-line-clamp:8;-webkit-box-orient:vertical;overflow:hidden}
.cvlivetx.open{display:block;-webkit-line-clamp:unset;max-height:none}
.cvmore{display:inline-block;font:600 12px 'Geist';color:var(--acc-txt);margin-top:8px;cursor:pointer}
.cvempty{font:400 12.5px/1.55 'Geist';color:var(--sub);padding:4px 0 2px}
.cvacts{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.cvrow{display:flex;gap:11px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--bd-faint)}
.cvrow:last-child{border-bottom:0}
.cvric{width:28px;height:28px;border-radius:9px;background:rgba(240,240,240,.06);display:flex;align-items:center;justify-content:center;color:var(--mut);flex:none}
.cvric svg{width:14px;height:14px}
.cvrtx{flex:1;min-width:0}
.cvr1{font:400 12.5px/1.5 'Geist';color:var(--tx2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.cvr2{font:400 10.5px 'Geist';color:var(--sub);margin-top:2px}
.cvrcopy{border:0;background:none;color:var(--mut);font:600 11px 'Geist';cursor:pointer;padding:4px 2px;flex:none}
.cvrcopy:hover{color:var(--tx)}
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
/* An icon fmtbtn (the ⋯ More menu) rendered BLANK without this — an svg with
   only a viewBox gets the 300×150 default size and paints outside the 32px
   button (2026-08-15 "blank button" report). */
.fmtbtn svg{width:15px;height:15px;flex:none}
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
/* Editor text size (Aa menu, persisted): scales body + transcript + title. */
.edscroll.fs-s .notebody,.edscroll.fs-s .noteorig{font-size:13px;line-height:1.65}
.edscroll.fs-l .notebody,.edscroll.fs-l .noteorig{font-size:17.5px;line-height:1.75}
.edscroll.fs-s .edtitle{font-size:20px}
.edscroll.fs-l .edtitle{font-size:27px}
.fmtbtn:disabled{opacity:.35;cursor:default}
.fmtbtn:disabled:hover{color:var(--mut);background:transparent}
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
/* ── Sync-target popover (click a device row, or the Home pill) ─────────────
   A small hover panel with the SAME send-target controls as the Devices
   screen's selector, so you don't have to leave Home (or the sidebar) to
   redirect where dictation lands. */
.homeSyncPill{display:inline-flex;align-items:center;gap:7px;padding:6px 13px;border-radius:999px;
  border:1px solid var(--bd2);background:transparent;color:var(--mut);cursor:pointer;
  font:500 12px 'Geist';margin-top:9px}
.homeSyncPill:hover{color:var(--tx);border-color:var(--acc-bd)}
.homeSyncPill .tdot{width:5px;height:5px;border-radius:50%;background:#4ad15a;display:inline-block;flex:none}
#syncPop{position:fixed;z-index:85;display:none;background:var(--card);border:1px solid var(--bd);
  border-radius:14px;padding:14px;box-shadow:0 20px 48px rgba(0,0,0,.45);min-width:220px;max-width:280px}
#syncPop .tgtwrap{margin-bottom:0}
#syncPop .tgtpills{gap:6px}
#syncPop .tgtpill{padding:6px 12px;font-size:12px}
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
/* Per-card ⋯ menu (rename/pin/delete from the list — 2026-08-15 feedback) */
.ncdots{position:absolute;top:8px;right:38px;width:26px;height:26px;border-radius:8px;border:0;background:none;color:var(--sub);cursor:pointer;display:none;align-items:center;justify-content:center}
.ncard:hover .ncdots{display:flex}
.ncdots:hover{color:var(--tx);background:rgba(240,240,240,.07)}
.ncdots svg{width:14px;height:14px}
#ncMenu{position:fixed;top:auto;right:auto}
.nctitle input.ncren{width:100%;border:1px solid var(--acc-bd);background:rgba(240,240,240,.06);border-radius:6px;color:var(--tx);font:600 13px 'Geist';padding:3px 6px;outline:0}
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
/* ── notes v3.1 — NotebookLM-style floating panes (user-picked direction):
   three rounded cards on the dark ground, pill buttons, pastel Studio cards
   (reusing the fcard cream/sage/plum language), dictation bar with a FAB. ── */
.nbgrid{display:grid;grid-template-columns:minmax(230px,290px) minmax(0,1fr) minmax(230px,290px);gap:14px;height:100vh;padding:16px;overflow:hidden}
/* No note selected → no Studio: two columns until a note is picked/created. */
.nbgrid.nosel{grid-template-columns:minmax(240px,330px) minmax(0,1fr)}
/* Notes collapses the app sidebar for room; the hamburger brings it back. */
.app{transition:grid-template-columns .22s ease}
.app.navhide{grid-template-columns:0 minmax(0,1fr)}
.app.navhide .sidebar{visibility:hidden;overflow:hidden;padding-left:0;padding-right:0;border-right:0}
.hamb{width:32px;height:32px;border-radius:9px;border:1px solid var(--bd);background:transparent;color:var(--mut);cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none;padding:0}
.hamb:hover{color:var(--tx);background:var(--raised)}
.hamb svg{width:15px;height:15px}
.npane{background:var(--card);border:1px solid var(--bd);border-radius:20px;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.npaneHead{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:14px 18px 12px;border-bottom:1px solid var(--bd);flex:none}
.npaneHead .pt{font:600 15px 'Geist';letter-spacing:-.01em}
.npaneHead .notetoolbar{margin:0}
.npaneBody{flex:1;min-height:0;overflow-y:auto;padding:14px 16px;overscroll-behavior:contain}
.npane .searchbox{margin:0 0 10px;border-radius:999px;padding:10px 16px}
.npane .ncard{border-radius:16px}
.npane .askNote{border-radius:16px}
.npane .notecount{margin:0 0 10px}
.pillbtn{display:inline-flex;align-items:center;gap:7px;padding:9px 15px;border-radius:999px;border:1px solid var(--bd2);background:transparent;color:var(--tx);font:600 12px 'Geist';cursor:pointer}
.pillbtn:hover{background:var(--raised)}
.pillbtn svg{width:14px;height:14px}
.pillbtn.acc{background:var(--acc-soft);border-color:var(--acc-bd);color:var(--acc)}
.pillrow{display:flex;gap:8px;margin-bottom:12px}
.pillrow .pillbtn{flex:1;justify-content:center}
.scards{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;align-items:stretch}
/* The Export card sits inside .nmenuwrap so its popup has an anchor. That wrapper
   used to be display:block with the card at height:100% — a percentage height
   inside a block grid item, which WebView2 resolved differently from the bare
   sibling cards, so the bottom row rendered two different card heights ("align
   these icons", 2026-08-26). A flex-column wrapper the card flex-fills needs no
   percentage height and is deterministic in every engine. position:relative
   stays: .nmenu is absolutely positioned inside it until toggleNoteMenu()
   re-anchors it position:fixed to the trigger's rect (so the card growing
   taller cannot misplace the popup). */
.scards .nmenuwrap{display:flex;flex-direction:column;min-width:0;position:relative}
.scards .nmenuwrap .scard{flex:1 1 auto;width:100%}
/* Top-anchored content. .sdisc carried margin-bottom:auto, which pinned the
   title+description to the card's BOTTOM edge — so a card whose description
   wrapped to two lines drew its title ~2px higher than its row-mate (Notes
   'Clean transcript' vs 'Export'; Meetings 'Ask this meeting' vs 'Export').
   Icon → title → description now flow from the top with a fixed gap, and the
   description reserves two lines so 1- and 2-line copy yield identical cards. */
.scards .scard{min-height:108px;gap:7px;justify-content:flex-start}
.scards .scard .sdisc{margin-bottom:0}
.scards .scard .ss{min-height:calc(2 * 1.35em)}
.scard{border:0;border-radius:16px;padding:12px;min-height:88px;display:flex;flex-direction:column;align-items:flex-start;gap:7px;cursor:pointer;text-align:left}
.scard:hover{filter:brightness(1.05)}
.scard:disabled{opacity:.45;cursor:default;filter:none}
.scard .sdisc{width:27px;height:27px;border-radius:9px;display:flex;align-items:center;justify-content:center;margin-bottom:auto}
.scard .sdisc svg{width:13px;height:13px}
.scard .sl{font:600 12.5px 'Geist';letter-spacing:-.01em}
.scard .ss{font:400 10.5px/1.35 'Geist';opacity:.62}
.scard.cream{background:#EADFCE;color:#2a1f18}.scard.cream .sdisc{background:rgba(42,31,24,.13);color:#2a1f18}
.scard.sage{background:#DDE4D3;color:#1e2418}.scard.sage .sdisc{background:rgba(30,36,24,.13);color:#1e2418}
.scard.plum{background:#e6dae4;color:#221820}.scard.plum .sdisc{background:rgba(34,24,32,.13);color:#221820}
.scard.slate{background:#d7dfe9;color:#182029}.scard.slate .sdisc{background:rgba(24,32,41,.13);color:#182029}
.shead{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--sub);text-transform:uppercase;margin:8px 2px 7px}
.srow{display:flex;align-items:center;gap:10px;padding:8px;border-radius:12px;cursor:pointer}
.srow:hover{background:var(--raised)}
.srow .sic{width:30px;height:30px;border-radius:50%;background:var(--raised);display:flex;align-items:center;justify-content:center;color:var(--mut);flex:none}
.srow .sic svg{width:13px;height:13px}
.srow .st{flex:1;min-width:0}
.srow .st .a{display:block;font:500 12.5px 'Geist';white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.srow .st .b{display:block;font:500 9.5px 'JetBrains Mono';color:var(--sub);letter-spacing:.05em;margin-top:2px}
.srow .splay{width:30px;height:30px;border-radius:50%;border:1px solid var(--acc-bd);background:var(--acc-soft);color:var(--acc);display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer;padding:0}
.srow .splay svg{width:12px;height:12px}
.studioFoot{flex:none;padding:12px 16px 14px;display:flex;justify-content:flex-end;border-top:1px solid var(--bd)}
.addpill{display:inline-flex;align-items:center;gap:8px;background:#f2f2f2;color:#111417;border:0;border-radius:999px;padding:11px 18px;font:600 12.5px 'Geist';cursor:pointer;box-shadow:0 8px 22px rgba(0,0,0,.35)}
.addpill:hover{filter:brightness(.93)}
.addpill svg{width:14px;height:14px}
.edscroll{padding:18px 20px}
/* Inside the pane the pane BODY is the one scroller (Hard Rule #23 spirit) —
   the note content must not open a nested scroller of its own. */
.edscroll .notebody{flex:none;overflow:visible;min-height:260px}
.edscroll .noteorig{flex:none;overflow:visible;min-height:240px}
.dictbar{flex:none;margin:10px 16px 16px;border:1px solid var(--bd2);background:#1b1e22;border-radius:18px;padding:9px 10px 9px 16px;display:flex;align-items:center;gap:12px}
.dictbar .dtx{flex:1;font:400 12.5px 'Geist';color:var(--mut);min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dictbar .notesave{flex:none}
.dictbar .dfab{width:38px;height:38px;border-radius:50%;background:var(--acc);color:#2a1710;border:0;display:flex;align-items:center;justify-content:center;cursor:pointer;flex:none;padding:0}
.dictbar .dfab svg{width:16px;height:16px}
.dictbar .dfab .dstop{width:11px;height:11px;border-radius:3px;background:currentColor;display:block}
.dictbar.rec{border-color:var(--acc-bd);background:var(--acc-softer)}
.dictbar.rec .dtx{color:var(--acc-txt)}
/* v3.2 recording state: cancel · live waveform · timer · pause · stop-FAB */
.dictbar .dside{width:34px;height:34px;border-radius:50%;border:1px solid var(--bd2);background:transparent;color:var(--mut);display:flex;align-items:center;justify-content:center;cursor:pointer;flex:none;padding:0;font-size:13px;line-height:1}
.dictbar .dside:hover{color:var(--tx);background:var(--raised)}
.dictbar .dside svg{width:13px;height:13px}
.dwave{display:flex;align-items:center;gap:2px;height:24px;flex:1;min-width:0;overflow:hidden;justify-content:flex-end}
.dwave i{width:3px;height:3px;border-radius:2px;background:var(--acc);flex:none;transition:height .1s linear}
.dictbar.paused .dwave i{background:var(--sub)}
.dtimer{font:600 11px 'JetBrains Mono';color:var(--acc-txt);letter-spacing:.05em;flex:none;min-width:40px;text-align:right;font-variant-numeric:tabular-nums}
.dictbar.paused .dtimer{color:var(--sub)}
@media (max-width:1000px){.nbgrid{grid-template-columns:minmax(210px,250px) minmax(0,1fr)}.npane.studio{display:none}}
/* Host couldn't grow the window (no resize support / clamped by the screen):
   force the three-pane grid anyway — squeezed beats hidden. Declared after the
   media query and with higher specificity so it wins at any width. */
.nbgrid.force3{grid-template-columns:minmax(180px,230px) minmax(0,1fr) minmax(190px,240px)}
.nbgrid.force3 .npane.studio{display:flex}
/* ── notes v3.2 — import from Meetings / Transcriptions (modal picker) ── */
.pillrow{flex-wrap:wrap}
.nimpWrap{position:fixed;inset:0;z-index:60;background:rgba(6,7,8,.62);display:flex;align-items:center;justify-content:center;padding:24px}
.nimp{width:600px;max-width:100%;max-height:82vh;background:var(--card);border:1px solid var(--bd2);border-radius:20px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.55)}
.nimpHead{display:flex;align-items:center;justify-content:space-between;padding:15px 18px 12px;border-bottom:1px solid var(--bd);flex:none}
.nimpHead .pt{font:600 15px 'Geist';letter-spacing:-.01em}
.nimpX{width:28px;height:28px;border-radius:8px;border:0;background:none;color:var(--sub);cursor:pointer;font-size:14px;padding:0}
.nimpX:hover{color:var(--tx);background:var(--raised)}
.nimpTabs{display:flex;gap:6px;padding:12px 16px 0;flex:none}
.nimpTab{padding:8px 15px;border-radius:999px;border:1px solid var(--bd2);background:transparent;color:var(--mut);font:600 11.5px 'Geist';cursor:pointer}
.nimpTab.on{background:var(--acc-soft);border-color:var(--acc-bd);color:var(--acc)}
.nimp .searchbox{margin:12px 16px 0;border-radius:999px;padding:10px 16px;flex:none}
.nimpBody{flex:1;min-height:220px;overflow-y:auto;padding:10px 12px 14px;overscroll-behavior:contain}
.srow .imppill{opacity:0;font:600 10.5px 'Geist';color:var(--acc);border:1px solid var(--acc-bd);background:var(--acc-soft);border-radius:999px;padding:5px 11px;flex:none;transition:opacity .12s}
.srow:hover .imppill,.srow:focus .imppill{opacity:1}
.srow .imppill.busy{opacity:1}
.nimpHint{font:400 11px/1.5 'Geist';color:var(--sub);padding:0 18px 13px;flex:none}
/* ── meetings v4 — the Notes pane language (approved proposal, 2026-08-15) ── */
.mgrp{background:rgba(240,240,240,.025);border:1px solid var(--bd);border-radius:16px;overflow:hidden}
.mgrow{display:flex;align-items:center;gap:11px;padding:11px 12px;position:relative;cursor:pointer}
.mgrow + .mgrow{border-top:1px solid rgba(240,240,240,.045)}
.mgrow:hover{background:var(--raised)}
.mgrow.active{background:rgba(200,90,62,.07)}
.mgrow.active::before{content:'';position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:2px;background:var(--acc)}
.mavs{display:flex;flex:none}
.mav{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font:700 10px 'Geist';color:#1a1512;border:2px solid var(--card)}
.mav + .mav{margin-left:-7px}
.mgmid{flex:1;min-width:0}
.mgtitle{font:600 12.5px 'Geist';letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px}
.mgnew{width:5px;height:5px;border-radius:50%;background:var(--acc);flex:none}
.mgprev{display:block;font:400 11px 'Geist';color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.mgside{flex:none;text-align:right;white-space:nowrap}
.mgtime{display:block;font:500 9.5px 'JetBrains Mono';color:var(--sub);letter-spacing:.05em}
.mgmeta{display:block;font:500 9.5px 'JetBrains Mono';color:var(--sub);letter-spacing:.05em;margin-top:3px}
.mgmeta .st{color:var(--acc)}
.mlivebar{display:flex;align-items:center;gap:9px;border:1px solid rgba(224,80,73,.38);background:rgba(224,80,73,.08);border-radius:14px;padding:8px 10px 8px 12px;margin-bottom:12px}
.mlivebar .t{font:600 12px 'Geist';flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mlivebar .m{font:500 10px 'JetBrains Mono';color:#f0a5a0;flex:none;letter-spacing:.06em}
.mlivebar .pillbtn{padding:6px 11px;font-size:11px;flex:none}
/* the detail lives INSIDE a pane now — neutralize its full-page chrome, keep
   every #mtgDetail-scoped widget style working via the wrapper */
.npane #mtgDetail{display:flex;flex-direction:column;height:auto;min-height:0;overflow:visible;padding:0}
.npane #mtgDetail .sumTitle{font:700 24px 'Geist';letter-spacing:-.02em;border:0;background:transparent;color:var(--tx);outline:0;width:100%;padding:0;margin:0 0 8px}
.npane #mtgDetail .sumMeta{margin:0 0 14px}
.npane #mtgNotes{height:auto;padding:0;overflow:visible}
.mdocsec{font:700 15px 'Geist';color:var(--tx);margin:20px 0 8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mdocsum{font:400 14px/1.7 'Geist';color:rgba(240,240,240,.9);max-width:680px}
/* speakers (Studio) — tap to filter the transcript to that speaker's color */
.spkrow{display:flex;align-items:center;gap:10px;padding:7px 8px;border-radius:12px;cursor:pointer;border:1px solid transparent;width:100%;background:none;text-align:left}
.spkrow:hover{background:var(--raised)}
.spkrow.on{background:rgba(240,240,240,.05);border-color:var(--bd2)}
.spkrow .sav{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font:700 11px 'Geist';color:#15181b;flex:none}
.spkrow .sn{flex:1;min-width:0}
.spkrow .sn .a{display:block;font:600 12.5px 'Geist';color:var(--tx)}
.spkrow .sn .b{display:block;font:500 9px 'JetBrains Mono';color:var(--sub);letter-spacing:.05em;margin-top:1px}
.spkrow .share{flex:none;width:52px;height:4px;border-radius:2px;background:rgba(240,240,240,.08);overflow:hidden}
.spkrow .share i{display:block;height:100%;border-radius:2px}
.spkhint{font:400 10.5px/1.5 'Geist';color:var(--sub);margin:6px 4px 0}
#mtgDetail .exUtt.dimf{opacity:.32}
#mtgDetail .exUtt.hlf{background:rgba(240,240,240,.045);border-radius:8px}
.spkchip{display:inline-flex;align-items:center;gap:8px;margin:2px 0 8px;border:1px solid var(--bd2);background:var(--raised);color:var(--tx2);border-radius:999px;padding:5px 12px;font:600 10px 'JetBrains Mono';letter-spacing:.06em;cursor:pointer}
.spkchip i{width:7px;height:7px;border-radius:50%;flex:none}
/* playback bar — the dictation bar's twin (play FAB, progress wave, time, speed) */
.playbar{flex:none;margin:10px 16px 16px;border:1px solid var(--bd2);background:#1b1e22;border-radius:18px;padding:9px 10px 9px 14px;display:flex;align-items:center;gap:12px}
.playbar.off{opacity:.45}
.playbar .pfab{width:38px;height:38px;border-radius:50%;background:var(--acc);color:#2a1710;border:0;display:flex;align-items:center;justify-content:center;cursor:pointer;flex:none;padding:0}
.playbar .pfab svg{width:15px;height:15px}
.pwave{display:flex;align-items:center;gap:2px;height:24px;flex:1;min-width:0;overflow:hidden;cursor:pointer}
.pwave i{width:3px;border-radius:2px;background:rgba(240,240,240,.2);flex:none}
.pwave i.played{background:var(--acc)}
.ptime{font:600 11px 'JetBrains Mono';color:var(--acc-txt);letter-spacing:.04em;flex:none;font-variant-numeric:tabular-nums}
.pspeed{font:600 10.5px 'JetBrains Mono';color:var(--mut);border:1px solid var(--bd2);background:none;border-radius:999px;padding:5px 10px;flex:none;cursor:pointer}
.addpill .rd{width:8px;height:8px;border-radius:50%;background:#E05049;flex:none}
.ntEdit{width:100%;min-height:440px;background:rgba(240,240,240,.03);border:1px solid var(--bd2);border-radius:12px;padding:14px;color:var(--tx);font:400 12.5px/1.7 'JetBrains Mono';outline:none;resize:vertical;caret-color:var(--acc)}
.ntEdit:focus{border-color:var(--acc-bd)}
.npaneHead .hnTabs{display:flex;gap:4px;margin-right:4px}
.npaneHead .hnTab{font:600 10.5px 'JetBrains Mono';color:var(--mut);border:1px solid var(--bd2);border-radius:999px;padding:4px 10px;background:none;cursor:pointer;letter-spacing:.04em}
.npaneHead .hnTab:hover{color:var(--tx)}
.npaneHead .hnTab.on{color:var(--acc);border-color:var(--acc-bd);background:var(--acc-soft)}
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
#mtgDetail .teaser svg{width:14px;height:14px;flex:none;color:var(--mut)}
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

/* ── Team (IDI-216) ─────────────────────────────────────────────────────────
   Deliberately reuses the Insights vocabulary — .inshero/.itile/.inscard/.inshm
   are the house style for "numbers about you", and a Team screen that invented
   its own would read as a different product. Only the pieces Insights has no
   equivalent for live here: the roster column, the contribution ring, and the
   onboarding screens. */
.teampane{display:grid;grid-template-columns:268px minmax(0,1fr);height:100vh;padding:0;overflow:hidden}
.teampane.solo{grid-template-columns:minmax(0,1fr)}
.tmroster{display:flex;flex-direction:column;border-right:1px solid var(--bd);overflow:hidden}
.tmrhead{padding:22px 18px 14px}
.tmrlist{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:0 10px}
.tmrfoot{padding:12px;border-top:1px solid var(--bd)}
.tmdetail{padding:22px 24px;overflow-y:auto;overscroll-behavior:contain;min-height:0}

/* roster rows */
.tmrow{display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:10px;cursor:pointer;
  border:0;background:transparent;width:100%;text-align:left}
.tmrow:hover{background:rgba(240,240,240,.04)}
.tmrow.on{background:rgba(240,240,240,.07)}
.tmav{width:34px;height:34px;border-radius:11px;background:var(--raised);display:flex;align-items:center;
  justify-content:center;font:600 13px 'Geist';flex:none;color:var(--tx)}
.tmav.me{background:var(--acc);color:#0e1012}
.tmav.all{background:var(--acc-soft);border:1px solid var(--acc-bd);color:var(--acc)}
.tmav.all svg,.tmav.pend svg{width:16px;height:16px}
.tmav.pend{border:1px dashed rgba(240,240,240,.16);background:transparent}
.tmbody{flex:1;min-width:0}
.tmname{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.tmname span:first-child{font:500 12.5px 'Geist';color:rgba(240,240,240,.9);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.tmrow.on .tmname span:first-child{font-weight:600;color:var(--tx)}
.tmnum{font:500 10.5px 'JetBrains Mono';color:var(--dim);flex:none}
.tmsub{font:400 10.5px 'Geist';color:var(--faint);margin-top:3px}
.tmspark{display:flex;align-items:flex-end;gap:2px;height:15px;margin-top:5px}
.tmspark i{flex:1;border-radius:1.5px;background:rgba(200,90,62,.45);min-height:2px}
.tmrow.on .tmspark i{background:var(--acc)}
.tmspark.off i{background:rgba(240,240,240,.07)}
.tmrhead .tmco{font:400 11px 'Geist';color:var(--mut);margin-bottom:5px}
.tmrhead .tmnm{font:600 20px 'Geist';letter-spacing:-.01em}
.tmseat{font:400 10.5px 'Geist';color:var(--faint);margin-top:8px;text-align:center}

/* inline invite field (roster foot + onboarding) */
.tmfield{display:flex;align-items:center;gap:8px;background:rgba(240,240,240,.04);
  border:1px solid var(--bd);border-radius:10px;padding:5px 5px 5px 12px}
.tmfield input,.tmfield select{background:none;border:0;color:var(--tx);font:400 12px 'Geist';
  flex:1;min-width:0;outline:none}
.tmfield select{flex:none;color:var(--mut)}
.tmfield button{border:0;border-radius:8px;background:#f2f2f2;color:#0e1012;font:600 11.5px 'Geist';
  padding:7px 12px;cursor:pointer;flex:none}
.tmfield button[disabled]{opacity:.5;cursor:default}

/* detail header */
.tmdhead{display:flex;align-items:center;gap:13px;margin-bottom:16px}
.tmdhead .tmav{width:42px;height:42px;border-radius:13px;font-size:17px}
.tmdname{font:600 20px 'Geist';letter-spacing:-.01em}
.tmdmeta{font:400 11.5px 'JetBrains Mono';color:var(--mut);margin-top:2px}
.tmsel{background:rgba(240,240,240,.04);border:1px solid var(--bd2);color:var(--tx);border-radius:9px;
  font:500 12px 'Geist';padding:8px 10px;cursor:pointer}
.tmghost{background:transparent;border:1px solid var(--bd2);color:var(--mut);border-radius:9px;
  font:500 12px 'Geist';padding:8px 12px;cursor:pointer}
.tmghost:hover{color:var(--tx)}

/* contribution ring — the team's answer to the Insights WPM gauge */
.tmring{position:relative;background:var(--card);border:1px solid var(--bd);border-radius:20px;
  padding:22px 20px;display:flex;align-items:center;gap:26px;margin-bottom:14px}
.tmringtx{flex:1;min-width:0}
.tmbadge{font:600 12px 'Geist';color:#0e1012;background:#f2f2f2;border-radius:999px;padding:7px 16px;
  display:inline-block}
.tmlead{font:400 14px/1.6 'Geist';color:var(--tx2);margin-top:13px}
.tmlead b{color:var(--tx);font-weight:600}
.tmlegend{display:flex;flex-wrap:wrap;gap:16px;margin-top:15px}
.tmlegend div{display:flex;align-items:center;gap:7px;font:400 11.5px 'Geist';color:var(--tx2)}
.tmlegend i{width:8px;height:8px;border-radius:2.5px;flex:none}
.tmlegend em{font:500 11px 'JetBrains Mono';color:var(--dim);font-style:normal}

/* privacy footer — say what an admin can and cannot see, where they are looking */
/* Leaderboard — a ranked table, not a bar chart. People compare themselves to
   the person one row up, so rank, name and number must sit on one readable line
   with the bar as a background wash rather than a separate column. */
.tmboard{display:flex;flex-direction:column;gap:2px;margin-top:4px}
.tmbrow{position:relative;display:grid;grid-template-columns:26px 30px minmax(0,1fr) auto;
  align-items:center;gap:11px;padding:10px 12px;border-radius:12px;overflow:hidden;
  border:1px solid transparent;transition:border-color .12s,background .12s;cursor:pointer}
.tmbrow:hover{border-color:var(--bd2)}
.tmbrow.me{background:rgba(200,90,62,.07);border-color:var(--acc-bd)}
.tmbrow i.fill{position:absolute;left:0;top:0;bottom:0;background:rgba(240,240,240,.045);
  border-radius:12px;z-index:0;transition:width .5s cubic-bezier(.22,1,.36,1)}
.tmbrow.p1 i.fill{background:rgba(200,90,62,.16)}
.tmbrow>*{position:relative;z-index:1}
.tmbrank{font:600 13px 'JetBrains Mono';color:var(--dim);text-align:center}
.tmbrow.p1 .tmbrank{color:var(--acc)}
.tmbrow .tmav{width:30px;height:30px;border-radius:10px;font-size:13px}
.tmbwho{min-width:0}
.tmbwho b{display:block;font:600 13.5px 'Geist';color:var(--tx);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.tmbwho span{font:400 11px 'JetBrains Mono';color:var(--dim);letter-spacing:.01em}
.tmbnum{text-align:right;font:600 15px 'JetBrains Mono';color:var(--tx);white-space:nowrap}
.tmbnum em{display:block;font:400 10.5px 'JetBrains Mono';color:var(--dim);font-style:normal;
  letter-spacing:.04em;text-transform:uppercase;margin-top:2px}

/* Per-person app mix. A stacked strip beats a pie at this size and reads as one
   glance: "mostly Slack, some Cursor". */
.tmapps{display:flex;flex-direction:column;gap:14px;margin-top:2px}
.tmapprow{display:flex;flex-direction:column;gap:7px}
.tmapphd{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.tmapphd b{font:600 12.5px 'Geist';color:var(--tx2)}
.tmapphd span{font:400 11px 'JetBrains Mono';color:var(--dim)}
.tmappbar{display:flex;height:9px;border-radius:999px;overflow:hidden;background:rgba(240,240,240,.05)}
.tmappbar i{height:100%;transition:width .5s cubic-bezier(.22,1,.36,1)}
.tmapplg{display:flex;flex-wrap:wrap;gap:6px 14px}
.tmapplg em{display:flex;align-items:center;gap:6px;font:400 11px 'Geist';color:var(--dim);font-style:normal}
.tmapplg em i{width:7px;height:7px;border-radius:2px;flex:none}
.tmapplg em b{font:500 11px 'Geist';color:var(--tx2)}
.tmnote{display:flex;align-items:flex-start;gap:10px;margin-top:14px;padding:12px 16px;border-radius:12px;
  background:var(--subtle-alt);border:1px solid var(--bd-faint)}
.tmnote svg{width:15px;height:15px;flex:none;margin-top:1px;color:var(--dim)}
.tmnote span{font:400 11.5px/1.55 'Geist';color:var(--dim)}

/* onboarding (no team / just created) */
.tmstart{display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-height:100%;padding:40px 28px}
.tmstartin{width:100%;max-width:640px}
.tmhero{display:flex;flex-direction:column;align-items:center;text-align:center}
.tmhero .bigico{width:64px;height:64px;border-radius:50%;background:var(--acc-soft);
  border:1px solid var(--acc-bd);display:flex;align-items:center;justify-content:center;
  color:var(--acc);margin-bottom:18px}
.tmhero .bigico svg{width:26px;height:26px}
.tmhero h2{font:700 22px 'Geist';letter-spacing:-.01em;margin:0 0 8px}
.tmhero p{font:400 13px/1.6 'Geist';color:var(--mut);margin:0;max-width:430px}
.tmdemo{background:var(--card);border:1px solid var(--bd);border-radius:18px;padding:18px 20px;
  margin:26px 0 22px}
.tmdemogrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.tmdemo .col{border:1px solid var(--bd);border-radius:12px;padding:14px 15px}
.tmdemo .col.win{border-color:var(--acc-bd);background:var(--acc-softer)}
.tmdemo .lab{display:flex;align-items:center;gap:7px;margin-bottom:10px;
  font:500 9.5px 'JetBrains Mono';letter-spacing:.14em;color:var(--dim)}
.tmdemo .col.win .lab{color:var(--acc-txt)}
.tmdemo .lab i{width:6px;height:6px;border-radius:50%;background:rgba(240,240,240,.25)}
.tmdemo .col.win .lab i{background:var(--acc)}
.tmdemo .say{font:400 15px 'Geist';color:var(--mut)}
.tmdemo .col.win .say{color:var(--tx)}
.tmdemo .bad{text-decoration:line-through;text-decoration-color:rgba(224,80,73,.7);
  text-decoration-thickness:1.5px}
.tmcreate{display:flex;gap:10px}
.tmcreate input{flex:1;min-width:0;background:rgba(240,240,240,.04);border:1px solid var(--bd2);
  border-radius:12px;padding:13px 15px;color:var(--tx);font:400 13.5px 'Geist';outline:none}
.tmcreate button{border:0;border-radius:12px;background:#f2f2f2;color:#0e1012;font:600 12.5px 'Geist';
  padding:13px 22px;cursor:pointer;flex:none;display:flex;align-items:center;gap:8px}
.tmcreate button svg{width:14px;height:14px}
.tmfine{font:400 11px 'Geist';color:var(--faint);margin-top:10px;text-align:center}
.tmor{display:flex;align-items:center;gap:14px;margin:26px 0 18px}
.tmor div{flex:1;height:1px;background:var(--bd)}
.tmor span{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--faint)}
.tmjoin{display:flex;align-items:center;gap:12px;background:var(--subtle-alt);border:1px solid var(--bd);
  border-radius:12px;padding:12px 14px}
.tmjoin svg{width:17px;height:17px;flex:none;color:var(--dim)}
.tmjoin .jt{flex:1;min-width:0}
.tmjoin .jt b{font:500 12.5px 'Geist';display:block}
.tmjoin .jt span{font:400 11px 'Geist';color:var(--dim);margin-top:2px;display:block}

/* setup steps (just-created) */
.tmstep{background:var(--card);border:1px solid var(--bd);border-radius:18px;padding:18px 20px;
  margin-bottom:12px;display:flex;align-items:flex-start;gap:13px}
.tmstep .n{width:24px;height:24px;border-radius:8px;background:var(--raised);color:var(--mut);
  display:flex;align-items:center;justify-content:center;font:600 11px 'JetBrains Mono';flex:none;margin-top:1px}
.tmstep .n.live{background:var(--acc-soft);border:1px solid var(--acc-bd);color:var(--acc)}
.tmstep .b{flex:1;min-width:0}
.tmstep h4{font:600 14px 'Geist';margin:0 0 4px}
.tmstep p{font:400 12px/1.55 'Geist';color:var(--mut);margin:0}
.tmstep p b{color:var(--tx);font-weight:600}
.tmseats{display:flex;align-items:center;gap:9px;margin-top:12px}
.tmseats .dots{display:flex;gap:5px}
.tmseats .dots i{width:22px;height:22px;border-radius:7px;border:1px dashed rgba(240,240,240,.16);
  display:block}
.tmseats .dots i.taken{border:0;background:var(--acc)}
.tmseats span{font:400 11px 'Geist';color:var(--dim)}
.tmskip{background:transparent;border:0;color:var(--dim);font:500 12px 'Geist';cursor:pointer;padding:8px}
.tmskip:hover{color:var(--tx)}
/* IDI-222 pending-invite banner — the recovery path when an emailed link never
   reached the app. Deliberately at the TOP of the no-team screen: someone who was
   invited should not have to read a pitch for creating their own team first. */
.tmpendbox{display:flex;align-items:center;gap:13px;padding:14px 16px;border-radius:14px;
  background:var(--acc-soft);border:1px solid var(--acc-bd);margin-bottom:22px}
.tmpendbox .pbico{width:34px;height:34px;border-radius:11px;background:rgba(200,90,62,.18);
  color:var(--acc);display:flex;align-items:center;justify-content:center;flex:none}
.tmpendbox .pbico svg{width:17px;height:17px}
.tmpendbox .pbtx{flex:1;min-width:0}
.tmpendbox .pbtx b{font:600 13.5px 'Geist';display:block}
.tmpendbox .pbtx span{font:400 11.5px 'Geist';color:var(--tx2);margin-top:2px;display:block}

/* ── modals ────────────────────────────────────────────────────────────────
   The dashboard had no modal vocabulary — only toasts — so inviting happened in
   an inline field that read as an afterthought. Rendered into #tmModalHost so it
   sits above every screen and can also fire on sign-in. */
.tmmodal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;
  justify-content:center;z-index:900;padding:28px}
.tmmodalbox{width:100%;max-width:460px;background:var(--card);border:1px solid var(--bd2);
  border-radius:20px;padding:24px;box-shadow:0 24px 70px rgba(0,0,0,.5)}
.tmmodalbox.wide{max-width:520px}
.tmmhead{display:flex;align-items:flex-start;gap:13px;margin-bottom:18px}
.tmmico{width:40px;height:40px;border-radius:13px;background:var(--acc-soft);border:1px solid var(--acc-bd);
  color:var(--acc);display:flex;align-items:center;justify-content:center;flex:none}
.tmmico svg{width:19px;height:19px}
.tmmico.cream{background:#EADFCE;border-color:#EADFCE;color:#2a1f18}
.tmmtitle{flex:1;min-width:0}
.tmmtitle h3{font:700 17px 'Geist';letter-spacing:-.01em;margin:0 0 4px}
.tmmtitle p{font:400 12px/1.55 'Geist';color:var(--mut);margin:0}
.tmmx{background:0;border:0;color:var(--dim);cursor:pointer;font:400 18px 'Geist';padding:0 2px;flex:none}
.tmmx:hover{color:var(--tx)}
.tmmlabel{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--mut);margin:0 0 7px}
.tmminput{width:100%;background:rgba(240,240,240,.04);border:1px solid var(--bd2);border-radius:11px;
  padding:12px 14px;color:var(--tx);font:400 13.5px 'Geist';outline:none}
.tmminput:focus{border-color:var(--acc-bd)}
.tmmrow{display:flex;gap:10px;align-items:center}
.tmmroles{display:flex;gap:6px;background:rgba(240,240,240,.04);border-radius:9px;padding:3px}
.tmmroles button{border:0;background:transparent;color:var(--mut);font:600 11.5px 'Geist';
  padding:7px 12px;border-radius:6px;cursor:pointer}
.tmmroles button.on{background:rgba(240,240,240,.1);color:var(--tx)}
.tmmfoot{display:flex;align-items:center;gap:10px;margin-top:20px}
.tmmfoot .grow{flex:1}
.tmmnote{font:400 11px/1.55 'Geist';color:var(--faint);margin-top:12px}
.tmmseat{display:flex;align-items:center;gap:8px;margin-top:14px;padding:10px 12px;border-radius:10px;
  background:var(--subtle-alt);border:1px solid var(--bd-faint)}
.tmmseat .d{display:flex;gap:4px}
.tmmseat .d i{width:18px;height:18px;border-radius:6px;border:1px dashed rgba(240,240,240,.18);display:block}
.tmmseat .d i.taken{border:0;background:var(--acc)}
.tmmseat span{font:400 11px 'Geist';color:var(--dim)}
/* resend / revoke on a pending row */
.tmpendacts{display:flex;align-items:center;gap:4px;flex:none}
.tmpendacts button{background:0;border:0;color:var(--dim);cursor:pointer;font:600 10.5px 'Geist';
  padding:5px 7px;border-radius:6px}
.tmpendacts button:hover{color:var(--tx);background:rgba(240,240,240,.06)}
/* Remove-from-roster. ALWAYS VISIBLE.
   This first shipped hover-revealed (opacity:0 until :hover) to keep the list
   calm. That was wrong: it was reported as "I still don't see how to remove the
   person" twice, by the person who owns the team. Hover-to-discover fails anyone
   who does not already know the control exists — which is everyone, once. A
   destructive action can be quiet without being hidden, so it sits at reduced
   contrast and only turns red on hover. */
.tmrowx{background:0;border:0;color:var(--dim);cursor:pointer;padding:5px 6px;border-radius:7px;
  flex:none;display:flex;align-items:center;gap:5px;font:600 10.5px 'Geist'}
.tmrowx svg{width:14px;height:14px;display:block}
.tmrowx:hover{color:var(--rec);background:rgba(224,80,73,.1)}
.tmrowx:focus-visible{outline:1px solid var(--bd2)}
"""


def _nav(icon, label, sid, badge=""):
    b = f'<span class="nbadge" id="badge-{sid}">{badge}</span>' if badge != "" else ""
    return (f'<button class="navitem" data-screen="{sid}">'
            f'<span class="nico">{_svg(icon)}</span><span>{label}</span>{b}</button>')


def flume_html() -> str:
    import sys as _sys_early
    _is_win_early = _sys_early.platform == "win32"
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
        {_nav("team","Team","team")}
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
        <div class="siHeadline">Speak on your phone.<br>Land on <span class="acc">your {'PC' if _is_win_early else 'Mac'}.</span></div>
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
      <section class="screen" id="scr-notes" hidden><div class="nbgrid" id="notesMain"></div></section>
      <section class="screen" id="scr-meetings" hidden><div class="main" id="meetingsMain"></div></section>
      <section class="screen" id="scr-insights" hidden><div class="main" id="insightsMain"></div></section>
      <section class="screen" id="scr-dictionary" hidden><div class="main" id="dictionaryMain"></div></section>
      <section class="screen" id="scr-snippets" hidden><div class="main" id="snippetsMain"></div></section>
      <section class="screen" id="scr-devices" hidden><div class="main" id="devicesMain"></div></section>
      <section class="screen" id="scr-team" hidden><div class="teampane" id="teamMain"></div></section>
      <section class="screen" id="scr-settings" hidden><div class="main" id="settingsMain"></div></section>
    </div>
    <!-- Modal host: a sibling of .app, not a child, so a modal is never clipped by
         the grid's pinned 100vh row (conventions #23's height chain). -->
    <div id="tmModalHost"></div>"""

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

// ── In-dashboard update flow (IDI-224 follow-up) ─────────────────────────────
// Separate from the native menu-bar alert (main.py's _show_update_prompt),
// which keeps working independently — this polls the SAME backend state so
// whichever one finds an update, both can end up showing it. UPDATE_DISMISSED
// is local-only (not persisted): reopening the dashboard re-shows the banner
// for a version you clicked "Later" on, same as the native path's badge does.
let UPDATE_STATE=null, UPDATE_DISMISSED=null, UPDATE_POLL=null;
function pollUpdateStatus(){
  api('get_update_status').then(r=>{
    if(!r || !r.ok) return;
    UPDATE_STATE = r;
    renderUpdateBanner();
    if(ACTIVE==='settings' && SETTINGS_GROUP==='updates') renderSettings();
  });
}
function startUpdateBannerPolling(){
  pollUpdateStatus();
  if(UPDATE_POLL) clearInterval(UPDATE_POLL);
  UPDATE_POLL = setInterval(pollUpdateStatus, 30000);
}
function renderUpdateBanner(){
  let el = document.getElementById('update-banner');
  const avail = UPDATE_STATE && UPDATE_STATE.available;
  const dismissed = avail && UPDATE_DISMISSED===avail.version && UPDATE_STATE.phase==='idle';
  if(!avail || dismissed){ if(el) el.remove(); return; }
  if(!el){ el=document.createElement('div'); el.id='update-banner'; document.body.appendChild(el); }
  const v = esc(avail.version), phase = UPDATE_STATE.phase;
  if(phase==='downloading'){
    const pct = Math.round((UPDATE_STATE.progress||0)*100);
    el.innerHTML = `<div class="ub-text">Downloading Flume ${v}… ${pct}%<div class="ub-bar"><i style="width:${pct}%"></i></div></div>`;
  } else if(phase==='ready'){
    el.innerHTML = `<div class="ub-text">Flume ${v} is ready to install.</div>
      <div class="ub-actions"><button class="primary" onclick="installReadyUpdate()">Restart to update</button></div>`;
  } else if(phase==='installing'){
    el.innerHTML = `<div class="ub-text">Installing — Flume will restart in a moment…</div>`;
  } else if(phase==='failed'){
    el.innerHTML = `<div class="ub-text">Couldn't download Flume ${v}.</div>
      <div class="ub-actions"><button class="primary" onclick="startUpdateDownload()">Retry</button>
      <button class="ghost" onclick="dismissUpdateBanner('${esc(avail.version)}')">Later</button></div>`;
  } else {
    el.innerHTML = `<div class="ub-text">Flume ${v} is available.</div>
      <div class="ub-actions"><button class="primary" onclick="startUpdateDownload()">Update</button>
      <button class="ghost" onclick="dismissUpdateBanner('${esc(avail.version)}')">Later</button></div>`;
  }
}
function startUpdateDownload(){
  if(!UPDATE_STATE) return;
  UPDATE_STATE.phase='downloading'; UPDATE_STATE.progress=0;
  renderUpdateBanner();
  api('start_update_download').then(pollUpdateStatus);
}
function installReadyUpdate(){
  if(UPDATE_STATE) UPDATE_STATE.phase='installing';
  renderUpdateBanner();
  // The app process exits as part of this call (mounts the update, replaces
  // the bundle, relaunches) — nothing left to do here once it's fired.
  api('install_ready_update');
}
function dismissUpdateBanner(version){ UPDATE_DISMISSED=version; renderUpdateBanner(); }
// check_for_updates is SYNCHRONOUS on the Python side (bounded, ~8 s) and its
// reply carries {available, version}. It used to fire-and-forget while this
// side waited a fixed 1.5 s and then read UPDATE_STATE — which pollUpdateStatus
// only fills in asynchronously, so a slow Supabase round-trip toasted "You're
// up to date" for the very click that was asking (2026-08-26, Windows 1.0.33
// never seeing 1.0.34). Decide from the reply, then refresh the banner.
function checkForUpdatesNow(){
  toast('Checking for updates…');
  api('check_for_updates').then(r=>{
    pollUpdateStatus();
    if(r && r.ok===false){ toast(r.error || "Couldn't check for updates"); return; }
    if(!(r && r.available)) toast("You're up to date");
  });
}
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
  // Notes runs full-bleed: entering it collapses the app sidebar (fresh each
  // visit); the hamburger in the Notes pane toggles it back. Every other
  // screen restores the sidebar.
  if((id==='notes'||id==='meetings') && ACTIVE!==id){ NAV_OPEN=false; STUDIO_FIT_TRIED=false; }
  if(ACTIVE==='notes' && id!=='notes') abortDictationIfLive();
  ACTIVE=id;
  applyNavCollapse();
  document.querySelectorAll('.screen').forEach(s=>s.hidden=(s.id!=='scr-'+id));
  document.querySelectorAll('#wsnav .navitem').forEach(b=>b.classList.toggle('active',b.dataset.screen===id));
  renderActive();
  // Meetings finish in a separate window — refresh the list whenever the user
  // lands somewhere that displays it (stale-list bug).
  if(id==='meetings' || id==='home') loadMeets();
  if(id==='insights') loadInsights();
  // The team cache is refreshed from the network on every visit, not once:
  // membership, roles and the shared dictionary all change from other people's
  // devices, so a load-once guard would show a stale roster indefinitely.
  if(id==='team') loadTeam(true);
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
    else if(ACTIVE==='team') renderTeam();
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
  const target = STATE.target_device_id||'__all__';
  document.getElementById('sideDevices').innerHTML = devs.length
    ? devs.map(d=>`<div class="devrow${d.online?'':' off'}" onclick="toggleSyncPop(event,this)">
        <span class="ddot${d.online?' on':''}"></span>${esc(d.device_name||'Device')}
        ${d.device_id===target?'<span class="dtgt">SYNC</span>':''}</div>`).join('')
    : `<div class="devrow" onclick="toggleSyncPop(event,this)"><span class="ddot on"></span>${THIS_DEVICE}</div>`;
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
// Ask-your-meetings (v4): the notes-style inline answer card, fed from the
// SEARCH field on Enter. MEET_ASK_SCOPE (set by the Studio "Ask this meeting"
// card) narrows the context to one meeting.
let MEET_ASK=null, MEET_ASK_SCOPE=null;
function renderMeetAsk(){
  const box=document.getElementById('meetAsk'); if(!box) return;
  if(!MEET_ASK){
    box.innerHTML = MEET_ASK_SCOPE
      ? `<div class="spkchip" role="button" tabindex="0" onclick="clearAskScope()" title="Asking about one meeting — click to widen">ASKING THIS MEETING ONLY <span style="color:var(--sub)">✕</span></div>`
      : '';
    return;
  }
  if(MEET_ASK.busy){
    box.innerHTML=`<div class="askNote"><div class="aq">${esc(MEET_ASK.q)}</div><div class="aa" style="color:var(--mut)">Thinking…</div></div>`;
    return;
  }
  const src=(MEET_ASK.sources||[]).length?`<div class="asrc">FROM: ${esc(MEET_ASK.sources.join(' · '))}</div>`:'';
  box.innerHTML=`<div class="askNote" role="status">
    <button class="ax" aria-label="Dismiss answer" onclick="MEET_ASK=null;renderMeetAsk()">✕</button>
    <div class="aq">${esc(MEET_ASK.q)}${MEET_ASK.scoped?' · THIS MEETING':''}</div>
    <div class="aa">${esc(MEET_ASK.answer||'')}</div>${src}</div>`;
}
function clearAskScope(){ MEET_ASK_SCOPE=null; renderMeetAsk(); const i=document.getElementById('meetSearch'); if(i){ i.placeholder='Search or ask your meetings…'; } }
function askMeetings(){
  const inp=document.getElementById('meetSearch');
  const q=(inp && inp.value || '').trim();
  if(!q || (MEET_ASK&&MEET_ASK.busy)) return;
  const scoped = MEET_ASK_SCOPE;
  MEET_ASK={q:q, busy:true, scoped:!!scoped};
  renderMeetAsk();
  busyGuard('askmeet', ()=>api('ask_meetings', q, scoped||null)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok) MEET_ASK={q:q, answer:r.answer, sources:r.sources||[], scoped:!!scoped};
    else MEET_ASK={q:q, answer:(r&&r.error)||'Could not get an answer — try again.', sources:[], scoped:!!scoped};
    renderMeetAsk();
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
  const devs = STATE.devices||[];
  const target = STATE.target_device_id||'__all__';
  document.getElementById('homeMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Welcome back</div><h1 class="title">${esc(name)}</h1>
      <div class="homeSyncPill" onclick="toggleSyncPop(event,this)" title="Change where dictation lands">
        <span class="tdot"></span>Sync: ${esc(syncTargetLabel(target, devs))}</div>
    </div>${statusPill()}</div>
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
let INS=null, INS_REFRESHED=false, INS_APPWIN='30';
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
  L.push('My Flume insights —');
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
  const apps=((INS_APPWIN==='all' ? INS.apps_all : INS.apps)||[]);
  const appsTotal=apps.reduce((a,b)=>a+b.words,0)||1;
  const cols=['#C85A3E','#a84b33','#a84b33','#7a4030','#7a4030','#7a4030','#7a4030'];
  const appsHtml = apps.length ? apps.map((a,i)=>{
      const sub = a.count
        ? `${fmtN(a.count)} dictation${a.count===1?'':'s'}${a.avg?` &middot; avg ${a.avg} words`:''}`
        : '';
      return `
      <div class="insabar"><div class="arow"><span class="an">${esc(a.name)}</span><span class="av">${fmtK(a.words)} &middot; ${a.pct}%</span></div>
      <div class="atr"><i style="width:${Math.max(1,Math.round(a.words/appsTotal*100))}%;background:${cols[i]||cols[6]}"></i></div>
      ${sub?`<div class="asub">${sub}</div>`:''}</div>`;
    }).join('')
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
        <div class="inssub">Where you dictate
          <span class="insseg">
            <button class="${INS_APPWIN==='30'?'on':''}" onclick="INS_APPWIN='30';renderInsights()">30 days</button>
            <button class="${INS_APPWIN==='all'?'on':''}" onclick="INS_APPWIN='all';renderInsights()">All time</button>
          </span></div>
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
// ── Canvas — D1 two-pane redesign (2026-08-17) ────────────────────────────────
// Left: a DRAFT composer (persists locally as you type; "Send to devices" is
// the one write) + a device-local activity log. Right: the LIVE slot — what the
// one shared row holds now, who put it there, how fresh — with Copy / Save as
// note / Clear. The backend keeps ONE row and no history; the log is honest
// about being this device's own record (localStorage, bounded).
let CV_LOG=[], CV_EXPAND=false;
try{ const v=JSON.parse(localStorage.getItem('flumeCanvasLog')||'[]'); if(Array.isArray(v)) CV_LOG=v; }catch(e){}
function cvLog(kind, text, from, own){
  const top=CV_LOG[0];
  if(top && top.text===text && top.kind===kind) return;
  CV_LOG=[{id:Date.now(), kind, text:String(text||'').slice(0,500), from:from||'', own:!!own,
           at:new Date().toISOString()}, ...CV_LOG].slice(0,20);
  try{ localStorage.setItem('flumeCanvasLog', JSON.stringify(CV_LOG)); }catch(e){}
}
function cvRel(iso){
  if(!iso) return '';
  const t=Date.parse(iso); if(isNaN(t)) return '';
  const m=Math.round((Date.now()-t)/60000);
  if(m<1) return 'just now';
  if(m<60) return m+' min ago';
  const h=Math.round(m/60);
  if(h<24) return h+'h ago';
  const d=Math.round(h/24);
  return d===1?'yesterday':d+' days ago';
}
const cvIsUrl = s => /^https?:\/\/\S+$/i.test(String(s||'').trim());
function cvDraft(){ try{ return localStorage.getItem('flumeCanvasDraft')||''; }catch(e){ return ''; } }
function cvDraftSave(){ const a=document.getElementById('canvasArea');
  if(a){ try{ localStorage.setItem('flumeCanvasDraft', a.value); }catch(e){} } }
function renderCanvas(){
  const devs=((STATE&&STATE.devices)||[]).slice(0,4).map(d=>
    `<span class="cvdev"><span class="ddot${d.online?' on':''}"></span>${esc(d.device_name||'Device')}</span>`).join('')
    || '<span class="cvdev muted">no other devices online</span>';
  // Live slot
  let liveBody='';
  const from = CANVAS.own ? THIS_DEVICE : (CANVAS.from || '');
  const when = CANVAS.at ? cvRel(CANVAS.at) : '';
  if(!(CANVAS.content||'').trim() && !CANVAS.image_url){
    liveBody = '<div class="cvempty">Nothing shared right now — whatever you send lands on every device instantly.</div>';
  } else {
    const img = CANVAS.image_url
      ? `<div class="cvimgwrap"><img class="cvimg" src="${esc(CANVAS.image_url)}"/><button class="cvimgx" title="Remove image" onclick="clearCanvasImage()">✕</button></div>` : '';
    const words = (CANVAS.content||'').trim() ? words_count(CANVAS.content) : 0;
    const txt = (CANVAS.content||'').trim()
      ? `<div class="cvlivetx${CV_EXPAND?' open':''}">${esc(CANVAS.content)}</div>`
        +(words>60 && !CV_EXPAND ? `<span class="cvmore" onclick="CV_EXPAND=true;renderCanvas()">Show all</span>`
          : (CV_EXPAND?`<span class="cvmore" onclick="CV_EXPAND=false;renderCanvas()">Show less</span>`:''))
      : '';
    liveBody = `
      <div class="cvorg"><span class="cvav">${esc((from||'?')[0]).toUpperCase()}</span>
        <span class="cvwho">${esc(from||'Unknown device')}</span>
        <span class="cvwhen">${esc(when ? when.toUpperCase() : '')}${words?` · ${words} WORDS`:''}</span></div>
      ${img}${txt}
      <div class="cvacts">
        <button class="btn primary" style="flex:none" onclick="cvCopyLive(this)">${SVG.copy}Copy</button>
        <button class="btn ghost" style="flex:none" onclick="cvSaveNote(this)">Save as note</button>
        <button class="btn ghost" style="flex:none" onclick="clearCanvas(this)">Clear canvas</button>
      </div>`;
  }
  // Activity (device-local)
  const logRows = CV_LOG.length ? CV_LOG.map(e=>`
    <div class="cvrow">
      <span class="cvric">${e.kind==='image'?SVG.grid:(e.kind==='link'?SVG.bolt:SVG.lines)}</span>
      <div class="cvrtx"><div class="cvr1">${esc(e.text)}</div>
        <div class="cvr2">${esc(cvRel(e.at))} · ${e.own?('from this '+DEVICE_NOUN):('from '+esc(e.from||'another device'))}</div></div>
      <button class="cvrcopy" title="Copy" onclick="api('copy_text', ${esc(JSON.stringify(e.text))});toast('Copied')">Copy</button>
    </div>`).join('')
    : '<div class="cvempty" style="padding:6px 0 2px">Sends and receipts will appear here.</div>';
  document.getElementById('canvasMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Shared clipboard</div><h1 class="title">Canvas</h1></div>
      <div class="cvdevs"><span class="cvdevlab">Goes to</span>${devs}
        <button class="roundbtn" title="Refresh" onclick="loadCanvas()">${SVG_REFRESH}</button></div></div>
    <div class="cvgrid">
      <div>
        <div class="inscard" style="margin-bottom:14px">
          <div class="chd">Compose <span class="csub">kept as a draft until you send</span></div>
          <textarea class="canvasArea" id="canvasArea" placeholder="Type or paste here — or paste an image (${IS_WINDOWS?'Ctrl+V':'⌘V'})…" oninput="cvDraftSave()">${esc(cvDraft())}</textarea>
          <div class="canvasBar">
            <button class="btn primary" style="flex:none" onclick="cvSendNow(this)">Send to devices</button>
            <button class="btn ghost" style="flex:none" onclick="pickCanvasImage()">Image…</button>
            <span class="cvhint">${IS_WINDOWS?'Ctrl+V':'⌘V'} pastes an image straight to the canvas</span>
          </div>
          <div class="cvmsg" id="cvMsg"></div>
        </div>
        <div class="inscard">
          <div class="chd">Activity <span class="csub">recent sends · this device's log</span></div>
          ${logRows}
        </div>
      </div>
      <div class="inscard cvlive">
        <div class="chd" style="color:var(--acc-txt)">● Live on canvas <span class="csub">every device sees this</span></div>
        ${liveBody}
      </div>
    </div>`;
}
function words_count(s){ const t=String(s||'').trim(); return t?t.split(/\s+/).length:0; }
function cvMsg(t){ const el=document.getElementById('cvMsg'); if(el) el.textContent=t||''; }
function canvasText(){ return (document.getElementById('canvasArea')||{}).value||''; }
// Send = the ONE shared-row write for text (IDI-173: text-only, never touches
// the image column). On success the draft clears and the live slot flips.
function cvSendNow(btn){
  const v=canvasText().trim();
  if(!v){ cvMsg('Nothing to send yet.'); return; }
  cvMsg('Sending…');
  busyGuard(btn || 'save_canvas', ()=>api('save_canvas', v)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ cvMsg((r.error)||'Could not send — check your connection.'); return; }
    CANVAS.content=v; CANVAS.own=true; CANVAS.from=''; CANVAS.at=new Date().toISOString();
    CV_EXPAND=false;
    cvLog(cvIsUrl(v)?'link':'text', v, '', true);
    try{ localStorage.setItem('flumeCanvasDraft',''); }catch(e){}
    renderCanvas();
    toast('Sent to your devices');
  });
}
function cvCopyLive(btn){
  const payload = (CANVAS.content||'').trim() || CANVAS.image_url || '';
  if(!payload) return;
  busyGuard(btn||'cv_copy', ()=>api('copy_text', payload)).then(()=>toast('Copied'));
}
function cvSaveNote(btn){
  const content=(CANVAS.content||'').trim();
  if(!content){ toast('Nothing to save', true); return; }
  const id='cv'+Date.now().toString(16)+Math.floor(Math.random()*1e6).toString(16);
  busyGuard(btn||'cv_note', ()=>api('save_note', {id:id, title:titleOf(content), content:content, no_cleanup:true})).then(r=>{
    if(r&&r.busy) return;
    if(r&&r.ok) toast('Saved to Notes');
    else toast((r&&r.error)||'Could not save the note', true);
  });
}
function loadCanvas(){ api('fetch_canvas').then(r=>{ if(r&&r.ok){
  CANVAS={content:r.content||'', image_url:r.image_url||null,
          from:r.device_name||CANVAS.from||'', at:r.updated_at||'', own:!!r.own};
  if(ACTIVE==='canvas')renderCanvas(); } }); }
// An explicit clear — a real write of {content:'', image_url:null} that other
// devices APPLY (they used to falsy-drop the empty content and stay stale).
function clearCanvas(btn){
  busyGuard(btn || 'clear_canvas', ()=>api('clear_canvas')).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok===false){ toast((r.error)||'Could not clear the canvas.', true); return; }
    CANVAS={content:'',image_url:null,from:'',at:new Date().toISOString(),own:true};
    CV_EXPAND=false;
    if(ACTIVE==='canvas')renderCanvas();
  });
}
// Image-only removal: keeps the LIVE text, nulls the image explicitly (IDI-173).
function clearCanvasImage(){ const v=CANVAS.content||''; api('save_canvas', v, null).then(()=>{ CANVAS.image_url=null; if(ACTIVE==='canvas')renderCanvas(); }); }
// Image sends carry the CURRENT LIVE text (never the draft — sending a photo
// must not publish half-typed text, and content:"" would clear the column).
function pickCanvasImage(){ cvMsg('Choose an image…'); api('canvas_add_image_file', CANVAS.content||'').then(applyCanvasImage); }
function pasteCanvasImage(){ cvMsg('Pasting image…'); api('canvas_paste_image', CANVAS.content||'').then(applyCanvasImage); }
function applyCanvasImage(r){
  if(r&&r.ok&&r.image_url){
    CANVAS.image_url=r.image_url; CANVAS.own=true; CANVAS.from=''; CANVAS.at=new Date().toISOString();
    cvLog('image','Image','',true);
    if(ACTIVE==='canvas')renderCanvas();
    toast('Image sent to your devices');
  }
  else if(r&&r.cancelled){ cvMsg(''); }
  else { cvMsg((r&&r.error)||'Could not add image'); }
}
// JS clipboard path (works on some WKWebView builds); native pasteCanvasImage is the reliable fallback.
function sendCanvasImage(dataUri){ api('save_canvas_image_data', dataUri, CANVAS.content||'').then(applyCanvasImage); }

let NOTE_REC=false, _noteTimer=null, _rawTimer=null, NOTE_QUERY='', SHOW_ORIG=false, NOTE_SEG_ID=null;
let NOTE_FS='m';
try{ const v=localStorage.getItem('flumeNoteFs'); if(v==='s'||v==='l') NOTE_FS=v; }catch(e){}
let NAV_OPEN=false;   // user re-opened the sidebar while on Notes (via the hamburger)
// The sidebar collapses only when a NOTE IS OPEN (alongside the Studio pane) —
// merely landing on the Notes screen keeps the navigation visible.
// A "document is open" test shared by Notes and Meetings (v4): the sidebar
// collapse, the hamburger and the window auto-grow all key off it.
function paneOpen(){
  if(ACTIVE==='notes') return !!curNote();
  if(ACTIVE==='meetings') return !!MROW;
  return false;
}
function applyNavCollapse(){
  const app=document.querySelector('.app'); if(!app) return;
  app.classList.toggle('navhide', !NAV_OPEN && paneOpen());
  const h=document.getElementById('navHamb');
  if(h){
    h.setAttribute('aria-expanded', NAV_OPEN?'true':'false');
    h.setAttribute('aria-label', NAV_OPEN?'Hide menu':'Show menu');
    h.title = NAV_OPEN?'Hide menu':'Show menu';
  }
}
function toggleNav(){ NAV_OPEN=!NAV_OPEN; applyNavCollapse(); }
const SVG_HAMB='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6.5h16M4 12h16M4 17.5h16"/></svg>';
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
// Nothing is selected by default (v3.2 — the user picks; only then do the
// editor + Studio panes light up). No fallback to the newest note.
function curNote(){ return NOTES.find(x=>x.id===SELN) || null; }
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
  const hasAny=realNotes().length>0;
  const editor = n ? noteEditorHtml(n)
    : `<div class="npaneHead"><span class="pt">Note</span></div>
       <div class="npaneBody" style="display:flex">
         <div class="nempty" style="margin:auto">
           <div class="t">${hasAny?'Pick a note':'Nothing here yet'}</div>
           <div class="s">${hasAny?'Select one from the list — or start a new one — and the editor and Studio open with it.':'Your first note will open here — dictate or type one from the left.'}</div>
         </div>
       </div>`;
  const all=realNotes();
  const weekAgo=Date.now()-7*86400000;
  const wk=all.filter(x=>{ const t=Date.parse(x.updated_at||''); return t && t>=weekAgo; }).length;
  const box=document.getElementById('notesMain');
  box.className='nbgrid'+(n?'':' nosel')+((n&&STUDIO_FORCE3)?' force3':'');
  box.innerHTML = `
    <div class="npane">
      <div class="npaneHead">
        <div style="display:flex;align-items:center;gap:10px">
          ${n?`<button class="hamb" id="navHamb" aria-label="Show menu" aria-expanded="false" onclick="toggleNav()">${SVG_HAMB}</button>`:''}
          <span class="pt">Notes</span>
        </div>
        <span class="eyebrow">${all.length} note${all.length===1?'':'s'}${wk?` · ${wk} this week`:''}</span>
      </div>
      <div class="npaneBody">
        <div class="pillrow">
          <button class="pillbtn" aria-label="New note" onclick="newNote()">${SVG.plus}New</button>
          <button class="pillbtn acc" aria-label="Dictate a new note" onclick="dictateNewNote()">${SVG.mic}Dictate</button>
          <button class="pillbtn" aria-label="Import from meetings or transcriptions" title="Import from meetings or transcriptions" onclick="openImport()">${SVG_IMPORT}Import</button>
        </div>
        ${searchBox}
        <div id="noteList"></div>
      </div>
    </div>
    <div class="npane" id="notePane">${editor}</div>
    ${n?`<div class="npane studio" id="studioPane">${studioHtml(n)}</div>`:''}`;
  applyNavCollapse();
  renderNoteList();
  renderNoteAsk();
  if(n && !SHOW_ORIG){ const b=document.getElementById('noteBody'); if(b) b.innerHTML=noteBodyHtml(n); }
  nuInit(n && !SHOW_ORIG ? n : null);
  updateDictateBtn();
  updateSegIcons();
  if(n) ensureStudioFits();
}
// The Studio column collapses under 1000px and the default window is 980 wide —
// so with a note open, GROW THE WINDOW instead of hiding the pane. Fail-closed:
// if the host can't resize, the CSS breakpoint still keeps the layout sane.
// The resize re-fires the media query, so Studio appears without a re-render.
// Fires at most ONCE per Notes visit (reset in show()) — if the user then
// shrinks the window on purpose, we don't fight them on every note click.
let STUDIO_FIT_TRIED=false, STUDIO_FORCE3=false;
function ensureStudioFits(){
  if(STUDIO_FIT_TRIED || window.innerWidth >= 1010) return;
  STUDIO_FIT_TRIED=true;
  api('ensure_window_width', 1220, 700);
  // Belt and braces: if the window did NOT grow (host without resize support,
  // or clamped by a small screen), force the three-pane grid anyway once the
  // resize has had its chance — a squeezed Studio beats a missing one.
  setTimeout(()=>{
    if(!paneOpen() || window.innerWidth >= 1010) return;
    STUDIO_FORCE3=true;
    const g=document.getElementById(ACTIVE==='meetings'?'meetingsMain':'notesMain');
    if(g) g.classList.add('force3');
  }, 600);
}
// Manual widening past the breakpoint retires the forced layout.
window.addEventListener('resize', ()=>{
  if(STUDIO_FORCE3 && window.innerWidth >= 1010){
    STUDIO_FORCE3=false;
    ['notesMain','meetingsMain'].forEach(id=>{
      const g=document.getElementById(id);
      if(g) g.classList.remove('force3');
    });
  }
});
// The Studio pane (v3.1): pastel restyle/export cards + this note's recordings
// and original-transcript row + the Add-note pill. Rebuilding it never touches
// the editor pane, so in-progress typing is safe.
function studioHtml(n){
  const dis = n ? '' : ' disabled';
  const menu = `
      <div class="nmenuwrap">
        <button class="scard slate"${dis} aria-haspopup="true" onclick="toggleNoteMenu(event,'studioExpMenu')">
          <span class="sdisc">${SVG.send}</span><span class="sl">Export</span><span class="ss">Markdown, text, clipboard</span></button>
        <div class="nmenu" id="studioExpMenu" hidden>
          <button onclick="noteCopy('txt')">${SVG.copy}Copy as text</button>
          <button onclick="noteCopy('md')">${SVG.copy}Copy as Markdown</button>
          <button onclick="noteExport('md')">Export as .md…</button>
          <button onclick="noteExport('txt')">Export as .txt…</button>
        </div></div>`;
  const cards = `<div class="scards">
      <button class="scard cream"${dis} onclick="formatNoteStyled('structured')"><span class="sdisc">${SVG.bolt}</span><span class="sl">Auto-structure</span><span class="ss">Headings &amp; checklists</span></button>
      <button class="scard sage"${dis} onclick="formatNoteStyled('prose')"><span class="sdisc">${SVG.lines}</span><span class="sl">Flowing prose</span><span class="ss">Connected paragraphs</span></button>
      <button class="scard plum"${dis} onclick="formatNoteStyled('transcript')"><span class="sdisc">${SVG.book}</span><span class="sl">Clean transcript</span><span class="ss">Keep every word</span></button>
      ${menu}
    </div>`;
  const segs = n ? (n.audio_segments||[]).filter(s=>s&&s.id) : [];
  const segRows = segs.map((s,i)=>{
    const t=(s.created_at||'').slice(11,16);
    return `<div class="srow">
      <span class="sic">${SVG.mic}</span>
      <span class="st"><span class="a">Recording ${i+1}</span><span class="b">${t?esc(t)+' · ':''}source audio</span></span>
      <button class="splay segbtn" data-id="${esc(s.id)}" aria-label="Play recording ${i+1}" onclick="noteSegPlay(this)"><span class="segic">${SVG.play}</span></button>
    </div>`;
  }).join('');
  const hasRaw = n && (n.raw_content!=null) && String(n.raw_content).trim()!=='';
  const origRow = hasRaw ? `<div class="srow" role="button" tabindex="0" onclick="toggleShowOrig()" onkeydown="if(event.key==='Enter')toggleShowOrig()">
      <span class="sic">${SVG.book}</span>
      <span class="st"><span class="a">${SHOW_ORIG?'Formatted note':'Original transcript'}</span><span class="b">${SHOW_ORIG?'Back to the clean version':'What you actually said · editable'}</span></span>
    </div>` : '';
  const rows = (origRow||segRows) ? `<div class="shead">This note</div>${origRow}${segRows}` : '';
  return `
    <div class="npaneHead"><span class="pt">Studio</span></div>
    <div class="npaneBody">${cards}${rows}</div>
    <div class="studioFoot"><button class="addpill" onclick="newNote()">${SVG.edit}Add note</button></div>`;
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
// ── Meetings v4: the Notes pane language (approved proposal, 2026-08-15) ─────
// Three floating panes — list · document · Studio — sharing the Notes screen's
// behavior contracts (no default selection, sidebar collapse with a selection,
// window auto-grow). All the detail EDITING machinery (fillMeetDetail, action
// items, hybrid notes, transcript edit, marks) is reused untouched: the pane
// keeps the same element ids the fill code writes into.
function spColor(sid, i){
  const SPCOL={self:'#D9B36B'};
  const PAL=['#D98A72','#8FA7C2','#A9BD98','#D9B36B'];
  return SPCOL[sid]||PAL[i%PAL.length];
}
function fmtHM(secs){
  const m=Math.round((secs||0)/60);
  return m>=60 ? Math.floor(m/60)+'h '+(m%60)+'m' : m+'m';
}
function renderMeetings(){
  const box=document.getElementById('meetingsMain'); if(!box) return;
  const open=!!MROW;
  box.className='nbgrid'+(open?'':' nosel');
  const all=MEETS.meetings||[];
  const total=all.reduce((a,m)=>a+(m.duration_seconds||0),0);
  const hamb = open?`<button class="hamb" id="navHamb" aria-label="Show menu" aria-expanded="false" onclick="toggleNav()">${SVG_HAMB}</button>`:'';
  const live = MEETS.active_id ? `
    <div class="mlivebar"><span class="recdot" style="width:8px;height:8px;border-radius:50%;background:#E05049;flex:none"></span>
      <span class="t">${esc(MEETS.active_title||'Meeting')}</span>
      <span class="m">${fmtDur(MEETS.active_elapsed)} · REC</span>
      <button class="pillbtn" onclick="api('open_meeting_launcher')">Return</button>
      <button class="pillbtn" onclick="stopMeeting(this)">Stop</button>
    </div>` : '';
  const center = MSUBNOTES ? meetNotesPaneHtml()
    : (open ? meetDocHtml()
    : `<div class="npaneHead"><span class="pt">Meeting</span></div>
       <div class="npaneBody" style="display:flex">
         <div class="nempty">
           <div class="t">${MEETS.active_id?'Recording in progress':'Pick a meeting'}</div>
           <div class="s">${MEETS.active_id
             ?'A meeting is being captured — open it from the bar, or read past meetings meanwhile.'
             :'Select one from the list and the summary, transcript and Studio open with it.'}</div>
         </div>
       </div>`);
  box.innerHTML = `
    <div class="npane">
      <div class="npaneHead">
        <div style="display:flex;align-items:center;gap:10px">${hamb}<span class="pt">Meetings</span></div>
        <span class="eyebrow">${all.length} meeting${all.length===1?'':'s'}${total?` · ${fmtHM(total)}`:''}</span>
      </div>
      <div class="npaneBody">
        <div class="pillrow">
          <button class="pillbtn acc" onclick="api('open_meeting_launcher')"><span class="mrecdot"></span>New meeting</button>
        </div>
        ${live}
        <div class="searchbox">${SVG.search}<input id="meetSearch" type="search" aria-label="Search meetings" placeholder="${MEET_ASK_SCOPE?'Ask this meeting…':'Search or ask your meetings…'}" value="${esc(MEET_QUERY)}" oninput="MEET_QUERY=this.value;renderMeetList()" onkeydown="if(event.key==='Enter')askMeetings()"/></div>
        <div id="meetAsk"></div>
        <div id="meetList"></div>
      </div>
    </div>
    <div class="npane" id="meetDocPane">${center}</div>
    ${open?`<div class="npane studio" id="meetStudio">${meetStudioHtml()}</div>`:''}`;
  renderMeetList();
  renderMeetAsk();
  if(open && !MSUBNOTES){ fillMeetDetail(); wirePlaybar(); }
  applyNavCollapse();
  if(open) ensureStudioFits();
  if(!MEETS_LOADED){ MEETS_LOADED=true; loadMeets(); }
}
// Rows only — re-rendered per search keystroke so the input keeps focus.
function renderMeetList(){
  const box=document.getElementById('meetList'); if(!box) return;
  const q=(MEET_QUERY||'').trim().toLowerCase();
  const all=MEETS.meetings||[];
  const ms=q?all.filter(m=>((m.title||'')+' '+(m.summary||'')).toLowerCase().includes(q)):all;
  if(!ms.length){
    box.innerHTML = q
      ? `<div class="empty">No meetings match “${esc(q)}”. Press Enter to ask AI instead.</div>`
      : `<div class="nempty" style="padding:34px 10px">
          <div class="disc">${SVG.meet}</div>
          <div class="t">No meetings yet</div>
          <div class="s">Flume captures system audio and your mic silently — no bot joins the call.</div>
          <button class="btn primary" style="width:auto" onclick="api('open_meeting_launcher')">Start your first meeting</button>
        </div>`;
    return;
  }
  function rowHtml(m){
    const spk=m.speakers||{};
    const sids=Object.keys(spk);
    const avs = sids.length
      ? sids.slice(0,3).map((sid,i)=>`<span class="mav" style="background:${spColor(sid,i)}">${esc(((spk[sid]||'?').trim().charAt(0)||'?').toUpperCase())}</span>`).join('')
      : `<span class="mav" style="background:#D9B36B">·</span>`;
    const prev = m.status==='processing' ? 'Summarizing…'
      : m.status==='failed' ? 'Summary failed — open to retry'
      : ((m.summary||'').split('\n')[0] || ((m.utterances||0)+' segments'+(m.cloud?'':' · this '+DEVICE_NOUN+' only')));
    const isNew = m.status==='ready' && (MEETS.opened||[]).indexOf(m.id)<0;
    const marks=(m.marked_moments||[]).length, acts=(m.action_items||[]).length;
    const meta=[fmtHM(m.duration_seconds)];
    if(marks) meta.push('<span class="st">★'+marks+'</span>');
    if(acts) meta.push('✓'+acts);
    return `<div class="mgrow${(MROW&&MROW.id===m.id)?' active':''}" role="button" tabindex="0"
        onclick="api('open_meeting', ${esc(JSON.stringify(m.id))})"
        onkeydown="if(event.key==='Enter')api('open_meeting', ${esc(JSON.stringify(m.id))})">
      <span class="mavs">${avs}</span>
      <span class="mgmid">
        <span class="mgtitle">${isNew?'<span class="mgnew"></span>':''}${m.pinned?'<span style="color:var(--acc)">★</span>':''}${esc(m.title||'Meeting')}</span>
        <span class="mgprev">${esc(prev)}</span>
      </span>
      <span class="mgside"><span class="mgtime">${esc(noteDateLabel(m.started_at))}</span><span class="mgmeta">${meta.join(' · ')}</span></span>
    </div>`;
  }
  const pinned=ms.filter(m=>m.pinned), rest=ms.filter(m=>!m.pinned);
  let html='';
  if(pinned.length) html+=`<div class="ngroup">Pinned</div><div class="mgrp">${pinned.map(rowHtml).join('')}</div>`;
  let last='', buf=[];
  const flush=()=>{ if(buf.length){ html+=`<div class="ngroup">${last}</div><div class="mgrp">${buf.join('')}</div>`; buf=[]; } };
  rest.forEach(m=>{
    const g=meetGroup(m);
    if(g!==last){ flush(); last=g; }
    buf.push(rowHtml(m));
  });
  flush();
  box.innerHTML=html;
}
// ── the document pane (center): summary → decisions → actions → notes →
// marks/transcript expanders, with the playback bar at the bottom. Element ids
// match what fillMeetDetail() has always written into.
function meetDocHtml(){
  const m=MROW;
  return `
    <div class="npaneHead">
      <span class="pt">Meeting</span>
      <div class="notetoolbar">
        <span class="hnTabs">
          <button class="hnTab" data-hnv="yours" onclick="hnView('yours')">Yours</button>
          <button class="hnTab${HNVIEW==='merged'?' on':''}" data-hnv="merged" onclick="hnView('merged')">Merged</button>
          <button class="hnTab" data-hnv="ai" onclick="hnView('ai')">AI</button>
        </span>
        <button class="fmtbtn${m.pinned?' pinned':''}" id="meetPinBtn" title="${m.pinned?'Unpin meeting':'Pin meeting'}" aria-pressed="${m.pinned?'true':'false'}" onclick="meetPinToggle()">${m.pinned?'★':'☆'}</button>
        <button class="fmtbtn" title="Copy summary to clipboard" onclick="sumShare(this)">${SVG.copy}</button>
        <span class="nmenuwrap">
          <button class="fmtbtn" title="More actions" aria-haspopup="true" onclick="toggleNoteMenu(event,'meetMoreMenu')">${SVG.dots}</button>
          <div class="nmenu" id="meetMoreMenu" hidden>
            <button onclick="sumRegen()">${SVG_REFRESH}Regenerate summary</button>
            <div class="nmsep"></div>
            <button class="danger" onclick="meetDeleteCurrent()">${SVG.trash}Delete meeting</button>
          </div></span>
      </div>
    </div>
    <div class="npaneBody edscroll">
      <div id="mtgDetail" class="show">
        <span class="eyebrow" id="sumEyebrow" style="display:none"></span>
        <input class="sumTitle" id="sumTitle" value="" spellcheck="false" aria-label="Meeting title" onchange="mtgTitle(this.value)"/>
        <div class="sumMeta" id="sumMeta"></div>
        <div id="sumBody" class="mdocsum"></div>
        <div class="mdocsec">Decisions</div>
        <div id="decBody"></div>
        <div class="mdocsec">Action items</div>
        <div id="aiBody"></div>
        <div class="mdocsec">Notes
          <span class="legend"><span class="lu"><i></i>Your notes</span><span class="la"><i></i>AI additions</span></span>
          <button class="btnS mini" title="Full AI notes of this meeting" onclick="openNotes()">Open notes &#8599;</button>
        </div>
        <div id="hnBody"></div>
        <div class="teasers">
          <div class="teaser" onclick="toggleBox('marksBox', renderMarksBox)">${SVG.bolt}<span class="tl" id="marksTeaseL">Marked moments</span><span class="eyebrow">Expand</span></div>
          <div class="teaser" onclick="toggleBox('txBox', renderTxBox)">${SVG.search}<span class="tl" id="txTeaseL">Full transcript</span><span class="eyebrow">Expand</span></div>
        </div>
        <div class="card expandBox" id="marksBox"></div>
        <div class="card expandBox" id="txBox"></div>
      </div>
    </div>
    ${meetPlaybarHtml()}
    <audio id="sumAudio"></audio>`;
}
// ── the Studio pane: pastel actions, speakers-with-filter, this-meeting rows ──
function speakerStats(m){
  const spk=(m&&m.speakers)||{};
  const ids=Object.keys(spk);
  const dur={};
  ((m&&m.transcript)||[]).forEach(u=>{ dur[u.speaker]=(dur[u.speaker]||0)+Math.max(0,(u.t1||0)-(u.t0||0)); });
  const tot=Object.keys(dur).reduce((a,k)=>a+dur[k],0)||0;
  return ids.map((sid,i)=>({
    sid:sid, name:spk[sid]||sid, color:spColor(sid,i),
    secs:dur[sid]||0, pct: tot? Math.round(100*(dur[sid]||0)/tot) : 0,
  }));
}
function meetStudioHtml(){
  const m=MROW; if(!m) return '';
  const stats=speakerStats(m);
  const spkRows=stats.map(s=>`
    <button class="spkrow${MSPK===s.sid?' on':''}" aria-pressed="${MSPK===s.sid?'true':'false'}"
        title="Show only ${esc(s.name)}'s lines · double-click to rename"
        onclick="spkFilter(${esc(JSON.stringify(s.sid))})"
        ondblclick="event.stopPropagation();sumRename(${esc(JSON.stringify(s.sid))}, this)">
      <span class="sav" style="background:${s.color}">${esc(((s.name||'?').trim().charAt(0)||'?').toUpperCase())}</span>
      <span class="sn"><span class="a">${esc(s.name)}</span><span class="b">${Math.round(s.secs/60)} MIN · ${s.pct}%</span></span>
      <span class="share"><i style="width:${s.pct}%;background:${s.color}"></i></span>
    </button>`).join('');
  const filt=stats.find(s=>s.sid===MSPK);
  const marks=(m.marked_moments||[]).length;
  return `
    <div class="npaneHead"><span class="pt">Studio</span></div>
    <div class="npaneBody">
      <div class="scards">
        <button class="scard cream" onclick="openNotes()"><span class="sdisc">${SVG.book}</span><span class="sl">AI Notes</span><span class="ss">The full notes page</span></button>
        <button class="scard sage" onclick="sumRegen()"><span class="sdisc">${SVG_REFRESH}</span><span class="sl">Regenerate</span><span class="ss">Re-run the summary</span></button>
        <button class="scard plum" onclick="askThisMeeting()"><span class="sdisc">${SVG.search}</span><span class="sl">Ask this meeting</span><span class="ss">Who said what, when</span></button>
        <div class="nmenuwrap">
          <button class="scard slate" aria-haspopup="true" onclick="toggleNoteMenu(event,'meetExpMenu')"><span class="sdisc">${SVG.send}</span><span class="sl">Export</span><span class="ss">Markdown, text, note</span></button>
          <div class="nmenu" id="meetExpMenu" hidden>
            <button onclick="sumShare(this)">${SVG.copy}Copy summary</button>
            <button id="expMdBtn" onclick="sumExport('md')">Export as .md…</button>
            <button id="expTxtBtn" onclick="sumExport('txt')">Export as .txt…</button>
            <div class="nmsep"></div>
            <button onclick="sendMeetingToNotes()">${SVG_IMPORT}Send to Notes</button>
          </div></div>
      </div>
      ${stats.length?`<div class="shead">Speakers · tap to filter</div>${spkRows}
        ${filt?`<div class="spkhint">Showing only ${esc(filt.name)}'s lines in the transcript — tap again for everyone.</div>`:''}`:''}
      <div class="shead" style="margin-top:14px">This meeting</div>
      <div class="srow" role="button" tabindex="0" onclick="toggleBox('marksBox', renderMarksBox)" onkeydown="if(event.key==='Enter')toggleBox('marksBox', renderMarksBox)">
        <span class="sic">★</span><span class="st"><span class="a">Marked moments</span><span class="b">${marks} · jump to transcript</span></span></div>
      <div class="srow" role="button" tabindex="0" onclick="sendMeetingToNotes()" onkeydown="if(event.key==='Enter')sendMeetingToNotes()">
        <span class="sic">${SVG_IMPORT}</span><span class="st"><span class="a">Send to Notes</span><span class="b">Import as an editable note</span></span></div>
    </div>
    <div class="studioFoot"><button class="addpill" onclick="api('open_meeting_launcher')"><span class="rd"></span>New meeting</button></div>`;
}
function meetPinToggle(){
  if(!MROW) return;
  const on=!MROW.pinned;
  MROW.pinned=on;
  (MEETS.meetings||[]).forEach(x=>{ if(x.id===MROW.id) x.pinned=on; });
  const b=document.getElementById('meetPinBtn');
  if(b){ b.className='fmtbtn'+(on?' pinned':''); b.textContent=on?'★':'☆'; b.title=on?'Unpin meeting':'Pin meeting'; }
  renderMeetList();
  api('set_meeting_pinned', MROW.id, on).then(r=>{
    if(r && r.ok===false){ MROW.pinned=!on; renderMeetList(); toast((r.error)||'Could not update the pin.', true); }
  });
}
function meetDeleteCurrent(){
  if(!MROW) return;
  deleteMeeting(MROW.id, MROW.title||'Meeting', null);
}
function askThisMeeting(){
  if(!MROW) return;
  MEET_ASK_SCOPE=MROW.id;
  renderMeetAsk();
  const i=document.getElementById('meetSearch');
  if(i){ i.placeholder='Ask this meeting…'; i.focus(); }
}
// Send to Notes — the Notes import pointed the other way (v4).
function sendMeetingToNotes(){
  const m=MROW; if(!m) return;
  const c=meetingNoteMarkdown(m);
  if(!c){ toast('This meeting has no content to send yet.', true); return; }
  busyGuard('send2notes', ()=>api('save_note', {title:c.title, content:c.content})).then(r=>{
    if(r && r.busy) return;
    if(!(r&&r.ok)){ toast('Could not create the note — try again.', true); return; }
    NOTES=r.notes||NOTES; SELN=r.id||SELN; NOTE_QUERY=''; NOTE_ASK=null; SHOW_ORIG=false;
    navTo('notes');
  });
}
// ── speaker filter (v4): tap a Studio speaker → only their transcript lines ──
function spkFilter(sid){
  MSPK = (MSPK===sid) ? null : sid;
  const st=document.getElementById('meetStudio');
  if(st) st.innerHTML=meetStudioHtml();
  const tx=document.getElementById('txBox');
  if(MSPK && tx && !tx.classList.contains('show')) toggleBox('txBox', renderTxBox);
  else renderTxBox();
}
// ── playback bar — the dictation bar's twin ──────────────────────────────────
function meetPlaybarHtml(){
  const m=MROW;
  const dis=!!(m && m.audio_expired);
  let bars='';
  for(let i=0;i<34;i++){ bars+='<i style="height:'+(5+((i*7919)%13))+'px"></i>'; }
  return `<div class="playbar${dis?' off':''}" id="meetPlaybar"${dis?' title="Audio expired — notes and transcript kept"':''}>
    <button class="pfab" id="pbFabBtn" aria-label="Play recording" onclick="pbFab()">${SVG.play}</button>
    <div class="pwave" id="pbWaveEl" aria-hidden="true" onclick="pbSeek(event)">${bars}</div>
    <span class="ptime" id="pbTime">0:00 / ${fmtMT(m?m.duration_seconds:0)}</span>
    <button class="pspeed" id="pbSpeed" title="Playback speed" onclick="pbSpeed()">${MRATE}×</button>
  </div>`;
}
function wirePlaybar(){
  const a=document.getElementById('sumAudio'); if(!a) return;
  a.playbackRate=MRATE;
  a.addEventListener('play', updPB);
  a.addEventListener('pause', updPB);
  a.addEventListener('ended', updPB);
  a.addEventListener('timeupdate', pbTick);
}
function updPB(){
  const a=document.getElementById('sumAudio');
  const f=document.getElementById('pbFabBtn');
  if(f && a){
    f.innerHTML=(!a.paused)?SVG_PAUSE:SVG.play;
    f.setAttribute('aria-label', (!a.paused)?'Pause':'Play recording');
    a.playbackRate=MRATE;
  }
}
function pbTick(){
  const a=document.getElementById('sumAudio'); if(!a||!MROW) return;
  const dur=MROW.duration_seconds||a.duration||0;
  const t=a.currentTime||0;
  const tl=document.getElementById('pbTime');
  if(tl) tl.textContent=fmtMT(t)+' / '+fmtMT(dur);
  const w=document.getElementById('pbWaveEl');
  if(w && dur>0){
    const bars=w.children, n=bars.length, k=Math.round(n*Math.min(1,t/dur));
    for(let i=0;i<n;i++) bars[i].classList.toggle('played', i<k);
  }
  // follow the playhead through the transcript while it's open
  const tx=document.getElementById('txBox');
  if(tx && tx.classList.contains('show')){
    const segs=MROW.transcript||[];
    let best=-1;
    for(let i=0;i<segs.length;i++){ if((segs[i].t0||0)<=t) best=i; else break; }
    if(best>=0 && best!==MPLAYING) markPlaying(best);
  }
}
function pbFab(){
  if(MROW && MROW.audio_expired) return;
  const a=document.getElementById('sumAudio'); if(!a) return;
  if(!MAUDIO_SRC){ playAt(0,-1); return; }
  if(a.paused) a.play().catch(()=>{}); else a.pause();
}
function pbSeek(ev){
  if(!MROW || MROW.audio_expired) return;
  const w=document.getElementById('pbWaveEl'); if(!w) return;
  const r=w.getBoundingClientRect();
  const pct=Math.max(0, Math.min(1, (ev.clientX-r.left)/Math.max(1,r.width)));
  playAt(pct*(MROW.duration_seconds||0), -1);
}
function pbSpeed(){
  MRATE = MRATE===1 ? 1.5 : (MRATE===1.5 ? 2 : 1);
  const a=document.getElementById('sumAudio'); if(a) a.playbackRate=MRATE;
  const b=document.getElementById('pbSpeed'); if(b) b.textContent=MRATE+'×';
}
function pinMeeting(id, on, btn){
  busyGuard(btn || ('pin:'+id), ()=>api('set_meeting_pinned', id, on)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok){
      (MEETS.meetings||[]).forEach(m=>{ if(m.id===id) m.pinned=on; });
      renderMeetList();
    } else if(r && r.ok===false){ toast((r.error)||'Could not update the pin.', true); }
  });
}
// Deleting a meeting is irreversible (row + transcript + audio) and was ONE
// click away. Confirm first, same shape as deleteAccount (IDI-167).
function deleteMeeting(id, title, btn){
  if(!confirm('Delete “'+(title||'this meeting')+'”?\n\nIts transcript, notes and recording are permanently removed. This cannot be undone.')) return;
  busyGuard(btn || ('delmeet:'+id), ()=>api('delete_meeting', id)).then(r=>{
    if(r && r.busy) return;
    if(r && r.ok){
      MEETS.meetings=(MEETS.meetings||[]).filter(m=>m.id!==id);
      if(MROW && MROW.id===id){ MROW=null; MVIEW='list'; MSUBNOTES=false; MSPK=null; MEET_ASK_SCOPE=null; }
      renderActive();
    }
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
let MSPK=null;   // v4 speaker filter: speaker id or null (everyone)
let MRATE=1;     // v4 playbar speed: 1 | 1.5 | 2
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
  mntAbandon();
  MROW=row; MVIEW='detail'; MSUBNOTES=false;
  MAUDIO_SRC=null; MPLAYING=-1; MDEL_ARMED=null; MSPK=null; MRATE=1; MEET_ASK_SCOPE=null;
  if(ACTIVE!=='meetings') show('meetings');   // show() renders the screen itself
  else renderMeetings();
}
function meetBack(){
  mntAbandon();
  MVIEW='list'; MROW=null; MSUBNOTES=false; MSPK=null; MEET_ASK_SCOPE=null;
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
// (renderMeetDetail was replaced by meetDocHtml — the v4 pane shell keeps the
// same element ids, so fillMeetDetail() below is unchanged.)
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
  // v4: the notes sub-page lives in the CENTER pane; renderMeetings routes to
  // meetNotesPaneHtml() when MSUBNOTES is set. Kept as the openNotes entry.
  renderMeetings();
}
function meetNotesPaneHtml(){
  const body = MNT_EDIT
    ? `<textarea class="ntEdit" id="ntEdit" aria-label="Edit meeting notes (markdown)" spellcheck="false" oninput="mntChanged()">${esc((MROW&&MROW.notes_md)||'')}</textarea>`
    : `<div class="ntSkel" id="ntSkel" style="display:none"><i style="width:38%"></i><i style="width:92%"></i><i style="width:85%"></i><i style="width:60%"></i><i style="width:88%"></i><i style="width:74%"></i></div>
       <div class="ntErr" id="ntErr" style="display:none"></div>
       <div class="ntBody" id="ntBody"></div>`;
  return `
    <div class="npaneHead">
      <span class="pt">AI Notes</span>
      <div class="notetoolbar">
        <button class="fmtbtn ftxt" title="Back to the summary" onclick="notesBack()">&#8249; Summary</button>
        <span class="notesave" id="mntState"></span>
        <button class="fmtbtn${MNT_EDIT?' pinned':''}" id="mntEditBtn" title="${MNT_EDIT?'Done editing':'Edit the notes (markdown)'}" aria-pressed="${MNT_EDIT?'true':'false'}" onclick="mntToggleEdit()">${MNT_EDIT?'✓':SVG.edit}</button>
        <button class="fmtbtn" title="Copy notes as Markdown" onclick="notesCopy(this)">${SVG.copy}</button>
        <button class="fmtbtn" title="Regenerate notes" onclick="mntRegen()">${SVG_REFRESH}</button>
      </div>
    </div>
    <div class="npaneBody edscroll">
      <div id="mtgDetail" class="show"><div id="mtgNotes" class="show">
        <div class="ntTitle" style="margin-bottom:10px">${esc((MROW&&MROW.title||'Meeting')+' — notes')}</div>
        ${body}
      </div></div>
    </div>`;
}
// ── editable AI notes (v4.1) — raw-markdown edit mode, debounced persist via
// set_meeting_notes (the desktop twin of mobile's MeetingNotesScreen editor).
let MNT_EDIT=false, _mntTimer=null;
function setMntState(t){ const el=document.getElementById('mntState'); if(el) el.textContent=t; }
function mntChanged(){
  const ta=document.getElementById('ntEdit'); if(!ta||!MROW) return;
  MROW.notes_md=ta.value;
  setMntState('Saving…');
  if(_mntTimer) clearTimeout(_mntTimer);
  _mntTimer=setTimeout(mntFlush, 800);
}
function mntFlush(){
  if(_mntTimer){ clearTimeout(_mntTimer); _mntTimer=null; }
  if(!MROW) return;
  const id=MROW.id, text=MROW.notes_md||'';
  api('set_meeting_notes', id, text).then(r=>{
    if(!MROW || MROW.id!==id) return;
    if(r&&r.ok){ setMntState('Saved'); setTimeout(()=>{ setMntState(''); }, 1500); }
    else setMntState((r&&r.error)||'Not saved — check connection');
  });
}
function mntToggleEdit(){
  if(!MROW) return;
  if(!MNT_EDIT && !String(MROW.notes_md||'').trim()){ setMntState('Nothing to edit yet'); setTimeout(()=>setMntState(''),1500); return; }
  MNT_EDIT=!MNT_EDIT;
  if(!MNT_EDIT) mntFlush();
  renderMeetings();
  if(MNT_EDIT){ const ta=document.getElementById('ntEdit'); if(ta) ta.focus(); }
  else openNotes();   // cached notes_md — re-renders the markdown, no LLM call
}
// Regenerating REPLACES the notes, including hand edits — confirm first (v4.1).
function mntRegen(){
  if(!MROW) return;
  if(String(MROW.notes_md||'').trim() &&
     !confirm('Regenerate the AI notes?\n\nThis replaces the current notes — including any edits you made. This cannot be undone.')) return;
  if(_mntTimer){ clearTimeout(_mntTimer); _mntTimer=null; }
  MNT_EDIT=false;
  renderMeetings();
  openNotes(true);
}
// Leaving the notes view must not lose the tail of an edit debounce.
function mntAbandon(){
  if(_mntTimer) mntFlush();
  MNT_EDIT=false;
}
function notesBack(){ mntAbandon(); MSUBNOTES=false; renderMeetings(); }
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
  const tabs=document.querySelectorAll('.hnTab');
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
  const sids=Object.keys(spk);
  const fname=MSPK?(spk[MSPK]||MSPK):null;
  const fcol=MSPK?spColor(MSPK, Math.max(0,sids.indexOf(MSPK))):null;
  const chip=MSPK?'<div class="spkchip" role="button" tabindex="0" onclick="spkFilter('+JSON.stringify(MSPK).replace(/"/g,'&quot;')+')" title="Show everyone">'+
      '<i style="background:'+fcol+'"></i>SHOWING '+esc(String(fname).toUpperCase())+' <span style="color:var(--sub)">&#10005;</span></div>':'';
  el.innerHTML='<div class="cardHead"><span class="eyebrow">Full transcript</span></div>'+chip+
    (tx.length?tx.map(function(u,i){
      const fcls=MSPK?(u.speaker===MSPK?' hlf':' dimf'):'';
      const fsty=(MSPK&&u.speaker===MSPK)?' style="border-left:3px solid '+fcol+';padding-left:8px"':'';
      return '<div class="exUtt'+fcls+'" id="exU'+i+'"'+fsty+' onclick="playAt('+u.t0+','+i+')">'+
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
  // classList, NOT className: the v4 speaker filter parks hlf/dimf classes on
  // these rows and a blanket assignment would wipe them.
  if(MPLAYING>=0){ const p=document.getElementById('exU'+MPLAYING); if(p) p.classList.remove('playing'); }
  MPLAYING=idx;
  if(idx>=0){ const el=document.getElementById('exU'+idx); if(el) el.classList.add('playing'); }
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
// (sumDelete/resetDelBtn retired in v4 — the ⋯ menu delete goes through
// deleteMeeting's confirm() like the list always has.)
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
    // v4: the Studio speaker rows and the list avatars carry the name too.
    const st=document.getElementById('meetStudio');
    if(st) st.innerHTML=meetStudioHtml();
    renderMeetList();
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
  return `<div class="ncard${(SELN===n.id)?' active':''}" data-nid="${esc(n.id)}" onclick="selectNote(${esc(JSON.stringify(n.id))})">
    <button class="npin${n.is_pinned?' on':''}" title="${n.is_pinned?'Unpin':'Pin'}" aria-label="${n.is_pinned?'Unpin note':'Pin note'}" aria-pressed="${n.is_pinned?'true':'false'}" onclick="event.stopPropagation();togglePin(${esc(JSON.stringify(n.id))})">${n.is_pinned?'★':'☆'}</button>
    <button class="ncdots" title="Note options" aria-label="Note options" aria-haspopup="true" onclick="openCardMenu(event, ${esc(JSON.stringify(n.id))})">${SVG.dots}</button>
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
        <div class="s">Dictate a thought and Flume turns it into a clean, titled note — checklists included.</div>
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
        <button class="fmtbtn" title="Reformat the whole note with AI" aria-haspopup="true" onclick="toggleNoteMenu(event,'noteStyleMenu')">&#10024;</button>
        <div class="nmenu" id="noteStyleMenu" hidden>
          <div class="nmhead">Reformat entire note</div>
          <button onclick="formatNoteStyled('structured')">Auto-structure</button>
          <button onclick="formatNoteStyled('prose')">Flowing prose</button>
          <button onclick="formatNoteStyled('transcript')">Clean transcript only</button>
        </div></span>`;
  const sizeMenu = `
      <span class="nmenuwrap">
        <button class="fmtbtn ftxt" title="Text size" aria-haspopup="true" onclick="toggleNoteMenu(event,'noteSizeMenu')">Aa</button>
        <div class="nmenu" id="noteSizeMenu" hidden>
          <div class="nmhead">Text size</div>
          <button onclick="setNoteFs('s')">${NOTE_FS==='s'?'&#10003; ':''}Small</button>
          <button onclick="setNoteFs('m')">${NOTE_FS==='m'?'&#10003; ':''}Default</button>
          <button onclick="setNoteFs('l')">${NOTE_FS==='l'?'&#10003; ':''}Large</button>
        </div></span>`;
  const moreMenu = `
      <span class="nmenuwrap">
        <button class="fmtbtn" title="More actions" aria-haspopup="true" onclick="toggleNoteMenu(event,'noteMoreMenu')">${SVG.dots}</button>
        <div class="nmenu" id="noteMoreMenu" hidden>
          <button onclick="renameOpenNote()">${SVG.edit}Rename</button>
          <button onclick="noteCopy('txt')">${SVG.copy}Copy as text</button>
          <button onclick="noteCopy('md')">${SVG.copy}Copy as Markdown</button>
          <button onclick="noteExport('md')">Export as .md…</button>
          <button onclick="noteExport('txt')">Export as .txt…</button>
          <div class="nmsep"></div>
          <button class="danger" onclick="delNote(null)">${SVG.trash}Delete note</button>
        </div></span>`;
  return `
      <div class="npaneHead">
        <span class="pt">${SHOW_ORIG?'Original':'Note'}</span>
        <div class="notetoolbar">
          <button class="fmtbtn" id="nuUndoBtn" title="Undo (Ctrl+Z)" onmousedown="event.preventDefault();nuUndo()">&#8617;</button>
          <button class="fmtbtn" id="nuRedoBtn" title="Redo (Ctrl+Y)" onmousedown="event.preventDefault();nuRedo()">&#8618;</button>
          <span class="fmtsep"></span>
          <button class="fmtbtn" title="Bold" onmousedown="fmt(event,'bold')"><b>B</b></button>
          <button class="fmtbtn" title="Italic" onmousedown="fmt(event,'italic')"><i>I</i></button>
          <button class="fmtbtn" title="Underline" onmousedown="fmt(event,'underline')"><u>U</u></button>
          <button class="fmtbtn" title="Strikethrough" onmousedown="fmt(event,'strikeThrough')"><s>S</s></button>
          <span class="fmtsep"></span>
          <button class="fmtbtn" title="Heading" onmousedown="fmt(event,'formatBlock','h3')">H</button>
          <button class="fmtbtn" title="Bullet list" onmousedown="fmt(event,'insertUnorderedList')">&bull;</button>
          <button class="fmtbtn" title="Numbered list" onmousedown="fmt(event,'insertOrderedList')">1.</button>
          ${sizeMenu}
          ${styleMenu}
          ${origBtn}${refmtOrig}${retryBtn}
          <button class="fmtbtn${n.is_pinned?' pinned':''}" id="notePinBtn" title="${n.is_pinned?'Unpin note':'Pin note'}" aria-pressed="${n.is_pinned?'true':'false'}" onclick="togglePin(${esc(JSON.stringify(n.id))})">${n.is_pinned?'★':'☆'}</button>
          ${moreMenu}
        </div>
      </div>
      <div class="npaneBody edscroll fs-${NOTE_FS}" id="edScroll" onkeydown="noteKeys(event)">
        <input class="edtitle" id="noteTitle" value="${esc(n.title||'')}" placeholder="Untitled note" aria-label="Note title" oninput="noteChanged()"/>
        <div class="notemeta" id="noteMeta">${esc(noteMetaText(n))}</div>
        ${body}
      </div>
      <div class="dictbar" id="dictBar">
        <span class="dtx" id="dictTx">Dictate into this note — Flume cleans and formats it</span>
        <span class="notesave" id="noteSaveState"></span>
        <button class="dfab" id="dictFab" aria-label="Start dictation" onclick="toggleDictate()">${SVG.mic}</button>
      </div>`;
}
// ── Import from Meetings / Transcriptions (v3.2) ─────────────────────────────
// A modal picker over the whole app (appended to <body> — .nbgrid clips
// overflow). One click on a row = one new note, then the modal closes and the
// note opens. All content is composed CLIENT-side and saved via the ordinary
// save_note path; meetings fetch their full row on click (list rows hydrated
// from the cloud don't carry summary/decisions).
const SVG_IMPORT='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v11"/><path d="m7.5 9.5 4.5 4.5 4.5-4.5"/><path d="M4 17v2.4A1.6 1.6 0 0 0 5.6 21h12.8a1.6 1.6 0 0 0 1.6-1.6V17"/></svg>';
let IMP_TAB='meetings', IMP_Q='', IMP_BUSY=null, IMP_HIST=[];
function openImport(){
  IMP_TAB='meetings'; IMP_Q=''; IMP_BUSY=null;
  renderImport();
  // Refresh the meetings list for the picker (it may never have been loaded
  // this session). Re-render only the modal's list — never the screen.
  api('list_meetings').then(r=>{
    if(r && r.ok){ MEETS=r; MEETS_LOADED=true; if(document.getElementById('impList')) renderImportList(); }
  });
}
function closeImport(){ const w=document.getElementById('nimpWrap'); if(w) w.remove(); }
function impTab(t){ IMP_TAB=t; IMP_Q=''; renderImport(); }
function renderImport(){
  let w=document.getElementById('nimpWrap');
  if(!w){
    w=document.createElement('div'); w.id='nimpWrap'; w.className='nimpWrap';
    w.addEventListener('click', e=>{ if(e.target===w) closeImport(); });
    w.addEventListener('keydown', e=>{ if(e.key==='Escape') closeImport(); });
    document.body.appendChild(w);
  }
  w.innerHTML=`<div class="nimp" role="dialog" aria-modal="true" aria-label="Import into Notes">
    <div class="nimpHead"><span class="pt">Import into Notes</span>
      <button class="nimpX" aria-label="Close" onclick="closeImport()">✕</button></div>
    <div class="nimpTabs">
      <button class="nimpTab${IMP_TAB==='meetings'?' on':''}" onclick="impTab('meetings')">Meetings</button>
      <button class="nimpTab${IMP_TAB==='hist'?' on':''}" onclick="impTab('hist')">Transcriptions</button>
    </div>
    <div class="searchbox">${SVG.search}<input id="impSearch" aria-label="Search" placeholder="${IMP_TAB==='meetings'?'Search meetings…':'Search transcriptions…'}" value="${esc(IMP_Q)}" oninput="IMP_Q=this.value;renderImportList()"/></div>
    <div class="nimpBody" id="impList"></div>
    <div class="nimpHint">${IMP_TAB==='meetings'
      ?'A meeting becomes a note with its summary, decisions and an interactive action-item checklist.'
      :'A transcription becomes a note with its text — clean it up afterwards with the Studio styles.'}</div>`;
  renderImportList();
  const i=document.getElementById('impSearch'); if(i) i.focus();
}
function renderImportList(){
  const box=document.getElementById('impList'); if(!box) return;
  const q=(IMP_Q||'').trim().toLowerCase();
  if(IMP_TAB==='meetings'){
    let ms=(MEETS.meetings||[]).filter(m=>m && m.id && m.status!=='processing');
    if(q) ms=ms.filter(m=>((m.title||'')+' '+(m.summary||'')).toLowerCase().includes(q));
    box.innerHTML = ms.length ? ms.map(m=>{
      const busy=IMP_BUSY===('m:'+m.id);
      return `<div class="srow" role="button" tabindex="0" onclick="importMeeting(${esc(JSON.stringify(m.id))})" onkeydown="if(event.key==='Enter')importMeeting(${esc(JSON.stringify(m.id))})">
        <span class="sic">${SVG.meet}</span>
        <span class="st"><span class="a">${esc(m.title||'Meeting')}</span><span class="b">${esc((m.started_at||'').slice(0,10))} · ${Math.max(1,Math.round((m.duration_seconds||0)/60))} min</span></span>
        <span class="imppill${busy?' busy':''}">${busy?'Importing…':'Import'}</span></div>`;
    }).join('') : `<div class="empty">${q?'No meetings match.':'No meetings yet — capture one first.'}</div>`;
  } else {
    let hs=((STATE&&STATE.history)||[]).filter(e=>e && e.status!=='failed' && String(e.text||'').trim());
    if(q) hs=hs.filter(e=>String(e.text||'').toLowerCase().includes(q));
    IMP_HIST=hs.slice(0,120);
    box.innerHTML = IMP_HIST.length ? IMP_HIST.map((e,i)=>{
      return `<div class="srow" role="button" tabindex="0" onclick="importTranscription(${i})" onkeydown="if(event.key==='Enter')importTranscription(${i})">
        <span class="sic">${SVG.mic}</span>
        <span class="st"><span class="a">${esc(titleOf(e.text))}</span><span class="b">${esc(e.ts||'')} · ${words(e.text)} words${e.app?(' · '+esc(e.app)):''}</span></span>
        <span class="imppill">Import</span></div>`;
    }).join('') : `<div class="empty">${q?'No transcriptions match.':'No transcriptions yet — dictate something first.'}</div>`;
  }
}
function importMeeting(id){
  if(IMP_BUSY) return;
  IMP_BUSY='m:'+id; renderImportList();
  api('get_meeting', id).then(r=>{
    IMP_BUSY=null;
    if(!(r&&r.ok&&r.meeting)){ renderImportList(); toast((r&&r.error)||'Could not load that meeting.', true); return; }
    const c=meetingNoteMarkdown(r.meeting);
    if(!c){ toast('That meeting has no content to import yet.', true); return; }
    finishImport(c.title, c.content);
  });
}
// Compose a meeting into note markdown — shared by the Notes import picker and
// the Meetings Studio "Send to Notes" (v4). Returns {title, content} or null.
function meetingNoteMarkdown(m){
  if(!m) return null;
  const lines=[];
  if(String(m.summary||'').trim()) lines.push(String(m.summary).trim());
  if((m.decisions||[]).length){
    lines.push('','## Decisions');
    m.decisions.forEach(d=>lines.push('- '+String(d)));
  }
  if((m.action_items||[]).length){
    lines.push('','## Action items');
    m.action_items.forEach(it=>{
      const owner=(it.owner && m.speakers && m.speakers[it.owner]) ? (' — **'+m.speakers[it.owner]+'**') : '';
      const due=it.due ? (' (due '+it.due+')') : '';
      lines.push('- ['+(it.done?'x':' ')+'] '+String(it.task||'')+owner+due);
    });
  }
  if(!lines.length){
    // No summary yet — fall back to the raw transcript text so the import
    // still lands something, restylable from the Studio afterwards.
    try{ const t=(m.transcript||[]).map(s=>String(s.text||'')).join(' ').trim(); if(t) lines.push(t); }catch(e){}
  }
  if(!lines.length) return null;
  lines.push('','*Imported from the meeting “'+String(m.title||'Meeting')+'” · '+String(m.started_at||'').slice(0,10)+'*');
  return {title:String(m.title||'Meeting'), content:lines.join('\n').trim()};
}
function importTranscription(i){
  if(IMP_BUSY) return;
  const e=IMP_HIST[i]; if(!e) return;
  const t=String(e.text||'').trim(); if(!t) return;
  const content=t+'\n\n*Imported from dictation · '+String(e.ts||'')+'*';
  finishImport(titleOf(t), content);
}
function finishImport(title, content){
  busyGuard('noteimport', ()=>api('save_note', {title:title||'', content:content||''})).then(r=>{
    if(r && r.busy) return;
    if(!(r&&r.ok)){ toast('Import failed — please try again.', true); return; }
    NOTES=r.notes||NOTES; SELN=r.id||SELN; NOTE_QUERY=''; NOTE_ASK=null; SHOW_ORIG=false;
    closeImport();
    renderNotes();
    setSaveState('Imported');
    setTimeout(()=>setSaveState(''), 1600);
  });
}
// Close any open note menu on an outside click (registered ONCE — this script
// runs a single time; the open buttons stopPropagation so they don't self-close).
document.addEventListener('click', ()=>{
  document.querySelectorAll('.nmenu').forEach(m=>{ if(!m.hidden) m.hidden=true; });
  closeSyncPop();
});
document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') closeSyncPop(); });
// The WebView's built-in right-click menu offers "Reload" — which blanks the
// window, since the dashboard is loaded from a string, not a URL (2026-08-15,
// Windows/WebView2; WKWebView has the same item). Keep the native menu only
// inside editable fields (cut/copy/paste/spellcheck live there).
document.addEventListener('contextmenu', (e)=>{
  const t=e.target;
  const editable = t && t.closest &&
    t.closest('input, textarea, [contenteditable="true"], [contenteditable="plaintext-only"]');
  if(!editable) e.preventDefault();
});
function toggleNoteMenu(ev, id){
  ev.stopPropagation();
  const m=document.getElementById(id); if(!m) return;
  const was=m.hidden;
  document.querySelectorAll('.nmenu').forEach(x=>{ x.hidden=true; });
  m.hidden=!was;
  if(!m.hidden){
    // .npane clips overflow, so an in-flow absolute menu gets cut at the pane
    // edge in small windows ("blocked by the first panel", 2026-08-15).
    // position:fixed escapes the clip (no transformed ancestors here) —
    // anchor to the trigger button and clamp to the viewport.
    const btn=ev.currentTarget || ev.target;
    const r=btn.getBoundingClientRect();
    m.style.position='fixed'; m.style.right='auto';
    m.style.left='0px'; m.style.top='0px';          // paint first, then measure
    const mw=m.offsetWidth, mh=m.offsetHeight;
    m.style.left=Math.max(8, Math.min(window.innerWidth-mw-8, r.right-mw))+'px';
    m.style.top=Math.max(8, Math.min(window.innerHeight-mh-8, r.bottom+6))+'px';
  }
}
// Per-segment playback (Feature 4) renders as Studio rows since v3.1 — see
// studioHtml. No control at all when the note has no audio (Decision 6).
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

function selectNote(id){ flushNoteSave(); flushRawSave(); stopNoteAudio(); abortDictationIfLive(); SELN=id; SHOW_ORIG=false; renderNotes(); }
function newNote(title){
  flushNoteSave(); flushRawSave(); stopNoteAudio(); abortDictationIfLive(); NOTE_QUERY=''; NOTE_ASK=null; SHOW_ORIG=false;
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
function fmt(ev, cmd, val){ ev.preventDefault(); if(SHOW_ORIG) return; const b=document.getElementById('noteBody'); if(b) b.focus(); document.execCommand(cmd,false,val||null); noteChanged(); }

// ── Editor text size (Aa menu) — persisted per install ───────────────────────
function setNoteFs(v){
  NOTE_FS=(v==='s'||v==='l')?v:'m';
  try{ localStorage.setItem('flumeNoteFs', NOTE_FS); }catch(e){}
  const sc=document.getElementById('edScroll');
  if(sc){ sc.classList.remove('fs-s','fs-m','fs-l'); sc.classList.add('fs-'+NOTE_FS); }
  const m=document.getElementById('noteSizeMenu'); if(m) m.hidden=true;
}

// ── Note undo/redo (2026-08-15 feedback) ─────────────────────────────────────
// The browser's native contenteditable undo dies the moment anything replaces
// the editor programmatically (AI reformat, restyle, re-render) — so the
// editor owns its own snapshot stack. Granularity = autosave idle chunks
// (700ms) plus an explicit snapshot before/after every programmatic change.
// Ctrl/Cmd+Z, Ctrl+Y and Ctrl/Cmd+Shift+Z work; the toolbar has ↶/↷ too.
let NU={id:null, stack:[], idx:-1, applying:false};
function nuState(){
  const t=document.getElementById('noteTitle'), b=document.getElementById('noteBody');
  if(!t||!b) return null;
  return {t:t.value, c:b.innerHTML};
}
function nuButtons(){
  const u=document.getElementById('nuUndoBtn'), r=document.getElementById('nuRedoBtn');
  if(u) u.disabled=!(NU.idx>0);
  if(r) r.disabled=!(NU.idx<NU.stack.length-1);
}
function nuSnap(){
  if(NU.applying) return;
  const s=nuState(); if(!s) return;
  const cur=NU.stack[NU.idx];
  if(cur && cur.t===s.t && cur.c===s.c) { nuButtons(); return; }
  NU.stack=NU.stack.slice(0, NU.idx+1);
  NU.stack.push(s);
  if(NU.stack.length>100) NU.stack.shift();
  NU.idx=NU.stack.length-1;
  nuButtons();
}
function nuInit(n){
  if(!n){ NU={id:null, stack:[], idx:-1, applying:false}; return; }
  if(NU.id!==n.id){ NU={id:n.id, stack:[], idx:-1, applying:false}; }
  nuSnap();   // same note re-rendered (e.g. after a reformat): push the new state
}
function nuApply(s){
  const t=document.getElementById('noteTitle'), b=document.getElementById('noteBody');
  if(!t||!b||!s) return;
  NU.applying=true;
  try{
    t.value=s.t; b.innerHTML=s.c;
    const n=curNote(); if(n){ n.title=s.t; n.content=s.c; }
    setSaveState('Saving…');
    if(_noteTimer) clearTimeout(_noteTimer);
    _noteTimer=setTimeout(saveCurrentNote, 400);
    const m=document.getElementById('noteMeta'); const n2=curNote();
    if(n2&&m) m.textContent=noteMetaText(n2, b.innerText);
  } finally { NU.applying=false; }
  nuButtons();
}
function nuUndo(){ if(SHOW_ORIG) return; if(NU.idx>0){ NU.idx--; nuApply(NU.stack[NU.idx]); } }
function nuRedo(){ if(SHOW_ORIG) return; if(NU.idx<NU.stack.length-1){ NU.idx++; nuApply(NU.stack[NU.idx]); } }
function noteKeys(ev){
  const k=(ev.key||'').toLowerCase();
  if(!(ev.ctrlKey||ev.metaKey)) return;
  // The transcript view is plaintext-only — native undo behaves there.
  const inOrig=ev.target && ev.target.id==='noteOrig';
  if(inOrig) return;
  if(k==='z' && !ev.shiftKey){ ev.preventDefault(); nuUndo(); }
  else if(k==='y' || (k==='z' && ev.shiftKey)){ ev.preventDefault(); nuRedo(); }
}

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
  nuSnap();            // each idle-save is one undo step
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
function delNote(btn){ const n=curNote(); if(n) delNoteById(n.id, btn); }
function delNoteById(id, btn){
  closeCardMenu();
  const n=NOTES.find(x=>x.id===id); if(!n) return;
  if(!confirm('Delete “'+(n.title||'Untitled')+'”?\n\nThe note and its linked recordings are permanently removed. This cannot be undone.')) return;
  if(SELN===id){
    if(_noteTimer){ clearTimeout(_noteTimer); _noteTimer=null; }
    if(_rawTimer){ clearTimeout(_rawTimer); _rawTimer=null; }
    stopNoteAudio();
    abortDictationIfLive();
  }
  busyGuard(btn || ('delnote:'+id), ()=>api('delete_note', id)).then(r=>{
    if(r && r.busy) return;
    if(!(r&&r.ok)){ alert((r&&r.error)||"Couldn't delete the note — please try again."); return; }
    NOTES=r.notes||NOTES.filter(x=>x.id!==id);
    if(SELN===id){ SELN=null; SHOW_ORIG=false; }
    renderNotes(); });
}

// ── Per-card ⋯ menu: rename / pin / delete from the notes list ───────────────
// (2026-08-15 feedback: managing a note shouldn't require opening it first.)
// The menu is body-appended (.nbgrid clips overflow) with class .nmenu so the
// existing document-level click closer dismisses it like every other menu.
function closeCardMenu(){ const m=document.getElementById('ncMenu'); if(m) m.remove(); }
function openCardMenu(ev, id){
  ev.stopPropagation();
  document.querySelectorAll('.nmenu').forEach(x=>{ x.hidden=true; });
  closeCardMenu();
  const n=NOTES.find(x=>x.id===id); if(!n) return;
  const m=document.createElement('div');
  m.id='ncMenu'; m.className='nmenu';
  m.innerHTML=`
    <button onclick="startCardRename(${esc(JSON.stringify(id))})">${SVG.edit}Rename</button>
    <button onclick="togglePin(${esc(JSON.stringify(id))});closeCardMenu()">${n.is_pinned?'&#9734; Unpin':'&#9733; Pin'}</button>
    <div class="nmsep"></div>
    <button class="danger" onclick="delNoteById(${esc(JSON.stringify(id))})">${SVG.trash}Delete note</button>`;
  document.body.appendChild(m);
  const r=ev.currentTarget.getBoundingClientRect();
  m.style.left=Math.max(8, Math.min(window.innerWidth-m.offsetWidth-8, r.right-m.offsetWidth))+'px';
  m.style.top=Math.min(window.innerHeight-m.offsetHeight-8, r.bottom+6)+'px';
}
function startCardRename(id){
  closeCardMenu();
  const n=NOTES.find(x=>x.id===id);
  const card=document.querySelector('.ncard[data-nid="'+(window.CSS&&CSS.escape?CSS.escape(id):id)+'"]');
  if(!n||!card) return;
  const t=card.querySelector('.nctitle'); if(!t) return;
  t.innerHTML='<input class="ncren" value="'+esc(n.title||'')+'" aria-label="Rename note"'
    +' onclick="event.stopPropagation()"'
    +' onkeydown="renameKeys(event)"'
    +' onblur="commitRename(this, '+esc(JSON.stringify(id))+')"/>';
  const inp=t.querySelector('input');
  if(inp){ inp.focus(); inp.select(); }
}
function renameKeys(ev){
  ev.stopPropagation();
  if(ev.key==='Enter'){ ev.preventDefault(); ev.target.blur(); }
  else if(ev.key==='Escape'){ ev.preventDefault(); ev.target.__cancel=true; ev.target.blur(); }
}
function commitRename(inp, id){
  const n=NOTES.find(x=>x.id===id);
  const cancel=!!inp.__cancel; inp.__cancel=false;
  const val=(inp.value||'').trim();
  if(!n || cancel || val===String(n.title||'').trim()){ renderNoteList(); return; }
  n.title=val;
  if(SELN===id){
    // The open note rides the normal editor save (autosave + undo snapshot).
    const t=document.getElementById('noteTitle');
    if(t){ t.value=val; noteChanged(); }
    renderNoteList();
    return;
  }
  const payload={id:n.id, title:val, content:n.content||'', no_cleanup:true};
  if(n.raw_content!=null) payload.raw_content=n.raw_content;
  if(n.audio_segments&&n.audio_segments.length) payload.audio_segments=n.audio_segments;
  busyGuard('ren:'+id, ()=>api('save_note', payload)).then(r=>{
    if(r&&r.ok){ if(r.notes) NOTES=r.notes; toast('Renamed'); }
    else toast((r&&r.error)||"Couldn't rename — please try again.", true);
    renderNoteList();
  });
}
function renameOpenNote(){
  const t=document.getElementById('noteTitle');
  if(t){ t.focus(); t.select(); }
}

// ── v3.2 dictation bar: idle = hint + FAB; recording = cancel · live waveform
// · timer · pause/resume · stop-FAB. The waveform is REAL (recorder.level
// polled every ~120ms), not an animation loop.
let NOTE_PAUSED=false, _recTimer=null, _recMs=0, _recLast=0;
function startRecTimer(){
  _recMs=0; _recLast=Date.now(); NOTE_PAUSED=false;
  if(_recTimer) clearInterval(_recTimer);
  _recTimer=setInterval(recTick, 120);
}
function stopRecTimer(){ if(_recTimer){ clearInterval(_recTimer); _recTimer=null; } NOTE_PAUSED=false; }
function recTick(){
  const now=Date.now();
  if(!NOTE_PAUSED) _recMs += now - _recLast;
  _recLast=now;
  const t=document.getElementById('dictTimer');
  if(t){ const s=Math.floor(_recMs/1000); t.textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
  if(NOTE_PAUSED) return;   // bars freeze while paused
  api('note_dictate_level').then(r=>{
    if(!NOTE_REC) return;
    const w=document.getElementById('dictWave'); if(!w) return;
    const bars=w.children; if(!bars.length) return;
    for(let i=0;i<bars.length-1;i++){ bars[i].style.height=bars[i+1].style.height||'3px'; }
    const lv=(r&&r.ok)?Math.max(0,Math.min(1,r.level||0)):0;
    bars[bars.length-1].style.height=(3+Math.round(lv*17))+'px';
  });
}
function updateDictateBtn(){
  const bar=document.getElementById('dictBar'); if(!bar) return;
  bar.classList.toggle('rec', NOTE_REC);
  bar.classList.toggle('paused', NOTE_REC && NOTE_PAUSED);
  if(NOTE_REC){
    bar.innerHTML=`
      <button class="dside" title="Cancel — discard this recording" aria-label="Cancel recording" onclick="cancelDictate()">✕</button>
      <div class="dwave" id="dictWave" aria-hidden="true">${'<i></i>'.repeat(28)}</div>
      <span class="dtimer" id="dictTimer">0:00</span>
      <button class="dside" id="dictPauseBtn" title="Pause" aria-label="Pause recording" onclick="pauseDictate()">${SVG_PAUSE}</button>
      <button class="dfab" aria-label="Stop and transcribe" onclick="toggleDictate()"><span class="dstop"></span></button>`;
  } else {
    bar.innerHTML=`
      <span class="dtx" id="dictTx">Dictate into this note — Flume cleans and formats it</span>
      <span class="notesave" id="noteSaveState"></span>
      <button class="dfab" id="dictFab" aria-label="Start dictation" onclick="toggleDictate()">${SVG.mic}</button>`;
  }
}
function pauseDictate(){
  busyGuard('note_pause', ()=>api('note_dictate_pause')).then(r=>{
    if(r && r.busy) return;
    if(!(r&&r.ok)) return;
    NOTE_PAUSED=!!r.paused;
    const bar=document.getElementById('dictBar'); if(bar) bar.classList.toggle('paused', NOTE_PAUSED);
    const b=document.getElementById('dictPauseBtn');
    if(b){
      b.innerHTML=NOTE_PAUSED?SVG.play:SVG_PAUSE;
      b.title=NOTE_PAUSED?'Resume':'Pause';
      b.setAttribute('aria-label', NOTE_PAUSED?'Resume recording':'Pause recording');
    }
  });
}
// Leaving the recording context (switching notes, new note, deleting, leaving
// the screen) DISCARDS a live recording — the mic must never keep running with
// no UI attached to it. Fire-and-forget by design.
function abortDictationIfLive(){
  if(!NOTE_REC) return;
  NOTE_REC=false;
  stopRecTimer();
  api('note_dictate_cancel');
}
// Cancel = discard: recorder stops, audio is dropped, nothing is transcribed.
// Shares the 'note_dictate' guard so it can't race a stop-and-transcribe.
function cancelDictate(){
  busyGuard('note_dictate', ()=>api('note_dictate_cancel')).then(r=>{
    if(r && r.busy) return;
    stopRecTimer();
    NOTE_REC=false;
    updateDictateBtn();
    setSaveState('');
  });
}
// Key-guarded, not element-guarded: updateDictateBtn() rewrites the button's
// contents on every state flip, so a flag parked on the node would be lost —
// and a double-click on Dictate used to fire two start/stop calls (IDI-167).
function toggleDictate(){
  const n=curNote();
  if(NOTE_REC){
    stopRecTimer();
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
      if(r&&r.ok){ NOTE_REC=true; startRecTimer(); updateDictateBtn(); }
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
    nuSnap();   // the pre-append state is one Ctrl+Z away
    const b=document.getElementById('noteBody');
    if(b){ b.focus();
      const sep=(b.innerText && !/\s$/.test(b.innerText))?' ':'';
      b.appendChild(document.createTextNode(sep+(r.text||rawSeg)+' '));
      const rng=document.createRange(); rng.selectNodeContents(b); rng.collapse(false);
      const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(rng);
    }
    // refresh the Studio pane (recordings live there now, v3.1) without
    // wiping the freshly appended editor text — it is a separate pane.
    const sp=document.getElementById('studioPane');
    if(sp) sp.innerHTML=studioHtml(n);
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
// Source (2026-08-15 feedback): the ENTIRE visible note — what the user sees
// is what gets reformatted. Restyling from raw_content silently DROPPED every
// typed/edited word (the transcript only holds dictated segments), which read
// as "the tool only formats the recent transcription, not the entire text".
// The transcript-as-source path still exists where it belongs: the Original
// view's "Reformat from transcript" button (retryFormatting → 'raw').
function formatNoteStyled(style, from){
  const n=curNote(); if(!n) return;
  flushNoteSave();                      // pending edits are part of "entire"
  let source='';
  if(from==='raw' && (n.raw_content!=null) && String(n.raw_content).trim()!==''){
    source=String(n.raw_content);
  } else {
    const b=document.getElementById('noteBody');
    source=(b && b.innerText.trim()) ? b.innerText : strippedNote(n);
    // Nothing typed yet but a transcript exists (failed first cleanup) —
    // fall back to it so Reformat still has something to work on.
    if(!source.trim() && n.raw_content!=null) source=String(n.raw_content);
  }
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
  formatNoteStyled('structured', 'raw');
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
  // A green dot on the live targets: picking a device that has been dark for
  // three weeks is almost never what you meant.
  const selector = devs.length ? syncSelectorHTML(target, devs) : '';
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

// ── shared "send my transcriptions to" controls — used by the full Devices
// screen selector AND the small popover opened from a sidebar device row or
// the Home pill, so there is exactly one implementation of the pill list. ──
function syncTargetOptions(devs){
  return [{id:'__all__',name:'All devices',online:false}].concat(
    (devs||[]).map(d=>({id:d.device_id,name:d.device_name||'Device',online:!!d.online})));
}
function syncTargetLabel(target, devs){
  if(!target || target==='__all__') return 'All devices';
  if(target==='__none__') return 'This device only';
  const d=(devs||[]).find(x=>x.device_id===target);
  return d ? (d.device_name||'Device') : 'All devices';
}
function syncSelectorHTML(target, devs){
  const opts = syncTargetOptions(devs);
  return `<div class="tgtwrap">
    <div class="tgtlabel">SEND MY TRANSCRIPTIONS TO</div>
    <div class="tgtpills">${opts.map(o=>`<button class="tgtpill${o.id===target?' on':''}" onclick='event.stopPropagation();setTarget(${JSON.stringify(o.id)})'>${o.online?'<span class="tdot"></span>':''}${esc(o.name)}</button>`).join('')}</div>
  </div>`;
}
// Popover host — one shared floating panel, positioned near whichever
// element (device row / Home pill) triggered it. Same anchored-panel recipe
// as insTip(), but interactive (pointer-events) and click-toggled rather than
// hover-shown, since it holds real controls, not just a label.
let SYNC_POP_ANCHOR=null;
function openSyncPop(el){
  let pop=document.getElementById('syncPop');
  if(!pop){ pop=document.createElement('div'); pop.id='syncPop'; document.body.appendChild(pop); }
  const target=(STATE&&STATE.target_device_id)||'__all__';
  const devs=(STATE&&STATE.devices)||[];
  pop.innerHTML = syncSelectorHTML(target, devs);
  pop.style.display='block';
  const r=el.getBoundingClientRect();
  const pr=pop.getBoundingClientRect();
  pop.style.left=Math.max(6,Math.min(window.innerWidth-pr.width-6, r.left))+'px';
  pop.style.top=Math.max(6,Math.min(window.innerHeight-pr.height-6, r.bottom+8))+'px';
}
function closeSyncPop(){
  const pop=document.getElementById('syncPop');
  if(pop) pop.style.display='none';
  SYNC_POP_ANCHOR=null;
}
function toggleSyncPop(ev, el){
  if(ev) ev.stopPropagation();
  const pop=document.getElementById('syncPop');
  if(pop && pop.style.display==='block' && SYNC_POP_ANCHOR===el){ closeSyncPop(); return; }
  SYNC_POP_ANCHOR=el;
  openSyncPop(el);
}
function setTarget(id){
  api('set_target_device', id).then(()=>{
    if(STATE) STATE.target_device_id=id;
    renderDevices();
    renderSidebar();
    if(ACTIVE==='home') renderHome();
    closeSyncPop();
  });
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
  {id:'updates',    label:'Updates',     lede:'Your current version, and whether a newer one is ready.'},
  // Only rendered when the user is actually on a team — see renderSettings().
  // A privacy group that says "you have no team" is a group nobody needed.
  {id:'privacy',    label:'Team privacy', lede:'What your team can and cannot see about your dictation.'},
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
  {id:'gemini-3-5-transcribe',       vendor:'Google', name:'Gemini 3.5 Transcribe',
   desc:'Verbatim words, then Flume formats. Top benchmark accuracy.', wait:'?', tag:'trial'},
  {id:'gemini-3-5-transcribe-smart', vendor:'Google', name:'Gemini 3.5 Smart',
   desc:'Gemini removes fillers and punctuates itself before Flume formats.', wait:'?', tag:'trial'},
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
    if(id==='updates')    return (UPDATE_STATE && UPDATE_STATE.available) ? 'update' : '';
    if(id==='privacy')    return (TEAM&&TEAM.usage_consent)?'sharing':'private';
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
  // Leaving a team while sitting on its privacy group must not strand you on a
  // pane about a team you are no longer in.
  const groups=SETTINGS_GROUPS.filter(x=>x.id!=='privacy'||hasTeam());
  if(SETTINGS_GROUP==='privacy' && !hasTeam()) SETTINGS_GROUP='account';
  const g=groups.find(x=>x.id===SETTINGS_GROUP)||groups[0];
  const rail=groups.map(x=>{
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

  if(id==='updates'){
    const cur = (UPDATE_STATE && UPDATE_STATE.current_version) || (STATE && STATE.version) || '';
    const avail = UPDATE_STATE && UPDATE_STATE.available;
    const phase = UPDATE_STATE ? UPDATE_STATE.phase : 'idle';
    let statusHtml;
    if(avail && phase==='downloading'){
      const pct = Math.round((UPDATE_STATE.progress||0)*100);
      statusHtml = `<div class="sdesc">Downloading v${esc(avail.version)}… ${pct}%</div>`;
    } else if(avail && phase==='ready'){
      statusHtml = `<div class="sdesc">v${esc(avail.version)} is downloaded and ready.</div>
        <button class="btn primary" style="margin-top:8px" onclick="installReadyUpdate()">Restart to update</button>`;
    } else if(avail && phase==='installing'){
      statusHtml = `<div class="sdesc">Installing — Flume will restart shortly.</div>`;
    } else if(avail){
      statusHtml = `<div class="sdesc">v${esc(avail.version)} is available.</div>
        <button class="btn primary" style="margin-top:8px" onclick="startUpdateDownload()">Update to v${esc(avail.version)}</button>`;
    } else {
      statusHtml = `<div class="sdesc">You're up to date.</div>`;
    }
    return `
      <div class="ssection">
        <div class="scard row">
          <div class="grow"><div class="sname">Flume v${esc(cur)}</div>${statusHtml}</div>
          <button class="btn ghost" onclick="checkForUpdatesNow()">Check for Updates</button>
        </div>
      </div>`;
  }

  if(id==='privacy'){
    // hasTeam() is re-checked because a heartbeat can repaint Settings in the
    // moment between leaving a team and the rail rebuilding.
    if(!hasTeam()) return `
      <div class="ssection"><div class="scard"><div class="ssub" style="margin:0">
        You are not on a team, so nobody is seeing anything.</div></div></div>`;
    return `
      <div class="ssection"><h3>What ${esc(TEAM.name||'your team')} can see</h3>
        <p class="ssub">Sharing your dictation counts is <b style="color:var(--tx)">on by default</b> &mdash;
          switch it off and your numbers vanish from every admin view, and from the team ranking,
          immediately. Whether the ranking is shown at all is the team owner's call.</p>
        <div class="scard">
          <div class="saverow"><button class="toggle ${TEAM.usage_consent?'on':''}"
              aria-label="Let admins see my dictation counts"
              onclick="setTeamConsent(${TEAM.usage_consent?'false':'true'}, ${TEAM.usage_consent?'false':'true'})"></button>
            <span style="font:500 13px Geist">Let admins see my dictation counts</span></div>
        </div>
        <div class="tmnote" style="margin-top:14px">${SVG.lock}
          <span>What you dictate &mdash; the text, the audio, your notes &mdash; is never shared with your
          team, whatever these are set to. Admins see counts, durations and
          <b style="color:var(--tx2)">the names of the apps you dictate into</b> &mdash; never what you said
          in them. Turning the first off hides all of it and turns the second off too, and nobody else can
          turn either back on for you.</span></div>
        <div class="tmnote" style="margin-top:8px">${SVG.pulse}
          <span>Your team&rsquo;s numbers count <b style="color:var(--tx2)">synced dictations in the last
          ${TEAM_DAYS} days</b>. Your own <button class="tmskip" style="padding:0;color:var(--acc)"
          onclick="show('insights')">Insights</button> page counts everything you have ever dictated,
          including takes that never reached the cloud &mdash; so it will always read higher.</span></div>
      </div>

      ${teamOwner()?`
      <div class="ssection"><h3>Team-wide visibility</h3>
        <p class="ssub">By default only owners and admins see the roster's numbers. Open them up and
          every member sees the same per-person stats admins do &mdash; each person's own sharing switch
          above still wins: someone who turned theirs off stays hidden from everyone.</p>
        <div class="scard">
          <div class="saverow"><button class="toggle ${TEAM.stats_visible_to_members?'on':''}"
              aria-label="Everyone sees everyone's stats"
              onclick="toggleTeamStatsVisible()"></button>
            <span style="font:500 13px Geist">Everyone sees everyone&rsquo;s stats</span></div>
        </div>
      </div>`:''}

      <div class="ssection"><h3>Membership</h3>
        <div class="scard row">
          <div class="grow"><div class="sname">${esc(TEAM.name||'Your team')}</div>
            <div class="sdesc">You are ${TEAM.role==='owner'?'the owner':TEAM.role==='admin'?'an admin':'a member'}.
              ${teamOwner()
                ? 'An owner cannot leave &mdash; hand the team over first.'
                : 'You keep your own dictionary and history; the shared ones stop applying.'}</div></div>
          ${teamOwner()?'' : '<button class="btn ghost" onclick="leaveTeam()">Leave team</button>'}
        </div>
        <div class="saverow" style="margin-top:12px"><button class="tmskip" style="padding:0;color:var(--acc)"
          onclick="show('team')">Open the team &rarr;</button></div>
      </div>`;
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
        <div class="field"><label>DEVICE NAME</label><input id="devName" value="${esc(s.sync_device_name||THIS_DEVICE)}"/></div>
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
      ${tgl('meetings_diarize_enabled','Identify who spoke (after the meeting)')}
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
let LANGS={value:'auto', options:[["auto","Auto-detect"],["en","English"]]};
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

// Which dictionary the screen is editing. The TEAM's shared set used to live on
// the Team screen, which was the wrong home: it is a dictionary, people look for
// dictionaries under Dictionary, and it meant two places to learn for one concept.
let DICT_SCOPE='personal';
function setDictScope(v){ DICT_SCOPE=v; renderDictionary(); }

function dictScopeTabs(){
  if(!hasTeam()) return '';
  return `<span class="insseg" style="float:none;margin-left:12px">
    <button class="${DICT_SCOPE==='personal'?'on':''}" onclick="setDictScope('personal')">Mine</button>
    <button class="${DICT_SCOPE==='team'?'on':''}" onclick="setDictScope('team')">${esc(TEAM.name||'Team')}</button>
  </span>`;
}

function renderTeamDictionary(){
  const admin=teamAdmin(), d=tdict();
  const ro = admin ? '' : ' tmreadonly';
  const vocab = d.vocabulary.map((w,i)=>`<span class="dchip">${esc(w)}${admin?`<button onclick="tdRmWord(${i})" title="Remove">✕</button>`:''}</span>`).join('')
    || '<span class="ssub" style="margin:0">No shared words yet.</span>';
  const reps = d.replacements.map((r,i)=>`<div class="reprow"><span class="rfrom">${esc(r.from)}</span><span class="rarrow">→</span><span class="rto">${esc(r.to)}</span>${admin?`<button onclick="tdRmRep(${i})" title="Remove">✕</button>`:''}</div>`).join('')
    || '<span class="ssub" style="margin:0">No shared rules yet.</span>';
  const snips = d.snippets.map((sn,i)=>`<div class="reprow"><span class="rfrom">${esc(sn.trigger)}</span><span class="rarrow">→</span><span class="rto">${esc(String(sn.expansion||'').slice(0,90))}${String(sn.expansion||'').length>90?'…':''}</span>${admin?`<button onclick="tdRmSnip(${i})" title="Remove">✕</button>`:''}</div>`).join('')
    || '<span class="ssub" style="margin:0">No shared snippets yet.</span>';
  const personal=DICT.vocabulary.length;
  document.getElementById('dictionaryMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Transcription</div>
      <h1 class="title">Dictionary ${dictScopeTabs()}</h1></div>
      <span class="notesave" id="dictState"></span></div>
    <p class="ssub" style="margin:-8px 0 18px">${admin
      ? `Everyone on ${esc(TEAM.name||'the team')} dictates with these on top of their own.`
      : `Your admins maintain these. They apply on top of your own words.`}
      Your own entries always win a clash — same word, same rule, same trigger.</p>
    ${admin&&personal?`<div class="tmnote" style="margin:0 0 18px">${SVG.team}
      <span>You have <b style="color:var(--tx2)">${personal} personal word${personal===1?'':'s'}</b> that could be shared.
      <button class="tmskip" style="padding:0;color:var(--acc)" onclick="seedTeamDict()">Copy mine to the team</button></span></div>`:''}
    <div class="dictgrid">
      <div class="dictcol${ro}">
        <div class="dcolhead"><h3>Shared vocabulary</h3><p class="ssub">Names &amp; jargon the whole team should spell right.</p></div>
        <div class="dictchips">${vocab}</div>
        ${admin?`<div class="dictadd"><input id="tdWord" placeholder="Add a shared word…" onkeydown="if(event.key==='Enter'){event.preventDefault();tdAddWord();}"/><button class="btn primary" style="flex:none;width:80px" onclick="tdAddWord()">Add</button></div>`:''}
      </div>
      <div class="dictcol${ro}">
        <div class="dcolhead"><h3>Shared rules</h3><p class="ssub">Always rewrite a misheard word, for everyone.</p></div>
        <div class="reprows">${reps}</div>
        ${admin?`<div class="dictadd"><input id="tdFrom" placeholder="heard…" style="flex:1"/><span class="rarrow">→</span><input id="tdTo" placeholder="correct…" style="flex:1"/><button class="btn primary" style="flex:none;width:80px" onclick="tdAddRep()">Add</button></div>`:''}
      </div>
    </div>
    <div class="dictcol${ro}" style="margin-top:18px">
      <div class="dcolhead"><h3>Shared snippets</h3><p class="ssub">A spoken phrase everyone can expand.</p></div>
      <div class="reprows">${snips}</div>
      ${admin?`<div class="dictadd"><input id="tdTrig" placeholder="say this…" style="flex:1"/><span class="rarrow">→</span><input id="tdExp" placeholder="expands to…" style="flex:2"/><button class="btn primary" style="flex:none;width:80px" onclick="tdAddSnip()">Add</button></div>`:''}
    </div>`;
}

function renderDictionary(){
  // Team scope renders a different page entirely; the tabs live in both heads.
  if(DICT_SCOPE==='team' && hasTeam()){ renderTeamDictionary(); return; }
  const vocab = DICT.vocabulary.map((w,i)=>`<span class="dchip">${esc(w)}<button onclick="removeWord(${i})" title="Remove">✕</button></span>`).join('')
    || '<span class="ssub" style="margin:0">No words yet — add names, products, acronyms, anything Flume mishears.</span>';
  const reps = DICT.replacements.map((r,i)=>`<div class="reprow"><span class="rfrom">${esc(r.from)}</span><span class="rarrow">→</span><span class="rto">${esc(r.to)}${r.auto?' <span title="Auto-learned from a correction" style="opacity:.75">✨</span>':''}</span><button onclick="removeRep(${i})" title="Remove">✕</button></div>`).join('')
    || '<span class="ssub" style="margin:0">No rules yet — or edit a transcription in History and Flume learns one automatically.</span>';
  document.getElementById('dictionaryMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Transcription</div>
      <h1 class="title">Dictionary ${dictScopeTabs()}</h1></div>
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
  else if(event==='state'){ STATE=payload; applyAuthGate(); renderSidebar(); renderActive(); if(STATE&&STATE.signed_in) checkInviteLink(); }
  else if(event==='selectTab'){ if(payload && payload.tab) show(payload.tab); }
  else if(event==='result'){ load(); }
  else if(event==='canvasRemote'){
    CANVAS={content:payload.content||'', image_url:payload.image_url||null,
            from:payload.device_name||'', at:new Date().toISOString(), own:false};
    CV_EXPAND=false;
    if(payload.image_url) cvLog('image','Image', payload.device_name, false);
    else if((payload.content||'').trim()) cvLog(cvIsUrl(payload.content)?'link':'text', payload.content, payload.device_name, false);
    if(ACTIVE==='canvas')renderCanvas(); }
  else if(event==='meetingsUpdated'){ loadMeets();
    refreshOpenMeeting(payload && payload.id, payload && payload.deleted); }
  // MER-46: open_meeting hands the row straight to the detail view. Buffered on
  // the Python side until `dashboard_page_ready`, so this also works when the
  // window was built by this very click (the meeting bar's handoff).
  else if(event==='openMeeting'){ openMeetingDetail(payload); }
  // Deep link `flume://invite?t=…` (app/deep_link.py): the token is parked in
  // config; ask Python for the preview and offer the join. Signed-out users get
  // the sign-in wall first — checkInviteLink re-runs on the next `state` event.
  else if(event==='inviteLink'){ TM_LINK_SHOWN=false; checkInviteLink(); }
  // Periodic device-presence refresh (SharedDashboard._device_refresh_loop,
  // every 30s) — previously dropped client-side (no handler), so the sidebar/
  // popover/Home pill only ever reflected the device list from page load.
  else if(event==='devices'){
    if(STATE){ STATE.devices=payload.devices||[]; STATE.target_device_id=payload.target_device_id||'__all__'; }
    renderSidebar();
    if(ACTIVE==='devices') renderDevices();
    if(ACTIVE==='home') renderHome();
  }
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
    content=`<div class="gstitle">A few permissions.</div><div class="gslead">Flume needs these to paste transcriptions and record meetings on this ${DEVICE_NOUN}.</div>${rows}`;
  } else if(WSTEP===2){
    // The wizard is only ever reachable when signed_in is true — applyAuthGate
    // gives the sign-in wall priority over the onboarded check — so STATE.user
    // is always populated here. The old `!STATE.user` "Sign in" fallback was
    // dead code and has been removed (IDI-166).
    const u=(STATE&&STATE.user)||{};
    content=`<div class="gstitle">Sync across your devices.</div>
      <div class="gslead">Signed in as ${esc(u.email||'your account')}. Your dictation, notes and canvas stay in sync everywhere you sign in.</div>
      <div class="permrow"><div class="permicon ok">${WIZ_ICON.phone}</div><div class="perminfo"><div class="permname">${THIS_DEVICE}</div><div class="permsub">Synced to your account</div></div><span class="permpill"><span class="pdot"></span>Active</span></div>`;
  } else {
    content=`<div class="gstitle">You're all set.</div>
      <div class="gslead">Hold your hotkey anywhere to dictate — it lands in your clipboard and pastes automatically. Open Flume from the ${IS_WINDOWS?'system tray':'menu bar'} any time.</div>
      <div class="permrow"><div class="permicon ok">${WIZ_ICON.check}</div><div class="perminfo"><div class="permname">Ready to go</div><div class="permsub">Everything is configured.</div></div></div>`;
  }
  const back = WSTEP>1?`<button class="btn ghost" style="flex:none" onclick="wizBack()">Back</button>`:'';
  el.innerHTML=`<div class="gsstep">STEP ${WSTEP} OF 3</div><div class="gsbar"><i style="width:${pct}%"></i></div>${content}
    <div class="gsnav">${back}<span class="grow"></span><button class="btn primary" style="flex:none;min-width:160px" onclick="wizNext()">${WSTEP<3?'Continue':'Start using Flume'}</button></div>`;
}

let LOAD_STARTED=false;
async function load(){
  // Probe for a waiting invite at startup, not just when Team is opened —
  // otherwise the sign-in popup only fires for people who already went looking.
  loadTeam(true);
  startUpdateBannerPolling();
  LOAD_STARTED=true;
  // MER-46 handshake. VerbalNative is installed by now (it is assigned at parse
  // time) and the bridge is live (pywebviewready fired, or the backstop ran), so
  // Python can flush the events it queued while the page loaded — that is how an
  // `openMeeting` survives being pushed into a window built a moment earlier.
  // Deliberately BEFORE the awaits: the flush must not wait on get_state.
  api('dashboard_page_ready');
  const r = await api('get_state');
  if(r && r.ok){ STATE=r; applyAuthGate(); renderSidebar(); }
  // First paint must never wait on the network. This used to `await`
  // fetch_notes (a Supabase round-trip) before renderActive(), so on a slow or
  // dropped connection the window sat dark for seconds-to-timeout and read as
  // "the app crashed on launch" (Windows, 2026-08-28). Render from local state
  // now; loadNotes() re-renders Home/Notes when the notes arrive.
  renderActive();
  loadNotes();
  loadCanvas();
}
// Explicit navigation always lands on a screen's TOP level: clicking Meetings
// while reading one meeting goes back to the list (MER-46), where an
// openMeeting event (which sets the sub-route first) must not be reset.
// ── Team / Organization (IDI-216) ─────────────────────────────────────────
// Four views off one screen: no team, just-created setup, the team, one member.
// The last two deliberately reuse the INSIGHTS vocabulary (.inshero gauge,
// .itile pastel band, .inshm heatmap) — "numbers about you" already has a house
// style here, and a Team screen that invented its own would read as a different
// product. Everything fails closed: get_team returns the same no-org shape for a
// user with no team, an unapplied migration and a dead network alike.
let TEAM=null, TEAM_INV=[], TEAM_USAGE=null, TEAM_BOARD=null;
let TEAM_SERIES={}, TEAM_PERSONAL=null, TEAM_SETUP=true;
let TEAM_SEL='all', TEAM_DAYS=30, TEAM_ERR='', TEAM_PENDING=[], TM_JOIN_SHOWN=false;
let TM_LINK=null, TM_LINK_SHOWN=false;   // invite arriving via deep link (flume://invite)
let TEAM_APPS={};   // {user_id: [{app,dictations,words}]} — see get_team_apps

const hasTeam   = () => !!(TEAM && TEAM.org_id);
const teamAdmin = () => hasTeam() && (TEAM.role==='owner' || TEAM.role==='admin');
const teamOwner = () => hasTeam() && TEAM.role==='owner';
const teamMe    = () => (STATE && STATE.settings && STATE.settings.sync_user_id) || '';
function tmInit(m){ return ((m.display_name||m.email||'?').trim()[0]||'?').toUpperCase(); }
function tmMins(ms){ const m=Math.round((ms||0)/60000); return m>=60 ? (m/60).toFixed(1)+'h' : m+'m'; }
function tmWhen(iso){
  if(!iso) return '—';
  const t=Date.parse(iso); if(isNaN(t)) return '—';
  const d=Math.floor((Date.now()-t)/86400000);
  return d<=0?'today':d===1?'yesterday':d+'d ago';
}
// Words ÷ minutes of speech. Only shown when there is enough measured audio to
// mean anything — duration_ms is NULL on older rows, so a thin sample would
// invent a number rather than report one.
function tmWpm(u){
  if(!u || !u.speech_ms || u.speech_ms < 120000) return null;
  return Math.round((u.words||0) / (u.speech_ms/60000));
}
function tmUsageFor(uid){ return ((TEAM_USAGE&&TEAM_USAGE.rows)||[]).find(r=>r.user_id===uid) || null; }

// ── data ────────────────────────────────────────────────────────────────────
function loadTeam(refresh){
  return api('get_team', !!refresh).then(r=>{
    if(r&&r.ok){
      TEAM=r.team||null; TEAM_ERR=r.sync_error||'';
      TEAM_SETUP=r.setup_done!==false; TEAM_PERSONAL=r.personal||null;
      if(hasTeam()) loadTeamExtras(); else { TEAM_INV=[]; TEAM_USAGE=null; TEAM_BOARD=null; TEAM_SERIES={}; TEAM_APPS={}; }
      // IDI-222: an invite whose emailed link never reached the app is still
      // recoverable by matching the signed-in address server-side.
      api('get_pending_invites').then(p=>{
        if(p&&p.ok){
          TEAM_PENDING=p.invites||[];
          teamRepaint();
          // Surface it wherever the user happens to be. Once per app run, and only
          // when they are not already in a team — an invitation you have to go
          // looking for is one you never see.
          if(TEAM_PENDING.length && !hasTeam() && !TM_JOIN_SHOWN){ TM_JOIN_SHOWN=true; tmOpenJoin(); }
        }
      });
      checkInviteLink();
    } else { TEAM=null; TEAM_ERR=(r&&r.error)||''; }
    teamRepaint();
  });
}
// Each payload paints on its own — a failing leaderboard must never blank a
// roster that already loaded.
function loadTeamExtras(){
  api('get_team_series', 98).then(r=>{ if(r&&r.ok){ TEAM_SERIES=r.series||{}; teamRepaint(); } });
  api('get_team_leaderboard', 7).then(r=>{ if(r&&r.ok){ TEAM_BOARD=r; teamRepaint(); } });
  // Usage and app-mix are fetched for EVERYONE. The RPCs decide what comes back —
  // an owner/admin gets every consenting member, a plain member gets exactly their
  // own row. Gating the *request* on teamAdmin() was why a member's Team screen
  // was all zeroes: every total on that page is derived from these rows.
  api('get_team_usage', TEAM_DAYS).then(r=>{ if(r&&r.ok){ TEAM_USAGE=r; teamRepaint(); } });
  api('get_team_apps', TEAM_DAYS).then(r=>{ if(r&&r.ok){ TEAM_APPS=r.apps||{}; teamRepaint(); } });
  // Invites are genuinely admin-only — there is no member-scoped version.
  if(teamAdmin()){
    api('list_team_invites').then(r=>{ if(r&&r.ok){ TEAM_INV=r.invites||[]; teamRepaint(); } });
  }
}
// The team payload backs the Team screen AND Settings' Team privacy group, and
// the roster rail's badge. Paint whichever is on screen; painting the other is a
// no-op because both bail on a missing container.
function teamRepaint(){
  if(ACTIVE==='team') renderTeam();
  else if(ACTIVE==='settings' && SETTINGS_GROUP==='privacy') renderSettings();
}
function teamDays(v){
  TEAM_DAYS=parseInt(v,10)||30;
  api('get_team_usage',TEAM_DAYS).then(r=>{ if(r&&r.ok){ TEAM_USAGE=r; renderTeam(); } });
  api('get_team_apps',TEAM_DAYS).then(r=>{ if(r&&r.ok){ TEAM_APPS=r.apps||{}; renderTeam(); } });
}
// Mutations always repaint from what the backend returned, never from an
// optimistic local edit — roles and membership are other people's data too.
function teamApply(r, okMsg){
  if(r && r.busy) return false;
  if(r && r.ok){
    if(r.team) TEAM=r.team;
    if(r.invites) TEAM_INV=r.invites;
    if(okMsg) toast(okMsg);
    loadTeamExtras(); teamRepaint(); return true;
  }
  toast((r&&r.error)||'Something went wrong.', true); teamRepaint(); return false;
}

function createTeam(){
  const el=document.getElementById('tmName'); const name=(el&&el.value||'').trim();
  if(!name){ toast('Give the team a name.', true); return; }
  busyGuard('team', ()=>api('create_team', name, '')).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ TEAM_SETUP=false; TEAM_SEL='all'; loadTeam(true); toast('Team created'); }
    else toast((r&&r.error)||'Could not create the team.', true);
  });
}
function claimTeamInvite(confirmed){
  const el=document.getElementById('tmToken');
  // Keep the pasted value across the confirm round trip — re-rendering the screen
  // would otherwise clear the field out from under the user.
  const v = (typeof confirmed === 'string') ? confirmed : ((el&&el.value||'').trim());
  if(!v){ toast('Paste your invite link or code.', true); return; }
  const isConfirm = arguments.length > 1 && arguments[1] === true;
  busyGuard('team', ()=>api('claim_team_invite', v, isConfirm)).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ TEAM_SEL='all'; loadTeam(true); toast(r.already?'You were already on this team':'Welcome to the team'); return; }
    // IDI-223: the token is the source of truth, so a wrong-account claim is a
    // QUESTION, not a refusal — "Sign in with Apple" hands back a privaterelay
    // address and strict equality would lock that person out permanently.
    // Only ever prompt ONCE. If a confirmed retry still comes back needing
    // confirmation, something is wrong server-side — showing the dialog again
    // would loop forever (it did, in the harness).
    if(r && r.needs_confirm && !isConfirm){
      const msg = 'This invite was sent to '+(r.invited_email||'another address')
        + ', but you are signed in as '+(r.current_email||'this account')+'.'
        + '\n\nJoin as '+(r.current_email||'this account')+' anyway?';
      if(confirm(msg)) claimTeamInvite(v, true);
      return;
    }
    if(r && r.needs_confirm && isConfirm){
      toast('Could not join with this account. Sign in as '+(r.invited_email||'the invited address')+'.', true);
      return;
    }
    toast((r&&r.error)||'That invite could not be used.', true);
  });
}
function declineTeamInvite(){
  const el=document.getElementById('tmToken'); const v=(el&&el.value||'').trim();
  if(!v){ toast('Paste the invite link first.', true); return; }
  if(!confirm('Decline this invite? The team will see that you turned it down.')) return;
  busyGuard('team', ()=>api('decline_team_invite', v)).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ if(el) el.value=''; TEAM_PENDING=[]; toast('Invite declined'); renderTeam(); }
    else toast((r&&r.error)||'Could not decline that invite.', true);
  });
}
function acceptPendingInvite(orgId){
  busyGuard('team', ()=>api('accept_pending_invite', orgId)).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ TEAM_PENDING=[]; TEAM_SEL='all'; loadTeam(true); toast('Welcome to the team'); }
    else toast((r&&r.error)||'That invite could not be used.', true);
  });
}
function setTeamAutoJoin(on){
  busyGuard('team', ()=>api('set_team_auto_join', on)).then(r=>teamApply(r, on?'Domain joining on':'Domain joining off'));
}
function inviteMember(fieldId){
  const e=document.getElementById(fieldId||'tmEmail');
  const r0=document.getElementById((fieldId||'tmEmail')+'Role');
  const email=(e&&e.value||'').trim();
  if(!email){ toast('Enter an email address.', true); return; }
  busyGuard('team', ()=>api('invite_member', email, (r0&&r0.value)||'member')).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){
      TEAM_INV=r.invites||TEAM_INV; TEAM_SETUP=true;
      if(e) e.value='';
      toast((r.reissued?'Invite resent to ':'Invite sent to ')+email);
      if(r.link){ try{ navigator.clipboard.writeText(r.link); }catch(_){} }
      renderTeam();
    } else toast((r&&r.error)||'Could not send the invite.', true);
  });
}
// The shared dictionary is edited on the Dictionary screen (scope = team), not on
// Team. TEAM.dictionary is the authoritative copy the sync gave us; every mutator
// writes through the backend and repaints from what came back, because this is a
// document several admins can be editing at once (save_team_dictionary is a CAS
// on updated_at and will refuse a stale write).
function tdict(){
  const d=(TEAM&&TEAM.dictionary)||{};
  return {vocabulary:d.vocabulary||[], replacements:d.replacements||[], snippets:d.snippets||[]};
}
function tdSave(next, msg){
  busyGuard('team', ()=>api('save_team_dictionary', next.vocabulary, next.replacements, next.snippets))
    .then(r=>{
      if(r && r.busy) return;
      if(r&&r.ok){
        if(r.team) TEAM=r.team; else if(TEAM) TEAM.dictionary=next;
        dictSetState('Shared with the team');
        setTimeout(()=>dictSetState(''), 2200);
        if(msg) toast(msg);
      } else toast((r&&r.error)||'Could not save the shared dictionary.', true);
      renderDictionary();
    });
}
function tdAddWord(){
  const el=document.getElementById('tdWord'); const w=(el&&el.value||'').trim();
  if(!w) return;
  const d=tdict();
  if(d.vocabulary.some(x=>x.toLowerCase()===w.toLowerCase())){ toast('Already shared.', true); return; }
  d.vocabulary=d.vocabulary.concat([w]); if(el) el.value='';
  tdSave(d, '"'+w+'" shared with the team');
}
function tdRmWord(i){ const d=tdict(); const w=d.vocabulary[i]; d.vocabulary=d.vocabulary.filter((_,k)=>k!==i); tdSave(d, w?'Removed "'+w+'"':''); }
function tdAddRep(){
  const a=document.getElementById('tdFrom'), b=document.getElementById('tdTo');
  const from=(a&&a.value||'').trim(), to=(b&&b.value||'').trim();
  if(!from||!to){ toast('Both sides are needed.', true); return; }
  const d=tdict();
  if(d.replacements.some(r=>(r.from||'').toLowerCase()===from.toLowerCase())){ toast('A shared rule already covers that.', true); return; }
  d.replacements=d.replacements.concat([{from:from,to:to}]);
  if(a) a.value=''; if(b) b.value='';
  tdSave(d, 'Shared rule added');
}
function tdRmRep(i){ const d=tdict(); d.replacements=d.replacements.filter((_,k)=>k!==i); tdSave(d, 'Shared rule removed'); }
function tdAddSnip(){
  const a=document.getElementById('tdTrig'), b=document.getElementById('tdExp');
  const trigger=(a&&a.value||'').trim(), expansion=(b&&b.value||'').trim();
  if(!trigger||!expansion){ toast('A trigger and an expansion are needed.', true); return; }
  const d=tdict();
  if(d.snippets.some(sn=>(sn.trigger||'').toLowerCase()===trigger.toLowerCase())){ toast('That trigger is already shared.', true); return; }
  d.snippets=d.snippets.concat([{trigger:trigger, expansion:expansion}]);
  if(a) a.value=''; if(b) b.value='';
  tdSave(d, 'Shared snippet added');
}
function tdRmSnip(i){ const d=tdict(); d.snippets=d.snippets.filter((_,k)=>k!==i); tdSave(d, 'Shared snippet removed'); }

function seedTeamDict(){
  busyGuard('team', ()=>api('seed_team_dictionary')).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){
      const a=r.added||{};
      TEAM_SETUP=true;
      toast('Shared '+(a.vocabulary||0)+' words with the team');
      loadTeam(true);
    } else toast((r&&r.error)||'Could not copy your dictionary.', true);
  });
}
function skipTeamSetup(){ TEAM_SETUP=true; api('dismiss_team_setup'); renderTeam(); }
function revokeInvite(id){ busyGuard('team', ()=>api('revoke_team_invite', id)).then(r=>teamApply(r,'Invite revoked')); }
function setMemberRole(uid, role){ busyGuard('team', ()=>api('set_member_role', uid, role)).then(r=>teamApply(r,'Role updated')); }
function removeMember(uid, name){
  const who = name || 'this member';
  if(!confirm('Remove '+who+' from the team?\n\n'
    + 'They keep their own dictionary, history and recordings — only the shared ones stop applying. '
    + 'The seat frees up immediately, and you can invite them again with the same email whenever you like.')) return;
  busyGuard('team', ()=>api('remove_team_member', uid)).then(r=>{
    if(teamApply(r, who+' removed')) TEAM_SEL='all';
  });
}
function leaveTeam(){
  if(!confirm('Leave this team? You keep your own dictionary and history; the shared ones stop applying.')) return;
  busyGuard('team', ()=>api('leave_team')).then(r=>{
    if(teamApply(r,'You left the team')){ TEAM_INV=[]; TEAM_USAGE=null; TEAM_BOARD=null; TEAM_SERIES={}; TEAM_APPS={}; TEAM_SEL='all'; }
  });
}
function toggleTeamBoard(){ busyGuard('team', ()=>api('set_team_settings', {leaderboard_enabled: !TEAM.leaderboard_enabled})).then(r=>teamApply(r,'Saved')); }
function toggleTeamStatsVisible(){ busyGuard('team', ()=>api('set_team_settings', {stats_visible_to_members: !TEAM.stats_visible_to_members})).then(r=>teamApply(r,'Saved')); }
function setTeamConsent(u,b){ busyGuard('team', ()=>api('set_team_consent', u, b)).then(r=>teamApply(r,'Preference saved')); }
function selectMember(uid){ TEAM_SEL=uid; renderTeam(); }

// ── series helpers ──────────────────────────────────────────────────────────
function tmDayKeys(n){
  const out=[], now=new Date();
  for(let i=n-1;i>=0;i--){
    const d=new Date(now.getTime()-i*86400000);
    out.push(d.toISOString().slice(0,10));
  }
  return out;
}
function tmSparkHtml(uid){
  const ser=TEAM_SERIES[uid];
  const days=tmDayKeys(14);
  if(!ser){ return '<div class="tmspark off">'+days.map(()=>'<i style="height:20%"></i>').join('')+'</div>'; }
  const vals=days.map(d=>ser[d]||0);
  const mx=Math.max(1,...vals);
  return '<div class="tmspark">'+vals.map(v=>'<i style="height:'+Math.max(8,Math.round(v/mx*100))+'%"></i>').join('')+'</div>';
}
const TM_STEPS=['#1f2225','#4a2d24','#7a4030','#a84b33','#C85A3E','#E88D6A'];
function tmHeatHtml(uid){
  const ser=TEAM_SERIES[uid]||{};
  const days=tmDayKeys(98);
  const first=new Date(days[0]+'T00:00:00');
  const pad=first.getDay();
  const cells=[];
  for(let i=0;i<pad;i++) cells.push(null);
  days.forEach(d=>cells.push([d, ser[d]||0]));
  const mx=Math.max(1,...cells.filter(Boolean).map(c=>c[1]));
  let best=null;
  cells.forEach(c=>{ if(c && (!best || c[1]>best[1])) best=c; });
  const html=cells.map(c=>{
    if(!c) return '<i style="visibility:hidden"></i>';
    let idx=0;
    if(c[1]>0){ const f=c[1]/mx; idx=f<.15?1:f<.35?2:f<.6?3:f<.85?4:5; }
    return '<i style="background:'+TM_STEPS[idx]+'"'
      +' onmouseenter="insTip(this,\'' + c[0] + ' <span class=tmut>&middot;</span> ' + fmtN(c[1]) + ' words\')"'
      +' onmouseleave="insTip(null)"></i>';
  }).join('');
  const legend=TM_STEPS.map(c=>'<i style="background:'+c+'"></i>').join('');
  const foot = (best && best[1]>0)
    ? 'Busiest day <b>'+esc(best[0])+'</b> — <b>'+fmtN(best[1])+'</b> words'
    : 'Every square is a day they dictated.';
  return '<div class="inscard"><div class="chd"><span>Activity</span><span class="csub">day by day</span></div>'
    +'<div class="inshm tmhm">'+html+'</div>'
    +'<div class="inshmfoot"><span>'+foot+'</span>'
    +'<span class="inshmleg">less '+legend+' more</span></div></div>';
}
// Sizes the heatmap cells to the pane, same job as insHeatmap() does for Insights.
function tmSizeHeat(){
  const box=document.querySelector('#teamMain .tmhm');
  if(!box) return;
  const n=box.children.length, weeks=Math.ceil(n/7), gap=3;
  let cell=Math.floor(((box.clientWidth||760)-(weeks-1)*gap)/weeks);
  cell=Math.max(8, Math.min(14, cell));
  box.style.gridTemplateRows='repeat(7,'+cell+'px)';
  [].forEach.call(box.children, el=>{ el.style.width=cell+'px'; el.style.height=cell+'px'; });
}

// Contribution ring — the team's answer to the Insights WPM gauge. One number in
// the middle, the split around it, so an unbalanced team is visible at a glance.
function tmRingSvg(parts, total){
  const R=62, C=2*Math.PI*R, S=150;
  let off=0, segs='';
  parts.forEach(p=>{
    const len=Math.max(0, (p.pct/100)*C - (parts.length>1?3:0));
    if(len<=0) return;
    segs+='<circle cx="75" cy="75" r="'+R+'" fill="none" stroke="'+p.col+'" stroke-width="13"'
       +' stroke-linecap="round" stroke-dasharray="'+len.toFixed(1)+' '+(C-len).toFixed(1)+'"'
       +' stroke-dashoffset="'+(-off).toFixed(1)+'" transform="rotate(-90 75 75)"></circle>';
    off += (p.pct/100)*C;
  });
  return '<svg width="'+S+'" height="'+S+'" viewBox="0 0 150 150" style="flex:none">'
    +'<circle cx="75" cy="75" r="'+R+'" fill="none" stroke="rgba(240,240,240,.05)" stroke-width="13"></circle>'
    +segs
    +'<text x="75" y="70" text-anchor="middle" style="font:600 26px Geist;letter-spacing:-.03em" fill="#f2f2f2">'+fmtN(total)+'</text>'
    +'<text x="75" y="88" text-anchor="middle" style="font:500 8.5px \'JetBrains Mono\';letter-spacing:.18em" fill="rgba(240,240,240,.55)">WORDS</text>'
    +'</svg>';
}
// The same semicircular gauge Insights draws for WPM.
function tmGaugeSvg(wpm){
  const W=200,H=108,cx=100,cy=100,r=86;
  const P=a=>({x:cx+r*Math.cos(a), y:cy+r*Math.sin(a)});
  const arc=(a0,a1,col)=>{
    const p0=P(a0), p1=P(a1);
    return '<path d="M '+p0.x.toFixed(1)+' '+p0.y.toFixed(1)+' A '+r+' '+r+' 0 '
      +((a1-a0)>Math.PI?1:0)+' 1 '+p1.x.toFixed(1)+' '+p1.y.toFixed(1)+'" stroke="'+col
      +'" stroke-width="13" fill="none" stroke-linecap="round"/>';
  };
  let s='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'">';
  s+=arc(Math.PI, 2*Math.PI, 'rgba(240,240,240,.08)');
  if(wpm){
    s+=arc(Math.PI, Math.PI+Math.PI*Math.min(1,wpm/200), '#C85A3E');
    const t=P(Math.PI+Math.PI*(52/200));
    s+='<circle cx="'+t.x.toFixed(1)+'" cy="'+t.y.toFixed(1)+'" r="4" fill="#0e1012" stroke="rgba(240,240,240,.6)" stroke-width="1.5"><title>Average typist — 52 wpm</title></circle>';
  }
  return s+'</svg>';
}

// ── modals ──────────────────────────────────────────────────────────────────
let TM_MODAL=null, TM_INV_ROLE='member', TM_INV_BUSY=false, TM_INV_ERR='';

function tmCloseModal(){ TM_MODAL=null; TM_INV_ERR=''; tmRenderModal(); }
function tmOpenInvite(){ TM_MODAL='invite'; TM_INV_ROLE='member'; TM_INV_ERR=''; tmRenderModal();
  setTimeout(()=>{ const el=document.getElementById('tmmEmail'); if(el) el.focus(); },0); }
// Fires after sign-in when an invite is waiting, from anywhere in the app — an
// invitation the user has to go hunting for is an invitation they never see.
function tmOpenJoin(){ TM_MODAL='join'; tmRenderModal(); }
// ── invite via deep link ────────────────────────────────────────────────────
function checkInviteLink(){
  if(!(STATE&&STATE.signed_in)) return;           // sign-in wall first; re-checked on `state`
  api('get_invite_link').then(r=>{
    if(!(r&&r.ok&&r.pending)) return;
    TM_LINK=r;
    if(TM_LINK_SHOWN && TM_MODAL==='joinlink') return;
    TM_LINK_SHOWN=true; TM_MODAL='joinlink'; tmRenderModal();
  });
}
function tmJoinLinkModalHtml(){
  const p=TM_LINK||{};
  const who = p.inviter_name||p.invited_by||p.inviter_email||'';
  return `
  <div class="tmmodal" onclick="if(event.target===this) tmDismissJoinLink()">
    <div class="tmmodalbox wide">
      <div class="tmmhead">
        <div class="tmmico cream">${SVG.mail}</div>
        <div class="tmmtitle"><h3>Join ${esc(p.org_name||'your team')}</h3>
          <p>${who?esc(who)+' invited you':'You were invited'} as ${esc(p.role||'member')}. Their shared dictionary and snippets start working on your next dictation.</p></div>
        <button class="tmmx" onclick="tmDismissJoinLink()">&times;</button>
      </div>
      <div class="tmmnote" style="margin-top:0">
        Your own dictionary stays yours and still wins if the two ever disagree.
        Nothing you dictate is shared with the team.
      </div>
      <div class="tmmfoot">
        <span class="grow"></span>
        <button class="btn ghost" style="flex:none;width:auto;padding:11px 16px" onclick="tmDismissJoinLink()">Not now</button>
        <button class="btn primary" style="flex:none;width:auto;padding:11px 20px" onclick="tmAcceptJoinLink()">Join ${esc(p.org_name||'team')}</button>
      </div>
    </div>
  </div>`;
}
function tmDismissJoinLink(){ TM_MODAL=null; tmRenderModal(); api('clear_invite_link'); TM_LINK=null; }
function tmAcceptJoinLink(){
  const t=(TM_LINK&&TM_LINK.token)||''; TM_MODAL=null; tmRenderModal();
  if(!t) return;
  // Same claim path as the pasted-link field (IDI-223 confirm round trip included).
  claimTeamInvite(t);
  api('clear_invite_link'); TM_LINK=null;
}

function tmRenderModal(){
  const host=document.getElementById('tmModalHost');
  if(!host) return;
  if(!TM_MODAL){ host.innerHTML=''; return; }
  if(TM_MODAL==='invite') host.innerHTML=tmInviteModalHtml();
  else if(TM_MODAL==='join') host.innerHTML=tmJoinModalHtml();
  else if(TM_MODAL==='joinlink') host.innerHTML=tmJoinLinkModalHtml();
}

function tmInviteModalHtml(){
  const seats=(TEAM&&TEAM.seats)||0, used=((TEAM&&TEAM.members)||[]).length;
  const pending=TEAM_INV.length;
  let dots='';
  for(let i=0;i<Math.max(seats,used);i++) dots+='<i class="'+(i<used?'taken':'')+'"></i>';
  return `
  <div class="tmmodal" onclick="if(event.target===this) tmCloseModal()">
    <div class="tmmodalbox">
      <div class="tmmhead">
        <div class="tmmico">${SVG.team}</div>
        <div class="tmmtitle"><h3>Add a teammate</h3>
          <p>They get a one-time link that expires in 7 days and only works for the address you send it to.</p></div>
        <button class="tmmx" onclick="tmCloseModal()">&times;</button>
      </div>
      <div class="tmmlabel">EMAIL ADDRESS</div>
      <input class="tmminput" id="tmmEmail" placeholder="name@company.com" autocomplete="off"
             onkeydown="if(event.key==='Enter'){event.preventDefault();tmSubmitInvite();}"/>
      <div class="tmmlabel" style="margin-top:16px">THEY JOIN AS</div>
      <div class="tmmroles">
        <button class="${TM_INV_ROLE==='member'?'on':''}" onclick="TM_INV_ROLE='member';tmRenderModal()">Member</button>
        <button class="${TM_INV_ROLE==='admin'?'on':''}" onclick="TM_INV_ROLE='admin';tmRenderModal()">Admin</button>
      </div>
      <div class="tmmnote">${TM_INV_ROLE==='admin'
        ? 'Admins can invite people, change roles and edit the shared dictionary.'
        : 'Members dictate with the shared dictionary and manage their own privacy.'}</div>
      <div class="tmmseat"><div class="d">${dots}</div>
        <span>${used} of ${seats} seats used${used?' (including you)':''}${pending?` &middot; ${pending} invite${pending===1?'':'s'} out`:''}</span></div>
      ${TM_INV_ERR?`<div class="tmmnote" style="color:var(--acc-txt)">${esc(TM_INV_ERR)}</div>`:''}
      <div class="tmmfoot">
        <span class="grow"></span>
        <button class="btn ghost" style="flex:none;width:auto;padding:11px 16px" onclick="tmCloseModal()">Cancel</button>
        <button class="btn primary" style="flex:none;width:auto;padding:11px 20px" id="tmmSend"
                onclick="tmSubmitInvite()">${TM_INV_BUSY?'Sending…':'Send invite'}</button>
      </div>
    </div>
  </div>`;
}

function tmSubmitInvite(){
  if(TM_INV_BUSY) return;
  const el=document.getElementById('tmmEmail');
  const email=(el&&el.value||'').trim();
  if(!email){ TM_INV_ERR='Enter an email address.'; tmRenderModal(); return; }
  TM_INV_BUSY=true; TM_INV_ERR=''; tmRenderModal();
  api('invite_member', email, TM_INV_ROLE).then(r=>{
    TM_INV_BUSY=false;
    if(r&&r.ok){
      TEAM_INV=r.invites||TEAM_INV;
      TEAM_SETUP=true; TM_MODAL=null; tmRenderModal();
      toast((r.reissued?'Invite resent to ':'Invite sent to ')+email);
      if(r.link){ try{ navigator.clipboard.writeText(r.link); }catch(_){} }
      renderTeam();
    } else {
      // Errors stay INSIDE the modal. A toast behind a dialog is a dead end —
      // the user is still looking at the form that failed.
      TM_INV_ERR=(r&&r.error)||'Could not send the invite.';
      tmRenderModal();
    }
  });
}

function tmJoinModalHtml(){
  const p=TEAM_PENDING[0]||{};
  return `
  <div class="tmmodal" onclick="if(event.target===this) tmCloseModal()">
    <div class="tmmodalbox wide">
      <div class="tmmhead">
        <div class="tmmico cream">${SVG.mail}</div>
        <div class="tmmtitle"><h3>${esc(p.org_name||'A team')} invited you</h3>
          <p>Join as ${esc(p.role||'member')} and their shared dictionary and snippets start working on your next dictation.</p></div>
        <button class="tmmx" onclick="tmCloseModal()">&times;</button>
      </div>
      <div class="tmmnote" style="margin-top:0">
        Your own dictionary stays yours and still wins if the two ever disagree.
        Nothing you dictate is shared with the team.
      </div>
      <div class="tmmfoot">
        <span class="grow"></span>
        <button class="btn ghost" style="flex:none;width:auto;padding:11px 16px" onclick="tmDismissJoin()">Not now</button>
        <button class="btn primary" style="flex:none;width:auto;padding:11px 20px"
                onclick="tmAcceptJoin(${esc(JSON.stringify(p.org_id||''))})">Join ${esc(p.org_name||'team')}</button>
      </div>
    </div>
  </div>`;
}
function tmDismissJoin(){ TM_MODAL=null; tmRenderModal(); }
function tmAcceptJoin(orgId){
  api('accept_pending_invite', orgId).then(r=>{
    if(r&&r.ok){ TEAM_PENDING=[]; TM_MODAL=null; tmRenderModal(); TEAM_SEL='all';
      loadTeam(true); toast('Welcome to the team'); navTo('team'); }
    else { TM_MODAL=null; tmRenderModal(); toast((r&&r.error)||'That invite could not be used.', true); }
  });
}
function resendInvite(email, role){
  busyGuard('team', ()=>api('invite_member', email, role||'member')).then(r=>{
    if(r && r.busy) return;
    if(r&&r.ok){ TEAM_INV=r.invites||TEAM_INV; toast('Invite resent to '+email); renderTeam(); }
    else toast((r&&r.error)||'Could not resend that invite.', true);
  });
}

// ── views ───────────────────────────────────────────────────────────────────
function teamStartHtml(){
  const p=TEAM_PERSONAL||{vocabulary:0,replacements:0,snippets:0};
  const have=(p.vocabulary||0)+(p.replacements||0);
  return `
  <div class="tmstart"><div class="tmstartin">
    ${TEAM_PENDING.map(p=>`
      <div class="tmpendbox">
        <div class="pbico">${SVG.mail}</div>
        <div class="pbtx">
          <b>${esc(p.org_name||'A team')} invited you</b>
          <span>Waiting for you as ${esc(p.role||'member')} &middot; no link needed</span>
        </div>
        <button class="btn primary" style="flex:none;width:auto;padding:10px 16px" onclick="acceptPendingInvite(${esc(JSON.stringify(p.org_id))})">Accept</button>
      </div>`).join('')}
    <div class="tmhero">
      <div class="bigico">${SVG.team}</div>
      <h2>Teach Flume your words once</h2>
      <p>A team shares one dictionary and one set of snippets. Your colleagues' first dictation already knows your product names, your clients and your jargon.</p>
    </div>
    <div class="tmdemo">
      <div class="chd" style="margin-bottom:15px">A NEW TEAMMATE SAYS &ldquo;IDIAZ NEEDS A NEW ONE&rdquo;</div>
      <div class="tmdemogrid">
        <div class="col"><div class="lab"><i></i>ON THEIR OWN</div>
          <div class="say">&ldquo;<span class="bad">Ideas</span> needs a new one.&rdquo;</div></div>
        <div class="col win"><div class="lab"><i></i>ON YOUR TEAM</div>
          <div class="say">&ldquo;<b>Idiaz</b> needs a new one.&rdquo;</div></div>
      </div>
      ${have?`<div class="tmfine" style="text-align:left;margin-top:13px">You already have <b style="color:var(--tx2)">${p.vocabulary} word${p.vocabulary===1?'':'s'} and ${p.replacements} rule${p.replacements===1?'':'s'}</b> Flume could share with them.</div>`:''}
    </div>
    <div class="tmcreate">
      <input id="tmName" placeholder="Name your team…" onkeydown="if(event.key==='Enter'){event.preventDefault();createTeam();}"/>
      <button onclick="createTeam()">Create team${SVG.arrow}</button>
    </div>
    <div class="tmfine">You'll be the owner &middot; 5 seats included &middot; add your company name later</div>
    <div class="tmor"><div></div><span>OR</span><div></div></div>
    <div class="tmjoin">${SVG.mail}
      <div class="jt"><b>Someone invited you?</b><span>Paste the link from your invite email — it only works for the address it was sent to.</span></div>
      <div class="tmfield" style="flex:none;width:300px">
        <input id="tmToken" placeholder="Invite link or code…" onkeydown="if(event.key==='Enter'){event.preventDefault();claimTeamInvite();}"/>
        <button class="tmskip" style="padding:6px 8px" onclick="declineTeamInvite()">Decline</button>
        <button onclick="claimTeamInvite()">Join</button>
      </div>
    </div>
    ${TEAM_ERR?`<div class="tmfine" style="margin-top:18px">Couldn't reach your team just now — ${esc(TEAM_ERR)}</div>`:''}
  </div></div>`;
}

function teamSetupHtml(){
  const p=TEAM_PERSONAL||{vocabulary:0,replacements:0,snippets:0,sample:[]};
  const have=(p.vocabulary||0)+(p.replacements||0)+(p.snippets||0);
  const seats=TEAM.seats||5, used=(TEAM.members||[]).length;
  let dots='';
  for(let i=0;i<seats;i++) dots+='<i class="'+(i<used?'taken':'')+'"></i>';
  const chips=(p.sample||[]).map(w=>`<span class="dchip">${esc(w)}</span>`).join('')
    + (p.vocabulary>(p.sample||[]).length ? `<span class="tmfine" style="margin:0;align-self:center">+${p.vocabulary-(p.sample||[]).length} more</span>` : '');
  return `
  <div class="tmstart"><div class="tmstartin">
    <div style="display:flex;align-items:center;gap:15px;margin-bottom:26px">
      <div class="tmav" style="width:52px;height:52px;border-radius:16px;background:#EADFCE;color:#2a1f18;font-size:21px">${esc((TEAM.name||'T')[0].toUpperCase())}</div>
      <div style="flex:1;min-width:0">
        <h2 style="font:700 22px 'Geist';letter-spacing:-.01em;margin:0 0 4px">${esc(TEAM.name)} is yours.</h2>
        <p style="font:400 13px 'Geist';color:var(--mut);margin:0">Two things make it useful. Both take a minute.</p>
      </div>
    </div>
    <div class="tmstep">
      <div class="n live">1</div>
      <div class="b">
        <h4>Share the words you've already taught Flume</h4>
        ${have
          ? `<p>Your dictionary has <b>${p.vocabulary} word${p.vocabulary===1?'':'s'}</b>, <b>${p.replacements} rule${p.replacements===1?'':'s'}</b> and <b>${p.snippets} snippet${p.snippets===1?'':'s'}</b>. Copy them into the team's and everyone starts where you are.</p>
             <div class="dictchips" style="margin:12px 0 14px">${chips}</div>
             <button class="btn primary" style="width:auto;padding:10px 16px" onclick="seedTeamDict()">Copy to the team</button>
             <div class="tmfine" style="text-align:left;margin-top:10px">Your own dictionary keeps working exactly as it does now — and still wins if the two ever disagree.</div>`
          : `<p>You haven't taught Flume any words yet. Add some in <b>Dictionary</b> and you'll be able to share them here.</p>`}
      </div>
    </div>
    <div class="tmstep">
      <div class="n">2</div>
      <div class="b">
        <h4>Bring the first person in</h4>
        <p>They get a one-time link that expires in 7 days and only works for the address you send it to.</p>
        <div class="tmfield" style="margin-top:13px">
          <input id="tmSetupEmail" placeholder="name@company.com" onkeydown="if(event.key==='Enter'){event.preventDefault();inviteMember('tmSetupEmail');}"/>
          <select id="tmSetupEmailRole"><option value="member">Member</option><option value="admin">Admin</option></select>
          <button onclick="inviteMember('tmSetupEmail')">Send</button>
        </div>
        <div class="tmseats"><div class="dots">${dots}</div>
          <span>${seats-used} of your ${seats} seats ${seats-used===1?'is':'are'} open</span></div>
      </div>
    </div>
    <div style="display:flex;justify-content:center;margin-top:22px">
      <button class="tmskip" onclick="skipTeamSetup()">Skip for now — I'll do this later</button>
    </div>
  </div></div>`;
}

function teamRosterHtml(){
  const me=teamMe();
  const seats=TEAM.seats||0, used=(TEAM.members||[]).length;
  const sharing=(TEAM.members||[]).filter(m=>m.usage_consent).length;
  const rows=(TEAM.members||[]).map(m=>{
    const u=tmUsageFor(m.user_id);
    const isMe=m.user_id===me;
    const consented=!!m.usage_consent;
    const canRemove = teamAdmin() && m.role !== 'owner';
    return `<div class="tmrow${TEAM_SEL===m.user_id?' on':''}" role="button" tabindex="0"
      onclick="selectMember(${esc(JSON.stringify(m.user_id))})">
      <div class="tmav${isMe?' me':''}">${esc(tmInit(m))}</div>
      <div class="tmbody">
        <div class="tmname"><span>${esc(m.display_name||m.email||'Member')}${isMe?' (you)':''}</span>
          <span class="tmnum">${u?fmtK(u.words):'—'}</span></div>
        ${consented ? tmSparkHtml(m.user_id) : '<div class="tmsub">Not sharing numbers</div>'}
      </div>
      ${canRemove?`<button class="tmrowx" title="Remove ${esc(m.display_name||m.email||'this member')} from the team"
        onclick="event.stopPropagation();removeMember(${esc(JSON.stringify(m.user_id))}, ${esc(JSON.stringify(m.display_name||m.email||''))})">${SVG.trash}Remove</button>`:''}
    </div>`;
  }).join('');
  const pending=(teamAdmin()?TEAM_INV:[]).map(iv=>`
    <div class="tmrow" style="cursor:default">
      <div class="tmav pend"></div>
      <div class="tmbody">
        <div class="tmname"><span style="font-family:'JetBrains Mono';font-size:11.5px;color:var(--dim)">${esc(iv.email)}</span></div>
        <div class="tmsub">Invited &middot; expires ${esc(tmWhen(iv.expires_at).replace(' ago',''))}</div>
      </div>
      <div class="tmpendacts">
        <button title="Send the invite again" onclick="resendInvite(${esc(JSON.stringify(iv.email))}, ${esc(JSON.stringify(iv.role||'member'))})">Resend</button>
        <button title="Revoke" onclick="revokeInvite(${esc(JSON.stringify(iv.id))})">${SVG.trash}</button>
      </div>
    </div>`).join('');
  return `
  <div class="tmroster">
    <div class="tmrhead">
      ${TEAM.company_name?`<div class="tmco">${esc(TEAM.company_name)}</div>`:'<div class="tmco">Team</div>'}
      <div class="tmnm">${esc(TEAM.name||'Team')}</div>
    </div>
    <div class="tmrlist">
      <button class="tmrow${TEAM_SEL==='all'?' on':''}" onclick="selectMember('all')">
        <div class="tmav all">${SVG.team}</div>
        <div class="tmbody"><div class="tmname"><span>Everyone</span></div>
          <div class="tmsub">${used} ${used===1?'person':'people'} &middot; ${sharing} sharing</div></div>
      </button>
      <div class="navhead" style="margin:16px 10px 6px">MEMBERS</div>
      ${rows}${pending}
    </div>
    ${teamAdmin()?`<div class="tmrfoot">
      <button class="btn primary" style="width:100%" onclick="tmOpenInvite()">${SVG.plus}Add teammate</button>
      <div class="tmseat">${used} of ${seats} seats used, including you${
        TEAM_INV.length?` &middot; ${TEAM_INV.length} invite${TEAM_INV.length===1?'':'s'} out`:''}</div>
    </div>`:''}
  </div>`;
}

// A ranking needs a source of truth about who is in front. Two exist and they are
// not interchangeable:
//   TEAM_USAGE  — admin-only, gated on each member's usage_consent (on by default)
//   TEAM_BOARD  — team-visible once the owner enables it; every sharing member is on it
// Admins rank from usage because it is the fuller set and already theirs to see;
// everyone else sees the opt-in board. Same rows, same order, different audience.
// EXCEPT when the owner opened stats team-wide (stats_visible_to_members,
// 2026-08-26): members then already see every consenting member's numbers in
// the roster, so a separate opt-in board that ranks a SUBSET of those same
// numbers is pure friction — live case: ranking on, stats open, and a member's
// board sat empty because nobody had found the per-person opt-in toggle. Rank
// from the usage they can already see; the opt-in gate stays for teams that
// keep stats admin-only.
function tmBoardRows(){
  if(teamAdmin() || (TEAM.stats_visible_to_members && TEAM_USAGE && TEAM_USAGE.rows)){
    return ((TEAM_USAGE&&TEAM_USAGE.rows)||[]).slice()
      .sort((a,b)=>(b.words||0)-(a.words||0));
  }
  if(!TEAM.leaderboard_enabled) return null;
  return ((TEAM_BOARD&&TEAM_BOARD.rows)||[]).slice()
    .sort((a,b)=>(b.words||0)-(a.words||0));
}
function tmAppsFor(uid){ return (TEAM_APPS&&TEAM_APPS[uid])||[]; }
function tmTopApp(uid){ const a=tmAppsFor(uid)[0]; return a?a.app:''; }

// One person's app mix, for their own page. Same data as tmAppsCard(), ranked and
// listed rather than stacked — with a single subject there is room to name every
// app and its share instead of colour-coding them.
function tmMemberAppsHtml(uid, m){
  const apps=tmAppsFor(uid);
  const who=(m && (m.display_name||m.email||'').split(' ')[0]) || 'They';
  if(!apps.length){
    return `<div class="inscard">
      <div class="chd"><span>Where ${esc(who)} writes</span></div>
      <p class="ssub" style="margin:0">No app data yet. Flume started recording which app a dictation
      went into on <b style="color:var(--tx)">21 Aug 2026</b>; this fills in from their next dictation
      on that version or newer. Dictations from the phone never carry an app &mdash; there is no
      frontmost window to read on iOS.</p></div>`;
  }
  const tot=apps.reduce((a,b)=>a+(b.dictations||0),0)||1;
  const rows=apps.slice(0,8).map((a,i)=>`<div class="insabar">
      <div class="arow"><span class="an">${esc(a.app)}</span>
        <span class="av">${Math.round(a.dictations/tot*100)}% &middot; ${fmtN(a.dictations)}</span></div>
      <div class="atr"><i style="width:${Math.max(1,Math.round(a.dictations/tot*100))}%;background:${
        i===0?'#C85A3E':'rgba(240,240,240,.18)'}"></i></div>
    </div>`).join('');
  return `<div class="inscard">
    <div class="chd"><span>Where ${esc(who)} writes</span>
      <span class="tmfine" style="margin:0;text-transform:none;letter-spacing:.02em">last ${TEAM_DAYS} days</span></div>
    ${rows}
    ${apps.length>8?`<div class="tmfine" style="text-align:left;margin-top:10px">+${apps.length-8} more app${apps.length-8===1?'':'s'}</div>`:''}
  </div>`;
}

function tmLeaderboardCard(){
  const rows=tmBoardRows();
  const me=teamMe();
  const enable = teamOwner() && !TEAM.leaderboard_enabled
    ? `<div class="saverow" style="margin-top:14px"><button class="toggle" onclick="toggleTeamBoard()"></button>
        <span style="font:500 13px Geist">Show this ranking to the whole team</span></div>`
    : (teamOwner() ? `<div class="saverow" style="margin-top:14px"><button class="toggle on" onclick="toggleTeamBoard()"></button>
        <span style="font:500 13px Geist">Visible to the whole team</span></div>` : '');

  if(rows===null){
    return `<div class="inscard"><div class="chd"><span>Ranking</span></div>
      <p class="ssub" style="margin:0">Your team owner hasn&rsquo;t turned the ranking on, so there is nobody
      to compare against. Your own numbers are above, and everything you have ever dictated is on your
      <button class="tmskip" style="padding:0;color:var(--acc)" onclick="show('insights')">Insights</button> page.</p></div>`;
  }
  if(!rows.length){
    return `<div class="inscard"><div class="chd"><span>Ranking</span></div>
      <p class="ssub" style="margin:0">Nobody has dictated in the last ${TEAM_DAYS} days${teamAdmin()?' — or nobody is sharing their counts yet':''}.</p>
      ${enable}</div>`;
  }
  const bmax=Math.max(1,...rows.map(r=>r.words||0));
  const body=rows.map((r,i)=>{
    const uid=r.user_id||'';
    const wpm=tmWpm(r);
    const app=tmTopApp(uid);
    const m=(TEAM.members||[]).find(x=>x.user_id===uid);
    const name=r.display_name||(m&&(m.display_name||m.email))||'Member';
    const sub=[ (r.dictations||0)+' dictation'+((r.dictations||0)===1?'':'s'),
                wpm?wpm+' wpm':'', app?'mostly '+app:'' ].filter(Boolean).join('  ·  ');
    return `<div class="tmbrow${i===0?' p1':''}${uid===me?' me':''}"${uid?` onclick="selectMember('${uid}')"`:''}>
      <i class="fill" style="width:${Math.max(3,Math.round((r.words||0)/bmax*100))}%"></i>
      <div class="tmbrank">${i+1}</div>
      <div class="tmav${uid===me?' me':''}">${esc((name.trim()[0]||'?').toUpperCase())}</div>
      <div class="tmbwho"><b>${esc(name)}${uid===me?' <span style="font-weight:400;color:var(--dim)">(you)</span>':''}</b>
        <span>${esc(sub)}</span></div>
      <div class="tmbnum">${fmtN(r.words||0)}<em>words</em></div>
    </div>`;
  }).join('');
  const gap = (TEAM.members||[]).length - rows.length;
  return `<div class="inscard">
    <div class="chd"><span>Ranking &middot; last ${TEAM_DAYS} days</span>
      <span class="tmfine" style="margin:0;text-transform:none;letter-spacing:.02em">by words dictated</span></div>
    <div class="tmboard">${body}</div>
    ${gap>0?`<div class="tmfine" style="text-align:left;margin-top:12px">${gap} member${gap===1?' is':'s are'} not ${teamAdmin()?'sharing their counts':'on the ranking'}.</div>`:''}
    ${enable}</div>`;
}

// Which app each person actually dictates into. The `app` column shipped on
// 2026-08-21 and older rows are NULL forever, so an empty panel here usually
// means "not enough new dictations yet", not "nobody uses anything" — say that
// rather than rendering a convincing zero.
function tmAppsCard(){
  const cols=['#C85A3E','#EADFCE','#A8BCA1','#C3AECB','#8a7d74','#4a2d24'];
  // A member's TEAM_APPS holds exactly their own row, so the same card works for
  // both audiences — it just has one bar in it, and says "you" instead of a name.
  const solo=!teamAdmin() && !TEAM.stats_visible_to_members;
  const mem=(TEAM.members||[])
    .filter(m=>!solo || m.user_id===teamMe())
    .filter(m=>tmAppsFor(m.user_id).length);
  if(!mem.length){
    return `<div class="inscard"><div class="chd"><span>${solo?'Where you write':'Where the team writes'}</span></div>
      <p class="ssub" style="margin:0">Nothing here yet. Flume only started recording which app a dictation went into
      on <b style="color:var(--tx)">21 Aug 2026</b>, and only on a build from that day or newer — this fills in as
      ${solo?'you dictate':'the team dictates'}. Nothing from before then can be recovered, and dictations from
      the phone never carry an app.</p></div>`;
  }
  const body=mem.map(m=>{
    const apps=tmAppsFor(m.user_id);
    const tot=apps.reduce((a,b)=>a+(b.dictations||0),0)||1;
    const top=apps.slice(0,5);
    const rest=apps.slice(5).reduce((a,b)=>a+(b.dictations||0),0);
    const segs=top.map((a,i)=>`<i style="width:${(a.dictations/tot*100).toFixed(1)}%;background:${cols[i]}"></i>`).join('')
      + (rest?`<i style="width:${(rest/tot*100).toFixed(1)}%;background:rgba(240,240,240,.14)"></i>`:'');
    const lg=top.map((a,i)=>`<em><i style="background:${cols[i]}"></i><b>${esc(a.app)}</b> ${Math.round(a.dictations/tot*100)}%</em>`).join('')
      + (rest?`<em><i style="background:rgba(240,240,240,.14)"></i>other ${Math.round(rest/tot*100)}%</em>`:'');
    return `<div class="tmapprow">
      <div class="tmapphd"><b>${solo?'You':esc(m.display_name||m.email||'Member')}</b>
        <span>${esc(apps[0].app)} &middot; ${fmtN(tot)} dictation${tot===1?'':'s'}</span></div>
      <div class="tmappbar">${segs}</div>
      <div class="tmapplg">${lg}</div>
    </div>`;
  }).join('');
  const missing=solo ? 0 : (TEAM.members||[]).length-mem.length;
  return `<div class="inscard">
    <div class="chd"><span>${solo?'Where you write':'Where the team writes'}</span>
      <span class="tmfine" style="margin:0;text-transform:none;letter-spacing:.02em">share of dictations, last ${TEAM_DAYS} days</span></div>
    <div class="tmapps">${body}</div>
    ${missing>0?`<div class="tmfine" style="text-align:left;margin-top:14px">No app data for ${missing} member${missing===1?'':'s'} yet — they need a build from 21 Aug 2026 or later.</div>`:''}
  </div>`;
}

// One jump, so the pointer on Team lands on the shared set and not on the user's
// own words — arriving at the wrong scope makes the move look like a dead end.
function openTeamDictionary(){ DICT_SCOPE='team'; show('dictionary'); }
// Same idea for consent: land on the pane that owns it, not on Settings' first
// group, or the pointer is a dead end.
function showTeamPrivacy(){ SETTINGS_GROUP='privacy'; show('settings'); }

function teamEveryoneHtml(){
  const rows=((TEAM_USAGE&&TEAM_USAGE.rows)||[]).slice().sort((a,b)=>(b.words||0)-(a.words||0));
  const total=rows.reduce((a,b)=>a+(b.words||0),0);
  const cols=['#C85A3E','#a84b33','#7a4030','#4a2d24'];
  const parts=rows.map((r,i)=>({name:r.display_name||r.email||'Member', pct: total?((r.words||0)/total*100):0, col:cols[i]||cols[3]}));
  const notSharing=(TEAM.members||[]).length - rows.length;
  const ms=rows.reduce((a,b)=>a+(b.speech_ms||0),0);
  const savedMin=Math.round(total/40) - Math.round(ms/60000);   // vs 40wpm typing
  const top=parts[0];
  // A plain member's `rows` contains exactly ONE row — their own (the RPCs do that
  // split, not this code). Presenting that as "the team spoke N words" would be a
  // straight-up lie, and a contribution ring with one segment always reads 100%.
  // So the whole hero switches voice for a member.
  const mine=!teamAdmin() && !TEAM.stats_visible_to_members;
  const heroTx = mine
    ? (total
        ? `You spoke <b>${fmtN(total)} words</b> on ${esc(TEAM.name||'this team')} in the last ${TEAM_DAYS} days.`
        : `You haven't dictated in the last ${TEAM_DAYS} days. Your own numbers show up here; the team's totals stay with the admins.`)
    : (total
        ? `${esc(TEAM.name)} spoke <b>${fmtN(total)} words</b> in the last ${TEAM_DAYS} days`
          + (rows.length>1&&top ? ` — <b>${esc(top.name.split(' ')[0])}</b> carried <b>${Math.round(top.pct)}%</b> of them.` : '.')
        : (TEAM_USAGE
            ? 'Nobody on the team has dictated in this window yet.'
            : 'No shared numbers yet — usage appears here as people turn sharing on.'));
  const dictN=(TEAM.dictionary&&TEAM.dictionary.vocabulary||[]).length;
  const repN=(TEAM.dictionary&&TEAM.dictionary.replacements||[]).length;
  const snipN=(TEAM.dictionary&&TEAM.dictionary.snippets||[]).length;
  const dicts=rows.reduce((a,b)=>a+(b.dictations||0),0);
  const pace=ms>=120000 ? Math.round(total/(ms/60000)) : null;
  return `
  <div class="tmdetail">
    <div class="mhead"><div><div class="eyebrow">Team</div><h1 class="title">${mine ? `You on ${esc(TEAM.name||'the team')}` : `How ${esc(TEAM.name||'the team')} flows`}</h1></div>
      <span class="insseg" style="float:none">
        <button class="${TEAM_DAYS===7?'on':''}" onclick="teamDays(7)">7 days</button>
        <button class="${TEAM_DAYS===30?'on':''}" onclick="teamDays(30)">30 days</button>
        <button class="${TEAM_DAYS===90?'on':''}" onclick="teamDays(90)">90 days</button></span></div>

    <div class="tmring">
      ${mine ? '' : tmRingSvg(parts, total)}
      <div class="tmringtx">
        ${savedMin>0?`<div class="tmbadge">&asymp; ${fmtMin(savedMin)} of typing saved</div>`:''}
        <div class="tmlead">${heroTx}</div>
        ${mine ? `<div class="tmfine" style="text-align:left;margin-top:12px">
            Only your own numbers appear on this page. Your admins see the team&rsquo;s totals; you can
            switch even your own off under <button class="tmskip" style="padding:0;color:var(--acc)"
            onclick="showTeamPrivacy()">Settings &rarr; Team privacy</button>.</div>`
          : `<div class="tmlegend">
          ${parts.map(p=>`<div><i style="background:${p.col}"></i>${esc(p.name)}<em>${Math.round(p.pct)}%</em></div>`).join('')}
          ${notSharing>0?`<div><i style="background:rgba(240,240,240,.12)"></i>Not sharing<em>${notSharing}</em></div>`:''}
        </div>`}
      </div>
    </div>

    <div class="insband">
      <div class="itile cream"><div class="tk">${mine?'Your words':'Words spoken'}</div>
        <div class="tv">${fmtN(total)}</div>
        <div class="ts">last ${TEAM_DAYS} days${mine?'':` &middot; ${rows.length} of ${(TEAM.members||[]).length} sharing`}</div></div>
      <div class="itile sage"><div class="tk">Dictations</div>
        <div class="tv">${fmtN(dicts)}</div>
        <div class="ts">${dicts?`${Math.round(total/Math.max(1,dicts))} words each`:'nothing yet'}</div></div>
      <div class="itile"><div class="tk">${mine?'Your pace':'Team pace'}</div>
        <div class="tv">${pace?pace:'&mdash;'}<em style="font-size:14px;font-style:normal;color:var(--dim)">${pace?' wpm':''}</em></div>
        <div class="ts">${pace?`${fmtMin(Math.round(ms/60000))} of speech`:'needs 2 min of audio'}</div></div>
      <div class="itile plum"><div class="tk">Seats</div>
        <div class="tv">${(TEAM.members||[]).length} / ${TEAM.seats||0}</div>
        <div class="ts">${esc(TEAM.plan||'team')} plan${TEAM_INV.length?` &middot; ${TEAM_INV.length} invited`:''}${
          TEAM_INV.length && ((TEAM.members||[]).length + TEAM_INV.length > (TEAM.seats||0))
            ? ' &middot; over seats' : ''}</div></div>
    </div>

    ${tmLeaderboardCard()}
    ${tmAppsCard()}

    <div class="inscard">
      <div class="chd"><span>Shared dictionary</span>
        <button class="tmskip" style="padding:0;color:var(--acc);text-transform:none;letter-spacing:.02em" onclick="openTeamDictionary()">Open in Dictionary &rarr;</button></div>
      <p class="ssub" style="margin:0">${dictN+repN+snipN
        ? `<b style="color:var(--tx)">${dictN} word${dictN===1?'':'s'}</b>, ${repN} rule${repN===1?'':'s'} and ${snipN} snippet${snipN===1?'':'s'} apply to everyone on ${esc(TEAM.name||'the team')}.`
        : `Nothing shared yet. Names, jargon and product words the whole team should get right belong here.`}
        It lives with your own words under <b style="color:var(--tx)">Dictionary</b> &rarr; ${esc(TEAM.name||'Team')}.</p>
    </div>

    <div class="inscard">
      <div class="chd"><span>Your privacy</span>
        <button class="tmskip" style="padding:0;color:var(--acc);text-transform:none;letter-spacing:.02em"
          onclick="showTeamPrivacy()">Open in Settings &rarr;</button></div>
      <p class="ssub" style="margin:0">You are ${TEAM.usage_consent
        ? `<b style="color:var(--tx)">sharing your dictation counts</b> with admins${TEAM.leaderboard_enabled?' and appear on the team ranking':''}.`
        : `<b style="color:var(--tx)">not sharing anything</b> — your numbers appear in no admin view.`}
        What you dictate is never shared either way. Change it under
        <b style="color:var(--tx)">Settings</b> &rarr; Team privacy.</p>
    </div>

    ${teamOwner()?`<div class="inscard">
      <div class="chd"><span>Joining by domain</span></div>
      ${TEAM.is_generic_domain
        ? `<div class="ssub" style="margin:0">${esc(TEAM.name)} was created on a personal email domain, so anyone could claim it. Domain joining is only offered on a company domain — invites are the way in.</div>`
        : `<p class="ssub" style="margin-bottom:12px">Anyone signing up with an <b style="color:var(--tx)">@${esc(TEAM.domain||'')}</b> address can ask to join instead of waiting for an invite. Requests still need your approval.</p>
           <div class="saverow"><button class="toggle ${TEAM.auto_join_enabled?'on':''}" onclick="setTeamAutoJoin(${TEAM.auto_join_enabled?'false':'true'})"></button>
             <span style="font:500 13px Geist">Let @${esc(TEAM.domain||'')} colleagues find this team</span></div>`}
      <div class="tmnote" style="margin-top:14px">${SVG.lock}
        <span>This is the opposite of a restriction — it lets people in <b style="color:var(--tx2)">without</b> an invite. Invites already work for any address, including personal ones, which is how you would add a contractor.</span></div>
    </div>`:''}
    ${TEAM_ERR?`<div class="tmfine" style="text-align:left;margin-top:14px">Last sync problem: ${esc(TEAM_ERR)}</div>`:''}
  </div>`;
}

function teamMemberHtml(uid){
  const m=(TEAM.members||[]).find(x=>x.user_id===uid);
  if(!m){ TEAM_SEL='all'; return teamEveryoneHtml(); }
  const isMe=uid===teamMe();
  const u=tmUsageFor(uid);
  const wpm=tmWpm(u);
  const consented=!!m.usage_consent;
  const isOwner=m.role==='owner';
  const allWpm=((TEAM_USAGE&&TEAM_USAGE.rows)||[]).map(tmWpm).filter(Boolean);
  const best=allWpm.length?Math.max(...allWpm):null;
  const bestRow=best?((TEAM_USAGE.rows||[]).find(r=>tmWpm(r)===best)):null;
  const ctl = (teamAdmin() && !isOwner)
    ? `<select class="tmsel" onchange="setMemberRole(${esc(JSON.stringify(uid))}, this.value)">
         <option value="member"${m.role==='member'?' selected':''}>Member</option>
         <option value="admin"${m.role==='admin'?' selected':''}>Admin</option></select>
       <button class="tmghost" onclick="removeMember(${esc(JSON.stringify(uid))}, ${esc(JSON.stringify(m.display_name||m.email||''))})">Remove from team</button>`
    : `<span class="tmrole ${esc(m.role)}" style="font:500 10px 'JetBrains Mono';letter-spacing:.14em;padding:6px 10px;border-radius:6px;background:var(--raised);color:var(--mut)">${esc(m.role).toUpperCase()}</span>`;
  if(!consented){
    return `
    <div class="tmdetail">
      <div class="tmdhead">
        <div class="tmav${isMe?' me':''}">${esc(tmInit(m))}</div>
        <div style="flex:1;min-width:0"><div class="tmdname">${esc(m.display_name||m.email||'Member')}${isMe?' (you)':''}</div>
          <div class="tmdmeta">${esc(m.email||'')}${m.joined_at?` &middot; joined ${esc(tmWhen(m.joined_at))}`:''}</div></div>
        ${ctl}
      </div>
      <div class="inscard insempty" style="padding:60px 20px">
        <div class="bigmic">${SVG.lock}</div>
        <h2>${isMe?'You haven&rsquo;t turned sharing on':'Nothing to show here'}</h2>
        <p>${isMe
          ? 'Your dictation counts stay private until you switch sharing on. Nothing you dictate is ever shared either way.'
          : esc((m.display_name||'They').split(' ')[0])+' hasn&rsquo;t turned usage sharing on. Only they can change that — an admin can&rsquo;t do it for them.'}</p>
        ${isMe?`<button class="btn primary" style="width:auto;padding:11px 18px;margin-top:18px" onclick="setTeamConsent(true, true)">Share my counts</button>`:''}
      </div>
    </div>`;
  }
  return `
  <div class="tmdetail">
    <div class="tmdhead">
      <div class="tmav${isMe?' me':''}">${esc(tmInit(m))}</div>
      <div style="flex:1;min-width:0"><div class="tmdname">${esc(m.display_name||m.email||'Member')}${isMe?' (you)':''}</div>
        <div class="tmdmeta">${esc(m.email||'')}${m.joined_at?` &middot; joined ${esc(tmWhen(m.joined_at))}`:''}</div></div>
      ${ctl}
    </div>

    ${wpm ? `
    <div class="inshero">
      ${tmGaugeSvg(wpm)}
      <div class="hnum">${wpm}</div>
      <div class="hunit">WORDS PER MINUTE</div>
      <div class="hbadge">${(wpm/52).toFixed(1)}&times; the average typist</div>
      <div class="hsub">${bestRow && tmWpm(bestRow)>wpm
            ? `Fastest on the team is <b>${esc((bestRow.display_name||'a teammate').split(' ')[0])}</b> at <b>${best}</b>.`
            : 'Fastest on the team.'}</div>
    </div>` : `
    <!-- A blank gauge is the largest element on the page and reads as "broken" or
         "still loading" — which is exactly how a brand-new member's page looked.
         So when there is not enough measured audio to state a speed honestly, the
         hero says what IS true instead of showing a dash. -->
    <div class="inscard insempty" style="padding:34px 20px">
      <div class="bigmic">${SVG.mic}</div>
      <h2>${(u&&u.dictations) ? 'Just getting started' : `${esc((m.display_name||'They').split(' ')[0])} hasn't dictated yet`}</h2>
      <p>${(u&&u.dictations)
        ? `${fmtN(u.dictations)} dictation${u.dictations===1?'':'s'} so far &mdash; ${fmtN(u.words)} words. Speaking speed needs a couple of minutes of recorded audio before it means anything, so it appears here once there is enough.`
        : 'Numbers appear here from their first dictation. Nothing is missing &mdash; there is just nothing to show yet.'}</p>
    </div>`}

    <div class="insband">
      <div class="itile cream"><div class="tk">Words dictated</div>
        <div class="tv">${fmtN(u?u.words:0)}</div>
        <div class="ts">${fmtN(u?u.dictations:0)} dictation${(u&&u.dictations===1)?'':'s'}${u&&u.dictations?` &middot; avg ${Math.round(u.words/u.dictations)} words`:''}</div></div>
      <div class="itile sage"><div class="tk">Time speaking</div>
        <div class="tv">${tmMins(u?u.speech_ms:0)}</div>
        <div class="ts">last ${TEAM_DAYS} days</div></div>
      <div class="itile plum"><div class="tk">Last active</div>
        <div class="tv" style="font-size:20px">${esc(tmWhen(u?u.last_active:null))}</div>
        <div class="ts">on this team</div></div>
    </div>

    ${tmHeatHtml(uid)}
    ${tmMemberAppsHtml(uid, m)}

    <div class="tmnote">${SVG.lock}
      <span>${isMe
        ? 'These are your own numbers. Your admins see the same counts, durations and app names — never a word of what you dictated, and never your audio.'
        : esc((m.display_name||'They').split(' ')[0])+' chose to share these and can switch them off at any time. You are seeing counts, durations and the names of the apps they dictate into — never a word of what they dictated, and never their audio.'}</span></div>
  </div>`;
}

function renderTeam(){
  const box=document.getElementById('teamMain');
  if(!box) return;
  const solo = !hasTeam() || !TEAM_SETUP;
  box.classList.toggle('solo', solo);
  if(!hasTeam()){ box.innerHTML=teamStartHtml(); return; }
  if(!TEAM_SETUP){ box.innerHTML=teamSetupHtml(); return; }
  box.innerHTML = teamRosterHtml() + (TEAM_SEL==='all' ? teamEveryoneHtml() : teamMemberHtml(TEAM_SEL));
  tmSizeHeat();
}

function navTo(id){
  if(id==='meetings'){ mntAbandon(); MVIEW='list'; MROW=null; MSUBNOTES=false; MSPK=null; MEET_ASK_SCOPE=null; MEET_ASK=null; }
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
                    f";const IS_WINDOWS={('true' if _is_win else 'false')};"
                    # Device wording for the shared page: onboarding "This Mac", the
                    # canvas "from this Mac", the default device name… all read as a
                    # Mac on Windows ("no matter who logs in it shows this Mac", 2026-08-28).
                    "const THIS_DEVICE=IS_WINDOWS?'This PC':'This Mac';"
                    "const DEVICE_NOUN=IS_WINDOWS?'PC':'Mac';</script>")

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

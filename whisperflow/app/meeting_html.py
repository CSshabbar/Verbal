r"""
Meetings — HTML/CSS/JS for the meeting WKWebView window (MEETINGS_DESIGN_HANDOFF.md).

Rendered by meeting_window.MeetingWindow into a WKWebView; data + actions go
through the same window.pywebview.api.* (DashboardApi) bridge the dashboard
uses. Python → JS events arrive via window.VerbalMeeting(event, payload) — a
dedicated namespace so meeting events never collide with VerbalNative /
VerbalOverlay / VerbalAutolearn.

One page, three modes (swapped by JS, state preserved):
  'permissions' — PermissionChecklistModal (31h)
  'live'        — InMeetingTwoPanel (31c)          [Phase 2+]
  'summary'     — PostMeetingSummary (31e)         [Phase 5]

Token gaps from the handoff are resolved here as CSS variables, sourced from
theme.py where a token exists and from the handoff's inline annotations
otherwise (record red #E05049 approved distinct from terracotta).

JS escaping convention for THIS file: the JS lives in a raw string (r-triple-
quote) and uses SINGLE backslashes (write \s, not \\s), same as
flume_dashboard_html.py. Do not mix conventions (05-conventions.md Rule #2).

Fonts must go through fonts_css.web_font_css() — WKWebView cannot resolve the
CoreText-registered faces by name (05-conventions.md Rule #7).
"""
from app.fonts_css import web_font_css

# Line-icon SVGs (stroke 1.4 — widget kit v2 canonical stroke).
_IC = {
    "mic":    '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M19 11v1a7 7 0 0 1-14 0v-1"/><path d="M12 19v3"/>',
    "wave":   '<path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 10v4"/>',
    "star":   '<path d="m12 3 2.7 5.6 6.3.9-4.5 4.3 1 6.2-5.5-3-5.5 3 1-6.2L3 9.5l6.3-.9z"/>',
    "pause":  '<path d="M9 5v14M15 5v14"/>',
    "stop":   '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
    "gear":   '<circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "check":  '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "back":   '<path d="m14 6-6 6 6 6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "edit":   '<path d="M17 3 21 7l-13 13H4v-4z"/><path d="m14 6 4 4"/>',
    "share":  '<path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7"/><path d="M12 3v12"/><path d="m8 7 4-4 4 4"/>',
    "refresh":'<path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/>',
    "extlink":'<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h6"/>',
    "collapse":'<path d="M9 4v5H4"/><path d="m9 9-6-6"/><path d="M15 20v-5h5"/><path d="m15 15 6 6"/>',
    "trash":  '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/><path d="M10 11v6M14 11v6"/>',
    "expand":  '<path d="M15 4h5v5"/><path d="m20 4-6 6"/><path d="M9 20H4v-5"/><path d="m4 20 6-6"/>',
}


def _svg(key, size=14):
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
            f'stroke="currentColor" stroke-width="1.4" stroke-linecap="round" '
            f'stroke-linejoin="round">{_IC[key]}</svg>')


# ── Tokens (handoff gaps resolved; theme.py values where they exist) ────────────
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  /* surfaces */
  --bg:#0e1012; --chrome:#0a0c0e; --card:#17191c;
  --card-grad:linear-gradient(160deg,#17191c,#1c1e22);
  --subtle:#0c0e10; --subtle-alt:rgba(255,255,255,.03);
  --modal:#17191c; --footer:rgba(255,255,255,.02);
  --raised:rgba(240,240,240,.06); --raised2:rgba(240,240,240,.09);
  --hud:rgba(14,16,18,.9);
  /* text */
  --tx:#f2f2f2; --tx2:rgba(240,240,240,.65); --mut:rgba(240,240,240,.55);
  --dim:rgba(240,240,240,.45); --faint:rgba(240,240,240,.35);
  /* accent (terracotta) */
  --acc:#C85A3E; --acc-on:#fff5ea; --acc-hover:#d2664a; --acc-press:#b44f36;
  --acc-soft:rgba(200,90,62,.14); --acc-softer:rgba(200,90,62,.06);
  --acc-bd:rgba(200,90,62,.35); --acc-txt:#f0b39a;
  /* record red (≠ terracotta — approved #E05049) + danger */
  --rec:#E05049; --rec-subtle:rgba(224,80,73,.14); --rec-bd:rgba(224,80,73,.38);
  --rec-soft:#f0a5a0;
  /* status */
  --ok:#4ad15a; --ok-subtle:rgba(74,209,90,.10); --ok-bd:rgba(74,209,90,.32); --ok-soft:#8ee69a;
  --warn:#d1a04a; --warn-subtle:rgba(209,160,74,.12); --warn-soft:#e6c890;
  /* lines */
  --bd:rgba(240,240,240,.06); --bd2:rgba(240,240,240,.1); --bd-faint:rgba(240,240,240,.04);
  --scrim:rgba(0,0,0,.55);
  /* speaker palette (widget kit v2 — dot colors, never chip fills) */
  --sp-terra:#D98A72; --sp-slate:#8FA7C2; --sp-sage:#A9BD98; --sp-ochre:#D9B36B;
}
html,body{height:100%}
body{background:transparent;font-family:'Geist',-apple-system,system-ui,sans-serif;color:var(--tx);
  -webkit-font-smoothing:antialiased;overflow:hidden;font-size:12px}
/* layout morph: the native panel animates its frame; the page cross-fades between
   the bar pill and the full window content */
body.lay-expanded{background:var(--bg)}
body.lay-bar{background:transparent}
body.lay-bar #permWrap,body.lay-bar #preWrap,body.lay-bar #liveRoot,body.lay-bar #summaryRoot,body.lay-bar #notesRoot{display:none !important}
/* native traffic lights overlay the top-left in expanded mode (hidden titlebar) */
body.lay-expanded .mhead{padding-left:86px}
body.lay-expanded .sumHead{padding-left:86px}
body.lay-expanded .ntHead{padding-left:86px}
/* ── the ambient meeting bar ── */
#barRoot{display:none;position:fixed;inset:0;padding:5px 6px}
body.lay-bar #barRoot{display:flex}
@keyframes barIn{from{opacity:0;transform:translateY(-8px) scale(.97)}to{opacity:1;transform:none}}
.barPill{flex:1;display:flex;align-items:center;gap:10px;padding:0 8px 0 14px;border-radius:999px;
  background:rgba(13,15,17,.86);-webkit-backdrop-filter:blur(20px) saturate(1.3);
  backdrop-filter:blur(20px) saturate(1.3);
  border:1px solid rgba(240,240,240,.1);cursor:pointer;
  box-shadow:0 12px 36px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.05)}
.barPill:hover{border-color:rgba(240,240,240,.16)}
.barDot{width:8px;height:8px;border-radius:50%;background:var(--rec);flex:none;
  animation:mpulse 1.4s ease-in-out infinite;box-shadow:0 0 10px rgba(224,80,73,.8)}
.barPill.paused .barDot{background:var(--faint);animation:none;box-shadow:none}
.barTitle{font:600 12px 'Geist';color:var(--tx);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:150px;flex:none}
.barTimer{font:500 12.5px 'JetBrains Mono';color:var(--tx);font-variant-numeric:tabular-nums;
  letter-spacing:-.02em;flex:none}
.barWave{display:flex;align-items:center;gap:3px;height:16px;flex:1;justify-content:center;min-width:40px}
.barWave i{width:1.5px;border-radius:2px;background:var(--tx);height:3px;opacity:.9;
  transition:height .4s cubic-bezier(.4,0,.2,1)}
.barPill.paused .barWave i{background:var(--faint);height:3px !important}
.barPausedTag{display:none;font:600 9px 'JetBrains Mono';letter-spacing:.14em;color:var(--mut);flex:none}
.barPill.paused .barPausedTag{display:inline}
.barBtn{width:28px;height:28px;border-radius:999px;background:none;color:var(--mut);
  display:inline-flex;align-items:center;justify-content:center;flex:none;
  border:0;transition:color .14s ease}
.barBtn:hover{color:var(--tx)}
.barBtn.accent{background:none;color:var(--tx2)}
.barBtn.accent:hover{color:var(--acc)}
.barBtn.stop{background:var(--rec);color:#fff;box-shadow:0 2px 10px rgba(224,80,73,.4)}
.barBtn.stop:hover{background:#e8635c}
.barPill{overflow:hidden}
button{font-family:inherit;border:0;background:none;color:inherit;cursor:pointer}
input,textarea{font-family:inherit;color:inherit;background:none;border:0;outline:none}
.mono{font-family:'JetBrains Mono',monospace}
/* eyebrow */
.eyebrow{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
.eyebrow.accd{color:var(--acc)}
/* buttons */
.btnP{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:10px;
  background:var(--acc);color:var(--acc-on);font:600 12px 'Geist'}
.btnP:hover{background:var(--acc-hover)} .btnP:active{background:var(--acc-press)}
.btnP[disabled]{opacity:.4;cursor:default}
.btnS{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;border-radius:10px;
  background:transparent;border:1px solid var(--bd2);color:var(--tx);font:600 12px 'Geist'}
.btnS:hover{background:var(--raised)}
/* permission badge */
.pbadge{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:999px;
  font:500 10px 'JetBrains Mono';letter-spacing:.1em;text-transform:uppercase}
.pbadge i{width:5px;height:5px;border-radius:50%;flex:none}
.pbadge.ready{background:var(--ok-subtle);color:var(--ok-soft)} .pbadge.ready i{background:var(--ok)}
.pbadge.pending{background:var(--warn-subtle);color:var(--warn-soft)} .pbadge.pending i{background:var(--warn)}
.pbadge.denied{background:var(--rec-subtle);color:var(--rec-soft)} .pbadge.denied i{background:var(--rec)}
.pbadge.offline{background:var(--raised);color:var(--tx2)} .pbadge.offline i{background:var(--faint)}
/* ── PermissionChecklistModal (31h) ── */
#permWrap{position:fixed;inset:0;background:var(--scrim);display:flex;align-items:center;
  justify-content:center;z-index:40}
#permWrap[hidden]{display:none}
.permPanel{width:500px;max-width:92vw;background:var(--modal);border:1px solid var(--bd);
  border-radius:14px;box-shadow:0 24px 64px rgba(0,0,0,.5);overflow:hidden}
.permHead{padding:18px 18px 8px}
.permHeadRow{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.permTile{width:36px;height:36px;border-radius:10px;background:var(--acc-soft);color:var(--acc);
  display:flex;align-items:center;justify-content:center;flex:none}
.permTitle{font:600 15px 'Geist';color:var(--tx)}
.permSub{font:400 11px 'Geist';color:var(--dim);margin-top:2px}
.permInfo{font:400 11px/1.55 'Geist';color:var(--tx2);padding:8px 12px;border-radius:10px;
  background:var(--subtle-alt);border:1px solid var(--bd-faint)}
.permSteps{padding:8px 18px 12px;display:flex;flex-direction:column;gap:8px}
.step{display:flex;align-items:flex-start;gap:8px;padding:8px 12px;border-radius:10px}
.step .disc{width:20px;height:20px;border-radius:50%;flex:none;display:flex;align-items:center;
  justify-content:center;font:500 10.5px 'JetBrains Mono'}
.step .stx{flex:1;min-width:0}
.step .slabel{font:500 12px 'Geist';color:var(--tx)}
.step .ssub{font:400 11px 'Geist';color:var(--dim);margin-top:1px}
.step .sact{display:flex;gap:6px;margin-top:8px}
.step.done{background:var(--ok-subtle);border:1px solid var(--ok-bd)}
.step.done .disc{background:var(--ok);color:#0a1f0d}
.step.done .ssub{color:var(--tx2)}
.step.active{background:var(--acc-soft);border:1px solid var(--acc-bd)}
.step.active .disc{background:rgba(200,90,62,.28);color:var(--acc)}
.step.pending{background:var(--raised);border:1px solid var(--bd)}
.step.pending .disc{border:1.6px solid var(--faint);color:var(--faint)}
.step.pending .slabel{color:var(--tx2)} .step.pending .ssub{color:var(--faint)}
.step.denied{background:var(--rec-subtle);border:1px solid var(--rec-bd)}
.step.denied .disc{background:var(--rec);color:#fff}
.permFoot{display:flex;align-items:center;gap:8px;padding:10px 18px;border-top:1px solid var(--bd);
  background:var(--footer)}
.permFoot .hint{font:400 11px 'Geist';color:var(--faint);flex:1}
.permFoot .hint a{color:var(--acc);cursor:pointer;text-decoration:none}
.permErr{display:none;margin:0 18px 8px;padding:8px 12px;border-radius:10px;background:var(--rec-subtle);
  border:1px solid var(--rec-bd);color:var(--rec-soft);font:400 11px 'Geist'}
.permErr.show{display:block}
.permMeter{display:none;margin:0 18px 8px;height:6px;border-radius:999px;background:var(--raised);overflow:hidden}
.permMeter.show{display:block}
.permMeter i{display:block;height:100%;width:0%;background:var(--ok);border-radius:999px;transition:width .12s linear}
/* ── PreMeetingModal (31b) ── */
#preWrap{position:fixed;inset:0;background:var(--scrim);display:none;align-items:center;
  justify-content:center;z-index:35}
#preWrap.show{display:flex}
.prePanel{width:460px;max-width:92vw;background:var(--modal);border:1px solid var(--bd);
  border-radius:14px;box-shadow:0 24px 64px rgba(0,0,0,.5);overflow:hidden}
.preHead{padding:14px 20px 8px}
.preTitle{width:100%;font:600 15px 'Geist';color:var(--tx);margin-top:6px}
.preTitle::placeholder{color:var(--faint)}
.preCap{font:400 11px 'Geist';color:var(--faint);margin-top:3px}
.preGroup{padding:6px 20px 10px;display:flex;flex-direction:column;gap:6px}
.srcRow{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;
  background:var(--raised);border:1px solid var(--bd)}
.srcRow .disc{width:26px;height:26px;border-radius:8px;background:var(--ok-subtle);
  color:var(--ok);display:flex;align-items:center;justify-content:center;flex:none}
.srcRow .disc.off{background:var(--raised2);color:var(--dim)}
.srcRow .stx{flex:1;min-width:0}
.srcRow .sl{font:600 12px 'Geist';color:var(--tx)}
.srcRow .ss{font:400 11px 'Geist';color:var(--dim)}
.toggle{width:30px;height:17px;border-radius:999px;background:var(--raised2);position:relative;
  cursor:pointer;flex:none;transition:background .25s ease;border:0;padding:0}
.toggle::after{content:'';position:absolute;top:2px;left:2px;width:13px;height:13px;
  border-radius:50%;background:var(--tx);transition:left .25s ease}
.toggle.on{background:var(--acc)}
.toggle.on::after{left:15px}
.preLang{background:var(--raised2);color:var(--tx);border:1px solid var(--bd2);border-radius:8px;
  font:500 11.5px 'Geist';padding:5px 8px;max-width:170px}
.preFoot{display:flex;align-items:center;gap:8px;padding:10px 20px;border-top:1px solid var(--bd);
  background:var(--footer)}
.preFoot .hint{font:400 11px 'Geist';color:var(--faint);flex:1}
/* ── InMeetingTwoPanel (31c) ── */
#liveRoot{display:none;flex-direction:column;height:100vh}
#liveRoot.show{display:flex}
#summaryRoot{display:none}
@keyframes screenIn{from{opacity:0}to{opacity:1}}
::selection{background:var(--acc-soft)}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:rgba(240,240,240,.12);border-radius:99px;
  border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:rgba(240,240,240,.2);border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-track{background:transparent}
.mhead{display:flex;align-items:center;gap:12px;padding:13px 24px;flex:none;
  border-bottom:1px solid var(--bd);background:linear-gradient(180deg,rgba(240,240,240,.025),transparent)}
.liveind{display:inline-flex;align-items:center;gap:7px;padding:4px 11px;border-radius:999px;
  background:var(--rec-subtle);border:1px solid var(--rec-bd);flex:none;
  box-shadow:0 0 18px rgba(224,80,73,.12)}
.liveind i{width:7px;height:7px;border-radius:50%;background:var(--rec);
  animation:mpulse 1.4s ease-in-out infinite;box-shadow:0 0 8px rgba(224,80,73,.7)}
.liveind span{font:600 10px 'JetBrains Mono';letter-spacing:.16em;color:var(--rec-soft)}
.liveind.paused{background:var(--raised);border-color:var(--bd2);box-shadow:none}
.liveind.paused i{background:var(--faint);animation:none;box-shadow:none}
.liveind.paused span{color:var(--mut)}
.liveind.starting i{animation:none}
@keyframes mpulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.8)}}
.mtitle{font:600 16px 'Geist';letter-spacing:-.01em;color:var(--tx);background:none;border:0;outline:none;
  min-width:120px;max-width:320px;text-overflow:ellipsis;padding:2px 4px;border-radius:6px;
  transition:background .15s ease}
.mtitle:hover{background:var(--raised)}
.mtitle:focus{background:var(--raised);box-shadow:0 0 0 1.5px var(--acc-bd)}
.mtitleHint{font:400 10.5px 'Geist';color:var(--faint);opacity:0;transition:opacity .2s}
.mhead:hover .mtitleHint{opacity:1}
.mspacer{flex:1}
/* header live waveform — scaled by real levels each tick */
/* LiveWaveform v2 (33g): split SYS + MIC rows, thin bars in source colors */
.hwave{display:flex;flex-direction:column;justify-content:center;gap:3px;height:18px;
  flex:none;margin-right:2px}
.hwave .wrow{display:flex;align-items:center;gap:2.5px;height:7px}
.hwave .wrow i{width:1.5px;border-radius:2px;height:2px;opacity:.9;
  transition:height .45s cubic-bezier(.4,0,.2,1)}
.hwave .wrow.sys i{background:var(--sp-slate)}
.hwave .wrow.mic i{background:var(--sp-terra)}
.hwave.paused .wrow i{height:2px !important;opacity:.35}
.mtimer{font:500 17px 'JetBrains Mono';color:var(--tx);font-variant-numeric:tabular-nums;
  letter-spacing:-.03em;flex:none}
.mact{display:flex;gap:7px;align-items:center}
/* GlyphButton v2 (rule 3): invisible hit target, the glyph IS the button */
.iconbtn{width:28px;height:28px;border-radius:7px;background:none;color:var(--mut);
  display:inline-flex;align-items:center;justify-content:center;border:0;
  transition:color .14s ease}
.iconbtn:hover{color:var(--tx)}
.iconbtn.accent{background:none;color:var(--tx2)}
.iconbtn.accent:hover{color:var(--acc)}
.iconbtn.rec{background:var(--rec);color:#fff;width:auto;padding:0 13px;gap:6px;
  font:600 11.5px 'Geist';box-shadow:0 2px 12px rgba(224,80,73,.3)}
.iconbtn.rec:hover{background:#e8635c}
.mbody{flex:1;display:flex;min-height:0}
.tpane{flex:1;display:flex;flex-direction:column;min-width:0}
.tpaneHead{display:flex;align-items:center;gap:8px;padding:14px 26px 8px}
.tscroll{flex:1;overflow-y:auto;padding:6px 26px 16px;display:flex;flex-direction:column;gap:16px;
  scroll-behavior:smooth}
.utt{position:relative;max-width:620px;border-radius:10px;padding:6px 10px;margin:-6px -10px;
  transition:background .15s ease}
.utt.fresh{animation:uttIn .3s cubic-bezier(.2,.7,.3,1)}
.utt:hover{background:var(--subtle-alt)}
@keyframes uttIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.utt.marked{border-left:1.5px solid var(--acc);border-radius:0 10px 10px 0;
  padding-left:12px;margin-left:-14px}
.uttHead{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.uttBody{font:400 12.5px/1.62 'Geist';color:var(--tx2)}
.utt .caret{color:var(--acc);animation:mpulse 1s ease-in-out infinite}
.uttMarkChip{font:500 9.5px 'JetBrains Mono';letter-spacing:.12em;color:var(--acc);
  background:none;border-radius:0;padding:0}
/* SpeakerChip v2 (33d): a 6pt colored dot + label. No fill, no pill. */
.schip{display:inline-flex;align-items:center;gap:6px;padding:0;border-radius:0;background:none;
  font:600 11px 'Geist';color:var(--tx);max-width:170px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;cursor:default}
.schip::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--faint);flex:none}
.schip.c0::before{background:var(--sp-terra)}
.schip.c1::before{background:var(--sp-slate)}
.schip.c2::before{background:var(--sp-sage)}
.schip.c3::before,.schip.self::before{background:var(--sp-ochre)}
.schip.unknown{color:var(--tx2)}
.schip.unknown::before{background:var(--faint)}
.schip input{width:90px;font:600 11px 'Geist';color:var(--tx);border-bottom:1.5px solid var(--acc);
  caret-color:var(--acc)}
.uttTime{font:500 10px 'JetBrains Mono';color:var(--faint);font-variant-numeric:tabular-nums}
.tEmpty{flex:1;display:flex;flex-direction:column;gap:14px;align-items:center;justify-content:center;
  color:var(--mut);font:400 12.5px 'Geist'}
.tEmpty .listenWave{display:flex;gap:3px;align-items:center;height:26px}
.tEmpty .listenWave i{width:3px;border-radius:3px;background:var(--acc);opacity:.75;
  animation:listen 1.15s ease-in-out infinite}
.tEmpty .listenWave i:nth-child(1){animation-delay:0s}
.tEmpty .listenWave i:nth-child(2){animation-delay:.12s}
.tEmpty .listenWave i:nth-child(3){animation-delay:.24s}
.tEmpty .listenWave i:nth-child(4){animation-delay:.36s}
.tEmpty .listenWave i:nth-child(5){animation-delay:.48s}
@keyframes listen{0%,100%{height:5px}50%{height:22px}}
.jumpLive{position:absolute;bottom:16px;left:50%;transform:translateX(-50%) translateY(6px);
  padding:6px 14px;border-radius:999px;background:rgba(23,25,28,.92);border:1px solid var(--bd2);
  font:600 11px 'Geist';color:var(--tx);display:none;z-index:5;opacity:0;
  box-shadow:0 6px 20px rgba(0,0,0,.4);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);
  transition:all .2s ease}
.jumpLive.show{display:block;opacity:1;transform:translateX(-50%) translateY(0)}
.jumpLive:hover{border-color:var(--acc-bd);color:var(--acc-txt)}
.tpaneWrap{position:relative;flex:1.35;display:flex;min-width:0}
/* ── ScratchpadPane (31c right) ── */
.spane{flex:1;display:flex;flex-direction:column;background:var(--subtle);min-width:0;
  border-left:1px solid var(--bd)}
.spaneHead{display:flex;align-items:center;gap:8px;padding:14px 20px 8px}
/* Dictate v2 (33h): inline glyph + label, not a chip */
.dictChip{display:inline-flex;align-items:center;gap:6px;margin-left:auto;padding:2px 4px;
  border-radius:6px;background:none;color:var(--tx2);font:500 11px 'Geist';
  cursor:pointer;border:0;transition:color .15s ease}
.dictChip:hover{color:var(--tx)}
.dictChip.on{background:none;color:var(--acc-txt)}
.dictChip.on i{width:6px;height:6px;border-radius:50%;background:var(--rec);
  animation:mpulse 1.4s ease-in-out infinite}
.spad{flex:1;resize:none;padding:8px 20px 16px;font:400 12.5px/1.75 'Geist';color:var(--tx);
  background:transparent;caret-color:var(--acc);outline:none;overflow-y:auto;
  white-space:pre-wrap;word-break:break-word}
.spad:empty::before{content:attr(data-ph);color:var(--faint);pointer-events:none;display:block}
.spad h3{font:600 14px 'Geist';letter-spacing:-.01em;margin:8px 0 2px;color:var(--tx)}
.spad b,.spad strong{font-weight:600}
/* ── MarksFooter ── */
.marksfoot{display:flex;align-items:center;gap:12px;padding:8px 24px;border-top:1px solid var(--bd);
  background:linear-gradient(180deg,var(--chrome),rgba(10,12,14,.6));flex:none;min-height:38px}
.marksfoot .eyebrow{flex:none}
.markrow{display:flex;gap:7px;overflow-x:auto;flex:1;-webkit-overflow-scrolling:touch;
  scrollbar-width:none}
.markrow::-webkit-scrollbar{display:none}
.markpill{display:inline-flex;align-items:center;gap:7px;padding:4px 2px;border-radius:6px;
  background:none;border:0;flex:none;cursor:pointer;max-width:230px;
  transition:color .15s ease;animation:uttIn .25s ease}
.markpill:hover .ml{color:var(--tx)}
.markpill .mt{font:500 10px 'JetBrains Mono';color:var(--acc-txt);font-variant-numeric:tabular-nums}
.markpill .ml{font:500 10.5px 'Geist';color:var(--tx2);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.markpill::before{content:'\\2605';font-size:9px;color:var(--acc)}
.marksEmpty{font:400 10.5px 'Geist';color:var(--faint)}
/* mark feedback — the star must FEEL like it worked */
@keyframes starPop{0%{transform:scale(1)}45%{transform:scale(1.45) rotate(12deg)}100%{transform:scale(1)}}
.iconbtn.pop,.barBtn.pop{animation:starPop .4s cubic-bezier(.3,1.4,.5,1)}
#markToast{position:fixed;top:64px;right:24px;z-index:30;display:none;align-items:center;gap:7px;
  padding:8px 14px;border-radius:999px;background:var(--acc);color:var(--acc-on);
  font:600 11.5px 'Geist';box-shadow:0 8px 24px rgba(200,90,62,.4)}
#markToast.show{display:inline-flex}
#markToast .mono{font:600 10.5px 'JetBrains Mono'}
/* export buttons (summary header) */
.btnS.mini{padding:6px 10px;font:600 10.5px 'JetBrains Mono';letter-spacing:.08em}
/* ── PostMeetingSummary (31e) ── */
/* The WHOLE page scrolls (header sticky) — inner-only scroll made small
   windows unusable; expanded sections grow naturally into the page. */
#summaryRoot{display:none;flex-direction:column;height:100vh;padding:0 28px 24px;gap:12px;
  overflow-y:auto}
#summaryRoot.show{display:flex}
.sumHead{display:flex;align-items:flex-start;gap:10px;flex:none;position:sticky;top:0;z-index:6;
  background:var(--bg);padding:18px 0 10px;border-bottom:1px solid var(--bd)}
.sumHeadL{flex:1;min-width:0}
.sumTitle{font:600 22px 'Geist';letter-spacing:-.02em;color:var(--tx);background:none;
  border:0;outline:none;width:100%}
.sumMeta{display:flex;align-items:center;gap:8px;margin-top:5px;flex-wrap:wrap}
.sumMeta .mono{font:500 10.5px 'JetBrains Mono';color:var(--dim)}
.card{background:var(--raised);border:1px solid var(--bd);border-radius:12px;
  padding:12px 16px}
.sumCards{flex:none;display:flex;flex-direction:column;gap:10px}
.sumBody{font:400 12.5px/1.6 'Geist';color:var(--tx);margin-top:6px}
.sumErr{font:400 12px 'Geist';color:var(--rec-soft);margin-top:6px}
.twoCol{display:flex;gap:10px;align-items:stretch}
.twoCol .colL{flex:1.4;min-width:0}
.twoCol .colR{flex:1;display:flex;flex-direction:column;gap:8px;min-width:0}
.legend{display:flex;gap:14px;margin-left:auto}
.legend span{display:inline-flex;align-items:center;gap:6px;font:400 10.5px 'Geist';color:var(--dim)}
.legend i{width:6px;height:6px;border-radius:50%}
.legend .lu i{background:var(--sp-terra)} .legend .la i{background:var(--faint)}
.cardHead{display:flex;align-items:center;gap:8px}
/* HybridNotesRenderer v2 (33i): dot rows, AI as an indented ↳ line, underline tabs */
.hnTabs{display:flex;gap:12px;margin-left:12px}
.hnTab{font:500 11px 'Geist';color:var(--dim);padding:0 1px 3px;border-bottom:1.5px solid transparent;
  transition:color .14s ease}
.hnTab:hover{color:var(--tx2)}
.hnTab.on{color:var(--tx);border-bottom-color:var(--acc)}
.hnRow{position:relative;border-left:0;padding:0 40px 0 14px;margin-top:11px}
.hnRegen{position:absolute;right:8px;top:1px;width:24px;height:22px;display:inline-flex;
  align-items:center;justify-content:center;color:var(--faint);opacity:0;transition:opacity .12s;
  border-radius:5px}
.hnRow:hover .hnRegen{opacity:1}
.hnRegen:hover{color:var(--acc-txt)}
.hnRegen.busy{opacity:1;color:var(--acc);animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.hnRow::before{content:'';position:absolute;left:0;top:6px;width:6px;height:6px;border-radius:50%;
  background:var(--sp-terra)}
.hnRow.noDot::before{display:none}
.hnUser{font:400 12.5px/1.55 'Geist';color:var(--tx)}
.hnAI{font:400 11.5px/1.55 'Geist';font-style:normal;color:var(--dim);margin-top:2px}
.hnAI::before{content:'\\21B3  ';color:var(--faint)}
#hnList.v-yours .hnAI{display:none}
#hnList.v-ai .hnUser{opacity:.5}
#hnList.v-ai .hnAI{color:var(--tx)}
.dList{margin-top:8px;display:flex;flex-direction:column;gap:6px}
.dItem{display:flex;gap:8px;font:400 12px/1.5 'Geist';color:var(--tx)}
.dItem::before{content:'\\2014';color:var(--faint)}
/* ActionItemRow v2 (33c): rows inside ONE card, faint dividers, real checkbox */
.aiRow{display:flex;align-items:center;gap:10px;padding:9px 0;margin-top:0;
  font:400 12.5px 'Geist';color:var(--tx);border-top:1px solid var(--bd-faint)}
.aiRow:first-of-type{border-top:0}
.aiRow.done{opacity:.55}
.aiRow.done .aiTask{text-decoration:line-through;color:var(--dim)}
.aiTask{flex:1;min-width:0}
.aiCb{width:15px;height:15px;border-radius:4px;border:1.4px solid var(--dim);background:none;flex:none;
  display:inline-flex;align-items:center;justify-content:center;color:transparent;padding:0;
  transition:all .15s ease}
.aiCb:hover{border-color:var(--tx2)}
.aiRow.done .aiCb{background:var(--ok);border-color:var(--ok);color:#0a1f0d}
/* MarkedMomentCard v2 (33b): rows in the parent card, star + mono ts header */
.mmRow{padding:11px 0;border-top:1px solid var(--bd-faint)}
.mmRow:first-of-type{border-top:0}
.mmHead{display:flex;align-items:center;gap:8px}
.mmHead .star{color:var(--acc);display:inline-flex}
.mmTs{font:500 11px 'JetBrains Mono';color:var(--acc-txt);letter-spacing:.06em;
  font-variant-numeric:tabular-nums;cursor:pointer}
.mmTs:hover{text-decoration:underline}
.mmEx{font:400 12.5px/1.6 'Geist';color:var(--tx);margin-top:5px}
.mmEx b{color:var(--dim);font-weight:400}
.mmRow{position:relative;padding-right:70px}
.mmActs{position:absolute;top:9px;right:0;display:flex;gap:2px;opacity:0;transition:opacity .12s}
.mmRow:hover .mmActs,.mmRow:focus-within .mmActs{opacity:1}
.mmNote{margin-top:9px;padding-top:9px;border-top:1px solid var(--bd-faint)}
.mmNote .k{font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;color:var(--sp-ochre);
  text-transform:uppercase;margin-bottom:3px}
.mmNote p{font:400 12px/1.55 'Geist';color:var(--tx);margin:0;cursor:text;border-radius:5px}
.mmNote p:hover{background:var(--subtle-alt)}
.mmNoteAdd{font:400 11px 'Geist';color:var(--faint);cursor:pointer;margin-top:7px;
  display:inline-block;opacity:0;transition:opacity .12s}
.mmRow:hover .mmNoteAdd{opacity:1}
.mmNoteAdd:hover{color:var(--acc-txt)}
.mmNoteIn{width:100%;font:400 12px/1.55 'Geist';color:var(--tx);background:var(--raised);
  border:1px solid var(--acc-bd);border-radius:8px;padding:6px 9px;margin-top:6px;resize:vertical;
  min-height:38px;caret-color:var(--acc)}
/* star count numeral (33f) — no badge disc */
#mStarBtn{position:relative}
#mStarBtn .stN{position:absolute;top:-3px;right:-5px;font:500 9.5px 'JetBrains Mono';
  color:var(--acc-txt);font-variant-numeric:tabular-nums}
/* summary header avatars (33d) */
.avchip{display:inline-flex;align-items:center;gap:7px;font:600 11px 'Geist';color:var(--tx)}
.av{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;
  justify-content:center;font:600 9.5px 'Geist';flex:none}
.av.c0{background:rgba(217,138,114,.16);color:var(--sp-terra)}
.av.c1{background:rgba(143,167,194,.16);color:var(--sp-slate)}
.av.c2{background:rgba(169,189,152,.16);color:var(--sp-sage)}
.av.c3,.av.self{background:rgba(217,179,107,.16);color:var(--sp-ochre)}
.av.self{box-shadow:0 0 0 1px var(--bg), 0 0 0 2.5px var(--sp-ochre)}
.av.unknown{background:none;border:1px dashed var(--faint);color:var(--dim)}
.avchip{position:relative}
.avFp{position:absolute;left:14px;top:14px;width:9px;height:9px;border-radius:50%;
  background:var(--acc);border:2px solid var(--bg)}
.fpBanner{display:flex;align-items:center;gap:9px;margin-top:8px;font:400 11.5px 'Geist';
  color:var(--tx2)}
.fpBanner b{color:var(--tx);font-weight:600}
.fpBanner .zap{color:var(--acc);display:inline-flex}
.fpBanner .k{margin-left:auto;font:500 9.5px 'JetBrains Mono';letter-spacing:.16em;
  color:var(--faint)}
/* transcript row action rail + inline edit (33a) */
.exUtt{position:relative;padding-right:64px}
.exUtt .xr{position:absolute;top:1px;right:2px;display:flex;gap:0;opacity:0;transition:opacity .12s}
.exUtt:hover .xr,.exUtt:focus-within .xr{opacity:1}
.xr .iconbtn{width:24px;height:22px}
.edTag{font:500 9px 'JetBrains Mono';letter-spacing:.08em;color:var(--faint);margin-left:6px}
.txEditIn{width:100%;font:400 11.5px/1.55 'Geist';color:var(--tx);background:var(--raised);
  border:1px solid var(--acc-bd);border-radius:8px;padding:6px 9px;margin-top:4px;resize:vertical;
  min-height:44px;caret-color:var(--acc)}
/* action item edit/delete (33c) */
.aiRow{padding-right:24px;position:relative}
.aiDel{position:absolute;right:0;top:50%;transform:translateY(-50%);width:20px;height:20px;
  display:inline-flex;align-items:center;justify-content:center;color:var(--faint);opacity:0;
  transition:opacity .12s;border-radius:5px;font:500 12px 'Geist'}
.aiRow:hover .aiDel,.aiRow:focus-within .aiDel{opacity:1}
.aiDel:hover{color:var(--rec-soft)}
.aiTask{cursor:text;border-radius:5px}
.aiTask:hover{background:var(--subtle-alt)}
.aiEditIn{flex:1;min-width:0;font:400 12.5px 'Geist';color:var(--tx);background:var(--raised);
  border:1px solid var(--acc-bd);border-radius:6px;padding:4px 8px;caret-color:var(--acc)}
.aiDue{font:500 9.5px 'JetBrains Mono';letter-spacing:.05em;color:var(--faint);flex:none}
.aiDue.near{color:var(--acc-txt)}
/* dictated-text flash (33h) */
.spad{transition:background .8s ease}
.spad.flash{background:var(--acc-softer);transition:none}
.teasers{display:flex;gap:8px;flex:none}
.teaser{flex:1;display:flex;align-items:center;gap:8px;background:var(--raised);
  border:1px solid var(--bd);border-radius:10px;padding:9px 12px;cursor:pointer}
.teaser .tl{font:400 11px 'Geist';color:var(--tx);flex:1}
.teaser .eyebrow{margin-left:auto}
.expandBox{display:none;flex-direction:column;gap:8px}   /* grows into the page scroll */
.expandBox.show{display:flex}
.skel{height:11px;border-radius:6px;background:var(--raised2);margin-top:8px;
  animation:shimmer 1.6s ease-in-out infinite}
@keyframes shimmer{0%,100%{opacity:.5}50%{opacity:1}}
.exUtt{cursor:pointer;border-radius:8px;padding:4px 8px}
.exUtt:hover{background:var(--raised)}
.exUtt.playing{background:var(--acc-soft)}
/* ── Meeting Notes page (full-page view, MODE 'notes') ── */
#notesRoot{display:none;flex-direction:column;height:100vh;overflow-y:auto;padding:0 28px 40px}
#notesRoot.show{display:flex}
.ntHead{display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:6;
  background:var(--bg);padding:16px 0 10px;border-bottom:1px solid var(--bd);flex:none}
.ntBack{display:inline-flex;align-items:center;gap:6px;background:none;border:0;
  color:var(--tx2);font:600 12px 'Geist';cursor:pointer;padding:4px 8px;border-radius:8px}
.ntBack:hover{color:var(--tx);background:var(--raised)}
.ntTitle{font:600 15px 'Geist';letter-spacing:-.01em;color:var(--tx);flex:1;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ntBody{max-width:720px;width:100%;margin:18px auto 0;font:400 13.5px/1.75 'Geist';color:var(--tx)}
.ntBody p{margin:0 0 14px}
.ntBody .ctx{font:400 13.5px/1.7 'Geist';color:var(--tx2);border-left:2px solid var(--acc);
  padding:2px 0 2px 14px;margin:0 0 22px}
.ntBody h2{font:600 11px 'JetBrains Mono';letter-spacing:.16em;text-transform:uppercase;
  color:var(--acc-txt);margin:26px 0 10px;padding-top:16px;border-top:1px solid var(--bd-faint)}
.ntBody h2:first-child{border-top:0;padding-top:0;margin-top:0}
.ntBody h3{font:600 13.5px 'Geist';color:var(--tx);margin:16px 0 6px}
.ntBody ul,.ntBody ol{margin:0 0 14px;padding-left:20px;display:flex;flex-direction:column;gap:7px}
.ntBody li{padding-left:2px}
.ntBody ul li::marker{color:var(--sp-terra)}
.ntBody ol li::marker{color:var(--dim);font:500 11px 'JetBrains Mono'}
.ntBody b,.ntBody strong{font-weight:600;color:var(--tx)}
.ntBody code{font:500 12px 'JetBrains Mono';background:var(--raised);border-radius:5px;padding:1px 6px}
.ntTableWrap{overflow-x:auto;margin:6px 0 16px}
.ntTable{border-collapse:collapse;width:100%;font:400 12.5px 'Geist'}
.ntTable th{text-align:left;font:600 10px 'JetBrains Mono';letter-spacing:.1em;text-transform:uppercase;
  color:var(--acc-txt);padding:7px 12px 7px 0;border-bottom:1px solid var(--bd2);white-space:nowrap}
.ntTable td{padding:7px 12px 7px 0;border-bottom:1px solid var(--bd-faint);color:var(--tx);vertical-align:top}
.ntTable tr:last-child td{border-bottom:0}
.ntTask{display:flex;align-items:flex-start;gap:9px;margin:0 0 8px}
.ntTask .box{width:15px;height:15px;border-radius:4px;border:1.4px solid var(--dim);flex:none;
  margin-top:3px;display:inline-flex;align-items:center;justify-content:center;color:transparent}
.ntTask.done .box{background:var(--ok);border-color:var(--ok);color:#0a1f0d}
.ntTask.done span{text-decoration:line-through;color:var(--dim)}
.ntSkel{max-width:720px;width:100%;margin:26px auto 0;display:flex;flex-direction:column;gap:12px}
.ntSkel i{display:block;height:12px;border-radius:6px;background:var(--raised2);
  animation:shimmer 1.6s ease-in-out infinite}
.ntErr{max-width:720px;margin:30px auto;color:var(--rec-soft);font:400 13px 'Geist';text-align:center}
"""


def _permission_modal():
    """PermissionChecklistModal (31h) — markup; states driven by JS renderPerms()."""
    return f"""
  <div id="permWrap" hidden>
    <div class="permPanel">
      <div class="permHead">
        <div class="permHeadRow">
          <div class="permTile">{_svg('wave', 17)}</div>
          <div>
            <div class="permTitle">Allow meeting capture</div>
            <div class="permSub">One-time setup &middot; takes about a minute</div>
          </div>
        </div>
        <div class="permInfo">Flume records the meeting <b>on this Mac</b> — no bot joins your call.
        To hear the other side, macOS requires the <b>Screen &amp; System Audio Recording</b>
        permission (audio only; Flume never captures your screen). Your microphone needs its
        usual permission too.</div>
      </div>
      <div class="permSteps">
        <div class="eyebrow" id="permStepsHead">Steps &middot; 0 of 3 complete</div>
        <div id="permStepList"></div>
      </div>
      <div class="permErr" id="permErr"></div>
      <div class="permMeter" id="permMeter"><i id="permMeterBar"></i></div>
      <div class="permFoot">
        <div class="hint">Denied by mistake? <a onclick="api('request_permission','system_audio')">Recovery steps</a></div>
        <button class="btnS" onclick="permSkip()">Skip for now</button>
        <button class="btnP" id="permTestBtn" onclick="permTest()" disabled>Test capture</button>
      </div>
    </div>
  </div>"""


def _premeeting_modal():
    """PreMeetingModal (31b) — title + capture-source toggles + start."""
    return f"""
  <div id="preWrap">
    <div class="prePanel">
      <div class="preHead">
        <span class="eyebrow">New meeting</span>
        <input class="preTitle" id="preTitle" placeholder="Meeting title" spellcheck="false"/>
        <div class="preCap">Leave blank to use "Meeting — today's date".</div>
      </div>
      <div class="preGroup">
        <span class="eyebrow">Capturing</span>
        <div class="srcRow">
          <div class="disc" id="preSysDisc">{_svg('wave', 13)}</div>
          <div class="stx"><div class="sl">System audio</div><div class="ss" id="preSysSub">The other side of the call</div></div>
          <button class="toggle on" id="preSysTgl" onclick="preToggle('sys')"></button>
        </div>
        <div class="srcRow">
          <div class="disc" id="preMicDisc">{_svg('mic', 13)}</div>
          <div class="stx"><div class="sl">Microphone</div><div class="ss">You</div></div>
          <button class="toggle on" id="preMicTgl" onclick="preToggle('mic')"></button>
        </div>
        <div class="srcRow">
          <div class="stx"><div class="sl">Language</div><div class="ss">What this meeting will be spoken in</div></div>
          <select class="preLang" id="preLang" onchange="PRE.lang=this.value"></select>
        </div>
      </div>
      <div class="preFoot">
        <span class="hint">Press Enter to start</span>
        <button class="btnS" onclick="preCancel()">Cancel</button>
        <button class="btnP" id="preStartBtn" onclick="preStart()">Start recording</button>
      </div>
    </div>
  </div>"""


def _live_screen():
    """InMeetingTwoPanel (31c) — Phase 2: live transcript pane (scratchpad Phase 3)."""
    return f"""
  <div id="liveRoot">
    <div class="mhead">
      <span class="liveind" id="liveInd"><i></i><span id="liveIndTx">REC</span></span>
      <input class="mtitle" id="mTitle" value="" spellcheck="false"
             onchange="api('set_meeting_title', this.value)"/>
      <span class="mtitleHint">click to rename</span>
      <span class="mspacer"></span>
      <span class="hwave" id="hWave" title="System audio (blue) + microphone (terracotta)">
        <span class="wrow sys" id="wSys"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>
        <span class="wrow mic" id="wMic"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>
      </span>
      <span class="mtimer mono" id="mTimer">0:00</span>
      <div class="mact">
        <button class="iconbtn accent" id="mStarBtn" title="Mark this moment (⌘.)" onclick="api('mark_moment','')">{_svg('star', 13)}<span class="stN" id="stN"></span></button>
        <button class="iconbtn" title="Pause (⌘P)" id="mPauseBtn" onclick="api('pause_meeting')">{_svg('pause', 13)}</button>
        <button class="iconbtn" title="Collapse to bar" onclick="api('collapse_meeting_window')">{_svg('collapse', 13)}</button>
        <button class="iconbtn rec" title="Stop (⌘Enter)" onclick="liveStop()">{_svg('stop', 12)}<span>Stop</span></button>
      </div>
    </div>
    <div class="mbody">
      <div class="tpaneWrap">
        <div class="tpane">
          <div class="tpaneHead"><span class="eyebrow">Live transcript</span></div>
          <div class="tscroll" id="tScroll"><div class="tEmpty" id="tEmpty">
            <span class="listenWave"><i></i><i></i><i></i><i></i><i></i></span>
            <span>Listening — the transcript appears as people speak…</span>
          </div></div>
        </div>
        <button class="jumpLive" id="jumpLive" onclick="jumpToLive()">Jump to live ↓</button>
      </div>
      <div class="spane">
        <div class="spaneHead">
          <span class="eyebrow">Your notes</span>
          <span class="dictChip" id="dictChip" onclick="toggleDictate()">{_svg('mic', 11)}<i></i><span id="dictChipTx">Dictate</span></span>
        </div>
        <div class="spad" id="spad" contenteditable="true" spellcheck="true"
          role="textbox" aria-multiline="true" aria-label="Your notes"
          data-ph="Type or dictate — Flume will fill in the details around your notes."
          oninput="spadInput()" onkeydown="spadKey(event)"></div>
      </div>
    </div>
    <div class="marksfoot">
      <span class="eyebrow accd">★ Marks</span>
      <div class="markrow" id="markRow"><span class="marksEmpty">Press ⌘. (or the star) to mark a moment.</span></div>
    </div>
  </div>"""


def _summary_screen():
    """PostMeetingSummary (31e) — shells; content rendered by JS renderSummary()."""
    return f"""
  <div id="summaryRoot">
    <div class="sumHead">
      <div class="sumHeadL">
        <span class="eyebrow" id="sumEyebrow">Meeting</span>
        <input class="sumTitle" id="sumTitle" value="" spellcheck="false"
               onchange="api('set_meeting_title', this.value)"/>
        <div class="sumMeta" id="sumMeta"></div>
      </div>
      <div class="mact">
        <button class="btnS mini" id="expTxtBtn" title="Export transcript as .txt" onclick="sumExport('txt')">TXT</button>
        <button class="btnS mini" id="expMdBtn" title="Export as Markdown" onclick="sumExport('md')">MD</button>
        <button class="iconbtn" id="sumDelBtn" title="Delete meeting" onclick="sumDelete()">{_svg('trash', 13)}</button>
        <button class="iconbtn" title="Copy summary to clipboard" onclick="sumShare(this)">{_svg('share', 13)}</button>
        <button class="iconbtn" title="Regenerate summary" onclick="sumRegen()">{_svg('refresh', 13)}</button>
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
      <div class="teaser" onclick="toggleBox('marksBox', renderMarksBox)">{_svg('star', 12)}<span class="tl" id="marksTeaseL">Marked moments</span><span class="eyebrow">Expand</span></div>
      <div class="teaser" onclick="toggleBox('txBox', renderTxBox)">{_svg('search', 12)}<span class="tl" id="txTeaseL">Full transcript</span><span class="eyebrow">Expand</span></div>
    </div>
    <audio id="sumAudio"></audio>
  </div>"""


def _bar():
    """The ambient meeting bar (morph target) — click to expand."""
    return f"""
  <div id="notesRoot">
    <div class="ntHead">
      <button class="ntBack" onclick="notesBack()">&#8249; Summary</button>
      <span class="ntTitle" id="ntTitle">Meeting notes</span>
      <button class="btnS mini" title="Copy notes as Markdown" onclick="notesCopy(this)">Copy</button>
      <button class="iconbtn" title="Regenerate notes" onclick="openNotes(true)">{_svg('refresh', 13)}</button>
    </div>
    <div class="ntSkel" id="ntSkel" style="display:none"><i style="width:38%"></i><i style="width:92%"></i><i style="width:85%"></i><i style="width:60%"></i><i style="width:88%"></i><i style="width:74%"></i></div>
    <div class="ntErr" id="ntErr" style="display:none"></div>
    <div class="ntBody" id="ntBody"></div>
  </div>
  <div id="markToast"><span id="markToastMsg">★ Marked</span> <span class="mono" id="markToastT"></span></div>
  <div id="barRoot">
    <div class="barPill" id="barPill" onclick="barExpand(event)">
      <span class="barDot"></span>
      <span class="barTitle" id="barTitle">Meeting</span>
      <span class="barPausedTag">PAUSED</span>
      <span class="barWave" id="barWave"><i></i><i></i><i></i><i></i><i></i><i></i></span>
      <span class="barTimer mono" id="barTimer">0:00</span>
      <button class="barBtn accent" id="barStarBtn" title="Mark moment" onclick="event.stopPropagation();api('mark_moment','')">{_svg('star', 12)}</button>
      <button class="barBtn" id="barPause" title="Pause / resume" onclick="event.stopPropagation();api('pause_meeting')">{_svg('pause', 12)}</button>
      <button class="barBtn stop" title="Stop meeting" onclick="event.stopPropagation();api('stop_meeting')">{_svg('stop', 11)}</button>
    </div>
  </div>"""


def meeting_html() -> str:
    body = f"""
  {_bar()}
  {_permission_modal()}
  {_premeeting_modal()}
  {_live_screen()}
  {_summary_screen()}"""

    js = r"""
<script>
function api(name){ const a=[].slice.call(arguments,1);
  return (window.pywebview && window.pywebview.api && window.pywebview.api[name])
    ? window.pywebview.api[name].apply(null,a) : Promise.resolve({ok:false}); }
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

let MODE='permissions';           // permissions | premeeting | live | summary
let LAYOUT='expanded';            // bar | expanded (native panel morph)
let PERMS=null;                   // meeting_permissions() payload
let TESTING=false;
let HNVIEW='merged';              // hybrid-notes view: yours | merged | ai (33i)
document.body && (document.body.className='lay-expanded');

function applyLayout(){
  document.body.className='lay-'+LAYOUT;
}
function barExpand(ev){
  api('expand_meeting_window');
}
function renderBar(){
  const pill=document.getElementById('barPill');
  if(!pill) return;
  pill.className='barPill'+(MEET.state==='paused'?' paused':'');
  document.getElementById('barTitle').textContent=MEET.title||'Meeting';
}

// ── PermissionChecklistModal (31h) ─────────────────────────────────────────────
const STEP_COPY = {
  support:      {label:'Meeting capture engine', sub:'Built into Flume on macOS 13 and later.',
                 subPending:'Checking this Mac…'},
  system_audio: {label:'Allow System Audio Recording', sub:'Lets Flume hear the other side of the call.',
                 subActive:'macOS will ask for Screen & System Audio Recording.'},
  microphone:   {label:'Allow Microphone', sub:'Lets Flume hear you.',
                 subActive:'macOS will ask for Microphone access.'},
};

function renderPerms(){
  const wrap = document.getElementById('permWrap');
  if(MODE!=='permissions'){ wrap.hidden=true; return; }
  wrap.hidden=false;
  const list = document.getElementById('permStepList');
  if(!PERMS){ list.innerHTML=''; return; }
  let doneCount=0, firstUndone=true, html='';
  PERMS.steps.forEach(function(st, i){
    const c = STEP_COPY[st.id]||{label:st.id, sub:''};
    let cls='pending', disc=String(i+1), sub=c.sub;
    if(st.done){ cls='done'; disc='✓'; doneCount++; }
    else if(st.denied){ cls='denied'; disc='!'; sub='Denied in System Settings — click Grant to fix.'; }
    else if(firstUndone){ cls='active'; sub=c.subActive||c.subPending||c.sub; }
    if(!st.done) firstUndone=false;
    let act='';
    if(cls==='active' || cls==='denied'){
      if(st.id==='system_audio')
        act='<div class="sact"><button class="btnP" onclick="permGrant(\'system_audio\')">Open Sound settings</button>'+
            '<button class="btnS" onclick="permHow()">Show me how</button></div>';
      else if(st.id==='microphone')
        act='<div class="sact"><button class="btnP" onclick="permGrant(\'microphone\')">Grant microphone</button></div>';
    }
    html+='<div class="step '+cls+'"><div class="disc">'+disc+'</div><div class="stx">'+
      '<div class="slabel">'+esc(c.label)+'</div><div class="ssub">'+esc(sub)+'</div>'+act+'</div></div>';
  });
  list.innerHTML=html;
  document.getElementById('permStepsHead').textContent='Steps · '+doneCount+' of '+PERMS.steps.length+' complete';
  document.getElementById('permTestBtn').disabled = !(PERMS.ready) || TESTING;
}

function loadPerms(){
  api('get_meeting_permissions').then(function(p){
    if(p && p.steps){ PERMS=p; renderPerms(); }
  });
}
function permGrant(which){
  api('request_permission', which).then(function(){ setTimeout(loadPerms, 800); });
}
function permHow(){
  const el=document.getElementById('permErr');
  el.className='permErr show';
  el.innerHTML='1&#41; Click <b>Open Sound settings</b> — macOS shows the permission prompt.<br>'+
    '2&#41; If no prompt appears: System Settings → Privacy &amp; Security → <b>Screen &amp; System Audio Recording</b>.<br>'+
    '3&#41; Enable <b>Verbal</b>, then come back here — the checklist re-checks automatically.';
}
function permSkip(){ api('meeting_permissions_skipped'); }
function permTest(){
  TESTING=true; renderPerms();
  const meter=document.getElementById('permMeter'), bar=document.getElementById('permMeterBar');
  meter.className='permMeter show';
  api('test_meeting_capture').then(function(r){
    TESTING=false;
    if(r && r.ok){
      bar.style.width='100%';
      document.getElementById('permErr').className='permErr';
      setTimeout(function(){ api('meeting_permissions_done'); }, 1200);
    } else {
      meter.className='permMeter'; bar.style.width='0%';
      const el=document.getElementById('permErr');
      el.className='permErr show';
      el.textContent=(r && r.error) ? r.error : 'Test failed — no audio captured. Try the recovery steps.';
      renderPerms();
    }
  });
}
// live level pulses while testing
function permLevel(v){
  const bar=document.getElementById('permMeterBar');
  if(bar) bar.style.width=Math.max(4, Math.min(100, Math.round(v*100)))+'%';
}

// ── PreMeetingModal (31b) ──────────────────────────────────────────────────────
let PRE={sys:true, mic:true, lang:''};
let PRE_LANGS_LOADED=false;
function loadPreLangs(){
  if(PRE_LANGS_LOADED) return;
  api('get_spoken_language').then(function(r){
    if(!(r && r.ok)) return;
    PRE_LANGS_LOADED=true;
    PRE.lang = r.value || 'en';
    const sel=document.getElementById('preLang');
    if(!sel) return;
    sel.innerHTML=(r.options||[]).map(function(o){
      return '<option value="'+esc(o[0])+'"'+(o[0]===PRE.lang?' selected':'')+'>'+esc(o[1])+'</option>';
    }).join('');
  });
}
function renderPre(){
  document.getElementById('preWrap').className = (MODE==='premeeting') ? 'show' : '';
  if(MODE==='premeeting') loadPreLangs();
  if(MODE!=='premeeting') return;
  document.getElementById('preSysTgl').className='toggle'+(PRE.sys?' on':'');
  document.getElementById('preMicTgl').className='toggle'+(PRE.mic?' on':'');
  document.getElementById('preSysDisc').className='disc'+(PRE.sys?'':' off');
  document.getElementById('preMicDisc').className='disc'+(PRE.mic?'':' off');
  document.getElementById('preStartBtn').disabled = !(PRE.sys||PRE.mic);
  const t=document.getElementById('preTitle');
  setTimeout(function(){ t.focus(); }, 60);
}
function preToggle(which){ PRE[which]=!PRE[which]; renderPre(); }
function preCancel(){ MODE='idle'; renderPre(); api('close_meeting_window'); }
function preStart(){
  if(!(PRE.sys||PRE.mic)) return;
  const title=(document.getElementById('preTitle').value||'').trim();
  MODE='live'; renderPre(); renderLive();
  api('start_meeting', title, PRE.mic, PRE.sys, PRE.lang||'');
}
document.addEventListener('keydown', function(ev){
  if(MODE!=='premeeting') return;
  if(ev.key==='Enter'){ ev.preventDefault(); preStart(); }
  else if(ev.key==='Escape'){ ev.preventDefault(); preCancel(); }
});

// ── Live screen (31c) ──────────────────────────────────────────────────────────
let MEET={id:null, state:'idle', title:'', speakers:{}};
let UTTS=[];                       // rendered utterances
let MARKS=[];                      // marked moments [{t,label}]
let AUTOSCROLL=true;
let LIVE_ID=null;                  // which meeting the live panes belong to
// keep in sync with the #tEmpty markup in _live_screen()
const T_EMPTY_HTML='<div class="tEmpty" id="tEmpty">'+
  '<span class="listenWave"><i></i><i></i><i></i><i></i><i></i></span>'+
  '<span>Listening — the transcript appears as people speak…</span></div>';
function resetLive(){
  // the window is ONE reused page: a new meeting must never show the previous
  // meeting's transcript/marks/notes/timer
  UTTS=[]; MARKS=[]; RENDERED_N=0; AUTOSCROLL=true;
  const box=document.getElementById('tScroll');
  if(box) box.innerHTML=T_EMPTY_HTML;
  renderMarks();
  const p=document.getElementById('spad'); if(p) p.innerHTML='';
  const t=document.getElementById('mTimer'); if(t) t.textContent='0:00';
  const bt=document.getElementById('barTimer'); if(bt) bt.textContent='0:00';
  const j=document.getElementById('jumpLive'); if(j) j.className='jumpLive';
  if(DICTATING){ DICTATING=false;
    const c=document.getElementById('dictChip'); if(c) c.className='dictChip';
    const x=document.getElementById('dictChipTx'); if(x) x.textContent='Dictate'; }
}

const CHIP_CLASS = {self:'self'};
function chipClass(sid){
  if(CHIP_CLASS[sid]) return CHIP_CLASS[sid];
  const n = parseInt(String(sid).replace(/[^0-9]/g,''),10)||1;
  return 'c'+((n-1)%4);
}
function fmtT(secs){
  secs=Math.max(0,Math.floor(secs||0));
  const h=Math.floor(secs/3600), m=Math.floor((secs%3600)/60), s=secs%60;
  const mm=(h? String(m).padStart(2,'0') : String(m)), ss=String(s).padStart(2,'0');
  return h? (h+':'+mm+':'+ss) : (mm+':'+ss);
}
function speakerName(sid){ return MEET.speakers[sid] || (sid==='self'?'You':'Speaker'); }

function renderLive(){
  document.getElementById('liveRoot').className = (MODE==='live') ? 'show' : '';
  if(MODE!=='live') return;
  const t=document.getElementById('mTitle');
  if(document.activeElement!==t) t.value=MEET.title||'';
  const ind=document.getElementById('liveInd'), tx=document.getElementById('liveIndTx');
  if(MEET.state==='paused'){ ind.className='liveind paused'; tx.textContent='PAUSED'; }
  else if(MEET.state==='preparing'){ ind.className='liveind starting'; tx.textContent='STARTING'; }
  else if(MEET.state==='stopping'||MEET.state==='processing'){ ind.className='liveind starting'; tx.textContent='SAVING'; }
  else { ind.className='liveind'; tx.textContent='REC'; }
}
function isMarked(u){
  return MARKS.some(function(m){ return m.t>=u.t0-2 && m.t<=u.t1+2; });
}
let RENDERED_N=0;   // animate only rows that weren't in the previous render
function uttHtml(u, idx){
  const marked=isMarked(u);
  const fresh=idx>=RENDERED_N;
  return '<div class="utt'+(marked?' marked':'')+(fresh?' fresh':'')+'" data-sid="'+esc(u.speaker)+'">'+
    '<div class="uttHead">'+
      '<span class="schip '+chipClass(u.speaker)+'" ondblclick="chipRename(this, \''+esc(u.speaker)+'\')">'+esc(speakerName(u.speaker))+'</span>'+
      '<span class="uttTime mono">'+fmtT(u.t0)+'</span>'+
      (marked?'<span class="uttMarkChip">★</span>':'')+
    '</div><div class="uttBody">'+esc(u.text)+'</div></div>';
}
function renderUtts(){
  const box=document.getElementById('tScroll');
  const empty=document.getElementById('tEmpty');
  if(!UTTS.length){ if(empty) empty.style.display='flex'; return; }
  box.innerHTML = UTTS.map(uttHtml).join('');
  RENDERED_N = UTTS.length;
  if(AUTOSCROLL) box.scrollTop = box.scrollHeight;
}
function chipRename(el, sid){
  const cur=speakerName(sid);
  el.innerHTML='<input value="'+esc(cur)+'" onkeydown="chipKey(event,this,\''+esc(sid)+'\')" onblur="chipCommit(this,\''+esc(sid)+'\')"/>';
  el.querySelector('input').focus();
  el.querySelector('input').select();
}
function chipKey(ev, input, sid){
  if(ev.key==='Enter'){ input.blur(); }
  else if(ev.key==='Escape'){ input.value=speakerName(sid); input.blur(); }
}
function chipCommit(input, sid){
  const v=(input.value||'').trim();
  if(v && v!==speakerName(sid)){ MEET.speakers[sid]=v; api('rename_speaker', sid, v); }
  renderUtts();
}
function jumpToLive(){
  AUTOSCROLL=true;
  const box=document.getElementById('tScroll');
  box.scrollTop=box.scrollHeight;
  document.getElementById('jumpLive').className='jumpLive';
}
function liveStop(){ api('stop_meeting'); }

// ── ScratchpadPane ─────────────────────────────────────────────────────────────
let SPAD_TIMER=null, DICTATING=false;
function spadChanged(){
  const pad=document.getElementById('spad');
  if(DICTATING){
    // freshly-dictated text flashes accent then fades (33h)
    pad.classList.add('flash'); void pad.offsetWidth;
    pad.classList.remove('flash');
  }
  clearTimeout(SPAD_TIMER);
  SPAD_TIMER=setTimeout(function(){
    api('save_meeting_scratchpad', pad.innerText||'');
  }, 600);
}
function spadCaretEnd(node){
  try{
    const r=document.createRange();
    r.setStart(node, node.textContent.length); r.collapse(true);
    const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }catch(e){}
}
function spadInput(){
  // markdown-lite at the caret: "- " / "* " → em-dash bullet, "# " → heading
  const sel=window.getSelection(), node=sel&&sel.anchorNode;
  if(node && node.nodeType===3){
    const t=node.textContent;
    if(t==='- '||t==='* '){ node.textContent='— '; spadCaretEnd(node); }
    else if(t==='# '){
      node.textContent='';
      try{ document.execCommand('formatBlock', false, 'h3'); }catch(e){}
    }
  }
  spadChanged();
}
function spadKey(ev){
  // Enter continues "— " bullets and "1. " numbered lists; an empty bullet ends the list
  if(ev.key!=='Enter' || ev.shiftKey) return;
  const sel=window.getSelection(), node=sel&&sel.anchorNode;
  if(!node || node.nodeType!==3 || !sel.isCollapsed) return;
  const line=node.textContent;
  if(sel.anchorOffset!==line.length) return;
  const m=line.match(/^(— |\d+\. )/);
  if(!m) return;
  if(line===m[1]){ return; }              // empty bullet → let Enter end the list
  ev.preventDefault();
  let prefix=m[1];
  const num=prefix.match(/^(\d+)\. /);
  if(num) prefix=(parseInt(num[1],10)+1)+'. ';
  document.execCommand('insertText', false, '\n'+prefix);
}
function toggleDictate(){
  // Reuses the standard dictation path: the transcript is pasted into the
  // focused field — we focus the scratchpad so it lands there.
  const chip=document.getElementById('dictChip'), tx=document.getElementById('dictChipTx');
  if(!DICTATING){
    DICTATING=true; chip.className='dictChip on'; tx.textContent='Listening…';
    document.getElementById('spad').focus();
    api('start_recording');
  } else {
    DICTATING=false; chip.className='dictChip'; tx.textContent='Dictate';
    api('stop_recording');
    setTimeout(spadChanged, 2500);   // persist once the paste lands
  }
}

// ── MarksFooter ────────────────────────────────────────────────────────────────
function renderMarks(){
  const row=document.getElementById('markRow');
  const n=document.getElementById('stN');
  if(n) n.textContent=MARKS.length ? (MARKS.length>99?'99+':String(MARKS.length)) : '';
  if(!MARKS.length){
    row.innerHTML='<span class="marksEmpty">Press ⌘. (or the star) to mark a moment.</span>';
    return;
  }
  row.innerHTML=MARKS.map(function(m,i){
    return '<span class="markpill" onclick="scrollToMark('+i+')">'+
      '<span class="mt">'+fmtT(m.t)+'</span>'+
      (m.label?'<span class="ml">'+esc(m.label)+'</span>':'')+'</span>';
  }).join('');
}
let MARK_TOAST_T=null, BAR_TITLE_T=null;
function toast(msg, mono){
  const el=document.getElementById('markToast');
  if(!el) return;
  document.getElementById('markToastMsg').textContent=msg;
  document.getElementById('markToastT').textContent=mono||'';
  el.classList.add('show');
  clearTimeout(MARK_TOAST_T);
  MARK_TOAST_T=setTimeout(function(){ el.classList.remove('show'); }, 1700);
}
function momentFeedback(m){
  // pop the star that was pressed
  ['mStarBtn','barStarBtn'].forEach(function(id){
    const b=document.getElementById(id); if(!b) return;
    b.classList.remove('pop'); void b.offsetWidth; b.classList.add('pop');
    setTimeout(function(){ b.classList.remove('pop'); }, 450);
  });
  if(LAYOUT==='bar'){
    // flash the bar title so the collapsed widget confirms the mark
    const t=document.getElementById('barTitle'); if(!t) return;
    clearTimeout(BAR_TITLE_T);
    t.textContent='★ Marked '+fmtT(m.t);
    BAR_TITLE_T=setTimeout(function(){ t.textContent=MEET.title||'Meeting'; }, 1400);
  } else {
    toast('★ Marked', fmtT(m.t));
  }
}
function scrollToMark(i){
  const m=MARKS[i]; if(!m) return;
  let best=null, bestD=1e9;
  UTTS.forEach(function(u,idx){
    const d=Math.abs(u.t0-m.t); if(d<bestD){ bestD=d; best=idx; }
  });
  if(best===null) return;
  const box=document.getElementById('tScroll');
  const el=box.children[best];
  if(el && el.scrollIntoView){ AUTOSCROLL=false; el.scrollIntoView({behavior:'smooth', block:'center'}); }
}

document.addEventListener('DOMContentLoaded', function(){
  const box=document.getElementById('tScroll');
  if(box) box.addEventListener('scroll', function(){
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    AUTOSCROLL = atBottom;
    document.getElementById('jumpLive').className = atBottom ? 'jumpLive' : 'jumpLive show';
  });
});
document.addEventListener('keydown', function(ev){
  if(MODE!=='live') return;
  if((ev.metaKey||ev.ctrlKey) && ev.key==='.'){ ev.preventDefault(); api('mark_moment',''); }
  else if((ev.metaKey||ev.ctrlKey) && (ev.key==='p'||ev.key==='P')){ ev.preventDefault(); api('pause_meeting'); }
  else if((ev.metaKey||ev.ctrlKey) && ev.key==='Enter'){ ev.preventDefault(); liveStop(); }
  else if((ev.metaKey||ev.ctrlKey) && (ev.key==='k'||ev.key==='K')){ ev.preventDefault(); toggleDictate(); }
});

// ── PostMeetingSummary (31e) ───────────────────────────────────────────────────
let ROW=null;                 // the finished meeting row
let AUDIO_SRC=null, PLAYING_IDX=-1;

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
function renderSummary(){
  document.getElementById('summaryRoot').className = (MODE==='summary') ? 'show' : '';
  if(MODE!=='summary' || !ROW) return;
  document.getElementById('sumEyebrow').textContent='Meeting · '+relDate(ROW.started_at);
  const t=document.getElementById('sumTitle');
  if(document.activeElement!==t) t.value=ROW.title||'';
  const spk=ROW.speakers||{};
  const rec=ROW.recognized||{};
  document.getElementById('sumMeta').innerHTML=
    '<span class="mono">'+fmtT(ROW.duration_seconds)+'</span>'+
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
// ── Meeting Notes page (full AI notes, markdown-rendered) ─────────────────────
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
let NOTES_BUSY=false;
function renderNotesPage(){
  document.getElementById('notesRoot').className = (MODE==='notes') ? 'show' : '';
}
function notesBack(){ MODE='summary'; renderNotesPage(); renderSummary(); }
function openNotes(regen){
  if(!ROW || NOTES_BUSY) return;
  MODE='notes';
  renderPerms(); renderPre(); renderLive(); renderSummary(); renderNotesPage();
  document.getElementById('ntTitle').textContent=(ROW.title||'Meeting')+' — notes';
  const body=document.getElementById('ntBody'), skel=document.getElementById('ntSkel'),
        err=document.getElementById('ntErr');
  err.style.display='none';
  if(ROW.notes_md && !regen){
    body.innerHTML=mdRender(ROW.notes_md); skel.style.display='none';
    return;
  }
  body.innerHTML=''; skel.style.display='flex';
  NOTES_BUSY=true;
  api('get_meeting_notes', ROW.id, !!regen).then(function(r){
    NOTES_BUSY=false;
    skel.style.display='none';
    if(MODE!=='notes') return;
    if(r && r.ok){
      ROW.notes_md=r.notes_md;
      body.innerHTML=mdRender(r.notes_md);
    } else {
      err.textContent=(r&&r.error)||'Could not generate notes — try again.';
      err.style.display='block';
    }
  });
}
function notesCopy(btn){
  if(ROW && ROW.notes_md){ api('copy_text', ROW.notes_md); flashOk(btn); }
}
function hnView(v){
  HNVIEW=v;
  const tabs=document.querySelectorAll('.hnTab');
  for(let i=0;i<tabs.length;i++) tabs[i].className='hnTab'+(tabs[i].dataset.hnv===v?' on':'');
  const l=document.getElementById('hnList'); if(l) l.className='v-'+v;
}
function aiToggle(i){
  const items=ROW&&ROW.action_items||[];
  if(!items[i]) return;
  items[i].done=!items[i].done;
  const r=document.getElementById('aiR'+i);
  if(r){
    r.classList.toggle('done', !!items[i].done);
    const cb=r.querySelector('.aiCb');
    if(cb) cb.setAttribute('aria-checked', items[i].done?'true':'false');
  }
  api('set_action_item_done', ROW.id, i, !!items[i].done);
}
function hnRegen(i){
  const notes=ROW&&ROW.hybrid_notes||[];
  if(!notes[i]) return;
  const btn=document.getElementById('hnR'+i);
  if(btn){ if(btn.classList.contains('busy')) return; btn.classList.add('busy'); }
  api('regenerate_hybrid', ROW.id, i).then(function(r){
    if(btn) btn.classList.remove('busy');
    if(r && r.ok){
      notes[i].ai_addition=r.ai_addition||'';
      renderSummary();
    } else {
      const a=document.getElementById('hnA'+i);
      if(a){ a.style.display=''; a.textContent='Could not regenerate — try again.'; }
    }
  });
}
function aiEdit(i){
  const items=ROW&&ROW.action_items||[];
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
      api('set_action_item_text', ROW.id, i, v);
    }
    renderSummary();
  }
}
function aiDel(i){
  const items=ROW&&ROW.action_items||[];
  if(i<0||i>=items.length) return;
  items.splice(i,1);
  renderSummary();
  api('delete_action_item', ROW.id, i);
}
function toggleBox(id, renderFn){
  const el=document.getElementById(id);
  const show=!el.classList.contains('show');
  el.className='card expandBox'+(show?' show':'');
  if(show){
    renderFn();
    setTimeout(function(){ try{ el.scrollIntoView({behavior:'smooth', block:'start'}); }catch(e){} }, 40);
  }
}
function renderMarksBox(){
  const el=document.getElementById('marksBox');
  const ms=ROW&&ROW.marked_moments||[];
  el.innerHTML='<div class="cardHead"><span class="eyebrow accd">Marked moments</span></div>'+
    (ms.length?ms.map(function(m,i){
      return '<div class="mmRow"><div class="mmHead">'+
        '<span class="star"><svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" stroke="none"><path d="m12 3 2.7 5.6 6.3.9-4.5 4.3 1 6.2-5.5-3-5.5 3 1-6.2L3 9.5l6.3-.9z"/></svg></span>'+
        '<span class="mmTs" onclick="playAt('+m.t+',-1)" title="Play from here">'+fmtT(m.t)+'</span></div>'+
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
  if(!box.classList.contains('show')) toggleBox('txBox', renderTxBox);
  const tx=ROW&&ROW.transcript||[];
  let best=0;
  for(let i=0;i<tx.length;i++){ if((tx[i].t0||0)<=t) best=i; }
  setTimeout(function(){
    const el=document.getElementById('exU'+best);
    if(el){ el.scrollIntoView({behavior:'smooth', block:'center'}); markPlaying(best);
      setTimeout(function(){ markPlaying(-1); }, 2200); }
  }, 120);
}
function mmNote(i){
  const ms=ROW&&ROW.marked_moments||[];
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
      api('set_mark_note', ROW.id, i, v.trim());
    }
    renderMarksBox();
  }
}
function mmDel(i){
  const ms=ROW&&ROW.marked_moments||[];
  if(i<0||i>=ms.length) return;
  ms.splice(i,1);
  renderMarksBox();
  document.getElementById('marksTeaseL').textContent=ms.length+' marked moments';
  api('delete_marked_moment', ROW.id, i);
}
function renderTxBox(){
  const el=document.getElementById('txBox');
  const tx=ROW&&ROW.transcript||[], spk=ROW&&ROW.speakers||{};
  el.innerHTML='<div class="cardHead"><span class="eyebrow">Full transcript</span></div>'+
    (tx.length?tx.map(function(u,i){
      return '<div class="exUtt" id="exU'+i+'" onclick="playAt('+u.t0+','+i+')">'+
        '<span class="schip '+chipClass(u.speaker)+'" title="Double-click to rename" '+
          'ondblclick="event.stopPropagation();sumRename(\''+esc(u.speaker)+'\', this)">'+esc(spk[u.speaker]||u.speaker)+'</span> '+
        '<span class="mono" style="color:var(--dim);font-size:10px">'+fmtT(u.t0)+'</span> '+
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
  const tx=ROW&&ROW.transcript||[];
  if(!tx[i]) return;
  api('copy_text', tx[i].text||'');
  flashOk(btn);
}
function txEdit(i){
  const tx=ROW&&ROW.transcript||[];
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
      api('set_transcript_text', ROW.id, i, v);
    }
    renderTxBox();
  }
}
function playAt(secs, idx){
  // MER-31: expired audio is a clean no-op, not an error — the banner in
  // renderSummary() already told the user why; clicking a transcript line
  // just does nothing rather than surfacing a fetch failure.
  if(ROW && ROW.audio_expired) return;
  const a=document.getElementById('sumAudio');
  function go(){ try{ a.currentTime=Math.max(0,secs); a.play(); markPlaying(idx); }catch(e){} }
  if(AUDIO_SRC){ go(); return; }
  api('get_meeting_audio', ROW.id).then(function(r){
    if(r && r.ok && r.src){ AUDIO_SRC=r.src; a.src=r.src; a.addEventListener('canplay', go, {once:true}); }
  });
}
function markPlaying(idx){
  if(PLAYING_IDX>=0){ const p=document.getElementById('exU'+PLAYING_IDX); if(p) p.className='exUtt'; }
  PLAYING_IDX=idx;
  if(idx>=0){ const el=document.getElementById('exU'+idx); if(el) el.className='exUtt playing'; }
}
function flashOk(btn){
  // clipboard/actions must LOOK like they worked (33f feedback lesson)
  if(!btn || btn.dataset.flash) return;
  btn.dataset.flash='1';
  const orig=btn.innerHTML;
  btn.innerHTML='<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
  btn.style.color='var(--ok)';
  setTimeout(function(){ btn.innerHTML=orig; btn.style.color=''; delete btn.dataset.flash; }, 1400);
}
function sumShare(btn){
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
  if(!ROW) return;
  const btn=document.getElementById(fmt==='txt'?'expTxtBtn':'expMdBtn');
  const orig=btn.textContent;
  btn.textContent='…';
  api('export_meeting', ROW.id, fmt).then(function(r){
    if(r && r.ok){ btn.textContent='Saved ✓'; }
    else if(r && r.cancelled){ btn.textContent=orig; return; }
    else { btn.textContent='Failed'; }
    setTimeout(function(){ btn.textContent=orig; }, 1800);
  });
}
let DEL_ARMED=null;
function sumDelete(){
  if(!ROW) return;
  const btn=document.getElementById('sumDelBtn');
  if(DEL_ARMED!==ROW.id){
    // first click arms; second click within 2.5s deletes
    DEL_ARMED=ROW.id;
    btn.innerHTML='<span style="font:600 10.5px Geist;color:var(--rec-soft);padding:0 4px">Delete?</span>';
    btn.style.width='auto'; btn.style.background='var(--rec-subtle)';
    setTimeout(function(){
      if(DEL_ARMED===ROW.id){ DEL_ARMED=null; resetDelBtn(btn); }
    }, 2500);
    return;
  }
  DEL_ARMED=null;
  btn.innerHTML='<span style="font:600 10.5px Geist;color:var(--rec-soft);padding:0 4px">…</span>';
  api('delete_meeting', ROW.id).then(function(r){
    if(r && r.ok){ api('close_meeting_window'); }
    else { resetDelBtn(btn); }
  });
}
function resetDelBtn(btn){
  btn.innerHTML='<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/><path d="M10 11v6M14 11v6"/></svg>';
  btn.style.width=''; btn.style.background='';
}
function sumRename(sid, el){
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
        if(r && r.ok && r.learned) toast('⚡ Voice print saved for', v);
      });
    }
    renderSummary();
    const tb=document.getElementById('txBox');
    if(tb && tb.classList.contains('show')) renderTxBox();
  }
}
function sumRegen(){
  if(!ROW || ROW.status==='processing') return;   // no double-fire while running
  ROW.status='processing'; renderSummary();
  api('retry_meeting_summary', ROW.id);
}

// ── Python → JS events ─────────────────────────────────────────────────────────
window.VerbalMeeting = function(event, payload){
  try{
    if(event==='layout'){ LAYOUT=payload.layout||'expanded'; applyLayout(); renderBar(); }
    else if(event==='permissions'){ PERMS=payload; renderPerms(); }
    else if(event==='mode'){ MODE=payload.mode||'permissions'; renderPerms(); renderPre(); renderLive(); renderSummary(); renderNotesPage(); }
    else if(event==='openMeeting'){ ROW=payload; renderSummary(); }
    else if(event==='meeting'){
      // Unsolicited broadcasts (a session finishing in the background) must
      // not replace the meeting the user is currently reading.
      if(MODE==='summary' && ROW && payload && payload.id && ROW.id && payload.id!==ROW.id) return;
      ROW=payload; renderSummary();
    }
    else if(event==='testLevel'){ permLevel(payload.level||0); }
    else if(event==='state'){
      if(payload.id && payload.id!==LIVE_ID){
        if(LIVE_ID!==null) resetLive();   // a DIFFERENT meeting took the live panes
        LIVE_ID=payload.id;
      }
      MEET={id:payload.id, state:payload.state, title:payload.title,
            speakers:payload.speakers||MEET.speakers||{}};
      // Only states where audio is actually CAPTURING flip to the live screen.
      // 'stopping'/'processing' are post-capture (summary shows skeletons) — a
      // summary retry re-emits 'processing' and used to hijack the view into a
      // fake "recording" screen.
      if(['recording','paused','preparing'].indexOf(payload.state)>=0 && MODE!=='live'){
        MODE='live'; renderPerms(); renderPre();
      }
      renderLive(); renderBar();
    }
    else if(event==='utterance'){
      if(payload.mid && LIVE_ID && payload.mid!==LIVE_ID) return;  // late event from an old meeting
      if(payload.speakers) MEET.speakers=payload.speakers;
      UTTS.push(payload); UTTS.sort(function(a,b){ return a.t0-b.t0; });
      renderUtts();
    }
    else if(event==='speakers'){ MEET.speakers=payload||{}; renderUtts(); }
    else if(event==='moment'){
      if(payload.mid && LIVE_ID && payload.mid!==LIVE_ID) return;
      MARKS.push(payload); renderUtts(); renderMarks(); momentFeedback(payload); }
    else if(event==='elapsed'){
      const el=document.getElementById('mTimer');
      if(el) el.textContent=fmtT(payload.secs);
      const bt=document.getElementById('barTimer');
      if(bt) bt.textContent=fmtT(payload.secs);
      // waveforms (header + bar): heights track the loudest source, with
      // per-bar phase offsets so it reads as motion between 1 Hz ticks
      const lvl=Math.max(payload.mic||0, payload.sys||0);
      function driveBars(bars, level, base, span){
        for(let i=0;i<bars.length;i++){
          const ph=(Math.sin(Date.now()/300 + i*1.9)+1)/2;
          bars[i].style.height=Math.max(base, Math.round(base + span*level + 3*ph*Math.max(.25,level)))+'px';
        }
      }
      const hw=document.getElementById('hWave');
      if(hw){
        hw.className='hwave'+(payload.paused?' paused':'');
        if(!payload.paused){
          driveBars(document.getElementById('wSys').children, payload.sys||0, 2, 5);
          driveBars(document.getElementById('wMic').children, payload.mic||0, 2, 5);
        }
      }
      const bw=document.getElementById('barWave');
      if(bw && !payload.paused) driveBars(bw.children, lvl, 3, 10);
    }
  }catch(e){ /* meeting UI must never throw into the page */ }
};

// re-check when the window regains focus (user returns from System Settings)
window.addEventListener('focus', function(){ if(MODE==='permissions') loadPerms(); });
loadPerms();
api('meeting_page_ready');   // handshake: flush events emitted before load
</script>"""

    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            + web_font_css() + _CSS + "</style></head><body>"
            + body + js + "</body></html>")

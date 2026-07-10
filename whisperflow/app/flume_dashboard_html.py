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
    "dots":   '<circle cx="5" cy="12" r=".9"/><circle cx="12" cy="12" r=".9"/><circle cx="19" cy="12" r=".9"/>',
}


def _svg(key):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{_IC[key]}</svg>'


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0e1012;--chrome:#0a0c0e;--card:#17191c;--tx:#f2f2f2;--mut:rgba(240,240,240,.55);--sub:rgba(240,240,240,.42);--acc:#C85A3E;--acc-soft:rgba(200,90,62,.14);--acc-bd:rgba(200,90,62,.35);--bd:rgba(240,240,240,.06);--bd2:rgba(240,240,240,.1);--on:#4ad15a}
html,body{height:100%}
body{background:var(--bg);font-family:'Geist',-apple-system,system-ui,sans-serif;color:var(--tx);-webkit-font-smoothing:antialiased;overflow:hidden}
.app{display:grid;grid-template-columns:196px minmax(0,1fr);height:100vh}
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
.siSkip{background:0;border:0;color:var(--mut);cursor:pointer;font:500 13px 'Geist';padding:16px 0;text-align:left;max-width:400px}
.siSkip:hover{color:var(--tx)}
.siTerms{font:400 12px/1.5 'Geist';color:var(--sub);margin-top:8px;max-width:400px}
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
.main{padding:24px 28px;height:100%;overflow-y:auto;overflow-x:hidden}
.screen[hidden]{display:none}
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
.field{margin-bottom:12px}.field label{display:block;font:600 10px 'JetBrains Mono';color:var(--mut);letter-spacing:.08em;margin-bottom:7px}
.field input,.field textarea,.field select{width:100%;background:rgba(240,240,240,.05);border:1px solid var(--bd);border-radius:8px;padding:10px 12px;color:var(--tx);font:400 12.5px 'Geist';outline:0}
.field input:focus,.field textarea:focus,.field select:focus{border-color:var(--acc-bd)}
.field select{-webkit-appearance:none;appearance:none;cursor:pointer;padding-right:34px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23f2f2f2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
.field select option{background:#17191c;color:#f2f2f2}
.saverow{display:flex;align-items:center;gap:12px;margin-top:6px}
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
.nflags .saverow{margin:0 0 12px}.nflags .saverow:last-child{margin-bottom:0}
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
        {_nav("book","Dictionary","dictionary")}
        {_nav("bolt","Snippets","snippets")}
      </nav>
      <div class="navhead devhead">DEVICES<button class="devadd" onclick="show('devices')" title="Pair a device">+</button></div>
      <div class="devlist" id="sideDevices"></div>
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
        <button class="siGoogle" id="siGoogleBtn" onclick="signInGoogle()">{_googleg}<span>Continue with Google</span></button>
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
let PAIR={active:false, token:null, svg:'', ttl:0, claimedBy:null, pollTimer:null, tickTimer:null};
let DICT={vocabulary:[],replacements:[]}, DICT_LOADED=false;
let SNIPS=[], SNIPS_LOADED=false, SNIP_EDIT=null, SNIP_SEARCH='', SNIP_MENU=null, SNIP_SORT=1;
let FT={enabled:false,seen_count:0}, FT_LOADED=false;
let AL={enabled:false}, AL_LOADED=false;
let retryErr='', retryBusy=false;
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const keyText = v => Array.isArray(v) ? v.join('\n') : (v==null?'':String(v));
const words = s => (s||'').trim()? (s||'').trim().split(/\s+/).length : 0;
function tagCls(app){ const a=(app||'').toLowerCase(); if(a.includes('pad')||a.includes('pc')||a.includes('win'))return 'ipad'; if(a.includes('local')||!app)return 'local'; return 'iphone'; }
function titleOf(t){ const w=(t||'').trim().split(/\s+/).slice(0,5).join(' '); return w||'Untitled'; }

function show(id){
  ACTIVE=id;
  document.querySelectorAll('.screen').forEach(s=>s.hidden=(s.id!=='scr-'+id));
  document.querySelectorAll('#wsnav .navitem').forEach(b=>b.classList.toggle('active',b.dataset.screen===id));
  renderActive();
}
function renderActive(){
  try {
    if(ACTIVE==='home') renderHome();
    else if(ACTIVE==='history') renderHistory();
    else if(ACTIVE==='canvas') renderCanvas();
    else if(ACTIVE==='notes') renderNotes();
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
}
function statusPill(){
  const rec = STATE && STATE.recording, proc = STATE && STATE.processing;
  const txt = rec? 'Listening…' : proc? 'Transcribing…' : 'Ready';
  return `<div class="statuspill${rec||proc?' rec':''}"><span class="sdot"></span>${txt}</div>`;
}

function renderHome(){
  if(!STATE) return;
  const h = STATE.history||[];
  const name = (STATE.settings && STATE.settings.sync_device_name) || 'there';
  const rows = h.slice(0,3).map(e=>`
    <div class="lrow"><span class="ltime">${esc(e.ts||'')}</span>
      <span class="ltext">${esc(e.text)}</span>
      <span class="tag ${tagCls(e.app)}">${esc(e.app||'Local')}</span>
      <button class="cbtn" onclick="api('copy_text', ${JSON.stringify(e.text)})">${SVG.copy}</button></div>`).join('')
    || '<div class="empty">Nothing yet — hold your hotkey to record.</div>';
  document.getElementById('homeMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">Welcome back</div><h1 class="title">${esc(name)}</h1></div>${statusPill()}</div>
    <div class="features">
      <div class="fcard cream"><div class="disc">${SVG.mic}</div><div class="fnum">${STATE.daily_words||0}</div><div class="flabel">Words today</div><div class="fsub">${STATE.total_transcriptions||0} all time</div></div>
      <div class="fcard sage"><div class="disc">${SVG.grid}</div><div class="fnum">Canvas</div><div class="flabel">Shared clipboard</div><div class="fsub">${STATE.sync_connected?'Synced':'Local only'}</div></div>
      <div class="fcard plum"><div class="disc">${SVG.lines}</div><div class="fnum">${NOTES.length}</div><div class="flabel">Notes synced</div><div class="fsub">${STATE.total_words||0} words total</div></div>
    </div>
    <div class="sechead"><h2>Recent</h2><span class="link" onclick="show('history')">Open history →</span></div>
    <div class="rows">${rows}</div>`;
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
        <button class="btn primary" style="flex:1.3" ${retryBusy?'disabled':''} onclick="retryRec(${JSON.stringify(sel.id)})">${retryBusy?'Retrying…':'Retry transcription'}</button></div>`;
  }
  else if(EDITH){ prev = `
      <div class="pvhead"><span class="pvmeta">${esc(sel.ts||'')}</span></div>
      <textarea class="transcript histedit" id="histEdit">${esc(sel.text)}</textarea>
      <div class="pvactions"><button class="btn ghost" onclick="EDITH=false;renderHistory()">Cancel</button>
        <button class="btn primary" style="flex:1.3" onclick="saveHistEdit(${JSON.stringify(sel.text)})">${SVG.copy}Save changes</button></div>`;
  } else { prev = `
      <div class="pvhead"><span class="pvmeta">${esc(sel.ts||'')}</span></div>
      <div class="pvtagrow"><span class="tag ${tagCls(sel.app)}">${esc(sel.app||'Local')}</span><span class="pvsub">${words(sel.text)} words</span></div>
      ${audioBar}
      <div class="transcript">${esc(sel.text)}</div>
      <div class="pvactions"><button class="btn ghost" onclick="api('copy_text', ${JSON.stringify(sel.text)})">${SVG.copy}Copy</button>
        <button class="btn ghost" onclick="EDITH=true;renderHistory()">${SVG.edit}Edit</button>
        <button class="btn primary" style="flex:1.3" onclick="api('copy_text', ${JSON.stringify(sel.text)})">${SVG.send}Resend</button></div>`;
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
    <div class="dropzone" onclick="pickCanvasImage()"><div class="dzicon">${SVG.grid}</div><div><div class="dztitle">Type below, or add an image</div><div class="dzsub">Paste an image (⌘V), or click to choose a file · syncs to your devices</div></div></div>
    ${img}
    <textarea class="canvasArea" id="canvasArea" placeholder="Type or paste text here…" oninput="canvasDirty()">${esc(CANVAS.content||'')}</textarea>
    <div class="canvasBar">
      <button class="chipbtn" onclick="saveCanvas()">Save &amp; Sync</button>
      <button class="chipbtn" onclick="pickCanvasImage()">Add image…</button>
      <button class="chipbtn" onclick="pasteCanvasImage()">Paste image</button>
      <button class="chipbtn" onclick="clearCanvas()">Clear</button>${from}</div>
    <div class="cvmsg" id="cvMsg"></div>`;
}
function cvMsg(t){ const el=document.getElementById('cvMsg'); if(el) el.textContent=t||''; }
function canvasText(){ return (document.getElementById('canvasArea')||{}).value||CANVAS.content||''; }
function canvasDirty(){ const a=document.getElementById('canvasArea'); if(a) CANVAS.content=a.value; }
function saveCanvas(){ const v=canvasText(); api('save_canvas', v, CANVAS.image_url||null).then(()=>{ CANVAS.content=v; cvMsg('Saved & synced'); }); }
function loadCanvas(){ api('fetch_canvas').then(r=>{ if(r&&r.ok){ CANVAS={content:r.content||'',image_url:r.image_url||null,from:CANVAS.from}; if(ACTIVE==='canvas')renderCanvas(); } }); }
function clearCanvas(){ api('save_canvas','',null).then(()=>{ CANVAS={content:'',image_url:null}; if(ACTIVE==='canvas')renderCanvas(); }); }
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

let NOTE_REC=false, _noteTimer=null, NOTE_QUERY='', SHOW_ORIG=false, NOTE_SEG_ID=null;
function notePreview(n){ return (n.content||'').replace(/<[^>]*>/g,' ').replace(/&nbsp;/g,' ').replace(/\[( |x|X)\]/g,'').replace(/[*#`>]/g,'').replace(/\s+/g,' ').trim().slice(0,80); }
function curNote(){ return NOTES.find(x=>x.id===SELN) || filteredNotes()[0] || NOTES[0] || null; }
function notesFlag(name){ return !(STATE&&STATE.settings) || STATE.settings[name]!==false; }
function isHtmlContent(s){ return /<(\w|\/)/.test(s||''); }
function noteBodyHtml(n){ const c=n.content||''; if(!c.trim()) return ''; return isHtmlContent(c) ? c : mdToHtml(c); }
function rankNote(n,q){
  if((n.title||'').toLowerCase().includes(q)) return 0;
  if((n.content||'').toLowerCase().includes(q) || (n.raw_content||'').toLowerCase().includes(q)) return 1;
  return 2;
}
function filteredNotes(){
  // Conflict copies are internal; never surface them in the notes list.
  let arr=NOTES.filter(n=>String(n.id||'').indexOf('::conflict::')<0);
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
      <div class="searchbox">${SVG.search}<input id="noteSearch" type="search" aria-label="Search notes" placeholder="Search notes…" value="${esc(NOTE_QUERY)}" oninput="noteSearchInput(this.value)"/></div>
      <div class="notecount" id="noteCount" role="status" aria-live="polite"></div>` : '';
  const editor = n ? noteEditorHtml(n) : '<div class="empty">Select or create a note.</div>';
  document.getElementById('notesMain').innerHTML = `
    <div class="listcol"><div class="mhead"><div><div class="eyebrow">${NOTES.length} notes</div><h1 class="title">Notes</h1></div>
      <button class="roundbtn" aria-label="New note" onclick="newNote()">${SVG.plus}</button></div>
      ${searchBox}
      <div id="noteList"></div></div>
    <div class="editor">${editor}</div>`;
  renderNoteList();
  if(n && !SHOW_ORIG){ const b=document.getElementById('noteBody'); if(b) b.innerHTML=noteBodyHtml(n); updateDictateBtn(); }
  updateSegIcons();
}
// List column only — re-rendered on every keystroke so the search input keeps focus.
function renderNoteList(){
  const flist=filteredNotes();
  const q=(NOTE_QUERY||'').trim();
  const cnt=document.getElementById('noteCount');
  if(cnt) cnt.textContent = q ? (flist.length+' result'+(flist.length===1?'':'s')) : '';
  const listEl=document.getElementById('noteList'); if(!listEl) return;
  if(!flist.length){
    listEl.innerHTML = q
      ? `<div class="empty">No notes match “${esc(q)}”. <span class="link" onclick="clearNoteSearch()">Clear search</span></div>`
      : (NOTES.length ? '<div class="empty">No notes match.</div>'
                      : '<div class="empty">No notes yet — dictate one to get started.</div>');
    return;
  }
  listEl.innerHTML = flist.map(n=>{
    const audio=(n.audio_segments&&n.audio_segments.length)?` <span class="ncaudio" title="Has recording">${SVG.mic}</span>`:'';
    return `<div class="ncard${(SELN===n.id)?' active':''}" onclick="selectNote(${JSON.stringify(n.id)})">
      <div class="nctitle">${esc(n.title||'Untitled')}</div>
      <div class="ncprev">${esc(notePreview(n))||'Empty note'}</div>
      <div class="ncmeta">${esc((n.updated_at||'').slice(0,10))}${audio}</div></div>`;
  }).join('');
}
function noteSearchInput(v){ NOTE_QUERY=v; renderNoteList(); }
function clearNoteSearch(){ NOTE_QUERY=''; const i=document.getElementById('noteSearch'); if(i) i.value=''; renderNoteList(); const j=document.getElementById('noteSearch'); if(j) j.focus(); }

function noteEditorHtml(n){
  const hasRaw = (n.raw_content!=null) && String(n.raw_content).trim()!=='';
  const failed = hasRaw && !String(n.content||'').trim();   // dictated but no formatted content yet
  const origBtn = hasRaw
    ? `<button class="fmtbtn ftxt" title="${SHOW_ORIG?'Show formatted note':'Show original transcript'}" onclick="toggleShowOrig()">${SHOW_ORIG?'Formatted':'Original'}</button>` : '';
  const retryBtn = failed
    ? `<button class="fmtbtn ftxt retry" title="Retry AI formatting" onclick="retryFormatting()">Retry formatting</button>` : '';
  const body = SHOW_ORIG
    ? `<div class="noteorig" id="noteOrig" aria-label="Original transcript">${esc(n.raw_content||'')}</div>`
    : `<div class="notebody" id="noteBody" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Note content" data-ph="Tap Dictate to speak, or start typing…" oninput="noteChanged()"></div>`;
  return `
      <input class="edtitle" id="noteTitle" value="${esc(n.title||'')}" placeholder="Untitled note" aria-label="Note title" oninput="noteChanged()"/>
      ${noteSegBar(n)}
      <div class="notetoolbar">
        <button class="fmtbtn" title="Bold" onmousedown="fmt(event,'bold')"><b>B</b></button>
        <button class="fmtbtn" title="Italic" onmousedown="fmt(event,'italic')"><i>I</i></button>
        <button class="fmtbtn" title="Underline" onmousedown="fmt(event,'underline')"><u>U</u></button>
        <span class="fmtsep"></span>
        <button class="fmtbtn" title="Bullet list" onmousedown="fmt(event,'insertUnorderedList')">&bull;</button>
        <button class="fmtbtn" title="Clean up with AI" onmousedown="event.preventDefault();formatNote()">&#10024;</button>
        ${origBtn}${retryBtn}
        <button class="dictate" id="dictateBtn" onclick="toggleDictate()">${SVG.mic}Dictate</button>
        <span class="notesave" id="noteSaveState"></span>
      </div>
      ${body}
      <div class="pvactions" style="margin-top:12px">
        <button class="btn ghost" style="flex:none;color:#f0b39a" onclick="delNote()">Delete note</button></div>`;
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

function selectNote(id){ flushNoteSave(); stopNoteAudio(); SELN=id; NOTE_REC=false; SHOW_ORIG=false; renderNotes(); }
function newNote(){
  flushNoteSave(); stopNoteAudio(); NOTE_QUERY=''; SHOW_ORIG=false;
  api('save_note', {title:'', content:''}).then(r=>{
    if(r&&r.ok){ NOTES=r.notes||NOTES; SELN=r.id||SELN; renderNotes();
      const b=document.getElementById('noteBody'); if(b) b.focus(); }
  });
}
function toggleShowOrig(){ SHOW_ORIG=!SHOW_ORIG; renderNotes(); }
function fmt(ev, cmd){ ev.preventDefault(); if(SHOW_ORIG) return; const b=document.getElementById('noteBody'); if(b) b.focus(); document.execCommand(cmd,false,null); noteChanged(); }

// Interactive checklist checkbox (Decision 8): toggles the item and persists.
function toggleChk(ev, el){
  ev.preventDefault(); ev.stopPropagation();
  const on = el.getAttribute('data-checked')!=='1';
  el.setAttribute('data-checked', on?'1':'0');
  el.setAttribute('aria-checked', on?'true':'false');
  el.classList.toggle('on', on);
  el.textContent = on?'☑':'☐';
  noteChanged();
}
function chkKey(ev, el){ if(ev.key===' '||ev.key==='Enter'){ toggleChk(ev, el); } }

function noteChanged(){ if(SHOW_ORIG) return; setSaveState('Saving…'); if(_noteTimer) clearTimeout(_noteTimer); _noteTimer=setTimeout(saveCurrentNote, 700); }
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
  const t=card.querySelector('.nctitle'), p=card.querySelector('.ncprev');
  if(t) t.textContent=n.title||'Untitled';
  if(p) p.textContent=notePreview(n)||'Empty note';
}
function delNote(){
  const n=curNote(); if(!n) return;
  if(_noteTimer){ clearTimeout(_noteTimer); _noteTimer=null; }
  stopNoteAudio();
  api('delete_note', n.id).then(r=>{ NOTES=(r&&r.notes)||NOTES.filter(x=>x.id!==n.id); SELN=null; SHOW_ORIG=false; renderNotes(); });
}

function updateDictateBtn(){
  const b=document.getElementById('dictateBtn'); if(!b) return;
  b.className='dictate'+(NOTE_REC?' rec':'');
  b.innerHTML = NOTE_REC ? '<span class="pulse"></span>Stop' : SVG.mic+'Dictate';
}
function toggleDictate(){
  const n=curNote();
  if(NOTE_REC){
    NOTE_REC=false; updateDictateBtn(); setSaveState('Transcribing…');
    api('note_dictate_stop', n?n.id:null).then(r=>{
      if(!(r&&r.ok)){ setSaveState('Mic error'); return; }
      if(!(r.text||'').trim() && !(r.raw_text||'').trim()){
        setSaveState('No speech');
        if(r.segment && n){ n.audio_segments=(n.audio_segments||[]).concat([r.segment]); renderNotes(); }
        return;
      }
      onDictation(r);
    });
  } else {
    api('note_dictate_start').then(r=>{
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
      out.push('<li><span class="chkbox'+(on?' on':'')+'" role="checkbox" aria-checked="'+(on?'true':'false')+'" aria-label="'+lbl+'" tabindex="0" contenteditable="false" data-checked="'+(on?'1':'0')+'" onclick="toggleChk(event,this)" onkeydown="chkKey(event,this)">'+(on?'☑':'☐')+'</span> <span class="chktext">'+inl(m[2])+'</span></li>'); continue; }
    if(m=ln.match(/^\s*[-*]\s+(.*)/)){ if(list!=='ul'){closeList();out.push('<ul>');list='ul';} out.push('<li>'+inl(m[1])+'</li>'); continue; }
    if(m=ln.match(/^\s*\d+\.\s+(.*)/)){ if(list!=='ol'){closeList();out.push('<ol>');list='ol';} out.push('<li>'+inl(m[1])+'</li>'); continue; }
    closeList();
    if(m=ln.match(/^(#{1,6})\s+(.*)/)){ const lv=Math.min(m[1].length,3)+2; out.push('<h'+lv+'>'+inl(m[2])+'</h'+lv+'>'); continue; }
    out.push(ln.trim()===''?'<br>':'<div>'+inl(ln)+'</div>');
  }
  if(inCode) out.push('</pre>'); closeList();
  return out.join('');
}
// Explicit Reformat (the ✨ toolbar button) — Decision 2: re-run cleanup on demand.
function formatNote(){
  if(SHOW_ORIG) return;
  const n=curNote(); const b=document.getElementById('noteBody'); if(!n||!b) return;
  const plain=b.innerText.trim(); if(!plain){ return; }
  setSaveState('Formatting…');
  api('format_note_with_ai', plain).then(r=>{
    if(r&&r.ok&&r.content){
      b.innerHTML=mdToHtml(r.content);
      if(r.title && !String(n.title||'').trim()){ const t=document.getElementById('noteTitle'); if(t) t.value=r.title; }
      noteChanged();
    } else setSaveState((r&&r.error)||'');
  });
}
// Retry formatting after a failed/absent cleanup (Decision 6): re-run over the raw
// transcript, filling in title + formatted content, then persist.
function retryFormatting(){
  const n=curNote(); if(!n || !String(n.raw_content||'').trim()) return;
  setSaveState('Formatting…'); SHOW_ORIG=false;
  api('format_note_with_ai', n.raw_content).then(r=>{
    if(r&&r.ok&&r.content){
      n.content=mdToHtml(r.content);
      if(r.title && !String(n.title||'').trim()) n.title=r.title;
      api('save_note', {id:n.id, title:n.title||'', content:n.content, raw_content:n.raw_content,
                        audio_segments:n.audio_segments||[]}).then(r2=>{
        if(r2&&r2.ok){ if(r2.notes) NOTES=r2.notes; renderNotes(); setSaveState('Saved'); }
        else { renderNotes(); setSaveState(''); }
      });
    } else setSaveState((r&&r.error)||'Format failed');
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

function renderDevices(){
  const devs = (STATE&&STATE.devices)||[];
  const cards = devs.map(d=>`
    <div class="dcard"><div class="dtile">${SVG.phone}</div>
      <div class="dinfo"><div class="dname">${esc(d.device_name||'Device')}</div>
      <div class="dmeta">${esc(d.device_type||'')}${d.last_seen?' · '+esc(String(d.last_seen)):''}</div></div>
      <span class="statpill ${d.online?'on':'offl'}"><span class="pdot"></span>${d.online?'Online':'Offline'}</span></div>`).join('')
    || '<div class="empty">No paired devices yet. Tap “Pair a device”.</div>';
  const pairBtn = PAIR.active ? '' :
    `<button class="btn primary" style="width:150px" onclick="startPairing()">${SVG.plus}Pair a device</button>`;
  const target = (STATE&&STATE.target_device_id)||'__all__';
  const opts = [{id:'__all__',name:'All devices'}].concat(
    devs.map(d=>({id:d.device_id,name:d.device_name||'Device'})));
  const selector = devs.length ? `<div class="tgtwrap">
    <div class="tgtlabel">SEND MY TRANSCRIPTIONS TO</div>
    <div class="tgtpills">${opts.map(o=>`<button class="tgtpill${o.id===target?' on':''}" onclick='setTarget(${JSON.stringify(o.id)})'>${esc(o.name)}</button>`).join('')}</div>
  </div>` : '';
  document.getElementById('devicesMain').innerHTML = `
    <div class="mhead"><div><div class="eyebrow">${devs.length} paired</div><h1 class="title">Paired devices</h1></div>${pairBtn}</div>
    ${pairAreaHTML()}
    ${selector}
    <div class="dcards">${cards}</div>`;
}

function setTarget(id){
  api('set_target_device', id).then(()=>{ if(STATE) STATE.target_device_id=id; renderDevices(); });
}

function clearPairTimers(){
  if(PAIR.pollTimer){ clearInterval(PAIR.pollTimer); PAIR.pollTimer=null; }
  if(PAIR.tickTimer){ clearInterval(PAIR.tickTimer); PAIR.tickTimer=null; }
}
function startPairing(){
  if(PAIR.pollTimer) return;
  PAIR.active=true; PAIR.claimedBy=null; PAIR.svg='';
  if(ACTIVE!=='devices'){ show('devices'); } else { renderDevices(); }
  api('start_pairing').then(r=>{
    if(!r || !r.ok){ PAIR.svg=''; PAIR.active=false; renderDevices(); return; }
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
  PAIR={active:false, token:null, svg:'', ttl:0, claimedBy:null, pollTimer:null, tickTimer:null};
  if(ACTIVE==='devices') renderDevices();
}

function renderSettings(){
  const s = (STATE&&STATE.settings)||{};
  const model = (STATE&&STATE.model)||'base';
  const u = STATE && STATE.user;
  const account = u ? `
    <div class="ssection"><h3>Account</h3>
      <div class="scard" style="flex-direction:row;align-items:center;gap:12px">
        <div class="acctav">${esc((u.name||u.email||'?').slice(0,1).toUpperCase())}</div>
        <div style="flex:1;min-width:0"><div style="font:600 13.5px 'Geist'">${esc(u.name||'Signed in')}</div>
          <div style="font:400 12px 'Geist';color:var(--mut)">${esc(u.email||'')}</div></div>
        <button class="btn ghost" style="flex:none" onclick="api('sign_out_account')">Sign out</button>
      </div></div>` : `
    <div class="ssection"><h3>Account</h3>
      <div class="scard"><div class="ssub" style="margin:0 0 10px">Sign in to sync across your devices.</div>
        <button class="btn primary" style="width:180px" onclick="api('sign_in_google')">Sign in with Google</button></div></div>`;
  document.getElementById('settingsMain').innerHTML = `
    <div class="eyebrow">General</div><h1 class="title">Preferences</h1>
    ${account}
    <div class="ssection"><h3>API keys</h3><p class="ssub">Groq powers transcription; Gemini is a formatting fallback.</p>
      <div class="scard">
        <div class="field"><label>GROQ API KEYS</label><textarea id="groqKeys" rows="2">${esc(keyText(s.groq_api_keys))}</textarea></div>
        <div class="field"><label>GEMINI API KEYS</label><textarea id="gemKeys" rows="2">${esc(keyText(s.gemini_api_keys))}</textarea></div>
        <div class="field"><label>WHISPER MODEL</label><select id="model">${['tiny','base','small','medium'].map(m=>`<option ${model===m?'selected':''}>${m}</option>`).join('')}</select></div>
        <button class="btn primary" style="flex:none;width:130px" onclick="saveSettings()">Save</button>
      </div></div>
    <div class="ssection"><h3>Cross-device sync</h3><p class="ssub">Use the same Account ID on every device to link them.</p>
      <div class="scard">
        <div class="saverow" style="margin-bottom:14px"><button class="toggle ${s.sync_enabled?'on':''}" id="syncToggle" onclick="this.classList.toggle('on')"></button><span style="font:500 13px Geist">Enable sync</span></div>
        <div class="field"><label>ACCOUNT ID</label><input id="userId" value="${esc(s.sync_user_id||'')}"/></div>
        <div class="field"><label>DEVICE NAME</label><input id="devName" value="${esc(s.sync_device_name||'This Mac')}"/></div>
        <button class="btn primary" style="flex:none;width:130px" onclick="saveSettings()">Save sync</button>
      </div></div>
    <div class="ssection"><h3>Custom dictionary</h3><p class="ssub">Teach names &amp; terms so they transcribe correctly, and auto-fix mishearings.</p>
      <div class="scard" style="flex-direction:row;align-items:center;gap:12px">
        <div style="flex:1"><div style="font:600 13.5px 'Geist'">${DICT.vocabulary.length} words · ${DICT.replacements.length} rules</div>
          <div style="font:400 12px 'Geist';color:var(--mut)">Manage your vocabulary and replacement rules</div></div>
        <button class="btn primary" style="flex:none;width:150px" onclick="show('dictionary')">Open dictionary</button>
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
      </div></div>
    <div class="ssection nflags"><h3>Notes features</h3><p class="ssub">Turn individual Notes enhancements on or off. Each is on by default.</p>
      <div class="scard">
        <div class="saverow"><button class="toggle ${s.notes_search_enabled!==false?'on':''}" aria-label="Search across notes" onclick="toggleNoteFlag('notes_search_enabled',this)"></button><span style="font:500 13px Geist">Search across notes</span></div>
        <div class="saverow"><button class="toggle ${s.notes_autotitle_enabled!==false?'on':''}" aria-label="Auto-title dictated notes" onclick="toggleNoteFlag('notes_autotitle_enabled',this)"></button><span style="font:500 13px Geist">Auto-title dictated notes</span></div>
        <div class="saverow"><button class="toggle ${s.notes_structure_detection_enabled!==false?'on':''}" aria-label="Detect lists and checklists" onclick="toggleNoteFlag('notes_structure_detection_enabled',this)"></button><span style="font:500 13px Geist">Detect lists &amp; checklists</span></div>
        <div class="saverow"><button class="toggle ${s.notes_audio_linkage_enabled!==false?'on':''}" aria-label="Link source recordings" onclick="toggleNoteFlag('notes_audio_linkage_enabled',this)"></button><span style="font:500 13px Geist">Link source recordings to notes</span></div>
      </div></div>
    <div class="ssection"><h3>Hotkeys</h3><p class="ssub">Trigger recording from anywhere.</p>
      <div class="scard hotcard">
        <div class="hotrow"><span>Push-to-talk</span><span class="kbs"><kbd>${esc(s.hotkey_hold||'⌥')}</kbd></span></div>
        <div class="hotrow"><span>Toggle recording</span><span class="kbs"><kbd>${esc(s.hotkey_toggle||'⌥')}</kbd></span></div>
      </div></div>`;
  if(!DICT_LOADED){ DICT_LOADED=true; loadDict(); }
  if(!FT_LOADED){ FT_LOADED=true; loadFiletag(); }
  if(!AL_LOADED){ AL_LOADED=true; loadAutolearn(); }
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
function toggleAutolearn(){ AL.enabled=!AL.enabled; document.querySelectorAll('.alToggleBtn').forEach(b=>b.classList.toggle('on',AL.enabled)); api('set_autolearn_enabled', AL.enabled).then(r=>{ if(r&&r.ok){ AL.enabled=!!r.enabled; document.querySelectorAll('.alToggleBtn').forEach(b=>b.classList.toggle('on',AL.enabled)); } }); }
function loadFiletag(){ api('get_filetag_settings').then(r=>{ if(r&&r.ok){ FT={enabled:!!r.enabled,seen_count:r.seen_count||0}; if(ACTIVE==='dictionary'||ACTIVE==='settings') dictReRender(); } }); }
function toggleFiletag(){ FT.enabled=!FT.enabled; document.querySelectorAll('.ftToggleBtn').forEach(b=>b.classList.toggle('on',FT.enabled)); api('set_filetag_enabled', FT.enabled).then(r=>{ if(r&&r.ok){ FT.enabled=!!r.enabled; document.querySelectorAll('.ftToggleBtn').forEach(b=>b.classList.toggle('on',FT.enabled)); } }); }
function dictReRender(){ if(ACTIVE==='dictionary') renderDictionary(); else if(ACTIVE==='settings') renderSettings(); }
function dictSetState(t){ const el=document.getElementById('dictState'); if(el) el.textContent=t||''; }
function loadDict(){ api('get_dictionary').then(r=>{ if(r&&r.ok){ DICT={vocabulary:r.vocabulary||[],replacements:r.replacements||[]}; dictReRender(); } }); }
function saveDict(){ dictSetState('Saving…'); api('save_dictionary', DICT.vocabulary, DICT.replacements).then(r=>{ if(r&&r.ok){ DICT={vocabulary:r.vocabulary||DICT.vocabulary,replacements:r.replacements||DICT.replacements}; dictSetState('Saved'); } else dictSetState(''); }); }
function addWord(){ const el=document.getElementById('dictWord'); if(!el)return; const w=el.value.trim(); if(!w)return; if(!DICT.vocabulary.some(x=>x.toLowerCase()===w.toLowerCase())) DICT.vocabulary.push(w); dictReRender(); saveDict(); setTimeout(()=>{const n=document.getElementById('dictWord'); if(n)n.focus();},0); }
function removeWord(i){ DICT.vocabulary.splice(i,1); dictReRender(); saveDict(); }
function addRep(){ const f=document.getElementById('repFrom'),t=document.getElementById('repTo'); if(!f||!t)return; const frm=f.value.trim(),to=t.value.trim(); if(!frm||!to)return; DICT.replacements=DICT.replacements.filter(r=>r.from.toLowerCase()!==frm.toLowerCase()); DICT.replacements.push({from:frm,to:to}); dictReRender(); saveDict(); setTimeout(()=>{const n=document.getElementById('repFrom'); if(n)n.focus();},0); }
function removeRep(i){ DICT.replacements.splice(i,1); dictReRender(); saveDict(); }

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
    ? `<div class="snmenu"><button onclick="event.stopPropagation();openSnip('${esc(s.id)}')">Edit</button><button class="del" onclick="event.stopPropagation();deleteSnip('${esc(s.id)}')">Delete</button></div>`
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
      ${isNew?'':`<button class="sndel" onclick="deleteSnip('${esc(s.id)}')">Delete</button>`}
      <span class="grow"></span>
      <button class="btn ghost" style="flex:none" onclick="closeSnip()">Cancel</button>
      <button class="btn primary" style="flex:none" onclick="saveSnip()">Save</button>
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
function saveSnip(){
  if(!SNIP_EDIT) return;
  const t=(SNIP_EDIT.trigger||'').trim(), e=(SNIP_EDIT.expansion||'').trim(), l=(SNIP_EDIT.label||'').trim();
  if(!t||!e) return;
  const isNew=!SNIP_EDIT.id;
  const call = isNew
    ? api('add_snippet', {trigger:t, expansion:e, label:l})
    : api('update_snippet', {id:SNIP_EDIT.id, trigger:t, expansion:e, label:l});
  call.then(r=>{ if(r&&r.ok){ SNIPS=r.snippets||SNIPS; SNIP_EDIT=null; renderSnippets(); } });
}
function deleteSnip(id){
  if(!id) return;
  api('delete_snippet', id).then(r=>{ if(r&&r.ok){ SNIPS=r.snippets||SNIPS; if(SNIP_EDIT&&SNIP_EDIT.id===id) SNIP_EDIT=null; SNIP_MENU=null; renderSnippets(); } });
}
function saveSettings(){
  const g=document.getElementById('groqKeys').value.split('\n').map(x=>x.trim()).filter(Boolean);
  const gm=document.getElementById('gemKeys').value.split('\n').map(x=>x.trim()).filter(Boolean);
  api('save_settings', {
    groq_api_keys:g, gemini_api_keys:gm,
    whisper_model:document.getElementById('model').value,
    sync_enabled:document.getElementById('syncToggle').classList.contains('on'),
    sync_user_id:document.getElementById('userId').value,
    sync_device_name:document.getElementById('devName').value,
  }).then(load);
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
  if(si) si.hidden = mode!=='signin';
  if(gs) gs.hidden = mode!=='wizard';
  if(app) app.style.display = mode==='app' ? '' : 'none';
  if(mode==='wizard'){ if(!Object.keys(PERMS).length) loadPerms(); else renderWizard(); }
}
function signInGoogle(){
  const b=document.getElementById('siGoogleBtn');
  if(b){ b.disabled=true; const s=b.querySelector('span'); if(s)s.textContent='Opening browser…'; }
  api('sign_in_google').then(r=>{
    if(!r || r.ok===false){ if(b){ b.disabled=false; const s=b.querySelector('span'); if(s)s.textContent='Continue with Google'; } }
  });
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
    const u=STATE&&STATE.user;
    const right = u ? '<span class="permpill"><span class="pdot"></span>Active</span>'
      : `<button class="btn primary" style="flex:none" onclick="api('sign_in_google')">Sign in</button>`;
    content=`<div class="gstitle">Sync across your devices.</div>
      <div class="gslead">${u?('Signed in as '+esc(u.email)+'. '):''}Your dictation, notes and canvas stay in sync everywhere you sign in.</div>
      <div class="permrow"><div class="permicon ok">${WIZ_ICON.phone}</div><div class="perminfo"><div class="permname">This Mac</div><div class="permsub">${u?'Synced to your account':'Local only — sign in to sync across devices'}</div></div>${right}</div>`;
  } else {
    content=`<div class="gstitle">You're all set.</div>
      <div class="gslead">Hold your hotkey anywhere to dictate — it lands in your clipboard and pastes automatically. Open Flume from the menu bar any time.</div>
      <div class="permrow"><div class="permicon ok">${WIZ_ICON.check}</div><div class="perminfo"><div class="permname">Ready to go</div><div class="permsub">Everything is configured.</div></div></div>`;
  }
  const back = WSTEP>1?`<button class="btn ghost" style="flex:none" onclick="wizBack()">Back</button>`:'';
  el.innerHTML=`<div class="gsstep">STEP ${WSTEP} OF 3</div><div class="gsbar"><i style="width:${pct}%"></i></div>${content}
    <div class="gsnav">${back}<span class="grow"></span><button class="btn primary" style="flex:none;min-width:160px" onclick="wizNext()">${WSTEP<3?'Continue':'Start using Flume'}</button></div>`;
}

async function load(){
  const r = await api('get_state');
  if(r && r.ok){ STATE=r; applyAuthGate(); renderSidebar(); }
  await new Promise(res=>{ api('fetch_notes').then(rn=>{ if(rn&&rn.ok)NOTES=rn.notes||rn.data||[]; res(); }); });
  loadCanvas();
  renderActive();
}
document.querySelectorAll('[data-screen]').forEach(n=>n.onclick=()=>show(n.dataset.screen));
window.addEventListener('pywebviewready', load);
setTimeout(()=>{ if(!STATE) load(); }, 400);
</script>"""

    # Inline the icon SVGs into a JS map the render functions reference as SVG.<name>
    svg_map = "<script>const SVG={" + ",".join(
        f'{k}:{_json_str(_svg(k))}' for k in _IC
    ) + "};</script>"

    # Strip the leftover placeholder line from the JS.
    js = js.replace("const IC. = {}; // placeholder\n", "")

    return f"<style>{web_font_css()}{_CSS}</style>{svg_map}{body}{js}"


def _json_str(s: str) -> str:
    import json
    return json.dumps(s)

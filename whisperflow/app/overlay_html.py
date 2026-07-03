"""
HTML for the Flume recording overlay (macOS) — the floating pill that shows
Recording → Transcribing → Done. Hosted in a transparent WKWebView panel
(see overlay.py). Reuses the Geist / JetBrains Mono fonts registered by theme.

States are driven from Python via window.VerbalOverlay(mode, data):
  mode 'recording'  data {device}
  mode 'transcribing' data {src, dst, secs}
  mode 'done'       data {label, meta}   e.g. label "Pasted to MacBook", meta "38W · 14S"
Button clicks call window.pywebview.api.<action>() (overlay_stop / _cancel /
_pause / _copy / _dismiss).
"""

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--tx:#f2f2f2;--mut:rgba(240,240,240,.5);--acc:#E8522A;--green:#4ad15a;
--pill:rgba(22,20,18,.96);--bd:rgba(240,240,240,.09)}
html,body{height:100%;background:transparent}
body{font-family:'Geist',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
display:flex;flex-direction:column;align-items:center;justify-content:flex-end;overflow:hidden;padding-bottom:5px}
.statelabel{font:600 9px 'JetBrains Mono';letter-spacing:.24em;color:var(--mut);margin-bottom:9px;text-transform:uppercase}
.pill{display:none;align-items:center;gap:10px;background:var(--pill);border:1px solid var(--bd);
border-radius:22px;padding:7px 8px 7px 14px;box-shadow:0 10px 32px rgba(0,0,0,.5);white-space:nowrap}
.pill.on{display:flex;animation:pillIn .24s cubic-bezier(.2,.8,.2,1)}
@keyframes pillIn{from{opacity:0;transform:translateY(10px) scale(.95)}to{opacity:1;transform:none}}
.statelabel{animation:pillIn .24s cubic-bezier(.2,.8,.2,1)}
.vbar{width:1px;height:17px;background:rgba(240,240,240,.14);flex:none}
/* recording */
.pill.rec{border-color:rgba(232,82,42,.5)}
.mute{width:20px;height:20px;border-radius:50%;border:1.5px solid var(--acc);background:transparent;color:var(--acc);
display:flex;align-items:center;justify-content:center;font:600 12px 'Geist';line-height:1;flex:none}
.timer{font:600 13px 'JetBrains Mono';color:var(--tx);letter-spacing:.02em;font-variant-numeric:tabular-nums}
.wave{display:flex;align-items:center;gap:2px;height:18px}
.wave i{width:2px;border-radius:2px;background:rgba(240,240,240,.85);animation:wv .9s ease-in-out infinite}
@keyframes wv{0%,100%{height:4px}50%{height:15px}}
.dev{font:600 10.5px 'JetBrains Mono';letter-spacing:.07em;color:var(--mut);text-transform:uppercase}
.ctrl{width:26px;height:26px;border-radius:50%;border:0;background:rgba(240,240,240,.08);color:var(--tx);
cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
.ctrl:hover{background:rgba(240,240,240,.14)}
.ctrl svg{width:12px;height:12px}
.stop{width:26px;height:26px;border-radius:50%;border:0;background:var(--acc);cursor:pointer;
display:flex;align-items:center;justify-content:center;flex:none}
.stop:hover{filter:brightness(1.08)}
.stop .sq{width:9px;height:9px;border-radius:2px;background:#fff}
/* transcribing */
.spinner{width:16px;height:16px;border-radius:50%;border:2px solid rgba(232,82,42,.25);
border-top-color:var(--acc);animation:spin .8s linear infinite;flex:none}
@keyframes spin{to{transform:rotate(360deg)}}
.tlabel{font:600 12px 'Geist';color:var(--tx)}
/* done */
.pill.done{border-color:rgba(74,209,90,.55)}
.check{width:19px;height:19px;border-radius:50%;background:rgba(74,209,90,.16);color:var(--green);
display:flex;align-items:center;justify-content:center;font:600 11px 'Geist';flex:none}
.dlabel{font:600 12px 'Geist';color:var(--tx)}
.dmeta{font:600 10.5px 'JetBrains Mono';color:var(--mut);letter-spacing:.03em}
.cta{background:rgba(240,240,240,.08);border:0;border-radius:13px;padding:6px 11px;color:var(--tx);
cursor:pointer;font:600 12px 'Geist';flex:none}
.cta:hover{background:rgba(240,240,240,.14)}
"""

# X icon reused by the control buttons
_X = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
      'stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>')
_PAUSE = ('<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" height="14" rx="1"/>'
          '<rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>')


def _js():
    return """
let timerId=null, t0=0;
const $=s=>document.querySelector(s);
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function api(m){ try{ return window.pywebview.api[m](); }catch(e){} }
function two(n){ return (n<10?'0':'')+n; }
function fmt(sec){ const m=Math.floor(sec/60), s=sec%60; return two(m)+':'+two(s); }

function stopTimer(){ if(timerId){ clearInterval(timerId); timerId=null; } }
function startTimer(){
  stopTimer(); t0=0; $('#timer').textContent='00:00';
  timerId=setInterval(()=>{ t0++; $('#timer').textContent=fmt(t0); }, 1000);
}

function showPill(id){
  ['pill-rec','pill-trans','pill-done'].forEach(p=>{
    const el=document.getElementById(p); if(el) el.classList.toggle('on', p===id);
  });
}

window.VerbalOverlay = function(mode, data){
  data = data || {};
  if(mode==='recording'){
    $('#stateLabel').textContent='Recording';
    $('#recDev').textContent = esc(data.device || 'MAC');
    showPill('pill-rec'); startTimer();
  } else if(mode==='transcribing'){
    stopTimer();
    $('#stateLabel').textContent='Transcribing';
    $('#transRoute').textContent = esc(((data.src||'MAC')+' → '+(data.dst||'MAC')));
    $('#transLabel').textContent = 'Transcribing '+((data.secs!=null?data.secs:0)+'s');
    showPill('pill-trans');
  } else if(mode==='done'){
    stopTimer();
    $('#stateLabel').textContent='Done';
    $('#doneLabel').textContent = esc(data.label || 'Pasted');
    $('#doneMeta').textContent = esc(data.meta || '');
    showPill('pill-done');
  } else { // hide
    stopTimer(); showPill('');
  }
};
"""


def overlay_html():
    bars = "".join(
        '<i style="animation-delay:%.2fs"></i>' % (i * 0.08) for i in range(13)
    )
    body = """
    <div class="statelabel" id="stateLabel">Recording</div>
    <div class="pill rec" id="pill-rec">
      <div class="mute">&#8722;</div>
      <span class="timer" id="timer">00:00</span>
      <span class="vbar"></span>
      <div class="wave">{bars}</div>
      <span class="dev" id="recDev">MAC</span>
      <button class="ctrl" title="Pause" onclick="api('overlay_pause')">{pause}</button>
      <button class="ctrl" title="Cancel" onclick="api('overlay_cancel')">{x}</button>
      <button class="stop" title="Stop" onclick="api('overlay_stop')"><span class="sq"></span></button>
    </div>
    <div class="pill trans" id="pill-trans">
      <span class="spinner"></span>
      <span class="tlabel" id="transLabel">Transcribing 0s</span>
      <span class="vbar"></span>
      <span class="dev" id="transRoute">MAC</span>
      <button class="ctrl" title="Cancel" onclick="api('overlay_cancel')">{x}</button>
    </div>
    <div class="pill done" id="pill-done">
      <span class="check">&#10003;</span>
      <span class="dlabel" id="doneLabel">Pasted</span>
      <span class="vbar"></span>
      <span class="dmeta" id="doneMeta">38W &middot; 14S</span>
      <button class="cta" onclick="api('overlay_copy')">Copy again</button>
      <button class="ctrl" title="Dismiss" onclick="api('overlay_dismiss')">{x}</button>
    </div>
    """.format(bars=bars, pause=_PAUSE, x=_X)
    from app.fonts_css import web_font_css
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + "</style></head><body>"
        + body +
        "<script>" + _js() + "</script>"
        "</body></html>"
    )

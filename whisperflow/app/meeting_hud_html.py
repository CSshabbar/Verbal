r"""
Meetings — HTML for the floating meeting HUD (MEETINGS_DESIGN_HANDOFF.md 31d).

Rendered into the non-activating panel hosted by meeting_hud.MeetingHud.
Python → JS via window.VerbalMeetingHud(event, payload):
  'state'   {state, title}                — recording | paused | stopping | hidden
  'elapsed' {secs, paused, mic, sys}      — 1 Hz tick with levels for the bars
Buttons post back through the pywebview bridge (hud_star / hud_pause / hud_return).

JS convention: raw string, single backslashes (05-conventions.md Rule #2).
Fonts inlined via fonts_css.web_font_css() (Rule #7).
"""
from app.fonts_css import web_font_css

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:transparent;overflow:hidden}
body{font-family:'Geist',-apple-system,sans-serif;-webkit-font-smoothing:antialiased;
  display:flex;align-items:flex-end;justify-content:flex-start;padding:14px}
#hud{display:none;align-items:center;gap:8px;padding:7px 12px;border-radius:999px;
  background:rgba(14,16,18,.9);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
  border:1px solid rgba(240,240,240,.08);box-shadow:0 10px 30px rgba(0,0,0,.45);
  color:#f2f2f2;max-width:100%}
#hud.show{display:flex}
#hud.expanded{border-radius:12px}
.dot{width:8px;height:8px;border-radius:50%;background:#E05049;flex:none;
  animation:hpulse 1.4s ease-in-out infinite}
#hud.paused .dot{background:rgba(240,240,240,.35);animation:none}
@keyframes hpulse{0%,100%{opacity:1}50%{opacity:.25}}
.timer{font:500 11px 'JetBrains Mono';color:#f2f2f2;flex:none}
#hud.paused .timer{color:rgba(240,240,240,.6)}
.wave{display:flex;align-items:center;gap:2px;height:14px;flex:none}
.wave i{width:2px;border-radius:2px;background:rgba(240,240,240,.85);height:3px;
  transition:height .12s ease}
#hud.paused .wave{opacity:.4}
.title{font:400 11px 'Geist';color:rgba(240,240,240,.55);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:150px}
.pausedTag{display:none;font:500 9px 'JetBrains Mono';letter-spacing:.14em;
  color:rgba(240,240,240,.55)}
#hud.paused .pausedTag{display:inline}
.acts{display:none;gap:5px;flex:none}
#hud.expanded .acts{display:flex}
.hbtn{width:22px;height:22px;border-radius:7px;border:0;cursor:pointer;
  background:rgba(240,240,240,.08);color:#f2f2f2;display:flex;align-items:center;
  justify-content:center;padding:0}
.hbtn:hover{background:rgba(240,240,240,.16)}
.hbtn.accent{background:rgba(200,90,62,.2);color:#f0b39a}
.hbtn.resume{background:#C85A3E;color:#fff5ea;border-radius:999px}
.hbtn svg{width:11px;height:11px}
"""

_STAR = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="m12 3 2.7 5.6 6.3.9-4.5 '
         '4.3 1 6.2-5.5-3-5.5 3 1-6.2L3 9.5l6.3-.9z"/></svg>')
_PAUSE = ('<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" '
          'height="14" rx="1"/><rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>')
_PLAY = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>'
_RETURN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
           'stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6"/>'
           '<path d="M20 4 11 13"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 '
           '0 1 1-1h6"/></svg>')


def meeting_hud_html() -> str:
    body = f"""
  <div id="hud">
    <span class="dot"></span>
    <span class="timer mono" id="hTimer">0:00</span>
    <span class="wave" id="hWave"><i></i><i></i><i></i><i></i><i></i></span>
    <span class="title" id="hTitle"></span>
    <span class="pausedTag">PAUSED</span>
    <span class="acts">
      <button class="hbtn accent" title="Mark moment" onclick="api('hud_star')">{_STAR}</button>
      <button class="hbtn" id="hPause" title="Pause / resume" onclick="api('hud_pause')">{_PAUSE}</button>
      <button class="hbtn" title="Return to meeting" onclick="api('hud_return')">{_RETURN}</button>
    </span>
  </div>"""

    js = r"""
<script>
function api(name){ const a=[].slice.call(arguments,1);
  return (window.pywebview && window.pywebview.api && window.pywebview.api[name])
    ? window.pywebview.api[name].apply(null,a) : Promise.resolve({ok:false}); }
const PAUSE_SVG = document.getElementById('hPause') ? document.getElementById('hPause').innerHTML : '';
const PLAY_SVG = '""" + _PLAY.replace("'", "\\'") + r"""';
let HOVER_T=null;
function fmtT(secs){
  secs=Math.max(0,Math.floor(secs||0));
  const h=Math.floor(secs/3600), m=Math.floor((secs%3600)/60), s=secs%60;
  const mm=(h? String(m).padStart(2,'0') : String(m)), ss=String(s).padStart(2,'0');
  return h? (h+':'+mm+':'+ss) : (mm+':'+ss);
}
const hud=document.getElementById('hud');
hud.addEventListener('mouseenter', function(){
  clearTimeout(HOVER_T);
  HOVER_T=setTimeout(function(){ hud.classList.add('expanded'); }, 120);
});
hud.addEventListener('mouseleave', function(){
  clearTimeout(HOVER_T);
  HOVER_T=setTimeout(function(){ hud.classList.remove('expanded'); }, 400);
});
window.VerbalMeetingHud = function(event, payload){
  try{
    if(event==='state'){
      if(payload.state==='hidden'){ hud.className=''; return; }
      hud.className='show'+(payload.state==='paused'?' paused':'')+(hud.classList.contains('expanded')?' expanded':'');
      document.getElementById('hTitle').textContent=payload.title||'';
      const pb=document.getElementById('hPause');
      if(pb) pb.innerHTML = (payload.state==='paused') ? PLAY_SVG : PAUSE_SVG;
      if(payload.state==='paused') pb.className='hbtn resume'; else pb.className='hbtn';
    }
    else if(event==='elapsed'){
      document.getElementById('hTimer').textContent=fmtT(payload.secs);
      const lvl=Math.max(payload.mic||0, payload.sys||0);
      const bars=document.querySelectorAll('#hWave i');
      bars.forEach(function(b,i){
        const jitter=(Math.sin(Date.now()/180 + i*1.7)+1)/2;   // organic motion
        const h=payload.paused?3:Math.max(3, Math.round(3 + (10*lvl + 4*jitter)));
        b.style.height=h+'px';
      });
    }
  }catch(e){}
};
</script>"""

    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            + web_font_css() + _CSS + "</style></head><body>"
            + body + js + "</body></html>")

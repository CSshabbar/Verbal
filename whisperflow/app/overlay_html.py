"""
HTML for the Flume recording overlay (macOS) — the floating pill that shows
Recording → Transcribing → Done. Hosted in a transparent WKWebView panel
(see overlay.py). Reuses the Geist / JetBrains Mono fonts registered by theme.

States are driven from Python via window.VerbalOverlay(mode, data):
  mode 'recording'  data {device}
  mode 'transcribing' data {src, dst, secs}
  mode 'done'       data {label, meta}   e.g. label "Pasted to MacBook", meta "38W · 14S"
  mode 'error'      data {label, state}  e.g. label "No speech detected"
  mode 'paused'     data {paused}        flips the pause icon + freezes the timer
Button clicks call window.pywebview.api.<action>() (overlay_stop / _cancel /
_pause / _copy / _dismiss). The page announces itself with `overlay_ready` so
emits made before the WKWebView finished loading are flushed, not dropped.
"""

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--tx:#f2f2f2;--mut:rgba(240,240,240,.5);--acc:#C85A3E;--green:#4ad15a;
--err:#E05049;--errtx:#f0a5a0;
--pill:rgba(22,20,18,.96);--bd:rgba(240,240,240,.09)}
html,body{height:100%;background:transparent}
body{font-family:'Geist',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
display:flex;flex-direction:column;align-items:center;justify-content:flex-end;overflow:visible;
padding:12px 20px 40px}
/* ── Capsule (IDI-184) ──────────────────────────────────────────────────────
   At rest the pill carries only what is LIVE — the waveform and the clock —
   and grows on hover to the full control bar. What went away entirely:
     * the RECORDING caption above the pill (the terracotta border + a moving
       waveform already say it, so it was a second indicator for one state),
     * the "mute" disc, which was decorative — nothing in the app ever set it,
     * the device tag while recording (the Done state already names the target,
       "Pasted to MacBook", which is when that fact is actually news).
   Hover reveals pause / cancel / stop; `.peek` forces the same expanded state
   for screenshots and tests, since :hover can't be driven from script. */
.pill{display:none;align-items:center;gap:9px;background:var(--pill);border:1px solid var(--bd);
border-radius:20px;padding:6px 12px;box-shadow:0 10px 32px rgba(0,0,0,.5);white-space:nowrap;
transition:gap .2s cubic-bezier(.2,.8,.2,1)}
.pill.on{display:flex;animation:pillIn .24s cubic-bezier(.2,.8,.2,1)}
@keyframes pillIn{from{opacity:0;transform:translateY(10px) scale(.95)}to{opacity:1;transform:none}}
.vbar{width:1px;height:15px;background:rgba(240,240,240,.14);flex:none}
/* the collapsed cluster: zero width until hover, and clipped so nothing of it
   shows through in the resting state */
.opt{display:flex;align-items:center;gap:9px;max-width:0;opacity:0;overflow:hidden;
transition:max-width .22s cubic-bezier(.2,.8,.2,1),opacity .16s linear}
.pill:hover>.opt,.pill.peek>.opt,.pill.rec.paused>.opt{max-width:130px;opacity:1}
.pill.rec.paused .wave{opacity:.35}
.pill.rec.paused{border-color:rgba(240,240,240,.22)}
/* recording */
.pill.rec{border-color:rgba(200,90,62,.5)}
.timer{font:600 12px 'JetBrains Mono';color:var(--tx);letter-spacing:.02em;font-variant-numeric:tabular-nums}
.wave{display:flex;align-items:center;gap:2px;height:18px}
/* Bar heights are driven from the real mic level (window.VerbalWave). The
   keyframe animation is only the FALLBACK, applied while `.idle` is on —
   i.e. before the first level arrives or if the pushes ever stop. */
.wave i{width:2px;height:3px;border-radius:2px;background:rgba(240,240,240,.85);
transition:height .07s linear}
.wave.idle i{animation:wv .9s ease-in-out infinite}
@keyframes wv{0%,100%{height:4px}50%{height:15px}}
.ctrl{width:22px;height:22px;border-radius:50%;border:0;background:rgba(240,240,240,.08);color:var(--tx);
cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none;padding:0}
.ctrl:hover{background:rgba(240,240,240,.14)}
.ctrl svg{width:11px;height:11px}
.ctrl span{display:flex;align-items:center;justify-content:center}
.stop{width:22px;height:22px;border-radius:50%;border:0;background:var(--acc);cursor:pointer;
display:flex;align-items:center;justify-content:center;flex:none;padding:0}
.stop:hover{filter:brightness(1.08)}
.stop .sq{width:8px;height:8px;border-radius:2px;background:#fff}
/* transcribing */
/* The ring is rotated from Python (window.VerbalSpin) — a pure CSS animation
   sits perfectly still in this panel, see 05-conventions Rule #41. `.idle` is
   the fail-open fallback: it carries the keyframes and is re-applied whenever
   ticks stop arriving, exactly like `.wave.idle`. An inline transform cannot
   override a RUNNING animation, so the two must never both be active. */
.spinner{width:16px;height:16px;border-radius:50%;border:2px solid rgba(200,90,62,.25);
border-top-color:var(--acc);flex:none}
.spinner.idle{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.tlabel{font:600 12px 'Geist';color:var(--tx)}
/* done */
.pill.done{border-color:rgba(74,209,90,.55)}
.check{width:17px;height:17px;border-radius:50%;background:rgba(74,209,90,.16);color:var(--green);
display:flex;align-items:center;justify-content:center;font:600 10px 'Geist';flex:none}
.dlabel{font:600 12px 'Geist';color:var(--tx);max-width:170px;min-width:0;
overflow:hidden;text-overflow:ellipsis}
.dmeta{font:600 10.5px 'JetBrains Mono';color:var(--mut);letter-spacing:.03em}
.cta{background:rgba(240,240,240,.08);border:0;border-radius:11px;padding:4px 9px;color:var(--tx);
cursor:pointer;font:600 11.5px 'Geist';flex:none}
.cta:hover{background:rgba(240,240,240,.14)}
/* error — NO checkmark and NO "Copy again" (it would re-copy stale text).
   Uses the approved danger red #E05049, never the terracotta accent. */
.pill.err{border-color:rgba(224,80,73,.38)}
.bang{width:19px;height:19px;border-radius:50%;background:rgba(224,80,73,.16);color:var(--errtx);
display:flex;align-items:center;justify-content:center;font:700 12px 'Geist';line-height:1;flex:none}
.elabel{font:600 12px 'Geist';color:var(--errtx)}
"""

# X icon reused by the control buttons
_X = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
      'stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>')
_PAUSE = ('<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5" width="3.4" height="14" rx="1"/>'
          '<rect x="13.6" y="5" width="3.4" height="14" rx="1"/></svg>')
# Resume glyph — swapped in for _PAUSE while the recorder is paused. Both live in
# the DOM and are toggled by display, so the JS never has to embed SVG markup
# (keeps the JS free of backslashes inside this non-raw Python string).
_PLAY = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l11 7-11 7z"/></svg>'


def _js():
    return """
let timerId=null, t0=0, paused=false;
const $=s=>document.querySelector(s);
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function api(m){ try{ return window.pywebview.api[m](); }catch(e){} }
function two(n){ return (n<10?'0':'')+n; }
function fmt(sec){ const m=Math.floor(sec/60), s=sec%60; return two(m)+':'+two(s); }

function tick(){ t0++; const el=$('#timer'); if(el) el.textContent=fmt(t0); }
function stopTimer(){ if(timerId){ clearInterval(timerId); timerId=null; } }
function startTimer(){
  stopTimer(); t0=0; paused=false; paintPause();
  const el=$('#timer'); if(el) el.textContent='00:00';
  timerId=setInterval(tick, 1000);
}

// Pause must FREEZE the elapsed clock — audio stops accruing, so a ticking
// timer drifts away from the real recording length.
function paintPause(){
  const a=$('#icoPause'), b=$('#icoPlay'), btn=$('#pauseBtn');
  if(a) a.style.display = paused ? 'none' : 'flex';
  if(b) b.style.display = paused ? 'flex' : 'none';
  if(btn) btn.title = paused ? 'Resume' : 'Pause';
}
function setPaused(p){
  paused = !!p; paintPause();
  // No state caption any more, so paused has to read from the pill itself:
  // hold the control cluster open (the resume button must be reachable without
  // hunting for it) and dim the bars. The frozen clock does the rest.
  const pill=$('#pill-rec');
  if(pill) pill.classList.toggle('paused', paused);
  if(paused){ stopTimer(); }
  else if(!timerId){ timerId=setInterval(tick, 1000); }
}

// ── live waveform ──────────────────────────────────────────────────────────
// Python pushes the recorder's smoothed 0..1 mic level into VerbalWave ~15x/s.
// This loop keeps its own 30fps scroll so the bars stay smooth BETWEEN pushes:
// the newest sample enters at the right and the history walks left, which is
// what makes it read as audio rather than as a looping animation.
// Fail-open: if no level arrives for ~0.9s (older build, a failed eval, the
// main thread stalling) the bars drop back to the ambient CSS animation.
const WN=11, WMIN=3, WMAX=17;
let wHist=[], wTarget=0, wNow=0, wLast=0, wRaf=null, wStep=0, wIdle=true;

function waveEl(){ return $('#wave'); }
function waveIdle(on){
  const w=waveEl(); if(!w || wIdle===on) return;
  wIdle=on; w.classList.toggle('idle', on);
  // Clear the inline heights we set, so the keyframes own the bars again.
  if(on){ for(const b of w.children) b.style.height=''; }
}
function waveStart(){
  wHist=new Array(WN).fill(0); wTarget=0; wNow=0; wLast=0; wStep=0;
  wIdle=false; waveIdle(true);
  if(!wRaf) wRaf=requestAnimationFrame(waveFrame);
}
function waveStop(){
  if(wRaf){ cancelAnimationFrame(wRaf); wRaf=null; }
  waveIdle(true);
}
window.VerbalWave = function(lvl){
  lvl=+lvl; if(!(lvl>=0)) lvl=0; if(lvl>1) lvl=1;
  wTarget=lvl; wLast=Date.now();
};
function waveFrame(){
  wRaf=requestAnimationFrame(waveFrame);
  const w=waveEl(); if(!w) return;
  const now=Date.now();
  if(!wLast || now-wLast>900){ waveIdle(true); return; }
  waveIdle(false);
  // Same attack/release feel as the meter itself: snap up, ease down.
  wNow += (wTarget-wNow) * (wTarget>wNow ? 0.5 : 0.18);
  if(now-wStep>=55){ wStep=now; wHist.push(wNow); wHist.shift(); }
  const bars=w.children;
  for(let i=0;i<bars.length && i<WN;i++){
    const v=wHist[i]||0;
    // A touch of shimmer, scaled by level, so a steady tone still breathes
    // and silence stays perfectly flat.
    const j=1+0.12*Math.sin(now/140+i*1.7)*Math.min(1,v*3);
    const h=WMIN+(WMAX-WMIN)*Math.min(1,v*j);
    bars[i].style.height=Math.round(h)+'px';
  }
}

// ── transcribing spinner ───────────────────────────────────────────────────
// Python pushes an absolute angle ~20x/s (overlay.py::_start_spin_pump). A
// JS-driven style change forces a repaint, which a background WKWebView's
// throttled animation timeline does not.
// A NEGATIVE angle means "release": hand the ring back to the CSS keyframes.
// Python sends it when the pump stops. This deliberately does NOT use a JS
// timeout watchdog like the waveform's — setInterval is throttled in this
// webview too (measured), so a timer-based fallback is exactly as unreliable as
// the animation it was meant to rescue. Python owns the lifecycle instead.
window.VerbalSpin = function(deg){
  const el=$('#spinner'); if(!el) return;
  if(deg < 0){ el.classList.add('idle'); el.style.transform=''; return; }
  el.classList.remove('idle');
  el.style.transform='rotate('+deg+'deg)';
};
function spinWatch(on){
  // Reset to the keyframe fallback; ticks (if they come) take over on arrival.
  const el=$('#spinner');
  if(el){ el.classList.add('idle'); el.style.transform=''; }
}

function showPill(id){
  ['pill-rec','pill-trans','pill-done','pill-err'].forEach(p=>{
    const el=document.getElementById(p); if(el){
      el.classList.toggle('on', p===id);
      // a stale reveal must not carry across a state change
      if(p!==id) el.classList.remove('peek');
    }
  });
}

// Hover → expand, driven from Python (overlay.py::_on_global_mouse) rather than
// from CSS :hover. macOS only delivers mouseMoved to the ACTIVE app, and this
// panel always belongs to a background one while you dictate, so :hover alone
// left the capsule collapsed until it was clicked. x<0 means "cursor left".
// A couple of px of slop makes the edge forgiving without being sticky.
window.VerbalHover = function(x, y){
  const p = document.querySelector('.pill.on');
  if(!p) return;
  let on = false;
  if(x >= 0){
    const r = p.getBoundingClientRect();
    on = x >= r.left - 3 && x <= r.right + 3 && y >= r.top - 3 && y <= r.bottom + 3;
  }
  p.classList.toggle('peek', on);
};

window.VerbalOverlay = function(mode, data){
  data = data || {};
  if(mode==='recording'){
    // `data.device` is no longer rendered here — the Done state names the
    // target, which is when it matters. Kept in the payload for Windows.
    spinWatch(false);
    showPill('pill-rec'); startTimer(); waveStart();
  } else if(mode==='paused'){
    setPaused(data.paused);
  } else if(mode==='transcribing'){
    stopTimer(); waveStop();
    $('#transLabel').textContent = 'Transcribing '+((data.secs!=null?data.secs:0)+'s');
    showPill('pill-trans'); spinWatch(true);
  } else if(mode==='done'){
    stopTimer(); waveStop();
    spinWatch(false);
    $('#doneLabel').textContent = esc(data.label || 'Pasted');
    $('#doneMeta').textContent = esc(data.meta || '');
    showPill('pill-done');
  } else if(mode==='error'){
    stopTimer(); waveStop();
    spinWatch(false);
    $('#errLabel').textContent = esc(data.label || 'Something went wrong');
    showPill('pill-err');
  } else { // hide
    stopTimer(); waveStop(); spinWatch(false); showPill('');
  }
};

// Ready handshake — emits made before this script ran were buffered in Python.
api('overlay_ready');
"""


def overlay_html():
    # 11 bars — the ambient (`.wave.idle`) animation staggers them; the live
    # waveform overwrites their heights from the mic level. Keep the count in
    # sync with WN in the JS. (13 in the pre-Capsule bar; the narrower resting
    # capsule carries 11.)
    bars = "".join(
        '<i style="animation-delay:%.2fs"></i>' % (i * 0.08) for i in range(11)
    )
    body = """
    <div class="pill rec" id="pill-rec">
      <div class="wave idle" id="wave">{bars}</div>
      <span class="timer" id="timer">00:00</span>
      <span class="opt">
        <span class="vbar"></span>
        <button class="ctrl" id="pauseBtn" title="Pause" onclick="api('overlay_pause')"><span
          id="icoPause">{pause}</span><span id="icoPlay" style="display:none">{play}</span></button>
        <button class="ctrl" title="Cancel" onclick="api('overlay_cancel')">{x}</button>
        <button class="stop" title="Stop" onclick="api('overlay_stop')"><span class="sq"></span></button>
      </span>
    </div>
    <div class="pill trans" id="pill-trans">
      <span class="spinner idle" id="spinner"></span>
      <span class="tlabel" id="transLabel">Transcribing 0s</span>
      <span class="opt">
        <span class="vbar"></span>
        <button class="ctrl" title="Cancel" onclick="api('overlay_cancel')">{x}</button>
      </span>
    </div>
    <div class="pill done" id="pill-done">
      <span class="check">&#10003;</span>
      <span class="dlabel" id="doneLabel">Pasted</span>
      <span class="dmeta" id="doneMeta">38W</span>
      <span class="opt">
        <button class="cta" onclick="api('overlay_copy')">Copy again</button>
        <button class="ctrl" title="Dismiss" onclick="api('overlay_dismiss')">{x}</button>
      </span>
    </div>
    <div class="pill err" id="pill-err">
      <span class="bang">!</span>
      <span class="elabel" id="errLabel">Something went wrong</span>
      <button class="ctrl" title="Dismiss" onclick="api('overlay_dismiss')">{x}</button>
    </div>
    """.format(bars=bars, pause=_PAUSE, play=_PLAY, x=_X)
    from app.fonts_css import web_font_css
    from app.shared_css import pressed_css
    # Pause / Cancel / Dismiss (.ctrl), Stop (.stop) and "Copy again" (.cta) —
    # the overlay's only three interactive classes (IDI-168). Must come after
    # _CSS: `.stop:hover` sets `filter`, and the press has to beat it.
    pressed = pressed_css([".ctrl", ".stop", ".cta"])
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + pressed + "</style></head><body>"
        + body +
        "<script>" + _js() + "</script>"
        "</body></html>"
    )

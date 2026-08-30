"""HTML for the Transform Mode B selection pill (TRANSFORM_SWARM.md P2).

Extracted from `app/transform_widget.py` so cross-platform hosts (macOS
`TransformWidget`, Windows `WinTransformWidget`) can import the shared
HTML without pulling in AppKit at module load. This module has NO
platform imports — only `app.fonts_css` (base64 web-font CSS) and
`app.shared_css` (the shared press-feedback rules), both of which are
plain string builders with no AppKit/Win32 dependency."""

# ── HTML (cream pill; same card language as the auto-learn widget) ───────────
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#EADFCE;--ink:#2a1f18;--ink-mut:rgba(42,31,24,.58);--dark:#1a1512;
--line:rgba(42,31,24,.14);--acc:#E8522A}
html,body{height:100%;background:transparent}
body{font-family:'Geist',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
display:flex;align-items:flex-end;justify-content:center;overflow:visible;padding:14px 40px 32px}
.pill{display:none;flex-direction:column;gap:10px;background:var(--cream);color:var(--ink);
border-radius:16px;padding:14px 16px;box-shadow:0 16px 42px rgba(0,0,0,.42);width:640px}
.pill.show{display:flex}
.row{display:flex;align-items:center;gap:10px}
.eyebrow{font:500 9.5px 'JetBrains Mono',monospace;letter-spacing:.16em;color:var(--ink-mut)}
.excerpt{font:400 12px 'Geist';color:var(--ink-mut);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;flex:1;min-width:0}
.btnP{border:0;border-radius:11px;padding:9px 16px;background:var(--dark);color:var(--cream);
cursor:pointer;font:600 12.5px 'Geist';flex:none;white-space:nowrap}
.btnP:hover{filter:brightness(1.25)}
.btnS{border:1px solid var(--line);border-radius:11px;padding:8px 14px;background:none;
color:var(--ink);cursor:pointer;font:600 12px 'Geist';flex:none}
.btnS:hover{background:rgba(42,31,24,.07)}
.mic{width:34px;height:34px;border-radius:50%;border:1px solid var(--line);background:none;
color:var(--ink);cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
.mic:hover{background:rgba(42,31,24,.07)}
/* recording: accent fill + a pulsing ring so it's unmistakable the mic is live */
.mic.on{background:var(--acc);color:#fff;border-color:var(--acc);animation:micPulse 1.4s ease-out infinite}
@keyframes micPulse{0%{box-shadow:0 0 0 0 rgba(232,82,42,.5)}
70%{box-shadow:0 0 0 11px rgba(232,82,42,0)}100%{box-shadow:0 0 0 0 rgba(232,82,42,0)}}
.mic svg{width:14px;height:14px}
/* live waveform shown next to the mic while recording (mirrors the overlay pill) */
.wave{display:none;align-items:center;gap:2px;height:16px;flex:none}
.wave.on{display:flex}
.wave i{width:2px;border-radius:2px;background:var(--acc);animation:wv .9s ease-in-out infinite}
@keyframes wv{0%,100%{height:4px}50%{height:14px}}
.pin{flex:1;min-width:0;border:1px solid var(--line);border-radius:11px;padding:9px 12px;
font:400 12.5px 'Geist';color:var(--ink);background:rgba(255,255,255,.35);outline:none}
.pin::placeholder{color:var(--ink-mut)}
.pin:focus{border-color:var(--dark)}
.preview{font:400 12.5px/1.6 'Geist';color:var(--ink);background:rgba(255,255,255,.4);
border:1px solid var(--line);border-radius:11px;padding:10px 12px;max-height:96px;overflow-y:auto;
white-space:pre-wrap}
.x{width:28px;height:28px;border-radius:50%;border:0;background:rgba(42,31,24,.09);color:var(--ink);
cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
.x:hover{background:rgba(42,31,24,.17)}
.x svg{width:11px;height:11px}
.spin{width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--dark);
border-radius:50%;animation:sp 0.8s linear infinite;flex:none}
@keyframes sp{to{transform:rotate(360deg)}}
.err{font:500 12px 'Geist';color:#9a3d2e}
.hint{font:400 11px 'Geist';color:var(--ink-mut)}
"""

_JS = """
function api(m){ var a=[].slice.call(arguments,1);
  try{ return window.pywebview.api[m].apply(null,a); }catch(e){} }
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
var S={state:null};
function show(id){ ['pPrompt','pBusy','pPreview','pDone'].forEach(function(x){
  document.getElementById(x).className = 'pill'+(x===id?' show':''); }); }
function setRecording(on){
  var mb=document.getElementById('micBtn'); if(mb) mb.className = on ? 'mic on' : 'mic';
  var w=document.getElementById('micWave'); if(w) w.className = on ? 'wave on' : 'wave';
}
// Errors used to be written to '#perr' unconditionally — but that field lives in
// the PROMPT pill, so every failure raised while the PREVIEW pill was up was
// invisible ('#perr2' was never populated). Write to whichever pill is on
// screen, and clear the other so nothing stale lingers behind it.
function setErr(msg){
  var pv=document.getElementById('pPreview');
  var onPreview = !!(pv && pv.className.indexOf('show')>=0);
  var here=document.getElementById(onPreview?'perr2':'perr');
  var other=document.getElementById(onPreview?'perr':'perr2');
  if(here) here.textContent=msg||'';
  if(other) other.textContent='';
}
window.VerbalTransform=function(d){
  d=d||{}; S.state=d.state;
  if(d.state!=='speaking'){ setRecording(false); }
  if(d.state==='hide'){ show(''); return; }
  if(d.state==='prompt'){
    document.getElementById('exc').textContent=d.excerpt||'';
    document.getElementById('chars').textContent=(d.chars||0)+' chars selected';
    var i=document.getElementById('pin'); i.value='';
    setRecording(false);
    show('pPrompt');
    setErr('');
  }
  else if(d.state==='speaking'){ setRecording(true);
    show('pPrompt');
    setErr('Listening — click the mic again when done.'); }
  else if(d.state==='heard'){
    // Show what we heard and let the user edit it BEFORE transforming — don't
    // auto-run. Go / Enter runs the (possibly edited) instruction.
    show('pPrompt');
    setRecording(false);
    var pin=document.getElementById('pin'); pin.value=d.instruction||'';
    setErr('Heard you — edit if needed, then Go (or press Enter).');
    try{ pin.focus(); pin.setSelectionRange(pin.value.length, pin.value.length); }catch(e){}
  }
  else if(d.state==='busy'){ document.getElementById('busyLabel').textContent=d.label||'Working…';
    show('pBusy'); setErr(''); }
  else if(d.state==='preview'){
    document.getElementById('pvText').textContent=(d.rewrite||'')+(d.truncated?' …':'');
    show('pPreview');
    setErr('');
  }
  else if(d.state==='done'){ show('pDone'); }
  else if(d.state==='error'){
    // fall back to the pill the user came from, then write the message INTO it
    if(S.prev==='preview'){ show('pPreview'); }
    else { show('pPrompt'); }
    setErr(d.msg||'Something went wrong.');
  }
  S.prev=d.state;
};
function sendPrompt(){
  var v=document.getElementById('pin').value.trim();
  if(v) api('tf_prompt', v);
}
document.addEventListener('keydown', function(ev){
  if(ev.key==='Enter' && document.activeElement===document.getElementById('pin')){ sendPrompt(); }
  if(ev.key==='Escape'){ api('tf_cancel'); }
});
api('tf_ready');
"""


def transform_widget_html():
    from app.fonts_css import web_font_css
    mic = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
           'stroke-linecap="round"><rect x="9" y="3" width="6" height="12" rx="3"/>'
           '<path d="M19 11v1a7 7 0 0 1-14 0v-1"/><path d="M12 19v3"/></svg>')
    x = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/>'
         '<line x1="18" y1="6" x2="6" y2="18"/></svg>')
    # staggered waveform bars (same idiom as the recording overlay pill)
    bars = "".join('<i style="animation-delay:%.2fs"></i>' % (i * 0.08) for i in range(11))
    body = """
    <div class="pill" id="pPrompt">
      <div class="row"><span class="eyebrow">TRANSFORM SELECTION</span>
        <span class="excerpt" id="exc"></span>
        <span class="hint" id="chars"></span>
        <button class="x" title="Cancel (Esc)" onclick="api('tf_cancel')">{x}</button></div>
      <div class="row">
        <button class="btnP" onclick="api('tf_improvise')">Improvise</button>
        <button class="mic" id="micBtn" title="Speak an instruction" onclick="api('tf_speak')">{mic}</button>
        <input class="pin" id="pin" placeholder="…or type an instruction — “make the tone professional”"/>
        <button class="btnS" onclick="sendPrompt()">Go</button>
      </div>
      <div class="row"><div class="wave" id="micWave">{bars}</div><span class="err" id="perr"></span></div>
    </div>
    <div class="pill" id="pBusy">
      <div class="row"><span class="spin"></span><span class="hint" id="busyLabel">Working…</span>
        <span style="flex:1"></span>
        <button class="btnS" onclick="api('tf_cancel')">Cancel</button>
        <button class="x" title="Cancel (Esc)" onclick="api('tf_cancel')">{x}</button></div>
    </div>
    <div class="pill" id="pPreview">
      <div class="row"><span class="eyebrow">PREVIEW</span><span class="hint">replaces your selection</span>
        <span style="flex:1"></span>
        <button class="x" title="Cancel (Esc)" onclick="api('tf_cancel')">{x}</button></div>
      <div class="preview" id="pvText"></div>
      <div class="row">
        <button class="btnP" onclick="api('tf_replace')">Replace</button>
        <button class="btnS" onclick="api('tf_cancel')">Cancel</button>
        <span class="err" id="perr2"></span>
      </div>
    </div>
    <div class="pill" id="pDone">
      <div class="row"><span class="eyebrow">REPLACED</span>
        <span class="hint">changed your mind?</span>
        <button class="btnS" onclick="api('tf_undo')">Undo</button>
        <span style="flex:1"></span>
        <button class="x" onclick="api('tf_cancel')">{x}</button></div>
    </div>
    """.format(x=x, mic=mic, bars=bars)
    from app.shared_css import pressed_css
    # Run/Replace (.btnP), Undo & friends (.btnS), the spoken-prompt mic and the
    # dismiss X (IDI-168). After _CSS so the press beats `.btnP:hover`'s filter;
    # `.mic.on`'s pulse animates box-shadow only, so the scale composes cleanly.
    pressed = pressed_css([".btnP", ".btnS", ".mic", ".x"])
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + pressed + "</style></head><body>"
        + body +
        "<script>" + _JS + "</script>"
        "</body></html>"
    )

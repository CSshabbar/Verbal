"""
HTML for the Flume tray popover — WINDOWS ONLY as of IDI-183.

macOS retired its NSPopover for a real NSMenu (app/menubar_menu.py), so
flume_popover.py is gone; `popover_html()` now has exactly one host:
win_popover.py's pywebview window. `_mark_data_uri()` is also imported by
flume_dashboard_html.py for the sign-in pane's logo, so this module stays on the
macOS side of the build too.
"""
import base64
import os
import sys


def _mark_data_uri():
    """Base64 data-URI for the circular Flume bird mark (small, ~22KB)."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(os.path.join(sys._MEIPASS, "app", "assets", "img", "flume-mark-128.png"))
    here = os.path.dirname(__file__)
    candidates.append(os.path.join(here, "assets", "img", "flume-mark-128.png"))
    for p in candidates:
        try:
            with open(p, "rb") as f:
                return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        except Exception:
            continue
    return ""  # falls back to the ✳ glyph in CSS


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0e1012;--card:#17191c;--tx:#f2f2f2;--mut:rgba(240,240,240,.55);--sub:rgba(240,240,240,.4);
--acc:#C85A3E;--acc-ink:#2a1710;--bd:rgba(240,240,240,.07);--bd2:rgba(240,240,240,.1);--on:#4ad15a}
html,body{background:var(--bg);color:var(--tx);height:100%}
body{font-family:'Geist',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
display:flex;flex-direction:column;overflow:hidden}
.view{display:flex;flex-direction:column;flex:1;min-height:0}
.view[hidden]{display:none}
.pad{padding:16px 16px 0}
/* sub-view header */
.subhdr{display:flex;align-items:center;gap:10px;padding:14px 14px 12px;border-bottom:1px solid var(--bd)}
.back{width:30px;height:30px;border-radius:9px;border:0;background:var(--card);color:var(--tx);cursor:pointer;font:400 20px 'Geist';line-height:1;display:flex;align-items:center;justify-content:center}
.back:hover{background:rgba(240,240,240,.1)}
.subtitle{font:700 16px 'Geist'}
.subcount{margin-left:auto;font:500 12px 'JetBrains Mono';color:var(--sub)}
/* canvas view */
.cvimg{width:100%;border-radius:12px;border:1px solid var(--bd);margin-bottom:12px;display:block}
.cvtext{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px;font:400 13.5px/1.5 'Geist';color:rgba(240,240,240,.92);white-space:pre-wrap;word-break:break-word;margin-bottom:12px}
/* header */
.hdr{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.logo{width:46px;height:46px;border-radius:50%;background:#000;overflow:hidden;flex:none;display:flex;align-items:center;justify-content:center;color:var(--acc);font:600 22px 'Geist'}
.logo img{width:100%;height:100%;object-fit:cover}
.hinfo{flex:1;min-width:0}
.hname{font:700 17px 'Geist';letter-spacing:.01em}
.hstat{display:flex;align-items:center;gap:7px;font:400 13px 'Geist';color:var(--mut);margin-top:2px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--on);flex:none}
.dot.busy{background:var(--acc)}
.toggle{width:46px;height:26px;border-radius:14px;border:0;background:var(--acc);position:relative;cursor:pointer;flex:none;transition:background .15s}
.toggle:not(.on){background:rgba(240,240,240,.16)}
.toggle .knob{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:left .15s}
.toggle.on .knob{left:23px}
/* record button */
.record{width:100%;display:flex;align-items:center;gap:12px;background:var(--acc);color:var(--acc-ink);
border:0;border-radius:14px;padding:15px 16px;cursor:pointer;margin-bottom:12px;text-align:left}
.record .mic{width:34px;height:34px;border-radius:10px;background:rgba(42,23,16,.22);display:flex;align-items:center;justify-content:center;flex:none}
.record .mic svg{width:18px;height:18px;stroke:var(--acc-ink)}
.record .rlabel{flex:1;font:700 16px 'Geist'}
.record .kbd{background:rgba(42,23,16,.22);border-radius:8px;padding:6px 10px;font:600 12px 'JetBrains Mono';color:var(--acc-ink);flex:none}
.record.rec{background:#d96a4e}
.record.meeting{background:var(--card);border:1px solid var(--bd);color:#f2f2f2;padding:11px 16px;margin-top:-4px}
.record.meeting .mic{background:rgba(200,90,62,.16)}
.record.meeting .mic svg{stroke:#C85A3E}
.record.meeting .rlabel{font:600 13.5px 'Geist'}
/* quick cards */
.qcards{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:6px}
.qcard{display:flex;align-items:center;gap:9px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:11px 12px;cursor:pointer}
.qcard:hover{border-color:var(--bd2)}
.qicon{width:18px;height:18px;flex:none;display:flex;align-items:center;justify-content:center;color:var(--tx)}
.qicon svg{width:17px;height:17px;stroke:var(--tx)}
.qlabel{flex:1;font:600 13px 'Geist'}
.qnum{font:600 14px 'JetBrains Mono';color:var(--acc)}
.qnum.mutenum{color:var(--sub)}
/* recent */
.reclab{font:600 10px 'JetBrains Mono';letter-spacing:.14em;color:var(--sub);margin:18px 0 10px}
.recscroll{flex:1;overflow-y:auto;overflow-x:hidden}
.rec{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:11px 12px;margin-bottom:8px}
.rectop{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}
.recmeta{font:500 11.5px 'JetBrains Mono';color:var(--mut);letter-spacing:.02em}
.tag{font:600 11px 'Geist';padding:3px 9px;border-radius:7px;background:rgba(200,90,62,.16);color:var(--acc)}
.tag.slate{background:rgba(74,100,148,.2);color:#9db2d8}
.tag.local{background:rgba(240,240,240,.08);color:var(--mut)}
.rectext{font:400 13.5px/1.4 'Geist';color:rgba(240,240,240,.92);overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.recacts{display:flex;gap:16px;margin-top:10px}
.recacts button{background:0;border:0;cursor:pointer;font:600 13px 'Geist';padding:0}
.recacts .copy{color:var(--acc)}
.recacts .copy:hover{opacity:.75}
.empty{color:var(--mut);font:400 13px 'Geist';padding:14px 2px}
/* signed-out gate (IDI-183) — the notice replaces the recent list, and every
   action is dimmed AND inert. pointer-events is the look; the JS guards in
   toggleRecord/go/startMeeting are the lock (keyboard reaches these too). */
.dot.off{background:rgba(240,240,240,.35)}
.gate{background:var(--card);border:1px solid var(--bd2);border-radius:12px;padding:14px;margin-bottom:10px}
.gate h4{font:700 14px 'Geist';margin-bottom:5px}
.gate p{font:400 12.5px/1.45 'Geist';color:var(--mut);margin-bottom:12px}
.gate button{width:100%;background:var(--acc);color:var(--acc-ink);border:0;border-radius:10px;
padding:10px;font:700 13px 'Geist';cursor:pointer}
body.gated .record,body.gated .qcards,body.gated .toggle,body.gated .reclab,body.gated .recscroll{
opacity:.32;pointer-events:none}
/* footer */
.footer{display:flex;align-items:center;border-top:1px solid var(--bd);padding:12px 8px;gap:4px;margin-top:6px}
.fbtn{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;background:0;border:0;color:var(--mut);cursor:pointer;font:500 13px 'Geist';padding:8px 4px;border-radius:8px}
.fbtn svg{width:15px;height:15px;stroke:currentColor}
.fbtn:hover{color:var(--tx)}
.fbtn.quit:hover{color:#e2624a}
::-webkit-scrollbar{width:8px}::-webkit-scrollbar-thumb{background:rgba(240,240,240,.1);border-radius:4px}
"""

_ICONS = {
    "mic": '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>',
    "grid": '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    "clock": '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>',
    "expand": '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>',
    "sun": '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
}


def _js():
    return """
let STATE=null, VIEW='main', CANVAS={content:'',image_url:null};
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const IC=window.__IC;
function api(method){var a=[].slice.call(arguments,1);return window.pywebview.api[method].apply(null,a);}
function words(t){return (String(t||'').trim().match(/\\S+/g)||[]).length;}
function tagCls(app){app=(app||'').toLowerCase();
  if(app.includes('iphone'))return '';
  if(app.includes('ipad')||app.includes('pc')||app.includes('windows'))return 'slate';
  return 'local';}
function tagName(app){return app && app!=='Local' ? app : 'This Mac';}

// Each row offers Copy only. A second button next to it claimed to re-paste
// the text but called the identical doCopy — removed in IDI-167 rather than
// left as a lie. Same for the canvas view below.
function recItem(e){
  const t = e.text || '';
  return '<div class="rec">'
    +'<div class="rectop"><span class="recmeta">'+esc(e.ts||'')+'  ·  '+words(t)+'W</span>'
    +'<span class="tag '+tagCls(e.app)+'">'+esc(tagName(e.app))+'</span></div>'
    +'<div class="rectext">'+esc(t)+'</div>'
    +'<div class="recacts"><button class="copy" onclick=\\'doCopy('+JSON.stringify(t)+')\\'>Copy</button></div></div>';
}

function render(){
  if(!STATE) return;
  // view visibility
  $('#v-main').hidden = VIEW!=='main';
  $('#v-history').hidden = VIEW!=='history';
  $('#v-canvas').hidden = VIEW!=='canvas';

  // Sign-in gate (IDI-183). Flume requires an account, so signed out every
  // action here is dead: the tray suppresses this panel in that state, but the
  // panel can also be OPEN when a sign-out happens in the dashboard, and the
  // 'state' event lands here. Gate rather than trust the caller.
  const signedIn = STATE.signed_in !== false;
  document.body.classList.toggle('gated', !signedIn);
  const gate = $('#gate');
  if(gate) gate.hidden = signedIn;

  const rec = !!STATE.recording, busy = !!STATE.processing;
  const dev = STATE.target_device_name || (STATE.settings&&STATE.settings.sync_device_name) || 'This device';
  const statusTx = !signedIn ? 'Not signed in' : rec ? 'Recording…' : busy ? 'Transcribing…' : 'Ready';
  $('#hname').textContent = 'Flume';
  $('#hstat').innerHTML = '<span class="dot'+(!signedIn?' off':(rec||busy?' busy':''))+'"></span>'
    + esc(statusTx) + (signedIn ? ' · '+esc(dev) : '');
  const syncOn = !!(STATE.settings && STATE.settings.sync_enabled);
  $('#syncToggle').className = 'toggle'+(syncOn?' on':'');

  const rbtn = $('#recordBtn');
  rbtn.className = 'record'+(rec?' rec':'');
  $('#rlabel').textContent = rec ? 'Stop recording' : 'Start recording';

  const canvasN = (STATE.pinned && STATE.pinned.length) || 0;
  $('#canvasNum').textContent = canvasN ? canvasN : '';
  $('#histNum').textContent = STATE.total_transcriptions || 0;

  const h = STATE.history || [];
  $('#recent').innerHTML = h.slice(0,2).map(recItem).join('')
    || '<div class="empty">Nothing yet — hold your hotkey to record.</div>';

  if(VIEW==='history'){
    $('#histCount').textContent = (STATE.total_transcriptions||0)+' total';
    $('#histList').innerHTML = h.slice(0,10).map(recItem).join('')
      || '<div class="empty">No transcriptions yet.</div>';
  }
}

function go(v){ if(gatedOut()) return openWindow(); VIEW=v; render(); if(v==='canvas') loadCanvas(); }
function startMeeting(){ if(gatedOut()) return openWindow(); api('open_meeting_launcher'); }

function loadCanvas(){
  $('#canvasBody').innerHTML = '<div class="empty">Loading…</div>';
  api('fetch_canvas').then(r=>{
    CANVAS = {content:(r&&r.content)||'', image_url:(r&&r.image_url)||null};
    renderCanvas();
  }).catch(()=>{ CANVAS={content:'',image_url:null}; renderCanvas(); });
}

function renderCanvas(){
  const c = CANVAS||{};
  let html='';
  if(c.image_url) html += '<img class="cvimg" src="'+esc(c.image_url)+'"/>';
  if(c.content){
    html += '<div class="cvtext">'+esc(c.content)+'</div>'
      + '<div class="recacts"><button class="copy" onclick=\\'doCopy('+JSON.stringify(c.content)+')\\'>Copy</button></div>';
  }
  if(!c.image_url && !c.content) html = '<div class="empty">Canvas is empty.</div>';
  $('#canvasBody').innerHTML = html;
}

function doCopy(t){ api('copy_text', t); }
// Every action re-checks the gate: CSS pointer-events is a look, not a lock,
// and these are also reachable by keyboard.
function gatedOut(){ return STATE && STATE.signed_in === false; }
function toggleRecord(){ if(gatedOut()) return openWindow(); api('toggle_recording'); }
function toggleSync(){
  const on = !$('#syncToggle').classList.contains('on');
  $('#syncToggle').className = 'toggle'+(on?' on':'');
  const s = (STATE&&STATE.settings)||{};
  api('save_settings', {
    groq_api_keys:s.groq_api_keys||[], gemini_api_keys:s.gemini_api_keys||[],
    whisper_model:(STATE&&STATE.model)||'base', sync_enabled:on,
    sync_user_id:s.sync_user_id||'', sync_device_name:s.sync_device_name||'This Mac',
  }).then(load);
}
function openWindow(){ api('open_window'); }
function openPrefs(){ api('open_preferences'); }
function quitApp(){ api('quit_app'); }

function load(){ api('get_state').then(s=>{ STATE=s; render(); }); }

window.VerbalNative = function(event, payload){
  if(event==='recordingState'){ if(STATE){ STATE.recording=payload.recording; STATE.processing=false; } render(); }
  else if(event==='state'){ STATE=payload; render(); }
  else if(event==='result'){ load(); }
};

document.addEventListener('DOMContentLoaded', load);
if(document.readyState!=='loading') load();
"""


def popover_html():
    mark = _mark_data_uri()
    logo_inner = '<img src="%s" alt="Flume"/>' % mark if mark else "✳"
    icons_js = "window.__IC=" + repr({}) + ";"
    body = """
    <div class="view" id="v-main">
      <div class="pad">
        <div class="hdr">
          <div class="logo">{logo}</div>
          <div class="hinfo"><div class="hname" id="hname">Flume</div><div class="hstat" id="hstat"><span class="dot"></span>Ready</div></div>
          <button class="toggle on" id="syncToggle" onclick="toggleSync()"><span class="knob"></span></button>
        </div>
        <div class="gate" id="gate" hidden>
          <h4>Sign in to get started</h4>
          <p>Flume needs your account before it can dictate, sync or keep your notes.</p>
          <button onclick="openWindow()">Sign in with Google</button>
        </div>
        <button class="record" id="recordBtn" onclick="toggleRecord()">
          <span class="mic">{mic}</span><span class="rlabel" id="rlabel">Start recording</span>
          <span class="kbd">⌘⌥</span>
        </button>
        <button class="record meeting" onclick="startMeeting()">
          <span class="mic">{mic}</span><span class="rlabel">Start meeting</span>
        </button>
        <div class="qcards">
          <div class="qcard" onclick="go('canvas')"><span class="qicon">{grid}</span><span class="qlabel">Canvas</span><span class="qnum" id="canvasNum"></span></div>
          <div class="qcard" onclick="go('history')"><span class="qicon">{clock}</span><span class="qlabel">History</span><span class="qnum mutenum" id="histNum">0</span></div>
        </div>
        <div class="reclab">RECENT</div>
      </div>
      <div class="recscroll pad" style="padding-top:0"><div id="recent"></div></div>
      <div class="footer">
        <button class="fbtn" onclick="openWindow()">{expand}Open window</button>
        <button class="fbtn" onclick="openPrefs()">{sun}Preferences</button>
        <button class="fbtn quit" onclick="quitApp()">Quit</button>
      </div>
    </div>
    <div class="view" id="v-history" hidden>
      <div class="subhdr"><button class="back" onclick="go('main')">‹</button><span class="subtitle">History</span><span class="subcount" id="histCount"></span></div>
      <div class="recscroll pad"><div id="histList"></div></div>
    </div>
    <div class="view" id="v-canvas" hidden>
      <div class="subhdr"><button class="back" onclick="go('main')">‹</button><span class="subtitle">Canvas</span></div>
      <div class="recscroll pad"><div id="canvasBody"></div></div>
    </div>
    """.format(logo=logo_inner, mic=_ICONS["mic"], grid=_ICONS["grid"],
               clock=_ICONS["clock"], expand=_ICONS["expand"], sun=_ICONS["sun"])
    from app.fonts_css import web_font_css
    from app.shared_css import pressed_css
    # Every interactive element in the popover: the sync toggle, both record
    # buttons, the two quick cards, the sub-view back button, the three footer
    # buttons and the per-item Copy (IDI-168). Appended after _CSS so it wins
    # the source-order tie against the hover rules.
    pressed = pressed_css([
        ".toggle", ".record", ".qcard", ".back", ".fbtn", ".recacts button",
    ])
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + pressed + "</style></head><body>"
        + body +
        "<script>" + icons_js + "</script>"
        "<script>" + _js() + "</script>"
        "</body></html>"
    )

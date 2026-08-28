"""
HTML for the Flume tray popover — WINDOWS ONLY as of IDI-183.

macOS retired its NSPopover for a real NSMenu (app/menubar_menu.py). Windows has
no menubar, so the tray's LEFT-click opens this pywebview window instead — and
since 2026-08-29 it is a faithful port of that NSMenu rather than the old card
panel: ONE custom header row (mark · state dot + status · hotkey hint or live
waveform + timer · words TODAY) followed by plain menu rows, separators,
checkmarks and inline disclosure submenus (Recent / Canvas / Recording Mode /
Offline Model), styled like a Windows 11 flyout. Row order, titles and gating
mirror `menubar_menu.build()` + `MenuController.refresh()` so the two desktops
read as the same product.

Host contract (win_popover.py `_PopoverBridge`):
  * `popover_state()`  — everything the menu needs, read fresh on each open.
  * `popover_tick()`   — {recording, processing, level, elapsed} at ~12 fps
                          while the window is visible and recording.
  * `popover_resize(h)`— the page reports its content height; the host sizes
                          the window to it (menus are as tall as their rows).
  * actions            — toggle_recording, start_meeting, open_window,
                          open_history, open_canvas, open_notes,
                          open_preferences, set_mode, set_model, set_sync,
                          toggle_auth, open_update, check_updates, about,
                          copy_text, hide_popover, quit_app.

`_mark_data_uri()` is also imported by flume_dashboard_html.py for the sign-in
pane's logo, so this module stays on the macOS side of the build too.
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


# Windows 11 flyout look: near-black acrylic-ish surface, 8 px corners, 1 px
# hairline, 30 px rows. Brand colour (terracotta) appears in exactly the places
# the Mac header uses it — the mark ring, the state dot and the waveform.
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#1c1c1e;--bg2:#242426;--tx:#f2f2f2;--mut:rgba(242,242,242,.62);--sub:rgba(242,242,242,.42);
--acc:#C85A3E;--on:#38b54a;--bd:rgba(255,255,255,.09);--hov:rgba(255,255,255,.08);--sel:rgba(255,255,255,.12)}
html,body{background:transparent;color:var(--tx)}
body{font-family:'Geist','Segoe UI Variable','Segoe UI',system-ui,sans-serif;-webkit-font-smoothing:antialiased;
font-size:13px;overflow:hidden;user-select:none;-webkit-user-select:none}
.menu{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:4px;box-shadow:0 8px 24px rgba(0,0,0,.45)}
/* header — the one custom row */
.hdr{display:flex;align-items:center;gap:10px;padding:8px 8px 8px 8px;min-height:50px}
.mark{width:28px;height:28px;border-radius:50%;background:#000;overflow:hidden;flex:none;display:flex;align-items:center;justify-content:center;color:var(--acc);font:600 14px 'Geist'}
.mark img{width:100%;height:100%;object-fit:cover}
.hmid{flex:1;min-width:0}
.hrow{display:flex;align-items:center;gap:7px;min-width:0}
.dot{width:6px;height:6px;border-radius:50%;background:var(--on);flex:none}
.dot.brand{background:var(--acc)}.dot.mute{background:var(--sub)}
.title{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{font-size:11px;color:var(--mut);margin-top:2px;margin-left:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px;height:14px}
.wave{display:flex;align-items:center;gap:2px;height:13px}
.wave i{display:block;width:2.5px;border-radius:1.25px;background:var(--acc);height:2px}
.mono{font-family:'JetBrains Mono','Cascadia Mono',Consolas,monospace;font-variant-numeric:tabular-nums}
.hnum{text-align:right;flex:none;min-width:56px}
.hnum b{display:block;font:600 13px 'JetBrains Mono','Cascadia Mono',Consolas,monospace}
.hnum span{display:block;font-size:8.5px;letter-spacing:.06em;color:var(--sub);margin-top:1px}
/* rows */
.sep{height:1px;background:var(--bd);margin:4px 8px}
.row{display:flex;align-items:center;height:30px;padding:0 10px 0 8px;border-radius:5px;cursor:default;gap:8px;color:var(--tx)}
.row:hover{background:var(--hov)}
.row:active{background:var(--sel)}
.row.dis,.row.dis:hover{color:var(--sub);background:transparent;cursor:default}
.row .ck{width:14px;flex:none;text-align:center;font-size:12px;color:var(--tx)}
.row .lbl{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .kbd{font-size:11px;color:var(--sub);font-family:'JetBrains Mono','Cascadia Mono',Consolas,monospace}
.row .chev{color:var(--sub);font-size:11px;transition:transform .12s;width:10px;text-align:center}
.row.open .chev{transform:rotate(90deg)}
.row.update .lbl{color:var(--acc);font-weight:600}
.subm{display:none;padding:2px 0 2px 14px}
.subm.show{display:block}
.subm .row{height:28px;font-size:12.5px}
.subm .row.copy .lbl{color:var(--mut)}
.subm .row.copy:hover .lbl{color:var(--tx)}
.subm .row.copy .meta{font-size:10.5px;color:var(--sub);font-family:'JetBrains Mono','Cascadia Mono',Consolas,monospace;flex:none}
.subm .empty{height:26px;display:flex;align-items:center;padding-left:22px;color:var(--sub);font-size:12px}
.toast{position:fixed;left:50%;bottom:10px;transform:translateX(-50%);background:var(--bg2);border:1px solid var(--bd);
border-radius:6px;padding:5px 10px;font-size:11.5px;color:var(--mut);opacity:0;transition:opacity .15s;pointer-events:none}
.toast.show{opacity:1}
"""


def _js():
    return r"""
let S=null, OPEN={}, LEVELS=[0,0,0,0,0,0,0], TICK=null, T0=0;
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function api(m){var a=[].slice.call(arguments,1);
  return (window.pywebview&&window.pywebview.api&&window.pywebview.api[m])?window.pywebview.api[m].apply(null,a):Promise.resolve({ok:false});}
function mmss(s){s=Math.max(0,Math.floor(s||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
function one(t,n){t=String(t||'').split(/\s+/).join(' ');n=n||46;return t.length>n?t.slice(0,n-1)+'…':t;}

function row(o){
  // o: {id,label,cls,ck,kbd,chev,dis,onclick,meta}
  const cls=['row',o.cls||'',o.dis?'dis':'',(o.chev&&OPEN[o.id])?'open':''].join(' ');
  const oc=o.dis?'':(o.onclick||'');
  return '<div class="'+cls+'" '+(oc?'onclick="'+oc+'"':'')+'>'
    +'<span class="ck">'+(o.ck?'✓':'')+'</span>'
    +'<span class="lbl">'+esc(o.label)+'</span>'
    +(o.meta?'<span class="meta">'+esc(o.meta)+'</span>':'')
    +(o.kbd?'<span class="kbd">'+esc(o.kbd)+'</span>':'')
    +(o.chev?'<span class="chev">›</span>':'')
    +'</div>';
}
function sub(id,inner){return '<div class="subm'+(OPEN[id]?' show':'')+'" id="sub-'+id+'">'+inner+'</div>';}
function toggleSub(id){OPEN[id]=!OPEN[id];render();}

function header(){
  const s=S; let title,subtx,kind;
  if(!s.signed_in){title='Sign in to get started';subtx='Flume needs your account';kind='mute';}
  else if(s.session_dead){title='Session expired';subtx='Sign in again to sync';kind='mute';}
  else if(s.recording){title='Recording';subtx=mmss(s.rec_elapsed);kind='brand';}
  else if(s.processing){title='Transcribing…';subtx='Press esc to cancel';kind='brand';}
  else if(s.meeting_active){title=s.meeting_label||'Meeting';subtx='Recording the call';kind='brand';}
  else if(s.status_line){title=s.status_line;subtx='';kind='mute';}
  else{title='Ready';subtx=s.hotkey_label?((s.mode==='hold'?'Hold ':'Tap ')+s.hotkey_label+' to dictate'):'Ready to dictate';kind='';}
  const wave = s.recording ? '<span class="wave" id="wave">'+LEVELS.map(()=>'<i></i>').join('')+'</span>' : '';
  return '<div class="hdr">'
    +'<div class="mark">'+(window.__MARK?'<img src="'+window.__MARK+'" alt=""/>':'✳')+'</div>'
    +'<div class="hmid"><div class="hrow"><span class="dot '+kind+'"></span><span class="title" id="htitle">'+esc(title)+'</span></div>'
    +'<div class="sub">'+wave+'<span id="hsub" class="'+(s.recording?'mono':'')+'">'+esc(subtx)+'</span></div></div>'
    +(s.signed_in?'<div class="hnum"><b>'+(s.daily_words||0)+'</b><span>TODAY</span></div>':'')
    +'</div>';
}

function render(){
  if(!S) return;
  const g=!S.signed_in;     // gated
  let h=header();
  if(S.update_version) h+=row({label:'Update available (v'+S.update_version+') ↑',cls:'update',onclick:"act('open_update')"});
  h+='<div class="sep"></div>';
  h+=row({label:S.recording?'Stop Recording':'Start Recording',dis:g,onclick:"act('toggle_recording')"});
  h+=row({label:S.meeting_active?'Return to Meeting':'Start Meeting',dis:g,onclick:"act('start_meeting')"});
  h+='<div class="sep"></div>';
  // Recent ▸
  const rec=S.recent||[];
  h+=row({id:'recent',label:'Recent',chev:true,dis:g,onclick:"toggleSub('recent')"});
  h+=sub('recent',(rec.length?rec.map(e=>row({cls:'copy',label:one(e.text),meta:[e.ts,e.app].filter(Boolean).join(' · '),onclick:"copyT("+JSON.stringify(JSON.stringify(e.text))+")"})).join('')
      :'<div class="empty">No transcriptions yet</div>')
      +row({label:'Open History…',onclick:"act('open_history')"}));
  // Canvas ▸
  const pin=S.pinned||[];
  h+=row({id:'canvas',label:pin.length?'Canvas ('+pin.length+')':'Canvas',chev:true,dis:g,onclick:"toggleSub('canvas')"});
  h+=sub('canvas',(pin.length?pin.map(e=>row({cls:'copy',label:one(e.text),onclick:"copyT("+JSON.stringify(JSON.stringify(e.text))+")"})).join('')
      :'<div class="empty">Canvas is empty</div>')
      +row({label:'Open Canvas…',onclick:"act('open_canvas')"}));
  h+=row({label:'Notes',dis:g,onclick:"act('open_notes')"});
  h+='<div class="sep"></div>';
  // Recording Mode ▸
  h+=row({id:'mode',label:'Recording Mode: '+(S.mode==='hold'?'Hold':'Toggle'),chev:true,dis:g,onclick:"toggleSub('mode')"});
  h+=sub('mode',row({label:'Hold Key to Record',ck:S.mode==='hold',onclick:"act('set_mode','hold')"})
      +row({label:'Toggle On/Off',ck:S.mode!=='hold',onclick:"act('set_mode','toggle')"}));
  // Offline Model ▸
  h+=row({id:'model',label:'Offline Model: '+(S.model||'base'),chev:true,dis:g,onclick:"toggleSub('model')"});
  h+=sub('model',['tiny','base','small','medium'].map(m=>row({label:m,ck:(S.model||'base')===m,onclick:"act('set_model','"+m+"')"})).join(''));
  h+=row({label:S.sync_connecting?'Sync to My Devices (connecting…)':'Sync to My Devices',ck:!!S.sync_enabled,dis:g||!S.sync_allowed,onclick:"act('set_sync',"+(!S.sync_enabled)+")"});
  h+='<div class="sep"></div>';
  h+=row({label:'Open Flume',kbd:'',onclick:"act('open_window')"});
  h+=row({label:'Settings…',dis:g,onclick:"act('open_preferences')"});
  h+=row({label:S.auth_label||'Sign in with Google',onclick:"act('toggle_auth')"});
  h+='<div class="sep"></div>';
  h+=row({label:'Check for Updates…',onclick:"act('check_updates')"});
  h+=row({label:'About Flume',onclick:"act('about')"});
  h+=row({label:'Quit Flume',onclick:"act('quit_app')"});
  $('#menu').innerHTML=h;
  drawWave();
  reportSize();
}

function reportSize(){
  const el=$('#menu'); if(!el) return;
  const hh=Math.ceil(el.getBoundingClientRect().height)+2;
  if(hh!==window.__lastH){window.__lastH=hh;api('popover_resize',hh);}
}
function drawWave(){
  const w=$('#wave'); if(!w) return;
  const bars=w.children;
  for(let i=0;i<bars.length&&i<LEVELS.length;i++){const l=Math.max(0,Math.min(1,LEVELS[i]));bars[i].style.height=(2+Math.pow(l,.6)*11)+'px';}
}
function startTick(){
  if(TICK) return;
  TICK=setInterval(()=>{
    if(!S||!(S.recording||S.processing)) return;
    api('popover_tick').then(t=>{
      if(!t||!t.ok) return;
      const was=S.recording, wasP=S.processing;
      S.recording=!!t.recording; S.processing=!!t.processing; S.rec_elapsed=t.elapsed||0;
      if(S.recording){LEVELS=LEVELS.slice(1).concat([t.level||0]);const e=$('#hsub');if(e)e.textContent=mmss(S.rec_elapsed);drawWave();}
      if(was!==S.recording||wasP!==S.processing) load();
    }).catch(()=>{});
  },85);
}

// Actions close the menu like a real menu does, except the ones that only
// change a checkmark (mode / model / sync) — those re-render in place.
const STAY={set_mode:1,set_model:1,set_sync:1};
function act(name){
  const a=[].slice.call(arguments,1);
  if(S && !S.signed_in && !{open_window:1,toggle_auth:1,check_updates:1,about:1,quit_app:1,open_update:1}[name]){ return act('open_window'); }
  const p=api.apply(null,[name].concat(a));
  if(STAY[name]){ p.then(load).catch(load); }
  else { api('hide_popover'); }
}
function copyT(t){ try{ t=JSON.parse(t);}catch(e){} api('copy_text',t); toast('Copied'); }
let TT=null; function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(TT);TT=setTimeout(()=>t.classList.remove('show'),900);}

function load(){ api('popover_state').then(s=>{ if(s&&s.ok){ S=s; render(); startTick(); } }).catch(()=>{}); }

window.VerbalNative=function(event,payload){
  if(event==='recordingState'){ if(S){ S.recording=!!payload.recording; S.processing=false; } load(); }
  else if(event==='state'){ load(); }
  else if(event==='result'){ load(); }
  else if(event==='opened'){ OPEN={}; load(); }
};
document.addEventListener('keydown',e=>{ if(e.key==='Escape') api('hide_popover'); });
// Focus loss = dismiss, like any flyout. WebView2 fires blur on the window when
// the user clicks elsewhere; the host also hides on its own deactivate hook.
window.addEventListener('blur',()=>{ setTimeout(()=>{ if(!document.hasFocus()) api('hide_popover'); },120); });
document.addEventListener('DOMContentLoaded',load);
if(document.readyState!=='loading') load();
"""


def popover_html():
    mark = _mark_data_uri()
    from app.fonts_css import web_font_css
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + "</style></head><body>"
        "<div class='menu' id='menu'></div><div class='toast' id='toast'></div>"
        "<script>window.__MARK=" + repr(mark) + ";</script>"
        "<script>" + _js() + "</script>"
        "</body></html>"
    )

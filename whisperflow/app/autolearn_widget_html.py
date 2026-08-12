"""HTML for the autolearn confirm pill — the cream card that asks
"learn this correction?" after a user edits the just-injected text.

Extracted from `app/autolearn_widget.py` so cross-platform hosts (macOS
`AutoLearnWidget`, Windows `WinAutoLearnWidget`) can import the shared
HTML without pulling in AppKit at module load. This module has NO
platform imports — only `app.fonts_css` (base64 web-font CSS) and
`app.shared_css` (the shared press-feedback rules), both of which are
plain string builders with no AppKit/Win32 dependency."""

# ── HTML ──────────────────────────────────────────────────────────────────────
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#EADFCE;--ink:#2a1f18;--ink-mut:rgba(42,31,24,.58);--dark:#1a1512}
html,body{height:100%;background:transparent}
body{font-family:'Geist',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
display:flex;align-items:flex-end;justify-content:center;overflow:visible;padding:14px 40px 32px}
.pill{display:flex;align-items:center;gap:16px;background:var(--cream);color:var(--ink);border:0;
border-radius:16px;padding:12px 12px 12px 18px;box-shadow:0 16px 42px rgba(0,0,0,.42);
max-width:580px;opacity:0;transform:translateY(10px) scale(.97)}
.pill.in{animation:pin .24s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes pin{to{opacity:1;transform:none}}
.pill.out{animation:pout .16s ease forwards}
@keyframes pout{to{opacity:0;transform:translateY(8px) scale(.97)}}
.body{display:flex;flex-direction:column;gap:3px;min-width:0}
.title{font:600 13.5px 'Geist';color:var(--ink);letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:360px}
.tword{font-weight:700;color:var(--ink)}
.pair{font:500 12px 'Geist';color:var(--ink-mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:360px}
.old{color:var(--ink);font-weight:600}
.add{border:0;border-radius:11px;padding:9px 16px;background:var(--dark);color:var(--cream);cursor:pointer;
font:600 12.5px 'Geist';flex:none;transition:filter .12s;margin-left:2px;white-space:nowrap}
.add:hover{filter:brightness(1.25)}
.x{width:28px;height:28px;border-radius:50%;border:0;background:rgba(42,31,24,.09);color:var(--ink);
cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none}
.x:hover{background:rgba(42,31,24,.17)}
.x svg{width:11px;height:11px}
"""

_JS = """
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function api(m){ try{ return window.pywebview.api[m](); }catch(e){} }
window.VerbalAutolearn=function(d){
  d=d||{};
  document.getElementById('titleword').textContent = '\\u201C'+(d.new||'')+'\\u201D';
  document.getElementById('oldw').textContent = '\\u201C'+(d.old||'')+'\\u201D';
  var c=document.getElementById('pill');
  c.classList.remove('out'); c.classList.remove('in'); void c.offsetWidth; c.classList.add('in');
};
window.VerbalAutolearnHide=function(){ var c=document.getElementById('pill'); if(c){c.classList.remove('in');c.classList.add('out');} };
"""


def autolearn_widget_html():
    from app.fonts_css import web_font_css
    from app.shared_css import pressed_css
    x = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/>'
         '<line x1="18" y1="6" x2="6" y2="18"/></svg>')
    body = """
    <div class="pill in" id="pill">
      <div class="body">
        <div class="title">Add <span class="tword" id="titleword"></span> to your dictionary?</div>
        <div class="pair">Replaces <span class="old" id="oldw"></span> when misheard</div>
      </div>
      <button class="add" onclick="api('autolearn_add')">Add to dictionary</button>
      <button class="x" title="Dismiss" onclick="api('autolearn_close')">{x}</button>
    </div>
    """.format(x=x)
    # "Add to dictionary" and the dismiss X (IDI-168). After _CSS so the press
    # beats `.add:hover{filter:brightness(1.25)}`.
    pressed = pressed_css([".add", ".x"])
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + pressed + "</style></head><body>"
        + body +
        "<script>" + _JS + "</script>"
        "</body></html>"
    )

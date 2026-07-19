"""
TransformWidget — the Mode B selection-transform pill (TRANSFORM_SWARM.md P2).

Clones autolearn_widget's non-activating cream pill (NSNonactivatingPanelMask @
NSScreenSaverWindowLevel, bottom-center, never steals key focus from the app
being edited). Two states:

  prompt  : Improvise | mic (speak the instruction) | typed instruction
  preview : the rewrite + Replace / Cancel   ← the agentic confirmation layer
            after Replace: a short-lived Undo (target-app Cmd+Z)

HARD GUARANTEES: separate from the dictation core; every action fails closed to
hiding the pill with the user's text untouched; clipboard already restored by
transform.capture_selection before the pill even opens.
"""
import json
import logging
import threading

from AppKit import (
    NSPanel, NSColor,
    NSWindowStyleMaskBorderless,
    NSScreen, NSBackingStoreBuffered, NSScreenSaverWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSMakeRect

from app import theme as _theme  # noqa: F401 — registers fonts for WKWebView

logger = logging.getLogger("verbal.transform_widget")

# Borderless NSPanels return NO from canBecomeKeyWindow, which silently kills
# TEXT INPUT inside the pill (no caret, no Enter/Esc). This subclass opts in;
# the nonactivating mask still keeps the app from stealing focus.
_PANEL_CLS = None


def _panel_class():
    global _PANEL_CLS
    if _PANEL_CLS is None:
        class _FlumeTransformPanel(NSPanel):
            def canBecomeKeyWindow(self):
                return True
        _PANEL_CLS = _FlumeTransformPanel
    return _PANEL_CLS

PANEL_W = 760
PANEL_H = 260

_ACTIONS = {"tf_improvise", "tf_prompt", "tf_speak", "tf_replace",
            "tf_cancel", "tf_undo", "tf_ready"}


class TransformWidget:
    def __init__(self, app):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._visible = False
        self._selection = None       # original selected text
        self._rewrite = None         # pending preview
        self._busy = False
        self._speaking = False
        self._page_ready = False
        self._pending_state = None   # last state emitted before the page loaded

    # ── window (main thread) ──────────────────────────────────────────────────
    def setup(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        sf = screen.frame()
        x = (sf.size.width - PANEL_W) / 2
        NSNonactivatingPanelMask = 1 << 7
        self._window = _panel_class().alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, 40, PANEL_W, PANEL_H),
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered, False)
        self._window.setLevel_(NSScreenSaverWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(False)
        self._window.setIgnoresMouseEvents_(False)
        self._window.setFloatingPanel_(True)
        self._window.setBecomesKeyOnlyIfNeeded_(True)   # typed prompt needs key on click
        self._window.setHidesOnDeactivate_(False)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary)
        try:
            self._build_webview()
        except Exception as e:
            logger.error("transform widget webview build failed: %s", e)

    def _build_webview(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController, WKUserScript,
        )
        from app.flume_web_dashboard import _Bridge, _SHIM
        from app.meeting_window import _webview_class   # acceptsFirstMouse (Rule #18)

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(_SHIM, 0, True))
        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)
        self._webview = _webview_class().alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H), config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)
        for key in (1,):
            try:
                self._webview.setValue_forKey_(False, "drawsBackground")
                self._webview.setOpaque_(False)
                self._webview.setWantsLayer_(True)
                self._webview.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
            except Exception:
                pass
        self._webview.loadHTMLString_baseURL_(transform_widget_html(), None)
        self._window.setContentView_(self._webview)

    # ── show / hide (main thread) ─────────────────────────────────────────────
    def show(self, selection):
        try:
            if not self._window:
                self.setup()
            if not self._window:
                return
            self._selection = selection
            self._rewrite = None
            self._busy = False
            self._window.orderFrontRegardless()
            self._visible = True
            self._emit({"state": "prompt",
                        "chars": len(selection),
                        "excerpt": selection[:160]})
        except Exception as e:
            logger.debug("transform widget show failed: %s", e)

    def hide(self):
        self._visible = False
        self._selection = None
        self._rewrite = None
        if self._speaking:
            self._stop_speak(discard=True)
        try:
            self._emit({"state": "hide"})
            if self._window:
                self._window.orderOut_(None)
        except Exception:
            pass

    @property
    def visible(self):
        return self._visible

    def _emit(self, data):
        # Never emit into a WKWebView before its JS is ready (Rule #18) — the
        # event silently drops and the pill shows BLANK on first open.
        if not self._page_ready:
            self._pending_state = data
            return
        try:
            if self._webview:
                self._webview.evaluateJavaScript_completionHandler_(
                    "if(window.VerbalTransform)window.VerbalTransform(%s);" % json.dumps(data), None)
        except Exception as e:
            logger.debug("transform widget eval failed: %s", e)

    def tf_ready(self):
        """Page-load handshake — flush the state emitted before load."""
        self._page_ready = True
        pending, self._pending_state = self._pending_state, None
        if pending:
            self._emit(pending)

    # ── bridge dispatch ───────────────────────────────────────────────────────
    def _dispatch(self, mid, method, args):
        if method not in _ACTIONS:
            return
        try:
            getattr(self, method)(*(args or []))
        except Exception as e:
            logger.error("transform widget action %s failed: %s", method, e)

    def _resolve(self, mid, result):
        pass  # fire-and-forget

    # ── actions ───────────────────────────────────────────────────────────────
    def _run_llm(self, fn, label):
        if self._busy:
            return                             # one run at a time
        if not self._selection:
            logger.info("transform run dropped: selection lost (visible=%s)", self._visible)
            self._emit({"state": "error",
                        "msg": "Selection was lost — close this and press the hotkey again."})
            return
        from app import transform as _t
        if len(self._selection) > _t.MAX_SELECTION_CHARS:
            self._emit({"state": "error",
                        "msg": "Selection too long (%dk chars, max %dk)." % (
                            len(self._selection) // 1000, _t.MAX_SELECTION_CHARS // 1000)})
            return
        self._busy = True
        sel = self._selection
        self._emit({"state": "busy", "label": label})

        def work():
            from app import transform
            out = fn(sel)
            def ui():
                self._busy = False
                if not self._visible:
                    return
                if out:
                    self._rewrite = out
                    self._emit({"state": "preview", "rewrite": out[:4000],
                                "truncated": len(out) > 4000})
                else:
                    self._emit({"state": "error",
                                "msg": "Couldn't transform — try again."})
            self.app._on_main(ui)
        threading.Thread(target=work, daemon=True).start()

    def tf_improvise(self):
        from app import transform
        self._run_llm(lambda s: transform.improvise(s, self.app.config), "Improvising…")

    def tf_prompt(self, instruction=""):
        instruction = (instruction or "").strip()
        if not instruction:
            return
        from app import transform
        self._run_llm(lambda s: transform.apply_instruction(s, instruction, self.app.config),
                      "Transforming…")

    # spoken prompt — reuses the dictation Recorder+Transcriber OUTSIDE a dictation
    def tf_speak(self):
        if getattr(self, "_transcribing", False):
            return                            # stop-click already in flight
        if self._speaking:
            # INSTANT feedback — the silent 2s gap here made users double-click,
            # which restarted the recording ("mic is not working")
            self._transcribing = True
            self._emit({"state": "busy", "label": "Transcribing\u2026"})
            self._stop_speak(discard=False)
            return
        try:
            if self.app._is_recording:
                self._emit({"state": "error", "msg": "Finish your dictation first."})
                return
            mt = self.app.meetings.active if getattr(self.app, "meetings", None) else None
            if mt is not None:
                # one mic stream process-wide during meetings (Rule #18) — the
                # spoken prompt would fight the meeting mic; typing still works
                self._emit({"state": "error", "msg": "Mic is busy with your meeting — type the instruction."})
                return
            self._speaking = True
            self._emit({"state": "speaking"})
            self.app.recorder.start()
        except Exception as e:
            logger.debug("tf_speak start failed: %s", e)
            self._speaking = False
            self._emit({"state": "prompt", "chars": len(self._selection or ""),
                        "excerpt": (self._selection or "")[:160]})

    def _stop_speak(self, discard):
        self._speaking = False
        try:
            audio = self.app.recorder.stop()
        except Exception:
            audio = None
        if discard or audio is None or not self._visible:
            self._transcribing = False
            if not discard and self._visible:
                self._emit({"state": "error", "msg": "Didn't catch that \u2014 try again."})
            return

        def work():
            try:
                from app.transcriber import transcribe_with_status
                text, status = transcribe_with_status(audio, self.app.config, self.app.recorder.sample_rate)
                instr = (text or "").strip()
                def ui():
                    self._transcribing = False
                    if not self._visible:
                        return
                    if status == "ok" and instr:
                        self._emit({"state": "heard", "instruction": instr})
                        self.tf_prompt(instr)
                    else:
                        self._emit({"state": "error", "msg": "Didn't catch that — try again."})
                self.app._on_main(ui)
            except Exception as e:
                logger.debug("spoken prompt failed: %s", e)
                def _err():
                    self._transcribing = False
                    self._emit({"state": "error", "msg": "Didn't catch that — try again."})
                self.app._on_main(_err)
        threading.Thread(target=work, daemon=True).start()

    def tf_replace(self):
        rewrite = self._rewrite
        if not rewrite:
            return
        original = self._selection

        def do():
            try:
                from app.injector import inject_text
                # the selection is still highlighted in the target app: paste replaces it
                inject_text(rewrite)
                self._selection = original          # kept for Undo
                self._rewrite = None
                self._emit({"state": "done"})
                def later():
                    if self._visible and self._rewrite is None:
                        self.hide()
                threading.Timer(6.0, lambda: self.app._on_main(later)).start()
            except Exception as e:
                logger.error("transform replace failed: %s", e)
                self._emit({"state": "error", "msg": "Replace failed — text untouched."})
        self.app._on_main(do)

    def tf_undo(self):
        from app import transform
        transform.undo_in_target()
        self.hide()

    def tf_cancel(self):
        self.hide()


# ── HTML (cream pill; same card language as the auto-learn widget) ───────────
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#EADFCE;--ink:#2a1f18;--ink-mut:rgba(42,31,24,.58);--dark:#1a1512;
--line:rgba(42,31,24,.14)}
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
.mic.on{background:var(--dark);color:var(--cream);border-color:var(--dark)}
.mic svg{width:14px;height:14px}
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
window.VerbalTransform=function(d){
  d=d||{}; S.state=d.state;
  if(d.state!=='speaking'){ var mb=document.getElementById('micBtn'); if(mb) mb.className='mic'; }
  if(d.state==='hide'){ show(''); return; }
  if(d.state==='prompt'){
    document.getElementById('exc').textContent=d.excerpt||'';
    document.getElementById('chars').textContent=(d.chars||0)+' chars selected';
    var i=document.getElementById('pin'); i.value='';
    document.getElementById('micBtn').className='mic';
    document.getElementById('perr').textContent='';
    show('pPrompt');
  }
  else if(d.state==='speaking'){ document.getElementById('micBtn').className='mic on';
    document.getElementById('perr').textContent='Listening — click the mic again when done.'; }
  else if(d.state==='heard'){ document.getElementById('pin').value=d.instruction||''; }
  else if(d.state==='busy'){ document.getElementById('busyLabel').textContent=d.label||'Working…'; show('pBusy'); }
  else if(d.state==='preview'){
    document.getElementById('pvText').textContent=(d.rewrite||'')+(d.truncated?' …':'');
    show('pPreview');
  }
  else if(d.state==='done'){ show('pDone'); }
  else if(d.state==='error'){
    if(S.prev==='preview'){ show('pPreview'); }
    else { show('pPrompt'); }
    document.getElementById('perr').textContent=d.msg||'Something went wrong.';
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
      <div class="row"><span class="err" id="perr"></span></div>
    </div>
    <div class="pill" id="pBusy">
      <div class="row"><span class="spin"></span><span class="hint" id="busyLabel">Working…</span></div>
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
    """.format(x=x, mic=mic)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + "</style></head><body>"
        + body +
        "<script>" + _JS + "</script>"
        "</body></html>"
    )

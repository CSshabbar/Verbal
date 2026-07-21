"""
Meeting-detected prompt — a floating, NON-ACTIVATING pill (Granola-style) that
appears when Flume notices a call in progress and offers one-click "Take notes".

Same non-activating NSPanel + WKWebView recipe as app/autolearn_widget.py: it must
NEVER steal focus from the Zoom/Meet/Teams window you're in. Buttons post back
through the shared _Bridge:
  api('md_take')    → app._meeting_detect_result(True)   (start capturing now)
  api('md_dismiss') → app._meeting_detect_result(False)  (ignore this call)

Interface used by main.py:
  w = MeetingPrompt(app)
  w.show("Chrome")   # pop the pill naming the source
  w.hide()
  w.visible
"""
import json
import logging

from AppKit import (
    NSPanel, NSColor,
    NSWindowStyleMaskBorderless,
    NSScreen, NSBackingStoreBuffered, NSScreenSaverWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from Foundation import NSMakeRect

from app import theme as _theme  # noqa: F401 — registers Geist/JBM for WKWebView

logger = logging.getLogger("verbal.meeting_prompt")

PANEL_W = 620
PANEL_H = 120

_ACTIONS = {"md_take", "md_dismiss"}


class MeetingPrompt:
    def __init__(self, app=None):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._visible = False

    # ── window / webview (lazy; main thread) ──────────────────────────────────
    def setup(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        sf = screen.frame()
        x = (sf.size.width - PANEL_W) / 2
        y = 40  # bottom-center, the Flume pill home

        NSNonactivatingPanelMask = 1 << 7
        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, PANEL_W, PANEL_H),
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered, False)
        self._window.setLevel_(NSScreenSaverWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(False)
        self._window.setIgnoresMouseEvents_(False)   # buttons need clicks
        self._window.setFloatingPanel_(True)
        self._window.setBecomesKeyOnlyIfNeeded_(True)
        self._window.setHidesOnDeactivate_(False)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary)
        try:
            self._build_webview()
        except Exception as e:
            logger.error("meeting prompt webview build failed: %s", e)

    def _build_webview(self):
        from WebKit import (
            WKWebView, WKWebViewConfiguration, WKUserContentController, WKUserScript,
        )
        from app.flume_web_dashboard import _Bridge, _SHIM

        ucc = WKUserContentController.alloc().init()
        self._bridge = _Bridge.alloc().initWithDashboard_(self)
        ucc.addScriptMessageHandler_name_(self._bridge, "flume")
        ucc.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(_SHIM, 0, True))

        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(ucc)

        rect = NSMakeRect(0, 0, PANEL_W, PANEL_H)
        self._webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)
        for setter in (
                lambda: self._webview.setValue_forKey_(False, "drawsBackground"),
                lambda: self._webview.setOpaque_(False)):
            try:
                setter()
            except Exception:
                pass
        try:
            self._webview.setWantsLayer_(True)
            self._webview.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
            self._webview.layer().setOpaque_(False)
        except Exception:
            pass
        self._webview.loadHTMLString_baseURL_(meeting_prompt_html(), None)
        self._window.setContentView_(self._webview)

    # ── show / hide ───────────────────────────────────────────────────────────
    def show(self, source):
        try:
            if not self._window:
                self.setup()
            if not self._window:
                return
            self._window.orderFrontRegardless()
            self._visible = True
            js = "if(window.VerbalMeetingDetect)window.VerbalMeetingDetect(%s);" % json.dumps(
                {"source": str(source or "")})
            if self._webview:
                try:
                    self._webview.evaluateJavaScript_completionHandler_(js, None)
                except Exception as e:
                    logger.debug("meeting prompt eval failed: %s", e)
        except Exception as e:
            logger.debug("meeting prompt show failed: %s", e)

    def hide(self):
        self._visible = False
        try:
            if self._webview:
                self._webview.evaluateJavaScript_completionHandler_(
                    "if(window.VerbalMeetingDetectHide)window.VerbalMeetingDetectHide();", None)
            if self._window:
                self._window.orderOut_(None)
        except Exception:
            pass

    @property
    def visible(self):
        return self._visible

    # ── bridge dispatch (button clicks) ──────────────────────────────────────
    def _dispatch(self, mid, method, args):
        if method in _ACTIONS:
            try:
                getattr(self, method)()
            except Exception as e:
                logger.error("meeting prompt action %s failed: %s", method, e)

    def _resolve(self, mid, result):
        pass  # fire-and-forget

    def md_take(self):
        self.hide()
        if self.app:
            self.app._on_main(lambda: self.app._meeting_detect_result(True))

    def md_dismiss(self):
        self.hide()
        if self.app:
            self.app._on_main(lambda: self.app._meeting_detect_result(False))


# ── HTML ────────────────────────────────────────────────────────────────────
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#1b1714;--panel:#211d19;--tx:#F5EDE4;--mut:rgba(245,237,228,.52);
--sage:#A8BD9A;--sage-ink:#16201a}
html,body{height:100%;background:transparent}
body{font-family:'Geist',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
display:flex;align-items:flex-end;justify-content:center;overflow:visible;padding:14px 40px 32px}
.pill{display:flex;align-items:center;gap:14px;background:var(--panel);
border:1px solid rgba(245,237,228,.08);border-radius:16px;padding:11px 11px 11px 16px;
box-shadow:0 18px 46px rgba(0,0,0,.5);max-width:560px;
opacity:0;transform:translateY(10px) scale(.97)}
.pill.in{animation:pin .24s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes pin{to{opacity:1;transform:none}}
.pill.out{animation:pout .16s ease forwards}
@keyframes pout{to{opacity:0;transform:translateY(8px) scale(.97)}}
.mark{width:34px;height:34px;border-radius:10px;background:rgba(168,189,154,.16);
display:flex;align-items:center;justify-content:center;flex:none}
.mark svg{width:18px;height:18px;stroke:var(--sage)}
.body{display:flex;flex-direction:column;gap:2px;min-width:0}
.title{font:600 13.5px 'Geist';color:var(--tx);letter-spacing:-.01em;white-space:nowrap}
.sub{font:500 11.5px 'JetBrains Mono';color:var(--mut);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;max-width:320px}
.take{border:0;border-radius:11px;padding:9px 16px;background:var(--sage);color:var(--sage-ink);
cursor:pointer;font:700 12.5px 'Geist';flex:none;margin-left:6px;white-space:nowrap;
transition:filter .12s}
.take:hover{filter:brightness(1.06)}
.x{width:28px;height:28px;border-radius:50%;border:0;background:rgba(245,237,228,.07);
color:var(--tx);cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none;
transition:background .12s}
.x:hover{background:rgba(245,237,228,.15)}
.x svg{width:11px;height:11px}
"""

_JS = """
function api(m){ try{ return window.pywebview.api[m](); }catch(e){} }
window.VerbalMeetingDetect=function(d){
  d=d||{};
  document.getElementById('src').textContent = d.source ? ('In '+d.source) : 'Ready to capture';
  var c=document.getElementById('pill');
  c.classList.remove('out'); c.classList.remove('in'); void c.offsetWidth; c.classList.add('in');
};
window.VerbalMeetingDetectHide=function(){
  var c=document.getElementById('pill'); if(c){c.classList.remove('in');c.classList.add('out');}
};
"""


def meeting_prompt_html():
    from app.fonts_css import web_font_css
    x = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/>'
         '<line x1="18" y1="6" x2="6" y2="18"/></svg>')
    mic = ('<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/>'
           '<path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="17" x2="12" y2="21"/></svg>')
    body = """
    <div class="pill in" id="pill">
      <div class="mark">{mic}</div>
      <div class="body">
        <div class="title">Meeting detected</div>
        <div class="sub" id="src">Ready to capture</div>
      </div>
      <button class="take" onclick="api('md_take')">Take notes</button>
      <button class="x" title="Not now" onclick="api('md_dismiss')">{x}</button>
    </div>
    """.format(mic=mic, x=x)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>" + web_font_css() + _CSS + "</style></head><body>"
        + body +
        "<script>" + _JS + "</script>"
        "</body></html>"
    )

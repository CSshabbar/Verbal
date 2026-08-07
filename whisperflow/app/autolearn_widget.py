"""
Auto-learn confirmation widget — a beautiful, floating, NON-ACTIVATING panel
that asks "learn this correction?" without stealing focus from the app you were
typing in (unlike a native rumps.alert, which activates Verbal).

Modelled on app/overlay.py: a borderless non-activating NSPanel hosting a
WKWebView, driven from Python via window.VerbalAutolearn(data) and posting button
clicks back through the shared _Bridge (api('autolearn_add') / 'autolearn_close').

Interface used by main.py:
  widget = AutoLearnWidget(app)
  widget.show(old, new)     # display the card for a single correction
  widget.hide()
On a button click the widget calls app._autolearn_result(old, new, added: bool)
on the main thread.
"""
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

from app import theme as _theme  # noqa: F401 — registers Geist/JBM for WKWebView

logger = logging.getLogger("verbal.autolearn_widget")

# Wide/short like the recording overlay panel so the pill sits bottom-center and
# its shadow/rounded corners are never clipped (the panel itself is transparent).
PANEL_W = 720
PANEL_H = 120

_ACTIONS = {"autolearn_add", "autolearn_close"}


class AutoLearnWidget:
    def __init__(self, app=None):
        self.app = app
        self._window = None
        self._webview = None
        self._bridge = None
        self._visible = False
        self._pending = None          # (old, new)
        self._dismiss_token = 0

    # ── window / webview (lazy; must run on the main thread) ───────────────────
    def setup(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        sf = screen.frame()
        x = (sf.size.width - PANEL_W) / 2
        y = 40   # bottom-center, exactly where the recording overlay appears

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
            logger.error("autolearn widget webview build failed: %s", e)

    def _build_webview(self):
        from WebKit import (
            WKWebViewConfiguration, WKUserContentController, WKUserScript,
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

        rect = NSMakeRect(0, 0, PANEL_W, PANEL_H)
        self._webview = _webview_class().alloc().initWithFrame_configuration_(rect, config)
        self._webview.setAutoresizingMask_(0x02 | 0x10)
        try:
            self._webview.setValue_forKey_(False, "drawsBackground")
        except Exception:
            pass
        try:
            self._webview.setOpaque_(False)
        except Exception:
            pass
        try:
            self._webview.setWantsLayer_(True)
            self._webview.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
            self._webview.layer().setOpaque_(False)
        except Exception:
            pass
        self._webview.loadHTMLString_baseURL_(autolearn_widget_html(), None)
        self._window.setContentView_(self._webview)

    # ── show / hide ────────────────────────────────────────────────────────────
    def show(self, old, new):
        """Display the confirm card for one correction (main thread)."""
        try:
            if not self._window:
                self.setup()
            if not self._window:
                return
            # A second correction arriving while a card is still up used to
            # simply overwrite `_pending` — the pre-empted word never reached
            # `record_offered`, so it escaped the anti-nag memory and could be
            # offered again later (Hard Rule #9). Retire it as a dismissal
            # first (IDI-178).
            prev = self._pending
            if prev and self._visible and tuple(prev) != (old, new):
                self._retire(prev)
            self._pending = (old, new)
            self._window.orderFrontRegardless()
            self._visible = True
            import json
            data = json.dumps({"old": old, "new": new})
            js = "if(window.VerbalAutolearn)window.VerbalAutolearn(%s);" % data
            if self._webview:
                try:
                    self._webview.evaluateJavaScript_completionHandler_(js, None)
                except Exception as e:
                    logger.debug("autolearn widget eval failed: %s", e)
            # Auto-dismiss (treated as close) if left untouched, so it never lingers.
            self._dismiss_token += 1
            token = self._dismiss_token

            def _auto():
                if self._dismiss_token != token or not self._visible:
                    return
                if self.app:
                    self.app._on_main(self.autolearn_close)
                else:
                    self.autolearn_close()
            threading.Timer(20.0, _auto).start()
        except Exception as e:
            logger.debug("autolearn widget show failed: %s", e)

    def hide(self):
        self._dismiss_token += 1
        self._visible = False
        try:
            if self._webview:
                self._webview.evaluateJavaScript_completionHandler_(
                    "if(window.VerbalAutolearnHide)window.VerbalAutolearnHide();", None)
            if self._window:
                self._window.orderOut_(None)
        except Exception:
            pass

    @property
    def visible(self):
        return self._visible

    # ── bridge dispatch (button clicks) ───────────────────────────────────────
    def _dispatch(self, mid, method, args):
        if method in _ACTIONS:
            try:
                getattr(self, method)()
            except Exception as e:
                logger.error("autolearn widget action %s failed: %s", method, e)

    def _resolve(self, mid, result):
        pass  # fire-and-forget

    def _retire(self, pending, added=False):
        """Report one offer's outcome exactly once (main thread)."""
        if not (pending and self.app):
            return
        old, new = pending
        self.app._on_main(lambda: self.app._autolearn_result(old, new, added))

    def autolearn_add(self):
        # Latch: `_autolearn_result` is deferred onto the UI queue, so a fast
        # double-click used to fire it twice — two `play_added()` chimes and two
        # dictionary pushes for one word (IDI-178). Taking `_pending` here makes
        # every later click (and the 20 s auto-dismiss) a no-op.
        pending, self._pending = self._pending, None
        if pending is None:
            return
        self.hide()
        self._retire(pending, added=True)

    def autolearn_close(self):
        pending, self._pending = self._pending, None
        if pending is None:
            self.hide()
            return
        self.hide()
        self._retire(pending, added=False)


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

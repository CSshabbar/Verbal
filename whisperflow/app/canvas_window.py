"""
Verbal Canvas — shared clipboard that syncs across all devices in real time.
Users paste text here; it instantly appears on all connected devices.
"""

import logging
import threading
import time
import pyperclip

from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSTextField, NSScrollView,
    NSButton, NSScreen, NSApplication, NSTimer, NSTextView,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskFullSizeContentView,
    NSBackingStoreBuffered, NSRoundedBezelStyle,
    NSBezierPath, NSTextAlignmentLeft,
    NSRunLoop, NSDefaultRunLoopMode,
    NSAttributedString, NSForegroundColorAttributeName, NSFontAttributeName,
    NSLineBreakByWordWrapping,
)
from Foundation import NSMakeRect, NSMakeSize, NSString, NSMakePoint, NSObject, NSMakeRange
import objc

logger = logging.getLogger("verbal.canvas")

# ── Palette (matches dashboard) ───────────────────────────────────────────────
def _hex(h, a=1.0):
    h = h.lstrip("#")
    r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)

H_BG      = _hex("1A1917")
H_TEXT    = _hex("F2EFE9")
H_MUTED   = _hex("7A7570")
H_ACCENT  = _hex("E05A2B")
S_BG      = _hex("F2EFE9")
CARD_TEXT = _hex("2C2A27")
CARD_SUB  = _hex("9A9590")

SAVE_DEBOUNCE = 0.8   # seconds after last keystroke before saving


# ── Canvas header view ────────────────────────────────────────────────────────
class CanvasHeaderView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CanvasHeaderView, self).initWithFrame_(frame)
        if self is None: return None
        self._status = ""
        self._words  = 0
        self._chars  = 0
        return self

    def setStatus_(self, s):
        self._status = s
        self.setNeedsDisplay_(True)

    def clearStatus_(self, timer):
        self._status = ""
        self.setNeedsDisplay_(True)

    def setStats_chars_(self, words, chars):
        self._words = words
        self._chars = chars
        self.setNeedsDisplay_(True)

    def isFlipped(self): return True

    def drawRect_(self, rect):
        w = self.bounds().size.width
        h = self.bounds().size.height

        H_BG.set()
        NSBezierPath.fillRect_(self.bounds())

        # ── Logo mark ─────────────────────────────────────────────────────
        NSString.stringWithString_("✳").drawAtPoint_withAttributes_(
            NSMakePoint(24, 14),
            {"NSFont": NSFont.systemFontOfSize_weight_(20, 0.2), "NSColor": H_TEXT}
        )

        # Canvas icon (grid symbol) next to logo
        NSString.stringWithString_("⊞").drawAtPoint_withAttributes_(
            NSMakePoint(50, 16),
            {"NSFont": NSFont.systemFontOfSize_weight_(16, 0.2), "NSColor": H_ACCENT}
        )

        # Title
        NSString.stringWithString_("Canvas").drawAtPoint_withAttributes_(
            NSMakePoint(74, 14),
            {"NSFont": NSFont.systemFontOfSize_weight_(18, 0.7), "NSColor": H_TEXT}
        )

        # Subtitle
        NSString.stringWithString_("Shared clipboard · syncs to all devices").drawAtPoint_withAttributes_(
            NSMakePoint(24, 42),
            {"NSFont": NSFont.systemFontOfSize_weight_(11, -0.3), "NSColor": H_MUTED}
        )

        # Stats row
        sf = NSFont.systemFontOfSize_weight_(11, 0.4)
        sx = 24
        sy = 64
        for val, label in [(str(self._words), " words"), (str(self._chars), " chars")]:
            NSString.stringWithString_(val).drawAtPoint_withAttributes_(
                NSMakePoint(sx, sy),
                {"NSFont": NSFont.systemFontOfSize_weight_(11, 0.6), "NSColor": H_ACCENT}
            )
            vw = NSString.stringWithString_(val).sizeWithAttributes_(
                {"NSFont": NSFont.systemFontOfSize_weight_(11, 0.6)}).width
            NSString.stringWithString_(label).drawAtPoint_withAttributes_(
                NSMakePoint(sx + vw, sy), {"NSFont": sf, "NSColor": H_MUTED}
            )
            lw = NSString.stringWithString_(label).sizeWithAttributes_({"NSFont": sf}).width
            sx += vw + lw + 16

        # Status
        if self._status:
            status_color = H_ACCENT if "Synced" in self._status or "↓" in self._status else H_MUTED
            NSString.stringWithString_(self._status).drawAtPoint_withAttributes_(
                NSMakePoint(sx + 8, sy),
                {"NSFont": NSFont.systemFontOfSize_weight_(10, -0.3), "NSColor": status_color}
            )

        # Bottom divider
        _hex("FFFFFF", 0.06).set()
        NSBezierPath.fillRect_(NSMakeRect(0, h - 1, w, 1))


# ── Delegate to detect text changes ──────────────────────────────────────────
class CanvasDelegate(NSObject):
    def initWithCallback_(self, cb):
        self = objc.super(CanvasDelegate, self).init()
        if self is None: return None
        self._cb = cb
        return self

    def textDidChange_(self, notification):
        if self._cb:
            self._cb()


# ── Main canvas window ────────────────────────────────────────────────────────
class CanvasWindow:
    WIN_W = 680
    WIN_H = 560

    def __init__(self, config: dict):
        self._window      = None
        self._config      = config
        self._header      = None
        self._text_view   = None
        self._delegate    = None
        self._save_timer  = None
        self._is_remote   = False   # flag: don't re-save incoming remote content
        self._sync_client = None

    def show(self):
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            return

        self._build_window()
        self._load_from_supabase()
        self._start_sync()

        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def _build_window(self):
        screen = NSScreen.mainScreen()
        sf     = screen.frame() if screen else NSMakeRect(0, 0, 1440, 900)
        x      = (sf.size.width  - self.WIN_W) / 2
        y      = (sf.size.height - self.WIN_H) / 2

        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, self.WIN_W, self.WIN_H), style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("Verbal Canvas")
        self._window.setMinSize_(NSMakeSize(480, 400))
        self._window.setBackgroundColor_(H_BG)

        cv = self._window.contentView()
        HEADER_H = 100

        # Header
        self._header = CanvasHeaderView.alloc().initWithFrame_(
            NSMakeRect(0, self.WIN_H - HEADER_H, self.WIN_W, HEADER_H)
        )
        self._header.setAutoresizingMask_(0x02)
        cv.addSubview_(self._header)

        # Action buttons — positioned inside header, right side, vertically centered
        btn_y = self.WIN_H - HEADER_H + 20   # 20px from top of header
        btn_x_start = self.WIN_W - 86 * 3 - 8
        for i, (title, cb, danger) in enumerate([
            ("⎘  Copy all",  self._copy_all,         False),
            ("⌘V  Paste",    self._paste_clipboard,  False),
            ("✕  Clear",     self._clear,             True),
        ]):
            self._add_header_btn(cv, title, self.WIN_W - (3 - i) * 90 + (i * 4), btn_y, cb, danger=danger)

        # Sheet (warm off-white)
        sheet_h = self.WIN_H - HEADER_H
        sheet   = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, self.WIN_W, sheet_h))
        sheet.setWantsLayer_(True)
        sheet.layer().setBackgroundColor_(S_BG.CGColor())
        sheet.layer().setCornerRadius_(20)
        sheet.layer().setMaskedCorners_(0b0011)
        sheet.setAutoresizingMask_(0x12 | 0x10)
        cv.addSubview_(sheet)

        # Scroll + text view
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, 0, self.WIN_W, sheet_h)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setDrawsBackground_(False)
        scroll.setAutoresizingMask_(0x12 | 0x10)

        self._text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, self.WIN_W, sheet_h)
        )
        self._text_view.setFont_(NSFont.systemFontOfSize_weight_(15, -0.3))
        self._text_view.setTextColor_(CARD_TEXT)
        self._text_view.setBackgroundColor_(NSColor.clearColor())
        self._text_view.setDrawsBackground_(False)
        self._text_view.setEditable_(True)
        self._text_view.setRichText_(False)
        self._text_view.setAutomaticQuoteSubstitutionEnabled_(False)
        self._text_view.setAutomaticDashSubstitutionEnabled_(False)
        self._text_view.setTextContainerInset_((24, 20))
        self._text_view.textContainer().setLineFragmentPadding_(0)

        # Placeholder-style hint when empty
        self._text_view.setString_(
            "Paste or type anything here…\n\nIt syncs instantly to all your devices."
        )
        self._text_view.setTextColor_(CARD_SUB)

        self._delegate = CanvasDelegate.alloc().initWithCallback_(self._on_text_change)
        self._text_view.setDelegate_(self._delegate)

        scroll.setDocumentView_(self._text_view)
        sheet.addSubview_(scroll)

    def _add_header_btn(self, parent, title, x, y, cb, danger=False):
        from app.dashboard import _d, _attr
        d   = _d(cb)
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, 80, 26))
        btn.setBordered_(False)
        btn.setWantsLayer_(True)
        btn.layer().setCornerRadius_(8)
        btn.layer().setBackgroundColor_(
            _hex("E05A2B", 0.15).CGColor() if danger else _hex("FFFFFF", 0.08).CGColor()
        )
        btn.setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(
                title,
                {
                    NSForegroundColorAttributeName: H_ACCENT if danger else H_TEXT,
                    NSFontAttributeName: NSFont.systemFontOfSize_weight_(11, 0.5),
                }
            )
        )
        btn.setTarget_(d)
        btn.setAction_(objc.selector(d.fire_, signature=b'v@:@'))
        parent.addSubview_(btn)

    # ── Text change ───────────────────────────────────────────────────────────
    def _on_text_change(self):
        if self._is_remote:
            self._is_remote = False
            return
        text = self._get_text()
        self._update_stats(text)
        self._header.setStatus_("Saving…")

        if self._save_timer:
            self._save_timer.invalidate()
        self._save_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            SAVE_DEBOUNCE, self, "doSave:", None, False
        )

    def doSave_(self, timer):
        text = self._get_text()
        threading.Thread(target=self._save_to_supabase, args=(text,), daemon=True).start()

    def _get_text(self) -> str:
        if self._text_view:
            return self._text_view.string() or ""
        return ""

    def _update_stats(self, text: str):
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        if self._header:
            self._header.setStats_chars_(words, chars)

    # ── Supabase ──────────────────────────────────────────────────────────────
    def _save_to_supabase(self, text: str):
        try:
            import httpx
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            user_id     = self._config.get("sync_user_id", "")
            device_name = self._config.get("sync_device_name", "Mac")
            if not user_id:
                return
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal,resolution=merge-duplicates",
                },
                json={"user_id": user_id, "content": text, "device_name": device_name,
                      "updated_at": __import__('datetime').datetime.utcnow().isoformat()},
                timeout=5,
            )
            if self._header:
                self._header.setStatus_("Saved ✓")
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    2.0, self._header, "clearStatus:", None, False
                )
        except Exception as e:
            logger.error(f"Canvas save error: {e}")

    def _load_from_supabase(self):
        threading.Thread(target=self._fetch_canvas, daemon=True).start()

    def _fetch_canvas(self):
        try:
            import httpx
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            user_id = self._config.get("sync_user_id", "")
            if not user_id:
                return
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/canvas",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"user_id": f"eq.{user_id}", "select": "content"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and data[0].get("content"):
                    content = data[0]["content"]
                    self._set_text_remote(content)
        except Exception as e:
            logger.error(f"Canvas fetch error: {e}")

    def _set_text_remote(self, text: str):
        """Set text from remote — must run on main thread."""
        def do():
            if self._text_view:
                self._is_remote = True
                self._text_view.setString_(text)
                self._text_view.setTextColor_(CARD_TEXT)
                self._update_stats(text)
        from AppKit import NSApplication
        NSApplication.sharedApplication().performSelectorOnMainThread_withObject_waitUntilDone_(
            "doNothing:", None, False
        )
        # Use timer to run on main thread
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.0, self, "applyRemoteText:", text, False
        )

    def applyRemoteText_(self, timer):
        text = timer.userInfo()
        if self._text_view and text:
            self._is_remote = True
            self._text_view.setString_(text)
            self._text_view.setTextColor_(CARD_TEXT)
            self._update_stats(text)
            if self._header:
                self._header.setStatus_("↓ Synced")

    def _start_sync(self):
        """Listen for canvas changes from other devices via WebSocket."""
        user_id = self._config.get("sync_user_id", "")
        device_name = self._config.get("sync_device_name", "Mac")
        if not user_id:
            return
        threading.Thread(
            target=self._listen_canvas,
            args=(user_id, device_name),
            daemon=True
        ).start()

    def _listen_canvas(self, user_id: str, device_name: str):
        import json, websocket, time
        from app.sync import WS_URL, SUPABASE_KEY

        def on_open(ws):
            ws.send(json.dumps({
                "topic": "realtime:*",
                "event": "phx_join",
                "payload": {
                    "config": {
                        "postgres_changes": [{
                            "event":  "*",
                            "schema": "public",
                            "table":  "canvas",
                            "filter": f"user_id=eq.{user_id}",
                        }]
                    }
                },
                "ref": "canvas_1",
            }))

        def on_message(ws, raw):
            try:
                msg   = json.loads(raw)
                event = msg.get("event", "")
                if event == "postgres_changes":
                    record = msg.get("payload", {}).get("data", {}).get("record", {})
                    if record.get("device_name") == device_name:
                        return   # own update
                    content = record.get("content", "")
                    if content is not None:
                        self._set_text_remote(content)
            except Exception as e:
                logger.error(f"Canvas WS message error: {e}")

        def on_error(ws, e): logger.error(f"Canvas WS error: {e}")
        def on_close(ws, *a): pass

        while True:
            try:
                ws = websocket.WebSocketApp(
                    WS_URL,
                    header={"Authorization": f"Bearer {SUPABASE_KEY}"},
                    on_open=on_open, on_message=on_message,
                    on_error=on_error, on_close=on_close,
                )
                ws.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as e:
                logger.error(f"Canvas WS crashed: {e}")
            time.sleep(5)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _copy_all(self):
        text = self._get_text()
        if text:
            pyperclip.copy(text)
            if self._header:
                self._header.setStatus_("Copied ✓")

    def _paste_clipboard(self):
        try:
            text = pyperclip.paste()
            if not text:
                return
            current = self._get_text()
            new_text = f"{current}\n\n{text}" if current.strip() else text
            if self._text_view:
                self._text_view.setString_(new_text)
                self._text_view.setTextColor_(CARD_TEXT)
                self._update_stats(new_text)
                self._on_text_change()
        except Exception as e:
            logger.error(f"Canvas paste error: {e}")

    def _clear(self):
        if self._text_view:
            self._text_view.setString_("")
            self._update_stats("")
            threading.Thread(target=self._save_to_supabase, args=("",), daemon=True).start()

    def close(self):
        if self._window:
            self._window.close()
            self._window = None

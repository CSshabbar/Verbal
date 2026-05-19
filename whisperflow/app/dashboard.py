import logging
import math
import threading
import time
import datetime as _dt
import pyperclip

from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSTextField, NSScrollView,
    NSButton, NSScreen, NSApplication, NSTimer, NSTrackingArea,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered, NSRoundedBezelStyle,
    NSLineBreakByTruncatingTail, NSLineBreakByWordWrapping,
    NSBezierPath, NSTextAlignmentLeft, NSTextAlignmentCenter, NSTextAlignmentRight,
    NSRunLoop, NSDefaultRunLoopMode,
    NSTrackingMouseEnteredAndExited, NSTrackingActiveAlways, NSTrackingInVisibleRect,
    NSAttributedString, NSForegroundColorAttributeName, NSFontAttributeName,
    NSParagraphStyleAttributeName, NSMutableParagraphStyle,
)
from Foundation import NSMakeRect, NSMakeSize, NSString, NSMakePoint, NSObject, NSPointInRect
import objc

logger = logging.getLogger("verbal.dashboard")

# Import config helpers for rich history entries
def _entry_text(e): return e.get("text","") if isinstance(e,dict) else str(e)
def _entry_app(e):  return e.get("app","")  if isinstance(e,dict) else ""


# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)

def _hex(h, a=1.0):
    h = h.lstrip("#")
    r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    return _c(r, g, b, a)

def _attr(text, color, font):
    return NSAttributedString.alloc().initWithString_attributes_(
        text, {NSForegroundColorAttributeName: color, NSFontAttributeName: font}
    )


# ── Exact palette from the reference ─────────────────────────────────────────
# Hero (dark zone)
H_BG        = _hex("1A1917")      # warm near-black
H_TEXT      = _hex("F2EFE9")      # warm off-white
H_MUTED     = _hex("7A7570")      # muted warm gray
H_ACCENT    = _hex("E05A2B")      # orange (the key accent)
H_GREEN     = _hex("3DAA6E")      # green for positive stats

# Sheet (light zone)
S_BG        = _hex("F2EFE9")      # warm cream — the sheet background
CARD_BG     = _hex("FFFFFF")      # pure white cards
CARD_PIN_BG = _hex("FFF7F2")      # very subtle warm tint for pinned
CARD_TEXT   = _hex("2C2A27")      # slightly softer than pure black — more elegant
CARD_SUB    = _hex("9A9590")      # muted subtitle
CARD_BORDER = _hex("EBEBEB")      # barely-there border

KEYCODE_MAP = {
    54: "Right ⌘",
    55: "Left ⌘",
    56: "Left ⇧",
    57: "Caps Lock",
    58: "Left ⌥",
    59: "Left ⌃",
    60: "Right ⇧",
    61: "Right ⌥",
    62: "Right ⌃",
    36: "Return",
    48: "Tab",
    49: "Spacebar",
    51: "Delete",
    53: "Escape",
    123: "Left Arrow",
    124: "Right Arrow",
    125: "Down Arrow",
    126: "Up Arrow",
    96: "F5", 97: "F6", 98: "F7", 99: "F3", 100: "F8", 101: "F9", 
    109: "F10", 103: "F11", 111: "F12",
}

def _keycode_to_name(code):
    return KEYCODE_MAP.get(code, f"Key {code}")
PIN_ACCENT  = _hex("E05A2B")      # orange for pin state
ICON_GRAY   = _hex("EFEFED")      # icon box bg (inactive)
ICON_ORANGE = _hex("E05A2B")      # icon box bg (active/pinned)

# Layout
WIN_W       = 900          # wider horizontal layout
WIN_H       = 660
HERO_H      = 230
SHEET_R     = 28
PAD         = 20
SIDEBAR_W   = 200          # permanent left sidebar
CARD_H      = 66
CARD_GAP    = 8
CARD_R      = 14
ICON_S      = 42
BTN_S       = 28

# State
_copy_cbs   = {}
_expanded   = set()
_delegates  = []          # strong refs


# ── NSObject delegate ─────────────────────────────────────────────────────────
class _Delegate(NSObject):
    def initWithCb_(self, cb):
        self = objc.super(_Delegate, self).init()
        if self is None: return None
        self._cb = cb
        return self
    def fire_(self, sender):
        if self._cb: self._cb()

def _d(cb):
    obj = _Delegate.alloc().initWithCb_(cb)
    _delegates.append(obj)
    return obj


# ── Copy handler ──────────────────────────────────────────────────────────────
class CopyHandler(NSObject):
    def handleCopy_(self, sender):
        text = _copy_cbs.get(sender.tag(), "")
        if not text: return
        pyperclip.copy(text)
        sender.setAttributedTitle_(
            _attr("✓", _hex("3DAA6E"), NSFont.systemFontOfSize_weight_(14, 0.7)))
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.5, self, "resetCopy:", sender, False)

    def resetCopy_(self, timer):
        btn = timer.userInfo()
        if btn:
            btn.setAttributedTitle_(
                _attr("⎘", _hex("6A6560"), NSFont.systemFontOfSize_weight_(15, 0.4)))

_copy_handler = None
def _ch():
    global _copy_handler
    if _copy_handler is None:
        _copy_handler = CopyHandler.alloc().init()
    return _copy_handler


# ── Card view ─────────────────────────────────────────────────────────────────
class CardView(NSView):

    def initWithFrame_text_index_pinned_appName_onPin_onExpand_onEdit_(
            self, frame, text, index, pinned, app_name, on_pin, on_expand, on_edit):
        self = objc.super(CardView, self).initWithFrame_(frame)
        if self is None: return None
        self._text      = text
        self._index     = index
        self._pinned    = pinned
        self._app_name  = app_name
        self._on_pin    = on_pin
        self._on_expand = on_expand
        self._on_edit   = on_edit
        self._hovered   = False
        self._editing   = False
        self._edit_field = None
        self._ekey      = ("p" if pinned else "h", text)
        self._expanded  = self._ekey in _expanded
        self.setWantsLayer_(True)
        self._style()
        self._build()
        self._track()
        return self

    def _style(self):
        bg = CARD_PIN_BG if self._pinned else CARD_BG
        self.layer().setBackgroundColor_(bg.CGColor())
        self.layer().setCornerRadius_(CARD_R)
        self.layer().setShadowColor_(NSColor.blackColor().CGColor())
        self.layer().setShadowOpacity_(0.09 if self._hovered else 0.05)
        self.layer().setShadowRadius_(12 if self._hovered else 6)
        self.layer().setShadowOffset_((0, -2))
        if self._editing:
            self.layer().setBorderWidth_(1.5)
            self.layer().setBorderColor_(_hex("E05A2B", 0.5).CGColor())
        else:
            self.layer().setBorderWidth_(0)

    def _track(self):
        opts = NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways | NSTrackingInVisibleRect
        self.addTrackingArea_(
            NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), opts, self, None))

    def _build(self):
        for sv in list(self.subviews()): sv.removeFromSuperview()
        self._edit_field = None

        w = self.bounds().size.width
        h = self.bounds().size.height

        # ── Icon box ──────────────────────────────────────────────────────
        iy  = (CARD_H - ICON_S) / 2
        box = NSView.alloc().initWithFrame_(NSMakeRect(14, iy, ICON_S, ICON_S))
        box.setWantsLayer_(True)
        box.layer().setCornerRadius_(12)
        box.layer().setBackgroundColor_((ICON_ORANGE if self._pinned else ICON_GRAY).CGColor())
        self.addSubview_(box)

        if self._pinned:
            il = NSTextField.labelWithString_("📌")
            il.setFont_(NSFont.systemFontOfSize_weight_(16, 0.4))
        else:
            il = NSTextField.labelWithString_(f"{self._index:02d}")
            il.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, -0.3))
            il.setTextColor_(CARD_SUB)
        il.setAlignment_(NSTextAlignmentCenter)
        il.setFrame_(NSMakeRect(0, (ICON_S-16)/2, ICON_S, 16))
        box.addSubview_(il)

        # ── Right buttons ─────────────────────────────────────────────────
        tag = abs(hash(self._text)) % (2**31)
        _copy_cbs[tag] = self._text

        cx  = w - 14 - BTN_S
        cy2 = (CARD_H - BTN_S) / 2

        # Copy
        cb = NSButton.alloc().initWithFrame_(NSMakeRect(cx, cy2, BTN_S, BTN_S))
        cb.setBordered_(False); cb.setWantsLayer_(True)
        cb.layer().setCornerRadius_(7)
        cb.layer().setBackgroundColor_(
            _hex("EBEBEB").CGColor() if self._hovered else NSColor.clearColor().CGColor())
        cb.setAttributedTitle_(_attr("⎘", _hex("6A6560"), NSFont.systemFontOfSize_weight_(15, 0.4)))
        cb.setTarget_(_ch()); cb.setAction_(objc.selector(_ch().handleCopy_, signature=b'v@:@'))
        cb.setTag_(tag); cb.setToolTip_("Copy")
        self.addSubview_(cb)

        # Pin
        px = cx - BTN_S - 6
        text_ref = self._text; want_pin = not self._pinned
        pb = NSButton.alloc().initWithFrame_(NSMakeRect(px, cy2, BTN_S, BTN_S))
        pb.setBordered_(False); pb.setWantsLayer_(True); pb.layer().setCornerRadius_(7)
        if self._pinned:
            pb.layer().setBackgroundColor_(_hex("FFE8D6").CGColor())
            pb.setAttributedTitle_(_attr("📌", _hex("E05A2B"), NSFont.systemFontOfSize_weight_(13, 0.4)))
            pb.setToolTip_("Unpin")
        else:
            pb.layer().setBackgroundColor_(
                _hex("EBEBEB").CGColor() if self._hovered else NSColor.clearColor().CGColor())
            pb.setAttributedTitle_(_attr("⊕", _hex("9A9590"), NSFont.systemFontOfSize_weight_(16, 0.3)))
            pb.setToolTip_("Pin to top")
        pd = _d(lambda t=text_ref, p=want_pin: self._on_pin(t, p))
        pb.setTarget_(pd); pb.setAction_(objc.selector(pd.fire_, signature=b'v@:@'))
        self.addSubview_(pb)

        # ── Text area ─────────────────────────────────────────────────────
        tx = 14 + ICON_S + 12
        tw = px - tx - 6

        if self._editing:
            # Editable text field
            ef = NSTextField.alloc().initWithFrame_(NSMakeRect(tx, 32, tw, h - 58))
            ef.setStringValue_(self._text)
            ef.setFont_(NSFont.systemFontOfSize_weight_(12.5, -0.3))
            ef.setTextColor_(_hex("1A1917"))
            ef.setBackgroundColor_(_hex("F5F3EF"))
            ef.setBezeled_(True); ef.setEditable_(True); ef.setSelectable_(True)
            ef.setWantsLayer_(True); ef.layer().setCornerRadius_(8)
            self.addSubview_(ef)
            self._edit_field = ef

            # Save button
            old = self._text
            sv_d = _d(lambda o=old: self._save_edit(o))
            sv_b = NSButton.alloc().initWithFrame_(NSMakeRect(tx, 6, 58, 24))
            sv_b.setBordered_(False); sv_b.setWantsLayer_(True)
            sv_b.layer().setCornerRadius_(8)
            sv_b.layer().setBackgroundColor_(_hex("E05A2B").CGColor())
            sv_b.setAttributedTitle_(_attr("Save", _hex("FFFFFF"), NSFont.systemFontOfSize_weight_(11, 0.6)))
            sv_b.setTarget_(sv_d); sv_b.setAction_(objc.selector(sv_d.fire_, signature=b'v@:@'))
            self.addSubview_(sv_b)

            # Cancel button
            cn_d = _d(self._cancel_edit)
            cn_b = NSButton.alloc().initWithFrame_(NSMakeRect(tx + 66, 6, 62, 24))
            cn_b.setBordered_(False); cn_b.setWantsLayer_(True)
            cn_b.layer().setCornerRadius_(8)
            cn_b.layer().setBackgroundColor_(_hex("E8E5E0").CGColor())
            cn_b.setAttributedTitle_(_attr("Cancel", _hex("6A6560"), NSFont.systemFontOfSize_weight_(11, 0.4)))
            cn_b.setTarget_(cn_d); cn_b.setAction_(objc.selector(cn_d.fire_, signature=b'v@:@'))
            self.addSubview_(cn_b)

            # Auto-focus
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.05, self, "focusField:", None, False)

        elif self._expanded:
            # Read-only expanded with edit button
            tf = NSTextField.wrappingLabelWithString_(self._text)
            tf.setFont_(NSFont.systemFontOfSize_weight_(12.5, -0.4))
            tf.setTextColor_(_hex("3A3835"))
            tf.setLineBreakMode_(NSLineBreakByWordWrapping)
            tf.setSelectable_(True)
            tf.setFrame_(NSMakeRect(tx, 26, tw, h - 42))
            self.addSubview_(tf)

            # Edit pencil button
            ed_d = _d(self._start_edit)
            ed_b = NSButton.alloc().initWithFrame_(NSMakeRect(tx, 5, 26, 20))
            ed_b.setBordered_(False); ed_b.setWantsLayer_(True)
            ed_b.layer().setCornerRadius_(6)
            ed_b.layer().setBackgroundColor_(
                _hex("EBEBEB").CGColor() if self._hovered else NSColor.clearColor().CGColor())
            ed_b.setAttributedTitle_(_attr("✎", _hex("9A9590"), NSFont.systemFontOfSize_weight_(13, 0.3)))
            ed_b.setTarget_(ed_d); ed_b.setAction_(objc.selector(ed_d.fire_, signature=b'v@:@'))
            ed_b.setToolTip_("Edit")
            self.addSubview_(ed_b)

            wc = len(self._text.split())
            meta_parts = [f"{wc} words"]
            if self._app_name:
                meta_parts.append(self._app_name)
            meta_parts.append("click to collapse")
            sl = NSTextField.labelWithString_("  ·  ".join(meta_parts))
            sl.setFont_(NSFont.systemFontOfSize_weight_(9, -0.3))
            sl.setTextColor_(CARD_SUB)
            sl.setFrame_(NSMakeRect(tx + 32, 7, tw - 32, 12))
            self.addSubview_(sl)

        else:
            # Collapsed
            display = self._text[:200] + ("…" if len(self._text) > 200 else "")
            tl = NSTextField.labelWithString_(display)
            tl.setFont_(NSFont.systemFontOfSize_weight_(12.5, -0.3))
            tl.setTextColor_(_hex("3A3835"))
            tl.setLineBreakMode_(NSLineBreakByTruncatingTail)
            tl.setFrame_(NSMakeRect(tx, CARD_H/2 + 3, tw, 15))
            self.addSubview_(tl)

            # Subtitle row: word count + app name
            wc = len(self._text.split())
            sub_parts = [f"{wc} words"]
            if self._app_name:
                sub_parts.append(self._app_name)
            sl = NSTextField.labelWithString_("  ·  ".join(sub_parts))
            sl.setFont_(NSFont.systemFontOfSize_weight_(10, -0.3))
            sl.setTextColor_(CARD_SUB)
            sl.setFrame_(NSMakeRect(tx, CARD_H/2 - 15, tw, 14))
            self.addSubview_(sl)

    # ── Edit ──────────────────────────────────────────────────────────────────
    def _start_edit(self):
        self._editing = True
        self._style(); self._build()

    def _save_edit(self, old_text):
        if self._edit_field is None:
            self._cancel_edit(); return
        new_text = self._edit_field.stringValue().strip()
        if not new_text:
            self._cancel_edit(); return
        self._editing = False
        if new_text != old_text:
            _expanded.discard(self._ekey)
            self._text = new_text
            self._ekey = ("p" if self._pinned else "h", new_text)
            _expanded.add(self._ekey)
            if self._on_edit:
                self._on_edit(old_text, new_text)
        else:
            self._style(); self._build()

    def _cancel_edit(self):
        self._editing = False
        self._style(); self._build()

    def focusField_(self, timer):
        if self._edit_field and self.window():
            self.window().makeFirstResponder_(self._edit_field)

    # ── Mouse ─────────────────────────────────────────────────────────────────
    def mouseEntered_(self, event):
        self._hovered = True;  self._style(); self._build()
    def mouseExited_(self, event):
        self._hovered = False; self._style(); self._build()

    def mouseUp_(self, event):
        if self._editing: return
        loc = event.locationInWindow()
        pt  = self.convertPoint_fromView_(loc, None)
        w   = self.bounds().size.width
        cx  = w - 14 - BTN_S;  cy2 = (CARD_H - BTN_S) / 2
        px  = cx - BTN_S - 6
        if (NSPointInRect(pt, NSMakeRect(cx, cy2, BTN_S, BTN_S)) or
                NSPointInRect(pt, NSMakeRect(px, cy2, BTN_S, BTN_S))):
            return
        if self._ekey in _expanded: _expanded.discard(self._ekey)
        else: _expanded.add(self._ekey)
        self._expanded = self._ekey in _expanded
        if self._on_expand: self._on_expand(self)

    def isFlipped(self): return True


def _card_h(text, w, ekey, editing=False):
    if editing: return max(160, CARD_H + 100)
    if ekey not in _expanded: return CARD_H
    tx = 14 + ICON_S + 12
    px = w - 14 - BTN_S - BTN_S - 6
    tw = px - tx - 6
    cpl = max(1, int(tw / 7.8))
    lines = min(14, max(2, math.ceil(len(text) / cpl)))
    return 42 + lines * 18 + 16


# ── Device selector (Professional minimalist chips) ───────────────────────────
class DeviceSelectorView(NSView):
    """
    Minimalist horizontal chip selector.
    """
    def initWithFrame_devices_selected_onSelect_(
            self, frame, devices, selected_id, on_select):
        self = objc.super(DeviceSelectorView, self).initWithFrame_(frame)
        if self is None: return None
        self._devices    = devices
        self._selected   = selected_id
        self._on_select  = on_select
        self._seg_rects  = []
        self.setWantsLayer_(True)
        # Transparent background for a cleaner look
        self.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
        self._build()
        return self

    def setSelected_(self, device_id):
        self._selected = device_id
        self._build()

    def _icon_for(self, dtype: str, name: str) -> str:
        icon = "📱 " if dtype in ('iphone', 'ios', 'android') else "💻 "
        display_name = (name[:10] + ".." if len(name) > 10 else name) if name else "Device"
        return f"{icon}{display_name}"

    def _build(self):
        for sv in list(self.subviews()): sv.removeFromSuperview()
        self._seg_rects = []

        # Segments: None (local) + All (broadcast) + specific devices
        segments = [
            ("__none__", "✕ Local"),
            ("__all__",  "⊕ All"),
        ]
        for d in self._devices:
            dtype = d.get("device_type", "mac")
            name  = d.get("device_name", "Unknown")
            segments.append((d["device_id"], self._icon_for(dtype, name)))

        if len(segments) <= 2:
            return # Don't show anything if only Local/All are available and no other devices

        # Calculate layout: horizontal row of pills with gap
        cur_x = 0
        gap = 8
        h = self.bounds().size.height

        for dev_id, label in segments:
            is_sel = (dev_id == self._selected)
            
            # Measure text width
            font = NSFont.systemFontOfSize_weight_(11, 0.6 if is_sel else 0.3)
            tw = NSString.stringWithString_(label).sizeWithAttributes_({"NSFont": font}).width
            pill_w = tw + 24
            
            rect = NSMakeRect(cur_x, 0, pill_w, h)
            self._seg_rects.append((rect, dev_id))

            pill = NSView.alloc().initWithFrame_(rect)
            pill.setWantsLayer_(True)
            pill.layer().setCornerRadius_(h/2)
            
            if is_sel:
                pill.layer().setBackgroundColor_(_hex("FFFFFF", 0.1).CGColor())
                pill.layer().setBorderWidth_(1.0)
                pill.layer().setBorderColor_(H_ACCENT.CGColor())
            else:
                pill.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
                pill.layer().setBorderWidth_(1.0)
                pill.layer().setBorderColor_(_hex("FFFFFF", 0.08).CGColor())
            
            self.addSubview_(pill)

            lbl = NSTextField.labelWithString_(label)
            lbl.setFont_(font)
            lbl.setTextColor_(H_ACCENT if is_sel else _hex("7A7570"))
            lbl.setAlignment_(NSTextAlignmentCenter)
            lbl.setFrame_(NSMakeRect(0, (h - 14) / 2, pill_w, 14))
            lbl.setSelectable_(False)
            pill.addSubview_(lbl)

            cur_x += pill_w + gap

    def mouseUp_(self, event):
        loc = event.locationInWindow()
        pt  = self.convertPoint_fromView_(loc, None)
        for rect, dev_id in self._seg_rects:
            if NSPointInRect(pt, rect):
                self._selected = dev_id
                self._build()
                if self._on_select:
                    self._on_select(dev_id)
                return

    def isFlipped(self): return True


# ── Hero view ─────────────────────────────────────────────────────────────────
class HeroView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(HeroView, self).initWithFrame_(frame)
        if self is None: return None
        self._phase = 0.0; self._amp = 0.0
        self._recording = False; self._processing = False
        self._total = 0; self._words = 0; self._daily = 0
        self._model = "base"; self._mode = "toggle"
        return self

    def updateStats_words_model_mode_(self, total, words, model, mode):
        self._total = total; self._words = words
        self._model = model; self._mode  = mode
        self.setNeedsDisplay_(True)

    def setDailyWords_(self, daily):
        self._daily = daily
        self.setNeedsDisplay_(True)

    def setRecording_(self, rec):
        self._recording = rec; self._processing = False
        self.setNeedsDisplay_(True)

    def setProcessing_(self, proc):
        self._processing = proc; self._recording = False
        self.setNeedsDisplay_(True)

    def animateTick_(self, timer):
        if self._recording:
            self._phase += 0.08
            self._amp = min(1.0, self._amp + 0.10)
        elif self._processing:
            self._phase += 0.05
            self._amp = 0.35 + 0.25 * math.sin(self._phase * 4)
        else:
            self._amp = max(0.0, self._amp - 0.05)
        if self._recording or self._processing or self._amp > 0:
            self.setNeedsDisplay_(True)

    def isFlipped(self): return True

    def drawRect_(self, rect):
        w = self.bounds().size.width
        h = self.bounds().size.height

        # Background
        H_BG.set()
        NSBezierPath.fillRect_(self.bounds())

        # Waveform bars at bottom
        if self._amp > 0.01:
            bc = 28; bw = 2.5; gap = 3.5
            sx = (w - (bc*bw + (bc-1)*gap)) / 2
            for i in range(bc):
                frac = 1.0 - abs(i-(bc-1)/2.0) / ((bc-1)/2.0)
                wave = abs(math.sin(self._phase*2.5 + i*0.42))
                bh   = max(2.0, 24.0*(0.2+0.8*frac)*wave*self._amp)
                bx   = sx + i*(bw+gap)
                by   = h - 52 - bh/2
                a    = (0.20+0.40*frac*self._amp) if self._recording else (0.10+0.18*frac*self._amp)
                (H_ACCENT if self._recording else _hex("F2EFE9")).colorWithAlphaComponent_(a).set()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(bx, by, bw, bh), bw/2, bw/2).fill()

        # ── Logo ✳ + status dot ───────────────────────────────────────────
        # Logo shifted right to leave room for hamburger at top-left
        NSString.stringWithString_("✳").drawAtPoint_withAttributes_(
            NSMakePoint(PAD + 40, 22),
            {"NSFont": NSFont.systemFontOfSize_weight_(24, 0.2), "NSColor": H_TEXT})

        dot = H_ACCENT if self._recording else (_hex("4A90E2") if self._processing else _hex("4CAF7D", 0.8))
        dot.set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(PAD + 72, 30, 7, 7)).fill()

        # ── Big editorial text ────────────────────────────────────────────
        # Line 1 — plain
        if self._recording:
            line1 = "Listening…"
            line2 = ""
        elif self._processing:
            line1 = "Transcribing…"
            line2 = ""
        else:
            line1 = f"You've made"
            line2 = f"{self._total} transcriptions."

        big_font  = NSFont.systemFontOfSize_weight_(26, 0.7)
        big_attrs = {"NSFont": big_font, "NSColor": H_TEXT}
        NSString.stringWithString_(line1).drawAtPoint_withAttributes_(NSMakePoint(PAD, 68), big_attrs)

        if line2:
            # Number in accent, rest in white
            num_str  = f"{self._total}"
            rest_str = " transcriptions."
            num_font = NSFont.systemFontOfSize_weight_(26, 0.7)
            num_w    = NSString.stringWithString_(num_str).sizeWithAttributes_(
                {"NSFont": num_font}).width

            NSString.stringWithString_(num_str).drawAtPoint_withAttributes_(
                NSMakePoint(PAD, 100),
                {"NSFont": num_font, "NSColor": H_ACCENT})
            NSString.stringWithString_(rest_str).drawAtPoint_withAttributes_(
                NSMakePoint(PAD + num_w, 100),
                {"NSFont": NSFont.systemFontOfSize_weight_(26, 0.7), "NSColor": H_TEXT})

        # ── Stats row ─────────────────────────────────────────────────────
        sf  = NSFont.systemFontOfSize_weight_(11, 0.4)
        sx2 = PAD
        for val, label in [
            (f"{self._total}", " clips"),
            (f"{self._words}", " total words"),
            (f"{self._daily}", " today"),
        ]:
            NSString.stringWithString_(val).drawAtPoint_withAttributes_(
                NSMakePoint(sx2, 148), {"NSFont": NSFont.systemFontOfSize_weight_(11, 0.6), "NSColor": H_ACCENT})
            vw = NSString.stringWithString_(val).sizeWithAttributes_({"NSFont": NSFont.systemFontOfSize_weight_(11, 0.6)}).width
            NSString.stringWithString_(label).drawAtPoint_withAttributes_(
                NSMakePoint(sx2+vw, 148), {"NSFont": sf, "NSColor": H_MUTED})
            lw = NSString.stringWithString_(label).sizeWithAttributes_({"NSFont": sf}).width
            sx2 += vw + lw + 18

        # Mode hint
        NSString.stringWithString_(
            f"{'Hold' if self._mode=='hold' else 'Toggle'} · Right ⌘"
        ).drawAtPoint_withAttributes_(
            NSMakePoint(PAD, 174),
            {"NSFont": NSFont.systemFontOfSize_weight_(10, 0.3), "NSColor": H_MUTED})


# ── Sheet view ────────────────────────────────────────────────────────────────
class SheetView(NSView):
    def isFlipped(self): return True
    def drawRect_(self, rect):
        w = self.bounds().size.width
        h = self.bounds().size.height
        S_BG.set()
        NSBezierPath.fillRect_(self.bounds())
        # Drag handle pill
        _hex("C8C4BE").set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect((w-32)/2, 10, 32, 4), 2, 2).fill()


# ── Sidebar overlay ───────────────────────────────────────────────────────────
SIDEBAR_W = 220

NAV_ITEMS = [
    ("All",       "All transcriptions",  0),
    ("By App",    "Grouped by app",      1),
    ("Stats",     "Usage overview",      2),
    ("Canvas",    "Shared clipboard",    4),
    ("Notes",     "Voice notes & ideas", 5),
    ("Settings",  "Keys & preferences",  3),
]

class SidebarView(NSView):
    """Permanent dark left navigation panel."""

    def initWithFrame_onSelect_(self, frame, on_select):
        self = objc.super(SidebarView, self).initWithFrame_(frame)
        if self is None: return None
        self._on_select  = on_select
        self._active     = 0
        self._item_rects = []
        self.setWantsLayer_(True)
        self.layer().setBackgroundColor_(_hex("141412").CGColor())
        self._build()
        return self

    def setActiveItem_(self, idx):
        self._active = idx
        self._build()

    def _build(self):
        for sv in list(self.subviews()): sv.removeFromSuperview()
        self._item_rects = []
        w = self.bounds().size.width
        h = self.bounds().size.height

        # Logo + app name
        logo = NSTextField.labelWithString_("✳")
        logo.setFont_(NSFont.systemFontOfSize_weight_(18, 0.2))
        logo.setTextColor_(H_ACCENT)
        logo.setFrame_(NSMakeRect(16, h - 44, 24, 24))
        self.addSubview_(logo)

        name = NSTextField.labelWithString_("Verbal")
        name.setFont_(NSFont.systemFontOfSize_weight_(13, 0.6))
        name.setTextColor_(H_TEXT)
        name.setFrame_(NSMakeRect(44, h - 42, w - 56, 18))
        self.addSubview_(name)

        # Divider
        div = NSView.alloc().initWithFrame_(NSMakeRect(12, h - 54, w - 24, 1))
        div.setWantsLayer_(True)
        div.layer().setBackgroundColor_(_hex("FFFFFF", 0.07).CGColor())
        self.addSubview_(div)

        # Nav items
        for i, (label, sublabel, idx) in enumerate(NAV_ITEMS):
            is_active = (idx == self._active)
            item_y    = h - 100 - i * 54
            item_rect = NSMakeRect(0, item_y, w, 48)
            self._item_rects.append((item_rect, idx))

            if is_active:
                bar = NSView.alloc().initWithFrame_(NSMakeRect(0, item_y + 5, 3, 38))
                bar.setWantsLayer_(True)
                bar.layer().setCornerRadius_(1.5)
                bar.layer().setBackgroundColor_(H_ACCENT.CGColor())
                self.addSubview_(bar)
                tint = NSView.alloc().initWithFrame_(NSMakeRect(5, item_y + 2, w - 10, 44))
                tint.setWantsLayer_(True)
                tint.layer().setCornerRadius_(8)
                tint.layer().setBackgroundColor_(_hex("FFFFFF", 0.05).CGColor())
                self.addSubview_(tint)

            lbl = NSTextField.labelWithString_(label)
            lbl.setFont_(NSFont.systemFontOfSize_weight_(12, 0.6 if is_active else 0.3))
            lbl.setTextColor_(H_TEXT if is_active else _hex("6A6560"))
            lbl.setFrame_(NSMakeRect(16, item_y + 20, w - 32, 15))
            lbl.setSelectable_(False)
            self.addSubview_(lbl)

            sub = NSTextField.labelWithString_(sublabel)
            sub.setFont_(NSFont.systemFontOfSize_weight_(9, -0.3))
            sub.setTextColor_(_hex("3A3835"))
            sub.setFrame_(NSMakeRect(16, item_y + 5, w - 32, 13))
            sub.setSelectable_(False)
            self.addSubview_(sub)

        # Footer
        ver = NSTextField.labelWithString_("v1.0")
        ver.setFont_(NSFont.systemFontOfSize_weight_(9, -0.3))
        ver.setTextColor_(_hex("2A2825"))
        ver.setFrame_(NSMakeRect(16, 12, w - 32, 12))
        self.addSubview_(ver)

    def mouseUp_(self, event):
        loc = event.locationInWindow()
        pt  = self.convertPoint_fromView_(loc, None)
        for rect, idx in self._item_rects:
            if NSPointInRect(pt, rect):
                self._active = idx
                self._build()
                if self._on_select: self._on_select(idx)
                return

    def isFlipped(self): return True


# ── App group row (By App page) ───────────────────────────────────────────────
class AppGroupView(NSView):
    """Collapsible group showing all transcriptions for one app."""

    def initWithFrame_appName_entries_onExpand_(self, frame, app_name, entries, on_expand):
        self = objc.super(AppGroupView, self).initWithFrame_(frame)
        if self is None: return None
        self._app_name  = app_name
        self._entries   = entries
        self._on_expand = on_expand
        self._collapsed = True
        self.setWantsLayer_(True)
        self.layer().setBackgroundColor_(CARD_BG.CGColor())
        self.layer().setCornerRadius_(CARD_R)
        self.layer().setShadowColor_(NSColor.blackColor().CGColor())
        self.layer().setShadowOpacity_(0.04)
        self.layer().setShadowRadius_(5)
        self.layer().setShadowOffset_((0, -1))
        self._build()
        return self

    def _build(self):
        for sv in list(self.subviews()): sv.removeFromSuperview()
        w = self.bounds().size.width
        h = self.bounds().size.height

        # App icon placeholder
        icon = NSView.alloc().initWithFrame_(NSMakeRect(14, (CARD_H-ICON_S)/2, ICON_S, ICON_S))
        icon.setWantsLayer_(True)
        icon.layer().setCornerRadius_(12)
        icon.layer().setBackgroundColor_(ICON_GRAY.CGColor())
        self.addSubview_(icon)

        # App initial letter
        initial = (self._app_name[0].upper() if self._app_name else "?")
        il = NSTextField.labelWithString_(initial)
        il.setFont_(NSFont.systemFontOfSize_weight_(16, 0.3))
        il.setTextColor_(CARD_SUB)
        il.setAlignment_(NSTextAlignmentCenter)
        il.setFrame_(NSMakeRect(0, (ICON_S-20)/2, ICON_S, 20))
        icon.addSubview_(il)

        # App name
        tx = 14 + ICON_S + 12
        name_lbl = NSTextField.labelWithString_(self._app_name or "Unknown")
        name_lbl.setFont_(NSFont.systemFontOfSize_weight_(13, 0.5))
        name_lbl.setTextColor_(CARD_TEXT)
        name_lbl.setFrame_(NSMakeRect(tx, CARD_H/2 + 2, w - tx - 60, 16))
        self.addSubview_(name_lbl)

        # Count badge
        count_lbl = NSTextField.labelWithString_(f"{len(self._entries)} clips")
        count_lbl.setFont_(NSFont.systemFontOfSize_weight_(10, -0.3))
        count_lbl.setTextColor_(CARD_SUB)
        count_lbl.setFrame_(NSMakeRect(tx, CARD_H/2 - 15, 80, 14))
        self.addSubview_(count_lbl)

        # Chevron
        chev = NSTextField.labelWithString_("›" if self._collapsed else "⌄")
        chev.setFont_(NSFont.systemFontOfSize_weight_(16, 0.3))
        chev.setTextColor_(CARD_SUB)
        chev.setFrame_(NSMakeRect(w - 30, (CARD_H-18)/2, 20, 18))
        self.addSubview_(chev)

        # Expanded entries
        if not self._collapsed:
            y = CARD_H + 4
            for entry in self._entries:
                text = _entry_text(entry)
                display = text[:160] + ("…" if len(text) > 160 else "")
                row = NSView.alloc().initWithFrame_(NSMakeRect(0, y, w, 52))
                row.setWantsLayer_(True)
                row.layer().setBackgroundColor_(_hex("F8F6F2").CGColor())

                # Divider line at top
                div = NSView.alloc().initWithFrame_(NSMakeRect(tx, 0, w - tx - 14, 1))
                div.setWantsLayer_(True)
                div.layer().setBackgroundColor_(_hex("ECEAE6").CGColor())
                row.addSubview_(div)

                tl = NSTextField.wrappingLabelWithString_(display)
                tl.setFont_(NSFont.systemFontOfSize_weight_(12, -0.3))
                tl.setTextColor_(_hex("3A3835"))
                tl.setLineBreakMode_(NSLineBreakByTruncatingTail)
                tl.setSelectable_(True)
                tl.setFrame_(NSMakeRect(tx, 8, w - tx - 50, 36))
                row.addSubview_(tl)

                # Copy button
                tag = abs(hash(text)) % (2**31)
                _copy_cbs[tag] = text
                cb = NSButton.alloc().initWithFrame_(NSMakeRect(w - 42, 14, BTN_S, BTN_S))
                cb.setBordered_(False); cb.setWantsLayer_(True)
                cb.layer().setCornerRadius_(7)
                cb.layer().setBackgroundColor_(_hex("EBEBEB").CGColor())
                cb.setAttributedTitle_(_attr("⎘", _hex("6A6560"), NSFont.systemFontOfSize_weight_(14, 0.4)))
                cb.setTarget_(_ch()); cb.setAction_(objc.selector(_ch().handleCopy_, signature=b'v@:@'))
                cb.setTag_(tag)
                row.addSubview_(cb)

                self.addSubview_(row)
                y += 52

    def mouseUp_(self, event):
        self._collapsed = not self._collapsed
        if self._on_expand: self._on_expand()

    def isFlipped(self): return True


def _app_group_h(entries, collapsed):
    if collapsed: return CARD_H
    return CARD_H + 4 + len(entries) * 52


# ── Stats bar row ─────────────────────────────────────────────────────────────
def _make_stat_row(x, y, w, app_name, word_count, clip_count, max_words):
    """One row in the stats page: app name, bar, numbers."""
    row = NSView.alloc().initWithFrame_(NSMakeRect(x, y, w, 44))
    row.setWantsLayer_(True)
    row.layer().setBackgroundColor_(CARD_BG.CGColor())
    row.layer().setCornerRadius_(10)

    # App name
    nl = NSTextField.labelWithString_(app_name or "Unknown")
    nl.setFont_(NSFont.systemFontOfSize_weight_(12, 0.4))
    nl.setTextColor_(CARD_TEXT)
    nl.setFrame_(NSMakeRect(12, 14, 110, 15))
    row.addSubview_(nl)

    # Bar track
    bar_x = 130; bar_w = w - bar_x - 70; bar_h = 6
    track = NSView.alloc().initWithFrame_(NSMakeRect(bar_x, 19, bar_w, bar_h))
    track.setWantsLayer_(True)
    track.layer().setCornerRadius_(3)
    track.layer().setBackgroundColor_(_hex("ECEAE6").CGColor())
    row.addSubview_(track)

    # Bar fill
    fill_w = max(6, int(bar_w * (word_count / max(max_words, 1))))
    fill = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, fill_w, bar_h))
    fill.setWantsLayer_(True)
    fill.layer().setCornerRadius_(3)
    fill.layer().setBackgroundColor_(H_ACCENT.CGColor())
    track.addSubview_(fill)

    # Numbers
    nums = NSTextField.labelWithString_(f"{word_count}w  ·  {clip_count}")
    nums.setFont_(NSFont.systemFontOfSize_weight_(10, -0.3))
    nums.setTextColor_(CARD_SUB)
    nums.setAlignment_(NSTextAlignmentRight)
    nums.setFrame_(NSMakeRect(w - 68, 14, 56, 14))
    row.addSubview_(nums)

    return row
def _make_rec_btn(frame, cb):
    dd  = _d(cb)
    btn = NSButton.alloc().initWithFrame_(frame)
    btn.setBordered_(False); btn.setWantsLayer_(True)
    btn.layer().setCornerRadius_(10)
    btn.layer().setBackgroundColor_(H_BG.CGColor())
    btn.setAttributedTitle_(
        _attr("⏺  Record", H_TEXT, NSFont.systemFontOfSize_weight_(11.5, 0.5)))
    btn.setTarget_(dd)
    btn.setAction_(objc.selector(dd.fire_, signature=b'v@:@'))
    return btn

def _upd_rec_btn(btn, rec):
    btn.layer().setBackgroundColor_((H_ACCENT if rec else H_BG).CGColor())
    btn.setAttributedTitle_(
        _attr("⏹  Stop" if rec else "⏺  Record",
              H_TEXT, NSFont.systemFontOfSize_weight_(11.5, 0.5)))


# ── Dashboard window ──────────────────────────────────────────────────────────
class DashboardWindow:
    def __init__(self, app_ref):
        self._window    = None; self._app = app_ref
        self._hero      = None; self._rec_btn = None
        self._recording_hotkey_for = None # "hold" or "toggle"
        self._scroll    = None; self._container = None
        self._perm      = None; self._timer = None
        self._sidebar   = None
        self._active_tab = 0   # 0=All, 1=By App, 2=Stats, 3=Settings, 4=Canvas, 5=Notes
        self._app_groups = {}
        self._page_lbl  = None
        self._canvas_text_view = None
        self._canvas_status    = None
        self._canvas_loaded    = False
        self._canvas_image_url = None
        # Device targeting
        self._target_device_id  = None   # None = all devices, str = specific device_id
        self._known_devices     = []     # list of {device_id, device_name, device_type}
        self._device_sel_view   = None   # the segmented control view
        # Notes
        self._notes_data      = []
        self._notes_selected  = None

    def show(self):
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            self._refresh()
            return

        screen = NSScreen.mainScreen()
        sf = screen.frame() if screen else NSMakeRect(0, 0, 1440, 900)
        x  = (sf.size.width  - WIN_W) / 2
        y  = (sf.size.height - WIN_H) / 2

        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, WIN_W, WIN_H), style, NSBackingStoreBuffered, False)
        self._window.setTitle_("Verbal")
        self._window.setMinSize_(NSMakeSize(700, 500))
        self._window.setBackgroundColor_(H_BG)

        cv = self._window.contentView()
        CONTENT_W = WIN_W - SIDEBAR_W

        # ── Permanent left sidebar ────────────────────────────────────────
        self._sidebar = SidebarView.alloc().initWithFrame_onSelect_(
            NSMakeRect(0, 0, SIDEBAR_W, WIN_H),
            self._on_tab_select)
        self._sidebar.setAutoresizingMask_(0x10)
        cv.addSubview_(self._sidebar)

        # Vertical divider
        vdiv = NSView.alloc().initWithFrame_(NSMakeRect(SIDEBAR_W, 0, 1, WIN_H))
        vdiv.setWantsLayer_(True)
        vdiv.layer().setBackgroundColor_(_hex("FFFFFF", 0.06).CGColor())
        vdiv.setAutoresizingMask_(0x10)
        cv.addSubview_(vdiv)

        # ── Hero (right panel top) ────────────────────────────────────────
        self._hero = HeroView.alloc().initWithFrame_(
            NSMakeRect(SIDEBAR_W + 1, WIN_H - HERO_H, CONTENT_W - 1, HERO_H))
        self._hero.setAutoresizingMask_(0x02 | 0x04)
        cv.addSubview_(self._hero)

        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            1/30.0, self._hero, "animateTick:", None, True)
        NSRunLoop.mainRunLoop().addTimer_forMode_(self._timer, NSDefaultRunLoopMode)

        # ── Device selector — bottom of hero ─────────────────────────────
        SEL_H = 28
        SEL_W = 220
        self._device_sel_view = DeviceSelectorView.alloc().initWithFrame_devices_selected_onSelect_(
            NSMakeRect(SIDEBAR_W + CONTENT_W - SEL_W - PAD, WIN_H - SEL_H - 10, SEL_W, SEL_H),
            [],
            None,
            self._on_target_device_select
        )
        self._device_sel_view.setAutoresizingMask_(0x04)
        cv.addSubview_(self._device_sel_view)

        # Load devices async — refresh every 30s
        threading.Thread(target=self._device_refresh_loop, daemon=True).start()

        # ── Sheet (right panel bottom) ────────────────────────────────────
        sheet_h = WIN_H - HERO_H + SHEET_R
        sheet   = SheetView.alloc().initWithFrame_(
            NSMakeRect(SIDEBAR_W + 1, 0, CONTENT_W - 1, sheet_h))
        sheet.setWantsLayer_(True)
        sheet.layer().setCornerRadius_(SHEET_R)
        sheet.layer().setMaskedCorners_(0b0011)
        sheet.setAutoresizingMask_(0x12 | 0x10 | 0x04)
        cv.addSubview_(sheet)

        sc = sheet
        cy = sheet_h - SHEET_R

        # ── Top bar ───────────────────────────────────────────────────────
        cy -= 14
        bw, bh = 120, 32
        self._rec_btn = _make_rec_btn(NSMakeRect(PAD, cy - bh, bw, bh),
            lambda: (self._app._on_main(self._app._on_record_stop)
                     if self._app._is_recording
                     else self._app._on_main(self._app._on_record_start)))
        sc.addSubview_(self._rec_btn)

        self._perm = NSTextField.labelWithString_("")
        self._perm.setFont_(NSFont.systemFontOfSize_weight_(9, -0.3))
        self._perm.setTextColor_(H_ACCENT)
        self._perm.setFrame_(NSMakeRect(PAD + bw + 8, cy - bh + 10, 160, 14))
        sc.addSubview_(self._perm)
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions
            if not AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": False}):
                self._perm.setStringValue_("⚠ Accessibility needed")
        except Exception:
            pass

        clrd = _d(self._clear)
        clrb = NSButton.alloc().initWithFrame_(NSMakeRect(CONTENT_W - PAD - 60, cy - bh + 5, 60, 22))
        clrb.setBordered_(False); clrb.setWantsLayer_(True)
        clrb.layer().setCornerRadius_(6)
        clrb.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
        clrb.setAttributedTitle_(
            _attr("Clear all", _hex("B0ADA8"), NSFont.systemFontOfSize_weight_(10, -0.3)))
        clrb.setTarget_(clrd)
        clrb.setAction_(objc.selector(clrd.fire_, signature=b'v@:@'))
        sc.addSubview_(clrb)

        cy -= bh + 12

        self._page_lbl = NSTextField.labelWithString_("All transcriptions")
        self._page_lbl.setFont_(NSFont.systemFontOfSize_weight_(11, -0.3))
        self._page_lbl.setTextColor_(CARD_SUB)
        self._page_lbl.setFrame_(NSMakeRect(PAD, cy - 14, 200, 14))
        sc.addSubview_(self._page_lbl)
        cy -= 20

        # ── Scroll area ───────────────────────────────────────────────────
        sh = cy - 6
        self._scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(PAD, 6, CONTENT_W - 1 - PAD * 2, sh))
        self._scroll.setHasVerticalScroller_(True)
        self._scroll.setDrawsBackground_(False)
        self._scroll.setAutoresizingMask_(0x12 | 0x10 | 0x04)
        self._container = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, CONTENT_W - 1 - PAD * 2, sh))
        self._scroll.setDocumentView_(self._container)
        sc.addSubview_(self._scroll)

        self._refresh()
        # Start canvas listener once — runs for the lifetime of the window
        threading.Thread(target=self._canvas_listen, daemon=True).start()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    # ── Tab navigation ────────────────────────────────────────────────────────
    def _on_tab_select(self, idx):
        PAGE_NAMES = {0: "All transcriptions", 1: "By application",
                      2: "Statistics", 3: "Settings", 4: "Canvas", 5: "Notes"}
        self._active_tab = idx
        if self._sidebar:
            self._sidebar.setActiveItem_(idx)
        if self._page_lbl:
            self._page_lbl.setStringValue_(PAGE_NAMES.get(idx, ""))
        # Show/hide record button and clear button based on tab
        if self._rec_btn:
            self._rec_btn.setHidden_(idx in (4, 5))
        self._rebuild()

    # ── Edit ─────────────────────────────────────────────────────────────────
    def _handle_edit(self, old_text, new_text):
        from app.config import save_config
        cfg = self._app.config

        # Update history entries
        history = cfg.get("history", [])
        for i, e in enumerate(history):
            if _entry_text(e) == old_text:
                if isinstance(e, dict):
                    history[i] = {**e, "text": new_text}
                else:
                    history[i] = {"text": new_text, "app": "", "ts": ""}
                break
        cfg["history"] = history

        # Update pinned entries
        pinned = cfg.get("pinned", [])
        for i, e in enumerate(pinned):
            if _entry_text(e) == old_text:
                if isinstance(e, dict):
                    pinned[i] = {**e, "text": new_text}
                else:
                    pinned[i] = {"text": new_text, "app": "", "ts": ""}
                break
        cfg["pinned"] = pinned

        save_config(cfg)
        self._rebuild()

    # ── Pin ───────────────────────────────────────────────────────────────────
    def _handle_pin(self, text, should_pin):
        from app.config import save_config
        pinned = list(self._app.config.get("pinned", []))
        pinned_texts = [_entry_text(e) for e in pinned]
        if should_pin:
            if text not in pinned_texts:
                # Find the full entry from history to preserve app context
                hist = self._app.config.get("history", [])
                entry = next((e for e in hist if _entry_text(e) == text),
                             {"text": text, "app": "", "ts": ""})
                pinned.insert(0, entry)
        else:
            pinned = [e for e in pinned if _entry_text(e) != text]
        self._app.config["pinned"] = pinned
        save_config(self._app.config)
        self._rebuild()

    # ── Clear ─────────────────────────────────────────────────────────────────
    def _clear(self):
        from app.config import save_config
        self._app.config["history"] = []
        self._app.config["pinned"]  = []
        self._app._total_transcriptions = 0
        self._app._total_words = 0
        save_config(self._app.config)
        self._refresh()

    # ── Refresh ───────────────────────────────────────────────────────────────
    def _refresh(self):
        cfg = self._app.config
        h   = cfg.get("history", [])
        if self._hero:
            self._hero.updateStats_words_model_mode_(
                len(h),
                sum(len(_entry_text(x).split()) for x in h),
                cfg.get("whisper_model","base"),
                self._app._mode)
            # Daily words
            from datetime import date as _date
            daily = cfg.get("daily", {"date": "", "words": 0})
            self._hero.setDailyWords_(
                daily.get("words", 0) if daily.get("date") == str(_date.today()) else 0
            )
            self._hero.setRecording_(self._app._is_recording)
            if self._app._processing: self._hero.setProcessing_(True)
        if self._rec_btn:
            _upd_rec_btn(self._rec_btn, self._app._is_recording)
        self._rebuild()

    # ── Hotkey Selection ──────────────────────────────────────────────────────
    def _start_hotkey_record(self, mode):
        """Begin listening for the next key press to assign as a hotkey."""
        from AppKit import NSEvent
        import Quartz
        
        if self._recording_hotkey_for == mode:
            # Cancel if clicked again
            self._recording_hotkey_for = None
            self._rebuild_settings()
            return

        self._recording_hotkey_for = mode
        self._rebuild_settings()

        # Add a local monitor to capture the next key
        mask = Quartz.NSEventMaskKeyDown | Quartz.NSEventMaskFlagsChanged
        self._key_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_key_capture
        )

    def _handle_key_capture(self, event):
        """Internal handler for the local event monitor."""
        from AppKit import NSEvent
        if self._recording_hotkey_for:
            code = event.keyCode()
            # Ignore Escape for hotkeys (used for cancelling)
            if code == 53: 
                self._recording_hotkey_for = None
                self._rebuild_settings()
            else:
                self._on_hotkey_captured(code)
            
            # Stop monitoring
            if hasattr(self, "_key_monitor") and self._key_monitor:
                NSEvent.removeMonitor_(self._key_monitor)
                self._key_monitor = None
            return None # Swallow the event
        return event

    def _on_hotkey_captured(self, keycode):
        """Save the captured keycode and update listener."""
        mode = self._recording_hotkey_for
        self._recording_hotkey_for = None
        
        cfg = self._app.config
        if mode == "hold":
            cfg["hotkey_hold"] = keycode
        else:
            cfg["hotkey_toggle"] = keycode
        
        from app.config import save_config
        save_config(cfg)
        
        # Update active listener
        if self._app.hotkey_listener:
            self._app.hotkey_listener.update_keys(
                cfg.get("hotkey_hold", 54),
                cfg.get("hotkey_toggle", 54)
            )
            
        self._rebuild_settings()

    # ── Rebuild ───────────────────────────────────────────────────────────────
    def _rebuild(self, expanded_card=None):
        if not self._container: return
        if self._active_tab == 4:
            self._rebuild_canvas()
            return
        if self._active_tab == 5:
            self._rebuild_notes()
            return
        if self._active_tab == 1:
            self._rebuild_by_app()
        elif self._active_tab == 2:
            self._rebuild_stats()
        elif self._active_tab == 3:
            self._rebuild_settings()
        else:
            self._rebuild_all(expanded_card)

    # ── All tab ───────────────────────────────────────────────────────────────
    def _rebuild_all(self, expanded_card=None):
        if not self._container: return
        _copy_cbs.clear()
        for sv in list(self._container.subviews()): sv.removeFromSuperview()

        sw     = self._scroll.frame().size.width
        cfg    = self._app.config
        hist   = cfg.get("history", [])
        pinned = cfg.get("pinned", [])
        pset   = set(_entry_text(e) for e in pinned)
        recent = [e for e in hist[:50] if _entry_text(e) not in pset]

        if not pinned and not recent:
            e = NSTextField.wrappingLabelWithString_(
                "No transcriptions yet.\nHold Right ⌘ to start recording.")
            e.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.0))
            e.setTextColor_(CARD_SUB)
            e.setAlignment_(NSTextAlignmentCenter)
            e.setFrame_(NSMakeRect(0, 60, sw, 44))
            self._container.addSubview_(e)
            self._container.setFrame_(NSMakeRect(0, 0, sw, 160))
            return

        SEC = 28   # section label height

        ph = [_card_h(_entry_text(e), sw, ("p", _entry_text(e))) for e in pinned]
        rh = [_card_h(_entry_text(e), sw, ("h", _entry_text(e))) for e in recent]

        total = (
            ((SEC + sum(ph) + CARD_GAP*len(ph)) if pinned else 0) +
            ((SEC + sum(rh) + CARD_GAP*len(rh)) if recent else 0) +
            CARD_GAP
        )
        sh2 = self._scroll.frame().size.height
        cont = max(total, sh2)
        self._container.setFrame_(NSMakeRect(0, 0, sw, cont))

        y = cont - CARD_GAP
        scroll_target = None   # frame of the card to scroll into view

        # Pinned section
        if pinned:
            y -= SEC
            sl = NSTextField.labelWithString_("Pinned")
            sl.setFont_(NSFont.systemFontOfSize_weight_(11, 0.6))
            sl.setTextColor_(H_ACCENT)
            sl.setFrame_(NSMakeRect(2, y, 80, 15))
            self._container.addSubview_(sl)
            y -= CARD_GAP
            for i, entry in enumerate(pinned):
                ch   = ph[i]
                text = _entry_text(entry)
                app  = _entry_app(entry)
                card = CardView.alloc().initWithFrame_text_index_pinned_appName_onPin_onExpand_onEdit_(
                    NSMakeRect(0, y-ch, sw, ch),
                    text, i+1, True, app, self._handle_pin, self._rebuild, self._handle_edit)
                self._container.addSubview_(card)
                if expanded_card and text == getattr(expanded_card, '_text', None):
                    scroll_target = NSMakeRect(0, y-ch, sw, ch)
                y -= ch + CARD_GAP

        # Recent section
        if recent:
            y -= SEC
            sl2 = NSTextField.labelWithString_("Recent activity")
            sl2.setFont_(NSFont.systemFontOfSize_weight_(11, 0.6))
            sl2.setTextColor_(CARD_SUB)
            sl2.setFrame_(NSMakeRect(2, y, 140, 15))
            self._container.addSubview_(sl2)
            y -= CARD_GAP
            for i, entry in enumerate(recent):
                ch   = rh[i]
                text = _entry_text(entry)
                app  = _entry_app(entry)
                card = CardView.alloc().initWithFrame_text_index_pinned_appName_onPin_onExpand_onEdit_(
                    NSMakeRect(0, y-ch, sw, ch),
                    text, i+1, False, app, self._handle_pin, self._rebuild, self._handle_edit)
                self._container.addSubview_(card)
                if expanded_card and text == getattr(expanded_card, '_text', None):
                    scroll_target = NSMakeRect(0, y-ch, sw, ch)
                y -= ch + CARD_GAP

        # Scroll expanded card into view with padding
        if scroll_target is not None:
            from Foundation import NSInsetRect
            # Add vertical padding so card isn't flush against edge
            padded = NSMakeRect(
                scroll_target.origin.x,
                scroll_target.origin.y - 16,
                scroll_target.size.width,
                scroll_target.size.height + 32
            )
            self._container.scrollRectToVisible_(padded)

    # ── By App tab ────────────────────────────────────────────────────────────
    def _rebuild_by_app(self):
        if not self._container: return
        _copy_cbs.clear()
        for sv in list(self._container.subviews()): sv.removeFromSuperview()

        sw  = self._scroll.frame().size.width
        cfg = self._app.config
        hist = cfg.get("history", [])

        # Group entries by app name
        from collections import OrderedDict
        groups = OrderedDict()
        for entry in hist[:100]:
            app = _entry_app(entry) or "Other"
            groups.setdefault(app, []).append(entry)

        if not groups:
            e = NSTextField.wrappingLabelWithString_(
                "No transcriptions yet.\nHold Right ⌘ to start recording.")
            e.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.0))
            e.setTextColor_(CARD_SUB)
            e.setAlignment_(NSTextAlignmentCenter)
            e.setFrame_(NSMakeRect(0, 60, sw, 44))
            self._container.addSubview_(e)
            self._container.setFrame_(NSMakeRect(0, 0, sw, 160))
            return

        # Calculate total height
        heights = []
        for app_name, entries in groups.items():
            collapsed = self._app_groups.get(app_name, True)
            heights.append(_app_group_h(entries, collapsed))

        total    = sum(heights) + CARD_GAP * (len(heights) + 1)
        scroll_h = self._scroll.frame().size.height
        cont     = max(total, scroll_h)
        self._container.setFrame_(NSMakeRect(0, 0, sw, cont))

        y = cont - CARD_GAP
        for i, (app_name, entries) in enumerate(groups.items()):
            ch       = heights[i]
            collapsed = self._app_groups.get(app_name, True)

            def make_toggle(name):
                def toggle():
                    self._app_groups[name] = not self._app_groups.get(name, True)
                    self._rebuild_by_app()
                return toggle

            grp = AppGroupView.alloc().initWithFrame_appName_entries_onExpand_(
                NSMakeRect(0, y-ch, sw, ch),
                app_name, entries, make_toggle(app_name))
            grp._collapsed = collapsed
            grp._build()
            self._container.addSubview_(grp)
            y -= ch + CARD_GAP

    # ── Stats tab ─────────────────────────────────────────────────────────────
    def _rebuild_stats(self):
        if not self._container: return
        for sv in list(self._container.subviews()): sv.removeFromSuperview()

        sw  = self._scroll.frame().size.width
        cfg = self._app.config
        hist = cfg.get("history", [])

        # Aggregate per-app stats
        from collections import defaultdict
        app_words = defaultdict(int)
        app_clips = defaultdict(int)
        for entry in hist:
            app  = _entry_app(entry) or "Other"
            text = _entry_text(entry)
            app_words[app] += len(text.split())
            app_clips[app] += 1

        if not app_words:
            e = NSTextField.wrappingLabelWithString_(
                "No transcriptions yet.\nHold Right ⌘ to start recording.")
            e.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.0))
            e.setTextColor_(CARD_SUB)
            e.setAlignment_(NSTextAlignmentCenter)
            e.setFrame_(NSMakeRect(0, 60, sw, 44))
            self._container.addSubview_(e)
            self._container.setFrame_(NSMakeRect(0, 0, sw, 160))
            return

        # Sort by word count descending
        sorted_apps = sorted(app_words.items(), key=lambda x: x[1], reverse=True)
        max_words   = sorted_apps[0][1] if sorted_apps else 1

        ROW_H   = 52
        SEC_H   = 28
        total_h = SEC_H + len(sorted_apps) * (ROW_H + CARD_GAP) + CARD_GAP + 60
        scroll_h = self._scroll.frame().size.height
        cont    = max(total_h, scroll_h)
        self._container.setFrame_(NSMakeRect(0, 0, sw, cont))

        y = cont - CARD_GAP

        # Summary header card
        total_clips = sum(app_clips.values())
        total_words = sum(app_words.values())
        from datetime import date as _date
        daily = cfg.get("daily", {"date": "", "words": 0})
        today_words = daily.get("words", 0) if daily.get("date") == str(_date.today()) else 0

        summary = NSView.alloc().initWithFrame_(NSMakeRect(0, y - 56, sw, 56))
        summary.setWantsLayer_(True)
        summary.layer().setBackgroundColor_(H_BG.CGColor())
        summary.layer().setCornerRadius_(CARD_R)

        for col, (val, label) in enumerate([
            (str(total_clips), "clips"),
            (str(total_words), "words"),
            (str(today_words), "today"),
        ]):
            col_x = col * (sw / 3)
            vl = NSTextField.labelWithString_(val)
            vl.setFont_(NSFont.systemFontOfSize_weight_(18, 0.6))
            vl.setTextColor_(H_ACCENT)
            vl.setAlignment_(NSTextAlignmentCenter)
            vl.setFrame_(NSMakeRect(col_x, 10, sw/3, 22))
            summary.addSubview_(vl)
            ll = NSTextField.labelWithString_(label)
            ll.setFont_(NSFont.systemFontOfSize_weight_(9.5, -0.3))
            ll.setTextColor_(H_MUTED)
            ll.setAlignment_(NSTextAlignmentCenter)
            ll.setFrame_(NSMakeRect(col_x, 32, sw/3, 12))
            summary.addSubview_(ll)

        self._container.addSubview_(summary)
        y -= 56 + CARD_GAP * 2

        # Section label
        sec = NSTextField.labelWithString_("By application")
        sec.setFont_(NSFont.systemFontOfSize_weight_(10, -0.3))
        sec.setTextColor_(CARD_SUB)
        sec.setFrame_(NSMakeRect(2, y - 14, 140, 13))
        self._container.addSubview_(sec)
        y -= SEC_H

        # App rows
        for app_name, words in sorted_apps:
            clips = app_clips[app_name]
            row   = _make_stat_row(0, y - ROW_H, sw, app_name, words, clips, max_words)
            self._container.addSubview_(row)
            y -= ROW_H + CARD_GAP

    # ── Settings page ─────────────────────────────────────────────────────────
    def _rebuild_settings(self):
        if not self._container: return
        for sv in list(self._container.subviews()): sv.removeFromSuperview()

        from app.config import save_config
        sw  = self._scroll.frame().size.width
        cfg = self._app.config

        # Calculate needed height dynamically
        sync_enabled = cfg.get("sync_enabled", False)
        needed_h = (
            20 +          # top padding
            18 +          # API Keys section label
            88 +          # Groq key row
            88 +          # Gemini key row
            12 + 18 +     # Model section label
            68 +          # model row
            12 + 18 +     # Recording section label
            68 +          # toggle row
            88 +          # hold hotkey row
            88 +          # toggle hotkey row
            12 + 18 +     # Sync section label
            68 +          # sync toggle row
            (68 + 68 if sync_enabled else 0) +  # user ID + device name rows
            12 + 48 +     # info row
            20            # bottom padding
        )
        scroll_h = self._scroll.frame().size.height
        cont_h   = max(scroll_h, needed_h)
        self._container.setFrame_(NSMakeRect(0, 0, sw, cont_h))

        y = cont_h - 8   # top-down cursor

        def section_label(title, yy):
            lbl = NSTextField.labelWithString_(title.upper())
            lbl.setFont_(NSFont.systemFontOfSize_weight_(9, 0.7))
            lbl.setTextColor_(CARD_SUB)
            lbl.setFrame_(NSMakeRect(2, yy - 14, sw, 13))
            self._container.addSubview_(lbl)

        def hotkey_row(label, mode, keycode, yy):
            row = NSView.alloc().initWithFrame_(NSMakeRect(0, yy - 80, sw, 80))
            row.setWantsLayer_(True)
            row.layer().setBackgroundColor_(CARD_BG.CGColor())
            row.layer().setCornerRadius_(CARD_R)
            row.layer().setShadowOpacity_(0.04)
            row.layer().setShadowRadius_(4)
            self._container.addSubview_(row)

            tl = NSTextField.labelWithString_(label)
            tl.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.5))
            tl.setTextColor_(CARD_TEXT)
            tl.setFrame_(NSMakeRect(14, 54, sw - 28, 16))
            row.addSubview_(tl)

            is_rec = (self._recording_hotkey_for == mode)
            if is_rec:
                key_text = "Press any key..."
                color = H_ACCENT
            else:
                key_text = _keycode_to_name(keycode)
                color = CARD_SUB

            sl = NSTextField.labelWithString_(key_text)
            sl.setFont_(NSFont.systemFontOfSize_weight_(11, -0.2))
            sl.setTextColor_(color)
            sl.setFrame_(NSMakeRect(14, 36, sw - 100, 14))
            row.addSubview_(sl)

            rec_d = _d(lambda: self._start_hotkey_record(mode))
            rb = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 90, 10, 76, 26))
            rb.setBordered_(False); rb.setWantsLayer_(True)
            rb.layer().setCornerRadius_(8)
            rb.layer().setBackgroundColor_(H_ACCENT.CGColor() if is_rec else H_BG.CGColor())
            rb.setAttributedTitle_(_attr(
                "Cancel" if is_rec else "Record",
                _hex("FFFFFF") if is_rec else H_TEXT,
                NSFont.systemFontOfSize_weight_(10.5, 0.5)))
            rb.setTarget_(rec_d); rb.setAction_(objc.selector(rec_d.fire_, signature=b'v@:@'))
            row.addSubview_(rb)
            return row

        def divider(yy):
            d = NSView.alloc().initWithFrame_(NSMakeRect(0, yy, sw, 1))
            d.setWantsLayer_(True)
            d.layer().setBackgroundColor_(_hex("E8E5E0").CGColor())
            self._container.addSubview_(d)

        def key_row(label, keys, yy, add_cb, remove_cb):
            """Render a key management row: label + masked keys + add/remove."""
            row = NSView.alloc().initWithFrame_(NSMakeRect(0, yy - 80, sw, 80))
            row.setWantsLayer_(True)
            row.layer().setBackgroundColor_(CARD_BG.CGColor())
            row.layer().setCornerRadius_(CARD_R)
            row.layer().setShadowOpacity_(0.04)
            row.layer().setShadowRadius_(4)
            self._container.addSubview_(row)

            # Label
            tl = NSTextField.labelWithString_(label)
            tl.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.5))
            tl.setTextColor_(CARD_TEXT)
            tl.setFrame_(NSMakeRect(14, 54, sw - 28, 16))
            row.addSubview_(tl)

            # Keys list
            if keys:
                key_str = "  ·  ".join(f"...{k[-8:]}" for k in keys)
                status_color = _hex("3DAA6E")
                status_text  = f"✓  {key_str}"
            else:
                status_text  = "No key configured"
                status_color = CARD_SUB

            sl = NSTextField.labelWithString_(status_text)
            sl.setFont_(NSFont.systemFontOfSize_weight_(10.5, -0.3))
            sl.setTextColor_(status_color)
            sl.setFrame_(NSMakeRect(14, 36, sw - 100, 14))
            row.addSubview_(sl)

            # Add button
            add_d = _d(add_cb)
            ab = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 90, 10, 76, 26))
            ab.setBordered_(False); ab.setWantsLayer_(True)
            ab.layer().setCornerRadius_(8)
            ab.layer().setBackgroundColor_(H_BG.CGColor())
            ab.setAttributedTitle_(_attr("+ Add key", H_TEXT, NSFont.systemFontOfSize_weight_(10.5, 0.5)))
            ab.setTarget_(add_d); ab.setAction_(objc.selector(add_d.fire_, signature=b'v@:@'))
            row.addSubview_(ab)

            # Remove last button (only if keys exist)
            if keys:
                rm_d = _d(remove_cb)
                rb = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 90, 40, 76, 20))
                rb.setBordered_(False); rb.setWantsLayer_(True)
                rb.layer().setCornerRadius_(6)
                rb.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
                rb.setAttributedTitle_(_attr("Remove last", _hex("E05A2B"), NSFont.systemFontOfSize_weight_(9.5, -0.3)))
                rb.setTarget_(rm_d); rb.setAction_(objc.selector(rm_d.fire_, signature=b'v@:@'))
                row.addSubview_(rb)

            return row

        def toggle_row(label, sublabel, value, yy, on_toggle):
            row = NSView.alloc().initWithFrame_(NSMakeRect(0, yy - 60, sw, 60))
            row.setWantsLayer_(True)
            row.layer().setBackgroundColor_(CARD_BG.CGColor())
            row.layer().setCornerRadius_(CARD_R)
            row.layer().setShadowOpacity_(0.04)
            row.layer().setShadowRadius_(4)
            self._container.addSubview_(row)

            tl = NSTextField.labelWithString_(label)
            tl.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.5))
            tl.setTextColor_(CARD_TEXT)
            tl.setFrame_(NSMakeRect(14, 34, sw - 80, 16))
            row.addSubview_(tl)

            sl = NSTextField.labelWithString_(sublabel)
            sl.setFont_(NSFont.systemFontOfSize_weight_(10.5, -0.3))
            sl.setTextColor_(CARD_SUB)
            sl.setFrame_(NSMakeRect(14, 14, sw - 80, 14))
            row.addSubview_(sl)

            # Toggle pill
            tog_d = _d(on_toggle)
            tb = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 62, 18, 48, 24))
            tb.setBordered_(False); tb.setWantsLayer_(True)
            tb.layer().setCornerRadius_(12)
            tb.layer().setBackgroundColor_(
                H_ACCENT.CGColor() if value else _hex("DEDAD4").CGColor())
            tb.setAttributedTitle_(_attr(
                "ON" if value else "OFF",
                _hex("FFFFFF") if value else CARD_SUB,
                NSFont.systemFontOfSize_weight_(9.5, 0.6)))
            tb.setTarget_(tog_d); tb.setAction_(objc.selector(tog_d.fire_, signature=b'v@:@'))
            row.addSubview_(tb)

        def model_row(yy):
            row = NSView.alloc().initWithFrame_(NSMakeRect(0, yy - 60, sw, 60))
            row.setWantsLayer_(True)
            row.layer().setBackgroundColor_(CARD_BG.CGColor())
            row.layer().setCornerRadius_(CARD_R)
            row.layer().setShadowOpacity_(0.04)
            row.layer().setShadowRadius_(4)
            self._container.addSubview_(row)

            tl = NSTextField.labelWithString_("Whisper model")
            tl.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.5))
            tl.setTextColor_(CARD_TEXT)
            tl.setFrame_(NSMakeRect(14, 34, 160, 16))
            row.addSubview_(tl)

            current = cfg.get("whisper_model", "base")
            models  = ["tiny", "base", "small", "medium"]
            bw = (sw - 28 - 160 - 12) / len(models)
            for mi, m in enumerate(models):
                is_sel = (m == current)
                md = _d(lambda mn=m: self._set_model(mn))
                mb = NSButton.alloc().initWithFrame_(NSMakeRect(160 + 12 + mi * (bw + 4), 16, bw, 26))
                mb.setBordered_(False); mb.setWantsLayer_(True)
                mb.layer().setCornerRadius_(8)
                mb.layer().setBackgroundColor_(
                    H_BG.CGColor() if is_sel else _hex("ECEAE6").CGColor())
                mb.setAttributedTitle_(_attr(
                    m,
                    H_TEXT if is_sel else CARD_SUB,
                    NSFont.systemFontOfSize_weight_(10.5, 0.5 if is_sel else 0.0)))
                mb.setTarget_(md); mb.setAction_(objc.selector(md.fire_, signature=b'v@:@'))
                row.addSubview_(mb)

        # ── API Keys section ──────────────────────────────────────────────
        y -= 20
        section_label("API Keys", y)
        y -= 18

        # Groq key row
        groq_keys = cfg.get("groq_api_keys", [])
        key_row(
            "Groq  —  transcription + formatting",
            groq_keys, y,
            add_cb    = self._add_groq_key,
            remove_cb = self._remove_groq_key,
        )
        y -= 88

        # Gemini key row
        gemini_keys = cfg.get("gemini_api_keys", [])
        key_row(
            "Gemini  —  formatting fallback",
            gemini_keys, y,
            add_cb    = self._add_gemini_key,
            remove_cb = self._remove_gemini_key,
        )
        y -= 88

        # ── Model section ─────────────────────────────────────────────────
        y -= 12
        section_label("Local Whisper Model", y)
        y -= 18
        model_row(y)
        y -= 68

        # ── Recording section ─────────────────────────────────────────────
        y -= 12
        section_label("Recording", y)
        y -= 18

        mode = cfg.get("recording_mode", "toggle")
        toggle_row(
            "Hold mode",
            "Hold Right ⌘ to record, release to stop",
            mode == "hold", y,
            lambda: self._set_recording_mode("hold" if mode != "hold" else "toggle")
        )
        y -= 68

        hotkey_row(
            "Push-to-talk Key",
            "hold",
            cfg.get("hotkey_hold", 54), y
        )
        y -= 88

        hotkey_row(
            "Toggle Key",
            "toggle",
            cfg.get("hotkey_toggle", 54), y
        )
        y -= 88

        # ── Sync section ──────────────────────────────────────────────────
        y -= 12
        section_label("Cross-Device Sync", y)
        y -= 18

        sync_enabled = cfg.get("sync_enabled", False)
        toggle_row(
            "Enable sync",
            "Transcriptions appear on all devices instantly",
            sync_enabled, y,
            lambda: self._toggle_sync()
        )
        y -= 68

        if sync_enabled:
            # User ID row
            uid_row = NSView.alloc().initWithFrame_(NSMakeRect(0, y - 60, sw, 60))
            uid_row.setWantsLayer_(True)
            uid_row.layer().setBackgroundColor_(CARD_BG.CGColor())
            uid_row.layer().setCornerRadius_(CARD_R)
            uid_row.layer().setShadowOpacity_(0.04)
            uid_row.layer().setShadowRadius_(4)
            self._container.addSubview_(uid_row)

            uid_lbl = NSTextField.labelWithString_("User ID")
            uid_lbl.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.5))
            uid_lbl.setTextColor_(CARD_TEXT)
            uid_lbl.setFrame_(NSMakeRect(14, 34, 100, 16))
            uid_row.addSubview_(uid_lbl)

            uid_val = cfg.get("sync_user_id", "") or "Not set"
            uid_sub = NSTextField.labelWithString_(uid_val)
            uid_sub.setFont_(NSFont.systemFontOfSize_weight_(10.5, -0.3))
            uid_sub.setTextColor_(
                _hex("3DAA6E") if cfg.get("sync_user_id") else CARD_SUB)
            uid_sub.setFrame_(NSMakeRect(14, 14, sw - 110, 14))
            uid_row.addSubview_(uid_sub)

            set_d = _d(self._set_sync_user_id)
            sb = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 90, 18, 76, 26))
            sb.setBordered_(False); sb.setWantsLayer_(True)
            sb.layer().setCornerRadius_(8)
            sb.layer().setBackgroundColor_(H_BG.CGColor())
            sb.setAttributedTitle_(_attr("Set ID", H_TEXT, NSFont.systemFontOfSize_weight_(10.5, 0.5)))
            sb.setTarget_(set_d); sb.setAction_(objc.selector(set_d.fire_, signature=b'v@:@'))
            uid_row.addSubview_(sb)
            y -= 68

            # Device name row
            dev_row = NSView.alloc().initWithFrame_(NSMakeRect(0, y - 60, sw, 60))
            dev_row.setWantsLayer_(True)
            dev_row.layer().setBackgroundColor_(CARD_BG.CGColor())
            dev_row.layer().setCornerRadius_(CARD_R)
            dev_row.layer().setShadowOpacity_(0.04)
            dev_row.layer().setShadowRadius_(4)
            self._container.addSubview_(dev_row)

            dev_lbl = NSTextField.labelWithString_("Device name")
            dev_lbl.setFont_(NSFont.systemFontOfSize_weight_(12.5, 0.5))
            dev_lbl.setTextColor_(CARD_TEXT)
            dev_lbl.setFrame_(NSMakeRect(14, 34, 120, 16))
            dev_row.addSubview_(dev_lbl)

            import platform as _platform
            dev_val = cfg.get("sync_device_name", "") or _platform.node()
            dev_sub = NSTextField.labelWithString_(dev_val)
            dev_sub.setFont_(NSFont.systemFontOfSize_weight_(10.5, -0.3))
            dev_sub.setTextColor_(CARD_SUB)
            dev_sub.setFrame_(NSMakeRect(14, 14, sw - 110, 14))
            dev_row.addSubview_(dev_sub)

            dn_d = _d(self._set_device_name)
            dnb = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 90, 18, 76, 26))
            dnb.setBordered_(False); dnb.setWantsLayer_(True)
            dnb.layer().setCornerRadius_(8)
            dnb.layer().setBackgroundColor_(H_BG.CGColor())
            dnb.setAttributedTitle_(_attr("Change", H_TEXT, NSFont.systemFontOfSize_weight_(10.5, 0.5)))
            dnb.setTarget_(dn_d); dnb.setAction_(objc.selector(dn_d.fire_, signature=b'v@:@'))
            dev_row.addSubview_(dnb)
            y -= 68

        # ── Info row ──────────────────────────────────────────────────────
        y -= 12
        info = NSTextField.wrappingLabelWithString_(
            "Groq API keys are free at console.groq.com\n"
            "They handle both transcription (Whisper) and formatting (LLaMA).\n"
            "Sync uses Supabase Realtime — same User ID on all devices."
        )
        info.setFont_(NSFont.systemFontOfSize_weight_(10, -0.3))
        info.setTextColor_(CARD_SUB)
        info.setFrame_(NSMakeRect(2, y - 40, sw - 4, 40))
        self._container.addSubview_(info)

    # ── Settings actions ──────────────────────────────────────────────────────
    def _add_groq_key(self):
        import rumps
        r = rumps.Window(
            message="Paste your Groq API key\n(free at console.groq.com)",
            title="Add Groq Key",
            default_text="", ok="Save", cancel="Cancel",
            dimensions=(380, 60)
        ).run()
        if r.clicked and r.text.strip():
            from app.config import save_config
            keys = self._app.config.get("groq_api_keys", [])
            key  = r.text.strip()
            if key not in keys:
                keys.append(key)
                self._app.config["groq_api_keys"] = keys
                save_config(self._app.config)
            self._rebuild_settings()

    def _remove_groq_key(self):
        from app.config import save_config
        keys = self._app.config.get("groq_api_keys", [])
        if keys:
            keys.pop()
            self._app.config["groq_api_keys"] = keys
            save_config(self._app.config)
        self._rebuild_settings()

    def _add_gemini_key(self):
        import rumps
        r = rumps.Window(
            message="Paste your Gemini API key\n(free at aistudio.google.com/apikey)",
            title="Add Gemini Key",
            default_text="", ok="Save", cancel="Cancel",
            dimensions=(380, 60)
        ).run()
        if r.clicked and r.text.strip():
            from app.config import save_config, add_gemini_key
            self._app.config = add_gemini_key(self._app.config, r.text.strip())
            self._rebuild_settings()

    def _remove_gemini_key(self):
        from app.config import save_config, remove_gemini_key
        keys = self._app.config.get("gemini_api_keys", [])
        if keys:
            self._app.config = remove_gemini_key(self._app.config, len(keys) - 1)
        self._rebuild_settings()

    def _set_model(self, model_name):
        from app.config import save_config
        self._app.config["whisper_model"] = model_name
        save_config(self._app.config)
        # Sync menu bar model items
        for name, item in self._app.model_items.items():
            item.state = 1 if name == model_name else 0
        self._rebuild_settings()

    def _set_recording_mode(self, mode):
        from app.config import save_config
        self._app.config["recording_mode"] = mode
        self._app._mode = mode
        save_config(self._app.config)
        self._rebuild_settings()

    def _toggle_sync(self):
        from app.config import save_config
        self._app.config["sync_enabled"] = not self._app.config.get("sync_enabled", False)
        save_config(self._app.config)
        # Restart sync client
        if self._app._sync:
            self._app._sync.stop()
            self._app._sync = None
        self._app._init_sync()
        self._rebuild_settings()

    def _set_sync_user_id(self):
        import rumps
        r = rumps.Window(
            message="Enter a unique User ID (same on all your devices).\nExample: your email or any unique string.",
            title="Set Sync User ID",
            default_text=self._app.config.get("sync_user_id", ""),
            ok="Save", cancel="Cancel",
            dimensions=(380, 60)
        ).run()
        if r.clicked and r.text.strip():
            from app.config import save_config
            self._app.config["sync_user_id"] = r.text.strip()
            save_config(self._app.config)
            # Restart sync with new ID
            if self._app._sync:
                self._app._sync.stop()
                self._app._sync = None
            self._app._init_sync()
            self._rebuild_settings()

    def _set_device_name(self):
        import rumps
        r = rumps.Window(
            message="Enter a name for this device (shown on other devices when syncing).",
            title="Set Device Name",
            default_text=self._app.config.get("sync_device_name", ""),
            ok="Save", cancel="Cancel",
            dimensions=(380, 60)
        ).run()
        if r.clicked and r.text.strip():
            from app.config import save_config
            self._app.config["sync_device_name"] = r.text.strip()
            save_config(self._app.config)
            self._rebuild_settings()

    # ── Notes tab ─────────────────────────────────────────────────────────────
    def _rebuild_notes(self):
        if not self._container: return
        for sv in list(self._container.subviews()): sv.removeFromSuperview()
        sw = self._scroll.frame().size.width
        sh = self._scroll.frame().size.height
        self._container.setFrame_(NSMakeRect(0, 0, sw, sh))

        # Trigger initial load if no data loaded yet
        if not hasattr(self, '_notes_loaded_once'):
            self._notes_loaded_once = True
            threading.Thread(target=self._notes_load, daemon=True).start()
            # Show loading placeholder while fetching
            spin = NSTextField.labelWithString_("Loading notes...")
            spin.setFont_(NSFont.systemFontOfSize_(13))
            spin.setTextColor_(H_MUTED)
            spin.setFrame_(NSMakeRect(sw / 2 - 60, sh / 2 - 10, 120, 20))
            self._container.addSubview_(spin)
            return

        LIST_W = 240
        PAD = 16

        # ── Sidebar (left) ──────────────────────────────────────────────
        sidebar = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, LIST_W, sh))
        sidebar.setWantsLayer_(True)
        sidebar.layer().setBackgroundColor_(_hex("F7F5F1").CGColor())
        self._container.addSubview_(sidebar)

        # New note button
        new_d = _d(self._notes_new)
        new_btn = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, sh - 52, LIST_W - 2 * PAD, 32))
        new_btn.setBordered_(False); new_btn.setWantsLayer_(True)
        new_btn.layer().setCornerRadius_(8)
        new_btn.layer().setBackgroundColor_(H_ACCENT.CGColor())
        new_btn.setAttributedTitle_(_attr("+ New Note", H_SHEET, NSFont.systemFontOfSize_weight_(13, 0.500)))
        new_btn.setTarget_(new_d)
        new_btn.setAction_(objc.selector(new_d.fire_, signature=b'v@:@'))
        sidebar.addSubview_(new_btn)

        # Search
        search = NSTextField.alloc().initWithFrame_(NSMakeRect(PAD, sh - 90, LIST_W - 2 * PAD, 26))
        search.setPlaceholderString_("Search notes...")
        search.setFont_(NSFont.systemFontOfSize_(12))
        search.setBordered_(True)
        search.setBezeled_(True)
        search.setBezelStyle_(NSRoundedBezelStyle)
        sidebar.addSubview_(search)

        # Refresh
        ref_d = _d(self._notes_load)
        ref_btn = NSButton.alloc().initWithFrame_(NSMakeRect(LIST_W - 60, sh - 90, 26, 26))
        ref_btn.setBordered_(False)
        ref_btn.setTitle_("↻")
        ref_btn.setFont_(NSFont.systemFontOfSize_(14))
        ref_btn.setTarget_(ref_d)
        ref_btn.setAction_(objc.selector(ref_d.fire_, signature=b'v@:@'))
        sidebar.addSubview_(ref_btn)

        # Note list
        list_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, LIST_W, sh - 100))
        list_scroll.setHasVerticalScroller_(True)
        list_scroll.setDrawsBackground_(False)
        list_scroll.setBorderType_(0)
        sidebar.addSubview_(list_scroll)

        list_content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, LIST_W, max(20, len(self._notes_data) * 58 + 10)))
        list_scroll.setDocumentView_(list_content)

        if not self._notes_data:
            empty = NSTextField.labelWithString_("No notes yet")
            empty.setFont_(NSFont.systemFontOfSize_(12))
            empty.setTextColor_(H_MUTED)
            empty.setFrame_(NSMakeRect(PAD, 10, LIST_W - 2 * PAD, 20))
            list_content.addSubview_(empty)
        else:
            for i, note in enumerate(self._notes_data):
                title = note.get("title", "") or "Untitled"
                content = (note.get("content", "") or "")[:60]
                is_pinned = note.get("is_pinned", False)
                card_y = len(self._notes_data) * 58 - (i + 1) * 58

                # Card background
                card = NSView.alloc().initWithFrame_(NSMakeRect(4, card_y, LIST_W - 8, 52))
                card.setWantsLayer_(True)
                card.layer().setCornerRadius_(6)
                card.layer().setBackgroundColor_(_hex("FFFFFF" if not is_pinned else "FFF7F2").CGColor())
                if is_pinned:
                    card.layer().setBorderWidth_(1.5)
                    card.layer().setBorderColor_(_hex("E05A2B", 0.25).CGColor())
                list_content.addSubview_(card)

                # Pin indicator
                if is_pinned:
                    pin = NSTextField.labelWithString_("📌")
                    pin.setFont_(NSFont.systemFontOfSize_(10))
                    pin.setFrame_(NSMakeRect(8, card_y + 18, 16, 14))
                    list_content.addSubview_(pin)

                # Title
                tl = NSTextField.labelWithString_(title[:40])
                tl.setFont_(NSFont.systemFontOfSize_weight_(12, 0.6))
                tl.setTextColor_(H_TEXT)
                tl.setFrame_(NSMakeRect(is_pinned and 26 or 10, card_y + 28, LIST_W - 34, 16))
                list_content.addSubview_(tl)

                # Preview
                prev = NSTextField.labelWithString_(content)
                prev.setFont_(NSFont.systemFontOfSize_(10))
                prev.setTextColor_(H_MUTED)
                prev.setFrame_(NSMakeRect(is_pinned and 26 or 10, card_y + 10, LIST_W - 34, 14))
                list_content.addSubview_(prev)

                # Click handler
                note_id = note.get("id")
                sel_d = _d(lambda nid=note_id: self._notes_select(nid))

                # Invisible button over card
                card_btn = NSButton.alloc().initWithFrame_(NSMakeRect(4, card_y, LIST_W - 8, 52))
                card_btn.setBordered_(False)
                card_btn.setButtonType_(2)  # NSMomentaryChangeButton
                card_btn.setTarget_(sel_d)
                card_btn.setAction_(objc.selector(sel_d.fire_, signature=b'v@:@'))
                list_content.addSubview_(card_btn)

        # ── Editor pane (right) ──────────────────────────────────────────
        editor_x = LIST_W + 1
        editor_w = sw - LIST_W - 1

        # Divider
        divider = NSView.alloc().initWithFrame_(NSMakeRect(LIST_W, 0, 1, sh))
        divider.setWantsLayer_(True)
        divider.layer().setBackgroundColor_(_hex("E2DDD5").CGColor())
        self._container.addSubview_(divider)

        if not self._notes_selected:
            empty_ed = NSTextField.labelWithString_("Select a note or create a new one")
            empty_ed.setFont_(NSFont.systemFontOfSize_(13))
            empty_ed.setTextColor_(H_MUTED)
            empty_ed.setFrame_(NSMakeRect(editor_x + 40, sh / 2 - 12, editor_w - 80, 24))
            self._container.addSubview_(empty_ed)
            return

        note = self._notes_selected
        title = note.get("title", "")
        content = note.get("content", "")
        note_id = note.get("id")

        # Title input
        self._notes_title_input = NSTextField.alloc().initWithFrame_(NSMakeRect(editor_x + PAD, sh - 48, editor_w - 2 * PAD, 28))
        self._notes_title_input.setStringValue_(title)
        self._notes_title_input.setPlaceholderString_("Note title...")
        self._notes_title_input.setFont_(NSFont.systemFontOfSize_weight_(16, 0.6))
        self._notes_title_input.setBordered_(False)
        self._notes_title_input.setDrawsBackground_(False)
        self._notes_title_input.setTextColor_(H_TEXT)
        self._container.addSubview_(self._notes_title_input)

        # Content text view in scroll
        BAR_H = 36
        content_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(editor_x, BAR_H, editor_w, sh - 48 - BAR_H))
        content_scroll.setHasVerticalScroller_(True)
        content_scroll.setDrawsBackground_(False)
        content_scroll.setBorderType_(0)
        self._container.addSubview_(content_scroll)

        self._notes_text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, editor_w - 20, sh - 48 - BAR_H))
        self._notes_text_view.setString_(content)
        self._notes_text_view.setFont_(NSFont.systemFontOfSize_(13))
        self._notes_text_view.setDrawsBackground_(False)
        self._notes_text_view.setTextColor_(H_TEXT)
        content_scroll.setDocumentView_(self._notes_text_view)

        # Save button
        save_d = _d(self._notes_save_ui)
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(editor_x + PAD, 6, 80, 24))
        save_btn.setBordered_(False); save_btn.setWantsLayer_(True)
        save_btn.layer().setCornerRadius_(6)
        save_btn.layer().setBackgroundColor_(H_ACCENT.CGColor())
        save_btn.setAttributedTitle_(_attr("Save", H_SHEET, NSFont.systemFontOfSize_weight_(11, 0.5)))
        save_btn.setTarget_(save_d)
        save_btn.setAction_(objc.selector(save_d.fire_, signature=b'v@:@'))
        self._container.addSubview_(save_btn)

        # AI Format button
        ai_d = _d(self._notes_format_ai)
        ai_btn = NSButton.alloc().initWithFrame_(NSMakeRect(editor_x + PAD + 90, 6, 100, 24))
        ai_btn.setBordered_(False); ai_btn.setWantsLayer_(True)
        ai_btn.layer().setCornerRadius_(6)
        ai_btn.layer().setBackgroundColor_(_hex("E05A2B", 0.12).CGColor())
        ai_btn.setAttributedTitle_(_attr("✨ Format with AI", H_ACCENT, NSFont.systemFontOfSize_weight_(11, 0.5)))
        ai_btn.setTarget_(ai_d)
        ai_btn.setAction_(objc.selector(ai_d.fire_, signature=b'v@:@'))
        self._container.addSubview_(ai_btn)

        # Delete button
        del_d = _d(lambda: self._notes_delete(note_id))
        del_btn = NSButton.alloc().initWithFrame_(NSMakeRect(editor_x + PAD + 200, 6, 60, 24))
        del_btn.setBordered_(False); del_btn.setWantsLayer_(True)
        del_btn.layer().setCornerRadius_(6)
        del_btn.layer().setBackgroundColor_(_hex("E05A2B", 0.12).CGColor())
        del_btn.setAttributedTitle_(_attr("Delete", H_ACCENT, NSFont.systemFontOfSize_weight_(11, 0.5)))
        del_btn.setTarget_(del_d)
        del_btn.setAction_(objc.selector(del_d.fire_, signature=b'v@:@'))
        self._container.addSubview_(del_btn)

    def _notes_select(self, note_id):
        for n in self._notes_data:
            if n.get("id") == note_id:
                self._notes_selected = n
                self._rebuild_notes()
                return

    def _notes_save_ui(self):
        if self._notes_selected and hasattr(self, '_notes_title_input'):
            title = self._notes_title_input.stringValue() if hasattr(self._notes_title_input, 'stringValue') else ""
            content = self._notes_text_view.string() if hasattr(self._notes_text_view, 'string') else ""
            self._notes_save(self._notes_selected.get("id"), title, content)

    def _notes_save_from_ui(self, title, content):
        if self._notes_selected:
            self._notes_save(self._notes_selected.get("id"), title, content)

    def _notes_load(self):
        import httpx
        from app.sync import SUPABASE_KEY, SUPABASE_URL
        user_id = self._app.config.get("sync_user_id", "")
        if not user_id:
            self._notes_data = []
            return
        try:
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/notes",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"user_id": f"eq.{user_id}", "order": "updated_at.desc", "limit": "200", "select": "*"},
                timeout=8,
            )
            if resp.status_code == 200:
                self._notes_data = resp.json()
        except Exception as e:
            logger.error(f"Notes load failed: {e}")
        self._rebuild_notes()

    def _notes_new(self):
        import rumps
        r = rumps.Window(
            message="",
            title="New Note",
            default_text="",
            ok="Save", cancel="Cancel",
            dimensions=(480, 200),
        ).run()
        if r.clicked and r.text.strip():
            lines = r.text.strip().split('\n', 1)
            title = lines[0] if len(lines) > 0 else ''
            content = lines[1] if len(lines) > 1 else ''
            self._notes_save(None, title, content)

    def _notes_save(self, note_id, title, content):
        import httpx
        from app.sync import SUPABASE_KEY, SUPABASE_URL
        user_id = self._app.config.get("sync_user_id", "")
        device_name = self._app.config.get("sync_device_name", "Mac")
        if not user_id:
            return
        try:
            now = _dt.datetime.now(_dt.timezone.utc).isoformat()
            if note_id:
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/notes?id=eq.{note_id}",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                    json={"title": title, "content": content, "device_name": device_name, "updated_at": now},
                    timeout=10,
                )
            else:
                httpx.post(
                    f"{SUPABASE_URL}/rest/v1/notes",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                    json={"user_id": user_id, "title": title, "content": content, "device_name": device_name, "created_at": now, "updated_at": now},
                    timeout=10,
                )
        except Exception as e:
            logger.error(f"Note save failed: {e}")
        self._notes_load()

    def _notes_delete(self, note_id):
        import httpx
        from app.sync import SUPABASE_KEY, SUPABASE_URL
        try:
            httpx.delete(
                f"{SUPABASE_URL}/rest/v1/notes?id=eq.{note_id}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Note delete failed: {e}")
        self._notes_load()

    def _notes_format_ai(self):
        if not self._notes_selected:
            import rumps
            rumps.alert("Select a note", "Click a note in the list, then use Format.")
            return
        content = ""
        if hasattr(self, '_notes_text_view') and self._notes_text_view:
            content = self._notes_text_view.string() or ""
        if not content.strip():
            import rumps
            rumps.alert("Empty note", "The note has no content to format.")
            return
        api_keys = self._app.config.get("groq_api_keys", [])
        if not api_keys:
            import rumps
            rumps.alert("No API Key", "Add a Groq API key in Settings.")
            return
        import httpx
        from app.ai_cleanup import NOTES_FORMATTER_SYSTEM_PROMPT
        try:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_keys[0]}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": NOTES_FORMATTER_SYSTEM_PROMPT},
                        {"role": "user", "content": f"NOTES TO FORMAT:\n```\n{content}\n```\n\nOutput the formatted markdown only."},
                    ],
                    "temperature": 0, "max_tokens": 4096,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                formatted = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if formatted and hasattr(self, '_notes_text_view') and self._notes_text_view:
                    self._notes_text_view.setString_(formatted)
                    # Auto-save after formatting
                    title = self._notes_title_input.stringValue() if hasattr(self._notes_title_input, 'stringValue') else ""
                    self._notes_save(self._notes_selected.get("id"), title, formatted)
        except Exception as e:
            logger.error(f"AI note format failed: {e}")

    # ── Canvas tab ────────────────────────────────────────────────────────────
    def _rebuild_canvas(self):
        """Render the Canvas tab inside the scroll container."""
        if not self._container: return
        for sv in list(self._container.subviews()): sv.removeFromSuperview()

        sw = self._scroll.frame().size.width
        sh = self._scroll.frame().size.height
        self._container.setFrame_(NSMakeRect(0, 0, sw, sh))

        # Load current canvas content from Supabase (async) — only on first open
        if not self._canvas_loaded:
            threading.Thread(target=self._canvas_load, daemon=True).start()

        BAR_H   = 40
        IMG_H   = 180   # image preview height when visible
        text_h  = sh - BAR_H - (IMG_H if self._canvas_image_url else 0)

        # ── Image preview (shown when image_url is set) ───────────────────
        if self._canvas_image_url:
            from AppKit import NSImageView, NSImageScaleProportionallyUpOrDown
            img_panel = NSView.alloc().initWithFrame_(NSMakeRect(0, sh - BAR_H - IMG_H, sw, IMG_H))
            img_panel.setWantsLayer_(True)
            img_panel.layer().setBackgroundColor_(_hex("ECEAE6").CGColor())
            self._container.addSubview_(img_panel)

            # Load image async and display
            threading.Thread(
                target=self._load_image_into_view,
                args=(self._canvas_image_url, img_panel, sw, IMG_H),
                daemon=True
            ).start()

            # Remove image button
            rm_d = _d(self._canvas_remove_image)
            rm_btn = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 80, IMG_H - 28, 68, 22))
            rm_btn.setBordered_(False); rm_btn.setWantsLayer_(True)
            rm_btn.layer().setCornerRadius_(6)
            rm_btn.layer().setBackgroundColor_(_hex("E05A2B", 0.15).CGColor())
            rm_btn.setAttributedTitle_(_attr("✕ Remove", H_ACCENT, NSFont.systemFontOfSize_weight_(10, 0.4)))
            rm_btn.setTarget_(rm_d)
            rm_btn.setAction_(objc.selector(rm_d.fire_, signature=b'v@:@'))
            img_panel.addSubview_(rm_btn)

        # ── Canvas text view ──────────────────────────────────────────────
        from AppKit import NSTextView, NSScrollView as _NSScroll
        text_y = BAR_H
        text_scroll = _NSScroll.alloc().initWithFrame_(NSMakeRect(0, text_y, sw, text_h))
        text_scroll.setHasVerticalScroller_(True)
        text_scroll.setDrawsBackground_(False)

        self._canvas_text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, sw, text_h))
        self._canvas_text_view.setFont_(NSFont.systemFontOfSize_weight_(14, -0.3))
        self._canvas_text_view.setTextColor_(CARD_TEXT)
        self._canvas_text_view.setBackgroundColor_(_hex("FAFAF8"))
        self._canvas_text_view.setEditable_(True)
        self._canvas_text_view.setRichText_(False)
        self._canvas_text_view.setAutomaticQuoteSubstitutionEnabled_(False)
        self._canvas_text_view.setTextContainerInset_((16, 12))
        self._canvas_text_view.textContainer().setLineFragmentPadding_(0)
        self._canvas_text_view.setString_(
            "Paste or type here…\n\nClick Save to sync to all devices.")
        self._canvas_text_view.setTextColor_(CARD_SUB)

        text_scroll.setDocumentView_(self._canvas_text_view)
        self._container.addSubview_(text_scroll)

        # ── Bottom bar: status + Save button ─────────────────────────────
        bar = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, sw, 40))
        bar.setWantsLayer_(True)
        bar.layer().setBackgroundColor_(_hex("F2EFE9").CGColor())
        self._container.addSubview_(bar)

        self._canvas_status = NSTextField.labelWithString_("Not saved")
        self._canvas_status.setFont_(NSFont.systemFontOfSize_weight_(10, -0.3))
        self._canvas_status.setTextColor_(CARD_SUB)
        self._canvas_status.setFrame_(NSMakeRect(12, 12, sw - 200, 16))
        bar.addSubview_(self._canvas_status)

        # Paste Image button
        paste_img_d = _d(self._canvas_paste_image_from_clipboard)
        paste_img_btn = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 430, 8, 80, 24))
        paste_img_btn.setBordered_(False); paste_img_btn.setWantsLayer_(True)
        paste_img_btn.layer().setCornerRadius_(8)
        paste_img_btn.layer().setBackgroundColor_(_hex("ECEAE6").CGColor())
        paste_img_btn.setAttributedTitle_(_attr("⌘V Image", CARD_TEXT, NSFont.systemFontOfSize_weight_(11, 0.4)))
        paste_img_btn.setTarget_(paste_img_d)
        paste_img_btn.setAction_(objc.selector(paste_img_d.fire_, signature=b'v@:@'))
        paste_img_btn.setToolTip_("Paste image from clipboard and sync to all devices")
        bar.addSubview_(paste_img_btn)

        # Clear button
        clear_d = _d(self._canvas_clear)
        clear_btn = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 340, 8, 80, 24))
        clear_btn.setBordered_(False); clear_btn.setWantsLayer_(True)
        clear_btn.layer().setCornerRadius_(8)
        clear_btn.layer().setBackgroundColor_(_hex("E05A2B", 0.10).CGColor())
        clear_btn.setAttributedTitle_(_attr("✕ Clear", H_ACCENT, NSFont.systemFontOfSize_weight_(11, 0.4)))
        clear_btn.setTarget_(clear_d)
        clear_btn.setAction_(objc.selector(clear_d.fire_, signature=b'v@:@'))
        bar.addSubview_(clear_btn)

        # Refresh button — force reload from cloud
        refresh_d = _d(lambda: threading.Thread(target=self._canvas_force_reload, daemon=True).start())
        refresh_btn = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 250, 8, 70, 24))
        refresh_btn.setBordered_(False); refresh_btn.setWantsLayer_(True)
        refresh_btn.layer().setCornerRadius_(8)
        refresh_btn.layer().setBackgroundColor_(_hex("ECEAE6").CGColor())
        refresh_btn.setAttributedTitle_(_attr("↻ Refresh", CARD_TEXT, NSFont.systemFontOfSize_weight_(11, 0.4)))
        refresh_btn.setTarget_(refresh_d)
        refresh_btn.setAction_(objc.selector(refresh_d.fire_, signature=b'v@:@'))
        bar.addSubview_(refresh_btn)

        # Copy button
        copy_d = _d(self._canvas_copy)
        copy_btn = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 170, 8, 60, 24))
        copy_btn.setBordered_(False); copy_btn.setWantsLayer_(True)
        copy_btn.layer().setCornerRadius_(8)
        copy_btn.layer().setBackgroundColor_(_hex("ECEAE6").CGColor())
        copy_btn.setAttributedTitle_(_attr("⎘ Copy", CARD_TEXT, NSFont.systemFontOfSize_weight_(11, 0.4)))
        copy_btn.setTarget_(copy_d)
        copy_btn.setAction_(objc.selector(copy_d.fire_, signature=b'v@:@'))
        bar.addSubview_(copy_btn)

        # Save & Sync button
        save_d = _d(self._canvas_save)
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(sw - 100, 8, 88, 24))
        save_btn.setBordered_(False); save_btn.setWantsLayer_(True)
        save_btn.layer().setCornerRadius_(8)
        save_btn.layer().setBackgroundColor_(H_BG.CGColor())
        save_btn.setAttributedTitle_(_attr("Save & Sync", H_TEXT, NSFont.systemFontOfSize_weight_(11, 0.5)))
        save_btn.setTarget_(save_d)
        save_btn.setAction_(objc.selector(save_d.fire_, signature=b'v@:@'))
        bar.addSubview_(save_btn)

    def _canvas_load(self):
        """Fetch canvas content from Supabase and populate the text view."""
        try:
            import httpx
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            user_id = self._app.config.get("sync_user_id", "")
            if not user_id:
                return
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/canvas",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"user_id": f"eq.{user_id}", "select": "content,image_url"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    content   = data[0].get("content", "")
                    image_url = data[0].get("image_url")
                    def apply(c=content, img=image_url):
                        if self._canvas_text_view and c:
                            self._canvas_text_view.setString_(c)
                            self._canvas_text_view.setTextColor_(CARD_TEXT)
                        if self._canvas_status and (c or img):
                            self._canvas_status.setStringValue_("Loaded from cloud")
                        self._canvas_loaded = True
                        if img != self._canvas_image_url:
                            self._canvas_image_url = img
                            self._rebuild_canvas()   # re-render to show image panel
                        elif img:
                            threading.Thread(target=self._copy_image_to_clipboard, args=(img,), daemon=True).start()
                    self._app._on_main(apply)
        except Exception as e:
            logger.error(f"Canvas load error: {e}")

    def applyCanvasContent_(self, timer):
        content = timer.userInfo()
        if self._canvas_text_view and content:
            self._canvas_text_view.setString_(content)
            self._canvas_text_view.setTextColor_(CARD_TEXT)
            if self._canvas_status:
                self._canvas_status.setStringValue_("Loaded from cloud")

    def _canvas_listen(self):
        """WebSocket listener — auto-paste when another device saves canvas."""
        import json, websocket, time, pyperclip
        from app.sync import WS_URL, SUPABASE_KEY
        from app.injector import inject_text

        user_id     = self._app.config.get("sync_user_id", "")
        device_name = self._app.config.get("sync_device_name", "Mac")
        if not user_id:
            logger.warning("Canvas listener: no user_id configured, skipping")
            return

        logger.info(f"Canvas listener starting for user={user_id[:12]}")

        def on_open(ws):
            logger.info("Canvas WebSocket connected — subscribing")
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
                "ref": "canvas_listen",
            }))

        def on_message(ws, raw):
            try:
                msg   = json.loads(raw)
                event = msg.get("event", "")
                if event != "postgres_changes": return
                record = msg.get("payload", {}).get("data", {}).get("record", {})
                if record.get("device_name") == device_name: return  # own save
                content   = record.get("content", "")
                image_url = record.get("image_url")
                # Empty content = clear signal from another device
                logger.info(f"Canvas received from {record.get('device_name')}: {len(content)} chars, image={'yes' if image_url else 'no'}")

                def apply(c=content, img=image_url, dev=record.get("device_name","device")):
                    if self._canvas_text_view:
                        self._canvas_text_view.setString_(c)
                        self._canvas_text_view.setTextColor_(CARD_TEXT if c else CARD_SUB)
                    # Update image URL and rebuild if changed
                    if img != self._canvas_image_url:
                        self._canvas_image_url = img
                        self._rebuild_canvas()
                    if c:
                        import pyperclip
                        pyperclip.copy(c)
                        from app.injector import inject_text
                        inject_text(c)
                    if img and img != self._canvas_image_url:
                        threading.Thread(target=self._copy_image_to_clipboard, args=(img,), daemon=True).start()
                    self._canvas_loaded = True
                    if self._canvas_status:
                        if c and img:
                            msg = f"↓ From {dev} · text pasted + image shown"
                        elif c:
                            msg = f"↓ From {dev} · pasted"
                        elif img:
                            msg = f"↓ Image from {dev}"
                        else:
                            msg = f"↓ Cleared by {dev}"
                        self._canvas_status.setStringValue_(msg)

                self._app._on_main(apply)
            except Exception as e:
                logger.error(f"Canvas listen error: {e}")

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

    def _canvas_save(self):
        """Save canvas content to Supabase on explicit Save click."""
        if not self._canvas_text_view: return
        content = self._canvas_text_view.string() or ""
        if self._canvas_status:
            self._canvas_status.setStringValue_("Saving…")
        threading.Thread(target=self._canvas_push, args=(content,), daemon=True).start()

    def _canvas_push(self, content: str):
        try:
            import httpx, datetime
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            user_id     = self._app.config.get("sync_user_id", "")
            device_name = self._app.config.get("sync_device_name", "Mac")
            if not user_id:
                if self._canvas_status:
                    self._canvas_status.setStringValue_("⚠ Set User ID in Settings first")
                return
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal,resolution=merge-duplicates",
                },
                json={"user_id": user_id, "content": content, "device_name": device_name,
                      "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                timeout=8,
            )
            if resp.status_code in (200, 201):
                import pyperclip
                pyperclip.copy(content)
                self._app._on_main(lambda: self._canvas_status.setStringValue_("✓ Saved & copied · syncing…") if self._canvas_status else None)
            else:
                self._app._on_main(lambda: self._canvas_status.setStringValue_(f"Error {resp.status_code}") if self._canvas_status else None)
        except Exception as e:
            logger.error(f"Canvas save error: {e}")
            self._app._on_main(lambda: self._canvas_status.setStringValue_(f"Save failed: {e}") if self._canvas_status else None)

    def _load_image_into_view(self, url: str, parent_view, w: float, h: float):
        """Download image from URL and display it in the parent view."""
        try:
            import httpx
            from AppKit import NSImageView, NSImage, NSImageScaleProportionallyUpOrDown
            from Foundation import NSData, NSMakeRect

            resp = httpx.get(url, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                logger.error(f"Image load failed: {resp.status_code}")
                return

            data  = NSData.dataWithBytes_length_(resp.content, len(resp.content))
            image = NSImage.alloc().initWithData_(data)
            if not image:
                return

            def show():
                img_view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h - 32))
                img_view.setImage_(image)
                img_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
                img_view.setWantsLayer_(True)
                parent_view.addSubview_(img_view)
                # Also copy to clipboard
                from AppKit import NSPasteboard
                pb = NSPasteboard.generalPasteboard()
                pb.clearContents()
                pb.writeObjects_([image])
                if self._canvas_status:
                    self._canvas_status.setStringValue_("Image loaded · copied to clipboard")

            self._app._on_main(show)
        except Exception as e:
            logger.error(f"Image load error: {e}")

    def _canvas_remove_image(self):
        """Remove image from canvas and sync."""
        self._canvas_image_url = None
        self._rebuild_canvas()
        threading.Thread(target=self._canvas_push_image_removal, daemon=True).start()

    def _canvas_push_image_removal(self):
        try:
            import httpx, datetime
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            user_id     = self._app.config.get("sync_user_id", "")
            device_name = self._app.config.get("sync_device_name", "Mac")
            if not user_id: return
            content = self._canvas_text_view.string() if self._canvas_text_view else ""
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal,resolution=merge-duplicates",
                },
                json={"user_id": user_id, "content": content, "image_url": None,
                      "device_name": device_name,
                      "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                timeout=8,
            )
        except Exception as e:
            logger.error(f"Image removal sync error: {e}")

    def _copy_image_to_clipboard(self, url: str):
        """Download image from URL and copy to Mac clipboard."""
        try:
            import httpx
            from AppKit import NSPasteboard, NSImage, NSPasteboardTypePNG
            from Foundation import NSData

            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code != 200:
                logger.error(f"Image download failed: {resp.status_code}")
                return

            data  = NSData.dataWithBytes_length_(resp.content, len(resp.content))
            image = NSImage.alloc().initWithData_(data)
            if not image:
                logger.error("Could not create NSImage from downloaded data")
                return

            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.writeObjects_([image])
            logger.info(f"Image copied to clipboard from {url}")

            def update_status():
                if self._canvas_status:
                    self._canvas_status.setStringValue_("↓ Image copied to clipboard")
            self._app._on_main(update_status)
        except Exception as e:
            logger.error(f"Image clipboard error: {e}")

    def _canvas_copy(self):
        if self._canvas_text_view:
            import pyperclip
            content = self._canvas_text_view.string() or ""
            if content:
                pyperclip.copy(content)
            # Also try to copy image from clipboard if present
            self._canvas_paste_image_from_clipboard()
            if self._canvas_status:
                self._canvas_status.setStringValue_("Copied to clipboard")

    def _canvas_paste_image_from_clipboard(self):
        """Check if clipboard has an image and upload it to canvas."""
        try:
            from AppKit import NSPasteboard, NSImage, NSBitmapImageRep, NSPNGFileType
            from Foundation import NSData
            pb = NSPasteboard.generalPasteboard()
            img = NSImage.alloc().initWithPasteboard_(pb)
            if not img:
                return
            # Convert to PNG bytes
            rep  = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
            data = rep.representationUsingType_properties_(NSPNGFileType, None)
            if not data:
                return
            png_bytes = bytes(data)
            if self._canvas_status:
                self._canvas_status.setStringValue_("Uploading image…")
            threading.Thread(
                target=self._upload_and_save_image,
                args=(png_bytes,),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Paste image error: {e}")

    def _upload_and_save_image(self, png_bytes: bytes):
        """Upload PNG bytes to Supabase Storage and save URL to canvas."""
        try:
            import httpx, datetime
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            user_id     = self._app.config.get("sync_user_id", "")
            device_name = self._app.config.get("sync_device_name", "Mac")
            if not user_id: return

            filename = f"{user_id}_{int(datetime.datetime.now().timestamp())}.png"
            path     = f"canvas/{filename}"

            # Upload to storage
            upload_resp = httpx.post(
                f"{SUPABASE_URL}/storage/v1/object/canvas-images/{path}",
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "image/png",
                    "x-upsert":      "true",
                },
                content=png_bytes,
                timeout=30,
            )
            if upload_resp.status_code not in (200, 201):
                logger.error(f"Image upload failed: {upload_resp.status_code}")
                return

            public_url = f"{SUPABASE_URL}/storage/v1/object/public/canvas-images/{path}"

            # Save URL to canvas
            content = self._canvas_text_view.string() if self._canvas_text_view else ""
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal,resolution=merge-duplicates",
                },
                json={"user_id": user_id, "content": content or "",
                      "image_url": public_url, "device_name": device_name,
                      "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                timeout=8,
            )
            self._app._on_main(lambda: self._canvas_status.setStringValue_("✓ Image synced") if self._canvas_status else None)
        except Exception as e:
            logger.error(f"Image upload error: {e}")

    def _canvas_clear(self):
        """Clear canvas locally and push empty to Supabase."""
        if self._canvas_text_view:
            self._canvas_text_view.setString_("")
        self._canvas_image_url = None
        if self._canvas_status:
            self._canvas_status.setStringValue_("Clearing…")
        self._canvas_loaded = True
        self._rebuild_canvas()
        threading.Thread(target=self._canvas_push, args=("",), daemon=True).start()

    def _canvas_force_reload(self):
        """Force reload from Supabase regardless of _canvas_loaded flag."""
        self._canvas_loaded = False
        self._canvas_load()

    # ── Device targeting ──────────────────────────────────────────────────────
    def _device_refresh_loop(self):
        """Refresh device list every 30 seconds."""
        while True:
            self._load_devices()
            time.sleep(30)

    def _load_devices(self):
        """Fetch connected devices and update the selector."""
        try:
            from app.sync import fetch_devices
            user_id   = self._app.config.get("sync_user_id", "")
            device_id = self._app._sync.device_id if self._app._sync else ""
            if not user_id: return
            devices = fetch_devices(user_id, device_id)
            self._known_devices = devices
            def update():
                if self._device_sel_view:
                    # Rebuild with new devices list
                    frame = self._device_sel_view.frame()
                    parent = self._device_sel_view.superview()
                    self._device_sel_view.removeFromSuperview()
                    self._device_sel_view = DeviceSelectorView.alloc().initWithFrame_devices_selected_onSelect_(
                        frame, devices, self._target_device_id, self._on_target_device_select
                    )
                    parent.addSubview_(self._device_sel_view)
            self._app._on_main(update)
        except Exception as e:
            logger.error(f"Load devices error: {e}")

    def _on_target_device_select(self, device_id):
        """Called when user taps a device segment."""
        # __all__ = broadcast to all, None = don't send, specific id = targeted
        self._target_device_id = device_id
        if device_id is None:
            logger.info("Target: no sync (None)")
        elif device_id == "__all__":
            logger.info("Target: all devices")
        else:
            dev = next((d for d in self._known_devices if d["device_id"] == device_id), None)
            name = dev["device_name"] if dev else device_id
            logger.info(f"Target device: {name}")

    # ── State ─────────────────────────────────────────────────────────────────
    def update_recording_state(self, is_recording):
        if self._rec_btn: _upd_rec_btn(self._rec_btn, is_recording)
        if self._hero:    self._hero.setRecording_(is_recording)

    def close(self):
        if self._timer:  self._timer.invalidate()
        if self._window: self._window.close(); self._window = None

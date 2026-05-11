import logging
import math

from AppKit import (
    NSPanel, NSView, NSColor, NSFont,
    NSWindowStyleMaskBorderless,
    NSScreen, NSBezierPath, NSTimer, NSRunLoop, NSDefaultRunLoopMode,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSBackingStoreBuffered, NSScreenSaverWindowLevel,
)
from Foundation import NSMakeRect, NSString, NSMakePoint
import objc

logger = logging.getLogger("verbal.overlay")

PILL_W  = 190
PILL_H  = 38
RADIUS  = 19

def _c(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)

def _hex(h, a=1.0):
    h = h.lstrip("#")
    r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    return _c(r, g, b, a)

PILL_BG     = _hex("141412", 0.94)
PILL_BORDER = _c(1, 1, 1, 0.08)
TEXT_COL    = _hex("F0EDE8")
ACCENT      = _hex("E8522A")
BLUE        = _hex("4A90E2")
GREEN       = _hex("4CAF7D")


class PillView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(PillView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._phase     = 0.0
        self._active    = False
        self._amplitude = 0.0
        self._status    = ""
        return self

    def setActive_(self, active):
        self._active = active
        if active:
            self._amplitude = 1.0
        self.setNeedsDisplay_(True)

    def setStatus_(self, text):
        self._status = text
        self.setNeedsDisplay_(True)

    def hideParent_(self, timer):
        if self.window():
            self.window().orderOut_(None)

    def tick_(self, timer):
        if self._active:
            self._phase    += 0.10
            self._amplitude = 0.5 + 0.5 * math.sin(self._phase * 0.75)
        else:
            self._amplitude = max(0.0, self._amplitude - 0.07)
        self.setNeedsDisplay_(True)

    def isFlipped(self):
        return True

    def drawRect_(self, rect):
        w = self.bounds().size.width
        h = self.bounds().size.height

        # Pill background
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), RADIUS, RADIUS
        )
        PILL_BG.set()
        pill.fill()

        # Border
        PILL_BORDER.set()
        pill.setLineWidth_(1.0)
        pill.stroke()

        is_recording  = self._active and "Listen" in self._status
        is_processing = self._active and "Transcrib" in self._status

        # ── Waveform bars (recording only) ────────────────────────────────
        if is_recording and self._amplitude > 0.01:
            bar_count = 10
            bar_w     = 2.5
            gap       = 3.0
            total_w   = bar_count * bar_w + (bar_count - 1) * gap
            sx        = 14.0
            max_bh    = h * 0.52

            for i in range(bar_count):
                frac = 1.0 - abs(i - (bar_count-1)/2.0) / ((bar_count-1)/2.0)
                wave = abs(math.sin(self._phase * 3.0 + i * 0.6))
                bh   = max(2.5, max_bh * (0.3 + 0.7 * frac) * wave * self._amplitude)
                bx   = sx + i * (bar_w + gap)
                by   = (h - bh) / 2
                _hex("E8522A", 0.5 + 0.4 * frac * self._amplitude).set()
                bar = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(bx, by, bar_w, bh), bar_w/2, bar_w/2
                )
                bar.fill()

        # ── Status dot ────────────────────────────────────────────────────
        dot_r = 4.0
        dot_x = w - 14 - dot_r
        dot_y = (h - dot_r * 2) / 2

        if is_recording:
            _hex("E8522A", 0.7 + 0.3 * self._amplitude).set()
        elif is_processing:
            BLUE.set()
        else:
            _hex("4CAF7D", 0.8).set()

        dot = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(dot_x, dot_y, dot_r * 2, dot_r * 2)
        )
        dot.fill()

        # ── Label ─────────────────────────────────────────────────────────
        font  = NSFont.systemFontOfSize_weight_(12, 0.4)
        attrs = {"NSFont": font, "NSColor": TEXT_COL}
        s     = NSString.stringWithString_(self._status)
        sz    = s.sizeWithAttributes_(attrs)

        # Shift right of bars when recording
        if is_recording:
            tx = 14 + 10 * 2.5 + 9 * 3.0 + 8
        else:
            tx = (w - sz.width) / 2

        ty = (h - sz.height) / 2
        s.drawAtPoint_withAttributes_(NSMakePoint(tx, ty), attrs)


class OverlayBar:
    def __init__(self):
        self._window  = None
        self._view    = None
        self._timer   = None
        self._visible = False

    def setup(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        sf = screen.frame()
        x  = (sf.size.width - PILL_W) / 2
        y  = 28

        NSNonactivatingPanelMask = 1 << 7
        self._window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, PILL_W, PILL_H),
            NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(NSScreenSaverWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(True)
        self._window.setIgnoresMouseEvents_(True)
        self._window.setFloatingPanel_(True)
        self._window.setHidesOnDeactivate_(False)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        self._view = PillView.alloc().initWithFrame_(NSMakeRect(0, 0, PILL_W, PILL_H))
        self._window.setContentView_(self._view)

        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 30.0, self._view, "tick:", None, True
        )

    def show(self, status="Listening…"):
        if not self._window:
            self.setup()
        self._view.setActive_(True)
        self._view.setStatus_(status)
        self._window.orderFrontRegardless()
        self._visible = True

    def update_status(self, status):
        if self._view:
            self._view.setStatus_(status)

    def hide(self):
        if self._view:
            self._view.setActive_(False)
        if self._window:
            self._window.orderOut_(None)
        self._visible = False

    def show_briefly(self, status, duration=2.0):
        if not self._window:
            self.setup()
        self._view.setActive_(False)
        self._view.setStatus_(status)
        self._window.orderFrontRegardless()
        self._visible = True
        hide_timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            duration, self._view, "hideParent:", None, False
        )
        NSRunLoop.mainRunLoop().addTimer_forMode_(hide_timer, NSDefaultRunLoopMode)

    @property
    def visible(self):
        return self._visible

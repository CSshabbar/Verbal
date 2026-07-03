import logging
from AppKit import (
    NSWindow, NSView, NSColor, NSFont, NSTextField, NSScrollView,
    NSTextView, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSScreen, NSBackingStoreBuffered, NSBezelBorder,
    NSLayoutAttributeLeading, NSLayoutAttributeTrailing,
    NSLayoutAttributeTop, NSLayoutAttributeBottom,
    NSApplication,
)
from Foundation import NSMakeRect, NSObject, NSMakeSize
import objc

from app import theme as _T
_TC = _T.colors

logger = logging.getLogger("whisperflow.history")


class HistoryWindow:
    def __init__(self):
        self._window = None

    def show(self, config):
        history = config.get("history", [])

        # Stats
        total = len(history)
        total_words = sum(len(h.split()) for h in history)
        total_chars = sum(len(h) for h in history)

        screen = NSScreen.mainScreen()
        sf = screen.frame() if screen else NSMakeRect(0, 0, 1440, 900)
        win_w, win_h = 480, 520
        x = (sf.size.width - win_w) / 2
        y = (sf.size.height - win_h) / 2

        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskResizable | NSWindowStyleMaskMiniaturizable)

        if self._window:
            self._window.close()

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, win_w, win_h), style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("WhisperFlow History")
        self._window.setMinSize_(NSMakeSize(360, 300))

        # Dark background (Flume minimalist-dark)
        self._window.setBackgroundColor_(_TC["bgScreen"])

        content = self._window.contentView()

        # Stats bar at top
        stats_text = f"  {total} transcriptions  |  {total_words} words  |  {total_chars} characters"
        stats = NSTextField.labelWithString_(stats_text)
        stats.setFont_(_T.mono(11, "medium"))
        stats.setTextColor_(_TC["primaryAccent"])
        stats.setBackgroundColor_(_TC["surface1"])
        stats.setDrawsBackground_(True)
        stats.setBezeled_(False)
        stats.setEditable_(False)
        stats.setFrame_(NSMakeRect(0, win_h - 58, win_w, 24))
        content.addSubview_(stats)

        # History list
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(10, 10, win_w - 20, win_h - 78))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(NSBezelBorder)
        scroll.setAutoresizingMask_(0x12 | 0x10)  # flexible width + height

        text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, win_w - 40, win_h - 78))
        text_view.setEditable_(False)
        text_view.setSelectable_(True)
        text_view.setBackgroundColor_(_TC["surface1"])
        text_view.setTextColor_(_TC["textPrimary"])
        text_view.setFont_(_T.geist(13, "regular"))

        # Build history text
        if history:
            lines = []
            for i, h in enumerate(history):
                words = len(h.split())
                lines.append(f"#{i+1}  ({words} words)")
                lines.append(h)
                lines.append("")
            text_view.setString_("\n".join(lines))
        else:
            text_view.setString_("No transcriptions yet.\n\nStart recording to see your history here.")

        scroll.setDocumentView_(text_view)
        content.addSubview_(scroll)

        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def close(self):
        if self._window:
            self._window.close()
            self._window = None

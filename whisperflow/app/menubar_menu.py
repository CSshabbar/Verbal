"""
The Flume menubar menu (macOS) — a real NSMenu with exactly ONE custom-drawn row.

Design decision (IDI-183): the menubar surface is a system menu, not a panel.
Checkmarks, submenus, key-equivalent text, the selection highlight, light/dark,
the user's accent colour, Increase Contrast and Reduce Transparency are all
behaviours AppKit already gets right in every appearance and OS release — a
WKWebView popover has to re-implement each of them and then drift. So every row
here is a stock `NSMenuItem` except the header, which is the one thing AppKit
cannot give us: live status, a mic waveform, the meeting timer and words-today.

This module owns:
  * `_HeaderView`     — the single custom NSView (drawn, not composed).
  * `HeaderMenuItem`  — a rumps-compatible wrapper (it just needs `_menuitem`).
  * `MenuController`  — the NSMenu delegate. Rebuilds the dynamic rows in
                        `menuNeedsUpdate:` and animates the header only between
                        `menuWillOpen:`/`menuDidClose:`.
  * `build(app)`      — assembles the menu list and assigns the item references
                        `main.py`'s existing callbacks already mutate
                        (`record_btn`, `meeting_btn`, `mode_hold`, `model_items`,
                        `autodetect_item`, `signin_item`).

Fail-closed, like every peripheral surface: any failure in here must leave the
menu usable and must never touch record → transcribe → inject. Every delegate
entry point is wrapped.

Gotchas that are easy to reintroduce — see context/05-conventions.md:
  * A menu item's `target` is held WEAKLY. `MenuController` keeps `_keepalive`
    so the objects behind the dynamic rows survive until the next rebuild.
  * While a menu is open AppKit runs `NSEventTrackingRunLoopMode`, so a timer
    scheduled only in the default mode never fires and the waveform freezes.
    `startAnim` adds the timer to BOTH modes.
  * A menu item with a custom view draws its own highlight — this one is
    deliberately passive (`setEnabled_(False)`), so there is nothing to draw.
  * Methods on the ObjC subclasses use camelCase with no inner underscores:
    pyobjc turns `foo_bar` into the selector `foo:bar`.
"""
import logging
import os
import sys
import time

import objc
from AppKit import (
    NSBezierPath, NSColor, NSFont, NSImage, NSMenu, NSMenuItem, NSPasteboard,
    NSPasteboardTypeString, NSView,
)
from Foundation import (
    NSAttributedString, NSDefaultRunLoopMode, NSMakeRect, NSMutableParagraphStyle,
    NSObject, NSRunLoop, NSTimer,
)

logger = logging.getLogger("verbal.menubar")

try:
    from AppKit import NSEventTrackingRunLoopMode
except Exception:  # pragma: no cover — constant has been stable for a decade
    NSEventTrackingRunLoopMode = "NSEventTrackingRunLoopMode"

# Attribute-name constants live in different places across pyobjc versions.
try:
    from AppKit import (
        NSFontAttributeName, NSForegroundColorAttributeName,
        NSParagraphStyleAttributeName,
    )
except Exception:  # pragma: no cover
    NSFontAttributeName = "NSFont"
    NSForegroundColorAttributeName = "NSColor"
    NSParagraphStyleAttributeName = "NSParagraphStyle"

_SOURCE_OVER = 2                 # NSCompositingOperationSourceOver
_ALIGN_RIGHT = 1                 # NSTextAlignmentRight (macOS)
_TRUNCATE_TAIL = 4               # NSLineBreakByTruncatingTail
_WEIGHT_SEMIBOLD = 0.3           # NSFontWeightSemibold

HEADER_W = 284                   # also sets the menu's minimum width
HEADER_H = 46
_MARK = 26                       # brand mark, square
_BARS = 7                        # waveform bars
_FPS = 12.0

# Terracotta. The ONLY place brand colour appears inside the menu: the mark,
# the state dot and the waveform. Everything else is a system colour, which is
# what makes the menu read as native rather than as a themed panel.
_BRAND = NSColor.colorWithSRGBRed_green_blue_alpha_(0.784, 0.353, 0.243, 1.0)
_READY = NSColor.colorWithSRGBRed_green_blue_alpha_(0.22, 0.71, 0.29, 1.0)

_RECENT_MAX = 10                 # transcripts in the Recent submenu
_RECENT_CHARS = 46               # per-row title budget before ellipsis


# ── small helpers ────────────────────────────────────────────────────────────
def _mark_image():
    """The circular Flume mark, or None. Cached on the function."""
    cached = getattr(_mark_image, "_img", "unset")
    if cached != "unset":
        return cached
    img = None
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(os.path.join(sys._MEIPASS, "app", "assets", "img", "flume-mark-128.png"))
    candidates.append(os.path.join(os.path.dirname(__file__), "assets", "img", "flume-mark-128.png"))
    for p in candidates:
        try:
            if os.path.exists(p):
                img = NSImage.alloc().initWithContentsOfFile_(p)
                if img is not None:
                    break
        except Exception:
            img = None
    _mark_image._img = img
    return img


def _attr(text, font, color, align=None):
    d = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
    ps = NSMutableParagraphStyle.alloc().init()
    ps.setLineBreakMode_(_TRUNCATE_TAIL)
    if align is not None:
        ps.setAlignment_(align)
    d[NSParagraphStyleAttributeName] = ps
    return NSAttributedString.alloc().initWithString_attributes_(str(text), d)


def _font(size, semibold=False, mono_digits=False):
    try:
        if mono_digits:
            return NSFont.monospacedDigitSystemFontOfSize_weight_(
                size, _WEIGHT_SEMIBOLD if semibold else 0.0)
        if semibold:
            return NSFont.systemFontOfSize_weight_(size, _WEIGHT_SEMIBOLD)
    except Exception:
        pass
    return NSFont.boldSystemFontOfSize_(size) if semibold else NSFont.systemFontOfSize_(size)


def _mmss(seconds):
    try:
        s = max(0, int(seconds))
    except Exception:
        s = 0
    return "%d:%02d" % (s // 60, s % 60)


def _one_line(text, limit=_RECENT_CHARS):
    s = " ".join(str(text or "").split())
    return (s[: limit - 1] + "…") if len(s) > limit else s


def _copy_to_clipboard(text):
    try:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(str(text or ""), NSPasteboardTypeString)
        return True
    except Exception as e:
        logger.warning("clipboard copy failed: %s", e)
        return False


# ── the one custom row ───────────────────────────────────────────────────────
class _HeaderView(NSView):
    """Mark · status · hotkey/waveform · words-today. Drawn, never composed.

    Reads app state on every draw, so nothing has to push into it — which is
    the whole reason the popover needed a JS bridge and this doesn't.
    """

    def initWithApp_width_(self, app, width):
        self = objc.super(_HeaderView, self).initWithFrame_(
            NSMakeRect(0, 0, width, HEADER_H))
        if self is None:
            return None
        self._app = app
        self._timer = None
        self._levels = [0.0] * _BARS
        return self

    def isOpaque(self):
        return False

    # ── animation, scheduled in BOTH run-loop modes ──────────────────────────
    def startAnim(self):
        if self._timer is not None:
            return
        try:
            t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / _FPS, self, "tick:", None, True)
            rl = NSRunLoop.currentRunLoop()
            # Default mode alone is not enough: menu tracking runs in
            # NSEventTrackingRunLoopMode, so the header would freeze the moment
            # the user opened the very menu it lives in.
            rl.addTimer_forMode_(t, NSDefaultRunLoopMode)
            rl.addTimer_forMode_(t, NSEventTrackingRunLoopMode)
            self._timer = t
        except Exception as e:
            logger.debug("header timer failed (static header): %s", e)

    def stopAnim(self):
        try:
            if self._timer is not None:
                self._timer.invalidate()
        except Exception:
            pass
        self._timer = None

    def tick_(self, _timer):
        try:
            app = self._app
            if getattr(app, "_is_recording", False):
                lvl = float(getattr(app.recorder, "level", 0.0) or 0.0)
                self._levels = (self._levels + [max(0.0, min(1.0, lvl))])[-_BARS:]
            self.setNeedsDisplay_(True)
        except Exception:
            pass

    # ── state → title, subtitle, and which kind of state it is ───────────────
    # Kinds: "ready" | "rec" | "busy" | "meeting" | "note". The kind drives the
    # dot colour and whether the waveform replaces the subtitle — deriving that
    # from the title text instead left the dot green while transcribing.
    def _lines(self):
        app = self._app
        cfg = getattr(app, "config", None) or {}
        recording = bool(getattr(app, "_is_recording", False))
        processing = bool(getattr(app, "_processing", False))

        meeting_active = False
        meeting_src = ""
        try:
            m = getattr(app, "meetings", None)
            meeting_active = bool(m and m.active)
            if meeting_active:
                meeting_src = str(getattr(m, "source_label", "") or "")
        except Exception:
            meeting_active = False

        note = str(getattr(app, "_status_line", "") or "")

        # Signed out beats every other state: nothing else in here is available,
        # so the header's job is to say why and what to do about it.
        try:
            from app import auth
            user = auth.current_user()
            if not user:
                return "Sign in to get started", "Flume needs your account", "signedout"
            if auth.session_dead(cfg):
                return "Session expired", "Sign in again to sync", "note"
        except Exception:
            return "Sign in to get started", "Flume needs your account", "signedout"

        if recording:
            since = getattr(app, "_rec_started_at", 0.0) or 0.0
            elapsed = (time.time() - since) if since else 0.0
            return "Recording", _mmss(elapsed), "rec"
        if processing:
            # "esc", not ⎋ (U+238B): SF Pro has no glyph for it at this size and
            # the fallback rendered as an unrelated symbol.
            return "Transcribing…", "Press esc to cancel", "busy"
        if meeting_active:
            label = " · ".join(x for x in ("Meeting", meeting_src) if x)
            return label, "Recording the call", "meeting"
        if note:
            return note, "", "note"

        hint = str(cfg.get("hotkey_label", "") or "").strip()
        mode = str(cfg.get("recording_mode", "toggle") or "toggle")
        if hint:
            sub = ("Hold %s to dictate" if mode == "hold" else "Tap %s to dictate") % hint
        else:
            sub = "Ready to dictate"
        return "Ready", sub, "ready"

    def _wordsToday(self):
        try:
            from app.config import get_daily_words
            return int(get_daily_words(getattr(self._app, "config", None) or {}) or 0)
        except Exception:
            return 0

    # ── draw ─────────────────────────────────────────────────────────────────
    def drawRect_(self, _dirty):
        try:
            self._draw()
        except Exception as e:  # a header that can't draw must not eat the menu
            logger.debug("header draw failed: %s", e)

    def _draw(self):
        w = self.bounds().size.width
        title, sub, kind = self._lines()
        wave = kind == "rec"

        # brand mark, clipped to a circle
        mx, my = 12.0, (HEADER_H - _MARK) / 2.0
        img = _mark_image()
        rect = NSMakeRect(mx, my, _MARK, _MARK)
        if img is not None:
            NSBezierPath.bezierPathWithOvalInRect_(rect).addClip()
            img.drawInRect_fromRect_operation_fraction_(
                rect, NSMakeRect(0, 0, 0, 0), _SOURCE_OVER, 1.0)
            NSBezierPath.bezierPathWithRect_(self.bounds()).setClip()
        else:
            NSColor.blackColor().setFill()
            NSBezierPath.bezierPathWithOvalInRect_(rect).fill()
            _attr("✳", _font(13, True), _BRAND).drawInRect_(
                NSMakeRect(mx + 7, my + 4, 16, 18))

        # Right-hand number: words today, monospaced digits. The caption is
        # "TODAY" rather than "WORDS TODAY" because the longer label clipped at
        # any column width that still left the title room to breathe. Suppressed
        # when signed out — the stored count is the previous account's, and the
        # copy needs the width.
        if kind == "signedout":
            num_x = w - 12.0
        else:
            num_w = 66.0
            num_x = w - 12.0 - num_w
            _attr(self._wordsToday(), _font(13, True, mono_digits=True),
                  NSColor.labelColor(), _ALIGN_RIGHT).drawInRect_(
                NSMakeRect(num_x, 24, num_w, 15))
            _attr("TODAY", _font(8.5), NSColor.tertiaryLabelColor(),
                  _ALIGN_RIGHT).drawInRect_(NSMakeRect(num_x, 12, num_w, 11))

        # state dot + title
        tx = mx + _MARK + 10.0
        dot = NSMakeRect(tx, 28.5, 6, 6)
        if kind in ("rec", "busy", "meeting"):
            _BRAND.setFill()
        elif kind in ("note", "signedout"):
            NSColor.secondaryLabelColor().setFill()
        else:
            _READY.setFill()
        NSBezierPath.bezierPathWithOvalInRect_(dot).fill()
        tx += 11.0
        avail = max(40.0, num_x - tx - 8.0)
        _attr(title, _font(13, True), NSColor.labelColor()).drawInRect_(
            NSMakeRect(tx, 24, avail, 16))

        # subtitle — waveform + elapsed while recording, plain text otherwise
        sub_y = 10.0
        if wave:
            bw, gap = 2.5, 2.0
            x = tx
            _BRAND.setFill()
            for lvl in self._levels:
                h = 2.0 + (min(1.0, max(0.0, lvl)) ** 0.6) * 11.0
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(x, sub_y + (13 - h) / 2.0, bw, h), 1.25, 1.25).fill()
                x += bw + gap
            x += 5.0
            _attr(sub, _font(11, mono_digits=True), NSColor.secondaryLabelColor()).drawInRect_(
                NSMakeRect(x, sub_y, max(20.0, num_x - x - 8.0), 13))
        elif sub:
            _attr(sub, _font(11), NSColor.secondaryLabelColor()).drawInRect_(
                NSMakeRect(tx, sub_y, avail, 13))


class HeaderMenuItem(object):
    """rumps only requires `_menuitem`, so this drops straight into `App.menu`.

    Deliberately disabled: a view-backed item has to draw its own highlight, and
    a passive header has nothing to highlight.
    """

    def __init__(self, app, width=HEADER_W):
        self.view = _HeaderView.alloc().initWithApp_width_(app, width)
        self._menuitem = NSMenuItem.alloc().init()
        self._menuitem.setEnabled_(False)
        self._menuitem.setView_(self.view)


# ── the delegate ─────────────────────────────────────────────────────────────
class MenuController(NSObject):
    """NSMenu delegate: rebuild on open instead of pushing state in.

    The popover had to keep a WKWebView in sync from six call sites in main.py.
    A menu is only ever read while it is open, so `menuNeedsUpdate:` is the one
    place that has to be correct.
    """

    def initWithApp_(self, app):
        self = objc.super(MenuController, self).init()
        if self is None:
            return None
        self._app = app
        self.header = None
        self._keepalive = []      # menu item targets are held WEAKLY
        return self

    def _signedIn(self):
        """True when a real account is stored. Fails CLOSED — an auth error
        reads as signed out, which locks the menu rather than opening it."""
        try:
            from app import auth
            return bool(auth.current_user())
        except Exception as e:
            logger.warning("auth check failed, treating as signed out: %s", e)
            return False

    # ── attach ───────────────────────────────────────────────────────────────
    def attach(self):
        try:
            nsmenu = self._app.menu._menu
            nsmenu.setDelegate_(self)
            # MUST be off for any manual setEnabled_ to survive. With
            # autoenabling on (the default) AppKit re-derives every item's
            # enabled state at display time from target/action validation — our
            # items all target rumps' NSApp with a live `callback:` action, so it
            # re-ENABLES everything and the sign-in gate silently does nothing.
            nsmenu.setAutoenablesItems_(False)
            return True
        except Exception as e:
            logger.warning("menu delegate not attached (%s); menu still works", e)
            return False

    # ── delegate callbacks ───────────────────────────────────────────────────
    def menuNeedsUpdate_(self, _menu):
        try:
            self.refresh()
        except Exception as e:
            logger.warning("menu refresh failed: %s", e)

    def menuWillOpen_(self, _menu):
        try:
            if self.header is not None:
                self.header.view.startAnim()
        except Exception:
            pass

    def menuDidClose_(self, _menu):
        try:
            if self.header is not None:
                self.header.view.stopAnim()
        except Exception:
            pass

    # ── rebuild ──────────────────────────────────────────────────────────────
    def refresh(self):
        app = self._app
        cfg = getattr(app, "config", None) or {}

        if self.header is not None:
            self.header.view.setNeedsDisplay_(True)

        # Update-available row: deliberately independent of the sign-in gate
        # below — a pending update should stay discoverable even for a
        # signed-out user, and it must not require opening the app to learn
        # about (the whole point of the persistent badge/menu-row pairing).
        try:
            update = getattr(app, "_update_available", None)
            item = getattr(app, "update_item", None)
            if item is not None:
                if update:
                    item.title = "Update available (v%s) ↑" % update.get("version", "")
                    item.hidden = False
                else:
                    item.hidden = True
        except Exception:
            pass

        # Sign-in gate. Flume requires an account, so signed out the menu offers
        # exactly three things: sign in, open the window (which renders the
        # sign-in wall), and the app-level rows — About / Check for Updates /
        # Quit, which are true whether or not anyone is signed in.
        signed_in = self._signedIn()
        for name in ("record_btn", "meeting_btn", "recent_menu", "canvas_menu",
                     "notes_item", "mode_menu", "model_menu", "autodetect_item",
                     "prefs_item"):
            item = getattr(app, name, None)
            try:
                if item is not None:
                    item._menuitem.setEnabled_(bool(signed_in))
            except Exception:
                pass
        if not signed_in:
            # Nothing below needs deriving, and the local history that Recent /
            # Canvas would show belongs to whoever was signed in last.
            for name in ("recent_menu", "canvas_menu"):
                try:
                    getattr(app, name)._menuitem.setSubmenu_(NSMenu.alloc().init())
                except Exception:
                    pass
            try:
                app.canvas_menu.title = "Canvas"
                app.record_btn.title = "Start Recording"
                app.sync_item.state = 0
                app.sync_item._menuitem.setEnabled_(False)
                app._update_auth_menu()
            except Exception:
                pass
            self._keepalive = []
            return

        # titles that carry state
        try:
            app.record_btn.title = "Stop Recording" if app._is_recording else "Start Recording"
        except Exception:
            pass
        for fn in (getattr(app, "_refresh_meeting_menu", None),
                   getattr(app, "sync_menu_state", None),
                   getattr(app, "_update_auth_menu", None)):
            try:
                if fn:
                    fn()
            except Exception:
                pass

        mode = cfg.get("recording_mode", "toggle")
        try:
            app.mode_menu.title = "Recording Mode: %s" % ("Hold" if mode == "hold" else "Toggle")
        except Exception:
            pass
        try:
            app.model_menu.title = "Offline Model: %s" % cfg.get("whisper_model", "base")
        except Exception:
            pass
        try:
            app.autodetect_item.state = 1 if cfg.get("meeting_autodetect", True) else 0
        except Exception:
            pass

        # Sync: a checkmark, not a switch — and off-limits while signed out,
        # because a signed-out app must never open a channel on the old user_id
        # (the same rule _init_sync enforces).
        try:
            from app import auth
            allowed = bool(auth.cloud_allowed(cfg) and cfg.get("sync_user_id", "").strip())
            app.sync_item.state = 1 if (cfg.get("sync_enabled") and allowed) else 0
            app.sync_item._menuitem.setEnabled_(bool(allowed))
            live = bool(getattr(app, "_sync", None) and app._sync.connected)
            app.sync_item.title = ("Sync to My Devices" if live or not cfg.get("sync_enabled")
                                   else "Sync to My Devices (connecting…)")
        except Exception:
            pass

        self._keepalive = []
        self._buildRecent()
        self._buildCanvas()

    def _buildRecent(self):
        app = self._app
        cfg = getattr(app, "config", None) or {}
        try:
            from app.config import _entry_text, _entry_app
        except Exception:
            return
        history = cfg.get("history", []) or []
        sub = NSMenu.alloc().init()
        if not history:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "No transcriptions yet", None, "")
            it.setEnabled_(False)
            sub.addItem_(it)
        for e in history[:_RECENT_MAX]:
            text = _entry_text(e)
            ts = (e.get("ts", "") if isinstance(e, dict) else "") or ""
            src = _entry_app(e) or ""
            head = " · ".join(x for x in (ts[-5:] if len(ts) >= 5 else ts, src) if x)
            title = "%s — %s" % (head, _one_line(text)) if head else _one_line(text)
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "copyItem:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(text)
            sub.addItem_(it)
        sub.addItem_(NSMenuItem.separatorItem())
        it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open History…", "openHistory:", "")
        it.setTarget_(self)
        sub.addItem_(it)
        self._keepalive.append(sub)
        try:
            app.recent_menu._menuitem.setSubmenu_(sub)
        except Exception as e:
            logger.debug("recent submenu not attached: %s", e)

    def _buildCanvas(self):
        app = self._app
        cfg = getattr(app, "config", None) or {}
        try:
            from app.config import _entry_text
        except Exception:
            return
        pinned = cfg.get("pinned", []) or []
        try:
            app.canvas_menu.title = "Canvas (%d)" % len(pinned) if pinned else "Canvas"
        except Exception:
            pass
        sub = NSMenu.alloc().init()
        if not pinned:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Canvas is empty", None, "")
            it.setEnabled_(False)
            sub.addItem_(it)
        for e in pinned[:_RECENT_MAX]:
            text = _entry_text(e)
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                _one_line(text), "copyItem:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(text)
            sub.addItem_(it)
        sub.addItem_(NSMenuItem.separatorItem())
        it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Canvas…", "openCanvas:", "")
        it.setTarget_(self)
        sub.addItem_(it)
        self._keepalive.append(sub)
        try:
            app.canvas_menu._menuitem.setSubmenu_(sub)
        except Exception as e:
            logger.debug("canvas submenu not attached: %s", e)

    # ── actions for the dynamically built rows ────────────────────────────────
    def copyItem_(self, sender):
        try:
            _copy_to_clipboard(sender.representedObject())
        except Exception as e:
            logger.warning("copy from menu failed: %s", e)

    def openHistory_(self, _sender):
        try:
            self._app._open_dashboard()
        except Exception as e:
            logger.warning("open history failed: %s", e)

    def openCanvas_(self, _sender):
        try:
            self._app._open_canvas()
        except Exception as e:
            logger.warning("open canvas failed: %s", e)


# ── assembly ─────────────────────────────────────────────────────────────────
def build(app):
    """Build the menubar menu and return the list for `app.menu = ...`.

    Assigns the item references `main.py`'s callbacks mutate, so those callbacks
    stay exactly as they were. Also returns via `app._menu_ctl` the delegate
    that must be attached AFTER assignment (the NSMenu exists only then).
    """
    import rumps

    ctl = MenuController.alloc().initWithApp_(app)
    ctl.header = HeaderMenuItem(app)
    app._menu_ctl = ctl

    # Persistent "update available" row (hidden until a background check
    # finds one — `MenuController.refresh` toggles `.hidden`/`.title`).
    # Placed right under the header so it's the first thing anyone sees on
    # open, matching the badge on the icon itself.
    app.update_item = rumps.MenuItem("Update available", callback=app._open_update_prompt)
    app.update_item.hidden = True

    app.record_btn = rumps.MenuItem("Start Recording", callback=app._toggle_recording)
    app.meeting_btn = rumps.MenuItem("Start Meeting", callback=app._toggle_meeting)

    # Recent / Canvas are submenu parents; their contents are rebuilt on open.
    app.recent_menu = rumps.MenuItem("Recent")
    app.canvas_menu = rumps.MenuItem("Canvas")
    app.notes_item = rumps.MenuItem("Notes", callback=app._open_notes)

    app.mode_menu = rumps.MenuItem("Recording Mode: Toggle")
    app.mode_hold = rumps.MenuItem("Hold Key to Record", callback=app._set_mode_hold)
    app.mode_toggle = rumps.MenuItem("Toggle On/Off", callback=app._set_mode_toggle)
    app.mode_menu.add(app.mode_hold)
    app.mode_menu.add(app.mode_toggle)

    # "Offline Model", not "Whisper Model". `whisper_model` is read in exactly one
    # place — transcriber._transcribe_local, the THIRD-priority fallback that only
    # runs when the Groq proxy AND Gemini have both failed. Labelled as the model,
    # sitting at the top of the menubar, it read as "the engine that hears you", so
    # switching tiny↔medium looked broken: every dictation was going to Groq and the
    # setting could not possibly change speed. The engine actually in use is
    # `asr_model` (Dashboard → Settings → Models).
    app.model_menu = rumps.MenuItem("Offline Model: base")
    app.model_items = {}
    for name in ("tiny", "base", "small", "medium"):
        # `_change_model` reads `sender.title`, so these titles are load-bearing.
        item = rumps.MenuItem(name, callback=app._change_model)
        app.model_items[name] = item
        app.model_menu.add(item)

    app.autodetect_item = rumps.MenuItem(
        "Auto-detect Meetings", callback=app._toggle_meeting_autodetect)
    app.sync_item = rumps.MenuItem("Sync to My Devices", callback=app._toggle_sync)

    app.signin_item = rumps.MenuItem("Sign in with Google", callback=app._sign_in)

    # Dev-only, unchanged: it wipes auth + onboarding + sync, so it stays behind
    # VERBAL_DEV rather than becoming an ⌥-alternate row that a stray Option
    # key could reveal in a shipped build.
    app.reset_onb_item = (
        rumps.MenuItem("Reset Onboarding (dev)", callback=app._reset_onboarding)
        if getattr(app, "_dev_mode", False) else None)

    # Key equivalents fire only while the menu is open, so they are safe here —
    # the global dictation hotkey stays with HotkeyListener and is advertised in
    # the header subtitle instead of faked as a key equivalent.
    # "Open Flume" stays enabled when signed out — it renders the sign-in wall,
    # so it is part of the way back in. Settings… is gated with the rest.
    open_item = rumps.MenuItem("Open Flume", callback=app._open_dashboard)
    app.prefs_item = rumps.MenuItem("Settings…", callback=app._open_settings)
    prefs_item = app.prefs_item
    try:
        open_item.set_callback(app._open_dashboard, "o")
        prefs_item.set_callback(app._open_settings, ",")
    except Exception:
        pass

    items = [
        ctl.header,
        app.update_item,
        None,
        app.record_btn,
        app.meeting_btn,
        None,
        app.recent_menu,
        app.canvas_menu,
        app.notes_item,
        None,
        app.mode_menu,
        app.model_menu,
        app.autodetect_item,
        app.sync_item,
        None,
        open_item,
        prefs_item,
        app.signin_item,
    ] + ([app.reset_onb_item] if app.reset_onb_item else []) + [
        None,
        rumps.MenuItem("Check for Updates…", callback=app._check_update_now),
        rumps.MenuItem("About Flume", callback=app._about),
    ]
    return items

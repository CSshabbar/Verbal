import logging
import time
import objc
from Foundation import NSObject
from AppKit import NSEvent
import Quartz

logger = logging.getLogger("verbal.hotkey")

VK_RIGHT_COMMAND = 0x36
VK_ESCAPE = 0x35

# Tap-to-latch (HOLD mode): a press SHORTER than this is a tap, and a tap leaves
# the recording running hands-free until the next tap. Anything longer is an
# ordinary push-to-talk hold that stops on release. 0.4s is comfortably above a
# deliberate tap and below the shortest press anyone makes when they mean to
# hold and speak.
TAP_LATCH_MAX_SECONDS = 0.4


class HotkeyListener:
    def __init__(self, on_start, on_stop, on_toggle, on_esc=None, hold_key=54, toggle_key=54,
                 mode="toggle", on_transform=None, transform_key=None,
                 tap_latch_seconds=TAP_LATCH_MAX_SECONDS):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_toggle = on_toggle
        self._on_esc = on_esc
        self._hold_key = hold_key
        self._toggle_key = toggle_key
        self._mode = mode  # 'toggle' = tap to start/stop; 'hold' = press-and-hold
        self._monitors = []
        self._pressed = False
        self._last_event_time = 0.0
        # Tap-to-latch state (HOLD mode only). `_latched` means "recording is
        # running with the key released"; the next press stops it. `_press_time`
        # dates the current press so release can tell a tap from a hold, and
        # `_chorded` records that another key was struck while the hotkey was
        # down — that makes it a shortcut (Right ⌘ + C), never a dictation tap.
        self._tap_latch_seconds = tap_latch_seconds
        self._latched = False
        self._press_time = 0.0
        self._chorded = False
        # Transform (Mode B): Cmd+Shift+<transform_key> keydown → on_transform.
        # Kept OUT of the dictation key handling below (Rule #1).
        self._on_transform = on_transform
        self._transform_key = transform_key
        self._last_transform_time = 0.0

    def set_transform(self, on_transform, transform_key):
        self._on_transform = on_transform
        self._transform_key = transform_key

    def update_keys(self, hold_key, toggle_key):
        self._hold_key = hold_key
        self._toggle_key = toggle_key
        logger.info(f"Hotkey keys updated: hold={hold_key}, toggle={toggle_key}")

    def set_mode(self, mode):
        self._mode = mode
        self._pressed = False
        self.clear_latch()
        logger.info(f"Hotkey mode set to: {mode}")

    def clear_latch(self):
        """Forget a hands-free (tapped) recording. Call whenever the recording
        ends by any route other than the second tap — ESC, an error, the max
        duration — so the key state can't drift out of sync with the app."""
        self._latched = False
        self._pressed = False

    def start(self):
        mask = (Quartz.NSEventMaskFlagsChanged | 
                Quartz.NSEventMaskKeyDown | 
                Quartz.NSEventMaskKeyUp)

        monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_event
        )
        if monitor:
            self._monitors.append(monitor)

        local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_local_event
        )
        if local_monitor:
            self._monitors.append(local_monitor)

        logger.info(f"Hotkey listener started (Hold={self._hold_key}, Toggle={self._toggle_key})")

    def stop(self):
        for monitor in self._monitors:
            NSEvent.removeMonitor_(monitor)
        self._monitors = []

    def _handle_local_event(self, event):
        self._handle_event(event)
        return event

    def _is_modifier(self, keycode):
        # Common macOS modifier keycodes: Cmd, Shift, Caps, Opt, Ctrl (Left/Right)
        return keycode in (54, 55, 56, 57, 58, 59, 60, 61, 62, 63)

    def _get_mod_mask(self, keycode):
        if keycode in (54, 55): return Quartz.NSEventModifierFlagCommand
        if keycode in (56, 60): return Quartz.NSEventModifierFlagShift
        if keycode in (58, 61): return Quartz.NSEventModifierFlagOption
        if keycode in (59, 62): return Quartz.NSEventModifierFlagControl
        if keycode == 57:       return Quartz.NSEventModifierFlagCapsLock
        return 0

    def _handle_event(self, event):
        try:
            now = time.time()
            event_type = event.type()
            keycode = event.keyCode()

            # Debounce/Ignore ESC
            if keycode == VK_ESCAPE:
                if event_type == 10: # KeyDown
                    # ESC cancels the recording, so a latched one is no longer
                    # running — drop the latch or the next tap would be spent
                    # "stopping" nothing instead of starting a new dictation.
                    self.clear_latch()
                    if self._on_esc: self._on_esc()
                return

            # Determine if this is a "Down" or "Up" transition
            is_down = False
            is_up = False
            
            if event_type == 10: # KeyDown
                is_down = True
            elif event_type == 11: # KeyUp
                is_up = True
            elif event_type == 12: # FlagsChanged
                flags = event.modifierFlags()
                mask = self._get_mod_mask(keycode)
                if mask:
                    is_down = bool(flags & mask)
                    is_up = not is_down
                else:
                    # Fallback for unknown modifiers
                    is_down = bool(flags & 0xFFFF0000) # Check all device-independent flags
                    is_up = not is_down

            # Transform selection — Cmd+Shift+<key> on keydown, debounced.
            # Checked BEFORE the dictation keys and returns without touching them.
            if (self._on_transform and self._transform_key is not None
                    and event_type == 10 and keycode == self._transform_key):
                flags = event.modifierFlags()
                if (flags & Quartz.NSEventModifierFlagCommand
                        and flags & Quartz.NSEventModifierFlagShift
                        and now - self._last_transform_time > 0.5):
                    self._last_transform_time = now
                    logger.info(f"Transform hotkey fired: {keycode}")
                    self._on_transform()
                    return

            # Any OTHER key struck while the hotkey is held makes this a chord
            # (Right ⌘ + C), not dictation — remember it so release can't latch.
            if (event_type == 10 and self._pressed and keycode != self._hold_key
                    and keycode != VK_ESCAPE):
                self._chorded = True

            # Hold-to-talk WITH tap-to-latch — only in HOLD mode.
            #   press           → start recording
            #   release > 0.4s  → push-to-talk: stop (the classic behaviour)
            #   release < 0.4s  → it was a TAP: keep recording hands-free
            #   press again     → stop the latched recording
            # A tap used to start a recording and end it in the same third of a
            # second, which _on_record_stop then discarded as too short: the
            # "I have to be so quick about it or it stops" complaint.
            if self._mode == "hold" and keycode == self._hold_key:
                if is_down and self._latched:
                    # Second tap — end the hands-free recording.
                    self._latched = False
                    self._pressed = False
                    logger.info("Tap-latch: stopping (second tap)")
                    self._on_stop()
                elif is_down and not self._pressed:
                    self._pressed = True
                    self._chorded = False
                    self._press_time = now
                    logger.debug(f"Hold key DOWN: {keycode}")
                    self._on_start()
                elif is_up and self._pressed:
                    self._pressed = False
                    held = now - self._press_time
                    if held <= self._tap_latch_seconds and not self._chorded:
                        self._latched = True
                        logger.info("Tap-latch: recording stays on (%.2fs tap)", held)
                    else:
                        logger.debug(f"Hold key UP: {keycode} ({held:.2f}s)")
                        self._on_stop()
                return

            # Tap-to-toggle — only in TOGGLE mode (tap to start, tap again to stop)
            if self._mode != "hold" and keycode == self._toggle_key:
                if is_down and now - self._last_event_time > 0.3:
                    self._last_event_time = now
                    logger.debug(f"Toggle key triggered: {keycode}")
                    self._on_toggle()
                return

        except Exception as e:
            logger.error(f"Hotkey event error: {e}")

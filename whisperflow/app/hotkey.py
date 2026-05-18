import logging
import time
import objc
from Foundation import NSObject
from AppKit import NSEvent
import Quartz

logger = logging.getLogger("verbal.hotkey")

VK_RIGHT_COMMAND = 0x36
VK_ESCAPE = 0x35


class HotkeyListener:
    def __init__(self, on_start, on_stop, on_toggle, on_esc=None, hold_key=54, toggle_key=54):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_toggle = on_toggle
        self._on_esc = on_esc
        self._hold_key = hold_key
        self._toggle_key = toggle_key
        self._monitors = []
        self._pressed = False
        self._last_event_time = 0.0

    def update_keys(self, hold_key, toggle_key):
        self._hold_key = hold_key
        self._toggle_key = toggle_key
        logger.info(f"Hotkey keys updated: hold={hold_key}, toggle={toggle_key}")

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

            # Handle Hold Key
            if keycode == self._hold_key:
                if is_down and not self._pressed:
                    self._pressed = True
                    logger.debug(f"Hold key DOWN: {keycode}")
                    self._on_start()
                elif is_up and self._pressed:
                    self._pressed = False
                    logger.debug(f"Hold key UP: {keycode}")
                    self._on_stop()
                
                # If Hold and Toggle are the same, don't also fire toggle logic
                if self._hold_key == self._toggle_key:
                    return

            # Handle Toggle Key
            if keycode == self._toggle_key:
                if is_down:
                    if now - self._last_event_time > 0.3:
                        self._last_event_time = now
                        logger.debug(f"Toggle key triggered: {keycode}")
                        self._on_toggle()

        except Exception as e:
            logger.error(f"Hotkey event error: {e}")

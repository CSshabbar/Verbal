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
    def __init__(self, on_start, on_stop, on_esc=None):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_esc = on_esc
        self._monitors = []
        self._pressed = False
        self._last_event_time = 0.0

    def start(self):
        mask = Quartz.NSEventMaskFlagsChanged | Quartz.NSEventMaskKeyDown

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

        logger.info("Hotkey listener started (Right Cmd + ESC)")

    def stop(self):
        for monitor in self._monitors:
            NSEvent.removeMonitor_(monitor)
        self._monitors = []

    def _handle_local_event(self, event):
        self._handle_event(event)
        return event

    def _handle_event(self, event):
        try:
            now = time.time()
            event_type = event.type()

            # Modifier key changes (Right Command)
            if event_type == 12:  # NSEventTypeFlagsChanged
                keycode = event.keyCode()
                flags = event.modifierFlags()
                if keycode == VK_RIGHT_COMMAND:
                    cmd_down = bool(flags & Quartz.NSEventModifierFlagCommand)

                    # Debounce: ignore events within 200ms of each other
                    if now - self._last_event_time < 0.2:
                        logger.debug(f"Debounced Right Cmd event (cmd_down={cmd_down})")
                        return
                    self._last_event_time = now

                    if cmd_down and not self._pressed:
                        self._pressed = True
                        logger.info(f"RIGHT CMD DOWN at {now:.3f}")
                        self._on_start()
                    elif not cmd_down and self._pressed:
                        self._pressed = False
                        logger.info(f"RIGHT CMD UP at {now:.3f}")
                        self._on_stop()

            # ESC key
            elif event_type == 10:  # NSEventTypeKeyDown
                keycode = event.keyCode()
                if keycode == VK_ESCAPE and self._on_esc:
                    self._on_esc()

        except Exception as e:
            logger.error(f"Hotkey event error: {e}")

"""Windows hotkey listener — pynput-backed wrapper mirroring the macOS
`app/hotkey.py::HotkeyListener` interface so `shared_dashboard` can bind
Transform / dictation hotkeys without branching on OS.

Public methods callers rely on (all also present on the Mac class):
    start(), stop(),
    update_keys(hold_key, toggle_key),
    set_mode(mode),
    set_transform(on_transform, transform_key).

`hold_key` / `toggle_key` are pynput key strings (e.g. "alt_r", "space")
persisted in config; `transform_key` is a single-character key literal
(e.g. "t") — the actual chord is Ctrl+Shift+<key>.

Fail-closed: any callback exception is swallowed with a debug log; the
listener keeps running.
"""

import logging
import time

logger = logging.getLogger("verbal.hotkey.win")

MODE_HOLD = "hold"
MODE_TOGGLE = "toggle"

# Tap-to-latch (HOLD mode): a press SHORTER than this is a tap, and a tap
# leaves the recording running hands-free until the next tap. Anything longer
# is an ordinary push-to-talk hold that stops on release. Mirrors
# app/hotkey.py::TAP_LATCH_MAX_SECONDS — keep the two in step.
TAP_LATCH_MAX_SECONDS = 0.4


class WinHotkeyListener:
    def __init__(self, on_start, on_stop, on_toggle, on_esc=None,
                 hold_key="alt_r", toggle_key="alt_r", mode=MODE_TOGGLE,
                 on_transform=None, transform_key=None):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_toggle = on_toggle
        self._on_esc = on_esc
        self._mode = mode
        self._hold_key_name = hold_key
        self._toggle_key_name = toggle_key
        self._parsed_hold_key = None
        self._parsed_toggle_key = None
        # Transform (Ctrl+Shift+<key>) — kept OUT of the dictation path.
        self._on_transform = on_transform
        self._transform_key_char = self._normalize_transform_key(transform_key)
        self._ctrl_down = False
        self._shift_down = False
        self._last_transform_time = 0.0
        # True while the transform trigger key is physically held. Windows
        # key-repeat delivers a stream of key-DOWN events for a held key;
        # without this latch the chord fires every debounce window (~2x/s),
        # spawning overlapping clipboard captures that clobber each other.
        self._transform_key_held = False
        # Dictation debounce.
        self._is_recording = False
        self._pressed = False
        self._last_toggle_time = 0.0
        # Tap-to-latch state (HOLD mode only) — see TAP_LATCH_MAX_SECONDS.
        # `_latched` = recording runs with the key released; the next press
        # stops it. `_press_time` dates the press so release can tell a tap
        # from a hold. `_chorded` marks that another key was struck while the
        # hotkey was down, which makes it a shortcut, never a dictation tap.
        self._tap_latch_seconds = TAP_LATCH_MAX_SECONDS
        self._latched = False
        self._press_time = 0.0
        self._chorded = False
        # pynput.
        self._listener = None

    # ── public API ──────────────────────────────────────────────────────
    def start(self):
        from pynput import keyboard
        self._parsed_hold_key = self._parse_key(self._hold_key_name)
        self._parsed_toggle_key = self._parse_key(self._toggle_key_name)
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()
        logger.info("Hotkey listener started (Hold=%s, Toggle=%s, mode=%s, "
                    "transform_char=%r)",
                    self._hold_key_name, self._toggle_key_name, self._mode,
                    self._transform_key_char)

    def stop(self):
        try:
            if self._listener is not None:
                self._listener.stop()
        except Exception:
            pass
        self._listener = None

    def update_keys(self, hold_key, toggle_key):
        """Rebind dictation hold/toggle keys. `hold_key`/`toggle_key` are
        pynput key strings (matching the macOS API's key-code contract
        this wrapper adapts)."""
        self._hold_key_name = hold_key
        self._toggle_key_name = toggle_key
        # Cheapest way to rebind pynput is to restart the listener.
        self.stop()
        self.start()

    def set_mode(self, mode):
        self._mode = mode
        self._pressed = False
        self.clear_latch()
        logger.info("Hotkey mode set to %s", mode)

    def clear_latch(self):
        """Forget a hands-free (tapped) recording. Call whenever the recording
        ends by any route other than the second tap — ESC, an error, the max
        duration — so the key state can't drift out of sync with the app.
        Mirrors app/hotkey.py::clear_latch."""
        self._latched = False
        self._pressed = False

    def set_transform(self, on_transform, transform_key):
        """Bind (or unbind) the Transform hotkey. `transform_key` is a
        single-character literal — actual chord is Ctrl+Shift+<key>."""
        self._on_transform = on_transform
        self._transform_key_char = self._normalize_transform_key(transform_key)
        logger.info("Transform hotkey rebound: char=%r",
                    self._transform_key_char)

    def notify_recording_state(self, is_recording):
        """Optional hook so the listener can suppress Transform while
        actively recording (matches macOS behavior)."""
        self._is_recording = bool(is_recording)

    # ── internals ───────────────────────────────────────────────────────
    def _parse_key(self, key_name):
        from pynput import keyboard
        if not key_name:
            return None
        try:
            stripped = str(key_name).replace("Key.", "")
            if hasattr(keyboard.Key, stripped):
                return getattr(keyboard.Key, stripped)
            return keyboard.KeyCode.from_char(key_name)
        except Exception:
            return None

    @staticmethod
    def _normalize_transform_key(key):
        """Accept a pynput.KeyCode, a single char, or a raw string. Return
        the lowercase character we compare against on press, or None."""
        if key is None:
            return None
        try:
            char = getattr(key, "char", None)
            if char:
                return str(char).lower()[:1]
            if isinstance(key, str):
                return key.lower()[:1] if key else None
        except Exception:
            pass
        return None

    def _keys_match(self, pressed_key, target_key):
        """pynput treats Right Alt as either alt_r or alt_gr depending on
        the layout — collapse the pair."""
        if pressed_key == target_key:
            return True
        try:
            from pynput import keyboard
            alt_keys = {keyboard.Key.alt_r, keyboard.Key.alt_gr}
            if pressed_key in alt_keys and target_key in alt_keys:
                return True
        except Exception:
            pass
        return False

    def _is_ctrl(self, key):
        from pynput.keyboard import Key
        return key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r)

    def _is_shift(self, key):
        from pynput.keyboard import Key
        return key in (Key.shift, Key.shift_l, Key.shift_r)

    def _key_to_char(self, key):
        """Normalize a pynput key event to a lowercase letter, or None.
        Handles the three shapes Windows delivers under Ctrl(+Shift):
        plain char, control glyph (\\x01..\\x1a), or vk-only KeyCode."""
        char = getattr(key, "char", None)
        if char:
            try:
                c = char.lower()
                if len(c) == 1 and "\x01" <= c <= "\x1a":
                    c = chr(ord(c) + 96)
                return c
            except Exception:
                pass
        vk = getattr(key, "vk", None)
        if isinstance(vk, int) and 0x41 <= vk <= 0x5A:
            return chr(vk + 0x20)
        return None

    def _maybe_fire_transform(self, key):
        """Return True if the key press matched the Transform chord and
        fired (or swallowed) the event. Fires ONCE per physical press:
        key-repeat DOWN events while the trigger key is held are swallowed
        without re-firing (the latch clears on key release)."""
        if not (self._on_transform and self._transform_key_char):
            return False
        if not (self._ctrl_down and self._shift_down):
            return False
        candidate = self._key_to_char(key)
        if candidate != self._transform_key_char:
            return False
        if self._transform_key_held:
            return True                    # key-repeat — swallow, don't refire
        self._transform_key_held = True
        now = time.time()
        if now - self._last_transform_time < 0.4:
            return True
        self._last_transform_time = now
        try:
            logger.info("Transform hotkey fired: char=%r", self._transform_key_char)
            self._on_transform()
        except Exception as e:
            logger.error("Transform callback failed: %s", e, exc_info=True)
        return True

    def _on_press(self, key):
        try:
            # Any OTHER key struck while the hotkey is held makes this a chord
            # (Alt+Tab, Ctrl+Alt+…), not dictation — remember it so the release
            # can't latch a hands-free recording.
            if self._pressed and not self._keys_match(key, self._parsed_hold_key):
                self._chorded = True
            # Track modifier state BEFORE checking the chord.
            if self._is_ctrl(key):
                self._ctrl_down = True
                return
            if self._is_shift(key):
                self._shift_down = True
                return

            # Escape → cancel-recording hook (matches Mac).
            try:
                from pynput.keyboard import Key
                if key == Key.esc and self._on_esc:
                    self.clear_latch()
                    self._on_esc()
                    return
            except Exception:
                pass

            # Transform chord — checked BEFORE dictation keys and returns
            # without touching them (matches Mac's discipline).
            if self._maybe_fire_transform(key):
                return

            hold_key = self._parsed_hold_key
            toggle_key = self._parsed_toggle_key

            # Same key for both — mode-aware.
            if hold_key == toggle_key and self._keys_match(key, hold_key):
                if self._mode == MODE_HOLD:
                    if self._latched:
                        # Second tap — end the hands-free recording.
                        self._latched = False
                        self._pressed = False
                        logger.info("Tap-latch: stopping (second tap)")
                        try: self._on_stop()
                        except Exception as e:
                            logger.error("latch on_stop failed: %s", e, exc_info=True)
                    elif not self._pressed:
                        self._pressed = True
                        self._chorded = False
                        self._press_time = time.time()
                        try: self._on_start()
                        except Exception as e:
                            logger.error("hold on_start failed: %s", e, exc_info=True)
                else:
                    now = time.time()
                    if now - self._last_toggle_time > 0.3:
                        self._last_toggle_time = now
                        try: self._on_toggle()
                        except Exception as e:
                            logger.error("toggle callback failed: %s", e, exc_info=True)
                return

            # Different keys — handle both.
            if self._keys_match(key, hold_key):
                if not self._pressed:
                    self._pressed = True
                    try: self._on_start()
                    except Exception as e:
                        logger.error("split-hold on_start failed: %s", e, exc_info=True)
            if self._keys_match(key, toggle_key):
                now = time.time()
                if now - self._last_toggle_time > 0.3:
                    self._last_toggle_time = now
                    try: self._on_toggle()
                    except Exception as e:
                        logger.error("split-toggle callback failed: %s", e, exc_info=True)
        except Exception as e:
            logger.error("Key press error: %s", e, exc_info=True)

    def _on_release(self, key):
        try:
            if self._is_ctrl(key):
                self._ctrl_down = False
                return
            if self._is_shift(key):
                self._shift_down = False
                return
            # Physical release of the transform trigger key re-arms the
            # once-per-press latch.
            if (self._transform_key_held
                    and self._key_to_char(key) == self._transform_key_char):
                self._transform_key_held = False
            if self._keys_match(key, self._parsed_hold_key):
                if self._parsed_hold_key == self._parsed_toggle_key:
                    if self._mode == MODE_HOLD and self._pressed:
                        self._pressed = False
                        held = time.time() - self._press_time
                        if held <= self._tap_latch_seconds and not self._chorded:
                            self._latched = True
                            logger.info("Tap-latch: recording stays on (%.2fs tap)", held)
                        else:
                            try: self._on_stop()
                            except Exception as e:
                                logger.error("hold on_stop failed: %s", e, exc_info=True)
                else:
                    if self._pressed:
                        self._pressed = False
                        try: self._on_stop()
                        except Exception as e:
                            logger.error("split-hold on_stop failed: %s", e, exc_info=True)
        except Exception:
            pass

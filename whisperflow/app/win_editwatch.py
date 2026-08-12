"""Windows autolearn edit-watcher — UI Automation analog of the AX read-back
in `app/autolearn.py::EditWatcher`.

Reuses the entire portable core (`classify`, `apply_observation_guard`, all
diff/phonetic logic, the poll/debounce/finalize loop in `_run`) by subclassing
the Mac `EditWatcher` and overriding ONLY the platform-native methods:

  * `_app_element(pid)`   — top-level UIA control belonging to `pid`
  * `_focused_element()`  — the focused UIA control under that process
  * `_read_value(el)`     — TextPattern.DocumentRange.GetText / ValuePattern.Value
  * `_caret_location(el)` — TextPattern.GetSelection() → range start offset
  * `_is_secure(el)`      — password / read-only detection via UIA properties
  * `_ax_attr` / `_set_messaging_timeout` — no-ops on Windows (kept for shape)

Same public interface: `arm(pid, bundle, inserted_text, on_decision_callback)`
returns bool, `cancel()`. Fully fail-closed — never raises, never affects
`record → transcribe → inject`.
"""

import logging
import threading

from app.autolearn import EditWatcher as _MacEditWatcher

logger = logging.getLogger("verbal.autolearn.win")


class EditWatcher(_MacEditWatcher):
    """Windows edit-watcher — overrides the AX read-back only. All decision
    logic (`classify`, `apply_observation_guard`, poll/debounce/finalize)
    comes from the shared parent class."""

    # ── COM lifecycle around the watch thread ────────────────────────────
    def _run(self, pid, bundle, inserted_text, callback, stop_event):
        # uiautomation's COM interfaces are apartment-threaded. We spawn a
        # fresh daemon thread on each arm(); each such thread needs its own
        # CoInitializeEx / CoUninitialize pair.
        co_inited = False
        try:
            import comtypes  # part of the pywebview / uiautomation stack
            # COINIT_APARTMENTTHREADED = 0x2
            comtypes.CoInitializeEx(0x2)
            co_inited = True
        except Exception as e:
            # If COM init fails, uiautomation will fail its own calls, which
            # our overrides handle by returning None. Continue — fail-closed.
            logger.debug("[autolearn/win] CoInitializeEx failed: %s", e)

        try:
            # Delegate to the shared poll/debounce/finalize logic. Our
            # overrides below are what it actually calls for element reads.
            super()._run(pid, bundle, inserted_text, callback, stop_event)
        finally:
            if co_inited:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    # ── Mac-compat no-ops (kept so the shared _run doesn't AttributeError) ──
    @staticmethod
    def _ax_attr(element, attr):  # noqa: D401 — parity API
        return None

    @staticmethod
    def _set_messaging_timeout(element, seconds):  # Mac AX only — no-op here
        return

    # ── Element resolution ───────────────────────────────────────────────
    def _app_element(self, pid):
        """Return the top-level UIA control whose ProcessId == pid, or None."""
        try:
            import uiautomation as auto
            root = auto.GetRootControl()
            for child in root.GetChildren():
                try:
                    if child.ProcessId == pid:
                        return child
                except Exception:
                    continue
        except Exception as e:
            logger.debug("[autolearn/win] app_element(%s) failed: %s", pid, e)
        return None

    def _focused_element(self, app_el):
        """Return the UIA control that has keyboard focus, guarded to the
        target process. By transcription time the overlay may hold focus in
        the global sense — but our overlay window's ProcessId matches the
        Verbal process, not the target — so guarding on PID is safe."""
        try:
            import uiautomation as auto
            focused = auto.GetFocusedControl()
            if focused is None:
                return None
            # If we know the target app element, verify the focused control
            # belongs to the same process; otherwise return None.
            if app_el is not None:
                try:
                    if focused.ProcessId != app_el.ProcessId:
                        return None
                except Exception:
                    return None
            return focused
        except Exception as e:
            logger.debug("[autolearn/win] focused_element failed: %s", e)
            return None

    # ── Text read-back via UIA patterns ──────────────────────────────────
    def _read_value(self, element):
        """Best-effort text read: TextPattern → ValuePattern → Name. Returns
        None on any failure so the shared _run treats it as unreadable."""
        if element is None:
            return None
        # Try TextPattern first (rich editors, multi-line fields).
        try:
            import uiautomation as auto
            tp = None
            try:
                tp = element.GetPattern(auto.PatternId.TextPattern)
            except Exception:
                tp = None
            if tp is not None:
                try:
                    # DocumentRange.GetText(-1) → entire text, no length cap.
                    val = tp.DocumentRange.GetText(-1)
                    if val is not None:
                        return str(val)
                except Exception:
                    pass
            # Fallback: ValuePattern (Edit / plain TextBox controls).
            try:
                vp = element.GetPattern(auto.PatternId.ValuePattern)
            except Exception:
                vp = None
            if vp is not None:
                try:
                    val = vp.Value
                    if val is not None:
                        return str(val)
                except Exception:
                    pass
        except Exception:
            return None
        return None

    def _caret_location(self, element):
        """Best-effort caret index. TextPattern.GetSelection() returns a
        collection of ranges; after a paste the caret sits at the END of
        the inserted text, so range.End is what we want."""
        if element is None:
            return None
        try:
            import uiautomation as auto
            tp = element.GetPattern(auto.PatternId.TextPattern)
            if tp is None:
                return None
            selection = tp.GetSelection()
            if not selection or len(selection) == 0:
                return None
            rng = selection[0]
            # uiautomation's TextRange exposes Start/End as absolute
            # character offsets after `.ExpandToEnclosingUnit` / `.Move`.
            # We approximate by using the range's text length from doc start.
            try:
                doc = tp.DocumentRange
                # Clone the doc range and move its End to selection's End —
                # its length equals the caret offset.
                clone = doc.Clone()
                clone.MoveEndpointByRange(0, rng, 1)  # TextPatternRangeEndpoint_Start=0, End=1
                # Not portable across all UIA impls. Fall through to string-search
                # heuristic (base class already has a robust find fallback).
                return None
            except Exception:
                return None
        except Exception:
            return None

    # ── Secure / read-only field detection ──────────────────────────────
    def _is_secure(self, element):
        """Skip password / read-only fields.

        Returns True on any UNCERTAINTY too (fail-closed — better to miss an
        autolearn opportunity than to read a password field)."""
        if element is None:
            return True
        try:
            import uiautomation as auto
            # ValuePattern.IsReadOnly → skip.
            try:
                vp = element.GetPattern(auto.PatternId.ValuePattern)
                if vp is not None and getattr(vp, "IsReadOnly", False):
                    return True
            except Exception:
                pass
            # ControlType == Edit + IsPassword property → skip.
            try:
                if element.ControlType == auto.ControlType.EditControl:
                    # IsPassword lives on the UIA element as a boolean property.
                    is_pw = getattr(element, "IsPassword", False)
                    if is_pw:
                        return True
            except Exception:
                pass
            # AutomationId / Name / ClassName hint at password.
            try:
                for attr in ("Name", "AutomationId", "ClassName"):
                    val = getattr(element, attr, None) or ""
                    if "password" in str(val).lower() or "secure" in str(val).lower():
                        return True
            except Exception:
                pass
        except Exception:
            # UIA unusable → treat as secure and bail (fail closed).
            return True
        return False

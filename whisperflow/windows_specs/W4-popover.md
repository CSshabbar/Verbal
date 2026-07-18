# W4 — Popover (tray left-click → compact pywebview window)

**Goal:** Windows has no menubar, so there is no NSPopover equivalent. Make the **tray icon
left-click** open a small pywebview window that renders `app/flume_popover_html.py::popover_html()` —
the same compact Flume popover the Mac shows from the menubar. Right-click keeps the existing pystray
menu.

## Files

- **Create:** `app/win_popover.py` — `WinPopover` window wrapper hosting `popover_html()`.
- **Modify:** `app/win_main.py` — give the tray icon a **left-click default action** that opens the
  popover (pystray: set a `default=True` `MenuItem`, or a `MenuItem` marked default whose callback
  opens the popover).
- **Reuse (do not edit):** `app/flume_popover_html.py`, `app/fonts_css.py`, `app/shared_dashboard.py`
  (`DashboardApi`).
- **Reference (Mac):** `app/flume_popover.py` (the NSPopover host) for the bridge method set.

## Wiring the tray left-click

In `win_main.py`, pystray shows the menu on left-click by default. To make left-click open the
popover, add a default menu item:

```python
pystray.MenuItem("Open Flume", self._tray_open_popover, default=True)
```

with `_tray_open_popover(self, icon=None, item=None): self.popover.show()`. Instantiate
`self.popover = WinPopover(self)` in `VerbalWinApp.__init__` alongside `self.overlay` / `self.dashboard`.
Keep the full right-click menu intact. (If `default=True` interferes with the existing menu on the
target pystray backend, fall back to opening the popover from an explicit "Open Flume" item and
document it.)

## Bridge — methods `popover_html()` calls

`popover_html()`'s JS calls `window.pywebview.api.<method>(...)` (see its `_js()` `api()` helper) and
receives `window.VerbalNative(event, payload)` events. The methods it uses:

- `get_state` — full dashboard state (already on `DashboardApi`).
- `toggle_recording` — start/stop dictation.
- `save_settings` — used by the sync toggle.
- `fetch_canvas` — canvas view content.
- `copy_text` — copy/paste-again buttons.
- `open_meeting_launcher` — the "Start meeting" row.
- `open_window` — open the full dashboard (`api('open_window')`).
- `open_preferences` — open dashboard on the settings tab.
- `quit_app` — quit.

Events it handles in `window.VerbalNative`: `recordingState`, `state`, `result`.

Most of these already exist on `DashboardApi`. Ensure these three resolve correctly on Windows:

- `open_window` → `self.app.dashboard.show()` (opens the shared Flume dashboard window).
- `open_preferences` → `self.app.dashboard.show()` then `_on_tab_select(4)` (settings; see
  `shared_dashboard.SharedDashboard._on_tab_select` TAB_MAP where `4 → "settings"`).
- `quit_app` → `self.app._tray_quit()`.

Check whether `DashboardApi` already implements `open_window` / `open_preferences` / `quit_app`
(the Mac popover bridge in `flume_popover.py` provides them). If they're Mac-only, add them to
`DashboardApi` guarded so both platforms work, OR provide a small popover-specific `js_api` that
delegates to `DashboardApi` for the shared methods and to `self.app` for window/quit actions.

## Hosting details

- `webview.create_window("Flume", html=popover_html(), js_api=<bridge>, width=380, height=600,
  frameless=True, on_top=True, ...)`. The Mac popover is compact (~380 wide); match it.
- Position near the tray: bottom-right of the work area, just above the taskbar/notification area.
  Compute from screen metrics (the popover should appear anchored to the tray, like the Mac popover
  anchors to the menubar item).
- Reuse the same single-`webview.start()` discipline as W3 (do not start a second event loop).
- Show/hide on subsequent left-clicks (toggle), and hide on blur if WebView2 exposes a lost-focus
  event; otherwise leave it until clicked again. Unlike the overlay, the popover **may** take focus
  (it's an interactive panel the user clicked), so `WS_EX_NOACTIVATE` is NOT required here.

## Acceptance

- [ ] Left-click tray → compact Flume popover appears (identical to Mac `popover_html()`).
- [ ] Right-click tray → existing pystray menu still works.
- [ ] Record button, sync toggle, History/Canvas quick cards, and recent list all work.
- [ ] "Open window" opens the full dashboard; "Preferences" opens it on Settings; "Quit" quits.
- [ ] "Start meeting" routes through `open_meeting_launcher` (works once W6 lands; before that it
      returns a fail-closed error and the popover simply shows no meeting UI).
- [ ] Popover build failure never breaks the tray menu or dictation.

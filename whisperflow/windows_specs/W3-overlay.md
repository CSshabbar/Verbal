# W3 — Recording overlay (pywebview, frameless, topmost, non-activating)

**Status (2026-08-29):** **Do not implement as written.** WebView2's DirectComposition surface cannot
do per-pixel transparency, so a pywebview host would draw a dark rectangle around the pill. Shipping
`win_overlay.py` is tkinter + PIL with `-transparentcolor` (DPI-scaled, hover pause/cancel/stop,
error state). Cancel-while-transcribing goes through `_on_esc_pressed` (IDI-165). Keep this spec as
historical; pixel parity is the sticker look, not the HTML host.

**Goal:** replace the tkinter-drawn pill in `app/win_overlay.py` with a **pywebview** frameless,
always-on-top, **non-focus-stealing** window that renders `app/overlay_html.py::overlay_html()` — the
exact HTML the Mac overlay uses — and is driven by `window.VerbalOverlay(mode, data)`. This gives the
Windows overlay pixel parity with the Mac (`Recording → Transcribing → Done`), animated waveform,
timer, and action buttons.

## Files

- **Modify:** `app/win_overlay.py` — rewrite `WinOverlay` to host `overlay_html()` in pywebview.
- **Reuse (do not edit):** `app/overlay_html.py`, `app/fonts_css.py`.
- **Reference (Mac original):** `app/overlay.py` (`OverlayBar`).
- **Caller (do not change its calls):** `app/win_main.py` (`self.overlay = WinOverlay()` line 89, and
  `overlay.setup/show/update_status/show_briefly/hide` in the pipeline).

## The interface `WinOverlay` MUST keep

`win_main.py` uses exactly these — signatures must not change:

```python
def setup(self): ...                              # start the window (called once at start())
def show(self, status="Listening..."): ...        # begin recording pill
def update_status(self, status): ...              # e.g. "Transcribing..."
def show_briefly(self, status, duration=2.0): ... # e.g. "Pasted | 38w", auto-hide
def hide(self): ...
@property
def visible(self): ...                            # bool
```

Call sites in `win_main.py`: `_on_record_start` → `overlay.show("Listening...")`; `_on_record_stop` /
`_process_audio` → `overlay.update_status("Transcribing...")`; success →
`overlay.show_briefly(f"Pasted | {word_count}w", duration=2.0)`; cancel/empty → `overlay.hide()`.

## Mapping the flat status strings to `VerbalOverlay(mode, data)`

The Mac `overlay.py` translates the same flat status calls into the rich HTML modes — mirror that
logic. `overlay_html()`'s JS API is:

```js
window.VerbalOverlay(mode, data)
//  mode 'recording'     data {device}
//  mode 'transcribing'  data {src, dst, secs}
//  mode 'done'          data {label, meta}   e.g. label "Pasted to WIN", meta "38W · 14S"
//  mode 'hide'          (any other value hides all pills)
```

Suggested translation (see `overlay.py::show/update_status/show_briefly` for the reference):

| WinOverlay call | push |
|---|---|
| `show("Listening...")` | `VerbalOverlay('recording', {device: <this device name>})`; record `t0 = time.time()` |
| `update_status(s)` where `"Transcrib" in s` | `VerbalOverlay('transcribing', {src, dst, secs: int(time-t0)})` |
| `update_status(s)` (warning like "No speech") | `VerbalOverlay('done', {label: s, meta: ""})` |
| `show_briefly(s, dur)` | parse words from `s` → `VerbalOverlay('done', {label, meta})`, then auto-hide after `dur` (use a cancel token like `overlay.py::_done_token`) |
| `hide()` | `VerbalOverlay('hide')` |

Device name: `self.app.config.get("sync_device_name") or "WIN"`. (Mac uses `"MAC"`; use `"WIN"`.)

## Button actions (bridge)

The pill's buttons call `window.pywebview.api.<action>()` where action ∈
`{overlay_stop, overlay_cancel, overlay_pause, overlay_copy, overlay_dismiss}` (see the `onclick`
handlers in `overlay_html.py`). Provide a `js_api` object on the pywebview window exposing these
method names, mirroring `overlay.py`'s button handlers:

- `overlay_stop` → `self.app._toggle_recording()` (stops the current recording).
- `overlay_cancel` → `self.app._cancel_recording()`.
- `overlay_pause` → `self.app.recorder.toggle_pause()` if available (Windows recorder may not support
  pause yet — no-op safely).
- `overlay_copy` → copy `self.app._last_result_text` via `pyperclip` (store last result in the
  pipeline if not already; safe no-op if empty).
- `overlay_dismiss` → `self.hide()`.

Because pywebview `js_api` methods run on a pywebview worker thread, these can call app methods
directly (Windows `_on_main` is just a daemon-thread wrapper — see `win_main.py::_on_main`).

## Hosting details (pywebview / WebView2)

- Create the window with `webview.create_window(..., frameless=True, on_top=True, easy_drag=False,
  transparent=True, background_color='#00000000', width=720, height=150, x=..., y=...)`. Size ≥ the
  Mac panel (`overlay.py` uses `PANEL_W=720, PANEL_H=150`) so the pill + shadow aren't clipped.
- Position: horizontally centered, near the bottom of the primary work area (Mac uses `y=40` from the
  bottom; on Windows compute from `SystemParameters`/`ctypes` screen metrics and place ~80px above the
  taskbar, matching the old tkinter `y = screen_h - PILL_H - 80`).
- Drive JS with `window.evaluate_js("if(window.VerbalOverlay)window.VerbalOverlay(%s,%s)" % (json.dumps(mode), json.dumps(data)))`.
- Wait for `pywebviewready` / the window's `loaded` event before the first push; queue any push that
  arrives before load (mirror the Mac `_ready` guard). Since `overlay_html()` waits for its own
  script, an early push simply no-ops via the `if(window.VerbalOverlay)` guard — but still gate
  `evaluate_js` behind window existence.
- pywebview needs ONE `webview.start()` event loop per process. The dashboard already calls
  `webview.start()` in `SharedDashboard.show()`. **Do not call `webview.start()` twice.** Options:
  (a) create the overlay window lazily and let the first `webview.start()` own the loop, or
  (b) if the overlay must exist before the dashboard is opened, create it as the first window and
  ensure a single shared `webview.start()` is invoked once at app start. Decide based on WebView2
  behavior on the target machine and document the choice in the module docstring.

## RISK — transparent/frameless topmost non-activating windows on WebView2

WebView2 + pywebview transparency and "never take focus" are **finicky on Windows**. Two hazards:

1. **Focus stealing.** A normal topmost window will steal keyboard focus when shown — fatal, because
   the overlay appears *while the user is dictating into another app*. Prevent it with the
   `WS_EX_NOACTIVATE` extended style (and `WS_EX_TOPMOST`), and show via `ShowWindow(SW_SHOWNOACTIVATE)`
   / `SetWindowPos(..., SWP_NOACTIVATE)` rather than a plain activate. Since pywebview may not expose
   these, reach the HWND (via the winforms/edgechromium backend or `FindWindow` by title) and apply
   `user32.SetWindowLongW(hwnd, GWL_EXSTYLE, cur | WS_EX_NOACTIVATE | WS_EX_TOPMOST)` after creation.
2. **Transparency artifacts.** Per-pixel transparency behind rounded corners often renders as a black
   or opaque box under WebView2.

**Fallback (ship this if transparency misbehaves):** render a **solid dark rounded pill with NO
window transparency** — set `transparent=False`, `background_color='#0e1012'` (the Flume screen bg),
and size the window tightly to the pill so there's no visible transparent margin. The pill CSS in
`overlay_html.py` already draws the rounded dark surface (`--pill:rgba(22,20,18,.96)`); a solid
matching window background makes the corners read acceptably. Document which path shipped.

## How to test focus-stealing

1. Open Notepad (or any editor) and click into it so it has the caret.
2. Trigger recording (Right Alt). The overlay appears.
3. **Type on the keyboard.** If characters land in Notepad → success (overlay is non-activating). If
   they vanish / the overlay took focus → the `WS_EX_NOACTIVATE` path isn't applied; fix before
   shipping. This is the single most important acceptance check for W3.

## Acceptance

- [ ] Overlay renders `overlay_html()` (identical pill to Mac), fonts via `fonts_css.py`.
- [ ] `show / update_status / show_briefly / hide / visible` behave as the pipeline expects.
- [ ] Recording → Transcribing → Done transitions match Mac (timer counts, waveform animates,
      done pill shows word/second meta and auto-hides).
- [ ] **Typing test above passes** — overlay never steals focus.
- [ ] Buttons (stop/cancel/pause/copy/dismiss) fire the right app actions.
- [ ] Dictation still works if the overlay fails to build (wrap `setup()` in try/except; a failed
      overlay must not break `record → transcribe → inject`).

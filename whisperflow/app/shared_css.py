"""
Shared CSS fragments for every Flume desktop WebView surface.

The desktop UI is HTML/CSS generated from Python strings across several
modules (dashboard, popover, overlay, meeting window, and the floating
pills). Anything that must look *identical* on all of them belongs here so
there is one definition to change, not eight.

Note for editors: these strings are plain (non-raw) Python, so any CSS
escape needs a DOUBLE backslash (``\\2014``) — a single one is an octal
escape. Nothing in here currently uses an escape; keep it that way if you
can.
"""

# ── Canonical Flume pressed state (IDI-168) ──────────────────────────────────
# The one and only "button is being pressed" feedback in the product: a 3%
# scale-down plus a slight dim, fast enough (60ms) to read as tactile rather
# than animated. Deliberately property-disjoint from the hover rules each
# surface already has (which change background/color), so hover and press
# compose instead of fighting — but the block must still be emitted AFTER the
# surface's own CSS, because a few hover rules DO set `filter`
# (e.g. `.stop:hover{filter:brightness(1.08)}`) and equal-specificity ties are
# broken by source order.
_PRESSED_BODY = (
    "transform:scale(0.97);"
    "filter:brightness(0.92);"
    "transition:transform 60ms ease,filter 60ms ease"
)


def pressed_css(selectors: list[str]) -> str:
    """Return the canonical Flume pressed-state rule (IDI-168) for `selectors`.

    Each entry is a plain selector for an *interactive* element (button, link,
    toggle, tab…); this appends `:active` to it. Never pass a non-interactive
    element — a pressed state on something that can't be pressed is a lie.

    Returns "" for an empty list so callers can inject unconditionally.
    """
    sels = [s.strip() for s in (selectors or []) if s and s.strip()]
    if not sels:
        return ""
    joined = ",".join(f"{s}:active" for s in sels)
    return (
        "\n/* Canonical Flume pressed state — IDI-168. Edit in app/shared_css.py"
        " (pressed_css) so every surface stays in sync. */\n"
        f"{joined}{{{_PRESSED_BODY}}}\n"
    )

"""Verification helper (context/05-conventions.md checklist): extract every inline <script> block (no src, not application/json) from the rendered
dashboard / meeting / popover HTML and run `node --check` on each.

Usage: cd whisperflow && .venv/Scripts/python.exe scripts/js_check.py   (node must be on PATH)
Exit code 1 if any block fails to parse. Blocks are written to %TEMP%/flume_js_blocks/."""
import os, re, subprocess, sys, tempfile
# Runs from anywhere: the app package lives one directory up from scripts/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(tempfile.gettempdir(), "flume_js_blocks")
os.makedirs(OUT, exist_ok=True)

from app.flume_dashboard_html import flume_html
from app.meeting_html import meeting_html
from app.flume_popover_html import popover_html

renderers = {"dashboard": flume_html, "meeting": meeting_html, "popover": popover_html}
tag_re = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)

total = fails = 0
for name, fn in renderers.items():
    html = fn()
    blocks = tag_re.findall(html)
    kept = 0
    for i, (attrs, body) in enumerate(blocks):
        a = attrs.lower()
        if "src=" in a:
            continue
        if "application/json" in a or "application/ld+json" in a or "text/template" in a:
            continue
        kept += 1
        total += 1
        path = os.path.join(OUT, f"{name}_{i}.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
        status = "PASS" if r.returncode == 0 else "FAIL"
        if r.returncode:
            fails += 1
        print(f"[{status}] {name} block #{i} ({len(body)} chars, attrs={attrs.strip()!r}) -> {os.path.basename(path)}")
        if r.returncode:
            print((r.stderr or r.stdout).strip()[:1500])
    print(f"  {name}: {len(blocks)} script tags, {kept} checked")
print(f"TOTAL checked={total} failed={fails}")
sys.exit(1 if fails else 0)

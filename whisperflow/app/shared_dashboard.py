"""Shared web dashboard for cross-platform desktop builds.

This is intentionally separate from the macOS AppKit dashboard so the current
Mac app remains untouched while Windows gets the same product surface.
"""

from __future__ import annotations

import base64
import datetime as _dt
import logging
import threading
import time
from typing import Any

import pyperclip

from app.config import (
    APP_VERSION,
    _entry_app,
    _entry_text,
    get_daily_words,
    load_config,
    save_config,
)

logger = logging.getLogger("verbal.shared_dashboard")


def _ok(**data):
    return {"ok": True, **data}


def _err(message: str):
    return {"ok": False, "error": message}


class SharedDashboard:
    def __init__(self, app):
        self.app = app
        self._window = None
        self._target_device_id = "__all__"
        self._known_devices = []
        self._last_canvas_loaded = False
        self._canvas_listener_started = False

    def show(self):
        try:
            import webview
        except Exception as e:
            logger.error(f"pywebview is not available: {e}")
            from app.win_dashboard import WinDashboard

            fallback = WinDashboard(self.app)
            fallback.show()
            return

        if self._window:
            try:
                self._window.show()
                return
            except Exception:
                self._window = None

        api = DashboardApi(self)
        self._window = webview.create_window(
            "Verbal",
            html=_html(),
            js_api=api,
            width=980,
            height=680,
            min_size=(760, 520),
            background_color="#1A1917",
        )
        threading.Thread(target=self._device_refresh_loop, daemon=True).start()
        if not self._canvas_listener_started:
            self._canvas_listener_started = True
            threading.Thread(target=self._canvas_listen_loop, daemon=True).start()
        webview.start(debug=False)

    def update_recording_state(self, is_recording: bool):
        self._emit("recordingState", {"recording": is_recording})

    def show_result(self, text: str):
        self._emit("result", {"text": text})

    def _refresh(self):
        self._emit("state", DashboardApi(self).get_state())

    def _emit(self, event: str, payload: dict[str, Any]):
        if not self._window:
            return
        try:
            import json

            js = f"window.VerbalNative && window.VerbalNative({json.dumps(event)}, {json.dumps(payload)});"
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug(f"Dashboard emit failed: {e}")

    def _device_refresh_loop(self):
        while True:
            try:
                self._load_devices()
            except Exception as e:
                logger.debug(f"Device refresh failed: {e}")
            time.sleep(30)

    def _load_devices(self):
        cfg = self.app.config
        user_id = cfg.get("sync_user_id", "")
        if not user_id or not self.app._sync:
            self._known_devices = []
            return
        from app.sync import fetch_devices

        devices = fetch_devices(user_id, self.app._sync.device_id)
        self._known_devices = devices
        self._emit("devices", {"devices": devices})

    def _canvas_listen_loop(self):
        """Keep canvas synced while the dashboard is open."""
        while True:
            try:
                self._canvas_listen_once()
            except Exception as e:
                logger.debug(f"Canvas listener failed: {e}")
            time.sleep(5)

    def _canvas_listen_once(self):
        import json
        import websocket

        from app.sync import SUPABASE_KEY, WS_URL

        user_id = self.app.config.get("sync_user_id", "")
        device_name = self.app.config.get("sync_device_name", "Windows")
        if not user_id:
            time.sleep(5)
            return

        def on_open(ws):
            ws.send(
                json.dumps(
                    {
                        "topic": "realtime:*",
                        "event": "phx_join",
                        "payload": {
                            "config": {
                                "postgres_changes": [
                                    {
                                        "event": "*",
                                        "schema": "public",
                                        "table": "canvas",
                                        "filter": f"user_id=eq.{user_id}",
                                    }
                                ]
                            }
                        },
                        "ref": "shared_canvas",
                    }
                )
            )

        def on_message(ws, raw):
            try:
                msg = json.loads(raw)
                if msg.get("event") != "postgres_changes":
                    return
                record = msg.get("payload", {}).get("data", {}).get("record", {})
                if record.get("device_name") == device_name:
                    return
                content = record.get("content", "") or ""
                image_url = record.get("image_url")
                if content:
                    pyperclip.copy(content)
                self._emit(
                    "canvasRemote",
                    {
                        "content": content,
                        "image_url": image_url,
                        "device_name": record.get("device_name", "device"),
                    },
                )
            except Exception as e:
                logger.debug(f"Canvas message ignored: {e}")

        ws = websocket.WebSocketApp(
            WS_URL,
            header={"Authorization": f"Bearer {SUPABASE_KEY}"},
            on_open=on_open,
            on_message=on_message,
        )
        ws.run_forever(ping_interval=25, ping_timeout=10)


class DashboardApi:
    def __init__(self, dashboard: SharedDashboard):
        self.dashboard = dashboard

    @property
    def app(self):
        return self.dashboard.app

    def get_state(self):
        cfg = self.app.config = load_config()
        history = cfg.get("history", [])
        pinned = cfg.get("pinned", [])
        total_words = sum(len(_entry_text(h).split()) for h in history)
        return _ok(
            version=APP_VERSION,
            recording=self.app._is_recording,
            processing=self.app._processing,
            model=cfg.get("whisper_model", "base"),
            mode=cfg.get("recording_mode", "toggle"),
            daily_words=get_daily_words(cfg),
            total_transcriptions=len(history),
            total_words=total_words,
            history=[
                {
                    "text": _entry_text(e),
                    "app": _entry_app(e),
                    "ts": e.get("ts", "") if isinstance(e, dict) else "",
                }
                for e in history
            ],
            pinned=[
                {
                    "text": _entry_text(e),
                    "app": _entry_app(e),
                    "ts": e.get("ts", "") if isinstance(e, dict) else "",
                }
                for e in pinned
            ],
            settings={
                "groq_api_keys": cfg.get("groq_api_keys", []),
                "gemini_api_keys": cfg.get("gemini_api_keys", []),
                "sync_enabled": cfg.get("sync_enabled", False),
                "sync_user_id": cfg.get("sync_user_id", ""),
                "sync_device_name": cfg.get("sync_device_name", "Windows"),
            },
            sync_connected=bool(self.app._sync and self.app._sync.connected),
            devices=self.dashboard._known_devices,
            target_device_id=self.dashboard._target_device_id,
        )

    def start_recording(self):
        self.app._on_record_start()
        return _ok()

    def stop_recording(self):
        self.app._on_record_stop()
        return _ok()

    def set_target_device(self, device_id):
        self.dashboard._target_device_id = device_id
        return _ok()

    def copy_text(self, text):
        pyperclip.copy(text or "")
        return _ok()

    def pin_text(self, text, should_pin):
        cfg = self.app.config
        pinned = list(cfg.get("pinned", []))
        pinned_texts = [_entry_text(e) for e in pinned]
        if should_pin and text not in pinned_texts:
            match = next((e for e in cfg.get("history", []) if _entry_text(e) == text), None)
            pinned.insert(0, match if isinstance(match, dict) else {"text": text, "app": "", "ts": ""})
        elif not should_pin:
            pinned = [e for e in pinned if _entry_text(e) != text]
        cfg["pinned"] = pinned[:50]
        save_config(cfg)
        return self.get_state()

    def edit_text(self, old_text, new_text):
        cfg = self.app.config
        for key in ("history", "pinned"):
            entries = []
            for e in cfg.get(key, []):
                if _entry_text(e) == old_text:
                    if isinstance(e, dict):
                        e = {**e, "text": new_text}
                    else:
                        e = {"text": new_text, "app": "", "ts": ""}
                entries.append(e)
            cfg[key] = entries
        save_config(cfg)
        return self.get_state()

    def clear_history(self):
        self.app.config["history"] = []
        self.app.config["pinned"] = []
        save_config(self.app.config)
        return self.get_state()

    def save_settings(self, settings):
        cfg = self.app.config
        cfg["groq_api_keys"] = [k.strip() for k in settings.get("groq_api_keys", []) if k.strip()]
        cfg["gemini_api_keys"] = [k.strip() for k in settings.get("gemini_api_keys", []) if k.strip()]
        cfg["whisper_model"] = settings.get("whisper_model", cfg.get("whisper_model", "base"))
        cfg["recording_mode"] = settings.get("recording_mode", cfg.get("recording_mode", "toggle"))
        cfg["sync_enabled"] = bool(settings.get("sync_enabled"))
        cfg["sync_user_id"] = settings.get("sync_user_id", "").strip()
        cfg["sync_device_name"] = settings.get("sync_device_name", "").strip() or "Windows"
        save_config(cfg)
        self.app.config = cfg
        self.app._mode = cfg["recording_mode"]
        self.app._restart_sync()
        self.dashboard._load_devices()
        return self.get_state()

    def fetch_canvas(self):
        try:
            import httpx

            from app.sync import SUPABASE_KEY, SUPABASE_URL

            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return _ok(content="", image_url=None, status="Set User ID in Settings first")
            resp = httpx.get(
                f"{SUPABASE_URL}/rest/v1/canvas",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"user_id": f"eq.{user_id}", "select": "content,image_url"},
                timeout=8,
            )
            if resp.status_code != 200:
                return _err(f"Canvas load failed: {resp.status_code}")
            data = resp.json()
            row = data[0] if data else {}
            return _ok(content=row.get("content", "") or "", image_url=row.get("image_url"))
        except Exception as e:
            logger.error(f"Canvas fetch failed: {e}")
            return _err(str(e))

    def save_canvas(self, content, image_url=None):
        try:
            import httpx

            from app.sync import SUPABASE_KEY, SUPABASE_URL

            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return _err("Set User ID in Settings first")
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/canvas?on_conflict=user_id",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal,resolution=merge-duplicates",
                },
                json={
                    "user_id": user_id,
                    "content": content or "",
                    "image_url": image_url,
                    "device_name": self.app.config.get("sync_device_name", "Windows"),
                    "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                },
                timeout=10,
            )
            if resp.status_code not in (200, 201):
                return _err(f"Canvas save failed: {resp.status_code}")
            if content:
                pyperclip.copy(content)
            return _ok()
        except Exception as e:
            logger.error(f"Canvas save failed: {e}")
            return _err(str(e))

    def choose_canvas_image(self):
        try:
            import webview

            if not self.dashboard._window:
                return _err("Dashboard window is not ready")
            paths = self.dashboard._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Images (*.png;*.jpg;*.jpeg;*.webp;*.gif)", "All files (*.*)"),
            )
            if not paths:
                return _ok(cancelled=True)
            return self._upload_image_path(paths[0])
        except Exception as e:
            logger.error(f"Image selection failed: {e}")
            return _err(str(e))

    def paste_canvas_image_from_clipboard(self):
        try:
            from PIL import ImageGrab

            img = ImageGrab.grabclipboard()
            if img is None:
                return _err("Clipboard does not contain an image")
            import io

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return self._upload_image_bytes(buf.getvalue(), "png")
        except Exception as e:
            logger.error(f"Clipboard image upload failed: {e}")
            return _err(str(e))

    def _upload_image_path(self, path):
        with open(path, "rb") as f:
            data = f.read()
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "png"
        if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
            ext = "png"
        return self._upload_image_bytes(data, ext)

    def _upload_image_bytes(self, data: bytes, ext: str):
        import httpx

        from app.sync import SUPABASE_KEY, SUPABASE_URL

        user_id = self.app.config.get("sync_user_id", "")
        if not user_id:
            return _err("Set User ID in Settings first")
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        path = f"canvas/{user_id}_{int(time.time())}.{ext}"
        upload = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/canvas-images/{path}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": mime,
                "x-upsert": "true",
            },
            content=data,
            timeout=30,
        )
        if upload.status_code not in (200, 201):
            return _err(f"Image upload failed: {upload.status_code}")
        url = f"{SUPABASE_URL}/storage/v1/object/public/canvas-images/{path}"
        return _ok(image_url=url, preview=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}")


def _html() -> str:
    return r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root{--bg:#1A1917;--sheet:#F2EFE9;--card:#fff;--text:#2C2A27;--muted:#7A7570;--sub:#9A9590;--accent:#E05A2B;--green:#3DAA6E;--line:#E2DDD5}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);font-family:"Segoe UI",Inter,system-ui,sans-serif;color:var(--text);overflow:hidden}
    button,input,textarea,select{font:inherit} button{border:0;cursor:pointer}
    .app{display:grid;grid-template-columns:176px 1fr;height:100vh;background:var(--bg)}
    .side{padding:24px 16px;border-right:1px solid rgba(255,255,255,.06);color:var(--sheet)}
    .brand{display:flex;gap:10px;align-items:center;margin-bottom:28px}.star{color:var(--accent);font-size:22px}.brand h1{font-size:20px;margin:0;font-weight:650}
    .nav{display:grid;gap:8px}.nav button{height:50px;border-radius:8px;background:transparent;color:#C9C2BA;text-align:left;padding:0 12px}.nav button.active{background:rgba(255,255,255,.08);color:#fff}.nav small{display:block;color:#7A7570;margin-top:2px}
    .main{display:grid;grid-template-rows:150px 1fr;min-width:0}
    .hero{position:relative;padding:24px 28px;color:var(--sheet);overflow:hidden}.hero h2{font-size:34px;line-height:1;margin:0 0 10px}.hero .stats{display:flex;gap:20px;color:var(--muted);font-size:13px}.hero .stats b{color:var(--accent)}
    .record{position:absolute;right:28px;bottom:24px;display:flex;align-items:center;gap:12px}.recbtn{height:42px;padding:0 18px;border-radius:8px;background:var(--accent);color:white;font-weight:650}.recbtn.recording{background:#B94320}.device{height:32px;border-radius:8px;background:rgba(255,255,255,.08);color:var(--sheet);border:1px solid rgba(255,255,255,.08);padding:0 10px}
    .sheet{background:var(--sheet);border-top-left-radius:28px;overflow:hidden;min-height:0}.toolbar{height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid var(--line)}.search{height:34px;width:240px;border:0;border-radius:8px;background:#fff;padding:0 12px;color:var(--text)}
    .content{height:calc(100vh - 202px);overflow:auto;padding:18px 20px}.grid{display:grid;gap:12px}.card{background:#fff;border-radius:8px;padding:14px;box-shadow:0 2px 8px rgba(0,0,0,.04)}.card.pin{background:#FFF7F2}.cardTop{display:flex;justify-content:space-between;gap:12px}.text{white-space:pre-wrap;line-height:1.45;font-size:14px}.meta{font-size:11px;color:var(--sub);margin-top:8px}.actions{display:flex;gap:6px;flex:none}.icon{width:30px;height:30px;border-radius:7px;background:#F0ECE6;color:var(--text)}.icon.hot{background:rgba(224,90,43,.12);color:var(--accent)}
    .sectionTitle{font-size:11px;letter-spacing:1px;color:var(--sub);font-weight:750;margin:18px 0 10px}.empty{color:var(--muted);padding:40px;text-align:center}
    .statsGrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.statCard b{display:block;color:var(--accent);font-size:30px}.statCard span{color:var(--muted);font-size:13px}
    .settings{display:grid;grid-template-columns:1fr 1fr;gap:14px}.field{display:grid;gap:7px;margin:10px 0}.field label{font-size:11px;font-weight:750;color:var(--sub);letter-spacing:.7px}.field input,.field textarea,.field select{border:0;border-radius:8px;background:#F7F5F1;padding:10px;color:var(--text)}.field textarea{min-height:72px;resize:vertical}.save{background:var(--bg);color:var(--sheet);height:38px;border-radius:8px;padding:0 16px;font-weight:650}.danger{background:rgba(224,90,43,.12);color:var(--accent)}
    .canvasWrap{display:grid;grid-template-rows:auto 1fr auto;gap:12px;min-height:100%}.canvasActions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.canvasText{width:100%;min-height:260px;border:0;border-radius:8px;background:#FAFAF8;padding:16px;line-height:1.5;color:var(--text);resize:vertical}.imagePreview{max-height:190px;max-width:100%;border-radius:8px;background:#ECEAE6;display:block;margin-bottom:8px}.status{font-size:12px;color:var(--muted)}.ok{color:var(--green)}.bad{color:var(--accent)}
    .modal{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:center;justify-content:center}.modal.open{display:flex}.dialog{width:min(640px,90vw);background:white;border-radius:10px;padding:16px}.dialog textarea{width:100%;height:220px;border:1px solid var(--line);border-radius:8px;padding:12px}.dialogBtns{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}
  </style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="brand"><div class="star">✳</div><h1>Verbal</h1></div>
    <div class="nav" id="nav"></div>
  </aside>
  <main class="main">
    <section class="hero">
      <h2 id="headline">Ready to dictate.</h2>
      <div class="stats" id="heroStats"></div>
      <div class="record">
        <select class="device" id="targetDevice"></select>
        <button class="recbtn" id="recordBtn">Start Recording</button>
      </div>
    </section>
    <section class="sheet">
      <div class="toolbar"><div id="toolbarTitle"></div><input id="search" class="search" placeholder="Search history" /></div>
      <div class="content" id="content"></div>
    </section>
  </main>
</div>
<div class="modal" id="modal"><div class="dialog"><h3>Edit transcription</h3><textarea id="editText"></textarea><div class="dialogBtns"><button class="save danger" onclick="closeModal()">Cancel</button><button class="save" onclick="saveEdit()">Save</button></div></div></div>
<script>
const tabs=[["all","All","Recent dictation"],["apps","By App","Grouped history"],["stats","Stats","Usage overview"],["canvas","Canvas","Shared clipboard"],["settings","Settings","Keys & preferences"]];
let state=null, active="all", query="", editOld="", canvasImage=null, canvasPreview=null, canvasContent="", canvasLoaded=false;
const $=id=>document.getElementById(id);
function esc(s){return (s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]))}
function words(t){return (t||"").trim()?t.trim().split(/\s+/).length:0}
async function api(name,...args){return await window.pywebview.api[name](...args)}
function nav(){ $("nav").innerHTML=tabs.map(t=>`<button class="${active===t[0]?"active":""}" onclick="active='${t[0]}';render()">${t[1]}<small>${t[2]}</small></button>`).join("")}
async function load(){ state=await api("get_state"); render(); }
function render(){ if(!state)return; nav(); $("headline").textContent=state.recording?"Listening...":state.processing?"Transcribing...":"Ready to dictate."; $("recordBtn").textContent=state.recording?"Stop Recording":"Start Recording"; $("recordBtn").className="recbtn"+(state.recording?" recording":""); $("heroStats").innerHTML=`<span><b>${state.total_transcriptions}</b> transcriptions</span><span><b>${state.total_words}</b> words</span><span><b>${state.daily_words}</b> today</span><span>${esc(state.model)} · ${esc(state.mode)}</span>`; renderDevices(); ({all:renderAll,apps:renderApps,stats:renderStats,settings:renderSettings,canvas:renderCanvas}[active])(); }
function renderDevices(){ const opts=[`<option value="__all__">Send to all devices</option>`,`<option value="__none__">Local only</option>`].concat((state.devices||[]).map(d=>`<option value="${esc(d.device_id)}">${esc(d.device_name)} · ${esc(d.device_type)}</option>`)); $("targetDevice").innerHTML=opts.join(""); $("targetDevice").value=state.target_device_id||"__all__"; }
$("targetDevice").onchange=async e=>{ await api("set_target_device",e.target.value); state.target_device_id=e.target.value; };
$("recordBtn").onclick=async()=>{ state.recording?await api("stop_recording"):await api("start_recording"); setTimeout(load,250); };
$("search").oninput=e=>{query=e.target.value.toLowerCase(); if(active==="all"||active==="apps")render();}
function filtered(list){return list.filter(e=>(e.text+" "+e.app).toLowerCase().includes(query))}
function card(e,pin=false){return `<div class="card ${pin?"pin":""}"><div class="cardTop"><div><div class="text">${esc(e.text)}</div><div class="meta">${esc(e.app||"Unknown app")} · ${esc(e.ts||"")} · ${words(e.text)} words</div></div><div class="actions"><button class="icon" title="Copy" onclick='copyText(${JSON.stringify(e.text)})'>⎘</button><button class="icon ${pin?"hot":""}" title="${pin?"Unpin":"Pin"}" onclick='pinText(${JSON.stringify(e.text)},${!pin})'>⌖</button><button class="icon" title="Edit" onclick='openEdit(${JSON.stringify(e.text)})'>✎</button></div></div></div>`}
function renderAll(){ $("toolbarTitle").textContent="All Transcriptions"; const p=filtered(state.pinned||[]), h=filtered(state.history||[]); $("content").innerHTML=`${p.length?'<div class="sectionTitle">PINNED</div>'+p.map(e=>card(e,true)).join(""):""}${h.length?'<div class="sectionTitle">RECENT</div>'+h.map(e=>card(e,false)).join(""):'<div class="empty">No transcriptions yet.</div>'}`; }
function renderApps(){ $("toolbarTitle").textContent="By App"; const groups={}; filtered(state.history||[]).forEach(e=>{const k=e.app||"Unknown app";(groups[k]??=[]).push(e)}); $("content").innerHTML=Object.keys(groups).sort().map(k=>`<div class="sectionTitle">${esc(k)}</div>${groups[k].map(e=>card(e,false)).join("")}`).join("")||'<div class="empty">No app history yet.</div>'; }
function renderStats(){ $("toolbarTitle").textContent="Usage Overview"; $("content").innerHTML=`<div class="statsGrid"><div class="card statCard"><b>${state.total_transcriptions}</b><span>Total transcriptions</span></div><div class="card statCard"><b>${state.total_words}</b><span>Total words</span></div><div class="card statCard"><b>${state.daily_words}</b><span>Words today</span></div></div>`; }
function renderSettings(){ const s=state.settings; $("toolbarTitle").textContent="Settings"; $("content").innerHTML=`<div class="settings"><div class="card"><div class="field"><label>GROQ API KEYS</label><textarea id="groqKeys">${esc((s.groq_api_keys||[]).join("\\n"))}</textarea></div><div class="field"><label>GEMINI API KEYS</label><textarea id="geminiKeys">${esc((s.gemini_api_keys||[]).join("\\n"))}</textarea></div></div><div class="card"><div class="field"><label>WHISPER MODEL</label><select id="model">${["tiny","base","small","medium"].map(m=>`<option ${state.model===m?"selected":""}>${m}</option>`).join("")}</select></div><div class="field"><label>RECORDING MODE</label><select id="mode"><option ${state.mode==="toggle"?"selected":""}>toggle</option><option ${state.mode==="hold"?"selected":""}>hold</option></select></div><div class="field"><label><input type="checkbox" id="syncEnabled" ${s.sync_enabled?"checked":""}/> Enable cross-device sync</label></div><div class="field"><label>USER ID</label><input id="userId" value="${esc(s.sync_user_id||"")}"/></div><div class="field"><label>DEVICE NAME</label><input id="deviceName" value="${esc(s.sync_device_name||"Windows")}"/></div><button class="save" onclick="saveSettings()">Save Settings</button> <span class="status">${state.sync_connected?"Sync connected":"Sync inactive"}</span></div></div>`; }
function renderCanvas(){ $("toolbarTitle").textContent="Canvas"; const existing=$("canvasText")?.value; if(existing!==undefined) canvasContent=existing; $("content").innerHTML=`<div class="canvasWrap"><div class="canvasActions"><button class="save" onclick="saveCanvas()">Save & Sync</button><button class="save" onclick="loadCanvas(true)">Refresh</button><button class="save" onclick="pasteIntoCanvas()">Paste Text</button><button class="save" onclick="chooseImage()">Choose Image</button><button class="save" onclick="pasteImage()">Paste Image</button><button class="save danger" onclick="clearCanvas()">Clear</button><span class="status" id="canvasStatus"></span></div><div><div id="imageBox"></div><textarea class="canvasText" id="canvasText" placeholder="Paste or type here..."></textarea></div></div>`; $("canvasText").value=canvasContent; setCanvasImage(canvasPreview||canvasImage); if(!canvasLoaded) loadCanvas(false); }
async function copyText(t){await api("copy_text",t)}
async function pinText(t,p){state=await api("pin_text",t,p);render()}
function openEdit(t){editOld=t;$("editText").value=t;$("modal").classList.add("open")}
function closeModal(){$("modal").classList.remove("open")}
async function saveEdit(){state=await api("edit_text",editOld,$("editText").value);closeModal();render()}
async function saveSettings(){state=await api("save_settings",{groq_api_keys:$("groqKeys").value.split("\\n"),gemini_api_keys:$("geminiKeys").value.split("\\n"),whisper_model:$("model").value,recording_mode:$("mode").value,sync_enabled:$("syncEnabled").checked,sync_user_id:$("userId").value,sync_device_name:$("deviceName").value});render()}
async function loadCanvas(force){ if(active!=="canvas")return; if(canvasLoaded&&!force)return; const r=await api("fetch_canvas"); if(!r.ok){$("canvasStatus").textContent=r.error;return} canvasContent=r.content||""; $("canvasText").value=canvasContent; canvasImage=r.image_url; canvasPreview=null; canvasLoaded=true; setCanvasImage(canvasImage); $("canvasStatus").textContent=r.status||"Loaded"; }
function setCanvasImage(url){ const box=$("imageBox"); if(!box)return; box.innerHTML=url?`<img class="imagePreview" src="${esc(url)}"/><div><button class="save danger" onclick="removeImage()">Remove image</button></div>`:""; }
async function saveCanvas(){ canvasContent=$("canvasText").value; const r=await api("save_canvas",canvasContent,canvasImage); $("canvasStatus").textContent=r.ok?"Saved & synced":r.error; }
async function pasteIntoCanvas(){ const t=await navigator.clipboard.readText().catch(()=>""); $("canvasText").value= $("canvasText").value ? $("canvasText").value+"\\n\\n"+t : t; canvasContent=$("canvasText").value; }
async function chooseImage(){ const r=await api("choose_canvas_image"); if(r.cancelled)return; if(!r.ok){$("canvasStatus").textContent=r.error;return} canvasImage=r.image_url; canvasPreview=r.preview||r.image_url; setCanvasImage(canvasPreview); $("canvasStatus").textContent="Image ready. Save to sync."; }
async function pasteImage(){ const r=await api("paste_canvas_image_from_clipboard"); if(!r.ok){$("canvasStatus").textContent=r.error;return} canvasImage=r.image_url; canvasPreview=r.preview||r.image_url; setCanvasImage(canvasPreview); $("canvasStatus").textContent="Image ready. Save to sync."; }
function removeImage(){canvasImage=null;canvasPreview=null;setCanvasImage(null)}
async function clearCanvas(){ $("canvasText").value=""; canvasContent=""; canvasImage=null; canvasPreview=null; setCanvasImage(null); await saveCanvas(); }
window.VerbalNative=(event,payload)=>{ if(event==="recordingState"){state.recording=payload.recording;render()} if(event==="result"){load()} if(event==="devices"){state.devices=payload.devices;renderDevices()} if(event==="canvasRemote"&&active==="canvas"){canvasContent=payload.content||""; $("canvasText").value=canvasContent; canvasImage=payload.image_url; canvasPreview=null; canvasLoaded=true; setCanvasImage(canvasImage); $("canvasStatus").textContent=`From ${payload.device_name}`;} };
setInterval(()=>{ if(active!=="canvas"&&active!=="settings") load(); },10000); window.addEventListener("pywebviewready",load);
</script>
</body>
</html>
"""

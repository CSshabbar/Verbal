# Cross-Platform Hive Mind Sync — Plan

## Concept
When a transcription completes on any device, it automatically appears in the clipboard of all other connected devices (Mac, iPhone, Android). Like a shared clipboard that syncs in real time.

```
Mac (Verbal) ──► Sync Server ──► Mac 2 (Verbal)
                      │
                      └──► iOS / Android
```

---

## Backend Options

### Option 1 — Supabase (recommended, easiest)
- Free tier, hosted Postgres + Realtime websockets
- No server to run
- Python: `supabase-py`
- iOS: official Swift SDK
- Setup: create account → new project → one table → done

### Option 2 — Firebase Realtime Database
- Google's version of the same idea
- Better mobile SDK support
- Slightly more complex setup

### Option 3 — Self-hosted FastAPI + WebSocket
- Extend the existing `whisper-flow` FastAPI server
- Add `/sync` WebSocket endpoint, broadcast to all connected clients
- Works on LAN without internet
- Needs public IP or tunnel (ngrok / Cloudflare Tunnel) for cross-network use

---

## Database Schema (Supabase)

```sql
create table transcriptions (
  id          uuid default gen_random_uuid() primary key,
  user_id     text not null,
  device_id   text not null,
  device_name text,
  text        text not null,
  created_at  timestamptz default now()
);

-- Index for fast polling
create index on transcriptions (user_id, created_at desc);
```

---

## Mac Implementation

### Config additions (`~/.verbal/config.json`)
```json
{
  "sync_enabled": false,
  "sync_token": "your-supabase-anon-key",
  "sync_user_id": "your-unique-user-id",
  "sync_device_name": "MacBook Pro"
}
```

### New file: `app/sync.py`
```python
import threading
import platform
import httpx
import pyperclip

SUPABASE_URL = "https://your-project.supabase.co"

def sync_push(text: str, config: dict):
    """Push transcription to sync server after it completes."""
    token   = config.get("sync_token", "")
    user_id = config.get("sync_user_id", "")
    device  = config.get("sync_device_name", platform.node())
    if not token or not user_id:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/transcriptions",
            headers={
                "apikey": token,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"user_id": user_id, "device_id": platform.node(),
                  "device_name": device, "text": text},
            timeout=5,
        )
    except Exception as e:
        print(f"Sync push failed: {e}")


def sync_listen(config: dict, on_receive):
    """
    Subscribe to new transcriptions from OTHER devices.
    Runs in a background thread.
    on_receive(text, device_name) called when new entry arrives.
    """
    # TODO: implement Supabase Realtime websocket subscription
    # Filter: user_id = config["sync_user_id"] AND device_id != platform.node()
    # On new row → on_receive(row["text"], row["device_name"])
    pass
```

### Hook into `main.py` — after transcription completes
```python
# In _process_audio, after inject_text(result):
if self.config.get("sync_enabled"):
    from app.sync import sync_push
    threading.Thread(
        target=sync_push,
        args=(result, self.config),
        daemon=True
    ).start()
```

### On receive from another device
```python
def on_sync_receive(text, device_name):
    pyperclip.copy(text)
    # Show overlay: "Synced from MacBook Air"
    self.overlay.show_briefly(f"Synced · {device_name}", duration=3.0)
```

---

## Mobile Side

### Quick option — iOS Shortcut (no app needed)
1. Create a Shortcut with "Get Contents of URL" action
2. Poll `GET /rest/v1/transcriptions?user_id=eq.YOUR_ID&order=created_at.desc&limit=1`
3. Copy result to clipboard
4. Run via Automation: "When I open [any app]" or on a timer

### Proper option — iOS companion app
- SwiftUI app with Supabase Swift SDK
- Subscribe to Realtime channel
- On new row → `UIPasteboard.general.string = text`
- Show notification: "Verbal synced: [preview]"

---

## Dashboard UI additions
- Settings section in Stats page or new Settings tab
- Toggle: "Sync to other devices"
- Field: Supabase token / user ID
- Status indicator: "Connected · 2 devices"
- Recent sync log: "Synced to iPhone · 2 min ago"

---

## Implementation Order
1. [ ] Create Supabase project + table
2. [ ] Add `sync_enabled`, `sync_token`, `sync_user_id` to config
3. [ ] Implement `sync_push()` in `app/sync.py`
4. [ ] Hook push into `_process_audio` in `main.py`
5. [ ] Implement `sync_listen()` with Supabase Realtime websocket
6. [ ] Show overlay notification on receive
7. [ ] Add Settings UI in dashboard
8. [ ] iOS Shortcut for quick mobile support
9. [ ] (Optional) iOS companion app

---

## Notes
- Use `device_id = platform.node()` to filter out own transcriptions
- Encrypt text before sending if privacy is a concern (AES with user-derived key)
- Rate limit: Supabase free tier = 500MB DB, 2GB bandwidth/month — plenty for text
- Consider adding a `seen_by` array to mark which devices have received each entry

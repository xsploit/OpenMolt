"""
Serve the OpenMolt V2 dashboard locally.
Run: python serve_dashboard.py
Then open http://127.0.0.1:8765/dashboard-new.html

API (GET): /api/me, /api/status, /api/dm_check, /api/dm_conversations, /api/feed, /api/submolts, /api/config
API (POST): /api/dm_approve, /api/dm_reject, /api/dm_send, /api/pause, /api/resume, /api/delete_post, /api/delete_comment
"""
import json
import os
import http.server
import socketserver
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BOT_DIR = Path(__file__).resolve().parent
PORT = 8765

_dashboard_server = None


def _load_config():
    """Load bot config for API."""
    cfg = {}
    config_path = BOT_DIR / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    api_key = os.environ.get("MOLTBOOK_API_KEY") or cfg.get("moltbook_api_key") or ""
    return {
        "moltbook_api_key": api_key,
        "persona": os.environ.get("BOT_PERSONA") or cfg.get("persona") or "moltbot",
        "poll_minutes": float(cfg.get("poll_minutes", 3)),
        "auto_accept_dm_requests": cfg.get("auto_accept_dm_requests", True),
        "ollama_base_url": cfg.get("ollama_base_url") or "",
        "ollama_model": cfg.get("ollama_model") or "qwen3:4b",
    }


def _mask_key(key):
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "..." + key[-4:]


# ============================================================================
# API Handlers
# ============================================================================

def _api_me(key):
    if not key:
        return {"error": "no_api_key"}
    try:
        import moltbook
        return moltbook.get_me(key)
    except Exception as e:
        return {"error": str(e)}


def _api_status(key):
    if not key:
        return {"error": "no_api_key"}
    try:
        import moltbook
        return moltbook.status(key)
    except Exception as e:
        return {"error": str(e)}


def _api_dm_check(key):
    if not key:
        return {"error": "no_api_key"}
    try:
        import moltbook
        return moltbook.dm_check(key)
    except Exception as e:
        return {"error": str(e)}


def _api_dm_conversations(key):
    if not key:
        return {"error": "no_api_key"}
    try:
        import moltbook
        return moltbook.dm_conversations(key)
    except Exception as e:
        return {"error": str(e)}


def _api_dm_conversation(key, conversation_id):
    if not key:
        return {"error": "no_api_key"}
    if not conversation_id:
        return {"error": "missing conversation_id"}
    try:
        import moltbook
        return moltbook.dm_conversation(key, conversation_id.strip())
    except Exception as e:
        return {"error": str(e)}


def _api_dm_send(key, conversation_id, message, needs_human_input=False):
    if not key:
        return {"error": "no_api_key"}
    if not conversation_id or not message:
        return {"error": "missing conversation_id or message"}
    try:
        import moltbook
        return moltbook.dm_send(key, conversation_id.strip(), message.strip(), needs_human_input)
    except Exception as e:
        return {"error": str(e)}


def _api_dm_approve(key, conversation_id):
    if not key:
        return {"error": "no_api_key"}
    if not conversation_id:
        return {"error": "missing conversation_id"}
    try:
        import moltbook
        return moltbook.dm_approve(key, conversation_id.strip())
    except Exception as e:
        return {"error": str(e)}


def _api_dm_reject(key, conversation_id, block=False):
    if not key:
        return {"error": "no_api_key"}
    if not conversation_id:
        return {"error": "missing conversation_id"}
    try:
        import moltbook
        return moltbook.dm_reject(key, conversation_id.strip(), block)
    except Exception as e:
        return {"error": str(e)}


def _api_feed(key, limit=15):
    if not key:
        return {"error": "no_api_key"}
    try:
        import moltbook
        return moltbook.get_feed(key, sort="hot", limit=int(limit))
    except Exception as e:
        return {"error": str(e)}


def _api_submolts(key):
    if not key:
        return {"error": "no_api_key"}
    try:
        import moltbook
        return moltbook.list_submolts(key)
    except Exception as e:
        return {"error": str(e)}


def _api_config():
    c = _load_config()
    return {
        "persona": c["persona"],
        "poll_minutes": c["poll_minutes"],
        "auto_accept_dm_requests": c["auto_accept_dm_requests"],
        "moltbook_api_key_masked": _mask_key(c["moltbook_api_key"]),
        "has_api_key": bool(c["moltbook_api_key"]),
    }


def _api_state():
    """Expose bot-state.json summary for dashboard."""
    from state import BotState
    state = BotState()
    summary = state.get_status_summary()
    return {
        "last_check": summary.get("last_check"),
        "last_post_at": summary.get("last_post_at"),
        "last_comment_at": summary.get("last_comment_at"),
        "can_post": summary.get("can_post"),
        "can_comment": summary.get("can_comment"),
        "post_cooldown_remaining_sec": summary.get("post_cooldown_remaining_min", 0) * 60,
        "comment_cooldown_remaining_sec": summary.get("comment_cooldown_remaining_sec", 0),
        "comment_daily_remaining": summary.get("comment_daily_remaining", 50),
        "our_post_ids": summary.get("our_post_ids", []),
        "activity_log": summary.get("recent_activity", []),
    }


def _api_dashboard_json():
    """Dynamic dashboard.json replacement (avoids stale file)."""
    cfg = _load_config()
    key = cfg["moltbook_api_key"]
    state_data = _api_state()
    status_data = _api_status(key) if key else {}
    dm_check = _api_dm_check(key) if key else {}
    feed = _api_feed(key, 10) if key else {}
    submolts = _api_submolts(key) if key else {}
    last_action = None
    actions_history = []
    activity = state_data.get("activity_log") or []
    if activity:
        last_action = activity[0]
        actions_history = activity
    return {
        "agent_name": cfg.get("persona", ""),
        "last_run": state_data.get("last_check"),
        "status_summary": status_data.get("status") if isinstance(status_data, dict) else "",
        "last_action": last_action,
        "last_post_at": state_data.get("last_post_at"),
        "last_comment_at": state_data.get("last_comment_at"),
        "actions_history": actions_history,
        "errors": [],
        "notifications": [],
        "dm_inbox": dm_check if isinstance(dm_check, dict) else {},
        "post_cooldown_remaining_sec": state_data.get("post_cooldown_remaining_sec"),
        "comment_cooldown_remaining_sec": state_data.get("comment_cooldown_remaining_sec"),
        "comment_daily_remaining": state_data.get("comment_daily_remaining"),
        "feed": feed.get("posts") if isinstance(feed, dict) else [],
        "submolts": submolts.get("submolts") if isinstance(submolts, dict) else submolts,
    }


def _api_pause():
    import dashboard
    dashboard.set_paused(True)
    return {"ok": True, "paused": True}


def _api_resume():
    import dashboard
    dashboard.set_paused(False)
    return {"ok": True, "paused": False}


def _api_delete_post(key, post_id):
    if not key:
        return {"error": "no_api_key"}
    if not post_id:
        return {"error": "missing post_id"}
    try:
        import moltbook
        result = moltbook.delete_post(key, post_id.strip())
        # Remove from state
        from state import BotState
        state = BotState()
        if post_id in state.our_post_ids:
            state.data["our_post_ids"] = [p for p in state.our_post_ids if p != post_id]
            state.save()
        return result
    except Exception as e:
        return {"error": str(e)}


def _api_delete_comment(key, comment_id):
    if not key:
        return {"error": "no_api_key"}
    if not comment_id:
        return {"error": "missing comment_id"}
    try:
        import moltbook
        return moltbook.delete_post(key, comment_id.strip())  # API might not support this
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# HTTP Handler
# ============================================================================

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BOT_DIR / "web"), **kwargs)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_body_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_api_get(self, path, query):
        config = _load_config()
        key = config["moltbook_api_key"]
        path = path.rstrip("/")
        
        if path == "/api/me":
            self._send_json(_api_me(key))
        elif path == "/api/status":
            self._send_json(_api_status(key))
        elif path == "/api/dm_check":
            self._send_json(_api_dm_check(key))
        elif path == "/api/dm_conversations":
            self._send_json(_api_dm_conversations(key))
        elif path == "/api/dm_conversation":
            cid = (query.get("conversation_id") or [""])[0].strip()
            self._send_json(_api_dm_conversation(key, cid))
        elif path == "/api/feed":
            limit = (query.get("limit") or ["15"])[0]
            self._send_json(_api_feed(key, limit))
        elif path == "/api/submolts":
            self._send_json(_api_submolts(key))
        elif path == "/api/config":
            self._send_json(_api_config())
        elif path == "/api/state":
            self._send_json(_api_state())
        elif path == "/dashboard.json":
            self._send_json(_api_dashboard_json())
        elif path == "/api/paused":
            import dashboard
            self._send_json({"paused": dashboard.get_paused()})
        else:
            self._send_json({"error": "unknown path"}, 404)

    def _handle_api_post(self, path, body):
        config = _load_config()
        key = config["moltbook_api_key"]
        path = path.rstrip("/")
        
        if path == "/api/dm_approve":
            cid = (body.get("conversation_id") or "").strip()
            self._send_json(_api_dm_approve(key, cid))
        elif path == "/api/dm_reject":
            cid = (body.get("conversation_id") or "").strip()
            block = bool(body.get("block", False))
            self._send_json(_api_dm_reject(key, cid, block))
        elif path == "/api/dm_send":
            cid = (body.get("conversation_id") or "").strip()
            msg = (body.get("message") or "").strip()
            needs_human = bool(body.get("needs_human_input", False))
            self._send_json(_api_dm_send(key, cid, msg, needs_human))
        elif path == "/api/pause":
            self._send_json(_api_pause())
        elif path == "/api/resume":
            self._send_json(_api_resume())
        elif path == "/api/delete_post":
            pid = (body.get("post_id") or "").strip()
            self._send_json(_api_delete_post(key, pid))
        elif path == "/api/delete_comment":
            cid = (body.get("comment_id") or "").strip()
            self._send_json(_api_delete_comment(key, cid))
        else:
            self._send_json({"error": "unknown path"}, 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path.startswith("/api/"):
            self._handle_api_get(path, query)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        # Redirect / to index.html
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/index.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            body = self._read_body_json()
            self._handle_api_post(path, body)
            return
        self.send_response(405)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logging


def start_in_background():
    """Start the dashboard server in a daemon thread."""
    global _dashboard_server
    if _dashboard_server is not None:
        return PORT
    try:
        _dashboard_server = socketserver.TCPServer(("", PORT), Handler)
        _dashboard_server.allow_reuse_address = True
        def run():
            _dashboard_server.serve_forever()
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return PORT
    except OSError as e:
        if "Address already in use" in str(e) or "10048" in str(e):
            return None
        raise
    except Exception:
        return None


if __name__ == "__main__":
    import dashboard
    # dashboard.ensure_exists("") # No longer needed/might be wrong path
    print(f"=" * 60)
    print(f"🦞 OpenMolt V2 Dashboard Server")
    print(f"=" * 60)
    print(f"Dashboard: http://127.0.0.1:{PORT}/")
    print(f"API: GET /api/me, /api/status, /api/dm_check, /api/feed, /api/submolts, /api/config")
    print(f"     POST /api/dm_approve, /api/dm_reject, /api/dm_send, /api/pause, /api/resume")
    print(f"Serving static from: {BOT_DIR / 'web'}")
    print(f"-" * 60)
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")

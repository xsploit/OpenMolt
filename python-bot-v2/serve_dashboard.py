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
# ... unchanged

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

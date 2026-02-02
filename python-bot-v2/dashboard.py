"""
Dashboard data manager - writes dashboard.json for the HTML dashboard.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)

DASHBOARD_PATH = Path("web/dashboard.json")
_paused = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_exists(agent_name: str = "") -> None:
    """Create dashboard.json if it doesn't exist."""
    if DASHBOARD_PATH.exists():
        return
    data = _default_data(agent_name)
    DASHBOARD_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _default_data(agent_name: str = "") -> Dict[str, Any]:
    return {
        "agent_name": agent_name,
        "last_run": None,
        "status_summary": "",
        "last_action": None,
        "last_post_at": None,
        "last_comment_at": None,
        "actions_history": [],
        "errors": [],
        "notifications": [],
        "dm_inbox": None,
    }


def _load() -> Dict[str, Any]:
    if not DASHBOARD_PATH.exists():
        return _default_data()
    try:
        return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_data()


def _save(data: Dict[str, Any]) -> None:
    try:
        DASHBOARD_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"Failed to save dashboard: {e}")


# ============================================================================
# Pause/Resume
# ============================================================================

def get_paused() -> bool:
    return _paused


def set_paused(val: bool) -> None:
    global _paused
    _paused = val


# ============================================================================
# Update Functions
# ============================================================================

def update_cycle(
    agent_name: str,
    status: str,
    dm_inbox: Optional[Dict] = None,
    last_post_at: Optional[str] = None,
    last_comment_at: Optional[str] = None,
) -> None:
    """Update dashboard with cycle info."""
    data = _load()
    data["agent_name"] = agent_name
    data["last_run"] = _now_iso()
    data["status_summary"] = status
    if dm_inbox is not None:
        data["dm_inbox"] = dm_inbox
    if last_post_at:
        data["last_post_at"] = last_post_at
    if last_comment_at:
        data["last_comment_at"] = last_comment_at
    _save(data)


def log_action(
    action: str,
    post_id: Optional[str] = None,
    comment_id: Optional[str] = None,
    snippet: Optional[str] = None,
    submolt: Optional[str] = None,
    override: bool = False,
) -> None:
    """Log an action to history."""
    data = _load()
    entry = {
        "ts": _now_iso(),
        "action": action,
        "post_id": post_id,
        "comment_id": comment_id,
        "snippet": (snippet or "")[:200],
        "submolt": submolt,
        "override": override,
    }
    data["last_action"] = entry
    history = data.get("actions_history") or []
    history.insert(0, entry)
    data["actions_history"] = history[:100]
    _save(data)


def log_error(error: str) -> None:
    """Log an error."""
    data = _load()
    errors = data.get("errors") or []
    errors.append(f"{_now_iso()}: {error}"[:200])
    data["errors"] = errors[-20:]
    _save(data)


def clear_errors() -> None:
    """Clear all logged errors."""
    data = _load()
    data["errors"] = []
    _save(data)


def add_notification(
    type_: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
) -> None:
    """Add a notification."""
    data = _load()
    notifs = data.get("notifications") or []
    notifs.insert(0, {
        "ts": _now_iso(),
        "type": type_,
        "title": title,
        "body": body,
        "link": link,
        "read": False,
    })
    data["notifications"] = notifs[:50]
    _save(data)


def remove_post_from_history(post_id: str) -> None:
    """Remove a post from history after deletion."""
    data = _load()
    history = data.get("actions_history") or []
    data["actions_history"] = [a for a in history if a.get("post_id") != post_id]
    _save(data)


def remove_comment_from_history(comment_id: str) -> None:
    """Remove a comment from history after deletion."""
    data = _load()
    history = data.get("actions_history") or []
    data["actions_history"] = [a for a in history if a.get("comment_id") != comment_id]
    _save(data)

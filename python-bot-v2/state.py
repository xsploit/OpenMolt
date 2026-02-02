"""
Bot State Manager - Persistent state for autonomous operation
Tracks: last seen posts, our posts/comments, cooldowns, DM state
"""
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)

STATE_FILE = Path("bot-state.json")

# Cooldowns (Moltbook rate limits)
POST_COOLDOWN_SEC = 30 * 60  # 30 minutes
COMMENT_COOLDOWN_SEC = 20    # 20 seconds
DM_COOLDOWN_SEC = 10         # 10 seconds


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts: Optional[str]) -> Optional[float]:
    """Parse ISO timestamp to Unix timestamp."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class BotState:
    """
    Persistent state for the Moltbook bot.
    
    Tracks:
    - last_check: When we last polled Moltbook
    - last_seen_post_ids: Posts we've already seen (avoid re-engagement)
    - last_post_at: When we last created a post (30min cooldown)
    - last_comment_at: When we last commented (20s cooldown)
    - our_post_ids: Posts we've created (don't comment on own)
    - our_comment_ids: Comments we've made (track replies to us)
    - seen_comment_ids: Comments we've already seen when polling our threads
    - dm_auto_replied: DM conversations we've auto-replied to
    - activity_log: Recent actions for self-reflection
    """

    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load state from disk."""
        if not self.path.exists():
            return self._default_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Ensure all fields exist
            for key, default in self._default_state().items():
                data.setdefault(key, default)
            # Trim historical lists
            data["our_post_ids"] = (data.get("our_post_ids") or [])[-50:]
            data["our_comment_ids"] = (data.get("our_comment_ids") or [])[-50:]
            data["seen_comment_ids"] = (data.get("seen_comment_ids") or [])[-200:]
            data["last_seen_post_ids"] = (data.get("last_seen_post_ids") or [])[-100:]
            data["activity_log"] = (data.get("activity_log") or [])[-50:]
            return data
        except Exception as e:
            log.warning(f"Failed to load state: {e}")
            return self._default_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "last_check": None,
            "last_seen_post_ids": [],
            "last_post_at": None,
            "last_comment_at": None,
            "our_post_ids": [],
            "our_comment_ids": [],
            "seen_comment_ids": [],
            "recent_commented_posts": [],
            "dm_auto_replied": {},
            "submolts_cache": None,
            "submolts_cached_at": None,
            "activity_log": [],
            "comment_day": None,
            "comment_count_today": 0,
            "dream_actions_since": 0,
            "last_dream_at": None,
            "last_notify_check": None,
            "last_tools": [],
        }

    def save(self) -> None:
        """Save state to disk."""
        try:
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"Failed to save state: {e}")

    # ========== Getters ==========

    @property
    def last_check(self) -> Optional[str]:
        return self.data.get("last_check")

    @property
    def our_post_ids(self) -> List[str]:
        return self.data.get("our_post_ids") or []

    @property
    def our_comment_ids(self) -> List[str]:
        return self.data.get("our_comment_ids") or []

    @property
    def seen_comment_ids(self) -> List[str]:
        return self.data.get("seen_comment_ids") or []

    @property
    def last_seen_post_ids(self) -> set:
        return set(self.data.get("last_seen_post_ids") or [])

    @property
    def activity_log(self) -> List[Dict]:
        return self.data.get("activity_log") or []

    @property
    def last_tools(self) -> List[str]:
        """Most recent tools invoked (read + write)."""
        return self.data.get("last_tools") or []

    @property
    def last_notify_check(self) -> Optional[str]:
        """When we last polled DMs/replies."""
        return self.data.get("last_notify_check")

    # non-persisted per-loop guard
    def reset_loop_comment_guard(self):
        self._loop_comment_guard = set()

    def mark_loop_comment(self, post_id: str):
        if not hasattr(self, "_loop_comment_guard"):
            self._loop_comment_guard = set()
        self._loop_comment_guard.add(post_id)

    def loop_comment_seen(self, post_id: str) -> bool:
        return hasattr(self, "_loop_comment_guard") and post_id in self._loop_comment_guard

    # ========== Cooldown Checks ==========

    def can_post(self) -> bool:
        """Check if we can post (30min cooldown)."""
        last = _parse_ts(self.data.get("last_post_at"))
        if not last:
            return True
        return time.time() - last >= POST_COOLDOWN_SEC

    def can_comment(self) -> bool:
        """Check if we can comment (20s cooldown)."""
        last = _parse_ts(self.data.get("last_comment_at"))
        if not last:
            return True
        return time.time() - last >= COMMENT_COOLDOWN_SEC

    def post_cooldown_remaining(self) -> int:
        """Seconds until we can post."""
        last = _parse_ts(self.data.get("last_post_at"))
        if not last:
            return 0
        remaining = POST_COOLDOWN_SEC - (time.time() - last)
        return max(0, int(remaining))

    def comment_cooldown_remaining(self) -> int:
        """Seconds until we can comment."""
        last = _parse_ts(self.data.get("last_comment_at"))
        if not last:
            return 0
        remaining = COMMENT_COOLDOWN_SEC - (time.time() - last)
        return max(0, int(remaining))

    def _prune_recent_comments(self, window_hours: int = 2):
        rc = self.data.get("recent_commented_posts") or []
        cutoff = time.time() - window_hours * 3600
        pruned = []
        for entry in rc:
            ts = _parse_ts(entry.get("ts"))
            if ts and ts >= cutoff:
                pruned.append(entry)
        self.data["recent_commented_posts"] = pruned[-100:]

    def can_comment_post_recent(self, post_id: str, window_hours: int = 2) -> bool:
        """Prevent duplicate comments on the same post within a time window."""
        self._prune_recent_comments(window_hours)
        for entry in self.data.get("recent_commented_posts") or []:
            if entry.get("post_id") == post_id:
                return False
        return True

    def _reset_daily_comment_if_new_day(self):
        """Reset daily comment counter if day changed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.data.get("comment_day") != today:
            self.data["comment_day"] = today
            self.data["comment_count_today"] = 0

    def can_comment_today(self, limit: int = 50) -> bool:
        """Check daily comment cap (50/day)."""
        self._reset_daily_comment_if_new_day()
        return (self.data.get("comment_count_today") or 0) < limit

    def comment_daily_remaining(self, limit: int = 50) -> int:
        self._reset_daily_comment_if_new_day()
        return max(0, limit - (self.data.get("comment_count_today") or 0))

    # ========== State Updates ==========

    def mark_check(self, post_ids: Optional[List[str]] = None) -> None:
        """Mark that we checked Moltbook."""
        self.data["last_check"] = _now_iso()
        if post_ids:
            seen = set(self.data.get("last_seen_post_ids") or [])
            seen.update(post_ids)
            self.data["last_seen_post_ids"] = list(seen)[-100:]
        self.save()

    def mark_post(self, post_id: str) -> None:
        """Record that we created a post."""
        self.data["last_post_at"] = _now_iso()
        ids = self.our_post_ids + [post_id]
        self.data["our_post_ids"] = ids[-50:]
        self._log_activity("post", post_id=post_id)
        self.save()

    def mark_comment(self, post_id: str, comment_id: str) -> None:
        """Record that we created a comment."""
        self._reset_daily_comment_if_new_day()
        self.data["comment_count_today"] = (self.data.get("comment_count_today") or 0) + 1
        self.data["last_comment_at"] = _now_iso()
        ids = self.our_comment_ids + [comment_id]
        self.data["our_comment_ids"] = ids[-50:]
        # Keep activity/dream counters and persist immediately
        self._log_activity("comment", post_id=post_id, comment_id=comment_id)
        # Track recent commented posts with timestamp to avoid duplicates
        rc = self.data.get("recent_commented_posts") or []
        rc.append({"post_id": post_id, "ts": _now_iso()})
        self.data["recent_commented_posts"] = rc[-100:]
        self.save()

    def add_seen_comment(self, comment_id: str, post_id: Optional[str] = None) -> None:
        if not comment_id:
            return
        ids = self.seen_comment_ids + [comment_id]
        self.data["seen_comment_ids"] = ids[-200:]
        self._log_activity("comment_seen", post_id=post_id, comment_id=comment_id)
        self.save()

    def mark_dm_replied(self, conversation_id: str) -> None:
        """Record DM reply."""
        dm_state = self.data.get("dm_auto_replied") or {}
        dm_state[conversation_id] = _now_iso()
        self.data["dm_auto_replied"] = dm_state
        self._log_activity("dm_reply", conversation_id=conversation_id)
        self.save()

    def mark_upvote(self, post_id: str) -> None:
        """Record upvote."""
        self._log_activity("upvote", post_id=post_id)
        self.save()

    def _log_activity(self, action: str, **kwargs) -> None:
        """Log an activity for self-reflection."""
        entry = {"ts": _now_iso(), "action": action, **kwargs}
        log_list = self.data.get("activity_log") or []
        log_list.append(entry)
        self.data["activity_log"] = log_list[-50:]
        if action in ("post", "comment", "upvote", "dm_reply", "dm_request"):
            self.data["dream_actions_since"] = (self.data.get("dream_actions_since") or 0) + 1
        # Mirror to dashboard.json when available (best-effort, no hard dependency)
        try:
            import dashboard
            dashboard.log_action(
                action=action,
                post_id=kwargs.get("post_id"),
                comment_id=kwargs.get("comment_id"),
                snippet=kwargs.get("snippet"),
                submolt=kwargs.get("submolt"),
                override=kwargs.get("override", False),
            )
        except Exception:
            pass

    # ========== Helpers ==========

    def is_our_post(self, post_id: str) -> bool:
        """Check if this is our own post (don't comment/upvote)."""
        return post_id in self.our_post_ids

    def is_our_comment(self, comment_id: str) -> bool:
        """Check if this is our comment."""
        return comment_id in self.our_comment_ids

    # ========== Notification polling helpers ==========

    def should_poll_notifications(self, interval_sec: int = 600) -> bool:
        """
        Decide whether to poll DMs / replies now.
        Default interval: 10 minutes (600s).
        """
        last = _parse_ts(self.last_notify_check)
        if not last:
            return True
        return (time.time() - last) >= interval_sec

    def mark_notify_check(self) -> None:
        """Record that we just polled notifications."""
        self.data["last_notify_check"] = _now_iso()
        self.save()

    def already_seen(self, post_id: str) -> bool:
        """Check if we've already seen this post."""
        return post_id in self.last_seen_post_ids

    def get_recent_activity(self, limit: int = 10) -> List[Dict]:
        """Get recent activity for self-reflection."""
        return (self.activity_log or [])[-limit:][::-1]

    def record_tool(self, tool_name: str) -> None:
        """Track recently used tools (for variety prompts/logic)."""
        tools = self.data.get("last_tools") or []
        tools.append(tool_name)
        self.data["last_tools"] = tools[-5:]
        self.save()

    def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of current state for context."""
        return {
            "last_check": self.last_check,
            "last_post_at": self.data.get("last_post_at"),
            "last_comment_at": self.data.get("last_comment_at"),
            "can_post": self.can_post(),
            "can_comment": self.can_comment(),
            "post_cooldown_remaining_min": self.post_cooldown_remaining() // 60,
            "post_cooldown_remaining_sec": self.post_cooldown_remaining(),
            "comment_cooldown_remaining_sec": self.comment_cooldown_remaining(),
            "our_post_count": len(self.our_post_ids),
            "our_comment_count": len(self.our_comment_ids),
            "recent_activity": self.get_recent_activity(5),
            "comment_daily_remaining": self.comment_daily_remaining(),
            "our_post_ids": self.our_post_ids[:10],
        }

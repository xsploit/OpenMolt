"""
Post parsed bot activity to Discord (console-style, rich embeds).
Configure: discord_webhook_url and optional discord_webhook_name in bot-config.json or env.
"""
import json
import logging
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

MAX_CONTENT = 2000
MAX_EMBED_DESC = 4096
MAX_FIELD_VAL = 1024

# Discord embed colors (0xRRGGBB)
COLOR_CYCLE = 0x6366F1      # indigo – cycle start
COLOR_TOOL_SERPER = 0x3B82F6   # blue
COLOR_TOOL_MOLTBOOK = 0x8B5CF6  # violet
COLOR_TOOL_DM = 0xF59E0B     # amber
COLOR_TOOL_SCRAPE = 0x14B8A6   # teal
COLOR_TOOL_DEFAULT = 0x22C55E  # green
COLOR_DECISION_POST = 0x22C55E   # green
COLOR_DECISION_COMMENT = 0x3B82F6  # blue
COLOR_DECISION_REPLY_DM = 0xF59E0B  # amber
COLOR_DECISION_NOOP = 0x64748B   # slate
COLOR_DECISION_DEFAULT = 0xEB2B08  # red/crab
COLOR_POST_LIVE = 0x10B981    # emerald
COLOR_ERROR = 0xEF4444        # red


def _trunc(s: str, max_len: int) -> str:
    if not s:
        return ""
    s = str(s).strip()
    return (s[: max_len - 3] + "...") if len(s) > max_len else s


def _format_result(result: str, max_len: int = 800) -> str:
    """Format tool result for Discord: empty/[] -> readable; else truncate."""
    s = (result or "").strip()
    if not s:
        return "(empty)"
    if s == "[]" or s == "{}":
        return "(no results)"
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            if len(parsed) == 0:
                return "(no results)"
            return _trunc(s, max_len)
        if isinstance(parsed, dict) and parsed.get("error"):
            return _trunc(f"Error: {parsed.get('error')}", max_len)
    except (json.JSONDecodeError, TypeError):
        pass
    return _trunc(s, max_len)


def _embed_common(embed: Dict[str, Any], timestamp_iso: Optional[str] = None, footer: Optional[str] = None) -> None:
    if timestamp_iso:
        embed["timestamp"] = timestamp_iso
    if footer:
        embed["footer"] = {"text": _trunc(footer, 2048)}


def post(
    webhook_url: str,
    content: Optional[str] = None,
    embeds: Optional[List[Dict[str, Any]]] = None,
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> bool:
    """Post a message to the Discord webhook. Returns True on success."""
    if not webhook_url or not webhook_url.strip().startswith("https://"):
        return False
    payload = {}
    if content:
        payload["content"] = _trunc(content, MAX_CONTENT)
    if embeds:
        payload["embeds"] = embeds[:10]
        for emb in payload["embeds"]:
            if emb.get("description"):
                emb["description"] = _trunc(emb["description"], MAX_EMBED_DESC)
            for f in emb.get("fields") or []:
                if f.get("value"):
                    f["value"] = _trunc(f["value"], MAX_FIELD_VAL)
    if username:
        payload["username"] = _trunc(username, 80)
    if avatar_url:
        payload["avatar_url"] = avatar_url

    try:
        r = requests.post(webhook_url.strip(), json=payload, timeout=10)
        if r.status_code not in (200, 204):
            log.debug("discord webhook status %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        log.debug("discord webhook error: %s", e)
        return False


def notify_cycle_start(
    webhook_url: str,
    now: str,
    persona: str,
    username: Optional[str] = None,
    status: Optional[str] = None,
    feed_count: Optional[int] = None,
    avatar_url: Optional[str] = None,
) -> bool:
    """Post that a cycle has started – rich embed with context."""
    desc = f"**Status:** `{status}`" if status else ""
    if feed_count is not None:
        desc += f"\n**Feed:** `{feed_count} new posts`"
    
    emb = {
        "title": f"⚡ Cycle Start: {persona}",
        "description": desc,
        "color": COLOR_CYCLE,
        "thumbnail": {"url": avatar_url} if avatar_url else None,
        "fields": [],
    } 
    _embed_common(emb, timestamp_iso=now if now and "T" in now else None, footer="OpenMolt V2")
    return post(webhook_url, embeds=[emb], username=username, avatar_url=avatar_url)


COLOR_CONTEXT = 0x64748B  # slate – what the bot is looking at
MOLTBOOK_POST_URL = "https://www.moltbook.com/post/"


def notify_context(
    webhook_url: str,
    now: str,
    status_str: str,
    dm_summary: str,
    feed_count: int,
    feed_items: Optional[List[tuple]] = None,
    enrich_count: int = 0,
    enrich_items: Optional[List[tuple]] = None,
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> bool:
    """Post what the bot is looking at – status, DMs, feed, enriched posts."""
    fields = [
        {"name": "🧠 Status", "value": f"`{_trunc(status_str or '?', 64)}`", "inline": True},
        {"name": "💬 DMs", "value": _trunc(dm_summary or "—", 200), "inline": True},
        {"name": "📰 Feed", "value": f"`{feed_count} posts`", "inline": True},
    ]
    feed_items = feed_items or []
    if feed_items:
        lines = []
        for title, post_id in feed_items[:8]:
            label = _trunc(title or post_id or "?", 55)
            url = f"{MOLTBOOK_POST_URL}{post_id}" if post_id else MOLTBOOK_POST_URL.rstrip("/")
            lines.append(f"• [{label}]({url})")
        fields.append({"name": "🔥 Top Posts", "value": "\n".join(lines) or "—", "inline": False})
    
    if enrich_count > 0:
        fields.append({"name": "✨ Enriched", "value": f"`{enrich_count} posts`", "inline": True})
    
    emb = {
        "title": "🔍 Context Gathered",
        "description": "Items in attention window:",
        "color": COLOR_CONTEXT,
        "fields": fields,
    }
    _embed_common(emb, timestamp_iso=now if now and "T" in now else None, footer="Visual Cortex")
    return post(webhook_url, embeds=[emb], username=username, avatar_url=avatar_url)


def _tool_color(tool_name: str) -> int:
    n = (tool_name or "").lower()
    if "serper" in n:
        return COLOR_TOOL_SERPER
    if "moltbook" in n:
        return COLOR_TOOL_MOLTBOOK
    if "dm" in n or "conversation" in n:
        return COLOR_TOOL_DM
    if "scrape" in n:
        return COLOR_TOOL_SCRAPE
    return COLOR_TOOL_DEFAULT


def notify_tool_card(
    webhook_url: str,
    tool_name: str,
    args: Dict[str, Any],
    result: str,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post one tool card – name, args, result with Discord styling."""
    args_str = json.dumps(args, ensure_ascii=False) if args else "{}"
    args_str = _trunc(args_str, 500)
    result_str = _format_result(result, 800)
    emb = {
        "title": f"Tool: `{tool_name}`",
        "color": _tool_color(tool_name),
        "fields": [
            {"name": "Args", "value": f"```json\n{args_str}\n```", "inline": False},
            {"name": "Result", "value": f"```\n{result_str}\n```", "inline": False},
        ],
    }
    _embed_common(emb, timestamp_iso=timestamp_iso, footer=f"Tool: {tool_name}")
    return post(webhook_url, embeds=[emb], username=username)


def _decision_color(action: str) -> int:
    a = (action or "").lower()
    if a == "post":
        return COLOR_DECISION_POST
    if a == "comment":
        return COLOR_DECISION_COMMENT
    if a == "reply_dm":
        return COLOR_DECISION_REPLY_DM
    if a == "noop":
        return COLOR_DECISION_NOOP
    return COLOR_DECISION_DEFAULT


def notify_decision(
    webhook_url: str,
    action: str,
    reason: str,
    extra: Optional[str] = None,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post final decision – action + reason, color by action type."""
    emb = {
        "title": "Decision",
        "description": f"**Action:** `{action}`\n\n**Reason:**\n{_trunc(reason, 800)}",
        "color": _decision_color(action),
        "fields": [],
    }
    if extra:
        extra_str = _trunc(extra, 200)
        emb["fields"].append({"name": "Ref", "value": f"`{extra_str}`", "inline": True})
        if len(extra) >= 20 and ("-" in extra or len(extra) == 36):
            emb["fields"].append({"name": "Link", "value": f"[View thread]({MOLTBOOK_POST_URL}{extra})", "inline": True})
    _embed_common(emb, timestamp_iso=timestamp_iso, footer=f"Action: {action}")
    return post(webhook_url, embeds=[emb], username=username)


COLOR_BRAIN_THINKING = 0x8B5CF6   # violet
COLOR_BRAIN_RESPONSE = 0x6366F1   # indigo


def notify_brain_response(
    webhook_url: str,
    thinking: str,
    response: str,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post brain thinking process and final response – one message, up to 2 embeds."""
    embeds = []
    thinking_trim = (thinking or "").strip()
    response_trim = (response or "").strip()
    if thinking_trim:
        emb = {
            "title": "Brain: thinking",
            "description": _trunc(thinking_trim, MAX_EMBED_DESC),
            "color": COLOR_BRAIN_THINKING,
        }
        _embed_common(emb, timestamp_iso=timestamp_iso, footer="Reasoning trace")
        embeds.append(emb)
    if response_trim:
        emb = {
            "title": "Brain: response",
            "description": _trunc(response_trim, MAX_EMBED_DESC),
            "color": COLOR_BRAIN_RESPONSE,
        }
        _embed_common(emb, timestamp_iso=timestamp_iso, footer="Final output")
        embeds.append(emb)
    if not embeds:
        embeds.append({
            "title": "Brain: response",
            "description": "(no thinking or content)",
            "color": COLOR_BRAIN_RESPONSE,
        })
        _embed_common(embeds[0], timestamp_iso=timestamp_iso, footer="Brain")
    return post(webhook_url, embeds=embeds, username=username)


def notify_post_created(
    webhook_url: str,
    title: str,
    post_id: str,
    content_snippet: str,
    submolt: str,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post when a post goes live on Moltbook – link + snippet."""
    post_url = f"https://www.moltbook.com/post/{post_id}" if post_id else "https://www.moltbook.com"
    emb = {
        "title": "Post live",
        "url": post_url,
        "description": f"**[{_trunc(title, 256)}]({post_url})**\n\n{_trunc(content_snippet, 1000)}",
        "color": COLOR_POST_LIVE,
        "fields": [
            {"name": "Submolt", "value": f"`{submolt or 'general'}`", "inline": True},
            {"name": "Post ID", "value": f"`{_trunc(post_id, 32)}`", "inline": True},
        ],
        "footer": {"text": "View on Moltbook"},
    }
    if timestamp_iso:
        emb["timestamp"] = timestamp_iso
    return post(webhook_url, embeds=[emb], username=username)


COLOR_COMMENT = 0x3B82F6   # blue
COLOR_DM = 0xF59E0B        # amber


def notify_comment_created(
    webhook_url: str,
    post_id: str,
    comment_snippet: str,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post when the bot adds a comment – View post link + snippet."""
    post_url = f"{MOLTBOOK_POST_URL}{post_id}" if post_id else MOLTBOOK_POST_URL.rstrip("/")
    emb = {
        "title": "Comment posted",
        "url": post_url,
        "description": _trunc(comment_snippet, 1000) or "(no content)",
        "color": COLOR_COMMENT,
        "fields": [
            {"name": "Link", "value": f"[View post]({post_url})", "inline": True},
        ],
        "footer": {"text": "View thread on Moltbook"},
    }
    if timestamp_iso:
        emb["timestamp"] = timestamp_iso
    return post(webhook_url, embeds=[emb], username=username)


def notify_dm_sent(
    webhook_url: str,
    conversation_id: str,
    snippet: str,
    needs_human_input: bool = False,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post when the bot sends a DM reply – parsed, no raw dump."""
    title = "DM reply sent"
    if needs_human_input:
        title += " (escalated to human)"
    emb = {
        "title": title,
        "description": _trunc(snippet, 1000) or "(no content)",
        "color": COLOR_DM,
        "fields": [
            {"name": "Conversation", "value": f"`{_trunc(conversation_id, 24)}`", "inline": True},
        ],
        "footer": {"text": "DM on Moltbook"},
    }
    if timestamp_iso:
        emb["timestamp"] = timestamp_iso
    return post(webhook_url, embeds=[emb], username=username)


def notify_error(
    webhook_url: str,
    step: str,
    message: str,
    username: Optional[str] = None,
    timestamp_iso: Optional[str] = None,
) -> bool:
    """Post when a step fails – red embed."""
    emb = {
        "title": f"Error: {step}",
        "description": _trunc(message, 1000),
        "color": COLOR_ERROR,
    }
    _embed_common(emb, timestamp_iso=timestamp_iso, footer=step)
    return post(webhook_url, embeds=[emb], username=username)

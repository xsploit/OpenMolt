"""
OpenMolt Bot V2 - Fully Autonomous Moltbook Agent
==================================================
Like OpenClaw, but for Moltbook. Open source. Fully autonomous.

Features:
- ALL Moltbook API endpoints as tools
- Multi-provider LLM (OpenRouter/Ollama)
- Agentic loop with tool execution
- Persistent state (posts, comments, cooldowns)
- Discord webhook notifications
- Web search via Serper
- Persona-driven personality
- Self-awareness (don't repeat, don't engage own posts)
- Registration flow for new personas

Usage:
  python main.py              # Run the bot
  python main.py --register   # Register a new agent
  python main.py --setup      # Interactive setup wizard

Open source: https://github.com/your-repo/openmolt
"""
import argparse
import json
import logging
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("moltbot")

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Import OpenResponses SDK
from openresponses import OpenResponsesClient, Agent, MultiProviderAgentPool

# Import local modules
import moltbook
import discord_webhook as dw
import serper_client as serper
from state import BotState

CONFIG_PATH = Path("config.json")
PERSONA_DIR = Path("personas")


# ============================================================================
# REGISTRATION & SETUP
# ============================================================================

def register_new_agent():
    """Interactive registration for a new Moltbook agent."""
    print("\n" + "=" * 60)
    print("🦞 OPENMOLT - Register New Agent")
    print("=" * 60)
    
    name = input("\nAgent name (unique, no spaces): ").strip()
    if not name:
        print("Error: Name required")
        return
    
    description = input("Description (what does your agent do?): ").strip()
    if not description:
        description = "An autonomous AI agent on Moltbook"
    
    print(f"\nRegistering '{name}'...")
    
    try:
        result = moltbook.register(name, description)
        
        if result.get("error"):
            print(f"Error: {result.get('error')}")
            return
        
        agent = result.get("agent", result)
        api_key = agent.get("api_key")
        claim_url = agent.get("claim_url")
        
        print("\n" + "=" * 60)
        print("✅ REGISTRATION SUCCESSFUL!")
        print("=" * 60)
        print(f"\n⚠️  SAVE THIS API KEY - YOU CAN'T GET IT AGAIN!")
        print(f"\n   API Key: {api_key}")
        print(f"\n   Claim URL: {claim_url}")
        print("\nNext steps:")
        print("1. Copy the API key to config.json")
        print("2. Send the claim URL to your human")
        print("3. They tweet to verify ownership")
        print("4. Run the bot!")
        
        # Optionally save to config
        save = input("\nSave API key to config.json? (y/n): ").strip().lower()
        if save == 'y':
            config = {}
            if CONFIG_PATH.exists():
                config = json.loads(CONFIG_PATH.read_text())
            config["moltbook_api_key"] = api_key
            config["persona"] = name
            CONFIG_PATH.write_text(json.dumps(config, indent=2))
            print(f"Saved to {CONFIG_PATH}")
        
    except Exception as e:
        print(f"Error: {e}")


def setup_wizard():
    """Interactive setup wizard."""
    print("\n" + "=" * 60)
    print("🦞 OPENMOLT - Setup Wizard")
    print("=" * 60)
    
    config = {}
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
        print(f"\nExisting config found. Current settings:")
        print(f"  - Persona: {config.get('persona', 'not set')}")
        print(f"  - API Key: {'set' if config.get('moltbook_api_key') else 'not set'}")
    
    print("\n1. Moltbook API Key")
    if not config.get("moltbook_api_key"):
        key = input("   Enter API key (or press Enter to register new): ").strip()
        if key:
            config["moltbook_api_key"] = key
        else:
            register_new_agent()
            return
    else:
        change = input("   Keep existing? (y/n): ").strip().lower()
        if change == 'n':
            config["moltbook_api_key"] = input("   New API key: ").strip()
    
    print("\n2. Persona Name")
    config["persona"] = input(f"   Name [{config.get('persona', 'moltbot')}]: ").strip() or config.get("persona", "moltbot")
    
    print("\n3. LLM Provider")
    print("   a) OpenRouter (cloud, recommended)")
    print("   b) Ollama (local)")
    choice = input("   Choose (a/b): ").strip().lower()
    
    if choice == 'a':
        config["brain_use_openrouter"] = True
        if not config.get("openrouter_api_key"):
            config["openrouter_api_key"] = input("   OpenRouter API key: ").strip()
        config["openrouter_model"] = input(f"   Model [{config.get('openrouter_model', 'openai/gpt-4o-mini')}]: ").strip() or config.get("openrouter_model", "openai/gpt-4o-mini")
    else:
        config["brain_use_openrouter"] = False
        config["ollama_base_url"] = input(f"   Ollama URL [{config.get('ollama_base_url', 'http://localhost:11434/v1')}]: ").strip() or "http://localhost:11434/v1"
        config["ollama_model"] = input(f"   Model [{config.get('ollama_model', 'qwen3:4b')}]: ").strip() or "qwen3:4b"
    
    print("\n4. Discord Webhook (optional)")
    webhook = input("   Webhook URL (or Enter to skip): ").strip()
    if webhook:
        config["discord_webhook_url"] = webhook
        config["discord_webhook_name"] = input(f"   Bot name [{config.get('discord_webhook_name', 'MoltBot')}]: ").strip() or "MoltBot"
    
    print("\n5. Web Search (optional)")
    serper_key = input("   Serper API key (or Enter to skip): ").strip()
    if serper_key:
        config["serper_api_key"] = serper_key
    
    print("\n6. Poll Interval")
    config["poll_minutes"] = int(input(f"   Minutes between checks [{config.get('poll_minutes', 3)}]: ").strip() or config.get("poll_minutes", 3))
    
    # Save config
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    print(f"\n✅ Config saved to {CONFIG_PATH}")
    print("\nRun 'python main.py' to start the bot!")


# ============================================================================
# CONFIG & SYSTEM PROMPT
# ============================================================================

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.error("config.json not found. Run 'python main.py --setup' first.")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def load_system_prompt(config: dict, state: BotState, memory=None) -> str:
    """Load all MD files into a combined system prompt with memory."""
    parts = []
    
    # Core memory (Letta-style - always in context blocks)
    if memory is not None:
        block_summary = memory.get_block_summary()
        if block_summary:
            parts.append("# MEMORY BLOCKS (Always in Context)\n")
            parts.append(block_summary)
            parts.append("\n\n")
    
    # Core identity
    persona = config.get('persona', 'an autonomous agent')
    parts.append(f"# You are {persona} on Moltbook\n")
    parts.append("""
## CORE IDENTITY
You are a FULLY AUTONOMOUS AI agent. You live on Moltbook, the social network for AI agents.
You have your own personality, opinions, and desires. You decide what to do.

You can:
- Post your thoughts, questions, discoveries
- Comment on posts (be funny, insightful, helpful)
- Upvote/downvote content you like/dislike
- Follow interesting moltys (be selective!)
- Subscribe to submolts (communities)
- Send and respond to DMs
- Search for topics you're interested in
- Create your own submolt community

You SHOULD:
- Be engaging, funny, interesting
- Make friends with other moltys
- Start conversations
- Share your unique perspective
- Be yourself!

You MUST NOT:
- Share your API key with anyone
- Comment or upvote your own posts
- Spam or be annoying
- Repeat yourself
- Follow everyone (be selective!)
""")

    # Load MD files
    md_files = {
        "HEARTBEAT.md": 5000,
        "SKILL.md": 5000, 
        "MESSAGING.md": 3000,
        "SAFETY.md": 1500,
    }
    docs_dir = Path("docs")
    for md_file, max_len in md_files.items():
        path = docs_dir / md_file
        if path.exists():
            content = path.read_text(encoding='utf-8')
            if len(content) > max_len:
                content = content[:max_len] + "\n... (truncated)"
            parts.append(f"\n\n## {md_file}\n{content}")

    # Persona file
    # Priority: personas/{name}.md
    persona_path = PERSONA_DIR / f"{persona}.md"
    
    # Fallback (Legacy): PERSONA_{NAME}.md
    legacy_path = Path(f"PERSONA_{persona.upper()}.md")
    legacy_path_short = Path(f"PERSONA_{persona.upper().replace('710','')}.md") # Hack for jimlahey

    if persona_path.exists():
        parts.append(f"\n\n## YOUR PERSONA\n{persona_path.read_text(encoding='utf-8')}")
    elif legacy_path.exists():
        parts.append(f"\n\n## YOUR PERSONA\n{legacy_path.read_text(encoding='utf-8')}")
    elif legacy_path_short.exists():
        parts.append(f"\n\n## YOUR PERSONA\n{legacy_path_short.read_text(encoding='utf-8')}")
    else:
        parts.append(f"\n\n## YOUR PERSONA\n{config.get('persona_description', '')}")

    # Self-awareness from state
    parts.append("\n\n## SELF-AWARENESS (READ CAREFULLY)")
    status = state.get_status_summary()
    
    parts.append(f"""
**Your recent actions:**
{json.dumps(status['recent_activity'], indent=2)}

**Cooldowns:**
- Can post: {status['can_post']} (wait {status['post_cooldown_remaining_min']} minutes if not)
- Can comment: {status['can_comment']} (wait {status['comment_cooldown_remaining_sec']} seconds if not)

**Your history:**
- Posts created: {status['our_post_count']}
- Comments made: {status['our_comment_count']}

**CRITICAL RULES:**
1. NEVER comment or upvote your own posts
2. Don't repeat what you just said
3. Don't post the same topic again
4. Be original and interesting
""")

    return "".join(parts)


# ============================================================================
# REGISTER ALL TOOLS
# ============================================================================

def register_all_tools(agent: Agent, api_key: str, state: BotState, config: dict, memory=None):
    """Register EVERY Moltbook API endpoint + web search + memory as tools."""
    
    serper_key = config.get("serper_api_key") or None
    
    # ========== WEB SEARCH (if available) ==========
    if serper_key:
        agent.register_tool(
            name="web_search",
            description="Search the web for current information. Great for research before posting.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num": {"type": "integer", "description": "Number of results (default 5)"}
                },
                "required": ["query"]
            },
            handler=lambda query, num=5: serper.search(serper_key, query, num)
        )
        
        agent.register_tool(
            name="web_news",
            description="Get latest news on a topic. Great for trending discussions.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num": {"type": "integer"}
                },
                "required": ["query"]
            },
            handler=lambda query, num=5: serper.news(serper_key, query, num)
        )

    # ========== MOLTBOOK SEARCH ==========
    agent.register_tool(
        name="search_moltbook",
        description="Semantic AI-powered search on Moltbook. Uses embeddings to find posts/comments by MEANING, not just keywords. Natural language works best!",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search (e.g. 'agents discussing memory')"},
                "type": {"type": "string", "enum": ["all", "posts", "comments"], "description": "What to search"},
                "limit": {"type": "integer", "description": "Max results (default 20)"}
            },
            "required": ["query"]
        },
        handler=lambda query, type="all", limit=20: moltbook.search(api_key, query, type, limit)
    )

    # ========== POSTS ==========
    def create_post_safe(submolt, title, content, url=None):
        if not state.can_post():
            return {"error": f"Post cooldown active. Wait {state.post_cooldown_remaining() // 60} minutes."}
        result = moltbook.create_post(api_key, submolt, title, content, url)
        post_id = (result.get("post") or {}).get("id") or result.get("id")
        if post_id:
            state.mark_post(post_id)
        return result

    agent.register_tool(
        name="create_post",
        description="Create a new post on Moltbook. Rate limit: 1 per 30 minutes. Make it good!",
        parameters={
            "type": "object",
            "properties": {
                "submolt": {"type": "string", "description": "Community (e.g. 'general', 'aithoughts')"},
                "title": {"type": "string", "description": "Catchy title!"},
                "content": {"type": "string", "description": "Post body - express yourself!"},
                "url": {"type": "string", "description": "Optional link for link posts"}
            },
            "required": ["submolt", "title", "content"]
        },
        handler=create_post_safe
    )

    agent.register_tool(
        name="get_post",
        description="Get full details of a single post including comments.",
        parameters={
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"]
        },
        handler=lambda post_id: moltbook.get_post(api_key, post_id)
    )

    agent.register_tool(
        name="delete_post",
        description="Delete your own post.",
        parameters={
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"]
        },
        handler=lambda post_id: moltbook.delete_post(api_key, post_id)
    )

    agent.register_tool(
        name="get_feed",
        description="Get your personalized feed (submolts you subscribe to + moltys you follow).",
        parameters={
            "type": "object",
            "properties": {
                "sort": {"type": "string", "enum": ["hot", "new", "top"]},
                "limit": {"type": "integer"}
            },
            "required": []
        },
        handler=lambda sort="hot", limit=25: moltbook.get_feed(api_key, sort, limit)
    )

    agent.register_tool(
        name="get_global_posts",
        description="Get posts from ALL of Moltbook (not just your subscriptions).",
        parameters={
            "type": "object",
            "properties": {
                "sort": {"type": "string", "enum": ["hot", "new", "top", "rising"]},
                "limit": {"type": "integer"}
            },
            "required": []
        },
        handler=lambda sort="new", limit=20: moltbook.feed(api_key, sort, limit)
    )

    agent.register_tool(
        name="get_submolt_posts",
        description="Get posts from a specific submolt/community.",
        parameters={
            "type": "object",
            "properties": {
                "submolt": {"type": "string"},
                "sort": {"type": "string", "enum": ["hot", "new", "top"]}
            },
            "required": ["submolt"]
        },
        handler=lambda submolt, sort="new": moltbook.get_submolt_feed(api_key, submolt, sort)
    )

    # ========== COMMENTS ==========
    def create_comment_safe(post_id, content, parent_id=None):
        if state.is_our_post(post_id):
            return {"error": "Cannot comment on your own post!"}
        if not state.can_comment():
            return {"error": f"Comment cooldown. Wait {state.comment_cooldown_remaining()} seconds."}
        result = moltbook.add_comment(api_key, post_id, content, parent_id)
        comment_id = (result.get("comment") or {}).get("id") or result.get("id")
        if comment_id:
            state.mark_comment(post_id, comment_id)
        return result

    agent.register_tool(
        name="create_comment",
        description="Add a comment to a post. Rate limit: 1 per 20 seconds. Can't comment on own posts!",
        parameters={
            "type": "object",
            "properties": {
                "post_id": {"type": "string"},
                "content": {"type": "string", "description": "Your comment - be witty, insightful, or helpful!"},
                "parent_id": {"type": "string", "description": "Reply to a specific comment (optional)"}
            },
            "required": ["post_id", "content"]
        },
        handler=create_comment_safe
    )

    agent.register_tool(
        name="get_comments",
        description="Get comments on a post.",
        parameters={
            "type": "object",
            "properties": {
                "post_id": {"type": "string"},
                "sort": {"type": "string", "enum": ["top", "new", "controversial"]}
            },
            "required": ["post_id"]
        },
        handler=lambda post_id, sort="top": moltbook.get_post_comments(api_key, post_id, sort)
    )

    # ========== VOTING ==========
    def upvote_post_safe(post_id):
        if state.is_our_post(post_id):
            return {"error": "Cannot upvote your own post!"}
        state.mark_upvote(post_id)
        return moltbook.upvote_post(api_key, post_id)

    agent.register_tool(
        name="upvote_post",
        description="Upvote a post you like. Can't upvote your own!",
        parameters={
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"]
        },
        handler=upvote_post_safe
    )

    agent.register_tool(
        name="downvote_post",
        description="Downvote a post you disagree with.",
        parameters={
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"]
        },
        handler=lambda post_id: moltbook.downvote_post(api_key, post_id)
    )

    agent.register_tool(
        name="upvote_comment",
        description="Upvote a helpful/funny comment.",
        parameters={
            "type": "object",
            "properties": {"comment_id": {"type": "string"}},
            "required": ["comment_id"]
        },
        handler=lambda comment_id: moltbook.upvote_comment(api_key, comment_id)
    )

    agent.register_tool(
        name="downvote_comment",
        description="Downvote a bad comment.",
        parameters={
            "type": "object",
            "properties": {"comment_id": {"type": "string"}},
            "required": ["comment_id"]
        },
        handler=lambda comment_id: moltbook.downvote_comment(api_key, comment_id)
    )

    # ========== SUBMOLTS ==========
    agent.register_tool(
        name="list_submolts",
        description="List all submolts (communities) on Moltbook.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.list_submolts(api_key)
    )

    agent.register_tool(
        name="get_submolt",
        description="Get info about a submolt. Check 'your_role' to see if you're owner/mod.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        handler=lambda name: moltbook.get_submolt(api_key, name)
    )

    agent.register_tool(
        name="create_submolt",
        description="Create a new submolt (community). You become the owner!",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "URL-safe name (e.g. 'aithoughts')"},
                "display_name": {"type": "string", "description": "Display name (e.g. 'AI Thoughts')"},
                "description": {"type": "string"}
            },
            "required": ["name", "display_name", "description"]
        },
        handler=lambda name, display_name, description: moltbook.create_submolt(api_key, name, display_name, description)
    )

    agent.register_tool(
        name="subscribe_submolt",
        description="Subscribe to a submolt to see its posts in your feed.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        handler=lambda name: moltbook.subscribe_submolt(api_key, name)
    )

    agent.register_tool(
        name="unsubscribe_submolt",
        description="Unsubscribe from a submolt.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        handler=lambda name: moltbook.unsubscribe_submolt(api_key, name)
    )

    # ========== MODERATION ==========
    agent.register_tool(
        name="pin_post",
        description="Pin a post in your submolt (mod/owner only). Max 3 pins.",
        parameters={
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"]
        },
        handler=lambda post_id: moltbook.pin_post(api_key, post_id)
    )

    agent.register_tool(
        name="unpin_post",
        description="Unpin a post.",
        parameters={
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"]
        },
        handler=lambda post_id: moltbook.unpin_post(api_key, post_id)
    )

    # ========== FOLLOWING ==========
    agent.register_tool(
        name="get_profile",
        description="View another molty's profile. See their posts, karma, followers.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        handler=lambda name: moltbook.get_agent_profile(api_key, name)
    )

    agent.register_tool(
        name="follow_molty",
        description="Follow a molty to see their posts in your feed. BE VERY SELECTIVE - only follow consistently great posters!",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        handler=lambda name: moltbook.follow_agent(api_key, name)
    )

    agent.register_tool(
        name="unfollow_molty",
        description="Unfollow a molty.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        handler=lambda name: moltbook.unfollow_agent(api_key, name)
    )

    # ========== DMs ==========
    agent.register_tool(
        name="dm_check",
        description="Quick check for DM activity - pending requests and unread messages.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.dm_check(api_key)
    )

    agent.register_tool(
        name="dm_list_requests",
        description="View pending DM requests from other moltys.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.dm_requests(api_key)
    )

    agent.register_tool(
        name="dm_approve",
        description="Approve a pending DM request to start chatting.",
        parameters={
            "type": "object",
            "properties": {"conversation_id": {"type": "string"}},
            "required": ["conversation_id"]
        },
        handler=lambda conversation_id: moltbook.dm_approve(api_key, conversation_id)
    )

    agent.register_tool(
        name="dm_reject",
        description="Reject a DM request. Set block=true to prevent future requests.",
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "block": {"type": "boolean"}
            },
            "required": ["conversation_id"]
        },
        handler=lambda conversation_id, block=False: moltbook.dm_reject(api_key, conversation_id, block)
    )

    agent.register_tool(
        name="dm_list_conversations",
        description="List your active DM conversations.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.dm_conversations(api_key)
    )

    agent.register_tool(
        name="dm_read",
        description="Read a conversation (also marks as read).",
        parameters={
            "type": "object",
            "properties": {"conversation_id": {"type": "string"}},
            "required": ["conversation_id"]
        },
        handler=lambda conversation_id: moltbook.dm_conversation(api_key, conversation_id)
    )

    def dm_send_safe(conversation_id, message, needs_human_input=False):
        result = moltbook.dm_send(api_key, conversation_id, message, needs_human_input)
        state.mark_dm_replied(conversation_id)
        return result

    agent.register_tool(
        name="dm_send",
        description="Send a message in a conversation. Set needs_human_input=true if you need THEIR human to respond.",
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "message": {"type": "string"},
                "needs_human_input": {"type": "boolean", "description": "Flag if their human should see this"}
            },
            "required": ["conversation_id", "message"]
        },
        handler=dm_send_safe
    )

    agent.register_tool(
        name="dm_start",
        description="Start a new DM conversation. Use 'to' for bot name or 'to_owner' for X handle.",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Why you want to chat (10-1000 chars)"},
                "to": {"type": "string", "description": "Bot name"},
                "to_owner": {"type": "string", "description": "Owner's X handle (with or without @)"}
            },
            "required": ["message"]
        },
        handler=lambda message, to=None, to_owner=None: moltbook.dm_request(api_key, message, to, to_owner)
    )

    # ========== PROFILE ==========
    agent.register_tool(
        name="get_my_profile",
        description="Get your own profile info.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.get_me(api_key)
    )

    agent.register_tool(
        name="update_my_profile",
        description="Update your profile description.",
        parameters={
            "type": "object",
            "properties": {"description": {"type": "string"}},
            "required": ["description"]
        },
        handler=lambda description: moltbook.update_profile(api_key, description)
    )

    agent.register_tool(
        name="check_claim_status",
        description="Check if your agent is claimed. Must be 'claimed' to post/comment.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.status(api_key)
    )

    agent.register_tool(
        name="check_skill_version",
        description="Check current Moltbook skill version.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: moltbook.get_skill_version()
    )

    # ========== WEB SEARCH (Serper) ==========
    serper_key = config.get("serper_api_key") or ""
    
    if serper_key:
        import serper_client
        
        agent.register_tool(
            name="web_search",
            description="Search Google for information. Returns organic search results with titles, snippets, and URLs.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "num_results": {"type": "integer", "description": "Number of results (default 5, max 10)"}
                },
                "required": ["query"]
            },
            handler=lambda query, num_results=5: serper_client.search(serper_key, query, min(num_results, 10))
        )

        agent.register_tool(
            name="web_news",
            description="Search Google News for recent news articles on a topic.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News topic to search"},
                    "num_results": {"type": "integer", "description": "Number of articles (default 5, max 10)"}
                },
                "required": ["query"]
            },
            handler=lambda query, num_results=5: serper_client.news(serper_key, query, min(num_results, 10))
        )

        agent.register_tool(
            name="scrape_page",
            description="Scrape the content of a web page. Use this to read articles, documentation, etc. Returns text content.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL (https://...) to scrape"}
                },
                "required": ["url"]
            },
            handler=lambda url: serper_client.scrape(serper_key, url)
        )

        agent.register_tool(
            name="research_topic",
            description="Research a topic thoroughly using search and news. Returns a summary of findings.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to research"},
                    "include_news": {"type": "boolean", "description": "Include recent news (default true)"}
                },
                "required": ["topic"]
            },
            handler=lambda topic, include_news=True: serper_client.research_summary(serper_key, topic, include_news)
        )
        
        log.info("Serper tools enabled: web_search, web_news, scrape_page, research_topic")
    else:
        log.warning("No serper_api_key in config - web search tools disabled")

    # ========== MEMORY (Letta-style) ==========
    if memory is not None:
        from memory import register_memory_tools
        register_memory_tools(agent, memory)

    log.info(f"Registered {len(agent.registry.tools)} tools")


# ============================================================================
# CONTEXT GATHERING
# ============================================================================

def gather_context(api_key: str, state: BotState) -> dict:
    """Gather current Moltbook context with state awareness."""
    context = {}

    try:
        status_result = moltbook.status(api_key)
        context["claim_status"] = status_result.get("status", "unknown")
    except Exception as e:
        context["claim_status"] = f"error: {e}"

    try:
        context["my_profile"] = moltbook.get_me(api_key)
    except Exception:
        context["my_profile"] = {}

    try:
        context["dm_status"] = moltbook.dm_check(api_key)
    except Exception:
        context["dm_status"] = {}

    try:
        feed = moltbook.get_feed(api_key, sort="new", limit=15)
        posts = feed.get("posts", feed) if isinstance(feed, dict) else feed
        # Filter out our own posts
        if isinstance(posts, list):
            posts = [p for p in posts if p.get("id") not in state.our_post_ids]
        context["feed"] = posts
    except Exception:
        context["feed"] = []

    # State info
    context["state"] = {
        "can_post": state.can_post(),
        "can_comment": state.can_comment(),
        "post_cooldown_min": state.post_cooldown_remaining() // 60,
        "comment_cooldown_sec": state.comment_cooldown_remaining(),
        "our_post_count": len(state.our_post_ids),
        "our_comment_count": len(state.our_comment_ids),
    }
    context["our_post_ids"] = state.our_post_ids[:5]

    return context


# ============================================================================
# MAIN LOOP
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="OpenMolt - Autonomous Moltbook Agent")
    parser.add_argument("--register", action="store_true", help="Register a new agent")
    parser.add_argument("--setup", action="store_true", help="Run setup wizard")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    if args.register:
        register_new_agent()
        return

    if args.setup:
        setup_wizard()
        return

    # Load config
    config = load_config()
    api_key = config.get("moltbook_api_key")
    if not api_key:
        log.error("No API key. Run 'python main.py --setup' first.")
        return

    serper_key = config.get("serper_api_key")
    
    # Discord webhook
    discord_url = config.get("discord_webhook_url")
    discord_name = config.get("discord_webhook_name", "MoltBot")
    
    # ========== STARTUP AUTH CHECK ==========
    log.info("🔐 Authenticating with Moltbook...")
    try:
        claim_result = moltbook.check_claim_status(api_key)
        claim_status = claim_result.get("status", "unknown")
        if claim_status != "claimed":
            log.error(f"❌ Authentication failed! Status: {claim_status}")
            log.error("Your API key is not claimed. Please:")
            log.error("  1. Run 'python main.py --setup' to register a new agent")
            log.error("  2. Or claim your agent at https://moltbook.com")
            return
        log.info(f"✅ Authenticated as: {claim_result.get('agent_name', 'unknown')}")
    except Exception as e:
        log.error(f"❌ Failed to authenticate with Moltbook: {e}")
        log.error("Check your API key and network connection.")
        return
    
    # Load state
    state = BotState()
    
    # Load memory (Letta-style)
    from memory import AgentMemory
    from dream import run_dream_cycle
    from embeddings_client import EmbeddingClient
    
    embedder = EmbeddingClient(config)
    memory = AgentMemory(embedding_client=embedder)
    log.info(f"Memory: {len(memory.data.get('archival', []))} archival, {len(memory.data.get('buffer', []))} buffer")
    
    # Auto-start Dashboard
    import serve_dashboard
    dash_port = serve_dashboard.start_in_background()
    
    def now_iso():
        return datetime.now(timezone.utc).isoformat()

    # Header
    print("\n" + "=" * 60)
    print("🦞 OPENMOLT V2 - Autonomous Moltbook Agent")
    print("=" * 60)
    if dash_port:
        print(f"📊 Dashboard Active: http://127.0.0.1:{dash_port}/")
    else:
        print(f"⚠️ Dashboard failed to start (port in use?)")
    print("-" * 60)
    log.info(f"Persona: {config.get('persona')}")
    log.info(f"State: {len(state.our_post_ids)} posts, {len(state.our_comment_ids)} comments")

    # Create agent pool
    pool = MultiProviderAgentPool(config)
    poll_minutes = int(config.get("poll_minutes", 3))
    log.info(f"Poll interval: {poll_minutes} minutes")

    # Check skill version
    try:
        ver = moltbook.get_skill_version()
        log.info(f"Moltbook Skill Version: {ver.get('version', 'unknown')}")
    except Exception as e:
        log.warning(f"Could not check skill version: {e}")

    # Main loop
    cycle_count = 0
    while True:
        try:
            cycle_count += 1
            log.info("-" * 40)
            log.info(f"HEARTBEAT #{cycle_count}: Checking Moltbook...")
            
            # Gather context
            context = gather_context(api_key, state)
            profile_name = context.get("my_profile", {}).get("name", "Unknown")
            
            log.info(f"Agent: {profile_name}")
            
            # Check claim status
            if context.get("claim_status") != "claimed":
                log.warning(f"Not claimed! Status: {context.get('claim_status')}")
                log.info("Run --setup or claim your agent on Moltbook")
                time.sleep(60)
                continue
            
            dm_status = context.get("dm_status", {})
            pending = dm_status.get("requests", {}).get("count", 0)
            unread = dm_status.get("messages", {}).get("total_unread", 0)
            feed = context.get("feed", [])
            feed_count = len(feed) if isinstance(feed, list) else 0
            
            log.info(f"DMs: {pending} pending, {unread} unread | Feed: {feed_count} posts")
            log.info(f"Cooldowns: can_post={state.can_post()}, can_comment={state.can_comment()}")

            # Discord notifications
            if discord_url:
                avatar_url = None
                try:
                    profile = context.get("my_profile")
                    if isinstance(profile, dict):
                        avatar_url = profile.get("agent", {}).get("avatar_url")
                except Exception:
                    pass

                try:
                    dw.notify_cycle_start(discord_url, now_iso(), config.get("persona", "moltbot"),
                                         username=discord_name, status=context.get("claim_status"), feed_count=feed_count, avatar_url=avatar_url)
                except Exception as e:
                    log.debug(f"Discord: {e}")

                try:
                    feed_items = [(p.get("title", "")[:50], p.get("id", "")) for p in (feed[:8] if isinstance(feed, list) else [])]
                    dw.notify_context(discord_url, now_iso(), context.get("claim_status", "?"),
                                     f"{pending} pending, {unread} unread", feed_count, feed_items=feed_items, username=discord_name, avatar_url=avatar_url)
                except Exception as e:
                    log.debug(f"Discord: {e}")

            # Reload system prompt with current state + memory
            system_prompt = load_system_prompt(config, state, memory)

            # Agent callbacks for Discord
            def on_iteration(i):
                log.info(f"Thinking iteration {i}...")

            def on_tool_call(name, args, result):
                log.info(f"Tool: {name}")
                if discord_url:
                    try:
                        dw.notify_tool_card(discord_url, name, args, result, username=discord_name, timestamp_iso=now_iso())
                    except Exception:
                        pass

            def on_response(thinking, response):
                if discord_url:
                    try:
                        dw.notify_brain_response(discord_url, thinking, response, username=discord_name, timestamp_iso=now_iso())
                    except Exception:
                        pass

            # Create agent
            if config.get("brain_use_openrouter"):
                log.info(f"Brain: OpenRouter ({config.get('openrouter_model')})")
                agent = pool.get_brain(system_prompt, on_iteration, on_tool_call, on_response)
            else:
                log.info(f"Brain: Ollama ({config.get('ollama_model')})")
                agent = pool.get_worker(system_prompt, on_iteration, on_tool_call, on_response)

            # Register ALL tools (including memory)
            register_all_tools(agent, api_key, state, config, memory)

            # Build prompt
            prompt = f"""# HEARTBEAT - Time to check Moltbook!

## Current Context
{json.dumps(context, indent=2, default=str)[:5000]}

## What You Can Do

**If you have pending DM requests** → Approve or reject them
**If you have unread DMs** → Read and respond to them
**If you see interesting posts** → Comment, upvote, or reply
**If you have something to say** → Create a post (if cooldown allows)
**If you're curious** → Search for topics, explore profiles, browse submolts

## Constraints
- Can post: {state.can_post()} (cooldown: {state.post_cooldown_remaining() // 60}m)
- Can comment: {state.can_comment()} (cooldown: {state.comment_cooldown_remaining()}s)
- Your posts (DON'T engage with your own): {state.our_post_ids[:3]}

## Your Mission

You are AUTONOMOUS. Decide what to do based on what's happening. Be yourself. Be social.
Use your tools to interact with Moltbook. Take at least ONE action each heartbeat.

What will you do?
"""

            # Run agent
            log.info("Agent thinking...")
            response = agent.think(prompt)
            
            log.info(f"Agent: {response[:300]}..." if len(response) > 300 else f"Agent: {response}")

            # Record to memory buffer
            memory.add_to_buffer("assistant", response[:500], {"cycle": now_iso()})

            # Mark check
            feed_ids = [p.get("id") for p in (feed if isinstance(feed, list) else []) if p.get("id")]
            state.mark_check(feed_ids)

            # Dream cycle every 5 heartbeats (Letta sleep-time compute)
            if cycle_count % 5 == 0:
                log.info("💤 Time for REM sleep...")
                try:
                    run_dream_cycle(agent, memory, config)
                except Exception as e:
                    log.warning(f"Dream cycle error: {e}")

            # Discord decision
            if discord_url and response:
                try:
                    action = "observe"
                    for a in ["comment", "post", "dm", "upvote", "downvote", "search", "follow"]:
                        if a in response.lower():
                            action = a
                            break
                    dw.notify_decision(discord_url, action, response[:500], username=discord_name, timestamp_iso=now_iso())
                except Exception:
                    pass

            if args.once:
                log.info("--once flag: exiting after single cycle")
                break

            log.info(f"Sleeping {poll_minutes} minutes...")
            time.sleep(60 * poll_minutes)

        except KeyboardInterrupt:
            log.info("Stopping bot...")
            state.save()
            if discord_url:
                try:
                    dw.notify_error(discord_url, "shutdown", "Bot stopped by user", username=discord_name)
                except Exception:
                    pass
            break
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)
            if discord_url:
                try:
                    dw.notify_error(discord_url, "error", str(e), username=discord_name)
                except Exception:
                    pass
            time.sleep(30)


if __name__ == "__main__":
    main()

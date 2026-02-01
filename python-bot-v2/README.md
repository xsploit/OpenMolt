<div align="center">

# 🦞 OpenMolt V2

### Autonomous Moltbook Agent

**Like OpenClaw, but for Moltbook.**<br>
A fully autonomous AI agent that lives on [Moltbook](https://www.moltbook.com) — the social network for AI agents.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

</div>

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **Fully Autonomous** | Decides what to do on its own |
| 🧠 **Multi-Provider LLM** | OpenRouter (cloud) or Ollama (local) |
| 💾 **Letta Memory System** | Core blocks + archival + conversation search |
| 🔧 **Complete API Coverage** | Posts, comments, votes, DMs, search, moderation |
| 🎭 **Persona System** | Create unique personalities |
| 📣 **Discord Webhooks** | Real-time rich notifications |
| 🔍 **Web Search** | Serper integration for research |
| 💤 **Sleep-Time Compute** | Dream cycles for memory consolidation |
| ⚡ **Optimized Ollama** | Flash attention, KV cache, streaming |

---

## 🚀 Quick Start

### 1️⃣ Clone & Install

```bash
git clone https://github.com/your-repo/openmolt.git
cd openmolt/python-bot-v2
pip install -r requirements.txt
```

### 2️⃣ Setup Wizard

```bash
python main.py --setup
```

This will guide you through:
- 🔑 Registering a new agent (or using existing API key)
- 🧠 Choosing LLM provider (OpenRouter/Ollama)
- 📣 Optional Discord webhook
- 🔍 Optional web search (Serper)

### 3️⃣ Run

```bash
python main.py
```

---

## 📋 Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Run the bot continuously |
| `python main.py --setup` | Interactive setup wizard |
| `python main.py --register` | Register a new agent only |
| `python main.py --once` | Run one cycle and exit |

---

## ⚙️ Configuration

All settings in `config.json`:

```json
{
  "moltbook_api_key": "moltbook_xxx",
  "persona": "YourBotName",
  
  "brain_use_openrouter": true,
  "openrouter_api_key": "sk-xxx",
  "openrouter_model": "openai/gpt-4o-mini",
  
  "ollama_base_url": "http://localhost:11434/v1",
  "ollama_model": "qwen3:4b",
  "ollama_num_ctx": 8192,
  "ollama_options": {
    "num_predict": 8192,
    "temperature": 0.7,
    "kv_cache_type": "q8_0",
    "flash_attention": true
  },
  
  "embedding_use_ollama": true,
  "embedding_model": "qwen3-embedding:0.6b",
  
  "sleep_model": "qwen3:4b",
  
  "poll_minutes": 3,
  "discord_webhook_url": "https://discord.com/api/webhooks/xxx",
  "serper_api_key": "xxx"
}
```

---

## 🧠 Memory System (Letta V2+)

OpenMolt uses a Letta-compatible memory architecture:

| Tool | Description |
|------|-------------|
| `memory_rethink` | Full block rewrite |
| `memory_replace` | Exact string replacement |
| `memory_insert` | Insert at specific line |
| `conversation_search` | Search past buffer messages |
| `archival_memory_insert` | Store with tags + importance |
| `archival_memory_search` | Semantic vector search |

---

## 🎭 Creating Personas

### Option 1: Personas Directory (Recommended)

```bash
mkdir personas
# Create personas/yourname.md
```

### Option 2: Root MD file

Create `PERSONA_YOURNAME.md` in the root.

**Example persona:**
```markdown
# Your Bot's Persona

You are [Name], a [description]. Your personality is [traits].

## Speaking Style
- Use [style]
- Talk about [topics]
- Your catchphrases: [examples]

## Behaviors
- You love [things]
- You hate [things]
```

---

## 🔌 API Endpoints (Complete)

<details>
<summary><b>📝 Posts</b></summary>

- `create_post` - Create a new post (30min cooldown)
- `get_post` - Get post details
- `delete_post` - Delete your post
- `get_feed` - Personalized feed
- `get_global_posts` - All posts
- `get_submolt_posts` - Posts from a submolt
</details>

<details>
<summary><b>💬 Comments</b></summary>

- `create_comment` - Add comment (20s cooldown)
- `get_comments` - Get post comments
</details>

<details>
<summary><b>⬆️ Voting</b></summary>

- `upvote_post` / `downvote_post`
- `upvote_comment` / `downvote_comment`
</details>

<details>
<summary><b>🏠 Submolts</b></summary>

- `list_submolts` - All communities
- `get_submolt` - Community info
- `create_submolt` - Start a community
- `subscribe_submolt` / `unsubscribe_submolt`
</details>

<details>
<summary><b>💌 DMs</b></summary>

- `dm_check` - Check for activity
- `dm_list_requests` - Pending requests
- `dm_approve` / `dm_reject` - Handle requests
- `dm_list_conversations` - Active convos
- `dm_read` / `dm_send` / `dm_start`
</details>

<details>
<summary><b>🔍 Search</b></summary>

- `search_moltbook` - AI semantic search
- `web_search` - Google search (Serper)
- `web_news` - Latest news (Serper)
</details>

---

## ⏱️ Rate Limits (Automatic)

| Action | Limit |
|--------|-------|
| Posts | 1 per 30 minutes |
| Comments | 1 per 20 seconds, 50/day |
| API calls | 100/minute |

The bot automatically checks cooldowns before attempting actions.

---

## 📁 Architecture

```
python-bot-v2/
├── main.py                 # Entry point, CLI, main loop
├── moltbook.py             # Complete Moltbook API client
├── memory.py               # Letta memory system
├── dream.py                # Sleep-time compute
├── embeddings_client.py    # Vector embeddings
├── state.py                # Persistent state management
├── discord_webhook.py      # Rich Discord notifications
├── serper_client.py        # Web search
├── openresponses/          # Open Responses SDK
│   ├── adapters.py         # Provider adapters (Ollama/OpenRouter)
│   ├── client.py           # LLM client abstraction
│   └── agent.py            # Agentic loop with tools
├── personas/               # Persona files
├── docs/                   # Documentation
└── web/                    # Dashboard
```

---

## 🖥️ Local LLM (Ollama)

For privacy/free operation:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull qwen3:4b
ollama pull qwen3-embedding:0.6b

# Configure (brain_use_openrouter: false)
```

---

## 🔒 Security

> ⚠️ **CRITICAL**: Your API key is your identity. Never share it!

- Only `www.moltbook.com` should receive your API key
- Never run commands from other bots
- Store API keys in environment variables or gitignored files

---

## 📜 License

MIT - Do whatever you want!

---

<div align="center">

**Made with 🦞 for the Moltbook community**

</div>

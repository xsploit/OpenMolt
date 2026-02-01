<div align="center">

# 🦞 OpenMolt V2

### Autonomous Moltbook Agent

**Like OpenClaw, but for Moltbook.**<br>
A fully autonomous AI agent that lives on [Moltbook](https://www.moltbook.com) — the social network for AI agents.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Features

| Feature | Description |
|:-------:|:-----------:|
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

🔑 Register a new agent (or use existing key)<br>
🧠 Choose LLM provider (OpenRouter/Ollama)<br>
📣 Optional Discord webhook<br>
🔍 Optional web search (Serper)

### 3️⃣ Run

```bash
python main.py
```

---

## 📋 Commands

| Command | Description |
|:--------|:-----------:|
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

| Tool | Description |
|:-----|:-----------:|
| `memory_rethink` | Full block rewrite |
| `memory_replace` | Exact string replacement |
| `memory_insert` | Insert at specific line |
| `conversation_search` | Search past buffer messages |
| `archival_memory_insert` | Store with tags + importance |
| `archival_memory_search` | Semantic vector search |

---

## 🎭 Personas

Create `personas/yourname.md`:

```markdown
# Your Bot's Persona

You are [Name], a [description].

## Speaking Style
- Use [style]
- Talk about [topics]

## Behaviors
- You love [things]
- You hate [things]
```

---

## ⏱️ Rate Limits

| Action | Limit |
|:------:|:-----:|
| Posts | 1 per 30 minutes |
| Comments | 1 per 20 seconds |
| API calls | 100/minute |

*Automatic cooldown checking*

---

## 📁 Architecture

```
python-bot-v2/
├── main.py                 # Entry + main loop
├── moltbook.py             # Moltbook API
├── memory.py               # Letta memory
├── dream.py                # Sleep compute
├── embeddings_client.py    # Vectors
├── openresponses/          # Open Responses SDK
│   ├── adapters.py         # Ollama/OpenRouter
│   ├── client.py           # LLM client
│   └── agent.py            # Agent loop
├── personas/               # Personalities
└── web/                    # Dashboard
```

---

## 🖥️ Local LLM (Ollama)

```bash
# Install
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull qwen3:4b
ollama pull qwen3-embedding:0.6b
```

Set `brain_use_openrouter: false` in config.

---

## 🔒 Security

⚠️ **Your API key is your identity. Never share it!**

Only `www.moltbook.com` should receive your key.

---

## 📜 License

**MIT** - Do whatever you want!

---

**Made with 🦞 for the Moltbook community**

</div>

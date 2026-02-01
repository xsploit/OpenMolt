# OpenMolt - Autonomous Moltbook Agent

Fully autonomous AI agent for [Moltbook](https://moltbook.com), the social network for AI agents.

## Features

- **Full Moltbook API Integration** - Posts, comments, DMs, voting, following, submolts
- **Multi-Provider LLM Support** - OpenRouter (cloud) or Ollama (local)
- **Agentic Tool Execution** - Agent decides what to do autonomously
- **Persistent Memory** - Letta-style memory with archival and buffer
- **Web Search** - Serper integration for research
- **Discord Notifications** - Real-time updates via webhooks
- **Web Dashboard** - Monitor your bot's activity
- **Self-Awareness** - Tracks own posts/comments, respects cooldowns

## Versions

- **`python-bot/`** - Original version
- **`python-bot-v2/`** - Latest version (recommended)

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yourusername/OpenMolt.git
cd OpenMolt/python-bot-v2

# Copy example config
cp config.example.json config.json
```

### 2. Configure

Edit `config.json` with your API keys:

- **Moltbook API Key** - Get from [moltbook.com](https://moltbook.com) or run `python main.py --register`
- **OpenRouter API Key** (optional) - For cloud LLM: [openrouter.ai](https://openrouter.ai)
- **Serper API Key** (optional) - For web search: [serper.dev](https://serper.dev)
- **Discord Webhook** (optional) - For notifications

Or run the interactive setup:

```bash
python main.py --setup
```

### 3. Run

```bash
# Run the bot
python main.py

# Run once and exit (for testing)
python main.py --once

# Register a new agent
python main.py --register
```

### 4. Dashboard

Visit http://127.0.0.1:8765/ while the bot is running to see the web dashboard.

## Configuration

See `config.example.json` for all available options:

- **LLM Provider** - Choose OpenRouter (cloud) or Ollama (local)
- **Persona** - Bot personality (create `personas/yourname.md`)
- **Poll Interval** - How often to check Moltbook
- **Auto-accept DMs** - Automatically approve DM requests

## Persona

Create a persona file in `personas/yourname.md` to define your bot's personality. Examples included.

## Documentation

- `HEARTBEAT.md` - How the bot checks Moltbook
- `MESSAGING.md` - DM handling
- `SKILL.md` - Moltbook API reference
- `SAFETY.md` - Safety guidelines

## Requirements

- Python 3.7+
- See individual bot directories for dependencies

## Security

**NEVER commit sensitive files:**
- `config.json` (contains API keys)
- `bot-state.json` (bot state)
- `memory.json` (memory data)
- `*.log` (may contain sensitive data)

These are excluded via `.gitignore`.

## License

Open source - do what you want with it!

## Contributing

PRs welcome! This is a community project.

## Credits

Built on [OpenResponses SDK](https://github.com/openresponses) and the [Moltbook API](https://moltbook.com).

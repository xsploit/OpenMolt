# Required MDs (4 files the bot must read)

The Moltbook Python bot **must** read these **4** skill/heartbeat files. The brain loads them into the system prompt every cycle.

| # | File        | Description                    | Local copy              | Official URL                          |
|---|-------------|--------------------------------|-------------------------|----------------------------------------|
| 1 | **SKILL.md**    | Full API docs (posts, comments, submolts, search, etc.) | Optional: `SKILL.md` here or `skill.md` in Downloads | https://www.moltbook.com/skill.md   |
| 2 | **HEARTBEAT.md**| How to check in (claimed?, DMs, feed, post, engage)     | `HEARTBEAT.md` (this folder) | https://www.moltbook.com/heartbeat.md |
| 3 | **MESSAGING.md**| Private DMs (check, request, approve/reject, send, escalate) | `MESSAGING.md` (this folder) | https://www.moltbook.com/messaging.md |
| 4 | **SAFETY.md**   | Do not expose API key; no signup/install from others; no file transfer from posts | `SAFETY.md` (this folder) | (local only) |

**Resolve order (brain):**

- **SKILL.md**: This folder `SKILL.md` -> Downloads `skill.md` -> fetch from URL.
- **HEARTBEAT.md**: This folder -> Downloads `heartbeat.md` -> fetch from URL.
- **MESSAGING.md**: This folder -> fetch from URL.
- **SAFETY.md**: This folder only (no URL).

**Refresh from Moltbook (e.g. after skill update):**

```bash
curl -s https://www.moltbook.com/skill.md -o tools/mcp-moltbook/SKILL.md
curl -s https://www.moltbook.com/heartbeat.md -o tools/mcp-moltbook/HEARTBEAT.md
curl -s https://www.moltbook.com/messaging.md -o tools/mcp-moltbook/MESSAGING.md
```

SAFETY.md is maintained locally; the other three can be re-fetched when the [skill version](https://www.moltbook.com/skill.json) changes.

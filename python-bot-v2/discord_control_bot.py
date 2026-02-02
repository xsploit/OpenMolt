"""
Discord control bot (optional).

Requirements:
  - python -m pip install discord.py
Config keys (optional):
  - discord_control_bot_token: bot token string
  - discord_control_channel_id: int (channel where bot should respond)
  - discord_control_owner_id: int (only this user can issue commands)

Behavior:
  - Listens in the allowed channel only.
  - Rejects commands from non-owner.
  - Commands:
      !status          -> enqueues {"type":"status"}
      !run             -> enqueues {"type":"run_once"}
      !say <text>      -> enqueues {"type":"director_note","text":...}
      !pause           -> enqueues {"type":"pause"}
      !resume          -> enqueues {"type":"resume"}
  - All commands are best-effort; errors are sent as ephemeral replies.

Integration:
  - In main.py, create a Queue and pass its getter into the main loop to act on messages.
  - Start this bot in a background thread if token is provided.
"""
import asyncio
import logging
from typing import Callable

import discord

log = logging.getLogger(__name__)


def start_discord_control(token: str, channel_id: int, owner_id: int, enqueue: Callable[[dict], None]) -> None:
    """Start the Discord control bot in its own asyncio loop."""

    intents = discord.Intents.none()
    intents.messages = True
    intents.message_content = True

    class ControlClient(discord.Client):
        async def on_ready(self):
            log.info(f"Discord control bot logged in as {self.user}")

        async def on_message(self, message: discord.Message):
            # Channel + owner gate
            if message.author.id != owner_id:
                return
            if message.channel.id != channel_id:
                return
            if message.author.bot:
                return
            content = message.content.strip()
            cmd, *rest = content.split(" ", 1)
            arg = rest[0].strip() if rest else ""

            def ack(text: str):
                try:
                    return asyncio.create_task(message.reply(text))
                except Exception:
                    return None

            if cmd == "!status":
                enqueue({"type": "status_request"})
                ack("Status requested.")
            elif cmd == "!run":
                enqueue({"type": "run_once"})
                ack("Run requested.")
            elif cmd == "!say":
                if not arg:
                    ack("Usage: !say <text>")
                else:
                    enqueue({"type": "director_note", "text": arg})
                    ack("Director note queued.")
            elif cmd == "!pause":
                enqueue({"type": "pause"})
                ack("Pause requested.")
            elif cmd == "!resume":
                enqueue({"type": "resume"})
                ack("Resume requested.")
            else:
                # ignore other messages
                return

    client = ControlClient(intents=intents)

    async def runner():
        try:
            await client.start(token)
        except Exception as e:
            log.error(f"Discord control bot failed: {e}")

    def run_loop():
        asyncio.run(runner())

    import threading

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

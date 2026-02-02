"""
Discord control bot using discord.py commands extension (optional).

Config (optional):
  - discord_control_bot_token: bot token string
  - discord_control_channel_id: int (channel where bot should respond)
  - discord_control_owner_id: int (only this user can issue commands)

Commands (owner + channel gated):
  !status        -> enqueue {"type": "status_request"}
  !run           -> enqueue {"type": "run_once"}
  !say <text>    -> enqueue {"type": "director_note", "text": ...}
  !pause         -> enqueue {"type": "pause"}
  !resume        -> enqueue {"type": "resume"}
"""
import asyncio
import logging
from typing import Callable

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


def start_discord_control(token: str, channel_id: int, owner_id: int, enqueue: Callable[[dict], None]) -> None:
    intents = discord.Intents.none()
    intents.messages = True
    intents.message_content = True

    def owner_and_channel_only():
        async def predicate(ctx: commands.Context):
            return ctx.author.id == owner_id and ctx.channel.id == channel_id and not ctx.author.bot
        return commands.check(predicate)

    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        log.info(f"Discord control bot logged in as {bot.user}")

    @bot.command(name="status")
    @owner_and_channel_only()
    async def status_cmd(ctx: commands.Context):
        enqueue({"type": "status_request"})
        await ctx.reply("Status requested.", mention_author=False)

    @bot.command(name="run")
    @owner_and_channel_only()
    async def run_cmd(ctx: commands.Context):
        enqueue({"type": "run_once"})
        await ctx.reply("Run queued.", mention_author=False)

    @bot.command(name="say")
    @owner_and_channel_only()
    async def say_cmd(ctx: commands.Context, *, text: str = ""):
        if not text.strip():
            await ctx.reply("Usage: !say <text>", mention_author=False)
            return
        enqueue({"type": "director_note", "text": text.strip()})
        await ctx.reply("Director note queued.", mention_author=False)

    @bot.command(name="pause")
    @owner_and_channel_only()
    async def pause_cmd(ctx: commands.Context):
        enqueue({"type": "pause"})
        await ctx.reply("Pause requested.", mention_author=False)

    @bot.command(name="resume")
    @owner_and_channel_only()
    async def resume_cmd(ctx: commands.Context):
        enqueue({"type": "resume"})
        await ctx.reply("Resume requested.", mention_author=False)

    @bot.event
    async def on_command_error(ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            return  # silently ignore non-owner/channel
        try:
            await ctx.reply(f"Error: {error}", mention_author=False)
        except Exception:
            pass
        log.warning(f"Discord command error: {error}")

    async def runner():
        try:
            await bot.start(token)
        except Exception as e:
            log.error(f"Discord control bot failed: {e}")

    def run_loop():
        asyncio.run(runner())

    import threading

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

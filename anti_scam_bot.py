"""
Discord Anti-Scam Bot
Detects and removes crypto/gambling scam messages automatically.
Includes spam flood detection and !nuke command.
"""

import discord
from discord.ext import commands
import re
import logging
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ─── CONFIG ───────────────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

LOG_CHANNEL_ID = None
WARNINGS_BEFORE_BAN = 3
MUTE_DURATION_MINUTES = 30
SPAM_MESSAGE_LIMIT = 3
SPAM_TIME_WINDOW = 10

# ─── SCAM DETECTION PATTERNS ──────────────────────────────────────────────────

SCAM_KEYWORDS = [
    r"\bpromo\s*code\b",
    r"\bactivate\s*code\b",
    r"\bbonus\s*code\b",
    r"\bcasino\b",
    r"\bgambling\b",
    r"\bsports?bet\b",
    r"\bpokerbros\b",
    r"\bpulse\s*casino\b",
    r"\bstake\.com\b",
    r"\bbc\.game\b",
    r"\brollbit\b",
    r"\bduelbits\b",
    r"\bprizepicks\b",
    r"\bbovada\b",
    r"\bgiving away\s*\$[\d,]+\b",
    r"\bclaim\s*(your\s*)?(reward|bonus|prize)\b",
    r"\bwithdrawal\s*success\b",
    r"\bwithdraw\s*(instantly|now)\b",
    r"\bfree\s*(crypto|bitcoin|btc|eth|usdt)\b",
    r"\bsend\s*\d+\s*(btc|eth|usdt|crypto)\b",
    r"\bdouble\s*your\s*(crypto|bitcoin|money)\b",
    r"\bkai\s*cenat\b",
    r"\b@kaicenat\b",
    r"\bcenat\b",
    r"\bany\s*means\s*possible\b",
    r"bit\.ly/",
    r"tinyurl\.com/",
    r"t\.co/[a-z0-9]+",
    r"\bclick\s*here\s*to\s*claim\b",
    r"\b(pedanex|pedanet|pedanes)\.com\b",
    r"\b\w+(casino|bet|stake|gambling)\w*\.com\b",
]

KEYWORD_THRESHOLD = 2

INSTANT_DELETE_PHRASES = [
    "withdrawal success",
    "activate code for bonus",
    "enter the promo code",
    "giving away $2,500",
    "giving away $2500",
    "promo code: cenat",
    "promo code cenat",
    "launch of my very own crypto casino",
]

# ─── BOT SETUP ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("anti_scam_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("AntiScamBot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

user_warnings: dict[int, int] = {}
user_scam_times: dict[int, list] = defaultdict(list)

compiled_patterns = [re.compile(p, re.IGNORECASE) for p in SCAM_KEYWORDS]
compiled_instant = [phrase.lower() for phrase in INSTANT_DELETE_PHRASES]

# ─── DETECTION LOGIC ──────────────────────────────────────────────────────────

def is_scam(content: str) -> tuple[bool, str]:
    text = content.lower()
    for phrase in compiled_instant:
        if phrase in text:
            return True, f"Instant-delete phrase: '{phrase}'"
    matched = [p.pattern for p in compiled_patterns if p.search(content)]
    if len(matched) >= KEYWORD_THRESHOLD:
        return True, f"{len(matched)} scam patterns matched: {matched[:3]}"
    return False, ""

def is_spam_flood(user_id: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=SPAM_TIME_WINDOW)
    user_scam_times[user_id] = [t for t in user_scam_times[user_id] if t > cutoff]
    user_scam_times[user_id].append(now)
    return len(user_scam_times[user_id]) >= SPAM_MESSAGE_LIMIT

# ─── EVENT HANDLERS ───────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    log.info(f"✅ Anti-Scam Bot online as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="for scams 🛡️"
        )
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    content = message.content or ""
    if message.attachments and not content.strip():
        await bot.process_commands(message)
        return

    scam, reason = is_scam(content)

    if scam:
        flood = is_spam_flood(message.author.id)
        if flood:
            await handle_spam_flood(message, reason)
        else:
            await handle_scam(message, reason)

    await bot.process_commands(message)


async def handle_spam_flood(message: discord.Message, reason: str):
    guild = message.guild
    author = message.author
    user_id = author.id

    log.info(f"🚨 SPAM FLOOD from {author} — instant ban + bulk delete")

    deleted_count = 0
    for channel in guild.text_channels:
        try:
            msgs_to_delete = []
            async for msg in channel.history(limit=100):
                if msg.author.id == user_id:
                    msgs_to_delete.append(msg)
            if msgs_to_delete:
                if len(msgs_to_delete) == 1:
                    await msgs_to_delete[0].delete()
                else:
                    await channel.delete_messages(msgs_to_delete)
                deleted_count += len(msgs_to_delete)
        except (discord.Forbidden, discord.HTTPException):
            pass

    log.info(f"🗑️  Bulk deleted {deleted_count} messages from {author}")

    try:
        await guild.ban(
            author,
            reason=f"Anti-scam bot: spam flood ({reason})",
            delete_message_days=1
        )
        log.info(f"🔨 Instant banned spammer {author}")
        user_scam_times.pop(user_id, None)
        user_warnings.pop(user_id, None)
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning(f"Could not ban {author}: {e}")

    if LOG_CHANNEL_ID:
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🚨 SPAM FLOOD — User Banned",
                color=discord.Color.dark_red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=f"{author} (`{user_id}`)", inline=True)
            embed.add_field(name="Messages Deleted", value=str(deleted_count), inline=True)
            embed.add_field(name="Reason", value=reason[:1000], inline=False)
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                pass


async def handle_scam(message: discord.Message, reason: str):
    guild = message.guild
    author = message.author
    user_id = author.id

    try:
        await message.delete()
        log.info(f"🗑️  Deleted scam from {author} in #{message.channel.name} | {reason}")
    except discord.Forbidden:
        log.warning(f"⚠️  Missing permissions to delete message from {author}")
        return
    except discord.NotFound:
        pass

    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warn_count = user_warnings[user_id]

    try:
        await author.send(
            f"⚠️ **Your message in {guild.name} was removed.**\n"
            f"Flagged as scam/spam. Warning **{warn_count}/{WARNINGS_BEFORE_BAN}**.\n"
            f"Continued violations will result in a ban."
        )
    except discord.Forbidden:
        pass

    if warn_count == 1 and MUTE_DURATION_MINUTES > 0:
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=MUTE_DURATION_MINUTES)
            await author.timeout(until, reason=f"Anti-scam bot: {reason}")
            log.info(f"🔇 Muted {author} for {MUTE_DURATION_MINUTES} minutes")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Could not mute {author}: {e}")

    if WARNINGS_BEFORE_BAN > 0 and warn_count >= WARNINGS_BEFORE_BAN:
        try:
            await guild.ban(author, reason=f"Anti-scam bot: {warn_count} warnings", delete_message_days=1)
            log.info(f"🔨 Banned {author} after {warn_count} warnings")
            del user_warnings[user_id]
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Could not ban {author}: {e}")

    if LOG_CHANNEL_ID:
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🚨 Scam Message Removed",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=f"{author.mention} (`{author.id}`)", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Warnings", value=f"{warn_count}/{WARNINGS_BEFORE_BAN}", inline=True)
            embed.add_field(name="Reason", value=reason[:1000], inline=False)
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                pass

# ─── MOD COMMANDS ─────────────────────────────────────────────────────────────

@bot.command(name="scamcheck")
@commands.has_permissions(manage_messages=True)
async def scamcheck(ctx, *, text: str):
    detected, reason = is_scam(text)
    if detected:
        await ctx.send(f"✅ **Would be flagged.** Reason: {reason}")
    else:
        await ctx.send("❌ **Would NOT be flagged** by current patterns.")

@bot.command(name="clearwarnings")
@commands.has_permissions(kick_members=True)
async def clearwarnings(ctx, member: discord.Member):
    if member.id in user_warnings:
        del user_warnings[member.id]
        await ctx.send(f"✅ Cleared warnings for {member.mention}")
    else:
        await ctx.send(f"{member.mention} has no warnings.")

@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    count = user_warnings.get(member.id, 0)
    await ctx.send(f"⚠️ {member.mention} has **{count}** warning(s).")

@bot.command(name="nuke")
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    """Deletes and recreates the channel, wiping all messages. Usage: !nuke"""
    channel = ctx.channel
    new_channel = await channel.clone(reason=f"Channel nuked by {ctx.author}")
    await new_channel.edit(position=channel.position)
    await channel.delete(reason=f"Nuked by {ctx.author}")
    embed = discord.Embed(
        title="💥 Channel Nuked",
        description=f"This channel was nuked by {ctx.author.mention}.\nAll previous messages have been wiped.",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    await new_channel.send(embed=embed)
    log.info(f"💥 #{channel.name} nuked by {ctx.author}")

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(BOT_TOKEN)

"""
Discord Anti-Scam Bot
Detects and removes crypto/gambling scam messages automatically.

Setup:
1. pip install discord.py
2. Create a bot at https://discord.com/developers/applications
3. Enable: MESSAGE CONTENT INTENT, SERVER MEMBERS INTENT
4. Set your BOT_TOKEN and optionally LOG_CHANNEL_ID below
5. Run: python anti_scam_bot.py
"""

import discord
from discord.ext import commands
import re
import logging
import os
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

# Channel ID to log deleted messages (set to None to disable)
LOG_CHANNEL_ID = None  # e.g. 1234567890123456789

# How many warnings before auto-ban (set to 0 to disable auto-ban)
WARNINGS_BEFORE_BAN = 3

# Mute duration in minutes after first offense (set to 0 to disable)
MUTE_DURATION_MINUTES = 30

# Delete messages containing images if they ALSO match scam keywords
# (helps catch screenshot-only spam)
SCAN_IMAGES_WITH_KEYWORDS = True

# ─── SCAM DETECTION PATTERNS ──────────────────────────────────────────────────

SCAM_KEYWORDS = [
    # Gambling/casino promo
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
    # Crypto giveaway scams
    r"\bgiving away\s*\$[\d,]+\b",
    r"\bclaim\s*(your\s*)?(reward|bonus|prize)\b",
    r"\bwithdrawal\s*success\b",
    r"\bwithdraw\s*(instantly|now)\b",
    r"\bfree\s*(crypto|bitcoin|btc|eth|usdt)\b",
    r"\bsend\s*\d+\s*(btc|eth|usdt|crypto)\b",
    r"\bdouble\s*your\s*(crypto|bitcoin|money)\b",
    # Impersonation signals
    r"\bkai\s*cenat\b",
    r"\b@kaicenat\b",
    r"\bcenat\b",
    r"\bany\s*means\s*possible\b",
    # Suspicious links/redirects
    r"bit\.ly/",
    r"tinyurl\.com/",
    r"t\.co/[a-z0-9]+",
    r"\bclick\s*here\s*to\s*claim\b",
    # Common scam site patterns
    r"\b(pedanex|pedanet|pedanes)\.com\b",
    r"\b\w+(casino|bet|stake|gambling)\w*\.com\b",
]

# Messages matching this many keyword patterns = scam
KEYWORD_THRESHOLD = 2

# Phrases that are instant-delete regardless of threshold
INSTANT_DELETE_PHRASES = [
    "withdrawal success",
    "activate code for bonus",
    "enter the promo code",
    "giving away $2,500",
    "giving away $2500",
    "promo code: cenat",
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

# Track warnings per user: {user_id: warning_count}
user_warnings: dict[int, int] = {}

compiled_patterns = [re.compile(p, re.IGNORECASE) for p in SCAM_KEYWORDS]
compiled_instant = [phrase.lower() for phrase in INSTANT_DELETE_PHRASES]

# ─── DETECTION LOGIC ──────────────────────────────────────────────────────────

def is_scam(content: str) -> tuple[bool, str]:
    """Returns (is_scam, reason)"""
    text = content.lower()

    # Check instant-delete phrases first
    for phrase in compiled_instant:
        if phrase in text:
            return True, f"Instant-delete phrase matched: '{phrase}'"

    # Count keyword pattern matches
    matched = []
    for pattern in compiled_patterns:
        if pattern.search(content):
            matched.append(pattern.pattern)

    if len(matched) >= KEYWORD_THRESHOLD:
        return True, f"{len(matched)} scam patterns matched: {matched[:3]}"

    return False, ""

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
    # Ignore bots and DMs
    if message.author.bot or not message.guild:
        return

    # Don't moderate admins/mods
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    content = message.content or ""

    # If message has attachments but little text, still scan what text exists
    # (Scammers often post screenshots + minimal text)
    if message.attachments and not content.strip():
        await bot.process_commands(message)
        return

    scam, reason = is_scam(content)

    if scam:
        await handle_scam(message, reason)

    await bot.process_commands(message)


async def handle_scam(message: discord.Message, reason: str):
    guild = message.guild
    author = message.author
    user_id = author.id

    # Delete the message
    try:
        await message.delete()
        log.info(f"🗑️  Deleted scam message from {author} in #{message.channel.name} | {reason}")
    except discord.Forbidden:
        log.warning(f"⚠️  Missing permissions to delete message from {author}")
        return
    except discord.NotFound:
        pass  # Already deleted

    # Increment warnings
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warn_count = user_warnings[user_id]

    # DM the user
    try:
        await author.send(
            f"⚠️ **Your message in {guild.name} was removed.**\n"
            f"It was flagged as a scam/spam message.\n"
            f"This is warning **{warn_count}/{WARNINGS_BEFORE_BAN}**.\n"
            f"Continued violations may result in a mute or ban."
        )
    except discord.Forbidden:
        pass  # User has DMs disabled

    # Mute on first offense
    if warn_count == 1 and MUTE_DURATION_MINUTES > 0:
        try:
            until = datetime.utcnow() + timedelta(minutes=MUTE_DURATION_MINUTES)
            await author.timeout(until, reason=f"Anti-scam bot: {reason}")
            log.info(f"🔇 Muted {author} for {MUTE_DURATION_MINUTES} minutes")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Could not mute {author}: {e}")

    # Ban after threshold
    if WARNINGS_BEFORE_BAN > 0 and warn_count >= WARNINGS_BEFORE_BAN:
        try:
            await guild.ban(author, reason=f"Anti-scam bot: repeated scam posting ({warn_count} warnings)", delete_message_days=1)
            log.info(f"🔨 Banned {author} after {warn_count} warnings")
            del user_warnings[user_id]
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Could not ban {author}: {e}")

    # Log to mod channel if configured
    if LOG_CHANNEL_ID:
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🚨 Scam Message Detected & Removed",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{author.mention} (`{author.id}`)", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Warnings", value=f"{warn_count}/{WARNINGS_BEFORE_BAN}", inline=True)
            embed.add_field(name="Reason", value=reason[:1000], inline=False)
            embed.add_field(
                name="Message Preview",
                value=f"```{message.content[:500]}```" if message.content else "_[no text]_",
                inline=False
            )
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                pass

# ─── MOD COMMANDS ─────────────────────────────────────────────────────────────

@bot.command(name="scamcheck")
@commands.has_permissions(manage_messages=True)
async def scamcheck(ctx, *, text: str):
    """Test if a phrase would be flagged. Usage: !scamcheck <text>"""
    detected, reason = is_scam(text)
    if detected:
        await ctx.send(f"✅ **Would be flagged.** Reason: {reason}")
    else:
        await ctx.send("❌ **Would NOT be flagged** by current patterns.")

@bot.command(name="clearwarnings")
@commands.has_permissions(kick_members=True)
async def clearwarnings(ctx, member: discord.Member):
    """Clear a user's warning count. Usage: !clearwarnings @user"""
    if member.id in user_warnings:
        del user_warnings[member.id]
        await ctx.send(f"✅ Cleared warnings for {member.mention}")
    else:
        await ctx.send(f"{member.mention} has no warnings.")

@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    """Check a user's warning count. Usage: !warnings @user"""
    count = user_warnings.get(member.id, 0)
    await ctx.send(f"⚠️ {member.mention} has **{count}** warning(s).")

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(BOT_TOKEN)

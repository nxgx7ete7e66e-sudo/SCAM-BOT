"""
Discord Anti-Scam Bot
- Scam detection + auto delete
- Profanity filter
- Custom banned links
- Spam flood = instant ban
- Warning system with ban enforcement
- Rich log embeds (ban/timeout/scam)
- !manage panel for bot settings
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

# Set this to your "SCAM BOT" channel ID
# You can get it by right-clicking the channel in Discord → Copy Channel ID
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0")) or None

WARNINGS_BEFORE_BAN = 3
MUTE_DURATION_MINUTES = 30
SPAM_MESSAGE_LIMIT = 3
SPAM_TIME_WINDOW = 10

# ─── BANNED LINKS ─────────────────────────────────────────────────────────────

BANNED_LINKS = [
    "stake.com",
    "bc.game",
    "rollbit.com",
    "duelbits.com",
    "prizepicks.com",
    "bovada.lv",
    "pokerbros.net",
    "pulsecasino.com",
    "pedanex.com",
    "pedanet.com",
    "bit.ly",
    "tinyurl.com",
]

# ─── PROFANITY FILTER ─────────────────────────────────────────────────────────

BANNED_WORDS = [
    "nigger",
    "nigga",
    "faggot",
    "retard",
    "chink",
    "spic",
    "kike",
]

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
compiled_banned_words = [re.compile(r'\b' + re.escape(w) + r'\b', re.IGNORECASE) for w in BANNED_WORDS]

# ─── DETECTION LOGIC ──────────────────────────────────────────────────────────

def is_scam(content: str) -> tuple[bool, str]:
    text = content.lower()
    for phrase in compiled_instant:
        if phrase in text:
            return True, f"Instant-delete phrase: '{phrase}'"
    matched = [p.pattern for p in compiled_patterns if p.search(content)]
    if len(matched) >= KEYWORD_THRESHOLD:
        return True, f"{len(matched)} scam patterns matched"
    return False, ""

def has_banned_link(content: str) -> tuple[bool, str]:
    text = content.lower()
    for domain in BANNED_LINKS:
        if domain.lower() in text:
            return True, f"Banned link: {domain}"
    return False, ""

def has_profanity(content: str) -> tuple[bool, str]:
    for pattern in compiled_banned_words:
        match = pattern.search(content)
        if match:
            return True, f"Profanity detected"
    return False, ""

def is_spam_flood(user_id: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=SPAM_TIME_WINDOW)
    user_scam_times[user_id] = [t for t in user_scam_times[user_id] if t > cutoff]
    user_scam_times[user_id].append(now)
    return len(user_scam_times[user_id]) >= SPAM_MESSAGE_LIMIT

# ─── LOG EMBED HELPERS ────────────────────────────────────────────────────────

async def send_log(guild: discord.Guild, embed: discord.Embed):
    """Send embed to the configured log channel."""
    if not LOG_CHANNEL_ID:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

def ban_embed(user: discord.User | discord.Member, reason: str, warn_count: int, channel: discord.TextChannel = None) -> discord.Embed:
    now = datetime.now(timezone.utc)
    embed = discord.Embed(
        title="🔨 User Banned",
        color=0xFF0000,
        timestamp=now
    )
    embed.set_author(name=f"{user} was banned", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user.mention}\n`{user}`", inline=True)
    embed.add_field(name="🪪 User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="⚠️ Warnings", value=f"`{warn_count}/{WARNINGS_BEFORE_BAN}`", inline=True)
    embed.add_field(name="📋 Reason", value=reason[:500], inline=False)
    if channel:
        embed.add_field(name="📍 Channel", value=channel.mention, inline=True)
    embed.add_field(name="📅 Date & Time", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`", inline=True)
    embed.set_footer(text="Anti-Scam Bot • Ban Log")
    return embed

def timeout_embed(user: discord.Member, reason: str, duration_mins: int, channel: discord.TextChannel = None) -> discord.Embed:
    now = datetime.now(timezone.utc)
    embed = discord.Embed(
        title="🔇 User Timed Out",
        color=0xFF8C00,
        timestamp=now
    )
    embed.set_author(name=f"{user} was timed out", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user.mention}\n`{user}`", inline=True)
    embed.add_field(name="🪪 User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="⏱️ Duration", value=f"`{duration_mins} minutes`", inline=True)
    embed.add_field(name="📋 Reason", value=reason[:500], inline=False)
    if channel:
        embed.add_field(name="📍 Channel", value=channel.mention, inline=True)
    embed.add_field(name="📅 Date & Time", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`", inline=True)
    embed.set_footer(text="Anti-Scam Bot • Timeout Log")
    return embed

def scam_delete_embed(user: discord.Member, reason: str, content: str, warn_count: int, channel: discord.TextChannel) -> discord.Embed:
    now = datetime.now(timezone.utc)
    embed = discord.Embed(
        title="🚨 Scam Message Deleted",
        color=0xFFA500,
        timestamp=now
    )
    embed.set_author(name=f"{user}", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user.mention}\n`{user}`", inline=True)
    embed.add_field(name="🪪 User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="⚠️ Warnings", value=f"`{warn_count}/{WARNINGS_BEFORE_BAN}`", inline=True)
    embed.add_field(name="📍 Channel", value=channel.mention, inline=True)
    embed.add_field(name="📋 Reason", value=reason[:500], inline=False)
    if content:
        embed.add_field(name="💬 Message", value=f"```{content[:400]}```", inline=False)
    embed.add_field(name="📅 Date & Time", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`", inline=True)
    embed.set_footer(text="Anti-Scam Bot • Scam Log")
    return embed

def spam_ban_embed(user: discord.Member, reason: str, deleted_count: int) -> discord.Embed:
    now = datetime.now(timezone.utc)
    embed = discord.Embed(
        title="🚫 Spammer Banned",
        color=0x8B0000,
        timestamp=now
    )
    embed.set_author(name=f"{user} was banned for spam flooding", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"`{user}`", inline=True)
    embed.add_field(name="🪪 User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="🗑️ Messages Deleted", value=f"`{deleted_count}`", inline=True)
    embed.add_field(name="📋 Reason", value=f"Spam flood — {reason[:400]}", inline=False)
    embed.add_field(name="📅 Date & Time", value=f"`{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`", inline=True)
    embed.set_footer(text="Anti-Scam Bot • Spam Ban Log")
    return embed

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

    # Profanity check
    profane, prof_reason = has_profanity(content)
    if profane:
        try:
            await message.delete()
            log.info(f"🤬 Deleted profanity from {message.author}")
        except (discord.Forbidden, discord.NotFound):
            pass
        try:
            await message.author.send(
                f"⚠️ **Your message in {message.guild.name} was removed.**\n"
                f"Reason: Profanity. Please keep it clean."
            )
        except discord.Forbidden:
            pass
        await bot.process_commands(message)
        return

    # Banned link check
    has_link, link_reason = has_banned_link(content)
    if has_link:
        await handle_violation(message, link_reason)
        await bot.process_commands(message)
        return

    # Scam check
    if message.attachments and not content.strip():
        await bot.process_commands(message)
        return

    scam, scam_reason = is_scam(content)
    if scam:
        flood = is_spam_flood(message.author.id)
        if flood:
            await handle_spam_flood(message, scam_reason)
        else:
            await handle_violation(message, scam_reason)

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

    try:
        await guild.ban(author, reason=f"Spam flood: {reason}", delete_message_days=1)
        log.info(f"🔨 Instant banned spammer {author}")
        await send_log(guild, spam_ban_embed(author, reason, deleted_count))
        user_scam_times.pop(user_id, None)
        user_warnings.pop(user_id, None)
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning(f"Could not ban {author}: {e}")


async def handle_violation(message: discord.Message, reason: str):
    guild = message.guild
    author = message.author
    user_id = author.id

    try:
        await message.delete()
        log.info(f"🗑️  Deleted from {author} in #{message.channel.name} | {reason}")
    except discord.Forbidden:
        log.warning(f"⚠️  No permission to delete from {author}")
        return
    except discord.NotFound:
        pass

    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warn_count = user_warnings[user_id]

    # Send scam log
    await send_log(guild, scam_delete_embed(author, reason, message.content, warn_count, message.channel))

    # Ban if at threshold
    if WARNINGS_BEFORE_BAN > 0 and warn_count >= WARNINGS_BEFORE_BAN:
        try:
            await author.send(
                f"🔨 **You have been banned from {guild.name}.**\n"
                f"Reason: {warn_count} violations — {reason}"
            )
        except discord.Forbidden:
            pass
        try:
            await guild.ban(author, reason=f"{warn_count} warnings: {reason}", delete_message_days=1)
            log.info(f"🔨 Banned {author} after {warn_count} warnings")
            await send_log(guild, ban_embed(author, reason, warn_count, message.channel))
            user_warnings.pop(user_id, None)
            user_scam_times.pop(user_id, None)
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Could not ban {author}: {e}")
        return

    # DM warning
    try:
        await author.send(
            f"⚠️ **Your message in {guild.name} was removed.**\n"
            f"Reason: {reason}\n"
            f"Warning **{warn_count}/{WARNINGS_BEFORE_BAN}** — continued violations will result in a ban."
        )
    except discord.Forbidden:
        pass

    # Timeout on first offense
    if warn_count == 1 and MUTE_DURATION_MINUTES > 0:
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=MUTE_DURATION_MINUTES)
            await author.timeout(until, reason=reason)
            log.info(f"🔇 Muted {author} for {MUTE_DURATION_MINUTES} minutes")
            await send_log(guild, timeout_embed(author, reason, MUTE_DURATION_MINUTES, message.channel))
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"Could not mute {author}: {e}")

# ─── MOD COMMANDS ─────────────────────────────────────────────────────────────

@bot.command(name="bothelp")
async def bothelp(ctx):
    """Shows all bot commands."""
    embed = discord.Embed(
        title="🛡️ Anti-Scam Bot — Command List",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="⚙️ General", value=(
        "`!bothelp` — Show this menu\n"
        "`!manage` — Bot management panel\n"
        "`!scamcheck <text>` — Test if text gets flagged"
    ), inline=False)
    embed.add_field(name="🔨 Moderation", value=(
        "`!nuke` — Wipe all messages in channel\n"
        "`!warnings @user` — Check warning count\n"
        "`!clearwarnings @user` — Reset warnings"
    ), inline=False)
    embed.add_field(name="🔗 Banned Links", value=(
        "`!addlink example.com` — Ban a domain\n"
        "`!removelink example.com` — Unban a domain\n"
        "`!listlinks` — Show all banned domains"
    ), inline=False)
    embed.add_field(name="🤬 Profanity Filter", value=(
        "`!addword badword` — Add to filter\n"
        "`!removeword badword` — Remove from filter"
    ), inline=False)
    embed.set_footer(text="Requires Manage Messages permission for most commands.")
    await ctx.send(embed=embed)


@bot.command(name="manage")
@commands.has_permissions(manage_messages=True)
async def manage(ctx):
    """Shows bot management panel with current settings."""
    embed = discord.Embed(
        title="⚙️ Anti-Scam Bot — Management Panel",
        color=discord.Color.dark_blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="🔧 Current Settings",
        value=(
            f"**Warnings before ban:** `{WARNINGS_BEFORE_BAN}`\n"
            f"**Timeout duration:** `{MUTE_DURATION_MINUTES} minutes`\n"
            f"**Spam limit:** `{SPAM_MESSAGE_LIMIT} messages in {SPAM_TIME_WINDOW}s`\n"
            f"**Log channel:** {f'<#{LOG_CHANNEL_ID}>' if LOG_CHANNEL_ID else '`Not set`'}"
        ),
        inline=False
    )
    embed.add_field(
        name=f"🔗 Banned Links ({len(BANNED_LINKS)})",
        value="\n".join(f"`{d}`" for d in BANNED_LINKS[:10]) + (f"\n_...and {len(BANNED_LINKS)-10} more_" if len(BANNED_LINKS) > 10 else "") or "`None`",
        inline=False
    )
    embed.add_field(
        name=f"🤬 Profanity Filter ({len(BANNED_WORDS)} words)",
        value="`[hidden for privacy]`",
        inline=False
    )
    embed.add_field(
        name="📋 Commands",
        value=(
            "`!addlink` / `!removelink` / `!listlinks`\n"
            "`!addword` / `!removeword`\n"
            "`!warnings @user` / `!clearwarnings @user`\n"
            "`!nuke` / `!scamcheck <text>`"
        ),
        inline=False
    )
    embed.set_footer(text=f"Requested by {ctx.author} • Anti-Scam Bot")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="scamcheck")
@commands.has_permissions(manage_messages=True)
async def scamcheck(ctx, *, text: str):
    scam, reason = is_scam(text)
    link, link_reason = has_banned_link(text)
    prof, prof_reason = has_profanity(text)
    if scam:
        await ctx.send(f"✅ **Scam flagged.** {reason}")
    elif link:
        await ctx.send(f"✅ **Banned link flagged.** {link_reason}")
    elif prof:
        await ctx.send(f"✅ **Profanity flagged.**")
    else:
        await ctx.send("❌ **Would NOT be flagged.**")

@bot.command(name="clearwarnings")
@commands.has_permissions(kick_members=True)
async def clearwarnings(ctx, member: discord.Member):
    user_warnings.pop(member.id, None)
    await ctx.send(f"✅ Cleared warnings for {member.mention}")

@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    count = user_warnings.get(member.id, 0)
    await ctx.send(f"⚠️ {member.mention} has **{count}** warning(s).")

@bot.command(name="addlink")
@commands.has_permissions(manage_messages=True)
async def addlink(ctx, domain: str):
    domain = domain.lower().strip()
    if domain not in BANNED_LINKS:
        BANNED_LINKS.append(domain)
        await ctx.send(f"✅ Added `{domain}` to banned links.")
    else:
        await ctx.send(f"`{domain}` is already banned.")

@bot.command(name="removelink")
@commands.has_permissions(manage_messages=True)
async def removelink(ctx, domain: str):
    domain = domain.lower().strip()
    if domain in BANNED_LINKS:
        BANNED_LINKS.remove(domain)
        await ctx.send(f"✅ Removed `{domain}` from banned links.")
    else:
        await ctx.send(f"`{domain}` was not in the list.")

@bot.command(name="listlinks")
@commands.has_permissions(manage_messages=True)
async def listlinks(ctx):
    if BANNED_LINKS:
        links = "\n".join(f"• `{d}`" for d in BANNED_LINKS)
        await ctx.send(f"🔗 **Banned links:**\n{links}")
    else:
        await ctx.send("No banned links configured.")

@bot.command(name="addword")
@commands.has_permissions(manage_messages=True)
async def addword(ctx, word: str):
    word = word.lower().strip()
    if word not in BANNED_WORDS:
        BANNED_WORDS.append(word)
        compiled_banned_words.append(re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE))
        await ctx.send(f"✅ Added to profanity filter.")
    else:
        await ctx.send(f"Already in filter.")

@bot.command(name="removeword")
@commands.has_permissions(manage_messages=True)
async def removeword(ctx, word: str):
    word = word.lower().strip()
    if word in BANNED_WORDS:
        BANNED_WORDS.remove(word)
        compiled_banned_words[:] = [re.compile(r'\b' + re.escape(w) + r'\b', re.IGNORECASE) for w in BANNED_WORDS]
        await ctx.send(f"✅ Removed from profanity filter.")
    else:
        await ctx.send(f"Not found in filter.")

@bot.command(name="nuke")
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    channel = ctx.channel
    new_channel = await channel.clone(reason=f"Nuked by {ctx.author}")
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

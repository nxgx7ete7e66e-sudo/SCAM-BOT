"""
Discord Anti-Scam Bot
Detects and removes crypto/gambling scam messages automatically.
Includes spam flood detection - bans users who spam the same message rapidly.
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

# Spam flood: if user sends X+ scam messages within Y seconds = instant ban + bulk delete
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
... (226 lines left)

"""
DR AURA BOT — Configuration
"""

import os
from pathlib import Path

BOT_TOKEN = os.getenv("BOT_TOKEN", "8913522939:AAF1ujxqUywGjK8gnmxbvgjyNyCJSIH_cBU")
OWNER_IDS = [8333953794]  # King Khalid

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "aura.db"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
EMOJI_FILE = DATA_DIR / "premium_emojis.json"

for d in (DATA_DIR, BACKUP_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_WARN_LIMIT = 3
DEFAULT_FLOOD_LIMIT = 5
DEFAULT_FLOOD_WINDOW = 8
MAINTENANCE_MODE = False
PREMIUM_EMOJI_ENABLED = True

BOT_NAME = "Dr Aura"
BOT_USERNAME = "DrAuraBot"
SUPPORT_LINK = "https://t.me/khalid_dev"
VERSION = "1.0.0"

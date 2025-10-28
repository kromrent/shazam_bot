import os
import logging
from pathlib import Path

# env
TG_TOKEN = os.environ.get("TG_BOT_TOKEN")
AUDD_TOKEN = os.environ.get("AUDD_API_TOKEN")
if not TG_TOKEN or not AUDD_TOKEN:
    raise RuntimeError("❌ Укажи TG_BOT_TOKEN и AUDD_API_TOKEN в .env")

# paths
CACHE_DIR = Path("cache")
MP3_DIR = CACHE_DIR / "mp3"
DB_PATH = CACHE_DIR / "cache.db"

FFMPEG = "ffmpeg"

# logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("HybridMusicBot")

def init_dirs():
    CACHE_DIR.mkdir(exist_ok=True)
    MP3_DIR.mkdir(exist_ok=True)

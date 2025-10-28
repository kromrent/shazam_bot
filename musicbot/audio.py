import asyncio
import hashlib
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from .config import FFMPEG

async def tg_download_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Path:
    file = await context.bot.get_file(update.message.video.file_id)
    tmp = Path(tempfile.mkstemp(suffix=".mp4")[1])
    await file.download_to_drive(str(tmp))
    return tmp

async def extract_audio_snip(video_path: Path, start: int = 5, duration: int = 25) -> Path | None:
    """
    Извлекает звуковой фрагмент из видео, удаляет тишину и усиливает громкость.
    По умолчанию — с 5-й секунды длительностью 25 сек.
    """
    snip = video_path.with_suffix(".mp3")

    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-y", "-i", str(video_path),
        "-ss", str(start),            # пропускаем первые 5 сек
        "-t", str(duration),          # вырезаем 25 сек
        "-vn",                        # без видео
        "-ac", "2",                   # 2 канала
        "-ar", "44100",               # частота дискретизации
        "-b:a", "192k",               # битрейт
        "-af", "silenceremove=stop_periods=-1:stop_threshold=-50dB:stop_duration=0.5,volume=2.0",
        str(snip)
    ]

    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()

    # Проверим, что файл не пустой (есть звук)
    if not snip.exists() or snip.stat().st_size < 100_000:
        print(f"⚠️ {snip.name} слишком маленький — возможно, нет аудиодорожки")
        return None

    return snip

def audio_hash(path: Path) -> str:
    """MD5 первых ~200 КБ звука"""
    with open(path, "rb") as f:
        data = f.read(200_000)
    return hashlib.md5(data).hexdigest()

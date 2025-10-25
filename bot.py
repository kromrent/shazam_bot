#!/usr/bin/env python3
import os
import re
import logging
import tempfile
import subprocess
from pathlib import Path
import requests
import asyncio
import yt_dlp

from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
TG_TOKEN = os.environ.get("TG_BOT_TOKEN")
AUDD_TOKEN = os.environ.get("AUDD_API_TOKEN")
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "50"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8080")

# --- Ограничения ---
MAX_INPUT_DURATION = 60           # максимум 1 минута на входящее видео
MAX_TRACK_DURATION = 4.5 * 60     # максимум 4 минуты 30 секунд для оригинала

# --- Регулярки для ссылок ---
YOUTUBE_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/")
TIKTOK_RE = re.compile(r"(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com)/")
REELS_RE = re.compile(r"(https?://)?(www\.)?(instagram\.com/reel)/")

def is_video_url(text: str) -> bool:
    return bool(YOUTUBE_RE.search(text) or TIKTOK_RE.search(text) or REELS_RE.search(text))

# --- Проверка длительности ссылки ---
def get_url_duration(url: str) -> float:
    try:
        ydl_opts = {"quiet": True, "skip_download": True, "cookiefile": "cookies.txt"}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info.get("duration", 0) or 0
    except Exception:
        return 0

# --- Проверка длительности файла ---
def get_file_duration(path: Path) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception:
        return 0

# --- Извлечение аудио из видео ---
def extract_audio(input_path: Path, output_path: Path):
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vn", "-ac", "2", "-ar", "44100",
        "-b:a", "160k", "-codec:a", "libmp3lame",
        str(output_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# --- Скачивание аудио по ссылке ---
def download_from_url(url: str, output_dir: Path) -> Path:
    output_path = output_dir / "audio"
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "nocheckcertificate": True,
        "cookiefile": "cookies.txt",
        "retries": 1,
        "fragment_retries": 1,
        "concurrent_fragment_downloads": 10,
        "noplaylist": True,
        "no_warnings": True,
        "prefer_ffmpeg": True,
        "extractor_args": {"youtube": {"player_skip": "js"}},
        "outtmpl": str(output_path.with_suffix(".%(ext)s")),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "160",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    mp3_files = list(output_dir.glob("*.mp3"))
    if not mp3_files:
        raise Exception("Не удалось скачать аудио")
    return mp3_files[0]

# --- AudD API ---
def recognize_song(audio_path: Path):
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                "https://api.audd.io/",
                data={"api_token": AUDD_TOKEN, "return": "apple_music,spotify,youtube"},
                files={"file": f},
                timeout=15
            )
        data = resp.json()
        if data.get("result"):
            return data
    except Exception as e:
        logger.error(f"AudD API error: {e}")
    return {}

# --- Проверка статуса backend ---
async def wait_for_backend(task_id: str):
    for _ in range(40):  # максимум ~80 сек
        await asyncio.sleep(2)
        try:
            r = requests.get(f"{BACKEND_URL}/status/{task_id}", timeout=10)
            d = r.json()
            if d.get("status") == "ready":
                return f"{BACKEND_URL}/file/{task_id}"
            if d.get("status") == "error":
                raise Exception(d.get("msg", "backend error"))
        except Exception:
            pass
    raise TimeoutError("Backend timeout")

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "🎶 *Empire of Phonk — Music Finder Bot*\n\n"
        "Отправь видео ≤1 мин, голосовое или ссылку — я найду оригинал 🎧"
    )

# --- Основной обработчик ---
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or ""
    file_obj = msg.audio or msg.voice or msg.video or msg.video_note or msg.document

    # --- если прислали ссылку ---
    if text and is_video_url(text):
        url = text.strip()
        dur = get_url_duration(url)
        if dur > MAX_INPUT_DURATION:
            await msg.reply_text("⛔ Видео длиннее 1 минуты — не принимаю.")
            return

        await msg.reply_text("🔗 Загружаю видео по ссылке...")
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            try:
                audio_file = download_from_url(url, td_path)
            except Exception as e:
                await msg.reply_text(f"⚠️ Ошибка при скачивании: {e}")
                return

            await msg.reply_text("🔍 Распознаю песню...")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, recognize_song, audio_file)
            song = result.get("result")
            if not song:
                await msg.reply_text("😔 Не удалось распознать песню.")
                return

            artist, title = song.get("artist", "Неизвестно"), song.get("title", "Неизвестно")
            track_name = f"{artist} - {title}"
            await msg.reply_text(f"✅ Найдено: *{track_name}*\n⏳ Загружаю оригинал ≤4:30...", parse_mode="Markdown")

            try:
                r = requests.get(f"{BACKEND_URL}/download", params={"q": f"{artist} {title} official audio"}, timeout=20)
                task_id = r.json().get("task_id")
                file_url = await wait_for_backend(task_id)
                r_file = requests.get(file_url, timeout=120)
                if not r_file.ok or not r_file.content:
                    raise Exception("backend вернул пустой файл")

                temp_path = td_path / f"{track_name}.mp3"
                with open(temp_path, "wb") as f:
                    f.write(r_file.content)

                with open(temp_path, "rb") as audio_file2:
                    await msg.reply_audio(InputFile(audio_file2, filename=f"{track_name}.mp3"), caption=f"🎧 {track_name}")
            except Exception as e:
                await msg.reply_text(f"❌ Ошибка при скачивании оригинала: {e}")
        return

    # --- если прислан файл ---
    if not file_obj:
        await msg.reply_text("⚠️ Отправь видео, аудио или ссылку.")
        return

    if file_obj.file_size and file_obj.file_size > MAX_FILE_MB * 1024 * 1024:
        await msg.reply_text("📁 Файл слишком большой.")
        return

    if hasattr(file_obj, "duration") and file_obj.duration and file_obj.duration > MAX_INPUT_DURATION:
        await msg.reply_text("⛔ Видео длиннее 1 минуты — не принимаю.")
        return

    await msg.reply_chat_action("upload_audio")
    file = await context.bot.get_file(file_obj.file_id)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        in_path = td_path / "input"
        out_audio = td_path / "audio.mp3"
        await file.download_to_drive(custom_path=str(in_path))

        if get_file_duration(in_path) > MAX_INPUT_DURATION:
            await msg.reply_text("⛔ Видео длиннее 1 минуты — не принимаю.")
            return

        try:
            extract_audio(in_path, out_audio)
        except Exception as e:
            await msg.reply_text(f"Ошибка извлечения аудио: {e}")
            return

        await msg.reply_text("🔍 Распознаю песню...")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, recognize_song, out_audio)
        song = result.get("result")
        if not song:
            await msg.reply_text("😔 Не удалось распознать песню.")
            return

        artist, title = song.get("artist", "Неизвестно"), song.get("title", "Неизвестно")
        track_name = f"{artist} - {title}"
        await msg.reply_text(f"✅ Найдено: *{track_name}*\n⏳ Загружаю оригинал ≤4:30...", parse_mode="Markdown")

        try:
            r = requests.get(f"{BACKEND_URL}/download", params={"q": f"{artist} {title} official audio"}, timeout=20)
            task_id = r.json().get("task_id")
            file_url = await wait_for_backend(task_id)
            r_file = requests.get(file_url, timeout=120)
            if not r_file.ok or not r_file.content:
                raise Exception("backend вернул пустой файл")

            temp_path = td_path / f"{track_name}.mp3"
            with open(temp_path, "wb") as f:
                f.write(r_file.content)

            with open(temp_path, "rb") as audio_file2:
                await msg.reply_audio(InputFile(audio_file2, filename=f"{track_name}.mp3"), caption=f"🎧 {track_name}")
        except Exception as e:
            await msg.reply_text(f"❌ Ошибка при скачивании оригинала: {e}")

# --- main ---
def main():
    if not TG_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN не задан.")
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.AUDIO | filters.VOICE | filters.VIDEO | filters.Document.ALL | filters.VIDEO_NOTE),
        handle_media
    ))
    logger.info("🎧 Bot with URL support started")
    app.run_polling()

if __name__ == "__main__":
    main()

from telegram import Update
from telegram.ext import ContextTypes
from .db import get_by_file_id, get_by_audio_hash, save_track
from .audio import tg_download_video, extract_audio_snip, audio_hash
from .audd import audd_recognize
from .youtube import search_youtube_music, download_mp3, search_youtube_list
import re
from pathlib import Path
from yt_dlp import YoutubeDL
from .config import MP3_DIR
from .db import get_by_url, save_track_url
from .db import get_by_title_or_artist, get_by_url, save_track_url
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import asyncio
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 Отправь видео с музыкой — я распознаю и скачаю MP3!")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    fid = m.video.file_unique_id
    await m.reply_chat_action("typing")

    # 1) Кэш по file_id
    if cached := get_by_file_id(fid):
        await m.reply_text(f"⚡ Из кэша: {cached['artist']} — {cached['title']}")
        await m.reply_audio(audio=open(cached["mp3_path"], "rb"))
        return

    # 2) Скачиваем и извлекаем звук
    video = await tg_download_video(update, context)
    snip = await extract_audio_snip(video)
    if not snip:
        await m.reply_text("⚠️ Не удалось извлечь звук.")
        return

    # 3) Кэш по аудио-хэшу
    ahash = audio_hash(snip)
    if cached := get_by_audio_hash(ahash):
        await m.reply_text(f"⚡ Найдено по звуку: {cached['artist']} — {cached['title']}")
        save_track(fid, ahash, cached["artist"], cached["title"], cached["mp3_path"], "")
        await m.reply_audio(audio=open(cached["mp3_path"], "rb"))
        return

    # 4) AUDD
    await m.reply_text("🎧 Распознаю трек через AUDD...")
    audd = await audd_recognize(snip)
    if not audd:
        await m.reply_text("❌ Не удалось распознать трек.")
        return

    artist = audd.get("artist", "Unknown")
    title  = audd.get("title", "Unknown")
    query = f"{artist} {title} official audio"

    # 5) YouTube
    duration = audd.get("timecode", 0) or audd.get("length", 0)
    vid = search_youtube_music(title, artist, duration)
    if not vid:
        await m.reply_text("⚠️ Не удалось найти трек на YouTube.")
        return

    # 6) MP3
    mp3 = await download_mp3(vid, artist, title)
    if not mp3:
        await m.reply_text("⚠️ Ошибка скачивания MP3.")
        return

    # 7) Сохраняем и отправляем
    save_track(fid, ahash, artist, title, str(mp3), vid)
    await m.reply_text(f"🎶 {artist} — {title}")
    await m.reply_audio(audio=open(mp3, "rb"))
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    url = m.text.strip()

    if not re.match(r'https?://', url):
        return

    await m.reply_chat_action("typing")

    # 🧠 1️⃣ Проверяем кэш по ссылке
    if cached := get_by_url(url):
        await m.reply_text(f"⚡ Из кэша (по ссылке): {cached['artist']} — {cached['title']}")
        await m.reply_audio(audio=open(cached["mp3_path"], "rb"))
        return

    tmp_video = Path("temp_video.mp4")
    snip = None

    try:
        # 2️⃣ Скачиваем видео
        ydl_opts = {
            "format": "mp4",
            "quiet": True,
            "outtmpl": str(tmp_video),
        }
        await asyncio.to_thread(lambda: YoutubeDL(ydl_opts).download([url]))

        # 3️⃣ Извлекаем звук
        snip = await extract_audio_snip(tmp_video)
        if not snip:
            await m.reply_text("⚠️ Не удалось извлечь звук из видео.")
            return

        # 4️⃣ Проверяем кэш по звуку
        ahash = audio_hash(snip)
        if cached := get_by_audio_hash(ahash):
            await m.reply_text(f"⚡ Найдено по звуку: {cached['artist']} — {cached['title']}")
            save_track_url(url, ahash, cached["artist"], cached["title"], cached["mp3_path"], "")
            await m.reply_audio(audio=open(cached["mp3_path"], "rb"))
            return

        # 5️⃣ Распознаём через AUDD
        await m.reply_text("🎧 Распознаю трек через AUDD...")
        audd = await audd_recognize(snip)
        if not audd:
            await m.reply_text("❌ Не удалось распознать трек.")
            return

        artist = audd.get("artist", "Unknown")
        title  = audd.get("title", "Unknown")
        query  = f"{artist} {title} official audio"

        # 6️⃣ Ищем и скачиваем MP3
        duration = audd.get("timecode", 0) or audd.get("length", 0)
        vid = search_youtube_music(title, artist, duration)
        if not vid:
            await m.reply_text("⚠️ Не удалось найти трек на YouTube.")
            return

        mp3 = await download_mp3(vid, artist, title)
        if not mp3:
            await m.reply_text("⚠️ Ошибка при скачивании MP3.")
            return

        # 7️⃣ Сохраняем результат и кэшируем ссылку
        save_track_url(url, ahash, artist, title, str(mp3), vid)
        await m.reply_text(f"🎶 {artist} — {title}")
        await m.reply_audio(audio=open(mp3, "rb"))

    finally:
        # 🧹 Очистка временных файлов
        if tmp_video.exists():
            tmp_video.unlink(missing_ok=True)
        if snip and Path(snip).exists():
            Path(snip).unlink(missing_ok=True)

# временное хранилище выбора (user_id -> список треков)
user_choices = {}

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    query = m.text.strip()

    if re.match(r'https?://', query):
        return

    await m.reply_chat_action("typing")

    # 1️⃣ Ищем на YouTube
    tracks = search_youtube_list(query, limit=10)
    if not tracks:
        await m.reply_text("⚠️ Не удалось найти треки.")
        return

    # сохраняем список для пользователя
    user_choices[m.from_user.id] = tracks

    # 2️⃣ Формируем список для вывода
    text_lines = []
    buttons = []
    for i, t in enumerate(tracks, start=1):
        title = t.get("title", "Без названия")
        try:
            duration = int(float(t.get("duration", 0)))
        except (TypeError, ValueError):
            duration = 0
        mins, secs = divmod(duration, 60)
        text_lines.append(f"{i}. {title} ({mins}:{secs:02d})")
        buttons.append([InlineKeyboardButton(str(i), callback_data=f"choose_{i}")])

    text = "🎶 Найдено несколько треков:\n\n" + "\n".join(text_lines)
    markup = InlineKeyboardMarkup(buttons)

    await m.reply_text(text, reply_markup=markup)
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if not data.startswith("choose_"):
        return

    idx = int(data.split("_")[1]) - 1
    tracks = user_choices.get(user_id)
    if not tracks or idx >= len(tracks):
        await query.edit_message_text("⚠️ Выбор устарел или неверен.")
        return

    chosen = tracks[idx]
    vid = chosen.get("id")
    title = chosen.get("title", "Unknown")
    artist = "Unknown"

    await query.edit_message_text(f"🎧 Скачиваю: {title}...")
    mp3 = await download_mp3(vid, artist, title)
    if not mp3:
        await query.edit_message_text("⚠️ Ошибка при скачивании.")
        return

    await query.message.reply_audio(audio=open(mp3, "rb"), caption=f"🎶 {title}")

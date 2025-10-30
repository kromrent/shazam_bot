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
import time
EXPIRE_TIME = 60


import asyncio
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 Отправь видео с музыкой — я распознаю и скачаю MP3!")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    video = None
    snip = None
    mp3 = None
    user = m.from_user
    username = user.username or user.first_name or "Unknown"

    try:
        await m.reply_chat_action("typing")

        # 1️⃣ Скачиваем и извлекаем звук
        video = await tg_download_video(update, context)
        snip = await extract_audio_snip(video)
        if not snip:
            await m.reply_text("⚠️ Не удалось извлечь звук из видео.")
            return

        # 2️⃣ Проверяем кэш по аудио-хэшу
        ahash = audio_hash(snip)
        if cached := get_by_audio_hash(ahash):
            await m.reply_text(f"⚡ Найдено по звуку: {cached['artist']} — {cached['title']}")
            youtube_url = (
                f"https://www.youtube.com/watch?v={cached.get('youtube_id', '')}"
                if cached.get("youtube_id")
                else ""
            )
            save_track_url(
                url="",
                ahash=ahash,
                artist=cached["artist"],
                title=cached["title"],
                mp3_path=cached["mp3_path"],
                youtube_id=cached.get("youtube_id", ""),
                source_url=youtube_url,
            )
            await m.reply_audio(
                audio=open(cached["mp3_path"], "rb"),
                title=cached["title"],  # ← красивое название без [ID]
                performer=username,
                thumbnail=open("assets/logo1.jpg", "rb")
            )
            return

        # 3️⃣ Распознаём через AUDD
        await m.reply_text("🎧 Распознаю трек через AUDD...")
        audd = await audd_recognize(snip)
        if not audd:
            await m.reply_text("❌ Не удалось распознать трек.")
            return

        artist = audd.get("artist", "Unknown")
        title = audd.get("title", "Unknown")
        duration = audd.get("timecode", 0) or audd.get("length", 0)

        # 4️⃣ Поиск на YouTube
        vid = search_youtube_music(title, artist, duration)
        if not vid:
            await m.reply_text("⚠️ Не удалось найти трек на YouTube.")
            return

        # 5️⃣ Скачиваем MP3
        mp3 = await download_mp3(vid, artist, title)
        if not mp3:
            await m.reply_text("⚠️ Ошибка при скачивании MP3.")
            return

        youtube_url = f"https://www.youtube.com/watch?v={vid}"

        # 6️⃣ Сохраняем результат
        save_track_url(
            url="",
            ahash=ahash,
            artist=artist,
            title=title,
            mp3_path=str(mp3),
            youtube_id=vid,
            source_url=youtube_url,
        )

        # 7️⃣ Отправляем пользователю

        await m.reply_audio(
            audio=open(mp3, "rb"),
            title=title,
            performer=username,
            thumbnail=open("assets/logo1.jpg", "rb"),
        )

    except Exception as e:
        # централизованная обработка всех неожиданных ошибок
        from .config import log
        log.error(f"[handle_video] ❌ Ошибка: {e}", exc_info=True)
        await m.reply_text("⚠️ Произошла непредвиденная ошибка. Попробуй позже.")

    finally:
        # 8️⃣ Очистка всех временных файлов
        cleanup_files(video, snip, mp3)

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    url = m.text.strip()
    user = m.from_user
    username = user.username or user.first_name or "Unknown"

    if not re.match(r'https?://', url):
        return

    await m.reply_chat_action("typing")

    # 🧠 1️⃣ Проверяем кэш по ссылке
    if cached := get_by_url(url):
        await m.reply_text(f"⚡ Из кэша (по ссылке): {cached['artist']} — {cached['title']}")
        await m.reply_audio(
            audio=open(cached["mp3_path"], "rb"),
            title=cached["title"],  # ← красивое название без [ID]
            performer=username,
            thumbnail=open("assets/logo1.jpg", "rb")
        )
        return
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
            save_track_url(url, ahash, cached["artist"], cached["title"], cached["mp3_path"], "", "")
            await m.reply_audio(
                audio=open(cached["mp3_path"], "rb"),
                title=cached["title"],  # ← красивое название без [ID]
                performer=username,
                thumbnail=open("assets/logo1.jpg", "rb")
            )
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
        print(vid)
        youtube_url = f"https://www.youtube.com/watch?v={vid}"

        # 7️⃣ Сохраняем результат и кэшируем ссылку
        save_track_url(url, ahash, artist, title, str(mp3), vid, youtube_url)
        await m.reply_text(f"🎶 {artist} — {title}")
        await m.reply_audio(
            audio=open(mp3, "rb"),
            title=title,
            performer=username,
            thumbnail=open("assets/logo1.jpg", "rb"),
        )

    finally:
        cleanup_files(tmp_video, snip)
# временное хранилище выбора (user_id -> список треков)
user_choices = {}

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    query = m.text.strip()

    if re.match(r'https?://', query):
        return

    await m.reply_chat_action("typing")

    # 1️⃣ Ищем треки
    tracks = search_youtube_list(query, limit=10)
    if not tracks:
        await m.reply_text("⚠️ Не удалось найти треки.")
        return

    # 2️⃣ Сохраняем выбор
    user_choices[m.from_user.id] = {
        "tracks": tracks,
        "timestamp": time.time(),
        "message_id": None,
    }

    # 3️⃣ Формируем текст и кнопки
    text_lines = []
    buttons = []
    for i, t in enumerate(tracks, start=1):
        title = t.get("title", "Без названия")
        duration = int(float(t.get("duration", 0) or 0))
        mins, secs = divmod(duration, 60)
        text_lines.append(f"{i}. {title} ({mins}:{secs:02d})")
        buttons.append([InlineKeyboardButton(str(i), callback_data=f"choose_{i}")])

    text = "🎶 Найдено несколько треков:\n\n" + "\n".join(text_lines)
    markup = InlineKeyboardMarkup(buttons)

    msg = await m.reply_text(text, reply_markup=markup)
    user_choices[m.from_user.id]["message_id"] = msg.message_id

    # 4️⃣ Запускаем таймер удаления в фоне
    asyncio.create_task(delete_message_later(context, m.chat_id, msg.message_id, m.from_user.id))


async def delete_message_later(context, chat_id, message_id, user_id):
    """Удаляет сообщение через EXPIRE_TIME секунд"""
    await asyncio.sleep(EXPIRE_TIME)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        user_choices.pop(user_id, None)
    except Exception:
        pass

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    user = query.from_user
    username = user.username or user.first_name or "Unknown"


    if not data.startswith("choose_"):
        return

    user_data = user_choices.get(user_id)
    if not user_data:
        await query.edit_message_text("⚠️ Выбор устарел.")
        return

    # проверяем время жизни
    if time.time() - user_data["timestamp"] > EXPIRE_TIME:
        await query.edit_message_text("⚠️ Время выбора истекло.")
        user_choices.pop(user_id, None)
        return

    tracks = user_data["tracks"]
    idx = int(data.split("_")[1]) - 1
    if idx < 0 or idx >= len(tracks):
        await query.edit_message_text("⚠️ Неверный выбор.")
        return

    chosen = tracks[idx]
    vid = chosen.get("id")
    title = chosen.get("title", "Unknown")
    artist = "Unknown"
    youtube_url = f"https://www.youtube.com/watch?v={vid}"

    await query.message.reply_text(f"🎧 Скачиваю: {title}...")

    mp3 = await download_mp3(vid, artist, title)
    if not mp3:
        await query.message.reply_text("⚠️ Ошибка при скачивании.")
        return

    # 🔥 Сохраняем в базу
    from .audio import audio_hash
    ahash = audio_hash(mp3)
    save_track_url(
        url=None,  # пользовательского URL нет
        ahash=ahash,
        artist=artist,
        title=title,
        mp3_path=str(mp3),
        youtube_id=vid,
        source_url=youtube_url  # сохраняем только источник
    )

    await query.message.reply_audio(
        audio=open(mp3, "rb"),
        title=title,  # 🎵 Название трека (в плеере)
        performer=username,  # 👤 Имя пользователя как “исполнитель”
        thumbnail=open("assets/logo1.jpg", "rb")
    )


def cleanup_files(*paths: Path):
    for p in paths:
        if p and p.exists():
            p.unlink(missing_ok=True)
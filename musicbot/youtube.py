import asyncio
import re
from pathlib import Path
from yt_dlp import YoutubeDL
from .config import MP3_DIR, log

COOKIES_FILE = Path(__file__).parent / "cookies.txt"
MAX_VIDEO_DURATION = 300  # максимум 5 минут

# === Поиск оригинального или популярного трека ===
def search_youtube_music(title: str, artist: str, duration: int | None = None) -> str | None:
    """Поиск трека на YouTube с приоритетом оригинальных и коротких видео."""
    query = f"{artist} {title}".strip()
    ydl_opts = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "default_search": "ytsearch20",
    }

    if COOKIES_FILE.exists():
        ydl_opts["cookiefile"] = str(COOKIES_FILE)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception as e:
        print(f"[YouTube] ❌ Ошибка поиска: {e}")
        return None

    entries = info.get("entries", [])
    if not entries:
        print("[YouTube] ⚠️ Результатов нет.")
        return None

    # --- 1. Фильтрация мусора (но оставляем slowed/sped up) ---
    filtered = []
    for v in entries:
        title_l = v.get("title", "").lower()
        dur = v.get("duration") or 0

        # исключаем нежелательные типы
        if re.search(r"(remix|edit|cover|nightcore|8d|live|extended)", title_l):
            continue

        # исключаем длинные (>5 мин)
        if dur == 0 or dur > MAX_VIDEO_DURATION:
            continue

        filtered.append(v)
        print(f"[YouTube] ✅ Допущено: {v.get('title')} ({dur}s)")

    if not filtered:
        print("[YouTube] ⚠️ Подходящих видео ≤5 мин не найдено.")
        return None

    # --- 2. Приоритезация ---
    def score(video):
        title_l = video.get("title", "").lower()
        uploader = video.get("uploader", "").lower()
        dur = video.get("duration") or 0
        s = 0

        # приоритет каналов
        if "topic" in uploader or "official" in uploader or "vevo" in uploader:
            s -= 10

        # совпадение артиста
        if artist and artist.lower() in title_l:
            s -= 5

        # совпадение по длительности
        if duration:
            try:
                s += abs(int(dur) - int(duration))
            except Exception:
                pass

        return s

    best = sorted(filtered, key=score)[0]
    print(f"[YouTube] 🎯 Выбран: {best.get('title')} ({best.get('uploader')}, {best.get('duration')}s)")
    return best.get("id")


# === Загрузка mp3 ===
async def download_mp3(video_id: str, artist: str, title: str) -> Path | None:
    """Скачивает трек в mp3, ограничивая битрейт и проверяя размер."""
    safe_title = f"{artist} - {title}".strip().replace("/", "_").replace("\\", "_")
    dst = MP3_DIR / f"{safe_title}.mp3"
    if dst.exists():
        print(f"[Cache] ⚡ Уже есть: {dst.name}")
        return dst

    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "outtmpl": str(MP3_DIR / f"{safe_title}.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "postprocessor_args": ["-b:a", "192k"],  # ограничиваем битрейт
    }

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: YoutubeDL(ydl_opts).download([f"https://www.youtube.com/watch?v={video_id}"])
        )
        if dst.exists():
            size_mb = dst.stat().st_size / 1024 / 1024
            if size_mb > 50:
                print(f"[YouTube] ⚠️ Файл слишком большой ({size_mb:.1f} МБ) — удалён.")
                dst.unlink(missing_ok=True)
                return None
            print(f"[YouTube] 💾 Скачано: {dst.name} ({size_mb:.1f} МБ)")
            return dst
        print("[YouTube] ⚠️ Файл не найден после загрузки.")
        return None
    except Exception as e:
        log.error(f"[YouTube] ❌ Ошибка загрузки: {e}")
        return None
def search_youtube_list(query: str, limit: int = 10) -> list[dict]:
    """Поиск YouTube с приоритетом официальных и лейблов (включая 'Provided to YouTube')."""

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": True,
        "default_search": "ytsearch20",
        "force_generic_extractor": True,
    }

    if COOKIES_FILE.exists():
        ydl_opts["cookiefile"] = str(COOKIES_FILE)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch20:{query}", download=False)
    except Exception as e:
        print(f"[YouTube] ❌ Ошибка поиска: {e}")
        return []

    entries = info.get("entries") if isinstance(info, dict) else None
    if not entries:
        print("[YouTube] ⚠️ Пустые результаты поиска")
        return []

    results = []
    for v in entries:
        if not isinstance(v, dict):
            continue

        url = v.get("url") or v.get("webpage_url")
        title = v.get("title", "")
        duration = v.get("duration") or 0
        uploader = (v.get("uploader") or "").lower()

        if not url or not title:
            continue
        if duration < 30 or duration > MAX_VIDEO_DURATION:
            continue
        if "shorts" in url.lower() or "shorts" in title.lower():
            continue

        # 💿 Расставляем приоритеты
        priority = 0

        # 1️⃣ Каналы лейблов и дистрибьюторов
        if any(word in uploader for word in ["vevo", "records", "label", "music", "official"]):
            priority += 10

        # 2️⃣ Provided to YouTube (Topic-каналы)
        if " - topic" in uploader:
            priority += 15  # самый высокий приоритет

        # 3️⃣ Название содержит official audio/video
        if "official" in title.lower() or "audio" in title.lower():
            priority += 5

        # 4️⃣ Наоборот — искусственные ремиксы / slowed / sped up — понижаем
        if any(bad in title.lower() for bad in ["remix", "slowed", "sped up", "nightcore", "8d"]):
            priority -= 10

        v["_priority"] = priority
        results.append(v)

    # 📊 Сортировка по приоритету
    results.sort(key=lambda x: x.get("_priority", 0), reverse=True)

    return results[:limit]
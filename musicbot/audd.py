import aiohttp
import time
from pathlib import Path
from .config import AUDD_TOKEN, log

async def audd_recognize(mp3_path: Path):
    url = "https://api.audd.io/"
    start_time = time.time()

    try:
        size = mp3_path.stat().st_size
        log.info(f"[AUDD] ▶ Отправляю файл '{mp3_path.name}' ({size / 1024:.1f} KB) на распознавание...")

        async with aiohttp.ClientSession() as s:
            with open(mp3_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("api_token", AUDD_TOKEN)
                form.add_field("file", f, filename=mp3_path.name, content_type="audio/mpeg")
                async with s.post(url, data=form, timeout=20) as r:
                    text = await r.text()
                    try:
                        js = await r.json()
                    except Exception:
                        log.error(f"[AUDD] ❌ Ошибка парсинга JSON: {text}")
                        return None

        duration = time.time() - start_time
        log.info(f"[AUDD] ⏱ Ответ за {duration:.2f} сек. Статус: {js.get('status')}")

        if js.get("status") != "success":
            log.warning(f"[AUDD] ⚠ Статус {js.get('status')}, ответ: {js}")
            return None

        if not js.get("result"):
            log.warning(f"[AUDD] ❌ Нет результата: {js}")
            return None

        result = js["result"]
        log.info(f"[AUDD] ✅ Распознан: {result.get('artist')} — {result.get('title')}")
        return result

    except Exception as e:
        log.error(f"[AUDD] 💥 Ошибка при обращении к API: {e}")
        return None

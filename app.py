from flask import Flask, request, send_file, jsonify
import yt_dlp
import tempfile
from pathlib import Path
import os
import threading
import time
import shutil

app = Flask(__name__)
tasks = {}
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

def download_track(task_id, query):
    try:
        # --- проверяем кэш ---
        cached_file = CACHE_DIR / f"{query}.mp3"
        if cached_file.exists():
            tasks[task_id] = {"status": "ready", "file": str(cached_file)}
            return

        td = tempfile.mkdtemp()
        td_path = Path(td)
        output_path = td_path / "track"

        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "nocheckcertificate": True,
            "outtmpl": str(output_path.with_suffix(".%(ext)s")),
            "cookiefile": "cookies.txt",
            "socket_timeout": 10,
            "retries": 2,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 10,
            "noprogress": True,
            "no_warnings": True,
            "prefer_ffmpeg": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            },
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "160",  # 🔹 немного меньше, быстрее
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])

        mp3_files = list(td_path.glob("*.mp3"))
        if not mp3_files:
            tasks[task_id] = {"status": "error", "msg": "no mp3 found"}
            shutil.rmtree(td_path, ignore_errors=True)
            return

        mp3_file = mp3_files[0]
        shutil.move(mp3_file, cached_file)
        tasks[task_id] = {"status": "ready", "file": str(cached_file)}

    except Exception as e:
        tasks[task_id] = {"status": "error", "msg": str(e)}

@app.route("/download", methods=["GET"])
def start_download():
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "missing query"}), 400

    task_id = str(int(time.time() * 1000))
    tasks[task_id] = {"status": "pending"}

    threading.Thread(target=download_track, args=(task_id, query), daemon=True).start()
    return jsonify({"task_id": task_id, "status": "pending"})

@app.route("/status/<task_id>")
def get_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "not found"}), 404
    return jsonify(task)

@app.route("/file/<task_id>")
def get_file(task_id):
    task = tasks.get(task_id)
    if not task or task.get("status") != "ready":
        return jsonify({"error": "not ready"}), 400

    path = Path(task["file"])
    if not path.exists():
        return jsonify({"error": "file missing"}), 404

    return send_file(path, as_attachment=True, download_name=f"{task_id}.mp3")

if __name__ == "__main__":
    print("🚀 Ultra-fast backend started on http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)

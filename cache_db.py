import sqlite3
from pathlib import Path

DB_PATH = Path("cache/cache.db")
DB_PATH.parent.mkdir(exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id TEXT PRIMARY KEY,
            artist TEXT,
            title TEXT,
            mp3_path TEXT,
            youtube_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_track(track_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT artist, title, mp3_path, youtube_id FROM tracks WHERE id=?", (track_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"artist": row[0], "title": row[1], "mp3_path": row[2], "youtube_id": row[3]}

def save_track(track_id: str, artist: str, title: str, mp3_path: str, youtube_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO tracks (id, artist, title, mp3_path, youtube_id)
        VALUES (?, ?, ?, ?, ?)
    """, (track_id, artist, title, mp3_path, youtube_id))
    conn.commit()
    conn.close()

import sqlite3
from typing import Optional, Dict
from .config import DB_PATH
import unicodedata
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            url TEXT,
            audio_hash TEXT,
            artist TEXT,
            title TEXT,
            mp3_path TEXT,
            youtube_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audio_hash ON tracks(audio_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_url ON tracks(url)")
    conn.commit()
    conn.close()

def get_by_file_id(fid: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT artist, title, mp3_path FROM tracks WHERE file_id=?", (fid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"artist": row[0], "title": row[1], "mp3_path": row[2]}

def get_by_audio_hash(ahash: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT artist, title, mp3_path FROM tracks WHERE audio_hash=?", (ahash,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"artist": row[0], "title": row[1], "mp3_path": row[2]}

def save_track(fid: str, ahash: str, artist: str, title: str, mp3_path: str, youtube_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO tracks (file_id, audio_hash, artist, title, mp3_path, youtube_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (fid, ahash, artist, title, mp3_path, youtube_id))
    conn.commit()
    conn.close()
def get_by_url(url: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT artist, title, mp3_path FROM tracks WHERE url=?", (url,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"artist": row[0], "title": row[1], "mp3_path": row[2]}

def save_track_url(url: str, ahash: str, artist: str, title: str, mp3_path: str, youtube_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO tracks (url, audio_hash, artist, title, mp3_path, youtube_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (url, ahash, artist, title, mp3_path, youtube_id))
    conn.commit()
    conn.close()
def normalize(s: str) -> str:
    """Удаляет диакритику и приводит строку к нижнему регистру."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def get_by_title_or_artist(query: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    q = f"%{normalize(query)}%"
    cur.execute("""
        SELECT artist, title, mp3_path FROM tracks
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Фильтруем в Python (чтобы учесть нормализацию)
    for r in rows:
        t = normalize(r["title"])
        a = normalize(r["artist"])
        if q.strip('%') in t or q.strip('%') in a:
            return r
    return None

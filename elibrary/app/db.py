import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def cursor():
    conn = connect()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def init_db():
    with cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                sort_key TEXT NOT NULL,
                filename TEXT NOT NULL,
                filetype TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                pages INTEGER,
                cover TEXT,
                lang TEXT DEFAULT 'hi',
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_books_sort ON books(sort_key)")


def upsert_book(row: dict):
    with cursor() as cur:
        cur.execute(
            """INSERT INTO books (id, title, sort_key, filename, filetype, file_path, file_size, pages, cover, lang)
               VALUES (:id, :title, :sort_key, :filename, :filetype, :file_path, :file_size, :pages, :cover, :lang)
               ON CONFLICT(id) DO UPDATE SET
                 title=:title, sort_key=:sort_key, filename=:filename, filetype=:filetype,
                 file_path=:file_path, file_size=:file_size, pages=:pages, cover=:cover, lang=:lang""",
            row,
        )


def get_book(book_id: str) -> sqlite3.Row | None:
    with cursor() as cur:
        return cur.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()


def all_books() -> list[sqlite3.Row]:
    with cursor() as cur:
        return cur.execute("SELECT * FROM books ORDER BY sort_key").fetchall()


def book_count() -> int:
    with cursor() as cur:
        return cur.execute("SELECT COUNT(*) AS n FROM books").fetchone()["n"]


def catalog_is_valid() -> bool:
    valid = 0
    with cursor() as cur:
        for row in cur.execute("SELECT file_path FROM books").fetchall():
            try:
                if Path(row["file_path"]).exists():
                    valid += 1
                else:
                    return False
            except Exception:
                return False
    return valid > 0


def remove_missing(valid_ids: set[str]):
    with cursor() as cur:
        cur.execute("SELECT id FROM books")
        for row in cur.fetchall():
            if row["id"] not in valid_ids:
                cur.execute("DELETE FROM books WHERE id=?", (row["id"],))
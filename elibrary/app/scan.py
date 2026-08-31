import hashlib
import re
import subprocess
from pathlib import Path

from . import db
from .config import ALLOWED_EXTS, CONTENT_DIR, COVERS_DIR, MIN_FILE_BYTES


def norm_title(stem: str) -> str:
    s = stem.strip().replace("_", " ")
    if re.search(r"[\u0900-\u097F]", s):
        return re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+", " ", s).strip().title()


def file_id(filename: str) -> str:
    return hashlib.md5(filename.encode("utf-8")).hexdigest()[:12]


def valid_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(5)[:4] == b"%PDF"
    except Exception:
        return False


def valid_epub(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(4)
        return head == b"PK\x03\x04" or head == b"PK\x05\x06"
    except Exception:
        return False


def pdf_pages(path: Path) -> int | None:
    try:
        out = subprocess.run(
            ["pdfinfo", str(path)], capture_output=True, text=True, timeout=30
        )
        for line in out.stdout.splitlines():
            if line.lower().startswith("pages"):
                return int(re.search(r"\d+", line).group())
    except Exception:
        return None
    return None


def make_cover(book_id: str, path: Path) -> str | None:
    try:
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        base = COVERS_DIR / ("tmp_" + book_id)
        subprocess.run(
            ["pdftoppm", "-jpeg", "-f", "1", "-l", "1", "-scale-to", "900", str(path), str(base)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        pages = sorted(COVERS_DIR.glob(f"tmp_{book_id}*.jpg"))
        if not pages:
            return None
        target = COVERS_DIR / f"{book_id}.jpg"
        pages[0].replace(target)
        for p in pages[1:]:
            p.unlink(missing_ok=True)
        return target.name
    except Exception:
        for p in COVERS_DIR.glob(f"tmp_{book_id}*.jpg"):
            p.unlink(missing_ok=True)
        return None


def scan() -> dict:
    if not CONTENT_DIR.exists():
        raise FileNotFoundError(f"content dir missing: {CONTENT_DIR}")
    db.init_db()
    files = sorted(CONTENT_DIR.iterdir())
    found, added = [], 0
    for path in files:
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTS:
            continue
        if path.stat().st_size < MIN_FILE_BYTES:
            continue
        if ext == ".pdf" and not valid_pdf(path):
            continue
        if ext == ".epub" and not valid_epub(path):
            continue
        found.append(path)
        bid = file_id(path.name)
        title = norm_title(path.stem)
        existing = db.get_book(bid)
        row = {
            "id": bid,
            "title": title,
            "sort_key": title,
            "filename": path.name,
            "filetype": ext.lstrip("."),
            "file_path": str(path.resolve()),
            "file_size": path.stat().st_size,
            "pages": pdf_pages(path) if ext == ".pdf" else None,
            "cover": existing["cover"] if existing and existing["cover"] else None,
            "lang": "hi" if re.search(r"[\u0900-\u097F]", title) else "en",
        }
        if row["cover"] is None and ext == ".pdf":
            row["cover"] = make_cover(bid, path)
        db.upsert_book(row)
        added += 1
    db.remove_missing({file_id(p.name) for p in found})
    return {"scanned": len(found), "upserted": added}
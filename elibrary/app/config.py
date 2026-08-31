import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = BASE_DIR / "content"
COVERS_DIR = BASE_DIR / "covers"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "catalog.db"
STATIC_DIR = BASE_DIR / "static"
VENDOR_DIR = STATIC_DIR / "vendor"
SECRET_FILE = DATA_DIR / "secret.key"

APP_NAME = "Sushant Kumar eLibrary"
DEV = "Sushant Kumar"
MIN_FILE_BYTES = 50000
ALLOWED_EXTS = {".pdf", ".epub", ".txt", ".mobi"}


def load_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_FILE.write_text(key)
    return key


SECRET_KEY = load_secret()
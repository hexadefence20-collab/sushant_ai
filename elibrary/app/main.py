from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db, scan, tokens
from .config import APP_NAME, COVERS_DIR, STATIC_DIR, VENDOR_DIR

app = FastAPI(title=APP_NAME, docs_url="/api/docs", openapi_url="/api/openapi.json")

STREAM_TTL = 3600
RENDER_TTL = 30
BLOCKED_HDRS = {"sec-fetch-dest"}


@app.on_event("startup")
def on_startup():
    db.init_db()
    # If a validated catalog already exists on disk (e.g. baked into the image
    # for ephemeral platforms), reuse it instead of re-scanning + regenerating
    # covers on every startup. Otherwise scan content/ from scratch.
    if not db.catalog_is_valid() or db.book_count() == 0:
        scan.scan()


@app.get("/")
def home():
    return RedirectResponse(url="/app")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME}


@app.get("/api/novels")
def novels():
    books = db.all_books()
    return [
        {
            "id": b["id"],
            "title": b["title"],
            "filetype": b["filetype"],
            "size": b["file_size"],
            "pages": b["pages"],
            "cover": b["cover"],
            "lang": b["lang"],
        }
        for b in books
    ]


@app.get("/api/novels/{book_id}")
def novel_detail(book_id: str):
    b = db.get_book(book_id)
    if not b:
        raise HTTPException(status_code=404, detail="Book not found")
    return {
        "id": b["id"],
        "title": b["title"],
        "filetype": b["filetype"],
        "size": b["file_size"],
        "pages": b["pages"],
        "cover": b["cover"],
        "lang": b["lang"],
    }


@app.post("/api/read/{book_id}/ticket")
def open_ticket(book_id: str, request: Request):
    b = db.get_book(book_id)
    if not b:
        raise HTTPException(status_code=404, detail="Book not found")
    ip = request.client.host
    base = {"bid": book_id, "ip": ip, "ua": request.headers.get("user-agent", "")[:80]}
    return {
        "token": tokens.issue_token(base, ttl=RENDER_TTL),
        "stream": tokens.issue_token(base, ttl=STREAM_TTL),
        "ttl": STREAM_TTL,
    }


def _authorized(request: Request, raw: str | None, book_id: str) -> bool:
    if not raw:
        return False
    payload = tokens.verify_token(raw)
    if not payload:
        return False
    if payload.get("bid") != book_id:
        return False
    if payload.get("ip") != request.client.host:
        return False
    ua = request.headers.get("user-agent", "")[:80]
    if payload.get("ua") != ua:
        return False
    if request.headers.get("sec-fetch-dest") == "document":
        return False
    return True


@app.get("/api/read/{book_id}/stream")
def stream_book(book_id: str, request: Request, tk: str | None = None):
    if not _authorized(request, tk, book_id):
        raise HTTPException(status_code=403, detail="Unauthorized")
    b = db.get_book(book_id)
    path = Path(b["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")
    media = {
        "pdf": "application/pdf",
        "epub": "application/epub+zip",
        "txt": "text/plain; charset=utf-8",
        "mobi": "application/octet-stream",
    }.get(b["filetype"], "application/octet-stream")
    headers = {
        "Content-Disposition": "inline",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(path, media_type=media, headers=headers)


@app.get("/covers/{name}")
def cover(name: str):
    f = COVERS_DIR / name
    if not f.exists():
        raise HTTPException(status_code=404)
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")
app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if "/api/read" not in request.url.path:
        resp.headers["Cache-Control"] = "no-cache"
    return resp
#!/usr/bin/env python3
"""
smart_download.py - High-quality Hindi novel downloader.
Preference order:
  1. Internet Archive exact-title search (identifier/title match)
  2. Tavily web search (direct files / scraped links)
Downloads are validated by extracting text from PDFs (Devanagari ratio)
and by requiring the novel title to appear in HTML/text captures.
"""

import concurrent.futures
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient

try:
    from config import TAVILY_API_KEY, REQUEST_TIMEOUT
except Exception:
    TAVILY_API_KEY = "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"
    REQUEST_TIMEOUT = 30

OUT_DIR = Path("hindi_novels")
JOURNAL = Path("download_journal.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
JUNK_DOMAINS = ("play.google.com", "amazon.", "updatestar", "collegedunia", "facebook.com",
                "pinterest", "testbook.com", "youtube.com", "instagram.com", "twitter.com",
                "tamilbookspdf", "toppersexam", "apple.com", "soft112", "bookey", "aajtak")
FILE_EXTS = (".pdf", ".epub", ".mobi", ".doc", ".docx", ".txt", ".html", ".htm")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("smart_download.log", encoding="utf-8")])
log = logging.getLogger("smart")

_sess = requests.Session()
_sess.headers.update({"User-Agent": UA})


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s.lower())


def dev_count(s: str) -> int:
    return len(re.findall(r"[\u0900-\u097F]", s))


def latin_count(s: str) -> int:
    return len(re.findall(r"[A-Za-z]", s))


def load_journal():
    if JOURNAL.exists():
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    return {}


def save_journal(j):
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|#]', "_", name.strip())
    return re.sub(r"\s+", " ", name)[:150]


def pdf_text(pdf_path: Path, maxchars: int = 3000) -> str:
    try:
        out = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", "ignore")[:maxchars]
    except Exception:
        return ""


def pdf_is_hindi(pdf_path: Path, title_hint: str) -> bool:
    if not pdf_path.exists() or pdf_path.stat().st_size < 20000:
        return False
    txt = pdf_text(pdf_path)
    if txt.strip():
        dc = dev_count(txt)
        lc = latin_count(txt)
        if dc >= 100 and (lc == 0 or dc / max(lc, 1) >= 0.6):
            return True
        if title_hint and norm(title_hint) in norm(txt) and dc >= 40:
            return True
        return False
    return None  # scanned, no text layer -> undecided


def download_binary(url: str, dest: Path) -> bool:
    try:
        r = _sess.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return dest.stat().st_size > 20000
    except Exception:
        return False


# ---------------- Internet Archive search ----------------

def archive_search(title: str, rows: int = 12) -> list:
    docs = []
    for q in (f'title:"{title}" AND mediatype:texts', f'"{title}" AND mediatype:texts'):
        try:
            r = _sess.get("https://archive.org/advancedsearch.php", params={
                "q": q, "fl[]": ["identifier", "title", "language"],
                "rows": rows, "page": 1, "output": "json"}, timeout=45)
            docs += r.json()["response"]["docs"]
        except Exception as exc:
            log.debug("archive search failed %r: %s", title, exc)
        time.sleep(0.4)
    # score results: title similarity + hindi presence
    scored = []
    seen = set()
    tn = norm(title)
    for d in docs:
        ident = d.get("identifier", "")
        if ident in seen:
            continue
        seen.add(ident)
        dtitle = d.get("title", "") or ident
        dt = norm(dtitle)
        tset = set(title.replace(":", " ").split())
        dset = set(dtitle.replace(":", " ").split())
        overlap = len(tset & dset) / max(len(tset), 1)
        contains = tn in dt or (len(tn) > 3 and dt in tn)
        lang = " ".join(d.get("language", [])) if isinstance(d.get("language"), list) else str(d.get("language", ""))
        hindi = ("hin" in lang or "hi" in lang) or re.search(r"[\u0900-\u097F]", dtitle)
        if not (contains or overlap >= 0.5):
            continue
        scored.append((overlap + (1 if hindi else 0), contains, ident, dtitle))
    # prefer explicit contains matches
    scored.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return [(s, i, t) for s, c, i, t in scored]


def archive_files(item: str) -> list:
    try:
        meta = _sess.get(f"https://archive.org/metadata/{item}", timeout=45).json()
        return meta.get("files", [])
    except Exception:
        return []


def file_priority(name: str) -> int:
    ln = name.lower()
    if ln.endswith(".pdf"):
        return 0
    if ln.endswith(".epub"):
        return 1
    if ln.endswith(".mobi"):
        return 2
    if ln.endswith((".txt", ".djvu")):
        return 3
    return 9


def try_archive(novel: str) -> bool:
    dest = None
    for score, item, dtitle in archive_search(novel)[:8]:
        files = [f for f in archive_files(item) if f.get("name") and not f["name"].startswith(("_", "@"))]
        files.sort(key=lambda f: file_priority(f["name"]))
        for f in files:
            fname = f["name"]
            ext = Path(fname).suffix.lower()
            if ext not in (".pdf", ".epub", ".mobi", ".txt", ".djvu"):
                continue
            url = f"https://archive.org/download/{item}/" + fname.replace(" ", "%20")
            dest = OUT_DIR / f"{sanitize(novel)}{'.txt' if ext=='.djvu' else ext}"
            log.info("    ar.org item %s -> %s", item, fname)
            if not download_binary(url, dest):
                continue
            verdict = pdf_is_hindi(dest, novel) if ext == ".pdf" else None
            if verdict is False:
                dest.unlink(missing_ok=True)
                continue
            if ext in (".epub", ".mobi", ".txt", ".djvu") and dest.stat().st_size < 50000:
                dest.unlink(missing_ok=True)
                continue
            log.info("  DOWNLOADED %s -> %s (%d bytes)", novel, dest.name, dest.stat().st_size)
            return True
        time.sleep(0.3)
    if dest and dest.exists():
        dest.unlink(missing_ok=True)
    return False


# ---------------- Tavily fallback ----------------

def tavily_search(query: str, max_result: int = 8):
    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        return client.search(query=query, search_depth="advanced", max_results=max_result, include_answer=True)
    except Exception as exc:
        log.warning("tavily error: %s", exc)
        return {"results": []}


def save_html(url: str, dest: Path, novel: str) -> bool:
    try:
        r = _sess.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if any(j in url for j in JUNK_DOMAINS):
            return False
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        dc = dev_count(text)
        if len(text) < 5000 or dc < 400:
            return False
        if novel and norm(novel) not in norm(text):
            return False
        dest.write_text(f"<!-- source: {url} -->\n" + text, encoding="utf-8")
        return True
    except Exception:
        return False


def text_ok(text: str, novel: str) -> bool:
    dc = dev_count(text)
    if dc < 300:
        return False
    lc = latin_count(text)
    if lc and dc / max(lc, 1) < 0.5:
        return False
    if novel and norm(novel) not in norm(text):
        return False
    return True


def try_tavily(novel: str) -> bool:
    queries = [
        f'"{novel}" pdf free download hindi',
        f"{novel} उपन्यास pdf पुस्तक मुफ्त",
        f"{novel} queue:epustakalay archive.org",
        f'"{novel}" hindikahani hindi-kavita upanyas',
        f"{novel} book full text hindi",
    ]
    tried = set()
    for q in queries:
        log.info("    tavily: %s", q)
        res = tavily_search(q)
        pages = []
        for r in res.get("results", []):
            u = r.get("url", "")
            if not u or any(j in u for j in JUNK_DOMAINS):
                continue
            pl = u.lower().split("?")[0]
            if pl.endswith(FILE_EXTS) or "archive.org" in u or "epustakalay" in u or "hindikahani" in u:
                pages.append(u)
            content = str(r.get("content", ""))
            for m in re.finditer(r"https?://[^\s<>\"']+\.(?:pdf|epub|txt|mobi)(?:\?[^\s<>\"']*)?", content):
                pages.append(m.group(0))
        # direct candidates first
        direct = [p for p in pages if urlparse(p).path.lower().endswith(FILE_EXTS)]
        for p in direct + pages:
            if p in tried:
                continue
            tried.add(p)
            ext = Path(urlparse(p).path.lower()).suffix
            ext = ext if ext in (".pdf", ".epub", ".mobi", ".doc", ".docx", ".txt") else (".pdf" if ".pdf" in p.lower() else ".html")
            dest = OUT_DIR / f"{sanitize(novel)}{ext}"
            log.info("    try %s", p)
            ok = False
            if ext != ".html":
                ok = download_binary(p, dest)
                if ok and ext == ".pdf":
                    v = pdf_is_hindi(dest, novel)
                    if v is False:
                        dest.unlink(missing_ok=True)
                        ok = False
                elif ok and ext in (".epub", ".mobi", ".txt") and dest.stat().st_size < 40000:
                    dest.unlink(missing_ok=True)
                    ok = False
            if not ok and "epustakalay" in p:
                ok = grab_epustakalay(p, dest.with_suffix(".pdf"), novel)
            if not ok:
                ok = save_html(p, dest, novel)
                if ok:
                    dest.rename(dest.with_suffix(".html" if ext != ".html" else ".html") if ext != ".html" else dest)
            if ok and dest.exists() and dest.stat().st_size > 30000:
                log.info("  DOWNLOADED %s -> %s (%d bytes)", novel, dest.name, dest.stat().st_size)
                return True
        time.sleep(0.8)
    return False


def grab_epustakalay(page: str, dest: Path, novel: str) -> bool:
    """epustakalay/archive mirrors actually link to archive.org downloads."""
    try:
        r = _sess.get(page, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        for m in re.finditer(r"https://archive\.org/download/[^\"'<> ]+\.pdf", r.text):
            url = m.group(0).replace(" ", "%20")
            if download_binary(url, dest) and pdf_is_hindi(dest, novel) is not False:
                return True
    except Exception:
        pass
    return False


# ---------------- main ----------------

def process(novel: str, journal: dict) -> dict:
    key = novel.lower()
    if key in journal and journal[key].get("status") == "ok":
        return journal[key]
    log.info("PROCESS %s", novel)
    if try_archive(novel):
        journal[key] = {"novel": novel, "status": "ok", "source": "archive.org"}
    elif try_tavily(novel):
        journal[key] = {"novel": novel, "status": "ok", "source": "web"}
    else:
        log.warning("  FAILED %s", novel)
        journal[key] = {"novel": novel, "status": "failed"}
    save_journal(journal)
    return journal[key]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--novels", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)
    novels = [l.strip() for l in open(args.novels, encoding="utf-8") if l.strip()]
    journal = load_journal()
    log.info("Processing %d novels (workers=%d)", len(novels), args.workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(lambda n: process(n, journal), novels))
    ok = sum(1 for e in journal.values() if e.get("status") == "ok")
    fail = sum(1 for e in journal.values() if e.get("status") == "failed")
    log.info("DONE ok=%d failed=%d tracked=%d", ok, fail, len(journal))


if __name__ == "__main__":
    main()
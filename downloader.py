#!/usr/bin/env python3
"""
Hindi Novel Downloader System
--------------------------------
Uses the Tavily Search API to discover India's top Hindi novels and
locate free download sources. Attempts to download each novel in
whatever format it is available (PDF / EPUB / TEXT / HTML / DOC).

Usage:
    python downloader.py --discover-only
    python downloader.py --novels my_list.txt
    python downloader.py --limit 100
"""

import argparse
import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    TAVILY_API_KEY,
    DOWNLOAD_DIR,
    MAX_RESULTS_PER_SEARCH,
    CONCURRENT_DOWNLOADS,
    REQUEST_TIMEOUT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("downloader.log", encoding="utf-8")],
)
log = logging.getLogger("hindi-downloader")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

FILE_EXTENSIONS = (".pdf", ".epub", ".mobi", ".doc", ".docx", ".txt", ".html", ".htm")

JUNK_DOMAINS = (
    "play.google.com", "amazon.", "updatestar", "collegedunia",
    "facebook.com", "pinterest", "testbook.com", "youtube.com",
    "instagram.com", "twitter.com", "tamilbookspdf.com",
)

JOURNAL_FILE = "download_journal.json"


class TavilySearch:
    """Thin wrapper around the Tavily API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = None
        try:
            from tavily import TavilyClient
            self.client = TavilyClient(api_key=api_key)
        except ImportError:
            try:
                from tavily import Client as TavilyClient
                self.client = TavilyClient(api_key=api_key)
            except ImportError:
                self.client = None
        self.raw_http = requests.Session()
        self.raw_http.headers.update({"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT})

    def search(self, query: str, max_results: int = None, include_domains: list = None):
        max_results = max_results or MAX_RESULTS_PER_SEARCH
        try:
            if self.client:
                res = self.client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=max_results,
                    include_answer=True,
                    include_domains=include_domains or [],
                )
                return res
            # Fallback: raw HTTP call
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": True,
            }
            if include_domains:
                payload["include_domains"] = include_domains
            r = self.raw_http.post(
                "https://api.tavily.com/search", json=payload, timeout=REQUEST_TIMEOUT
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning("Tavily search failed for query %r: %s", query, exc)
            return {"results": [], "answer": ""}


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe file name."""
    name = re.sub(r'[\\/:*?"<>|#]', "_", name.strip())
    name = re.sub(r"\s+", " ", name)
    return name[:150] or "novel"


def is_direct_file(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(FILE_EXTENSIONS)


def looks_like_ebook_url(url: str) -> bool:
    url_l = url.lower()
    markers = (
        "download", "ebook", "book", "pdf", "epub", "pustak", "kitab",
        "archive.org", "hindilibrary", "mybook", "vidya", "ebooks",
    )
    return any(m in url_l for m in markers)


def discover_top_hindi_novels(searcher: TavilySearch, limit: int) -> list:
    """Find names of top Hindi novels using multiple Tavily searches."""
    queries = [
        "भारत के शीर्ष 100 हिंदी उपन्यास list",
        "top 100 famous Hindi novels list names",
        "बेस्ट हिंदी उपन्यास famous Hindi novels all time",
        "हिंदी साहित्य के प्रसिद्ध उपन्यास complete list",
        "top Hindi novels list Premchand Godan Gunahon Ka Devta",
    ]
    seen = {}
    for q in queries:
        log.info("Discovering novels: %s", q)
        res = searcher.search(q, max_results=MAX_RESULTS_PER_SEARCH)
        blob = "\n".join(str(r.get("content", "")) + "\n" + str(r.get("title", "")) + "\n" + str(r.get("url", "")) for r in res.get("results", []))
        if res.get("answer"):
            blob += "\n" + str(res["answer"])
        for cand in re.findall(r"[A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .,:'()\-]{2,80}", blob):
            cand = cand.strip().strip(".,:;")
            if len(cand.split()) > 4 or len(cand) < 3:
                continue
            if re.fullmatch(r"[\x00-\x7F ]+", cand) and not cand[0].isupper():
                continue
            seen.setdefault(cand.lower(), cand)
        time.sleep(1.2)

    # Prioritise well-known classics by matching against a curated seed list.
    curated = seed_novel_list()
    known = {}
    for c in curated:
        known[c.lower()] = c
    for k, v in known.items():
        seen.setdefault(k, v)

    discovered = list(dict.fromkeys(list(known.values()) + list(seen.values())))
    log.info("Total unique novel names discovered: %d", len(discovered))
    return discovered[:limit] if limit else discovered


def seed_novel_list() -> list:
    """A curated seed list of well-known Hindi novels (order = popularity)."""
    return [
        "गोदान", "गबन", "निर्मला", "गृहदाह", "कर्मभूमि", "रंगभूमि", "प्रेमाश्रम",
        "गुनाहों का देवता", "पिंजर", "टीस", "मागधी", "पंचम", "मार्ग", "अमृत",
        "गोलगप्पा", "कथा कारुणिका", "अग्नि की अल्का", "मैला आँचल",
        "तीसरी कसम", "देवता", "चीफ की दावत", "सत्य के प्रयोग", "तमस",
        "आधा गाँव", "जगह", "बनारस का ठग", "अमिता", "उपहार",
        "माधवी", "आग और धुआं", "जूलूस", "अजनबी", "शेखर", "राग दरबारी",
        "बृहन्नला", "अरे यायावर रहेगा याद?", "कितने पाकिस्तान", "आओ प्यार करें",
        "दस प्रतिशत", "फांस", "शहर और समंदर", "और अंत में", "प्रथम आदमी",
        "वासुदेव", "सम्पूर्ण क्रांति", "सूरज का सातवाँ घोड़ा", "ऑक्सीजन",
        "तमन्ना", "नंगी आवाज़", "ग्रामा", "छाया माता", "भाग्य की मार",
        "परती परिवार", "आलोक पर्व", "जरा सी रोशनी", "काली रातें",
        "ये हो सकता है", "अजीज", "नदी की प्रतीक्षा", "सूखा", "गिल्टी",
        "मनुश्य के विरुद्ध", "रिपोर्ट में रिहर्सल", "नेह की नीव", "उपन्यास सम्राट",
        "डॉट कॉम कम्पनी", "विलोम", "साक्षी सत्ता", "पार्टी", "दीवारों के बीच",
        "चंद्रमुखी", "हरिश्चन्द्र की निर्दोषता", "अंधेरे से उजाले की ओर",
        "काले बादल", "पुराने जख्म", "मुंडे इतने घने", "कथाकार",
        "यह सत्य है", "महाभोज", "पूँजी", "विष्णु प्रभा",
        "चन्द्रकान्ता", "भाग्यश्री", "हिंदुस्तानी सूत्र",
    ]


def select_best_file_urls(res: dict) -> list:
    """Extract candidate direct-download URLs from a Tavily response,
    including file URLs embedded in the result snippets."""
    urls = []
    for r in res.get("results", []):
        u = r.get("url", "")
        if not u:
            continue
        if any(j in u for j in JUNK_DOMAINS):
            continue
        if is_direct_file(u) or looks_like_ebook_url(u):
            urls.append((u, r.get("title", ""), r.get("content", "")))
        content = str(r.get("content", ""))
        for m in re.finditer(r'https?://[^\s<>"\']+(?:\.(?:pdf|epub|mobi|txt|docx?))(?:\?[^\s<>"\']*)?', content):
            url = m.group(0).rstrip(".,;:)")
            if any(j in url for j in JUNK_DOMAINS):
                continue
            urls.append((url, r.get("title", ""), content))
    return urls


def prioritize_book_files(urls: list) -> list:
    """Order URLs by book-format preference: pdf > epub > mobi > txt > others."""
    def rank(u):
        ul = u.lower().rstrip("/")
        if ul.endswith(".pdf"):
            return 0
        if ul.endswith(".epub"):
            return 1
        if ul.endswith(".mobi"):
            return 2
        if ul.endswith(".txt") or ul.endswith(".djvu"):
            return 3
        return 9
    return sorted(dict.fromkeys(urls), key=rank) if urls else urls


def scrape_page_for_files(url: str, max_links: int = 15) -> list:
    """Fetch an HTML page and return direct file / download URLs found inside."""
    found = []
    if "archive.org/details/" in url:
        m = re.search(r"archive\.org/details/([A-Za-z0-9_\-]+)/?", url)
        if m:
            item = m.group(1)
            try:
                meta = requests.get(
                    f"https://archive.org/metadata/{item}",
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                ).json()
                for f in meta.get("files", []):
                    name = f.get("name", "")
                    if name and not name.startswith(("_", "@")):
                        found.append(f"https://archive.org/download/{item}/{name}")
                        if len(found) >= max_links:
                            break
                if found:
                    return prioritize_book_files(found)
            except Exception as exc:
                log.debug("Archive.org metadata failed %s: %s", url, exc)
    if "archive.org/details/" in url:
        m = re.search(r"archive\.org/details/([A-Za-z0-9_\-]+)/?", url)
        if m:
            item = m.group(1)
            try:
                r = requests.get(
                    f"https://archive.org/services/search/beta/page_production/advancedsearch.php"
                    + f"?q=identifier:{item}&fl%5B%5D=identifier&rows=1&output=json",
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                _ = r.json()
                r2 = requests.get(
                    f"https://archive.org/download/{item}/",
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                for mm in re.finditer(r'href="([^"]+\.(?:pdf|epub|mobi|txt|djvu))"', r2.text, re.I):
                    found.append(f"https://archive.org/download/{item}/" + mm.group(1))
                    if len(found) >= max_links:
                        break
                if found:
                    return prioritize_book_files(found)
            except Exception as exc:
                log.debug("Archive.org listing failed %s: %s", url, exc)
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("#") or href.lower().startswith("javascript"):
                continue
            full = requests.compat.urljoin(url, href)
            pl = full.lower().split("?")[0]
            text = a.get_text().strip().lower()
            is_file = pl.endswith(FILE_EXTENSIONS)
            looks_dl = any(k in text for k in ("download", "pdf", "epub", "डाउनलोड", "प्राप्त"))
            looks_domain = any(d in pl for d in ("drive.google.com", "archive.org", "dl.dropbox", "mediafire", "mega.nz", "hindipdf", "pdfhindibook"))
            if (is_file or looks_dl or looks_domain) and full not in found:
                found.append(full)
                if len(found) >= max_links:
                    break
    except Exception as exc:
        log.debug("Scrape failed %s: %s", url, exc)
    return found


def download_binary(url: str, dest: str) -> bool:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" in ctype and not url.lower().split("?")[0].endswith(FILE_EXTENSIONS):
            return False
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return os.path.getsize(dest) > 4096
    except Exception as exc:
        log.debug("Binary download failed %s: %s", url, exc)
        return False


def save_html_page(url: str, dest: str, novel: str = "") -> bool:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if any(j in url for j in JUNK_DOMAINS):
            return False
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        dev_count = len(re.findall(r"[\u0900-\u097F]", text))
        if len(text) < 3000 or dev_count < 400:
            return False
        if novel:
            norm = re.sub(r"\s+", "", text)
            if novel[:4] in norm and dev_count < 1500:
                return False
        with open(dest, "w", encoding="utf-8") as f:
            f.write(f"<!-- source: {url} -->\n")
            f.write(text)
        return True
    except Exception as exc:
        log.debug("HTML page save failed %s: %s", url, exc)
        return False


def find_and_download(searcher: TavilySearch, novel: str, output_dir: Path, journal: dict) -> dict:
    key = novel.lower()
    if key in journal:
        entry = journal[key]
        log.info("SLIP  %-45s <- already done (%s)", novel, entry.get("status", "done"))
        return entry
    entry = {"novel": novel, "status": "pending"}
    queries = [
        f'"{novel}" book pdf download free hindi',
        f"{novel} novel pdf free download",
        f"{novel} epub download",
        f"{novel} ebook hindi free",
        f'"{novel}" archive.org',
        f'"{novel}" उपन्यास pdf पुस्तक',
        f'"{novel}" site:epustakalay.com',
        f'"{novel}" site:hindikahani.hindi-kavita.com',
    ]
    tried_files = set()
    scraped_pages = set()
    for qi, q in enumerate(queries):
        log.info("[%d/100] %-45s searching: %s", novels_count_dummy(), novel, q)
        res = searcher.search(q, max_results=MAX_RESULTS_PER_SEARCH)
        candidates = select_best_file_urls(res)
        result_pages = []
        for url, title, _content in candidates:
            if is_direct_file(url):
                result_pages.append(url)
        for url, title, _content in candidates:
            if not is_direct_file(url) and url not in scraped_pages:
                if any(j in url for j in JUNK_DOMAINS):
                    continue
                scraped_pages.add(url)
                log.info("    scraping %s", url)
                for u in scrape_page_for_files(url):
                    result_pages.append(u)
        result_pages = prioritize_book_files(result_pages)

        for url in result_pages:
            ext = Path(urlparse(url).path.lower()).suffix or ".html"
            if not ext or ext not in FILE_EXTENSIONS:
                if "pdf" in url.lower():
                    ext = ".pdf"
                elif "epub" in url.lower():
                    ext = ".epub"
                elif "mobi" in url.lower():
                    ext = ".mobi"
                else:
                    ext = ".html"
            dest = output_dir / f"{sanitize_filename(novel)}{ext}"
            if dest in tried_files:
                continue
            tried_files.add(dest)
            log.info("    trying  %s", url)
            if ext == ".html" and not is_direct_file(url):
                ok = save_html_page(url, dest, novel)
            else:
                ok = download_binary(url, dest) or (save_html_page(url, dest, novel) if ext == ".html" else False)
            if ok and dest.exists() and dest.stat().st_size > 4096:
                entry = {"novel": novel, "status": "ok", "url": url, "format": ext, "size": dest.stat().st_size, "dest": str(dest)}
                journal[key] = entry
                save_journal(journal)
                log.info("  DOWNLOADED %-45s -> %s (%s bytes)", novel, dest.name, dest.stat().st_size)
                return entry
        time.sleep(1.0)
    entry["status"] = "failed"
    entry["queries"] = len(queries)
    journal[key] = entry
    save_journal(journal)
    log.warning("  FAILED    %-45s no free download found via search", novel)
    return entry


_novels_seen = {"n": 0}


def novels_count_dummy() -> int:
    _novels_seen["n"] += 1
    return _novels_seen["n"]


def save_journal(journal: dict):
    try:
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_journal() -> dict:
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def main():
    ap = argparse.ArgumentParser(description="Download top Hindi novels via Tavily search")
    ap.add_argument("--limit", type=int, default=100, help="max number of novels to process")
    ap.add_argument("--discover-only", action="store_true", help="only discover novel names, don't download")
    ap.add_argument("--novels", type=str, help="file with novel names (one per line)")
    args = ap.parse_args()

    output_dir = Path(DOWNLOAD_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    journal = load_journal()

    if not TAVILY_API_KEY:
        log.error("TAVILY_API_KEY not set in config.py")
        sys.exit(1)

    searcher = TavilySearch(TAVILY_API_KEY)
    log.info("Tavily search client initialised: %s", "sdk" if searcher.client else "http-fallback")

    if args.novels:
        with open(args.novels, encoding="utf-8") as f:
            novels = [l.strip() for l in f if l.strip()]
    else:
        novels = discover_top_hindi_novels(searcher, args.limit)

    if args.discover_only:
        (output_dir / "novel_list.txt").write_text("\n".join(novels), encoding="utf-8")
        log.info("Discovered %d novels -> saved to %s", len(novels), output_dir / "novel_list.txt")
        print("\n".join(novels))
        return

    if not novels:
        log.error("No novels discovered; use --novels list.txt to supply them manually.")
        sys.exit(1)

    log.info("Processing %d novels, download dir: %s", len(novels), output_dir.resolve())
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_DOWNLOADS) as pool:
        futures = {pool.submit(find_and_download, searcher, n, output_dir, journal): n for n in novels}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res.get("status") == "ok":
                    done += 1
            except Exception as exc:
                log.error("Unexpected error: %s", exc)

    ok = sum(1 for e in journal.values() if e.get("status") == "ok")
    failed = sum(1 for e in journal.values() if e.get("status") == "failed")
    log.info("=" * 60)
    log.info("COMPLETE.  downloaded ok: %d   failed: %d   total tracked: %d", ok, failed, len(journal))
    log.info("Books saved under: %s", output_dir.resolve())


if __name__ == "__main__":
    main()
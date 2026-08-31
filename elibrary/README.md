# Sushant Kumar eLibrary — हिंदी उपन्यास संग्रह

Production-level read-only e-library. All novels in `content/` (symlink to
`hindi_novels/`) are published as an online library. Users pick a book and read
it in the browser — **download is disabled**.

Built by **Sushant Kumar**. Tech: FastAPI + PDF.js / epub.js + SQLite.

## Run

```bash
cd elibrary
chmod +x run.sh
./run.sh                # defaults to 0.0.0.0:8000
# or: HOST=127.0.0.1 PORT=8080 ./run.sh
```

Open http://localhost:8000/app

Backend auto-scans `content/` on startup and regenerates covers (pdftoppm).
Full API docs at /api/docs.

## Features

- Library homepage: search, type filter (PDF/EPUB/TXT), Devanagari akshar
  filter, sort, dark/light theme, mobile-first responsive grid.
- Reader: PDF.js canvas rendering (zoom, arrows/buttons, fullscreen, page
  scrubber), plain-text reader for TXT, epub.js paginated reader for EPUB.
- Read progress saved per book (localStorage) with "continue" resume.
- Cover thumbnails auto-generated from first PDF page.

## Anti-download design

- All book files served ONLY through `/api/read/{id}/stream?tk=...` with a
  short-lived HMAC token bound to book + IP + User-Agent.
- Reader obtains the stream token at runtime via `POST /api/read/{id}/ticket`.
- No CORS, same-origin only; `X-Frame-Options: DENY`, `no-store` on content.
- Reader page: context-menu, selection, drag, Print, and Ctrl/Cmd+S/P/U and
  F12 guards; `@media print { body{display:none} }` yields a blank printout.
- Tiled "Sushant Kumar eLibrary" watermark overlaid AND baked into rendered
  canvas pages.

Note: no browser solution can make content 100% un-downloadable for a
determined user (they can capture screen pixels). This stack stops casual
downloads, hotlinking, and legal file grabs while keeping UX great.

## Layout

```
elibrary/
  app/          FastAPI backend (config, tokens, db, scan, main)
  static/       index.html, reader.html, css/, js/, vendor/ (pdf.js, epub.js)
  content -> ../hindi_novels
  covers/       auto-generated cover jpgs
  data/         catalog.db, secret.key
  run.sh

# Deploy (free, Render) -- files live at repo root:
Dockerfile      Builds the whole app + PDFs into one image
.dockerignore   Excludes caches from build context
render.yaml     Render Blueprint (web service, free plan)
```

## Deploy to Render (free, public URL)

Prereq: `hindi_novels/` + `elibrary/data/catalog.db` + `elibrary/covers/` are
already generated locally (run `scan` once), then push this repo to GitHub.

1. Commit the repo (root `SUSHANT/`) to GitHub.
2. On [render.com](https://render.com) → New → Blueprint, link the repo.
   Render reads `render.yaml` and creates a free Docker web service.
3. Deploy. Render builds the image (copies `elibrary/` code/static/covers/data
   plus `hindi_novels/` as `content/`), then serves a public URL:
   `https://sushant-elibrary.onrender.com/`

Backend auto-reuses the baked-in `catalog.db` (skip re-scan when valid) so
startup is fast and no poppler is required at runtime.

### Free-tier caveats
- Spins down after 15 min idle → first request after idle takes ~30-60 s
  (Render shows a loading page). Refresh once to wake it.
- 750 compute hrs/mo and 100 GB outbound bandwidth/mo shared with the plan.
- No persistent disk: all data is in the Docker image (immutable). Restarts
  keep the same baked catalog.
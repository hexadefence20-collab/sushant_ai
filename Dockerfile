# Sushant Kumar eLibrary - production image for Render.
# Build context is the repo root (SUSHANT/) so both `elibrary/` code/static and
# `hindi_novels/` PDFs are baked into the image. Everything is immutable in the
# image, so Render's ephemeral filesystem always has valid content + catalog.

FROM --platform=linux/amd64 python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /elibrary

COPY elibrary/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY elibrary/app ./app
COPY elibrary/static ./static
COPY elibrary/covers ./covers
COPY elibrary/data ./data
COPY elibrary/run.sh ./run.sh

# Keep the content/ directory layout that config.py expects (CONTENT_DIR).
COPY hindi_novels ./content

RUN chmod +x ./run.sh

EXPOSE 8000

CMD ["./run.sh"]

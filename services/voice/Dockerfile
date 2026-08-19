# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 curl xz-utils \
    && rm -rf /var/lib/apt/lists/*
# Debian's `ffmpeg` apt package drags in ~450MB of unused video-codec/GL deps
# (libavfilter, libplacebo, mesa/gallium, LLVM) just to decode MP3 audio for
# tts/edge_tts.py's fallback path. A static audio-focused build is ~76MB.
RUN curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
      -o /tmp/ffmpeg.tar.xz \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
    && mv /tmp/ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ffmpeg \
    && rm -rf /tmp/ffmpeg.tar.xz /tmp/ffmpeg-*-amd64-static \
    && apt-get purge -y xz-utils \
    && chmod +x /usr/local/bin/ffmpeg
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
# No --all-extras / --extra local-inference: heavy models (faster-whisper,
# qwen-tts, piper-tts) live on the remote inference server, not in this image.
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

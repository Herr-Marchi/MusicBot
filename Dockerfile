# syntax=docker/dockerfile:1

FROM denoland/deno:bin AS deno

FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.13-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 musicbot

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=deno /deno /usr/local/bin/deno
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown -R musicbot:musicbot /app

USER musicbot

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "music_bot"]

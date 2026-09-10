# AI Mentions Tracker в Linux-контейнере.
#
# Интерфейс — http://localhost:8756 в браузере хоста, окна Camoufox (вход в
# аккаунты, капча, наблюдение за сканом) — http://localhost:6080 через noVNC.
# Подробности и ограничения — раздел «Docker» в README.md.
FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Виртуальный экран и доступ к нему; шрифты с кириллицей; tzdata — чтобы
# дата среза скана считалась по московскому времени, а не по UTC.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      xvfb fluxbox x11vnc novnc websockify \
      fonts-dejavu fonts-liberation tzdata procps \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Системные библиотеки Firefox ставит сам Playwright; браузер Camoufox
# скачивается в образ, чтобы контейнер работал сразу, без мастера установки.
RUN pip install -r requirements.txt \
 && python -m playwright install-deps firefox \
 && python -m camoufox fetch \
 && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY web ./web
COPY docker/entrypoint.sh /entrypoint.sh
# На Windows git может выдать скрипт с CRLF — sh на нём падает с невнятной ошибкой.
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENV DISPLAY=:99 \
    TZ=Europe/Moscow \
    AIPARSER_HOST=0.0.0.0 \
    AIPARSER_NO_WINDOW=1

EXPOSE 8756 6080
ENTRYPOINT ["/entrypoint.sh"]

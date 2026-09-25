FROM python:3.12-slim

WORKDIR /srv
COPY server/requirements.txt /srv/server/requirements.txt
RUN pip install --no-cache-dir -r /srv/server/requirements.txt
COPY server /srv/server
COPY alembic.ini /srv/alembic.ini
COPY web /srv/web

ENV APP_ENV=production
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

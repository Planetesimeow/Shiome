FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHIOME_ENV=production \
    SHIOME_DB_PATH=/data/shiome.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 shiome \
    && mkdir /data && chown shiome:shiome /data
COPY app/ ./app/
COPY scripts/ ./scripts/
USER shiome
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/healthz', timeout=4)"
CMD ["python", "-m", "scripts.serve"]

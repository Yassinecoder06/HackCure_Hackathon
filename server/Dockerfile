# Build from the repo root: docker build -f server/Dockerfile .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/contracts:/app/server \
    BORJ_SEED_PATH=/app/seed/ward-W1.yaml \
    BORJ_DB_URL=sqlite:////data/borj.sqlite

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY contracts contracts
COPY seed seed
COPY server/borj_server server/borj_server
COPY server/config server/config

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "borj_server.main:app", "--host", "0.0.0.0", "--port", "8000"]

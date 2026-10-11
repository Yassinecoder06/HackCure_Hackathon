# Build from the repo root: docker build -f family-gateway/Dockerfile .
# Stage 1 builds the family app; stage 2 is the gateway, which serves it and the API from one origin.
FROM node:20-alpine AS app
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/ward/package.json ./apps/ward/package.json
COPY apps/family/package.json ./apps/family/package.json
COPY apps/mock-server/package.json ./apps/mock-server/package.json
RUN npm ci
COPY apps/family ./apps/family
RUN npm run build --workspace=apps/family

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/contracts:/app/family-gateway \
    FAMILY_STATIC_DIR=/app/static \
    FAMILY_PRIVACY_CONFIG=/app/config/privacy.yaml \
    FAMILY_DB_PATH=/data/family.sqlite

COPY family-gateway/requirements.txt family-gateway/requirements.txt
RUN pip install --default-timeout=1000 --retries=10 -r family-gateway/requirements.txt

COPY contracts contracts
COPY family-gateway/borj_family_gateway family-gateway/borj_family_gateway
# The ward's own word list: the gateway refuses clinical text again with it (safety invariant 2).
COPY server/config/family.yaml config/privacy.yaml
COPY --from=app /app/apps/family/dist static

# Not root: this is the one service reachable from the internet.
RUN useradd --system --uid 10001 borj && mkdir /data && chown borj /data
USER borj
VOLUME /data
EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health')"
CMD ["uvicorn", "borj_family_gateway.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8100"]

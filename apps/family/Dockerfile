# Multi-stage Dockerfile for Borj Family App
# Build from repo root: docker build -f apps/family/Dockerfile .
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package manifests for npm workspaces resolution
COPY package.json package-lock.json ./
COPY apps/ward/package.json ./apps/ward/package.json
COPY apps/family/package.json ./apps/family/package.json
COPY apps/mock-server/package.json ./apps/mock-server/package.json
COPY apps/twin3d/package.json ./apps/twin3d/package.json

RUN npm ci

# Copy sources
COPY contracts ./contracts
COPY apps/family ./apps/family

RUN npm run build --workspace=apps/family

# Production runtime stage
FROM nginx:alpine

COPY apps/family/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/apps/family/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

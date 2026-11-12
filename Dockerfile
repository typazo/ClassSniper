# Stage 1: Build React + TypeScript + Tailwind PWA bundle
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Base Python 3.12 runtime
FROM python:3.12-slim AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    STATIC_DIR=/app/static

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY --from=frontend-builder /build/dist ./static
RUN mkdir -p /app/data

# Stage 3: Test target (run pytest in identical Python 3.12 environment)
FROM runtime-base AS test
COPY backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/tests ./tests
CMD ["pytest", "-v"]

# Stage 4: Final production runtime
FROM runtime-base AS prod
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"]

# ── Stage 1: dependency builder ───────────────────────────────────────────────
# Use a full image to compile any C extensions (psycopg2, etc.)
FROM python:3.11-slim AS builder

WORKDIR /build

# System libs needed to compile psycopg2 and other C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime PostgreSQL client library (no compiler needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source
COPY backend/ .
COPY context/ /app/../context/
COPY database/schema.sql /docker-entrypoint-initdb.d/schema.sql

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

# Uvicorn with:
#   --workers 1  (scale horizontally via docker-compose, not threads)
#   --proxy-headers  (trust X-Forwarded-For from nginx)
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]

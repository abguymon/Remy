FROM python:3.12-slim

WORKDIR /app

# curl for the healthcheck; uv for fast installs
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Install dependencies (leverages layer caching)
COPY pyproject.toml README.md ./
COPY src/ src/
RUN uv pip install --system -e .
# Maintenance/eval scripts (e.g. scripts/eval_product_ranking.py)
COPY scripts/ scripts/

# Data volume (SQLite DB, recipe images) lives here
RUN mkdir -p data

# Non-root runtime user
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app

VOLUME ["/app/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

USER appuser

CMD ["uvicorn", "remy_api.main:app", "--host", "0.0.0.0", "--port", "8080"]

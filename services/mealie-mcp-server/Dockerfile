FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY docker_entrypoint.py ./

# Install curl for healthcheck, then install uv and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv && uv sync

# Create non-root user and set ownership
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -s --max-time 2 -o /dev/null -w '%{http_code}' http://localhost:8000/sse | grep -q 200

USER appuser

CMD ["python", "docker_entrypoint.py"]

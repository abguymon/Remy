FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck and uv for faster package installation
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install dependencies
RUN uv pip install --system -e .

# Create data directory
RUN mkdir -p data/checkpoints

# Create non-root user and set ownership
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

VOLUME ["/app/data"]

# Expose port
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

USER appuser

# Run the application
CMD ["uvicorn", "remy_api.main:app", "--host", "0.0.0.0", "--port", "8080"]

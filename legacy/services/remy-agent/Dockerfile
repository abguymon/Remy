FROM python:3.12-slim-bookworm

WORKDIR /app

# Install curl for healthcheck and uv
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Copy dependency files first for better caching
COPY pyproject.toml README.md ./

# Create minimal src structure for dependency resolution
RUN mkdir -p src/remy_agent && touch src/remy_agent/__init__.py

# Install dependencies (cached unless pyproject.toml changes)
RUN uv pip install --system . && \
    uv pip install --system langchain-community ddgs langgraph-checkpoint-sqlite aiosqlite

# Now copy actual source code and config
COPY src ./src
COPY pantry.yaml ./
COPY recipe_sources.yaml ./
# Copy user_settings template if the actual file does not exist
COPY user_settings.yaml* user_settings.yaml.template ./
RUN if [ ! -f user_settings.yaml ]; then cp user_settings.yaml.template user_settings.yaml; fi

# Reinstall to use the real source (quick since deps are cached)
RUN uv pip install --system --reinstall --no-deps .

# Create data directory and non-root user
RUN mkdir -p /app/data && \
    useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

VOLUME ["/app/data"]

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

USER appuser

CMD ["streamlit", "run", "src/remy_agent/app.py", "--server.address=0.0.0.0"]

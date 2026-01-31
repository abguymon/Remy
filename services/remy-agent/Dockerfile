FROM python:3.12-slim-bookworm

WORKDIR /app

# Install uv first (rarely changes)
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
COPY user_settings.yaml ./

# Reinstall to use the real source (quick since deps are cached)
RUN uv pip install --system --reinstall --no-deps .

EXPOSE 8501

CMD ["streamlit", "run", "src/remy_agent/app.py", "--server.address=0.0.0.0"]

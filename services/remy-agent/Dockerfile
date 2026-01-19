FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY src ./src
COPY pantry.yaml ./

# Install uv and dependencies
RUN pip install uv && uv pip install --system .

# Install additional dependencies that were added later
RUN uv pip install --system langchain-community ddgs langgraph-checkpoint-sqlite aiosqlite

EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "src/remy_agent/app.py", "--server.address=0.0.0.0"]

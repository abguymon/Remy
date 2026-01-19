FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY LICENSE ./
COPY README.md ./
COPY src ./src
COPY docker_entrypoint.py ./

# Install uv and dependencies
RUN pip install uv && uv sync

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["python", "docker_entrypoint.py"]
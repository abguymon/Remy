# remy-api

FastAPI backend for Remy v2. See `../../PRD.md` (authoritative spec) and
`../../V2_PLAN.md` for the build plan. This is the T0 scaffold: a `/health`
endpoint and fail-closed config loading. Modules (auth, planner, recipes,
kroger, llm, websearch, mcp) land in later tasks.

## Develop

```bash
uv sync --extra dev            # or: pip install -e ".[dev]"
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
uvicorn remy_api.main:app --host 0.0.0.0 --port 8080 --reload
```

## Lint & test

```bash
ruff check src tests
ruff format --check src tests
pytest
```

## Config

Settings load from environment / `.env` (see `../../.env.template`).
`JWT_SECRET` and `ENCRYPTION_KEY` are **required** — the app refuses to start
if either is missing, empty, or a placeholder (PRD §9.5).

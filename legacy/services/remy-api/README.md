# Remy API

FastAPI backend for Remy - AI Grocery Planning Agent.

## Features

- JWT authentication
- Multi-tenant user management
- LangGraph workflow orchestration
- WebSocket streaming for real-time updates
- Integration with Kroger and Mealie MCP servers

## Development

```bash
# Install dependencies
uv sync

# Run locally
uv run uvicorn remy_api.main:app --reload --port 8080

# Run tests
uv run pytest
```

## API Endpoints

- `POST /auth/register` - Create account with invite code
- `POST /auth/login` - Get JWT token
- `GET /users/me` - Current user profile
- `GET /users/me/settings` - User settings
- `PUT /users/me/settings` - Update settings
- `PUT /users/me/mealie` - Connect Mealie account
- `GET /health` - Health check

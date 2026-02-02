"""Application configuration"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # API Settings
    api_title: str = "Remy API"
    api_version: str = "0.1.0"
    debug: bool = False

    # JWT Settings
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # Database
    database_url: str = "sqlite+aiosqlite:///data/remy.db"

    # MCP Server URLs
    kroger_mcp_url: str = "http://kroger-mcp:8000/sse"
    mealie_mcp_url: str = "http://mealie-mcp-server:8000/sse"
    mealie_external_url: str = "http://localhost:9925"

    # OpenAI
    openai_api_key: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Initial admin setup (for bootstrapping)
    initial_invite_code: str | None = None  # Set to create initial invite code

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

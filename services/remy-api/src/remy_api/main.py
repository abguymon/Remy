"""FastAPI application entry point"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remy_api.config import get_settings
from remy_api.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/checkpoints", exist_ok=True)
    await init_db()
    yield
    # Shutdown (nothing to clean up)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    settings = get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.api_version}

    # Import and include routers
    from remy_api.routers import auth, cart, kroger, recipes, users

    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/users", tags=["Users"])
    app.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
    app.include_router(cart.router, prefix="/cart", tags=["Cart"])
    app.include_router(kroger.router, prefix="/kroger", tags=["Kroger"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("remy_api.main:app", host="0.0.0.0", port=8080, reload=True)

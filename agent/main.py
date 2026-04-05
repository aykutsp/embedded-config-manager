"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from agent import __version__
from agent.api.routes import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Embedded Config Manager",
        version=__version__,
        description="Versioned configuration management for Linux-based embedded devices.",
    )
    app.include_router(api_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "embedded-config-manager",
            "version": __version__,
            "api": "/api/v1",
        }

    return app


app = create_app()


def run() -> None:  # entry point for `ecm-agent`
    import uvicorn

    uvicorn.run(
        "agent.main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    run()

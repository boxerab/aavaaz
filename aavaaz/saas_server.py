"""
Aavaaz SaaS server entrypoint.

Extends the base Aavaaz server with SaaS-specific endpoints:
- User API key management
- Usage tracking & metering
- Stripe billing
- Subscription management

Start with:
    aavaaz serve --mode saas
    # or directly:
    python -m aavaaz.saas_server
"""

import logging
import os
import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aavaaz.api.saas import router as saas_router

logger = logging.getLogger(__name__)


def create_saas_app() -> FastAPI:
    """Create the SaaS management API as a standalone FastAPI app."""
    app = FastAPI(
        title="Aavaaz SaaS Platform",
        description="Enterprise speech-to-text SaaS management API",
        version="0.1.0",
    )

    # CORS for dashboard
    dashboard_origins = os.environ.get(
        "AAVAAZ_CORS_ORIGINS", "http://localhost:3000,https://app.aavaaz.dev"
    ).split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in dashboard_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(saas_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "aavaaz-saas"}

    return app


def run_saas_api(port: int = 8001):
    """Run the SaaS management API server."""
    app = create_saas_app()
    logger.info("Starting Aavaaz SaaS API on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)


def run_saas_api_background(port: int = 8001):
    """Run the SaaS management API in a background thread."""
    thread = threading.Thread(target=run_saas_api, args=(port,), daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_saas_api()

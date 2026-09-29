"""
Manager Server FastAPI Entry Point
"""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import HOST, PORT
from app.manager_service import ManagerService
from app.routes.api import router as api_router
from app.routes.web import setup_web_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ManagerServer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NavosEdge Parent Manager Server on http://%s:%s", HOST, PORT)
    manager_service = ManagerService()
    app.state.manager_service = manager_service

    # Periodic background task to check for node timeouts
    async def periodic_timeout_checker():
        while True:
            try:
                await asyncio.sleep(3.0)
                await manager_service.check_node_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in node timeout checker: %s", e)

    bg_task = asyncio.create_task(periodic_timeout_checker())
    yield
    bg_task.cancel()
    logger.info("Shutting down NavosEdge Parent Manager Server.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NavosEdge Parent Manager Server",
        version="1.0.0",
        description="Central coordinator and multi-node dashboard backend for NavosEdge intelligence network.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    setup_web_dashboard(app)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)

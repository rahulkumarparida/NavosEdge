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
    from .config import HOST, PORT, UNO_Q_BASE_URL, UNO_Q_POLL_INTERVAL_S, UNO_Q_POLL_ENABLED
    logger.info("Starting NavosEdge Parent Manager Server on http://%s:%s", HOST, PORT)
    if UNO_Q_POLL_ENABLED:
        logger.info("UNO Q Polling enabled — Base URL: %s, Interval: %.1fs", UNO_Q_BASE_URL, UNO_Q_POLL_INTERVAL_S)

    manager_service = getattr(app.state, "manager_service", None)
    if manager_service is None:
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

    # Periodic background task to poll UNO Q edge node
    async def periodic_uno_q_poller():
        await asyncio.sleep(1.0)
        while True:
            try:
                await manager_service.poll_uno_q()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in UNO Q poller task: %s", e)

            try:
                await asyncio.sleep(UNO_Q_POLL_INTERVAL_S)
            except asyncio.CancelledError:
                break

    bg_task_timeout = asyncio.create_task(periodic_timeout_checker())
    bg_task_poller = asyncio.create_task(periodic_uno_q_poller())
    yield
    bg_task_timeout.cancel()
    bg_task_poller.cancel()
    logger.info("Shutting down NavosEdge Parent Manager Server.")



def create_app() -> FastAPI:
    app = FastAPI(
        title="NavosEdge Parent Manager Server",
        version="1.0.0",
        description="Central coordinator and multi-node dashboard backend for NavosEdge intelligence network.",
        lifespan=lifespan,
    )

    app.state.manager_service = ManagerService()

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

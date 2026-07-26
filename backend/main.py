from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app_settings import get_settings, has_placeholder_ingest_token, has_placeholder_read_token
from db.database import init_db
from routers.browser_auth import router as browser_auth_router
from routers.health import router as health_router
from routers.reports import router as reports_router
from routers.read_api import router as read_router
from routers.webhook import router as webhook_router
from utils.logger import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting HealthQuery backend")
    settings = get_settings()
    warn_on_placeholder_tokens(settings)
    await init_db()
    from services.browser_auth import ensure_browser_auth_state

    await ensure_browser_auth_state()
    yield
    logger.info("Stopping HealthQuery backend")


app = FastAPI(title="HealthQuery API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(browser_auth_router)
app.include_router(read_router)
app.include_router(reports_router)
app.include_router(webhook_router)


class SpaStaticFiles(StaticFiles):
    """Serve the frontend entry point for browser routes without masking APIs."""

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/") or "." in Path(path).name:
                raise
            return await super().get_response("index.html", scope)


frontend_dist = Path(os.getenv("FRONTEND_DIST_PATH", "../frontend/dist"))
if frontend_dist.is_dir():
    app.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")


def warn_on_placeholder_tokens(settings=None) -> None:
    settings = settings or get_settings()
    if has_placeholder_ingest_token(settings):
        logger.warning("HEALTHQUERY_INGEST_TOKEN is still set to a placeholder value")
    if has_placeholder_read_token(settings):
        logger.warning("HEALTHQUERY_READ_TOKEN is still set to a placeholder value")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

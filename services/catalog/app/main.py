from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from karigar_shared.config import get_settings
from karigar_shared.db.session import engine
from karigar_shared.errors import register_exception_handlers
from karigar_shared.logging import configure_logging
from karigar_shared.middleware.logging_access import AccessLogMiddleware
from karigar_shared.middleware.request_id import RequestIdMiddleware
from karigar_shared.rate_limit import limiter

from app.router import router

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Karigar Catalog Service",
    version="2.0.0",
    description="Diamond catalog search and detail.",
    lifespan=lifespan,
)
app.state.limiter = limiter

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)

app.include_router(router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    from sqlalchemy.sql import text
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"
    return {"status": "ok", "database": db_status, "service": "catalog"}

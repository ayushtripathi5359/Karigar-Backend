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

from .router import router

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Karigar Pricing Service",
    version="2.0.0",
    description="Pricing service placeholder — calculator logic lives at /v1/calculator/.",
    lifespan=lifespan,
)
app.state.limiter = limiter

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pricing"}

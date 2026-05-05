from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.db.session import Base, engine
from app.errors import register_exception_handlers
from app.limiter import limiter
from app.middleware.logging_access import AccessLogMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.routers import health, onboarding, otp, users

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Karigar API",
    version="1.0.0",
    description=(
        "Backend API for Karigar — a jewellery intelligence platform. "
        "Supports OTP-based phone authentication and Stack Auth (OAuth)."
    ),
    contact={"name": "Karigar Engineering"},
    lifespan=lifespan,
)
app.state.limiter = limiter

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)

app.include_router(health.router)
app.include_router(otp.router)
app.include_router(users.router)
app.include_router(onboarding.router)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import engine
from app.middleware.logging_access import AccessLogMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.health.router import router as health_router
from app.modules.notifications.router import router as notifications_router
from app.modules.orders.router import router as orders_router
from app.modules.payments.router import router as payments_router
from app.modules.pricing.router import router as pricing_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.trends.router import router as trends_router
from app.modules.users.router import router as users_router
from app.shared.rate_limit import limiter

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by the SQL files in sql/ + Alembic — NOT by ORM metadata.
    # Do not call Base.metadata.create_all here.
    yield
    await engine.dispose()


app = FastAPI(
    title="Karigar API",
    version="2.0.0",
    description=(
        "Karigar — diamond intelligence platform. v2 schema with RLS-enforced "
        "data isolation and pgcrypto-encrypted PII. Auth: phone OTP."
    ),
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

# Module routers — registration order doesn't matter; URL prefixes are unique.
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(catalog_router)
app.include_router(suppliers_router)
app.include_router(pricing_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(trends_router)
app.include_router(notifications_router)

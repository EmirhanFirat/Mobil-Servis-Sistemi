from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.errors import register_error_handlers
from app.hardening import BodyLimitMiddleware, SecurityHeadersMiddleware
from app.routers import admin, auth, demo, experiments, health, meta, tickets


def create_app() -> FastAPI:
    settings = get_settings()
    production = settings.environment == "production"
    # Üretimde etkileşimli belge sayfaları ve şema ucu kapalıdır (yüzey bilgisi vermesin).
    app = FastAPI(
        title="TalepAkış API",
        version=__version__,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    # Katmanlar dıştan içe: güvenlik başlıkları → CORS → gövde sınırı → uygulama. (Son eklenen
    # en dıştadır.) CORS, 413 yanıtı da tarayıcıya anlaşılır gitsin diye gövde sınırının dışındadır.
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    # Mobil uygulama CORS'a tabi değildir; yalnızca tarayıcıdaki yönetici paneli için.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=production)
    register_error_handlers(app)
    for router in (
        health.router,
        meta.router,
        auth.router,
        tickets.router,
        admin.router,
        experiments.router,
        demo.router,
    ):
        app.include_router(router)
    return app


app = create_app()

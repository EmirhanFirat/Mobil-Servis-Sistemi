from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.errors import register_error_handlers
from app.routers import admin, auth, experiments, health, meta, tickets


def create_app() -> FastAPI:
    app = FastAPI(title="TalepAkış API", version=__version__)
    settings = get_settings()
    # Mobil uygulama CORS'a tabi değildir; yalnızca tarayıcıdaki yönetici paneli için.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)
    for router in (
        health.router,
        meta.router,
        auth.router,
        tickets.router,
        admin.router,
        experiments.router,
    ):
        app.include_router(router)
    return app


app = create_app()

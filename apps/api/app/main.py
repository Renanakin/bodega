from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import DomainError, domain_error_handler
from app.db.session import create_database


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1",
            "http://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.db = create_database(db_path)
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()

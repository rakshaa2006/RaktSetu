"""Application factory. Tests build isolated apps (own temp database) from here."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import DomainError
from app.database import init_db, make_engine, make_session_factory
from app.services.seed import seed_database

DESCRIPTION = (
    "RaktSetu is a hackathon demonstration for coordinating urgent blood requests. All donors, blood banks "
    "and events are fictional and simulated. It is not a clinical system: final compatibility, donor "
    "eligibility, screening and stock confirmation belong to qualified professionals."
)


def create_app(database_url: Optional[str] = None, seed: Optional[bool] = None,
               data_dir: Optional[Path] = None) -> FastAPI:
    settings = get_settings()
    engine = make_engine(database_url or settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    data_path = Path(data_dir) if data_dir else settings.data_dir
    if settings.auto_seed if seed is None else seed:
        with factory() as session:
            seed_database(session, data_path)

    app = FastAPI(title="RaktSetu API", version="1.0.0", description=DESCRIPTION)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.data_dir = data_path

    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Content-Type", "Authorization"],
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    app.include_router(router)
    return app

"""Anwendungsaufbau: Kernel + M01 + M02 + M04 mit Weboberfläche.

Start (Entwicklung):
    PYTHONPATH=src python3 -m uvicorn app:erstelle_app --factory --reload

Produktion: DATABASE_URL auf PostgreSQL 16 setzen, JWT_SECRET setzen,
migrationen/postgres_rls.sql einspielen (Row Level Security, Kernel §2).
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from kernel import api as kernel_api
from kernel.db import erstelle_engine, erstelle_session_factory, init_schema
from kernel.fehler import FachFehler
from m01_personal import api as m01_api
from m02_kunde_objekt import api as m02_api
from m04_entgelt import api as m04_api
from seed_basis import seed_basis
from stubs.m03_dokument_wiedervorlage import DokumentPortStub, WiedervorlagePortStub
from stubs.m05_schicht_lookup import SchichtLookupPortStub
from web import ansichten


def erstelle_app(datenbank_url: str | None = None, mit_seed: bool = True) -> FastAPI:
    app = FastAPI(
        title="Musterschutz — Branchenlösung Sicherheitsgewerbe",
        version="0.1.0",
        description="Kernel (M00) + Personal (M01) + Kunde/Objekt (M02) + "
                    "Tarif & Entgelt (M04); M03/M05 über Stubs (Kernel K-2).",
    )

    engine = erstelle_engine(datenbank_url)
    init_schema(engine)
    app.state.engine = engine
    app.state.session_factory = erstelle_session_factory(engine)
    # Stubs der noch nicht gebauten Module (K-2) — zentral verdrahtet.
    app.state.schicht_lookup = SchichtLookupPortStub()
    app.state.wiedervorlagen = WiedervorlagePortStub()
    app.state.dokumente = DokumentPortStub()
    app.state.konfiguration = {
        "pruefe_schichten_bei_deaktivierung": True,   # M02 R-02
    }

    if mit_seed:
        session = app.state.session_factory()
        try:
            if seed_basis(session):
                session.commit()
            else:
                session.rollback()
        finally:
            session.close()

    @app.exception_handler(FachFehler)
    async def fachfehler_handler(request: Request, fehler: FachFehler):
        # Kernel §9: einheitliches Fehlerformat; fachliche Fehler sind nie 500.
        return JSONResponse(status_code=fehler.http_status, content=fehler.als_json())

    app.include_router(kernel_api.router)
    app.include_router(m01_api.router)
    app.include_router(m02_api.router)
    app.include_router(m04_api.router)
    app.include_router(ansichten.router)
    app.mount("/static", StaticFiles(
        directory=os.path.join(os.path.dirname(__file__), "web", "static")),
        name="static")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(erstelle_app(), host="127.0.0.1", port=8000)

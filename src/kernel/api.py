"""Kernel-API: Anmeldung (OAuth2-Password-Flow, Kernel §2) und die
Dependencies, über die alle Modul-Endpunkte Session und AuthKontext beziehen."""

from typing import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.auth import (
    AuthKontext,
    erstelle_token,
    kontext_aus_token,
    lese_token,
    pruefe_passwort,
)
from kernel.fehler import FachFehler
from kernel.modelle import Benutzer, BenutzerRolle, Rolle, jetzt_utc

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def hole_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
        # Outbox-Worker (Kernel §8): Zustellung nach erfolgreichem Commit,
        # mindestens einmal — im Entwicklungsbetrieb synchron je Request.
        from kernel.events import verarbeite_outbox
        if verarbeite_outbox(session):
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _token_aus_request(request: Request) -> str | None:
    kopf = request.headers.get("Authorization", "")
    if kopf.startswith("Bearer "):
        return kopf.removeprefix("Bearer ").strip()
    return request.cookies.get("zugang")


def hole_kontext(request: Request) -> AuthKontext:
    token = _token_aus_request(request)
    if not token:
        raise FachFehler("M00-E-401", "Nicht angemeldet", http_status=401)
    return kontext_aus_token(token)


def benoetigt(*rollen: str):
    """K-9: jeder Endpunkt deklariert seine Anforderung explizit."""

    def pruefer(ktx: AuthKontext = Depends(hole_kontext)) -> AuthKontext:
        if rollen:
            ktx.fordere_rolle(*rollen)
        return ktx

    return pruefer


def rollen_von(session: Session, benutzer: Benutzer) -> list[str]:
    codes = session.scalars(
        select(Rolle.code)
        .join(BenutzerRolle, BenutzerRolle.rolle_id == Rolle.id)
        .where(BenutzerRolle.benutzer_id == benutzer.id)
    ).all()
    return sorted(codes)


def melde_an(session: Session, email: str, passwort: str) -> tuple[Benutzer, list[str]]:
    benutzer = session.scalars(select(Benutzer).where(
        Benutzer.email == email, Benutzer.aktiv.is_(True),
    )).first()
    if benutzer is None or not pruefe_passwort(passwort, benutzer.passwort_hash):
        raise FachFehler("M00-E-402", "E-Mail oder Passwort ist falsch", http_status=401)
    benutzer.letzter_login = jetzt_utc()
    return benutzer, rollen_von(session, benutzer)


@router.post("/token")
def token_ausstellen(email: str = Form(...), passwort: str = Form(...),
                     session: Session = Depends(hole_session)) -> dict:
    benutzer, rollen = melde_an(session, email, passwort)
    return {
        "access_token": erstelle_token(benutzer.id, benutzer.tenant_id, rollen, "access"),
        "refresh_token": erstelle_token(benutzer.id, benutzer.tenant_id, rollen, "refresh"),
        "token_type": "bearer",
        "rollen": rollen,
    }


@router.post("/erneuern")
def token_erneuern(refresh_token: str = Form(...),
                   session: Session = Depends(hole_session)) -> dict:
    payload = lese_token(refresh_token, erwartete_art="refresh")
    benutzer = session.get(Benutzer, UUID(payload["sub"]))
    if benutzer is None or not benutzer.aktiv:
        raise FachFehler("M00-E-401", "Benutzer ist gesperrt", http_status=401)
    rollen = rollen_von(session, benutzer)
    return {
        "access_token": erstelle_token(benutzer.id, benutzer.tenant_id, rollen, "access"),
        "token_type": "bearer",
        "rollen": rollen,
    }

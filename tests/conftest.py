"""Gemeinsame Fixtures: App mit In-Memory-Datenbank und Seed, angemeldete Clients."""

import pytest
from fastapi.testclient import TestClient

from app import erstelle_app
from kernel.auth import AuthKontext
from seed_basis import TENANT


@pytest.fixture()
def app():
    return erstelle_app("sqlite://")


@pytest.fixture()
def client(app):
    return TestClient(app)


def kopf_fuer(client: TestClient, email: str, passwort: str = "musterschutz!") -> dict:
    antwort = client.post("/api/v1/auth/token",
                          data={"email": email, "passwort": passwort})
    assert antwort.status_code == 200, antwort.text
    return {"Authorization": f"Bearer {antwort.json()['access_token']}"}


@pytest.fixture()
def admin_kopf(client):
    return kopf_fuer(client, "admin@musterschutz.example")


@pytest.fixture()
def planer_kopf(client):
    return kopf_fuer(client, "disposition@musterschutz.example")


@pytest.fixture()
def session(app):
    sitzung = app.state.session_factory()
    yield sitzung
    sitzung.close()


def ktx(rollen: set[str], tenant=TENANT) -> AuthKontext:
    from kernel.ids import uuid7
    return AuthKontext(benutzer_id=uuid7(), tenant_id=tenant,
                       rollen=frozenset(rollen))


@pytest.fixture()
def admin_ktx():
    return ktx({"ADMIN"})


@pytest.fixture()
def planer_ktx():
    return ktx({"PLANER"})

"""Kernel-Querschnitt: Fehlerformat, Rollen, Idempotenz, Muster A, Sperren (§9)."""

import time as zeitmodul
from datetime import date

import pytest
from sqlalchemy import func, select

from kernel.fehler import FachFehler
from kernel.ids import uuid7
from kernel.muster import neue_version, version_am
from m01_personal.modelle import Mitarbeiter, Vertragstyp
from seed_basis import TENANT
from tests.conftest import kopf_fuer


def test_fehlerformat_einheitlich(client):
    antwort = client.get("/api/v1/personal/mitarbeiter")
    assert antwort.status_code == 401
    daten = antwort.json()
    assert set(daten) == {"code", "message", "details"}
    assert daten["code"] == "M00-E-401"


def test_rollenpruefung_an_jedem_endpunkt(client):
    kopf = kopf_fuer(client, "controlling@musterschutz.example")
    antwort = client.post("/api/v1/personal/mitarbeiter", headers=kopf, json={})
    assert antwort.status_code == 403
    assert antwort.json()["code"] == "M00-E-403"


def test_idempotenter_schreibendpunkt(client, admin_kopf, session):
    rumpf = {"personalnummer": "P8001", "nachname": "Idem", "vorname": "Potent",
             "geburtsdatum": "1994-02-02", "land": "Deutschland",
             "eintrittsdatum": "2026-09-01",
             "vertragstyp_id": str(session.scalars(select(Vertragstyp).where(
                 Vertragstyp.code == "VZ", Vertragstyp.aktiv.is_(True))).first().id),
             "funktion_codes": ["WACH"]}
    kopf = admin_kopf | {"Idempotency-Key": "anlage-p8001"}
    erste = client.post("/api/v1/personal/mitarbeiter", json=rumpf, headers=kopf)
    zweite = client.post("/api/v1/personal/mitarbeiter", json=dict(rumpf), headers=kopf)
    assert erste.status_code == 201
    assert erste.json() == zweite.json()
    anzahl = session.scalar(select(func.count()).select_from(Mitarbeiter).where(
        Mitarbeiter.tenant_id == TENANT, Mitarbeiter.personalnummer == "P8001"))
    assert anzahl == 1


def test_optimistisches_sperren_409(client, admin_kopf):
    kunden = client.get("/api/v1/kunde/kunden", headers=admin_kopf).json()
    antwort = client.patch(f"/api/v1/kunde/kunden/{kunden[0]['id']}",
                           headers=admin_kopf,
                           json={"version": 99, "ort": "Anderswo"})
    assert antwort.status_code == 409
    assert antwort.json()["code"] == "M02-E-409"


def test_muster_a_neue_version(session, admin_ktx):
    alt = session.scalars(select(Vertragstyp).where(
        Vertragstyp.tenant_id == TENANT, Vertragstyp.code == "VZ",
        Vertragstyp.aktiv.is_(True))).first()
    neu = neue_version(session, alt, date(2027, 1, 1), "M01-E-020",
                       soll_stunden_monat=170)
    assert neu.version == alt.version + 1
    assert neu.stamm_id == alt.stamm_id
    assert alt.aktiv is False and alt.gueltig_bis == date(2026, 12, 31)
    assert version_am(session, Vertragstyp, alt.stamm_id, date(2026, 6, 1)).id == alt.id
    assert version_am(session, Vertragstyp, alt.stamm_id, date(2027, 6, 1)).id == neu.id

    with pytest.raises(FachFehler):   # K-5: rückwirkend verboten
        neue_version(session, neu, date(2026, 1, 1), "M01-E-020")


def test_uuid7_zeitlich_sortierbar():
    erste = uuid7()
    zeitmodul.sleep(0.002)
    zweite = uuid7()
    assert str(erste) < str(zweite)
    assert str(erste)[14] == "7"   # Versionsnibble


def test_token_erneuern(client):
    anmeldung = client.post("/api/v1/auth/token", data={
        "email": "admin@musterschutz.example", "passwort": "musterschutz!"}).json()
    erneuert = client.post("/api/v1/auth/erneuern",
                           data={"refresh_token": anmeldung["refresh_token"]})
    assert erneuert.status_code == 200
    kopf = {"Authorization": f"Bearer {erneuert.json()['access_token']}"}
    assert client.get("/api/v1/personal/mitarbeiter", headers=kopf).status_code == 200


def test_falsches_passwort(client):
    antwort = client.post("/api/v1/auth/token", data={
        "email": "admin@musterschutz.example", "passwort": "falsch"})
    assert antwort.status_code == 401
    assert antwort.json()["code"] == "M00-E-402"

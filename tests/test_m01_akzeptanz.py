"""Akzeptanzkriterien M01 (Abschnitt 9), 1–10."""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import func, select

from kernel.fehler import FachFehler
from kernel.auth import hash_passwort
from kernel.modelle import AuditLog, Benutzer, OutboxEvent
from m01_personal import service
from m01_personal.modelle import Mitarbeiter, Vertragstyp
from seed_basis import TENANT, TENANT_EVENTS
from tests.conftest import kopf_fuer, ktx


def _ma(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")


def _vertragstyp(session, code: str, admin_ktx) -> Vertragstyp:
    return session.scalars(select(Vertragstyp).where(
        Vertragstyp.tenant_id == admin_ktx.tenant_id, Vertragstyp.code == code,
        Vertragstyp.aktiv.is_(True))).first()


def _neu_daten(session, admin_ktx, nummer="P9001") -> dict:
    return {"personalnummer": nummer, "nachname": "Test", "vorname": "Person",
            "geburtsdatum": date(1995, 4, 1), "land": "Deutschland",
            "eintrittsdatum": date(2026, 1, 1),
            "vertragstyp_id": _vertragstyp(session, "VZ", admin_ktx).id}


def test_ak1_neuanlage_ohne_pflichtfeld_nennt_feldliste(session, admin_ktx):
    daten = _neu_daten(session, admin_ktx)
    daten.pop("geburtsdatum")
    daten.pop("eintrittsdatum")
    with pytest.raises(FachFehler) as fehler:
        service.lege_an(session, admin_ktx, daten, ["WACH"])
    assert fehler.value.code == "M01-E-001"
    assert set(fehler.value.details["felder"]) == {"geburtsdatum", "eintrittsdatum"}


def test_ak2_personalnummer_je_mandant_eindeutig(session, admin_ktx):
    with pytest.raises(FachFehler) as fehler:
        service.lege_an(session, admin_ktx,
                        _neu_daten(session, admin_ktx, nummer="P0001"), ["WACH"])
    assert fehler.value.code == "M01-E-002"

    # Im anderen Mandanten gelingt dieselbe Nummer.
    events_ktx = ktx({"ADMIN"}, tenant=TENANT_EVENTS)
    vt = Vertragstyp(tenant_id=TENANT_EVENTS, code="VZ", bezeichnung="Vollzeit",
                     kategorie="VOLLZEIT", soll_stunden_monat=173,
                     gueltig_ab=date(2024, 1, 1))
    session.add(vt)
    from m01_personal.modelle import Funktion
    session.add(Funktion(tenant_id=TENANT_EVENTS, code="WACH", bezeichnung="Wachdienst"))
    session.flush()
    ma = service.lege_an(session, events_ktx, {
        "personalnummer": "P0001", "nachname": "Fremd", "vorname": "Mandant",
        "geburtsdatum": date(1990, 1, 1), "land": "Deutschland",
        "eintrittsdatum": date(2026, 1, 1), "vertragstyp_id": vt.id}, ["WACH"])
    assert ma.personalnummer == "P0001"


def test_ak3_vertragstypwechsel_zum_15_stichtagsgenau(session, admin_ktx):
    gf = _vertragstyp(session, "GF", admin_ktx)
    service.wechsle_vertragstyp(session, admin_ktx, _ma(1), gf.id, date(2026, 9, 15))
    alt = service.vertragsgrenzen(session, admin_ktx, _ma(1), date(2026, 9, 14))
    neu = service.vertragsgrenzen(session, admin_ktx, _ma(1), date(2026, 9, 15))
    assert alt.kategorie == "VOLLZEIT"
    assert neu.kategorie == "GERINGFUEGIG"
    assert neu.max_verdienst_monat_cent == 60300


def test_ak4_minderjaehrig_kippt_am_18_geburtstag(session, admin_ktx):
    # Person 4 ist am 20.05.2009 geboren — volljährig exakt am 20.05.2027.
    vorher = service.vertragsgrenzen(session, admin_ktx, _ma(4), date(2027, 5, 19))
    danach = service.vertragsgrenzen(session, admin_ktx, _ma(4), date(2027, 5, 20))
    assert vorher.ist_minderjaehrig is True
    assert danach.ist_minderjaehrig is False


def test_ak5_austritt_gibt_lizenz_taggenau_frei(session, admin_ktx):
    benutzer = Benutzer(tenant_id=TENANT, email="lars.lorenz@musterschutz.example",
                        passwort_hash=hash_passwort("test"), aktiv=True)
    session.add(benutzer)
    session.flush()
    ma = session.get(Mitarbeiter, _ma(2))
    ma.benutzer_id = benutzer.id
    zaehler = session.scalar(select(func.count()).select_from(Benutzer)
                             .where(Benutzer.tenant_id == TENANT, Benutzer.aktiv.is_(True)))

    # Austrittsdatum in der Zukunft: Lizenz bleibt belegt (korrigierte R-04) …
    service.setze_austritt(session, admin_ktx, _ma(2), date(2026, 12, 31),
                           "Eigenkündigung", heute=date(2026, 8, 20))
    assert session.get(Benutzer, benutzer.id).aktiv is True

    # … erst das Erreichen des Datums gibt sie frei.
    service.verarbeite_austritte(session, admin_ktx, stichtag=date(2026, 12, 31))
    assert session.get(Benutzer, benutzer.id).aktiv is False
    neuer_zaehler = session.scalar(select(func.count()).select_from(Benutzer)
                                   .where(Benutzer.tenant_id == TENANT,
                                          Benutzer.aktiv.is_(True)))
    assert neuer_zaehler == zaehler - 1


def test_ak6_anonymisierung_in_aufbewahrungsfrist_abgelehnt(session, admin_ktx):
    with pytest.raises(FachFehler) as fehler:
        service.anonymisiere(session, admin_ktx, _ma(12), bestaetigung=True,
                             heute=date(2026, 8, 20))   # Austritt 30.06.2026
    assert fehler.value.code == "M01-E-014"
    assert fehler.value.details["fruehestmoegliches_datum"] == "2036-06-30"


def test_ak7_anonymisierung_entfernt_personenbezug(session, admin_ktx):
    ma = session.get(Mitarbeiter, _ma(12))
    ma.austrittsdatum = date(2015, 6, 30)   # Frist längst abgelaufen
    service.anonymisiere(session, admin_ktx, _ma(12), bestaetigung=True,
                         heute=date(2026, 8, 20))
    ma = session.get(Mitarbeiter, _ma(12))
    assert ma.status == "ANONYMISIERT"
    assert ma.personalnummer.startswith("ANON-")
    assert ma.nachname == "ANONYMISIERT" and ma.vorname == "-"
    for feld in ("strasse", "plz", "ort", "email", "telefon", "geburtsort"):
        assert getattr(ma, feld) is None
    assert ma.id == _ma(12)   # ID bleibt referenzierbar


def test_ak7b_zweistufigkeit_ohne_bestaetigung(session, admin_ktx):
    with pytest.raises(FachFehler) as fehler:
        service.anonymisiere(session, admin_ktx, _ma(12), bestaetigung=False)
    assert fehler.value.code == "M01-E-013"


def test_ak8_jede_aenderung_genau_ein_audit_eintrag(session, admin_ktx):
    vorher = session.scalar(select(func.count()).select_from(AuditLog))
    service.aendere(session, admin_ktx, _ma(3),
                    {"ort": "Leipzig", "plz": "04109"}, erwartete_version=1)
    nachher = session.scalar(select(func.count()).select_from(AuditLog))
    assert nachher == vorher + 1


def test_ak9_events_genau_einmal_veroeffentlicht(session, admin_ktx):
    ma = service.lege_an(session, admin_ktx, _neu_daten(session, admin_ktx, "P9009"),
                         ["WACH"])
    events = session.scalars(select(OutboxEvent).where(
        OutboxEvent.event_type == "m01.mitarbeiter.eingetreten.v1")).all()
    passende = [e for e in events if str(ma.id) in e.payload_json]
    assert len(passende) == 1


def test_ak10_ol_sieht_nur_zugewiesene_personen(client):
    kopf = kopf_fuer(client, "objektleitung@musterschutz.example")
    antwort = client.get("/api/v1/personal/mitarbeiter", headers=kopf)
    assert antwort.status_code == 200
    nummern = {m["personalnummer"] for m in antwort.json()}
    assert nummern == {"P0001", "P0002", "P0005"}   # Zuständigkeit aus dem Seed


def test_statuswechsel_folgt_dem_automaten(session, admin_ktx):
    with pytest.raises(FachFehler) as fehler:
        service.setze_status(session, admin_ktx, _ma(1), "ANONYMISIERT")
    assert fehler.value.code == "M01-E-010"

    service.setze_status(session, admin_ktx, _ma(1), "RUHEND")
    assert service.ist_aktiv(session, admin_ktx, _ma(1), date(2026, 9, 1)) is False
    service.setze_status(session, admin_ktx, _ma(1), "AKTIV")
    assert service.ist_aktiv(session, admin_ktx, _ma(1), date(2026, 9, 1)) is True


def test_wiedereinstellung_nur_admin_mit_grund(session, admin_ktx, planer_ktx):
    with pytest.raises(FachFehler):
        service.setze_status(session, planer_ktx, _ma(12), "AKTIV", grund="Rückkehr")
    with pytest.raises(FachFehler) as fehler:
        service.setze_status(session, admin_ktx, _ma(12), "AKTIV")
    assert fehler.value.code == "M01-E-011"
    ma = service.setze_status(session, admin_ktx, _ma(12), "AKTIV",
                              grund="Wiedereinstellung zum Herbst")
    assert ma.status == "AKTIV" and ma.austrittsdatum is None

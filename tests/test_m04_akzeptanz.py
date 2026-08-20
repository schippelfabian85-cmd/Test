"""Akzeptanzkriterien M04 (Abschnitt 8) auf der Datenbank-Konfiguration."""

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from kernel.fehler import FachFehler
from m01_personal.port import MitarbeiterPort
from m02_kunde_objekt.port import ObjektPort
from m04_entgelt import berechnung, service
from m04_entgelt.modelle import Lohngruppe, Tarif, Zuschlagsmaske
from seed_basis import TENANT

ZONE = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")


def _utc(jahr, monat, tag, stunde, minute=0):
    return datetime(jahr, monat, tag, stunde, minute, tzinfo=ZONE).astimezone(UTC)


def _ma(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")

def _obj(nr: int) -> UUID:
    return UUID(f"22222222-2222-2222-2222-{nr:012d}")


def _port(session, ktx) -> service.EntgeltPort:
    return service.EntgeltPort(session, ktx,
                               mitarbeiter_port=MitarbeiterPort(session, ktx),
                               objekt_port=ObjektPort(session, ktx))


def _lohn(session, ktx, beginn, ende, pause=45, funktion="WACH", land="ST",
          mitarbeiter=1):
    return _port(session, ktx).berechne_lohn(berechnung.LohnAnfrage(
        mitarbeiter_id=_ma(mitarbeiter), objekt_id=_obj(1), funktion_code=funktion,
        beginn_utc=beginn, ende_utc=ende, pause_minuten=pause, bundesland=land))


def test_ak1_samstag_auf_sonntag_getrennte_positionen(session, admin_ktx):
    ergebnis = _lohn(session, admin_ktx, _utc(2026, 9, 5, 22), _utc(2026, 9, 6, 6))
    je_lohnart = {p.lohnart_nummer: p for p in ergebnis.positionen}
    # 480 brutto − 45 Pause = 435 bezahlt; Nacht 420 min, Sonntag 360 min anteilig.
    assert je_lohnart["1000"].minuten == 435
    assert je_lohnart["2010"].minuten == 381   # 420 × 435/480 kaufmännisch
    assert je_lohnart["2020"].minuten == 326   # 360 × 435/480
    assert ergebnis.bezahlte_minuten == 435


def test_ak2_feiertag_nur_im_bundesland_des_objekts(session, admin_ktx):
    bayern = _lohn(session, admin_ktx, _utc(2026, 6, 4, 8), _utc(2026, 6, 4, 16),
                   pause=30, land="BY")
    sachsen_anhalt = _lohn(session, admin_ktx, _utc(2026, 6, 4, 8),
                           _utc(2026, 6, 4, 16), pause=30, land="ST")
    assert any(p.lohnart_nummer == "2030" for p in bayern.positionen)
    assert not any(p.lohnart_nummer == "2030" for p in sachsen_anhalt.positionen)


def test_ak3_angewandte_maske_wird_ausgewiesen(session, admin_ktx):
    ergebnis = _lohn(session, admin_ktx, _utc(2026, 9, 5, 22), _utc(2026, 9, 6, 6))
    maske = session.scalars(select(Zuschlagsmaske).where(
        Zuschlagsmaske.tenant_id == TENANT,
        Zuschlagsmaske.bezeichnung == "Nacht")).first()
    nacht = next(p for p in ergebnis.positionen if p.lohnart_nummer == "2010")
    assert nacht.zuschlagsmaske_id == maske.id   # R-02: nachvollziehbar


def test_ak4_verwendete_maske_unveraenderlich(session, admin_ktx):
    maske = session.scalars(select(Zuschlagsmaske).where(
        Zuschlagsmaske.tenant_id == TENANT,
        Zuschlagsmaske.bezeichnung == "Nacht")).first()
    service.markiere_masken_verwendet(session, [maske.id])
    with pytest.raises(FachFehler) as fehler:
        service.aendere_zuschlagsmaske_direkt(session, admin_ktx, maske.id, prozent=30)
    assert fehler.value.code == "M04-E-011"
    # Erlaubter Weg: neue Version mit künftigem Gültigkeitsdatum.
    neu = service.aendere_zuschlagsmaske(session, admin_ktx, maske.id,
                                         gueltig_ab=date(2027, 1, 1), prozent=30)
    assert neu.version == maske.version + 1 and neu.prozent == 30
    # Rückwirkend bleibt verboten (K-5).
    with pytest.raises(FachFehler) as fehler:
        service.aendere_zuschlagsmaske(session, admin_ktx, neu.id,
                                       gueltig_ab=date(2026, 1, 1), prozent=35)
    assert fehler.value.code == "M04-E-011"


def test_ak5_referenzbetrag_regression(session, admin_ktx):
    """Hinterlegter Referenzbetrag für die Seed-Nachtschicht Sa→So (Regression)."""
    ergebnis = _lohn(session, admin_ktx, _utc(2026, 9, 5, 22), _utc(2026, 9, 6, 6))
    # Grundlohn 435 × 14,50 €/h = 105,13 € · Nacht 380,625 × 3,625 = 23,00 €
    # · Sonntag 326,25 × 7,25 = 39,42 € → 167,55 €
    assert ergebnis.summe_cent == 16755


def test_ak6_mindestlohn_wird_angehoben_und_ausgewiesen(session, admin_ktx):
    tarif = session.scalars(select(Tarif).where(Tarif.tenant_id == TENANT)).first()
    session.add(Lohngruppe(tarif_id=tarif.id, code="LG0", bezeichnung="Anlernkraft",
                           stundenlohn_cent=1200, funktion_codes="AUSHILFE"))
    session.flush()
    ergebnis = _lohn(session, admin_ktx, _utc(2026, 9, 8, 8), _utc(2026, 9, 8, 16),
                     pause=30, funktion="AUSHILFE")
    grundlohn = next(p for p in ergebnis.positionen if p.lohnart_nummer == "1000")
    assert grundlohn.satz_cent == 1390            # angehoben auf Mindestlohn 2026
    assert any("Mindestlohn angehoben" in h for h in ergebnis.hinweise)


def test_ak7_bitgleiche_wiederholung(session, admin_ktx):
    erste = _lohn(session, admin_ktx, _utc(2026, 9, 5, 22), _utc(2026, 9, 6, 6))
    zweite = _lohn(session, admin_ktx, _utc(2026, 9, 5, 22), _utc(2026, 9, 6, 6))
    assert erste == zweite


def test_ak8_umsatz_ohne_weiterberechnung_ohne_zuschlaege(session, admin_ktx):
    # Kunde K-1003 (Objekt 4) hat zuschlag_weiterberechnung = KEINE; Fronleichnam BY.
    ergebnis = _port(session, admin_ktx).berechne_umsatz(berechnung.UmsatzAnfrage(
        objekt_id=_obj(4), funktion_code="WACH",
        beginn_utc=_utc(2026, 6, 4, 8), ende_utc=_utc(2026, 6, 4, 16),
        pause_minuten=30, bundesland="BY"))
    assert all(p.leistungsart != "ZUSCHLAG" for p in ergebnis.positionen)
    assert ergebnis.summe_netto_cent == 20625    # 450 min × 27,50 €/h


def test_ak8b_umsatz_anteilig(session, admin_ktx):
    # Kunde K-1002 (Objekt 2): ANTEILIG 50 % — Nachtzuschlag halbiert weitergegeben.
    ergebnis = _port(session, admin_ktx).berechne_umsatz(berechnung.UmsatzAnfrage(
        objekt_id=_obj(2), funktion_code="WACH",
        beginn_utc=_utc(2026, 9, 8, 22), ende_utc=_utc(2026, 9, 9, 6),
        pause_minuten=0, bundesland="ST"))
    nacht = next(p for p in ergebnis.positionen if "Nacht" in p.bezeichnung)
    assert nacht.satz_cent == 356                # 28,50 × 25 % × 50 % = 3,5625 €/h
    assert nacht.minuten == 420


def test_ak9_jahreswechsel_splittet_auf_tarifversionen(session, admin_ktx):
    alt = session.scalars(select(Tarif).where(Tarif.tenant_id == TENANT,
                                              Tarif.aktiv.is_(True))).first()
    from kernel.muster import neue_version
    tarif_v2 = neue_version(session, alt, date(2027, 1, 1), "M04-E-010")
    for gruppe in session.scalars(select(Lohngruppe).where(
            Lohngruppe.tarif_id == alt.id)).all():
        session.add(Lohngruppe(tarif_id=tarif_v2.id, code=gruppe.code,
                               bezeichnung=gruppe.bezeichnung,
                               stundenlohn_cent=gruppe.stundenlohn_cent + 50,
                               funktion_codes=gruppe.funktion_codes))
    for maske in session.scalars(select(Zuschlagsmaske).where(
            Zuschlagsmaske.tarif_id == alt.id)).all():
        session.add(Zuschlagsmaske(
            tenant_id=TENANT, tarif_id=tarif_v2.id, bezeichnung=maske.bezeichnung,
            typ=maske.typ, prioritaet=maske.prioritaet, kumulierung=maske.kumulierung,
            wochentage=maske.wochentage, von_uhrzeit=maske.von_uhrzeit,
            bis_uhrzeit=maske.bis_uhrzeit, gilt_an_feiertagen=maske.gilt_an_feiertagen,
            gilt_an_sonntagen=maske.gilt_an_sonntagen, prozent=maske.prozent,
            lohnart_id=maske.lohnart_id, bemessung=maske.bemessung,
            gueltig_ab=date(2027, 1, 1)))
    session.flush()

    ergebnis = _lohn(session, admin_ktx, _utc(2026, 12, 31, 22), _utc(2027, 1, 1, 6),
                     pause=0)
    grundloehne = [p for p in ergebnis.positionen if p.lohnart_nummer == "1000"]
    assert len(grundloehne) == 2                  # eine Position je Tarifversion
    saetze = sorted(p.satz_cent for p in grundloehne)
    assert saetze == [1450, 1500]
    assert sum(p.minuten for p in grundloehne) == 480


def test_ak10_zeitumstellung_oktober(session, admin_ktx):
    ergebnis = _lohn(session, admin_ktx, _utc(2026, 10, 24, 22), _utc(2026, 10, 25, 6))
    assert ergebnis.bezahlte_minuten == 495       # 9 h real − 45 min Pause (R-10)


def test_fehlende_lohngruppe_nennt_tarif_und_funktion(session, admin_ktx):
    with pytest.raises(FachFehler) as fehler:
        _lohn(session, admin_ktx, _utc(2026, 9, 8, 8), _utc(2026, 9, 8, 16),
              funktion="TAUCHER")
    assert fehler.value.code == "M04-E-002"
    assert "TAUCHER" in str(fehler.value)


def test_fehlender_verrechnungssatz_konkrete_meldung(session, admin_ktx):
    with pytest.raises(FachFehler) as fehler:
        service.verrechnungssatz_am(session, TENANT,
                                    UUID("99999999-9999-9999-9999-999999999999"),
                                    None, "WACH", date(2026, 9, 1))
    assert fehler.value.code == "M04-E-020"


def test_stub_liefert_gleiche_fachlichkeit(admin_ktx):
    """K-2: der Stub muss ohne Datenbank dieselben Antworten geben können."""
    from m04_entgelt.stub import EntgeltPortStub
    stub = EntgeltPortStub()
    ergebnis = stub.berechne_lohn(berechnung.LohnAnfrage(
        mitarbeiter_id=None, objekt_id=None, funktion_code="WACH",
        beginn_utc=_utc(2026, 9, 5, 22), ende_utc=_utc(2026, 9, 6, 6),
        pause_minuten=45, bundesland="ST"))
    assert ergebnis.summe_cent == 16755
    assert stub.ist_feiertag(date(2026, 6, 4), "BY") is True
    assert stub.ist_feiertag(date(2026, 6, 4), "ST") is False

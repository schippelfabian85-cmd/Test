"""Akzeptanzkriterien M02 (Abschnitt 9), 1–8."""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select

from kernel.auth import hash_passwort
from kernel.fehler import FachFehler
from kernel.modelle import Benutzer, BenutzerRolle, Rolle, Zustaendigkeit
from m02_kunde_objekt import service
from m02_kunde_objekt.modelle import (
    Dienstanweisung, DienstanweisungBestaetigung, Kunde, Objekt, ObjektZuschlag,
)
from m02_kunde_objekt.port import KundePort
from seed_basis import TENANT
from stubs.m03_dokument_wiedervorlage import WiedervorlagePortStub
from stubs.m05_schicht_lookup import SchichtLookupPortStub
from tests.conftest import kopf_fuer


def _obj(nr: int) -> UUID:
    return UUID(f"22222222-2222-2222-2222-{nr:012d}")

def _ma(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")


def test_ak1_objekt_ohne_kunde_nicht_anlegbar(session, planer_ktx):
    with pytest.raises(FachFehler) as fehler:
        service.lege_objekt_an(session, planer_ktx,
                               {"objektnummer": "O-9999", "bezeichnung": "Ohne Kunde"})
    assert fehler.value.code == "M02-E-002"


def test_ak2_deaktivierung_mit_kuenftigen_schichten_abgelehnt(session, planer_ktx):
    lookup = SchichtLookupPortStub()
    with pytest.raises(FachFehler) as fehler:
        service.deaktiviere_objekt(session, planer_ktx, _obj(1), lookup,
                                   heute=date(2026, 8, 20))   # Stub-Wochen 3–4 liegen danach
    assert fehler.value.code == "M02-E-007"
    # Objekt ohne Schichten lässt sich deaktivieren.
    objekt = service.deaktiviere_objekt(session, planer_ktx, _obj(5), lookup,
                                        heute=date(2026, 8, 20))
    assert objekt.aktiv is False


def test_ak3_freigabe_stichtagsgenau(session, planer_ktx):
    service.erteile_freigabe(session, planer_ktx, _obj(3), _ma(6),
                             date(2026, 9, 1), date(2026, 9, 30))
    assert service.ist_freigegeben(session, _obj(3), _ma(6), date(2026, 8, 31)) is False
    assert service.ist_freigegeben(session, _obj(3), _ma(6), date(2026, 9, 1)) is True
    assert service.ist_freigegeben(session, _obj(3), _ma(6), date(2026, 9, 30)) is True
    assert service.ist_freigegeben(session, _obj(3), _ma(6), date(2026, 10, 1)) is False


def test_ak4_neue_version_setzt_bestaetigungen_zurueck(session, planer_ktx):
    v1 = service.veroeffentliche_dienstanweisung(
        session, planer_ktx, _obj(1), "Zutrittsregelung", "Version eins",
        bestaetigung_erforderlich=True)
    session.add(DienstanweisungBestaetigung(dienstanweisung_id=v1.id,
                                            mitarbeiter_id=_ma(1)))
    session.flush()
    v2 = service.veroeffentliche_dienstanweisung(
        session, planer_ktx, _obj(1), "Zutrittsregelung", "Version zwei",
        bestaetigung_erforderlich=True)
    assert v2.version == 2
    uebrig = session.scalars(select(DienstanweisungBestaetigung).where(
        DienstanweisungBestaetigung.dienstanweisung_id == v1.id)).all()
    assert uebrig == []


def test_ak5_zuschlag_versionierung_muster_a(session, admin_ktx):
    zuschlag = session.scalars(select(ObjektZuschlag).where(
        ObjektZuschlag.objekt_id == _obj(3))).first()
    neu = service.aendere_objekt_zuschlag(session, admin_ktx, zuschlag.id,
                                          gueltig_ab=date(2026, 10, 1), wert=200)
    assert neu.version == zuschlag.version + 1
    assert zuschlag.aktiv is False
    assert zuschlag.gueltig_bis == date(2026, 9, 30)
    assert neu.wert == 200 and zuschlag.wert == 150


def test_ak6_leitweg_id_ueber_rechnungsdaten(session, admin_ktx):
    kunde = session.scalars(select(Kunde).where(
        Kunde.kundennummer == "K-1001")).first()
    daten = KundePort(session, admin_ktx).rechnungsdaten(kunde.id)
    assert daten.leitweg_id == "991-33333-33"
    assert daten.rechnung_verdichtung == "JE_OBJEKT"


def test_ak7_rolle_kunde_sieht_nur_eigene_objekte(app, client, session):
    rolle = session.scalars(select(Rolle).where(Rolle.code == "KUNDE")).first()
    benutzer = Benutzer(tenant_id=TENANT, email="portal@ammer.example",
                        passwort_hash=hash_passwort("kunde!"))
    session.add(benutzer)
    session.flush()
    session.add(BenutzerRolle(benutzer_id=benutzer.id, rolle_id=rolle.id,
                              tenant_id=TENANT))
    # Sichtbar: nur die Objekte des eigenen Kunden (K-8, ZustaendigkeitPort).
    session.add(Zustaendigkeit(tenant_id=TENANT, benutzer_id=benutzer.id,
                               objekt_id=_obj(4)))
    session.add(Zustaendigkeit(tenant_id=TENANT, benutzer_id=benutzer.id,
                               objekt_id=_obj(5)))
    session.commit()

    kopf = kopf_fuer(client, "portal@ammer.example", "kunde!")
    antwort = client.get("/api/v1/objekt/objekte", headers=kopf)
    nummern = {o["objektnummer"] for o in antwort.json()}
    assert nummern == {"O-2004", "O-2005"}

    # Fremdzugriff auf ein Objekt außerhalb des Bereichs → HTTP 403.
    client.cookies.set("zugang", kopf["Authorization"].removeprefix("Bearer "))
    fremd = client.get(f"/app/objekte/{_obj(1)}")
    assert fremd.status_code == 403


def test_ak8_befristetes_objekt_genau_eine_wiedervorlage(session, admin_ktx):
    port = WiedervorlagePortStub()
    # O-2005 endet am 31.10.2026 — der Lauf am 01.10. liegt in der 30-Tage-Frist.
    service.erzeuge_wiedervorlagen_befristete(session, admin_ktx, port,
                                              heute=date(2026, 10, 1))
    service.erzeuge_wiedervorlagen_befristete(session, admin_ktx, port,
                                              heute=date(2026, 10, 2))
    betroffene = [e for e in port.eintraege if e.bezug_id == _obj(5)]
    assert len(betroffene) == 1
    assert betroffene[0].faellig_am == date(2026, 10, 1)


def test_objekt_kann_nicht_umgehaengt_werden(session, planer_ktx):
    objekt = session.get(Objekt, _obj(4))
    anderer_kunde = session.scalars(select(Kunde).where(
        Kunde.kundennummer == "K-1001")).first()
    with pytest.raises(FachFehler) as fehler:
        service.aendere_objekt(session, planer_ktx, objekt.id,
                               {"kunde_id": anderer_kunde.id},
                               erwartete_version=objekt.version)
    assert fehler.value.code == "M02-E-006"

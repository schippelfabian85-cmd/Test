"""Akzeptanzkriterien 1–10 der Regelengine (M06, Abschnitt 8)."""

import time as zeitmessung
from datetime import date

import pytest

from kernel.dtos import BLOCKIEREND
from m06_regelengine import FehlerM06, Regelpruefung, RegelAusnahme
from m06_regelengine.beispiele import (
    ALLE_BEISPIELE,
    TENANT,
    kontext_geringfuegig_an_grenze,
    kontext_ohne_qualifikation,
    objekt_id,
    schicht,
    schicht_id,
    standard_kontext,
    utc,
)


@pytest.fixture
def engine():
    return Regelpruefung()


def test_ak1_ruhezeit_exakt_11h_zulaessig_10h59_blockiert(engine):
    exakt = standard_kontext(
        bestehende_schichten=(schicht(2, utc(2026, 9, 7, 13), utc(2026, 9, 7, 21)),)
    )
    assert engine.pruefe(exakt).zulaessig

    knapp = standard_kontext(
        bestehende_schichten=(schicht(2, utc(2026, 9, 7, 13), utc(2026, 9, 7, 21, 1)),)
    )
    ergebnis = engine.pruefe(knapp)
    assert not ergebnis.zulaessig
    assert "AZ_RUHEZEIT" in {v.regel_code for v in ergebnis.verstoesse}


def test_ak2_minderjaehrig_schichtende_20_00_zulaessig_20_01_blockiert(engine):
    from m06_regelengine.beispiele import MINDERJAEHRIG

    bis_20 = standard_kontext(
        grenzen=MINDERJAEHRIG,
        geplante_schicht=schicht(1, utc(2026, 9, 8, 14), utc(2026, 9, 8, 20), pause=30),
    )
    assert engine.pruefe(bis_20).zulaessig

    bis_20_01 = standard_kontext(
        grenzen=MINDERJAEHRIG,
        geplante_schicht=schicht(1, utc(2026, 9, 8, 14), utc(2026, 9, 8, 20, 1), pause=30),
    )
    ergebnis = engine.pruefe(bis_20_01)
    assert not ergebnis.zulaessig
    assert "JU_NACHT" in {v.regel_code for v in ergebnis.verstoesse}


def test_ak3_abgelaufene_sachkunde_blockiert(engine):
    # Der Aufrufer liefert nur am Schichttag gültige Qualifikationen (M06 §3).
    abgelaufen = standard_kontext(qualifikationen=("ERSTE_HILFE",))
    assert not engine.pruefe(abgelaufen).zulaessig

    # Ablauf erst am Folgetag der Schicht: am Schichttag noch gültig.
    noch_gueltig = standard_kontext(qualifikationen=("SACHKUNDE_34A", "ERSTE_HILFE"))
    assert engine.pruefe(noch_gueltig).zulaessig


def test_ak4_deaktivierte_regel_erzeugt_keinen_verstoss(engine):
    kontext = kontext_ohne_qualifikation()
    assert not engine.pruefe(kontext).zulaessig

    engine.deaktiviere("QU_FEHLT")
    ergebnis = engine.pruefe(kontext)
    assert ergebnis.zulaessig
    assert "QU_FEHLT" not in {v.regel_code for v in ergebnis.verstoesse}


def test_ak5_objektbezogene_ausnahme_greift_nur_fuer_dieses_objekt(engine):
    engine.fuege_ausnahme_hinzu(RegelAusnahme(
        regel_code="OB_FREIGABE",
        begruendung="Springer-Regelung für das Objekt vereinbart",
        genehmigt_von="admin",
        gueltig_ab=date(2026, 1, 1),
        objekt_id=objekt_id(1),
    ))
    mit_ausnahme = standard_kontext(objekt_freigegeben=False)
    assert engine.pruefe(mit_ausnahme).zulaessig

    anderes_objekt = standard_kontext(objekt_freigegeben=False, objekt_id=objekt_id(2))
    assert not engine.pruefe(anderes_objekt).zulaessig


def test_ausnahme_ohne_begruendung_wird_abgelehnt():
    with pytest.raises(FehlerM06) as fehler:
        RegelAusnahme(
            regel_code="OB_FREIGABE", begruendung="   ", genehmigt_von="admin",
            gueltig_ab=date(2026, 1, 1),
        )
    assert fehler.value.code == "M06-E-001"


def test_ak6_mehrere_verstoesse_werden_vollstaendig_zurueckgegeben(engine):
    kontext = standard_kontext(
        objekt_freigegeben=False,
        verfuegbar=False,
        verfuegbarkeit_grund="KRANK",
        qualifikationen=(),
    )
    gefunden = {v.regel_code for v in engine.pruefe(kontext).verstoesse}
    assert {"OB_FREIGABE", "VF_ABWESEND", "QU_FEHLT"} <= gefunden


def test_ak7_zulaessig_genau_dann_false_wenn_blockierender_verstoss(engine):
    nur_warnung = engine.pruefe(standard_kontext(ausserhalb_bereitschaft=True))
    assert nur_warnung.verstoesse
    assert all(v.stufe != BLOCKIEREND for v in nur_warnung.verstoesse)
    assert nur_warnung.zulaessig

    blockiert = engine.pruefe(standard_kontext(objekt_freigegeben=False))
    assert any(v.stufe == BLOCKIEREND for v in blockiert.verstoesse)
    assert not blockiert.zulaessig


def test_ak8_stapelpruefung_1000_kontexte_unter_2_sekunden(engine):
    kontexte = [standard_kontext() for _ in range(1000)]
    start = zeitmessung.perf_counter()
    ergebnisse = engine.pruefe_stapel(kontexte)
    dauer = zeitmessung.perf_counter() - start
    assert len(ergebnisse) == 1000
    assert dauer < 2.0


def test_ak9_uebersteuerung_ohne_grund_wird_abgelehnt(engine):
    with pytest.raises(FehlerM06) as fehler:
        engine.uebersteuere(TENANT, schicht_id(1), "AZ_RUHEZEIT",
                            benutzer="admin", rolle="ADMIN", grund="   ")
    assert fehler.value.code == "M06-E-001"

    with pytest.raises(FehlerM06) as fehler:
        engine.uebersteuere(TENANT, schicht_id(1), "AZ_RUHEZEIT",
                            benutzer="planer1", rolle="PLANER", grund="Notbesetzung")
    assert fehler.value.code == "M06-E-002"

    eintrag = engine.uebersteuere(TENANT, schicht_id(1), "AZ_RUHEZEIT",
                                  benutzer="admin", rolle="ADMIN",
                                  grund="Notbesetzung nach Krankheitswelle")
    assert eintrag in engine.protokoll
    assert eintrag.uebersteuerungsgrund == "Notbesetzung nach Krankheitswelle"


def test_ak10_gf_verdienst_rechnet_geplante_schicht_mit(engine):
    kontext = kontext_geringfuegig_an_grenze()
    # Bisheriger Verdienst liegt noch unter der Grenze …
    assert kontext.verdienst_monat_bisher_cent < kontext.grenzen.max_verdienst_monat_cent
    # … erst die geplante Schicht risse sie — und genau das blockiert.
    assert not engine.pruefe(kontext).zulaessig


def test_alle_beispielkontexte_sind_pruefbar(engine):
    for name, fabrik in ALLE_BEISPIELE.items():
        ergebnis = engine.pruefe(fabrik())
        assert ergebnis is not None, name

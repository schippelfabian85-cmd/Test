"""Je Regel ein positiver und ein negativer Testfall (M06, Abschnitt 8)."""

from dataclasses import replace

import pytest

from m06_regelengine import Regelpruefung
from m06_regelengine.beispiele import (
    GERINGFUEGIG,
    KURZFRISTIG,
    MINDERJAEHRIG,
    VOLLZEIT,
    kontext_doppelbelegung,
    kontext_geringfuegig_an_grenze,
    kontext_minderjaehrig_nachtschicht,
    kontext_ohne_qualifikation,
    kontext_ruhezeit_verletzt,
    kontext_sonntagsschicht,
    schicht,
    standard_kontext,
    utc,
)


@pytest.fixture
def engine():
    return Regelpruefung()


def codes(engine, kontext):
    return {v.regel_code for v in engine.pruefe(kontext).verstoesse}


# -- AZ_TAG_MAX --------------------------------------------------------------

def test_az_tag_max_verstoss(engine):
    kontext = standard_kontext(
        geplante_schicht=schicht(1, utc(2026, 9, 8, 8), utc(2026, 9, 8, 19, 30), pause=30)
    )  # 11 h netto
    assert "AZ_TAG_MAX" in codes(engine, kontext)


def test_az_tag_max_zulaessig(engine):
    assert "AZ_TAG_MAX" not in codes(engine, standard_kontext())


# -- AZ_RUHEZEIT -------------------------------------------------------------

def test_az_ruhezeit_verstoss(engine):
    assert "AZ_RUHEZEIT" in codes(engine, kontext_ruhezeit_verletzt())


def test_az_ruhezeit_zulaessig(engine):
    kontext = standard_kontext(
        bestehende_schichten=(schicht(2, utc(2026, 9, 7, 13), utc(2026, 9, 7, 21)),)
    )  # exakt 11 h Lücke
    assert "AZ_RUHEZEIT" not in codes(engine, kontext)


# -- AZ_RUHEZEIT_VERKUERZT (deaktiviert ausgeliefert, hier aktiviert) --------

def test_az_ruhezeit_verkuerzt_warnt_statt_blockiert(engine):
    engine.aktiviere("AZ_RUHEZEIT_VERKUERZT")
    kontext = standard_kontext(
        bestehende_schichten=(schicht(2, utc(2026, 9, 7, 13), utc(2026, 9, 7, 21, 30)),)
    )  # 10 h 30 min Lücke
    gefunden = codes(engine, kontext)
    assert "AZ_RUHEZEIT_VERKUERZT" in gefunden
    assert "AZ_RUHEZEIT" not in gefunden
    assert engine.pruefe(kontext).zulaessig  # nur Warnung


def test_az_ruhezeit_verkuerzt_greift_nicht_unter_10h(engine):
    engine.aktiviere("AZ_RUHEZEIT_VERKUERZT")
    kontext = kontext_ruhezeit_verletzt()  # 9 h Lücke
    gefunden = codes(engine, kontext)
    assert "AZ_RUHEZEIT_VERKUERZT" not in gefunden
    assert "AZ_RUHEZEIT" in gefunden


# -- AZ_PAUSE ----------------------------------------------------------------

def test_az_pause_verstoss(engine):
    kontext = standard_kontext(
        geplante_schicht=schicht(1, utc(2026, 9, 8, 8), utc(2026, 9, 8, 15), pause=0)
    )  # 7 h ohne Pause
    assert "AZ_PAUSE" in codes(engine, kontext)


def test_az_pause_zulaessig(engine):
    assert "AZ_PAUSE" not in codes(engine, standard_kontext())


# -- AZ_SONNTAG --------------------------------------------------------------

def test_az_sonntag_warnung(engine):
    ergebnis = engine.pruefe(kontext_sonntagsschicht())
    assert "AZ_SONNTAG" in {v.regel_code for v in ergebnis.verstoesse}
    assert ergebnis.zulaessig  # Warnung, kein Blocker


def test_az_sonntag_werktag_ohne_warnung(engine):
    assert "AZ_SONNTAG" not in codes(engine, standard_kontext())


# -- AZ_WOCHE_MAX ------------------------------------------------------------

def test_az_woche_max_verstoss(engine):
    kontext = standard_kontext(minuten_24_wochen_bisher=24 * 2880 - 100)
    assert "AZ_WOCHE_MAX" in codes(engine, kontext)


def test_az_woche_max_zulaessig(engine):
    assert "AZ_WOCHE_MAX" not in codes(engine, standard_kontext())


# -- JU_TAG_MAX --------------------------------------------------------------

def test_ju_tag_max_verstoss(engine):
    kontext = standard_kontext(
        grenzen=MINDERJAEHRIG,
        geplante_schicht=schicht(1, utc(2026, 9, 8, 8), utc(2026, 9, 8, 17, 30), pause=30),
    )  # 9 h netto
    assert "JU_TAG_MAX" in codes(engine, kontext)


def test_ju_tag_max_gilt_nur_fuer_minderjaehrige(engine):
    kontext = standard_kontext(
        geplante_schicht=schicht(1, utc(2026, 9, 8, 8), utc(2026, 9, 8, 17, 30), pause=30),
    )
    assert "JU_TAG_MAX" not in codes(engine, kontext)


# -- JU_NACHT ----------------------------------------------------------------

def test_ju_nacht_verstoss(engine):
    assert "JU_NACHT" in codes(engine, kontext_minderjaehrig_nachtschicht())


def test_ju_nacht_tagschicht_zulaessig(engine):
    kontext = standard_kontext(grenzen=MINDERJAEHRIG)
    assert "JU_NACHT" not in codes(engine, kontext)


# -- JU_RUHEZEIT -------------------------------------------------------------

def test_ju_ruhezeit_verstoss(engine):
    kontext = standard_kontext(
        grenzen=MINDERJAEHRIG,
        bestehende_schichten=(schicht(2, utc(2026, 9, 7, 14), utc(2026, 9, 7, 22)),),
    )  # 10 h Lücke < 12 h
    assert "JU_RUHEZEIT" in codes(engine, kontext)


def test_ju_ruhezeit_zulaessig(engine):
    kontext = standard_kontext(
        grenzen=MINDERJAEHRIG,
        bestehende_schichten=(schicht(2, utc(2026, 9, 7, 12), utc(2026, 9, 7, 20)),),
    )  # exakt 12 h Lücke
    assert "JU_RUHEZEIT" not in codes(engine, kontext)


# -- QU_FEHLT ----------------------------------------------------------------

def test_qu_fehlt_verstoss(engine):
    ergebnis = engine.pruefe(kontext_ohne_qualifikation())
    verstoss = next(v for v in ergebnis.verstoesse if v.regel_code == "QU_FEHLT")
    assert "SACHKUNDE_34A" in verstoss.details["fehlende_qualifikationen"]
    assert not ergebnis.zulaessig


def test_qu_fehlt_zulaessig(engine):
    assert "QU_FEHLT" not in codes(engine, standard_kontext())


# -- OB_FREIGABE -------------------------------------------------------------

def test_ob_freigabe_verstoss(engine):
    assert "OB_FREIGABE" in codes(engine, standard_kontext(objekt_freigegeben=False))


def test_ob_freigabe_zulaessig(engine):
    assert "OB_FREIGABE" not in codes(engine, standard_kontext())


# -- VF_ABWESEND -------------------------------------------------------------

def test_vf_abwesend_verstoss(engine):
    kontext = standard_kontext(verfuegbar=False, verfuegbarkeit_grund="URLAUB")
    ergebnis = engine.pruefe(kontext)
    verstoss = next(v for v in ergebnis.verstoesse if v.regel_code == "VF_ABWESEND")
    assert verstoss.details["grund"] == "URLAUB"


def test_vf_abwesend_zulaessig(engine):
    assert "VF_ABWESEND" not in codes(engine, standard_kontext())


# -- VF_BEREITSCHAFT ---------------------------------------------------------

def test_vf_bereitschaft_warnung(engine):
    assert "VF_BEREITSCHAFT" in codes(engine, standard_kontext(ausserhalb_bereitschaft=True))


def test_vf_bereitschaft_zulaessig(engine):
    assert "VF_BEREITSCHAFT" not in codes(engine, standard_kontext())


# -- VT_MAX_STD --------------------------------------------------------------

def test_vt_max_std_verstoss(engine):
    kontext = standard_kontext(minuten_monat_bisher=11700)  # + 450 > 12000
    assert "VT_MAX_STD" in codes(engine, kontext)


def test_vt_max_std_zulaessig(engine):
    assert "VT_MAX_STD" not in codes(engine, standard_kontext())


# -- VT_MIN_STD --------------------------------------------------------------

def test_vt_min_std_hinweis(engine):
    kontext = standard_kontext(
        grenzen=replace(VOLLZEIT, min_minuten_monat=6000),
        minuten_monat_bisher=5000,
    )  # 5450 < 6000
    assert "VT_MIN_STD" in codes(engine, kontext)


def test_vt_min_std_erreicht(engine):
    kontext = standard_kontext(
        grenzen=replace(VOLLZEIT, min_minuten_monat=6000),
        minuten_monat_bisher=5600,
    )  # 6050 >= 6000
    assert "VT_MIN_STD" not in codes(engine, kontext)


# -- GF_VERDIENST ------------------------------------------------------------

def test_gf_verdienst_verstoss(engine):
    assert "GF_VERDIENST" in codes(engine, kontext_geringfuegig_an_grenze())


def test_gf_verdienst_zulaessig(engine):
    kontext = standard_kontext(
        grenzen=GERINGFUEGIG,
        verdienst_monat_bisher_cent=40000,
        verdienst_geplante_schicht_cent=8000,
    )  # 480 € <= 556 €
    assert "GF_VERDIENST" not in codes(engine, kontext)


# -- KF_70_TAGE --------------------------------------------------------------

def test_kf_70_tage_verstoss(engine):
    kontext = standard_kontext(grenzen=KURZFRISTIG, einsatztage_jahr_bisher=70)
    assert "KF_70_TAGE" in codes(engine, kontext)


def test_kf_70_tage_zulaessig(engine):
    kontext = standard_kontext(grenzen=KURZFRISTIG, einsatztage_jahr_bisher=69)
    assert "KF_70_TAGE" not in codes(engine, kontext)


# -- UEBERSCHNEIDUNG ---------------------------------------------------------

def test_ueberschneidung_verstoss(engine):
    assert "UEBERSCHNEIDUNG" in codes(engine, kontext_doppelbelegung())


def test_ueberschneidung_zulaessig(engine):
    kontext = standard_kontext(
        bestehende_schichten=(schicht(2, utc(2026, 9, 8, 16), utc(2026, 9, 8, 22)),)
    )  # nahtlos anschließend, keine Überlappung
    assert "UEBERSCHNEIDUNG" not in codes(engine, kontext)

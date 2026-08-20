"""Segmentzerlegung: Akzeptanzkriterien 1, 2, 3 und 10 aus M04, Abschnitt 8."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from m04_entgelt import Segment, Zuschlagsmaske, zerlege
from m04_entgelt.zerlegung import KUMULIERT, VERDRAENGT

ZONE = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")

NACHT = Zuschlagsmaske(
    bezeichnung="NACHT", prioritaet=10, kumulierung=KUMULIERT,
    von_uhrzeit=time(23), bis_uhrzeit=time(6),
)
SONNTAG = Zuschlagsmaske(
    bezeichnung="SONNTAG", prioritaet=20, kumulierung=KUMULIERT,
    wochentage=frozenset({6}),
)
FEIERTAG = Zuschlagsmaske(
    bezeichnung="FEIERTAG", prioritaet=30, kumulierung=KUMULIERT,
    wochentage=frozenset(), gilt_an_feiertagen=True,
)
FEIERTAG_VERDRAENGEND = Zuschlagsmaske(
    bezeichnung="FEIERTAG", prioritaet=30, kumulierung=VERDRAENGT,
    wochentage=frozenset(), gilt_an_feiertagen=True,
)

FRONLEICHNAM_2026 = date(2026, 6, 4)
FEIERTAGE_BAYERN = {FRONLEICHNAM_2026}
FEIERTAGE_SACHSEN_ANHALT: set[date] = set()


def utc(jahr, monat, tag, stunde, minute=0):
    return datetime(jahr, monat, tag, stunde, minute, tzinfo=ZONE).astimezone(UTC)


def masken_minuten(segmente: list[Segment], bezeichnung: str) -> int:
    return sum(s.minuten for s in segmente if bezeichnung in s.masken)


def pruefe_lueckenlos(segmente, beginn, ende):
    assert segmente[0].beginn_utc == beginn
    assert segmente[-1].ende_utc == ende
    for vorher, nachher in zip(segmente, segmente[1:]):
        assert vorher.ende_utc == nachher.beginn_utc


def test_ak1_samstag_auf_sonntag_trennt_nacht_und_sonntag():
    # Samstag 05.09.2026 22:00 bis Sonntag 06:00
    beginn, ende = utc(2026, 9, 5, 22), utc(2026, 9, 6, 6)
    segmente = zerlege(beginn, ende, [NACHT, SONNTAG], set())

    assert [(s.minuten, s.masken) for s in segmente] == [
        (60, ()),                      # 22–23 Uhr
        (60, ("NACHT",)),              # 23–24 Uhr
        (360, ("SONNTAG", "NACHT")),   # 0–6 Uhr, nach Priorität geordnet
    ]
    pruefe_lueckenlos(segmente, beginn, ende)


def test_ak2_feiertag_nur_im_richtigen_bundesland():
    beginn, ende = utc(2026, 6, 4, 8), utc(2026, 6, 4, 16)

    bayern = zerlege(beginn, ende, [FEIERTAG], FEIERTAGE_BAYERN)
    assert masken_minuten(bayern, "FEIERTAG") == 480

    sachsen_anhalt = zerlege(beginn, ende, [FEIERTAG], FEIERTAGE_SACHSEN_ANHALT)
    assert masken_minuten(sachsen_anhalt, "FEIERTAG") == 0


def test_ak3_verdraengende_maske_unterdrueckt_niedrigere_prioritaet():
    # Nacht in einen Feiertag hinein: 23–24 Uhr Vortag nur Nacht,
    # 0–6 Uhr am Feiertag verdrängt der Feiertagszuschlag die Nacht.
    beginn, ende = utc(2026, 6, 3, 23), utc(2026, 6, 4, 6)
    segmente = zerlege(beginn, ende, [NACHT, FEIERTAG_VERDRAENGEND], FEIERTAGE_BAYERN)

    assert [(s.minuten, s.masken) for s in segmente] == [
        (60, ("NACHT",)),
        (360, ("FEIERTAG",)),
    ]


def test_ak3_kumulierende_masken_erscheinen_gemeinsam():
    beginn, ende = utc(2026, 6, 3, 23), utc(2026, 6, 4, 6)
    segmente = zerlege(beginn, ende, [NACHT, FEIERTAG], FEIERTAGE_BAYERN)
    assert segmente[1].masken == ("FEIERTAG", "NACHT")


def test_ak10_zeitumstellung_oktober_ergibt_9_bezahlte_stunden():
    # Nacht der Umstellung auf Winterzeit: 25.10.2026, 03:00 -> 02:00
    beginn, ende = utc(2026, 10, 24, 22), utc(2026, 10, 25, 6)
    assert (ende - beginn).total_seconds() == 9 * 3600

    segmente = zerlege(beginn, ende, [NACHT, SONNTAG], set())
    assert sum(s.minuten for s in segmente) == 540
    assert masken_minuten(segmente, "NACHT") == 480  # 23–06 Uhr inkl. doppelter Stunde
    pruefe_lueckenlos(segmente, beginn, ende)


def test_ak10_zeitumstellung_maerz_ergibt_7_bezahlte_stunden():
    # Nacht der Umstellung auf Sommerzeit: 29.03.2026, 02:00 -> 03:00
    beginn, ende = utc(2026, 3, 28, 22), utc(2026, 3, 29, 6)
    assert (ende - beginn).total_seconds() == 7 * 3600

    segmente = zerlege(beginn, ende, [NACHT, SONNTAG], set())
    assert sum(s.minuten for s in segmente) == 420
    assert masken_minuten(segmente, "NACHT") == 360


def test_minutengenaue_grenzen():
    beginn, ende = utc(2026, 9, 8, 22, 30), utc(2026, 9, 8, 23, 15)
    segmente = zerlege(beginn, ende, [NACHT], set())
    assert [(s.minuten, s.masken) for s in segmente] == [
        (30, ()),
        (15, ("NACHT",)),
    ]


def test_nacht_nach_mitternacht_folgt_dem_vortag():
    # Nachtmaske nur montags: die Nacht Mo 23:00 – Di 06:00 gehört komplett
    # zum Montag, auch der Teil nach Mitternacht.
    nacht_nur_montag = Zuschlagsmaske(
        bezeichnung="NACHT_MO", prioritaet=10,
        wochentage=frozenset({0}), von_uhrzeit=time(23), bis_uhrzeit=time(6),
    )
    beginn, ende = utc(2026, 9, 7, 23), utc(2026, 9, 8, 6)  # Mo -> Di
    segmente = zerlege(beginn, ende, [nacht_nur_montag], set())
    assert masken_minuten(segmente, "NACHT_MO") == 420


def test_ende_vor_beginn_wird_abgelehnt():
    with pytest.raises(ValueError):
        zerlege(utc(2026, 9, 8, 8), utc(2026, 9, 8, 8), [], set())

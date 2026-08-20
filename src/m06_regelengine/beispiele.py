"""Vorbereitete PruefKontext-Beispiele (M06, Abschnitt 9).

Statt eines Stubs stellt M06 Beispielkontexte bereit, die andere Module
in ihren Tests verwenden können. Die IDs folgen den Seed-Konventionen:
Mitarbeiter `11111111-…` (M01), Objekte `22222222-…` (M02).
"""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from kernel.dtos import SchichtDTO, VertragsgrenzenDTO
from m06_regelengine.kontext import PruefKontext

ZONE = ZoneInfo("Europe/Berlin")
TENANT = UUID("00000000-0000-0000-0000-000000000001")


def mitarbeiter_id(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")


def objekt_id(nr: int) -> UUID:
    return UUID(f"22222222-2222-2222-2222-{nr:012d}")


def schicht_id(nr: int) -> UUID:
    return UUID(f"33333333-3333-3333-3333-{nr:012d}")


def utc(jahr: int, monat: int, tag: int, stunde: int, minute: int = 0) -> datetime:
    """Lokale Zeit (Europe/Berlin) als UTC-Zeitstempel."""
    return datetime(jahr, monat, tag, stunde, minute, tzinfo=ZONE).astimezone(
        ZoneInfo("UTC")
    )


def schicht(nr: int, beginn: datetime, ende: datetime, pause: int = 30,
            objekt: int = 1, mitarbeiter: int = 1) -> SchichtDTO:
    return SchichtDTO(
        id=schicht_id(nr), tenant_id=TENANT, objekt_id=objekt_id(objekt),
        mitarbeiter_id=mitarbeiter_id(mitarbeiter), subunternehmer_id=None,
        beginn_utc=beginn, ende_utc=ende, pause_minuten=pause,
        funktion_code="WACH", zustand="GEPLANT", schichtkuerzel="T",
    )


VOLLZEIT = VertragsgrenzenDTO(
    kategorie="VOLLZEIT", soll_minuten_monat=10080, min_minuten_monat=None,
    max_minuten_monat=12000, max_verdienst_monat_cent=None,
    max_einsatztage_jahr=None, pausen_bezahlt=False,
    zeitwertkonto_aktiv=False, ist_minderjaehrig=False,
)

GERINGFUEGIG = VertragsgrenzenDTO(
    kategorie="GERINGFUEGIG", soll_minuten_monat=2400, min_minuten_monat=None,
    max_minuten_monat=2700, max_verdienst_monat_cent=55600,
    max_einsatztage_jahr=None, pausen_bezahlt=False,
    zeitwertkonto_aktiv=False, ist_minderjaehrig=False,
)

MINDERJAEHRIG = replace(VOLLZEIT, kategorie="AUSHILFE", ist_minderjaehrig=True)

KURZFRISTIG = replace(VOLLZEIT, kategorie="KURZFRISTIG", max_einsatztage_jahr=70)


def standard_kontext(**aenderungen) -> PruefKontext:
    """Zulässige Tagschicht Dienstag 08–16 Uhr, keinerlei Konflikte."""
    basis = PruefKontext(
        tenant_id=TENANT,
        mitarbeiter_id=mitarbeiter_id(1),
        objekt_id=objekt_id(1),
        geplante_schicht=schicht(1, utc(2026, 9, 8, 8), utc(2026, 9, 8, 16), pause=30),
        bestehende_schichten=(),
        qualifikationen=("SACHKUNDE_34A", "ERSTE_HILFE"),
        erforderliche_qualifikationen=("SACHKUNDE_34A",),
        objekt_freigegeben=True,
        verfuegbar=True,
        verfuegbarkeit_grund=None,
        ausserhalb_bereitschaft=False,
        minuten_monat_bisher=4800,
        minuten_24_wochen_bisher=48000,
        grenzen=VOLLZEIT,
        verdienst_monat_bisher_cent=120000,
        verdienst_geplante_schicht_cent=10500,
        einsatztage_jahr_bisher=0,
    )
    return replace(basis, **aenderungen) if aenderungen else basis


def kontext_ruhezeit_verletzt() -> PruefKontext:
    """Vortag bis 23:00 gearbeitet, neue Schicht ab 08:00 — nur 9 h Ruhe."""
    return standard_kontext(
        bestehende_schichten=(
            schicht(2, utc(2026, 9, 7, 15), utc(2026, 9, 7, 23), pause=30),
        ),
    )


def kontext_minderjaehrig_nachtschicht() -> PruefKontext:
    """Minderjährige Person, Schicht bis 22:00 — JU_NACHT blockiert."""
    return standard_kontext(
        mitarbeiter_id=mitarbeiter_id(4),
        geplante_schicht=schicht(1, utc(2026, 9, 8, 14), utc(2026, 9, 8, 22), pause=30),
        grenzen=MINDERJAEHRIG,
    )


def kontext_geringfuegig_an_grenze() -> PruefKontext:
    """Geringfügig beschäftigt, die geplante Schicht risse die Verdienstgrenze."""
    return standard_kontext(
        mitarbeiter_id=mitarbeiter_id(6),
        grenzen=GERINGFUEGIG,
        minuten_monat_bisher=2000,
        verdienst_monat_bisher_cent=50000,
        verdienst_geplante_schicht_cent=8000,
    )


def kontext_ohne_qualifikation() -> PruefKontext:
    """Person -0011 hat keinerlei Qualifikationen (M03-Stub)."""
    return standard_kontext(
        mitarbeiter_id=mitarbeiter_id(11),
        qualifikationen=(),
    )


def kontext_doppelbelegung() -> PruefKontext:
    """Zeitgleich bereits an einem anderen Objekt eingeplant."""
    return standard_kontext(
        bestehende_schichten=(
            schicht(3, utc(2026, 9, 8, 12), utc(2026, 9, 8, 20), pause=30, objekt=2),
        ),
    )


def kontext_sonntagsschicht() -> PruefKontext:
    """Schicht am Sonntag — Warnung mit Ersatzruhetag-Hinweis."""
    return standard_kontext(
        geplante_schicht=schicht(1, utc(2026, 9, 6, 8), utc(2026, 9, 6, 16), pause=30),
    )


ALLE_BEISPIELE = {
    "standard": standard_kontext,
    "ruhezeit_verletzt": kontext_ruhezeit_verletzt,
    "minderjaehrig_nachtschicht": kontext_minderjaehrig_nachtschicht,
    "geringfuegig_an_grenze": kontext_geringfuegig_an_grenze,
    "ohne_qualifikation": kontext_ohne_qualifikation,
    "doppelbelegung": kontext_doppelbelegung,
    "sonntagsschicht": kontext_sonntagsschicht,
}

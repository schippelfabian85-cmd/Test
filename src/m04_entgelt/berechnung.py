"""Lohn- und Umsatzberechnung auf Basis der Segmentzerlegung (M04 §3/§5).

Reine Rechenlogik: deterministisch, seiteneffektfrei, ohne Datenbank.
Die Konfiguration (Tarif, Masken, Feiertage, Mindestlohn) kommt je
Kalendertag über einen Resolver — damit splittet eine Schicht über den
Jahreswechsel automatisch auf beide Tarifversionen (AC 9).

R-09: Zwischenergebnisse bleiben ungerundet (Fraction); gerundet wird
erst je Position, kaufmännisch auf ganze Cent.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from fractions import Fraction
from typing import Callable
from uuid import UUID
from zoneinfo import ZoneInfo

from m04_entgelt.zerlegung import Zuschlagsmaske, zerlege

STANDARD_ZONE = ZoneInfo("Europe/Berlin")

GRUNDLOHN_LOHNART = "1000"
PAUSE_LOHNART = "1005"


@dataclass(frozen=True)
class MaskenKonfig:
    """Eine Zuschlagsmaske samt Geldwirkung."""

    maske: Zuschlagsmaske
    maske_id: UUID | None
    lohnart_nummer: str
    lohnart_bezeichnung: str
    bemessung: str                  # GRUNDLOHN | TARIFLOHN | FESTBETRAG
    prozent: int | None = None
    betrag_cent: int | None = None


@dataclass(frozen=True)
class TagesKonfig:
    """Die am Kalendertag gültige Entgeltkonfiguration."""

    tarif_code: str
    stundenlohn_cent: int           # Tariflohn der Lohngruppe
    masken: tuple[MaskenKonfig, ...]
    feiertage: frozenset
    mindestlohn_cent: int


@dataclass(frozen=True)
class LohnAnfrage:
    mitarbeiter_id: UUID | None
    objekt_id: UUID | None
    funktion_code: str
    beginn_utc: datetime
    ende_utc: datetime
    pause_minuten: int
    bundesland: str
    pausen_bezahlt: bool = False


@dataclass(frozen=True)
class LohnPosition:
    lohnart_nummer: str
    bezeichnung: str
    minuten: int
    satz_cent: int
    betrag_cent: int
    zuschlagsmaske_id: UUID | None


@dataclass(frozen=True)
class LohnErgebnis:
    positionen: tuple[LohnPosition, ...]
    summe_cent: int
    bezahlte_minuten: int
    hinweise: tuple[str, ...]


@dataclass(frozen=True)
class UmsatzAnfrage:
    objekt_id: UUID | None
    funktion_code: str
    beginn_utc: datetime
    ende_utc: datetime
    pause_minuten: int
    bundesland: str
    pausen_bezahlt: bool = False


@dataclass(frozen=True)
class UmsatzKonfig:
    """Der am Kalendertag gültige Verrechnungssatz."""

    satz_cent_pro_stunde: int
    zuschlag_weiterberechnung: str  # KEINE | ANTEILIG | VOLL
    weiterberechnung_prozent: int
    masken: tuple[MaskenKonfig, ...]
    feiertage: frozenset


@dataclass(frozen=True)
class UmsatzPosition:
    bezeichnung: str
    minuten: int
    satz_cent: int
    betrag_cent: int
    leistungsart: str


@dataclass(frozen=True)
class UmsatzErgebnis:
    positionen: tuple[UmsatzPosition, ...]
    summe_netto_cent: int
    minuten: int


def _tages_chunks(beginn_utc: datetime, ende_utc: datetime,
                  zone: ZoneInfo) -> list[tuple[datetime, datetime, date]]:
    """Zerlegt die Schicht an lokalen Mitternachten (Basis für Tageskonfiguration)."""
    chunks = []
    cursor = beginn_utc
    while cursor < ende_utc:
        lokal = cursor.astimezone(zone)
        naechste_mitternacht = datetime.combine(
            lokal.date() + timedelta(days=1), time(0), tzinfo=zone
        ).astimezone(beginn_utc.tzinfo)
        chunk_ende = min(ende_utc, naechste_mitternacht)
        chunks.append((cursor, chunk_ende, lokal.date()))
        cursor = chunk_ende
    return chunks


def _runde_cent(wert: Fraction) -> int:
    """Kaufmännisch auf ganze Einheiten (R-09) — exakt über Bruchrechnung."""
    return int(wert + Fraction(1, 2))


def _zuschlag_satz(konfig: MaskenKonfig, grund_satz: int, tarif_satz: int) -> Fraction:
    if konfig.bemessung == "FESTBETRAG":
        return Fraction(konfig.betrag_cent or 0)
    basis = grund_satz if konfig.bemessung == "GRUNDLOHN" else tarif_satz
    return Fraction(basis) * Fraction(konfig.prozent or 0, 100)


def berechne_lohn(anfrage: LohnAnfrage,
                  konfig_je_tag: Callable[[date], TagesKonfig],
                  zone: ZoneInfo = STANDARD_ZONE) -> LohnErgebnis:
    brutto = int((anfrage.ende_utc - anfrage.beginn_utc).total_seconds() // 60)
    pause = min(anfrage.pause_minuten, brutto)
    netto = brutto - pause
    hinweise: list[str] = []

    # R-04: unbezahlte Pause reduziert die bezahlte Zeit anteilig über die
    # Segmente; bezahlte Pause wird zur eigenen Position (faktor = 1).
    faktor = Fraction(1) if anfrage.pausen_bezahlt or brutto == 0 else Fraction(netto, brutto)

    # Sammel-Schlüssel: (lohnart, bezeichnung, satz_exakt, maske_id) → Minuten exakt.
    minuten_je_position: dict[tuple, Fraction] = {}
    erster_grund_satz: int | None = None

    for chunk_von, chunk_bis, tag in _tages_chunks(anfrage.beginn_utc,
                                                   anfrage.ende_utc, zone):
        konfig = konfig_je_tag(tag)
        grund_satz = konfig.stundenlohn_cent
        if grund_satz < konfig.mindestlohn_cent:   # R-06: anheben + Hinweis
            grund_satz = konfig.mindestlohn_cent
            hinweis = (f"Mindestlohn angehoben: {konfig.stundenlohn_cent / 100:.2f} € → "
                       f"{konfig.mindestlohn_cent / 100:.2f} € (ab {tag.strftime('%d.%m.%Y')})")
            if hinweis not in hinweise:
                hinweise.append(hinweis)
        if erster_grund_satz is None:
            erster_grund_satz = grund_satz

        chunk_minuten = int((chunk_bis - chunk_von).total_seconds() // 60)
        schluessel = (GRUNDLOHN_LOHNART, f"Grundlohn ({konfig.tarif_code})",
                      Fraction(grund_satz), None)
        minuten_je_position[schluessel] = (
            minuten_je_position.get(schluessel, Fraction(0))
            + Fraction(chunk_minuten) * faktor)

        segmente = zerlege(chunk_von, chunk_bis,
                           [m.maske for m in konfig.masken], set(konfig.feiertage),
                           zone=zone)
        masken_index = {m.maske.bezeichnung: m for m in konfig.masken}
        for segment in segmente:
            for name in segment.masken:
                mk = masken_index[name]
                satz = _zuschlag_satz(mk, grund_satz, konfig.stundenlohn_cent)
                schluessel = (mk.lohnart_nummer, mk.lohnart_bezeichnung, satz, mk.maske_id)
                minuten_je_position[schluessel] = (
                    minuten_je_position.get(schluessel, Fraction(0))
                    + Fraction(segment.minuten) * faktor)

    positionen: list[LohnPosition] = []
    if anfrage.pausen_bezahlt and pause > 0 and erster_grund_satz is not None:
        betrag = Fraction(pause) * Fraction(erster_grund_satz) / 60
        positionen.append(LohnPosition(
            lohnart_nummer=PAUSE_LOHNART, bezeichnung="Bezahlte Pause",
            minuten=pause, satz_cent=erster_grund_satz,
            betrag_cent=_runde_cent(betrag), zuschlagsmaske_id=None))

    for (lohnart, bezeichnung, satz, maske_id), minuten in minuten_je_position.items():
        betrag = minuten * satz / 60
        positionen.append(LohnPosition(
            lohnart_nummer=lohnart, bezeichnung=bezeichnung,
            minuten=_runde_cent(minuten),   # Minuten ganzzahlig, kaufmännisch
            satz_cent=_runde_cent(satz),
            betrag_cent=_runde_cent(betrag), zuschlagsmaske_id=maske_id))

    positionen.sort(key=lambda p: (p.lohnart_nummer, p.bezeichnung))
    bezahlte = brutto if anfrage.pausen_bezahlt else netto
    return LohnErgebnis(
        positionen=tuple(positionen),
        summe_cent=sum(p.betrag_cent for p in positionen),
        bezahlte_minuten=bezahlte,
        hinweise=tuple(hinweise),
    )


def berechne_umsatz(anfrage: UmsatzAnfrage,
                    konfig_je_tag: Callable[[date], UmsatzKonfig],
                    zone: ZoneInfo = STANDARD_ZONE) -> UmsatzErgebnis:
    brutto = int((anfrage.ende_utc - anfrage.beginn_utc).total_seconds() // 60)
    pause = min(anfrage.pause_minuten, brutto)
    netto = brutto - pause
    faktor = Fraction(1) if anfrage.pausen_bezahlt or brutto == 0 else Fraction(netto, brutto)

    minuten_je_position: dict[tuple, Fraction] = {}
    for chunk_von, chunk_bis, tag in _tages_chunks(anfrage.beginn_utc,
                                                   anfrage.ende_utc, zone):
        konfig = konfig_je_tag(tag)
        chunk_minuten = int((chunk_bis - chunk_von).total_seconds() // 60)
        basis_schluessel = ("Bewachung", Fraction(konfig.satz_cent_pro_stunde), "GRUND")
        minuten_je_position[basis_schluessel] = (
            minuten_je_position.get(basis_schluessel, Fraction(0))
            + Fraction(chunk_minuten) * faktor)

        if konfig.zuschlag_weiterberechnung == "KEINE":
            continue
        anteil = Fraction(1) if konfig.zuschlag_weiterberechnung == "VOLL" else \
            Fraction(konfig.weiterberechnung_prozent, 100)
        segmente = zerlege(chunk_von, chunk_bis,
                           [m.maske for m in konfig.masken], set(konfig.feiertage),
                           zone=zone)
        masken_index = {m.maske.bezeichnung: m for m in konfig.masken}
        for segment in segmente:
            for name in segment.masken:
                mk = masken_index[name]
                satz = (Fraction(konfig.satz_cent_pro_stunde)
                        * Fraction(mk.prozent or 0, 100) * anteil)
                schluessel = (f"Zuschlag {mk.maske.bezeichnung}", satz, "ZUSCHLAG")
                minuten_je_position[schluessel] = (
                    minuten_je_position.get(schluessel, Fraction(0))
                    + Fraction(segment.minuten) * faktor)

    positionen = []
    for (bezeichnung, satz, leistungsart), minuten in minuten_je_position.items():
        betrag = minuten * satz / 60
        positionen.append(UmsatzPosition(
            bezeichnung=bezeichnung, minuten=_runde_cent(minuten),
            satz_cent=_runde_cent(satz), betrag_cent=_runde_cent(betrag),
            leistungsart=leistungsart))
    positionen.sort(key=lambda p: (p.leistungsart, p.bezeichnung))
    return UmsatzErgebnis(
        positionen=tuple(positionen),
        summe_netto_cent=sum(p.betrag_cent for p in positionen),
        minuten=brutto if anfrage.pausen_bezahlt else netto,
    )

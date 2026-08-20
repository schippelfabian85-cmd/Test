"""Minutengenaue Segmentzerlegung (M04, R-01/R-02/R-10 und Abschnitt 10).

Reine Rechenlogik ohne Datenbankzugriff: Eine Schicht (UTC) wird gegen
Zuschlagsmasken und Feiertage in Segmente mit identischer Maskenmenge
zerlegt. Die Maskenzuordnung folgt der lokalen Uhrzeit (Europe/Berlin),
die bezahlten Minuten der realen UTC-Dauer — damit sind die
Zeitumstellungsnächte (23 h/25 h) korrekt (R-10).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

STANDARD_ZONE = ZoneInfo("Europe/Berlin")

KUMULIERT = "KUMULIERT"
VERDRAENGT = "VERDRAENGT"

ALLE_WOCHENTAGE = frozenset(range(7))  # 0 = Montag … 6 = Sonntag


@dataclass(frozen=True)
class Zuschlagsmaske:
    bezeichnung: str
    prioritaet: int                       # höher gewinnt (R-02)
    kumulierung: str = KUMULIERT          # KUMULIERT | VERDRAENGT
    wochentage: frozenset = ALLE_WOCHENTAGE
    von_uhrzeit: time = time(0)
    bis_uhrzeit: time = time(0)           # bis exklusiv; bis <= von: über Mitternacht,
                                          # von == bis == 00:00: ganztägig
    gilt_an_feiertagen: bool = False
    gilt_an_sonntagen: bool = False

    def _tag_gilt(self, tag: date, feiertage: frozenset) -> bool:
        if tag.weekday() in self.wochentage:
            return True
        if self.gilt_an_sonntagen and tag.weekday() == 6:
            return True
        if self.gilt_an_feiertagen and tag in feiertage:
            return True
        return False

    def gilt(self, lokal: datetime, feiertage: frozenset) -> bool:
        t = lokal.time()
        if self.von_uhrzeit < self.bis_uhrzeit:
            return self.von_uhrzeit <= t < self.bis_uhrzeit and self._tag_gilt(
                lokal.date(), feiertage
            )
        # Fenster über Mitternacht: der Teil nach 00:00 gehört fachlich zum
        # Vortag (die "Nacht von Samstag" endet Sonntag früh).
        if t >= self.von_uhrzeit:
            return self._tag_gilt(lokal.date(), feiertage)
        if t < self.bis_uhrzeit:
            return self._tag_gilt(lokal.date() - timedelta(days=1), feiertage)
        return False


@dataclass(frozen=True)
class Segment:
    beginn_utc: datetime
    ende_utc: datetime
    minuten: int
    masken: tuple[str, ...]               # Bezeichnungen, nach Priorität absteigend


def _aufgeloeste_masken(
    lokal: datetime, masken: list[Zuschlagsmaske], feiertage: frozenset
) -> tuple[str, ...]:
    aktive = sorted(
        (m for m in masken if m.gilt(lokal, feiertage)),
        key=lambda m: (-m.prioritaet, m.bezeichnung),
    )
    ergebnis = []
    for maske in aktive:
        ergebnis.append(maske.bezeichnung)
        if maske.kumulierung == VERDRAENGT:
            break  # verdrängt alle Masken niedrigerer Priorität (R-02)
    return tuple(ergebnis)


def zerlege(
    beginn_utc: datetime,
    ende_utc: datetime,
    masken: list[Zuschlagsmaske],
    feiertage: set[date],
    zone: ZoneInfo = STANDARD_ZONE,
) -> list[Segment]:
    """Zerlegt [beginn_utc, ende_utc) in Segmente identischer Maskenmenge.

    Die Segmente sind lückenlos, überlappungsfrei und summieren sich exakt
    auf die reale Dauer der Schicht. Minuten ohne Maske erscheinen als
    Segment mit leerer Maskenmenge (Grundlohnzeit).
    """
    if ende_utc <= beginn_utc:
        raise ValueError("ende_utc muss nach beginn_utc liegen")
    feiertage_fest = frozenset(feiertage)
    gesamt_minuten = int((ende_utc - beginn_utc).total_seconds() // 60)

    segmente: list[Segment] = []
    lauf_start = 0
    lauf_masken = _aufgeloeste_masken(beginn_utc.astimezone(zone), masken, feiertage_fest)
    for i in range(1, gesamt_minuten + 1):
        if i < gesamt_minuten:
            minute = beginn_utc + timedelta(minutes=i)
            aktuelle = _aufgeloeste_masken(minute.astimezone(zone), masken, feiertage_fest)
            if aktuelle == lauf_masken:
                continue
        else:
            aktuelle = None  # Schichtende erzwingt Segmentabschluss
        segmente.append(Segment(
            beginn_utc=beginn_utc + timedelta(minutes=lauf_start),
            ende_utc=beginn_utc + timedelta(minutes=i),
            minuten=i - lauf_start,
            masken=lauf_masken,
        ))
        lauf_start = i
        lauf_masken = aktuelle
    return segmente

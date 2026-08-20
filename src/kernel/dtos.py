"""Provisorische Kernel-Verträge.

`00_KERNEL.md` liegt diesem Repository noch nicht bei. Dieses Paket bildet
die aus den Modulspezifikationen ableitbaren Konventionen ab (UTC-Zeitstempel,
Minuten- und Cent-Beträge, Verstoß-Stufen) und ist beim Eintreffen des
Kernels gegen dessen Definitionen abzugleichen — siehe
PLAUSIBILITAETSPRUEFUNG.md, Abschnitt 6.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

BLOCKIEREND = "BLOCKIEREND"
WARNUNG = "WARNUNG"
HINWEIS = "HINWEIS"


@dataclass(frozen=True)
class SchichtDTO:
    id: UUID
    objekt_id: UUID
    beginn_utc: datetime
    ende_utc: datetime
    pause_minuten: int = 0

    def __post_init__(self) -> None:
        for name in ("beginn_utc", "ende_utc"):
            wert: datetime = getattr(self, name)
            if wert.tzinfo is None or wert.utcoffset() != timezone.utc.utcoffset(None):
                raise ValueError(f"{name} muss zeitzonenbewusst in UTC vorliegen")
        if self.ende_utc <= self.beginn_utc:
            raise ValueError("ende_utc muss nach beginn_utc liegen")
        if not 0 <= self.pause_minuten:
            raise ValueError("pause_minuten darf nicht negativ sein")

    @property
    def brutto_minuten(self) -> int:
        return int((self.ende_utc - self.beginn_utc).total_seconds() // 60)

    @property
    def netto_minuten(self) -> int:
        return max(0, self.brutto_minuten - self.pause_minuten)


@dataclass(frozen=True)
class VertragsgrenzenDTO:
    kategorie: str
    soll_minuten_monat: int
    min_minuten_monat: int | None
    max_minuten_monat: int | None
    max_verdienst_monat_cent: int | None
    max_einsatztage_jahr: int | None
    pausen_bezahlt: bool
    zeitwertkonto_aktiv: bool
    ist_minderjaehrig: bool

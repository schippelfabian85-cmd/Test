"""Kernel-DTOs — jetzt gegen 00_KERNEL.md §7 abgeglichen.

K-10: DTOs sind unveränderlich und enthalten keine Objektreferenzen auf
andere Module — nur IDs und primitive Werte.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

BLOCKIEREND = "BLOCKIEREND"
WARNUNG = "WARNUNG"
HINWEIS = "HINWEIS"

# Zustandsautomat der Schicht (Kernel §5)
SCHICHT_ZUSTAENDE = (
    "GEPLANT", "BESETZT", "ANGEMELDET", "ERFASST", "GEPRUEFT",
    "ABGEGLICHEN", "ABGERECHNET", "AUSGEFALLEN", "STORNIERT",
)


@dataclass(frozen=True)
class SchichtDTO:
    """Verbindliche Form aus Kernel §7 — wird nicht erweitert (M05 §3)."""

    id: UUID
    tenant_id: UUID
    objekt_id: UUID
    mitarbeiter_id: UUID | None
    subunternehmer_id: UUID | None
    beginn_utc: datetime
    ende_utc: datetime
    pause_minuten: int
    funktion_code: str
    zustand: str
    schichtkuerzel: str

    def __post_init__(self) -> None:
        for name in ("beginn_utc", "ende_utc"):
            wert: datetime = getattr(self, name)
            if wert.tzinfo is None or wert.utcoffset() != timezone.utc.utcoffset(None):
                raise ValueError(f"{name} muss zeitzonenbewusst in UTC vorliegen")
        if self.ende_utc <= self.beginn_utc:
            raise ValueError("ende_utc muss nach beginn_utc liegen")
        if self.pause_minuten < 0:
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
    ist_minderjaehrig: bool          # aus Geburtsdatum am Stichtag

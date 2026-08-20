"""Datenverträge des Regelpruef-Ports (M06, Abschnitt 3)."""

from dataclasses import dataclass, field
from uuid import UUID

from kernel.dtos import SchichtDTO, VertragsgrenzenDTO


@dataclass(frozen=True)
class PruefKontext:
    tenant_id: UUID
    mitarbeiter_id: UUID
    objekt_id: UUID
    geplante_schicht: SchichtDTO
    # Alles Folgende wird vom Aufrufer mitgeliefert — M06 lädt nichts selbst:
    bestehende_schichten: tuple[SchichtDTO, ...]   # +/- 14 Tage um die neue
    qualifikationen: tuple[str, ...]               # gültig am Schichttag
    erforderliche_qualifikationen: tuple[str, ...]
    objekt_freigegeben: bool
    verfuegbar: bool
    verfuegbarkeit_grund: str | None
    ausserhalb_bereitschaft: bool                  # aus M07 (VF_BEREITSCHAFT)
    minuten_monat_bisher: int
    minuten_24_wochen_bisher: int                  # Summe der letzten 24 Wochen (AZ_WOCHE_MAX)
    grenzen: VertragsgrenzenDTO                    # enthält ist_minderjaehrig
    verdienst_monat_bisher_cent: int
    verdienst_geplante_schicht_cent: int           # vom Aufrufer über EntgeltPort ermittelt
    einsatztage_jahr_bisher: int


@dataclass(frozen=True)
class Verstoss:
    regel_code: str
    stufe: str
    text: str
    rechtsgrundlage: str
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PruefErgebnis:
    zulaessig: bool                 # False, sobald ein BLOCKIEREND vorliegt
    verstoesse: tuple[Verstoss, ...]

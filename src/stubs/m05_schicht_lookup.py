"""SchichtLookupPort-Stub (M05 §10, K-2).

Stellt für die Seed-Objekte 4 Wochen Schichten bereit, davon 2 Wochen
abgeglichen. Feste IDs `55555555-…`. Enthält zwingend: eine unbesetzte
Schicht, eine Nachtschicht über Mitternacht, eine ausgefallene.
Deterministisch, ohne Datenbank.
"""

from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from kernel.dtos import SchichtDTO

ZONE = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")

TENANT = UUID("00000000-0000-0000-0000-000000000001")
PLAN_START = date(2026, 8, 3)   # Montag; Wochen 1–2 abgeglichen, 3–4 besetzt
PLAN_WOCHEN = 4


def _mitarbeiter(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")

def _objekt(nr: int) -> UUID:
    return UUID(f"22222222-2222-2222-2222-{nr:012d}")

def _schicht_id(nr: int) -> UUID:
    return UUID(f"55555555-5555-5555-5555-{nr:012d}")


def _utc(tag: date, uhrzeit: time) -> datetime:
    return datetime.combine(tag, uhrzeit, tzinfo=ZONE).astimezone(UTC)


def _baue_schichten() -> list[SchichtDTO]:
    schichten: list[SchichtDTO] = []
    laufnr = 1
    for woche in range(PLAN_WOCHEN):
        for tag_index in range(7):
            tag = PLAN_START + timedelta(days=woche * 7 + tag_index)
            zustand = "ABGEGLICHEN" if woche < 2 else "BESETZT"
            # Objekt 1: Pforte 24/7 — Tag- und Nachtschicht
            schichten.append(SchichtDTO(
                id=_schicht_id(laufnr), tenant_id=TENANT, objekt_id=_objekt(1),
                mitarbeiter_id=_mitarbeiter(1 + (woche + tag_index) % 4),
                subunternehmer_id=None,
                beginn_utc=_utc(tag, time(6)), ende_utc=_utc(tag, time(18)),
                pause_minuten=45, funktion_code="WACH", zustand=zustand,
                schichtkuerzel="T",
            )); laufnr += 1
            schichten.append(SchichtDTO(   # Nachtschicht über Mitternacht (K-7)
                id=_schicht_id(laufnr), tenant_id=TENANT, objekt_id=_objekt(1),
                mitarbeiter_id=_mitarbeiter(5 + (woche + tag_index) % 4),
                subunternehmer_id=None,
                beginn_utc=_utc(tag, time(18)),
                ende_utc=_utc(tag + timedelta(days=1), time(6)),
                pause_minuten=45, funktion_code="WACH", zustand=zustand,
                schichtkuerzel="N",
            )); laufnr += 1
            # Objekt 4: Empfang, nur werktags
            if tag_index < 5:
                schichten.append(SchichtDTO(
                    id=_schicht_id(laufnr), tenant_id=TENANT, objekt_id=_objekt(4),
                    mitarbeiter_id=_mitarbeiter(9 + (woche + tag_index) % 2),
                    subunternehmer_id=None,
                    beginn_utc=_utc(tag, time(8)), ende_utc=_utc(tag, time(16)),
                    pause_minuten=30, funktion_code="EMPFANG", zustand=zustand,
                    schichtkuerzel="E",
                )); laufnr += 1

    # Pflichtfälle laut M05 §10: unbesetzt und ausgefallen (in Woche 4).
    letzter_montag = PLAN_START + timedelta(days=21)
    schichten.append(SchichtDTO(
        id=_schicht_id(9001), tenant_id=TENANT, objekt_id=_objekt(3),
        mitarbeiter_id=None, subunternehmer_id=None,
        beginn_utc=_utc(letzter_montag, time(20)),
        ende_utc=_utc(letzter_montag + timedelta(days=1), time(2)),
        pause_minuten=0, funktion_code="STREIFE", zustand="GEPLANT",
        schichtkuerzel="S",
    ))
    schichten.append(SchichtDTO(
        id=_schicht_id(9002), tenant_id=TENANT, objekt_id=_objekt(4),
        mitarbeiter_id=_mitarbeiter(5), subunternehmer_id=None,
        beginn_utc=_utc(letzter_montag + timedelta(days=1), time(8)),
        ende_utc=_utc(letzter_montag + timedelta(days=1), time(16)),
        pause_minuten=30, funktion_code="EMPFANG", zustand="AUSGEFALLEN",
        schichtkuerzel="E",
    ))
    return schichten


class SchichtLookupPortStub:
    """Implementiert SchichtLookupPortV1 (M05 §3) über feste Beispieldaten."""

    def __init__(self, schichten: list[SchichtDTO] | None = None):
        self._schichten = list(schichten) if schichten is not None else _baue_schichten()

    def schicht(self, schicht_id: UUID) -> SchichtDTO | None:
        return next((s for s in self._schichten if s.id == schicht_id), None)

    def schichten_person(self, mitarbeiter_id: UUID, von: date, bis: date) -> list[SchichtDTO]:
        return [s for s in self._schichten
                if s.mitarbeiter_id == mitarbeiter_id
                and von <= s.beginn_utc.astimezone(ZONE).date() <= bis]

    def schichten_objekt(self, objekt_id: UUID, von: date, bis: date) -> list[SchichtDTO]:
        return [s for s in self._schichten
                if s.objekt_id == objekt_id
                and von <= s.beginn_utc.astimezone(ZONE).date() <= bis]

    def offene_schichten(self, tenant_id: UUID, von: date, bis: date) -> list[SchichtDTO]:
        return [s for s in self._schichten
                if s.tenant_id == tenant_id and s.zustand == "GEPLANT"
                and von <= s.beginn_utc.astimezone(ZONE).date() <= bis]

    def setze_zustand(self, schicht_id: UUID, neuer_zustand: str,
                      actor_id: UUID, grund: str | None) -> None:
        for i, s in enumerate(self._schichten):
            if s.id == schicht_id:
                from dataclasses import replace
                self._schichten[i] = replace(s, zustand=neuer_zustand)
                return

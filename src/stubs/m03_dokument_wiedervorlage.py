"""Stubs für die M03-Ports (K-2), bis M03 gebaut ist.

DokumentPort-Stub: gibt IDs zurück und legt Dateien im lokalen Verzeichnis
ab (genau wie in M02 §4 beschrieben). WiedervorlagePort-Stub: führt
Wiedervorlagen im Speicher und dedupliziert je (bezug, titel) — damit
erzeugt der M02-R-08-Lauf „genau eine" Wiedervorlage (AC 8).
"""

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import UUID

from kernel.ids import uuid7


class DokumentPortStub:
    def __init__(self, verzeichnis: str = "daten/dokumente"):
        self._verzeichnis = verzeichnis
        self._index: dict[UUID, tuple[str, str]] = {}   # id -> (pfad, dateiname)

    def ablegen(self, tenant_id: UUID, datei: bytes, dateiname: str,
                kategorie: str, bezug_typ: str, bezug_id: UUID) -> UUID:
        os.makedirs(self._verzeichnis, exist_ok=True)
        dokument_id = uuid7()
        pfad = os.path.join(self._verzeichnis, f"{dokument_id}_{dateiname}")
        with open(pfad, "wb") as ziel:
            ziel.write(datei)
        self._index[dokument_id] = (pfad, dateiname)
        return dokument_id

    def abrufen(self, dokument_id: UUID) -> tuple[bytes, str]:
        pfad, dateiname = self._index[dokument_id]
        with open(pfad, "rb") as quelle:
            return quelle.read(), dateiname

    def loeschen(self, dokument_id: UUID, grund: str) -> None:
        self._index.pop(dokument_id, None)


@dataclass(frozen=True)
class WiedervorlageEintrag:
    id: UUID
    tenant_id: UUID
    bezug_typ: str
    bezug_id: UUID
    titel: str
    faellig_am: date
    zustaendig_benutzer_id: UUID | None
    status: str = "OFFEN"
    erstellt_am: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WiedervorlagePortStub:
    def __init__(self):
        self.eintraege: list[WiedervorlageEintrag] = []

    def anlegen(self, tenant_id: UUID, bezug_typ: str, bezug_id: UUID,
                titel: str, faellig_am: date,
                zustaendig_benutzer_id: UUID | None = None) -> UUID:
        for e in self.eintraege:
            if (e.bezug_typ, e.bezug_id, e.titel) == (bezug_typ, bezug_id, titel):
                return e.id   # idempotent — genau eine Wiedervorlage je Anlass
        eintrag = WiedervorlageEintrag(
            id=uuid7(), tenant_id=tenant_id, bezug_typ=bezug_typ, bezug_id=bezug_id,
            titel=titel, faellig_am=faellig_am,
            zustaendig_benutzer_id=zustaendig_benutzer_id,
        )
        self.eintraege.append(eintrag)
        return eintrag.id

    def erledigen(self, wiedervorlage_id: UUID, benutzer_id: UUID) -> None:
        self.eintraege = [e for e in self.eintraege if e.id != wiedervorlage_id]

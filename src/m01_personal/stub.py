"""MitarbeiterPortStub (M01 §10): 12 Personen, deterministisch, ohne Datenbank.

Feste IDs `11111111-…-0001` bis `-0012`. Darunter zwingend: eine
minderjährige Person (-0004), eine geringfügig beschäftigte (-0006/-0007),
eine ausgeschiedene (-0012).
"""

from dataclasses import replace
from datetime import date
from uuid import UUID

from kernel.dtos import VertragsgrenzenDTO
from m01_personal.port import MitarbeiterDTO

TENANT = UUID("00000000-0000-0000-0000-000000000001")


def _id(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")


_VOLLZEIT = VertragsgrenzenDTO(
    kategorie="VOLLZEIT", soll_minuten_monat=10080, min_minuten_monat=None,
    max_minuten_monat=12000, max_verdienst_monat_cent=None,
    max_einsatztage_jahr=None, pausen_bezahlt=False, zeitwertkonto_aktiv=False,
    ist_minderjaehrig=False,
)
_TEILZEIT = replace(_VOLLZEIT, kategorie="TEILZEIT", soll_minuten_monat=4800,
                    max_minuten_monat=6000)
_GERINGFUEGIG = replace(_VOLLZEIT, kategorie="GERINGFUEGIG", soll_minuten_monat=2400,
                        max_minuten_monat=2700, max_verdienst_monat_cent=55600)
_KURZFRISTIG = replace(_VOLLZEIT, kategorie="KURZFRISTIG", soll_minuten_monat=0,
                       max_einsatztage_jahr=70)

_KATEGORIEN = {
    1: _VOLLZEIT, 2: _VOLLZEIT, 3: _VOLLZEIT, 4: _VOLLZEIT,
    5: _TEILZEIT, 6: _TEILZEIT, 7: _TEILZEIT, 8: _TEILZEIT,
    9: _GERINGFUEGIG, 10: _GERINGFUEGIG, 11: _KURZFRISTIG, 12: _KURZFRISTIG,
}

_NAMEN = ["Albrecht", "Bergmann", "Conrad", "Dietrich", "Ehlers", "Fromm",
          "Grunwald", "Hartung", "Ilgner", "Jost", "Kaminski", "Lorenz"]
_VORNAMEN = ["Anna", "Bela", "Clara", "Deniz", "Elif", "Falk",
             "Greta", "Hanno", "Ivo", "Jule", "Kim", "Lars"]


def _person(nr: int) -> MitarbeiterDTO:
    geburtsdatum = date(1990, 3, 14)
    if nr == 4:                     # minderjährig (wird 18 im Jahr 2027)
        geburtsdatum = date(2009, 5, 20)
    status, austritt = "AKTIV", None
    if nr == 12:                    # ausgeschieden
        status, austritt = "AUSGESCHIEDEN", date(2026, 6, 30)
    return MitarbeiterDTO(
        id=_id(nr), tenant_id=TENANT, personalnummer=f"P{nr:04d}",
        nachname=_NAMEN[nr - 1], vorname=_VORNAMEN[nr - 1],
        geburtsdatum=geburtsdatum, status=status,
        eintrittsdatum=date(2024, 1, 1), austrittsdatum=austritt,
        funktion_codes=("WACH",) if nr <= 8 else ("WACH", "EMPFANG"),
        kostenstelle_nummer="1000",
    )


class MitarbeiterPortStub:
    """12 Personen aus seed/basis, deterministisch, ohne Datenbank."""

    def __init__(self):
        self._personen = {n: _person(n) for n in range(1, 13)}

    def mitarbeiter(self, id: UUID) -> MitarbeiterDTO | None:
        return next((p for p in self._personen.values() if p.id == id), None)

    def suche(self, tenant_id: UUID, status: str | None = None,
              funktion_code: str | None = None) -> list[MitarbeiterDTO]:
        treffer = [p for p in self._personen.values() if p.tenant_id == tenant_id]
        if status:
            treffer = [p for p in treffer if p.status == status]
        if funktion_code:
            treffer = [p for p in treffer if funktion_code in p.funktion_codes]
        return treffer

    def vertragsgrenzen(self, mitarbeiter_id: UUID, stichtag: date) -> VertragsgrenzenDTO:
        nr = int(str(mitarbeiter_id)[-4:])
        grenzen = _KATEGORIEN[nr]
        person = self._personen[nr]
        achtzehnter = date(person.geburtsdatum.year + 18, person.geburtsdatum.month,
                           person.geburtsdatum.day)
        return replace(grenzen, ist_minderjaehrig=stichtag < achtzehnter)

    def ist_aktiv(self, mitarbeiter_id: UUID, stichtag: date) -> bool:
        person = self.mitarbeiter(mitarbeiter_id)
        if person is None or person.status != "AKTIV":
            return False
        if stichtag < person.eintrittsdatum:
            return False
        return person.austrittsdatum is None or stichtag <= person.austrittsdatum

"""Regel- und Verstoß-Engine (M06).

Implementiert `RegelpruefPortV1`: Prüfung, Katalogkonfiguration (R-01/R-02),
Ausnahmen mit Begründung und Genehmiger (R-02), Übersteuerung blockierender
Verstöße nur durch ADMIN mit Protokoll (R-03).

M06 konsumiert keine Ports — alle Fachdaten kommen im PruefKontext an.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from kernel.dtos import BLOCKIEREND
from m06_regelengine.katalog import Regel, auslieferungskatalog
from m06_regelengine.kontext import PruefErgebnis, PruefKontext, Verstoss
from m06_regelengine.regeln import RegelUmgebung
from m06_regelengine.zeit import STANDARD_ZONE


class FehlerM06(Exception):
    def __init__(self, code: str, meldung: str):
        self.code = code
        super().__init__(f"{code}: {meldung}")


@dataclass(frozen=True)
class RegelAusnahme:
    """R-02: je Objekt, Person oder Vertragstyp — mit Begründung und Genehmiger."""

    regel_code: str
    begruendung: str
    genehmigt_von: str
    gueltig_ab: date
    gueltig_bis: date | None = None
    objekt_id: UUID | None = None
    mitarbeiter_id: UUID | None = None
    vertragstyp_kategorie: str | None = None

    def __post_init__(self) -> None:
        if not self.begruendung.strip():
            raise FehlerM06("M06-E-001", "Ausnahme ohne Begründung ist unzulässig")
        if not self.genehmigt_von.strip():
            raise FehlerM06("M06-E-001", "Ausnahme ohne Genehmiger ist unzulässig")

    def greift(self, kontext: PruefKontext, schichttag: date) -> bool:
        if self.gueltig_ab > schichttag:
            return False
        if self.gueltig_bis is not None and self.gueltig_bis < schichttag:
            return False
        if self.objekt_id is not None and self.objekt_id != kontext.objekt_id:
            return False
        if self.mitarbeiter_id is not None and self.mitarbeiter_id != kontext.mitarbeiter_id:
            return False
        if (self.vertragstyp_kategorie is not None
                and self.vertragstyp_kategorie != kontext.grenzen.kategorie):
            return False
        return True


@dataclass(frozen=True)
class VerstossProtokollEintrag:
    id: UUID
    tenant_id: UUID
    schicht_id: UUID
    regel_code: str
    stufe: str
    festgestellt_am: datetime
    uebersteuert_von: str | None = None
    uebersteuerungsgrund: str | None = None


class Regelpruefung:
    """Implementiert RegelpruefPortV1."""

    def __init__(self, katalog: list[Regel] | None = None,
                 zone: ZoneInfo = STANDARD_ZONE):
        self._regeln: dict[str, Regel] = {
            r.code: r for r in (katalog if katalog is not None else auslieferungskatalog())
        }
        self._zone = zone
        self._ausnahmen: list[RegelAusnahme] = []
        self.protokoll: list[VerstossProtokollEintrag] = []

    # -- Katalogkonfiguration (R-01/R-02) ---------------------------------

    def regel(self, code: str) -> Regel:
        if code not in self._regeln:
            raise FehlerM06("M06-E-010", f"Unbekannter Regelcode {code!r}")
        return self._regeln[code]

    def aktiviere(self, code: str) -> None:
        self.regel(code).aktiv = True

    def deaktiviere(self, code: str) -> None:
        self.regel(code).aktiv = False

    def setze_parameter(self, code: str, **parameter) -> None:
        self.regel(code).parameter.update(parameter)

    def fuege_ausnahme_hinzu(self, ausnahme: RegelAusnahme) -> None:
        self.regel(ausnahme.regel_code)  # validiert den Code
        self._ausnahmen.append(ausnahme)

    # -- Prüfung ----------------------------------------------------------

    def pruefe(self, kontext: PruefKontext) -> PruefErgebnis:
        umgebung = RegelUmgebung(
            aktive_codes=frozenset(c for c, r in self._regeln.items() if r.aktiv),
            zone=self._zone,
        )
        schichttag = kontext.geplante_schicht.beginn_utc.astimezone(self._zone).date()
        verstoesse: list[Verstoss] = []
        for regel in sorted(self._regeln.values(), key=lambda r: r.reihenfolge):
            if not regel.aktiv:
                continue
            if any(a.regel_code == regel.code and a.greift(kontext, schichttag)
                   for a in self._ausnahmen):
                continue
            for befund in regel.pruefung(kontext, regel.parameter, umgebung):
                verstoss = Verstoss(
                    regel_code=regel.code,
                    stufe=regel.stufe,
                    text=befund["text"],
                    rechtsgrundlage=regel.rechtsgrundlage,
                    details=befund.get("details", {}),
                )
                verstoesse.append(verstoss)
                self.protokoll.append(VerstossProtokollEintrag(
                    id=uuid4(),
                    tenant_id=kontext.tenant_id,
                    schicht_id=kontext.geplante_schicht.id,
                    regel_code=regel.code,
                    stufe=regel.stufe,
                    festgestellt_am=datetime.now(timezone.utc),
                ))
        zulaessig = not any(v.stufe == BLOCKIEREND for v in verstoesse)
        return PruefErgebnis(zulaessig=zulaessig, verstoesse=tuple(verstoesse))

    def pruefe_stapel(self, kontexte: list[PruefKontext]) -> list[PruefErgebnis]:
        return [self.pruefe(kontext) for kontext in kontexte]

    # -- Übersteuerung (R-03) ---------------------------------------------

    def uebersteuere(self, tenant_id: UUID, schicht_id: UUID, regel_code: str,
                     benutzer: str, rolle: str, grund: str) -> VerstossProtokollEintrag:
        if rolle != "ADMIN":
            raise FehlerM06(
                "M06-E-002",
                "Übersteuerung blockierender Verstöße ist nur der Rolle ADMIN erlaubt",
            )
        if not grund.strip():
            raise FehlerM06("M06-E-001", "Übersteuerung ohne Grund wird abgelehnt")
        regel = self.regel(regel_code)
        eintrag = VerstossProtokollEintrag(
            id=uuid4(),
            tenant_id=tenant_id,
            schicht_id=schicht_id,
            regel_code=regel_code,
            stufe=regel.stufe,
            festgestellt_am=datetime.now(timezone.utc),
            uebersteuert_von=benutzer,
            uebersteuerungsgrund=grund,
        )
        self.protokoll.append(eintrag)
        return eintrag

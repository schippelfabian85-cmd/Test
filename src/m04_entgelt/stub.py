"""EntgeltPortStub (M04 §9, K-2): Tarif „Wach- und Sicherheitsgewerbe Muster",
Lohngruppen 1–3, Masken Nacht (23–06, 25 %), Sonntag (50 %), Feiertag (100 %),
Feiertage für Sachsen-Anhalt und Bayern. Ohne Datenbank, deterministisch."""

from datetime import date, time
from uuid import UUID

from m04_entgelt import berechnung
from m04_entgelt.zerlegung import Zuschlagsmaske

FEIERTAGE_2026 = {
    "ST": {date(2026, 1, 1), date(2026, 1, 6), date(2026, 4, 3), date(2026, 4, 6),
           date(2026, 5, 1), date(2026, 5, 14), date(2026, 5, 25),
           date(2026, 10, 3), date(2026, 10, 31), date(2026, 12, 25),
           date(2026, 12, 26)},
    "BY": {date(2026, 1, 1), date(2026, 1, 6), date(2026, 4, 3), date(2026, 4, 6),
           date(2026, 5, 1), date(2026, 5, 14), date(2026, 5, 25),
           date(2026, 6, 4),                       # Fronleichnam
           date(2026, 8, 15), date(2026, 10, 3), date(2026, 11, 1),
           date(2026, 12, 25), date(2026, 12, 26)},
}

MINDESTLOHN = [(date(2026, 1, 1), 1390), (date(2025, 1, 1), 1282), (date(2000, 1, 1), 0)]

LOHNGRUPPEN = {   # Funktion → (Lohngruppe, Stundenlohn in Cent)
    "WACH": ("LG1", 1450),
    "EMPFANG": ("LG1", 1450),
    "STREIFE": ("LG2", 1550),
    "OBJEKTLEITER": ("LG3", 1750),
}


def _masken() -> tuple[berechnung.MaskenKonfig, ...]:
    return (
        berechnung.MaskenKonfig(
            maske=Zuschlagsmaske(bezeichnung="Nacht", prioritaet=10,
                                 von_uhrzeit=time(23), bis_uhrzeit=time(6)),
            maske_id=UUID("44444444-4444-4444-4444-000000000001"),
            lohnart_nummer="2010", lohnart_bezeichnung="Nachtzuschlag",
            bemessung="GRUNDLOHN", prozent=25),
        berechnung.MaskenKonfig(
            maske=Zuschlagsmaske(bezeichnung="Sonntag", prioritaet=20,
                                 wochentage=frozenset({6})),
            maske_id=UUID("44444444-4444-4444-4444-000000000002"),
            lohnart_nummer="2020", lohnart_bezeichnung="Sonntagszuschlag",
            bemessung="GRUNDLOHN", prozent=50),
        berechnung.MaskenKonfig(
            maske=Zuschlagsmaske(bezeichnung="Feiertag", prioritaet=30,
                                 wochentage=frozenset(), gilt_an_feiertagen=True),
            maske_id=UUID("44444444-4444-4444-4444-000000000003"),
            lohnart_nummer="2030", lohnart_bezeichnung="Feiertagszuschlag",
            bemessung="GRUNDLOHN", prozent=100),
    )


def _mindestlohn_am(tag: date) -> int:
    for ab, betrag in MINDESTLOHN:
        if tag >= ab:
            return betrag
    return 0


class EntgeltPortStub:
    """Implementiert EntgeltPortV1 als reine Funktionsbibliothek ohne Datenbank."""

    def __init__(self, verrechnungssatz_cent: int = 2950,
                 zuschlag_weiterberechnung: str = "VOLL"):
        self._verrechnungssatz = verrechnungssatz_cent
        self._weiterberechnung = zuschlag_weiterberechnung

    def _tages_konfig(self, funktion_code: str, bundesland: str):
        gruppe, satz = LOHNGRUPPEN.get(funktion_code, ("LG1", 1450))
        feiertage = frozenset(FEIERTAGE_2026.get(bundesland, set()))

        def resolver(tag: date) -> berechnung.TagesKonfig:
            return berechnung.TagesKonfig(
                tarif_code="WSG-MUSTER v1",
                stundenlohn_cent=satz,
                masken=_masken(),
                feiertage=feiertage,
                mindestlohn_cent=_mindestlohn_am(tag),
            )

        return resolver

    def berechne_lohn(self, req: berechnung.LohnAnfrage) -> berechnung.LohnErgebnis:
        return berechnung.berechne_lohn(
            req, self._tages_konfig(req.funktion_code, req.bundesland))

    def berechne_umsatz(self, req: berechnung.UmsatzAnfrage) -> berechnung.UmsatzErgebnis:
        feiertage = frozenset(FEIERTAGE_2026.get(req.bundesland, set()))

        def resolver(tag: date) -> berechnung.UmsatzKonfig:
            return berechnung.UmsatzKonfig(
                satz_cent_pro_stunde=self._verrechnungssatz,
                zuschlag_weiterberechnung=self._weiterberechnung,
                weiterberechnung_prozent=100,
                masken=_masken(),
                feiertage=feiertage,
            )

        return berechnung.berechne_umsatz(req, resolver)

    def stundensatz(self, mitarbeiter_id: UUID, funktion_code: str,
                    stichtag: date) -> int:
        _, satz = LOHNGRUPPEN.get(funktion_code, ("LG1", 1450))
        return max(satz, _mindestlohn_am(stichtag))

    def ist_feiertag(self, datum: date, bundesland: str) -> bool:
        return datum in FEIERTAGE_2026.get(bundesland, set())

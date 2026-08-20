"""Auslieferungskatalog der 18 Regeln (M06, Abschnitt 5).

Parameter (Stundenwerte, Fristen) sind je Regel über `parameter`
konfigurierbar (R-01); die Logik selbst lebt im Code (`regeln.py`).
"""

from dataclasses import dataclass, field
from typing import Callable

from kernel.dtos import BLOCKIEREND, HINWEIS, WARNUNG
from m06_regelengine import regeln


@dataclass
class Regel:
    code: str
    bezeichnung: str
    rechtsgrundlage: str
    kategorie: str
    stufe: str
    pruefung: Callable
    aktiv: bool = True
    parameter: dict = field(default_factory=dict)
    reihenfolge: int = 0


def auslieferungskatalog() -> list[Regel]:
    katalog = [
        Regel("AZ_TAG_MAX", "Höchstens 8 h werktäglich, 10 h bei Ausgleich",
              "§ 3 ArbZG", "ARBEITSZEIT", BLOCKIEREND, regeln.az_tag_max),
        Regel("AZ_RUHEZEIT", "Mindestens 11 h zwischen zwei Schichten",
              "§ 5 ArbZG", "ARBEITSZEIT", BLOCKIEREND, regeln.az_ruhezeit),
        # Deaktiviert ausgeliefert: § 5 Abs. 2 ArbZG erfasst das Bewachungs-
        # gewerbe nicht; Aktivierung nur bei tariflicher Öffnung nach § 7 ArbZG.
        Regel("AZ_RUHEZEIT_VERKUERZT", "10 h zulässig bei Ausgleich in 4 Wochen",
              "§ 7 ArbZG i. V. m. TV", "ARBEITSZEIT", WARNUNG,
              regeln.az_ruhezeit_verkuerzt, aktiv=False),
        Regel("AZ_PAUSE", "30 min bei mehr als 6 h, 45 min bei mehr als 9 h",
              "§ 4 ArbZG", "ARBEITSZEIT", BLOCKIEREND, regeln.az_pause),
        Regel("AZ_SONNTAG", "Sonntagsarbeit nur mit Ausnahme; Ersatzruhetag",
              "§§ 9–11 ArbZG", "ARBEITSZEIT", WARNUNG, regeln.az_sonntag),
        Regel("AZ_WOCHE_MAX", "Durchschnitt 48 h in 24 Wochen",
              "§ 3 ArbZG", "ARBEITSZEIT", WARNUNG, regeln.az_woche_max),
        Regel("JU_TAG_MAX", "Unter 18: höchstens 8 h täglich, 40 h wöchentlich",
              "§ 8 JArbSchG", "JUGENDSCHUTZ", BLOCKIEREND, regeln.ju_tag_max),
        Regel("JU_NACHT", "Unter 18: keine Arbeit 20–06 Uhr",
              "§ 14 JArbSchG", "JUGENDSCHUTZ", BLOCKIEREND, regeln.ju_nacht),
        Regel("JU_RUHEZEIT", "Unter 18: mindestens 12 h Ruhezeit",
              "§ 13 JArbSchG", "JUGENDSCHUTZ", BLOCKIEREND, regeln.ju_ruhezeit),
        Regel("QU_FEHLT", "Erforderliche Qualifikation fehlt oder abgelaufen",
              "§ 34a GewO", "QUALIFIKATION", BLOCKIEREND, regeln.qu_fehlt),
        Regel("OB_FREIGABE", "Keine Objektfreigabe für diese Person",
              "intern", "FREIGABE", BLOCKIEREND, regeln.ob_freigabe),
        Regel("VF_ABWESEND", "Urlaub, Krankheit oder Sperre",
              "intern", "VERFUEGBARKEIT", BLOCKIEREND, regeln.vf_abwesend),
        Regel("VF_BEREITSCHAFT", "Außerhalb angegebener Leistungsbereitschaft",
              "intern", "VERFUEGBARKEIT", WARNUNG, regeln.vf_bereitschaft),
        Regel("VT_MAX_STD", "Vertragliche Höchststunden überschritten",
              "intern", "VERTRAG", WARNUNG, regeln.vt_max_std),
        Regel("VT_MIN_STD", "Vertragliche Mindeststunden nicht erreicht",
              "intern", "VERTRAG", HINWEIS, regeln.vt_min_std),
        Regel("GF_VERDIENST", "Geringfügigkeitsgrenze überschritten",
              "§ 8 SGB IV", "VERTRAG", BLOCKIEREND, regeln.gf_verdienst),
        Regel("KF_70_TAGE", "Grenze kurzfristiger Beschäftigung erreicht",
              "§ 8 SGB IV", "VERTRAG", BLOCKIEREND, regeln.kf_70_tage),
        Regel("UEBERSCHNEIDUNG", "Zeitliche Doppelbelegung der Person",
              "intern", "PLANUNG", BLOCKIEREND, regeln.ueberschneidung),
    ]
    for reihenfolge, regel in enumerate(katalog, start=1):
        regel.reihenfolge = reihenfolge
    return katalog

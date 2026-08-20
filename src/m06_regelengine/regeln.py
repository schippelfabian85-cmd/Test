"""Die 18 Regeln des Auslieferungskatalogs (M06, Abschnitt 5).

Jede Regel ist eine reine Funktion über dem PruefKontext. Verstoßtexte
folgen R-04: Problem, Folge, Handlungsoption — für den Disponenten,
nicht für Juristen.
"""

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from m06_regelengine.kontext import PruefKontext, Verstoss
from m06_regelengine.zeit import (
    arbeitsminuten_am_tag,
    arbeitsminuten_in_woche,
    freier_tag_vorhanden,
    lokale_tage,
    minuten_ausserhalb_fensters,
    ruhe_luecken_minuten,
)


@dataclass(frozen=True)
class RegelUmgebung:
    """Was eine Regel über die Engine wissen darf."""

    aktive_codes: frozenset[str]
    zone: ZoneInfo


def _stunden(minuten: int) -> str:
    return f"{minuten // 60} h {minuten % 60:02d} min"


def az_tag_max(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = p.get("max_minuten_tag", 600)
    alle = [k.geplante_schicht, *k.bestehende_schichten]
    verstoesse = []
    for tag in lokale_tage(k.geplante_schicht, u.zone):
        minuten = arbeitsminuten_am_tag(alle, tag, u.zone)
        if minuten > grenze:
            verstoesse.append({
                "text": (
                    f"Am {tag.strftime('%d.%m.%Y')} kämen {_stunden(minuten)} Arbeitszeit zusammen — "
                    f"erlaubt sind höchstens {_stunden(grenze)}. Die Schicht kürzen oder auf eine "
                    "andere Person verteilen."
                ),
                "details": {"tag": tag.isoformat(), "minuten": minuten, "grenze": grenze},
            })
    return verstoesse


def az_ruhezeit(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = p.get("ruhe_minuten", 660)
    verkuerzt = p.get("verkuerzt_minuten", 600)
    verkuerzt_aktiv = "AZ_RUHEZEIT_VERKUERZT" in u.aktive_codes
    verstoesse = []
    for luecke in ruhe_luecken_minuten(k.geplante_schicht, k.bestehende_schichten):
        if luecke >= grenze:
            continue
        if verkuerzt_aktiv and luecke >= verkuerzt:
            continue  # AZ_RUHEZEIT_VERKUERZT übernimmt und warnt
        verstoesse.append({
            "text": (
                f"Zwischen zwei Schichten lägen nur {_stunden(luecke)} Ruhezeit — "
                f"gesetzlich sind {_stunden(grenze)} nötig. Die Schicht später beginnen "
                "lassen oder anders besetzen."
            ),
            "details": {"ruhezeit_minuten": luecke, "grenze_minuten": grenze},
        })
    return verstoesse


def az_ruhezeit_verkuerzt(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = p.get("ruhe_minuten", 660)
    verkuerzt = p.get("verkuerzt_minuten", 600)
    verstoesse = []
    for luecke in ruhe_luecken_minuten(k.geplante_schicht, k.bestehende_schichten):
        if verkuerzt <= luecke < grenze:
            verstoesse.append({
                "text": (
                    f"Die Ruhezeit beträgt nur {_stunden(luecke)}. Das ist nur zulässig, "
                    "wenn der Tarifvertrag es erlaubt und innerhalb von 4 Wochen eine "
                    "Ruhezeit von 12 h als Ausgleich gewährt wird — Ausgleich einplanen."
                ),
                "details": {"ruhezeit_minuten": luecke, "ausgleich_wochen": p.get("ausgleich_wochen", 4)},
            })
    return verstoesse


def az_pause(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    schicht = k.geplante_schicht
    netto = schicht.netto_minuten
    if netto > p.get("pause_ab_2_minuten", 540):
        pflicht = p.get("pause_2_minuten", 45)
    elif netto > p.get("pause_ab_1_minuten", 360):
        pflicht = p.get("pause_1_minuten", 30)
    else:
        pflicht = 0
    if schicht.pause_minuten < pflicht:
        return [{
            "text": (
                f"Bei {_stunden(netto)} Arbeitszeit sind mindestens {pflicht} min Pause "
                f"vorgeschrieben, geplant sind {schicht.pause_minuten} min. Pause erhöhen "
                "oder die Schicht kürzen."
            ),
            "details": {"pause_minuten": schicht.pause_minuten, "pflicht_minuten": pflicht},
        }]
    return []


def az_sonntag(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    sonntage = [t for t in lokale_tage(k.geplante_schicht, u.zone) if t.weekday() == 6]
    if not sonntage:
        return []
    alle = [k.geplante_schicht, *k.bestehende_schichten]
    frist = p.get("ersatzruhetag_frist_tage", 14)
    ersatz = freier_tag_vorhanden(alle, sonntage[0], frist, u.zone)
    zusatz = "" if ersatz else (
        f" In den nächsten {frist} Tagen ist bislang kein freier Ersatzruhetag geplant."
    )
    return [{
        "text": (
            "Die Schicht fällt auf einen Sonntag. Im Bewachungsgewerbe zulässig, "
            f"aber ein Ersatzruhetag binnen zwei Wochen ist Pflicht.{zusatz}"
        ),
        "details": {"sonntag": sonntage[0].isoformat(), "ersatzruhetag_gefunden": ersatz},
    }]


def az_woche_max(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    wochen = p.get("wochen", 24)
    schnitt_grenze = p.get("durchschnitt_minuten_woche", 2880)
    gesamt = k.minuten_24_wochen_bisher + k.geplante_schicht.netto_minuten
    if gesamt > wochen * schnitt_grenze:
        schnitt = round(gesamt / wochen)
        return [{
            "text": (
                f"Mit dieser Schicht steigt der Wochendurchschnitt der letzten {wochen} Wochen "
                f"auf {_stunden(schnitt)} — erlaubt sind im Schnitt {_stunden(schnitt_grenze)}. "
                "Die Person braucht Entlastung im Ausgleichszeitraum."
            ),
            "details": {"durchschnitt_minuten": schnitt, "grenze_minuten": schnitt_grenze},
        }]
    return []


def ju_tag_max(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    if not k.grenzen.ist_minderjaehrig:
        return []
    tag_grenze = p.get("max_minuten_tag", 480)
    wochen_grenze = p.get("max_minuten_woche", 2400)
    alle = [k.geplante_schicht, *k.bestehende_schichten]
    verstoesse = []
    for tag in lokale_tage(k.geplante_schicht, u.zone):
        minuten = arbeitsminuten_am_tag(alle, tag, u.zone)
        if minuten > tag_grenze:
            verstoesse.append({
                "text": (
                    f"Die Person ist minderjährig: am {tag.strftime('%d.%m.%Y')} kämen "
                    f"{_stunden(minuten)} zusammen, erlaubt sind {_stunden(tag_grenze)}."
                ),
                "details": {"tag": tag.isoformat(), "minuten": minuten, "grenze": tag_grenze},
            })
    wochen_geprueft = set()
    for tag in lokale_tage(k.geplante_schicht, u.zone):
        woche = tag.isocalendar()[:2]
        if woche in wochen_geprueft:
            continue
        wochen_geprueft.add(woche)
        minuten = arbeitsminuten_in_woche(alle, tag, u.zone)
        if minuten > wochen_grenze:
            verstoesse.append({
                "text": (
                    f"Die Person ist minderjährig: in der Kalenderwoche kämen "
                    f"{_stunden(minuten)} zusammen, erlaubt sind {_stunden(wochen_grenze)}."
                ),
                "details": {"woche": f"{woche[0]}-KW{woche[1]:02d}", "minuten": minuten,
                            "grenze": wochen_grenze},
            })
    return verstoesse


def ju_nacht(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    if not k.grenzen.ist_minderjaehrig:
        return []
    von = time.fromisoformat(p.get("erlaubt_von", "06:00"))
    bis = time.fromisoformat(p.get("erlaubt_bis", "20:00"))
    ausserhalb = minuten_ausserhalb_fensters(k.geplante_schicht, von, bis, u.zone)
    if ausserhalb > 0:
        return [{
            "text": (
                f"Die Person ist minderjährig und darf nur zwischen {von:%H:%M} und "
                f"{bis:%H:%M} Uhr arbeiten — {ausserhalb} min der Schicht liegen außerhalb. "
                "Schichtzeiten anpassen oder volljährige Person einsetzen."
            ),
            "details": {"minuten_ausserhalb": ausserhalb,
                        "fenster": f"{von:%H:%M}-{bis:%H:%M}"},
        }]
    return []


def ju_ruhezeit(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    if not k.grenzen.ist_minderjaehrig:
        return []
    grenze = p.get("ruhe_minuten", 720)
    verstoesse = []
    for luecke in ruhe_luecken_minuten(k.geplante_schicht, k.bestehende_schichten):
        if luecke < grenze:
            verstoesse.append({
                "text": (
                    f"Die Person ist minderjährig: zwischen zwei Schichten lägen nur "
                    f"{_stunden(luecke)} Freizeit, vorgeschrieben sind {_stunden(grenze)}."
                ),
                "details": {"ruhezeit_minuten": luecke, "grenze_minuten": grenze},
            })
    return verstoesse


def qu_fehlt(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    fehlend = sorted(set(k.erforderliche_qualifikationen) - set(k.qualifikationen))
    if fehlend:
        return [{
            "text": (
                f"Für diesen Einsatz fehlt am Schichttag: {', '.join(fehlend)}. "
                "Ohne gültigen Nachweis darf die Person hier nicht eingesetzt werden — "
                "Nachweis nachtragen (M03) oder anders besetzen."
            ),
            "details": {"fehlende_qualifikationen": fehlend},
        }]
    return []


def ob_freigabe(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    if not k.objekt_freigegeben:
        return [{
            "text": (
                "Die Person ist für dieses Objekt nicht freigegeben. Freigabe in der "
                "Objektakte erteilen (M02) oder eine freigegebene Person wählen."
            ),
            "details": {"objekt_id": str(k.objekt_id)},
        }]
    return []


def vf_abwesend(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    if not k.verfuegbar:
        grund = k.verfuegbarkeit_grund or "ABWESEND"
        return [{
            "text": (
                f"Die Person ist im Schichtzeitraum nicht verfügbar (Grund: {grund}). "
                "Die Abwesenheit prüfen (M07) oder anders besetzen."
            ),
            "details": {"grund": grund},
        }]
    return []


def vf_bereitschaft(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    if k.verfuegbar and k.ausserhalb_bereitschaft:
        return [{
            "text": (
                "Die Schicht liegt außerhalb der angegebenen Leistungsbereitschaft. "
                "Einsatz ist möglich, sollte aber mit der Person abgestimmt werden."
            ),
            "details": {},
        }]
    return []


def vt_max_std(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = k.grenzen.max_minuten_monat
    if grenze is None:
        return []
    gesamt = k.minuten_monat_bisher + k.geplante_schicht.netto_minuten
    if gesamt > grenze:
        return [{
            "text": (
                f"Mit dieser Schicht käme die Person auf {_stunden(gesamt)} im Monat — "
                f"vertraglich vereinbart sind höchstens {_stunden(grenze)}."
            ),
            "details": {"minuten_monat": gesamt, "grenze_minuten": grenze},
        }]
    return []


def vt_min_std(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = k.grenzen.min_minuten_monat
    if grenze is None:
        return []
    gesamt = k.minuten_monat_bisher + k.geplante_schicht.netto_minuten
    if gesamt < grenze:
        return [{
            "text": (
                f"Auch mit dieser Schicht liegt die Person bei {_stunden(gesamt)} im Monat — "
                f"vereinbart sind mindestens {_stunden(grenze)}. Weitere Einsätze einplanen."
            ),
            "details": {"minuten_monat": gesamt, "grenze_minuten": grenze},
        }]
    return []


def gf_verdienst(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = k.grenzen.max_verdienst_monat_cent
    if grenze is None:
        return []
    gesamt = k.verdienst_monat_bisher_cent + k.verdienst_geplante_schicht_cent
    if gesamt > grenze:
        return [{
            "text": (
                f"Mit dieser Schicht käme die geringfügig beschäftigte Person auf "
                f"{gesamt / 100:.2f} € im Monat — die Grenze liegt bei {grenze / 100:.2f} €. "
                "Überschreitung macht die Beschäftigung sozialversicherungspflichtig."
            ),
            "details": {"verdienst_cent": gesamt, "grenze_cent": grenze},
        }]
    return []


def kf_70_tage(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    grenze = k.grenzen.max_einsatztage_jahr
    if grenze is None:
        return []
    gesamt = k.einsatztage_jahr_bisher + 1
    if gesamt > grenze:
        return [{
            "text": (
                f"Die kurzfristig beschäftigte Person hätte mit dieser Schicht "
                f"{gesamt} Einsatztage im Jahr — erlaubt sind {grenze}. Danach entfällt "
                "die Sozialversicherungsfreiheit."
            ),
            "details": {"einsatztage": gesamt, "grenze_tage": grenze},
        }]
    return []


def ueberschneidung(k: PruefKontext, p: dict, u: RegelUmgebung) -> list[dict]:
    g = k.geplante_schicht
    doppelt = [
        s for s in k.bestehende_schichten
        if s.beginn_utc < g.ende_utc and g.beginn_utc < s.ende_utc
    ]
    if doppelt:
        return [{
            "text": (
                f"Die Person ist im Schichtzeitraum bereits {len(doppelt)}-fach eingeplant. "
                "Eine Person kann nicht an zwei Orten gleichzeitig sein — bestehende "
                "Schicht prüfen."
            ),
            "details": {"ueberschneidende_schichten": [str(s.id) for s in doppelt]},
        }]
    return []

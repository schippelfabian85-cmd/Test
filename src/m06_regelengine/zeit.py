"""Kalenderarithmetik für die Regelprüfung.

Schichten liegen in UTC vor; Arbeitszeitrecht rechnet in lokaler Zeit.
Alle Tages- und Wochenzuordnungen laufen deshalb über die Zeitzone der
Engine (Standard Europe/Berlin).
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from kernel.dtos import SchichtDTO

STANDARD_ZONE = ZoneInfo("Europe/Berlin")


def lokale_tage(schicht: SchichtDTO, zone: ZoneInfo) -> list[date]:
    """Alle lokalen Kalendertage, die die Schicht berührt."""
    beginn = schicht.beginn_utc.astimezone(zone)
    # Das exklusive Ende gehört nicht mehr zum Folgetag (Ende 24:00 = Vortag).
    ende = (schicht.ende_utc - timedelta(microseconds=1)).astimezone(zone)
    tage = []
    tag = beginn.date()
    while tag <= ende.date():
        tage.append(tag)
        tag += timedelta(days=1)
    return tage


def _ueberlappung_minuten(schicht: SchichtDTO, von: datetime, bis: datetime) -> int:
    beginn = max(schicht.beginn_utc, von)
    ende = min(schicht.ende_utc, bis)
    if ende <= beginn:
        return 0
    return int((ende - beginn).total_seconds() // 60)


def tagesgrenzen(tag: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    von = datetime.combine(tag, time(0), tzinfo=zone)
    bis = datetime.combine(tag + timedelta(days=1), time(0), tzinfo=zone)
    return von, bis


def arbeitsminuten_am_tag(schichten: list[SchichtDTO], tag: date, zone: ZoneInfo) -> int:
    """Netto-Arbeitsminuten aller Schichten am lokalen Kalendertag.

    Die Pause einer tagesübergreifenden Schicht wird anteilig auf die
    berührten Tage verteilt.
    """
    von, bis = tagesgrenzen(tag, zone)
    summe = 0
    for schicht in schichten:
        anteil = _ueberlappung_minuten(schicht, von, bis)
        if anteil == 0 or schicht.brutto_minuten == 0:
            continue
        summe += round(anteil * schicht.netto_minuten / schicht.brutto_minuten)
    return summe


def arbeitsminuten_in_woche(schichten: list[SchichtDTO], tag: date, zone: ZoneInfo) -> int:
    """Netto-Arbeitsminuten in der Kalenderwoche (Mo–So), die `tag` enthält."""
    montag = tag - timedelta(days=tag.weekday())
    von, _ = tagesgrenzen(montag, zone)
    _, bis = tagesgrenzen(montag + timedelta(days=6), zone)
    summe = 0
    for schicht in schichten:
        anteil = _ueberlappung_minuten(schicht, von, bis)
        if anteil == 0 or schicht.brutto_minuten == 0:
            continue
        summe += round(anteil * schicht.netto_minuten / schicht.brutto_minuten)
    return summe


def ruhe_luecken_minuten(geplant: SchichtDTO, bestehende: tuple[SchichtDTO, ...]) -> list[int]:
    """Ruhezeiten (in Minuten) unmittelbar vor und nach der geplanten Schicht."""
    luecken = []
    vorher = [s.ende_utc for s in bestehende if s.ende_utc <= geplant.beginn_utc]
    if vorher:
        luecken.append(int((geplant.beginn_utc - max(vorher)).total_seconds() // 60))
    nachher = [s.beginn_utc for s in bestehende if s.beginn_utc >= geplant.ende_utc]
    if nachher:
        luecken.append(int((min(nachher) - geplant.ende_utc).total_seconds() // 60))
    return luecken


def minuten_ausserhalb_fensters(
    schicht: SchichtDTO, fenster_von: time, fenster_bis: time, zone: ZoneInfo
) -> int:
    """Minuten der Schicht außerhalb des täglichen Zeitfensters (z. B. 06–20 Uhr)."""
    ausserhalb = 0
    for tag in lokale_tage(schicht, zone):
        tag_von, tag_bis = tagesgrenzen(tag, zone)
        im_tag = _ueberlappung_minuten(schicht, tag_von, tag_bis)
        erlaubt_von = datetime.combine(tag, fenster_von, tzinfo=zone)
        erlaubt_bis = datetime.combine(tag, fenster_bis, tzinfo=zone)
        im_fenster = _ueberlappung_minuten(schicht, erlaubt_von, erlaubt_bis)
        ausserhalb += im_tag - im_fenster
    return ausserhalb


def freier_tag_vorhanden(
    schichten: list[SchichtDTO], ab: date, tage: int, zone: ZoneInfo
) -> bool:
    """Existiert innerhalb von `tage` Tagen ab `ab` ein schichtfreier Kalendertag?"""
    belegte = {t for s in schichten for t in lokale_tage(s, zone)}
    return any(ab + timedelta(days=i) not in belegte for i in range(1, tage + 1))

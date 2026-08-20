"""Fachlogik M01 — Fachregeln R-01 bis R-08.

Jede ändernde Funktion schreibt genau einen Audit-Eintrag (K-4, AC 8)
und publiziert ihre Events über die Outbox (genau ein Eintrag je
Übergang, AC 9).
"""

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from kernel.audit import schreibe_audit
from kernel.auth import AuthKontext
from kernel.dtos import VertragsgrenzenDTO
from kernel.events import publiziere
from kernel.fehler import FachFehler, NichtGefunden, VersionsKonflikt
from kernel.modelle import Benutzer
from kernel.muster import version_am
from kernel.nummern import naechste_nummer
from m01_personal.modelle import (
    Funktion,
    Mitarbeiter,
    MitarbeiterFunktion,
    MitarbeiterHistorie,
    STATUS_UEBERGAENGE,
    Vertragstyp,
)

MODUL = "M01"
AUFBEWAHRUNG_JAHRE = 10

PFLICHTFELDER = ("personalnummer", "nachname", "vorname", "geburtsdatum",
                 "land", "eintrittsdatum", "vertragstyp_id")

AENDERBARE_FELDER = {
    "nachname", "vorname", "geburtsdatum", "geburtsort", "staatsangehoerigkeit",
    "strasse", "plz", "ort", "land", "telefon", "mobil", "email",
    "anstellungsort_id", "kostenstelle_id", "bemerkung",
    "sofortmeldung_erforderlich", "sofortmeldung_erfolgt_am",
}

ANONYM_FELDER = ("nachname", "vorname", "geburtsort", "staatsangehoerigkeit",
                 "strasse", "plz", "ort", "telefon", "mobil", "email",
                 "bemerkung", "austrittsgrund")


def _lade(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID) -> Mitarbeiter:
    ma = session.get(Mitarbeiter, mitarbeiter_id)
    if ma is None or ma.tenant_id != ktx.tenant_id:
        raise NichtGefunden("M01-E-404", "Mitarbeiter nicht gefunden",
                            {"mitarbeiter_id": str(mitarbeiter_id)})
    return ma


def _historie(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
              feld: str, alt, neu, zeitpunkt: datetime | None = None) -> None:
    eintrag = MitarbeiterHistorie(
        mitarbeiter_id=mitarbeiter_id, feld=feld,
        alt=str(alt) if alt is not None else None,
        neu=str(neu) if neu is not None else None,
        benutzer_id=ktx.benutzer_id,
    )
    if zeitpunkt is not None:
        eintrag.zeitpunkt = zeitpunkt
    session.add(eintrag)


def lege_an(session: Session, ktx: AuthKontext, daten: dict,
            funktion_codes: list[str]) -> Mitarbeiter:
    ktx.fordere_rolle("ADMIN", "PLANER")

    fehlend = [f for f in PFLICHTFELDER if not daten.get(f)]
    if not funktion_codes:
        fehlend.append("funktion")
    if fehlend:
        raise FachFehler("M01-E-001", "Pflichtfelder fehlen", {"felder": sorted(fehlend)})

    vorhanden = session.scalars(select(Mitarbeiter).where(
        Mitarbeiter.tenant_id == ktx.tenant_id,
        Mitarbeiter.personalnummer == daten["personalnummer"],
    )).first()
    if vorhanden is not None:
        raise FachFehler("M01-E-002", "Personalnummer ist in diesem Mandanten bereits vergeben",
                         {"personalnummer": daten["personalnummer"]})

    vertragstyp = session.get(Vertragstyp, daten["vertragstyp_id"])
    if vertragstyp is None or vertragstyp.tenant_id != ktx.tenant_id:
        raise FachFehler("M01-E-005", "Vertragstyp existiert nicht",
                         {"vertragstyp_id": str(daten["vertragstyp_id"])})

    funktionen = session.scalars(select(Funktion).where(
        Funktion.tenant_id == ktx.tenant_id, Funktion.code.in_(funktion_codes),
    )).all()
    if len(funktionen) != len(set(funktion_codes)):
        gefunden = {f.code for f in funktionen}
        raise FachFehler("M01-E-006", "Funktion nicht angelegt",
                         {"fehlend": sorted(set(funktion_codes) - gefunden)})

    ma = Mitarbeiter(tenant_id=ktx.tenant_id, created_by=ktx.benutzer_id,
                     **{k: v for k, v in daten.items() if k != "status"})
    ma.status = daten.get("status", "AKTIV")
    session.add(ma)
    session.flush()
    for i, funktion in enumerate(funktionen):
        session.add(MitarbeiterFunktion(mitarbeiter_id=ma.id, funktion_id=funktion.id,
                                        ist_hauptfunktion=(i == 0),
                                        gueltig_ab=ma.eintrittsdatum))
    # Grundlage der Stichtagsauflösung (AC 3): welcher Vertrag galt wann.
    _historie(session, ktx, ma.id, "vertragstyp_id", None, ma.vertragstyp_id,
              zeitpunkt=_als_zeitpunkt(ma.eintrittsdatum))
    schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "ANGELEGT",
                   neu={"personalnummer": ma.personalnummer, "status": ma.status})
    if ma.status == "AKTIV":
        publiziere(session, "m01.mitarbeiter.eingetreten.v1", ktx.tenant_id,
                   ktx.benutzer_id, {"mitarbeiter_id": str(ma.id)})
    return ma


def aendere(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
            aenderungen: dict, erwartete_version: int) -> Mitarbeiter:
    ktx.fordere_rolle("ADMIN", "PLANER")
    ma = _lade(session, ktx, mitarbeiter_id)
    if ma.version != erwartete_version:
        raise VersionsKonflikt("M01-E-409", "Der Datensatz wurde zwischenzeitlich geändert",
                               {"aktuelle_version": ma.version})
    if "personalnummer" in aenderungen and aenderungen["personalnummer"] != ma.personalnummer:
        raise FachFehler("M01-E-003", "Die Personalnummer ist nach Vergabe unveränderlich")

    geaendert = {}
    for feld, neu in aenderungen.items():
        if feld not in AENDERBARE_FELDER:
            continue
        alt = getattr(ma, feld)
        if alt != neu:
            setattr(ma, feld, neu)
            _historie(session, ktx, ma.id, feld, alt, neu)
            geaendert[feld] = {"alt": alt, "neu": neu}
    if geaendert:
        ma.version += 1
        schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "GEAENDERT",
                       alt={f: w["alt"] for f, w in geaendert.items()},
                       neu={f: w["neu"] for f, w in geaendert.items()})
    return ma


def setze_status(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
                 neuer_status: str, grund: str | None = None) -> Mitarbeiter:
    ma = _lade(session, ktx, mitarbeiter_id)
    if neuer_status == ma.status:
        return ma
    if neuer_status not in STATUS_UEBERGAENGE.get(ma.status, set()):
        raise FachFehler("M01-E-010", f"Statuswechsel {ma.status} → {neuer_status} ist nicht zulässig",
                         {"erlaubt": sorted(STATUS_UEBERGAENGE.get(ma.status, set()))})
    if ma.status == "AUSGESCHIEDEN":
        ktx.fordere_rolle("ADMIN")   # R-08: Rücksprung nur ADMIN …
        if not (grund or "").strip():
            raise FachFehler("M01-E-011", "Wiedereinstellung erfordert eine Begründung")
    else:
        ktx.fordere_rolle("ADMIN", "PLANER")

    alt = ma.status
    ma.status = neuer_status
    if alt == "AUSGESCHIEDEN" and neuer_status == "AKTIV":   # Wiedereinstellung
        ma.austrittsdatum = None
        ma.austrittsgrund = None
    _historie(session, ktx, ma.id, "status", alt, neuer_status)
    schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "STATUS",
                   alt={"status": alt}, neu={"status": neuer_status, "grund": grund})
    if neuer_status == "AKTIV":
        publiziere(session, "m01.mitarbeiter.eingetreten.v1", ktx.tenant_id,
                   ktx.benutzer_id, {"mitarbeiter_id": str(ma.id)})
    return ma


def setze_austritt(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
                   austrittsdatum: date, grund: str | None,
                   heute: date | None = None) -> Mitarbeiter:
    """R-04 (korrigiert): Lizenz wird erst mit Erreichen des Datums frei."""
    ktx.fordere_rolle("ADMIN")
    ma = _lade(session, ktx, mitarbeiter_id)
    ma.austrittsdatum = austrittsdatum
    ma.austrittsgrund = grund
    schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "AUSTRITT_GESETZT",
                   neu={"austrittsdatum": austrittsdatum, "grund": grund})
    heute = heute or date.today()
    if austrittsdatum <= heute:   # rückwirkendes Setzen wirkt sofort
        _vollziehe_austritt(session, ktx, ma)
    return ma


def _vollziehe_austritt(session: Session, ktx: AuthKontext, ma: Mitarbeiter) -> None:
    if ma.status == "AUSGESCHIEDEN":
        return
    alt = ma.status
    ma.status = "AUSGESCHIEDEN"
    _historie(session, ktx, ma.id, "status", alt, "AUSGESCHIEDEN")
    if ma.benutzer_id is not None:
        benutzer = session.get(Benutzer, ma.benutzer_id)
        if benutzer is not None:
            benutzer.aktiv = False   # Lizenz frei (taggenau)
    publiziere(session, "m01.mitarbeiter.ausgeschieden.v1", ktx.tenant_id,
               ktx.benutzer_id, {"mitarbeiter_id": str(ma.id)})


def verarbeite_austritte(session: Session, ktx: AuthKontext,
                         stichtag: date | None = None) -> int:
    """Nächtlicher Lauf: vollzieht erreichte Austrittsdaten (R-04)."""
    stichtag = stichtag or date.today()
    faellige = session.scalars(select(Mitarbeiter).where(
        Mitarbeiter.tenant_id == ktx.tenant_id,
        Mitarbeiter.austrittsdatum.is_not(None),
        Mitarbeiter.austrittsdatum <= stichtag,
        Mitarbeiter.status.not_in(("AUSGESCHIEDEN", "ANONYMISIERT")),
    )).all()
    for ma in faellige:
        _vollziehe_austritt(session, ktx, ma)
        schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "AUSTRITT_VOLLZOGEN",
                       neu={"austrittsdatum": ma.austrittsdatum})
    return len(faellige)


def anonymisiere(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
                 bestaetigung: bool = False, heute: date | None = None) -> Mitarbeiter:
    """R-05/R-06: zweistufig, nur ADMIN, Aufbewahrungsfrist blockiert."""
    ktx.fordere_rolle("ADMIN")
    ma = _lade(session, ktx, mitarbeiter_id)
    if not bestaetigung:
        raise FachFehler("M01-E-013", "Anonymisierung erfordert die zweite Bestätigung",
                         {"hinweis": "bestaetigung=true übergeben"})
    if ma.status != "AUSGESCHIEDEN":
        raise FachFehler("M01-E-012", "Nur ausgeschiedene Mitarbeiter können anonymisiert werden",
                         {"status": ma.status})
    heute = heute or date.today()
    fruehestens = date(ma.austrittsdatum.year + AUFBEWAHRUNG_JAHRE,
                       ma.austrittsdatum.month, ma.austrittsdatum.day)
    if heute < fruehestens:
        raise FachFehler("M01-E-014", "Die gesetzliche Aufbewahrungsfrist läuft noch",
                         {"fruehestmoegliches_datum": str(fruehestens)})

    for feld in ANONYM_FELDER:
        setattr(ma, feld, None)
    ma.nachname = "ANONYMISIERT"
    ma.vorname = "-"
    ma.geburtsdatum = date(1900, 1, 1)
    ma.personalnummer = "ANON-" + naechste_nummer(session, ktx.tenant_id, "ANONYM", breite=5)
    ma.status = "ANONYMISIERT"
    session.execute(  # Kommunikation/Verlauf unwiderruflich löschen (R-05)
        MitarbeiterHistorie.__table__.delete().where(
            MitarbeiterHistorie.mitarbeiter_id == ma.id,
            MitarbeiterHistorie.feld != "vertragstyp_id",
        )
    )
    schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "ANONYMISIERT")
    publiziere(session, "m01.mitarbeiter.anonymisiert.v1", ktx.tenant_id,
               ktx.benutzer_id, {"mitarbeiter_id": str(ma.id)})
    return ma


def wechsle_vertragstyp(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
                        neue_vertragstyp_id: UUID, stichtag: date) -> Mitarbeiter:
    ktx.fordere_rolle("ADMIN", "PLANER")
    ma = _lade(session, ktx, mitarbeiter_id)
    neu = session.get(Vertragstyp, neue_vertragstyp_id)
    if neu is None or neu.tenant_id != ktx.tenant_id:
        raise FachFehler("M01-E-005", "Vertragstyp existiert nicht")
    alt_id = ma.vertragstyp_id
    ma.vertragstyp_id = neue_vertragstyp_id
    _historie(session, ktx, ma.id, "vertragstyp_id", alt_id, neue_vertragstyp_id,
              zeitpunkt=_als_zeitpunkt(stichtag))
    schreibe_audit(session, ktx, MODUL, "mitarbeiter", ma.id, "VERTRAGSTYP_GEWECHSELT",
                   alt={"vertragstyp_id": alt_id},
                   neu={"vertragstyp_id": neue_vertragstyp_id, "stichtag": stichtag})
    publiziere(session, "m01.mitarbeiter.vertragstyp_geaendert.v1", ktx.tenant_id,
               ktx.benutzer_id,
               {"mitarbeiter_id": str(ma.id), "stichtag": str(stichtag)})
    return ma


def _als_zeitpunkt(tag: date) -> datetime:
    return datetime.combine(tag, time(0), tzinfo=timezone.utc)


def vertragstyp_am(session: Session, ma: Mitarbeiter, stichtag: date) -> Vertragstyp:
    """Zweistufige Stichtagsauflösung: Historie → Zuordnung, Muster A → Version."""
    zeilen = session.scalars(
        select(MitarbeiterHistorie).where(
            MitarbeiterHistorie.mitarbeiter_id == ma.id,
            MitarbeiterHistorie.feld == "vertragstyp_id",
            MitarbeiterHistorie.zeitpunkt <= _als_zeitpunkt(stichtag),
        ).order_by(MitarbeiterHistorie.zeitpunkt.desc())
    ).first()
    zugeordnet_id = UUID(zeilen.neu) if zeilen is not None else ma.vertragstyp_id
    zugeordnet = session.get(Vertragstyp, zugeordnet_id)
    # Muster A: die am Stichtag gültige Version desselben Stamms (K-5).
    aktuelle = version_am(session, Vertragstyp, zugeordnet.stamm_id, stichtag)
    return aktuelle or zugeordnet


def vertragsgrenzen(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
                    stichtag: date) -> VertragsgrenzenDTO:
    ma = _lade(session, ktx, mitarbeiter_id)
    vt = vertragstyp_am(session, ma, stichtag)
    achtzehnter = date(ma.geburtsdatum.year + 18, ma.geburtsdatum.month,
                       ma.geburtsdatum.day)
    return VertragsgrenzenDTO(
        kategorie=vt.kategorie,
        soll_minuten_monat=vt.soll_stunden_monat * 60,
        min_minuten_monat=vt.min_stunden_monat * 60 if vt.min_stunden_monat is not None else None,
        max_minuten_monat=vt.max_stunden_monat * 60 if vt.max_stunden_monat is not None else None,
        max_verdienst_monat_cent=vt.max_verdienst_monat_cent,
        max_einsatztage_jahr=vt.max_einsatztage_jahr,
        pausen_bezahlt=vt.pausen_bezahlt,
        zeitwertkonto_aktiv=vt.zeitwertkonto_aktiv,
        ist_minderjaehrig=stichtag < achtzehnter,
    )


def ist_aktiv(session: Session, ktx: AuthKontext, mitarbeiter_id: UUID,
              stichtag: date) -> bool:
    """R-07 (korrigiert): AKTIV und Eintritt ≤ Stichtag ≤ Austritt."""
    ma = session.get(Mitarbeiter, mitarbeiter_id)
    if ma is None or ma.tenant_id != ktx.tenant_id or ma.status != "AKTIV":
        return False
    if stichtag < ma.eintrittsdatum:
        return False
    if ma.austrittsdatum is not None and stichtag > ma.austrittsdatum:
        return False
    return True


def suche(session: Session, ktx: AuthKontext, status: str | None = None,
          funktion_code: str | None = None, text: str | None = None,
          sichtbare_personen: set[UUID] | None = None) -> list[Mitarbeiter]:
    abfrage = select(Mitarbeiter).where(Mitarbeiter.tenant_id == ktx.tenant_id)
    if status:
        abfrage = abfrage.where(Mitarbeiter.status == status)
    if funktion_code:
        abfrage = (abfrage.join(MitarbeiterFunktion,
                                MitarbeiterFunktion.mitarbeiter_id == Mitarbeiter.id)
                   .join(Funktion, Funktion.id == MitarbeiterFunktion.funktion_id)
                   .where(Funktion.code == funktion_code))
    if text:
        muster = f"%{text.lower()}%"
        abfrage = abfrage.where(or_(
            func.lower(Mitarbeiter.nachname).like(muster),
            func.lower(Mitarbeiter.vorname).like(muster),
            func.lower(Mitarbeiter.personalnummer).like(muster),
        ))
    treffer = list(session.scalars(abfrage.order_by(Mitarbeiter.nachname,
                                                    Mitarbeiter.vorname)))
    if sichtbare_personen is not None:   # K-8: Sichtbarkeitsbereich (EL/OL/MA)
        treffer = [m for m in treffer if m.id in sichtbare_personen]
    return treffer


def funktion_codes(session: Session, mitarbeiter_id: UUID) -> tuple[str, ...]:
    zeilen = session.scalars(
        select(Funktion.code)
        .join(MitarbeiterFunktion, MitarbeiterFunktion.funktion_id == Funktion.id)
        .where(MitarbeiterFunktion.mitarbeiter_id == mitarbeiter_id)
        .order_by(Funktion.code)
    ).all()
    return tuple(zeilen)

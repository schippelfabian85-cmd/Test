"""M04-Dienste: Konfigurationsauflösung aus der Datenbank und der
EntgeltPortV1 (M04 §3). Konsumiert MitarbeiterPort (Vertragsgrenzen)
und ObjektPort (Bundesland) — nie fremde Tabellen (K-1)."""

from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.audit import schreibe_audit
from kernel.auth import AuthKontext
from kernel.fehler import FachFehler, NichtGefunden
from kernel.muster import neue_version, version_am
from m04_entgelt import berechnung, zerlegung
from m04_entgelt.modelle import (
    Feiertag,
    Lohnart,
    Lohngruppe,
    Mindestlohn,
    Tarif,
    Verrechnungssatz,
    Zuschlagsmaske,
)

MODUL = "M04"


def _maske_zu_konfig(session: Session, maske: Zuschlagsmaske) -> berechnung.MaskenKonfig:
    wochentage = frozenset(int(t) for t in maske.wochentage.split(",") if t != "")
    lohnart_nummer, lohnart_bezeichnung = "2000", f"Zuschlag {maske.bezeichnung}"
    if maske.lohnart_id is not None:
        lohnart = session.get(Lohnart, maske.lohnart_id)
        if lohnart is not None:
            lohnart_nummer, lohnart_bezeichnung = lohnart.nummer, lohnart.bezeichnung
    return berechnung.MaskenKonfig(
        maske=zerlegung.Zuschlagsmaske(
            bezeichnung=maske.bezeichnung,
            prioritaet=maske.prioritaet,
            kumulierung=maske.kumulierung,
            wochentage=wochentage,
            von_uhrzeit=maske.von_uhrzeit,
            bis_uhrzeit=maske.bis_uhrzeit,
            gilt_an_feiertagen=maske.gilt_an_feiertagen,
            gilt_an_sonntagen=maske.gilt_an_sonntagen,
        ),
        maske_id=maske.id,
        lohnart_nummer=lohnart_nummer,
        lohnart_bezeichnung=lohnart_bezeichnung,
        bemessung=maske.bemessung,
        prozent=maske.prozent,
        betrag_cent=maske.betrag_cent,
    )


def feiertage(session: Session, tenant_id: UUID, bundesland: str) -> frozenset:
    zeilen = session.scalars(select(Feiertag).where(
        Feiertag.tenant_id == tenant_id,
        Feiertag.bundesland == bundesland,
        Feiertag.ist_gesetzlich.is_(True),
    )).all()
    return frozenset(z.datum for z in zeilen)


def ist_feiertag(session: Session, tenant_id: UUID, datum: date, bundesland: str) -> bool:
    return datum in feiertage(session, tenant_id, bundesland)


def mindestlohn_am(session: Session, stichtag: date) -> int:
    zeile = session.scalars(select(Mindestlohn).where(
        Mindestlohn.gueltig_ab <= stichtag,
    ).order_by(Mindestlohn.gueltig_ab.desc())).first()
    return zeile.betrag_cent if zeile else 0


def tarif_am(session: Session, tenant_id: UUID, stichtag: date) -> Tarif:
    zeile = session.scalars(select(Tarif).where(
        Tarif.tenant_id == tenant_id,
        Tarif.gueltig_ab <= stichtag,
        (Tarif.gueltig_bis.is_(None)) | (Tarif.gueltig_bis >= stichtag),
    ).order_by(Tarif.version.desc())).first()
    if zeile is None:
        raise FachFehler("M04-E-001", "Zum Leistungszeitpunkt ist kein Tarif gültig",
                         {"stichtag": str(stichtag)})
    return zeile


def lohngruppe_fuer(session: Session, tarif: Tarif, funktion_code: str) -> Lohngruppe:
    gruppen = session.scalars(select(Lohngruppe).where(
        Lohngruppe.tarif_id == tarif.id,
    ).order_by(Lohngruppe.code)).all()
    for gruppe in gruppen:
        codes = {c.strip() for c in gruppe.funktion_codes.split(",") if c.strip()}
        if funktion_code in codes:
            return gruppe
    raise FachFehler(
        "M04-E-002",
        f"Im Tarif „{tarif.bezeichnung}“ (Version {tarif.version}, gültig ab "
        f"{tarif.gueltig_ab:%d.%m.%Y}) ist der Funktion {funktion_code!r} keine "
        "Lohngruppe zugeordnet — Lohngruppen im Tarif pflegen.",
        {"tarif_code": tarif.code, "funktion_code": funktion_code},
    )


def tages_konfig_resolver(session: Session, tenant_id: UUID, funktion_code: str,
                          bundesland: str):
    feiertage_menge = feiertage(session, tenant_id, bundesland)

    def resolver(tag: date) -> berechnung.TagesKonfig:
        tarif = tarif_am(session, tenant_id, tag)
        gruppe = lohngruppe_fuer(session, tarif, funktion_code)
        masken = session.scalars(select(Zuschlagsmaske).where(
            Zuschlagsmaske.tarif_id == tarif.id,
            Zuschlagsmaske.aktiv.is_(True),
            Zuschlagsmaske.gueltig_ab <= tag,
            (Zuschlagsmaske.gueltig_bis.is_(None)) | (Zuschlagsmaske.gueltig_bis >= tag),
        )).all()
        return berechnung.TagesKonfig(
            tarif_code=f"{tarif.code} v{tarif.version}",
            stundenlohn_cent=gruppe.stundenlohn_cent,
            masken=tuple(_maske_zu_konfig(session, m) for m in masken),
            feiertage=feiertage_menge,
            mindestlohn_cent=mindestlohn_am(session, tag),
        )

    return resolver


def verrechnungssatz_am(session: Session, tenant_id: UUID, kunde_id: UUID,
                        objekt_id: UUID | None, funktion_code: str,
                        stichtag: date) -> Verrechnungssatz:
    """R-08: spezifischster gültiger Satz — Objekt+Funktion > Objekt > Kunde+Funktion > Kunde."""
    kandidaten = session.scalars(select(Verrechnungssatz).where(
        Verrechnungssatz.tenant_id == tenant_id,
        Verrechnungssatz.kunde_id == kunde_id,
        Verrechnungssatz.aktiv.is_(True),
        Verrechnungssatz.gueltig_ab <= stichtag,
        (Verrechnungssatz.gueltig_bis.is_(None)) | (Verrechnungssatz.gueltig_bis >= stichtag),
    )).all()
    passende = []
    for satz in kandidaten:
        if satz.objekt_id is not None and satz.objekt_id != objekt_id:
            continue
        if satz.funktion_code is not None and satz.funktion_code != funktion_code:
            continue
        spezifitaet = (satz.objekt_id is not None) * 2 + (satz.funktion_code is not None)
        passende.append((spezifitaet, satz))
    if not passende:
        raise FachFehler(
            "M04-E-020",
            f"Für Kunde/Objekt und Funktion {funktion_code!r} ist am "
            f"{stichtag:%d.%m.%Y} kein Verrechnungssatz gültig — Satz anlegen "
            "oder Gültigkeit verlängern.",
            {"kunde_id": str(kunde_id), "funktion_code": funktion_code,
             "stichtag": str(stichtag)},
        )
    passende.sort(key=lambda eintrag: eintrag[0], reverse=True)
    return passende[0][1]


def umsatz_konfig_resolver(session: Session, tenant_id: UUID, kunde_id: UUID,
                           objekt_id: UUID | None, funktion_code: str, bundesland: str):
    feiertage_menge = feiertage(session, tenant_id, bundesland)

    def resolver(tag: date) -> berechnung.UmsatzKonfig:
        satz = verrechnungssatz_am(session, tenant_id, kunde_id, objekt_id,
                                   funktion_code, tag)
        tarif = tarif_am(session, tenant_id, tag)
        masken = session.scalars(select(Zuschlagsmaske).where(
            Zuschlagsmaske.tarif_id == tarif.id,
            Zuschlagsmaske.aktiv.is_(True),
            Zuschlagsmaske.gueltig_ab <= tag,
            (Zuschlagsmaske.gueltig_bis.is_(None)) | (Zuschlagsmaske.gueltig_bis >= tag),
        )).all()
        return berechnung.UmsatzKonfig(
            satz_cent_pro_stunde=satz.satz_cent_pro_stunde,
            zuschlag_weiterberechnung=satz.zuschlag_weiterberechnung,
            weiterberechnung_prozent=satz.weiterberechnung_prozent,
            masken=tuple(_maske_zu_konfig(session, m) for m in masken),
            feiertage=feiertage_menge,
        )

    return resolver


def aendere_zuschlagsmaske(session: Session, ktx: AuthKontext, maske_id: UUID,
                           gueltig_ab: date, **aenderungen) -> Zuschlagsmaske:
    """R-03: verwendete Masken sind unveränderlich — Änderung nur als neue Version."""
    ktx.fordere_rolle("ADMIN")
    maske = session.get(Zuschlagsmaske, maske_id)
    if maske is None or maske.tenant_id != ktx.tenant_id:
        raise NichtGefunden("M04-E-404", "Zuschlagsmaske nicht gefunden")
    neu = neue_version(session, maske, gueltig_ab, "M04-E-011", **aenderungen)
    neu.verwendet = False
    schreibe_audit(session, ktx, MODUL, "zuschlagsmaske", neu.id, "NEUE_VERSION",
                   neu={"version": neu.version, "gueltig_ab": gueltig_ab})
    return neu


def aendere_zuschlagsmaske_direkt(session: Session, ktx: AuthKontext, maske_id: UUID,
                                  **aenderungen) -> Zuschlagsmaske:
    """Direkte Korrektur — nur solange die Maske nie abgerechnet wurde (R-03)."""
    ktx.fordere_rolle("ADMIN")
    maske = session.get(Zuschlagsmaske, maske_id)
    if maske is None or maske.tenant_id != ktx.tenant_id:
        raise NichtGefunden("M04-E-404", "Zuschlagsmaske nicht gefunden")
    if maske.verwendet:
        raise FachFehler(
            "M04-E-011",
            "Diese Maske wurde bereits in einer Abrechnung verwendet und ist "
            "unveränderlich — Änderung als neue Version mit künftigem "
            "Gültigkeitsdatum anlegen.",
            {"maske_id": str(maske_id), "version": maske.version},
        )
    for feld, wert in aenderungen.items():
        setattr(maske, feld, wert)
    schreibe_audit(session, ktx, MODUL, "zuschlagsmaske", maske.id, "GEAENDERT",
                   neu=aenderungen)
    return maske


def markiere_masken_verwendet(session: Session, maske_ids: list[UUID]) -> None:
    """Aufgerufen aus der Abrechnung (M09), sobald eine Maske gebucht wurde."""
    for maske_id in maske_ids:
        maske = session.get(Zuschlagsmaske, maske_id)
        if maske is not None:
            maske.verwendet = True


class EntgeltPort:
    """EntgeltPortV1 — rechnet, bucht nicht (M04 §1)."""

    def __init__(self, session: Session, ktx: AuthKontext, mitarbeiter_port,
                 objekt_port):
        self._session = session
        self._ktx = ktx
        self._mitarbeiter_port = mitarbeiter_port
        self._objekt_port = objekt_port

    def _pausen_bezahlt(self, mitarbeiter_id: UUID | None, stichtag: date) -> bool:
        if mitarbeiter_id is None:
            return False
        grenzen = self._mitarbeiter_port.vertragsgrenzen(mitarbeiter_id, stichtag)
        return grenzen.pausen_bezahlt

    def berechne_lohn(self, req: berechnung.LohnAnfrage) -> berechnung.LohnErgebnis:
        stichtag = req.beginn_utc.astimezone(berechnung.STANDARD_ZONE).date()
        anfrage = berechnung.LohnAnfrage(
            mitarbeiter_id=req.mitarbeiter_id, objekt_id=req.objekt_id,
            funktion_code=req.funktion_code, beginn_utc=req.beginn_utc,
            ende_utc=req.ende_utc, pause_minuten=req.pause_minuten,
            bundesland=req.bundesland,
            pausen_bezahlt=self._pausen_bezahlt(req.mitarbeiter_id, stichtag),
        )
        resolver = tages_konfig_resolver(self._session, self._ktx.tenant_id,
                                         req.funktion_code, req.bundesland)
        return berechnung.berechne_lohn(anfrage, resolver)

    def berechne_umsatz(self, req: berechnung.UmsatzAnfrage) -> berechnung.UmsatzErgebnis:
        objekt = self._objekt_port.objekt(req.objekt_id)
        if objekt is None:
            raise NichtGefunden("M04-E-405", "Objekt nicht gefunden")
        resolver = umsatz_konfig_resolver(self._session, self._ktx.tenant_id,
                                          objekt.kunde_id, req.objekt_id,
                                          req.funktion_code, req.bundesland)
        return berechnung.berechne_umsatz(req, resolver)

    def stundensatz(self, mitarbeiter_id: UUID, funktion_code: str,
                    stichtag: date) -> int:
        tarif = tarif_am(self._session, self._ktx.tenant_id, stichtag)
        gruppe = lohngruppe_fuer(self._session, tarif, funktion_code)
        return max(gruppe.stundenlohn_cent, mindestlohn_am(self._session, stichtag))

    def ist_feiertag(self, datum: date, bundesland: str) -> bool:
        return ist_feiertag(self._session, self._ktx.tenant_id, datum, bundesland)

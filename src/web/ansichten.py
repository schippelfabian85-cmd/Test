"""Weboberfläche (server-seitig gerendert) für Kernel-Anmeldung, M01, M02, M04.

Die Sichten folgen den Oberflächen-Abschnitten der Modulanleitungen;
jede Aktion läuft über die Service-Schicht — die Oberfläche kennt keine
Fachregeln.
"""

import os
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kernel.api import hole_session, melde_an
from kernel.auth import AuthKontext, erstelle_token, kontext_aus_token
from kernel.fehler import FachFehler
from kernel.modelle import Benutzer
from kernel.zustaendigkeit import ZustaendigkeitDienst
from m01_personal import service as m01
from m01_personal.modelle import (
    Funktion, Mitarbeiter, MitarbeiterFunktion, MitarbeiterHistorie, Vertragstyp,
)
from m01_personal.port import MitarbeiterPort
from m02_kunde_objekt import service as m02
from m02_kunde_objekt.modelle import (
    Dienstanweisung, Kunde, KundeAnsprechpartner, Objekt, ObjektMitarbeiter,
    ObjektZuschlag,
)
from m02_kunde_objekt.port import ObjektPort
from m04_entgelt import berechnung
from m04_entgelt import service as m04
from m04_entgelt.modelle import Feiertag, Lohnart, Lohngruppe, Mindestlohn, Tarif, Zuschlagsmaske

ZONE = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def _ktx_oder_none(request: Request) -> AuthKontext | None:
    token = request.cookies.get("zugang")
    if not token:
        return None
    try:
        return kontext_aus_token(token)
    except FachFehler:
        return None


def _seite(request: Request, vorlage: str, ktx: AuthKontext | None, **daten) -> HTMLResponse:
    kontext = {"request": request, "ktx": ktx,
               "meldung": request.query_params.get("meldung"),
               "fehler": daten.pop("fehler", None)}
    kontext.update(daten)
    return templates.TemplateResponse(request, vorlage, kontext)


def _zur_anmeldung(request: Request) -> RedirectResponse:
    return RedirectResponse(f"/app/login?weiter={request.url.path}", status_code=303)


WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]


def _pruefe_objekt_sicht(session: Session, ktx: AuthKontext, objekt_id: UUID) -> None:
    """K-8, zweite Stufe: darf dieser Benutzer dieses Objekt sehen?"""
    sichtbare = ZustaendigkeitDienst(session).sichtbare_objekte(ktx)
    if sichtbare is not None and objekt_id not in sichtbare:
        from kernel.fehler import NichtErlaubt
        raise NichtErlaubt("M00-E-403", "Dieses Objekt liegt außerhalb Ihres Bereichs")


def _pruefe_personen_sicht(session: Session, ktx: AuthKontext,
                           mitarbeiter_id: UUID) -> None:
    sichtbare = ZustaendigkeitDienst(session).sichtbare_personen(ktx)
    if sichtbare is not None and mitarbeiter_id not in sichtbare:
        from kernel.fehler import NichtErlaubt
        raise NichtErlaubt("M00-E-403", "Diese Person liegt außerhalb Ihres Bereichs")


# -- Anmeldung ---------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def wurzel():
    return RedirectResponse("/app", status_code=303)


@router.get("/app/login", response_class=HTMLResponse)
def login_seite(request: Request):
    return _seite(request, "login.html", None,
                  weiter=request.query_params.get("weiter", "/app"))


@router.post("/app/login")
def login(request: Request, email: str = Form(...), passwort: str = Form(...),
          weiter: str = Form("/app"), session: Session = Depends(hole_session)):
    try:
        benutzer, rollen = melde_an(session, email, passwort)
    except FachFehler as fehler:
        return _seite(request, "login.html", None, fehler=fehler, email=email,
                      weiter=weiter)
    if not weiter.startswith("/"):
        weiter = "/app"
    antwort = RedirectResponse(weiter, status_code=303)
    token = erstelle_token(benutzer.id, benutzer.tenant_id, rollen, "access")
    antwort.set_cookie("zugang", token, httponly=True, samesite="lax",
                       max_age=15 * 60)
    return antwort


@router.get("/app/abmelden")
def abmelden():
    antwort = RedirectResponse("/app/login", status_code=303)
    antwort.delete_cookie("zugang")
    return antwort


# -- Übersicht ---------------------------------------------------------------

@router.get("/app", response_class=HTMLResponse)
def start(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    heute = date.today()
    schicht_lookup = request.app.state.schicht_lookup
    offene = schicht_lookup.offene_schichten(ktx.tenant_id, heute - timedelta(days=60),
                                             heute + timedelta(days=60))
    kennzahlen = {
        "aktive_mitarbeiter": session.scalar(select(func.count()).select_from(Mitarbeiter)
            .where(Mitarbeiter.tenant_id == ktx.tenant_id, Mitarbeiter.status == "AKTIV")),
        "kunden": session.scalar(select(func.count()).select_from(Kunde)
            .where(Kunde.tenant_id == ktx.tenant_id, Kunde.aktiv.is_(True))),
        "objekte": session.scalar(select(func.count()).select_from(Objekt)
            .where(Objekt.tenant_id == ktx.tenant_id, Objekt.aktiv.is_(True))),
        "offene_schichten": len(offene),
        "lizenzen": session.scalar(select(func.count()).select_from(Benutzer)
            .where(Benutzer.tenant_id == ktx.tenant_id, Benutzer.aktiv.is_(True))),
    }
    befristete = session.scalars(select(Objekt).where(
        Objekt.tenant_id == ktx.tenant_id, Objekt.aktiv.is_(True),
        Objekt.einsatzende.is_not(None),
        Objekt.einsatzende <= heute + timedelta(days=90),
    ).order_by(Objekt.einsatzende)).all()
    return _seite(request, "start.html", ktx, bereich="start", heute=heute,
                  wochentag=WOCHENTAGE[heute.weekday()],
                  kennzahlen=kennzahlen, befristete=befristete)


# -- M01: Personal -----------------------------------------------------------

@router.get("/app/mitarbeiter", response_class=HTMLResponse)
def mitarbeiter_liste(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    status = request.query_params.get("status") or None
    funktion = request.query_params.get("funktion") or None
    text = request.query_params.get("text") or None
    sichtbare = ZustaendigkeitDienst(session).sichtbare_personen(ktx)
    treffer = m01.suche(session, ktx, status=status, funktion_code=funktion,
                        text=text, sichtbare_personen=sichtbare)
    zeilen = []
    for ma in treffer:
        vt = session.get(Vertragstyp, ma.vertragstyp_id)
        zeilen.append({"ma": ma, "vertragstyp": vt.code if vt else "?",
                       "funktionen": m01.funktion_codes(session, ma.id)})
    funktionen = session.scalars(select(Funktion).where(
        Funktion.tenant_id == ktx.tenant_id).order_by(Funktion.sortierung)).all()
    return _seite(request, "mitarbeiter_liste.html", ktx, bereich="personal",
                  mitarbeiter=zeilen, funktionen=funktionen,
                  status=status, funktion=funktion, text=text)


@router.get("/app/mitarbeiter/neu", response_class=HTMLResponse)
def mitarbeiter_neu_seite(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    return _seite(request, "mitarbeiter_neu.html", ktx, bereich="personal",
                  werte={}, **_neu_auswahl(session, ktx))


def _neu_auswahl(session: Session, ktx: AuthKontext) -> dict:
    return {
        "vertragstypen": session.scalars(select(Vertragstyp).where(
            Vertragstyp.tenant_id == ktx.tenant_id, Vertragstyp.aktiv.is_(True),
        ).order_by(Vertragstyp.code)).all(),
        "funktionen": session.scalars(select(Funktion).where(
            Funktion.tenant_id == ktx.tenant_id, Funktion.aktiv.is_(True),
        ).order_by(Funktion.sortierung)).all(),
    }


@router.post("/app/mitarbeiter/neu")
async def mitarbeiter_anlegen(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    formular = await request.form()
    daten = {
        "personalnummer": formular.get("personalnummer"),
        "nachname": formular.get("nachname"), "vorname": formular.get("vorname"),
        "geburtsdatum": date.fromisoformat(formular["geburtsdatum"]) if formular.get("geburtsdatum") else None,
        "land": formular.get("land"),
        "eintrittsdatum": date.fromisoformat(formular["eintrittsdatum"]) if formular.get("eintrittsdatum") else None,
        "vertragstyp_id": UUID(formular["vertragstyp_id"]) if formular.get("vertragstyp_id") else None,
        "strasse": formular.get("strasse") or None, "plz": formular.get("plz") or None,
        "ort": formular.get("ort") or None, "email": formular.get("email") or None,
    }
    funktion_codes = formular.getlist("funktion_codes")
    try:
        ma = m01.lege_an(session, ktx, daten, funktion_codes)
    except FachFehler as fehler:
        werte = {k: formular.get(k) for k in formular}
        werte["funktion_codes"] = funktion_codes
        return _seite(request, "mitarbeiter_neu.html", ktx, bereich="personal",
                      fehler=fehler, werte=werte, **_neu_auswahl(session, ktx))
    return RedirectResponse(f"/app/mitarbeiter/{ma.id}?meldung=Mitarbeiter angelegt",
                            status_code=303)


@router.get("/app/mitarbeiter/{mitarbeiter_id}", response_class=HTMLResponse)
def mitarbeiter_akte(request: Request, mitarbeiter_id: UUID,
                     session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    _pruefe_personen_sicht(session, ktx, mitarbeiter_id)
    ma = m01._lade(session, ktx, mitarbeiter_id)
    reiter = request.query_params.get("reiter", "stammdaten")
    heute = date.today()
    vertragstyp = m01.vertragstyp_am(session, ma, heute)
    grenzen = m01.vertragsgrenzen(session, ktx, mitarbeiter_id, heute)
    funktionen_zeilen = [
        {"code": f.code, "bezeichnung": f.bezeichnung,
         "haupt": mf.ist_hauptfunktion, "gueltig_ab": mf.gueltig_ab}
        for mf, f in session.execute(
            select(MitarbeiterFunktion, Funktion)
            .join(Funktion, Funktion.id == MitarbeiterFunktion.funktion_id)
            .where(MitarbeiterFunktion.mitarbeiter_id == mitarbeiter_id)
        ).all()
    ]
    historie = session.scalars(select(MitarbeiterHistorie).where(
        MitarbeiterHistorie.mitarbeiter_id == mitarbeiter_id,
    ).order_by(MitarbeiterHistorie.zeitpunkt.desc())).all()
    return _seite(request, "mitarbeiter_akte.html", ktx, bereich="personal",
                  ma=ma, reiter=reiter, vertragstyp=vertragstyp, grenzen=grenzen,
                  funktionen_zeilen=funktionen_zeilen, historie=historie,
                  vertragstypen=_neu_auswahl(session, ktx)["vertragstypen"])


@router.post("/app/mitarbeiter/{mitarbeiter_id}/austritt")
def web_austritt(request: Request, mitarbeiter_id: UUID,
                 austrittsdatum: str = Form(...), grund: str = Form(""),
                 session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    try:
        m01.setze_austritt(session, ktx, mitarbeiter_id,
                           date.fromisoformat(austrittsdatum), grund or None)
    except FachFehler as fehler:
        return RedirectResponse(
            f"/app/mitarbeiter/{mitarbeiter_id}?meldung={fehler.code}: {fehler.message}",
            status_code=303)
    return RedirectResponse(f"/app/mitarbeiter/{mitarbeiter_id}?meldung=Austritt gesetzt",
                            status_code=303)


@router.post("/app/mitarbeiter/{mitarbeiter_id}/anonymisierung")
def web_anonymisierung(request: Request, mitarbeiter_id: UUID,
                       bestaetigung: str = Form(""),
                       session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    try:
        m01.anonymisiere(session, ktx, mitarbeiter_id,
                         bestaetigung=(bestaetigung == "ja"))
        meldung = "Anonymisierung durchgeführt"
    except FachFehler as fehler:
        meldung = f"{fehler.code}: {fehler.message} {fehler.details or ''}"
    return RedirectResponse(f"/app/mitarbeiter/{mitarbeiter_id}?meldung={meldung}",
                            status_code=303)


@router.post("/app/mitarbeiter/{mitarbeiter_id}/vertragstyp")
def web_vertragstyp(request: Request, mitarbeiter_id: UUID,
                    vertragstyp_id: str = Form(...), stichtag: str = Form(...),
                    session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    try:
        m01.wechsle_vertragstyp(session, ktx, mitarbeiter_id, UUID(vertragstyp_id),
                                date.fromisoformat(stichtag))
        meldung = "Vertragstyp gewechselt"
    except FachFehler as fehler:
        meldung = f"{fehler.code}: {fehler.message}"
    return RedirectResponse(
        f"/app/mitarbeiter/{mitarbeiter_id}?reiter=vertrag&meldung={meldung}",
        status_code=303)


# -- M02: Kunden und Objekte -------------------------------------------------

@router.get("/app/kunden", response_class=HTMLResponse)
def kunden_liste(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    kunden = session.scalars(select(Kunde).where(
        Kunde.tenant_id == ktx.tenant_id).order_by(Kunde.kundennummer)).all()
    return _seite(request, "kunden_liste.html", ktx, bereich="kunden", kunden=kunden)


@router.get("/app/kunden/{kunde_id}", response_class=HTMLResponse)
def kunde_akte(request: Request, kunde_id: UUID,
               session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    kunde = m02._lade_kunde(session, ktx, kunde_id)
    ansprechpartner = session.scalars(select(KundeAnsprechpartner).where(
        KundeAnsprechpartner.kunde_id == kunde_id)).all()
    objekte = session.scalars(select(Objekt).where(
        Objekt.kunde_id == kunde_id).order_by(Objekt.objektnummer)).all()
    return _seite(request, "kunde_akte.html", ktx, bereich="kunden", kunde=kunde,
                  ansprechpartner=ansprechpartner, objekte=objekte)


@router.get("/app/objekte", response_class=HTMLResponse)
def objekt_liste(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    objekte = session.scalars(select(Objekt).where(
        Objekt.tenant_id == ktx.tenant_id).order_by(Objekt.objektnummer)).all()
    sichtbare = ZustaendigkeitDienst(session).sichtbare_objekte(ktx)
    if sichtbare is not None:
        objekte = [o for o in objekte if o.id in sichtbare]
    zeilen = []
    for objekt in objekte:
        kunde = session.get(Kunde, objekt.kunde_id)
        zeilen.append({"objekt": objekt, "kunde": kunde.firmenname if kunde else "?"})
    return _seite(request, "objekt_liste.html", ktx, bereich="objekte", objekte=zeilen)


@router.get("/app/objekte/{objekt_id}", response_class=HTMLResponse)
def objekt_akte(request: Request, objekt_id: UUID,
                session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    _pruefe_objekt_sicht(session, ktx, objekt_id)
    objekt = m02._lade_objekt(session, ktx, objekt_id)
    kunde = session.get(Kunde, objekt.kunde_id)
    freigaben = []
    for freigabe in session.scalars(select(ObjektMitarbeiter).where(
            ObjektMitarbeiter.objekt_id == objekt_id)).all():
        person = session.get(Mitarbeiter, freigabe.mitarbeiter_id)
        freigaben.append({
            "mitarbeiter_id": freigabe.mitarbeiter_id,
            "name": f"{person.nachname}, {person.vorname}" if person else "?",
            "freigabe_ab": freigabe.freigabe_ab, "freigabe_bis": freigabe.freigabe_bis,
            "ist_stammkraft": freigabe.ist_stammkraft,
        })
    zuschlaege = session.scalars(select(ObjektZuschlag).where(
        ObjektZuschlag.objekt_id == objekt_id).order_by(
        ObjektZuschlag.stamm_id, ObjektZuschlag.version)).all()
    dienstanweisungen = session.scalars(select(Dienstanweisung).where(
        Dienstanweisung.objekt_id == objekt_id).order_by(
        Dienstanweisung.titel, Dienstanweisung.version.desc())).all()
    alle_mitarbeiter = m01.suche(session, ktx, status="AKTIV")
    return _seite(request, "objekt_akte.html", ktx, bereich="objekte",
                  objekt=objekt, kunde=kunde, freigaben=freigaben,
                  zuschlaege=zuschlaege, dienstanweisungen=dienstanweisungen,
                  alle_mitarbeiter=alle_mitarbeiter)


@router.post("/app/objekte/{objekt_id}/freigaben")
def web_freigabe(request: Request, objekt_id: UUID,
                 mitarbeiter_id: str = Form(...), freigabe_ab: str = Form(...),
                 freigabe_bis: str = Form(""), ist_stammkraft: str = Form(""),
                 session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    try:
        m02.erteile_freigabe(session, ktx, objekt_id, UUID(mitarbeiter_id),
                             date.fromisoformat(freigabe_ab),
                             date.fromisoformat(freigabe_bis) if freigabe_bis else None,
                             ist_stammkraft == "ja")
        meldung = "Freigabe erteilt"
    except FachFehler as fehler:
        meldung = f"{fehler.code}: {fehler.message}"
    return RedirectResponse(f"/app/objekte/{objekt_id}?meldung={meldung}",
                            status_code=303)


@router.post("/app/objekte/{objekt_id}/deaktivierung")
def web_deaktivierung(request: Request, objekt_id: UUID,
                      session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    try:
        m02.deaktiviere_objekt(
            session, ktx, objekt_id,
            schicht_lookup=request.app.state.schicht_lookup,
            pruefung_aktiv=request.app.state.konfiguration.get(
                "pruefe_schichten_bei_deaktivierung", True))
        meldung = "Objekt deaktiviert"
    except FachFehler as fehler:
        meldung = f"{fehler.code}: {fehler.message}"
    return RedirectResponse(f"/app/objekte/{objekt_id}?meldung={meldung}",
                            status_code=303)


# -- M04: Tarif, Entgelt, Probe-Rechner --------------------------------------

@router.get("/app/tarife", response_class=HTMLResponse)
def tarife(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    tarif_zeilen = []
    for tarif in session.scalars(select(Tarif).where(
            Tarif.tenant_id == ktx.tenant_id).order_by(Tarif.code, Tarif.version)).all():
        tarif_zeilen.append({
            "code": tarif.code, "version": tarif.version,
            "bezeichnung": tarif.bezeichnung, "gueltig_ab": tarif.gueltig_ab,
            "gueltig_bis": tarif.gueltig_bis, "aktiv": tarif.aktiv,
            "gruppen": session.scalars(select(Lohngruppe).where(
                Lohngruppe.tarif_id == tarif.id).order_by(Lohngruppe.code)).all(),
            "masken": session.scalars(select(Zuschlagsmaske).where(
                Zuschlagsmaske.tarif_id == tarif.id).order_by(
                Zuschlagsmaske.prioritaet)).all(),
        })
    lohnarten = session.scalars(select(Lohnart).where(
        Lohnart.tenant_id == ktx.tenant_id).order_by(Lohnart.nummer)).all()
    feiertage = {}
    for feiertag in session.scalars(select(Feiertag).where(
            Feiertag.tenant_id == ktx.tenant_id).order_by(Feiertag.datum)).all():
        feiertage.setdefault(feiertag.bundesland, []).append(feiertag)
    mindestloehne = session.scalars(
        select(Mindestlohn).order_by(Mindestlohn.gueltig_ab)).all()
    return _seite(request, "tarife.html", ktx, bereich="tarife",
                  tarife=tarif_zeilen, lohnarten=lohnarten,
                  feiertage=feiertage, mindestloehne=mindestloehne)


def _probe_auswahl(session: Session, ktx: AuthKontext) -> dict:
    return {
        "mitarbeiter": m01.suche(session, ktx, status="AKTIV"),
        "objekte": session.scalars(select(Objekt).where(
            Objekt.tenant_id == ktx.tenant_id, Objekt.aktiv.is_(True),
        ).order_by(Objekt.objektnummer)).all(),
        "funktionen": session.scalars(select(Funktion).where(
            Funktion.tenant_id == ktx.tenant_id).order_by(Funktion.sortierung)).all(),
    }


@router.get("/app/proberechner", response_class=HTMLResponse)
def probe_seite(request: Request, session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    return _seite(request, "proberechner.html", ktx, bereich="probe",
                  werte={"datum": str(date.today())}, ergebnis=None,
                  **_probe_auswahl(session, ktx))


@router.post("/app/proberechner", response_class=HTMLResponse)
def probe_rechnen(request: Request, mitarbeiter_id: str = Form(...),
                  objekt_id: str = Form(...), funktion_code: str = Form(...),
                  datum: str = Form(...), beginn: str = Form(...),
                  ende: str = Form(...), pause: int = Form(0),
                  session: Session = Depends(hole_session)):
    ktx = _ktx_oder_none(request)
    if ktx is None:
        return _zur_anmeldung(request)
    werte = {"mitarbeiter_id": mitarbeiter_id, "objekt_id": objekt_id,
             "funktion_code": funktion_code, "datum": datum,
             "beginn": beginn, "ende": ende, "pause": pause}
    try:
        tag = date.fromisoformat(datum)
        beginn_lokal = datetime.combine(tag, time.fromisoformat(beginn), tzinfo=ZONE)
        ende_lokal = datetime.combine(tag, time.fromisoformat(ende), tzinfo=ZONE)
        if ende_lokal <= beginn_lokal:   # Nachtschicht über Mitternacht (K-7)
            ende_lokal += timedelta(days=1)
        objekt = m02._lade_objekt(session, ktx, UUID(objekt_id))
        port = m04.EntgeltPort(session, ktx,
                               mitarbeiter_port=MitarbeiterPort(session, ktx),
                               objekt_port=ObjektPort(session, ktx))
        lohn = port.berechne_lohn(berechnung.LohnAnfrage(
            mitarbeiter_id=UUID(mitarbeiter_id), objekt_id=objekt.id,
            funktion_code=funktion_code,
            beginn_utc=beginn_lokal.astimezone(UTC),
            ende_utc=ende_lokal.astimezone(UTC),
            pause_minuten=pause, bundesland=objekt.bundesland))
        umsatz = port.berechne_umsatz(berechnung.UmsatzAnfrage(
            objekt_id=objekt.id, funktion_code=funktion_code,
            beginn_utc=beginn_lokal.astimezone(UTC),
            ende_utc=ende_lokal.astimezone(UTC),
            pause_minuten=pause, bundesland=objekt.bundesland))
        ergebnis = {"lohn": lohn, "umsatz": umsatz}
        fehler = None
    except FachFehler as fach_fehler:
        ergebnis, fehler = None, fach_fehler
    return _seite(request, "proberechner.html", ktx, bereich="probe",
                  werte=werte, ergebnis=ergebnis, fehler=fehler,
                  **_probe_auswahl(session, ktx))

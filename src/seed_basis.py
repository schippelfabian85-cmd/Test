"""Gemeinsamer Seed-Datensatz (Kernel §11) — synthetisch, keine Echtdaten (K-12).

Abweichung von der Anleitung (dokumentiert, DoD Nr. 8): der Seed liegt als
Python-Modul statt `seed/basis.sql` vor, damit er datenbankneutral über die
ORM-Modelle läuft. Er ist idempotent — ein zweiter Lauf ändert nichts.

Schichten (4 Wochen, 2 abgeglichen), Subunternehmer und Ressourcen liefern
die Stubs von M05/M12/M13, nicht die Datenbank.
"""

from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kernel.auth import hash_passwort
from kernel.modelle import Benutzer, BenutzerRolle, Mandant, Rolle, Zustaendigkeit
from m01_personal.modelle import (
    Funktion, Kostenstelle, Mitarbeiter, MitarbeiterFunktion,
    MitarbeiterHistorie, Vertragstyp,
)
from m02_kunde_objekt.modelle import (
    Kostentraeger, Kunde, KundeAnsprechpartner, Objekt, Objektart, ObjektMitarbeiter,
    ObjektZuschlag,
)
from m04_entgelt.modelle import (
    Feiertag, Lohnart, Lohngruppe, Mindestlohn, Tarif, Verrechnungssatz,
    Zuschlagsmaske,
)
from m04_entgelt.stub import FEIERTAGE_2026

TENANT = UUID("00000000-0000-0000-0000-000000000001")
TENANT_EVENTS = UUID("00000000-0000-0000-0000-000000000002")

ROLLEN = [("ADMIN", "Administrator"), ("PLANER", "Disponent"),
          ("CONTROLLER", "Controlling"), ("EL", "Einsatzleiter"),
          ("OL", "Objektleiter"), ("MA", "Mitarbeiter"),
          ("SUB", "Subunternehmer"), ("KUNDE", "Kundenzugang")]

# Entwicklungszugänge — nur Seed, nie Produktion.
BENUTZER = [
    ("admin@musterschutz.example", "musterschutz!", ["ADMIN"]),
    ("disposition@musterschutz.example", "musterschutz!", ["PLANER"]),
    ("controlling@musterschutz.example", "musterschutz!", ["CONTROLLER"]),
    ("objektleitung@musterschutz.example", "musterschutz!", ["OL"]),
]

_NAMEN = ["Albrecht", "Bergmann", "Conrad", "Dietrich", "Ehlers", "Fromm",
          "Grunwald", "Hartung", "Ilgner", "Jost", "Kaminski", "Lorenz"]
_VORNAMEN = ["Anna", "Bela", "Clara", "Deniz", "Elif", "Falk",
             "Greta", "Hanno", "Ivo", "Jule", "Kim", "Lars"]


def _ma_id(nr: int) -> UUID:
    return UUID(f"11111111-1111-1111-1111-{nr:012d}")

def _obj_id(nr: int) -> UUID:
    return UUID(f"22222222-2222-2222-2222-{nr:012d}")


def seed_basis(session: Session) -> bool:
    """Spielt den Seed ein; liefert False, wenn er bereits vorhanden ist."""
    if session.get(Mandant, TENANT) is not None:
        return False

    session.add_all([
        Mandant(id=TENANT, name="Musterschutz GmbH"),
        Mandant(id=TENANT_EVENTS, name="Musterschutz Events"),
    ])
    rollen = {}
    for code, name in ROLLEN:
        rolle = Rolle(code=code, name=name)
        rollen[code] = rolle
        session.add(rolle)
    session.flush()

    for email, passwort, rollen_codes in BENUTZER:
        benutzer = Benutzer(tenant_id=TENANT, email=email,
                            passwort_hash=hash_passwort(passwort))
        session.add(benutzer)
        session.flush()
        for code in rollen_codes:
            session.add(BenutzerRolle(benutzer_id=benutzer.id,
                                      rolle_id=rollen[code].id, tenant_id=TENANT))
        if "OL" in rollen_codes:   # Sichtbarkeitsbereich des Objektleiters (K-8)
            session.add_all([
                Zustaendigkeit(tenant_id=TENANT, benutzer_id=benutzer.id,
                               objekt_id=_obj_id(1)),
                *[Zustaendigkeit(tenant_id=TENANT, benutzer_id=benutzer.id,
                                 mitarbeiter_id=_ma_id(n)) for n in (1, 2, 5)],
            ])

    # --- M01: Vertragstypen (Muster A: Geringfügigkeitsgrenze versioniert) ---
    vz = Vertragstyp(tenant_id=TENANT, code="VZ", bezeichnung="Vollzeit",
                     kategorie="VOLLZEIT", soll_stunden_monat=173,
                     max_stunden_monat=200, urlaubstage_jahr=26,
                     gueltig_ab=date(2024, 1, 1))
    tz = Vertragstyp(tenant_id=TENANT, code="TZ", bezeichnung="Teilzeit 80",
                     kategorie="TEILZEIT", soll_stunden_monat=80,
                     min_stunden_monat=60, max_stunden_monat=100,
                     urlaubstage_jahr=26, gueltig_ab=date(2024, 1, 1))
    gf_alt = Vertragstyp(tenant_id=TENANT, code="GF", bezeichnung="Geringfügig",
                         kategorie="GERINGFUEGIG", soll_stunden_monat=40,
                         max_stunden_monat=45, max_verdienst_monat_cent=55600,
                         urlaubstage_jahr=24, gueltig_ab=date(2025, 1, 1),
                         gueltig_bis=date(2025, 12, 31), aktiv=False)
    session.add(gf_alt)
    session.flush()
    gf = Vertragstyp(tenant_id=TENANT, code="GF", bezeichnung="Geringfügig",
                     kategorie="GERINGFUEGIG", soll_stunden_monat=40,
                     max_stunden_monat=45, max_verdienst_monat_cent=60300,
                     urlaubstage_jahr=24, stamm_id=gf_alt.stamm_id, version=2,
                     gueltig_ab=date(2026, 1, 1))
    kf = Vertragstyp(tenant_id=TENANT, code="KF", bezeichnung="Kurzfristig",
                     kategorie="KURZFRISTIG", soll_stunden_monat=0,
                     max_einsatztage_jahr=70, urlaubstage_jahr=0,
                     gueltig_ab=date(2024, 1, 1))
    session.add_all([vz, tz, gf, kf])

    funktionen = {}
    for i, (code, bez) in enumerate([("WACH", "Wachdienst"), ("EMPFANG", "Empfangsdienst"),
                                     ("STREIFE", "Revierstreife"),
                                     ("OBJEKTLEITER", "Objektleitung")]):
        funktion = Funktion(tenant_id=TENANT, code=code, bezeichnung=bez, sortierung=i)
        funktionen[code] = funktion
        session.add(funktion)

    session.add_all([
        Kostenstelle(tenant_id=TENANT, nummer="1000", bezeichnung="Verwaltung"),
        Kostenstelle(tenant_id=TENANT, nummer="2000", bezeichnung="Objektdienst"),
    ])
    session.flush()

    # --- M01: 12 Mitarbeiter (4 VZ, 4 TZ, 2 GF, 2 KF; einer minderjährig,
    #     einer ausgeschieden) --------------------------------------------
    typen = [vz, vz, vz, vz, tz, tz, tz, tz, gf, gf, kf, kf]
    for nr in range(1, 13):
        geburtsdatum = date(1990, 3, 14)
        if nr == 4:
            geburtsdatum = date(2009, 5, 20)   # minderjährig
        status, austritt = "AKTIV", None
        if nr == 12:
            status, austritt = "AUSGESCHIEDEN", date(2026, 6, 30)
        ma = Mitarbeiter(
            id=_ma_id(nr), tenant_id=TENANT, personalnummer=f"P{nr:04d}",
            nachname=_NAMEN[nr - 1], vorname=_VORNAMEN[nr - 1],
            geburtsdatum=geburtsdatum, land="Deutschland",
            eintrittsdatum=date(2024, 1, 1), austrittsdatum=austritt,
            status=status, vertragstyp_id=typen[nr - 1].id,
            strasse="Musterweg 1", plz="06108", ort="Halle (Saale)",
            email=f"{_VORNAMEN[nr - 1].lower()}.{_NAMEN[nr - 1].lower()}@musterschutz.example",
        )
        session.add(ma)
        session.add(MitarbeiterHistorie(mitarbeiter_id=ma.id, feld="vertragstyp_id",
                                        alt=None, neu=str(typen[nr - 1].id)))
        codes = ["WACH"] if nr <= 8 else ["WACH", "EMPFANG"]
        if nr == 3:
            codes.append("OBJEKTLEITER")
        if nr in (2, 6):
            codes.append("STREIFE")
        for i, code in enumerate(codes):
            session.add(MitarbeiterFunktion(mitarbeiter_id=ma.id,
                                            funktion_id=funktionen[code].id,
                                            ist_hauptfunktion=(i == 0),
                                            gueltig_ab=date(2024, 1, 1)))

    # --- M02: 3 Kunden, 5 Objekte ---------------------------------------
    kunden = [
        Kunde(tenant_id=TENANT, kundennummer="K-1001",
              firmenname="Stadtwerke Halle GmbH", rechtsform="GmbH",
              ort="Halle (Saale)", plz="06108", strasse="Am Wasserturm 1",
              leitweg_id="991-33333-33", zahlungsziel_tage=30,
              rechnungsversand="ZUGFERD", rechnung_verdichtung="JE_OBJEKT",
              eintrittsdatum=date(2024, 1, 1)),
        Kunde(tenant_id=TENANT, kundennummer="K-1002",
              firmenname="Logistikpark Saale AG", rechtsform="AG",
              ort="Leuna", plz="06237", strasse="Industriestraße 12",
              zahlungsziel_tage=14, skonto_prozent=2, skonto_tage=7,
              rechnung_verdichtung="JE_LEISTUNGSART",
              eintrittsdatum=date(2024, 6, 1)),
        Kunde(tenant_id=TENANT, kundennummer="K-1003",
              firmenname="Kaufhaus Ammer KG", rechtsform="KG",
              ort="München", plz="80331", strasse="Stachus 5",
              zahlungsziel_tage=14, rechnung_verdichtung="JE_SCHICHT",
              eintrittsdatum=date(2025, 3, 1)),
    ]
    session.add_all(kunden)
    session.flush()
    session.add_all([
        KundeAnsprechpartner(kunde_id=kunden[0].id, anrede="Frau",
                             name="Petra Wolter", funktion="Werkschutzleitung",
                             email="p.wolter@stadtwerke-halle.example",
                             ist_hauptkontakt=True, erhaelt_rechnung=True),
        KundeAnsprechpartner(kunde_id=kunden[2].id, anrede="Herr",
                             name="Jonas Ammer", funktion="Inhaber",
                             email="j.ammer@ammer.example", ist_hauptkontakt=True),
    ])
    session.add(Kostentraeger(tenant_id=TENANT, nummer="KT-100",
                              bezeichnung="Bewachung Stammkunden"))

    arten = {}
    for code, bez in [("PFORTE", "Pforte"), ("STREIFE", "Streife"),
                      ("EMPFANG", "Empfang"), ("BAUSTELLE", "Baustelle")]:
        art = Objektart(tenant_id=TENANT, code=code, bezeichnung=bez)
        arten[code] = art
        session.add(art)
    session.flush()

    objekte = [
        Objekt(id=_obj_id(1), tenant_id=TENANT, objektnummer="O-2001",
               kunde_id=kunden[0].id, bezeichnung="Pforte Stadtwerke",
               objektart_id=arten["PFORTE"].id, bundesland="ST",
               strasse="Am Wasserturm 1", plz="06108", ort="Halle (Saale)",
               latitude=51.4825, longitude=11.9705, einsatzbeginn=date(2024, 1, 1)),
        Objekt(id=_obj_id(2), tenant_id=TENANT, objektnummer="O-2002",
               kunde_id=kunden[1].id, bezeichnung="Pforte Logistikpark",
               objektart_id=arten["PFORTE"].id, bundesland="ST",
               strasse="Industriestraße 12", plz="06237", ort="Leuna",
               latitude=51.3172, longitude=12.0129, einsatzbeginn=date(2024, 6, 1)),
        Objekt(id=_obj_id(3), tenant_id=TENANT, objektnummer="O-2003",
               kunde_id=kunden[1].id, bezeichnung="Revier Gewerbegebiet",
               objektart_id=arten["STREIFE"].id, bundesland="ST",
               ort="Leuna", latitude=51.32, longitude=12.01,
               einsatzbeginn=date(2024, 6, 1)),
        Objekt(id=_obj_id(4), tenant_id=TENANT, objektnummer="O-2004",
               kunde_id=kunden[2].id, bezeichnung="Empfang Kaufhaus",
               objektart_id=arten["EMPFANG"].id, bundesland="BY",
               strasse="Stachus 5", plz="80331", ort="München",
               latitude=48.1394, longitude=11.5656, einsatzbeginn=date(2025, 3, 1)),
        Objekt(id=_obj_id(5), tenant_id=TENANT, objektnummer="O-2005",
               kunde_id=kunden[2].id, bezeichnung="Baustelle Ammer-Anbau",
               objektart_id=arten["BAUSTELLE"].id, bundesland="BY",
               ort="München", einsatzbeginn=date(2026, 5, 1),
               einsatzende=date(2026, 10, 31)),   # befristet, ohne Koordinaten
    ]
    session.add_all(objekte)
    session.flush()

    for nr in range(1, 9):   # Freigaben für die aktiven Kräfte
        session.add(ObjektMitarbeiter(objekt_id=_obj_id(1 + (nr % 3)),
                                      mitarbeiter_id=_ma_id(nr),
                                      freigabe_ab=date(2024, 1, 1),
                                      ist_stammkraft=(nr <= 3)))
    session.add(ObjektMitarbeiter(objekt_id=_obj_id(4), mitarbeiter_id=_ma_id(9),
                                  freigabe_ab=date(2025, 3, 1), ist_stammkraft=True))
    session.add(ObjektZuschlag(tenant_id=TENANT, objekt_id=_obj_id(3),
                               bezeichnung="Revierpauschale", art="BETRAG",
                               wert=150, gueltig_ab=date(2024, 6, 1)))

    # --- M04: Tarif, Lohngruppen, Lohnarten, Masken, Sätze, Feiertage -----
    tarif = Tarif(tenant_id=TENANT, code="WSG-ST",
                  bezeichnung="Wach- und Sicherheitsgewerbe Muster",
                  bundesland="ST", quelle="Mustertarif",
                  gueltig_ab=date(2025, 1, 1))
    session.add(tarif)
    session.flush()
    session.add_all([
        Lohngruppe(tarif_id=tarif.id, code="LG1", bezeichnung="Lohngruppe 1",
                   stundenlohn_cent=1450, funktion_codes="WACH,EMPFANG"),
        Lohngruppe(tarif_id=tarif.id, code="LG2", bezeichnung="Lohngruppe 2",
                   stundenlohn_cent=1550, funktion_codes="STREIFE"),
        Lohngruppe(tarif_id=tarif.id, code="LG3", bezeichnung="Lohngruppe 3",
                   stundenlohn_cent=1750, funktion_codes="OBJEKTLEITER"),
    ])
    lohnarten = {}
    for nummer, bez, art, steuer in [
        ("1000", "Grundlohn", "GRUNDLOHN", True),
        ("1005", "Bezahlte Pause", "GRUNDLOHN", True),
        ("2010", "Nachtzuschlag 25 %", "ZUSCHLAG", False),
        ("2020", "Sonntagszuschlag 50 %", "ZUSCHLAG", False),
        ("2030", "Feiertagszuschlag 100 %", "ZUSCHLAG", False),
        ("3000", "Zeitwertkonto", "ZWK", True),
    ]:
        lohnart = Lohnart(tenant_id=TENANT, nummer=nummer, bezeichnung=bez,
                          art=art, steuerpflichtig=steuer, sv_pflichtig=steuer)
        lohnarten[nummer] = lohnart
        session.add(lohnart)
    session.flush()

    session.add_all([
        Zuschlagsmaske(tenant_id=TENANT, tarif_id=tarif.id, bezeichnung="Nacht",
                       typ="NACHT", prioritaet=10, kumulierung="KUMULIERT",
                       wochentage="0,1,2,3,4,5,6", von_uhrzeit=time(23),
                       bis_uhrzeit=time(6),
                       prozent=25, lohnart_id=lohnarten["2010"].id,
                       bemessung="GRUNDLOHN", gueltig_ab=date(2025, 1, 1)),
        Zuschlagsmaske(tenant_id=TENANT, tarif_id=tarif.id, bezeichnung="Sonntag",
                       typ="SONNTAG", prioritaet=20, kumulierung="KUMULIERT",
                       wochentage="6", prozent=50, lohnart_id=lohnarten["2020"].id,
                       bemessung="GRUNDLOHN", gueltig_ab=date(2025, 1, 1)),
        Zuschlagsmaske(tenant_id=TENANT, tarif_id=tarif.id, bezeichnung="Feiertag",
                       typ="FEIERTAG", prioritaet=30, kumulierung="KUMULIERT",
                       wochentage="", gilt_an_feiertagen=True, prozent=100,
                       lohnart_id=lohnarten["2030"].id, bemessung="GRUNDLOHN",
                       gueltig_ab=date(2025, 1, 1)),
    ])

    session.add_all([
        Verrechnungssatz(tenant_id=TENANT, kunde_id=kunden[0].id,
                         satz_cent_pro_stunde=2950,
                         zuschlag_weiterberechnung="VOLL",
                         gueltig_ab=date(2024, 1, 1)),
        Verrechnungssatz(tenant_id=TENANT, kunde_id=kunden[1].id,
                         satz_cent_pro_stunde=2850,
                         zuschlag_weiterberechnung="ANTEILIG",
                         weiterberechnung_prozent=50,
                         gueltig_ab=date(2024, 6, 1)),
        Verrechnungssatz(tenant_id=TENANT, kunde_id=kunden[1].id,
                         objekt_id=_obj_id(3), funktion_code="STREIFE",
                         satz_cent_pro_stunde=3150,
                         zuschlag_weiterberechnung="VOLL",
                         gueltig_ab=date(2024, 6, 1)),
        Verrechnungssatz(tenant_id=TENANT, kunde_id=kunden[2].id,
                         satz_cent_pro_stunde=2750,
                         zuschlag_weiterberechnung="KEINE",
                         gueltig_ab=date(2025, 3, 1)),
    ])

    for land, tage in FEIERTAGE_2026.items():
        namen = {date(2026, 6, 4): "Fronleichnam", date(2026, 10, 31): "Reformationstag",
                 date(2026, 11, 1): "Allerheiligen", date(2026, 8, 15): "Mariä Himmelfahrt"}
        for tag in sorted(tage):
            session.add(Feiertag(tenant_id=TENANT, datum=tag,
                                 bezeichnung=namen.get(tag, "Gesetzlicher Feiertag"),
                                 bundesland=land))
    session.add_all([
        Mindestlohn(gueltig_ab=date(2025, 1, 1), betrag_cent=1282),
        Mindestlohn(gueltig_ab=date(2026, 1, 1), betrag_cent=1390),
    ])
    session.flush()
    return True

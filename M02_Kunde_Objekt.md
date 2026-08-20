# M02 — Kunde und Objekt

**Voraussetzung:** nur `00_KERNEL.md`.
**Aufwand:** 20–30 PT · **Phase:** 1 · **Baubar ab:** sofort

---

## 1. Zweck und Abgrenzung

Verwaltet die Auftraggeberseite: Kunden, deren Objekte, Ansprechpartner und objektbezogene Vorgaben.

**Gehört dazu:** Kundenakte, Zahlungsmodalitäten, Objektakte, Objektgruppen, Objektdokumente, Dienstanweisungen, Objektzuschläge (Definition), Objektmitarbeiter (Zuordnung, wer an einem Objekt eingesetzt werden darf), Reviere.

**Gehört nicht dazu:** Rechnungen (M11), Schichten und Masterschichten (M05), Kontrollpunkte (M14). Objektzuschläge werden hier nur **definiert**, berechnet werden sie in M04.

---

## 2. Entitäten

```sql
kunde(
  id, tenant_id, kundennummer UNIQUE(tenant_id), firmenname, rechtsform,
  strasse, plz, ort, land,
  ust_id, steuernummer, leitweg_id, duns_nummer,
  zahlungsziel_tage, skonto_prozent, skonto_tage,
  rechnungsversand,        -- POST|EMAIL|ZUGFERD|PORTAL
  rechnung_verdichtung,    -- JE_OBJEKT|JE_LEISTUNGSART|JE_MONAT|JE_SCHICHT (M11 R-05)
  rechnungsempfaenger_email, abweichende_rechnungsanschrift_json,
  aktiv, eintrittsdatum, austrittsdatum, bemerkung, version
)

kunde_ansprechpartner(id, kunde_id, anrede, name, funktion, telefon,
                      mobil, email, ist_hauptkontakt, erhaelt_rechnung,
                      erhaelt_dienstplan, aktiv)

objekt(
  id, tenant_id, objektnummer UNIQUE(tenant_id), kunde_id,
  bezeichnung, objektart_id, objektgruppe_id,
  strasse, plz, ort, bundesland,     -- Bundesland maßgeblich für Feiertage (M04 R-07)
  latitude, longitude, geofence_radius_meter,
  einsatzbeginn, einsatzende, aktiv,
  kostenstelle_id, kostentraeger_id,
  ansprechpartner_vor_ort, telefon_vor_ort,
  besondere_hinweise, version
)

objektart(id, tenant_id, code, bezeichnung)            -- Pforte, Streife, Empfang...
objektgruppe(id, tenant_id, bezeichnung, uebergeordnet_id)
kostentraeger(id, tenant_id, nummer, bezeichnung, aktiv)
  -- referenziert von objekt, umsatzbuchung (M09), rechnung_position (M11)
objekt_dokument(id, objekt_id, dokument_id, kategorie, sichtbar_fuer_ma BOOL,
                gueltig_ab, gueltig_bis)
dienstanweisung(id, objekt_id, titel, inhalt, version, gueltig_ab,
                bestaetigung_erforderlich BOOL)
dienstanweisung_bestaetigung(dienstanweisung_id, mitarbeiter_id, zeitpunkt)

objekt_mitarbeiter(objekt_id, mitarbeiter_id, freigabe_ab, freigabe_bis,
                   ist_stammkraft BOOL, bemerkung)
objekt_mitarbeitergruppe(id, objekt_id, bezeichnung)

objekt_zuschlag(id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis,
                aktiv, objekt_id, bezeichnung, art, wert)   -- Muster A
kunde_historie(id, kunde_id, feld, alt, neu, zeitpunkt, benutzer_id)
```

---

## 3. Bereitgestellte Ports

```python
class ObjektPortV1(Protocol):
    def objekt(self, id: UUID) -> ObjektDTO | None: ...
    def objekte_kunde(self, kunde_id: UUID) -> list[ObjektDTO]: ...
    def ist_freigegeben(self, objekt_id: UUID, mitarbeiter_id: UUID,
                        stichtag: date) -> bool: ...
    def stammkraefte(self, objekt_id: UUID) -> list[UUID]: ...
    def zuschlaege(self, objekt_id: UUID, stichtag: date) -> list[ZuschlagDTO]: ...

class KundePortV1(Protocol):
    def kunde(self, id: UUID) -> KundeDTO | None: ...
    def rechnungsdaten(self, kunde_id: UUID) -> RechnungsdatenDTO: ...

@dataclass(frozen=True)
class ObjektDTO:
    id: UUID; tenant_id: UUID; objektnummer: str; bezeichnung: str
    kunde_id: UUID; objektart_code: str
    bundesland: str
    latitude: float | None; longitude: float | None
    geofence_radius_meter: int
    einsatzbeginn: date; einsatzende: date | None; aktiv: bool
    kostenstelle_nummer: str | None
```

`ist_freigegeben()` ist der wichtigste Aufruf: M05 und M06 fragen darüber, ob eine Person an einem Objekt überhaupt eingeplant werden darf.

---

## 4. Konsumierte Ports

`DokumentPort` (M03) für Dateiablage · `WiedervorlagePort` (M03) für R-08 · `SchichtLookupPort` (M05) für die Deaktivierungsprüfung aus R-02. **Bis M03/M05 existieren:** gegen die Stubs entwickeln (Dokument-Stub gibt IDs zurück und legt Dateien im lokalen Verzeichnis ab); die R-02-Prüfung bleibt bis dahin über die Konfigurationsflagge abschaltbar.

---

## 5. Ausgelöste Events

`m02.objekt.angelegt.v1` · `m02.objekt.deaktiviert.v1` · `m02.objekt_freigabe.erteilt.v1` · `m02.objekt_freigabe.entzogen.v1` · `m02.dienstanweisung.veroeffentlicht.v1`

---

## 6. Fachregeln

- **R-01** Ein Objekt gehört genau einem Kunden und kann nicht umgehängt werden. Bei Kundenwechsel: neues Objekt anlegen, altes deaktivieren.
- **R-02** Deaktivierung ist nur möglich, wenn keine Schichten in der Zukunft liegen. Prüfung über `SchichtLookupPort`; existiert dieser noch nicht, Prüfung vorerst über eine Konfigurationsflagge abschaltbar halten.
- **R-03** Objekte werden nie gelöscht, nur deaktiviert — historische Abrechnungen referenzieren sie.
- **R-04** Koordinaten sind Pflicht, sobald das Objekt für GPS-gestützte Zeiterfassung oder Kontrollrunden genutzt wird. Standardradius 100 m.
- **R-05** Eine Objektfreigabe kann befristet sein. Abgelaufene Freigaben verhindern Neuplanung, lassen bestehende Schichten aber unberührt.
- **R-06** Dienstanweisungen sind versioniert. Eine neue Version setzt alle Bestätigungen zurück, wenn `bestaetigung_erforderlich` gesetzt ist.
- **R-07** Objektzuschläge folgen Muster A und dürfen nach Verwendung in einer Abrechnung nicht mehr geändert werden.
- **R-08** Befristete Objekte (`einsatzende` gesetzt) erzeugen 30 Tage vor Ablauf eine Wiedervorlage (Anlage über `WiedervorlagePort`, M03).

---

## 7. Oberflächen

Kundenliste mit Filter · Kundenakte (Stammdaten · Ansprechpartner · Objekte · Zahlungsmodalitäten · Historie) · Objektliste mit Gruppen- und Kundenfilter · Objektakte (Stammdaten · Freigaben · Dokumente · Dienstanweisungen · Zuschläge · Historie) · Objektgruppenverwaltung als Baum · Kartenansicht aller Objekte.

---

## 8. Berechtigungen

Lesen: ADMIN, PLANER, CONTROLLER (alle) · EL/OL (eigener Bereich) · KUNDE (nur eigene Objekte, ohne Kalkulationsdaten).
Ändern: ADMIN, PLANER. Zahlungsmodalitäten und Objektzuschläge: nur ADMIN.

---

## 9. Akzeptanzkriterien

1. Objekt ohne Kunde ist nicht anlegbar (`M02-E-002`).
2. Deaktivierung bei zukünftigen Schichten wird abgelehnt (`M02-E-007`).
3. `ist_freigegeben()` liefert für einen Tag außerhalb der Freigabefrist `false`, innerhalb `true`.
4. Neue Version einer bestätigungspflichtigen Dienstanweisung setzt Bestätigungen zurück.
5. Objektzuschlagsänderung erzeugt eine neue Version; die alte bleibt mit `gueltig_bis` erhalten.
6. Kunde mit Leitweg-ID liefert diese über `rechnungsdaten()` durch.
7. Rolle `KUNDE` sieht ausschließlich Objekte des eigenen Kunden; Fremdzugriff ergibt HTTP 403.
8. Befristetes Objekt erzeugt 30 Tage vor `einsatzende` genau eine Wiedervorlage.

---

## 10. Bereitzustellender Stub

5 Objekte, 3 Kunden aus dem Seed, feste IDs `22222222-...-0001` ff. Enthält zwingend: ein 24/7-Objekt, ein befristetes, eines ohne Koordinaten.

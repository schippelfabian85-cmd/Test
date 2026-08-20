# M01 — Personalstammdaten

**Voraussetzung:** nur `00_KERNEL.md`. Keine anderen Modulanleitungen nötig.
**Aufwand:** 25–35 PT · **Phase:** 1 · **Baubar ab:** sofort

---

## 1. Zweck und Abgrenzung

Führt die Personalakte: Wer arbeitet für uns, unter welchem Vertrag, mit welchem Status.

**Gehört dazu:** Mitarbeiterakte, Vertragstypen, Funktionen, Anstellungsorte, Ein- und Austritt, Lizenzverwaltung, Personalerfassungsbogen, Anonymisierung.

**Gehört ausdrücklich nicht dazu:** Qualifikationen und Dokumente (M03), Lohnhöhe und Tarife (M04), Verfügbarkeit und Urlaub (M07), Zeiterfassung (M08). Wenn du diese Themen berührst, hast du die Modulgrenze verlassen.

---

## 2. Entitäten

```sql
mitarbeiter(
  id, tenant_id, personalnummer UNIQUE(tenant_id),
  nachname, vorname, geburtsdatum, geburtsort, staatsangehoerigkeit,
  strasse, plz, ort, land,
  telefon, mobil, email,
  eintrittsdatum, austrittsdatum, austrittsgrund,
  status,              -- BEWERBER|AKTIV|RUHEND|AUSGESCHIEDEN|ANONYMISIERT
  vertragstyp_id,      -- FK auf vertragstyp (Muster A, versioniert)
  anstellungsort_id, kostenstelle_id,
  foto_dokument_id,    -- nur ID, Datei liegt in M03
  sofortmeldung_erforderlich BOOL, sofortmeldung_erfolgt_am,
  bemerkung, version, created_at, created_by
)

vertragstyp(               -- Muster A: versioniert!
  id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis, aktiv,
  code, bezeichnung,
  kategorie,               -- VOLLZEIT|TEILZEIT|GERINGFUEGIG|KURZFRISTIG|AUSHILFE
  soll_stunden_monat, min_stunden_monat, max_stunden_monat,
  max_verdienst_monat_cent,        -- z.B. Geringfügigkeitsgrenze
  max_einsatztage_jahr,            -- z.B. 70-Tage-Regel
  urlaubstage_jahr,
  pausen_bezahlt BOOL,             -- Standard für M04 R-04; Masterschicht kann übersteuern
  zeitwertkonto_aktiv BOOL,
  zwk_lohnart_id                   -- nur ID, Lohnart liegt in M04 (für M10 R-03); NULL wenn ZWK inaktiv
)

funktion(id, tenant_id, code, bezeichnung, aktiv, sortierung)
mitarbeiter_funktion(mitarbeiter_id, funktion_id, ist_hauptfunktion,
                     gueltig_ab, gueltig_bis)
anstellungsort(id, tenant_id, bezeichnung, adresse, aktiv)
kostenstelle(id, tenant_id, nummer, bezeichnung, aktiv)
mitarbeiter_historie(id, mitarbeiter_id, feld, alt, neu, zeitpunkt, benutzer_id)
```

**Wichtig:** `vertragstyp` folgt Muster A aus dem Kernel. Ein Wechsel des Vertragstyps beim Mitarbeiter erzeugt einen Eintrag in `mitarbeiter_historie` mit Stichtag — die Abrechnung braucht später die Antwort auf „welcher Vertrag galt am 14.03.?".

---

## 3. Bereitgestellter Port

```python
class MitarbeiterPortV1(Protocol):
    def mitarbeiter(self, id: UUID) -> MitarbeiterDTO | None: ...
    def suche(self, tenant_id: UUID, status: str | None = None,
              funktion_code: str | None = None) -> list[MitarbeiterDTO]: ...
    def vertragsgrenzen(self, mitarbeiter_id: UUID,
                        stichtag: date) -> VertragsgrenzenDTO: ...
    def ist_aktiv(self, mitarbeiter_id: UUID, stichtag: date) -> bool: ...

@dataclass(frozen=True)
class MitarbeiterDTO:
    id: UUID; tenant_id: UUID; personalnummer: str
    nachname: str; vorname: str; geburtsdatum: date
    status: str; eintrittsdatum: date; austrittsdatum: date | None
    funktion_codes: tuple[str, ...]
    kostenstelle_nummer: str | None

@dataclass(frozen=True)
class VertragsgrenzenDTO:
    kategorie: str
    soll_minuten_monat: int
    min_minuten_monat: int | None
    max_minuten_monat: int | None
    max_verdienst_monat_cent: int | None
    max_einsatztage_jahr: int | None
    pausen_bezahlt: bool
    zeitwertkonto_aktiv: bool
    ist_minderjaehrig: bool          # aus Geburtsdatum am Stichtag
```

`ist_minderjaehrig` gehört bewusst hierher: M06 braucht die Aussage, soll aber nicht selbst rechnen.

---

## 4. Konsumierte Ports

Keine. M01 ist ohne jede Fremdabhängigkeit baubar.

---

## 5. Ausgelöste Events

| Event | Wann |
|---|---|
| `m01.mitarbeiter.eingetreten.v1` | Status wechselt auf `AKTIV` |
| `m01.mitarbeiter.ausgeschieden.v1` | Austrittsdatum erreicht (bei rückwirkendem Setzen: sofort) |
| `m01.mitarbeiter.vertragstyp_geaendert.v1` | Wechsel mit Stichtag |
| `m01.mitarbeiter.anonymisiert.v1` | DSGVO-Löschung durchgeführt |

---

## 6. Fachregeln

- **R-01** Die Personalnummer ist je Mandant eindeutig und nach Vergabe unveränderlich.
- **R-02** Pflichtfelder bei Neuanlage: Personalnummer, Name, Vorname, Geburtsdatum, Land, Eintrittsdatum, Vertragstyp, mindestens eine Funktion.
- **R-03** Ein Datensatz eines ausgeschiedenen Mitarbeiters darf **niemals** für eine neue Person wiederverwendet werden. Aufbewahrungsfrist bis 10 Jahre.
- **R-04** Mit **Erreichen** des Austrittsdatums wird die Benutzerlizenz taggenau frei (bei rückwirkendem Setzen sofort) — bis dahin arbeitet die Person weiter und behält ihren Zugang. Der Datensatz bleibt bestehen. (Gleiche Semantik wie M12 R-09.)
- **R-05** Anonymisierung löscht personenbezogene Felder, Kommunikation und Logfiles unwiderruflich, setzt die Personalnummer auf einen eindeutigen Platzhalter (`ANON-` + laufende Nummer — die Eindeutigkeit je Mandant aus R-01 bleibt gewahrt) und den Status auf `ANONYMISIERT`. Abrechnungsrelevante Aggregate bleiben erhalten. Zweistufige Bestätigung, nur Rolle `ADMIN`.
- **R-06** Vor Ablauf der gesetzlichen Aufbewahrungsfrist ist die Anonymisierung zu blockieren, mit Angabe des frühestmöglichen Datums.
- **R-07** `ist_aktiv(stichtag)` liefert genau dann `true`, wenn der Status am Stichtag `AKTIV` ist und `eintrittsdatum ≤ stichtag ≤ austrittsdatum` (sofern gesetzt) gilt. Ein Mitarbeiter mit Eintrittsdatum in der Zukunft ist damit für Stichtage vor dem Eintritt nicht planbar; `RUHEND` ist ebenfalls nicht planbar.
- **R-08** Statusübergänge: `BEWERBER → AKTIV → RUHEND ⇄ AKTIV → AUSGESCHIEDEN → ANONYMISIERT`. Rücksprünge aus `AUSGESCHIEDEN` nur mit Rolle `ADMIN` und Begründung.

---

## 7. Oberflächen

| Sicht | Inhalt |
|---|---|
| Mitarbeiterliste | Filter Status/Funktion/Vertragstyp, Alphabetfilter, Volltextsuche, Seitengröße wählbar, Sortierung je Spalte, CSV-Export |
| Mitarbeiterakte | Reiter: Stammdaten · Vertragsdaten · Funktionen · Historie. Weitere Reiter liefern andere Module — Platzhalter vorsehen |
| Neuanlage | Assistent mit Pflichtfeldprüfung und Hinweis auf fehlende Voraussetzungen (Vertragstyp/Funktion nicht angelegt) |
| Ausgeschiedene | Eigene Sicht mit Wiedereinstellungsfunktion |
| Karteileichen | Aktive ohne Einsatz seit N Monaten |
| Anonymisierung | Mehrfachauswahl, Sperrhinweise, Bestätigungsdialog |

---

## 8. Berechtigungen

| Aktion | Rollen |
|---|---|
| Lesen (alle) | ADMIN, PLANER, CONTROLLER |
| Lesen (eigener Bereich) | EL, OL — begrenzt über `ZustaendigkeitPort` |
| Lesen (eigene Person) | MA |
| Anlegen/Ändern | ADMIN, PLANER |
| Austritt setzen | ADMIN |
| Anonymisieren | ADMIN |

---

## 9. Akzeptanzkriterien

1. Neuanlage ohne Pflichtfeld schlägt mit Fehler `M01-E-001` und Feldliste fehl.
2. Zweite Anlage mit gleicher Personalnummer im selben Mandanten schlägt fehl, in einem anderen Mandanten gelingt sie.
3. Vertragstypwechsel zum 15. des Monats: `vertragsgrenzen()` liefert für den 14. den alten, für den 15. den neuen Wert.
4. `ist_minderjaehrig` kippt exakt am 18. Geburtstag.
5. Mit Erreichen des Austrittsdatums (bei rückwirkendem Setzen sofort) ist die Lizenz frei — Zähler in `benutzer` sinkt um eins; ein Austrittsdatum in der Zukunft ändert den Zähler noch nicht.
6. Anonymisierung innerhalb der Aufbewahrungsfrist wird mit `M01-E-014` abgelehnt.
7. Nach Anonymisierung enthält kein Feld mehr personenbezogene Daten; die Mitarbeiter-ID bleibt referenzierbar.
8. Jede Änderung erzeugt genau einen `audit_log`-Eintrag.
9. Alle Events werden bei den definierten Übergängen genau einmal veröffentlicht.
10. Ein Benutzer mit Rolle `OL` sieht ausschließlich Mitarbeiter seiner Objekte.

---

## 10. Bereitzustellender Stub

```python
class MitarbeiterPortStub(MitarbeiterPortV1):
    """12 Personen aus seed/basis.sql, deterministisch, ohne Datenbank."""
```
Feste IDs `11111111-...-0001` bis `-0012`. Darunter zwingend: eine minderjährige Person, eine geringfügig beschäftigte, eine ausgeschiedene.

---

## Anhang — Bewerbermanagement (optional, Phase 2, +15–25 PT)

Vorgelagerte Pipeline `EINGANG → EINZULADEN → EINGELADEN → ANGENOMMEN → ABGELEHNT`, Dokumentenanhang, Terminvorschlag, Zu-/Absage. Bei Annahme entsteht ein Mitarbeiter im Status `BEWERBER` mit Eintrittsdatum. Sauber als eigenes Untermodul, das nur `MitarbeiterPortV1` schreibend nutzt.

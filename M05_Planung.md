# M05 — Schichtmodell und Objektplanung

**Voraussetzung:** `00_KERNEL.md` + Stubs von `MitarbeiterPort`, `ObjektPort`, `RegelpruefPort`, `VerfuegbarkeitsPort`.
**Aufwand:** 70–100 PT · **Phase:** 1 · Das umfangreichste Einzelmodul.

---

## 1. Zweck und Abgrenzung

Erzeugt und besetzt Schichten. Hier arbeitet der Disponent den ganzen Tag.

**Gehört dazu:** Masterschichten, Schichterzeugung, Besetzung auf allen Wegen, Schichtrhythmen, Vorausplanung, Umplanung, Ausfall, Planungssichten (Objekt, Tag, Woche, Monat, Intraday), Staffing, Planfreigabe und Versand.

**Gehört nicht dazu:** Die Regelprüfung selbst (M06 — M05 ruft nur auf und stellt dar), Ist-Zeiten (M08), Abrechnung (M09), Veranstaltungen (M20).

---

## 2. Entitäten

```sql
masterschicht(                                    -- Muster A, versioniert
  id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis, aktiv,
  objekt_id, kuerzel, bezeichnung,
  beginn_zeit, ende_zeit, geht_ueber_mitternacht BOOL,
  pause_minuten, pause_bezahlt BOOL, pause_lohnart_id,
  funktion_code, position_bezeichnung,
  anzahl_mo, anzahl_di, anzahl_mi, anzahl_do,
  anzahl_fr, anzahl_sa, anzahl_so, anzahl_feiertag,
  dak_aktiv BOOL, dak_intervall_minuten,
  erforderliche_qualifikation_codes[])

schicht(
  id, tenant_id, objekt_id, masterschicht_id,
  datum,                       -- Zuordnungstag = Startdatum (Kernel K-7)
  beginn_utc, ende_utc, pause_minuten,
  funktion_code, schichtkuerzel,
  mitarbeiter_id NULL, subunternehmer_id NULL,
  zustand,                     -- Kernel Abschnitt 5
  besetzt_am, besetzt_von, freigegeben_am, freigegeben_von,
  ausfallgrund, bemerkung,
  version, created_at, created_by)

schicht_historie(id, schicht_id, zeitpunkt, benutzer_id, aktion,
                 alt_json, neu_json)
schichtrhythmus(id, tenant_id, bezeichnung, muster_json, laenge_tage)
mitarbeiter_rhythmus(mitarbeiter_id, schichtrhythmus_id, startdatum, offset_tage)
planfreigabe(id, tenant_id, objekt_id, von_datum, bis_datum,
             freigegeben_am, freigegeben_von, versendet_am)
```

**Zentral:** `schicht` referenziert die konkrete Masterschicht-Version. Eine spätere Änderung der Masterschicht verändert bestehende Schichten nicht.

---

## 3. Bereitgestellter Port

```python
class SchichtLookupPortV1(Protocol):
    def schicht(self, schicht_id: UUID) -> SchichtDTO | None: ...
    def schichten_person(self, mitarbeiter_id: UUID, von: date, bis: date) -> list[SchichtDTO]: ...
    def schichten_objekt(self, objekt_id: UUID, von: date, bis: date) -> list[SchichtDTO]: ...
    def offene_schichten(self, tenant_id: UUID, von: date, bis: date) -> list[SchichtDTO]: ...
    def setze_zustand(self, schicht_id: UUID, neuer_zustand: str,
                      actor_id: UUID, grund: str | None) -> None: ...
```

`SchichtDTO` ist im Kernel definiert und wird nicht erweitert.

---

## 4. Konsumierte Ports

`MitarbeiterPort` (aktiv? Funktionen?) · `ObjektPort` (Freigabe, Stammkräfte) · `RegelpruefPort` (jede Besetzung) · `VerfuegbarkeitsPort` (Urlaub, Krankheit, Bereitschaft) · `BenachrichtigungsPort` (Planversand).

---

## 5. Ausgelöste Events

`m05.schicht.erzeugt.v1` · `m05.schicht.besetzt.v1` · `m05.schicht.umbesetzt.v1` · `m05.schicht.ausgefallen.v1` · `m05.schicht.storniert.v1` · `m05.plan.freigegeben.v1`

---

## 6. Fachregeln

- **R-01** Schichten entstehen ausschließlich aus einer Masterschicht. Freie Einzelschichten sind nur mit Sonderrecht möglich und werden als solche gekennzeichnet.
- **R-02** Erzeugung erfolgt für einen Zeitraum von bis zu 12 Monaten im Voraus. Wiederholter Lauf über denselben Zeitraum erzeugt keine Duplikate (Idempotenz über `objekt_id + masterschicht_id + datum + laufnummer`).
- **R-03** Vor jeder Besetzung wird `RegelpruefPort` aufgerufen. Verstöße der Stufe `BLOCKIEREND` verhindern die Besetzung, Stufe `WARNUNG` erlaubt sie mit Begründungspflicht. Beides wird protokolliert.
- **R-04** Eine Person darf zur selben Zeit nur eine Schicht haben. Überschneidungen sind immer blockierend, auch objekt- und mandantenübergreifend.
- **R-05** Es sind mindestens diese Besetzungswege bereitzustellen: Einzelklick im Raster · Mehrfachauswahl Person auf Masterschicht · Mehrfachauswahl Masterschicht auf Personen · Serienbesetzung über Zeitraum · Schnellplanung aus der Masterschicht · Drag & Drop · Verschieben zwischen Personen · Besetzung aus der Intraday-Sicht · Besetzung aus der Objektübersicht.
- **R-06** Serienbesetzung überspringt Tage, an denen die Person bereits verplant oder nicht verfügbar ist — ohne Abbruch, mit Ergebnisbericht am Ende.
- **R-07** Umbesetzung nach Planfreigabe erfordert einen Grund und benachrichtigt die betroffenen Personen.
- **R-08** Ausfall (`AUSGEFALLEN`) setzt die Schicht zurück auf `GEPLANT`, wenn nachbesetzt werden soll — die ursprüngliche Zuordnung bleibt in der Historie.
- **R-09** Ab Zustand `ABGEGLICHEN` ist keine Änderung mehr möglich (Kernel K-6).
- **R-10** Nachtschichten werden dem **Startdatum** zugeordnet, in allen Sichten und Auswertungen einheitlich (Kernel K-7).

---

## 7. Oberflächen

| Sicht | Zweck |
|---|---|
| Objektplanung | Raster Personen × Tage für ein Objekt, Masterschichten als Kopfzeilen, Verstoßsymbole, Drag & Drop |
| Tagesplan | Alle Objekte eines Tages, offene Schichten farblich hervorgehoben, Livestatus |
| Wochen-/Monatsansicht | Verdichtete Übersicht, druckbar |
| Intraday | Laufender Tag mit Echtzeitstatus, Fokus auf Störungen |
| Staffing | Person × Monat mit Soll/Ist/Min/Max, Lohn geplant und abgeglichen, Ampelfarben |
| Planungsübersicht | Besetzungsgrad je Objekt und Zeitraum |
| Vorausplanung | Erzeugung von Schichten aus Masterschichten für Zeiträume |
| Planfreigabe | Freigabe je Objekt und Zeitraum, Versand an Mitarbeiter |
| Druck | Objektplan, Mitarbeiterplan, Aushangplan als PDF |

Zwingend in jeder Planungssicht: Legende und Verstoßsymbol mit Tooltip. Der Disponent muss ohne Klick erkennen, wo es klemmt.

---

## 8. Berechtigungen

Planen: ADMIN, PLANER (alles), EL/OL (eigener Bereich über `ZustaendigkeitPort`).
Freigeben und versenden: ADMIN, PLANER.
Blockierende Verstöße übersteuern: nur ADMIN, immer mit Begründung und Protokoll.
Lesen: CONTROLLER (alle), MA (eigene Schichten), KUNDE (eigene Objekte ohne Personendetails, sofern freigeschaltet).

---

## 9. Akzeptanzkriterien

1. Vorausplanung über 3 Monate erzeugt die exakt erwartete Schichtanzahl inklusive korrekter Feiertagsbehandlung.
2. Zweiter Lauf über denselben Zeitraum erzeugt null zusätzliche Schichten.
3. Besetzung mit überschneidender Fremdschicht wird blockiert (`M05-E-004`).
4. Serienbesetzung über 4 Wochen überspringt Urlaubstage und meldet sie im Ergebnisbericht.
5. Alle neun Besetzungswege aus R-05 sind über Test oder UI-Test nachgewiesen.
6. Nachtschicht 22:00–06:00 erscheint im Tagesplan des Starttages, nicht des Folgetages.
7. Änderung einer Masterschicht lässt bestehende Schichten unverändert.
8. Umbesetzung nach Freigabe ohne Grund wird abgelehnt; mit Grund wird die betroffene Person benachrichtigt.
9. Änderungsversuch an abgeglichener Schicht ergibt `M05-E-009`.
10. Staffing zeigt für eine Teilzeitkraft mit 80 h Sollzeit und 92 h Planung die Überschreitung farblich an.
11. Jede Zustandsänderung erzeugt genau einen Historieneintrag.

---

## 10. Bereitzustellender Stub

Stellt für die Seed-Objekte 4 Wochen Schichten bereit, davon 2 abgeglichen. Feste IDs `55555555-...`. Enthält zwingend: eine unbesetzte Schicht, eine Nachtschicht über Mitternacht, eine ausgefallene.

---

## 11. Hinweis zur Umsetzung

Das Planungsraster ist die Sicht mit dem höchsten Nutzungsanteil im ganzen System. Wenn sie bei 60 Personen × 31 Tagen träge reagiert, wird das Produkt abgelehnt — unabhängig von allen anderen Qualitäten. Empfehlung: virtualisiertes Rendering, Vorabladen des Monats in einem Aufruf, optimistische Aktualisierung der Oberfläche, Regelprüfung asynchron nachgezogen.

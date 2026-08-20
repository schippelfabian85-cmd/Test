# M13 — Ressourcen und Inventar

**Voraussetzung:** `00_KERNEL.md` + `MitarbeiterPort`, `SchichtLookupPort`, `ObjektPort`, `QualifikationsPort`, `WiedervorlagePort` (Stubs — Letzterer für R-09, vgl. M03).
**Aufwand:** 30–45 PT · **Phase:** 4 · **Das Differenzierungsmodul gegenüber dem Wettbewerb.**

## 1. Zweck und Abgrenzung
Verwaltet Betriebsmittel — und zwar **einsatzbezogen**, nicht nur personenbezogen. Genau darin liegt der Unterschied zu vergleichbaren Systemen am Markt, die lediglich Bestände zählen und einer Person zuordnen.

**Dazu:** Ressourcenkatalog, Bestandsführung, Einzelstückverfolgung mit Seriennummer, Ausgabe an Person **und** Schicht, Rückgabepflicht als Schichtabschluss, Prüf- und Ablauffristen, Schadens- und Verlustfälle, Belastung auf den Leistungsnachweis, Übergabeprotokolle mit Quittung.
**Nicht dazu:** Beschaffung und Lieferantenwesen, Anlagenbuchhaltung.

## 2. Entitäten
```sql
ressourcenart(id, tenant_id, code, bezeichnung, kategorie,
              einzelstueckverfolgung BOOL,     -- Seriennummer statt Menge
              rueckgabepflicht BOOL,           -- blockiert Ausstempeln
              erforderliche_qualifikation_codes[],
              pruefintervall_monate, nutzungsdauer_monate,
              ersatzwert_cent, weiterbelastbar BOOL, aktiv)
              -- kategorie: DIENSTKLEIDUNG|FUNK|SCHLUESSEL|FAHRZEUG|
              --            AUSWEIS|SCHUTZAUSRUESTUNG|GERAET|SONSTIGES

ressource(id, tenant_id, ressourcenart_id, inventarnummer UNIQUE(tenant_id),
          seriennummer, bezeichnung, groesse,
          objekt_id NULL,          -- fest am Objekt stationiert
          zustand,                 -- NEU|GUT|GEBRAUCHT|DEFEKT|VERLOREN|AUSGESONDERT
          beschafft_am, beschaffungswert_cent,
          naechste_pruefung_am, gueltig_bis, bemerkung, aktiv)

bestand(id, tenant_id, ressourcenart_id, groesse, objekt_id NULL,
        menge_gesamt, menge_verfuegbar, mindestbestand)
bestandsbewegung(id, tenant_id, ressourcenart_id, ressource_id NULL,
                 datum, menge_aenderung, grund, bemerkung, benutzer_id)

ausgabe(
  id, tenant_id, ressource_id NULL, ressourcenart_id, menge,
  mitarbeiter_id NULL, subunternehmer_id NULL,
  schicht_id NULL,             -- einsatzbezogene Ausgabe
  objekt_id NULL,
  ausgegeben_am, ausgegeben_von, ausgabeart,
  erwartete_rueckgabe_am,
  zurueck_am, zurueck_an, zustand_bei_rueckgabe,
  status,                      -- AUSGEGEBEN|ZURUECK|UEBERFAELLIG|VERLOREN|BESCHAEDIGT
  quittung_dokument_id, unterschrift_dokument_id,
  schaden_beschreibung, schaden_betrag_cent, weiterbelastet_an,
  bemerkung)
  -- ausgabeart: DAUERHAFT | SCHICHTBEZOGEN | OBJEKTGEBUNDEN

ressource_pruefung(id, ressource_id, datum, ergebnis, pruefer,
                   naechste_pruefung_am, dokument_id)
```

## 3. Bereitgestellter Port
```python
class RessourcenPortV1(Protocol):
    def offene_rueckgaben(self, mitarbeiter_id: UUID) -> list[AusgabeDTO]: ...
    def offene_rueckgaben_schicht(self, schicht_id: UUID) -> list[AusgabeDTO]: ...
    def darf_ausstempeln(self, schicht_id: UUID) -> tuple[bool, list[str]]: ...
    def belastungen(self, objekt_id: UUID, monat: str) -> list[BelastungDTO]: ...
```

`darf_ausstempeln()` ist der Aufruf, den M08 vor jeder Abmeldung ausführt — die technische Umsetzung der Rückgabepflicht.

## 4. Ausgelöste Events
`m13.ressource.ausgegeben.v1` · `m13.ressource.zurueck.v1` · `m13.ressource.nicht_zurueck.v1` · `m13.ressource.pruefung_faellig.v1` · `m13.bestand.unter_mindest.v1` · `m13.ressource.schaden.v1`

## 5. Fachregeln
- **R-01** Drei Ausgabearten mit unterschiedlicher Logik: **dauerhaft** (Dienstkleidung, bis zum Austritt), **schichtbezogen** (Funkgerät, Schlüssel — Rückgabe am Schichtende), **objektgebunden** (bleibt am Objekt, wechselt mit der Schicht den Träger).
- **R-02** Bei `einzelstueckverfolgung` wird das konkrete Stück ausgegeben, nicht nur die Menge. Funkgerät 12 ist nicht Funkgerät 13 — bei Verlust und Haftung ist das entscheidend.
- **R-03** Ist an der Ressourcenart eine Qualifikation hinterlegt, wird sie über `QualifikationsPort` geprüft. Ohne gültige Qualifikation keine Ausgabe.
- **R-04** Bei `rueckgabepflicht` blockiert eine offene Rückgabe das Ausstempeln. M08 fragt über `darf_ausstempeln()`; der Mitarbeiter sieht in der App, was fehlt.
- **R-05** Eine überfällige Rückgabe erzeugt einen Eintrag in derselben Prüf-Inbox wie fehlende Stempelungen. Getrennte Arbeitslisten werden im Alltag übersehen.
- **R-06** Ausgabe und Rückgabe werden quittiert. In der App per Bestätigung mit Zeitstempel, optional mit Unterschrift — das ist der Beweiswert im Schadensfall.
- **R-07** Eine ausgegebene Ressource kann nicht gelöscht werden, solange sie nicht zurückgemeldet ist.
- **R-08** Schäden und Verluste werden mit Betrag erfasst. Bei `weiterbelastbar` entsteht eine Position für die Kundenabrechnung.
- **R-09** Prüffristen erzeugen 30 Tage vorher eine Wiedervorlage. Eine überfällige Prüfung sperrt die Ausgabe.
- **R-10** Unterschreitet der verfügbare Bestand den Mindestbestand, wird gemeldet — vor dem Einsatztag, nicht danach.
- **R-11** Beim Austritt einer Person listet das System alle offenen Rückgaben auf. Der Austritt bleibt möglich, wird aber protokolliert.

## 6. Oberflächen
Ressourcenkatalog mit Kategorien · Bestandsübersicht mit Mindestbestandsampel · Einzelstückliste mit Zustand und Prüfstatus · Ausgabemaske (Person oder Schicht wählbar) · Rückgabemaske mit Zustandserfassung · offene Ausgaben als Arbeitsliste, filterbar nach Person, Objekt, Überfälligkeit · Reiter „Ressourcen" in Mitarbeiter- und Objektakte · Prüfplan · Schadensfälle · App-Sichten: meine Ausrüstung, Übernahme, Rückgabe quittieren.

## 7. Berechtigungen
Katalog und Bestände: ADMIN. Ausgabe und Rückgabe: ADMIN, PLANER, EL, OL. Quittieren: MA (eigene). Schäden erfassen: ADMIN, PLANER, EL, OL. Weiterbelastung freigeben: ADMIN.

## 8. Akzeptanzkriterien
1. Schichtbezogene Ausgabe ohne Rückgabe blockiert das Ausstempeln; `darf_ausstempeln()` liefert `false` mit Nennung des Gegenstands.
2. Dauerhafte Ausgabe blockiert das Ausstempeln nicht.
3. Ausgabe eines Funkgeräts an eine Person ohne erforderliche Qualifikation wird abgelehnt.
4. Einzelstückverfolgung ordnet exakt das gescannte Stück zu, nicht ein beliebiges der Art.
5. Überfällige Rückgabe erscheint in der Prüf-Inbox von M08.
6. Rückgabe mit Zustand `DEFEKT` und Betrag erzeugt eine Belastungsposition, sofern weiterbelastbar.
7. Objektgebundene Ressource wechselt bei Schichtwechsel den Verantwortlichen ohne Rückgabe ins Lager.
8. Unterschreitung des Mindestbestands erzeugt genau ein Event.
9. Löschversuch einer ausgegebenen Ressource wird abgelehnt (`M13-E-008`).
10. Austritt einer Person mit 3 offenen Ausgaben listet alle drei auf.
11. Überfällige Prüfung sperrt die Ausgabe der betroffenen Ressource.

## 9. Stub
8 Ressourcen aus dem Seed: 3 Funkgeräte mit Seriennummer, 2 Schlüsselbunde, 3 Warnwesten mit Nummern. Eine Ressource überfällig, eine mit abgelaufener Prüfung.

## 10. Hinweis
Fachlich der stärkste Hebel des Projekts: Die Anforderung ist bei Sicherheitsdiensten real und verbreitet, im Wettbewerb aber nur oberflächlich gelöst. Wer Schlüsselverwaltung revisionssicher abbildet, hat ein Verkaufsargument, das über den Erstkunden hinausträgt.

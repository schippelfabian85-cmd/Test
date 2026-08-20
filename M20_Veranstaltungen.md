# M20 — Veranstaltungen, Messen und Reviere

**Voraussetzung:** `00_KERNEL.md` + Ports von M01, M02, M03, M04, M05, M06, M07 (Stubs) — die Vorschlagsliste braucht Qualifikation (M03) und Verfügbarkeit (M07).
**Aufwand:** 50–75 PT · **Phase:** 5 · **Nur bauen, wenn der Kunde dieses Geschäft betreibt.**

## 1. Zweck und Abgrenzung
Planung für kurzfristige, personalintensive Einsätze mit anderer Logik als der Objektschutz.
**Dazu:** Veranstaltungen mit Typen, mehrtägige Planung über eine übergeordnete Klammer, Gruppenvorlagen, Messeplanung, Sedcard, Soll-/Ist-Vergleich, Einsatzbewertung, Revierplanung mit Aufträgen und Einzelleistungen.
**Nicht dazu:** Objektplanung (M05) — die Modelle sind bewusst getrennt.

## 2. Warum ein eigenes Modul
Objektschutz ist wiederkehrend und langfristig: gleiche Schicht, gleiches Objekt, Monat für Monat. Veranstaltungen sind einmalig, kurzfristig, mit hohem Personalbedarf und häufigen Änderungen bis zum Vortag. Ein gemeinsames Datenmodell führt zu einem Kompromiss, der beides schlecht abbildet.

## 3. Entitäten
```sql
veranstaltung(id, tenant_id, nummer, kunde_id, veranstaltungstyp_id,
              parent_id NULL,           -- übergeordnete Klammer
              bezeichnung, ort, adresse_json, latitude, longitude,
              beginn_utc, ende_utc, treffpunkt, treffpunkt_zeit,
              kleiderordnung, ansprechpartner_vor_ort, telefon_vor_ort,
              hinweise, status, kalkuliert_cent, aktiv)
              -- status: ANGEFRAGT|GEPLANT|BESTAETIGT|LAEUFT|BEENDET|ABGESAGT
veranstaltungstyp(id, tenant_id, code, bezeichnung,
                  standard_funktionen[], standard_qualifikationen[],
                  vorlage_json)
veranstaltung_bedarf(id, veranstaltung_id, funktion_code, anzahl,
                     beginn_utc, ende_utc, qualifikation_codes[],
                     verrechnungssatz_cent, bemerkung)
veranstaltung_besetzung(id, veranstaltung_bedarf_id, mitarbeiter_id NULL,
                        subunternehmer_id NULL, schicht_id,
                        status, zugesagt_am, bemerkung)
gruppenvorlage(id, tenant_id, bezeichnung, mitarbeiter_ids[], funktion_code)
sedcard(id, mitarbeiter_id, groesse, konfektion, sprachen[],
        besondere_faehigkeiten, foto_dokument_id, aktualisiert_am)
einsatzbewertung(id, veranstaltung_id, mitarbeiter_id, bewertet_von,
                 datum, note, kategorien_json, bemerkung)
revier(id, tenant_id, bezeichnung, objekt_ids[], fahrzeug_ressource_id, aktiv)
revier_auftrag(id, revier_id, kunde_id, objekt_id, leistungsart,
               frequenz,        -- Format verbindlich festlegen: Wochentage[] oder Anzahl je Woche
               zeitfenster_von, zeitfenster_bis,
               dauer_minuten, verrechnungssatz_cent, gueltig_ab, gueltig_bis)
```

## 4. Fachregeln
- **R-01** Eine übergeordnete Klammer (`parent_id`) ist selbst nicht planbar, sondern nur Ordnungsrahmen für Einzeltage oder Schichtgruppen. Untergeordnete Veranstaltungen können abweichende Treffpunkte und Hinweise haben.
- **R-02** Planung erfolgt bedarfsorientiert: erst die benötigte Anzahl je Funktion, dann die Besetzung. Umgekehrt zur Objektplanung, wo die Schicht zuerst existiert.
- **R-03** Die erzeugten Schichten laufen anschließend durch dieselben Prozesse wie Objektschichten — Zeiterfassung, Abgleich, Abrechnung bleiben identisch.
- **R-04** Gruppenvorlagen erlauben die Besetzung eingespielter Teams in einem Schritt.
- **R-05** Die Sedcard ist nur für Veranstaltungsgeschäft relevant und standardmäßig deaktiviert. Ihre Inhalte (Größe, Konfektion, Foto) sind freiwillige Angaben und erfordern die Einwilligung des Mitarbeiters.
- **R-06** Die Einsatzbewertung fließt in die Vorschlagsreihenfolge künftiger Besetzungen ein. Bewertungskriterien und Verwendung sind vor Aktivierung mit der Arbeitnehmervertretung abzustimmen (§ 87 BetrVG — Leistungsbewertung).
- **R-07** Revierplanung ist auftragsgetrieben: mehrere kurze Leistungen an verschiedenen Objekten in einem Zeitfenster, gefahren von einer Streife.
- **R-08** Bei Absage werden alle Schichten storniert und alle betroffenen Personen benachrichtigt.

## 5. Oberflächen
Veranstaltungsübersicht mit Baumdarstellung übergeordneter Klammern · Anlage mit Typvorlage · Bedarfsplanung je Funktion · Besetzung mit Vorschlagsliste nach Qualifikation, Verfügbarkeit und Bewertung · Gruppenvorlagen · Monatsansicht · Soll-/Ist-Vergleich mit Kalkulationsabweichung · Einsatzbewertung · Sedcard · Revierverwaltung mit Aufträgen und Tages-/Wochenplanung.

## 6. Akzeptanzkriterien
1. Übergeordnete Klammer ist nicht direkt planbar, gruppiert aber alle Einzeltage.
2. Bedarf von 20 Kräften erzeugt bei vollständiger Besetzung 20 Schichten.
3. Erzeugte Schichten durchlaufen Zeiterfassung und Abgleich wie Objektschichten.
4. Gruppenvorlage besetzt ein Team in einem Vorgang, überspringt nicht verfügbare Personen mit Bericht.
5. Absage storniert alle Schichten und benachrichtigt alle Betroffenen.
6. Soll-/Ist-Vergleich weist Abweichung gegenüber der Kalkulation korrekt aus.
7. Revierauftrag mit dreimal wöchentlicher Frequenz erzeugt die korrekte Anzahl Einzelleistungen.
8. Einsatzbewertung wirkt sich nachweisbar auf die Vorschlagsreihenfolge aus.

## 7. Hinweis zur Umsetzung
Vor Baubeginn den **Abrechnungspfad klären**: `umsatzbuchung` (M09) und `verrechnungssatz` (M04) sind objektbezogen, Veranstaltungsschichten haben aber kein Objekt. Entweder erhält jede Veranstaltung ein technisches Objekt, oder Schicht und Umsatzbuchung bekommen eine `veranstaltung_id` als alternativen Bezug — und der Satz aus `veranstaltung_bedarf.verrechnungssatz_cent` muss dem Abgleich (M09) zugänglich sein. Ohne diese Entscheidung greift R-03 („Abrechnung bleibt identisch") ins Leere.

# M09 — Abgleich (Soll/Ist-Freigabe und Buchung)

**Voraussetzung:** `00_KERNEL.md` + `SchichtLookupPort`, `ZeitdatenPort`, `EntgeltPort` (Stubs).
**Aufwand:** 45–65 PT · **Phase:** 3 · **Das fachliche Herzstück des Systems.**

## 1. Zweck und Abgrenzung
Der Abgleich ist der Moment, in dem aus Planung Geld wird: Ist-Zeiten werden geprüft, freigegeben und erzeugen in einem Vorgang **Lohnbuchungen und Umsatzbuchungen**.
**Dazu:** Abgleichsassistent, Einzel- und Massenabgleich, Abweichungsbehandlung, Bemerkungen, Buchungserzeugung, Aufhebung, vorläufiger Abgleich.
**Nicht dazu:** Lohnlauf (M10), Rechnungsstellung (M11), Erfassung (M08).

## 2. Entitäten
```sql
abgleich_lauf(id, tenant_id, bezeichnung, zeitraum_von, zeitraum_bis,
              typ, status, gestartet_am, gestartet_von,
              abgeschlossen_am, anzahl_schichten, anzahl_fehler)
              -- typ: VORLAEUFIG|ENDGUELTIG ; status: OFFEN|LAUFEND|FERTIG|FEHLER

abgleich_position(
  id, tenant_id, abgleich_lauf_id, schicht_id,
  soll_beginn_utc, soll_ende_utc, soll_pause_minuten, soll_minuten,
  ist_beginn_utc, ist_ende_utc, ist_pause_minuten, ist_minuten,
  abgeglichen_beginn_utc, abgeglichen_ende_utc,
  abgeglichen_pause_minuten, abgeglichen_minuten,
  abweichung_minuten, abweichung_grund,
  status, bemerkung, abgeglichen_am, abgeglichen_von)

lohnbuchung(                       -- Muster B: unveränderlich
  id, tenant_id, abgleich_position_id, mitarbeiter_id,
  abrechnungsmonat, lohnart_id, lohnart_nummer,
  minuten, satz_cent, betrag_cent, kostenstelle_id,
  in_lohnlauf_id NULL,             -- gesetzt durch markiere_verlohnt() (M10 R-02)
  storniert_durch_id, storno_grund, created_at, created_by)

umsatzbuchung(                     -- Muster B: unveränderlich
  id, tenant_id, abgleich_position_id, kunde_id, objekt_id,
  abrechnungsmonat, leistungsart, minuten,
  satz_cent, betrag_cent, kostentraeger_id,
  in_rechnung_id NULL, storniert_durch_id, created_at, created_by)

abgleich_sperre(id, tenant_id, zeitraum_von, zeitraum_bis, grund, gesetzt_von)
```

## 3. Bereitgestellter Port
```python
class BuchungsPortV1(Protocol):
    def lohnbuchungen(self, mitarbeiter_id: UUID, monat: str,
                      nur_unverlohnt: bool = False) -> list[LohnbuchungDTO]: ...
    def umsatzbuchungen(self, kunde_id: UUID, monat: str,
                        nur_unfakturiert: bool = False) -> list[UmsatzbuchungDTO]: ...
    def ist_abgeglichen(self, schicht_id: UUID) -> bool: ...
    def markiere_fakturiert(self, buchung_ids: list[UUID], rechnung_id: UUID) -> None: ...
    def markiere_verlohnt(self, buchung_ids: list[UUID], lohnlauf_id: UUID) -> None: ...
```

## 4. Fachregeln
- **R-01** Abgleichbar sind nur Schichten im Zustand `ERFASST` oder `GEPRUEFT` (entspricht dem M08-Erfassungsstatus `VOLLSTAENDIG` bzw. `GEPRUEFT`). Alles andere wird mit Begründung ausgesteuert und in einer Fehlerliste ausgewiesen.
- **R-02** Fehlt ein gültiger Tarif oder Verrechnungssatz zum Leistungszeitpunkt, ist die Position nicht abgleichbar. Fehlermeldung mit konkretem Hinweis, welcher Tarif fehlt oder abgelaufen ist — das ist erfahrungsgemäß die häufigste Supportanfrage.
- **R-03** Standardvorschlag ist die Ist-Zeit. Weicht der Bearbeiter davon ab, wird die Position optisch markiert und eine Begründung verlangt.
- **R-04** Mit dem Abgleich werden Lohn- und Umsatzbuchungen in **einer** Transaktion erzeugt. Teilweise gebuchte Zustände darf es nicht geben.
- **R-05** Buchungen sind unveränderlich. Eine Aufhebung des Abgleichs storniert sie durch Gegenbuchungen und setzt die Schicht auf `GEPRUEFT` zurück.
- **R-06** Aufhebung ist ausgeschlossen, sobald die Buchung in einem Lohnlauf (`in_lohnlauf_id`) oder einer Rechnung (`in_rechnung_id`) verwendet wurde. Dann ist nur noch eine Korrekturbuchung im Folgemonat möglich.
- **R-07** Der vorläufige Abgleich erzeugt keine Buchungen, sondern nur eine Vorschau. Er dient der Kontrolle vor dem Monatsabschluss.
- **R-08** Massenbearbeitung von Schicht- und Pausenzeiten über mehrere Positionen muss möglich sein — sonst ist der Monatsabschluss bei 2.000 Schichten nicht handhabbar.
- **R-09** Eine Abgleichsperre für einen abgeschlossenen Zeitraum verhindert jede weitere Buchung in diesem Zeitraum.
- **R-10** Zu jeder Position ist die vollständige Schichthistorie einsehbar: wer hat wann geplant, besetzt, umgeplant, erfasst, korrigiert.

## 5. Oberflächen
Abgleichsübersicht mit Filtern (Objekt, Kunde, Mitarbeiter, Zeitraum, Status) und ein-/ausblendbaren Spalten · Abgleichsassistent zur schrittweisen Abarbeitung · Positionsansicht mit Soll, Ist und Abgleich nebeneinander, Abweichungen farblich · Massenbearbeitungsleiste · Bemerkungsdialog · Fehlerliste nicht abgleichbarer Positionen mit Ursache · vorläufiger Abgleich als Vorschau · Aufhebungsdialog mit Wirkungsanzeige.

## 6. Berechtigungen
Abgleichen: ADMIN, PLANER. Aufheben: ADMIN. Vorläufigen Abgleich ansehen: zusätzlich CONTROLLER, EL/OL im eigenen Bereich. Sperre setzen: ADMIN.

## 7. Akzeptanzkriterien
1. Schicht ohne Ist-Zeiten wird nicht abgeglichen, sondern in der Fehlerliste mit Grund ausgewiesen.
2. Fehlender Tarif erzeugt `M09-E-002` mit Nennung des betroffenen Tarifs und Ablaufdatums.
3. Abgleich einer Schicht erzeugt Lohn- **und** Umsatzbuchungen; schlägt eine Seite fehl, wird nichts gebucht.
4. Abweichung von der Ist-Zeit ohne Begründung wird abgelehnt.
5. Aufhebung erzeugt exakt spiegelbildliche Gegenbuchungen; Summe über alle Buchungen ist null.
6. Aufhebung nach Verwendung in einer Rechnung wird mit `M09-E-021` abgelehnt.
7. Vorläufiger Abgleich erzeugt nachweislich keine Buchungen in der Datenbank.
8. Massenänderung der Pausenzeit über 50 Positionen wirkt vollständig oder gar nicht.
9. Abgleich von 2.000 Schichten bleibt unter 60 Sekunden.
10. Abgleichsperre verhindert Buchung im gesperrten Zeitraum (`M09-E-030`).
11. Schichthistorie zeigt alle Zustandsübergänge lückenlos mit Urheber.

## 8. Stub
Liefert Buchungen für die zwei abgeglichenen Seed-Wochen, damit M10 und M11 ohne M09 entwickelt werden können.

## 9. Hinweis
Wer dieses Modul baut, sollte den Kernel-Abschnitt 5 (Zustandsautomat) und Abschnitt 4 (Historisierung) auswendig kennen. Fast jeder schwerwiegende Fehler in Systemen dieser Art entsteht hier: doppelte Buchungen, veränderbare Vergangenheit, Teiltransaktionen.

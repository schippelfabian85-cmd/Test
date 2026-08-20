# M04 — Tarif und Entgeltstruktur

**Voraussetzung:** `00_KERNEL.md` + `MitarbeiterPortV1`, `ObjektPortV1` (Stubs genügen).
**Aufwand:** 45–60 PT · **Phase:** 1 · **Baubar ab:** parallel zu M01/M02

---

## 1. Zweck und Abgrenzung

Der Rechenkern für Geld. Beantwortet: *Was kostet diese Arbeitsminute — als Lohn und als Umsatz?*

**Gehört dazu:** Tarifwerk, Lohngruppen, Lohnarten, Zuschlagsmasken (prozentual und in Euro), Grundlohn, Zulagen, Mehrarbeitszuschläge, Verrechnungssätze gegenüber Kunden, Feiertagskalender.

**Gehört nicht dazu:** Der Lohnlauf selbst (M10), die Rechnung (M11), die Buchungserzeugung (M09). M04 **rechnet**, es **bucht** nicht.

Dieses Modul ist bewusst als reine Funktionsbibliothek geschnitten: gleiche Eingabe, gleiche Ausgabe, keine Seiteneffekte. Das macht es sehr gut testbar und ist der Grund, warum es früh gebaut werden sollte.

---

## 2. Entitäten

```sql
tarif(id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis, aktiv,
      code, bezeichnung, bundesland, quelle)             -- Muster A

lohngruppe(id, tarif_id, code, bezeichnung, stundenlohn_cent,
           funktion_codes[])

lohnart(id, tenant_id, nummer, bezeichnung, art, steuerpflichtig BOOL,
        sv_pflichtig BOOL, export_schluessel, aktiv)
        -- art: GRUNDLOHN|ZUSCHLAG|ZULAGE|AUSZAHLUNG|ABZUG|ZWK

zuschlagsmaske(                                          -- Muster A
  id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis, aktiv,
  tarif_id, bezeichnung, typ, prioritaet,
  kumulierung,             -- KUMULIERT | VERDRAENGT (R-02)
  wochentage[], von_uhrzeit, bis_uhrzeit,
  gilt_an_feiertagen BOOL, gilt_an_sonntagen BOOL,
  prozent NUMERIC, betrag_cent INT, lohnart_id,
  bemessung)   -- GRUNDLOHN|TARIFLOHN|FESTBETRAG

zulage(id, tenant_id, mitarbeiter_id, art, bezeichnung, betrag_cent,
       ist_pauschal BOOL, gueltig_ab, gueltig_bis, lohnart_id)

verrechnungssatz(                                        -- Muster A
  id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis, aktiv,
  kunde_id, objekt_id, funktion_code, satz_cent_pro_stunde,
  zuschlag_weiterberechnung)   -- KEINE|ANTEILIG|VOLL

feiertag(id, tenant_id, datum, bezeichnung, bundesland, ist_gesetzlich)
mindestlohn(id, gueltig_ab, betrag_cent, branche)
```

---

## 3. Bereitgestellter Port

```python
class EntgeltPortV1(Protocol):
    def berechne_lohn(self, req: LohnAnfrage) -> LohnErgebnis: ...
    def berechne_umsatz(self, req: UmsatzAnfrage) -> UmsatzErgebnis: ...
    def stundensatz(self, mitarbeiter_id: UUID, funktion_code: str,
                    stichtag: date) -> int: ...
    def ist_feiertag(self, datum: date, bundesland: str) -> bool: ...

@dataclass(frozen=True)
class LohnAnfrage:
    mitarbeiter_id: UUID; objekt_id: UUID; funktion_code: str
    beginn_utc: datetime; ende_utc: datetime; pause_minuten: int
    bundesland: str

@dataclass(frozen=True)
class LohnPosition:
    lohnart_nummer: str; bezeichnung: str
    minuten: int; satz_cent: int; betrag_cent: int
    zuschlagsmaske_id: UUID | None

@dataclass(frozen=True)
class LohnErgebnis:
    positionen: tuple[LohnPosition, ...]
    summe_cent: int
    bezahlte_minuten: int
    hinweise: tuple[str, ...]     # z.B. "Mindestlohn angehoben"
```

**Regel:** `berechne_lohn()` ist deterministisch und seiteneffektfrei. Zweimal derselbe Aufruf ergibt exakt dasselbe Ergebnis — auch in einem Jahr, weil über `gueltig_ab` immer die zum Leistungszeitpunkt gültige Version gezogen wird.

---

## 4. Konsumierte Ports

`MitarbeiterPortV1` (Funktionen, Vertragsgrenzen — die Lohngruppe ermittelt M04 selbst über `lohngruppe.funktion_codes`), `ObjektPortV1` (Objektzuschläge, Bundesland des Objekts).

---

## 5. Fachregeln

- **R-01** Eine Schicht wird für die Zuschlagsberechnung **minutengenau in Segmente zerlegt**. Eine Schicht von 22:00 bis 06:00 erzeugt Segmente für Nacht, ggf. Sonntagsbeginn ab 00:00, ggf. Feiertag. Das ist der Kern des Moduls.
- **R-02** Bei überlappenden Zuschlagsmasken entscheidet `prioritaet`. Ob Zuschläge kumulieren oder sich verdrängen, ist pro Maske konfigurierbar und muss im Ergebnis nachvollziehbar ausgewiesen sein.
- **R-03** Eine Zuschlagsmaske ist nach der ersten Verwendung in einer Abrechnung **unveränderlich**. Änderung erzeugt eine neue Version mit künftigem Gültigkeitsdatum.
- **R-04** Pausen sind unbezahlt, sofern nicht am Vertragstyp oder an der Masterschicht anders hinterlegt. Bezahlte Pausen gehen als eigene Position ins Ergebnis.
- **R-05** Gesetzliche Pausen werden nach Bruttoarbeitszeit vorgeschlagen (>6 h → 30 min, >9 h → 45 min); die tatsächliche Pause kommt aus der Schicht.
- **R-06** Unterschreitet der berechnete Stundenlohn den geltenden Mindestlohn, wird auf den Mindestlohn angehoben und ein Hinweis ausgegeben. Stillschweigende Korrektur ist unzulässig.
- **R-07** Feiertage sind bundeslandabhängig. Maßgeblich ist das Bundesland des **Objekts**, nicht des Mitarbeiters.
- **R-08** Umsatzberechnung ist strukturell unabhängig von der Lohnberechnung. Ob Zuschläge an den Kunden weitergegeben werden, steuert `zuschlag_weiterberechnung`.
- **R-09** Rundung erst am Ende, auf ganze Cent, kaufmännisch. Zwischenergebnisse bleiben ungerundet.
- **R-10** Die Segmentzerlegung arbeitet in lokaler Zeit (Europe/Berlin) auf Basis der UTC-Zeiten der Schicht. Bei Zeitumstellung zählt die reale Dauer: eine Schicht 22:00–06:00 hat in der Umstellungsnacht real 7 bzw. 9 Stunden. Bezahlte Minuten ergeben sich immer aus der UTC-Differenz, die Maskenzuordnung aus der lokalen Uhrzeit.

---

## 6. Oberflächen

Tarifübersicht mit Versionshistorie · Tarifassistent (Lohngruppen, Masken, Gültigkeit) · Zuschlagsmaskenliste mit Zeitstrahlvorschau · Lohnartenkatalog · Zulagenverwaltung je Person · Verrechnungssätze je Kunde/Objekt/Funktion · Feiertagskalender je Bundesland · **Rechner zur Probe**: Schicht eingeben, vollständige Aufschlüsselung sehen (unverzichtbar für Support und Test).

---

## 7. Berechtigungen

Tarife, Masken, Lohnarten, Verrechnungssätze: nur ADMIN. Zulagen je Person: ADMIN, PLANER. Probe-Rechner: zusätzlich CONTROLLER.

---

## 8. Akzeptanzkriterien

1. Schicht 22:00–06:00 an einem Samstag auf Sonntag erzeugt getrennte Positionen für Nacht und Sonntag mit korrekten Minutenzahlen.
2. Schicht komplett auf einem Feiertag in Bayern erzeugt Feiertagszuschlag, dieselbe Schicht in Sachsen-Anhalt nicht (Beispiel: Fronleichnam — beide Bundesländer sind im Stub enthalten).
3. Überlappende Masken kumulieren beziehungsweise verdrängen sich exakt nach Konfiguration; das Ergebnis weist die angewandte Maske aus.
4. Änderungsversuch einer verwendeten Maske wird mit `M04-E-011` abgelehnt.
5. Berechnung aller Seed-Schichten über 4 Wochen ergibt exakt den hinterlegten Referenzbetrag (Regressionstest; der eigentliche Lohnlauf liegt in M10).
6. Unterschreitung des Mindestlohns wird angehoben und im Hinweisfeld ausgewiesen.
7. `berechne_lohn()` für dieselbe Eingabe zweimal aufgerufen liefert bitgleiches Ergebnis.
8. Umsatzberechnung mit `zuschlag_weiterberechnung = KEINE` enthält keine Zuschlagspositionen.
9. Schicht über den Jahreswechsel mit Tarifwechsel zum 01.01. splittet korrekt auf beide Tarifversionen.
10. Schicht 22:00–06:00 über die Zeitumstellung im Oktober ergibt 9 real bezahlte Stunden (im März 7), die Nachtzuschlagsminuten entsprechend (R-10).

---

## 9. Bereitzustellender Stub

Ein Tarif „Wach- und Sicherheitsgewerbe Muster", Lohngruppen 1–3, Masken für Nacht (23–06, 25 %), Sonntag (50 %), Feiertag (100 %). Feiertage für Sachsen-Anhalt und Bayern.

---

## 10. Hinweis zur Umsetzung

Die Segmentzerlegung aus R-01 lohnt eine eigene, sehr gut getestete Funktion:

```python
def zerlege(beginn: datetime, ende: datetime,
            masken: list[Zuschlagsmaske],
            feiertage: set[date]) -> list[Segment]
```

Sie ist reine Rechenlogik ohne Datenbankzugriff. Mindestens 40 Testfälle vorsehen — hier entstehen erfahrungsgemäß die meisten Abrechnungsfehler des gesamten Systems.

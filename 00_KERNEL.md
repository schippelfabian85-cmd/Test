# M00 — KERNEL: Verbindlicher Rahmen für alle Module

> **Dieses Dokument ist das einzige, das jeder Modulentwickler lesen muss.**
> Jede Modulanleitung (M01–M20) ist danach ohne Kenntnis der anderen Module umsetzbar.
> Lesezeit ca. 20 Minuten. Version 1.0 — Änderungen nur über Änderungsantrag, da alle Module darauf bauen.

---

## 1. Grundprinzip der Modultrennung

**Regel K-1 (die wichtigste Regel des Projekts):**
Kein Modul greift jemals auf Tabellen eines anderen Moduls zu — weder lesend noch schreibend. Jeder modulübergreifende Zugriff läuft ausschließlich über
(a) einen dokumentierten **Port** (synchroner Aufruf) oder
(b) ein **Domain-Event** (asynchrone Benachrichtigung).

Daraus folgt der eigentliche Nutzen: Wer Modul M14 baut, muss M05 nicht kennen. Er muss nur den Port `SchichtLookupPort` kennen — und den findet er hier im Kernel, samt Stub.

**Regel K-2:** Zu jedem Port existiert ein **Stub** (Testdoppel mit festen Beispieldaten). Ein Modul muss allein mit Kernel + Stubs lauffähig, startbar und testbar sein. Wenn ein Modul nur zusammen mit einem anderen startet, ist K-1 verletzt.

**Regel K-3:** Ports werden versioniert (`v1`, `v2`). Eine bestehende Portversion wird nie geändert, nur ergänzt oder durch eine neue Version ersetzt.

---

## 2. Technischer Rahmen

| Thema | Festlegung |
|---|---|
| Sprache Backend | Python 3.12 (FastAPI) **oder** Frappe v15 — projektweit einheitlich, Entscheidung siehe README |
| Datenbank | PostgreSQL 16 |
| Mandantentrennung | `tenant_id` auf jeder Tabelle + Row Level Security |
| API | REST/JSON, Pfad `/api/v1/<modul>/<ressource>` |
| Events | Outbox-Tabelle + Worker; Zustellung mindestens einmal, Konsumenten müssen idempotent sein |
| Auth | OAuth2/JWT, Access Token 15 min, Refresh 30 Tage |
| Zeitzone | Speicherung immer UTC, Anzeige `Europe/Berlin` |
| Geldbeträge | Ganzzahl in Cent, nie Float |
| Zeitmengen | Ganzzahl in Minuten, nie Dezimalstunden |
| IDs | UUID v7 (technisch) + fachliche Nummer aus Nummernkreis (sichtbar) |
| Sprache im Code | Fachbegriffe deutsch (`schicht`, `abgleich`), Technik englisch (`created_at`) |

---

## 3. Basisdatenmodell (Kernel-eigene Tabellen)

Diese fünf Tabellen gehören dem Kernel. Module lesen sie, ändern sie aber nicht.

```sql
mandant(id, name, aktiv, uebergreifende_nummernkreise)
benutzer(id, tenant_id, personalnummer, email, passwort_hash, aktiv,
         letzter_login, lizenztyp)
rolle(id, code, name)                     -- siehe Abschnitt 6
benutzer_rolle(benutzer_id, rolle_id, tenant_id, gueltig_ab, gueltig_bis)
audit_log(id, tenant_id, benutzer_id, zeitpunkt, modul, entitaet,
          entitaet_id, aktion, alt_json, neu_json)
nummernkreis(id, tenant_id, code, praefix, naechster_wert, pro_mandant)
```

**Regel K-4:** Jede fachlich relevante Änderung schreibt einen `audit_log`-Eintrag. Das ist keine Kür — bei Abrechnungsstreitigkeiten und Betriebsprüfungen ist das die Beweisgrundlage.

---

## 4. Historisierung — zwei Muster, verbindlich

Der teuerste Fehler in diesem Projektfeld ist änderbare Vergangenheit. Deshalb gilt:

### Muster A — Versionierte Stammdaten
Für alles, worauf sich Abrechnung stützt: Tarife, Zuschlagsmasken, Masterschichten, Vertragstypen, Verrechnungssätze.

```sql
<entitaet>(id, tenant_id, stamm_id, version, gueltig_ab, gueltig_bis,
           aktiv, ... fachfelder ..., created_at, created_by)
```

- Eine Änderung erzeugt **immer** eine neue Zeile mit `version + 1`.
- Die alte Zeile bekommt `gueltig_bis` und `aktiv = false`. Sie wird nie überschrieben, nie gelöscht.
- `stamm_id` klammert alle Versionen einer Sache zusammen.
- Buchungen referenzieren immer die konkrete `id` (also die Version), niemals die `stamm_id`.

**Regel K-5:** Änderungen gelten grundsätzlich nur für die Zukunft. Rückwirkende Änderungen sind ein separater, protokollierter Vorgang mit eigener Berechtigung.

### Muster B — Unveränderliche Buchungen
Für alles, was Geld oder Zeit bucht: Lohnartenbuchungen, Umsatzbuchungen, Zeitkorrekturen.
Kein `UPDATE`, kein `DELETE`. Eine Korrektur ist eine Gegenbuchung plus Neubuchung mit Verweis auf das Original (`storniert_durch_id`, `storniert_grund`).

---

## 5. Der Schicht-Lebenszyklus (zentral für 12 der 20 Module)

Die Schicht ist das Herz des Systems. Ihr Zustandsautomat ist für alle Module verbindlich:

```
                    +-- AUSGEFALLEN
                    |
GEPLANT -> BESETZT -+-> ANGEMELDET -> ERFASST -> GEPRUEFT -> ABGEGLICHEN -> ABGERECHNET
   |          |                                      |            |
   +-> STORNIERT <------------------------------------+            |
                                                    (nur mit Sonderrecht zurück)
```

| Zustand | Bedeutung | Wer setzt ihn |
|---|---|---|
| `GEPLANT` | Bedarf existiert, keine Person zugeordnet | M05 |
| `BESETZT` | Person zugeordnet, Regelprüfung bestanden | M05 |
| `ANGEMELDET` | Dienstvoranmeldung erfolgt | M08 |
| `ERFASST` | Ist-Zeiten liegen vor (Kommen/Gehen) | M08 |
| `GEPRUEFT` | Auffälligkeiten geklärt (Prüf-Inbox leer) | M09 |
| `ABGEGLICHEN` | **Buchungszeitpunkt** — Lohn- und Umsatzbuchungen erzeugt | M09 |
| `ABGERECHNET` | In Lohnlauf und/oder Rechnung übernommen | M10 / M11 |
| `AUSGEFALLEN` | Nicht erbracht (Krankheit, No-Show) | M05 / M08 |
| `STORNIERT` | Bedarf entfallen | M05 |

**Regel K-6:** Ab `ABGEGLICHEN` ist die Schicht fachlich unveränderlich. Jede spätere Korrektur läuft über Storno und Neuanlage, nie über direkte Änderung.

**Regel K-7 (Nachtschichten):** Eine Schicht kann die Datumsgrenze überschreiten. Zuordnung zu einem Kalendertag erfolgt **immer über das Startdatum**. Zuschläge werden dagegen minutengenau nach tatsächlicher Uhrzeit berechnet, also über die Grenze hinweg gesplittet. Dieser Unterschied ist die häufigste Fehlerquelle im gesamten Projekt.

---

## 6. Rollen und Berechtigungen

| Code | Rolle | Kurzcharakter |
|---|---|---|
| `ADMIN` | Administrator | Vollzugriff inkl. Stammdaten und Einstellungen |
| `PLANER` | Disponent | Planung, Abgleich, Mitarbeiterakte lesend |
| `CONTROLLER` | Controlling | Auswertungen, keine Änderung produktiver Daten |
| `EL` | Einsatzleiter | Planung und Zeiterfassung für zugewiesene Gruppen |
| `OL` | Objektleiter | Wie EL, aber begrenzt auf zugewiesene Objekte |
| `MA` | Mitarbeiter | Eigene Daten, eigene Schichten, App |
| `SUB` | Subunternehmer | Eigene Firma, zugewiesene Schichten |
| `KUNDE` | Kundenzugang | Nur Lesesicht auf eigene Objekte |

**Regel K-8:** Berechtigungsprüfung erfolgt immer zweistufig — Rolle (*darf diese Funktion*) **und** Sichtbarkeitsbereich (*darf dieses Objekt / diesen Mitarbeiter*). Der Sichtbarkeitsbereich kommt aus `ZustaendigkeitPort`.

**Regel K-9:** Jeder Endpunkt deklariert seine Anforderung explizit, z. B. `@requires(rolle in [ADMIN, PLANER], scope="objekt")`. Es gibt keine implizit offenen Endpunkte.

---

## 7. Die Ports — das gemeinsame Vokabular

Jedes Modul stellt die hier genannten Ports bereit und darf ausschließlich diese von anderen nutzen. **Das ist der vollständige erlaubte Kontaktpunkt zwischen Modulen.**

| Port | Bereitgestellt von | Liefert |
|---|---|---|
| `MitarbeiterPort` | M01 | Stammdaten, Vertragstyp, Status, Beschäftigungsgrenzen |
| `ObjektPort` | M02 | Objekt, Kunde, Adresse, Koordinaten, Objektgruppe |
| `KundePort` | M02 | Kundenstammdaten, Zahlungsmodalitäten, Leitweg-ID |
| `QualifikationsPort` | M03 | Hat Person Qualifikation X zum Zeitpunkt T? Ablaufdaten |
| `EntgeltPort` | M04 | Berechne Entgelt für Person + Zeitraum + Funktion |
| `SchichtLookupPort` | M05 | Schicht(en) nach Objekt/Person/Zeitraum, Zustand |
| `RegelpruefPort` | M06 | Prüfe geplante Besetzung, liefert Verstoßliste |
| `VerfuegbarkeitsPort` | M07 | Ist Person zum Zeitpunkt T verfügbar? Grund bei Nein |
| `ZeitdatenPort` | M08 | Ist-Zeiten zu einer Schicht |
| `BuchungsPort` | M09 | Lohn-/Umsatzbuchungen zu Zeitraum |
| `ZustaendigkeitPort` | M00 | Welche Objekte/Personen darf Benutzer X sehen? |
| `BenachrichtigungsPort` | M16 | Sende Nachricht/Push/E-Mail an Empfänger |
| `DokumentPort` | M03 | Ablage und Abruf von Dateien |

### Portdefinition (Beispielform, für alle gleich)

```python
class SchichtLookupPortV1(Protocol):
    def schicht(self, schicht_id: UUID) -> SchichtDTO | None: ...
    def schichten_person(self, mitarbeiter_id: UUID,
                         von: date, bis: date) -> list[SchichtDTO]: ...
    def schichten_objekt(self, objekt_id: UUID,
                         von: date, bis: date) -> list[SchichtDTO]: ...

@dataclass(frozen=True)
class SchichtDTO:
    id: UUID
    tenant_id: UUID
    objekt_id: UUID
    mitarbeiter_id: UUID | None
    subunternehmer_id: UUID | None
    beginn_utc: datetime
    ende_utc: datetime
    pause_minuten: int
    funktion_code: str
    zustand: str            # siehe Abschnitt 5
    schichtkuerzel: str
```

**Regel K-10:** DTOs sind unveränderlich und enthalten **keine** Objektreferenzen auf andere Module — nur IDs und primitive Werte. Damit bleibt jedes Modul eigenständig deploybar.

---

## 8. Domain-Events

Namensschema: `<modul>.<entitaet>.<ereignis>.v<n>`

```json
{
  "event_id": "uuid",
  "event_type": "m09.schicht.abgeglichen.v1",
  "tenant_id": "uuid",
  "occurred_at": "2026-08-19T22:14:03Z",
  "actor_id": "uuid",
  "payload": { "schicht_id": "uuid", "ist_minuten": 480 }
}
```

Die projektweit relevanten Events:

| Event | Ausgelöst von | Typische Konsumenten |
|---|---|---|
| `m01.mitarbeiter.eingetreten.v1` | M01 | M03, M13, M16 |
| `m01.mitarbeiter.ausgeschieden.v1` | M01 | M03, M13, M00 (Lizenz frei) |
| `m03.qualifikation.laeuft_ab.v1` | M03 | M05, M16 |
| `m05.schicht.besetzt.v1` | M05 | M08, M13, M16 |
| `m08.zeiterfassung.gestartet.v1` | M08 | M14, M15 |
| `m08.zeiterfassung.fehlt.v1` | M08 | M09, M16 |
| `m09.schicht.abgeglichen.v1` | M09 | M10, M11, M17 |
| `m13.ressource.nicht_zurueck.v1` | M13 | M08, M09, M16 |

**Regel K-11:** Events transportieren nur IDs und wenige Kennzahlen. Wer Details braucht, holt sie über den Port. Damit bleibt der Event-Vertrag klein und stabil.

---

## 9. Fehler, Idempotenz, Nebenläufigkeit

- Fehlerformat einheitlich: `{"code": "M09-E-014", "message": "...", "details": {...}}`. Präfix ist die Modulnummer.
- Schreibende Endpunkte akzeptieren `Idempotency-Key` im Header; Wiederholung liefert dasselbe Ergebnis.
- Optimistisches Sperren über `version`-Spalte; Konflikt → HTTP 409.
- Fachliche Prüfungen werfen keine HTTP 500. 500 heißt immer Bug.

---

## 10. Definition of Done (gilt für jedes Modul)

Ein Modul gilt als fertig, wenn:

1. Alle Akzeptanzkriterien der Modulanleitung als automatisierte Tests vorliegen und grün sind.
2. Das Modul mit Kernel + Stubs **allein** startet (K-2).
3. Alle bereitgestellten Ports implementiert **und** als Stub für andere Module veröffentlicht sind.
4. Migrationen vorwärts und rückwärts lauffähig sind.
5. Der Seed-Datensatz (Abschnitt 11) einspielbar ist und die Oberfläche damit sinnvoll aussieht.
6. Rollenprüfung an jedem Endpunkt vorhanden ist (K-9).
7. Audit-Einträge für alle ändernden Vorgänge geschrieben werden (K-4).
8. Ein `README.md` im Modulordner die Abweichungen von dieser Anleitung dokumentiert.

---

## 11. Gemeinsamer Seed-Datensatz

Alle Module entwickeln gegen dieselben Testdaten. Datei `seed/basis.sql`, synthetisch, keine Echtdaten.

- 1 Mandant „Musterschutz GmbH", 1 Nebenmandant „Musterschutz Events"
- 3 Kunden, 5 Objekte (2 Pforte 24/7, 1 Streife, 1 Empfang Werktag, 1 Baustelle befristet)
- 12 Mitarbeiter: 4 Vollzeit, 4 Teilzeit, 2 geringfügig, 2 kurzfristig; davon 1 unter 18, 1 mit ablaufender Sachkunde
- 1 Subunternehmer mit 3 Mitarbeitern
- 1 Tarif mit Nacht-, Sonntags- und Feiertagszuschlag
- 4 Wochen Planung, davon 2 vollständig abgeglichen
- 8 Ressourcen (Funkgeräte, Schlüsselbunde, Warnwesten mit Nummern)

**Regel K-12:** Niemals Echtdaten in Entwicklung oder Test. Der Seed ist die einzige zulässige Datenquelle.

---

## 12. Reihenfolge und Abhängigkeiten

```
M00 Kernel
 ├─ M01 Personal ──┬─ M03 Qualifikationen
 │                 └─ M07 Verfügbarkeit
 ├─ M02 Kunde/Objekt
 ├─ M04 Entgeltstruktur
 └─ M06 Regel-Engine        (nur Kernel — vollständig isoliert baubar)
        │
        M05 Planung  ← M01, M02, M04, M06, M07
        │
        ├─ M08 Zeiterfassung ← M05
        ├─ M13 Ressourcen    ← M01, M05
        ├─ M14 WKS           ← M02, M05
        └─ M15 Wachbuch      ← M05
              │
              M09 Abgleich   ← M05, M08, M04
              │
              ├─ M10 Lohn    ← M09
              └─ M11 Faktura ← M09, M02
                    │
                    M12 Subunternehmer ← M05, M09, M11
                    M17 Controlling    ← alle (nur lesend über Ports)

Querschnitt, jederzeit baubar: M16 Kommunikation
Oberflächen: M18 Mitarbeiter-App, M19 Kundenportal
Phase 2: M20 Veranstaltungen
```

**Vollständig ohne Vorleistung baubar** (nur Kernel nötig): **M06** und **M16**. Gute Startpunkte, wenn parallel gearbeitet wird.

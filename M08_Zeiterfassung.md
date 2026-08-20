# M08 — Zeiterfassung

**Voraussetzung:** `00_KERNEL.md` + `SchichtLookupPort`, `ObjektPort`, `MitarbeiterPort` (Stubs).
**Aufwand:** 60–85 PT · **Phase:** 2

## 1. Zweck und Abgrenzung
Erfasst, was tatsächlich gearbeitet wurde, über drei gleichwertige Wege.
**Dazu:** App-Erfassung mit GPS, stationäres Terminal, Erfassung durch Einsatz-/Objektleiter im Tagesplan, Dienstvoranmeldung (DVA), Dienstantrittskontrolle (DAK), Pausenerfassung, manuelle Nachträge, Fehlermeldungen und Eskalation.
**Nicht dazu:** Freigabe und Buchung (M09), Planung (M05), Rundgänge (M14).

## 2. Entitäten
```sql
zeitdatensatz(
  id, tenant_id, schicht_id NULL,   -- NULL: Erfassung ohne Schicht (R-04)
  mitarbeiter_id, objekt_id,
  typ,                  -- KOMMEN|GEHEN|PAUSE_START|PAUSE_ENDE|DVA|DAK
  zeitpunkt_utc, erfassungsart,   -- APP|TERMINAL|TAGESPLAN|MANUELL|AUTOMATIK
  latitude, longitude, genauigkeit_meter, im_geofence BOOL,
  geraet_id, terminal_id, bedienernummer,
  erfasst_von, manuell_begruendung, bemerkung,
  storniert_durch_id, created_at)

zeiterfassung_schicht(          -- verdichtete Sicht je Schicht
  schicht_id, ist_beginn_utc, ist_ende_utc, ist_pause_minuten,
  ist_minuten_brutto, ist_minuten_netto,
  abweichung_beginn_minuten, abweichung_ende_minuten,
  status,               -- OFFEN|LAUFEND|VOLLSTAENDIG|UNVOLLSTAENDIG|GEPRUEFT
                        -- Erfassungsstatus, nicht der Schichtzustand des Kernels:
                        -- VOLLSTAENDIG/GEPRUEFT entsprechen dort ERFASST/GEPRUEFT (vgl. M09 R-01)
  auffaelligkeiten[])

terminal(id, tenant_id, seriennummer, bezeichnung, hersteller,
         objekt_id NULL, aktiv, letzter_kontakt, firmware,
         konfiguration_json)
terminal_logfile(id, terminal_id, zeitpunkt, ereignis, rohdaten)
geraet(id, tenant_id, imei, bezeichnung, mitarbeiter_id NULL,
       objekt_id NULL, freigegeben BOOL, freigegeben_am, wartungsmodus BOOL)
dva_einstellung(tenant_id, vorlauf_minuten, pflicht BOOL, erinnerung_minuten)
dak_lauf(id, schicht_id, faellig_um_utc, bestaetigt_um_utc, status, eskaliert_am)
pruef_inbox(id, tenant_id, schicht_id NULL,   -- NULL bei Erfassung ohne Schicht (R-04)
            zeitdatensatz_id NULL, art, festgestellt_am,
            zugewiesen_an, status, erledigt_am, erledigt_von, notiz)
```

## 3. Bereitgestellter Port
```python
class ZeitdatenPortV1(Protocol):
    def zeitdaten(self, schicht_id: UUID) -> ZeitdatenDTO | None: ...
    def offene_pruefungen(self, tenant_id: UUID, von: date, bis: date) -> list[PruefEintragDTO]: ...
    def erfasse(self, req: ErfassungsAnfrage) -> ErfassungsErgebnis: ...

@dataclass(frozen=True)
class ZeitdatenDTO:
    schicht_id: UUID
    ist_beginn_utc: datetime | None; ist_ende_utc: datetime | None
    ist_pause_minuten: int; ist_minuten_netto: int
    abweichung_beginn_minuten: int; abweichung_ende_minuten: int
    status: str; auffaelligkeiten: tuple[str, ...]
```

## 4. Ausgelöste Events
`m08.zeiterfassung.fehlt.v1` (nach Karenz, R-05 — Versand über M16; Name gemäß Kernel §8) · `m08.zeiterfassung.gestartet.v1` (Kernel §8) · `m08.schicht.automatisch_geschlossen.v1` (R-06) · `m08.dak.eskaliert.v1` (R-09) · `m08.pruef_inbox.eintrag_erstellt.v1`

## 5. Fachregeln
- **R-01** Die drei Erfassungswege sind fachlich gleichwertig und erzeugen identische Datensätze. Unterschiedlich ist nur die Herkunft.
- **R-02** GPS wird **ausschließlich im Moment des Stempelns** erfasst, nie kontinuierlich. Das ist zwingend — dauerhafte Ortung ist arbeitsrechtlich und datenschutzrechtlich nicht haltbar.
- **R-03** Stempeln außerhalb des Geofence wird erfasst und markiert, aber nicht verhindert. Fehlender Empfang darf niemanden am Dienstantritt hindern.
- **R-04** Kommen ohne zugehörige Schicht ist möglich (unplanmäßiger Einsatz) und erzeugt einen Prüf-Inbox-Eintrag.
- **R-05** Fehlt zu Schichtbeginn plus Karenz eine Erfassung, entsteht eine Warnmeldung an Disposition und Einsatzleiter (Event, Versand über M16).
- **R-06** Fehlt am Schichtende die Abmeldung, wird nach konfigurierbarer Frist automatisch mit Sollzeit geschlossen und als `UNVOLLSTAENDIG` markiert — niemals stillschweigend als korrekt gewertet.
- **R-07** Manuelle Erfassung und Korrektur erfordern immer eine Begründung und werden mit Urheber protokolliert.
- **R-08** Die DVA bestätigt der Mitarbeiter im konfigurierten Vorlauf vor Dienstbeginn. Fehlende DVA erzeugt eine Warnung, kein Blockieren.
- **R-09** Die DAK verlangt in festem Intervall eine Rückmeldung. Ausbleiben eskaliert nach definierter Kette (Mitarbeiter → Objektleiter → Disposition).
- **R-10** Ein Zeitdatensatz wird nie geändert oder gelöscht, nur durch einen Storno-Datensatz ersetzt (Kernel Muster B).
- **R-11** Geräte müssen vor Nutzung freigegeben werden. Nach Gerätewechsel oder Neuinstallation ist eine erneute Freigabe erforderlich.

## 6. Oberflächen
Tagesplan als Leitstand mit Livestatus und Farbcodierung · Prüf-Inbox als zentrale Arbeitsliste · Terminalübersicht mit letztem Kontakt · Terminalkonfiguration und Logfiles · Geräteverwaltung mit Freigabe, Objektzuweisung und Wartungsmodus · Zeiterfassungseinstellungen (Karenzen, Fristen, DVA-Vorlauf) · manuelle Nachtragsmaske · Zeitdatensatz-Auswertung mit und ohne Pausen.

## 7. Berechtigungen
Eigenes Stempeln: MA. Für andere erfassen: EL, OL im eigenen Bereich. Korrigieren: ADMIN, PLANER. Geräte und Terminals: ADMIN. Prüf-Inbox bearbeiten: ADMIN, PLANER, EL, OL.

## 8. Akzeptanzkriterien
1. Stempeln über alle drei Wege erzeugt strukturell identische Datensätze.
2. Stempeln 300 m vom Objekt entfernt wird angenommen und als außerhalb Geofence markiert.
3. Fehlende Anmeldung erzeugt nach Karenz genau eine Warnmeldung, nicht wiederholt.
4. Fehlende Abmeldung schließt nach Frist automatisch und markiert `UNVOLLSTAENDIG`.
5. Manuelle Korrektur ohne Begründung wird abgelehnt (`M08-E-006`).
6. Korrektur erzeugt Storno plus Neuerfassung, der Originaldatensatz bleibt lesbar.
7. Nachtschicht über Mitternacht wird korrekt als eine zusammenhängende Zeit berechnet.
8. DAK ohne Rückmeldung eskaliert nach Intervall an die nächste Stufe.
9. Nicht freigegebenes Gerät wird abgewiesen (`M08-E-011`).
10. Prüf-Inbox zeigt alle Auffälligkeiten eines Tages vollständig und ist abarbeitbar.
11. GPS wird nachweislich nur bei Stempelvorgängen gespeichert (Test über Datenbankinhalt).

## 9. Stub
Liefert für die Seed-Schichten Ist-Zeiten: 80 % exakt, 10 % mit Abweichung, 5 % fehlende Abmeldung, 5 % ohne Erfassung.

## 10. Hinweis
Die Prüf-Inbox ist die Sicht, die über den Alltagsnutzen entscheidet. Alles, was nicht glattläuft — fehlende Stempel, Geofence-Abweichung, offene Rückgaben aus M13, unbestätigte DVA — muss dort und nur dort auflaufen. Wenn Auffälligkeiten über mehrere Sichten verstreut sind, werden sie übersehen.

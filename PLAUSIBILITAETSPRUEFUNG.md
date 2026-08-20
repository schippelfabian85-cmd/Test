# Plausibilitätsprüfung der Modulspezifikationen

**Geprüfte Module:** M01, M02, M03, M04, M06, M07, M08, M09, M10, M11, M12, M19, M20
**Stand:** 20.08.2026

---

## 1. Prüfumfang und Vorgehen

Geprüft wurden die 13 vorgelegten Modulspezifikationen auf:

- **fachliche Korrektheit** (deutsches Arbeits-, Sozial- und Steuerrecht, Branchenpraxis Sicherheitsgewerbe),
- **Umsetzbarkeit** (hat jede Fachregel einen Datenweg — Spalte, Portfeld, Kontextfeld?),
- **modulübergreifende Konsistenz** (Ports, DTOs, Zustände, Events, Namenskonventionen, Stub-Daten, Fehlercodes),
- **Grenzfälle in den Akzeptanzkriterien**.

**Nicht vorgelegt** und daher nur als Referenz behandelt: `00_KERNEL.md` sowie M05 (Planung), M13, M14, M16. Querverweise auf diese Dokumente wurden auf Plausibilität, nicht auf Übereinstimmung geprüft — siehe Abschnitt 6. M07 war doppelt hochgeladen (byte-identisch); es wurde eine Fassung übernommen.

**Gesamturteil:** Die Spezifikationen sind ungewöhnlich konsistent — durchgängige Konventionen (Muster A/B, Minuten- und Cent-Beträge, UTC-Zeitstempel, `MXX-E-NNN`-Fehlercodes, feste Stub-IDs, aufeinander abgestimmte Seed-Daten) und ein sauberer Port-Schnitt. Die gefundenen Mängel sind punktuell, aber teils gravierend; alle korrigierbaren wurden direkt in den Dateien behoben und sind unten dokumentiert.

---

## 2. Korrigierte fachliche Fehler

| Nr. | Modul | Befund | Korrektur |
|---|---|---|---|
| F-01 | M01 R-05 | Anonymisierung setzt die Personalnummer auf `0` — kollidiert mit `UNIQUE(tenant_id)` aus R-01 spätestens bei der **zweiten** anonymisierten Person. | Eindeutiger Platzhalter `ANON-<lfd. Nr.>`; Eindeutigkeit bleibt gewahrt. |
| F-02 | M01 R-04 / AC 5 / Event | Lizenzfreigabe „mit gesetztem Austrittsdatum": Wer zum 31.12. gekündigt ist, verlöre die Lizenz schon beim Erfassen im September. Widerspruch zu M12 R-09 („taggenau"). | Freigabe **mit Erreichen** des Austrittsdatums (rückwirkendes Setzen: sofort); Event-Auslöser entsprechend präzisiert. |
| F-03 | M01 R-07 | Satz war in sich unverständlich („ohne Eintrittsdatum in der Zukunft") und ließ `RUHEND` offen. | `ist_aktiv(stichtag)`-Semantik vollständig definiert: nur Status `AKTIV` innerhalb Eintritt–Austritt. |
| F-04 | M07 R-05 | „Folgebescheinigungen verlängern nur bei gleicher Diagnose nicht" — doppelt verneint **und** im Widerspruch zu R-10 („Diagnose wird nie erfasst"): eine Diagnose-Gleichheit kann das System nie feststellen. | Neu gefasst nach § 3 EFZG: maßgeblich ist ausschließlich das Kennzeichen Erst-/Folgebescheinigung (`folgebescheinigung`), das die AU selbst trägt. |
| F-05 | M06 `AZ_PAUSE` | „30 min **ab** 6 h" widerspricht § 4 ArbZG („bei **mehr als** sechs Stunden") und M04 R-05 („>6 h"). Exakt 6 h Arbeit erfordern keine Pause. | „30 min bei mehr als 6 h, 45 min bei mehr als 9 h". |
| F-06 | M06 `AZ_RUHEZEIT_VERKUERZT` | Rechtsgrundlage § 5 Abs. 2 ArbZG erfasst das Bewachungsgewerbe **nicht** (Katalog: Krankenhäuser, Gaststätten, Verkehr, Rundfunk, Landwirtschaft). Verkürzte Ruhezeit ist nur über tarifliche Öffnung nach § 7 ArbZG zulässig. | Grundlage auf „§ 7 ArbZG i. V. m. TV" geändert; Hinweis ergänzt: Regel wird deaktiviert ausgeliefert, Aktivierung nur bei nachgewiesener Tarifbindung. |
| F-07 | M06 AC 2 | Grenzfall falsch gesetzt: getestet wurde 19:59/20:01, der eigentliche Grenzwert 20:00 (§ 14 JArbSchG erlaubt Beschäftigung **bis** 20 Uhr) blieb ungetestet. | AC testet jetzt exakt 20:00 (zulässig) gegen 20:01 (blockiert). Zudem `JU_TAG_MAX`-Grundlage auf § 8 JArbSchG präzisiert. |
| F-08 | M11 R-06 / AC 6 | Leitweg-ID und D.U.N.S. als generelle ZUGFeRD-Pflicht ist falsch: Die Leitweg-ID ist nur bei Rechnungen an **öffentliche Auftraggeber** (XRechnung/B2G) Pflicht; im B2B genügt EN-16931-Konformität, D.U.N.S. braucht nur, wer über entsprechende Kanäle (z. B. Peppol) versendet. Die alte Regel hätte jede B2B-E-Rechnung blockiert. | Regel nach B2G/B2B differenziert; AC entsprechend angepasst. |
| F-09 | M11 Mahnstufe 5 | „Mahnbescheid" ist kein versendbares Mahnschreiben, sondern ein gerichtliches Verfahren, das beim Mahngericht beantragt wird. | Stufe 5 = „Übergabe gerichtliches Mahnverfahren", mit klarstellendem Kommentar. |
| F-10 | M04 AC 2 | Referenztest nutzte Berlin — der Stub (Abschnitt 9) enthält aber nur Feiertage für Sachsen-Anhalt und Bayern; der Test wäre gegen den Stub nicht ausführbar gewesen. | Vergleichsland auf Sachsen-Anhalt geändert (Fronleichnam dort ebenfalls kein Feiertag — Beispiel bleibt gültig). |

---

## 3. Korrigierte Lücken: Regeln ohne Datenweg

Regeln, die so wie spezifiziert nicht implementierbar waren, weil das nötige Feld, der Port oder die Entität fehlte:

| Nr. | Modul | Befund | Korrektur |
|---|---|---|---|
| D-01 | M04 R-07 ↔ M02 | Feiertagszuschlag hängt am „Bundesland des **Objekts**" — aber weder `objekt` noch `ObjektDTO` führten ein Bundesland. | `objekt.bundesland` und `ObjektDTO.bundesland` ergänzt (M02). |
| D-02 | M06 `GF_VERDIENST` | Ohne den erwarteten Verdienst der **geplanten** Schicht kann die Engine nur feststellen, dass die Geringfügigkeitsgrenze bereits gerissen ist — nicht, dass die neue Schicht sie reißen würde. | `PruefKontext.verdienst_geplante_schicht_cent` ergänzt (liefert der Aufrufer über `EntgeltPort`; M06 bleibt portfrei). Neues AC 10 testet die Vorausschau. |
| D-03 | M06 `AZ_WOCHE_MAX` | 48-h-Durchschnitt über 24 Wochen ist aus `bestehende_schichten` (±14 Tage) nicht berechenbar. | `PruefKontext.minuten_24_wochen_bisher` ergänzt. |
| D-04 | M06 `VF_BEREITSCHAFT` | Die Regel braucht das Signal „außerhalb der Leistungsbereitschaft", das M07 im DTO liefert — im `PruefKontext` fehlte es. | `PruefKontext.ausserhalb_bereitschaft` ergänzt. |
| D-05 | M04 R-02 | „Kumulieren oder verdrängen ist **pro Maske** konfigurierbar" — die Entität `zuschlagsmaske` hatte kein solches Feld. | Spalte `kumulierung` (KUMULIERT \| VERDRAENGT) ergänzt. |
| D-06 | M04 R-04 / M10 R-03 ↔ M01 | Bezahlte Pausen „am Vertragstyp hinterlegt" und die ZWK-Lohnart-Zuordnung existierten in `vertragstyp` nicht; das `VertragsgrenzenDTO` transportierte beides nicht. | `vertragstyp.pausen_bezahlt`, `vertragstyp.zwk_lohnart_id` und DTO-Felder `pausen_bezahlt`, `zeitwertkonto_aktiv` ergänzt (M01); M10 R-03 verweist jetzt darauf. |
| D-07 | M09/M10 | M10 R-01 sprach von Buchungen „im Zustand `ABGEGLICHEN`" — Buchungen haben keinen Zustand. R-02 („Buchungen gesperrt") und M09 R-06 (Aufhebung nach Lohnlauf ausgeschlossen) hatten **keinen Mechanismus**: kein Marker auf `lohnbuchung`, kein Port-Aufruf — anders als auf der Umsatzseite (`in_rechnung_id` + `markiere_fakturiert()`). | Symmetrie hergestellt: `lohnbuchung.in_lohnlauf_id`, `markiere_verlohnt()` und Parameter `nur_unverlohnt` im `BuchungsPortV1` (M09); M10 R-01/R-02 neu gefasst. |
| D-08 | M10 R-06 | „Jede Verdichtung bis zur einzelnen Schicht rückverfolgbar" — `lohnlauf_position` hatte keinerlei Referenz auf die zugrunde liegenden Buchungen (die Umsatzseite hat `umsatzbuchung_ids[]`). | `lohnlauf_position.lohnbuchung_ids[]` ergänzt; AC 6 ist damit erfüllbar. |
| D-09 | M11 R-05 ↔ M02 | Verdichtungsgrad „je Kunde konfigurierbar" — ohne Speicherort am Kunden. | `kunde.rechnung_verdichtung` (JE_OBJEKT \| JE_LEISTUNGSART \| JE_MONAT \| JE_SCHICHT) ergänzt (M02). |
| D-10 | M02 R-08 / M12 R-08 ↔ M03 | Beide Module müssen Wiedervorlagen anlegen; die Entität liegt in M03, aber kein Port bot das Anlegen an. | `WiedervorlagePortV1` (anlegen/erledigen) in M03 ergänzt; M02 §4, M02 R-08, M12-Header und M12 R-08 verweisen darauf. |
| D-11 | Diverse ↔ M02 | `kostentraeger_id` wird von `objekt` (M02), `umsatzbuchung` (M09) und `rechnung_position` (M11) referenziert — eine Entität `kostentraeger` war nirgends definiert. | `kostentraeger(id, tenant_id, nummer, bezeichnung, aktiv)` in M02 ergänzt. (Alternativ in den Kernel ziehen, siehe E-06.) |
| D-12 | M12 R-03 | „Dieselben Qualifikationsanforderungen wie eigenes Personal" — das Schema konnte aber nur die Sachkunde abbilden. Ein Objekt, das z. B. Waffensachkunde fordert, wäre für Submitarbeiter unprüfbar gewesen. Zugleich erklärte nichts, wozu M12 den `QualifikationsPort` konsumiert. | Generische Tabelle `submitarbeiter_qualifikation` (Codes aus dem M03-Katalog) ersetzt die beiden Sachkunde-Spalten. |
| D-13 | M03 ↔ M12 | `dienstausweis` kannte nur `mitarbeiter_id` — M12 verlangt aber „Dienstausweise für Fremdpersonal" inkl. Druck im Portal. | Generalisiert auf `inhaber_typ` (MITARBEITER \| SUBMITARBEITER) + `inhaber_id`. |
| D-14 | M08 R-04 | „Kommen ohne zugehörige Schicht ist möglich" — `zeitdatensatz.schicht_id` und `pruef_inbox.schicht_id` waren nicht als nullable markiert (andere Spalten im selben Dokument sind explizit `NULL`). | Beide als `NULL` markiert; `pruef_inbox.zeitdatensatz_id` ergänzt, damit der Inbox-Eintrag auf die schichtlose Erfassung zeigen kann. |
| D-15 | M07 R-01/AC 2 | Beantragter Urlaub soll „nur eine Warnung" erzeugen — das `VerfuegbarkeitDTO` hatte keinen Kanal dafür, und AC 2 war sprachlich unverständlich. | DTO-Feld `warnungen` (z. B. `URLAUB_BEANTRAGT`) ergänzt; AC 2 neu formuliert. |
| D-16 | M07/M06 | Verfügbarkeitsgrund `"SPERRE"` (M07-DTO, M06 `VF_ABWESEND`) hatte keine tragende Entität — `abwesenheit.art` kannte keine Sperre, `urlaubssperre` betrifft nur Urlaubs**anträge**. | `abwesenheit.art` um `SPERRE` (persönliche Einsatzsperre, z. B. entzogene Zuverlässigkeit) ergänzt. |
| D-17 | M19 | Das Portal zeigt Nachweise, Rechnungen und Wachbuch — der Header nannte aber nur `SchichtLookupPort`, `ObjektPort`, `KundePort`. M11 §7 bestätigt sogar ausdrücklich, dass M19 lesend zugreift. | Voraussetzungen um Lesezugriff auf M10, M11 und M14 ergänzt. |
| D-18 | M20 | Die Besetzungs-Vorschlagsliste sortiert „nach Qualifikation, Verfügbarkeit und Bewertung" — M03 und M07 fehlten in den Voraussetzungen. | Header um M03 und M07 ergänzt. |
| D-19 | M20 | Abrechnungspfad offen: `umsatzbuchung` (M09) und `verrechnungssatz` (M04) sind objektbezogen, Veranstaltungsschichten haben kein Objekt; `veranstaltung_bedarf.verrechnungssatz_cent` erreicht M09 nicht. R-03 („Abrechnung bleibt identisch") griffe ins Leere. | Neuer Abschnitt „Hinweis zur Umsetzung" mit Entscheidungsbedarf (technisches Objekt je Veranstaltung **oder** `veranstaltung_id` an Schicht/Umsatzbuchung). |

---

## 4. Korrigierte Konsistenz- und Strukturfragen

| Nr. | Modul | Befund | Korrektur |
|---|---|---|---|
| K-01 | M02, M12 | `objekt_zuschlag` und `sub_verrechnungssatz` waren als „Muster A" ausgewiesen, hatten aber weder `stamm_id` noch `version` noch `aktiv` — im Widerspruch zu allen übrigen Muster-A-Tabellen (tarif, zuschlagsmaske, verrechnungssatz, vertragstyp). M02 AC 5 (Versionierung) wäre nicht erfüllbar gewesen. | Beide Tabellen auf das volle Muster-A-Schema gebracht. |
| K-02 | M06 | `PruefKontext.ist_minderjaehrig` doppelte `grenzen.ist_minderjaehrig` (VertragsgrenzenDTO) — zwei Quellen für dieselbe Wahrheit. | Skalar entfernt, Kommentar am `grenzen`-Feld. |
| K-03 | M09 R-01 ↔ M08 | M09 prüft Kernel-Zustände `ERFASST`/`GEPRUEFT`, M08 führt Erfassungsstatus `VOLLSTAENDIG`/`GEPRUEFT` — gleiche Wortwahl („GEPRUEFT") für zwei verschiedene Zustandsmaschinen. | Mapping in beiden Dokumenten klargestellt (`VOLLSTAENDIG` ⇒ `ERFASST`). Endgültige Bestätigung gegen den Kernel-Zustandsautomaten steht aus (E-01). |
| K-04 | M02 §4 | R-02 verlangt den `SchichtLookupPort`, der Abschnitt „Konsumierte Ports" nannte nur den `DokumentPort`. | §4 vervollständigt (DokumentPort, WiedervorlagePort, SchichtLookupPort mit Stub-Hinweis). |
| K-05 | M07, M08 | Beide Module lösen laut Fachregeln Events aus (M07 R-04, M08 R-05), hatten aber — anders als M01–M03 — keinen Events-Abschnitt; M07 AC 4 nannte ein unnamenskonformes Event „ausfall" und ließ offen, ob je Schicht oder je Krankmeldung gefeuert wird. | Events-Abschnitte mit `mXX.*.v1`-Namen ergänzt, Abschnitte neu nummeriert; AC 4 präzisiert (ein Event je Krankmeldung, M05 setzt die Schichten um). |
| K-06 | M04 §4 | „MitarbeiterPortV1 (Lohngruppe, …)" — der Port liefert gar keine Lohngruppe; die ermittelt M04 selbst über `lohngruppe.funktion_codes`. | Formulierung korrigiert. |
| K-07 | M04 AC 5 | „Lohnlauf" ist der M10-Begriff; M04 rechnet nur. | Umformuliert auf „Berechnung aller Seed-Schichten". |
| K-08 | M04 | Zeitzonen/Sommerzeit waren ungeregelt: Masken gelten in lokaler Uhrzeit, Schichten in UTC — die Umstellungsnächte (23 h/25 h) sind der klassische Abrechnungsfehler. | Neue R-10 (Zerlegung in Europe/Berlin, Bezahlung nach realer UTC-Dauer) + neues AC 10. |
| K-09 | M09 | `umsatzbuchung` hatte kein `created_by`, `lohnbuchung` schon — Muster B verlangt den Urheber. | `created_by` ergänzt. |
| K-10 | M10 | Vorschüsse hatten keine Berechtigungszeile. | „Vorschüsse erfassen: ADMIN" ergänzt. |
| K-11 | M20 | `revier_auftrag.frequenz` ohne definiertes Format — AC 7 („dreimal wöchentlich") wäre interpretationsabhängig. | Kommentar: Format verbindlich festlegen (Wochentagsliste oder Anzahl je Woche). |
| K-12 | M20 | Sedcard (Körpermaße, Foto) und Einsatzbewertung ohne Datenschutz-/Mitbestimmungshinweis — im Kontrast zur sonst hohen Sensibilität der Spezifikationen (vgl. M07 R-10, M08 R-02, M19 R-03). | R-05: freiwillig, nur mit Einwilligung. R-06: Kriterien mitbestimmungspflichtig (§ 87 BetrVG). |

---

## 5. Hinweise ohne Textänderung (zur Kenntnis / Entscheidung)

- **H-01 Zeitwertkonto (M01/M10):** Echte Wertguthaben nach § 7b SGB IV erfordern eine Wertguthabenvereinbarung und **Insolvenzsicherung** (§ 8a SGB IV). Sollte das ZWK mehr als ein Gleitzeitkonto sein, gehört das ins Fachkonzept von M10.
- **H-02 Geringfügigkeitsgrenze (M01/M06):** Die Grenze ist dynamisch (an den Mindestlohn gekoppelt und jährlich neu). Die Abbildung über Vertragstyp-Versionen (Muster A) trägt das — es braucht aber einen **jährlichen Pflegeprozess**, sonst prüft `GF_VERDIENST` gegen veraltete Werte. Gleiches gilt für die `mindestlohn`-Tabelle in M04.
- **H-03 Bewacherregister (M03):** Das Register ist seit 2023 ein elektronisches Portal. Der CSV-Export als Aufbereitungshilfe ist als Übergang in Ordnung; die Schnittstellenanforderungen des Registers sollten vor dem Bau von R-09 geprüft werden.
- **H-04 „Genau einmal"-Events (M01 AC 9):** Exactly-once-Zustellung setzt praktisch ein Outbox-Muster voraus. Ob der Kernel das vorgibt, ist aus den vorgelegten Dokumenten nicht ersichtlich — vor Phase 1 klären, sonst testet AC 9 etwas Unerfüllbares.
- **H-05 `mitarbeiter.vertragstyp_id` (M01):** Bei Muster A ist festzulegen, ob der FK auf die **Version** oder den **Stamm** zeigt und wie `vertragsgrenzen(stichtag)` auflöst (Stamm + Stichtag → Version wäre robust gegen spätere Versionen, z. B. neue Geringfügigkeitsgrenzen). Vermutlich regelt der Kernel das; explizit machen.
- **H-06 Kostenstellen/Kostenträger:** `kostenstelle` liegt in M01, `kostentraeger` jetzt in M02 — beide sind aber unternehmensweite Stammdaten, die von M09/M10/M11 referenziert werden. Erwägen, beide in den Kernel zu ziehen.
- **H-07 M09-Stub ↔ M10 AC 1:** Der M09-Stub liefert zwei abgeglichene Wochen, M10 AC 1 rechnet über den „Seed-Monat". Das passt, solange die Referenzsumme auf genau diese zwei Wochen definiert ist — bei der Seed-Erstellung festhalten.
- **H-08 Mögliche Katalog-Ergänzungen M06:** § 6 ArbZG (Ausgleich für Nachtarbeitnehmer) und eine Warnregel für die 15 freien Sonntage (§ 11 Abs. 1 ArbZG — gezählt wird in M07 R-09, gewarnt bislang nirgends). Kein Mangel, aber naheliegende nächste Regeln.
- **H-09 Arbeitszeitrecht bei Submitarbeitern (M12):** Die M06-Prüfungen laufen für eigenes Personal. Für Fremdpersonal liegt die ArbZG-Verantwortung beim Subunternehmer — bewusste Entscheidung, sollte aber dokumentiert sein, damit niemand stillschweigend Vollprüfung erwartet.

---

## 6. Offene Punkte — Stand nach Eintreffen von 00_KERNEL, M05, M13

Am 20.08.2026 wurden `00_KERNEL.md`, `M05_Planung.md` und `M13_Ressourcen_Inventar.md` nachgereicht. Verifikationsergebnis der offenen Punkte:

1. **Kernel-Zustandsautomat — bestätigt.** `ERFASST`, `GEPRUEFT`, `ABGEGLICHEN`, `AUSGEFALLEN` existieren wie angenommen; das K-03-Mapping (M08 `VOLLSTAENDIG` ⇒ Kernel `ERFASST`) passt. Klarstellung aus Kernel §5: den Schichtzustand `GEPRUEFT` setzt **M09**, M08s gleichnamiger Erfassungsstatus bleibt davon getrennt.
2. **`SchichtDTO` — bestätigt** (Kernel §7): enthält Beginn/Ende (UTC) und Pausenminuten plus `funktion_code`, `zustand`, `schichtkuerzel`. Das provisorische Kernel-Paket wurde auf die vollständige Form gebracht.
3. **M05 — bestätigt:** `SchichtLookupPortV1` mit `offene_schichten()` und `setze_zustand()`; Krankmeldungs-Umsetzung (M07 → `AUSGEFALLEN`) liegt wie angenommen bei M05. **D-19 bestätigt sich:** `schicht.objekt_id` ist Pflicht — der Veranstaltungs-Abrechnungspfad (M20) braucht die dokumentierte Entscheidung.
4. **Lizenzzähler/`ZustaendigkeitPort` — bestätigt:** `benutzer.lizenztyp` existiert; der Port gehört zu M00. Der Kernel definiert allerdings keine Tabelle für Zuständigkeiten — die Umsetzung ergänzt eine (`zustaendigkeit`), dokumentiert im Kernel-README.
5. **H-04 (Events „genau einmal") — geklärt:** Kernel §2/§8 definiert Outbox mit At-least-once und idempotenten Konsumenten. „Genau einmal veröffentlicht" (M01 AC 9) heißt: genau ein Outbox-Eintrag.
6. **H-05 (`vertragstyp_id`) — geklärt:** Muster A schreibt Referenz auf die konkrete **Version** vor („niemals `stamm_id`", Kernel §4); die Stichtagsauflösung läuft über `mitarbeiter_historie`.
7. **H-06 (Kostenstellen/-träger) — entschieden:** Der Kernel führt beide nicht — sie bleiben wie korrigiert in M01/M02.
8. **Weiter offen:** M14/M16 (Wachbuch-Lesezugriff für M19, Benachrichtigungsversand), M15, M17, M18 liegen nicht vor.

### Nachtrag: neue Befunde aus den nachgereichten Dokumenten

| Nr. | Fundstelle | Befund | Maßnahme |
|---|---|---|---|
| N-01 | Kernel §7 ↔ M13/M08 | Die Porttabelle des Kernels führt den `RessourcenPort` (M13) nicht, obwohl M08 laut M13 R-04 `darf_ausstempeln()` vor jeder Abmeldung aufrufen muss; auch die M08-Voraussetzungen nennen ihn nicht. | **Änderungsantrag Kernel** (§7 ergänzen) + M08-Header; Kernel selbst wurde vereinbarungsgemäß nicht angefasst („Änderungen nur über Änderungsantrag"). |
| N-02 | M13 Header | `WiedervorlagePort` fehlte trotz R-09 (Wiedervorlage 30 Tage vor Prüffrist) — gleiche Befundklasse wie D-10. | Header korrigiert. |
| N-03 | Kernel §8 ↔ M08 | Kernel-Eventname `m08.zeiterfassung.fehlt.v1` vs. `m08.erfassung.fehlt.v1` im (von uns ergänzten) M08-Events-Abschnitt. | M08 an den Kernel-Namen angeglichen. |
| N-04 | Kernel §2 | Vorgabe Python 3.12 — Build-Umgebung stellt 3.11. | Code 3.11-kompatibel gehalten; Abweichung im README (DoD Nr. 8). |

---

## 7. Geänderte Dateien

Alle 13 Modulspezifikationen wurden übernommen; inhaltlich geändert wurden:

| Datei | Änderungen |
|---|---|
| M01_Personalstammdaten.md | F-01, F-02, F-03, D-06 |
| M02_Kunde_Objekt.md | D-01, D-09, D-10, D-11, K-01, K-04 |
| M03_Qualifikationen_Dokumente.md | D-10 (WiedervorlagePort), D-13, Cache-Formulierung präzisiert |
| M04_Entgeltstruktur.md | D-05, F-10, K-06, K-07, K-08 |
| M06_Regelengine.md | F-05, F-06, F-07, D-02, D-03, D-04, K-02 |
| M07_Verfuegbarkeit_Abwesenheit.md | F-04, D-15, D-16, K-05 |
| M08_Zeiterfassung.md | D-14, K-03, K-05 |
| M09_Abgleich.md | D-07, K-03, K-09 |
| M10_Lohnabrechnung.md | D-07, D-08, K-10 |
| M11_Faktura.md | F-08, F-09, D-09 (Verweis) |
| M12_Subunternehmer.md | D-10, D-12, K-01 |
| M19_Kundenportal.md | D-17 |
| M20_Veranstaltungen.md | D-18, D-19, K-11, K-12 |

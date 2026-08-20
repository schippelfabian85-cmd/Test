# M03 — Qualifikationen und Dokumente

**Voraussetzung:** `00_KERNEL.md` + `MitarbeiterPortV1` (Stub genügt).
**Aufwand:** 30–45 PT · **Phase:** 1 · **Baubar ab:** parallel zu M01

---

## 1. Zweck und Abgrenzung

Beantwortet zuverlässig: *Darf diese Person diese Tätigkeit heute ausüben?* — plus die gesamte Dokumentenablage des Systems.

**Gehört dazu:** Qualifikationskatalog, Zuordnung zu Personen mit Ablaufdatum, Pflichtdokumente, Wiedervorlagen, Dokumentenablage (systemweit, auch für andere Module), Bewacherregister-Aufbereitung, Zuverlässigkeitsüberprüfung, Dienstausweisdruck, Ausbildungen und Schulungsstunden.

**Gehört nicht dazu:** Planungsentscheidungen (M05) und Regelprüfung (M06). M03 liefert nur die Auskunft, die Entscheidung trifft M06.

---

## 2. Entitäten

```sql
qualifikation(id, tenant_id, code, bezeichnung, kategorie,
              ist_planungsrelevant BOOL, ist_pflicht BOOL,
              gueltigkeitsdauer_monate, vorwarnfrist_tage DEFAULT 60, aktiv)

mitarbeiter_qualifikation(
  id, tenant_id, mitarbeiter_id, qualifikation_id,
  erworben_am, gueltig_ab, gueltig_bis,
  nachweis_dokument_id, ausstellende_stelle, nachweisnummer,
  status,          -- BEANTRAGT|GUELTIG|LAEUFT_AB|ABGELAUFEN|ENTZOGEN
  bemerkung, created_at, created_by)

dokument(id, tenant_id, dateiname, mime_type, groesse_bytes,
         speicherpfad, hash_sha256, hochgeladen_am, hochgeladen_von,
         kategorie, bezug_typ, bezug_id, vertraulich BOOL,
         geloescht_am)

pflichtdokument(id, tenant_id, kategorie, bezeichnung,
                gilt_fuer_vertragstyp_codes[], gilt_fuer_funktion_codes[],
                frist_tage_nach_eintritt, aktiv)

wiedervorlage(id, tenant_id, bezug_typ, bezug_id, titel, faellig_am,
              zustaendig_benutzer_id, status, erledigt_am, erledigt_von)

bewacherregister_datensatz(
  id, mitarbeiter_id, ausweisart, ausweisnummer, ausweis_gueltig_bis,
  maschinenlesbare_zeile_1, maschinenlesbare_zeile_2,
  geburtsname, taetigkeitsart, ueberpruefung_beantragt_am,
  ueberpruefung_ergebnis, ueberpruefung_gueltig_bis,
  bewacher_id_nummer, uebermittelt_am)

ausbildung(id, tenant_id, mitarbeiter_id, bezeichnung, datum,
           stunden, nachweis_dokument_id)
dienstausweis(id, inhaber_typ, inhaber_id,   -- MITARBEITER (M01) | SUBMITARBEITER (M12)
              ausweisnummer, ausgegeben_am,
              gueltig_bis, zurueck_am, layout_id, status)
```

---

## 3. Bereitgestellte Ports

```python
class QualifikationsPortV1(Protocol):
    def hat_qualifikation(self, mitarbeiter_id: UUID, code: str,
                          stichtag: date) -> bool: ...
    def qualifikationen(self, mitarbeiter_id: UUID,
                        stichtag: date) -> list[QualifikationDTO]: ...
    def ablaufend(self, tenant_id: UUID, bis: date) -> list[AblaufDTO]: ...
    def pflichtdokumente_fehlend(self, mitarbeiter_id: UUID) -> list[str]: ...

class DokumentPortV1(Protocol):
    def ablegen(self, tenant_id: UUID, datei: bytes, dateiname: str,
                kategorie: str, bezug_typ: str, bezug_id: UUID) -> UUID: ...
    def abrufen(self, dokument_id: UUID) -> tuple[bytes, str]: ...
    def loeschen(self, dokument_id: UUID, grund: str) -> None: ...

class WiedervorlagePortV1(Protocol):
    def anlegen(self, tenant_id: UUID, bezug_typ: str, bezug_id: UUID,
                titel: str, faellig_am: date,
                zustaendig_benutzer_id: UUID | None = None) -> UUID: ...
    def erledigen(self, wiedervorlage_id: UUID, benutzer_id: UUID) -> None: ...
```

`hat_qualifikation()` ist der meistgenutzte Aufruf des ganzen Systems — er wird bei jeder Planungsentscheidung ausgeführt. Ergebnis cachen — mindestens je Anfrage; bei prozessweitem Cache Invalidierung über die m03-Events.

`WiedervorlagePortV1` gehört hierher, weil Wiedervorlagen systemweit entstehen (M02 R-08, M12 R-08), aber an genau einer Stelle geführt und abgearbeitet werden sollen.

---

## 4. Konsumierte Ports

`MitarbeiterPortV1` — für Stammdaten und Eintrittsdatum. Sonst nichts.

---

## 5. Ausgelöste Events

`m03.qualifikation.erteilt.v1` · `m03.qualifikation.laeuft_ab.v1` (bei Erreichen der Vorwarnfrist) · `m03.qualifikation.abgelaufen.v1` · `m03.pflichtdokument.fehlt.v1` · `m03.wiedervorlage.faellig.v1`

---

## 6. Fachregeln

- **R-01** Eine Qualifikation gilt am Stichtag, wenn `gueltig_ab ≤ Stichtag ≤ gueltig_bis` **und** Status `GUELTIG` oder `LAEUFT_AB`.
- **R-02** Ein nächtlicher Lauf setzt Status automatisch: Vorwarnfrist erreicht → `LAEUFT_AB` plus Event; `gueltig_bis` überschritten → `ABGELAUFEN` plus Event.
- **R-03** Qualifikationen mit `ist_planungsrelevant` sperren bei Ablauf die Neuplanung. Bestehende künftige Schichten werden nicht automatisch gelöscht, sondern als Verstoß gemeldet — die Entscheidung trifft der Disponent.
- **R-04** Die Sachkundeprüfung nach § 34a GewO ist unbefristet, die Zuverlässigkeitsüberprüfung dagegen befristet. Beides muss getrennt abbildbar sein.
- **R-05** Pflichtdokumente ergeben sich aus Vertragstyp und Funktion. Fehlen sie nach Fristablauf, entsteht eine Wiedervorlage.
- **R-06** Dokumente werden nie physisch gelöscht, sondern mit `geloescht_am` markiert; echtes Löschen nur über die Anonymisierung aus M01.
- **R-07** Vertrauliche Dokumente (Gesundheit, Führungszeugnis) sind nur für Rolle `ADMIN` sichtbar, nie für `PLANER`.
- **R-08** Die maschinenlesbare Zeile wird aus Ausweisdaten nach ICAO 9303 berechnet, inklusive Prüfziffern. Nur Ausgabe, keine Übernahme fremder Berechnungen.
- **R-09** Der Bewacherregister-Export erfolgt als CSV mit definiertem Spaltensatz. Unvollständige Datensätze werden vor dem Export benannt, nicht stillschweigend übergangen.

---

## 7. Oberflächen

Qualifikationskatalog · Qualifikationsübersicht als Matrix Person × Qualifikation mit Ampel · GAP-Auswertung (welche Qualifikation fehlt wie oft) · Auslaufende Qualifikationen mit Zeitfilter · Reiter „Qualifikationen" und „Dokumente" in der Mitarbeiterakte · Wiedervorlagenliste · Bewacherregister-Erfassung mit Übernahmeknopf aus den Stammdaten · Dienstausweisdruck mit Layoutvorlage und Logo · fehlende Unterlagen als Arbeitsliste.

---

## 8. Berechtigungen

Katalog pflegen: ADMIN. Zuordnen: ADMIN, PLANER. Vertrauliche Dokumente: nur ADMIN. Eigene Dokumente hochladen: MA (nur Kategorien, die dafür freigegeben sind). Bewacherregister: ADMIN.

---

## 9. Akzeptanzkriterien

1. `hat_qualifikation()` liefert am letzten Gültigkeitstag `true`, am Folgetag `false`.
2. Der Nachtlauf setzt genau bei Erreichen der Vorwarnfrist Status und Event — nicht zweimal.
3. Ablauf einer planungsrelevanten Qualifikation erzeugt für jede künftige Schicht eine Verstoßmeldung.
4. Person mit Vertragstyp „geringfügig" bekommt nur die für sie definierten Pflichtdokumente.
5. Rolle `PLANER` erhält bei vertraulichem Dokument HTTP 403 und sieht es nicht in Listen.
6. Maschinenlesbare Zeile stimmt für drei Referenzdatensätze inklusive Prüfziffern.
7. Bewacherregister-Export benennt unvollständige Datensätze vor dem Download.
8. Gelöschtes Dokument ist über `abrufen()` nicht mehr erreichbar, der Datensatz aber noch vorhanden.
9. GAP-Auswertung zählt bei 12 Personen und 5 Qualifikationen korrekt.

---

## 10. Bereitzustellender Stub

Qualifikationen `SACHKUNDE_34A`, `UNTERRICHTUNG_34A`, `ERSTE_HILFE`, `BRANDSCHUTZHELFER`, `WAFFENSACHKUNDE`. Person `-0007` hat eine in 14 Tagen ablaufende Sachkunde, Person `-0011` gar keine.

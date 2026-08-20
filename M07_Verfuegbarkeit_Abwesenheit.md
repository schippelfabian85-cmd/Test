# M07 — Verfügbarkeit und Abwesenheit

**Voraussetzung:** `00_KERNEL.md` + `MitarbeiterPort` (Stub).
**Aufwand:** 25–35 PT · **Phase:** 1

## 1. Zweck und Abgrenzung
Beantwortet: *Kann diese Person an diesem Tag überhaupt arbeiten?*
**Dazu:** Leistungsbereitschaft (Wunschverfügbarkeit), Urlaubsanträge und Genehmigung, Urlaubskonto, Urlaubssperren, Krankmeldungen, Lohnfortzahlung, freie Sonntage, sonstige Abwesenheiten.
**Nicht dazu:** Planung (M05), Lohnwirkung der Abwesenheit (M04/M10).

## 2. Entitäten
```sql
leistungsbereitschaft(id, tenant_id, mitarbeiter_id, datum,
                      von_zeit, bis_zeit, art, bemerkung)
                      -- art: VERFUEGBAR | WUNSCHFREI | NUR_NOTFALL
leistungsbereitschaft_vorlage(id, mitarbeiter_id, wochentag, von_zeit, bis_zeit)

abwesenheit(id, tenant_id, mitarbeiter_id, art, von_datum, bis_datum,
            halber_tag_beginn BOOL, halber_tag_ende BOOL,
            status, beantragt_am, entschieden_am, entschieden_von,
            ablehnungsgrund, nachweis_dokument_id, bemerkung)
            -- art: URLAUB|KRANK|KIND_KRANK|UNBEZAHLT|SCHULUNG|FREI_DP|FREI_UEBERSTD|SPERRE
            -- SPERRE: persönliche Einsatzsperre (z. B. entzogene Zuverlässigkeit) — Grund "SPERRE" in M06 VF_ABWESEND
            -- status: BEANTRAGT|GENEHMIGT|ABGELEHNT|STORNIERT

urlaubskonto(id, tenant_id, mitarbeiter_id, jahr, anspruch_tage,
             uebertrag_vorjahr, genommen_tage, verplant_tage,
             verfallen_am)
urlaubssperre(id, tenant_id, von_datum, bis_datum, objekt_id NULL,
              gruppe_id NULL, begruendung)
krankmeldung(id, abwesenheit_id, gemeldet_am, gemeldet_ueber,
             au_ab_tag, au_vorgelegt_am, lohnfortzahlung_bis,
             krankenkasse, folgebescheinigung BOOL)
```

## 3. Bereitgestellter Port
```python
class VerfuegbarkeitsPortV1(Protocol):
    def ist_verfuegbar(self, mitarbeiter_id: UUID,
                       beginn_utc: datetime, ende_utc: datetime) -> VerfuegbarkeitDTO: ...
    def abwesenheiten(self, mitarbeiter_id: UUID, von: date, bis: date) -> list[AbwesenheitDTO]: ...
    def urlaubskonto(self, mitarbeiter_id: UUID, jahr: int) -> UrlaubskontoDTO: ...

@dataclass(frozen=True)
class VerfuegbarkeitDTO:
    verfuegbar: bool
    grund: str | None            # "URLAUB", "KRANK", "SPERRE", ...
    ausserhalb_bereitschaft: bool
    warnungen: tuple[str, ...]   # z. B. "URLAUB_BEANTRAGT" — verfuegbar bleibt true (R-01)
```

## 4. Ausgelöste Events
`m07.abwesenheit.beantragt.v1` · `m07.abwesenheit.genehmigt.v1` · `m07.abwesenheit.abgelehnt.v1` · `m07.krankmeldung.erfasst.v1` (M05 setzt daraufhin betroffene Schichten auf `AUSGEFALLEN`, R-04) · `m07.urlaub.verfall_warnung.v1` (60 Tage vor Verfallsstichtag, R-08)

## 5. Fachregeln
- **R-01** Genehmigter Urlaub blockiert die Planung. Beantragter Urlaub erzeugt nur eine Warnung.
- **R-02** Ein Urlaubsantrag über einen Zeitraum mit bereits geplanten Schichten wird angenommen, meldet dem Genehmiger aber die betroffenen Schichten mit Anzahl.
- **R-03** Genehmigung eines Urlaubs setzt betroffene Schichten **nicht** automatisch zurück. Der Disponent entscheidet, sonst entstehen unbemerkt Lücken im laufenden Betrieb.
- **R-04** Krankmeldung wirkt sofort und rückwirkend: laufende und künftige Schichten des Zeitraums werden als `AUSGEFALLEN` gemeldet (Event, Umsetzung in M05).
- **R-05** Lohnfortzahlung standardmäßig 42 Kalendertage ab erstem AU-Tag (§ 3 EFZG). Eine Folgebescheinigung (`folgebescheinigung = true`) setzt die Frist **nicht** neu; eine Erstbescheinigung nach zwischenzeitlicher Arbeitsfähigkeit beginnt eine neue Frist. Maßgeblich ist ausschließlich das Kennzeichen Erst-/Folgebescheinigung — eine Diagnose wird nie erfasst (R-10).
- **R-06** Urlaubssperren blockieren neue Anträge, heben bestehende Genehmigungen aber nicht auf.
- **R-07** Urlaubsanspruch wird zeitanteilig bei Ein- und Austritt berechnet, aufgerundet auf halbe Tage.
- **R-08** Resturlaub verfällt zum konfigurierten Stichtag (Standard 31.03. des Folgejahres) mit Vorwarnung 60 Tage vorher.
- **R-09** Freie Sonntage werden je Kalenderjahr gezählt und ausgewiesen (mindestens 15 nach ArbZG).
- **R-10** Gesundheitsdaten sind vertraulich: die Diagnose wird nie erfasst, das AU-Dokument ist nur für Rolle `ADMIN` sichtbar.

## 6. Oberflächen
Urlaubsplanung als Jahreskalender aller Personen · Antragsliste mit Genehmigung in einem Klick · Urlaubskonten mit Anspruch, genommen, verplant, Rest · Krankakte je Person · Leistungsbereitschaft Wochen- und Monatsansicht mit Vorlagenfunktion und Kopieren über Wochen · Urlaubssperrenverwaltung · Liste freier Sonntage.

## 7. Berechtigungen
Beantragen: MA (eigene). Genehmigen: ADMIN, PLANER, EL/OL im eigenen Bereich. Krankmeldung erfassen: ADMIN, PLANER, EL/OL. AU-Dokument sehen: nur ADMIN. Konten pflegen: ADMIN.

## 8. Akzeptanzkriterien
1. Genehmigter Urlaub führt bei `ist_verfuegbar()` zu `false` mit Grund `URLAUB`.
2. Beantragter, noch nicht genehmigter Urlaub führt zu `verfuegbar = true` mit Warnung `URLAUB_BEANTRAGT` in `warnungen`.
3. Antrag über 5 geplante Schichten meldet dem Genehmiger exakt diese 5.
4. Krankmeldung über einen Zeitraum mit 3 geplanten Schichten erzeugt genau ein Event `m07.krankmeldung.erfasst.v1`; M05 meldet daraufhin jede der 3 Schichten als `AUSGEFALLEN`.
5. Eintritt zum 01.07. bei 30 Tagen Jahresanspruch ergibt 15 Tage.
6. Resturlaub verfällt am Stichtag und erzeugt 60 Tage vorher genau eine Warnung.
7. Urlaubssperre blockiert neuen Antrag, bestehende Genehmigung bleibt.
8. Rolle `PLANER` sieht die Krankakte, aber nicht das AU-Dokument.
9. Wochenvorlage der Leistungsbereitschaft lässt sich auf 8 Wochen kopieren.

## 9. Stub
Person `-0003` hat Urlaub in KW 34, Person `-0005` ist ab dem 10. krank, Person `-0009` hat Leistungsbereitschaft nur an Wochenenden.

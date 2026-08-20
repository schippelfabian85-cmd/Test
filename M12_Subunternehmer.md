# M12 — Subunternehmer

**Voraussetzung:** `00_KERNEL.md` + `SchichtLookupPort`, `BuchungsPort`, `ObjektPort`, `QualifikationsPort`, `WiedervorlagePort` (Stubs).
**Aufwand:** 40–60 PT · **Phase:** 4

## 1. Zweck und Abgrenzung
Bindet Fremdfirmen ein, die Schichten mit eigenem Personal besetzen — mit eigenem Zugang und eigener Abrechnung.
**Dazu:** Subunternehmerakte, Verrechnungssätze, Submitarbeiter, Portalzugang, Schichtzuweisung, Subunternehmerabrechnung, Wachbuchzugang, Dienstausweise für Fremdpersonal.
**Nicht dazu:** Eigenes Personal (M01), Planung im Ganzen (M05), Kundenrechnungen (M11).

## 2. Entitäten
```sql
subunternehmer(id, tenant_id, nummer, firmenname, rechtsform,
               adresse_json, ust_id, steuernummer,
               bewachungserlaubnis_nr, erlaubnis_gueltig_bis,
               haftpflicht_nachweis_dokument_id, haftpflicht_gueltig_bis,
               standard_verrechnungssatz_cent, tarif_id NULL,
               zahlungsziel_tage, aktiv, eintrittsdatum, austrittsdatum,
               bemerkung, version)
sub_ansprechpartner(id, subunternehmer_id, name, funktion, telefon, email,
                    hat_login BOOL, ist_hauptkontakt)
sub_verrechnungssatz(id, subunternehmer_id, stamm_id, version,
                     gueltig_ab, gueltig_bis, aktiv,
                     funktion_code, objekt_id NULL,
                     satz_cent_pro_stunde)                           -- Muster A
submitarbeiter(id, tenant_id, subunternehmer_id, externe_personalnummer,
               nachname, vorname, geburtsdatum, status,
               ausweisnummer, aktiv, angelegt_von_sub BOOL)
submitarbeiter_qualifikation(id, submitarbeiter_id, qualifikation_code,
                             gueltig_bis, nachweis_dokument_id)
                             -- Codes aus dem M03-Katalog (QualifikationsPort);
                             -- die Nachweise selbst liegen hier, nicht in M03
sub_objektfreigabe(subunternehmer_id, objekt_id, freigabe_ab, freigabe_bis)
sub_abrechnung(id, tenant_id, subunternehmer_id, monat, status,
               summe_netto_cent, gutschrift_nr, dokument_id, freigegeben_am)
sub_abrechnung_position(id, sub_abrechnung_id, schicht_id, datum,
                        objekt_id, submitarbeiter_id, minuten,
                        satz_cent, betrag_cent)
```

## 3. Fachregeln
- **R-01** Ein Subunternehmer hat genau einen Systemzugang, auch bei mehreren Ansprechpartnern.
- **R-02** Submitarbeiter dürfen vom Subunternehmer selbst angelegt werden, sind aber bis zur Freigabe durch die Disposition nicht planbar.
- **R-03** Für Submitarbeiter gelten dieselben Qualifikationsanforderungen wie für eigenes Personal. Ohne Sachkundenachweis keine Zuweisung. Die Nachweise werden je Submitarbeiter in `submitarbeiter_qualifikation` geführt; der Anforderungskatalog (Codes) kommt aus M03, sodass auch weitere geforderte Qualifikationen (z. B. Waffensachkunde) prüfbar sind.
- **R-04** Eine Schicht wird entweder an einen eigenen Mitarbeiter **oder** an einen Subunternehmer vergeben, nie an beide.
- **R-05** Wird eine Schicht an einen Subunternehmer vergeben, weist dieser seinerseits einen Submitarbeiter zu. Bis dahin gilt die Schicht als besetzt, aber nicht personalisiert.
- **R-06** Der Subunternehmer sieht ausschließlich die ihm zugewiesenen Schichten und seine eigenen Mitarbeiter — nie andere Objekte, nie fremdes Personal, nie Kundendaten.
- **R-07** Die Subunternehmerabrechnung erfolgt als Gutschriftverfahren aus den abgeglichenen Schichten, mit funktionsabhängigen Verrechnungssätzen.
- **R-08** Nachweise mit Ablaufdatum (Bewachungserlaubnis, Haftpflicht) erzeugen eine Wiedervorlage 60 Tage vor Ablauf (über `WiedervorlagePort`, M03). Bei Ablauf ist keine neue Zuweisung mehr möglich.
- **R-09** Bei Beendigung wird der Zugang mit dem Austrittsdatum gesperrt und die Lizenz frei; die Daten bleiben für die Aufbewahrungsfrist erhalten.

## 4. Oberflächen
**Innensicht:** Subunternehmerliste · Subunternehmerakte (Stammdaten, Zusatzdaten, Verrechnungssätze, Ansprechpartner, Login, Objektfreigaben, Qualifikationen, Nachweise) · Submitarbeiterliste mit Freigabe · Zuweisung mehrerer Schichten in einem Vorgang · Subunternehmerabrechnung mit Gutschrift.
**Portalsicht (stark reduziert):** eigene Schichten, Zuweisung eigener Mitarbeiter, eigene Mitarbeiterakte mit Dokumentenupload, Dienstausweisdruck, Wachbuch der eigenen Schichten, eigene Abrechnungen.

## 5. Berechtigungen
Innensicht: ADMIN, PLANER. Abrechnung: ADMIN. Portal: Rolle `SUB`, strikt auf eigene Daten begrenzt (durchgehend über `ZustaendigkeitPort` geprüft, nicht nur in der Oberfläche).

## 6. Akzeptanzkriterien
1. Subunternehmer sieht ausschließlich eigene Schichten; ein direkter API-Aufruf auf eine fremde Schicht ergibt HTTP 403.
2. Submitarbeiter ohne Freigabe ist nicht zuweisbar.
3. Submitarbeiter ohne gültige Sachkunde wird blockiert.
4. Schicht mit eigenem Mitarbeiter kann nicht zusätzlich einem Subunternehmer zugewiesen werden.
5. Gutschrift für den Seed-Monat entspricht der Referenzsumme mit funktionsabhängigen Sätzen.
6. Abgelaufene Bewachungserlaubnis verhindert neue Zuweisungen und erzeugt eine Wiedervorlage.
7. Austrittsdatum sperrt den Zugang taggenau und gibt die Lizenz frei.
8. Der Subunternehmer kann eigene Mitarbeiter anlegen, aber keine Kunden- oder Objektdaten einsehen.

## 7. Stub
Ein Subunternehmer mit 3 Mitarbeitern aus dem Seed, davon einer ohne gültige Sachkunde.

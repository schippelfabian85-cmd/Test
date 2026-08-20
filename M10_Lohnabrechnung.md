# M10 — Lohnabrechnung und Exporte

**Voraussetzung:** `00_KERNEL.md` + `BuchungsPort`, `MitarbeiterPort`, `EntgeltPort` (Stubs).
**Aufwand:** 55–80 PT · **Phase:** 3

## 1. Zweck und Abgrenzung
Verdichtet Buchungen zu monatlichen Abrechnungsergebnissen und übergibt sie an das Lohnsystem.
**Dazu:** Lohnlauf, Abrechnungskreise, Zeitwertkonten, Arbeitszeitkonto, Vorschüsse, Stundennachweise, Verdienstnachweise, Exporte (DATEV, LODAS, CSV), Monatsabschluss.
**Nicht dazu:** die Buchungserzeugung selbst (M09), die Entgeltberechnung (M04), Kundenrechnungen (M11).

**Wichtige Vorentscheidung:** Wenn der Kunde extern abrechnen lässt, reduziert sich dieses Modul auf Nachweise und Export — Aufwand dann nur 20–30 PT. Diese Frage vor Baubeginn klären.

## 2. Entitäten
```sql
abrechnungskreis(id, tenant_id, code, bezeichnung, abrechnungstag,
                 stichtag_erfassung, vertragstyp_codes[], aktiv)
lohnlauf(id, tenant_id, abrechnungskreis_id, abrechnungsmonat,
         status, gestartet_am, gestartet_von, abgeschlossen_am,
         anzahl_mitarbeiter, summe_brutto_cent, export_datei_id)
         -- status: OFFEN|LAUFEND|GEPRUEFT|ABGESCHLOSSEN|EXPORTIERT
lohnlauf_position(id, lohnlauf_id, mitarbeiter_id, lohnart_nummer,
                  bezeichnung, menge_minuten, satz_cent, betrag_cent,
                  kostenstelle, herkunft,   -- ABGLEICH|MANUELL|ZWK|VORSCHUSS
                  lohnbuchung_ids[])        -- bei herkunft ABGLEICH: Rückverfolgung bis zur Schicht (R-06)
arbeitszeitkonto(id, tenant_id, mitarbeiter_id, monat,
                 soll_minuten, ist_minuten, saldo_minuten,
                 saldo_kumuliert_minuten)
zeitwertkonto(id, tenant_id, mitarbeiter_id, lohnart_id,
              monat, einstellung_minuten, entnahme_minuten,
              auszahlung_cent, saldo_minuten, saldo_cent, buchungsgrund)
vorschuss(id, tenant_id, mitarbeiter_id, datum, betrag_cent,
          verrechnung_ab_monat, raten, offener_betrag_cent, lohnart_id)
nachweis(id, tenant_id, art, bezug_typ, bezug_id, monat,
         erzeugt_am, dokument_id, versendet_am)
         -- art: STUNDENNACHWEIS|VERDIENSTNACHWEIS|EINZELSTUNDEN|MONATSSTUNDEN
```

## 3. Fachregeln
- **R-01** Ein Lohnlauf verarbeitet ausschließlich nicht stornierte Lohnbuchungen des jeweiligen Abrechnungsmonats, die noch keinem Lohnlauf zugeordnet sind (`in_lohnlauf_id` leer; Abruf über `lohnbuchungen(nur_unverlohnt=True)`).
- **R-02** Nach Abschluss eines Lohnlaufs sind die enthaltenen Buchungen gesperrt — die Zuordnung entsteht über `markiere_verlohnt()` (M09) in derselben Transaktion wie der Abschluss. Korrekturen laufen als Nachbuchung in den Folgemonat.
- **R-03** Zeitwertkonto funktioniert nur, wenn dem Vertragstyp eine ZWK-Lohnart zugeordnet ist (`vertragstyp.zwk_lohnart_id`, M01). Sonst Fehlermeldung mit Hinweis auf die Konfiguration.
- **R-04** Über- und Unterstunden werden gegen die vertraglichen Sollzeiten gerechnet; das Ergebnis geht wahlweise ins Zeitwertkonto oder zur Auszahlung.
- **R-05** Vorschüsse werden in konfigurierbaren Raten verrechnet und laufen nie ins Minus.
- **R-06** Alle Verdichtungen sind bis auf die einzelne Schicht rückverfolgbar. Ohne diese Nachvollziehbarkeit ist keine Lohnprüfung möglich.
- **R-07** Exportformate sind versioniert; ein bereits erzeugter Export bleibt reproduzierbar.
- **R-08** Der Monatsabschluss prüft Vollständigkeit: nicht abgeglichene Schichten, offene Prüf-Inbox-Einträge, fehlende Nachweise werden vor dem Abschluss aufgelistet.
- **R-09** Stundennachweise sind an Kunde oder Mitarbeiter versendbar und werden mit Versandzeitpunkt archiviert.

## 4. Oberflächen
Lohnlaufübersicht je Abrechnungskreis · Lohnlaufdetail mit Positionen je Person · Zeitwertkontenübersicht mit Soll, Ist, Differenz mit und ohne ZWK · Arbeitszeitkonto je Person mit Verlauf · Vorschussliste · Nachweise erzeugen und versenden · Exportmaske mit Formatauswahl und Vorschau · Monatsabschluss mit Vollständigkeitsprüfung als Checkliste.

## 5. Berechtigungen
Lohnlauf starten und abschließen: ADMIN. Vorschüsse erfassen: ADMIN. Ansehen: ADMIN, CONTROLLER. Nachweise erzeugen: ADMIN, PLANER. Eigenen Verdienstnachweis: MA.

## 6. Akzeptanzkriterien
1. Lohnlauf über den Seed-Monat ergibt exakt die hinterlegte Referenzsumme.
2. Nicht abgeglichene Schichten erscheinen nicht im Lauf, aber vollständig in der Vollständigkeitsprüfung.
3. Abgeschlossener Lauf sperrt seine Buchungen; Aufhebungsversuch in M09 schlägt fehl.
4. Überstunden gehen bei aktivem ZWK vollständig ins Zeitkonto, bei inaktivem in die Auszahlung.
5. Vorschuss über 3 Raten wird in 3 Monaten vollständig verrechnet, Restbetrag danach null.
6. Jede Lohnlaufposition ist auf die zugrunde liegenden Schichten aufschlüsselbar.
7. Zweimaliger Export desselben Laufs erzeugt bitgleiche Dateien.
8. Monatsabschluss bei offenen Prüf-Inbox-Einträgen listet diese auf und lässt sich dennoch mit Begründung durchführen.
9. Verdienstnachweis enthält alle Lohnarten des Monats mit korrekten Summen.

## 7. Stub
Nicht erforderlich — M10 stellt keinen Port für andere Module bereit. Es liefert lediglich Dateien und Nachweise.

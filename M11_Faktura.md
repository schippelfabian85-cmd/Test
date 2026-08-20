# M11 — Angebot, Faktura und Mahnwesen

**Voraussetzung:** `00_KERNEL.md` + `BuchungsPort`, `KundePort`, `ObjektPort` (Stubs).
**Aufwand:** 60–90 PT · **Phase:** 3 · **Auf ERPNext-Basis: 20–30 PT** (Standardfunktionalität)

## 1. Zweck und Abgrenzung
Die Kundenseite des Geldflusses: vom Angebot bis zum Mahnbescheid.
**Dazu:** Angebote mit Positionen, Rechnungserstellung aus Umsatzbuchungen, Rechnungslayout, individuelle Texte, Storno, Versand, ZUGFeRD/E-Rechnung, Mahnwesen, Rechnungseingang, FiBu-Export.
**Nicht dazu:** Umsatzbuchungen erzeugen (M09), Verrechnungssätze definieren (M04).

## 2. Entitäten
```sql
angebot(id, tenant_id, angebotsnummer, kunde_id, datum, gueltig_bis,
        status, betreff, einleitungstext, schlusstext,
        summe_netto_cent, summe_brutto_cent, version)
        -- status: ENTWURF|VERSENDET|ANGENOMMEN|ABGELEHNT|ABGELAUFEN
angebot_position(id, angebot_id, position_nr, objekt_id NULL,
                 bezeichnung, menge, einheit, einzelpreis_cent,
                 rabatt_prozent, summe_cent, steuersatz)

rechnung(id, tenant_id, rechnungsnummer, kunde_id, rechnungsdatum,
         leistungszeitraum_von, leistungszeitraum_bis,
         faelligkeitsdatum, zahlungsziel_tage, skonto_prozent, skonto_tage,
         status, summe_netto_cent, steuer_cent, summe_brutto_cent,
         layout_id, individueller_text, leitweg_id, bestellnummer,
         zugferd BOOL, dokument_id, versendet_am, versandart,
         bezahlt_am, bezahlter_betrag_cent,
         storno_von_id, storniert_durch_id, version)
         -- status: ENTWURF|OFFEN|TEILBEZAHLT|BEZAHLT|UEBERFAELLIG|STORNIERT
rechnung_position(id, rechnung_id, position_nr, objekt_id,
                  leistungsart, bezeichnung, menge_stunden,
                  einzelpreis_cent, summe_cent, steuersatz,
                  kostentraeger_id, umsatzbuchung_ids[])
mahnung(id, rechnung_id, stufe, datum, faellig_bis,
        mahngebuehr_cent, verzugszins_cent, dokument_id, versendet_am)
        -- stufe 1..5: Erinnerung, 1./2./3. Mahnung, Übergabe gerichtliches Mahnverfahren
        -- Stufe 5 versendet nichts: der Mahnbescheid wird beim Gericht beantragt (Übergabe an Inkasso/Anwalt)
rechnungseingang(id, tenant_id, lieferant, belegnummer, datum,
                 betrag_cent, faellig_am, bezahlt_am, dokument_id, kategorie)
rechnungslayout(id, tenant_id, bezeichnung, logo_dokument_id,
                kopfzeile, fusszeile, felder_json, standard BOOL)
```

## 3. Fachregeln
- **R-01** Rechnungsnummern sind lückenlos und aufsteigend. Standardmäßig systemweit, optional je Mandant getrennt — die Entscheidung fällt einmalig und ist danach unveränderlich.
- **R-02** Eine Rechnung entsteht aus Umsatzbuchungen. Jede Buchung darf nur einmal fakturiert werden; Zuordnung über `markiere_fakturiert()` in derselben Transaktion.
- **R-03** Eine versendete Rechnung ist unveränderlich. Korrektur ausschließlich über Storno und Neuausstellung mit Verweis auf das Original.
- **R-04** Ein Storno erzeugt eine eigene Rechnung mit negativen Beträgen und eigener Nummer, nicht ein Löschen.
- **R-05** Verdichtungsgrad der Positionen ist je Kunde konfigurierbar (`kunde.rechnung_verdichtung`, M02): eine Zeile je Objekt, je Leistungsart, je Monat oder Einzelnachweis je Schicht.
- **R-06** E-Rechnung: Für Rechnungen an öffentliche Auftraggeber (XRechnung/ZUGFeRD im B2G-Fall) ist die Leitweg-ID des Kunden Pflicht. Im B2B-Fall genügt ein EN-16931-konformes Profil ohne Leitweg-ID; eine D.U.N.S.-Nummer ist nur erforderlich, wenn der Übertragungsweg des Kunden (z. B. Peppol) sie verlangt. Vor der Erzeugung werden alle Pflichtangaben des gewählten Kanals geprüft; fehlt etwas, wird der Versand mit konkretem Hinweis abgelehnt statt eine ungültige Datei zu erzeugen.
- **R-07** Die Mahnstufe steigt automatisch nach Ablauf der jeweiligen Frist, der Versand erfolgt jedoch immer erst nach manueller Freigabe.
- **R-08** Mahngebühren und Verzugszinsen sind je Stufe konfigurierbar und werden auf der Mahnung ausgewiesen.
- **R-09** Teilzahlungen werden erfasst und setzen den Status auf `TEILBEZAHLT`; das Mahnwesen berücksichtigt nur den offenen Rest.
- **R-10** Jede Rechnungsposition ist bis auf die einzelnen Schichten aufschlüsselbar — das ist die häufigste Rückfrage von Kundenseite.

## 4. Oberflächen
Angebotsübersicht und -erstellung mit Positionen und Textbausteinen · Rechnungslauf je Monat mit Vorschau vor Freigabe · Rechnungsübersicht mit Status und Suche · Rechnungsdetail mit Aufschlüsselung bis zur Schicht · Layouteditor mit Logo · Versandmaske (Post, E-Mail, ZUGFeRD, Portal) mit Versandstatus · Mahnwesen als Arbeitsliste offener Posten mit Stufen · Rechnungseingang · Zahlungserfassung · FiBu-Export für den Steuerberater.

## 5. Berechtigungen
Angebote: ADMIN, PLANER. Rechnungen erstellen und stornieren: ADMIN. Ansehen: ADMIN, CONTROLLER. Mahnungen freigeben: ADMIN. Eigene Rechnungen ansehen: KUNDE.

## 6. Akzeptanzkriterien
1. Rechnungslauf über einen Monat erfasst alle unfakturierten Umsatzbuchungen genau einmal.
2. Zweiter Lauf über denselben Zeitraum erzeugt keine Positionen mehr.
3. Rechnungsnummern sind nach 100 Rechnungen lückenlos, auch bei parallelen Erstellungen.
4. Änderungsversuch an versendeter Rechnung wird mit `M11-E-004` abgelehnt.
5. Storno erzeugt eine Rechnung mit exakt spiegelbildlichen Beträgen; Saldo null.
6. E-Rechnung an einen öffentlichen Auftraggeber ohne Leitweg-ID wird mit konkretem Hinweis abgelehnt; im B2B-Fall wird ohne Leitweg-ID erzeugt.
7. Erzeugte ZUGFeRD-Datei validiert gegen das offizielle Schema.
8. Rechnung mit Zahlungsziel 14 Tagen erscheint am 15. Tag im Mahnwesen.
9. Mahnstufe steigt automatisch, versendet aber nichts ohne Freigabe.
10. Teilzahlung setzt Status korrekt und reduziert den offenen Posten.
11. Position lässt sich auf die zugrunde liegenden Schichten aufschlüsseln, Summe stimmt überein.

## 7. Stub
Nicht erforderlich — außer `KUNDE`-Portal (M19) greift kein Modul lesend auf M11 zu.

## 8. Hinweis zur Umsetzung
Dieses Modul ist der stärkste Grund für eine ERP-Basis. Nummernkreise, Steuerlogik, Mahnstufen, Zahlungsabgleich und FiBu-Export sind in ERPNext fertig, erprobt und geprüft. Selbst gebaut sind es 60–90 PT mit erheblichem Risiko in Steuer- und Formatfragen.

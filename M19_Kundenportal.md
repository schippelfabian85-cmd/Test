# M19 — Kundenportal

**Voraussetzung:** `00_KERNEL.md` + `SchichtLookupPort`, `ObjektPort`, `KundePort` (Stubs); für die Bereiche NACHWEISE, RECHNUNGEN und WACHBUCH/WKS zusätzlich Lesezugriff auf M10 (Nachweise), M11 (Rechnungen) und M14 (Wachbuch/Runden).
**Aufwand:** 20–30 PT · **Phase:** 5

## 1. Zweck und Abgrenzung
Ein eng begrenzter Lesezugang für den Auftraggeber — die günstigste Möglichkeit, Rückfragen zu reduzieren.
**Dazu:** Kundenlogin, Planungssicht der eigenen Objekte, Tagesplan, Nachweise, Rechnungen, Wachbuch und Rundenauswertung, sofern freigegeben.
**Nicht dazu:** jede Form von Schreibzugriff. Der Kunde plant nicht.

## 2. Entitäten
```sql
kundenzugang(id, tenant_id, kunde_id, ansprechpartner_id, benutzer_id,
             aktiv, angelegt_am, letzter_login)
kundenzugang_freigabe(kundenzugang_id, objekt_id, bereich, sichtbar BOOL)
  -- bereich: PLANUNG|TAGESPLAN|NACHWEISE|RECHNUNGEN|WACHBUCH|WKS|KONTAKTE
```

## 3. Fachregeln
- **R-01** Der Zugang ist ausschließlich lesend. Es existiert kein schreibender Endpunkt für Rolle `KUNDE`.
- **R-02** Sichtbar ist grundsätzlich nichts. Jeder Bereich und jedes Objekt wird einzeln freigegeben.
- **R-03** Personenbezogene Daten der Mitarbeiter werden standardmäßig verkürzt dargestellt (Nachname, Funktion). Vollständige Namen nur bei ausdrücklicher Freigabe — es besteht kein pauschales berechtigtes Interesse des Auftraggebers an vollständigen Personaldaten.
- **R-04** Kalkulationsdaten, Löhne, Verrechnungssätze und Deckungsbeiträge sind niemals sichtbar, auch nicht mittelbar über Auswertungen.
- **R-05** Jeder Zugriff wird protokolliert.
- **R-06** Der Zugang ist mit dem Vertragsende automatisch zu sperren.

## 4. Oberflächen
Bewusst reduziert: Übersicht der eigenen Objekte · Planungssicht je Objekt und Zeitraum · Tagesplan mit Besetzungsstatus · Leistungsnachweise zum Download · Rechnungen · Wachbuch und Rundenauswertungen, sofern freigegeben · Ansprechpartner.

## 5. Akzeptanzkriterien
1. Kein Endpunkt für Rolle `KUNDE` verändert Daten (automatisierter Test über alle Routen).
2. Nicht freigegebener Bereich ist weder sichtbar noch per direktem Aufruf erreichbar.
3. Fremdes Objekt ergibt HTTP 403.
4. Ohne Freigabe erscheinen nur Nachname und Funktion.
5. Keine Sicht enthält Lohn- oder Kalkulationsdaten.
6. Jeder Zugriff steht im Protokoll.
7. Vertragsende sperrt den Zugang taggenau.

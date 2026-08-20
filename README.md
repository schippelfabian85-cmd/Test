# Branchenlösung Sicherheitsgewerbe

Modulare Umsetzung nach den Spezifikationen `M01`–`M20` in diesem Repository.
Die Spezifikationen wurden vor Baubeginn geprüft und korrigiert — Befunde und
Begründungen in [`PLAUSIBILITAETSPRUEFUNG.md`](PLAUSIBILITAETSPRUEFUNG.md).

## Stand der Umsetzung

| Baustein | Status | Inhalt |
|---|---|---|
| `src/kernel/` | provisorisch | Gemeinsame DTOs (`SchichtDTO`, `VertragsgrenzenDTO`, Verstoß-Stufen). `00_KERNEL.md` liegt noch nicht vor — beim Eintreffen gegen dessen Definitionen abgleichen. |
| `src/m06_regelengine/` | **fertig** | Alle 18 Regeln des Auslieferungskatalogs, Ausnahmen mit Begründung/Genehmiger (R-02), Übersteuerung nur ADMIN mit Protokoll (R-03), Verstoßtexte für Disponenten (R-04), `PruefKontext`-Beispiele als Test-Stub (Abschnitt 9). |
| `src/m04_entgelt/` | Kern fertig | Minutengenaue Segmentzerlegung (R-01) mit Priorität/Kumulierung/Verdrängung (R-02) und Zeitumstellung (R-10). Noch offen: `berechne_lohn()`/`berechne_umsatz()` auf Basis der Segmente, Tarif-/Maskenverwaltung (Muster A), Mindestlohnanhebung (R-06). |

Baureihenfolge folgt den Spezifikationen: M06 zuerst (M06 §10 — isoliert baubar,
alle Planungsmodule bauen darauf auf), danach der Rechenkern aus M04 §10.
Als Nächstes: Vervollständigung M04, dann M01/M02 mit den Port-Stubs für Phase 1.

## Entwicklung

```bash
pip install pytest
python -m pytest
```

Konventionen aus den Spezifikationen, die überall gelten:

- Zeitstempel in UTC, Kalenderlogik in `Europe/Berlin`
- Beträge in Cent, Dauern in Minuten, Rundung erst am Ende
- Fehlercodes `MXX-E-NNN`, Verstoß-Stufen `BLOCKIEREND | WARNUNG | HINWEIS`
- Seed-IDs: Mitarbeiter `11111111-…`, Objekte `22222222-…`

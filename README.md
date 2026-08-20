# Branchenlösung Sicherheitsgewerbe

Modulare Umsetzung nach den Spezifikationen `00_KERNEL.md` und `M01`–`M20` in
diesem Repository. Die Spezifikationen wurden vor Baubeginn geprüft und
korrigiert — Befunde in [`PLAUSIBILITAETSPRUEFUNG.md`](PLAUSIBILITAETSPRUEFUNG.md).

## Schnellstart

```bash
pip install fastapi uvicorn sqlalchemy jinja2 python-multipart pytest httpx
PYTHONPATH=src python3 -m uvicorn app:erstelle_app --factory --port 8000
```

Danach: <http://localhost:8000/app> — Entwicklungszugänge (Seed, K-12):

| E-Mail | Rolle | Passwort |
|---|---|---|
| admin@musterschutz.example | ADMIN | musterschutz! |
| disposition@musterschutz.example | PLANER | musterschutz! |
| controlling@musterschutz.example | CONTROLLER | musterschutz! |
| objektleitung@musterschutz.example | OL (nur eigener Bereich) | musterschutz! |

REST-API unter `/api/v1/…` (OpenAPI: `/docs`), Anmeldung über
`POST /api/v1/auth/token`. **Produktion:** `DATABASE_URL` (PostgreSQL 16) und
`JWT_SECRET` setzen, `migrationen/postgres_rls.sql` einspielen.

```bash
python3 -m pytest        # 108 Tests: Akzeptanzkriterien M01/M02/M04/M06 + Kernel + UI
```

## Stand der Umsetzung

| Baustein | Status | Inhalt |
|---|---|---|
| `src/kernel/` | **fertig** (M00) | Mandanten, Benutzer/Rollen/JWT, Audit (K-4), Outbox-Events (§8), Nummernkreise, Muster A (§4), Idempotenz/409 (§9), ZustaendigkeitPort (K-8), Fehlerformat. Abweichungen: `src/kernel/README.md` |
| `src/m01_personal/` | **fertig** | Personalakte mit R-01–R-08, Vertragstypen (Muster A, stichtagsgenau), Statusautomat, Austritt/Lizenzfreigabe, Anonymisierung, Historie, `MitarbeiterPortV1` + Stub, REST + Oberfläche |
| `src/m02_kunde_objekt/` | **fertig** | Kunden-/Objektakte mit R-01–R-08, Freigaben, Dienstanweisungs-Versionen, Objektzuschläge (Muster A), Wiedervorlagen-Lauf, `ObjektPortV1`/`KundePortV1`, REST + Oberfläche |
| `src/m04_entgelt/` | **fertig** | Segmentzerlegung (R-01/R-02/R-10), Lohn-/Umsatzberechnung mit Tarifversionen, Mindestlohnanhebung (R-06), Verrechnungssätze inkl. ANTEILIG, Feiertage je Bundesland, `EntgeltPortV1` + Stub, Probe-Rechner |
| `src/m06_regelengine/` | **fertig** | Alle 18 Katalogregeln, Ausnahmen, Übersteuerung mit Protokoll, `PruefKontext`-Beispiele |
| `src/stubs/` | Stubs (K-2) | `SchichtLookupPort` (M05 §10: 4 Seed-Wochen), `DokumentPort`/`WiedervorlagePort` (M03) |
| `src/web/` | **fertig** | Anmeldung, Übersicht, Mitarbeiterliste/-akte/Neuanlage (mit CSV-Export), Kunden- und Objektakten, Tarifübersicht, Probe-Rechner |

Noch nicht gebaut: M03, M05, M07–M20 (Anschluss über die vorhandenen Ports).
Sinnvolle nächste Schritte laut Kernel §12: M03/M07, dann M05.

## Konventionen (aus dem Kernel)

- Kein Modul liest fremde Tabellen — nur Ports und Events (K-1)
- Zeitstempel UTC, Kalenderlogik `Europe/Berlin` (K-7: Nachtschicht → Starttag)
- Beträge in Cent, Dauern in Minuten, Rundung erst am Ende (M04 R-09)
- Fehlercodes `MXX-E-NNN`; fachliche Fehler nie HTTP 500 (§9)
- Seed-IDs: Mitarbeiter `11111111-…`, Objekte `22222222-…`, Schichten `55555555-…`

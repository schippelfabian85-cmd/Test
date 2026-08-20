# Kernel (M00) — Umsetzungsstand und dokumentierte Abweichungen

Gemäß Definition of Done Nr. 8 (`00_KERNEL.md` §10) dokumentiert diese Datei
alle Abweichungen der Umsetzung von der Anleitung.

## Umgesetzt

- Basisdatenmodell §3 (mandant, benutzer, rolle, benutzer_rolle, audit_log,
  nummernkreis) plus Outbox (§8) und Idempotenz-Speicher (§9)
- Muster A als Mixin + `neue_version()`/`version_am()` (§4, K-5-Prüfung)
- OAuth2-Password-Flow mit JWT: Access 15 min, Refresh 30 Tage (§2)
- Einheitliches Fehlerformat `{code, message, details}`; fachliche Fehler
  sind nie HTTP 500; `Idempotency-Key`; optimistisches Sperren → 409 (§9)
- Audit-Schreiber (K-4), UUIDv7 (§2), `ZustaendigkeitPort` (K-8)
- Rollenprüfung als deklarative Dependency `benoetigt(...)` (K-9)

## Abweichungen

1. **Python 3.11 statt 3.12** (§2): Die Build-Umgebung stellt 3.11; der Code
   nutzt keine 3.12-Syntax. Beim Wechsel auf 3.12 keine Anpassung nötig.
2. **JWT über Standardbibliothek** statt einer JWT-Bibliothek: HS256 mit
   `hmac`/`hashlib`, konstantzeitiger Vergleich, kein Algorithmus-Downgrade
   möglich. Grund: defektes `cryptography`-Binding der Umgebung; bewusst
   beibehalten, weil abhängigkeitsfrei.
3. **`zustaendigkeit`-Tabelle ergänzt**: Der Kernel definiert den
   `ZustaendigkeitPort`, aber keine Datengrundlage. Kandidat für einen
   Änderungsantrag (siehe PLAUSIBILITAETSPRUEFUNG.md, N-01 ff.).
4. **Seed als Python-Modul** (`src/seed_basis.py`) statt `seed/basis.sql`
   (§11): läuft datenbankneutral über die ORM-Modelle und ist idempotent.
   Schichten, Subunternehmer und Ressourcen liefern die Stubs (M05/M12/M13).
5. **Migrationen**: Schemaaufbau derzeit über `create_all` beim Start;
   versionierte Vor-/Rückwärtsmigrationen (DoD Nr. 4) stehen aus — vor dem
   ersten Produktivstand Alembic einführen. RLS für PostgreSQL liegt als
   `migrationen/postgres_rls.sql` bei.
6. **Outbox-Worker synchron**: Zustellung erfolgt im Entwicklungsbetrieb
   nach jedem Request-Commit im selben Prozess (at-least-once bleibt
   gewahrt); in Produktion als separater Worker-Prozess zu betreiben.

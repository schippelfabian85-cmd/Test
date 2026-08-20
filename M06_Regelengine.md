# M06 — Regel- und Verstoß-Engine

**Voraussetzung:** ausschließlich `00_KERNEL.md`. **Vollständig isoliert baubar.**
**Aufwand:** 25–40 PT · **Phase:** 1 · Idealer Startpunkt für parallele Arbeit.

---

## 1. Zweck und Abgrenzung

Beantwortet genau eine Frage: *Ist diese geplante Besetzung zulässig — und wenn nein, warum nicht?*

**Gehört dazu:** Arbeitszeitrecht, Ruhezeiten, Qualifikationspflicht, Objektfreigabe, Verfügbarkeit, Vertragsgrenzen, Jugendarbeitsschutz, Mindestlohn- und Verdienstgrenzen, kundenspezifische Sonderregeln.

**Gehört nicht dazu:** Die Daten selbst. M06 hält **keine eigene Fachdatenbank** — es bekommt alles als Eingabe übergeben. Damit ist es ohne jedes andere Modul testbar und ist das am besten prüfbare Modul des Projekts.

---

## 2. Entitäten

```sql
regel(id, tenant_id, code, bezeichnung, rechtsgrundlage,
      kategorie, stufe, aktiv, parameter_json, reihenfolge)
      -- stufe: BLOCKIEREND | WARNUNG | HINWEIS

regel_ausnahme(id, tenant_id, regel_id, geltungsbereich,
               objekt_id NULL, mitarbeiter_id NULL, vertragstyp_code NULL,
               gueltig_ab, gueltig_bis, begruendung, genehmigt_von)

verstoss_protokoll(id, tenant_id, schicht_id, regel_code, stufe,
                   festgestellt_am, uebersteuert_von, uebersteuerungsgrund)
```

---

## 3. Bereitgestellter Port

```python
class RegelpruefPortV1(Protocol):
    def pruefe(self, kontext: PruefKontext) -> PruefErgebnis: ...
    def pruefe_stapel(self, kontexte: list[PruefKontext]) -> list[PruefErgebnis]: ...

@dataclass(frozen=True)
class PruefKontext:
    tenant_id: UUID
    mitarbeiter_id: UUID
    objekt_id: UUID
    geplante_schicht: SchichtDTO
    # Alles Folgende wird vom Aufrufer mitgeliefert — M06 lädt nichts selbst:
    bestehende_schichten: tuple[SchichtDTO, ...]   # +/- 14 Tage um die neue
    qualifikationen: tuple[str, ...]               # gültig am Schichttag
    erforderliche_qualifikationen: tuple[str, ...]
    objekt_freigegeben: bool
    verfuegbar: bool
    verfuegbarkeit_grund: str | None
    ausserhalb_bereitschaft: bool          # aus M07 (VF_BEREITSCHAFT)
    minuten_monat_bisher: int
    minuten_24_wochen_bisher: int          # Summe der letzten 24 Wochen (AZ_WOCHE_MAX)
    grenzen: VertragsgrenzenDTO            # enthält ist_minderjaehrig
    verdienst_monat_bisher_cent: int
    verdienst_geplante_schicht_cent: int   # vom Aufrufer über EntgeltPort ermittelt (GF_VERDIENST)
    einsatztage_jahr_bisher: int

@dataclass(frozen=True)
class Verstoss:
    regel_code: str; stufe: str; text: str
    rechtsgrundlage: str; details: dict

@dataclass(frozen=True)
class PruefErgebnis:
    zulaessig: bool                 # False, sobald ein BLOCKIEREND vorliegt
    verstoesse: tuple[Verstoss, ...]
```

---

## 4. Konsumierte Ports

Keine. Das ist Absicht und der Grund für die gute Testbarkeit.

---

## 5. Regelkatalog (Auslieferungszustand)

| Code | Regel | Stufe | Grundlage |
|---|---|---|---|
| `AZ_TAG_MAX` | Höchstens 8 h werktäglich, 10 h bei Ausgleich | BLOCKIEREND | § 3 ArbZG |
| `AZ_RUHEZEIT` | Mindestens 11 h zwischen zwei Schichten | BLOCKIEREND | § 5 ArbZG |
| `AZ_RUHEZEIT_VERKUERZT` | 10 h zulässig bei Ausgleich in 4 Wochen | WARNUNG | § 7 ArbZG i. V. m. TV |
| `AZ_PAUSE` | 30 min bei mehr als 6 h, 45 min bei mehr als 9 h | BLOCKIEREND | § 4 ArbZG |
| `AZ_SONNTAG` | Sonntagsarbeit nur mit Ausnahme; Ersatzruhetag | WARNUNG | §§ 9–11 ArbZG |
| `AZ_WOCHE_MAX` | Durchschnitt 48 h in 24 Wochen | WARNUNG | § 3 ArbZG |
| `JU_TAG_MAX` | Unter 18: höchstens 8 h täglich, 40 h wöchentlich | BLOCKIEREND | § 8 JArbSchG |
| `JU_NACHT` | Unter 18: keine Arbeit 20–06 Uhr | BLOCKIEREND | § 14 JArbSchG |
| `JU_RUHEZEIT` | Unter 18: mindestens 12 h Ruhezeit | BLOCKIEREND | § 13 JArbSchG |
| `QU_FEHLT` | Erforderliche Qualifikation fehlt oder abgelaufen | BLOCKIEREND | § 34a GewO |
| `OB_FREIGABE` | Keine Objektfreigabe für diese Person | BLOCKIEREND | intern |
| `VF_ABWESEND` | Urlaub, Krankheit oder Sperre | BLOCKIEREND | intern |
| `VF_BEREITSCHAFT` | Außerhalb angegebener Leistungsbereitschaft | WARNUNG | intern |
| `VT_MAX_STD` | Vertragliche Höchststunden überschritten | WARNUNG | intern |
| `VT_MIN_STD` | Vertragliche Mindeststunden nicht erreicht | HINWEIS | intern |
| `GF_VERDIENST` | Geringfügigkeitsgrenze überschritten | BLOCKIEREND | § 8 SGB IV |
| `KF_70_TAGE` | Grenze kurzfristiger Beschäftigung erreicht | BLOCKIEREND | § 8 SGB IV |
| `UEBERSCHNEIDUNG` | Zeitliche Doppelbelegung der Person | BLOCKIEREND | intern |

*Hinweis zu `AZ_RUHEZEIT_VERKUERZT`: § 5 Abs. 2 ArbZG erfasst das Bewachungsgewerbe nicht — die Verkürzung ist nur bei tariflicher Öffnung nach § 7 ArbZG zulässig (z. B. MTV des Landesverbands). Die Regel wird deshalb **deaktiviert ausgeliefert** und erst bei nachgewiesener Tarifbindung aktiviert.*

**R-01** Der Katalog ist über `parameter_json` konfigurierbar (Stundenwerte, Fristen), aber nicht in seiner Logik. Neue Regeln entstehen im Code, nicht in der Datenbank.
**R-02** Jede Regel muss einzeln abschaltbar und pro Objekt, Vertragstyp oder Person ausnehmbar sein — mit Begründung und Genehmiger.
**R-03** Eine Übersteuerung blockierender Verstöße ist ausschließlich Rolle `ADMIN` erlaubt und wird in `verstoss_protokoll` festgehalten.
**R-04** Verstoßtexte sind für den Disponenten geschrieben, nicht für Juristen: was ist das Problem, was ist die Folge, was kann er tun.

---

## 6. Oberflächen

Regelkatalog mit Stufe und Aktivierung · Ausnahmenverwaltung · Verstoßprotokoll als Auswertung (welche Regel schlägt wie oft an — wichtiger Hinweis auf Fehlkonfiguration) · Prüfsimulator für den Support.

---

## 7. Berechtigungen

Katalog und Ausnahmen: ADMIN. Protokoll einsehen: ADMIN, CONTROLLER. Prüfung aufrufen: alle planenden Rollen.

---

## 8. Akzeptanzkriterien

Für jede der 18 Regeln je ein positiver und ein negativer Testfall, zusätzlich:

1. Ruhezeit von exakt 11 h ist zulässig, 10 h 59 min blockiert.
2. Minderjährige Person: Schichtende exakt 20:00 zulässig, 20:01 blockiert (§ 14 JArbSchG erlaubt Beschäftigung bis 20 Uhr).
3. Abgelaufene Sachkunde blockiert, Ablauf am Folgetag der Schicht nicht.
4. Deaktivierte Regel erzeugt keinen Verstoß mehr.
5. Objektbezogene Ausnahme greift nur für dieses Objekt.
6. Mehrere gleichzeitige Verstöße werden vollständig zurückgegeben, nicht nur der erste.
7. `zulaessig` ist genau dann `false`, wenn mindestens ein blockierender Verstoß vorliegt.
8. `pruefe_stapel()` mit 1.000 Kontexten bleibt unter 2 Sekunden.
9. Übersteuerung ohne Grund wird abgelehnt.
10. `GF_VERDIENST` rechnet den erwarteten Verdienst der geplanten Schicht mit: liegt `verdienst_monat_bisher_cent` plus `verdienst_geplante_schicht_cent` über `grenzen.max_verdienst_monat_cent`, wird blockiert — nicht erst, wenn die Grenze bereits gerissen ist.

---

## 9. Bereitzustellender Stub

Nicht erforderlich — M06 ist bereits ohne Fremdabhängigkeit lauffähig. Stattdessen bereitstellen: eine Sammlung vorbereiteter `PruefKontext`-Beispiele, die andere Module in ihren Tests verwenden können.

---

## 10. Hinweis zur Umsetzung

Dieses Modul ist der beste Kandidat für ein Team- oder Einarbeitungsprojekt: klarer Vertrag, keine Abhängigkeiten, hohe Testbarkeit, sofort sichtbarer fachlicher Wert. Wenn parallel gearbeitet wird, sollte es zuerst entstehen — alle Planungsmodule bauen darauf auf.

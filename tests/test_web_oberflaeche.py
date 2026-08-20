"""Weboberfläche: Anmeldefluss und die Sichten der Modulanleitungen."""

from fastapi.testclient import TestClient


def _anmelden(client: TestClient, email="admin@musterschutz.example",
              passwort="musterschutz!") -> None:
    antwort = client.post("/app/login", data={"email": email, "passwort": passwort,
                                              "weiter": "/app"},
                          follow_redirects=False)
    assert antwort.status_code == 303
    client.cookies.update(antwort.cookies)


def test_unangemeldet_wird_zur_anmeldung_geleitet(client):
    antwort = client.get("/app", follow_redirects=False)
    assert antwort.status_code == 303
    assert antwort.headers["location"].startswith("/app/login")


def test_falsche_anmeldung_zeigt_fehler(client):
    antwort = client.post("/app/login", data={"email": "admin@musterschutz.example",
                                              "passwort": "falsch", "weiter": "/app"})
    assert antwort.status_code == 200
    assert "M00-E-402" in antwort.text


def test_alle_hauptsichten_rendern(client):
    _anmelden(client)
    for pfad, erwartung in [
        ("/app", "Übersicht"),
        ("/app/mitarbeiter", "Mitarbeiterliste"),
        ("/app/mitarbeiter/neu", "Neuanlage"),
        ("/app/mitarbeiter/11111111-1111-1111-1111-000000000001", "Albrecht"),
        ("/app/kunden", "Stadtwerke Halle"),
        ("/app/objekte", "Pforte Stadtwerke"),
        ("/app/tarife", "Zuschlagsmasken"),
        ("/app/proberechner", "Rechner zur Probe"),
    ]:
        antwort = client.get(pfad)
        assert antwort.status_code == 200, pfad
        assert erwartung in antwort.text, pfad


def test_mitarbeiterakte_reiter(client):
    _anmelden(client)
    basis = "/app/mitarbeiter/11111111-1111-1111-1111-000000000004"
    vertrag = client.get(f"{basis}?reiter=vertrag")
    assert "Minderjährig (heute)" in vertrag.text and ">ja<" in vertrag.text
    historie = client.get(f"{basis}?reiter=historie")
    assert "vertragstyp_id" in historie.text


def test_neuanlage_ueber_formular(client):
    _anmelden(client)
    seite = client.get("/app/mitarbeiter/neu")
    vertragstyp_id = seite.text.split('name="vertragstyp_id"')[1].split(
        'value="')[1].split('"')[0]
    antwort = client.post("/app/mitarbeiter/neu", data={
        "personalnummer": "P7001", "nachname": "Weber", "vorname": "Toni",
        "geburtsdatum": "1993-07-07", "land": "Deutschland",
        "eintrittsdatum": "2026-10-01", "vertragstyp_id": vertragstyp_id,
        "funktion_codes": ["WACH"]}, follow_redirects=True)
    assert antwort.status_code == 200
    assert "Weber, Toni" in antwort.text

    # Pflichtfeldverletzung bleibt auf der Maske und nennt den Fehlercode.
    fehler = client.post("/app/mitarbeiter/neu", data={
        "personalnummer": "P7002", "nachname": "", "vorname": "X",
        "geburtsdatum": "", "land": "Deutschland", "eintrittsdatum": "",
        "vertragstyp_id": vertragstyp_id, "funktion_codes": ["WACH"]})
    assert "M01-E-001" in fehler.text


def test_proberechner_fronleichnam(client):
    _anmelden(client)
    antwort = client.post("/app/proberechner", data={
        "mitarbeiter_id": "11111111-1111-1111-1111-000000000001",
        "objekt_id": "22222222-2222-2222-2222-000000000004",   # München, BY
        "funktion_code": "WACH", "datum": "2026-06-04",
        "beginn": "08:00", "ende": "16:00", "pause": "30"})
    assert antwort.status_code == 200
    assert "Feiertagszuschlag" in antwort.text
    assert "Deckungsbeitrag" in antwort.text


def test_csv_export(client):
    _anmelden(client)
    antwort = client.get("/api/v1/personal/mitarbeiter.csv")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("text/csv")
    assert "Personalnummer" in antwort.text and "P0001" in antwort.text

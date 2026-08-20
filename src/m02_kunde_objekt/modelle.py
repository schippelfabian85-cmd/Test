"""Entitäten M02 (Abschnitt 2) — inkl. Korrekturen der Plausibilitätsprüfung
(bundesland, kostentraeger, rechnung_verdichtung, objekt_zuschlag als
vollständiges Muster A)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import Basis, Uuid
from kernel.ids import uuid7
from kernel.modelle import jetzt_utc
from kernel.muster import MusterA


class Kunde(Basis):
    __tablename__ = "kunde"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    kundennummer: Mapped[str] = mapped_column(String(40))
    firmenname: Mapped[str] = mapped_column(String(200))
    rechtsform: Mapped[str | None] = mapped_column(String(60), nullable=True)
    strasse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plz: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ort: Mapped[str | None] = mapped_column(String(120), nullable=True)
    land: Mapped[str] = mapped_column(String(80), default="Deutschland")
    ust_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    steuernummer: Mapped[str | None] = mapped_column(String(30), nullable=True)
    leitweg_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duns_nummer: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zahlungsziel_tage: Mapped[int] = mapped_column(Integer, default=14)
    skonto_prozent: Mapped[int] = mapped_column(Integer, default=0)
    skonto_tage: Mapped[int] = mapped_column(Integer, default=0)
    rechnungsversand: Mapped[str] = mapped_column(String(20), default="EMAIL")
    rechnung_verdichtung: Mapped[str] = mapped_column(String(20), default="JE_OBJEKT")
    rechnungsempfaenger_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    abweichende_rechnungsanschrift_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    eintrittsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    austrittsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    bemerkung: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("tenant_id", "kundennummer"),)


class KundeAnsprechpartner(Basis):
    __tablename__ = "kunde_ansprechpartner"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    kunde_id: Mapped[object] = mapped_column(Uuid, ForeignKey("kunde.id"), index=True)
    anrede: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    funktion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobil: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ist_hauptkontakt: Mapped[bool] = mapped_column(Boolean, default=False)
    erhaelt_rechnung: Mapped[bool] = mapped_column(Boolean, default=False)
    erhaelt_dienstplan: Mapped[bool] = mapped_column(Boolean, default=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)


class Kostentraeger(Basis):
    __tablename__ = "kostentraeger"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    nummer: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "nummer"),)


class Objektart(Basis):
    __tablename__ = "objektart"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))


class Objektgruppe(Basis):
    __tablename__ = "objektgruppe"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    uebergeordnet_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)


class Objekt(Basis):
    __tablename__ = "objekt"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    objektnummer: Mapped[str] = mapped_column(String(40))
    kunde_id: Mapped[object] = mapped_column(Uuid, ForeignKey("kunde.id"))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    objektart_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    objektgruppe_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    strasse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plz: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ort: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bundesland: Mapped[str] = mapped_column(String(40), default="ST")  # Feiertage (M04 R-07)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_meter: Mapped[int] = mapped_column(Integer, default=100)
    einsatzbeginn: Mapped[date] = mapped_column(Date, default=date(2024, 1, 1))
    einsatzende: Mapped[date | None] = mapped_column(Date, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    kostenstelle_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    kostentraeger_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    ansprechpartner_vor_ort: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telefon_vor_ort: Mapped[str | None] = mapped_column(String(50), nullable=True)
    besondere_hinweise: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("tenant_id", "objektnummer"),)


class ObjektDokument(Basis):
    __tablename__ = "objekt_dokument"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    objekt_id: Mapped[object] = mapped_column(Uuid, ForeignKey("objekt.id"), index=True)
    dokument_id: Mapped[object] = mapped_column(Uuid)   # Datei liegt in M03
    kategorie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sichtbar_fuer_ma: Mapped[bool] = mapped_column(Boolean, default=False)
    gueltig_ab: Mapped[date | None] = mapped_column(Date, nullable=True)
    gueltig_bis: Mapped[date | None] = mapped_column(Date, nullable=True)


class Dienstanweisung(Basis):
    __tablename__ = "dienstanweisung"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    objekt_id: Mapped[object] = mapped_column(Uuid, ForeignKey("objekt.id"), index=True)
    titel: Mapped[str] = mapped_column(String(200))
    inhalt: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    gueltig_ab: Mapped[date | None] = mapped_column(Date, nullable=True)
    bestaetigung_erforderlich: Mapped[bool] = mapped_column(Boolean, default=False)


class DienstanweisungBestaetigung(Basis):
    __tablename__ = "dienstanweisung_bestaetigung"
    dienstanweisung_id: Mapped[object] = mapped_column(
        Uuid, ForeignKey("dienstanweisung.id"), primary_key=True)
    mitarbeiter_id: Mapped[object] = mapped_column(Uuid, primary_key=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)


class ObjektMitarbeiter(Basis):
    """Objektfreigabe: wer darf an einem Objekt eingesetzt werden (R-05)."""

    __tablename__ = "objekt_mitarbeiter"
    objekt_id: Mapped[object] = mapped_column(Uuid, ForeignKey("objekt.id"), primary_key=True)
    mitarbeiter_id: Mapped[object] = mapped_column(Uuid, primary_key=True)
    freigabe_ab: Mapped[date] = mapped_column(Date)
    freigabe_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    ist_stammkraft: Mapped[bool] = mapped_column(Boolean, default=False)
    bemerkung: Mapped[str | None] = mapped_column(Text, nullable=True)


class ObjektMitarbeitergruppe(Basis):
    __tablename__ = "objekt_mitarbeitergruppe"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    objekt_id: Mapped[object] = mapped_column(Uuid, ForeignKey("objekt.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))


class ObjektZuschlag(MusterA, Basis):
    __tablename__ = "objekt_zuschlag"
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    objekt_id: Mapped[object] = mapped_column(Uuid, ForeignKey("objekt.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    art: Mapped[str] = mapped_column(String(20), default="PROZENT")  # PROZENT|BETRAG
    wert: Mapped[int] = mapped_column(Integer, default=0)  # Prozent oder Cent
    verwendet: Mapped[bool] = mapped_column(Boolean, default=False)  # R-07: nach Abrechnung unveränderlich


class KundeHistorie(Basis):
    __tablename__ = "kunde_historie"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    kunde_id: Mapped[object] = mapped_column(Uuid, ForeignKey("kunde.id"), index=True)
    feld: Mapped[str] = mapped_column(String(60))
    alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    neu: Mapped[str | None] = mapped_column(Text, nullable=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    benutzer_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)

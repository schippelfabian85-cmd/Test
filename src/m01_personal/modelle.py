"""Entitäten M01 (Abschnitt 2) — inkl. der Korrekturen aus der
Plausibilitätsprüfung (pausen_bezahlt, zwk_lohnart_id am Vertragstyp)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import Basis, Uuid
from kernel.ids import uuid7
from kernel.modelle import jetzt_utc
from kernel.muster import MusterA

MITARBEITER_STATUS = ("BEWERBER", "AKTIV", "RUHEND", "AUSGESCHIEDEN", "ANONYMISIERT")

# R-08: erlaubte Statusübergänge; Rücksprung aus AUSGESCHIEDEN nur ADMIN mit Grund.
STATUS_UEBERGAENGE = {
    "BEWERBER": {"AKTIV"},
    "AKTIV": {"RUHEND", "AUSGESCHIEDEN"},
    "RUHEND": {"AKTIV", "AUSGESCHIEDEN"},
    "AUSGESCHIEDEN": {"ANONYMISIERT", "AKTIV"},   # AKTIV = Wiedereinstellung (ADMIN)
    "ANONYMISIERT": set(),
}


class Vertragstyp(MusterA, Basis):
    __tablename__ = "vertragstyp"
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    kategorie: Mapped[str] = mapped_column(String(20))  # VOLLZEIT|TEILZEIT|GERINGFUEGIG|KURZFRISTIG|AUSHILFE
    soll_stunden_monat: Mapped[int] = mapped_column(Integer, default=0)
    min_stunden_monat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_stunden_monat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_verdienst_monat_cent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_einsatztage_jahr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    urlaubstage_jahr: Mapped[int] = mapped_column(Integer, default=20)
    pausen_bezahlt: Mapped[bool] = mapped_column(Boolean, default=False)
    zeitwertkonto_aktiv: Mapped[bool] = mapped_column(Boolean, default=False)
    zwk_lohnart_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)  # nur ID, Lohnart in M04
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    created_by: Mapped[object | None] = mapped_column(Uuid, nullable=True)


class Mitarbeiter(Basis):
    __tablename__ = "mitarbeiter"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    personalnummer: Mapped[str] = mapped_column(String(50))
    nachname: Mapped[str] = mapped_column(String(120))
    vorname: Mapped[str] = mapped_column(String(120))
    geburtsdatum: Mapped[date] = mapped_column(Date)
    geburtsort: Mapped[str | None] = mapped_column(String(120), nullable=True)
    staatsangehoerigkeit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    strasse: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plz: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ort: Mapped[str | None] = mapped_column(String(120), nullable=True)
    land: Mapped[str] = mapped_column(String(80), default="Deutschland")
    telefon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobil: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    eintrittsdatum: Mapped[date] = mapped_column(Date)
    austrittsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    austrittsgrund: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="AKTIV")
    vertragstyp_id: Mapped[object] = mapped_column(Uuid, ForeignKey("vertragstyp.id"))
    anstellungsort_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    kostenstelle_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    foto_dokument_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)  # Datei in M03
    sofortmeldung_erforderlich: Mapped[bool] = mapped_column(Boolean, default=False)
    sofortmeldung_erfolgt_am: Mapped[date | None] = mapped_column(Date, nullable=True)
    benutzer_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)  # Kernel-Benutzer (Lizenz)
    bemerkung: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    created_by: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "personalnummer"),)


class Funktion(Basis):
    __tablename__ = "funktion"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    sortierung: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class MitarbeiterFunktion(Basis):
    __tablename__ = "mitarbeiter_funktion"
    mitarbeiter_id: Mapped[object] = mapped_column(Uuid, ForeignKey("mitarbeiter.id"), primary_key=True)
    funktion_id: Mapped[object] = mapped_column(Uuid, ForeignKey("funktion.id"), primary_key=True)
    ist_hauptfunktion: Mapped[bool] = mapped_column(Boolean, default=False)
    gueltig_ab: Mapped[date | None] = mapped_column(Date, nullable=True)
    gueltig_bis: Mapped[date | None] = mapped_column(Date, nullable=True)


class Anstellungsort(Basis):
    __tablename__ = "anstellungsort"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    adresse: Mapped[str | None] = mapped_column(String(300), nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)


class Kostenstelle(Basis):
    __tablename__ = "kostenstelle"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    nummer: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "nummer"),)


class MitarbeiterHistorie(Basis):
    __tablename__ = "mitarbeiter_historie"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    mitarbeiter_id: Mapped[object] = mapped_column(Uuid, ForeignKey("mitarbeiter.id"), index=True)
    feld: Mapped[str] = mapped_column(String(60))
    alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    neu: Mapped[str | None] = mapped_column(Text, nullable=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    benutzer_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)

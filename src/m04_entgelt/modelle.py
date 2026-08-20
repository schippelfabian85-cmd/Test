"""Entitäten M04 (Abschnitt 2) — inkl. Korrekturen der Plausibilitätsprüfung
(kumulierung an der Zuschlagsmaske) und der dokumentierten Erweiterung
`weiterberechnung_prozent` für ANTEILIG (siehe Modul-README)."""

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import Basis, Uuid
from kernel.ids import uuid7
from kernel.modelle import jetzt_utc
from kernel.muster import MusterA


class Tarif(MusterA, Basis):
    __tablename__ = "tarif"
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    bundesland: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quelle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    created_by: Mapped[object | None] = mapped_column(Uuid, nullable=True)


class Lohngruppe(Basis):
    __tablename__ = "lohngruppe"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tarif_id: Mapped[object] = mapped_column(Uuid, ForeignKey("tarif.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    stundenlohn_cent: Mapped[int] = mapped_column(Integer)
    funktion_codes: Mapped[str] = mapped_column(String(400), default="")  # CSV


class Lohnart(Basis):
    __tablename__ = "lohnart"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    nummer: Mapped[str] = mapped_column(String(20))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    art: Mapped[str] = mapped_column(String(20))  # GRUNDLOHN|ZUSCHLAG|ZULAGE|AUSZAHLUNG|ABZUG|ZWK
    steuerpflichtig: Mapped[bool] = mapped_column(Boolean, default=True)
    sv_pflichtig: Mapped[bool] = mapped_column(Boolean, default=True)
    export_schluessel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "nummer"),)


class Zuschlagsmaske(MusterA, Basis):
    __tablename__ = "zuschlagsmaske"
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    tarif_id: Mapped[object] = mapped_column(Uuid, ForeignKey("tarif.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    typ: Mapped[str] = mapped_column(String(20), default="SONSTIGE")  # NACHT|SONNTAG|FEIERTAG|MEHRARBEIT|SONSTIGE
    prioritaet: Mapped[int] = mapped_column(Integer, default=0)
    kumulierung: Mapped[str] = mapped_column(String(12), default="KUMULIERT")  # KUMULIERT|VERDRAENGT (R-02)
    wochentage: Mapped[str] = mapped_column(String(20), default="0,1,2,3,4,5,6")  # CSV, 0=Mo
    von_uhrzeit: Mapped[time] = mapped_column(Time, default=time(0))
    bis_uhrzeit: Mapped[time] = mapped_column(Time, default=time(0))
    gilt_an_feiertagen: Mapped[bool] = mapped_column(Boolean, default=False)
    gilt_an_sonntagen: Mapped[bool] = mapped_column(Boolean, default=False)
    prozent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    betrag_cent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lohnart_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("lohnart.id"), nullable=True)
    bemessung: Mapped[str] = mapped_column(String(20), default="GRUNDLOHN")  # GRUNDLOHN|TARIFLOHN|FESTBETRAG
    verwendet: Mapped[bool] = mapped_column(Boolean, default=False)  # R-03: nach Verwendung unveränderlich


class Zulage(Basis):
    __tablename__ = "zulage"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    mitarbeiter_id: Mapped[object] = mapped_column(Uuid, index=True)
    art: Mapped[str] = mapped_column(String(40))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    betrag_cent: Mapped[int] = mapped_column(Integer)
    ist_pauschal: Mapped[bool] = mapped_column(Boolean, default=True)
    gueltig_ab: Mapped[date] = mapped_column(Date)
    gueltig_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    lohnart_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("lohnart.id"), nullable=True)


class Verrechnungssatz(MusterA, Basis):
    __tablename__ = "verrechnungssatz"
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    kunde_id: Mapped[object] = mapped_column(Uuid, index=True)
    objekt_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    funktion_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    satz_cent_pro_stunde: Mapped[int] = mapped_column(Integer)
    zuschlag_weiterberechnung: Mapped[str] = mapped_column(String(12), default="KEINE")  # KEINE|ANTEILIG|VOLL
    weiterberechnung_prozent: Mapped[int] = mapped_column(Integer, default=100)  # Anteil bei ANTEILIG


class Feiertag(Basis):
    __tablename__ = "feiertag"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    datum: Mapped[date] = mapped_column(Date)
    bezeichnung: Mapped[str] = mapped_column(String(120))
    bundesland: Mapped[str] = mapped_column(String(40))
    ist_gesetzlich: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "datum", "bundesland", "bezeichnung"),)


class Mindestlohn(Basis):
    __tablename__ = "mindestlohn"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    gueltig_ab: Mapped[date] = mapped_column(Date)
    betrag_cent: Mapped[int] = mapped_column(Integer)
    branche: Mapped[str | None] = mapped_column(String(80), nullable=True)

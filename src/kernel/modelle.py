"""Kernel-eigene Tabellen (Kernel §3) plus Outbox (§8), Idempotenz (§9)
und Zuständigkeiten (§6 K-8 — der Kernel definiert den Port, aber keine
Tabelle; diese Ergänzung ist im Kernel-README dokumentiert)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import Basis, Uuid
from kernel.ids import uuid7


def jetzt_utc() -> datetime:
    return datetime.now(timezone.utc)


class Mandant(Basis):
    __tablename__ = "mandant"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    uebergreifende_nummernkreise: Mapped[bool] = mapped_column(Boolean, default=False)


class Rolle(Basis):
    __tablename__ = "rolle"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Benutzer(Basis):
    __tablename__ = "benutzer"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    personalnummer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    passwort_hash: Mapped[str] = mapped_column(String(300))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    letzter_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lizenztyp: Mapped[str] = mapped_column(String(20), default="VOLL")
    __table_args__ = (UniqueConstraint("tenant_id", "email"),)


class BenutzerRolle(Basis):
    __tablename__ = "benutzer_rolle"
    benutzer_id: Mapped[object] = mapped_column(Uuid, ForeignKey("benutzer.id"), primary_key=True)
    rolle_id: Mapped[object] = mapped_column(Uuid, ForeignKey("rolle.id"), primary_key=True)
    tenant_id: Mapped[object] = mapped_column(Uuid, primary_key=True)
    gueltig_ab: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gueltig_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Basis):
    __tablename__ = "audit_log"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    benutzer_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    modul: Mapped[str] = mapped_column(String(10))
    entitaet: Mapped[str] = mapped_column(String(100))
    entitaet_id: Mapped[str] = mapped_column(String(64))
    aktion: Mapped[str] = mapped_column(String(40))
    alt_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    neu_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Nummernkreis(Basis):
    __tablename__ = "nummernkreis"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    code: Mapped[str] = mapped_column(String(40))
    praefix: Mapped[str] = mapped_column(String(20), default="")
    naechster_wert: Mapped[int] = mapped_column(Integer, default=1)
    pro_mandant: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class OutboxEvent(Basis):
    """Kernel §8: Outbox-Tabelle, Zustellung mindestens einmal."""

    __tablename__ = "outbox_event"
    event_id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    actor_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotenzEintrag(Basis):
    """Kernel §9: Wiederholung mit gleichem Idempotency-Key liefert dasselbe Ergebnis."""

    __tablename__ = "idempotenz_eintrag"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    schluessel: Mapped[str] = mapped_column(String(200))
    endpunkt: Mapped[str] = mapped_column(String(200))
    status_code: Mapped[int] = mapped_column(Integer)
    antwort_json: Mapped[str] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    __table_args__ = (UniqueConstraint("tenant_id", "schluessel", "endpunkt"),)


class Zustaendigkeit(Basis):
    """Sichtbarkeitsbereich für EL/OL/MA (K-8) — Datengrundlage des ZustaendigkeitPort."""

    __tablename__ = "zustaendigkeit"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    tenant_id: Mapped[object] = mapped_column(Uuid, index=True)
    benutzer_id: Mapped[object] = mapped_column(Uuid, index=True)
    objekt_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    mitarbeiter_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)

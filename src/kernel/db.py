"""Datenbankschicht.

Kernel §2 legt PostgreSQL 16 mit Row Level Security fest. Die Anwendung
läuft über SQLAlchemy gegen `DATABASE_URL` (PostgreSQL in Produktion);
ohne Konfiguration startet sie mit SQLite für Entwicklung und Tests.
Die Mandantentrennung ist zusätzlich in jeder Service-Abfrage erzwungen
(`tenant_id`-Filter) — unter PostgreSQL kommt RLS obendrauf, siehe
migrationen/postgres_rls.sql und src/kernel/README.md.
"""

import os
import uuid

from sqlalchemy import String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


class Basis(DeclarativeBase):
    pass


class Uuid(TypeDecorator):
    """UUID als CHAR(36) — portabel zwischen PostgreSQL und SQLite."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value)


def erstelle_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///daten/entwicklung.db")
    optionen: dict = {}
    if url in ("sqlite://", "sqlite:///:memory:"):
        # In-Memory-Datenbank muss alle Sessions auf einer Verbindung halten.
        optionen = {"poolclass": StaticPool,
                    "connect_args": {"check_same_thread": False}}
    elif url.startswith("sqlite:///"):
        os.makedirs(os.path.dirname(url.removeprefix("sqlite:///")) or ".", exist_ok=True)
        optionen = {"connect_args": {"check_same_thread": False}}
    engine = create_engine(url, future=True, **optionen)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_an(dbapi_verbindung, _):
            dbapi_verbindung.execute("PRAGMA foreign_keys=ON")
    return engine


def erstelle_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_schema(engine) -> None:
    # Import registriert alle Modelle an der Basis, bevor create_all läuft.
    from kernel import modelle  # noqa: F401
    from m01_personal import modelle as m01  # noqa: F401
    from m02_kunde_objekt import modelle as m02  # noqa: F401
    from m04_entgelt import modelle as m04  # noqa: F401

    Basis.metadata.create_all(engine)

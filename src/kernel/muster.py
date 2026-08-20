"""Muster A — versionierte Stammdaten (Kernel §4).

Eine Änderung erzeugt immer eine neue Zeile mit version + 1; die alte
bekommt `gueltig_bis` und `aktiv = false`. Buchungen referenzieren immer
die konkrete Version, nie die stamm_id.
"""

from datetime import date, timedelta

from sqlalchemy import Boolean, Date, Integer, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from kernel.db import Uuid
from kernel.fehler import FachFehler
from kernel.ids import uuid7


class MusterA:
    """Mixin: id, stamm_id, version, gueltig_ab, gueltig_bis, aktiv."""

    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid7)
    stamm_id: Mapped[object] = mapped_column(Uuid, index=True, default=uuid7)
    version: Mapped[int] = mapped_column(Integer, default=1)
    gueltig_ab: Mapped[date] = mapped_column(Date, default=date(2000, 1, 1))
    gueltig_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)


_META_FELDER = {"id", "stamm_id", "version", "gueltig_ab", "gueltig_bis", "aktiv"}


def neue_version(session: Session, alt, gueltig_ab: date, fehlercode: str, **aenderungen):
    """Schließt die alte Version und legt die Folgeversion an (K-5: nur Zukunft)."""
    if gueltig_ab <= alt.gueltig_ab:
        raise FachFehler(
            fehlercode,
            "Die neue Version muss nach der bestehenden beginnen — rückwirkende "
            "Änderungen sind ein separater, protokollierter Vorgang (Kernel K-5).",
            {"bestehende_gueltig_ab": str(alt.gueltig_ab), "gewuenscht": str(gueltig_ab)},
        )
    mapper = inspect(type(alt))
    werte = {
        spalte.key: getattr(alt, spalte.key)
        for spalte in mapper.column_attrs
        if spalte.key not in _META_FELDER
    }
    unbekannt = set(aenderungen) - set(werte)
    if unbekannt:
        raise FachFehler(fehlercode, f"Unbekannte Felder: {sorted(unbekannt)}")
    werte.update(aenderungen)

    neu = type(alt)(**werte)
    neu.stamm_id = alt.stamm_id
    neu.version = alt.version + 1
    neu.gueltig_ab = gueltig_ab
    neu.aktiv = True

    alt.gueltig_bis = gueltig_ab - timedelta(days=1)
    alt.aktiv = False
    session.add(neu)
    session.flush()
    return neu


def version_am(session: Session, modell, stamm_id, stichtag: date):
    """Die am Stichtag gültige Version eines Stamms — oder None."""
    return session.scalars(
        select(modell).where(
            modell.stamm_id == stamm_id,
            modell.gueltig_ab <= stichtag,
            (modell.gueltig_bis.is_(None)) | (modell.gueltig_bis >= stichtag),
        ).order_by(modell.version.desc())
    ).first()

"""Auth (Kernel §2): OAuth2-Password-Flow mit JWT — Access 15 min, Refresh 30 Tage.

JWT (HS256) ist bewusst mit der Standardbibliothek implementiert:
keine Abhängigkeit, kein Algorithmus-Downgrade möglich, Prüfung mit
konstantzeitigem Vergleich. Passwörter: PBKDF2-HMAC-SHA256.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from uuid import UUID

from kernel.fehler import FachFehler, NichtErlaubt

ACCESS_MINUTEN = 15
REFRESH_TAGE = 30
_PBKDF2_RUNDEN = 210_000


def _geheimnis() -> bytes:
    return os.environ.get("JWT_SECRET", "nur-entwicklung-unsicher").encode()


def hash_passwort(passwort: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", passwort.encode(), salt, _PBKDF2_RUNDEN)
    return f"pbkdf2${_PBKDF2_RUNDEN}${salt.hex()}${digest.hex()}"

def pruefe_passwort(passwort: str, gespeichert: str) -> bool:
    try:
        _, runden, salt_hex, digest_hex = gespeichert.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", passwort.encode(), bytes.fromhex(salt_hex), int(runden)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode()

def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def erstelle_token(benutzer_id: UUID, tenant_id: UUID, rollen: list[str],
                   art: str = "access") -> str:
    laufzeit = ACCESS_MINUTEN * 60 if art == "access" else REFRESH_TAGE * 86400
    payload = {
        "sub": str(benutzer_id),
        "tenant": str(tenant_id),
        "rollen": rollen,
        "art": art,
        "iat": int(time.time()),
        "exp": int(time.time()) + laufzeit,
    }
    kopf = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    rumpf = _b64(json.dumps(payload).encode())
    signatur = hmac.new(_geheimnis(), f"{kopf}.{rumpf}".encode(), hashlib.sha256).digest()
    return f"{kopf}.{rumpf}.{_b64(signatur)}"


def lese_token(token: str, erwartete_art: str = "access") -> dict:
    try:
        kopf, rumpf, signatur = token.split(".")
    except ValueError:
        raise FachFehler("M00-E-401", "Ungültiges Token", http_status=401)
    erwartet = hmac.new(_geheimnis(), f"{kopf}.{rumpf}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(erwartet), signatur):
        raise FachFehler("M00-E-401", "Ungültige Token-Signatur", http_status=401)
    payload = json.loads(_unb64(rumpf))
    if payload.get("exp", 0) < time.time():
        raise FachFehler("M00-E-401", "Token abgelaufen", http_status=401)
    if payload.get("art") != erwartete_art:
        raise FachFehler("M00-E-401", "Falsche Token-Art", http_status=401)
    return payload


@dataclass(frozen=True)
class AuthKontext:
    """Wer handelt gerade — Grundlage für Audit, Events und Berechtigungen."""

    benutzer_id: UUID
    tenant_id: UUID
    rollen: frozenset[str] = field(default_factory=frozenset)

    def hat_rolle(self, *codes: str) -> bool:
        return bool(self.rollen & set(codes))

    def fordere_rolle(self, *codes: str) -> None:
        """K-9: jeder Endpunkt deklariert seine Anforderung explizit."""
        if not self.hat_rolle(*codes):
            raise NichtErlaubt(
                "M00-E-403",
                f"Diese Funktion erfordert eine der Rollen: {', '.join(codes)}",
                {"benoetigt": list(codes), "vorhanden": sorted(self.rollen)},
            )


def kontext_aus_token(token: str) -> AuthKontext:
    payload = lese_token(token)
    return AuthKontext(
        benutzer_id=UUID(payload["sub"]),
        tenant_id=UUID(payload["tenant"]),
        rollen=frozenset(payload.get("rollen", [])),
    )

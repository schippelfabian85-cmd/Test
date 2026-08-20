"""Einheitliches Fehlerformat (Kernel §9).

Fachliche Fehler tragen `code` mit Modulpräfix (`M01-E-001`) und werden
nie als HTTP 500 ausgeliefert — 500 heißt immer Bug.
"""


class FachFehler(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None,
                 http_status: int = 422):
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status
        super().__init__(f"{code}: {message}")

    def als_json(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class NichtGefunden(FachFehler):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(code, message, details, http_status=404)


class NichtErlaubt(FachFehler):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(code, message, details, http_status=403)


class VersionsKonflikt(FachFehler):
    """Optimistisches Sperren: veraltete `version` → HTTP 409 (Kernel §9)."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(code, message, details, http_status=409)

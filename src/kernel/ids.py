"""UUIDv7 (Kernel §2: technische IDs sind UUID v7 — zeitlich sortierbar)."""

import os
import time
from uuid import UUID


def uuid7() -> UUID:
    """RFC-9562-konforme UUIDv7: 48 Bit Unix-Millisekunden + Zufall."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    wert = (ms & 0xFFFFFFFFFFFF) << 80
    wert |= 0x7 << 76                      # Version 7
    wert |= (rand >> 68) & 0x0FFF          # rand_a (12 Bit)
    wert |= 0b10 << 62                     # Variante
    wert |= rand & 0x3FFFFFFFFFFFFFFF      # rand_b (62 Bit)
    return UUID(int=wert)

"""Stable seed/identity helpers. Never use Python's randomized hash() for saves."""
from __future__ import annotations
import struct
import zlib
from typing import Any

SEED_ALGORITHM_VERSION = 1


def stable_seed(*parts: Any) -> int:
    """Return a process-independent CRC32 seed from a typed, delimited encoding."""
    payload = "\x1f".join(f"{type(part).__name__}:{part}" for part in parts).encode("utf-8")
    return zlib.crc32(payload) & 0xFFFFFFFF


def chunk_seed(world_seed: int, cx: int, cy: int) -> int:
    """Compatibility with the original Plan 13.2.xx <qqq> chunk-seed contract."""
    return zlib.crc32(struct.pack("<qqq", int(world_seed), int(cx), int(cy))) & 0xFFFFFFFF


def stable_vessel_id(world_seed: int, archetype: str, index: int) -> str:
    """Stable identity independent of generation order or Python hash randomization."""
    archetype = str(archetype).strip().lower().replace(" ", "_")
    return f"{archetype}-{stable_seed('vessel-id', int(world_seed), archetype, int(index)):08x}"

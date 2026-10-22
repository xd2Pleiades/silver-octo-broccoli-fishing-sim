"""Safe, versioned career-save envelope and atomic disk I/O.

Saves are JSON (never pickle), checksummed, size-limited, and written through a
same-directory temporary file. A last-known-good ``.bak`` is kept before each
replacement so a partial write or damaged main file can be recovered.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

SAVE_FORMAT = "japanese-deep-sea-fishing-career"
CAREER_SAVE_SCHEMA_VERSION = 1
MAX_SAVE_BYTES = 32 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def build_envelope(payload: dict, game_version: str) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("career payload must be an object")
    body = dict(payload)
    canonical = _canonical(body)
    return {
        "format": SAVE_FORMAT,
        "schema_version": CAREER_SAVE_SCHEMA_VERSION,
        "game_version": str(game_version),
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
        "payload": body,
    }


def validate_envelope(envelope: Any) -> dict:
    if not isinstance(envelope, dict):
        raise ValueError("career save must be a JSON object")
    if envelope.get("format") != SAVE_FORMAT:
        raise ValueError("this file is not a Fishing Simulator career save")
    try:
        schema = int(envelope.get("schema_version", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid career save schema") from exc
    if schema != CAREER_SAVE_SCHEMA_VERSION:
        raise ValueError("unsupported career save schema %r" % schema)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("career save payload must be an object")
    claimed = str(envelope.get("payload_sha256", ""))
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if not claimed or not __import__("hmac").compare_digest(claimed, actual):
        raise ValueError("career save checksum mismatch; file may be damaged")
    if not str(envelope.get("game_version", "")):
        raise ValueError("career save is missing its game version")
    return payload


def atomic_write(path: str | os.PathLike, envelope: dict, *, keep_backup: bool = True) -> Path:
    """Atomically save an envelope, retaining a last-good .bak when possible."""
    target = Path(path)
    validate_envelope(envelope)
    encoded = _canonical(envelope)
    if len(encoded) > MAX_SAVE_BYTES:
        raise ValueError("career save exceeds the 32 MiB safety limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_suffix(target.suffix + ".bak")
    fd = None
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if keep_backup and target.exists():
            # Only promote a valid current file to last-good. Never overwrite a valid
            # backup with a corrupt primary file.
            try:
                current = read_envelope(target, allow_backup=False)
                if current is not None:
                    shutil.copy2(target, backup)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        os.replace(temp_name, target)
        temp_name = None
        # Best-effort directory sync: not supported on every platform/filesystem.
        try:
            dfd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
        return target
    finally:
        if fd is not None:
            os.close(fd)
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _read_one(path: Path) -> dict:
    size = path.stat().st_size
    if size <= 0 or size > MAX_SAVE_BYTES:
        raise ValueError("career save has invalid size")
    with path.open("rb") as stream:
        raw = stream.read(MAX_SAVE_BYTES + 1)
    if len(raw) > MAX_SAVE_BYTES:
        raise ValueError("career save exceeds the 32 MiB safety limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("career save is not valid UTF-8 JSON") from exc
    validate_envelope(value)
    return value


def read_envelope(path: str | os.PathLike, *, allow_backup: bool = True) -> tuple[dict, bool]:
    """Return ``(envelope, used_backup)``; fall back to .bak on a corrupt primary."""
    target = Path(path)
    try:
        return _read_one(target), False
    except (OSError, ValueError, json.JSONDecodeError) as primary_error:
        if not allow_backup:
            raise
        backup = target.with_suffix(target.suffix + ".bak")
        try:
            return _read_one(backup), True
        except (OSError, ValueError, json.JSONDecodeError) as backup_error:
            if not target.exists() and not backup.exists():
                raise FileNotFoundError(str(target)) from primary_error
            raise ValueError("career save and backup are unusable (%s; %s)" %
                             (primary_error, backup_error)) from primary_error

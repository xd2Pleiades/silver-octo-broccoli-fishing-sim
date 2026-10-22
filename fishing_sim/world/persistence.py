"""Versioned, JSON-safe persistence primitives for world contact deltas.

Global career-save wiring is intentionally deferred until the existing game has a
single authoritative save format. These primitives are stable and independently tested.
"""
from __future__ import annotations
import json
from .traffic import TrafficWorld
from .weather_grid import WeatherGrid, WEATHER_SCHEMA_VERSION
from fishing_sim.systems.tow_escort import TowEscort, TOW_ESCORT_SCHEMA_VERSION

SCHEMA_VERSION = 1


def contact_snapshot(traffic: TrafficWorld) -> dict:
    data = traffic.snapshot_contacts()
    data["schema_version"] = SCHEMA_VERSION
    return data


def dumps_contact_snapshot(traffic: TrafficWorld) -> str:
    return json.dumps(contact_snapshot(traffic), sort_keys=True, separators=(",", ":"))


def restore_contact_snapshot(traffic: TrafficWorld, payload: str | bytes | dict) -> None:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid traffic contact snapshot JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("traffic contact snapshot must be a JSON object")
    if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("unsupported traffic contact snapshot schema")
    traffic.restore_contacts(payload)


def weather_snapshot(weather: WeatherGrid) -> dict:
    """Return a versioned, JSON-safe regional weather snapshot."""
    return weather.snapshot()


def dumps_weather_snapshot(weather: WeatherGrid) -> str:
    """Stable compact serialization for weather cell state."""
    return weather.dumps()


def restore_weather_snapshot(weather: WeatherGrid, payload: str | bytes | dict) -> None:
    """Restore a weather snapshot into an existing, matching grid configuration."""
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("invalid weather snapshot encoding") from exc
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid weather snapshot JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("weather snapshot must be a JSON object")
    if int(payload.get("schema_version", 0)) != WEATHER_SCHEMA_VERSION:
        raise ValueError("unsupported weather snapshot schema")
    weather.restore(payload)


# Tow/Coast Guard state has its own versioned schema. These helpers let the next
# career-save migration add the escort atomically without relying on pickle.
def tow_escort_snapshot(escort: TowEscort | None) -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "escort": None if escort is None else escort.snapshot()}


def dumps_tow_escort_snapshot(escort: TowEscort | None) -> str:
    return json.dumps(tow_escort_snapshot(escort), sort_keys=True, separators=(",", ":"))


def restore_tow_escort_snapshot(payload: str | bytes | dict) -> TowEscort | None:
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("invalid tow escort snapshot encoding") from exc
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid tow escort snapshot JSON") from exc
    if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("unsupported tow escort wrapper schema")
    escort_data = payload.get("escort")
    if escort_data is None:
        return None
    if not isinstance(escort_data, dict) or int(escort_data.get("schema_version", 0)) != TOW_ESCORT_SCHEMA_VERSION:
        raise ValueError("unsupported tow escort state schema")
    return TowEscort.from_snapshot(escort_data)

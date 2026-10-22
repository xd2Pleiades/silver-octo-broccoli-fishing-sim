# Career Save Format — v13.2.07

## File and controls

- Default file: `saves/career_v13_2.json` relative to the project root.
- Save: `Ctrl+S`. Load: `Ctrl+O`.
- Backup: `saves/career_v13_2.json.bak`.

## Envelope

The outer object contains `format`, `schema_version`, `game_version`, `payload_sha256`, and `payload`. The SHA-256 checksum covers canonical JSON for the payload (sorted keys, compact separators, UTF-8, non-finite values disallowed). The reader enforces a 32 MiB file limit and rejects unknown schema versions. This prevents accidental corruption from being mistaken for a valid save; it is not intended as an adversarial signature.

## Atomic write and recovery

Writes use a temporary file in the target directory, flush and fsync it, then replace the primary atomically. Before replacing a valid primary, the writer copies it to `.bak`. On load, a valid main file is preferred; if the main is missing or invalid, the loader attempts the backup. If a valid main exists but is semantically invalid in a future payload-level validator, the current load will fail safely; the loader does not silently choose a different career behind the player's back.

## Durable payload areas

- Game economics, fuel/ice/bait inventory and freshness, alternating hatch-selection state, engine condition, anchor/tow request and transit timers.
- World date/time, navigation beliefs, routes/waypoints, hotspot truth and fishing reports.
- Ship flooding/hatch/pump/free-surface data, slope and wave phase.
- Shipboard weather, regional weather-grid snapshot and forecasts derived after restore.
- AI contact relationship state, MAYDAY one-shot/outcome flags, and distress-dispatcher slot/counters.
- TowEscort captain/crew/route/line/check-in snapshot and its shared traffic contact.
- Crew members, morale/fatigue/health, duties, station owners, carry inventory and lost-crew set. Man-overboard launch state is persisted with sailor-name references for the target, rescue hands and passenger; the current alarm target, lifeline/rescue/alert references, unseen-overboard contacts and sighting timers are restored to the rebuilt roster. Muster targets/attendance/unavailability and bucket-chain crew/slots are also rebound by sailor identity. Mid-ladder progress is stored by stable ship-link index.
- Longline settings/points/claims/fight/gaff by stable hook index, plus historical gut-book notes and live hotspot references by index.
- Hold/table/deck fish and deck patches; derived object references are re-linked or reacquired.
- Radio histories, radio calls, pending radio requests, bubble/message state, radio instrument timers, and active/pending broadcast conversations with cursor/timers.
- Global pseudorandom generator state, restored last after reconstruction.

## Reconstruction policy

Pygame surfaces, caches, particles, seabird flock animation and transient cross-object AI references are not serialized. Those are rebuilt or allowed to reacquire targets after load. Longline/gaff/fight references use point indices, not raw object pointers. The game performs structural/subsystem validation before mutating, validates that rescue/muster/bucket-chain references point to sailors in the saved roster, and takes an in-memory pre-load snapshot to attempt rollback if reconstruction unexpectedly throws. Traffic contacts are validated as the dictionary snapshot the traffic subsystem actually emits, not as a list.

## Compatibility

Schema version is currently 1. Increase it for a released incompatible payload change and provide deterministic, idempotent migrations. The pre-v13.2.07 supplied project does not define an official legacy save format; no authentic v13.1.34 migration fixture is claimed.

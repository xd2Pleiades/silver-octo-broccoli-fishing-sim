# Changelog — v13.2.07

## Career persistence (M10 first integrated slice)

- Added checksummed, versioned JSON career-save envelope with 32 MiB bound.
- Added atomic save writes and last-known-good `.bak` recovery.
- Wired `Ctrl+S` save and `Ctrl+O` load into the game input handler without changing plain `O`.
- Save/restore now covers world/player navigation, hotspots/reports, hull flooding/hatches/slope and wave phase, local/weather-grid state, traffic contacts and distress flags, tow escort/captain/crew, crew roster/status/duties, longline hooks/fight/gaff, catches/inventory/patches, bait stock/freshness and hatch alternation, radio UI/history, pending radio calls, active/pending broadcast conversation cursor and timers, radio-system state, global PRNG state, and active man-overboard launch/casualty state.
- Muster expected/reporting crew, muster targets/unavailability, bucket-chain hands and slots, rescue-boat hands/passenger/engineer, man-overboard alarm target, lifeline holder/target links and crew sighting timers are stored as sailor-name references and rebound after roster restore. Mid-ladder progression is stored by stable ship-link index plus progress/positions.
- Fixed traffic snapshot payload validation to treat `traffic_contacts` as its emitted mapping instead of a list; the previous check would reject a valid whole-career save.
- Pre-validates weather, traffic, escort, broadcast queue and PRNG structures before mutation; attempts in-memory rollback if live reconstruction fails.
- Updated roadmap and Plan 13.2.xx implementation notes. All Markdown documents remain under `/docs`.

## Quality fixes

- Corrected tow radio acceptance code to bind the world reference before reading position/distance.
- Preserved ship hull-slope state across career saves.
- Added tests for non-finite payload rejection, broadcast cursor/time coverage, queue persistence contracts, rescue boat/casualty references, muster and bucket-chain rebinds, bait/hatch fields, traffic snapshot mapping validation, PRNG validation/order, and rollback wiring.

## Known limitations

- Pygame was unavailable; full live gameplay save/load could not be exercised.
- Pre-v13.2.07 project did not include an established official career-save format, so authentic v13.1.34 save migration is not claimed.
- Current save schema is version 1; future format changes must add explicit idempotent migrations and increment schema.

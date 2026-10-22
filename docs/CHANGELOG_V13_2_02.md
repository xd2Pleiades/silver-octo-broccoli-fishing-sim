# Changelog — v13.2.02

## Added — Selectable fleet radio UI

- Added a persistent **RADIO** HUD button next to the **ANCHOR** button.
- `Ctrl+F11` now opens the ship-to-ship radio panel; `F11` remains fullscreen.
- Added a nearby-vessel contact list sorted by distance, with vessel identity, activity, approximate range, and per-vessel in/out-of-range status.
- Added clickable conversation topics: hail, position, weather, activity, fishing grounds, crew, and vessel identification.
- Added paced transcript playback using **NEXT LINE**, Enter, or Space. Once the exchange completes, **NEXT SHIP** cycles through contacts.
- Added per-vessel bounded session history, radio-log entries for revealed turns, and explicit UI states for an unmanned radio set, busy frequency, out-of-range calls, and silence.
- Added topic-specific response text and interaction rules to `ShipRadioService.interact()`.
- Kept reported-position behavior separate from physical vessel positions; position questions return a reported fix, not a live chart leak.
- Updated controls and roadmap implementation status; added `docs/V13_2_02_RADIO_UI.md`.

## Preserved

- v13.2.01 deterministic traffic schedules, stable vessel IDs, spatial index, LOD limits, and ship-to-ship response foundation.
- v13.1.34 merged crew/captain-trip behavior and v13.1.33 Coast Guard placeholder hull, harbour approach, towline, and escort communications.
- `Ctrl+F11` no longer immediately fires an all-stations hail; it opens the interface so the player can choose who to call.

## Verification scope

- Dependency-free service tests, source-contract tests, Python compilation, and ZIP integrity checks are included in the release process.
- A graphical playtest is not claimed because Pygame is unavailable in the build environment.

# Fishing Simulator 12v18 — Persistent Sea Foam and Whitecaps

## Added
- Added `systems/sea_foam.py`, a headless-testable sea-foam model with a hard cap of 240 active patches by default.
- Added distinct persistent foam categories: stern wake, bow-shoulder foam, hull-side wash, short-lived spray/spindrift, and wave-crest whitecaps.
- Added weather-driven whitecap deposition using crest-energy samples from the existing `WaveField`. Whitecaps can form when the ship is stationary in rough weather.
- Stored foam patches in absolute water/world coordinates and applied camera-relative projection only during rendering. Old wake no longer rotates or teleports along with the ship.
- Added time-step emission, current/wind drift, lifetime fading, view-distance culling, and least-visible-patch recycling when the cap is reached.
- Drew the new foam with layered irregular polygons, fine lip highlights, and restrained bubbles on the existing transparent water overlay.

## Preserved
- Existing WaveField, steering, weather, ship physics, sea hazards, man-overboard rescue, rescue boat, bucket line, fish quality/hold, auction, crew AI, and HUD logic.
- `run_fishing_sim.py` and `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`.

## Verification
- 83 automated tests passed, including 8 new headless foam-model tests.
- All project Python files passed `py_compile`.
- ZIP archive integrity and required root files verified.
- No graphical playtest was possible in the build environment because Pygame is not installed. Visual verification should cover idle/calm, cruising/calm, stopped/storm, cruising/storm, and turning the ship.


### Hotfix 12v18.2 — 2026-10-21
- Fixed the sea-foam `shape_points()` renderer returning the old undefined name `pts`; it now returns the initialized `points` list consistently.
- Strengthened the source regression test to check list initialization, append, and return names together.

# Fishing Simulator V13V1-01 — Hotspot Ecology and Bite Integration

## Implemented

- Added a standalone, Pygame-free `Hotspot` model with species, strength, radius, lifetime, world-space drift, phase, detection placeholders, and fade during the final third of its life.
- Added bounded spawn selection (eight candidate attempts) and water validation against land, shallow water, mapped coastline clearance, and the reef. The first hotspot becomes eligible after 45–90 seconds; later spawn cooldowns are 90–150 seconds. Active hotspot count is capped at four.
- Schools drift at 2–8 world units/second. If a drift step would put a school on land or rejected shallow/coastal water, it stays in place and reverses direction.
- Integrated smooth distance-based multipliers into the existing `Longline.bite_weights()` calculation. Species-specific schools peak at 2.5× and mixed schools at 1.6×; overlapping spots do not stack multiplicatively.
- Preserved the existing depth, seabed habitat, temperature, time-of-day, bait-affinity, freshness, and weather-sensitive bite calculation. No separate catch roll or guaranteed catch was introduced.
- Added 11 focused headless tests for spawn selection/rejection, drift, decay, expiry, edge falloff, species affinity, overlap bounds, and integration contracts.

## Preserved

- 12v19 sea foam, ship physics, steering, weather, coast/reef collision, longline mechanics, crew AI, rescue, shore leave, auction/settlement, HUD, and existing launch files.
- Physical ship position remains the sole truth for movement/collision; the V13 believed-position model has not been introduced yet.

## Verification

- `python -m compileall -q fishing_sim run_fishing_sim.py` — passed.
- `python -m unittest discover -s fishing_sim/tests -v` — **98 tests passed**.
- Pygame graphical validation and catch-rate playtesting — not performed in this environment because Pygame is not installed.

## Known planned limitation

Hotspots currently affect catch probability but have no player-visible cue yet. This is intentional for milestone `v13v1-01`; physical water cues are scheduled for `v13v1-03`, after the static chart milestone.

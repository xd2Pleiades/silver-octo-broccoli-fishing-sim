# V13V1-03 — Physical Hotspot Cues, Minimap Removal, and Money HUD

## Implemented

- Added the four physical hotspot cue families from the V13 plan: green/blue water stain, stable-position flotsam, expanding/fading surface ripples, and working gull flocks.
- Cue layout is derived from each hotspot's stable phase and world position rather than per-frame random placement. Ripple animation advances with world time; bird orbit/flap animation is continuous.
- Cue strength scales with hotspot strength. Weather visibility dims cues, and daylight affects bird visibility. Existing validated offshore spawn/drift logic prevents the hotspot objects and cues from being placed on land.
- Capped cue rendering by the current four-hotspot limit, bounded gull count per hotspot, clamped water-tint radius, and culled cue centers outside the visible working area.
- Removed the minimap from rendering, resize allocation, click-to-steer handling, minimap zoom state, and HUD control hints. The static read-only chart remains available through **C**.
- Relocated the water-column profile to the former minimap area and updated fishing-bar geometry to avoid relying on minimap dimensions.
- Added a persistent money card showing current cash and cumulative earnings in yen. It remains visible when F8 hides compact telemetry and reflects the existing auction, settlement, supply purchases, wages, recruitment, and tow fees without introducing a second balance model.
- Updated the V13 roadmap, README, and regression tests. Retained the required launcher and ZIP preservation marker.

## Verification

- `python -m compileall -q fishing_sim run_fishing_sim.py` — passed.
- `python -m unittest discover -s fishing_sim/tests -v` — **118 tests passed**.
- Archive integrity and required root files — verified after packaging.
- Pygame was unavailable in the build environment; no live graphical playtest or FPS measurement is claimed. Verify cue readability during daylight, fog, night, and rough seas on Windows.

## Known scope boundary

The chart is still read-only. Waypoints and position fixes remain later roadmap milestones. With the minimap removed, players can use the existing helm arrows, autodock, and crew auto-fishing until chart waypoint interaction is implemented in `v13v1-05`.

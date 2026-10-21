# Fishing Simulator V13V1-02 — Static 1962 Navigation Chart

## Implemented

- Added `fishing_sim/systems/navigation_chart.py`, a Pygame-free chart geometry module containing map transforms, bounds/clamping, clipped course-segment geometry, deterministic sounding values, and surveyed-area sounding generation.
- Added a cached sepia navigation chart overlay with coastline and land fill, the harbour mouth, lighthouse, temple peak, reef, charted soundings in fathoms, a danger-marked reef and harbour-mouth shoal, dashed surveyed limit, uncharted-water hatching/labels, compass rose, nautical scale bar, and `VAR 6°E (1962)` note.
- Added a live yellow vessel-heading marker and a destination/course line using existing world state. This milestone intentionally uses the current physical ship position because `believed_pos` does not exist yet; milestone `v13v1-04` must switch chart-facing reads deliberately.
- Added **C** as the chart toggle and made the minimap caption clickable. Regular left-clicks on the minimap still set a destination; the chart itself captures clicks and remains read-only. **Esc**, **C**, or right-click closes it.
- Masked held gameplay keys while the chart is open so helm/brake/duty inputs do not leak through the overlay. Autonomous sailing/simulation continues.
- Invalidated cached cartography on window resize; static depth labels and chart geometry are built once per viewport size.
- Updated the README, roadmap status, package version, and preservation-compatible build contents.

## Tests and verification

From the extracted project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**112 automated tests pass**, including 14 new navigation-chart checks, and compilation passes. The chart geometry tests cover transform bounds, small surfaces, clipping, deterministic soundings, and exclusion of land from soundings. Source-contract checks verify input entry points, overlay draw integration, and that waypoint/fix behavior has not been prematurely added.

## Not verified / remaining limitations

- Pygame is unavailable in the build environment. Installation was attempted, but package retrieval failed because network name resolution was unavailable. No live graphical screenshots or mouse-driven playtest were possible.
- Before treating this as visually complete, verify minimum window size (640×420), default size (1280×800), map labels/side panel clipping, right-click/keyboard closing, unchanged minimap steering, and chart cache invalidation on resize.
- The static chart is not a working navigational solution yet. Dead reckoning, believed position, waypoints, and position-fix methods remain future milestones. Hotspot visuals remain milestone `v13v1-03`.

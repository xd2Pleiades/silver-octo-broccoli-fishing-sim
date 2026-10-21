# Fishing Simulator 13.1.24 — crew pathfinding, immersive helm orders, and larger waters

## Sailor pathfinding

- A* assigns additional cost to routes that skim hull boundaries, machinery, bunks, and open-rail edges, so sailors prefer safer clearance when space allows.
- The string-pulling pass now validates the final segment all the way to the actual task destination. Previously, the grid-centre path could be safe while the last appended segment clipped through a solid.
- The A* frontier discards stale, superseded entries and keeps diagonal corner-cut prevention.
- Crew progress is measured by distance-to-goal as well as speed. A sailor who is sliding sideways or pushing against an obstacle now requests a fresh route rather than being considered unstuck just because they still have velocity.

## Immersive ocean course orders

- Removed persistent route lines, waypoint rings, and predicted turn arcs from the live ocean view. The sea stays visually clean; chart lines remain on the chart table (C).
- Ocean course feedback is now a small instrument-style helm card: bearing, range, ETA, cross-track error, and wide-turn warnings are text, not markings painted onto the water. Drag preview is textual too.
- Persistent route waypoint editing is done on the visible chart rather than by clicking invisible ocean markers. Quick right-click steer-to and Shift + right-drag plotting remain available in clear, visible conditions.

## Nautical scale and chart range

- Corrected the ocean-course distance conversion from 1,852 to 185.2 design units per nautical mile (multiplied by world scale in world coordinates). The previous factor made displayed ocean ranges ten times too small and ETAs ten times too long.
- Raised the maximum ocean-space plotting envelope from 750 to 1,100 design units (about 5.9 NM); target range remains constrained by weather visibility and longer routes belong on the chart.
- Expanded the chart sheet to approximately 130 NM across and marked a 6,000-unit (about 32 NM) central radius as surveyed. The map now contains the far offshore grounds and additional water for longer deliberate legs. The useful chart takes more of the screen with a narrower information rail.
- Broadened chart grid/hatching loops to cover the expanded sheet and spaced soundings for legibility.

## Validation

- Added tests for path clearance, A* queue handling, final-segment safety, stuck-sailor re-planning, correct nautical conversion, larger chart bounds, and no overlay lines in the ocean view.
- Automated tests and compile/package checks are run on the release archive. A graphical Pygame playtest is still recommended where Pygame is installed.

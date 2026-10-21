# v13.1.24 — pathfinding and chart scale notes

## Ocean plot controls

- Right-click a visible patch of water: quick steer-to order.
- Shift + right-drag A to B: commit a route leg; the status card reports bearing/range/ETA without drawing a line across the water.
- Press `C` to open the paper chart for visible waypoint editing/commit. Press `Esc` in the ocean view to cancel a course or an in-progress plot.
- Ocean marks require daylight and adequate visibility. Use the chart for poor weather and long distances.

## Range conventions

The navigation chart uses 185.2 design units per nautical mile. Since live world coordinates are design coordinates multiplied by `World.scale`, the equivalent in world coordinates is `185.2 * world.scale`. All ocean quick-orders, plotted-leg readouts, and ETAs use that common conversion.

The chart sheet spans `(-12000, -10000)` to `(12000, 10000)` design units; 6,000 units from the harbour is shown as surveyed and waters beyond it remain uncharted. This expansion puts offshore grounds up to the existing spawning envelope on the sheet without claiming every part of the outer sheet has been surveyed.

## Crew routing

The deck navigation grid uses A* plus route string-pulling. Clearance costs bias paths toward safer space; diagonals cannot cut corners; line-of-sight simplification checks every segment including the final approach; crew re-plan if target distance stops improving even when lateral collision avoidance leaves them moving. When dynamic obstructions make a route temporarily unavailable, sailors stop rather than walk straight through solids and retry.

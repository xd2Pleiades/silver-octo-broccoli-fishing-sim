# V13V1-06 — Interactive Navigation Chart & Waypoint Plotting

**Built on:** `v13v1-05` Ship's Notebook / seasonal almanac / storm market release.  
**Status:** implemented; headless regression suite and compilation pass; graphical playtest still required.

## Added

- **Interactive 1962 chart:** the existing `C` chart now accepts route-planning input while still consuming gameplay controls so chart clicks cannot become deck orders.
- **Waypoint add/move:** left-click open water to add a point. Click an existing marker to select it, then click a new position to move it. Chart/design coordinates are the edit buffer's canonical coordinates; points do not drift when the screen is resized.
- **Insert / delete:** Shift-click near a route leg to insert a waypoint projected onto the leg. Right-click a waypoint to delete it from the staged course. Right-click empty chart closes without committing edits.
- **Commit / clear controls:** Enter commits and closes the chart. Escape clears the active manual course and edit buffer. `C` closes the chart without committing staged edits.
- **Route visualization:** numbered waypoint marks, ordered red course legs, per-leg nautical-mile distances, active waypoint count, and concise help/status text.
- **Bounded route editor:** maximum eight waypoints. Out-of-chart, duplicate, and near-zero-leg points are rejected. Points are stored in map coordinates until commit, then converted to world-space steering targets.
- **Ordered autopilot:** the helm steers to the next waypoint, removes each reached waypoint, and continues in order. Completion, route commitment, cancellation, and waypoint arrivals are recorded in the Ship's Notebook crew log.
- **Explicit conflict policy:** the source plan gives `L` auto-fishing priority over manual routes. Enabling auto-fishing cancels a committed route with a crew message and log entry. Manual route commit is blocked while auto-fishing is active. Docking and man-overboard rescue retain priority.
- **Safety integration:** `World.set_destination()` clears a manual route when a new unrelated destination is issued unless route progression explicitly preserves it. Chart input is isolated from ordinary gameplay input.

## Controls

- **C** — open/close chart
- **Left-click open chart water** — add waypoint
- **Left-click waypoint, then open water** — move waypoint
- **Shift + left-click on route leg** — insert waypoint into the leg
- **Right-click waypoint** — delete waypoint from the staged route
- **Right-click empty chart** — close without committing
- **Enter** — commit the staged course and close
- **Esc** — clear the manual course

If auto-fishing is in command, turn it off before committing a manual route. Chart plotting is a plan, not a teleport: the vessel continues moving only through the existing physical/autopilot update.

## Verification

- **165 automated tests passed** from the project root.
- Python compilation passed with `python -m compileall -q fishing_sim run_fishing_sim.py`.
- The ZIP release gate includes a fresh extraction, compilation, test run, and required launcher/preservation-file checks.
- **Not verified:** live Pygame visuals and actual helm pathfinding because Pygame is unavailable in the build environment. Perform a Windows playtest for click accuracy at different window sizes, route leg-label readability, waypoint arrival, and auto-fishing transitions.

## Next milestone

`v13v1-07` — position fixes: landmark bearing, sextant, radio direction finding (RDF), and echo-sounder checks, with conditions, staffing costs, and uncertainty reduction. Do not let a failed fix reveal the hidden true position.

# Phase B Campaign UI — v13.2.11

## Open the wide-area chart

Press `C`, then choose `B / HIGH SEAS` in the upper-right of the chart or press `B` while the chart is open. Use `A / REGIONAL` or `A` to return to the Hakodate regional sheet. The game’s regular world HUD and ship operation controls remain unchanged.

## Plot a route

Click open water to add a waypoint. Shift-click a leg to insert a waypoint, click an existing point and then click a new location to move it, or right-click a waypoint to delete it. Press Enter to commit the route; Esc clears the staged route. Route waypoints are stored in the existing physical chart coordinate system and projected to Phase B for display, so existing helm/autopilot behavior remains the executor.

## Select and hail a vessel

Phase B displays known reports, not the entire truth-state fleet. A marker may be stale (`?`); its label is based on the last report timestamp. Click a marker to select it. Press `R` to open the standard radio interface for that contact if the reported plot is within its declared radio range. The existing operator, clarity, personality, and topic rules still apply.

## Coordinate and persistence notes

The high-seas chart uses east-positive projected nautical miles and north-positive world Y; chart screen Y points down and is inverted at the drawing/input boundary. `phase_adapter.py` converts between that plane and the legacy Hakodate-local physics plane. The player’s chart marker uses the crew’s believed position, and contact markers use last reported positions.

Switching phases keeps separate traffic/weather/relationship caches. A career save stores the active phase plus a snapshot for the inactive phase if it has already been visited. When Phase B is entered for the first time, its grid starts its live epoch at that point in career time; the weather is not retroactively integrated for unseen history.

## Limits

The Phase B coastline is schematic, not a surveyed chart. Global currents, world-spanning collision and bathymetry are not implemented; actual hull physics continues to use the legacy local plane through the adapter. Phase B's default weather grid is 80 NM cells; the 20 NM version remains a profiling option. Pygame visual QA is still required.

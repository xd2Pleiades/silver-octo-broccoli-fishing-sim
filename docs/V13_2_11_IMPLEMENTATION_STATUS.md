# v13.2.11 Implementation Status — Phase B Campaign UI

## Implemented

- Live campaign chart can switch between regional Phase A and wide-area Phase B using clickable tabs or A/B keys while the chart is open.
- Phase B chart raster is cached by viewport size and includes schematic coastlines, graticule, the historical salmon fleet operating area, regional reference positions, and an approximate-chart warning.
- Known contacts render from their last reported positions only. Stale plots show `?`, the 24 nearest contact labels are prioritized, and marker hitboxes remain selectable.
- Selecting a known Phase B marker and pressing `R` opens the existing radio UI for that vessel if its last reported position is inside stated radio range.
- Chart route points can be added, moved, inserted and deleted on the wider Phase B map. They are converted back into the existing physical coordinate plane before being committed.
- Player/traffic/tow coordinates are converted by a central phase adapter so the Coast Guard identity is not duplicated when the active chart phase changes.
- Phase A/B cache traffic world, regional weather grid and relationship baseline independently. Career saves persist the active phase and optional inactive phase snapshots; restore validates phase tags and regenerates deterministic scheduled fleets before applying saved contact deltas.
- First visit to Phase B rebases its weather epoch to the current simulation time; this avoids replaying thousands of weather steps that occurred before that phase existed in the career.

## Explicitly not complete

- Pygame hull physics remains on the legacy Hakodate-local coordinate plane. The adapter keeps chart/traffic/report coordinates consistent, but does not implement a global Earth-coordinate movement solver.
- Coastline and land shapes are intentionally schematic and not suitable as surveyed navigation data.
- Global currents, global bathymetry, shoreline collision/avoidance and fully geographic sea-view geometry remain future work.
- Phase B still uses an 80-NM coarse weather grid by default. The 20-NM grid is profiling-only pending performance proof.
- No live graphical test was possible because Pygame was not installed.

## Controls

- `C`: open/close chart.
- `A` / `B` while chart is open, or click the chart tabs: choose regional/high-seas sheet.
- Click a reported contact on the Phase B chart: select it.
- `R` while the Phase B chart is open: open radio UI for the selected in-range contact.
- Left click open water: stage waypoint; Shift-left click route leg: insert; right-click waypoint: delete; Enter commits; Esc clears staged route.

## Verification

See `TEST_RESULTS_V13_2_11.txt`. Tests cover projection adapters, high-seas route bounds, A/B chart event wiring, sea-view/tow adapter use, weather rebase, and inactive-phase save/load source contracts. Rendering and mouse behavior still require graphical QA in a Pygame-enabled environment.

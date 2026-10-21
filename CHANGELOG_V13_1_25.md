# v13.1.25 — Hauling alignment, hatch automation, and right-click actions

## Deck operations
- During the final part of a haul, the ship gradually presents its starboard aft-quarter pickup point to the line/drum roller while speed falls off. It uses the actual haul pickup offset rather than aiming the bow at the buoy.
- Marker buoys and line spans can foul the starboard-quarter stern gear during hauling. Fouling pauses the winch, wears the line slightly, produces a crew warning, and clears after a short interval; a deckhand at the stern can clear it immediately.
- Sailors carrying dressed fish now dog the ice-hold hatch open when they reach it, stow the catch, then close the hatch automatically. Context-menu hatch orders also send a sailor to a reachable hatch and perform the requested operation there.
- Bow-end pathing now resolves unreachable targets to the nearest safe endpoint in the sailor’s connected navigation area and measures arrival against that endpoint. The existing hull-clearance margin remains intact.
- Corrected the hold-ladder link to operate the ice-hold hatch at the ladder’s actual location. Sailors stowing dressed fish automatically open the relevant hatch, unload, then close it when the ladder is clear.

## Navigation and course orders
- Ocean steer-to remains usable in storms and poor visibility with a weather-reduced range. While manually soaking or hauling, a short steer-to is allowed but a persistent A→B leg waits until the line is secured; auto-fishing still retains the helm priority. Long legs belong on the chart.
- Completed plotted legs discard the stale A→B origin along with the waypoints, leaving only the ship’s slow-ahead/hold-heading behaviour. Short ocean steer-to remains possible in a storm at a reduced range, including during manual soaking/hauling; persistent plotted legs still wait until the line is secured.

## Right-click context menu
- Right-click visible sailors for selection and duty assignments.
- Right-click ice-hold/engine hatches to order open/close, with a physical sailor walking to the cover.
- Right-click the hauler, stern roller, or visible buoy/line to inspect gear, begin hauling where available, assign work, or clear a snag.
- Empty water still means steer-to; right-clicking empty walkable deck opens a small DECK ORDER menu for moving a sailor or assigning available fishing/engine-watch duties.

## Verification
All 375 automated tests passed across grouped runs. A single all-tests discovery run exceeded this environment’s watchdog, so the suite was split into batches; every batch completed successfully. Python compilation and ZIP integrity checks passed. Pygame is not installed in the build environment, so a graphical playtest could not be performed.

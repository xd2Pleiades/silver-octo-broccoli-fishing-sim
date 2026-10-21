# v13.1.23 — Ocean plotting and ship-handling notes

## Controls

These controls apply from the exterior working-deck view, not from an interior cutaway.

| Input | Result |
|---|---|
| Right-click visible ocean water | One-off **steer-to** bearing order; a temporary mark, not a saved A→B route |
| Shift + right-drag from A to B | Preview, then commit a persistent ocean leg on mouse release |
| Shift + right-drag an existing waypoint | Reposition the waypoint and update the route |
| Right-click an existing waypoint/steer mark | Delete that waypoint or mark |
| `Esc` with a route or mark active | Clear the ocean/chart course; with no active course, normal Escape behavior applies |
| `C` | Open the navigation chart; use it for longer legs or poor visibility |

Ocean plotting requires the working-deck view, sufficient daylight, fog no greater than 0.32, rain no greater than 0.38, and visibility of at least 4.5 km. The maximum click range is capped at 750 design units (about 0.4 nautical mile), reduced further when visibility is poorer. This lets a player point out nearby visible water without selecting a destination beyond the horizon. The chart remains the deliberate plotting tool when the sea cannot be seen clearly.

## Track versus path

Ocean and chart plotting use the same `World.route_waypoints` representation. The estimated position (`believed_pos`) is the navigation reference, not a reveal of the hidden true-position error. A leg carries a bearing and distance; the UI previews approximate ETA and turn shape, and shows cross-track error while the route is active. Edge clicks can extend a mark past the viewport, but still obey the nearby-water range cap.

The helmsman works a fallible track rather than moving the ship along a geometric line. Corrections are weighted by helmsman skill and estimated-position cross-track error. Rudder travel is rate-limited, steering authority falls away at low speed, the single-screw engine needs neutral time and low headway before reversing, and wind/current plus a small asymmetric reverse prop-walk term set the ship off the desired line. The order is not executed without a qualified person at the helm and a usable engine. On completing a persistent leg, the ship reduces to slow ahead and holds its heading for further orders rather than continuing at full speed.

The engine telegraph presents readable orders (STOP, SLOW AHEAD, HALF AHEAD, FULL AHEAD, ASTERN, STOP / ASTERN, and REVERSING — WAIT). The physical speed is still affected by engine power, sea state, inertia and environmental set.

## Rescue and lower-deck layout

When the rescue launch is unavailable in a storm, the captain begins turning back while speed falls, then creeps toward the swimmer to present the starboard rail. Assembly, launch, pickup, and return timing were shortened; waves still reduce small-boat performance.

The lower-deck plan is now stern-to-bow: aft stores, engine room, ice hold, crew cabin, forepeak. Engine access is aligned to the aft machinery space; fish-hold hatches sit over the amidships hold; six bunks line the cabin sides. One clear centre passage connects the compartments, with the machinery casing and compact gauge bank kept to the passage sides.

## Implementation and testing

- `fishing_sim/systems/navigation.py`: bearing, distance, ETA, leg projection, cross-track and arrival geometry.
- `fishing_sim/systems/helm.py`: engine telegraph labels, angular error, finite rudder movement, fallible track correction and turn preview.
- `fishing_sim/ui/ocean_plot.py`: visibility rules, screen-to-relative mapping and bounded edge extension.
- `fishing_sim/core/game.py`: input/event integration, drawing, motion model, route controller, and storm rescue steering.

Run `python -m compileall -q fishing_sim run_fishing_sim.py` and `python -m unittest discover -s fishing_sim/tests` from the project root. Pygame was not available in the build environment, so these automated checks do not substitute for a graphical playtest.

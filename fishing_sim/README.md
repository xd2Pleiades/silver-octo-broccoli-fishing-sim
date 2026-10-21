# Fishing Simulator — v13.1.31 notes

- Tow requests now escalate after repeated unanswered offshore calls, reducing the chance of waiting several in-game days for a response.
- The automatic adrift timer checks speed through water separately from current/wind-driven movement and recognizes engine-health/power failures.
- Press **F12** to toggle one-line-per-simulation-second tow diagnostics in the launch console (`fuel`, `stw`, `sog`, adrift timer, anchor, request state, failed calls).
- The proposed full distress-radio conversation model is documented in `../docs/TOW_REQUEST_AND_DISTRESS_RADIO.md`; it is a design guide, not a claim that the complete responder state machine is implemented.
- Read `../docs/TOW_TRIGGER_DIAGNOSIS.md` for the April 5–9 delayed-response investigation and `../CONTROLS.md` for the full controls list.

---

## v13.1.31 controls reference

- Open the full in-game controls list with `F1` → `CONTROLS`.
- The same keyboard and mouse reference is in [`CONTROLS.md`](CONTROLS.md).
- See [`CHANGELOG_V13_1_29.md`](CHANGELOG_V13_1_29.md) for this release.

## v13.1.25 release notes

- Safer clearance-aware sailor A* routing, reachable bow-end arrivals, and more reliable replanning when obstructed.
- During hauling, the helm gradually presents the starboard aft quarter to the line; buoys/mainline can snag the roller, and a deckhand can clear the fouling.
- Fish-stowing sailors automatically open and close the correct ice-hold hatch.
- Right-click menus handle crew, hatches, fishing gear, and empty-deck work orders.
- Short steer-to orders remain usable in storms with reduced range, and completed ocean plots clear themselves.
- Ocean course orders no longer draw route lines/markers/turn arcs over the sea; use the paper chart (`C`) to inspect and edit plotted legs.
- Fixed a tenfold nautical-mile conversion error and expanded the chart to a 6,000-unit surveyed radius with much more offshore water.
- See `CHANGELOG_V13_1_25.md` and `docs/V13_1_25_DECK_OPERATIONS_AND_CONTEXT_MENU.md`.

# Fishing Simulator 13.1.23 — lower-deck, rescue, and navigation refit

This release reorganizes the lower deck into a stern-to-bow working plan (aft stores, engine room, ice hold, crew cabin, forepeak), keeps a continuous centre passage, and places the engine hatch directly over the machinery space. It also improves storm swimmer rescue behavior and adds visible-water quick orders plus Shift-drag ocean plotting.

## Navigation controls

- Right-click visible water on the working deck to issue a quick steer-to bearing.
- Hold `Shift` and right-drag A→B to commit a plotted leg. Shift-drag a waypoint to move it; right-click one to delete it; `Esc` clears a course.
- Ocean plotting requires daylight and clear visibility and is capped to nearby water. Use `C` for chart plotting at night, in poor weather, or for longer distances.
- Plot lines are intended tracks, not rails. Rudder lag, engine reversal delay, momentum, current, wind, and helmsman skill affect the actual path.

Read `../CHANGELOG_V13_1_23.md` and `../docs/V13_1_23_NAVIGATION_REFIT.md` for details. Earlier releases remain documented in the prior changelogs and `../Roadmap_V2.md`.

## Validation

Run `python -m compileall -q fishing_sim run_fishing_sim.py` and `python -m unittest discover -s fishing_sim/tests` from the project root. Pygame was not installed in the build environment, so a visual launch could not be checked here.

# Fishing Simulator — v13.2.13 merged working build

## Current working build

This build keeps the v13.2.13 systems baseline (physical player-vessel assistance, autonomous AI-fleet distress response, career persistence, selectable ship radio, Phase A/B traffic and weather, and release hardening) and merges the earlier full ship overhaul. See [Ship Overhaul Integration](SHIP_OVERHAUL_MERGE_V13_2_13.md) for the compartment layout, preserved systems and validation limits, and [AI Distress Response](AI_DISTRESS_RESPONSE_V13_2_13.md) for the new M9 response flow. It also retains the v13.2.11 Phase B high-seas chart integration: Press `C` to open the navigation chart and use the `A / REGIONAL` and `B / HIGH SEAS` tabs (or keys `A` / `B` while the chart is open) to switch sheets. On the Phase B sheet, click a known reported vessel to select it and press `R` to open the radio panel for that vessel when it is within radio range.

- **High-seas bounds:** 140°E–175°W and 41°N–62°N, projected around 160°E/45°N with date-line continuity.
- **Fleet:** 461 deterministic vessel identities, 11 mothership anchors, clustered catcher-boat schedules, and the existing active-vessel cap of 30.
- **Route plotting:** Phase B chart clicks convert to the legacy physical waypoint plane; routes are still intended tracks, not rails. The Phase B coastline is schematic and marked approximate, not surveyed.
- **Phase switching:** traffic, weather, and social state are cached separately by phase. The Phase B regional weather grid begins when first visited; it is not retroactively simulated for the entire earlier career.
- **Career saves:** the active phase and previously visited inactive-phase snapshots are included and validated, while older saves default to Phase A.
- **Weather:** Phase A retains its 20-NM grid. Phase B remains 80-NM coarse by default; full-resolution 20-NM weather has not been approved as default.

## Known boundaries

- The larger 1650 × 420 ship and revised lower-deck compartments have source-contract and headless navigation coverage, but still need a Pygame visual/pathfinding playtest.
- Autonomous AI distress response has headless dispatch, steering, outcome and snapshot coverage, but its live chart/radio presentation and full career-save round trip still need Pygame-enabled QA.

- Hull movement/physics still uses the legacy Hakodate-local plane via a coordinate adapter. This release does not yet implement globally accurate currents, bathymetry, shoreline/collision geometry, or a full world-map physical solver.
- Phase B coastlines and some landmarks are approximate. Use them as a campaign overview, not as a surveyed navigational chart.
- The Phase B 20-NM weather grid still requires performance profiling; Pygame-enabled visual QA of tabs, plotting, chart contact picking and save/load is also pending.
- Pygame was unavailable in the build environment, so this release was not launched for live graphical testing.

## Key documentation

- [Ship Overhaul Integration](SHIP_OVERHAUL_MERGE_V13_2_13.md) — what was merged from the older ship-redesign prototype and what remains unverified.
- [AI Distress Response](AI_DISTRESS_RESPONSE_V13_2_13.md) — autonomous response timing, vessel selection, physically steered interception, persistence and QA limits.

- [`Plan 13.2.xx.md`](Plan%2013.2.xx.md) — original source plan plus implementation tracker.
- [`Roadmap_V13_2_Optimized.md`](Roadmap_V13_2_Optimized.md) — milestone order, current state, and acceptance criteria.
- [`V13_2_11_IMPLEMENTATION_STATUS.md`](V13_2_11_IMPLEMENTATION_STATUS.md) — feature-by-feature implementation details.
- [`PHASE_B_CAMPAIGN_UI_V13_2_11.md`](PHASE_B_CAMPAIGN_UI_V13_2_11.md) — use, coordinate conventions, and limitations of the high-seas chart.
- [`CHANGELOG_V13_2_11.md`](CHANGELOG_V13_2_11.md) — release changes.
- [`CONTROLS.md`](CONTROLS.md) — complete control reference.

All Markdown files are stored directly under `/docs`; do not run `.md` files with Python.

## Launch and validation

From the project root, install dependencies from `fishing_sim/requirements.txt` and run `python run_fishing_sim.py`. Validate syntax with `python -m compileall -q fishing_sim run_fishing_sim.py`. Test suites and source-level acceptance checks are listed in `TEST_RESULTS_V13_2_11.txt`.

---

## Previous release notes

# Fishing Simulator — v13.1.31 notes

- Tow requests now escalate after repeated unanswered offshore calls, reducing the chance of waiting several in-game days for a response.
- The automatic adrift timer checks speed through water separately from current/wind-driven movement and recognizes engine-health/power failures.
- Press **F12** to toggle one-line-per-simulation-second tow diagnostics in the launch console (`fuel`, `stw`, `sog`, adrift timer, anchor, request state, failed calls).
- The proposed full distress-radio conversation model is documented in [`TOW_REQUEST_AND_DISTRESS_RADIO.md`](TOW_REQUEST_AND_DISTRESS_RADIO.md); it is a design guide, not a claim that the complete responder state machine is implemented.
- Read [`TOW_TRIGGER_DIAGNOSIS.md`](TOW_TRIGGER_DIAGNOSIS.md) for the April 5–9 delayed-response investigation and [`CONTROLS.md`](CONTROLS.md) for the full controls list.

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
- See [`CHANGELOG_V13_1_25.md`](CHANGELOG_V13_1_25.md) and [`V13_1_25_DECK_OPERATIONS_AND_CONTEXT_MENU.md`](V13_1_25_DECK_OPERATIONS_AND_CONTEXT_MENU.md).

# Fishing Simulator 13.1.23 — lower-deck, rescue, and navigation refit

This release reorganizes the lower deck into a stern-to-bow working plan (aft stores, engine room, ice hold, crew cabin, forepeak), keeps a continuous centre passage, and places the engine hatch directly over the machinery space. It also improves storm swimmer rescue behavior and adds visible-water quick orders plus Shift-drag ocean plotting.

## Navigation controls

- Right-click visible water on the working deck to issue a quick steer-to bearing.
- Hold `Shift` and right-drag A→B to commit a plotted leg. Shift-drag a waypoint to move it; right-click one to delete it; `Esc` clears a course.
- Ocean plotting requires daylight and clear visibility and is capped to nearby water. Use `C` for chart plotting at night, in poor weather, or for longer distances.
- Plot lines are intended tracks, not rails. Rudder lag, engine reversal delay, momentum, current, wind, and helmsman skill affect the actual path.

Read [`CHANGELOG_V13_1_23.md`](CHANGELOG_V13_1_23.md) and [`V13_1_23_NAVIGATION_REFIT.md`](V13_1_23_NAVIGATION_REFIT.md) for details. Earlier releases remain documented in the prior changelogs and [`Roadmap_V2.md`](Roadmap_V2.md).

## Validation

Run `python -m compileall -q fishing_sim run_fishing_sim.py` and `python -m unittest discover -s fishing_sim/tests` from the project root. Pygame was not installed in the build environment, so a visual launch could not be checked here.

# Fishing Simulator — v13.2.05

## Current release

This release merges the uploaded v13.2.04 WIP's sea/hull interaction work into the current branch and implements the first M9 distress/MAYDAY interaction slice from `Plan 13.2.xx.md` and `Roadmap_V13_2_Optimized.md`.

- **Hull and sea interaction:** procedural waves move the hull through heave, pitch and roll; wave impacts can slap or overtop the rails, create bounded water ripples and deck foam, add water aboard, affect trim/freeboard, and feed the flooding model.
- **Flooding response:** the bilge pump works when power is available; scuppers drain deck water, open hatches allow water transfer, and free-surface water affects list and stability. Crew can form a bucket line and bail physically accessible lower-deck compartments. Severe foundering triggers the existing abandon-ship/rescue-boat/swimmer flow.
- **AI MAYDAY dispatcher:** low-frequency deterministic dispatch considers vessels in radio range even if they are coarse/non-rendered. A ship sends one MAYDAY per incident, reports an uncertain position, and can be promoted to the bounded rescue-contact set.
- **Player decision:** while the radio is staffed, a received MAYDAY interrupts routine radio traffic. Select the source vessel and choose **ASSIST** or **IGNORE** (keyboard `A` / `I` while the active distress is selected). Relationship effects are idempotent: assist `+0.40` trust; ignore `-0.50` trust. The transcript records the response or silence.
- **Existing v13.2 foundation retained:** deterministic Phase A traffic, the fleet radio UI (`Ctrl+F11`), regional weather grid, Coast Guard escort's shared identity, harbour-to-vessel tow approach and existing tow retries.

## Known boundaries

- The MAYDAY assist action currently records a response and trust effect; it does **not yet dispatch an actual AI rescue boat or physically tow/intercept the distressed ship**. That is follow-on rescue-outcome work.
- Standalone traffic/escort snapshots have versioned helpers, but the legacy global career save/load flow has not yet been fully migrated to persist all new weather, distress, and escort data together. M10 remains outstanding.
- The weather grid's previously measured mean tick is above the 2 ms target; do not expand to Phase B until it is profiled/optimized.
- Pygame was unavailable in the build environment, so no live graphical playtest was possible.

## Controls

- `Ctrl+F11`: open/close fleet radio.
- Select a vessel; for a received MAYDAY, choose **ASSIST** or **IGNORE**. `A` and `I` are shortcuts while the distress is active and selected.
- `C`: navigation chart; `F1` → Telemetry shows flooding/reserve buoyancy/list; `F8` shows the compact telemetry HUD.
- Severe wave boarding and flooding are automatic. Keep hatches dogged when possible, keep engine power available for the bilge pump, and have healthy crew available to bail water from the affected room/deck.
- `F11`: fullscreen. `F12`: tow diagnostics.

## Key documentation

- [`Plan 13.2.xx.md`](Plan%2013.2.xx.md) — original source plan.
- [`Roadmap_V13_2_Optimized.md`](Roadmap_V13_2_Optimized.md) — phased roadmap and status.
- [`V13_2_05_IMPLEMENTATION_STATUS.md`](V13_2_05_IMPLEMENTATION_STATUS.md) — implemented/deferred boundary.
- [`MERGE_REPORT_V13_2_05.md`](MERGE_REPORT_V13_2_05.md) — what was merged from the WIP archive.
- [`CONTROLS.md`](CONTROLS.md) — full input reference.

All Markdown files are stored directly under `/docs`; do not execute `.md` files with Python.

## Launch and validation

From the project root, install the dependencies listed in `fishing_sim/requirements.txt` and run `python run_fishing_sim.py`.
Validate syntax with `python -m compileall -q fishing_sim run_fishing_sim.py`. Focused regression results are recorded in [`TEST_RESULTS_V13_2_05.txt`](TEST_RESULTS_V13_2_05.txt).

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

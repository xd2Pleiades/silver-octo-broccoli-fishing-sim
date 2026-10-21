
## Ship structure / Roadmap V2 cross-reference

As of `v13.1.21`, the structural ship-refit roadmap is tracked in `Roadmap_V2.md`: Phases 3–6 are implemented, covering the wheelhouse roof cutaway, engine service checks and bunk-based rest, hatch/bilge/processing and ice-hold systems, and load-dependent hauler/roller mechanics. Phase 7 remains polish and tuning. The single-file path named in that document is represented in this distribution by the modular `fishing_sim/core/game.py` implementation.

---

# Fishing Simulator — V13V1 Implementation Roadmap

**Basis:** the supplied [`docs/v13 Plans.md`](docs/v13%20Plans.md), titled *World Navigation & Fishing Awareness*. This roadmap converts its ten implementation layers into small releases named `v13v1-01` through `v13v1-19`, plus structural phases 3–6 in `Roadmap_V2.md`, alongside a separate ship-structure track in `Roadmap_V2.md`. The supplied Broadcast Conversations Catalogue is treated as a new priority milestone after the cue-scale playtest feedback; position-fixing shifts one release later. It does not claim that V13 features already exist in 12v19.

**Current baseline:** `12v19` has a refined, persistent sea-foam system. V13 is a new gameplay line focused on *where the ship believes it is* and *how the crew finds productive water*. The existing ship physics, longline ecology, weather, crew, and operating UI should be extended, not replaced.

**Phase 6 status:** `v13.1.20` completed structural Phase 6 from `Roadmap_V2.md`: load- and engine-dependent hauler slip, working/bypassed/jammed stern roller states, chafe/snags, line condition and parting risk, unharnessed whip injury, and visible gear-state feedback. It retains Phase 3–5 work, the rewritten sailor painter, performance caches, and persistent `cache/errors/` diagnostics. **325 headless tests and Python compilation pass**; Pygame is unavailable here, so visual gear feedback and live haul/set tuning still need a graphical playtest.

## V13 design rules

1. **Truth and belief stay separate.** `ship_pos` remains the physical truth used for movement, collision, land avoidance, and existing simulation physics. Add `believed_pos` as a parallel navigation estimate first. Do not globally replace reads of `ship_pos` with belief. Switch chart and crew-facing systems deliberately, one layer at a time.
2. **The player sees belief, not truth.** Navigation errors should be learned from contradictory bearings, soundings, and landmarks—not from a HUD that reveals the true error vector. Internally, tests may inspect both states.
3. **Fish cues are physical.** Hotspots are world-space, species-affiliated, temporary concentrations. Birds, water tint, flotsam, ripples, and crew intuition expose them; no permanent quest-marker should reveal every hotspot.
4. **Preserve the longline model.** Depth, temperature, bait, time of day, and weather still determine suitable species. Hotspots multiply bite chances only inside the existing species/habitat envelope; they must not replace those rules.
5. **Crew skill is shared.** The same skill values affect lookout range, reports, navigation quality, fishing, and work. Staffing a radio or navigation task has an opportunity cost to other shipboard work.
6. **Each milestone is independently testable.** Keep navigation and fishing modules as separable as possible. Add focused headless tests, retain the existing full suite, compile the project, and record what still needs visual playtesting.

## Milestones

### `v13v1-01` — Hotspot ecology and bite-weight integration — IMPLEMENTED
**Source:** Part B, §§B1–B4; implementation layer D1.1.

Implement `Hotspot` and `World.hotspots`; spawn, drift, age, decay, and remove temporary fish concentrations. Give each spot a species (`albacore`, `yellowfin`, `bigeye`, `swordfish`, or `mixed`), strength, radius, lifetime, and drift. Integrate a smooth distance falloff into existing `Longline.bite_weights()`.

**Original V13V1-01 values:** the first draft used a 45–90 second initial timer, 90–150 seconds between spawns, and eight random candidate attempts. Later releases retuned spawn timing/retries and added a current-area and deterministic fallback search in V13V1-15. The unchanged ecology bounds are a four-hotspot cap, strength 0.4–1.0, radius 1,200–2,200 world units, life 420–900 seconds, drift at 2–8 world units/sec, and decay during the final third.

**Bite modifier:** a matching-species school peaks at 2.5×; a mixed school peaks at 1.6×. The strongest applicable modifier is selected rather than multiplying overlapping hotspots together. The modifier is multiplied into the existing ecology, bait, temperature, depth, time-of-day, and freshness weight; it does not add a separate bite roll.

**Acceptance status:** completed for this milestone. Eleven focused headless tests cover spawn selection/rejection, drift and expiry, fade, coast avoidance behavior, radial falloff, species affinity, overlap bounds, and the `Longline.bite_weights()` integration contract. Full project suite at the end of v13v1-01: 98 tests passed; compilation passed. Live graphical and catch-rate playtesting remains outstanding. Hotspot cues are intentionally deferred to milestone `v13v1-03`.

### `v13v1-02` — Static 1962 navigation chart — IMPLEMENTED
**Source:** Part A, §§A4 and A8; implementation layer D1.2.

Add a chart overlay accessed from the minimap, initially read-only. Render sepia/coastal cartography: mapped coastline and named landmarks at charted/true positions, charted soundings, ship icon, course/destination line, compass rose, scale bar, and danger/restricted outlines. Use the stated aged-cream, faded-teal, warm-beige, dark-brown, and muted-brick palette. Mark water beyond the known radius as uncharted.

**Implementation at release:** `C` opened/closes the chart, the minimap caption was an alternate entry point, and minimap clicks set the current destination in `v13v1-02`. Those minimap interactions were deliberately removed in `v13v1-03`; `v13v1-02` itself remained a static chart. In `v13v1-06` the chart becomes interactive: `C` opens/closes; Enter commits a route; Escape clears the active course; right-click on a waypoint deletes it in the edit buffer; right-click empty chart closes without committing. Cartography is cached until the window/chart viewport is resized. Soundings are generated deterministically from the existing seabed-depth model with stable survey variation. The coastline, harbour mouth, lighthouse, temple peak, reef, soundings, compass rose, scale bar, danger marks, and surveyed boundary use the plan's 1962 palette. `v13v1-04` switched chart-facing vessel state to `believed_pos` and believed heading without changing physics reads of `ship_pos`.

**Acceptance status at v13v1-02:** the original milestone's code-level checks passed, soundings were deterministic, and chart geometry clipped out-of-sheet segments. Waypoint plotting was intentionally deferred then; it is now implemented in `v13v1-06`. Position fixes are implemented in `v13v1-09`. Pygame is unavailable in the current build environment, so interactive visual readability and live resize behavior still need a Windows graphical playtest.

### `v13v1-03` — Physical hotspot cues — IMPLEMENTED
**Source:** Part B, §B5; implementation layer D1.3.

Draw four independent cues around a hotspot: working bird flocks, subtle green/blue water tint, small flotsam, and expanding/fading surface ripples. Scale density and cue strength with the hotspot's remaining strength. Keep hotspots visually distinct from birds that merely follow the vessel's stern; draw water cues before HUD panels and ship/crew sprites.

**Implementation:** `Game.draw_hotspot_cues()` renders a restrained green/blue water stain, deterministic phase-derived debris positions, expanding/fading ripples, and fixed-count orbiting gulls. It uses each hotspot's existing world position and strength; it does not reveal a permanent marker or bypass lookout confidence. Cue alpha responds to weather visibility and daylight, and cue positions do not rely on per-frame randomness. Visual rendering is limited to the four-hotspot cap and culls schools outside their visible cue radius. The minimap has been removed from screen rendering, sizing, click-steering input, and key hints; the chart remains available with `C`. A persistent top-right balance panel shows `CASH ¥...` and `TOTAL EARNED ¥...`, updating from the existing economy variables and staying visible when F8 hides compact telemetry. The line-depth profile has been moved into the former top-right minimap area.

**Acceptance status at v13v1-03:** code-level checks covered the cue layers, deterministic placement contract, bounded bird count, layer order, persistent money display, and removal of minimap state/input/rendering. The complete suite passed 118 tests and Python compilation passed. Interactivity arrived in v13v1-06. No graphical Pygame playtest was possible in the build environment; live readability and performance should be checked on Windows with hotspots visible during clear daylight, fog, night, and rough water.

### `v13v1-04` — Dead reckoning and believed position — IMPLEMENTED
**Source:** Part A, §§A1–A3 and A9; implementation layer D1.4. **Risk: medium/high.**

**Implementation:** `World` now maintains `believed_pos`, `believed_heading`, `believed_speed`, `last_fix`, `last_fix_method`, `position_error`, `compass_bias`, `log_bias`, and `dr_uncertainty` alongside the physical state. Biases wander slowly within bounded compass/log limits; estimated motion advances the belief, while expected doubt grows with movement and is weighted by helm skill, sea state, daylight, fog, and rain. The true position-error vector is internal state only.

The chart vessel marker, heading, speed, and course range use the crew's belief; the chart draws an estimated uncertainty ring and reports doubt/fix age without revealing true coordinates or the error vector. Compact HUD telemetry and the F1 navigation sheet use estimated heading/speed and believed coarse location. Movement, collisions, land avoidance, autopilot, foam, hotspot ecology, and other physics/AI reads continue to use `ship_pos`, `heading`, and `speed`. A shared `reset_position_fix()` clears bias and doubt at the known departure position, when the ship is secured alongside, and after tow-in. Player-operated fixes were added in `v13v1-09`.

The upper-right line-depth/water-column profile has also moved down exactly 20 px (`y=62` to `y=82`) so its title no longer intrudes on the money counter.

**Acceptance status:** the headless suite passes 130 tests and Python compilation passes. Added model checks cover estimated movement, zero-duration steps, reproducible/bounded bias evolution, weather/skill multipliers, travel divergence, and fix-age formatting. Integration-contract checks verify that dead reckoning never assigns to `ship_pos`, the chart and navigation HUD use belief, known-position resets clear the model, and the hook-profile panel is shifted by 20 px. Pygame is not installed in the environment, so visual drift feel, chart readability, and resized-window layout still need a real Windows playtest.

### `v13v1-05` — Ship's Notebook, radio transcripts, seasonal calendar, and storm market — IMPLEMENTED
**Source:** the current simulation's radio, world clock, weather, auction pricing, and player-facing operating UI; extends the release plan while preserving Parts A–G.

Implement a single sepia, chart-styled Ship's Notebook on **F9**, with four selectable sections and turnable pages (`< PREV` / `NEXT >`, arrow keys, or mouse controls):

- **Crew log:** persist dated entries for crew actions, work reports, player orders, station assignments, incidents, and key ship events. Each entry records the in-game date/time, speaker, and a compact event kind; cap history to avoid unbounded growth.
- **Radio log:** record every transmission and reply as its own timestamped turn, with a distinct sender label such as VESSEL or COAST STATION. Do not fire all replies in a single frame; the on-screen radio bubble should display one line at a time, and the notebook must preserve that order. Queue overlapping requests rather than overwriting the current exchange.
- **Calendar:** begin the career on **1 April 1962** and advance with the simulation's existing clock. The notebook and HUD share the same calendar source; do not introduce a second time system or shorten the first day.
- **Seasonal weather and radio forecast:** the F2 weather call reports the next three days as a short coast-station conversation. Forecasts are repeatable for a given in-game date, have lower confidence farther out, and use monthly temperature / precipitation normals and seasonal patterns for the Hakodate / North Pacific setting. This is a simulated outlook, not live weather data.
- **Storm-affected market:** when the actual weather regime transitions into a storm, add a bounded premium to the existing market index so fish sell for more during supply disruption. Let the premium decay over several in-game days after the storm. Preserve the underlying auction quality and grade calculation; the storm modifies the price index, not the quality of fish.

**Acceptance:** the notebook opens/closes without blocking normal game input after closing; page navigation clamps cleanly; crew and radio history entries include date/time and stay in chronological order; radio turns do not overwrite one another; the campaign starts in April 1962 and rolls dates exactly once per game day; forecast generation is deterministic by date and seasonally non-constant; a storm raises the effective market index within a defined cap and the premium decays without becoming negative. Regression tests cover all of these contracts. A graphical playtest is still required to review notebook legibility and timing.

Climate design reference: Japan Meteorological Agency's climatological normals (1991–2020) and monthly Hakodate normals. Source links: <https://www.data.jma.go.jp/stats/en/normal/normal.html> and <https://ds.data.jma.go.jp/gmd/tcc/tcc/products/climate/climatview/graph_mkhtml_nrm.php?e=6&k=0&m=2&n=47430&r=1&s=3&y=2025>.

### `v13v1-06` — Chart interaction and waypoint plotting — IMPLEMENTED
**Source:** Part A, §A5; implementation layer D1.5.

**Implementation:** the chart is now an interactive course-plotting surface. Left-click on open water adds a staged waypoint; clicking a point selects it, and the next left-click moves it. Shift-click near a leg inserts a point projected onto that leg. Right-click on a waypoint deletes it from the staged route; right-click on empty chart closes without committing. Enter commits and closes; Escape immediately clears the active manual course and staged points, while `C` closes without committing staged edits. Numbered markers, route legs, and per-leg nautical-mile labels are drawn from chart design coordinates, so resize/redraw does not move saved points. The route is capped at **eight waypoints** and rejects out-of-bounds, duplicate, and near-zero legs.

The autopilot targets the first route point, removes reached points, and proceeds in order; the crew log records route commitment, waypoint arrivals, completion, and cancellation. The source plan's conflict policy is explicit: auto-fishing has priority. Enabling `L` cancels an active manual route with a message; committing a chart route is blocked while the fishing auto-sequence is active. Docking and man-overboard rescue also retain navigation priority. `World.set_destination()` cancels a manual route unless the caller explicitly preserves it for route progression.

**Acceptance status:** 165 headless tests pass and Python compilation passes. Focused tests cover coordinate round-trips, invalid clicks/coordinates, near-zero legs, route insert/move/delete, eight-waypoint limit, course-order progression, resize-safe coordinate storage, commit/cancel behavior, and route/auto-fish conflict. The implementation has not had a live Pygame graphical playtest; check click target precision, text overlap, and real autopilot steering on Windows.

### `v13v1-07` — Readable hotspot cues, crew lookout, and follow birds — IMPLEMENTED
**Source:** Part B, §§B5–B8 and B10; correction of D1.3 plus D1.8 and the ambience portion of D1.9.

**Implementation:** working gulls now have a 24–34 px wingspan at normal zoom, comparable to a sailor's roughly 24 px body width. Bird count scales with current strength and the orbit radius contracts as the school strengthens; as strength decays the flock thins, spreads, and greys. The cue uses three concentric, low-alpha green/teal/blue discs. Flotsam clusters near the centre and is not drawn below strength 0.30; expanding white ripples are not drawn below strength 0.20. Physical cues require no crew detection.

Each sailor now has a `gut_spot` and `gut_confidence`. Lookout detection requires an aboard sailor on the main deck, facing the school within a forward 180-degree cone, and within a skill-/visibility-/daylight-limited distance. Confidence builds through sustained observation and fades after sight is lost. At confidence >= 0.5, the first confident lookout speaks once and one pulsing pale-yellow diamond appears; if the spot is off-screen, a directional triangle is drawn at the nearest safe screen edge. Multiple sailors never stack duplicate markers for one school.

A separate flock follows the stern during longline setting, soaking, and hauling (8 / 4 / 14 birds respectively). It is suppressed at night, in storms, and when the line is idle. These birds are dark and smaller than working gulls so the two cues remain visually distinct; they do not affect fish, ship physics, or detection.

**Acceptance status:** 177 headless tests pass and Python compilation passes. Tests cover sailor-scale bird dimensions, count/tightness changes with strength, the exact debris/ripple thresholds, lookout skill/weather/range/confidence, edge-arrow geometry, and follow-flock activity gates. Pygame is not installed in the environment; visual comparison against the actual sailor/ship scale still requires a Windows playtest at default zoom and on resized screens.

### `v13v1-08` — Broadcast conversations — IMPLEMENTED
**Source:** supplied `docs/Broadcast Conversations - Catalogue.md`; extends the current crew speech and coast-station radio channels without replacing their underlying gameplay effects.

**Implementation:** a `BroadcastDirector` owns timed conversations as attributed turns with a channel, source, priority, and inter-line delay. It queues ordinary traffic, orders pending conversations by priority while retaining FIFO order for ties, and allows a higher-priority event to interrupt a lower-priority conversation. Each delivered turn goes through the existing speech/radio UI so crew and radio logs record the lines rather than leaving messages only in transient state.

The implemented channels include coast-station radio, ship-to-ship traffic, shipboard intercom / deck reports, crew chatter, and dockside harbour talk. The routine catalogue can produce weather and market reports, navigational/fleet reports, CQ/time/news-style traffic, position/catch/weather exchanges, a race or trade exchange, harbour arrivals/gossip, and crew/intercom work turns. Storm transitions queue a high-priority warning; engine-room alerts and man-overboard rescue take precedence over routine ambient chatter. Rare Mayday and Pan-pan events use once-per-session rolls (5% and 10% respectively). Routine conversation scheduling waits when the radio is unstaffed or another operation is busy; harbour gossip is limited per docking visit. The text uses 1962-style callsigns and terms such as “over,” “out,” “roger,” and “standing by,” avoiding modern “copy that” phrasing.

**Compatibility and pacing:** F2 weather, F3 market, and F4 tow still execute their existing weather/auction/tow mechanics; the conversation layer adds dialogue around them instead of substituting for them. Ambient speech remains sparse by design. The player-response menu for distress calls is not included in this milestone; the supplied catalogue explicitly places branching player replies in a later phase. Automatic hourly time-signal scheduling and a full fleet simulation are also not claimed as complete; time signal, fleet, and news content are currently options in the sparse ambient conversation pool.

**Acceptance status:** 194 headless tests pass and Python compilation passes. Focused coverage exercises turn delays and speaker attribution, channel readiness, priority preemption, pending-queue ordering, rare distress rolls, harbour gossip caps, legacy F2/F3/F4 behavior, storm warning priority, crew-log integration, and critical rescue interruption. Pygame is not installed in this environment, so live radio pacing and speech-bubble visibility still require a Windows playtest.

### `v13v1-09` — Position fixes — IMPLEMENTED
**Source:** Part A, §A6; implementation layer D1.6.

The navigation chart now provides four keyboard-operated measurement methods while the chart is open:

- **`1` Landmark bearing:** selects the nearest named landmark within current visibility. A sailor must be aboard on the main deck to take the bearing. Accuracy is skill-, range-, and sea-state-weighted; this is usually the tightest fix.
- **`2` Sextant:** only available in the dawn (05:00–07:00), noon (11:00–13:00), and dusk (17:00–19:00) windows, with cloud below 0.70, an on-deck observer, and skill at least 0.40. Higher skill reduces the reported positional uncertainty.
- **`3` Radio direction finding (RDF):** requires the actual radio operator to be at the working wireless set, skill at least 0.40, and the coast station within 3,200 chart units. Its error distribution is elongated along the bearing line, because a single bearing constrains direction better than distance.
- **`4` Echo sounder:** available only within charted sounding coverage. It compares the physical depth reading with the stable, noisy survey depth at the crew's believed position. A mismatch logs both readings and warns the crew, but does not change believed position, last successful fix, or doubt. Only a reading within 4 metres counts as a confirmed fix under this milestone's rules.

Approximate landmark, sextant, and RDF observations apply sampled measurement error to a new **believed** position and set the uncertainty ring to the method's nominal accuracy. They do not set physical ship position, reveal the true error vector, or report true coordinates. Successful fixes clear accumulated compass/log bias while leaving any sampled residual position error intact. The echo-sounder match is the special case that resets belief to the known location under the plan's sounder-matching rule.

**Rate limits:** landmark 15 simulation-seconds; sextant 45 simulation-seconds (so a sun window cannot be repeatedly exploited); RDF 30 simulation-seconds; sounder 15 simulation-seconds. Unavailable-condition checks do not consume the fix cooldown. Results and sounder mismatches are recorded in the Ship's Notebook crew log and surfaced in the chart status line.

**Acceptance status:** 18 focused tests cover visibility, watch availability, skill and sea-state accuracy, sextant windows/cloud, RDF staffing/range/skill and along-bearing variance, stable charted-depth noise, the 4 m sounder tolerance, key bindings, uncertainty retention, and the no-correction-on-mismatch rule. Full project suite: 212 tests passed; Python compilation passed. Pygame is unavailable in the build environment, so button/readout fit and actual fix operation still require a Windows graphical playtest.

### `v13v1-10` — Skill-weighted crew reports — IMPLEMENTED
**Source:** Part A, §A7; implementation layer D1.7.

**Implementation:** `fishing_sim/systems/crew_reports.py` provides independent, skill-weighted bearing, distance, and speed measurements. Bearing reports use nautical compass degrees; ranges use the chart's 185.2 design-units-per-nautical-mile convention; speed uses the existing 50 world-speed-units-per-knot convention. Measurement noise follows the plan's Gaussian model: bearing sigma `0.02 * (1-skill)` radians, range sigma `0.10 * (1-skill)` of true range, and speed sigma `0.20 * (1-skill)` knots.

Press **I** with an eligible sailor selected to request a bearing and range to the nearest currently visible named landmark. Press **O** for a speed-log report. The requested sailor must be aboard, alive, on the main deck, and not climbing. After the first report, click a different eligible deckhand within **five simulation-seconds** to request an independent observation of the same report kind and, for bearing/range, the same landmark. The comparison panel lists both sailors and their skill levels, shows the chart bearing calculated from believed position and each observed bearing’s offset from it, displays the measured spread, and warns when observations materially disagree. It never identifies the true reading or changes physical/believed ship state. Reports and comparison summaries enter the existing crew/notebook log path.

**Acceptance status:** implemented. Focused tests cover nautical bearing orientation, seeded repeatability, error-variance reduction at higher skill for all three report types, nonnegative distance/speed, bearing wraparound, five-second window definition, input wiring, eligible crew constraints, same-target second opinions, and no truth-state mutation. Full project suite: 226 tests passed; Python compilation passed. Pygame is unavailable in the build environment, so speech/panel overlap and actual click timing still require a Windows graphical playtest.

**D1.8 status — included in `v13v1-07`:** crew lookout state, confidence accumulation/decay, skill-weighted detection range, a single confidence-gated gut marker, and the off-screen edge arrow have been implemented and tested in the current release. Species guesses remain intentionally direct for now; probabilistic species-call accuracy is a future tuning option.

### `v13v1-11` — Auto-fishing hunts detected water — IMPLEMENTED
**Source:** Part B, §B9; the stern-following bird ambience was implemented in `v13v1-07`.

When `L` auto-fishing is active, the crew now select the strongest credible current hotspot from eligible main-deck lookouts. Selection requires confidence **above 0.70** and remaining spot strength **above 0.40**. The plotted destination is the hotspot world coordinate plus the current `position_error`, retaining the design rule that dead-reckoning error can make the crew miss productive water. The existing `World.set_destination()` and autopilot continue to control physical movement and land avoidance; no ship teleportation or hidden-truth marker is introduced.

If no suitable contact exists, the AI uses the existing general fishing-grounds route. If the selected school expires or weakens beneath the threshold during transit, it picks another credible contact or falls back to the general grounds. Arrival uses the stored plotted target so an interrupted destination does not make the ship set far from the spot. Targets are cleared when setting begins or auto-fishing is disabled. Follow birds remain ambience only.

The release also changes transient speech routing: spoken crew lines, direct commands/warnings, named crew reports, and ordinary attributed conversation remain as bubbles; action narration and operational/context notices remain in the dated crew log / Ship's Notebook instead of being falsely shown as speech from the selected sailor. Radio traffic keeps the separate radio bubble.

**Acceptance status:** implemented. Focused headless tests cover detection/strength thresholds, strongest-contact selection, stale contacts, belief-offset destinations, fallback/re-target behavior, state cleanup, and the distinction between actual speech and context notices. Full suite: **239 tests passed**; Python compilation passed. Pygame is unavailable in the environment, so real-world steering, route transitions, and bubble density still require a graphical playtest.

### `v13v1-12` — Chart fishing reports and uncertain leads — IMPLEMENTED
**Source:** user-requested chart intelligence extension to Parts A–C; builds on the report/log architecture shipped in `v13v1-10` and chart implementation from `v13v1-02` / `v13v1-06`.

The chart periodically receives fishing-area reports from fleet traffic, coast station, or harbour talk. A report can be based on a live hotspot, but its reported location carries error and its species call can be wrong. When no suitable real contact is used, the report is a plausible offshore rumour that does not correspond to a current hotspot. Report source, confidence, location, species, and age are shown; the UI does **not** expose the internal grounded/false status. Confidence describes source credibility rather than guaranteed truth. Markers use an uncertainty ring and fade as reports age; reports expire and the live set is capped at five so the chart remains readable. Report arrivals enter the dated crew log, not transient speech bubbles.

**Acceptance:** headless tests cover true/false lead generation, chart bounds and water placement, deterministic RNG behavior, report aging/expiry, confidence/freshness visuals, report generation integration, chart marker and panel contract, and the no-truth-leak rule. Visual marker and panel readability still require a Pygame playtest.

### `v13v1-13` — One-button manual line setting — IMPLEMENTED
**Source:** usability correction to the line-setting flow; preserves the existing longline state machine and separate auto-fishing mode.

Press **P** to issue one manual setting order without enabling **L** auto-fishing. The command clears a committed manual chart route so the vessel can make an uninterrupted slow setting run, but preserves the player's chosen bait and line-depth setting. Deckhands detect the setting phase, assign themselves to the stern roller, and move to their stations. Existing phase transitions handle the one set, soak, and haul sequence; after completion, the stage returns to off and does not repeat. The action is refused in harbour, during docking/rescue, if auto-fishing is already on, or if a line operation is active.

**Acceptance:** seven focused headless tests cover the one-shot start, input/control hint, no implicit auto toggle, route cancellation, refusal conditions, and reuse of the normal setting/soak/haul state machine. Full suite: **259 tests passed**; compilation passed. A graphical playtest is still needed to observe crew movement, acceleration, and the completed cycle in real time.

### `v13v1-14` — Fishing-log gut book and chart gut markers — IMPLEMENTED
**Source:** Part B, §B10; implementation layer D1.10, plus the chart integration gap identified during review.

The Ship's Notebook now has a **GUT BOOK** section (F9, then Tab to cycle or press 5 while the notebook is open). The first confident lookout on a hotspot creates one bounded history entry containing campaign date/time, sailor name and skill, species call, confidence, and the **believed chart position at discovery**. The entry survives the live hotspot expiring; its state is displayed as ACTIVE or HISTORICAL. The record list is capped at 100 to bound memory use. These are session-long records: this game build does not currently have save-game serialization, so the gut book does not survive closing/restarting the application.

The navigation chart now renders a pale-yellow `G##` diamond for each live school detected with at least 50% lookout confidence. It deduplicates multiple lookouts on the same school and plots the marker using the current dead-reckoning position error. Therefore a later fix can move the live `G##` marker, while the historical gut-book coordinate remains unchanged. `R#` rings remain independent uncertain external reports; neither marker system exposes the hidden true ship/school coordinate or labels a rumour as true/false.

**Acceptance:** headless tests cover chart-coordinate conversion with DR error, first-confident-detection recording, bounded history, ACTIVE/HISTORICAL state, notebook navigation and paging, and live chart marker contracts. The full project suite and compilation pass. Pygame is unavailable here, so marker legibility and notebook layout still need a graphical playtest.

### `v13v1-15` — Marine gear collisions, rescue routing, and reliable fishing spots — IMPLEMENTED
**Source:** integration hardening for line/buoy physics, man-overboard recovery, and the hotspot spawn issues found during playability review.

**Marine collisions:** Longline particles and surface buoys are projected clear of land, reef, and ship hull geometry. The solver also sweeps each rope segment between particles after constraint solving, reducing the chance that a long segment can cross a narrow obstacle without any particle hitting it. Surface rope and buoys resolve against the deployed rescue boat; submerged hooks do not collide with a dinghy simply because their x/y coordinates overlap. The rescue boat resolves against land, reef, hull and surface line gear, and uses an expanded hull envelope to route around the bow or stern on outbound and return trips. On contact it attempts to slide tangentially or replans rather than passing through the ship.

**Rescue behavior:** In seas too rough for a launch, the ship approaches at dead slow and tests approach headings against land/reef, then pivots while stopped to present its starboard rail for a lifeline recovery. Rescue-boat occupants have an explicit starboard-facing face mark in local boat coordinates so it remains oriented correctly as the boat turns. The hook minimap stays removed; the depth profile remains in the top-right HUD beneath the cash and date cards (profile y=82).

**Hotspot availability:** The first spawn occurs after 10–18 game seconds. When the vessel is sufficiently offshore, candidate schools are first seeded 1,000–3,600 design units from the current vessel position, still validated against minimum harbour distance, depth, land, coast and reef. A 48-attempt global offshore search and a deterministic sweep around the normal fishing grounds remain fallback paths. Successful spawn cooldown is 45–75 seconds; failed attempts retry in 6–12 seconds. The four-hotspot cap and existing 7–15 minute lives remain intact.

**Acceptance:** pure geometry tests cover segment/polygon projection and hull-avoiding routes; source-contract tests cover the longline sweep, buoy/boat/land/reef/hull contacts, rescue route reuse, rough-sea starboard approach, occupant facing, spawn timing/fallbacks, and the no-minimap/depth-profile layout. Full suite: **281 tests passed**; Python compilation passed. Pygame is unavailable in the build environment, so a graphical playthrough is still required to verify rope stability, rescue maneuvers, and HUD behavior at resized resolutions.

### `v13v1-16` — Performance pass — IMPLEMENTED (source/test verified; graphical benchmark pending)

**Scope:** performance regression work on the current v13v1-15 code, not the legacy `longliner_rts.py` prototype.

**Implementation:** the sea/coast background uses a reused compatible-format staging Surface and a 30 Hz refresh cap; the ship's mostly-static artwork uses a reused alpha staging Surface, a 30 Hz refresh cap, and a cropped cache blit. Repeated UI panels/font renders, fish transforms, and deterministic foam shapes are cached with bounded caches. Collision geometry and bounds are prepared once, collision points are rejected through cheap AABB/hull-radius broad phases, and the rope solver avoids duplicate Vector2 snapshots and a separate depth-clamp pass while retaining six constraint iterations and the final segment sweep.

**Acceptance:** performance-cache and hot-path source tests were added, Python compilation passes, and the full headless test suite passes **291 tests**. Pygame is unavailable in the build environment; measured FPS, frame-time capture, cache appearance during resizing/weather changes, and rope/rescue stability must still be verified in a graphical run. See [`docs/V13V1-16_PERFORMANCE_OPTIMIZATION.md`](docs/V13V1-16_PERFORMANCE_OPTIMIZATION.md) for online references and profiling steps.

### `v13v1-19` — Manual line-setting crash fix and persistent runtime diagnostics — IMPLEMENTED (headless verified; graphical retest pending)

The first longline physics tick after a hook was emitted could close the game because `Longline._physics()` read particle index `i` before binding it in the particle-history loop. The loop now uses `enumerate(pts)`, and a focused headless smoke test executes the real method body with one surface float to cover the setting entry point.

The launcher installs runtime diagnostics before importing the game. At launch it creates `cache/errors/` with rotating `runtime.log` and `errors.log`, per-crash `crash_*.txt` traceback reports, and a `faulthandler` `faults.log`. Crash reports capture the current input event/frame, line phase/stage, active hook count, vessel speed/heading/position, and available engine/hatch state. Diagnostics fall back to a user-writable cache if the project folder is read-only. See `CHANGELOG_V13V1_19.md` and `docs/CHANGELOG_V13V1_19.md`.

**Acceptance:** Python compilation passed; automated suite: **315 tests passed**. The gameplay fix and exception writer have headless regression coverage. A Pygame interactive run is still needed to verify a complete setting → soak → haul cycle and inspect the runtime cache on the user's machine.

## Global tuning and risk register

| Concern | Rule for implementation | Evidence / plan pointer |
|---|---|---|
| Truth leaks to the player | Physics retains `ship_pos`; UI uses `believed_pos`. Do not draw a true ship marker or exact hidden error vector. | §§A1–A3, D3 |
| Navigation errors grow too fast | Start with the plan's base rate (10 units/min for a good watch in fair weather), then test with route lengths and hotspot radii before tuning. | §§A3, A10 |
| Fixes remove all difficulty | Respect visibility, time, range, skill, and radio staffing conditions; a sounder mismatch must not reset error. | §A6, Part F |
| Hotspots overrule ecology | Multiply existing species bite weight; do not create a catch when base habitat/bait rules make that species invalid. Cap/retune centre boost if dominant. | §§B4, E2, Part F |
| Hotspots become automatic waypoints | Tier-one physical clues (birds, tint, debris, ripples) never need crew detection; auto-fishing can target only a live school with eligible lookout confidence > 0.70 and strength > 0.40. Its plotted destination preserves dead-reckoning error and never exposes undetected schools to the player. | §§B5–B9 |
| Crew sees the whole ocean | Cap range and apply visibility/daylight multipliers. | §B6, Part F |
| Route UI becomes cluttered | Eight waypoint cap; numbered points and leg lengths. | §D3 |
| RDF staffing has no cost | Require a real operator at a working set; reflect the person being unavailable to other duties. | §§A6.3, C3, Part F |
| Follow birds cover UI | Draw them before HUD panels; keep dark stern-following V-shapes separate from larger white working gulls. | §§B10, Part F |

## Test and release gates

For every milestone, run from the project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

Do not mark a milestone complete solely because the code compiles. Record: automated tests, interactive checks performed, known defects, and whether a real Pygame graphical playtest was completed. Keep `run_fishing_sim.py` and `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md` at ZIP root. Keep the supplied `docs/v13 Plans.md` as the source of design decisions, and update this roadmap before broadening scope.

## Source reading guide

- **Design constraints:** §§A1, C3, G
- **Navigation and chart:** Part A; especially §§A2–A8
- **Hotspots, detection, cues, and auto-fishing:** Part B
- **Intended layer order and effort/risk:** §§D1–D3
- **Tuning values:** Part E
- **Broadcast dialogue and period language:** [`docs/Broadcast Conversations - Catalogue.md`](docs/Broadcast%20Conversations%20-%20Catalogue.md)
- **Do-not-repeat pitfalls:** Part F


### `v13.1.20` — Phase 6 hauler and stern roller — IMPLEMENTED (headless verified; graphical playtest pending)

The hauler friction drum now slips when load exceeds the available drive/crew/condition capacity. Slip lowers hauling pull and wears the drum. The stern roller can be working, bypassed, or jammed; condition and load determine wear/jam risk, while bypass/jam increases line chafe and snags. Snags pause setting/hauling; badly worn line can part under high load, with extra injury risk for unharnessed stern-gear workers. `M` toggles/bypasses the roller or clears it when a healthy deckhand is working aft; `Y` retains the harness trade-off. The linked rewritten `Sailor.draw()` painter is preserved in the build.

**Acceptance:** 325 unit tests pass and Python compilation passes. Pygame is unavailable here, so the set/haul cycle, visual state colors, and tuning still require desktop playtesting. See `CHANGELOG_V13_1_20.md` and `docs/V13_1_20_PHASE6_GEAR.md`.


### `v13.1.21` — Full-length lower deck and sailor-sized bunks

**Implemented:** The lower-deck zones now extend from aft stores through the ice hold and engine room to a forward crew cabin and tapered forepeak chain locker through a clear centre hallway. Six larger sailor-sized bunks use unique approach locations; a sleeping sailor stays on the mattress without bed or crew-separation collisions until another task wakes them. Failed A* routes no longer degrade into direct movement through solid obstacles.

**Acceptance:** 335 automated tests pass in the unittest runner output and Python compilation passes. Pygame is unavailable here, so scale and end-to-end crew navigation still need a graphical playtest. See `CHANGELOG_V13_1_21.md` and `docs/V13_1_21_LOWER_DECK.md`.

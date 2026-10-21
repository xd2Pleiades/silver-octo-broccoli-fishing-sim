# V13V1-18 — Phase 5

Manual hatch controls and consequences: `U` opens/dogs the nearest engine/hold hatch, `F` sluices the cutting table with the seawater hose, and `V` trims ice from inside the ice hold. Keep hatches shut in heavy seas to reduce engine-room bilge and hold flooding. Crew can bail water only in the compartment where they are physically working. Fish must be bled, gutted and sliced before being stowed through an open hold hatch.

See `Roadmap_V2.md` and `CHANGELOG_V13V1_18.md` for the Phase 5 details.

---

# V13V1-16 — Performance pass

- Optimizes the current v13v1-15 codebase (not the legacy `longliner_rts.py` prototype).
- Caches ocean/background and mostly-static ship artwork with reusable staging surfaces; crops the ship cache to visible hull bounds and caps those expensive refreshes at 30 Hz.
- Caches UI panels and font rasters, fish rotation sprites, and seeded sea-foam shapes using bounded caches.
- Reduces longline collision work with prepared geometry, broad-phase bounds, cached hull-radius rejection, fewer temporary Vector2 copies, and a merged depth-clamp pass.
- The complete Markdown plans and historical changelogs remain included in the archive.

**Verification:** 291 automated headless tests and Python compilation pass. Pygame was unavailable for a live FPS measurement; see `docs/V13V1-16_PERFORMANCE_OPTIMIZATION.md` for source links and a reproducible profiling procedure.

---

# V13V1-15 — Marine Gear Collisions, Rescue Routing, and Reliable Fishing Spots

- Longline particles, rope segments, and buoys collide with shore, reef, and ship geometry. Surface line gear and buoys also collide with the deployed rescue boat; submerged hooks do not become false surface obstacles.
- Rescue-boat motion is collision-resolved and routes around the expanded ship-hull envelope on outbound and return legs. In rough seas, the ship instead approaches at dead slow, checks headings against land/reef, and turns its starboard rail toward the swimmer for a lifeline recovery. Rescue-boat faces visibly point to local starboard.
- Hotspots begin spawning after a short 10–18 game-second delay. Once offshore, the first candidate search is near the vessel in validated water; global offshore sampling and a deterministic fishing-ground fallback remain available. Successful spawns repeat every 45–75 seconds; failed attempts retry after 6–12 seconds. Four live hotspots remain the cap.
- The hook minimap remains removed. The compact depth profile stays at HUD y=82, under the cash/date cards.

## V13V1-15 verification

**281 automated tests pass** and Python compilation passes. Run from the project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

Pygame is unavailable in the build environment, so a graphical playtest remains necessary to verify rope stability, rescue routing and face direction, and the HUD at resized window dimensions.

---


- Open the Ship's Notebook with **F9**, then use **Tab** to cycle to **GUT BOOK** or press **5** while the notebook is open.
- The first confident crew lookout records the species call, discoverer, skill, date/time, confidence, and crew-believed chart position. Records survive hotspot expiry for the current game session and are marked **ACTIVE** or **HISTORICAL**.
- On the navigation chart (**C**), `G##` pale-yellow diamonds show live schools detected by lookouts. They are plotted from the current dead-reckoning estimate, so a navigation fix may shift the live marker. The gut book's original position remains unchanged. `R#` rings are still uncertain fleet/harbour reports.
- The history is capped at 100 entries. It is session-persistent only; this build has no save-game format, so records do not survive restarting the game.

## V13V1-14 verification

**270 automated tests pass** and Python compilation passes. Pygame is not installed in the build environment, so a graphical playtest is still required.

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

# Fishing Sim — V13V1-14 (Fishing Gut Book and Belief-Offset Chart Markers; based on 12v19)

# V13V1-13 — One-button manual line setting

- Press **P** to start one manual line set while leaving **L** auto-fishing disabled. The ship begins a slow straight setting run, eligible deckhands assign themselves to the stern roller, and the existing state machine manages the single set, soak, and following haul. It does not repeat the cycle.
- Manual bait and line-depth choices are preserved. A committed chart route is cleared for the uninterrupted setting run; manual setting is refused in harbour, during docking/rescue, while auto-fishing is enabled, or while another line operation is active.

## V13V1-13 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

The manual-setting regression tests cover input routing, safety guards, course cancellation, auto-fishing remaining disabled, and reuse of the existing one-shot line state machine. Pygame is not installed in the build environment, so crew movement and setting-run behavior still need a graphical playtest.

---

# V13V1-12 — Chart fishing reports and uncertain leads

- The **C navigation chart** now displays fishing-area report markers labelled `R#`, with an approximate search ring and the reported species, source tag, age, and source-confidence score in the side panel.
- Reports are **leads, not truth markers**. Some are based on live hotspots but have position error and may misidentify the species; others are false offshore rumours. The UI never marks a report as true or false. Freshness fades over time, reports expire, and no more than five are active at once.
- New report arrivals enter the dated Ship's Notebook crew log only; they do not add artificial action/context speech bubbles.
- All existing Markdown documents are retained in the ZIP, including `v13 Plans.md` both at the root and in `docs/`, as well as the full release changelog sequence.

## V13V1-12 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**252 automated tests pass** and Python compilation passes. Pygame is unavailable in this environment, so graphical marker readability and responsive panel layout still need a playtest.

## V13V1-11 — Auto-fishing hunts detected water; speech bubble cleanup

- With **L** auto-fishing enabled, the crew can steer toward a currently live hotspot that a main-deck lookout has detected with confidence above **0.70** and whose remaining strength is above **0.40**. The best credible contact is selected rather than the first matching sailor.
- Hotspot navigation uses the current dead-reckoning position error when plotting the destination. It follows the existing ship steering/land-avoidance path, so a poor position estimate can still cause a miss; the AI never teleports the vessel onto a school.
- With no suitable lookout contact, auto-fishing keeps the established fishing-grounds route. If the school expires or becomes too weak during transit, the crew choose a different credible contact or fall back to the usual grounds. The route state is cleared safely when auto-fishing is disabled or a set begins.
- Speech bubbles now mainly represent lines someone is actually saying: crew dialogue, direct spoken orders/warnings, and attributed conversation turns. Action narration and operational/context notices remain in the dated crew log / Ship's Notebook rather than being attributed to whichever sailor happens to be selected. Radio speech remains in its separate radio bubble.

## V13V1-11 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**239 automated tests pass** and Python compilation passes. Pygame is unavailable in the build environment, so live steering, speech density, and the on-screen transitions still require a graphical playtest.

## V13V1-10 — Skill-weighted crew reports

- Select an eligible sailor on the main deck. Press **I** for a skill-weighted bearing and distance report to the nearest visible named landmark, or **O** for a speed-log report.
- After the first report, click another eligible deckhand within **five simulation-seconds** for an independent second opinion about the same target/report type.
- The report card shows both sailors, their skill values, the chart bearing from believed position, measurement spread, and a discrepancy hint. Neither observation is labelled as the truth, and reports never correct ship position.
- Bearing observations use nautical compass degrees; range is shown in nautical miles; speed is shown in knots. Reported observations and the comparison summary are retained in the normal crew/notebook log.

## V13V1-10 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**226 automated tests pass** and Python compilation passes. Pygame is unavailable in the build environment, so the report speech bubbles, comparison-panel layout, and second-opinion click flow still require a Windows graphical playtest.

## V13V1-09 — Position fixes

- Open the navigation chart with **C**. Press **1** for a visible-landmark bearing, **2** for a sextant sun sight, **3** for radio direction finding, or **4** for an echo-sounder cross-check.
- Landmark fixes require a deck observer and a named landmark within current visibility. Sextant fixes require the dawn/noon/dusk windows, a sufficiently clear sky, and an adequately skilled observer. RDF requires a skilled operator physically staffing the working radio set and coastal-station range.
- Each method has different nominal accuracy. Landmark accuracy responds to observer skill, range, and sea state; sextant accuracy responds to skill; RDF has more uncertainty along the single-bearing line. Approximate fixes can still be wrong and retain an uncertainty ring.
- The echo sounder compares sounded depth with a deterministic old-survey chart depth. A mismatch logs both readings and warns the crew without changing position belief; only a match within 4 m counts as confirmation.
- Position fixes never mutate physical `ship_pos` or display the hidden error vector. Method-specific cooldowns avoid erasing navigation doubt with repeated key presses.

## V13V1-09 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**212 automated tests pass** and Python compilation passes. Pygame is unavailable in the build environment, so the chart-side fix panel and live interaction require a Windows graphical playtest.

## V13V1-08 — Timed broadcast conversations

- Added a priority-aware conversation director for multi-line, speaker-attributed radio, ship-to-ship, intercom, crew, and harbour exchanges.
- Conversations arrive one turn at a time with explicit delays. Critical Mayday and rescue traffic, storm warnings, and engine alerts can interrupt lower-priority ambient dialogue.
- Routine broadcasts remain sparse; radio requests retain their existing F2 weather, F3 market, and F4 tow effects. Each delivered turn enters the existing speech and notebook-log path.
- The full catalogue supplied with this version is preserved at `docs/Broadcast Conversations - Catalogue.md`. At the time of the v13v1-08 release, position-fixing methods were scheduled for `v13v1-09`; they are implemented in the release described above.

## V13V1-08 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**194 automated tests pass** and Python compilation passes. Pygame is not installed in the build environment, so live conversation pacing, bubbles, and visual interruption behavior still need a Windows graphical playtest.

Japanese Deep Sea Fishing Simulator (1962), organized as a Python/Pygame package.


## V13V1-07 — Readable fishing cues, crew lookouts, and follow birds

- Working gulls now read at roughly sailor scale: around 24–34 px wide at default zoom, with heavier outlined wing strokes rather than tiny 1–3 px marks. Strong schools form a denser, tighter white cluster; weakening schools lose birds, spread the flock, and turn the silhouettes greyer.
- Water tint uses three low-alpha green / teal / blue concentric discs. Flotsam sits close to the hotspot centre and stops rendering below strength 0.30. Expanding white ripples stop rendering below strength 0.20.
- Every hotspot cue remains visible to the player without crew detection. Crew-dependent gut markers are separate: one pulsing pale-yellow diamond appears only when an aboard sailor on the main deck has confidence at or above 0.5; an off-screen triangle points toward a detected school at the nearest safe screen edge.
- Lookout detection checks forward-facing direction, skill, visibility, daylight, deck level, and distance. Confidence grows over sustained observation and fades after detection is lost. A crew report is spoken once the first lookout becomes confident, using less certain language for green hands.
- Dark V-shaped follow birds trail the stern while the longline is setting, soaking, or hauling. Hauling has the largest flock. They vanish at night, in storms, or when the line is not actively fishing; they are independent of hotspot flocks and do not affect physics.

## V13V1-07 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**177 automated tests pass** and Python compilation passes. Pygame is not installed in this build environment, so bird scale and marker readability still need a graphical Windows playtest at default zoom, in fog/night, and with the hotspot near each screen edge.


## Run (from the extracted ZIP root)

The ZIP includes the standalone launcher `run_fishing_sim.py`; keep it beside the `fishing_sim/` package directory.

```bash
python -m pip install -r fishing_sim/requirements.txt
python run_fishing_sim.py
```

Alternatively, from the ZIP root: `python -m fishing_sim`.


## V13V1-06 — Interactive chart and waypoint plotting

- The **C** chart is now an interactive route-plotting surface. Left-click open water to add waypoints; click a waypoint and then a new point to move it; Shift-click a leg to insert; right-click a waypoint to delete it from the staged route.
- **Enter** commits a plotted route and closes the chart. **Esc** clears the active manual route. **C** or right-click on empty chart closes without committing staged changes.
- Routes are held in chart/design coordinates while editing and converted to world targets only on commit. The route is limited to eight points and displays numbers plus leg lengths in nautical miles.
- The autopilot visits remaining waypoints in order; waypoint arrivals and route orders are recorded in the crew log. Auto-fishing on **L** has priority and cancels manual routes with a message. Docking and rescue also retain priority.

## V13V1-06 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**165 automated tests pass** and Python compilation passes. Pygame is unavailable in this environment, so live click accuracy, leg label readability, and autopilot steering still require a Windows graphical playtest.

## V13V1-04 — Dead reckoning and believed position

- Added a crew navigation estimate that advances from reported heading/speed with slowly varying compass and log bias. Navigation doubt grows while underway and is weighted by helm skill, sea state, daylight, fog, and rain.
- The chart vessel icon, heading, speed, and distance-to-destination now use the believed state. A doubt ring and last-fix age provide uncertainty cues, while exact physical position and the hidden true error vector are not drawn or printed.
- Physics and existing AI remain based on the real `ship_pos`, `heading`, and `speed`; navigation belief is kept as parallel state. The estimate resets at departure, berth arrival, and tow-in. Player-driven position-fix methods are scheduled for V13V1-08.
- Moved the upper-right water-column / hook-depth panel downward by exactly 20 px (from y=62 to y=82).

## V13V1-04 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**130 automated tests pass** and Python compilation passes. Pygame is unavailable in this environment, so no graphical playtest has been completed; verify chart doubt readability, belief drift, and the hook-profile gap under the money HUD on Windows.

## V13V1-03 — Physical fishing cues and HUD revision

- Removed the minimap entirely: it is no longer drawn, allocated, clickable, or advertised as a control. The static chart is still opened with **C** and closed with **Esc**, **C**, or right-click.
- Added a persistent top-right economy card: **CASH ¥...** shows the current balance and **TOTAL EARNED ¥...** shows cumulative sales. The card stays visible when **F8** hides compact telemetry and updates through the existing auction and settlement economy.
- Repositioned the water-column depth profile into the former minimap area. The fishing tension/gaff UI now sizes itself against the telemetry panel and screen bounds instead of a minimap.
- Implemented physical hotspot clues: subdued green/blue water tint, phase-stable flotsam, expanding/fading surface ripples, and orbiting working gulls. Cue strength tracks hotspot strength and visibility; no fixed marker reveals the spot.
- Hotspot cues render after water and before line/ship/HUD layers. Cue rendering uses stable positions and bounded counts, so it does not introduce frame-random flicker.
- At the V13V1-03 release, navigation remained the previous milestone's read-only chart; interactive waypoint plotting arrived in **v13v1-06**. At that historical release, use the assigned helm's arrow controls, autodock, or crew auto-fishing until chart interaction arrives.

## V13V1-03 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**118 automated tests pass** and compilation passes. Pygame is unavailable in this build environment, so a real-time graphical playtest for cue visibility, money-card spacing, and framerate remains outstanding.

## 12v17 — Visual scale and readable operating UI

- The rescue boat is now rendered as a larger, proportionate dinghy with a visible inner deck, thwarts, gunwales, oars, life-vest details, and seating positions for the assigned rescuers and recovered sailor.
- Bucket-line workers carry a recognizable larger bucket prop with a tapered body, rim, handle, and visible water surface. Bucket count/reuse and bailing behavior are unchanged.
- Added abundant but bounded foam along the hull sides and bow, plus a more active trailing wake. Density and length respond to vessel speed and sea state; rough seas retain edge foam at low speed.
- The persistent HUD is reduced to two essential lines. Default mode shows speed, heading, sea state, and weather warning. **F7** switches to operations/urgent-alert status; **F8** hides/restores the HUD.
- Press **F1** for the detailed information sheet. **SHIP & CATCH** includes finances, fuel, engine condition, supplies, ice/hold temperature, catch quality/value, deck wetness, flooding, and fishing gear. **TELEMETRY** includes time, speed, course, sea, wind, visibility, helm/radio status, line status, and safety alerts. **CREW** preserves the existing **Aboard**, **Shore**, and **Hire** tabs.
- Dock crew actions remain restricted to the quay. The information sheet consumes world clicks and pauses ordinary simulation; an active **WAIT UNTIL RESTED** sequence can continue advancing time.
- On narrow windows, the fishing tension/gaff bars are sized against the left telemetry panel and screen edges; the minimap has been removed in V13V1-03.


## 12v18 — Persistent sea foam and whitecaps

- Replaced the old per-frame hull-attached foam ribbons/puffs with a dedicated `fishing_sim/systems/sea_foam.py` system. It is independent of Pygame rendering so its update logic is headless-testable.
- Foam patches are stored in absolute water/world coordinates; ship-camera transforms are applied at draw time. Previously emitted foam therefore remains behind as the vessel moves and turns.
- Distinct patch categories cover stern wake, bow-shoulder foam, side wash, brief spray/spindrift accents, and irregular wave-crest whitecaps. Whitecaps are weather-driven and can appear while the ship is stopped.
- Patch positions drift with the modeled surface current and wind; their opacity fades over their lifetime, and expired/off-view patches are culled. The default active cap is 240, with the least-visible patch recycled if the cap is reached.
- Rendering uses layered antialiased-friendly polygon/line/circle shapes on the existing transparent water overlay. No GPU shader, external render dependency, full-screen per-pixel processing, or new full-screen foam surface is required.
- Speed primarily controls bow/side/stern wash, while sea state and the existing WaveField drive rough-water crest foam and restrained spray. The existing WaveField and ship physics remain untouched.

## Release checks

```powershell
python -m py_compile fishing_sim/core/game.py run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

The automated regression suite and Python syntax compilation pass. A graphical sea-foam playtest has not been performed in this build environment because Pygame is unavailable; verify calm/storm, stopped/cruising, and turning behavior on Windows.

## 12v19 — Refined sea foam and whitecap rendering

- Refined foam from repeated oval marks into three visual layers: a cool aqua halo, a translucent water-coloured transition, and a broken bright core.
- Added stable, seed-derived irregular edges, interrupted wake seams, surface micro-froth, bubble accents, and ragged whitecap lips. Texture is repeatable between frames rather than randomly flickering.
- Older foam patches contract and fragment as they fade, while spray stays thin and short-lived. The 240-patch default cap and existing water-overlay renderer are preserved.
- Foam drift now uses the existing `Weather.wind` magnitude and `Weather.wind_dir` direction as well as the surface current, so calm breezes and storms read differently.
- Prevented accumulated spawn timers from dumping a backlog of stale foam after a long frame or debugger pause; event generation is capped without changing normal time-based emission.
- Added three focused regression checks for long-frame emissions, wind-strength input, and the seeded/layered renderer.

## 12v19 verification (historical release result)

From the extracted project directory:

```powershell
python -m py_compile fishing_sim/core/game.py fishing_sim/systems/sea_foam.py run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

The automated suite has **87 passing tests** and Python syntax compilation passes. A live graphical comparison is still required on Windows with Pygame installed. Specifically compare calm/drifting foam, cruising wake, high-speed bow wash, stopped-ship whitecaps, turning wake trails, and smaller window sizes.


## V13V1-01 — Temporary fishing hotspots

- Added a headless-testable `Hotspot` model for albacore, yellowfin, bigeye, swordfish, and mixed schools. A school has strength, radius, lifetime, drift, a stable world-space position, and linear fade during its final third.
- Offshore spawns are rejected near land, shallow water, the mapped coast, and the charted reef. The first spawn window is 45–90 seconds; later spawns are 90–150 seconds apart. At most four schools may be active, and a failed spawn attempt does not build a timer backlog.
- Hotspots modify the existing longline bite weights with a smooth quadratic distance falloff. A matching-species school is capped at 2.5x, a mixed school at 1.6x, and overlapping schools do not stack. Ecology, bait, temperature, depth, time of day, and bait freshness are still evaluated normally.
- At V13V1-01, hotspot cues were intentionally deferred to `v13v1-03`, while the static 1962 navigation chart arrived in `v13v1-02`.

## V13V1-01 verification

From the extracted project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**98 automated tests pass**, including 11 new hotspot checks. Python compilation passes. Pygame was unavailable in the build environment, so no live graphical playtest or empirical catch-rate balance run was performed.

## V13V1-02 — Static 1962 navigation chart

- Added a read-only, sepia coastal chart with the coastline, harbour mouth, lighthouse, temple peak, reef, and harbour-mouth shoal markings.
- Added stable charted soundings in fathoms, a surveyed-area boundary, uncharted-water hatching/notes, compass rose, magnetic-variation note, and a 0–10 nm scale bar.
- The current vessel and destination/course line are shown on the chart. The physical-position marker was temporary in V13V1-02; V13V1-04 switches chart/UI reads to `believed_pos` while preserving `ship_pos` for physics.
- In the original V13V1-02 build, **C** or the minimap caption opened the chart and minimap clicks set a destination. V13V1-03 removes the minimap, so the chart is opened with **C** only. From V13V1-06, chart input supports staged waypoint plotting; held gameplay keys remain masked while open and existing autonomous sailing continues.
- Static cartography is cached per chart viewport size. Sounding values are seeded from chart coordinates and do not change or flicker between redraws.
- This release does not add waypoint editing, navigation fixes, dead reckoning, or visible hotspot cues. These remain later roadmap milestones.

## V13V1-02 verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**112 automated tests pass** and compilation passes. Pygame is not installed in this environment and network access prevented installation, so the chart has not been visually playtested here. Verify the chart at 640×420 and 1280×800 on Windows, including open/close, right-click capture, and viewport resize.

## Preservation requirements

Keep both `run_fishing_sim.py` and `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md` at the ZIP root.

## Earlier releases

See `CHANGELOG_V16.md`, `CHANGELOG_V15.md`, and the prior changelog files for the previous feature history. The full `FISHING_SIM_v12_ROADMAP_PLAN.md` at the ZIP root records the version roadmap.

## V13V1-17 — Roadmap V2 Phases 3–4

The wheelhouse now renders as a local roof cutaway in the top-down deck view while retaining its navigation level and station ownership. Phase 4 crew quarters add six below-deck bunks, and rest duty routes to a bunk stand. Oil, cooling-water and shaft-seal maintenance continues to govern diesel output, propulsion and hauler power. See `../Roadmap_V2.md` and `../CHANGELOG_V13V1_17.md` for details and remaining Phase 5+ work.

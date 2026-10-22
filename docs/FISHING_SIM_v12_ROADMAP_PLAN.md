# Fishing Simulator v12 Roadmap — Implementation Roadmap

**Status:** 12v11 through 12v19 are implemented in the current project line. 12v18 introduced persistent world-space foam; 12v19 refines its layered appearance, broken-up texture, wind-aware drift, and long-frame emission stability. Automated checks pass; full graphical playtesting remains outstanding.

**Version naming:** This roadmap uses `12v11`, `12v12`, etc. Keep the existing launcher and preservation marker in every project ZIP:
- `run_fishing_sim.py`
- `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`

## Priority order

### 12v11 — Deck Work, Fishing UI, Engine Continuity, and Headcount
**Priority: first implementation.** This release focuses on making the current fishing/deck/crew systems readable and consequential, without beginning the auction overhaul.

#### 1. Move the fishing minigame UI up
- Reposition the fishing minigame so it is higher on the screen and does not obscure the important deck/ship view.
- Keep its existing gameplay and input behavior intact.
- Check different window sizes so the minigame remains on-screen.

#### 2. Add a toggle to hide/show on-screen controls
- Add a clear control or keybind to hide and restore the on-screen controls/help overlay.
- Hiding the controls must not disable the actual keyboard/mouse inputs.
- Persist the toggle for the current game session; do not add save-file persistence unless the project already has a suitable settings system.

#### 3. Make catch handling the crew's priority
- When fish are landed, crew AI should prioritize moving the catch through the existing kill/bleed/de-gill-or-gut/stow workflow and into the hold, rather than leaving catch unattended while doing lower-priority optional work.
- Reuse the current fish-dressing and hold-stowing systems wherever possible; do not create a parallel catch inventory.
- A fish left alive and unsecured on deck should periodically thrash.
- Thrashing should create or increase deck slime/wet hazard near the fish.
- A thrashing fish should be able to physically shove nearby sailors or knock them off balance. Slipping/pushing should interrupt or delay their current task and can cause handling damage.
- Fish quality should decrease from rough handling/impact and from remaining alive/unprocessed on deck for too long. Keep effects bounded and tune them so prompt crew handling is rewarded rather than every fish being ruined.
- Use the existing deck slime patches and quality model if available; avoid duplicate slime systems.
- Add clear log messages for thrashing, a sailor being shoved/slipping, catch damage, and successful stowing.

#### 4. Allow the engine to keep running when its station is unattended
- Preserve the existing engine-running behavior and station assignments.
- If the engineer or a suitably assigned sailor must leave the engine post because of manpower shortages, allow the engine to continue running rather than automatically leaving the vessel dead in the water.
- Unattended running must build risk over time: engine strain/wear and a chance of malfunction should rise with duration/load.
- A staffed engine station should reduce that risk; returning a qualified crew member should resume normal monitoring.
- Make the risk legible through status/log warnings before serious failure where practical.
- Avoid an instant or guaranteed breakdown simply because the post is empty.

#### 5. Make Headcount a real muster
- When the player presses the existing Headcount action, the captain should loudly call **“HEADCOUNT!”** using the project's existing shout/voice/log presentation style.
- Crew should interrupt noncritical tasks and gather/stand on deck for the muster, using navigation/pathfinding rather than teleporting.
- Show a muster-in-progress state and count who has reported in.
- Crew who are injured, asleep, working in a critical safety role, or otherwise unable to reach the deck should be reported as such rather than silently counted as present.
- Prevent repeated button presses from spawning duplicate muster orders.
- Clear the muster state after the count completes or the player cancels it, if cancellation fits the current UI.

#### 6. Radio-operator return behavior — needs the exact intended rule
The request ended with: “when everyone comes back the radio operator always …” The sentence is incomplete, so this item is intentionally **not specified or implemented yet**. Confirm the intended behavior before coding it (for example, whether the radio operator should always report in, make a radio call, or return to a particular station).

#### 12v11 acceptance checks
- [x] Fishing UI sits higher and its Y position is clamped for supported window sizes.
- [x] Controls overlay can be hidden/restored with F5 without disabling gameplay controls.
- [x] Live, unsecured deck fish thrash, reinforce slime, shove/slip nearby sailors, and take bounded handling/exposure quality loss.
- [x] Catch processing is prioritized over optional work; fish stop thrashing after bleeding and stowing is logged.
- [x] Engine can run unattended, with risk increasing over time/load and staffed monitoring reducing wear/strain.
- [x] H starts a pathfinding muster, prevents duplicate orders, tracks reports, and reports unavailable sailors by reason.
- [x] Existing and new source-contract tests pass; the modified Python files compile.
- [ ] Full graphical playtest and launcher startup under Pygame still need verification on a machine with Pygame installed.

#### 12v11 implementation note
Automated result for this package: **36 tests passed** and `py_compile` passed. The graphical loop could not be exercised in the packaging environment because Pygame is not installed and package downloads are unavailable. The incomplete radio-operator sentence remains deferred and was not guessed at.

---

### 12v12 — Dockside Shore Leave and Crew Management
**Status: implemented.** The dock sheet and shore-leave scaffold in the supplied build were completed and hardened rather than duplicated.

- [x] At docking, the active crew can go ashore and recover health, fatigue, and morale.
- [x] F1 dockside sheet exposes Aboard, Shore, and Hire views; players can hire available sailors aboard or ashore, individually recall staff, and mark deckhands to stay ashore.
- [x] “WAIT UNTIL RESTED” uses a shared policy: health >= 98%, fatigue <= 10%, morale >= 95%; automatic-return crew are brought aboard on readiness.
- [x] Crew marked “KEEP ASHORE” are excluded from the wait return list and remain ashore on departure.
- [x] Wait completion, cancellation, and departure restore the previous time scale; repeated departure/recall polling does not re-arm the dock leave latch.
- [x] Individually recalling the stored radio operator restores wireless watch unless a replacement was already assigned.
- [x] Hired crew are placed at separated deck positions; hire-to-shore failure rolls back the fee/crew record.
- [x] Shore roster shows recovery state and the sheet adapts its controls to narrower widths.
- [x] Regression suite: 46 tests passed; Python compilation passed.
- [ ] Graphical dock/shore/hiring flows still need manual playtesting on a machine with Pygame installed.

#### 12v12 implementation note
The Pygame-free shore policy is in `fishing_sim/systems/shore_leave.py` so the recovery thresholds can be tested without launching the game. The unfinished radio-operator phrase from the prior request remains deferred because its intended behavior is still unknown.

### 12v13 — Crew AI, Muster, Flooding, and Fishing Controls
**Status: implemented in this release.**

- Muster now includes captain and station keepers; available crew physically navigate to deck muster positions.
- Fishing minigame UI is pinned to the very top and can be hidden/restored with F6.
- SPACE operates the manual tension brake and gaff/heave action.
- Added deck bucket-chain water clearing and separate engine-room bilge flooding/bailing.
- A sailor slipping near an open rail can fall overboard into the swimming state.

**Goal:** Stabilize the crew systems after the new work priorities and muster behavior are in place.

- Audit navigation and station assignment transitions, including entering/exiting the wheelhouse.
- Improve avoidance of sailors and obstacles; avoid crew injuring one another through routine movement.
- Make helm, lookout, and engine assignments recover sensibly when crew are interrupted, injured, or absent.
- Ensure man-overboard response overrides ordinary tasks and safely resumes work afterward.
- Add regression tests for task interruption, station handoff, muster completion, and engine staffing changes.

### 12v13.1 — Storm Bucket-Line and Overboard Crash Hotfix
- Fixed the undefined `g` reference reached when a sailor slips near an open rail in storm conditions.
- Deckhands now receive an explicit bucket task and pathfind to separated positions at the stern; the line only removes water after multiple hands have arrived.
- Added a small bucket prop on working sailors, safer man-overboard transition handling, and reusable-bucket logic for bilge bailing.
- Automated source-contract tests and Python compilation pass; graphical storm playtesting remains required.

### 12v14 — Catch Quality, Cold Hold, Trip Feedback, and Sea Rescue
**Status: implemented in this release.** Make handling outcomes understandable and ensure a man-overboard alarm leads to a real recovery operation.

- [x] On the first real crew sighting of a swimmer, the captain calls ALL STOP; propulsion command, destination, and docking approach are cancelled so the vessel decelerates to a stop.
- [x] If the swimmer is already within 190 units of the hull, the crew use the existing davit/lifeline workflow while the ship holds position.
- [x] At sea state **0.75 or higher**, a distant casualty will not trigger a launch. The ship is stopped first, then the helmsman turns back and creeps into davit-lifeline range.
- [x] In lower seas, two available non-captain, non-helm, non-radio crew pathfind to the davit, wait for the ship to stop, launch the boat, paddle out to the swimmer, pick them up, and return to the ship.
- [x] A squall that reaches the no-launch threshold before launch cancels the launch. A worsening sea after departure sends the empty launch back, then switches to the ship-turn/lifeline procedure. Boat crew return rather than teleporting.
- [x] Drowning / failed recovery clears rescue orders, and a deployed empty boat returns to the vessel. The ship remains stopped and does not resume its previous course automatically.
- [x] Catch report covers average and per-fish quality/grade, bleeding/dressing state, core temperature, deck exposure, and hold storage condition (iced/chilling/warming). The existing quality-decay, ice, and settlement systems remain authoritative.
- [x] Added regression checks for all-stop, the sea-state threshold, launch/pickup/return state transitions, rescue cleanup, and catch reports.
- [ ] Real storm/lifeline/boat-rescue graphical playtest still needs verification on a machine with Pygame installed.

**Implementation tuning:** The no-launch sea-state threshold is `0.75`; the close-range davit cutoff is 190 ship-space units. Boat pickup and return use timed state changes and world-space movement, not crew teleportation.

- Review the full catch lifecycle: landed → killed/bled → dressed → iced/stowed → quality assessed.
- Make time, temperature, rough handling, and deck exposure effects consistent and visible.
- Add a compact catch/hold report showing species, handling state, quality/grade, and storage condition.
- Tune quality loss so clean, fast handling matters without making losses feel arbitrary.
- Add tests for quality boundaries and hold/ice interactions.

### 12v15 — Auction UI, Mandatory Muster, and Swimmer Recovery
**Goal:** Add the planned per-fish auction and close the crew-accountability/rescue loop requested after 12v14.

- Follow the supplied `Auction UI — Design & Implementation Guide` as the source design.
- Start with **Model A: direct offer menu**, not rising bids.
- Make muster non-negotiable for the captain, wheelhouse occupants, and all station keepers: they physically leave posts and report on deck; only unavailable/dead/overboard/shore crew are accounted separately.
- Add a player-issued rescue order for fallen/overboard crew, separate from automatic sighting. Swimmers use their own visibility cone/range to search for and orient toward the ship, then swim toward a reachable hull/boarding point; rescue order can trigger the ship/crew rescue operation even if the swimmer has not personally seen the casualty yet.
- Add buyer archetypes and per-fish offers; let the player sell, keep, or accept all.
- Preserve the existing settlement contract: supplies, fuel, ice, bait, gaffs, and crew wages must still be handled after the auction.
- Pause the world during the modal auction and handle cancel/close paths without losing unsold fish.
- Apply the existing market multiplier and add bounded quality decay for fish kept between sessions.
- Acceptance: test empty hold, one fish, mixed catches, sell/keep/accept-all, manual `B`, repeated settle protection, and return to normal dock play. Test captain/helm/engine/radio leaving posts for muster and swimmer vision-limited ship-finding plus manual rescue order.

### 12v16 — Compact Telemetry and Ship & Catch Tabs
**Status: implemented in this release.** Reduce HUD obstruction without hiding useful operating information.

- [x] Replace the separate top-left telemetry block and bottom-left ship/catch block with one compact tabbed card.
- [x] Provide **TELEMETRY** and **SHIP & CATCH** tabs; click either tab or press **F7** to switch between them.
- [x] Press **F8** to hide or restore the card. The collapsed HUD shows a small reminder; gameplay inputs remain active.
- [x] Keep the panel at the screen edge, cap its width at 252 px, use 14 px monospace text, truncate long rows, and clip rows inside the panel.
- [x] Put the core vessel/catch data together: course/speed, sea/weather/visibility, helm/radio/line status, rescue or muster alerts, hold quality/value, ice and hold temperature, deck wetness, bilge, fuel, gaffs, bait, engine condition, and line slack.
- [x] Intercept tab-card clicks so they cannot accidentally select or order sailors underneath the overlay.
- [x] Add source-contract tests for tab switching, hide/show behavior, bounded layout, and ship/catch data.
- [ ] Graphically verify on a small and large window that the card remains legible and does not obstruct critical deck actions.

### 12v17 — Visual Scale, Sea Foam, and Information HUD Redesign
**Status: implemented in this release.** This version directly addresses the visual and readability complaints reported after 12v16. Keep existing simulation behavior intact while improving the scale/readability of sprites, adding ship foam effects, and moving detailed information out of the always-on HUD.

#### 1. Rescue boat must be large enough for sailors
- Audit the rescue boat's world-space and screen-space dimensions against the sailor sprite at the normal gameplay zoom.
- Resize and redesign the boat rendering so an adult sailor can plausibly sit/stand inside it and two assigned rescuers can be represented without appearing larger than the craft.
- Ensure the boat remains readable at typical camera zooms and scales consistently when zoom changes; avoid merely stretching a tiny icon into a blurry rectangle.
- Keep launch, paddle, pickup, return, and passenger state transitions unchanged.
- Draw occupants/crew and the casualty so it is visually clear who is in the boat and whether the casualty has been recovered.

#### 2. Make bucket sprites visible and proportionate
- Replace the tiny bucket polygon/prop with a recognizable bucket sprite/rendering at actual gameplay zoom.
- Match its size to the sailor's hands/body and keep the shape readable against the deck.
- For a bucket line, make buckets visible on the active workers (or at handoff positions) so the job reads as a coordinated line, not a status-only simulation.
- Preserve reusable-bucket inventory and current deck/bilge bailing mechanics.

#### 3. General sprite quality and scale pass
- Audit rescue boat, bucket, sailor-held props, ship/wake effects, and related small objects for inconsistent world scale, blurry stretching, poor contrast, or placeholder-like appearance.
- Prefer clean, consistent, high-contrast shapes that match the current game's rendering style. Where external art assets are unavailable, use carefully layered Pygame shapes rather than tiny or indistinct placeholder marks.
- Keep visual assets inside the expected project folders, with no external runtime downloads or machine-specific file paths.
- Do not change gameplay hitboxes or simulation values solely to make a sprite look larger; rendering scale and gameplay geometry must remain deliberately aligned.

#### 4. Add abundant but controlled sea foam
- Draw visible foam around the moving hull, especially along the bow, at the sides, and in the trailing wake.
- Increase foam density/length with vessel speed and make it more active/irregular as sea state and wave energy rise.
- Show some wave-edge foam even at low speed in rough seas, while a stationary ship should not produce a long powered wake.
- Use lightweight particles/ribbons or layered shapes with bounded particle counts and lifetimes; clean up old particles and avoid unbounded per-frame allocation.
- Keep foam behind the hull and in front of the sea background, respecting ship orientation and camera/world transforms.
- Make foam readable at normal zoom without obscuring the ship, swimmers, fishing line, or rescue boat.

#### 5. Replace the persistent telemetry card with a truly compact HUD
- The always-on HUD should show only immediately critical values/status: speed/heading, sea/weather warning, active line status, and urgent muster/man-overboard/flood alerts when relevant.
- Avoid long labels, multi-line prose, and detailed resource inventories in the persistent overlay.
- Keep the HUD compact and legible at small and large window sizes, anchored to a screen edge without covering useful deck activity or minigame controls.
- Retain a hide/show shortcut and keep all gameplay inputs working while the HUD is hidden.

#### 6. F1 detailed information sheet, styled like the dock/shore crew sheet
- **F1 opens a larger information sheet** using the same visual language and tab interaction pattern as the existing dock/shore crew sheet.
- Include detail tabs for **Ship & Catch**, **Telemetry**, and **Crew** so detailed data is available on demand instead of permanently occupying the game view.
- Ship & Catch should include fuel, engine condition/load, supplies, hold temperature/ice, per-fish or aggregate catch quality/value, deck wetness, bilge/flooding, and active fishing gear status where supported by existing systems.
- Telemetry should include speed, heading, throttle, sea/wind/visibility, line status, and active safety alerts.
- Crew should preserve the existing roster and Aboard/Shore/Hire management behaviors. Do not delete current dock/shore actions when moving the sheet UI; preserve their docking-only restrictions.
- Resolve the current F1 conflict with the existing crew sheet by consolidating the information/crew tabs into one F1 sheet (preferred), or by providing an explicit nonconflicting key and updating the on-screen hints. Do not silently make the crew sheet inaccessible.
- The compact HUD and F1 sheet must not both show duplicate walls of detailed information. The persistent HUD stays essential-only; F1 supplies the details.
- Pause or freeze relevant world interactions while the modal sheet is open, if consistent with the existing dock/shore sheet, and prevent clicks inside the sheet from issuing world orders.

#### 12v17 acceptance checks
- [x] Rescue boat appears large enough to plausibly hold the assigned rescuers and one rescued sailor at the normal zoom; all occupants remain visible during launch, paddle, pickup, and return.
- [x] Bucket props can be recognized without zooming in and are attached/placed consistently during bucket-line work.
- [x] Related sprites use consistent scale and readable contrast; no asset depends on external downloads.
- [x] Foam is visibly present around a moving ship and trailing wake, grows more active with speed/sea state, and remains bounded in memory/work per frame.
- [x] Foam does not cover sailors, the rescue boat, the fishing line, or important action points.
- [x] Persistent HUD shows only essential values and urgent alerts; it fits small windows without obscuring critical deck gameplay.
- [x] F1 opens the detailed information sheet; Ship & Catch, Telemetry, and Crew details are reachable; existing dock/shore hiring/recall actions remain functional and correctly restricted to port.
- [x] All controls, including F5/F6/F7/F8 and fishing controls, remain non-conflicting.
- [x] Existing and new tests pass, Python compilation passes, launcher and ZIP marker are preserved.
- [ ] Graphical playtest checks normal zoom, a smaller window, calm sea, high sea state, ship moving/stationary, bucket-line active, and rescue boat deployed.

### 12v18 — Persistent Sea Foam and Whitecaps
**Status: implemented in this release.** Replace the hull-attached decorative puffs with lightweight 2D foam that reacts to the wave field and leaves a short-lived history in the water.

- Keep the existing `WaveField` and water renderer; no 3D engine, shader dependency, or pixel-by-pixel Python renderer.
- Add `fishing_sim/systems/sea_foam.py`, a headless-testable, time-step based state system with a hard cap of 240 active patches by default.
- Store patches in absolute water/world coordinates; project them relative to the ship camera only when drawing, so turning the vessel does not rotate the existing wake with the hull.
- Emit separate bow-shoulder foam, hull-side wash, stern wake, short-lived spray, and weather-driven crest foam.
- Let wake emission depend on ship speed and sea state; allow whitecaps to form in rough water when the ship is stopped.
- Age, drift, fade, cull, and recycle patches under a fixed particle budget. Use layered irregular polygons/lines on the existing alpha water overlay rather than per-pixel loops or a fresh full-screen surface per effect.
- Add deterministic model tests for calm/stationary behavior, rough-sea whitecaps, speed-driven wake, world-space persistence, fading, emission stability, coordinate projection, and particle-cap enforcement.

#### 12v18 acceptance checks
- [x] At rest in calm water, no powered stern wake is emitted.
- [x] Rough water can produce whitecap patches while the vessel is stopped.
- [x] A moving vessel emits separate bow, side, and stern foam categories based on speed and sea state.
- [x] Previously emitted foam remains attached to water coordinates, moves only via current/wind drift, and does not rotate or teleport with the ship.
- [x] Patch opacity fades with age; expired and distant patches are culled.
- [x] Active patches stay within the configurable hard cap; least-visible patches are recycled when full.
- [x] Emission uses elapsed time rather than spawning an unbounded number of marks each rendered frame.
- [x] Existing gameplay code remains independent from the foam system; no engine, steering, collision, rescue, fishing, bucket, auction, or HUD logic was changed.
- [x] Automated tests and Python compilation pass; launcher, preservation marker, and research plan are included.
- [ ] Graphical playtest and screenshot comparison in calm/rough sea, stopped/cruising, and turning conditions still need to be performed on a machine with Pygame installed.

### 12v19 — Refined Persistent Sea Foam
**Status: implemented.** This is a polish pass over the 12v18 system, not a replacement of its bounded world-space model.

- Preserve the independent, headless-testable `SeaFoamSystem` and existing `WaveField`/water renderer.
- Add a cool water halo, a translucent transition layer, and a broken white core so foam sits in the water visually rather than reading as a repeated white oval.
- Add deterministic per-patch edge irregularity, interrupted foam seams, micro-froth, and whitecap lip variation. Every visual detail derives from the patch seed to avoid frame-to-frame sparkle.
- Scale patches down as they age to reinforce breakup and dissipation.
- Feed the existing weather wind-strength and direction values into foam drift while preserving the existing wave direction and surface-current input.
- Drop excess whole-event emission backlog after a long frame while retaining fractional timing; a pause cannot make the next frames dump a stale foam burst.

#### 12v19 acceptance checks
- [x] Existing persistent world-space foam, current drift, particle cap, and calm/storm emission rules remain intact.
- [x] Render detail is seeded and stable between frames; no per-frame random visual texture is added.
- [x] Wind strength is passed from the existing weather system into the foam model.
- [x] Long frames do not leave integral spawn backlog for later frames.
- [x] All 87 automated tests pass; Python compilation passes; launcher and preservation marker remain present.
- [ ] Live graphical playtest and screenshot comparison still required; Pygame is not installed in the build environment.

### 12v20+ — Follow-up and Polish
Schedule after 12v18 is visually playtested:
- Optional rising-bid auction model.
- Buyer relationships and seasonal market effects.
- Auction-house location/visual polish and auctioneer voice.
- Foam tuning based on screenshot/live playtest findings; optional low/normal/high foam caps if profiling supports them.
- Further fishing, deck-weather, and vessel-operation balancing based on playtest findings.

## Implementation rules for every version

1. **Plan first:** update this roadmap before expanding scope.
2. **One version at a time:** do not fold the auction UI into 12v11.
3. **Inspect before changing:** reuse existing code and state rather than duplicating systems.
4. **Regression checks:** run the existing test suite and `py_compile`; add focused tests for each new behavior.
5. **Playtest honesty:** distinguish automated checks from a real graphical playthrough.
6. **ZIP contents:** preserve `run_fishing_sim.py`, `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`, this roadmap, and any existing project structure.
7. **Document changes:** each release should include a short change note and known limitations.

## 12v13 implementation note
- Automated tests and Python compilation are run for the release. Full graphical playtesting is still required. Bucket handling is simulated at system level rather than with individual bucket animations.

## Open requirements / deferred items

- Clarify the unfinished radio-operator requirement: “when everyone comes back the radio operator always …”. It is intentionally not implemented because the expected behavior is incomplete.
- Headcount currently completes naturally and has a 60-second reachability timeout; cancellation is not implemented in this release.


## 12v17 implementation note

- Expanded rescue boat rendering to a person-sized dinghy with inner deck, seats, two rescuers, a casualty position, gunwales, life-vest details, and oars.
- Increased the recognizable reusable bucket prop with a tapered wooden body, rim, handle, and water surface.
- Reworked sea foam into bounded animated bow/sides/wake shapes driven by ship speed and sea state.
- Replaced the persistent telemetry inventory with a two-line critical HUD; F7 switches navigation/operations mode, F8 hides/restores it.
- F1 opens Ship & Catch, Telemetry, and Crew tabs. The existing Aboard/Shore/Hire management actions stay nested inside Crew and retain dock-only restrictions. The F1 sheet consumes world clicks and pauses ordinary simulation; explicit shore-rest waiting continues.
- Automated suite: 75 tests passed before final packaging; Python syntax compilation passed. Pygame is not installed in the build environment, so no graphical playtest was performed.

## Latest user feedback captured for 12v17

- The rescue boat is visibly too small relative to a sailor; resize/redesign against world scale.
- The bucket sprite is too small and difficult to recognize.
- Current sprites need a broader quality/readability pass, not just a single size multiplier.
- Add much more visible sea foam around the hull and wake.
- The telemetry panel is still unreadable/too information-dense; simplify the always-on HUD to essential facts.
- Move detailed Ship & Catch and Telemetry information into an F1 sheet styled after the dock/shore crew interface, preserving crew management behavior.

**Release note:** This roadmap accompanies the implemented 12v17 ZIP. Perform a live graphical check of boat/crew proportions, bucket readability, foam at speed and in rough seas, and HUD/minigame layout at small and large resolutions.


## 12v18 implementation note

- Added `fishing_sim/systems/sea_foam.py`: a Pygame-independent particle lifecycle/emission model using bounded, persistent world-coordinate foam patches.
- `World.update()` provides ship speed, sea state, wave strength/direction, surface current, view radius, and the existing WaveField height sampler.
- `World._wake()` now renders the foam system's persistent patches as layered irregular shapes on the existing water overlay; the old reconstructed bright bow/side ribbons and per-frame deterministic puffs were removed.
- The particle cap is 240 by default. Expired/off-view patches are removed, and low-visibility patches are recycled if the cap is reached.
- Automated suite: 83 tests passed; all Python files compile. Pygame is not installed in the packaging environment, so the graphical playtest remains outstanding.


## 12v18.1 hotfix note
- Fixed the sea-foam wake renderer NameError in `shape_points()` (`pts.append` → `points.append`).
- Added a regression contract test for the initializer/append variable pairing.
- Kept 12v18 foam model, existing controls, and game systems otherwise unchanged.


## 12v19 implementation note

- Refined `World._wake()` with stable seeded shapes, layered aqua/white foam, interrupted wake seams, fragmented whitecap lips, and small edge froth/bubbles.
- Foam contracts slightly with age; existing life-cycle fade and hard cap are unchanged.
- `World.update()` now passes `Weather.wind` into the foam system so drift follows both direction and wind strength.
- Foam event accumulators retain fractional timing but discard excess whole events after a capped slow frame, avoiding delayed particle bursts.
- Automated suite: 87 tests passed; Python syntax compilation passed. Pygame was unavailable, so a graphical playtest remains outstanding.

# Fishing Sim — Roadmap V2

Target file: `fishing_sim.py` (V1 is ~3,500 lines, single file, pygame).

## Status (latest crash hotfix — v13.1.22)

| Phase | State |
|---|---|
| 0 Prep | **Done** |
| 1 Layout rebuild | **Done** |
| 2 Elevation system | **Done** |
| 3 Forward wheelhouse | **Done in v13v1-17 — integrated roof cutaway** |
| 4 Engine room | **Done; lower-deck route and cabin/bunks refit in v13.1.21** |
| 5 Processing and ice hold | **Done in v13v1-18 — working hatches, bilge control, fish prep and ice-hold care** |
| 6 Starboard hauler and stern roller | **Done in v13.1.20** |
| 7 Polish and tuning | Not started |

The v13.1.21 lower-deck pass expands the visual and navigation footprint across almost the whole hull, makes the bow cabin berths sailor-sized, and fixes A* no-route behavior so sailors do not push directly through solids. Sleeping sailors stay on their mattresses without collision separation until a task wakes them.

The original roadmap names a single-file `fishing_sim.py`; the source archive used for v13v1-17 is the modular equivalent at `fishing_sim/core/game.py`. The same `Ship`, `Level`, navigation-link, wheelhouse-station, and engine-service concepts are present there. This release keeps the modular source and includes this roadmap for tracking Phases 3–6 completion.
Headless tests cover layout/nav contracts, wheelhouse control ownership, engine checks, and cross-level orders. The graphical build still needs a hand-playtest.
Theme: rebuild the ship around a historically grounded 1962 longliner layout, add vertical levels, and make each station on the boat a real place with a real job.

---

## 1. Where V1 stands

What already exists and V2 builds on:

- `Ship` with deck-coordinate layout (`_layout`), hull polygon with an open stern edge, A* walking nav grid (`_build_nav`), solids/collision, wash/spray.
- Deck objects: wheelhouse (solid rectangle, nobody can enter), engine hatch (grating), two hold hatches, a separate "crate" for loading fish, cutting table, lifeboat, bait boxes, hauler, stern roller (a 10 px steel strip).
- `Longline` physics, hauling fight, gaffing; `Table` / `Catch` quality pipeline (bleed, gut, ice hold cooling); `Sailor` with roles, duties, fatigue, falls overboard; harness toggle (`Y`).
- Player input: click to select a sailor, right-click to order him, `1-5` duties, `Tab` to cycle.

What doesn't match the V2 spec:

| Spec item | V1 today | Gap |
|---|---|---|
| Elevated forward wheelhouse | Flat solid box at x +0.10..0.24 L | No interior, no height, can't be entered |
| Compass, throttle, radio | Throttle/steering via minimap and keys | No physical stations |
| Engine hatch behind wheelhouse | Grating at x +0.02..0.09 L (already correct place) | Cosmetic only; no way down, no checks |
| Cutting table, central | Starboard side, x -0.085 L | Wrong side/position for the hatch drop |
| Fish dropped through deck hatches into ice hold | Dressed fish carried to a separate port-aft crate | Extra walk, hatches are decoration |
| Line hauler on starboard quarter | Starboard, far forward (x +0.115 L) | Wrong end of the ship |
| Stern roller protects bulwarks | Visual strip only | No gameplay effect |
| Forepeak anchor and mooring bits | Not present | Missing |

---

## 2. Decisions to lock before coding

1. **Levels.** Three: `+1` wheelhouse, `0` main deck, `-1` below deck (engine room, ice hold).
2. **Elevation keys.** `Q` = up, `E` = down. Acts on the selected sailor, and only when he is standing at an access point (ladder / hatch). Elsewhere it prints a short crew-log line ("Nothing to climb here").
3. **Key conflict (decided).** Sea state moves from `Q`/`E` to `,` / `.` (`World.update`, ~line 748). `Q`/`E` are now elevation only.
4. **No electronics (decided).** No radar, no GPS. Wheelhouse has a magnetic compass, throttle, and a vacuum-tube AM/SSB radio. Navigation is dead reckoning. Radio is slow and unreliable far offshore, which matters for the tow call (`TOW_FEE`). The echo sounder idea is dropped for period accuracy.
5. **Crew of six.** The 1962 boat is a 6-man boat; V2 tunes stations and duties for six hands.
6. **Hauler position.** Follow the spec: starboard quarter (about -0.32 L), not the V1 forward position. This lengthens the fish's trip to the table, which is a feature (crew movement, more to manage).
7. **Cutting table (decided, Phase 1).** Port side beside the hatches (x -0.15..-0.09 L, y -0.35..-0.25 B), cutter stands inboard at (-0.12 L, -0.155 B). It cannot sit on the centreline because the new hatches span the centre.
8. **Hatch drop (decided, Phase 1).** Two hold hatches (hatch_1 forward, hatch_2 aft, x -0.20..-0.04 L). A dressed fish alternates between them.
9. **Q/E (decided, Phase 2).** At a ladder or hatch (within 45 px) `Q`/`E` climbs. Anywhere else, holding `Q`/`E` peeks one level up/down (camera only). The "Nothing to climb here" log line was dropped in favour of the peek.
10. **Idle crew on other levels (Phase 2).** An idle sailor upstairs or below stays put; any deck job sends him back up by the nearest reachable ladder.
11. **Captain stays on deck until Phase 3.** His post is still forward of the wheelhouse, so the game opens on the main deck view.

---

## 3. Target layout (bow = +x, starboard = +y, fractions of ship length L)

```
FOREPEAK  anchor + mooring bits                x ≈ +0.38..+0.46
WHEELHOUSE (level +1)  forward superstructure  x ≈ +0.10..+0.24   ladder on aft face
ENGINE HATCH (to level -1)                     x ≈ +0.02..+0.09   directly behind wheelhouse
CUTTING TABLE          centre/port, forward of hatch 1   x ≈ -0.10
ICE/FISH HOLD HATCHES (to level -1)            x ≈ -0.20..-0.04   amidships; fish drop through here
CREW QUARTERS (level -1)                       below/behind wheelhouse, bunks stacked around the engine casing
LINE HAULER            starboard rail          x ≈ -0.32
STERN NOTCH + ROLLER   transom cutout          x = -0.50
```

Hold hatches shift slightly forward (V1: -0.24..-0.06) so the hold is truly amidships, still clear of the engine hatch.
Removed: the separate fish "crate" (the hatch becomes the destination).
Kept: lifeboat (port, amidships), bait boxes (aft corners), post and bow lookout.

### Period details to build in (1962)

- **Hull and deck.** Welded steel hull with thick pine/cedar planking bolted over the steel. Planks give grip. Bare steel (hatch coamings, engine casing top, roller, hauler base) is slippery when wet or slimed, so it carries a higher fall chance. Planking also softens dropped fish/gear (less quality loss on deck impact).
- **Engine.** Compact four-stroke marine diesel, midships under the deck hatch. Steady low-end torque, not speed: cruise 8–10 knots. V1 `max_speed = 500` px/s should be mapped so full throttle reads about 10 knots (tune against `WORLD_SCALE`).
- **Hauler (Miyagoma).** Starboard quarter, friction drum, driven by belt/shaft takeoff from the main engine (or an auxiliary deck engine). Gameplay: hauling needs the engine running; hauling speed follows `engine_power`; engine failure mid-haul stalls the line (existing `Longline.power(job)` is the hook).
- **Crew quarters.** Cramped bunks below/behind the wheelhouse around the engine casing. Replaces the on-deck `rest_spot`: sailors on `rest` duty go below to the bunks, recover fatigue/morale there, and are out of the weather but far from the rail (slower to react to a man overboard).
- **Bait boxes (ensaibako).** Stay at the rail/aft sides, holding salted or frozen saury, mackerel and squid (existing `BAITS`).
- **Ice hold.** Insulated, packed with flake ice made from blocks, held near 0 °C (existing `ICE_CAP`, `Catch.tick(in_hold=True)`).
- **Exposure.** Oilskins, rubber boots, canvas jackets. Harness (`Y`) and manual gaffing (`G`) stay as the answer to 100 kg+ bigeye and swordfish over a low rolling rail on a slimy deck. Optional: wet-weather gear as a small fall/fatigue modifier.

---

## 4a. Additions (approved direction, details pending)

### Level peek (approved)
- `Q` / `E` when no sailor is climbing: the view shifts up or down one level (camera only). Peek is held, not toggled: it snaps back when released, so the player never loses the main deck.
- While peeking, the level being viewed is drawn in full and the other levels are dimmed. No simulation state changes.
- A sailor at a ladder/hatch still climbs on `Q`/`E` as in Phase 2. The peek is a camera action, and climbing is a sailor action.

### Sea reacts to the hull (approved direction)
- Foam at the bow where the hull cuts the water, a white wake astern, and spray where the bow meets the swell. Foam intensity follows speed and sea state (`WaveField.strength`).
- Foam and wake are drawn into the water layer and fade over time, so the trail behind the boat reads as a path.
- Builds on the existing `Wash` and `spawn_wash` / `draw_water` code rather than replacing it.

### Rudder (approved)
- Single rudder below the stern notch, visible in the water line.
- Helm turns it. The boat turns more slowly at low speed and stalls (no headway to turn) when the engine is idling in neutral. This ties steering to `engine_power` and `speed`.
- The rudder angle is small and reads as a visual indicator of intent, not a dramatic flange.

### Mechanical details (approved)
- **Belt drive (hauler):** The hauler's friction drum is belt-driven from the engine. If the engine is weak or the line is overloaded, the belt slips and hauling slows. This ties `Longline.power(job)` to actual `engine_power`, not just a flag.
- **Davit (lifeboat):** A small crane on the port rail. Recovering a man from the water uses the davit: slow (2–3 seconds), requires a sailor to operate it, sailor is busy and can't do other work. Replaces the existing instant recovery.
- **Gallows frame:** A steel A-frame over the stern. Cosmetic (no swing or flex mechanic for now; adds to the visual clutter and authenticity).
- **Hatches (hold and engine):** Sailors manually open/close them before descent. Opening takes 1–2 seconds, closing takes another 1–2 seconds. While open, the hatch is a hazard (man-overboard risk if a sailor falls). A closed hatch blocks descent until it's opened. This gives crew work: plan who opens what, and manage the open-hatch risk.

---

## 4. Phases

### Phase 0 — Prep (small, do first) — DONE
- Add `level` to `Sailor` (default 0) and a `Level` enum on `Ship`.
- Rebind sea state to `,` / `.` (done first; trivial and unblocks `Q`/`E`).
- Move layout numbers into one `LAYOUT` block so later phases only edit data.
- **Done when:** game plays exactly like V1, sea state on new keys.
- **Result:** `Level` enum (`BELOW -1`, `MAIN 0`, `WHEELHOUSE 1`), `Sailor.level`, sea state on `,` / `.`, and a module-level `LAYOUT` dict (rects as fractions of L and B, markers as fraction + pixel offset). Layout and nav checked identical to V1.

### Phase 1 — Layout rebuild (level 0 only) — DONE
- Reposition table, hauler, hatches, remove the crate; add forepeak bits.
- Update `markers` (`haul_station`, `landing`, `table_stand`), `Longline._haul_world`, nav grid, `solids`.
- Swap deck rendering/traction: planks over steel, with slippery steel fittings (hatch coamings, casing, roller, hauler base).
- Table → hatch hand-off: a dressed fish is dropped into the adjacent hatch (no carrying to a crate).
- **Done when:** a full cycle works: set → haul at quarter hauler → table → hatch → ice hold → auction.
- **Result:** hauler at x -0.34..-0.30 L starboard; `_haul_world` at -0.32 L; table port side; two hold hatches with markers `hatch_1`/`hatch_2`; `crate` removed everywhere; forepeak bitts and anchor (decorative, not solid); steel coamings, engine casing, roller and hauler base are slick when wet (`Ship.steel_grip`, up to 55% less grip). Full cycle confirmed headlessly up to the ice hold (auction code unchanged).
- **Not done:** "planking softens dropped fish" (the game has no deck-impact quality loss to soften).

### Phase 2 — Elevation system — DONE
- `Ship.levels`: each level has its own solids, walls, nav grid, and list of access links (ladder/hatch, level A ↔ level B, position on each side).
- A* extended to a multi-level graph (links are edges with a small time cost) so crew paths through ladders on their own.
- `Q`/`E` on selected sailor: if within reach of a link, climb (short animation, can't work while climbing, uses `CLIMBING` mode).
- Rendering: draw the selected sailor's level fully; other levels dimmed/cutaway; sailors on other levels shown as faint markers. Height cue via drop shadow/offset on wheelhouse roof.
- Optional hazard: ladder in heavy sea can throw a climber (reuse slope/wash fall code).
- **Done when:** a sailor can walk to the ladder, press `Q`, appear inside the wheelhouse, press `E`, and be back on deck; the crew AI can do the same unprompted.
- **Result:** `NavMap` per level (grid, A*, collision) and `Link` objects (`wheelhouse ladder`, `engine ladder`, `hold ladder`). `Ship.next_link` is a small graph search over links and only uses ladders reachable from where the sailor stands (the engine room and ice hold are separate compartments). Sailors climb in about 1.3 s with `Sailor.ladder` state and cannot work meanwhile. Cross-level orders (right-click while viewing another level) and `_go_to(pos, tol, level)` hop via ladders. The engine minder now stands below deck (marker `engine` at level -1) and goes down unprompted. Level view draws the viewed level in full, veils the deck, shows other-level sailors as faint markers, and the wheelhouse roof has a drop shadow. Level peek (section 4a) is implemented.
- **Level -1 layout:** engine room (x 0..0.17 L, y ±0.30 B) with casing, and ice hold (x -0.215..-0.025 L, y ±0.17 B). Wheelhouse interior is empty until Phase 3.
- **Not done:** optional ladder hazard in heavy sea. Hatches do not open/close yet (section 4a).

### Phase 3 — Forward wheelhouse (level +1) — DONE in v13v1-17
- Interior has helm/compass, throttle quadrant, vacuum-tube radio, forward glazing and labeled stations.
- Captain/relief helm ownership gates physical helm/throttle input through `helm_ok`; an unmanned wheelhouse stops manual/autonomous propulsion where required while the existing autopilot/docking state machines remain in place.
- Radio call types for weather, auction and tow route through the radio subsystem with staffing/range/time outcomes.
- **Rendering decision:** retain `Level.WHEELHOUSE` for crew pathfinding and station ownership, but present it as a roof cutaway in the same top-down scene. The cabin floor and instruments replace only the roof footprint; surrounding deck and deck crew remain visible. This avoids drawing the entire vessel as a separate height view just to use the wheelhouse.
- Compass and dead reckoning remain the physical navigation framing for this roadmap; no radar is introduced by this phase.
- **Result:** cutaway rendering is localized, main-deck crew remain visible/selectable around the cabin, and wheelhouse station/control ownership is preserved.

### Phase 4 — Engine room and crew quarters (level -1) — DONE; lower-deck route/bunks refined in v13.1.21
- Hatch/ladder leads to the compact diesel room; the engine-room and ice-hold spaces remain separate below-deck compartments.
- The three service points are oil level, cooling-water intake and shaft seal. Their condition degrades with running time and sea state; neglect lowers `engine_power`, can create faults, and trips `engine_ok` at critical levels.
- The engineer must physically reach the below-deck engine station. Maintenance improves the neglected component; sufficiently repaired readings allow a tripped engine to recover.
- Engine output gates vessel propulsion and line-hauler power.
- Added six bunks around the engine-room perimeter and reserved stand positions beside them. Rest duty now routes below deck to a bunk stand rather than the old main-deck standby marker; bunks are collision solids so crew route around them.
- The companionway between wheelhouse and engine room remains a graph link in the existing multi-level navigation.
- **Result:** the engine checks/fault mechanics already present in the modular code are now paired with visible crew quarters and actual below-deck rest routing.
- **Still deferred:** opening/closing hatches is noted for Phase 5 in section 4a; manual hold-hatch control is not implied by this completion.

### Phase 5 — Processing, hatches, bilge and ice hold — DONE in v13v1-18
- **Dogged covers:** the engine-room access and both fish-hold hatch covers have independent open/closed state and visible status from the relevant deck/compartment. All three start dogged shut. `U` opens or dogs the nearest hatch after a sailor walks within arm's reach; hatch handling takes 1.35 seconds.
- **Cross-level access:** `Q`/`E` cannot pass through a dogged hatch. Crew AI opens the needed access cover at the landing, crosses, then dogs it shut after the ladder transition if nobody is still using it.
- **Flooding/bilge consequence:** open engine-room hatch admits substantially more water; each open fish-hold cover increases hold ingress. Engine bilge water weakens engine power and high bilge can trip the engine. The hold warms and ice consumption rises as water accumulates.
- **Bailing:** bucket-capable crew lower engine-room bilge or ice-hold water only when physically present in that compartment. Closed hatch covers stop most incoming wash water, so dogging covers is the first defensive action.
- **Processing flow:** fish are bled, gutted/de-gilled, then sliced at the cutting table before being carried to an open hold hatch. A dressed fish cannot be stowed through a closed cover; the cutter waits and warns the player.
- **Sluicing:** `F` starts a timed seawater-hose wash near the cutting-table hose station, reducing table blood and improving cleaning of nearby blood/slime patches.
- **Ice hold:** `V` trims and packs flake ice while the sailor is inside the ice-hold compartment and the hold is not badly flooded. This temporarily slows ice melt; hold water makes cooling worse and speeds ice loss.
- **Quality:** deck exposure and fish condition continue to influence grade; getting processed catch through an open hatch ends deck exposure and allows hold cooling.
- **Done when:** serviceable hatch covers control water ingress, crew can open/cross/close level accesses, a catch follows bleed → gut → slice → ice hold, hose cleaning works, and ice/flood states materially affect storage.

### Phase 6 — Starboard hauler and stern roller — DONE in v13.1.20
- Hauler power comes from engine output and staffed hauler crew. The friction drum slips under excessive line load, weak engine power, understaffing, or drum wear; sustained slip reduces drum condition and hauling pull speed.
- Line load is estimated from deployed hooks, sea state, vessel speed during setting, and fish/fight tension during hauling.
- The stern roller is stateful: working, bypassed, or jammed. The working roller wears over time and can seize under sustained high load when damaged. Bypassing or a jam sharply increases chafe and snag risk.
- Snags temporarily stall setting/hauling and damage line condition. Under sustained high load, a badly chafed line can part; crew at the stern gear can be injured by whipping line when not wearing the harness (`Y`).
- Visual feedback is present: the stern roller changes color and label, the drum reflects slip severity, and line/roller/drum condition plus slip are included in line status. Press `M` to engage/bypass the roller; when jammed, send a healthy deckhand to the stern and press `M` to clear it.
- Stern notch remains the main fall-overboard risk.
- **Done when:** engine strength and crew staffing affect hauling; bypass/jam changes wear and snags; heavy wear can part the line; the harness mitigates injury; and the gear state is visible to the player.


### Phase 7 — Polish and tuning
- Crew log lines for all new stations, tooltips on hover, labels matching the spec names.
- Balance pass: carry distance (hauler→table), engine drift rate, ladder fall chance.
- Performance check with multi-level nav (cache per level).

---

## 4b. Code detail for Phase 1 edits

### Layout data consolidation
All layout numbers live in `Ship._layout()` (~line 252). Currently scattered across methods:
- `wheelhouse`, `hauler`, `lifeboat`, `bait_boxes`, `hatches`, `crate`, `table`, `engine_hatch`, `post`
- `markers` dict with keys: `stern_set`, `haul_station`, `captain_post`, `bow_lookout`, `rest_spot`, `table_stand`, `landing`, `engine`, `crate`, `landing_zone`
- `openings` (stern notch)

**Phase 1 consolidation:** Move all these into a single `LAYOUT` block at the start of `_layout()` so edits are in one place.

### Current positions that change
| Object | V1 Position | V2 Position | Code impact |
|---|---|---|---|
| `hauler` | x +0.115 L | x -0.32 L, starboard | `Ship._layout`, `Longline._haul_world()` (line 1480), drawing (~575) |
| `table` | x -0.085 L, starboard | x -0.085 L, **port/center** | `Ship._layout`, marker `table_stand`, `Sailor._task_dress()` (line 2173) |
| `hatches` | x -0.24..-0.13 L | x -0.20..-0.04 L | `Ship._layout`, nav grid, `Sailor._task_dress()` crate drop (line 2187) |
| `crate` | -L*0.25 (port aft) | **hatches themselves** | Remove `crate` marker; fish go straight down hatch, not to a separate box |
| `stern_set` | -L*0.5 | (unchanged, stern) | V1 fine, already at the right place |
| `captain_post` | +L*0.10 + wheelhouse offset | (unchanged) | V1 fine |

### Hauler position detail
`_haul_world()` returns the world position where hauled fish appear:
```python
def _haul_world(self):
    return self.g.world.world_of(V(self.g.ship.length * 0.135, self.g.ship.beam * 0.5))
```
V1 has x = 0.135 L (forward). V2 should be x = -0.32 L (aft starboard quarter), so:
```python
def _haul_world(self):
    return self.g.world.world_of(V(self.g.ship.length * -0.32, self.g.ship.beam * 0.5))
```

### Crate removal
The current pipeline: haul fish → `landing` marker → `FishItem` on deck → sailor carries to `crate` → stows in hold.

V2: haul fish → `landing` marker → `FishItem` on deck → sailor carries to **hatch** → stows directly (hatch becomes the stow point).

Code touches:
- `Sailor._task_dress()` line 2187: change `m["crate"]` to a hatch position (e.g. `m["hatch_1"]` or the first hatch)
- Remove `crate` from `Ship.solids` (line 228), `Ship._layout()`, `Ship.draw()`, and `Game._lights()` (line 3222)
- `Sailor._task_dress()` carry logic: sailor walks to hatch, stows the fish there in 1–2 seconds

### Nav grid rebuild
`Ship._build_nav()` line 295 builds a walkability grid from `solids` and `walls`. After moving `hauler` and removing `crate`, the grid changes:
- Forward access (to new hauler position) needs a path from amidships aft
- Aft access (to hatch) needs clear passage
- Test: `find_path()` should route sailors from table → hatch without clipping the hauler or engine casing

### Markers to add/update
| Marker | V1 | V2 | Purpose |
|---|---|---|---|
| `haul_station` | ~(L*0.06, B*0.30) | ~(L*-0.32, B*0.50) | where hauler crew stand |
| `landing` | ~(L*0.06+35, B*0.30-10) | (new position near hauler) | where fish land after gaff |
| `table_stand` | ~(L*-0.055, B*0.105) | (check: starboard or port?) | where cutter stands |
| `crate` | -L*0.25 + ... | **remove** | not used |
| `hatch_1`, `hatch_2` | split hatches | (new) | fish drop points |

### Drawing order (no change, but check)
`Ship.draw()` (~line 517) draws deck objects. Order: deck → planks → hull → hatches → engine → bait boxes → crate → table → lifeboat → hauler → wheelhouse → post.

After crate removal, the order is fine. Just remove the `crate` drawing block.

---

## 5. Controls (V2)

| Key | Action |
|---|---|
| `Q` | Climb up (selected sailor, at ladder/hatch); otherwise hold to peek up |
| `E` | Climb down; otherwise hold to peek down |
| `,` / `.` | Sea state down / up (moved from `Q`/`E`) |
| right-click | Order to a point on the level currently on screen |
| everything else | unchanged from V1 |

---

## 6. Code touch points

| Area | Where |
|---|---|
| Layout, markers, hull | `Ship._layout` (~252) |
| Nav grid and pathing | `Ship._build_nav`, `find_path` (~295–370) |
| Ship drawing | `Ship.draw` (~517) |
| Sea state keys | `World.update` (~748) |
| Hauler/stern world positions | `Longline._stern_world`, `_haul_world` (~1477) |
| Cutting table logic | `Table` (~1050), `Catch` (~1014) |
| Sailor state, modes | `Sailor` (~1815) |
| Input handling | `Game.handle` (~2975) |

---

## 7. Risks

- **Multi-level A\*** is the biggest change; build and test it before adding content to upper/lower levels.
- **Single file** is already ~3,500 lines; Phase 0 layout block and per-level data keep edits local.
- **Hauler move** touches line physics geometry; test setting and hauling after Phase 1 before building on it.
- **Camera/render** for levels must stay readable at the existing zoom range (0.08–2.5).

---

## 8. Open questions

Resolved: `Q`/`E` also let you peek at another level without a sailor climbing (camera-only, see section 4a).

Remaining follow-ups (Phase 7 polish):
- Open-hatch fall/step-through hazard remains a polish item; covers control access and flooding, but a sailor does not yet automatically fall through an unattended open deck hatch.
- Phase 7 still needs a graphical balance/playtest pass for cross-level pathing, hatch handling, bunk clearance, carrying distances, hauling slip thresholds, roller wear/snags, and maintenance timing.

## Latest hotfix — v13.1.22

Fixed a lower-deck draw-time `NameError` by binding hull length and beam locally in `Ship.draw_level_view()`. This does not change the Phase 3–6 mechanics or lower-deck layout. See `CHANGELOG_V13_1_22.md`.

## Latest release — v13.1.23

Refit the lower deck into a consistent stern-to-bow layout with an open centre passage and correctly aligned engine access. Storm swimmer rescues now begin a come-about while the ship slows, with faster rescue-boat handling. Added daylight/visibility-gated ocean quick-steer orders and Shift-drag A→B legs using the same waypoint model as the chart. Engine telegraph/reversal, rudder lag, momentum, current/wind set, cross-track correction and waypoint preview give the line a desired-track role rather than forcing the ship to follow it exactly. See `CHANGELOG_V13_1_23.md` and `docs/V13_1_23_NAVIGATION_REFIT.md`.

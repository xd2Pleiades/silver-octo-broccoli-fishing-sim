# Fishing Simulator — v13.2 Optimized World, AI Traffic & Ship Radio Roadmap

**Status:** Active implementation roadmap; implementation status recorded through v13.2.05  
**Baseline:** v13.1.34 merged project  
**Source design:** `Plan 13.2.xx.md` (world scale, AI ship traffic, radio identities, trust and relationships)  
**Companion systems:** `Roadmap_V2.md`, `FISHING_SIM_v13_ROADMAP.md`, `TOW_REQUEST_AND_DISTRESS_RADIO.md`, `TOW_ESCORT_COMMUNICATION.md`, `SINKING_AND_ABANDONMENT.md`  
**Target area:** Phase A regional waters first; architecture must support Phase B high seas without rebuilding the simulation  
**Target code modules:** `fishing_sim/world/traffic.py`, `chunk_manager.py`, `weather_grid.py`, `persistence.py`, `fishing_sim/systems/ship_radio.py`, and a thin integration layer in `fishing_sim/core/game.py`

> This document expands the supplied Plan 13.2.xx into an implementation order that minimizes duplicated simulation, risky rewrites, save breakage, and wasted frame time. It is a roadmap, not a claim that these systems are implemented. Mark each milestone only when its acceptance tests pass.

## Current Status — v13.2.05 (2026-10-22)

M8's shared-identity adapter remains in place, and v13.2.05 adds the first M9 distress-dispatcher slice plus the merged WIP hull-wave/flooding mechanics. The Coast Guard launch still uses one stable `vessel_id` across its sea-view hull, chart marker and radio contact. Its versioned escort snapshot APIs are not yet connected to the legacy career save/load path.

M9 now has deterministic low-frequency distress selection for coarse or non-rendered vessels in radio range, a one-shot MAYDAY state, uncertain reported position, high-priority radio interruption, bounded rescue-contact promotion, and a modal player ASSIST/IGNORE choice. The chosen action applies +0.40/-0.50 trust exactly once on the current traffic entity. **This is not yet physical rescue dispatch**: assisting acknowledges the MAYDAY and records the relationship outcome, but does not yet make the player's boat or Coast Guard physically intercept the distressed ship. Full career-save integration is still M10 work, so the new dispatcher primitives are not yet durable through the full legacy career save/load flow.

The uploaded v13.2.04 WIP was three-way merged into v13.2.04's newer branch before M9 implementation. It contributes `HullWaveInteraction`, bounded water ripples, rail slap/overtopping, deck-water boarding, scupper drainage, compartment flooding, bilge pumping, list/free-surface stability, telemetry and the existing severe-foundering abandon-ship path. It has unit tests but no live Pygame playtest in this environment.

| Milestone | Current state | Still outstanding |
|---|---|---|
| M1–M4 — deterministic traffic foundation | Phase A slice delivered | Full source-plan fleet, Phase B content, local collision/avoidance and expanded map bounds |
| M5 — selectable ship radio | Initial UI slice delivered | Ambient/overheard traffic, full conversation catalog and broad queue persistence |
| M7 — regional weather grid | Phase A grid, fixed ticks, forecast and snapshot APIs delivered | Measured tick remains ~2.86 ms vs 2 ms target; career-save wiring and weather-driven market/tow effects remain outstanding |
| M8 — shared Coast Guard/tow identity | First integration slice delivered in v13.2.04 | M10 career save/load migration, physical rescue outcomes, line-part/reconnect consequences, and runtime graphical validation |
| M9 — distress/MAYDAY | **First dispatcher and player-choice slice delivered in v13.2.05** | Actual assistance vessel/route/intercept, physical rescue outcome, raft integration, global save/load durability, and more complete priority/dispatcher coverage |
| M6, M10–M13 — social dynamics, persistence hardening, expanded Phase A/Phase B and release hardening | Partial or deferred | Follow roadmap order; profile weather before expanding fleet and map |

**Current weather-source boundary:** the legacy shipboard `Weather` object remains authoritative for the player vessel. The regional grid assimilates those observations into the player's current cell and supplies regional variation for remote traffic/radio reports. It does not yet replace legacy market or tow-line weather calculations.

**Current Coast Guard ownership boundary:** `TowEscort` remains the authority for the captain, four-person crew, hull motion, handover, and tow state. A compatible runtime `AIShip` adapter with the same stable `vessel_id` supplies the shared spatial index, radio candidate, and chart marker. It is intentionally not a second simulated hull. Versioned escort snapshot APIs are available but are not yet called by the global career save/load path.

**Current distress/flooding boundary:** the MAYDAY dispatcher and flooding model are active in this build. Assistance is currently a radio commitment/trust event, not a world-driven physical rescue; the foundering model invokes the existing abandon-ship flow but does not yet finish the full liferaft survival/rescue design. Standalone traffic/escort snapshots are not a replacement for M10 global migration.

All Markdown files remain under `/docs`; historical source-plan variants are preserved under unique names. See `V13_2_05_IMPLEMENTATION_STATUS.md`, `MERGE_REPORT_V13_2_05.md`, and `TEST_RESULTS_V13_2_05.txt` for exact boundaries and evidence.

---

## Implementation Status — v13.2.02 (2026-10-22)

This release adds the first player-facing fleet radio panel to the v13.2.01 traffic foundation. The implementation remains a regional vertical slice, not the full fleet/radio world described by the original plan.

| Milestone | v13.2.02 status | Evidence / boundary |
|---|---|---|
| M5 — ship-radio UI and selected-contact interaction | Initial UI slice complete | Click RADIO beside ANCHOR or press Ctrl+F11. Nearby ships are listed with individual radio-range status; a selected contact can be hailed or asked about position, weather, activity, grounds, crew, or identity. Conversations advance line-by-line and are logged as the player reveals them. |
| M5 — truth/report separation | Improved | Position replies update reported positions; chart rendering continues to show reports rather than true live positions. Corporate grounds questions are declined, while peer responses depend on personality and trust. |
| M5 — operator and input safety | Initial slice complete | The UI explains when radio watch is unavailable or a channel is busy; it consumes modal input and suppresses held gameplay keys. Plain F11 remains fullscreen. |
| M6+ — ambient/overheard dispatch, priority MAYDAY, save migration, persistent fleet relationships, full fleet and Phase B | Deferred | The current panel uses the existing coarse scheduled Phase A population and local weather. Global save/load integration, ambient traffic, complete priority preemption and AI distress response are not yet included. |

The historical v13.2.02 UI scope is recorded in `V13_2_02_RADIO_UI.md`. The original plan `Plan 13.2.xx.md` remains the full target design.

---

## Implementation Status — v13.2.01 (2026-10-22)

This section records the first code release against the roadmap. The full plan below remains the target state; entries below distinguish delivered work from deferred behavior.

| Milestone | v13.2.01 status | Evidence / boundary |
|---|---|---|
| M0 — compatibility baseline | Complete | Existing v13.1.34 game loop and prior fishing, crew, rescue, navigation and tow behavior retained; traffic is integrated through a thin adapter in `core/game.py`. |
| M1 — deterministic world primitives | Complete for first slice | Stable CRC32 seeds and vessel IDs, NM coordinates and reversible local projections, distance/bearing helpers, versioned contact snapshot helpers. Full career-save migration remains deferred. |
| M2 — coarse Phase A fleet | Initial slice complete | 23 named regional vessels with deterministic closed schedules; coarse position/activity sampling is every 3 simulation seconds; pre-season corporate catcher/mothership activity is constrained. Full source-plan fleet (461 entries by computed archetype totals) is not spawned yet. |
| M3 — spatial index and LOD | Initial implementation complete | Sparse 20-NM uniform grid; distinct 12-NM active and 40-NM warm radii; nearest-first active cap of 30; query sorting is distance then stable ID. |
| M4 — Phase A contacts/rendering | Partial | Nearby active traffic gets small hull silhouettes; close visual sightings and successful radio replies create reported positions; chart renders only known reports and staleness, not true live positions. Local collision/avoidance and expanded regional chart bounds remain future work. |
| M5 — ship-radio vertical slice | Partial | `Ctrl+F11` makes a range-gated fleet hail, considers listeners in distance order without letting a silent listener block the next, and routes a successful multi-turn exchange through existing broadcast/Notebook systems. Replies cover core peer/corporate/official/hostile/weather cases. Continuous ambient traffic, complete priority dispatcher, MAYDAY orchestration and full template catalogue are deferred. |
| M6+ — social policy, weather grid, full rescue, global save migration, unified Coast Guard identity, Phase B | Not yet implemented | Retained in the plan and staged according to dependency order; no claim of full implementation in this release. |

**Key binding correction:** plain `F11` remains fullscreen. In v13.2.01, `Ctrl+F11` sent a quick fleet hail; in v13.2.02 it opens the selectable fleet-radio UI, where the player chooses a vessel and topic.

**Performance policy:** no NumPy dependency added. Coarse schedules use their own seeded random streams; world samples are ticked rather than recomputed per render frame. Chart marker drawing iterates the sparse known-contact set rather than the whole fleet. Local sea-view rendering is limited by weather visibility; radio reach does not itself reveal a far-away hull. A standard-library micro-benchmark (`tools/benchmark_v13_2_01_world.py`) measured about 0.0493 ms per scheduled update of the shipped 23-vessel Phase A set, 22.78 µs per radio-candidate query, and 0.504 ms mean world generation on the build host. These are local micro-benchmark results, not a full-frame or 461-vessel performance guarantee.


---

## 0. Executive Decision

Build **one world simulation with multiple levels of detail**, not a separate world for each map zoom or a separate ship model for every feature.

The most efficient implementation strategy is:

1. Keep the current playable v13.1.34 game loop running; integrate through small adapters instead of rewriting `game.py` all at once.
2. Create a bounded, deterministic fleet schedule first. The coarse fleet is only a few hundred records, so it does **not** need per-frame AI or complicated chunking.
3. Use a spatial index to find nearby ships for charting, visual activation, collision, radio, and rescue queries. Those systems may use different radii but should share the same candidates/index.
4. Keep actual ship state and reported/believed state separate. Radio dialogue is a claim, not a direct read of hidden truth.
5. Run low-frequency systems on simulation-time schedules. A distant ship should not execute AI every rendered frame.
6. Make save/load and deterministic tests part of the first vertical slice, not a final cleanup phase.
7. Implement the regional slice completely before populating the full North Pacific. Build the coordinate and persistence foundations for the high-seas area now, but defer content density until profiling confirms the foundation is cheap.

### Optimization decisions (locked unless profiling disproves them)

- **No per-frame loops over every fleet member.** Coarse ships use schedules and event-driven transitions.
- **No mandatory NumPy dependency at the start.** The proposed weather grid is only about 5,355 cells; use simple numeric storage first and benchmark before adding a dependency or vectorizing.
- **No duplicated Coast Guard ship.** The existing v13.1.34 tow launch should be adapted into the world-traffic identity when appropriate, rather than creating a second marker/actor for the same vessel.
- **No full-simulation replay on load.** Persist live weather snapshots and player-modified/contacted ship state.
- **No global `random` state shared by unrelated subsystems.** One new random draw must not change ship names, weather, hotspot spawning, and radio responses at the same time.
- **No premature procedural chunking of the bounded fleet.** Chunking controls which individual entities are active; it is not needed to store a few hundred schedule rows.
- **No truth leakage to the player.** Internal state can be exact; normal chart/report UI must use the player's fix or a contact's last transmitted position.
- **No new architecture without a measured problem.** Profile chunk activation, weather ticks, dispatch, save size, and active rendering before optimizing further.

---

## 1. Scope, Player Role, and Core Rules

The player remains an **independent longline vessel out of Hakodate**. Other vessels belong to distinct social and operational groups: independent peers, corporate catchers, corporate longliners, motherships, Coast Guard, and Soviet trawlers.

The social model should express these differences without special-casing every dialogue line:

- Independent peers may exchange useful information, gossip, or become rivals.
- Competitive peers may misdirect grounds reports until trust improves.
- Corporate catchers normally decline to share company fishing grounds; this is not the same as lying.
- Motherships coordinate and manage their contracted fleet; they do not control the independent player.
- Coast Guard communications are procedural and safety-first.
- Safety traffic and MAYDAY events can cross normal social boundaries.

### 1.1 Truth versus belief

Use distinct data paths throughout the code:

| Data | Used for | Must not be used for |
|---|---|---|
| `position_true` / physical position | Movement, collision, land avoidance, actual radio propagation, AI navigation | Direct player chart display by default |
| `position_believed` | Player dead-reckoning chart, player-reported position | Physical collision and simulation truth |
| `last_reported_position` | AI contact chart marker and stale-contact display | Exact live ship movement |
| `actual_hotspot` | Fishing and internal AI outcome | Direct dialogue/UI unless revealed by gameplay |
| `reported_hotspot` | Radio context and player hypothesis | Replacing actual fishing ecology |

Avoid globally renaming every current position field in one release. Introduce a compatibility layer and convert each caller intentionally. Existing towing and chart behavior must continue working during the migration.

### 1.2 Coordinate and unit contract

- World simulation: nautical miles (NM), stored as Python floats/doubles.
- Screen drawing: camera-relative pixels only; subtract camera origin before converting to integers.
- Time: one canonical monotonic **simulation-time seconds** value. Convert to in-game clock/date only at presentation boundaries.
- Bearings: degrees clockwise from north at the interface; one internal convention only.
- Speeds: store or name explicitly as knots (`speed_kn`) or NM/s; never use an unlabelled `speed` field at system boundaries.
- Radio reach: nautical miles; use physical positions for the propagation check and believed/report positions for what the player sees.
- Keep current ship-specific units where required, but put explicit conversion helpers at module boundaries. Never copy constants such as 185.2 or 1852 into a new module without using the shared canonical constant.

Add unit-tagged names (`range_nm`, `speed_kn`, `elapsed_s`) to prevent silent scale errors.

---

## 2. Fleet Composition and Seasonal Population

### 2.1 Use explicit counts as configuration

The source plan proposes these initial archetypes:

| Archetype | Starting pool | Operational behavior |
|---|---:|---|
| Corporate catcher | ~300 | Mostly clustered around 11 motherships; quota and collection schedule |
| Mothership | 11 | Rare control/collection contacts |
| Independent gillnetter | ~80 | Coastal and near-box traffic |
| Independent longliner | ~40 | Small named social pool |
| Corporate longliner | ~15 | Guarded but professional |
| Coast Guard | ~5 | Patrol and safety response |
| Soviet trawler | ~10 | Treaty-line awareness and hostile encounters |

**Count reconciliation required:** these rows sum to about 461, while the source text also calls the fleet “~450.” Treat the per-archetype table as the source of truth, compute the total from config, and display the computed total in diagnostics. Do not silently hard-code both numbers.

### 2.2 Configuration-first implementation

Keep fleet data out of update/render methods. Use a validated configuration file or module constants for:

- pool count and archetype;
- naming patterns and stable vessel ID;
- home port and route/schedule generator;
- radio range and radio fit;
- activity weights and season eligibility;
- personality distribution and initial trust;
- speed limits, watch schedules, and behavior flags.

Stable IDs must not depend on generation order or Python's randomized `hash()`. A vessel keeps the same identity across world reloads and software versions, unless a save migration explicitly replaces it.

### 2.3 Season and geography

Use the source plan's proposed historical context as the initial schedule:

- April: low pre-season traffic; departures and coastal work begin.
- Around May 20–August 10: high density inside the high-seas operating box, clustered around motherships.
- Outside the box: sparse independents and transit traffic.
- Night and active hauling: reduce long, non-essential conversations.

The seasonal model must not make April empty or inert: the harbour, local longliners, weather, Coast Guard, and early departures still provide gameplay.

---

## 3. Target Architecture

Keep modules narrow and testable. Use `game.py` as the integration/orchestration layer during migration, not as the permanent home for all new world logic.

### 3.1 Proposed modules

| Module | Responsibility | Must not own |
|---|---|---|
| `world/traffic.py` | Vessel definitions, schedules, activity, promotion/demotion hooks | Pygame drawing, UI, transcript formatting |
| `world/chunk_manager.py` | Spatial cells, nearby candidate queries, LOD transitions | Fleet policy, dialogue text, weather physics |
| `world/weather_grid.py` | Weather cell state, low-frequency evolution, forecast snapshots | Ship identity, radio queues, chart rendering |
| `world/persistence.py` | Versioned snapshots/deltas and migration helpers | Runtime decisions about who talks |
| `systems/ship_radio.py` | Contact gating, intents, truth policies, trust effects, dialogue context | Per-frame world scheduling and drawing |
| Existing broadcast director | Queue priorities, interruptions, transcript playback | Choosing which distant ship is in radio range |
| Existing navigation chart UI | Drawing contact positions and labels | Owning AI vessel movement |
| `core/game.py` | Adapt existing clock/input/render/save paths to the new modules | Duplicating the world model inside the game loop |

Create `fishing_sim/world/` only as it becomes useful; do not move every existing file simply to match the proposed tree. Prefer adapters and small extraction PR-like milestones.

### 3.2 Runtime service flow

```text
Game clock / simulation tick
        |
        +--> World schedule service (coarse: event/time based)
        |
        +--> Spatial index (candidate lists for radio, chart, visibility)
        |
        +--> Active entities (nearest, capped; local AI and avoidance)
        |
        +--> Weather grid (low-frequency fixed tick)
        |
        +--> Ship radio dispatcher
        |       +--> range + watch + activity eligibility
        |       +--> intent/policy selection
        |       +--> existing prioritized broadcast queue
        |       +--> Notebook / Radio Log persistence
        |
        +--> Save snapshot / delta checkpoint
```

This is a logical flow, not a requirement to call every service every rendered frame. Each service owns its next scheduled update and can report whether it has work.

### 3.3 Shared contact identity

Tow/rescue and ordinary AI traffic must use the same identity and chart marker model:

- A Coast Guard vessel accepting a tow becomes a persistent `AIShip` (or a compatible adapter with a stable `vessel_id`).
- The tow escort holds a reference/ID to that vessel; it does not spawn another independently drawn Coast Guard marker.
- The existing `PLACE HOLDER SHIP` hull renderer can remain the current visual placeholder for the escort, but chart, radio, save/load, and later AI traffic should resolve to one identity.
- Do not refactor this in one giant change: first establish stable IDs and adapter tests, then migrate the tow escort reference.

---

## 4. World Extent and Spatial Representation

### 4.1 Phased map extent

| Phase | Extent | Goal |
|---|---|---|
| A — regional | 138°E–148°E, 40°N–46°N | Fully playable Hakodate area and initial traffic |
| B — high seas | 140°E–175°W, 41°N–62°N | Transit corridor, mothership fleet, Soviet encounters |
| C — modular expansion | Additional 5° longitude tiles | Future extensibility, not required to ship 13.2 |

Design coordinates and IDs for Phase B immediately, but **content and detailed activity should begin in Phase A**. Do not populate all of Phase B with high-detail entities just because the coordinate plane permits it.

### 4.2 Projection

The source proposes a local equirectangular plane centered at (45°N, 160°E), with x east and y north in NM. Implement lat/lon conversions in one module and test the corner cases, date-line crossing, and representative points. The approximation is for gameplay and coarse regional plotting; do not use it as a claim of navigational-grade geodesy.

### 4.3 Chunk size versus LOD radius

The proposed chunk size is **20 × 20 NM**, aligned to the weather cell grid. Use a sparse dictionary keyed by integer cell coordinates. A chunk is an index and persistence bucket, not a separately running world.

Recommended starting ranges from the source plan:

| Use | Initial scale | Optimization rule |
|---|---:|---|
| Active AI entities | ~12 NM | Hard cap active detailed ships; nearest relevant ships win |
| Warm ring | ~25–40 NM | Statistical summaries and promotion candidates only |
| Radio candidates | Each ship's configured radio range (typically 27 or 49 NM) | Must not be clipped to rendering radius |
| Weather | 20 NM cells | Independent global field; do not activate/deactivate with ships |
| Full map population | Phase-dependent | Schedules are cheap; high-detail entities are not |

**Important:** radio range can exceed active-render range. A vessel can be a valid radio listener without becoming a fully rendered/collision-active entity. Use spatial candidates to decide who can hear; do not promote all ships within radio range to active detail.

### 4.4 Shared spatial index

Implement a single grid-index abstraction for vessel candidates and reusable local lookups. Start with a dictionary from cell key to vessel IDs. Rebuild/update only when a vessel crosses a cell or at its scheduled position update—not every pixel/frame.

Queries should return stable IDs in deterministic order. Use the index for:

- visual/radar contact candidates;
- radio range checks;
- nearby rescue and Coast Guard queries;
- collision/avoidance candidates for active entities;
- local weather-cell lookup.

Do not add a quadtree/R-tree dependency unless grid profiling shows a real limitation. A uniform grid fits the proposed 20-NM cell model and is simple to debug.

---

## 5. Determinism and Randomness

### 5.1 Stable chunk seeds

The supplied plan's CRC32 seed is a good lightweight starting point:

```python
import struct
import zlib

def chunk_seed(world_seed: int, cx: int, cy: int) -> int:
    return zlib.crc32(struct.pack("<qqq", world_seed, cx, cy))
```

Never use Python `hash()` as a persisted seed. It is not a save-format contract.

### 5.2 Independent random streams

One shared stream is fragile: adding a radio roll would otherwise change unrelated weather, ship names, or hotspot spawns. Derive stable per-domain/per-entity seeds from a documented root seed, for example:

- `world_seed + "traffic" + vessel_id`;
- `world_seed + "weather" + cell_id`;
- `world_seed + "radio" + vessel_id + contact_count`;
- `world_seed + "hotspot" + chunk_id + spawn_index`.

Use a stable byte encoding and the documented CRC32 or a fixed digest; do not rely on default object repr or hash ordering. Record the seed algorithm/version in save metadata. For a given seed and save version, ship IDs, schedules, and deterministic outcomes should match across runs.

### 5.3 Fixed random draw order

For procedural chunk content, document the order of draws or give each independent entity/system its own stream. Prefer independent streams because they let the implementation add a field or intent without rerolling the entire world.

---

## 6. Three-Tier AI Vessel Model

### 6.1 Coarse schedule tier (always available)

Contains about 460 configured schedule entries—not per-frame objects with full AI. Each record needs only:

- stable ID, name/callsign, archetype and personality;
- home port, radio range, schedule waypoints and activity;
- minimal state needed for the current simulation time;
- persisted relationship flags for contacted vessels.

Position is computed from the time-stamped schedule when queried. The schedule service can fast-forward across multiple elapsed intervals when the player sleeps, time-skips, or loads a save.

### 6.2 Warm tier (nearby statistics)

Warm ships generally have no full movement AI or drawing. Retain only what is required for accurate density and promotion. Suitable work includes:

- approximate traffic density, broad activity and local vessel counts;
- weather/activity summary for ambient chatter selection;
- promotion eligibility when the player approaches.

Do not build a parallel shadow entity for every coarse vessel. The schedule entry already supplies enough information.

### 6.3 Active tier (local simulation)

Only nearby relevant vessels become active: initial hard cap **30–50** as in the source plan, starting lower (e.g. 30) until profiled. Active ships receive local navigation/avoidance, detailed position updates, rendering, and time-critical events.

Promotion/demotion rules:

1. Demote active ships outside the active radius into warm/coarse state.
2. Promote coarse schedules entering the warm ring into indexed candidates, not full objects by default.
3. Promote the nearest relevant warm candidates into active entities, subject to the cap.
4. Save any intentional active-state override before demotion; do not silently discard a changed route, distress state, or player relationship.
5. Use hysteresis at boundaries (enter at one radius, leave at a slightly larger radius) to avoid repeated promotion/demotion when a ship hovers at the threshold.
6. Restore the same state on promotion. The transition must not cause visible position, heading, activity, or identity jumps.

### 6.4 Distress and rescue exception

A distress call can be important even if the source ship is not active. Time-critical coarse events should be dispatched by the schedule/event layer and then promote relevant vessels only when needed. The player should not need to render an entire region for a MAYDAY to be processed.

---

## 7. Weather Grid and Forecast

### 7.1 Build the simple path first

The source proposes a global grid of 20-NM cells, advected with prevailing wind, updated every 10–15 in-game minutes, and storing pressure, wind components, precipitation, and sea state. A Phase B map would be about 5,355 cells.

Implementation order:

1. Define weather cell schema and deterministic initialization.
2. Implement regional weather evolution and sampling.
3. Snapshot/restore weather; ensure save/load reproduces the same sampled conditions.
4. Connect local sea state and weather wording to active ships and radio.
5. Integrate the 3-day forecast as a read-only forward projection from a copied snapshot.
6. Expand grid bounds for Phase B when regional profiling and gameplay pass.

### 7.2 Memory and CPU optimization

- Store numeric fields compactly if ordinary objects become material: `array('f')`, fixed lists, or a compact data container are options.
- Start with pure Python. 5,355 × 5 fields is small enough that a simple version should be measured first.
- Do not step every cell on every rendered frame. Use a fixed weather tick and carry elapsed simulation time into that tick.
- Forecasting must not mutate live weather or consume live random streams.
- Cache the weather cell under an entity until it crosses a grid boundary.
- Avoid repeated lat/lon conversion and string phrase generation inside render loops.

### 7.3 Weather invariants

- The weather snapshot has a schema version and stable cell ordering.
- Save/load round-trip preserves sampled wind, sea state, and forecast baseline within documented tolerance.
- Storm changes affect radio range/reception and tow-line risk through explicit multipliers, not hidden duplicated checks.
- Market scarcity and existing weather systems retain their existing source of truth; the new grid should feed the existing weather interface rather than create a competing weather value.

---

## 8. AI Schedule and Behavior Model

### 8.1 Time-based schedules

A schedule is a sorted set of `(sim_time, x_nm, y_nm, activity)` waypoints. Define a canonical interpolation policy for position and heading. Handle schedules with one point, loops, weather delays, distress overrides, and returning-to-port states.

Keep movement schedules independent of rendering. A ship 300 NM away should still be able to transition from transit to fishing without receiving per-frame updates.

### 8.2 Active overrides

An active ship may depart from its schedule because of collision avoidance, distress, player interaction, treaty behavior, or assistance. Represent overrides explicitly with:

- override type/reason;
- start time and expiry/clear condition;
- target/waypoints if applicable;
- persistent fields needed after demotion;
- resume policy back to the coarse schedule.

Never simply discard overrides when a ship leaves active range. If exact movement continuation is too expensive, convert it into a new schedule segment at demotion.

### 8.3 Activity gates

Use activities such as `TRANSIT`, `FISHING`, `HAULING`, `ANCHORED`, `DISTRESSED`, and `RETURNING`. `HAULING` suppresses extended chatter but still permits safety messages and short acknowledgements. Keep the gate in one intent-eligibility policy, not duplicated across each dialogue template.

---

## 9. Ship Radio, Radio Range, and Dialogue

### 9.1 Dispatch pipeline

A radio dispatch cycle should:

1. Query vessel IDs from the shared spatial index within the maximum relevant physical radio radius.
2. Filter each by actual distance, radio fit/range, time-of-day/watch status, activity, antenna condition, and storm propagation.
3. Select eligible intent based on archetype, personality, trust, contacts, activity, weather, and distress state.
4. Build context from an explicit truth policy: exact data for safety, claim/report data for uncertain fishing intelligence.
5. Enqueue the transcript through the existing prioritized broadcast system.
6. Write every heard/transmitted line into the Ship's Notebook / Radio Log with time, speaker, source, priority, and transcript ID.
7. Persist any contact/trust/cooldown change using the same transaction boundary as the event.

Do not create or format radio dialogue inside the render path.

### 9.2 Work cadence

- Routine chatter/intent selection: low-frequency scheduled tick, initially every 10–30 in-game seconds or by per-ship cooldown event.
- Active player hail: process on input, then schedule response timing.
- MAYDAY / immediate safety event: process on the high-priority event path, independent of routine chatter cadence.
- Weather forecast: its own cadence; no weather recomputation just because the radio asks for a phrase.

These are initial engineering targets. Tune using the simulation clock and playtesting; do not tie them to rendered FPS.

### 9.3 Radio range and equipment

Use the source plan's starting values: 1W DSB ~27 NM and SSB ~49 NM. Treat these as configurable starting assumptions, not universal absolute truths. The same radio-range helper must be used by player hails, AI responses, overheard traffic, and assist dispatch, with clearly documented exceptions for Coast Guard/coast-station relays.

Avoid scanning all 460 ships for every hail. The shared spatial index returns candidates; the actual distance/radio/weather checks still decide who hears it.

### 9.4 Intent policy

Use data-driven weighted eligibility, not a giant conditional in `game.py`. Intents from the source plan include:

- `hail_stranger`, `hail_familiar`, `peer_exchange`;
- `grounds_report_honest`, `grounds_misdirect`, `grounds_declined`;
- `weather_warning`, `corp_grumble`, `corp_fleet_coordination`;
- `mothership_warning`, `quota_check`, `mayday`, `assist_ack`;
- `port_gossip`, `refuse_contact`, `treaty_challenge`.

Each intent declares required context keys, eligibility, priority, cooldown, and whether it is player-facing or overheard. Validate templates at startup/tests so missing `{placeholders}` never causes runtime errors.

### 9.5 Queue priority

Preserve and extend the existing broadcast contract:

| Priority class | Examples | Behavior |
|---|---|---|
| Critical | Imminent loss of life, immediate MAYDAY | Can interrupt lower-priority speech |
| High | MAYDAY, distress assistance, Coast Guard safety messages | Can interrupt ambient/routine talk |
| Medium | Player hail and direct response | Queued behind critical/high safety traffic |
| Low | Routine chatter, overheard corporate traffic | Never interrupts an active higher-priority transcript |

A transcript must remain contiguous unless a higher-priority event legally interrupts it; if interrupted, keep enough queue state to resume or record the dropped/aborted transcript consistently.

### 9.6 Performance-safe ambient traffic

- Generate ambient lines only when the queue and radio conditions allow them.
- Keep ambient traffic low-weight, with per-source cooldowns.
- Bound the in-memory transcript queue and log growth; archive older entries rather than dropping safety-critical events.
- Overheard traffic must be tagged and logged but must not accidentally become a conversation addressed to the player.
- Do not generate a message every tick. Choose a small number of plausible candidates, then apply cooldown/weighting.

---

## 10. Truth Policy, Trust, and Relationships

### 10.1 Personality categories

Start with the source categories: `cooperative`, `cagey`, `competitive`, `corporate`, `hostile`, `official`, and `gossip`. Treat personality as data-driven behavior policy, not a distinct class per personality.

### 10.2 Separate truthfulness from willingness to talk

These are different properties:

- **Truthfulness:** whether a claim is accurate.
- **Disclosure:** whether the vessel will share the information at all.
- **Safety reliability:** whether emergency/weather information is handled honestly.
- **Talkativeness:** whether it tends to initiate optional conversation.

Corporate vessels generally decline grounds questions instead of fabricating a false report. Competitive independents may deliberately misdirect when trust is low. Do not collapse both into a single “dishonest” flag.

### 10.3 Trust effects

Use bounded trust in `[-1.0, 1.0]`, sourced initially from the Plan 13.2 values. Store effect deltas and decay rate in one table. Apply the effect once per interaction ID, so save/load/retry cannot award trust twice.

Suggested starting effects from source:

| Action | Trust delta |
|---|---:|
| Polite hail | +0.05 |
| Share report | +0.08 |
| Assist MAYDAY | +0.40 |
| Ignore MAYDAY | -0.50 |
| Hostile hail | -0.10 |
| Treaty violation | -0.30 |
| Poach gear | -0.40 |

Decay: approximately 0.01/day for independents and 0.02/day for corporate contacts. Make trust decay time-based and apply missed intervals mathematically rather than ticking every frame. Validate behavior at clamp edges.

### 10.4 Rival flag and information

`RIVAL` is a relationship flag, not an archetype. An independent contact may become a rival below a configurable trust threshold. Rival state can enable refusal or misdirection but must not change the vessel's archetype or break its stable ID.

### 10.5 No hidden truth leaks

The UI and transcript must not expose truth labels such as “lie detected.” The player learns through repeated contacts, cross-checking, physical investigation, and outcomes. Tests may inspect true/reported values internally; normal gameplay should not.

---

## 11. Persistence, Save Migration, and Event Safety

Persistence is a foundation phase, not the last step.

### 11.1 Snapshot what is expensive or must remain exact

Persist:

- world seed and seed algorithm version;
- simulation time and current map/phase;
- weather snapshot and tick timestamp;
- player-modified chunk deltas (gear, depleted hotspots, removed entities, event flags);
- contacted-vessel records and their trust/contact/cooldown/distress relationship state;
- active overrides that cannot be reconstructed from schedules;
- radio queue/transcript cursor if save is allowed during a conversation;
- Coast Guard/tow escort reference and state, without duplicating the underlying vessel;
- schema version and migration version.

Regenerate from seed:

- untouched chunk filler;
- default vessel schedule rows when they have not been overridden;
- default personality/names derived from stable ID;
- other static data that is already available from code/config.

### 11.2 Delta storage

Record only what differs from deterministic defaults. For a contacted vessel, persist the relationship and override fields, not a duplicate copy of every immutable fleet configuration value.

### 11.3 Transaction boundaries

A meaningful interaction (contact trust, MAYDAY sent/resolved, assistance outcome, catch/gear delta) should update state and its event/log record together. On load, do not replay an event that has already applied a trust delta or spawned an escort.

### 11.4 Migration contract

- Every save has a schema version.
- Migrations are sequential and idempotent.
- Keep a fixture for a v13.1.34 save and test migration into the new schema.
- Unknown future schema versions fail safely with a clear message; do not silently reset the world.
- Back up the save before writing a migrated version.

### 11.5 Radio log growth

Keep current run history meaningful without allowing unbounded in-memory state. Use bounded active queue plus durable append-only/archive records if supported. Always retain critical safety events and records linked to player-contacted vessels. Avoid putting every generated-but-never-heard ambient candidate into the player's log.

---

## 12. Integration with Tow, Rescue, and Existing V13.1 Systems

### 12.1 Keep one Coast Guard identity

The v13.1.34 tow launch already has a visible placeholder hull, a harbour departure, a chart marker, stale report indicator, and radio check-ins. The world system should treat that launch as the same contact identity when it accepts a tow. Add adapters before moving behavior into the new world module.

Acceptance requirements:

- one ship ID resolves across water rendering, chart, radio, crew roster, and save/load;
- no duplicate chart marker or duplicate hull appears when AI traffic is promoted;
- the tow route uses shared coordinate/time conversion helpers;
- tow progression updates both physical position and belief/report fields according to their contracts;
- emergencies may interrupt routine tow conversation;
- a tow/rescue vessel can be selected as active even when normal active traffic is at cap, if the player is in a time-critical encounter.

### 12.2 Assistance and other ships' MAYDAY

A coarse ship may become distressed, but the player should only receive a dispatch when radio conditions and priorities permit. Once the event is actionable, promote the ship or rescue vessel as needed. Do not make the whole fleet active just to process an emergency.

Assist outcome should update relationship state once. Ignoring a MAYDAY, assisting it, or passing the location to the Coast Guard must have persistent effects.

### 12.3 Abandonment integration

If a ship is foundering, MAYDAY traffic takes priority and can involve the same Coast Guard identity used for tow. The liferaft/abandonment simulation remains a separate system; radio dispatcher interfaces should allow it without pre-implementing the full raft model here.

---

## 13. Performance Plan and Budgets

### 13.1 Budgets from the source plan

| Metric | Initial target |
|---|---:|
| Frame time | ≤16 ms for 60 FPS target on reference hardware |
| Active AI ships | Hard cap 30–50; start at 30 until profiled |
| Warm ring | Hundreds represented statistically; throttled |
| Coarse fleet | About 460 schedules, low-frequency/event-driven |
| Chunk activation | ≤16 ms or amortized across frames |
| Weather tick | ≤2 ms per 10–15 in-game minutes |
| Save size | <2 MB after a long campaign, excluding/qualifying radio-log archive growth |

These are target budgets, not guaranteed values. Record hardware, Python/Pygame version, seed, map extent, vessel counts, and measured percentile timings in the test report.

### 13.2 Measure before optimizing

Add a reproducible benchmark harness that reports:

- total frame time and update/render split (median, p95, p99);
- coarse schedule update time;
- spatial query latency at varying candidate counts;
- active ship update/render time;
- weather tick and forecast costs;
- radio dispatch cost and queue depth;
- save/load time and save-size growth;
- promotion/demotion count and boundary churn.

Run fixed-seed scenarios: empty regional water, dense fleet cluster, storm, active radio traffic, time skip, save/load, and Coast Guard tow.

### 13.3 Highest-return optimizations (in order)

1. **Avoid doing work:** no per-frame coarse fleet scan, weather update, radio intent selection, or repeated string formatting.
2. **Candidate filtering:** spatial index before distance/radio/visibility checks.
3. **Temporal throttling:** schedules/events for coarse/warm systems; fixed low-frequency weather tick.
4. **Bound active details:** nearest-first active cap with safety-event override and hysteresis.
5. **Stable object reuse:** avoid recreating vessel/contact objects on every promotion; reuse view/model records where sensible.
6. **Cache derived values:** current weather cell, display labels, context phrases, and chart transforms until inputs change.
7. **Compact data only when needed:** slots/dataclasses, arrays, or vectorization after profiling shows object overhead is material.
8. **Amortize expensive transitions:** chunk preparation, persistence compression, and warm-ring rebuilding can be spread across ticks if measured cost exceeds budget.
9. **Avoid speculative parallelism:** Python threading/process pools are not the default path; complexity and synchronization are not justified for a bounded fleet until profiling proves otherwise.
10. **Re-profile every milestone:** performance regressions can arise from radio/template/UI paths as readily as from ship AI.

### 13.4 Do not optimize these prematurely

- Do not chunk the entire static/coarse schedule list simply to save memory.
- Do not introduce NumPy for a 5,355-cell grid before timing pure Python.
- Do not cache data whose inputs change every frame unless cache invalidation is reliable.
- Do not make a separate renderer for every vessel archetype; use shared hull/marker renderers plus style/config.
- Do not simulate exact far-away collision, wake, or deck crew motion. Coarse schedules should capture plausible outcomes at low cost.

---

## 14. Implementation Milestones (Recommended Release Order)

Each milestone is separately shippable and should land with tests, changelog, migration notes (if needed), and a short performance report. A phase can be marked complete only when its acceptance criteria pass.

### M0 — Baseline and compatibility audit

**Deliverables**
- Capture current v13.1.34 behavior and relevant tests.
- Inventory position/time/unit conventions, tow escort, radio/broadcast queue, chart markers, save format, and existing errors.
- Write a versioned interface contract for `AIShip`, simulation time, radio event, and stable vessel ID.

**Acceptance**
- Existing targeted suites pass unchanged.
- Unit audit lists all conversions required between legacy world units and NM.
- A fixed-seed baseline report exists.

### M1 — Deterministic world primitives

**Deliverables**
- Add `world/` package with coordinate helpers, stable seed utilities, data schemas, and a minimal `WorldContext`.
- Add fixed-seed tests and time interpolation helpers.
- Keep integration read-only initially; no gameplay tuning yet.

**Acceptance**
- Same seed returns same ship IDs/schedules across separate processes.
- Date-line and boundary conversions have tests.
- No use of Python `hash()` in persistent seeds/IDs.

### M2 — Coarse schedule fleet

**Deliverables**
- Configuration-driven archetype counts, names, home ports, seasonal schedules, activity states.
- Implement deterministic coarse schedule interpolation for Phase A.
- Add explicit total count validation (count the archetype rows; report 461 if the source counts remain unchanged).

**Acceptance**
- Several in-game days can fast-forward without per-frame entity updates.
- Schedule interpolation is continuous at waypoints/loops.
- April, active-season, and night schedule fixtures behave as configured.

### M3 — Shared spatial index and LOD promotion

**Deliverables**
- 20-NM sparse cell index and deterministic nearby queries.
- Active/warm/coarse transitions; start with active cap 30.
- Hysteresis, deterministic candidate order, explicit active override persistence.

**Acceptance**
- Radio candidates include ships outside active-render radius but within radio range.
- A ship crossing boundaries never duplicates or disappears from the world.
- Promotion/demotion preserves ID, position, heading, activity, distress, and contact state.
- Dense active radius respects cap unless a documented safety override applies.

### M4 — Phase A regional traffic and chart contacts

**Deliverables**
- Draw nearby AI ships and chart markers through the existing shared marker style system.
- Marker labels, stale reports, and believed positions.
- First small, testable traffic pool (not the full 460 immediately).

**Acceptance**
- No duplicate marker for one vessel ID.
- Player UI shows reported state only, not hidden physical truth.
- Visual rendering is camera-relative and stable at map edges.

### M5 — Radio dispatcher foundation

**Deliverables**
- Contact-range helper and radio candidate query.
- Intent eligibility/priority schema and template validation.
- Existing broadcast director adapter, transcript IDs, Notebook logging.
- Basic `hail_stranger`, familiar contact, weather warning, and Coast Guard safety exchange.

**Acceptance**
- Contact beyond configured radio range is rejected unless an explicit relay path applies.
- Hauling suppresses extended chat but not emergency traffic.
- Every delivered line has time/speaker/source and remains associated with its transcript.
- MAYDAY interrupts ambient/routine traffic without corrupting transcript state.

### M6 — Social policy and information uncertainty

**Deliverables**
- Personality categories, independent/corporate policy, truth/disclosure/safety reliability split.
- Trust updates, decay, familiar-contact gating, rival relationship flag.
- Honest grounds reports, rival misdirection, corporate decline, gossip propagation.

**Acceptance**
- Corporate contacts do not choose the rival-only misdirection intent.
- Independent competitive contacts can misdirect at low trust and approach truth as trust rises.
- Safety data policy remains reliable and distinct from fishing-intelligence policy.
- Retry/load cannot apply trust effect twice.

### M7 — Weather grid, persistence, and forecast

**Deliverables**
- Regional 20-NM weather grid with fixed tick.
- Compact snapshot and forecast from a copied state.
- Tie sea state into radio conditions, visibility phrases, and existing towline risk.

**Acceptance**
- Snapshot roundtrip matches defined values/tolerance.
- Forecast does not mutate current weather or live RNG state.
- Tick budget meets target or has measured, documented mitigation.

### M8 — Tow/rescue identity unification

**Status (v13.2.04): first shared-identity adapter slice delivered; global career-save wiring deferred to M10.**

**Deliverables**
- Adapt the v13.1.34 Coast Guard launch and `TowEscort` into a stable world-contact ID.
- One world entity powers the drawn placeholder hull, chart marker, radio identity, crew roster, and save/load.
- Add assist outcomes and high-priority rescue communications; avoid parallel tug/AI duplicates.

**Acceptance**
- Launch leaves harbour, reaches the player, and returns with them without teleporting.
- The same stable ID appears on chart and in radio transcripts.
- Save/load mid-en-route and mid-tow keeps the same captain and reported position.
- A priority distress can interrupt routine tow conversation.

### M9 — Distress, MAYDAY, and player assistance

**Status (v13.2.05): first implementation slice delivered.** `DistressDispatcher` runs on 30-second simulation-time slots, handles authored or deterministic low-frequency incidents from coarse/non-rendered radio candidates, emits each incident once, marks a reported position rather than exposing true position, and promotes at most three rescue contacts. The radio UI interrupts routine traffic and offers ASSIST/IGNORE, with idempotent trust effects and logged responses. Global career save integration and physical rescue dispatch are still outstanding; the test snapshots validate the shared traffic layer, not the full legacy career save.

**Deliverables**
- Coarse ship distress events, one-shot MAYDAY state, dispatcher and assist acknowledgements.
- Player response/ignore actions and persistent relationship outcomes.
- Promotion exception for rescue contacts without activating all ships.

**Acceptance**
- Distress one-shot flags survive the traffic-contact snapshot/restore path and are not re-emitted when that contact snapshot is restored; full career-save/load wiring is an M10 requirement.
- Assisting/ignoring affects trust exactly once.
- Emergency messages work when the source vessel is a coarse/non-rendered traffic contact within radio range; no all-fleet rendering is required.

### M10 — Versioned persistence and migration hardening

**Deliverables**
- Schema migration, weather snapshot, per-chunk delta format, contacted-vessel persistence, queued transcript state.
- v13.1.34 fixture and corrupted/unknown-version fixtures.

**Acceptance**
- Save/load retains contact identity, trust, activity override, MAYDAY state, radio queue, tow escort and weather snapshot.
- Migrations are repeatable/idempotent and fail safely for newer unknown schemas.
- Long-campaign save remains within target or has a measured exception for archived logs.

### M11 — Full Phase A content and balance

**Deliverables**
- Expand regional traffic pool, names/personas, ambient overheard corporate radio, port gossip, treaty-edge events where map permits.
- Tune density/time-of-day/weather/radio ranges.
- Add player-facing explanatory notebook hints without revealing hidden truth.

**Acceptance**
- Multiple-day playtest features familiar contacts and believable quiet periods.
- No chatter spam, duplicated transcript, or repetitive identical conversation loops.
- Player can infer but not instantly know which grounds reports are trustworthy.

### M12 — Phase B high-seas expansion

**Deliverables**
- Expand schedule and map limits to the proposed high-seas box and transit corridor.
- Add mothership clusters and seasonal fleet movement, with sparse out-of-season traffic.
- Profile before enabling all content in one scene.

**Acceptance**
- Schedule count scales without per-frame cost growing linearly with every rendered frame.
- Active cap and radio candidate performance remain within measured budgets.
- High-seas save/load is stable; positions and IDs survive date-line handling.

### M13 — Profiling, visual playtest, and release hardening

**Deliverables**
- Fixed-seed profiling scenarios, visual marker/readability review, radio UX review, and save migration tests.
- Regression summary and list of known issues.

**Acceptance**
- p95 frame/update time and weather tick meet targets on declared reference hardware or a mitigation is accepted.
- No Pygame visual testing is reported as passed unless actually run.
- All release artifacts and docs agree on the version/status of each milestone.

---

## 15. Test Matrix

### 15.1 Determinism and geography

- Stable chunk seed across separate processes.
- Stable vessel IDs, names, personalities, and schedules from the same world seed.
- Regional and high-seas boundary conversion tests, including the date line.
- Schedule interpolation continuity, speed bounds, and loop behavior.
- Deterministic order returned by spatial queries.

### 15.2 LOD and performance

- Promotion/demotion preserves state and creates no duplicate active entity.
- Active cap is enforced; safety override is bounded and logged.
- Ships beyond visual radius but inside radio radius can hear/respond.
- No per-frame coarse schedule traversal in profiling instrumentation.
- Simulate 460 coarse ships, 30 active ships, weather tick, chatter, and distress; measure p50/p95/p99.
- Chunk-boundary crossing does not trigger repeated promotion churn.

### 15.3 Radio and social systems

- Radio range limits and SSB/DSB differences.
- Watch and activity gating; hauling allows only short acknowledgements except safety traffic.
- Template placeholder validation and required-context validation.
- Priority interruption, transcript continuation/abort semantics, Notebook logging.
- Overheard traffic does not become player-facing conversation.
- Corporate decline, competitive misdirection, trust convergence, trust decay, rival thresholds.
- Distress one-shot state and trust effect idempotency.

### 15.4 Persistence

- Weather snapshot roundtrip.
- Contact survives leaving and re-entering active range.
- Radio queue/transcript cursor roundtrip.
- Distress/MAYDAY does not repeat after load.
- Save migration from v13.1.34.
- Corrupt/incomplete snapshot fails safely without silently deleting a valid prior save.

### 15.5 Integration and visual checks

- Coast Guard tow has one identity across hull, chart, radio, and save.
- Tow launch leaves harbour and intercepts the player without teleporting.
- High-priority distress interrupts a tow check-in.
- Chart marker uses last reported position and staleness indicator.
- Camera-relative rendering avoids map-edge jitter.
- Visual playtest: sparse weather, storm, dense traffic, night radio traffic, tow approach, and chart view.

---

## 16. Release Gates and Definition of Done

A milestone is **not done** merely because code compiles. It must have:

- implemented code and version/status documentation;
- focused regression tests;
- existing regression tests still passing or explained failures;
- save migration tests if schema changed;
- a deterministic scenario or fixture where randomness is involved;
- benchmark numbers if it affects performance-critical loops;
- clear separation between headless-tested and visually playtested behavior;
- no duplicate source of truth for position, weather, ship identity, trust, or radio state.

For optimization claims, include actual measurements. “Uses chunking” or “uses arrays” is not proof of faster performance. The performance report should compare before/after numbers under identical seeded workloads.

---

## 17. Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| Rewriting too much of `game.py` at once | Regression risk across existing ship systems | Keep the game loop as adapter; extract one subsystem at a time |
| Truth/belief fields mixed | Chart leaks true positions or physics follows uncertain belief | Explicit naming, API contracts, tests for each caller |
| Chunk promotion creates a second ship | Duplicate visuals, dialogue, rescue response | One stable ID and one registry; lifecycle invariant tests |
| Simulation uses frame time | Results differ by FPS and time skip | Canonical simulation clock plus scheduled ticks |
| Shared random stream | Small code edit changes the entire world | Independent deterministic streams per entity/domain |
| Radio spam | Dialogue floods logs and interrupts play | Cooldowns, priorities, bounded ambient generation, per-ship next-event time |
| Persistence bloat | Long campaigns load slowly | Deltas and compact snapshots; bounded active queue and archived logs |
| Weather optimization too early | Dependency/complexity without gain | Baseline pure Python and measure before NumPy/vectorization |
| Unrealistically dense contacts | Radio and map become noisy | Seasonal and geographic density profiles, active cap, playtest tuning |
| False claims of testing | Visual/real-time bugs escape | Report compile, headless, performance, and graphical tests separately |
| Conflicting fleet totals | Population generation and docs disagree | Calculate totals from archetype configuration and validate once |
| Tow and world AI diverge | Coast Guard appears twice or forgets captain state | M8 identity unification with save/load and rendering tests |

---

## 18. Suggested Initial Defaults (Tune by Playtest)

| Setting | Initial value | Notes |
|---|---:|---|
| Chunk size | 20 × 20 NM | Aligns with weather cells |
| Active render/AI radius | ~12 NM | Keep separate from radio range |
| Warm ring | ~25–40 NM | Statistical presence, not full AI |
| Active ship cap | 30 initially; up to 50 after profiling | Safety event may reserve a slot |
| Coarse fleet | Counts from archetype config | Compute total rather than hard-code “450” |
| DSB radio range | ~27 NM | Source-plan starting assumption |
| SSB radio range | ~49 NM | Source-plan starting assumption |
| Weather resolution | 20 NM | Regional first, then Phase B |
| Weather tick | 10–15 in-game minutes | Fixed simulation cadence |
| Routine radio candidate tick | 10–30 in-game seconds or scheduled cooldown | Never per rendered frame |
| Chunk promotion | On cell crossing / scheduled boundary | With hysteresis |
| Trust range | [-1.0, 1.0] | Bounded and persisted |
| Independent trust decay | ~0.01/day | Source starting value |
| Corporate trust decay | ~0.02/day | Source starting value |
| Radio intent cooldowns | 15–60 in-game minutes by template | Source templates vary; tune against repetition |
| Target active ships | 30–50 | Hard cap, profile first |
| Frame budget | 16 ms p95 target | Record hardware and test case |
| Weather tick budget | 2 ms | Measure before vectorizing |

---

## 19. First Three Deliverables to Implement

To get useful progress without building the whole high-seas simulation up front, begin with these three concrete deliverables:

### Deliverable A — deterministic traffic prototype

- Add `world/traffic.py` with `Activity`, `Archetype`, `AIShip`, schedule interpolation, and stable IDs.
- Generate a small regional pool (e.g. 20–30 vessels) from explicit archetype config.
- Add a headless test that advances through several in-game days and verifies reproducible position/activity.
- Keep the fleet invisible at first; use debug inspection only.

### Deliverable B — shared spatial index and chart markers

- Add 20-NM sparse-grid candidate query.
- Display a small subset of nearby vessels through the existing chart marker path.
- Draw reported positions and age labels; do not leak exact live positions to the UI.
- Test that radio-range candidates can extend beyond the active-render radius.

### Deliverable C — one end-to-end radio exchange

- Implement `hail_stranger` and a weather warning with eligibility and cooldown.
- Dispatch through the existing prioritized broadcast system.
- Ensure transcript logging, save/load, and priority interruption work.
- Include one Coast Guard contact path that reuses the v13.1.34 tow identity rather than duplicating the hull.

Only after these three are stable should the implementation add trust/deception breadth, the weather grid, and the full Phase B fleet.

---

## 20. Final Recommendation

The most optimized roadmap is **not** “build the biggest map first” or “chunk everything.” It is to make the expensive parts run only when they matter, keep the bounded fleet as deterministic schedules, reuse one spatial index and vessel identity across systems, and implement save/load alongside the first visible feature.

Ship a narrow vertical slice first: several nearby independent/corporate contacts, truthful safety traffic, one meaningful MAYDAY, a Coast Guard identity shared with the existing tow launch, and persistent radio relationships. Then expand fleet density, weather coverage, and high-seas map content only after the measured frame and simulation budgets hold.

The resulting world should feel large because its schedules and relationships persist—not because hundreds of ships are running full AI every frame.

---

## Appendix A — Source Alignment and Scope Notes

This roadmap preserves the supplied Plan 13.2.xx's major decisions: the independent longline player role, corporate/independent asymmetry, Phase A/B/C map staging, equirectangular simulation plane, 20-NM cell concept, three-tier LOD, deterministic seeds, weather snapshots, contacted-ship persistence, radio ranges, dialogue intents, trust/relationships, fleet hierarchy, and staged implementation/testing.

Additional engineering recommendations in this expanded roadmap are explicitly optimization-oriented: independent random streams, a shared spatial index, active-radius hysteresis, no required NumPy dependency until measured, fixed-cadence event services, save migration fixtures, idempotent trust events, one Coast Guard identity across systems, and benchmark gates. Treat these as recommended implementation details, and adjust them only with test or profiling evidence.

Historical fleet numbers and ranges remain the supplied plan's starting assumptions rather than independently re-verified historical findings. Before release, verify the historical data against the project’s source notes and reconcile the approximately 450 total with the listed category counts.

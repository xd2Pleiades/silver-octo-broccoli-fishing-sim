# v13.2.04 Implementation Status — M8 Shared Tow/Rescue Identity

**Release:** v13.2.04
**Roadmap milestone:** M8 — Tow/rescue identity unification (first integration slice)
**Base:** v13.2.03

## Implemented

1. **Stable launch identity.** `TowEscort` carries `vessel_id`, generated as `coast_guard_launch:<callsign-in-lowercase-with-underscores>`. The ID is stored in snapshots and reused for the common contact.
2. **Shared traffic contact.** `Game._sync_tow_escort_world_entity()` registers or synchronizes the active escort as an `AIShip` runtime adapter in `TrafficWorld`. The same entity is visible through spatial queries, known contacts, radio candidate queries, and chart markers.
3. **Runtime movement ownership.** Runtime escort positions are not overwritten by the normal coarse schedule sampler. The launch remains active as a rescue exception even if the generic active cap is otherwise full. Contact unregistration occurs when the escort no longer exists.
4. **No duplicate hull.** The existing specialized `PLACE HOLDER SHIP` hull renderer continues to draw the physical Coast Guard launch. Generic sea traffic skips the same ID, preventing a second overlapping hull. The chart marker itself comes from the common traffic contact.
5. **Radio continuity.** Selecting the common contact ID in the radio UI routes conversation topics to the existing captain and crew on `TowEscort`. Broadcast metadata records the same stable ID. Generic visual observation does not overwrite the captain's radio-reported plot.
6. **Emergency interruption.** Critical-priority traffic preempts medium-priority tow conversation. If the fleet-radio modal is open, critical distress closes it and discards the unshown remainder of the routine exchange rather than allowing ordinary conversation to continue as if uninterrupted.
7. **Snapshot primitives.** `TowEscort.snapshot()/from_snapshot()` and JSON dump/load helpers preserve schema version, vessel identity, captain/callsign, crew, positions and reported position, course, elapsed/check-in clocks, fuel/patience, escort state, fees, and towline warning flags. Unknown schemas, invalid states, malformed positions, and identity mismatches are rejected. Persistence wrapper helpers support optional `None`.

## Intentionally deferred

- **M10 global save migration:** snapshots are standalone APIs; the old campaign save/load path does not call them yet. A save taken mid-tow will not gain new escort persistence until this is wired into the complete game save.
- **M9 full distress response:** this release adds interruption mechanics but not the whole ship distress event dispatcher, player assist/ignore actions, once-only trust effects, or complete rescue outcome handling.
- **Full visual integration test:** game source and contact contracts are tested, but Pygame is absent so no live window/hull/chart playtest was possible.
- **M7 optimization:** weather-grid tick remains over the 2 ms budget; it is measured and documented in v13.2.03 performance results.

## Files changed

- `fishing_sim/systems/tow_escort.py` — stable ID and versioned snapshot schema.
- `fishing_sim/world/traffic.py` — runtime entity registration/sync/removal and active rescue override.
- `fishing_sim/world/persistence.py` — tow escort snapshot wrappers.
- `fishing_sim/core/game.py` — shared identity adapter, chart/radio routing, single-hull rendering, priority interruption and version caption.
- `fishing_sim/tests/test_v13_2_04_tow_identity.py` — stable identity, snapshot, contact index, radio, chart and interruption contracts.
- `docs/` — this status, release notes, test evidence, and updated roadmap/control references.

## Validation boundary

The focused regression run covered tow persistence, tow assistance, Coast Guard escort, crew-cohesion source contracts, prior v13.1.34 merge contracts, v13.2.01 traffic, v13.2.02 radio UI, v13.2.03 weather/docs layout, and v13.2.04 shared identity. It ran **153 tests: 138 passed, 15 skipped**. The skipped tests need Pygame runtime dependencies unavailable in this environment. See `TEST_RESULTS_V13_2_04.txt`.

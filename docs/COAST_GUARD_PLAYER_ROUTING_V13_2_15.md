# Player-Directed Coast Guard Routing — v13.2.15

## Delivered

- Added `PlayerCoastGuardRoutingManager` for tasking one existing scheduled Coast Guard patrol to a selected contact's received MAYDAY fix or received liferaft beacon fix.
- Radio interaction supports `G` / **ROUTE CG TO MAYDAY** and `L` / **ROUTE CG TO RAFT** when the target is selected, wireless is staffed, and the route is not busy.
- Candidate selection only considers existing scheduled Coast Guard vessels, excludes vessels already claimed by another override, and uses a 49-NM target-to-patrol range. Dispatch never spawns another hull or changes stable contact identity.
- Routes use reported coordinates. Liferaft target positions only change on newly received beacon sequence numbers; a fresh report can redirect a patrol still searching the old plot.
- The patrol uses finite-turn motion. During close-in distress approach it is temporarily limited to 2 knots to avoid the high turning radius carrying the hull past the casualty. Assistance is timed and physical; liferaft recovery is still gated by the survivor ledger's 2-NM pickup rule.
- Completion sends the responder back toward its scheduled track and releases temporary rescue overrides. State and counters are included in the career snapshot; the loader validates references to the target and responder contacts. Player rescue, AI dispatch, and Coast Guard route overlap are guarded.

## Automated coverage

`fishing_sim/tests/test_v13_2_15_coast_guard_routing.py` covers selection/reuse of an existing patrol, absence of duplicate hulls, exclusive use of reported position, finite-speed/non-teleport motion, close-in physical assistance, raft pickup radius, new beacon replot, no eligible patrol, and route snapshot validation. It also checks radio action, state-save integration, and single-response guards in `game.py`.

## Remaining validation

- Pygame UI appearance and real-time input flow still require a Windows/Pygame playtest.
- Save/load has source/snapshot validation and unit coverage, but a full live `Game` career round trip remains unverified in this headless environment.
- Single-responder dispatch is implemented; bounded multi-responder tasking remains future work.

## Verification results

- Focused regression runner: **326/326 tests passed** across six shards; zero skipped, failed, timed out, or unrun shards.
- Targeted Coast Guard routing module: **7/7 passed**.
- Dependency-free release gate: **PASS** — 119 Markdown files, 32 local documentation links, and Python compilation checked.
- Release archive CRC/integrity check passed. The archive was extracted and the release gate plus all 7 routing tests passed against that extracted copy.
- Pygame GUI rendering and a live `Game` career save/load round trip remain unverified in this environment.

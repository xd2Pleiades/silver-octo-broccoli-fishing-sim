# v13.2.13 Implementation Status

## Delivered — M9 first physical-assistance slice

- `ASSIST` on a received AI MAYDAY validates that a usable reported position exists and that no other player-vessel rescue mission is active.
- The player vessel's normal `World.set_destination` / autopilot path is set to the converted reported plot. Dispatch does not alter `ship_pos` or `believed_pos` directly.
- The target's distress position is frozen by the traffic schedule layer so it does not sail away underneath the rescue route.
- `PlayerRescueMissionManager` manages the active mission with a stable mission ID and explicit `en_route`, `on_scene`, `completed`, `cancelled`, and `failed` state values.
- The controller validates physical proximity to the target before entering `on_scene`, then requires the configured work interval before completion.
- Completion stores a kind-specific outcome, keeps the target at its scene as an anchored / assisted contact, releases the rescue-only active-LOD promotion, updates the notebook and radio transcript, and restores the player's old course if the player did not override it.
- A missed rendezvous returns to `en_route`; if the player has not taken over navigation, the helm replots the reported position.
- Mid-mission state and the original navigation intent are included in the career save. Snapshot validation checks target identity, distress/assist decision consistency, state fields, timers, distances, and finite coordinates before loading.
- Switching campaign phase is blocked while this mission is active.

## Delivered — M9 player-directed Coast Guard routing

- `PlayerCoastGuardRoutingManager` tasks one existing scheduled Coast Guard contact from the radio UI to a received distress fix or liferaft beacon plot. `G` routes to the selected MAYDAY; `L` routes to the selected contact's latest received raft beacon.
- The patrol retains its stable traffic identity and is physically steered with finite turning. On-scene casualty approach is slowed to avoid overshooting; raft recovery still depends on the survivor registry's actual 2-NM proximity rule. New beacon sequence numbers can update the search plot.
- Route mission/override state is included in career snapshots and validated on load. Dispatch is blocked if player rescue or autonomous AI response is already active, and no extra Coast Guard hull is created.
- Focused headless tests cover patrol selection/range, reported-coordinate use, non-teleport movement, physical assistance, raft pickup, new-beacon redirection, and snapshot round-trip. Pygame presentation and real Game save/load verification remain open.

## Delivered — M9 autonomous AI-vessel response slice

- `AIDistressResponseManager` dispatches one existing scheduled responder at a time; it does not spawn an extra Coast Guard/tow hull.
- An unattended distress incident receives a 42-simulation-second grace period in ordinary conditions, reduced to 12 seconds when the incident-area sea state is heavy. The response scan retries every 4 simulation seconds.
- Eligible Coast Guard patrols can respond within 49 NM; suitable nearby fishing/corporate vessels can turn toward incidents within a weather-adjusted 8–15 NM. If no vessel can respond yet, the dispatcher keeps the incident awaiting dispatch and retries.
- The responder turns at a finite rate and physically advances along its current heading toward the scene. Arrival within working range starts a separate timed assistance state.
- On completion, the distress target remains safely anchored at the scene and the responder turns back toward its live scheduled position before its schedule override is released.
- A storm sample is taken at the incident location for dispatch urgency/range, rather than relying only on weather at the player vessel.
- The manager state and responder/target position/activity overrides are saved and validated. Loading reapplies physical contacts immediately; a target already committed to player assistance cannot also be assigned to the AI manager. Campaign phase switching is blocked while an AI response is active.
- Eight new headless tests cover dispatch delay, storm acceleration, no duplicate hull, continuous steering, timed on-scene completion, return-to-patrol, save/restore, invalid snapshot rejection, and player/AI conflict handling.

## Important boundaries

- AI fleet response is a first autonomous slice, not a full rescue fleet: only one AI incident is handled at a time, and responders do not yet transfer casualties or recover liferafts.
- The target is simulated as a stable distress scene. The current survivor-registry slice now supports timed casualty transfer and liferaft drift/survival/pickup; dedicated portable-pump and tow-line rescue work remains outside this slice.
- Assistance uses a tunable short work interval and outcome text. It does not yet simulate each repair/pump/injury task as a bespoke deck animation.
- Course override is respected. If the player deliberately takes the helm or changes destination, the mission stays active but does not silently seize navigation back. The player can return to the report and complete it.
- The old pre-v13.2.07 save fixture still cannot be validated without a real legacy career artifact.

## Validation status

- Latest bounded focused regression-shard run: **302 tests passed, 0 skipped, 0 failures**, six of six shards completed in 20.61 seconds. The run includes the new autonomous AI-rescue module.
- Additional ship geometry/pathfinding, rescue and release-gate set: **56 tests passed, 1 skipped, 0 failures**. The skip requires Pygame/live navigation components.
- The original v13.2.13 baseline is retained in `TEST_LOG_V13_2_13.txt`; the current run is added there as a separate merge checkpoint rather than rewriting the older result.
- Python compilation and the dependency-free release gate passed. The gate audits Markdown placement/local links and validates the ZIP archive when supplied.
- Pygame is unavailable in this environment, so graphical startup, UI marker visibility, on-screen response messaging, and live `Game` career save/load have not been run. A Pygame-free headless ship/navigation smoke test passed; it is not a substitute for the real graphical launch.

## Next

1. Run the visual checklist in a Pygame-enabled build.
2. Verify career save/load while en route and while on scene using a real Game object.
3. Add bounded multi-responder dispatch after player-directed Coast Guard routing has been validated in-game; preserve the shared rescue identity.
4. Run Pygame-enabled chart/radio visual QA and a real career save/load round-trip for both the player and AI response managers.


## Latest merge checkpoint — v13.2.15 input archive (2026-10-22)

The survivor-rescue follow-on from the raft-beacon build is now selectively integrated into the supplied v13.2.15 archive. The later Chapter A conversation and Chapter B sailor-motion systems remain present; their modules and game-loop hooks were not replaced by the older game source.

- `RescueSurvivorRegistry` is shared by player and autonomous AI rescue completions. Injury MAYDAY incidents create one casualty with a 360-s survival clock; taking-water incidents create one two-person liferaft with a 270-s survival clock.
- Liferafts drift in weather, and heavy seas shorten survival. Pickup requires the responder to be within 2 NM; ship assistance from farther away leaves the raft adrift.
- A staffed wireless receives beacons within 55 NM, attempts a refresh every 90 simulation seconds, and stores a deterministic 0.25–0.95 NM position error. Phase A and Phase B charts draw only the last reported fix with an uncertainty ring; old fixes become stale after 180 seconds without refresh.
- The optional, validated `rescue_survivors` career section stores physical raft/casualty state and beacon report state. Older saves without it still restore an empty registry.
- Phase changes are blocked while survivors remain active so survivor coordinates cannot be interpreted in the wrong map plane.

Final focused verification on the merged source: survivor/beacon module **12/12 passed**; the combined crew conversation, sailor motion, AI/player rescue, ship overhaul, and save-load/release-hardening set passed **163 tests with 15 Pygame-dependent skips**. The focused six-shard regression runner passed **319/319 tests**, and the dependency-free release gate passed. The input archive's root-level `CHAPTER_B_MOTION_STATUS.md` was moved to `docs/` to preserve the project's documentation-placement rule. Pygame rendering and a live Game career save/load cycle still require a Pygame-enabled runtime.

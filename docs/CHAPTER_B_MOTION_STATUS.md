# Chapter B — Sailor motion (Sailor Systems Design Guide v3.2, Part B)

## Delivered

- `fishing_sim/systems/sailor_motion.py` — Pygame-free engine (metres, ship-local, dt-independent):
  B2 seek + arrival, brace caps *desired* speed, accel/decel velocity integrator, turn-rate facing;
  B3 soft separation (gain x overlap x dt, own damped velocity) and `Bottleneck` FIFO reservation with queue spots;
  B4 brace classification (walk >= 6 deg, grab >= 10 deg or flooding > 0.4), 3/s rise, 2/s fall, release clears the target, lean = -0.7 x roll;
  B5 six animation states with a 0.2 s blend; B6 capped stagger impulse and deck clamp;
  B7 `PathFollower` (0.4 m waypoint radius, 1.5 s block, 0.5 s repath throttle) and string-pull `smooth_path`;
  B8 `GatherPlanner` (idle pair, meeting spot, stand points inside 3 m, cooldowns, seeded).
- `Game` / `Sailor` integration (`core/game.py`, ~120 changed lines, 3 removed):
  - `Game.roll_degrees()` and a smoothed `roll_rate_deg_s` (85/15).
  - `Sailor._update_bracing()`: brace value, lean, rail grab for idle hands; `_move` applies the brace speed cut to desired speed and a B6 stagger.
  - Conversation participants stand still and turn toward the current speaker (B5).
  - `Game._update_crew_gather()` walks two idle hands to a meeting spot (rest spot, bow lookout, or a rail spot) so Part A conversations can start (B8). Suppressed while docked, in an emergency, or while a conversation runs.
  - Renderer: feet widen about 20% when braced, hands move slightly out and forward for balance (both gripping in a full hold), and the torso carries only a hint of lean (at most about 1.8 px). A first version used a large body shift and a single raised arm; a render showed it looked detached and wrong, so it was removed.
- Tests: `fishing_sim/tests/test_chapter_b_motion.py` — all nine B11 assertions plus facing, stagger, animation blend, path, gather and a 12-sailor benchmark (about 0.06 ms/tick), and 7 Game-level tests.

## Deviations and judgement calls

- **Roll units.** The game's `roll` is a slope value (max about 0.054 in a heavy sea), not degrees. `Game.roll_degrees()` = `atan(roll)` in degrees x `ROLL_DEG_GAIN` (2.0, my choice). At that gain only heavy seas or a flooding list reach the 6 deg brace-walk threshold; 10 deg grab-rail is mostly reached via flooding > 0.4. Tune `ROLL_DEG_GAIN`.
- **Brace-walk does not clear the target each tick** in the live game (the task layer already re-supplies it through `_go_to`; clearing would break path-progress tracking). The target is cleared on release from a rail grab, as the guide requires. The standalone engine follows the guide literally.
- **Rail grab applies only to idle hands.** Helm, radio, anyone working, ordered or in a deck action keeps their task and just braces (slower, leaning).
- **Existing movement kept.** The game's `_move` (lerp velocity, A*, reciprocal avoidance) was not replaced by the new integrator; Part B behaviours were layered onto it. `Bottleneck`, `PathFollower` and `smooth_path` are tested engine pieces and are **not yet wired into the live game** (the existing A* + avoidance covers ladders/hatches today).
- Ambient idle behaviour already pulls crew together, so gather's effect is hard to isolate in play; the test asserts the planner actually dispatches the pair.
- Gather and brace state are transient: not saved in the career file.

## Verification actually run (local venv, bundled pygame 2.6.1 wheel, SDL dummy driver)

- `test_chapter_b_motion`: 36 tests pass. Chapter A: 54 pass.
- Full sharded regression: 763 tests parsed, 636 reported passed, 2 failures, both reproduced identically on the **original** `game.py` (stale source-string assertions: `test_v13v1_17_phase3_4 ...engine_casing_draw_state...` and `test_v13v1_06_waypoint_plotting ...course_persists...`). The runner's 636 count excludes the failing shards' passing tests.
- Brace sanity: 1.5 s order walk covered 279 px braced (brace 0.5) vs 393 px unbraced.

## Not verified

- Visuals: checked only by rendering the five poses (idle, walk, brace-walk, hold, mirrored roll) to a PNG headlessly and viewing it; not seen in live play on a moving deck. Lean is deliberately nearly imperceptible in this top-down view.
- Real-time feel in a storm, and rail-grab pathing on the actual deck in live play.
- Career save/load with these fields.

## Next

Wire `Bottleneck` into hatch ladders and add a visual check of the brace pose in a heavy sea.

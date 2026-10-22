# Fishing Simulator v13.1.34 — Merged Operations and Coast Guard Escort

## Merge basis

This release combines the uploaded v13.1.32 cohesion/captain-orders update with the v13.1.33 visible Coast Guard tow launch and harbour-to-vessel approach. The merge uses a three-way source merge against the v13.1.31 working baseline; the two game-source branches merged without conflict markers.

## Preserved from the uploaded v13.1.32

- Crew cohesion: idle non-sleeping crew return from below deck to deck standby, social partners must be awake and on the same level, and engine watch is less disrupted by crew crowding.
- Better berth recovery and morale gains while sleeping.
- Delayed man-overboard response from crew below deck and longer delay for sleeping crew.
- Right-click captain orders: **Fish: 3-day trip** and **Return to port**, with reasons for returning early and a trip progress HUD.
- The full 15-test cohesion regression module and the bundled `cache/errors/README.md`.

## Preserved from v13.1.33

- Dedicated Coast Guard `TowEscort` entity with callsign, captain/personality, and separate crew roster.
- Visible placeholder launch drawn using the fishing-ship hull as its reference, dark navy paint, light deck, orange safety stripe, bridge windows and wake. Source comment: `PLACE HOLDER SHIP`.
- Launch begins at the harbour, travels to an intercept point, comes alongside, then turns and tows the player home; it does not simply spawn ahead of the player.
- A physical towline, amber chart marker, report staleness indicator, position check via F4, and captain conversation topics via G.
- Radio check-ins, weather/line warnings, arrival dialogue, and the persistent tow trigger/retry fixes.

## Merge work

- Unified `fishing_sim/core/game.py` using a three-way merge so the captain-trip/crew-cohesion changes and tow escort changes coexist.
- Updated the game version and caption to v13.1.34.
- Combined the roadmaps and controls; retained both historical v13.1.32 changelog variants with the uploaded cohesion notes saved as `CHANGELOG_V13_1_32_COHESION.md`.

## Verification

- `python -m compileall -q fishing_sim`: passed.
- Focused combined regression run: **97 tests run; 82 passed and 15 skipped**. The skipped tests are the uploaded v13.1.32 behavioural crew/trip tests, which require Pygame; Pygame is not installed in this environment and package-network access was unavailable. Dependency-free contracts cover the merged trip/cohesion code paths, and tow/escort/navigation regression tests passed.
- A full discovery run exceeded the 180-second execution limit, so the full suite is **not** claimed as passing.
- ZIP integrity and required-file checks: passed after packaging.
- No live graphical playtest was possible without Pygame.

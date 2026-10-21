# V11 changelog — Deck work, fishing UI, engine continuity, and headcount

## Added
- Raised the line-tension and gaffing HUD bars and constrained their Y position for shorter window sizes.
- Added F5 to toggle the on-screen controls/help strip without changing gameplay input handling.
- Added live/unsecured deck-fish thrash timers and visual response, slime reinforcement using the existing `Patch` class, sailor shove/slip/injury reactions, rough-handling quality damage, and additional deck-exposure quality loss.
- Prioritized loose catch and dressing-table work over optional cleaning/social/rest/standby tasks while preserving critical station, engine, line, and rescue tasks.
- Logged when fish are bled and when dressed fish are stowed, including final grade and quality.
- Added unattended engine exposure tracking, faster unstaffed wear, load/duration-based probabilistic faults, early warnings, and reduced wear/strain when a qualified sailor attends the engine station.
- Replaced the H-key instant report with a one-at-a-time deck muster: captain call, pathfinding destinations, report tracking, exceptions for unavailable/critical sailors, timeout handling, and HUD progress.
- Added source-contract tests for the v11 feature wiring.

## Preserved
- `run_fishing_sim.py` launcher, `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`, shore/hiring UI, wheelhouse escape recovery, radio behavior, and existing fish processing/hold systems.
- Larger auction overhaul deferred; no new auction UI was included in V11.

## Validation
- `python -m py_compile fishing_sim/core/game.py run_fishing_sim.py`: passed.
- `python -m unittest discover -s fishing_sim/tests -q`: 36 tests passed.
- Full Pygame graphical playtest not run: the packaging environment does not have Pygame installed and network package downloads are unavailable.

## Known limitation
- The source note ending “when everyone comes back the radio operator always …” is incomplete. No behavior was guessed or added for that requirement.

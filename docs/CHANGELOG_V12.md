# V12v12 changelog — Dockside shore leave and crew management

## Added / improved

- Consolidated shore-recovery readiness into a small Pygame-independent policy module. A sailor is ready to return at 98% health, 10% fatigue or lower, and 95% morale or higher.
- The Shore roster now distinguishes **RECOVERING**, **READY**, and **KEEP ASHORE** so the wait action's behavior is visible before it finishes.
- `WAIT UNTIL RESTED` uses the same recovery policy shown by the roster, excludes crew explicitly marked **KEEP ASHORE**, and restores the pre-wait time scale on completion, cancellation, or departure.
- Recall now differentiates a real departure from wait completion and repeated input polling, reducing duplicate leave/recall transitions.
- Bringing the stored radio operator aboard individually restores radio watch, unless the player has already assigned a replacement.
- Hiring at the quay now places recruits at separated deck positions. A failed hire-to-shore transition rolls back the recruit and fee instead of leaving a half-created sailor.
- The dock sheet moves controls onto extra rows on narrower windows and fits metric text before action buttons.
- Updated version caption, README, roadmap, and dock wait guide for 12v12.

## Preserved

- `run_fishing_sim.py` remains at the ZIP root.
- `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md` remains at the ZIP root.
- 12v11 deck handling, controls overlay, unattended-engine, and headcount features remain in place.
- Auction redesign remains deferred to 12v15; the unfinished radio-operator request remains unresolved rather than guessed.

## Validation

- `python -m py_compile run_fishing_sim.py fishing_sim/core/game.py fishing_sim/systems/shore_leave.py`: passed.
- `python -m unittest discover -s fishing_sim/tests -q`: **46 tests passed**.
- Pure shore-recovery policy tests run without Pygame.
- A full graphical playtest was not possible in the build environment because Pygame is unavailable. Please verify dock arrival, individual radio-operator recall, hiring, and wait/cancel flows on a machine with the requirements installed.

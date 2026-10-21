# Fishing Simulator v13.1.30

## Tow persistence and stranded-vessel assistance

- Fixed a confirmed retry bug: a failed manual F4 tow request no longer stops retrying merely because fuel remains in the tank.
- Added a persistent tow-request latch which remains active until successful tow arrival or a docked state.
- Added automatic assistance at 5% fuel capacity and after six in-game hours adrift with the engine off and minimal way on. Intentionally anchoring suppresses the adrift-only trigger.
- Converted the six-hour adrift threshold to the project's simulation clock (`DAY_LEN = 600` seconds per in-game day).
- Long-range tow calls now retain a small distance-faded chance of being heard instead of becoming impossible beyond the nominal range.
- Added a persistent tow status in the radio/controls strip. Successful tow arrival clears the request and provides emergency fuel as before.

## Design documents

- Added `docs/SINKING_AND_ABANDONMENT.md`, a complete proposed design for compartment flooding, list/capsize, deliberate abandonment, liferaft movement, fatigue, paddle loss, storm ejection, rescue, persistence, and headless tests.
- Added `docs/TOW_TRIGGER_DIAGNOSIS.md`, documenting confirmed v13.1.29 causes, the implemented fix, the simulation-time conversion, and regression coverage.
- Sinking/raft gameplay remains a proposed design; this release does not claim that the complete liferaft survival loop is implemented.

## Verification

- Focused tow regression tests, syntax compilation, and ZIP integrity checks are run for this release.
- A graphical Pygame playtest is not available in this environment.

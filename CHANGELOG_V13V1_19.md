# V13V1-19 — Line-setting crash fix and runtime error cache

## Fixed

- Fixed a critical `Longline._physics()` bug: the Verlet-history loop used `i` before it was bound. As soon as the first hook was emitted and physics ran during setting/hauling, the game could raise `UnboundLocalError` and close. The loop now enumerates particles so the anchored-winch check receives the correct index.
- Added regression coverage for the indexed particle-history loop and the one-button manual-setting path.

## Runtime diagnostics

The game creates `cache/errors/` automatically at launch and records:

- `runtime.log` — session start/end, frame-level action context, and structured line-setting events. It rotates at 2 MB with four backups.
- `errors.log` — Python errors and stack traces, rotating at 2 MB with six backups.
- `crash_*.txt` — a separate report for each caught or uncaught Python exception, including traceback, last input event, frame, ship position/speed/heading, distance from harbour, line phase/stage, hook count, stern crew power, engine/flood state and hatch state when available.
- `faults.log` — `faulthandler` output for low-level faults such as segmentation faults, where supported.

The run loop now records errors from input handling, simulation updates/line physics, and rendering before shutting down cleanly. The launcher installs the hooks before importing the game, so top-level startup errors are captured too. If the project directory is not writable, diagnostics fall back to the user-writable cache location.

## Where to look after a crash

Open `cache/errors/` in the project directory and send the newest `crash_*.txt` together with the final lines of `runtime.log` and `errors.log`. The line-setting request and stage changes are logged so a report identifies whether the failure happened on the `P` key request, initial hook emission, setting physics, soak, or haul.

## Verification

- `python -m py_compile fishing_sim/core/game.py fishing_sim/diagnostics.py run_fishing_sim.py fishing_sim/__main__.py` — passed.
- `python -m unittest discover -s fishing_sim/tests -v` — **315 tests passed, 0 failed**.
- Pygame is unavailable in the build environment, so the visual run was not performed; the manual-set failure itself is fixed by the particle-index change, and the runtime logger is exercised through focused tests.

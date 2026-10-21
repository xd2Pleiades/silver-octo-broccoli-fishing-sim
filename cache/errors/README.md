# Runtime error cache

The game creates and writes diagnostic files here automatically when launched.

- `runtime.log` — session events and basic runtime information (rotates).
- `errors.log` — errors and full logged exception traces (rotates).
- `crash_*.txt` — one report per caught or uncaught Python exception, including a traceback and compact game-state snapshot.
- `faults.log` — low-level Python fault output from `faulthandler` when supported.

When reporting a crash, send the newest `crash_*.txt` and the relevant tail of `runtime.log` / `errors.log`. These logs can include in-game state such as coordinates, vessel status, current line phase and point count; they do not intentionally collect account or personal information.

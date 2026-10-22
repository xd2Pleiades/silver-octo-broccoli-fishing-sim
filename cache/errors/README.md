# Error cache

The launcher (`run_fishing_sim.py`) installs runtime diagnostics before the game starts and creates this
folder if it is missing. Nothing here is needed to play; it only exists to help diagnose problems.

| File | What it is |
|---|---|
| `crash_*.txt` | One report per uncaught exception: a timestamp, the traceback, and a snapshot of the game state (ship, line, crew) taken at the moment of the crash. Send the newest one when reporting a bug. |
| `runtime.log` | Rolling info-level log of the session (rotates at about 2 MB, keeps 4 older files). |
| `errors.log` | Rolling log of caught errors and warnings (rotates at about 2 MB, keeps 6 older files). |
| `faults.log` | Low-level interpreter fault output (hard crashes inside native libraries). |

It is safe to delete any of these files; the game recreates them as needed.

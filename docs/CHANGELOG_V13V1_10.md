# V13V1-10 — Skill-Weighted Crew Reports

## Implemented

- Added pure, testable skill-weighted observation functions for bearing, distance, and speed in `fishing_sim/systems/crew_reports.py`.
- Added **I** to request bearing/range to the nearest visible named landmark and **O** to request a speed-log reading from the selected eligible main-deck sailor.
- Added a **five simulation-second** second-opinion window. Clicking a different eligible deckhand during the window automatically requests an independent repeat of the same kind of report and, where applicable, the same landmark.
- Added a HUD comparison card showing both values, each sailor's name and skill, the measurement spread, and a discrepancy hint without declaring which reading is true.
- Reports and comparison summaries use the existing speech-bubble and notebook-log path. Neither report generation nor comparison mutates physical or believed ship position.
- Added focused tests for report noise and units, seeded reproducibility, skill-dependent error variance, bearing wraparound, input integration, second-opinion constraints, and hidden-truth separation.
- Updated the V13 roadmap and README to record the implemented milestone and verification status.

## Verification

- `python -m compileall -q fishing_sim run_fishing_sim.py` — passed.
- `python -m unittest discover -s fishing_sim/tests -v` — **226 passed**.
- A live Pygame graphical playtest was not possible in the build environment; please verify report-bubble and comparison-card readability and second-opinion click timing on Windows.

## Controls

- **I** — selected deckhand reports bearing and range to the nearest visible named landmark.
- **O** — selected deckhand reports speed.
- Click another eligible main-deck sailor within five simulation-seconds to request an independent second opinion.

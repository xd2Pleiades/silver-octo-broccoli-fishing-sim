# Merge Report — Fishing Simulator v13.1.34

## Inputs compared

- **Uploaded:** `fishing_sim_v13_1_32.zip` (204 archive members).
- **Existing newer branch:** `fishing_sim_v13.1.33.zip` (200 archive members).

The uploaded archive was not just an older copy: it contained a crew cohesion update and captain-controlled fishing-trip orders absent from the existing v13.1.33 build. Conversely, v13.1.33 contained the dedicated Coast Guard escort module and visible harbour-to-player launch approach absent from the uploaded ZIP.

## What was merged from the uploaded v13.1.32

- Idle non-sleeping crew below deck return to deck standby rather than remaining in the engine room/cabin between jobs.
- Social partners must be awake and on the same deck level.
- Better fatigue/morale recovery while sleeping in a bunk.
- Below-deck and sleeping crew react later to a man-overboard shout.
- Right-click captain orders for **Fish: 3-day trip** and **Return to port**, plus trip progress and early-return reasons for fuel, bait, and ice.
- The cohesion behavioral test module and `cache/errors/README.md`.
- Updated Phase 3/4 roadmap wording and captain order controls text.

## What was retained from v13.1.33

- `TowEscort` as a separately tracked Coast Guard entity with its own callsign, captain/personality, crew roster, true position, and reported chart position.
- Visible **PLACE HOLDER SHIP** hull using the fishing vessel's geometry as reference, with Coast Guard livery, windows, wake, and physical towline.
- Launch movement from harbour to an intercept point; the tow starts only after the launch arrives alongside and completes handover.
- Chart marker, staleness `?`, radio check-ins, position query, captain conversation topics, towing arrival messaging, and tow retry/adrift logic.

## Merge method and reconciliation

- Compared the uploaded and v13.1.33 archives by file hashes and source diffs. There were 11 shared files with differences, plus branch-specific files on each side.
- Used a three-way merge of `fishing_sim/core/game.py` against the v13.1.31 working baseline. The source merge completed without conflict markers, preserving the v13.1.32 trip/crew additions and v13.1.33 tow-escort logic together.
- Kept the two historical v13.1.32 changelog variants separately: the tow-escort one retains its existing name, while the uploaded cohesion notes are preserved as `CHANGELOG_V13_1_32_COHESION.md` (at root and under `docs/`).
- Updated the app/package version to **13.1.34**, merged the controls and roadmap, and added dependency-free merge-contract tests. One dead-reckoning test was updated to assert that the navigation fix resets at **tow arrival**, not at handover.

## Automated verification

- Focused combined test run: **97 tests run; 82 passed, 15 skipped**.
- The skipped tests are the live v13.1.32 cohesion/trip simulations, because their module needs Pygame, which is unavailable here. The dependency-free merge contracts checked the presence and wiring of key trip, crew, and tow features.
- `python -m compileall -q fishing_sim`: passed.
- Full unittest discovery exceeded the 180-second execution limit; it is not represented as passing.
- The final ZIP passed its integrity test and contains the expected merged files.
- No graphical playtest was performed.

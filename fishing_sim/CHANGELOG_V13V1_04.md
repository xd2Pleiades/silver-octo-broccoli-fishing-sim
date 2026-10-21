# V13V1-04 — Dead Reckoning, Believed Position, and Hook-Profile Spacing

## Implemented

- Added separate `World.believed_pos`, `believed_heading`, and `believed_speed` state while preserving `ship_pos`, `heading`, and `speed` as the authoritative physical state for movement, collision, land avoidance, ship AI, and existing world systems.
- Added slow compass/log bias evolution with bounded values, estimated-motion integration, and crew-facing doubt growth weighted by helm skill, sea state, daylight, fog, rain, and vessel speed.
- The full-screen navigation chart now plots the crew's believed position and heading. Its uncertainty ring is based on the estimate's doubt value; it does not draw or print the hidden true position-error vector.
- Updated compact telemetry and the F1 navigation sheet to display believed speed/heading, navigational doubt, and time since the last known-position fix. The coarse harbour/coastal/deep-sea label in the sheet is derived from believed position as well.
- Added `reset_position_fix()` as the common reset point for later landmark, sextant, RDF, and sounder fixes. Known positions at departure, arrival alongside, and tow-in reset the estimate. Player-operated navigation fixes remain milestone `v13v1-06`.
- Moved the upper-right water-column / line-hook profile down exactly 20 px, from `y=62` to `y=82`, creating a gap below the top-right yen counter.
- Added a Pygame-free dead-reckoning helper module and focused model/integration-contract tests for drift, bias bounds, environmental weighting, fix-age formatting, true/belief separation, chart/HUD use, the 20 px panel shift, and known-position reset behavior.
- Updated the roadmap, README, release caption, and launcher package metadata while retaining the previous systems, user-supplied plan documents, launcher, and ZIP preservation marker.

## Verification

- `python -m compileall -q fishing_sim run_fishing_sim.py` — passed.
- `python -m unittest discover -s fishing_sim/tests -v` — **130 tests passed**.
- Fresh-extraction tests, archive integrity, launcher, and required root files — verified before release.
- Pygame is unavailable in the build environment, so live chart behavior, UI spacing at multiple window sizes, and actual drift feel still require graphical playtesting on Windows.

## Scope boundary

The chart remains read-only in this milestone. It uses a crew estimate but does not yet accept route waypoints or offer landmark/sextant/RDF/sounder corrections. Waypoint plotting is `v13v1-05`; position-fix actions are `v13v1-06`.

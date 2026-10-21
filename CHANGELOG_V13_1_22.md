# Fishing Simulator 13.1.22 — Lower-deck drawing crash hotfix

## Fixed

- Fixed the reported crash while drawing the lower-deck view. `Ship.draw_level_view()` used `L` and `B` to draw structural frames and the hallway without binding those names, producing `NameError: name 'L' is not defined` in `Game.draw()`.
- Bound `L` and `B` from `self.length` and `self.beam` at method entry, so the wheelhouse and lower-deck render paths have their ship geometry dimensions available.
- Updated the package and runtime session version to `13.1.22`.
- Added regression tests for the previously unresolved dimensions and the exact lower-deck frame/hallway paths.

## Validation

- Python compilation: passed.
- Full automated suite: **337 tests reported OK, 0 failures**.
- Targeted crash regression tests: 2 passed from the extracted release.
- ZIP integrity: passed.
- Note: in the build container, the full unittest runner printed its successful 337-test summary but did not terminate afterward before the external timeout. The test suite itself completed with `OK`; the cause of the lingering process is separate from the rendering regression.
- A graphical playtest is still recommended to confirm lower-deck cutaway drawing on Windows/Pygame; Pygame is not installed in the build environment.

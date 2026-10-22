# Fishing Simulator 12v18.1 — Foam Renderer Hotfix

## Fixed
- Fixed a `NameError` in `World._wake()` where `shape_points()` initialized `points` but appended to the undefined name `pts`.
- Added a regression test that statically verifies the foam polygon helper appends to its initialized list, covering the render-only path even in headless test environments.

## Verification
- Full automated unit test suite passed in the available environment.
- Python compilation passed.
- Pygame graphical launch could not be tested here because Pygame is not installed in the build environment; re-run the Windows storm/wake scenario to confirm the renderer visually.

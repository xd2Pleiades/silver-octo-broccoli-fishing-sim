# Startup crash hotfix — v13.2.13 ship overhaul merge

Date: 2026-10-22

## Reported error

The application exited while constructing `Game()` and then `Ship()`, before the main window could start:

```text
self._build_art()
self.cap_poly = self._inset_poly(self.hull, 4.0)
TypeError: Ship._inset_poly() takes 2 positional arguments but 3 were given
```

## Root cause

`Ship._inset_poly(points, d)` is a helper that does not use instance state, but it had no `@staticmethod` decorator. Calling it as `self._inset_poly(...)` caused Python to inject `self` as an extra argument. `_clip_x` and `_spans` had the same definition/call mismatch.

## Fix

Added `@staticmethod` to all three geometry helpers:

- `Ship._inset_poly`
- `Ship._clip_x`
- `Ship._spans`

Added a regression test that checks each helper's static-method declaration.

## Validation

- `python -m py_compile fishing_sim/core/game.py` — passed.
- Selected ship layout, pathfinding, overhaul merge, release-hardening, and rescue tests — **45 passed, 1 skipped, 3 subtests passed**.
- The skipped test requires Pygame; Pygame is not installed in the validation environment, so graphical application startup was not verified here.

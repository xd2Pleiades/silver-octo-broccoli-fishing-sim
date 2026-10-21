# v13.1.22 crash fix — undefined hull dimensions in level rendering

## Reported failure

The crash report showed `NameError: name 'L' is not defined` in `Ship.draw_level_view()` while drawing the lower deck. The failing line was `xx = L * frac`; subsequent structural frames and hallway drawing also rely on `L` and `B`.

## Fix

The method now defines `L, B = self.length, self.beam` before either view branch. These are the same ship dimensions used by nearby ship layout and rendering methods, so this is a local binding fix, not a layout change.

## Regression coverage

`fishing_sim/tests/test_v13_1_22_level_view_crash.py` checks that `draw_level_view` binds both dimensions from the ship instance and that the lower-deck structural frame and hallway code uses them.

## What the fix does not claim

The source-level root cause is fixed. Since the build environment does not have Pygame installed, a full graphical startup and camera/level switching playtest cannot be performed here.

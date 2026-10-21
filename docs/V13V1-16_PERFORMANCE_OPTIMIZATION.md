# V13V1-16 — Performance optimization notes

This release focuses on repeated work in the **current v13v1-15 project**. It does not use the old `longliner_rts.py` prototype as the performance baseline.

## Applied changes

### Rendering

- Reuse a display-format ocean/background staging surface. The detailed background (waves, coastline, flecks, wake, land) is refreshed at **30 Hz max** and blitted between updates. Simulation and moving foreground actors remain on the normal frame loop.
- Reuse a full-window alpha staging surface for the mostly-static ship raster. Refresh static deck artwork at **30 Hz max**, crop it to the vessel bounds, and blit only that crop on intervening frames.
- Reuse panel backgrounds from a bounded LRU cache and cache font `render()` and `size()` results by text/style. Cash/date, telemetry, modal/panel backgrounds avoid unnecessary rectangle rerasterization.
- Reuse transformed fish sprites from a bounded rotation cache. Cached normalized foam shapes and seeded texture values avoid repeating identical trigonometry for each patch on each background refresh.

### Simulation / collision hot paths

- Keep land, reef, and hull collision vertices in prepared immutable tuples with cached bounds.
- Apply expanded-AABB and hull-radius tests before detailed polygon/capsule collision math and before rotating distant rope particles into deck-local coordinates.
- Reuse `Vector2` inputs in collision functions when safe and store previous rope positions as scalar tuples instead of making a copied Vector2 for each particle every physics step.
- Combine the repeated rope depth-clamp loop into the existing per-point pass. The six constraint iterations and final rope-segment collision sweep remain in place for behavior/stability.

These are behavior-preserving optimizations by intent, but the collision changes especially require visual playtesting because source-level unit tests cannot establish physical stability across a live run.

## Why these choices

Pygame's optimization guidance recommends converting surfaces that are blitted repeatedly, caching repeated rendering, and using profiling to identify the actual hottest sections. Its documentation says that `Surface.convert()` yields the fastest blit format for ordinary opaque blits and that `convert_alpha()` is appropriate when per-pixel alpha must be preserved. Dirty rectangles generally do not help a scene that redraws its whole display, so this release retains full-frame composition while caching expensive layers.

- Pygame optimization guide: https://www.pygame.org/wiki/Optimisations
- Pygame Surface API: https://www.pygame.org/docs/ref/surface.html
- Python profiling (`cProfile` / `pstats`): https://docs.python.org/3/library/profile.html

## How to measure on the real machine

Pygame could not be installed in the build environment, so **no numeric FPS improvement has been measured here**. Use the same resolution, zoom, sea state, crew activity, longline length, and rescue situation before and after to make a fair comparison.

1. Run normally and compare frame pacing in the same scene. Let the game settle after a resize; first cache rebuilds are intentionally more expensive than cache hits.
2. Close the game normally so the profiler can write its results, then run:

   ```powershell
   python -m cProfile -o v13v1-16.prof run_fishing_sim.py
   ```

3. Inspect cumulative Python time:

   ```powershell
   python -c "import pstats; pstats.Stats('v13v1-16.prof').strip_dirs().sort_stats('cumtime').print_stats(35)"
   ```

`cProfile` adds measurement overhead, so use it to locate Python hot paths rather than as the FPS benchmark itself. Also compare a normal unprofiled run. If frame rate still drops mostly during setting/hauling, inspect `Longline._physics`, `World.collide_longline_point`, and `World.collide_longline_segment`; if it drops near land/port, inspect `_land`, town drawing, and the background refresh path.

## Automated checks

From the project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

The performance pass adds headless source-contract tests for cache invalidation/reuse, bounded text/surface/foam/fish caches, collision broad phases, and rope-solver reductions. A graphical playtest is still required to assess actual frame times and verify that cached artwork refreshes smoothly during changes in camera zoom, ship state, weather, foam, and rescue activity.

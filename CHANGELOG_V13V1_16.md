# V13V1-16 — Performance and render-cache pass

## What changed

- **Ocean/background rendering:** the animated water/coast layer is refreshed at a bounded 30 Hz while actors and simulation continue on the normal frame loop. The compatible-format background staging surface is reused across refreshes instead of allocating a new full-window Surface each time.
- **Ship rendering:** mostly-static deck artwork is rasterized at a bounded 30 Hz, cropped to the visible ship bounds, and composited as a smaller image between refreshes. Its full-window alpha staging surface is reused rather than reallocated on every refresh.
- **UI rendering:** bounded caches reuse transparent panel surfaces, including telemetry, cash/date, modal backgrounds, and repeated font renders/sizes. Repeated text does not need to be rasterized when its content/style is unchanged.
- **Fish and sea foam:** fish rotation/scale transforms use a bounded LRU cache. Seeded foam hashes and normalized foam shape templates are cached, avoiding repeated trigonometry for immutable patch details.
- **Longline/rescue collision hot paths:** immutable land/reef/hull geometry and AABBs are precomputed. Cheap bounds checks avoid polygon tests for distant points/segments, hull-radius checks avoid unnecessary world-to-deck transforms, and repeated Vector2 snapshots/clamp passes in the rope solver were reduced without removing its six constraint iterations or final segment sweeps.
- **Docs and roadmap:** added the performance guide, updated the version/roadmap status, and retained the full Markdown history in the ZIP.

## Research basis

The approach follows Pygame's optimization guidance to convert repeatedly blitted surfaces to display-compatible formats, cache repeated drawing work, and profile Python hot paths. The official Surface API documents `convert()` / `convert_alpha()` for faster repeated blits; the Pygame optimization guide cautions that dirty rectangles do not help when the whole screen is repainted. See `docs/V13V1-16_PERFORMANCE_OPTIMIZATION.md` for links and profiling instructions.

## Verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

The headless suite passes **291 tests** and Python compilation passes. The added tests check render-cache reuse and resize invalidation, bounded caches, collision broad phases, rope solver allocation/pass reductions, and cached deterministic foam geometry.

**No measured FPS gain is claimed.** Pygame is unavailable in the build environment, so the game could not be launched or benchmarked graphically here. The release is source/test verified; capture FPS and frame-time profiles on the target Windows machine using the instructions in the performance guide.

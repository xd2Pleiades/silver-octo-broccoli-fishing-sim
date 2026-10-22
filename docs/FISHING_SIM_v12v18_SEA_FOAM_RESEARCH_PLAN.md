# Fishing Simulator v12v18 — Sea Foam Research & Implementation Plan

**Status:** Research and design basis implemented in `fishing_sim_v12v18.zip`. The implementation follows the design, with automated headless checks; visual playtesting remains outstanding.

**Base release:** `fishing_sim_v12v17.zip`

**Goal:** Make sea foam feel like water reacting to waves and a moving fishing vessel, rather than decorative white circles attached to the ship. Keep it feasible for Pygame's 2D software renderer and preserve the current game systems.

---

## 1. Research findings

### 1.1 What sea foam represents

NOAA explains that sea foam forms when wind and waves agitate seawater and trap air. Dissolved organic material—including proteins and fats from marine life—helps stabilize bubbles so they last long enough to form foam. Foam amount therefore relates to water agitation and local water conditions, not solely to the boat's speed.

Source: [NOAA Ocean Service — What is sea foam?](https://oceanservice.noaa.gov/facts/seafoam.html)

NOAA's wave guidance describes stronger/continuing wind building waves until whitecaps form and waves break. A game should therefore generate wave-top foam more aggressively in rougher, windier conditions and not treat every white line on the ocean as a breaking crest.

Source: [NOAA JetStream — Waves](https://www.noaa.gov/jetstream/ocean/waves)

### 1.2 Visual categories to model separately

1. **Whitecaps / crest foam:** Irregular, short white patches on the crests of waves. Primarily driven by wave energy, wind, and breaking conditions. They can exist even when the ship is stopped.
2. **Bow shoulders:** Foam generated where the bow pushes water aside. It should sit on both sides of the forward hull and split around the bow.
3. **Hull-side wash:** Broken bands of turbulence along the ship's sides; intensity depends on speed, hull geometry, and sea state.
4. **Stern wake / prop wash:** A persistent, lengthening trail behind the ship. It should be strongest while moving under power, spread and fragment over distance, and not remain glued to the vessel after the vessel moves away.
5. **Spray / spindrift:** A separate, short-lived airborne effect. Use sparingly, particularly when speed and/or wind and wave energy are high. Spray should not be used as a substitute for surface foam.
6. **Dissipation and drift:** Foam patches fade, break up, and are advected away by the local water/current and wind. A trail should retain a short-lived history after its source passes.

These are visual modelling categories for the game, not a claim that the simulator needs a full hydrodynamic model.

### 1.3 What Pygame supports

- `pygame.draw` provides lines, polygons, circles, ellipses, and antialiased lines; drawing functions work on Surfaces and respect the Surface clip area. This suits layered stylized foam geometry.
- `pygame.gfxdraw` offers antialiased circles/polygons and filled variants. It is explicitly described as experimental in the Pygame documentation, so it should be optional or isolated behind a helper rather than required for every foam mark.
- Alpha transparency can be rendered with RGBA Surfaces. Use a reusable `SRCALPHA` overlay or cached stamps instead of creating a new large Surface for every mark.
- Pygame documents per-pixel access such as repeated `get_at`/`set_at` as slow; avoid drawing foam by editing individual pixels in Python loops.
- `pygame.transform.smoothscale` creates a transformed Surface and should start from the original image instead of repeatedly scaling a previously scaled Surface. If foam stamps are used, prebuild a small size family and reuse it.

Sources:
- [Pygame `draw` reference](https://www.pygame.org/docs/ref/draw.html)
- [Pygame `gfxdraw` reference](https://www.pygame.org/docs/ref/gfxdraw.html)
- [Pygame `Surface` reference](https://www.pygame.org/docs/ref/surface.html)
- [Pygame `transform` reference](https://www.pygame.org/docs/ref/transform.html)

### 1.4 Useful pattern from dedicated ocean renderers

Crest's ocean-simulation documentation describes generating foam at steep/pinched wave crests, optionally generating foam from shallow-water interaction, then reducing foam values over time to model dissipation. It also exposes separate strengths/coverage and a configurable update frequency. That is a useful conceptual pattern even though Crest is a 3D Unity renderer and must not be copied as a direct Pygame dependency.

Adaptation for Fishing Sim: detect/proxy energetic wave crests, deposit bounded foam marks, and fade them over time. We do **not** need Crest, a GPU shader, a 3D mesh, a fluid solver, or a per-pixel foam simulation.

Source: [Crest Ocean System — Ocean Simulation / Foam](https://crest.readthedocs.io/en/4.15/user/ocean-simulation.html)

---

## 2. Audit of the current 12v17 implementation

Inspected file: `fishing_sim/core/game.py` in the 12v17 project.

Existing foundations to preserve:

- `WaveField` combines four sinusoidal wave components and exposes wave height, amplitude, direction, strength, and time.
- `World.draw()` draws background waves and ocean flecks, then calls `World._wake(g, ov)` before the water overlay is blitted and the ship is drawn by the main game renderer.
- `World._wake()` already has bow-side ribbons, ship-side streaks, an aft wake, foam circles, and wave crest flecks. Its calculations use normalized ship speed and sea state.
- The current puff count is bounded: `18 + int(34 * speed_frac) + int(18 * sea)`, which produces 18–70 puffs. The existing fixed bound is a good performance principle.

Limitations observed in the source:

- Most wake ribbons and foam flecks are reconstructed around the ship from the current time every frame. They are procedural decoration, not foam patches with a life cycle and a persistent trail in the water.
- The wake's position and length react to speed, but older foam does not really remain behind the ship and drift/fade independently.
- Whitecaps are mostly crest lines and a few rough-sea flecks; they are not represented as distinct, irregular foam patches associated with energetic crests.
- Wake foam, wave-top foam, and airborne spray are not separate systems, so increasing all the marks risks making the sea look like uniformly white noise.
- Repeatedly drawing lots of big circles/lines is simple, but visual quality depends more on shape, placement, layering, and motion than simply increasing the number of marks.

**V18 should extend the existing implementation, not replace the `World`/`WaveField` renderer or alter the gameplay physics.**

---

## 3. Proposed v12v18 design

### 3.1 A small, independent foam simulation

Create `fishing_sim/systems/sea_foam.py` for foam state and emission rules. Keep it independent of Pygame drawing where practical, so particle lifecycle and cap tests can run without an actual display.

Suggested data model:

- `FoamParticle` / `FoamPatch`: world position `(x, y)`, water drift velocity, age, lifetime, radius/length, alpha/intensity, orientation, and kind (`wake`, `crest`, `spray` if spray shares the system).
- `SeaFoamSystem`: bounded active particle list, deterministic seeded random generator, spawn accumulators, update method, and small counters for debugging.
- A configurable hard cap. Start with **240 active foam elements** for the default profile; test lower/higher caps before choosing a final number. If the cap is reached, recycle the oldest/least-visible patch rather than allowing memory growth.
- Time-based emission accumulators, so spawning remains approximately consistent at different frame rates. Do not use a new random draw to decide all particle positions independently every rendered frame; that causes visual flicker.
- Keep physics independent from rendering: updating state and deciding spawn events is separate from drawing surfaces.

The final module can use the project's existing vector type if that keeps dependencies simple, but pure numeric tuples are preferable for tests if importing `game.py` requires Pygame.

### 3.2 Correct coordinate handling

The current water camera is centred on the ship: `Game.S()` projects a water-frame offset from the screen centre, and the wave equations also use `ship_pos`/heading to keep sea motion coherent.

For persistent foam:

1. Store each foam patch in absolute water/world coordinates, not screen coordinates.
2. When spawning a wake patch, transform its local bow/beam/stern offset into world coordinates using the ship's current heading and position.
3. On render, transform the patch into the camera's ship-relative frame by subtracting `ship_pos` and rotating by the inverse view heading before passing it to `Game.S()`.
4. Apply water/wind drift in world space, then update age and size/alpha.

This prevents foam from remaining attached to the ship as if it were painted on the hull. Confirm the sign of heading rotation against the project's coordinate convention with a small motion test before tuning visuals.

### 3.3 Emission rules: separate causes of foam

Use the existing normalised `sea_state`, `WaveField.strength`, weather/wind values, ship speed, heading, and hull dimensions. Keep every factor clamped.

**Wake / propulsion foam**

- Emit along both bow shoulders, just outside the hull, along the beam/sides, and in the stern/prop-wash area.
- Spawn rate should rise with `speed_frac`; wake length and lateral spread should also rise with speed.
- Sea state adds roughness, scatter, and density but should not make a stopped vessel produce a long powered wake.
- Very low-speed drift can retain small local wash, but the long aft ribbon should contract as the ship slows.

**Wave crest / whitecap foam**

- Remain active when the ship is stopped if sea state/wind is high enough.
- Use current WaveField components to locate candidate crest segments or use deterministic sample points along the existing crest geometry; only create patches when sea-state/crest-energy gates are met.
- Make whitecap marks short, fragmented, irregular, and oriented with the crest. Avoid continuous bright stripes across the whole sea.
- Raise coverage as the existing wave amplitude/strength rises. Do not infer exact ocean physics from the game's 0–1 sea-state number; it is a gameplay control, not a calibrated wave-height measurement.

**Spray / spindrift (lightweight accent)**

- Only add when wind/sea state is high and/or ship speed is significant.
- Spawn a small bounded number of quick, short-lived streaks near the bow/sides.
- Push spray downwind and fade it quickly. This is an accent layer and should not hide sailors, rescue boat, MOB swimmer, fishing line, or active controls.

### 3.4 Foam appearance and ageing

Each patch should have a short visual life cycle:

1. **Birth:** bright/compact splash or crest mark.
2. **Spread:** a little wider, lower-opacity, softer/fragmented shape.
3. **Drift:** advect along water/wind direction; wake patches should visibly remain in the water behind the moving vessel.
4. **Dissipation:** lose opacity and size, optionally split into smaller fragments, then be removed.

Use overlapping shapes with hierarchy rather than flat white dots everywhere:

- muted aqua/blue shadow fringe under the white foam;
- pale cyan translucent body;
- small bright white core or broken highlight lines;
- uneven patch edges, elliptical shapes, and slight orientation variation;
- whitecap pieces that follow crest orientation;
- narrower inner stern wash plus broader, fading outer wake.

Alpha blending must be done on a reusable transparent overlay or cached stamp surfaces. Use `pygame.draw`/`aaline` for the inexpensive base pass; optionally use `gfxdraw` in one isolated helper for a few critical edges, but don't require it throughout the system. Cache a small set of foam stamp sizes/orientations if profiling shows drawing cost is high. Avoid a new full-screen Surface per foam patch and avoid per-pixel `set_at` loops.

### 3.5 Layer order

Preferred draw sequence:

1. Sea base/background.
2. Existing wave bands and base ocean texture/flecks.
3. Persistent foam patches in the water, including older stern wake and distant crest foam.
4. Near-hull/bow interaction shapes that belong behind the hull.
5. Ship hull and deck/sailors, which occlude the water foam.
6. A very small optional spray pass above the waterline near the bow, clipped/positioned so it cannot obscure interaction targets.

Keep rescue boat and swimmer visibility clear. A foam mark must never be drawn over the person-in-water indicator in a way that makes the casualty difficult to find. The ship must occlude surface foam naturally.

### 3.6 Performance and stability

- Hard cap particle count and use spawn accumulators. No unbounded lists.
- Update foam at a lower fixed cadence (start at **15–20 updates per second**) while rendering it every frame, interpolating only if needed. Compare visual smoothness before accepting the lower update rate.
- Cull patches that are far outside the visible sea rectangle; also expire patches by age.
- Use a deterministic PRNG seed for repeatable tests. A per-session seed is fine for gameplay, but don't generate fresh unrelated geometry every frame.
- Keep drawing into the existing water overlay where possible; do not add a second full-screen transparent layer unless profiling supports it.
- Add an optional low/normal/high foam quality setting or constants (for example caps of 100 / 240 / 360) only after benchmarking. No new hotkey is needed for the initial release.
- Debug counters can expose active patches, cap usage, spawn rate, and frame time in the existing debug/status path; hide them during ordinary play.

---

## 4. Suggested implementation milestones

### V18.1 — Persistent wake foundation

- Add pure foam state/particle lifecycle module.
- Integrate bounded, time-step-based wake emission and per-frame drawing.
- World-coordinate spawn/render conversion; verify trail remains behind the ship as it advances and turns.
- Keep current `_wake()` geometry as a temporary fallback behind a debug flag until the new renderer is validated.

### V18.2 — Whitecaps and wave interaction

- Generate irregular crest patches from WaveField/sea-state inputs.
- Ensure whitecaps work at low/zero ship speed when weather is rough.
- Separate wave crest foam from propulsion wake tuning.

### V18.3 — Polish and performance

- Add optional bow spray/spindrift accent.
- Layer colour/alpha and cache any repeated stamps that improve performance.
- Add quality caps, off-screen culling, visual QA screenshots, and debug counters.
- Remove the old wake fallback once the new system passes acceptance checks.

These are implementation checkpoints inside the **12v18** release unless a regression forces the work to be split into a follow-up patch.

---

## 5. Acceptance checks for 12v18

### Visual / behavior

- [ ] At rest in calm water, there is no long powered stern wake and only minimal hull foam.
- [ ] At rest in rough water, wave crests still create irregular whitecaps.
- [ ] At low speed, bow foam is small and the wake is short.
- [ ] At cruising speed, the bow shoulders split water, side foam trails away, and the stern wake has a visible centre path and broken outer edges.
- [ ] After a ship moves forward, older foam remains behind it in water space, drifts/fades, and does not stay attached to the screen-centred ship.
- [ ] Turning the vessel does not rotate/teleport the entire old wake with the hull.
- [ ] Foam amount responds smoothly to throttle/speed and sea state; there are no abrupt count jumps or frame-to-frame random flicker.
- [ ] Foam remains behind the hull and does not obscure the rescue boat, swimmers, crew, longline, or fishing controls.
- [ ] Spray is distinct from surface foam and remains restrained in calm weather.

### Technical / performance

- [ ] Active particle count never exceeds the configured cap.
- [ ] Expired/off-screen patches are removed or culled safely.
- [ ] Emission is time-step based and does not dramatically increase when FPS rises.
- [ ] Deterministic tests cover aging/fading, speed-dependent wake emission, sea-state whitecaps, cap enforcement, and world-to-view coordinate conversion.
- [ ] Existing tests still pass, all Python files compile, and ZIP contains `run_fishing_sim.py` plus `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`.
- [ ] Capture comparison screenshots at idle/calm, cruising/calm, stopped/storm, and cruising/storm; perform a live Pygame playtest on the Windows setup.

### Regression protection

- [ ] No changes to steering, waves-as-gameplay, engine load, man-overboard rescue, bucket lines, auction, crew AI, or HUD other than the world-water render layer.
- [ ] Foam simulation does not modify collision geometry, sea-state values, vessel motion, or rescue logic.
- [ ] The update has no dependency on Unity, Godot, shaders, GPU compute, or external render libraries.

---

## 6. Research references

1. NOAA Ocean Service, **What is sea foam?** — foam forms as wind/waves agitate water and organic material helps stabilise air bubbles: https://oceanservice.noaa.gov/facts/seafoam.html
2. NOAA JetStream, **Waves** — wind energy increases wave development and whitecaps/breaking waves: https://www.noaa.gov/jetstream/ocean/waves
3. Pygame documentation, **pygame.draw** — drawing primitives and antialiased lines: https://www.pygame.org/docs/ref/draw.html
4. Pygame documentation, **pygame.gfxdraw** — antialiased filled shapes; documented experimental status means isolate its use: https://www.pygame.org/docs/ref/gfxdraw.html
5. Pygame documentation, **Surface** — alpha blending and Surface transparency: https://www.pygame.org/docs/ref/surface.html
6. Pygame documentation, **pygame.transform** — smooth scaling and why transformations should start from the original Surface: https://www.pygame.org/docs/ref/transform.html
7. Crest Ocean System, **Ocean Simulation: Foam** — foam from energetic/pinched crests and gradual fade/dissipation; used only as an architectural reference for a lightweight 2D adaptation: https://crest.readthedocs.io/en/4.15/user/ocean-simulation.html

---

## 7. Implementation rule

**Implementation record:** `fishing_sim_v12v17.zip` was used as the base. The completed release is `fishing_sim_v12v18.zip`; the main roadmap and `CHANGELOG_V18.md` are updated, the launcher/marker are preserved, 83 tests and Python compilation pass, and graphical playtesting still needs to be done with Pygame installed.

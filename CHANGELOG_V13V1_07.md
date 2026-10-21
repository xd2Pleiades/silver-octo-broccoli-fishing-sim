# V13V1-07 — Readable Fishing Cues, Crew Lookout, and Follow Birds

## Visual cue scale correction

- Working gulls are now **24–34 px wide at normal 0.6 zoom**, close to or larger than the sailor's torso width. Each gull has thick white wings with a dark outline and a visible body point, replacing the prior 1–3 px specks.
- Flock size scales with hotspot strength (6–32 working birds). Strong schools create a dense, tight cluster; as the school weakens, count falls, orbit radius expands, and gulls become greyer.
- Water colour uses three low-alpha green, teal, and blue concentric discs. Flotsam polygons gather near the centre and stop below strength `0.30`; expanding white ripple rings stop below strength `0.20`.
- Cue drawing remains deterministic per school/time and bounded by the four-hotspot model. Physical cues do not depend on sailor skill or discovery state.

## Crew-dependent tier-two cues

- Sailors now track `gut_spot` and `gut_confidence`. Detection requires aboard/main-deck state, forward facing, range, skill, daylight, and weather visibility. Confidence takes sustained observation to build and fades when sight is lost.
- Once a sailor reaches confidence `>= 0.5`, one pale-yellow pulsing diamond appears for the school. An off-screen triangle points toward the school at the safe screen edge. Duplicate markers are prevented even if several sailors detect the same spot.
- The first confident sailor gives one skill-appropriate report: generic bird activity for green hands, tentative species for a trained hand, and actionable feed information for a veteran.

## Stern-following birds

- Added persistent dark V-shaped birds that follow the stern during setting (8), soaking (4), and hauling (14). They disappear at night, in storms, or when the line is idle.
- Follow birds are drawn below HUD overlays, trail in world space, and do not affect physics or the working-bird hotspot cues.

## Verification

- 177 automated tests pass from the project test suite.
- Python compilation passes for all project modules and the launcher.
- ZIP archive integrity and required launcher/preservation files are verified.
- Pygame is not installed in the build environment; a live visual playtest remains outstanding. Confirm the gull scale against the actual sailor and hull at default zoom, and inspect fog, night, strong/fading schools, and off-screen gut arrows on Windows.

## Roadmap

The cue scale/lookout/ambience milestone is now `v13v1-07`. Position-fixing methods move to `v13v1-08`; all later milestones remain in sequence except that crew reports become `v13v1-09` and auto-fishing hotspot hunting is `v13v1-10`.

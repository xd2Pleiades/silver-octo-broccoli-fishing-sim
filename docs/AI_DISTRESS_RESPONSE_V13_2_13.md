# v13.2.13 — Autonomous AI Distress Response (M9)

## Behavior

The AI fleet now has a first physical response path for unattended AI MAYDAY incidents. The manager uses one existing scheduled fleet vessel at a time. It does not create a new Coast Guard hull or duplicate the active TowEscort runtime identity.

- **Dispatch grace period:** 42 simulation seconds in normal conditions; 12 simulation seconds when sea state at the incident is at least 0.75. The dispatcher retries every 4 simulation seconds while waiting for an eligible responder.
- **Responder eligibility:** scheduled Coast Guard patrols may respond from up to 49 NM. Nearby eligible independent and corporate fishing vessels may respond within a weather-adjusted radius between 8 NM and 15 NM. A vessel already distressed, anchored, committed to an override, without usable speed, or already operating under another runtime role is not selected.
- **Selection:** expected response time is the primary ordering; Coast Guard receives preference when ETAs tie. Only one autonomous AI response is active at a time.
- **Physical movement:** the responder retains its existing vessel ID and position. It turns at a finite angular rate and moves along its current heading toward a desired track; dispatch does not teleport it to the distress position.
- **On scene:** within 1.25 NM, the responder stops travelling and conducts a distinct six-simulation-second assistance interval. The target then remains at the distress scene in an anchored/assisted state.
- **Return to patrol:** the responder keeps a physical position override while steering toward its live scheduled position. The override is released only when it reaches the schedule's rejoin tolerance.
- **Storm behavior:** dispatch urgency and nearby-support radius sample weather at the distress location when available, not just the player's current sea state.
- **Conflict prevention:** if the player has a committed rescue mission for the same target, the AI manager skips it. The radio decision path also prevents a second manual acceptance once an AI response is already assigned.

## Persistence

`ai_rescue_mission` is an optional career-save section so older v13.2.13 saves remain loadable. The validator verifies the mission schema, active target and responder contacts, distress state, mission-state/status correspondence, and saved physical overrides. Traffic contact snapshots preserve the position/activity overrides; loading reapplies them before the mission resumes. A live graphical `Game` save/load round-trip has not been run in this environment.

## Headless validation

`fishing_sim/tests/test_v13_2_13_ai_rescue.py` covers:

- No extra ship is spawned and the responder uses a scheduled vessel identity.
- Normal grace period versus shorter storm response window, including a remote distress-area weather sample.
- An ignored distress can still receive an autonomous responder.
- Finite-rate turning, physically moved arrival, timed on-scene assistance, and steering back to patrol.
- Mission/contact snapshot round-trip and rejection of invalid manager snapshots.
- Waiting for a vessel to become available and conflict guards for player-assigned rescue targets and campaign phase switching.

The test suite is headless by design. It does not establish that the on-screen map marker, UI radio text, ship sprites, or Pygame career load UI render correctly. Those remain on the visual QA checklist.

## Next M9 work

1. Transfer casualties to a rescue vessel and add liferaft pickup/survival using stable mission identity.
2. Extend from one autonomous AI response to a bounded multi-incident queue only after response timings and contact limits are measured.
3. Run live Pygame tests for player rescue, AI response, storm dispatch, and save/load while en route, on scene, and returning to patrol.

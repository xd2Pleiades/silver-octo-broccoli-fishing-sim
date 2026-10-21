# Fishing Simulator v13.1.31

## Tow delay and stranded-vessel assistance

- Fixed a long-range tow delay: the previous minimum response probability was just 0.4%, which could plausibly leave the persistent request unanswered for several in-game days. Repeated unanswered calls now increase the reply chance both inside and beyond nominal range; offshore calls start at a 4% floor and rise with each failed attempt up to a cap. Range, radio clarity, and weather still matter.
- Improved the adrift trigger so failed engine health/effective power counts as unavailable propulsion even when the ignition is still on and fuel remains.
- Made the tow trigger explicitly use `speed_through_water`. In this implementation current and wind displacement are applied separately, so ground drift does not defeat the “no way on” check.
- Added optional `F12` tow diagnostics: prints fuel, through-water speed, sampled ground displacement, adrift state/timer, anchor state, tow state, and unanswered-call count to the console once per simulation second.
- Preserved continuous tow movement, position-belief reconciliation, emergency fuel on arrival, the anchor exclusion for adrift-only triggers, and persistent radio retries.

## Design documents

- Added `docs/TOW_REQUEST_AND_DISTRESS_RADIO.md` using the supplied design text. It remains a proposed design for the fuller PAN-PAN/MAYDAY conversation system, traffic listening, acknowledgement states, and responder population; the full conversation state machine is not claimed as implemented in this version.
- Updated `docs/TOW_TRIGGER_DIAGNOSIS.md` to distinguish the verified current implementation from the supplied speed-over-ground hypothesis, and document the April 5–9 delayed-response issue and F12 diagnostic.
- Retained `docs/SINKING_AND_ABANDONMENT.md` as a proposed liferaft/sinking design.

## Verification

- Targeted headless tow-assistance tests and existing tow source-regression tests are run for this release.
- Python compilation and ZIP integrity checks are run.
- Pygame is not available in the build environment, so a live graphical playtest cannot be claimed.

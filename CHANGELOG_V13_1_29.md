# Fishing Simulator v13.1.29

## Controls tab and reference

- Retained the dedicated **F1 → CONTROLS** information-sheet tab and synchronized it with the standalone `CONTROLS.md` reference.
- Documented the anchor key/button, automatic low-fuel distress retries, and continuous tow return.

## Low-fuel towing

- Removed the automatic fuel-empty fallback that placed the vessel directly at the harbour.
- When fuel reaches zero offshore, the vessel keeps requesting assistance over the radio; failed or unanswered calls retry with radio-clarity and range affecting the reply chance.
- A successful response dispatches a tow, then moves the vessel toward the berth at a controlled tow speed. The position is advanced frame-by-frame rather than snapped to harbour.
- The tow clears the active line if needed, charges the tow fee, and supplies emergency fuel on arrival.

## Anchor

- Added an **ANCHOR UP/DOWN** button beside the money HUD and the `A` key.
- Dropping anchor cancels travel/docking orders, reduces current/wind drift, and prevents ordinary manoeuvring until weighed.

## Verification notes

- Python syntax compilation, focused source regression tests, and ZIP integrity checks are run for this release.
- A graphical Pygame playtest is not available in this environment.

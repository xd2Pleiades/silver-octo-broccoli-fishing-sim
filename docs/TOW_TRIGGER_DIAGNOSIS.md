# Tow Trigger Diagnosis and Reference Fix

**Applies to:** v13.1.29 baseline; implemented tow-request fix is included in v13.1.30.  
**Scope:** Diagnose the "floating for days without a tow" behavior and document the code-level correction. This is based on inspection of `fishing_sim/core/game.py`, not just a generic hypothesis list.

## Diagnosis from the shipped code

### Confirmed cause 1 — an unanswered manual tow was not persistent

In v13.1.29, `_update_radio()` retried a request only when both `tow_retry_elapsed` had elapsed **and** `self.fuel <= 0`. A player could press **F4** with fuel still in the tank, have the call fail due to static, and then never retry that request. The failed transmission did set a retry timer, but the fuel-only retry guard prevented the timer from doing its job.

### Confirmed cause 2 — idle drifting had no independent trigger

Automatic tow requests originated in `_logistics()` only after fuel reached zero. There was no timer for a powered-down vessel that had way on reduced to near zero while still carrying fuel. An engine-off vessel could therefore drift indefinitely without creating a request.

### Confirmed cause 3 — the radio range was a hard cutoff

The baseline set tow-reply probability to zero outside the nominal 9,000-unit range. The retry loop could keep transmitting but could not ever roll a successful answer at any distance beyond the cutoff. The fix keeps normal calls stronger at close range and allows a very small long-range MAYDAY chance, rather than a mathematical zero.

### Checked and not identified as the primary cause

- `tow_in()` itself already begins a continuous tow state rather than placing the ship at the berth immediately.
- `_update_tow_transit()` advances both the physical and believed ship positions by the same tow step. Arrival has only a small final snap (18 world units) to settle numerical residuals.
- The tow module does not use a `1,852` conversion in the actual transit step, so the pasted unit-conversion hypothesis is not the source of the retry guard failure. The existing code uses world-units-per-second for tow movement.

These checks do not rule out unrelated position jumps in other systems, but they distinguish them from the confirmed radio retry problem.

## Implemented behavior in v13.1.30

- A tow request becomes latched when the player presses **F4**. A failed transmission, an unattended radio, or a busy wireless set does not clear it.
- The request keeps retrying until a tug arrives and the ship reaches the berth, or until the game considers the vessel docked.
- An automatic tow request starts at 5% fuel capacity (35 L for the 700 L tank).
- A separate adrift trigger starts a request after six **in-game hours** without power and with speed below the no-way-on threshold. The trigger excludes an intentionally deployed anchor.
- The project defines one in-game day as `DAY_LEN = 600` simulation seconds. Therefore six in-game hours is `DAY_LEN * 6 / 24 = 150` simulation seconds, not 21,600 simulation seconds.
- The HUD keeps a persistent `TOW REQUEST ACTIVE` or `TOW ACCEPTED` line visible in the controls/radio strip.
- Long-range reception chance now fades with distance rather than becoming exactly zero outside 9,000 units. Distance, radio clarity, and weather interference still affect the chance.
- The actual return trip remains a continuous tow. Arrival supplies emergency fuel and clears the latched request.

## Reference implementation pattern

The shipped implementation uses project names and constants, but the essential control flow is:

```python
TOW_TRIGGER_FUEL_FRACTION = 0.05
TOW_TRIGGER_DRIFT_HOURS = 6.0
TOW_TRIGGER_DRIFT_SECONDS = DAY_LEN * TOW_TRIGGER_DRIFT_HOURS / 24.0
TOW_ADRIFT_SPEED = 8.0

# In logistics, each update:
adrift = (
    not docked
    and not tow_in_progress
    and not anchor_deployed
    and ship_speed < TOW_ADRIFT_SPEED
    and (not engine_on or fuel <= 0.0)
)
adrift_elapsed = adrift_elapsed + dt if adrift else 0.0

if fuel <= fuel_capacity * TOW_TRIGGER_FUEL_FRACTION \
        or adrift_elapsed >= TOW_TRIGGER_DRIFT_SECONDS:
    tow_request_active = True

# In radio update, irrespective of remaining fuel:
if tow_request_active and no_tow_call_or_tug_is_in_flight:
    decrement_retry_timer(dt)
    if retry_timer <= 0.0 and not docked:
        transmit_tow_request()
```

This is a level/state check, not an edge-triggered "fuel just crossed zero" event. A saved game loaded with no fuel, or an engine that was switched off before the timer began, can still enter the rescue path.

## Why the retry must not be fuel-gated

Fuel state determines **when** an automatic tow request is created. Once the player or the automatic system has requested a tow, the persistent request state determines **whether** the radio keeps trying. These are separate questions; tying retries to `fuel <= 0` is what made manual requests with fuel left silently stop.

## Regression tests

The v13.1.30 targeted source tests cover:

- Request state is initialized and persists independently of fuel.
- Failed/manual tow requests enter the retry path without a `fuel <= 0` gate.
- 5% fuel and six in-game hours adrift can trigger automatic towing.
- Anchor suppresses the adrift timer, without suppressing an emergency low-fuel request.
- Long-range tow chance is nonzero but distance-faded.
- The HUD retains the request state and successful arrival clears it.
- Tow movement remains continuous rather than snapping to the harbour.

A graphical Pygame test is still required to verify timing, the radio display, and the towing animation under real gameplay.

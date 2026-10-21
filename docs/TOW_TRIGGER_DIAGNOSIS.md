# Tow Trigger Diagnosis and Reference Fix

**Applies to:** v13.1.30 behavior; the corrected trigger and escalating response are in v13.1.31.  
**Scope:** Investigates a vessel stranded from April 5 until April 9 before receiving a tow, using the current `fishing_sim/core/game.py` implementation.

## What the code shows

### Confirmed cause 1 — offshore response chance could be as low as 0.4%

In v13.1.30, tow requests did persist, but a tow reply beyond the nominal 9,000-unit range used a lower bound of `0.004` (0.4%). A persistent retry loop does not guarantee a prompt response: repeated rolls at that low probability can plausibly take multiple in-game days. This is the most direct explanation for a request that remained active and eventually succeeded on April 9.

In v13.1.31, long-range tow chance has a **4% minimum** and grows with each failed transmission up to a cap. Distance, radio clarity, and weather interference continue to affect the probability; repeated failures now meaningfully raise the chance of reaching a listener.

### Confirmed cause 2 — the adrift predicate did not include all engine failures

The old predicate required `not self._engine_on or self.fuel <= 0.0`. That missed a vessel whose engine was unavailable because `engine_ok` or effective `engine_power` had failed while the ignition flag was still on and fuel remained in the tank. v13.1.31 now treats a failed engine or effectively zero power as no propulsion.

### The supplied current / speed hypothesis — partly ruled out by this code

The suggested diagnosis said current-generated speed over ground may keep the adrift timer from accumulating. In the inspected code, `World.speed` is the propulsion/inertia speed through the water; current, wind leeway, and prop-walk are applied separately to `ship_pos`. Therefore, current drift itself does **not** raise `World.speed` and is not the direct cause of this predicate failing in this version.

To make that distinction explicit, v13.1.31 exposes `World.speed_through_water` and feeds that named value into the adrift check. It also adds engine-health/power-state checks and an optional F12 trace that prints both through-water speed and sampled ground displacement (`sog`).

### Other checks

- The timer threshold is `DAY_LEN * 6 / 24`; `DAY_LEN = 600`, so the threshold is 150 simulation seconds (six in-game hours), not 21,600 simulation seconds.
- A deliberate anchor suppresses the adrift-only timer, but it does not suppress the separate low-fuel trigger. The tow launch clears the anchor.
- Tow transit does not use a `1,852` conversion. It advances both `ship_pos` and `believed_pos` by `tow_speed * dt`, then snaps only the final 18 world units into the berth.
- A manual F4 request remains latched and retries independently of whether fuel is empty.

## Implemented behavior in v13.1.31

- Persistent F4/automatic tow requests remain active until tow arrival or docking.
- Automatic requests start at 5% tank capacity, or after six in-game hours with no propulsion and less than the minimum useful speed through water.
- “No propulsion” includes ignition off, failed engine health, effective engine power at or below 0.01, or an empty tank. A ship being pushed by current/wind can still be adrift.
- Repeated unanswered long-range calls escalate the probability of a response: a 4% floor, attempt-based response pressure, and a 25% cap. Normal close-range reception remains governed by clarity, range, and weather.
- `F12` toggles one line per simulation second in the launch console:

  `date clock fuel stw sog adrift drift_t anchor tow failed_calls`

  `stw` is the speed-through-water value used by the trigger. `sog` is sampled movement across the world, including drift. This makes it possible to confirm that a drifting hull with no propulsion still accumulates the timer.
- Tow success clears the failure count, retry timer, and adrift timer. Physical towing still advances the true and believed positions together.

## F12 diagnostic reading guide

| What you see | Meaning |
|---|---|
| `sog` is high, `stw` is below 8, engine has no propulsion, `adrift=True` | Current/wind are moving the hull, but the timer should accumulate correctly. |
| `adrift=False` while speed is low | Check `anchor`, engine availability/power, fuel, or whether the ship is docked/under tow. |
| `drift_t` reaches `150.0` but `tow= NORMAL` | The automatic transition is blocked; capture the surrounding console lines for diagnosis. |
| `tow=REQUESTED`, `failed_calls` rises | Trigger worked; radio reception is the remaining wait. The chance now escalates per failed call. |
| `tow=UNDER_TOW` | Tug accepted and is moving the vessel; verify `sog` and distance to harbour fall. |

## Regression coverage

The v13.1.31 tests cover the pure adrift rule, engine faults with fuel remaining, anchor/dock/tow exclusions, escalating and bounded long-range probability, F12 diagnostics wiring, persistent retries, continuous tow movement, and the presence of the radio/distress design guide.

A graphical Pygame playtest remains necessary. In particular, use F12 during an engine failure/offshore wait to confirm the real runtime state and console trace.

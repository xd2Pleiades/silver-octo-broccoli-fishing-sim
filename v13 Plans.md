```markdown
# World Navigation & Fishing Awareness

Two coupled systems that turn the current "steer to the fishing grounds and set" into a real search, with the ship's navigation quality determining how well you find fish.

Reference: `fishing_sim_11.py`. Layers are independent; each can ship without the others.

---

## Overview

| Part | System | Purpose |
|---|---|---|
| **A** | Navigation | Dead reckoning with crew-weighted error, a full-screen chart, four fixes, voice reports |
| **B** | Fishing | Hotspots, cues, crew detection, gut icons, follow birds |
| **C** | Integration | Why the two systems depend on each other |
| **D** | Implementation | Layer order, cost, risks |
| **E** | Tuning | Both systems' knobs in one place |

The two systems share one interface: `believed_pos`. Navigation moves it (with drift); fishing reads it (to place hotspots on the chart). When nav is wrong, the fishing becomes worse — not because of a rule but because the player literally cannot see where the fish are.

---

# Part A — Navigation, Dead Reckoning, and the Chart

## A1. Design philosophy

The player is a 1962 captain. They trust their navigator, or they verify. Navigation is not a HUD element — it is a **state of the crew's belief about where the ship is**, maintained by dead reckoning and corrected only by physical fixes. When the belief is wrong, the chart is wrong, and every decision made from the chart inherits the error.

Two consequences shape the whole design:

- **Truth never leaks.** The player never sees `ship_pos` directly. They see `believed_pos` — the crew's best estimate. If the navigator is bad, the player sees a wrong chart and can't tell.
- **Error is visible by contradiction, not by magnitude.** A wrong bearing and a wrong position together produce an inconsistent chart: the fix line doesn't meet the landmark, the sounder disagrees with the chart. The player learns to read *contradictions*, not numbers.

## A2. Dead reckoning model

Two positions coexist:

```python
# World state
self.ship_pos     = V(350, -120) * self.scale   # TRUE position (physics)
self.believed_pos = V(self.ship_pos)            # crew's DR estimate
self.believed_heading = 0.0                     # crew's perceived heading
self.last_fix     = 0.0                         # time since last fix
self.position_error = V(0, 0)                   # believed - true
self.compass_bias = 0.0                         # slow-walk compass error (rad)
self.log_bias     = 0.0                         # slow-walk speed error (fraction)
```

Each frame, truth moves by the physics in `World.update`. Belief moves by the crew's plot:

```python
def _update_dr(self, dt):
    # Compass error: ±2° for magnetic; the game has no gyro on a 1962 boat.
    # Error is a slow random walk around zero — a compass that's consistently 2° off
    # is a compass that was never swung, and a good navigator would have caught that.
    self.compass_bias += random.gauss(0, 0.005) * dt    # rad^2/s
    self.compass_bias *= math.exp(-0.02 * dt)           # regression toward zero

    # Log error: ±2% of indicated speed
    self.log_bias += random.gauss(0, 0.0005) * dt
    self.log_bias *= math.exp(-0.02 * dt)

    # The crew plot using believed heading and believed speed:
    bh = self.heading + self.compass_bias
    bs = self.speed * (1.0 + self.log_bias)
    self.believed_pos += V(1, 0).rotate_rad(bh) * bs * dt

    # Truth has moved by the physics step (already done by World.update)

    # The position error is simply the difference:
    self.position_error = self.believed_pos - self.ship_pos
```

Over a straight run, the errors accumulate at roughly `|compass_bias| * speed * dt` perpendicular to track and `|log_bias| * speed * dt` along track. With `compass_bias ≈ 2°` and `log_bias ≈ 2%` on a 9-knot cruise, that's ~10–20 design units per minute in fair weather.

**Weather and skill multiply this.** A bad watchkeeper (deckhand at the helm) has 5× the compass bias of the captain. Fog and night extend the intervals between fixes, which is when error grows fastest.

## A3. Error growth rates

Target: in fair weather with a good navigator, DR error grows at ~10 units/min. In fog with a green watchkeeper, ~50 units/min.

```python
def dr_error_rate(self):
    # Base rate 10 units/min in fair weather with a good navigator
    base = 10.0 / 60.0  # units/sec

    # Whoever's on watch determines the accuracy
    watch = self.g.helmsman()          # the sailor at the wheel, or None
    if watch is None:
        skill = 0.15                    # green hand or nobody
    else:
        skill = watch.skill

    # Low-skill: up to 5x error rate
    skill_factor = 2.0 - skill

    # Sea state and night extend the error
    sea_factor = 1.0 + self.g.world.sea_state
    night_factor = 2.0 if self.g.world.daylight() < 0.3 else 1.0
    weather_factor = 1.0 + 2.0 * self.g.weather.fog + 0.5 * self.g.weather.rain

    return base * skill_factor * sea_factor * night_factor * weather_factor
```

Expected values:

| Condition | Watchkeeper | Rate (units/min) | After 2h |
|---|---|---|---|
| Clear, calm | Captain (0.7) | 13 | 1560 |
| Clear, moderate sea | Captain | 19 | 2280 |
| Fog, calm | Captain | 26 | 3120 |
| Fog, moderate | Deckhand (0.2) | 90 | 10,800 |
| Storm | Deckhand | 90+ | 10,800+ |

For reference: the ship is 1100 units long; a hotspot radius is 1200–2200 units. After 2 hours in fog with a bad watch, you're well outside hotspot accuracy. In clear weather with the captain watching, you're inside.

## A4. The chart — full-screen navigation

**Access.** Click the minimap. Full-screen chart overlays the deck view. ESC or right-click closes.

**Layout.** Chart occupies ~80% of the screen. Right column is an information panel (see A5). Bottom strip has fix options.

**What it draws.**

- **Coastline and land** at true positions (the crew knows these from charts). Sepia-tinted.
- **Landmarks** at true positions, with icons and names: the lighthouse, the temple peak, the reef, the harbour mouth. Fix sources.
- **Charted soundings** — small numbers scattered across the water ("47", "92", "113"), representing the survey depth at those points. Faint grey.
- **The ship icon** at the chart's centre — this is `believed_pos`, not truth. A small yellow arrow with an **error circle** around it whose radius equals `|position_error|`.
- **The course line** from current position toward the current destination.
- **Waypoints** as numbered dots.
- **Hotspots** (Part B) at their believed positions.
- **The compass rose** at the bottom-right, with the ship's heading and the course marked.

**Fog of war.** The chart's *known* extent is the mapped area — home harbour plus a 3000-unit radius offshore. Beyond that, the chart shows "UNCHARTED" and rough surveyor's notes (dashed lines, "unsurveyed", a scalloped edge). Sailing into new water expands the known area (if a navigator is logging).

## A5. Course plotting and waypoints

**In chart mode:**

- **Left-click open water** — add a waypoint.
- **Left-click existing waypoint** — pick it up; drop it somewhere else.
- **Right-click a waypoint** — delete it.
- **Shift + left-click a leg** — insert a waypoint in the middle.
- **Left-click the last leg's end** — extend the course.
- **Escape** — clear the entire course.
- **Enter** — commit and close.

The autopilot steers through the waypoints in order, dropping each one as it is reached. If the crew are fishing on autopilot (`L`), the auto-fish overrides a manual course (see B9).

**Right column (info panel):**

```
POSITION
  Believed: 42°14.3' N, 141°09.8' E
  Doubt:    ± 340 units (≈ 1.8 nm)
  Last fix: 2 h 14 m ago (DR)

COURSE
  Waypoints: 3
  Leg 1: 5.2 nm at 090°
  Leg 2: 1.8 nm at 045°
  Leg 3: 7.0 nm at 120°
  ETA: ~1 h 32 m at cruise

CONDITIONS
  Visibility: 6.2 km
  Sea state: 0.42
  Watch:      Takeda (skill 0.8)

FIXES AVAILABLE
  [F5] Sextant       (clear sky — dawn/dusk)   acc ±140
  [F6] RDF beacon    (range 3200 units)       acc ±180
  [F7] Landmark      (lighthouse in sight)    acc ± 80
  [F8] Echo sounder  (depth 47, charted 51)   acc ±320
```

The **Doubt** figure is `|position_error|` — how far the believed position might be from truth. It grows visibly as the chart is open (well, as time passes; the fix lines update).

## A6. Fixes — how to reset the error

Four sources, each with different conditions and accuracy.

### A6.1 Landmark bearing fix

The most accurate, the most situational. The crew needs a named landmark in sight and a sailor on deck to take a bearing.

```python
def fix_landmark(self, landmark):
    fixer = self.g.best_watchkeeper()      # highest-skill aboard sailor
    if fixer is None or fixer.mode != Sailor.ABOARD:
        return "no_one"
    # Landmark must be within visibility
    d = self.g.world.ship_pos.distance_to(landmark.pos) / self.g.world.scale
    if d > 3000 * self.g.weather.visibility_km() / 10.0:
        return "not_visible"
    # Accuracy: fixer's bearing-taking skill
    bearing_error = 0.02 * (1.0 - fixer.skill) * (1.0 + self.g.world.sea_state)
    pos_error = bearing_error * d * 1000.0
    self.position_error = V(
        random.gauss(0, pos_error),
        random.gauss(0, pos_error)
    )
    self.believed_pos = self.ship_pos + self.position_error
    self.last_fix = self.g.world.time
    return "ok", pos_error
```

A captain (0.7) in calm weather taking a bearing on a landmark 2000 units away: bearing_error ≈ 0.006 rad ≈ 0.34°, position_error ≈ 13 units. Excellent.
A deckhand (0.2) in moderate sea: bearing_error ≈ 0.02 rad ≈ 1.1°, position_error ≈ 23 units. Good — still a useful fix.

Landmark fixes are the tightest because a bearing is a precise physical measurement.

### A6.2 Sextant fix

Only available at dawn, dusk, or clear noon. Requires clear sky.

```python
def fix_sextant(self):
    if self.g.weather.cloud > 0.7:
        return "overcast"
    hour = self.g.world.hour()
    if not (5.0 < hour < 7.0 or 11.0 < hour < 13.0 or 17.0 < hour < 19.0):
        return "no_sun"
    fixer = self.g.best_watchkeeper()
    if fixer is None or fixer.skill < 0.4:
        return "unskilled"
    pos_error = 200.0 * (1.0 - fixer.skill) / 0.7
    self.position_error = V(random.gauss(0, pos_error), random.gauss(0, pos_error))
    self.believed_pos = self.ship_pos + self.position_error
    self.last_fix = self.g.world.time
    return "ok", pos_error
```

A sextant fix is a mid-quality fix: less precise than a nearby landmark, more reliable than nothing.

### A6.3 RDF — radio direction finding

Requires the radio to be working, a sailor at the radio set, and being within the coast station's range.

```python
def fix_rdf(self):
    if not self.radio_station_ok():
        return "no_operator"
    op = self.g.radio_operator()
    if op.skill < 0.4:
        return "unskilled"
    distance = self.g.world.dist() * self.g.world.scale
    if distance > 3200.0:
        return "out_of_range"
    bearing_error = 0.05 * (1.0 - op.skill) * (1.0 + distance / 3200.0)
    pos_error = bearing_error * distance
    along = V(1, 0).rotate_rad(self.bearing_to_coast_station() + math.pi / 2)
    perp = V(1, 0).rotate_rad(self.bearing_to_coast_station())
    self.position_error = (
        along * random.gauss(0, pos_error * 3.0) +
        perp * random.gauss(0, pos_error * 0.3)
    )
    self.believed_pos = self.ship_pos + self.position_error
    self.last_fix = self.g.world.time
    return "ok", pos_error
```

RDF is less accurate than a landmark but works at longer range and in fog. The bearing-line error shape is realistic — you know you're *north* of the station, but not *how far* north.

### A6.4 Echo sounder fix

The subtle one. The sounder reads the true depth under the ship. The chart shows a depth at the *believed* position. If they match, you're probably where you think you are.

```python
def fix_sounder(self):
    sounded = self.g.world.bottom_m(self.g.world.ship_pos.distance_to(HARBOUR) / self.g.world.scale)
    charted = self.g.world.charted_depth_at(self.believed_pos)
    if abs(sounded - charted) < 4.0:
        self.position_error = V(0, 0)
        self.believed_pos = V(self.ship_pos)
        self.last_fix = self.g.world.time
        return "ok"
    return "mismatch"
```

The sounder doesn't tell you *where* you are — it tells you *whether your belief matches reality*. If the depths disagree, the sounder reports the disagreement, and the player knows their position is wrong but not how to fix it. They must use a landmark or sextant.

This is why the sounder is the interesting one: it's a *check*, not a *fix*, but in game design terms it's still a "fix" because it can zero the error when conditions allow.

**charted_depth_at** — needs a smooth charted field. Reuse `bottom_m(d)` at the believed position plus survey noise:

```python
def charted_depth_at(self, pos):
    base = self.bottom_m(pos.distance_to(HARBOUR) / self.scale)
    r = random.Random(int(pos.x // 100) * 73856093 ^ int(pos.y // 100) * 19349663)
    return base * r.uniform(0.93, 1.07)
```

## A7. Crew reports with error

Every bearing, distance, speed, and depth report from a sailor is skill-weighted. The player sees the *reported* number, not the truth. A sailor isn't lying — he's doing his best, and his best is as good as his skill.

```python
def report_bearing(self, target):
    true = math.atan2(target.y - self.pos.y, target.x - self.pos.x)
    err = random.gauss(0, 0.02 * (1.0 - self.skill))
    return (true + err) % TAU

def report_distance(self, target):
    true = self.pos.distance_to(target) / self.g.world.scale
    err = random.gauss(0, 0.10 * (1.0 - self.skill)) * true
    return true + err

def report_speed(self):
    true = self.g.world.speed / 50.0    # kt
    err = random.gauss(0, 0.2 * (1.0 - self.skill))
    return true + err
```

**Reported values are spoken, not charted.** A bearing call appears as a speech bubble:

> **Takeda:** Lighthouse bears two seven three. Land's about two point eight miles off.

The player can:
- Note the numbers mentally (skill 0.8 → trust)
- Cross-check against the chart's bearing line
- Ask another sailor for a second opinion (see below)

**Second opinion.** If the player clicks a second sailor during the first's report window (say within 5 seconds), the second one reports. Their number will differ — it's a second observation, not a repeat of the first. Two reports on the same target from two sailors, compared, tell the player which is more reliable.

The HUD shows the two reports side-by-side, and a small "discrepancy" note:

> Bearing to lighthouse:
>   Takeda (skill 0.8): 273°
>   Sato (skill 0.2):   267°
>   Chart:              270° — discrepancy noted

If the player is experienced enough to know which sailor's number to trust — that's the game.

## A8. Chart cartography

The chart should *look* like 1962 — hand-drawn, sepia, with soundings and compass roses.

**Palette:**

- Background: `#d8cba8` (aged cream)
- Water: `#b8c8c0` (faded teal)
- Land: `#c8b890` (warm beige)
- Coastline: `#4a3020` (dark brown, 2px)
- Landmarks: `#7a3020` (muted brick)
- Soundings: `#6a6050` (grey-brown, small monospace font)
- Compass rose: `#4a3020` with `#c9a227` accents
- Ship icon: yellow `#f2d04b`, error circle `#f2d04b` at 30% alpha
- Hotspot icon: `#f5e070` (see Part B)
- Course line: `#8a3b2f` (dark red)
- Fix line (from ship to landmark bearing): `#3d6a8a` (steel blue, dashed)

**Chart furniture:**

- **Title block** at bottom-right: *"NORTH PACIFIC — APPROACHES TO [HARBOUR NAME] — 1962 — SOUNDINGS IN FATHOMS — HAND CORRECTED"*.
- **Scale bar** bottom-left: `0───5───10 nm`.
- **Compass rose** at the centre-top of the water area, with the ship's course marked as a red arrow.
- **Soundings** scattered at 200–400 unit intervals on water, faint. Add survey noise.
- **Restricted/danger zones** as dashed scallops — the lighthouse reef, the harbour mouth sandbar.
- **Magnetic variation** noted in a corner: *"VAR 6°E (1962)"* — flavor, but the compass bearing displayed to the player should *not* subtract it; the player sees raw compass, the chart is drawn in true frame. A skilled navigator notes the difference.

## A9. HUD indicators

Two small additions to the existing HUD:

- **Telemetry line**: `DR: ±120u  fix 2h14m`
- Colour-coded: white if `|position_error| < 300`, yellow under 800, red beyond.
- Add a `Fix` reminder if `|position_error| > 1000 and last_fix > 3600`.

Crew comments as the error grows:

- `|position_error| > 500 and time since fix > 1800`: **"Takeda: It's been a while since a fix. Want me to take a bearing?"**
- `|position_error| > 1500`: **"Captain: We're running blind on DR. Get a fix."**
- `|position_error| > 3000`: **"Captain: I don't trust the chart. Bring her round to something solid."**

These are rare enough to feel meaningful, common enough to warn.

## A10. Navigation tuning

| Parameter | Where | Default | Notes |
|---|---|---|---|
| `compass_bias` sigma | `_update_dr` | 0.005 | Slow walk; player can't feel it in a minute |
| `log_bias` sigma | `_update_dr` | 0.0005 | Speed reading error |
| `dr_error_rate base` | `dr_error_rate` | 10/60 = 0.17 u/s | Multiply by `skill_factor * sea * night * weather` |
| `MAX_FIX_ERROR` (landmark) | `fix_landmark` | 60 | Fix precision with a perfect landmark sighting |
| `MAX_FIX_ERROR` (sextant) | `fix_sextant` | 200 | Worse than landmark |
| `MAX_FIX_ERROR` (RDF) | `fix_rdf` | 250 | Longer range, worse precision |
| `sounder_match_tol` | `fix_sounder` | 4.0 | Depth units |
| `charted_depth_noise` | `charted_depth_at` | ±7% | Old surveys |
| `report_bearing_sigma` | `report_bearing` | 0.02 rad * (1-skill) | ±1.1° for a deckhand |

If DR is too aggressive, lengthen the initial fix interval or reduce base rate. If hotspots become too hard to find, either accept the challenge (this is the design) or widen hotspot radius.

---

# Part B — Fishing Spots, Cues, and Crew Intuition

## B1. What a hotspot is

A hotspot is a **world position** where the fishing is better than usual for one specific species, for a limited time. It is not a map marker placed by the designers — it spawns, drifts, and decays on its own, and the player finds it by reading the water.

```python
class Hotspot:
    """A temporary concentration of fish in the world.

    The spot is not visible as such — the player only sees physical cues (birds, tint,
    flotsam) that scatter and fade as the spot weakens. Crew members with enough skill
    also 'feel' it: they will comment, and a small icon will appear once at least one
    of them is sure. The spot dies on its own after a few game minutes.
    """
    def __init__(self, pos, species, strength=1.0, radius=1800.0, life=600.0):
        self.pos = V(pos)
        self.species = species                     # "albacore" / "yellowfin" / "bigeye" / "swordfish" / "mixed"
        self.strength = strength                   # 0..1: how strongly the fish are congregating
        self.strength_now = strength               # decays over life
        self.radius = radius                       # world px; how wide the effect extends
        self.life = life                           # seconds of game time before it dies
        self.age = 0.0
        self.drift = V(1, 0).rotate_rad(random.uniform(0, TAU)) * random.uniform(2.0, 8.0)
        self.phase = random.uniform(0, TAU)        # for the cue animation phase
        self.detected_by = None                    # the first sailor to notice it
        self.detected_at = None
```

**Species affinity.** A spot is not generic. It is:

- `"albacore"`, `"yellowfin"`, `"bigeye"`, `"swordfish"` — the spot concentrates that species specifically.
- `"mixed"` — several species benefit, but by less; more common than a single-species spot.

**Strength and radius determine how much the bite rate goes up.** A strength-1.0 yellowfin spot at radius 1800 means: within 1800 world px of its centre, `bite_weights` for yellowfin is multiplied by ~3× at the centre, falling off smoothly to 1× at the edge. Strength 0.5 means ~2×. A `"mixed"` spot means ~1.4× for all four.

## B2. Where they spawn

Only offshore, in water deep enough to matter:

```python
def _spawn_hotspot(self, dt):
    self.hotspot_cd -= dt
    if self.hotspot_cd > 0:
        return
    self.hotspot_cd = random.uniform(45.0, 90.0)

    for _ in range(8):                             # up to 8 tries
        ang = random.uniform(0, TAU)
        r = random.uniform(4000, 9000) * self.scale
        pos = HARBOUR + V(math.cos(ang), math.sin(ang)) * r
        if in_poly(pos, self.land_w):
            continue
        d = pos.distance_to(HARBOUR) / self.scale
        if d < 1500:
            continue
        species = random.choices(
            ["albacore", "yellowfin", "bigeye", "swordfish", "mixed"],
            weights=[0.30, 0.30, 0.15, 0.10, 0.15],
        )[0]
        strength = random.uniform(0.4, 1.0)
        radius = random.uniform(1200, 2200)
        life = random.uniform(420, 900)            # 7–15 game minutes
        self.hotspots.append(Hotspot(pos, species, strength, radius, life))
        return
```

## B3. Drift and decay

```python
def _update_hotspots(self, dt):
    survivors = []
    for h in self.hotspots:
        h.age += dt
        if h.age >= h.life:
            continue
        h.pos += h.drift * dt
        if h.age > h.life * 0.66:
            t = (h.age - h.life * 0.66) / (h.life * 0.33)
            h.strength_now = h.strength * (1.0 - t)
        else:
            h.strength_now = h.strength
        survivors.append(h)
    self.hotspots = survivors
```

## B4. Bite-weight integration

In `Longline.bite_weights`:

```python
def bite_weights(self, p, hd):
    w = self.g.world
    # ... existing computation for `s` per species ...

    hpos = p["pos"]
    for h in w.hotspots:
        d = hpos.distance_to(h.pos)
        if d >= h.radius:
            continue
        falloff = 1.0 - (d / h.radius) ** 2
        boost = h.strength_now * falloff
        if h.species == name:
            s *= 1.0 + boost * 2.0                 # up to 3x at centre of a strength-1 spot
        elif h.species == "mixed":
            s *= 1.0 + boost * 0.6                 # up to 1.6x
    return out
```

**Important**: the hotspot is a *modifier on top of* depth, temperature, bait, and time of day, not a replacement. A bigeye spot at 90 m with saury still doesn't catch bigeye — they are not there. A bigeye spot at 260 m with squid catches a *lot* of bigeye. The player still has to make the depth and bait decisions; the hotspot multiplies the payoff when they're right.

**A hotspot doesn't need to be set through.** If the player steams over it without setting, nothing happens. The hooks that later land inside the hotspot's world-space circle get the boost; the hooks that land outside do not. A longline set through a hotspot is a *deliberate* act, and the reward is proportional to how many hooks fell in the zone.

## B5. Visible cues

The hotspot is invisible. The player finds it by reading four physical signs.

### B5.1 Birds working

The most important cue. Real tuna fishers use birds more than anything else. A flock of birds working over a spot is the single strongest sign of a baitfish school, which is what the tuna are chasing.

```python
def _draw_hotspot_birds(self, g, ov):
    for h in self.hotspots:
        if h.strength_now < 0.15:
            continue
        n = int(8 + 20 * h.strength_now)
        for i in range(n):
            orbit_r = 40 + 80 * (i % 5) / 5.0
            orbit_a = h.phase * 0.3 + i * 1.7 + g.world.time * (0.6 + 0.1 * (i % 3))
            wp = h.pos + V(math.cos(orbit_a), math.sin(orbit_a)) * orbit_r * self.scale
            sp = g.S(g.deck_of(wp))
            wing = 3 + 2 * math.sin(g.world.time * 12 + i * 2.3)
            pygame.draw.polygon(g.screen, (240, 240, 235),
                [(sp.x - wing, sp.y), (sp.x, sp.y - 3), (sp.x + wing, sp.y)])
            if random.random() < 0.02:
                pygame.draw.line(g.screen, (240, 240, 235),
                    (sp.x, sp.y), (sp.x, sp.y + 8), 1)
```

At a distance, the flock reads as a small cluster of white specks over the water — exactly what a working flock looks like from a boat. The player learns to scan the horizon for that cluster.

**Bird count and orbit radius scale with strength** — a strong spot has a tight, dense flock (40+ birds, radius 30–60); a weak spot has a loose scatter (8 birds, radius 100+).

**The flock disperses as the spot dies**, giving a physical cue that the fish have moved on.

### B5.2 Water colour tint

Real spots often show as a slight colour change — a green tint where cooler water is welling up, or a bluer stain of feeding fish.

```python
def _draw_hotspot_tint(self, g, ov):
    for h in self.hotspots:
        if h.strength_now < 0.2:
            continue
        c = g.S(g.deck_of(h.pos))
        r = h.radius * g.zoom * 0.85
        for k in (0.85, 0.55, 0.30):
            rr = r * k
            alpha = int(22 * h.strength_now * (1 - k))
            col = mix((40, 120, 100), (30, 80, 140), 1 - k)
            pygame.draw.circle(ov, col + (alpha,), c, int(rr))
```

Effect is subtle — a low-alpha green-blue disc — but it gives a *visible* water change that reads at default zoom. Combine with the birds, and the player has two independent signals.

### B5.3 Flotsam

Fish concentrate under rafts of floating weed, debris, or a dead whale. Real tuna fishers look for flotsam on the surface.

```python
def _draw_hotspot_flotsam(self, g, ov):
    for h in self.hotspots:
        if h.strength_now < 0.3:
            continue
        for i in range(int(4 + 6 * h.strength_now)):
            wa = h.phase * 0.7 + i * 2.1
            wr = 100 + 200 * (i % 3) / 3.0
            wp = h.pos + V(math.cos(wa), math.sin(wa)) * wr * self.scale
            sp = g.S(g.deck_of(wp))
            s = 2 + 3 * h.strength_now
            pygame.draw.polygon(ov, (120, 100, 70, 200),
                [(sp.x, sp.y - s), (sp.x + s, sp.y), (sp.x, sp.y + s * 0.6), (sp.x - s, sp.y + s * 0.2)])
```

Small brown polygons — a scattering of floating wood and weed at the surface. Cheap to draw, reads instantly.

### B5.4 Ripples and surface activity

The surface above a school is never glassy. Small concentric rings scattered across the spot indicate fish near the surface.

```python
def _draw_hotspot_ripples(self, g, ov):
    for h in self.hotspots:
        if h.strength_now < 0.2:
            continue
        for i in range(int(3 + 8 * h.strength_now)):
            seed = (h.phase * 13 + i * 71) % 1000
            r_frac = (g.world.time * 0.8 + seed) % 1.0
            wa = h.phase + i * 1.9 + seed
            wr = h.radius * 0.7 * (r_frac ** 0.5)
            wp = h.pos + V(math.cos(wa), math.sin(wa)) * wr
            sp = g.S(g.deck_of(wp))
            r = 4 + 10 * r_frac
            a = int(120 * (1 - r_frac) * h.strength_now)
            pygame.draw.circle(ov, (200, 230, 240, a), sp, int(r), 1)
```

Rings expand and fade — the visual language of fish rising to the surface. Fires more often on stronger spots.

## B6. Crew detection

The visible cues are **always present** — the player can spot a hotspot purely by eye, without any HUD assistance. The **crew detect it too**, and their detection is what produces a gut icon and a comment.

A sailor notices a spot if:

- They are on deck (`mode == ABOARD`, `level == MAIN`).
- They are **facing** the spot (within ±90° of their `facing`).
- The spot is within their **detection range**, which is skill-dependent.

```python
def detect_range(self):
    vis = self.g.weather.visibility_km() / 10.0     # 1.0 in clear, down to ~0.05 in fog
    night = 0.4 if self.g.world.daylight() < 0.3 else 1.0
    return self.skill * 2500.0 * self.scale * vis * night
```

- Captain (skill 0.7): ~1750 world units in clear daylight
- Veteran (skill 0.8): ~2000 world units
- Deckhand (skill 0.1–0.3): ~250–750 units
- A deckhand who has been mentored up to skill 0.55: ~1375 units

At 2.2 × 0.6 zoom, 1750 world units is roughly half the screen width. So a captain at the bow can spot a spot the deckhand at the stern misses — exactly the effect we want.

**Fog and night shrink this aggressively.** A veteran in fog at night still sees what a deckhand in clear daylight misses. That is the mechanic that makes experience matter.

### B6.1 Per-sailor gut state

```python
# In Sailor
self.gut_spot = None                # the hotspot he's currently aware of
self.gut_confidence = 0.0           # 0..1: how sure he is (builds up over time)
self.gut_last_comment = -99.0       # cooldown on speech

def _update_gut(self, dt):
    if self.mode != self.ABOARD or self.level != Level.MAIN:
        self.gut_spot = None
        self.gut_confidence = 0.0
        return
    w = self.g.world
    best = None
    for h in w.hotspots:
        d = self.pos.distance_to(h.pos) * (1.0 / w.scale)
        if d > self.detect_range():
            continue
        to = h.pos - w.world_of(self.pos)
        if to.length() > 1 and to.normalize().dot(V(1, 0).rotate_rad(self.facing)) < 0.2:
            continue
        if best is None or h.strength_now > best.strength_now:
            best = h
    if best is None:
        self.gut_spot = None
        self.gut_confidence = max(0.0, self.gut_confidence - dt * 0.3)
    elif best is not self.gut_spot:
        self.gut_spot = best
        self.gut_confidence = 0.0
        best.detected_by = best.detected_by or self
        best.detected_at = best.detected_at or w.time
        if w.time - self.gut_last_comment > 20 and best.strength_now > 0.3:
            self.gut_last_comment = w.time
            self._gut_comment(best)
    else:
        self.gut_confidence = min(1.0, self.gut_confidence + dt / 3.0)
```

## B7. Gut comments

Different skills see different things:

```python
def _gut_comment(self, h):
    lower = h.species.replace("_", " ")
    if self.skill < 0.35:
        # A green hand just sees "birds"
        self.g.crew.say("%s: Birds working over there." % self.name)
    elif self.skill < 0.65:
        # A trained hand names what he thinks it is
        self.g.crew.say("%s: Looks like %s under those birds." % (self.name, lower))
    else:
        # A veteran says the fishing decision directly
        if h.species == "mixed":
            self.g.crew.say("%s: Mixed feed under the flock. Could be worth a set." % self.name)
        else:
            self.g.crew.say("%s: %s on the birds. Line's going in here." % (self.name, lower.title()))
```

The captain is spoken to as "Captain:" by the crew, but his own gut comment is in his own voice — the crew bubble speaker handles that automatically.

## B8. The gut icon

Once **at least one sailor has confidence ≥ 0.5**, the spot shows on the water as a small marker. It's not a fish silhouette or an exclamation — it's a small compass/needle icon that gently pulses, telling you "someone on the crew is sure there's fish here."

```python
def _draw_gut_markers(self, g):
    for h in g.world.hotspots:
        confidence = max((s.gut_confidence for s in g.sailors
                          if s.gut_spot is h and s.mode == Sailor.ABOARD and s.level == Level.MAIN),
                         default=0.0)
        if confidence < 0.5:
            continue
        c = g.S(g.world.deck_of(h.pos))
        m = 60
        on_screen = m < c[0] < g.W - m and m < c[1] < g.H - m
        if on_screen:
            pulse = 0.7 + 0.3 * math.sin(g.world.time * 2.5 + h.phase)
            size = int((10 + 4 * pulse) * g.zoom * 2)
            alpha = int(200 * confidence * pulse)
            pts = [(c[0], c[1] - size), (c[0] + size, c[1]),
                   (c[0], c[1] + size), (c[0] - size, c[1])]
            pygame.draw.polygon(g.ov_d, (255, 240, 150, alpha), pts, 2)
            pygame.draw.circle(g.ov_d, (255, 240, 150, alpha), c, max(2, size // 3), 1)
        else:
            d = V(c) - g.CENTER
            half = g.CENTER - V(m, m)
            k = min(half.x / max(abs(d.x), 1e-3), half.y / max(abs(d.y), 1e-3))
            pos = g.CENTER + d * k
            a = math.atan2(d.y, d.x)
            size = int(14 * g.zoom * 2)
            pygame.draw.polygon(g.ov_d, (255, 240, 150, 220),
                [pos + V(size, 0).rotate_rad(a),
                 pos + V(size * 0.7, 0).rotate_rad(a + 2.5),
                 pos + V(size * 0.7, 0).rotate_rad(a - 2.5)])
            pygame.draw.circle(g.ov_d, (255, 240, 150, 180), pos, max(2, size // 4), 1)
```

The icon is **a small pale-yellow diamond** — deliberately not a fish silhouette, not a target reticle. It says "someone has an intuition here" rather than "there is a fish here."

**Confidence-gated.** A deckhand who half-notices something shows a faint icon (confidence 0.5). A veteran who's been watching the birds build for 20 seconds shows a bright one (confidence 1.0). The player learns to trust the veteran's icon more than the deckhand's.

**Fades on detection loss.** When the sailor loses sight of the spot (fog, distance, time decay), `gut_confidence` drops and the icon fades.

**Off-screen arrow** if the spot is beyond the screen edge, so the player doesn't miss it while looking elsewhere.

**One icon per spot, not per sailor.** `_draw_gut_markers` iterates hotspots and picks the max confidence across all sailors, so two sailors looking at the same flock produce a single icon.

## B9. Auto-fish interaction

When crew fishing is on (`self.line.auto == True`):

```python
# In Longline._auto(dt), before the "travel" branch decision:
if self.stage == "travel":
    spotted = None
    for s in g.sailors:
        if s.gut_spot is not None and s.gut_confidence > 0.7:
            spotted = s.gut_spot
            break
    if spotted and spotted.strength_now > 0.4:
        w.set_destination(spotted.pos)
```

The auto-fish takes the ship to the spot it has detected, not just to the general fishing grounds. When you leave the crew to fish, they **hunt** — using the veteran's eyes — and the player can watch them steer toward a bird flock. If no one has detected anything, they head to the general grounds as they do now.

## B10. Follow birds (ambience)

Separate system. Birds trail the ship continuously, drawn from a chum wake, and their density and closeness reflect the ship's activity. This is atmosphere and information — birds close astern means the ship is feeding them, which means the crew is fishing, which means the player sees the work is happening.

```python
class FollowBird:
    def __init__(self, pos):
        self.pos = V(pos)
        self.vel = V(random.uniform(-15, 15), random.uniform(-15, 15))
        self.flutter = random.uniform(0, TAU)
        self.z = random.uniform(60, 240)
        self.dive_t = 0.0

# On World
self.follow_birds = []
```

### Spawning and drift

```python
def _update_follow_birds(self, dt):
    g = self.g
    if g.weather.storm > 0.6:
        target = 0
    elif g.line.phase == Longline.HAULING:
        target = 14
    elif g.line.phase == Longline.SETTING:
        target = 8
    elif g.line.phase == Longline.SOAKING:
        target = 4
    else:
        target = 2

    if self.daylight() < 0.25:                # birds roost at night
        target = 0

    while len(self.follow_birds) < target:
        stern = g.world.world_of(V(-g.ship.length * 0.55, random.uniform(-200, 200)))
        self.follow_birds.append(FollowBird(stern))

    while len(self.follow_birds) > target:
        self.follow_birds.pop()

    for b in self.follow_birds:
        anchor = g.world.world_of(V(-g.ship.length * 0.6, random.uniform(-150, 150)))
        to = anchor - b.pos
        if to.length() > 10:
            b.vel += to.normalize() * 30.0 * dt
        b.vel *= math.exp(-0.5 * dt)
        b.pos += b.vel * dt
        b.flutter += dt * 8.0
```

### Drawing

```python
def _draw_follow_birds(self, g):
    for b in self.follow_birds:
        sp = g.S(g.deck_of(b.pos))
        size = (14.0 - b.z / 30.0) * g.zoom * 0.8
        flap = 1.0 if math.sin(b.flutter) > 0 else 0.6
        w = size * flap
        pygame.draw.line(g.screen, (30, 30, 30),
                         (sp.x - w, sp.y - w * 0.5), (sp.x, sp.y), max(1, int(2 * g.zoom)))
        pygame.draw.line(g.screen, (30, 30, 30),
                         (sp.x, sp.y), (sp.x + w, sp.y - w * 0.5), max(1, int(2 * g.zoom)))
        if random.random() < 0.005:
            pygame.draw.line(g.screen, (30, 30, 30),
                             sp, (sp.x, sp.y + size * 2), 1)
```

The visual is a V shape — two lines meeting at a point — that flaps. Dark against the sky. Small enough that a few of them at a distance reads as gulls, not detail.

**Behaviour.** Birds drift toward the ship's stern where the chum is. If the ship steams away, they lose ground, then new birds spawn at the new stern. This naturally produces a flock that trails the boat.

**Storm:** fade out. **Night:** fade out. Gulls roost.

**Setting:** birds gather at the stern while line is being laid. **Hauling:** birds dive occasionally — reuse `g.splats` or add a small foam ring.

**Independent of hotspots.** A ship inside a hotspot has *both* follow-birds (trailing the stern) and working-birds (over the spot, in front). The two are visually distinct.

---

# Part C — How the Two Systems Interact

## C1. Bad nav = you miss the fish

The core coupling. **Hotspots are drawn on the chart at their believed positions, not their true positions.**

Why? Because the crew sight a hotspot from `believed_pos` (they don't know any better). Their sighting gives bearing and distance to the birds, and they plot from their believed position. If their belief is wrong by 500 units east, the hotspot is plotted 500 units east of where it really is.

The player clicks the hotspot pixel on the chart. The destination is `Hs + position_error` — off from the true hotspot by exactly the position error.

If `position_error > hotspot.radius`, you miss entirely. If it's 50% of radius, you get a partial bonus. If you've just taken a fix, you hit it dead centre.

**Landmarks, by contrast, are drawn at true positions** — the crew knows them from charts. Clicking a landmark always lands you at the landmark. This asymmetry is the design: good nav = you find fish; bad nav = you steam into empty water and don't understand why.

## C2. The full loop

1. Crewman spots birds. **"Yellowfin on the birds. Line's going in here."**
2. Gut icon appears on the chart at the *believed* position of the spot.
3. Player takes a bearing on the lighthouse to fix position first. *("We're not on the spot yet — get a fix.")*
4. Position error collapses. Chart updates. The gut icon shifts to its true position — the discrepancy the player just saw is the nav error they just fixed.
5. Player clicks the gut icon. Ship steers there.
6. Sets the line at ~90 m with saury. `bite_weights` boosted 3× for yellowfin.
7. Catch comes in thick.
8. Sell. Loop.

Without step 3, step 5 lands you 500 units from the true spot; you catch less; you might notice the discrepancy (the gut icon doesn't match the *observed* birds on screen — the birds are visibly 500 units west of the icon). That's the cue to take a fix.

## C3. Compounding crew skill

The same sailor's skill affects:

- **Fishing** — `Longline.power()` uses skill for haul rate
- **Engineer** — `update_engine_room` uses skill for check intervals
- **Navigation** — `dr_error_rate` uses skill for error growth
- **Watchkeeping** — `detect_range` uses skill for how far away he can spot birds
- **Bearing accuracy** — `report_bearing` uses skill for how close his number is

A veteran who can nail a hauling manoeuvre in a fight and can spot birds 2000 units out and can take a bearing accurate to 1° is *the* most valuable crewman on the boat. The player who keeps Takeda out of the wheelhouse and onto the deck where his eyes matter, and keeps the captain at the chart to take fixes, is playing the game correctly.

A captain who leaves the helm for the radio (as happens in the current game when F2/F3/F4 are pressed with a radio duty set) is a captain not taking fixes. The deckhand takes the wheel. The chart drifts. That's a cost — a real, visible, in-game cost — of every radio call you make.

This is the design: **crew skill is one attribute that touches every system**, and every system asks the player to make a scheduling choice.

---

# Part D — Implementation Plan

## D1. Layer order

Ten independent layers, each shippable. Nav layers (D1.1–D1.6) and fishing layers (D1.7–D1.10) can interleave.

### D1.1 Hotspots (bite-weight integration)
- `Hotspot` class, `World.hotspots`, `_spawn_hotspot`, `_update_hotspots`, `bite_weights` integration.
- **Test:** set a line through a hotspot; observe 3× more bites.
- Cost: ~60 lines. No new drawing. **Gameplay changes immediately.**

### D1.2 Chart cartography (static)
- `Game.draw_chart()` — full-screen sepia chart with coastline, landmarks, soundings, compass rose, scale bar. No interaction yet.
- Triggered by `Tab` (rebind sailor cycle).
- Cost: ~120 lines. Big visual impact.

### D1.3 Hotspot cues on the water
- Bird flocks, water tint, flotsam, ripples drawn in `World.draw`.
- Cost: ~80 lines. Highly readable — you can find spots by eye.

### D1.4 DR model
- `believed_pos`, `position_error`, `compass_bias`, `log_bias`, `_update_dr`, `dr_error_rate`.
- Chart/minimap centre on `believed_pos`. Ship icon shows uncertainty circle.
- Cost: ~50 lines. **Medium risk** — see D3.

### D1.5 Chart interaction
- Waypoints, course lines, fix options panel.
- Cost: ~150 lines. Big UI, straightforward.

### D1.6 Fixes
- `fix_landmark`, `fix_sextant`, `fix_rdf`, `fix_sounder`. Panel shows available fixes with accuracy estimates.
- Cost: ~100 lines. Small but high-impact — the mechanic that lets the player recover.

### D1.7 Crew reports with error
- `report_bearing`, `report_distance`, `report_speed`. Speech bubbles show skill-weighted numbers. Second-opinion windows.
- Cost: ~50 lines. Fills the world with voices.

### D1.8 Crew detection and gut icon
- `gut_spot`, `gut_confidence`, `_update_gut`, `_gut_comment`. Diamond icon on chart and minimap.
- Cost: ~100 lines. Closes the loop between crew skill and hotspot discovery.

### D1.9 Follow birds (ambience)
- `FollowBird`, `_update_follow_birds`, `_draw_follow_birds`.
- Cost: ~60 lines. Atmospheric only.

### D1.10 Fishing-log gut book (optional)
- A "log" UI listing spots the crew have detected, with timestamps, species guesses, and position. A fishing diary.
- Crew could remember spots they've set through before and steer back if a spot forms nearby later.
- Cost: UI + per-sailor memory. Long-term; probably Phase 7+.

## D2. Cost estimate

| Layer | Lines | Session risk |
|---|---|---|
| D1.1 Hotspots | 60 | Low — self-contained |
| D1.2 Chart preview | 120 | Low — new draw code |
| D1.3 Cues | 80 | Low — draw only |
| D1.4 DR model | 50 | **Medium** — touches ship position everywhere |
| D1.5 Chart interaction | 150 | Medium — new mouse event handling |
| D1.6 Fixes | 100 | Low — clear interface |
| D1.7 Reports | 50 | Low — voice only |
| D1.8 Gut icon | 100 | Low — draw + one AI branch |
| D1.9 Follow birds | 60 | Very low — pure ambience |
| **Total** | **770** | |

Roughly 3–4 focused sessions if D1.4 (DR model) is approached carefully and D1.5 (chart interaction) is treated as a self-contained UI project.

## D3. Risks

**The DR model touches every read of `ship_pos`.** Almost every system — collision, autopilot, hotspot detection, land avoidance, fishing grounds — uses `ship_pos` as truth. Introducing `believed_pos` as a *separate* state means the developer must audit every read to decide whether it wants truth or belief.

**Rule of thumb:** physics uses truth; UI, chart, and crew decisions use belief.

**Mitigation:** add `believed_pos` as a parallel attribute in D1.4, but do *not* replace any existing `ship_pos` read. Instead, only the chart/minimap draw code uses `believed_pos`. Physics and AI continue to use `ship_pos`. Then, layer by layer, decide which systems should switch. Hotspot detection — the one that matters for gameplay — switches in D1.1.

**Waypoint rendering is verbose.** Thirty waypoints at screen scale are visually crowded. **Fix:** cap waypoints at 8, show numbered dots with the leg lengths, drop oldest when over cap.

**Fixes trivialize navigation if too easy.** A player who presses `F5` every minute never sees error. **Fix:** rate-limit fixes. Sextant only at dawn/dusk/noon. Landmark only when a landmark is in sight. RDF only within range. Sounder only in charted water. Force the player to *plan* their fixes.

**Species guess always exact.** A veteran guessing "yellowfin" is always right. That's OK for now. To add tension later, make the crew's species *call* skill-weighted (40% correct at deckhand, 85% at veteran), but keep the actual spot's species fixed. The player then has to decide: is Takeda's yellowfin call right, or is it really bigeye?

---

# Part E — Tuning

## E1. Navigation knobs

| Parameter | Where | Default | Notes |
|---|---|---|---|
| `compass_bias` sigma | `_update_dr` | 0.005 | Slow walk; player can't feel it in a minute |
| `log_bias` sigma | `_update_dr` | 0.0005 | Speed reading error |
| `dr_error_rate base` | `dr_error_rate` | 10/60 = 0.17 u/s | Multiply by `skill_factor * sea * night * weather` |
| `MAX_FIX_ERROR` (landmark) | `fix_landmark` | 60 | Fix precision with a perfect landmark sighting |
| `MAX_FIX_ERROR` (sextant) | `fix_sextant` | 200 | Worse than landmark |
| `MAX_FIX_ERROR` (RDF) | `fix_rdf` | 250 | Longer range, worse precision |
| `sounder_match_tol` | `fix_sounder` | 4.0 | Depth units |
| `charted_depth_noise` | `charted_depth_at` | ±7% | Old surveys |
| `report_bearing_sigma` | `report_bearing` | 0.02 rad * (1-skill) | ±1.1° for a deckhand |

If DR is too aggressive, lengthen the initial fix interval or reduce base rate.

## E2. Fishing knobs

| Parameter | Where | Default | What it controls |
|---|---|---|---|
| `hotspot_cd` range | `_spawn_hotspot` | 45–90 s | How many spots exist at once |
| `strength` range | `Hotspot` spawn | 0.4–1.0 | How strong any individual spot is |
| `radius` range | `Hotspot` spawn | 1200–2200 | How wide a spot's effect extends |
| `life` range | `Hotspot` spawn | 420–900 s | How long a spot lasts |
| Boosting factor | `bite_weights` | 2.0 | How much the hotspot multiplies the bite |
| `detect_range` | `Sailor` | 2500 * skill | How far crew can spot a spot |
| `confidence rate` | `_update_gut` | 3.0 s to full | How fast a crew member becomes sure |
| Follow bird count | `_update_follow_birds` | 14 max | Ambient flock density |

The default values make hotspots **rare enough to feel special** (one at a time on average) but **strong enough to matter** (3× catch rate). If playtest shows them too weak, raise the boosting factor. If too common, lengthen `hotspot_cd`.

---

# Part F — Failure modes

**Hotspots too strong.** If the boost dominates, the player only sets on hotspots and ignores depth/bait. **Fix:** cap the boost at 2.5× and require bait/depth to be right for the boost to apply (multiply *within* the species' habitat envelope, not in place of it).

**Hotspots too common.** The search feels pointless if there's always one nearby. **Fix:** `hotspot_cd` at 90–150 s, so a full setting trip typically sees 1–2 spots.

**Crew detect everything.** If the veteran's detection range covers the whole screen, the mechanic disappears. **Fix:** cap `detect_range` at 2000 units (about a screen and a half at default zoom) and apply fog/night multipliers aggressively.

**Birds clip into the HUD.** Follow birds trail the stern and might appear behind HUD panels. **Fix:** draw follow birds before `draw_hud()`, which is already the draw order.

**Gut icons stack.** If multiple sailors detect the same spot, don't draw multiple icons. **Fix:** `_draw_gut_markers` iterates hotspots, not sailors.

**Species guesses are wrong.** A veteran guesses "yellowfin" but it's a bigeye spot. **Fix:** the species guess is drawn from the spot's actual species, so it's always right. Later refinement: make the guess probabilistic, skill-weighted. Deckhand 40% correct, veteran 85%.

**Sounder trivialises navigation.** A player who uses the sounder in charted water every few minutes has zero error. **Fix:** sounder only fixes when the depth matches (within `sounder_match_tol`). If the player has drifted, sounder returns "mismatch" and does *not* zero the error — the player is warned but not helped.

**RDF trivialises navigation.** Press F6 every few minutes, never have error. **Fix:** RDF requires a sailor at the radio. Every sailor sent to the radio is a sailor not at the fishing/hauling/reporting stations. Push the *cost* of using fixes, not the *ease*.

---

# Part G — Why this fits the existing game

The longline simulation is already unusually deep — depth/temperature ecology, day-night species migration, bait affinity, seabed shoaling. **What it lacks is a "where" that the player has to actually find.** Right now, all offshore water is roughly equal, and the fishing grounds are a single destination point. The hotspot system gives the world *texture*: some water is much better than other water, and the player reads it from birds and colour, not from a quest marker.

The nav system adds a second texture: **your knowledge of where you are is itself uncertain**, and that uncertainty feeds directly into the fishing. The player is not just searching for the fish — the player is searching for *their own position* so they can search for the fish.

The systems compose cleanly:

- Depth still decides *which* species bite (a yellowfin spot at 260 m is still a bad set).
- Bait still decides which species will be interested.
- Time of day still decides the vertical migration (swordfish still want night, bigeye still want deep).
- Hotspot decides *how many* of the species you've set for.
- Weather still modulates the whole thing.
- Crew skill, already important for hauling and rescue, now also matters for finding.

Nothing is replaced; everything is multiplied. That's the right shape for a fishing sim.

The birds are the visual language. The crew comments are the confirmation. The gut icon is the reward for good watchkeeping. The chart is the confirmation that you're where you think you are. The follow birds are the sense that the sea is alive around the boat. Each layer is small, and together they turn the open ocean into a place with pattern and reward.

---

## Summary

**Two systems, ten layers, one integration:**

**Navigation** — dead reckoning with crew-skill-weighted error, a full-screen chart, four fix sources (landmark, sextant, RDF, sounder), and voice reports with per-sailor accuracy.

**Fishing** — hotspots with visible cues, crew detection, gut icons, and follow birds.

**The coupling** — hotspots are drawn at their *believed* positions, so nav error makes the chart lie about where the fish are. Fixing your position is the act that lets you catch fish.

The player's job, expanded: **read the water, read the crew, read the chart, fix your position, choose your depth and bait, set the line, sell the catch.** That is what a 1962 tuna longliner's day was actually made of.
```

Save as `WORLD_NAVIGATION_AND_FISHING.md`.

**What changed from the merge:** the two source files overlapped heavily — both described the hotspot/fishing system in detail, and File 1's "Prior suggestion" section was effectively a summary of File 2. I've deduplicated those into a single Part B that keeps the fuller implementations from File 2, and moved all the navigation content (which was only in File 1) into Part A. The implementation plan (Part D) is merged: nav layers and fishing layers are now one ordered list of ten, with the cost table updated to match. Failure modes from both files are in Part F, with two additional ones (sounder and RDF trivialisation) that only surfaced when thinking about the two systems together.

**Key architectural warning remains §D3:** `ship_pos` is read everywhere, so introducing `believed_pos` needs a careful audit — physics keeps using truth, but chart and crew use belief. Once you make that distinction cleanly, both systems slot in without fighting each other.
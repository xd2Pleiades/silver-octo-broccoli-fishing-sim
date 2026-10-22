```markdown
# 13.2.1-xx — World Scale, AI Ship Traffic & Ship-to-Ship Radio

**Status:** Plan / Pre-implementation
**Depends on:** v13v1-05 (Ship's Notebook, Radio Log, queued transcripts), v13v1-11 (priority interruption), `radio_chatter.py`
**Supersedes:** the separate `13.2.0-xx` world-scale document (folded in as §§4–10) and incorporates **Amendment A** (player role, corporate/independent split)
**Modules:** `fishing_sim/world/traffic.py`, `fishing_sim/world/chunk_manager.py`, `fishing_sim/world/weather_grid.py`, `fishing_sim/world/persistence.py`, `fishing_sim/systems/ship_radio.py`

---

## 1. Objective

Define the high-seas world and populate it with coarse-tier AI vessels that carry a radio persona whose reported information may diverge from actual state. The player is an **independent longline crew**, and the fleet they meet is split between **independent peers** and **corporate hierarchy**.

Three goals:

1. **A big ocean.** The player operates across the historical 1962 North Pacific fishery, not a diorama.
2. **Social uncertainty.** Reported positions and fishing intel are *claims*, mirroring "truth never leaks."
3. **Performance discipline.** Distant ships cost nothing per frame; chunking applies to entities and state, not to the ocean surface.

---

## 2. Player Role & Social Position

### 2.1 Player vessel

The player operates an **independent longline vessel** out of Hakodate — owner-operator, not under company contract.

This is historically grounded. The 1962 authorization split **702 land-based vessels** into:

| Gear type | Vessels | Notes |
|---|---|---|
| Gillnet | 333 | Mostly mothership catcher-boats; some land-based |
| **Longline** | **369** | Land-based, independent and corporate; sell at auction |

The mothership fleet (11 motherships, 369 catcher-boats) was a **separate, corporate-organized system**. The player is outside it: no mothership quota, no guaranteed buyer, exposed to auction price volatility. This is already partly modelled by the existing market/scarcity system — this document makes the *social* dimension explicit.

### 2.2 Player characteristics

| Trait | Value | Gameplay consequence |
|---|---|---|
| Vessel type | Independent longline | Gear, catch mix, and haul rhythm differ from gillnet catcher-boats |
| Crew size | Small (historically ~8–15 for a longliner of this class) | Fewer hands; hauling is slower; radio operator may be the captain |
| Radio fit | 1W DSB (~27 nm) or SSB (~49 nm) | Contact is local and earned |
| Sales channel | Hakodate auction | Price volatility; storm scarcity premium applies directly |
| Affiliation | None | No mothership protection, no quota transfer, no corporate intel feed |

### 2.3 Social position

An independent longliner occupies a specific **social position**:

- **Peers** — other independent longliners and gillnetters. Informal networks, gossip, mutual aid, shared intel.
- **Corporate catcher-boats** — contract-bound to a mothership or company. Formal, quota-focused, **less free to share grounds intel** (company orders).
- **Motherships** — corporate hierarchy. Structured radio, collection schedules, quota enforcement.
- **Coast Guard / officials** — procedural, truthful, safety-first.
- **Soviet trawlers** — hostile, treaty-line aware.

The player is **outside the corporate structure but dependent on the same auction**. That asymmetry is the core social tension.

---

## 3. Fleet Composition (1962)

| Archetype | Count | Notes |
|---|---|---|
| Corporate catcher (mothership-contracted gillnet) | ~300 | The bulk of the fleet; clustered around 11 motherships |
| Mothership | 11 | Rare, high-value contacts |
| Independent gillnet | ~80 | Coastal and near-box |
| **Independent longline** | **~40** | Player's peers; the social core of the game |
| Corporate longliner | ~15 | Company-owned longliners selling at auction |
| Coast Guard | ~5 | Patrol vessels |
| Soviet trawler | ~10 | Treaty-line encounters |

The independent longline pool (~40) is small enough that the player can **learn names and personalities over a campaign**. This is the point: the player's social world is legible, while the corporate fleet is an anonymous hierarchy.

### 3.1 Naming conventions (historical)

| Archetype | Name pattern | Example |
|---|---|---|
| Independent longliner | Family/small-company name + Maru | `Kita Maru`, `Daiichi Maru` |
| Independent gillnetter | Same | `Sakura Maru` |
| Corporate catcher | Company name + numbered fleet | `Taiyo Maru No. 18`, `Nichiro Maru No. 7` |
| Corporate longliner | Company name + numbered fleet | `Hokoku Maru No. 3` |
| Mothership | Company name + large vessel name | `Taiyo Maru`, `Nichiro Maru` |
| Coast Guard | Patrol vessel name | `Tsugaru`, `Soya` |
| Soviet trawler | Soviet naming | `SRT-XXXX`, `Mayakovsky` |

The **"No. X"** pattern is a reliable in-world signal that a vessel is corporate. Players can learn to read it — a small, historically accurate piece of legibility that rewards attention.

---

## 4. Map Extent

### 4.1 Historical bounds

The 1962 mothership salmon fleet operated within:

- **Longitude:** 160°E – 175°W (25° span)
- **Latitude:** 46°N – 62°N (16° span)
- **Season:** ~May 20 – Aug 10

But the player's home port is **Hakodate (~140.7°E, 41.8°N)**, outside the box. Catcher-boats transited from Hokkaido to the motherships — hundreds of nautical miles. A playable map must include the **transit corridor**, not only the fishing box.

### 4.2 Proposed extent (phased)

| Phase | Extent | Approx. size | Content |
|---|---|---|---|
| **A — Regional** | 138°E–148°E, 40°N–46°N | ~440 × 360 nm | Hakodate, Hokkaido grounds, coastal traffic, first AI ships |
| **B — High seas** | 140°E–175°W, 41°N–62°N | **~1,700 × 1,250 nm** | Full 1962 box, mothership fleet, Soviet encounters, transit corridor |
| **C — Modular east** | +5° longitude tiles | 5° ≈ 190 nm at 50°N | Future expansion toward 175°W and beyond |

**Recommendation:** build the world foundation sized for **Phase B**, but populate and tune **Phase A** first. The full extent is ~2.1 million nm² — sparse water, cheap to represent — but only the regional area needs content in early versions. Phase C is a tiling capability, not a v13.2 deliverable.

### 4.3 Projection

Simulation uses a **local equirectangular plane** centered at (45°N, 160°E):

- `x` = east in nautical miles, `y` = north in nautical miles.
- Conversion from lat/lon at map edges; error < ~0.5% across the full extent.
- This error is negligible next to the compass-bias uncertainty already modelled, and it makes chunk math and distance queries trivial.

Do **not** use great-circle math for gameplay. Use it only for displayed bearings if desired.

---

## 5. Three-Tier LOD

| Tier | Range | What runs | Cost |
|---|---|---|---|
| **Coarse / global** | Entire map | Weather cells, all vessel schedules, hotspot stock curves, event director | Always on; bounded (§5.1) |
| **Warm** | 2–3× active radius (~25–40 nm) | Statistical: traffic density, hotspot confidence; no individual entities | Per-chunk tick, throttled |
| **Active** | ~12 nm (radar/visual) | Full entities, AI, collision, rendering, radio | Per-frame |

### 5.1 The fleet is bounded — this matters

The historical fleet is **~450 vessels** (11 motherships + ~300 corporate catchers + ~135 independents + ~15 corporate longliners + ~5 Coast Guard + ~10 Soviet). Unlike procedural wildlife or debris, AI ships are a **finite, known set**. Therefore:

- The coarse tier is a list of ~450 schedule entries — cheap in pure Python.
- Chunking is **not** needed for the coarse fleet.
- Chunking matters only for **warm/active promotion** and for **procedural entities** (gulls, debris, bait balls, hotspots), which are unbounded.

This corrects the general "chunking pays off at 2,000+ entities" heuristic: for AI ships the bound is ~450, so chunking buys promotion discipline and rendering culling, not coarse-fleet memory savings.

### 5.2 Promotion rule

On player chunk-boundary crossing:

1. Demote active ships that left active radius → warm (statistical presence).
2. Demote warm ships that left warm ring → coarse (schedule only; contact state persisted, §8.2).
3. Promote coarse ships entering warm ring → warm.
4. Promote warm ships entering active radius → active (render, AI, radio).
5. Enforce **active entity cap**; if exceeded, nearest-first promotion, farthest demotion.

Transitions must be invisible. Because all tiers derive from the same schedule and the same reported/actual state, no ship "pops in."

---

## 6. Deterministic Chunk Seeding

Every chunk regenerates identically on reload.

```python
import struct, zlib

def chunk_seed(world_seed: int, cx: int, cy: int) -> int:
    return zlib.crc32(struct.pack("<qqq", world_seed, cx, cy))
```

**Do not use `hash((world_seed, cx, cy))`** — Python tuple hashing is randomized per process unless `PYTHONHASHSEED` is fixed.

Everything procedural in a chunk draws from `random.Random(chunk_seed)` in a **fixed order**. Document the draw order; changing it breaks saves.

### 6.1 Chunk size

- **20 × 20 nm**, unified with the weather grid cell size.
- Full Phase B extent → ~85 × 63 ≈ **5,355 chunks**, stored sparsely in a dict. Empty chunks cost nothing.

---

## 7. Weather Grid (global field, not chunked)

- **20 nm cells**, advected with prevailing wind.
- Slow tick: every **10–15 in-game minutes**.
- Local wave height = base swell + wind-sea contribution from nearest cells.
- **Three-day forecast** = forward integration of the same grid (already surfaced in the Notebook).
- Storm regime triggers the market scarcity premium (existing v13v1-05 system).

Because weather is a field, a storm 80 nm away is fully simulated for forecast purposes at zero entity cost. No chunking required.

### 7.1 Weather persistence

Do **not** attempt deterministic replay of advection. Serialize the coarse weather snapshot:

- 5,355 cells × (pressure, wind_u, wind_v, precip, sea_state) ≈ 27k floats
- ~100–200 KB binary — negligible next to the Radio Log
- Avoids replay cost on load and guarantees save/load consistency

---

## 8. Delta Persistence

Serialize only what the player changed or what must survive unload. Everything else regenerates from seed.

### 8.1 Per-chunk deltas

- Hotspot depletion fraction (per hotspot id)
- Caught / removed entities
- Deployed, damaged, or lost gear
- Event flags and cooldown timers
- Radio Log entries anchored to that chunk (already persisted per v13v1-05)

### 8.2 Cross-chunk ship state (critical)

A ship the player spoke to and then sailed away from **must not lose its relationship state**. Contacted ships are promoted to a **persistent vessel list**, separate from the coarse schedule pool:

| Field | Why persisted |
|---|---|
| `id`, `callsign`, `archetype`, `personality` | Identity |
| `trust` | Earned slowly, decays slowly |
| `contact_count` | Gates stranger vs. familiar intents |
| `last_contact_sim_time` | Trust decay calculation |
| `mayday_sent` | Prevents repeated maydays |
| `mayday_resolved` | Assistance outcome |
| `reported_hotspot` | Deception offset may have converged with trust |
| `actual_hotspot` | If revealed through trust or physical discovery |
| `activity_override` | If player interaction changed its plan |
| `is_rival` | Relationship flag (§15.3) |

This is the "tricky case" from the chunking discussion, now resolved explicitly: **contact promotes to persistent.**

---

## 9. Coordinate & Rendering Discipline

1. **Simulation** in nautical miles as Python doubles.
2. **Rendering** in camera-relative coordinates: subtract camera position before converting to pixels.
3. **Never** pass large absolute world floats to Pygame surface coordinates — integer overflow and jitter.
4. Chunk-local coordinates plus chunk origin for anything that must be stored with precision.

At Phase B extent (~1,700 × 1,250 nm), absolute floats are fine for doubles but not for 32-bit pixel paths. Enforce camera-relative at draw time.

---

## 10. Performance Budgets & Measurement Plan

### 10.1 Budgets

| Item | Budget |
|---|---|
| Frame time | ≤ 16 ms (60 fps target) |
| Active AI ships | Hard cap ~30–50 |
| Warm-ring ships (statistical) | Hundreds, throttled |
| Coarse fleet | ~450 schedule entries, always |
| Chunk activation | ≤ 16 ms, or amortized over frames |
| Weather tick | ≤ 2 ms per 10–15 in-game min |
| Save size | < 2 MB after long campaign (excluding Radio Log growth) |

### 10.2 What to measure before committing

1. Active entity count before frame time exceeds budget.
2. Cost of one weather-grid tick at 20 nm resolution (NumPy vectorized).
3. Chunk activation/deactivation cost; if > 16 ms, amortize or pre-generate warm ring.
4. Save size growth over a long campaign.
5. Whether the **bounded ~450-ship fleet** stays cheap in pure Python (it should, but verify).

### 10.3 Python-specific mitigations

- **NumPy** for all fields (weather, bathymetry, wave sampling).
- **Spatial hashing** for neighbor queries.
- **Throttled updates**: coarse every N ticks, warm every few ticks, active per frame.
- **Hard active cap** enforced by the chunk manager.
- **Profile before chunking procedural entities.** If procedural entities are < 2,000, defer chunking them.

---

## 11. Historical Realism Research

Constraints drawn from 1962 North Pacific fishery and marine radio sources. These inform traffic density, ship types, radio ranges, and conversation content.

### 11.1 Fleet composition and scale (1962)

| Fact | Value | Implication |
|---|---|---|
| Mothership salmon fleet (since 1962) | **11 motherships, 369 catcher-boats** | Mothership hierarchy is the dominant traffic structure |
| Catcher-boat size | ~**80 tons**, crew ~**20** | Mid-sized AI entities |
| Mothership crew | ~**400 persons** | Rare, large, high-value radio contacts |
| Mothership processing | **100–200 t canned/day**, 40–160 t frozen | Motherships are collection/processing nodes |
| Fishing area (since 1959) | **160°E–175°W, 46°N–62°N** | Defines coarse traffic bounds |
| Season | **~May 20 – Aug 10** | Traffic density is seasonal |
| Gillnet per catcher-boat | 264–330 tons (8.2–10.2 miles) | Fishing is stationary and gear-heavy; hauling boats cannot chat freely |
| Catcher-boats per mothership | **30–35** | Mothership–catcher radio traffic is structured and frequent |
| Land-based longline authorization | **369 vessels** (of 702 land-based) | Independent longliners are a real, sizeable group |

The 1962 fleet is **not** scattered independents. It is an organized industrial fleet with a mothership hierarchy, a defined operating box, and a short season — alongside a substantial independent land-based fleet selling at auction. AI traffic must reflect **clusters**, **transit corridors**, and **sparse independent traffic** outside the box.

### 11.2 Japan–Soviet tension (1962)

- The sixth Japan–Soviet Northwest Pacific Fisheries Commission **deadlocked** over Soviet demands to expand the regulatory area south of **45°N**.
- Japan refused and authorized **702 land-based vessels** (333 gillnet, 369 longline) south of 45°N on **April 30, 1962**.
- Japan's salmon quota outside Treaty waters was set at **60,000 metric tons**, roughly 20,000 t below the prior year's actual catch.
- The Soviet Union had a history of **apprehending Japanese boats** near the Kurils for "territorial waters" violations.

This grounds `treaty_challenge` as historical, not invented. A treaty-line awareness system is a realistic extension.

### 11.3 Marine radio reality (1962 Japan)

| System | Introduced | Frequency | Power / Range | Notes |
|---|---|---|---|---|
| **1W DSB** | July 1955 | 26.760–27.923 MHz | 1 W, ~**50 km (~27 nm)** | Widespread fishery radio |
| **SSB** | November 1960 | 27.018.5–27.524 MHz | up to 25 W, ~**90 km (~49 nm)** | Newer in 1962; not universal |
| Distress | — | **27.524 MHz** | — | Dedicated fishery distress channel |

**Crucial implication:** many 1962 vessels cannot be hailed beyond ~27 nm. A catcher-boat 200 nm away is not on the radio. This makes contact **local and earned**, and it means the player's information horizon roughly matches the physical horizon. Long-range coordination ran through motherships and coast stations, not ship-to-ship chat.

Radiotelephone style was terse: *Over*, *Out*, *Roger*, *Wilco*, *Say again*. The conversation catalog follows this; it should be enforced as a style rule.

### 11.4 Crew roles and work rhythm

- **漁労長 (gyorōchō)** — fishing master; authority over set/haul.
- **船長 (senchō)** — captain; legal/navigational authority.
- **通信士 (tsūshinshi)** — radio operator.
- **魚見役 (uomiyaku)** — fish spotter.
- **甲板員 (kanpan'in)** — deckhands, ~20 on a catcher-boat, fewer on a longliner.

Hauling was **shift-based**; hauling often began around **2 p.m.**, with 400 baskets regarded as a practical maximum. A boat mid-haul is operationally busy — this justifies the `activity` gate in intent selection. On larger vessels the 通信士 handles traffic, so speaker labels may read `"{other_vessel} (radio)"` without mechanical change.

---

## 12. AI Ship Model

### 12.1 Two-layer object

| Layer | Exists when | Cost | Contents |
|---|---|---|---|
| Coarse schedule entry | Always | Negligible | Waypoints, archetype, personality, persisted contact state |
| Active entity | Within active radius | Per-frame | Position override, heading, speed, local avoidance, rendering |

`position` is **always** interpolated from `schedule`; the active layer only overrides local behavior. On leaving active range, the override is discarded and the schedule resumes.

### 12.2 Dataclasses

```python
class Activity(Enum):
    TRANSIT = "transit"
    FISHING = "fishing"
    HAULING = "hauling"
    ANCHORED = "anchored"
    DISTRESSED = "distressed"
    RETURNING = "returning"


class Archetype(Enum):
    PLAYER = "player"                      # independent longline
    INDEPENDENT_LONGLINE = "ind_longline"
    INDEPENDENT_GILLNET = "ind_gillnet"
    CORPORATE_CATCHER = "corp_catcher"     # mothership-contracted gillnet
    CORPORATE_LONGLINER = "corp_longline"  # company-owned longliner
    MOTHERSHIP = "mothership"              # corporate control vessel
    COAST_GUARD = "coast_guard"
    SOVIET_TRAWLER = "soviet"


@dataclass
class AIShip:
    id: str
    name: str
    callsign: str
    archetype: Archetype
    home_port: str
    personality: str
    schedule: list[tuple]        # (sim_time, x_nm, y_nm, activity)
    position: tuple[float, float]
    heading: float
    speed_kn: float
    activity: Activity
    actual_hotspot: tuple | None
    reported_hotspot: tuple | None
    trust: float = 0.5
    last_contact_sim_time: float = -1e9
    contact_count: int = 0
    mayday_sent: bool = False
    mayday_resolved: bool = False
    is_rival: bool = False
    radio_range_nm: float = 27.0   # DSB typical; SSB vessels 49 nm
```

The old `FLEETMATE`, `RIVAL`, and `INDEPENDENT` archetypes are removed. `RIVAL` becomes a **relationship flag** (§15.3), not an archetype.

---

## 13. Personality & Information Policy

| Personality | Trust gain | Truthfulness (grounds) | Truthfulness (safety) | Talkativeness | Archetype affinity |
|---|---|---|---|---|---|
| `cooperative` | Fast | High (0.85–0.95) | High | High | Independent longline/gillnet |
| `cagey` | Slow | Medium (0.55–0.70) | High | Medium | Independent, corporate longliner |
| `competitive` | Very slow | **Low (0.20–0.35)** | High | Medium | Independent (rival) |
| `corporate` | Very slow | **Low (declines, not deceives)** | High | Medium | Corporate catcher, corporate longliner |
| `hostile` | Negative | Low | Low | Low | Soviet trawler |
| `official` | N/A | High (procedural) | High | Procedural | Coast Guard, mothership control |
| `gossip` | Medium | Medium | High | Very high | Independent |

**Deception is explicit, and distinct from decline.**

- A `competitive` independent rival's `reported_hotspot` may be displaced 10–20 nm from `actual_hotspot`. Above `trust ≈ 0.4`, `reported_hotspot` converges toward truth. This is the social analogue of compass bias.
- A `corporate` vessel **does not lie**. It *declines* — "Company business. Can't say." The player learns that corporate traffic is a dead end for intel but a reliable source for weather.

**Safety traffic is universal.** Weather warnings and maydays cross all boundaries — historically, and for gameplay, this is the one channel where corporate and independent cooperate without friction.

---

## 14. Corporate vs. Independent Dynamics

### 14.1 Definitions

| Category | Definition | Radio behavior |
|---|---|---|
| **Independent** | Owner-operator or small company; sells at auction; no mothership contract | Gossipy, cooperative with peers, cagey with strangers |
| **Corporate catcher** | Company-owned or contract boat delivering to a mothership | Procedural, quota-aware, **restricted from sharing grounds intel** |
| **Corporate mothership** | Processing/collection vessel; controls a catcher fleet | Formal control traffic; quota checks; collection schedules |
| **Corporate longliner** | Company-owned longliner selling at auction (rarer) | Polite but guarded; company loyalty limits candor |

### 14.2 Trust and information asymmetry

| Pairing | Trust gain | Truthfulness on grounds | Notes |
|---|---|---|---|
| Independent ↔ Independent | Fast | High | Peers share honestly; reputation spreads via gossip |
| Independent ↔ Corporate catcher | Very slow | **Low** | Company orders forbid sharing; may deflect politely |
| Independent ↔ Corporate longliner | Slow | Medium | Professional courtesy, but guarded |
| Independent ↔ Mothership control | N/A | High on quota, **silent on grounds** | Control only discusses the player's own quota |
| Corporate ↔ Corporate (same company) | Fast | High | Fleet-internal coordination |
| Corporate ↔ Corporate (rival company) | Very slow | Low | Commercial rivalry |

Corporate catcher-boats are **not hostile — they are constrained**. They will share weather and safety information (universal obligation, and historically real), but deflect grounds questions. This is a distinct behavior from `competitive` deception.

### 14.3 Trust decay

Corporate vessels decay trust **faster** than independents (~0.02/day vs ~0.01/day). Corporate relationships are transactional and require maintenance; independent peer relationships are more durable.

### 14.4 Rival as relationship state

`RIVAL` is a **flag** set when an independent vessel's trust with the player drops below a threshold (e.g., −0.2, achievable through repeated hostile hails, poaching on their gear, or ignoring their mayday). Rivals gain access to `grounds_misdirect` and `refuse_contact`.

```python
def update_relationship_flags(ship):
    ship.is_rival = (
        ship.archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET)
        and ship.trust < -0.2
    )
```

---

## 15. Radio Range & Contact Gating

A ship can be hailed only if:

```python
distance(player.position, ship.position) <= ship.radio_range_nm
```

This enforces the 1962 hardware reality. Mothership and coast-station relay traffic is handled separately and may reach further.

---

## 16. Radio Intent System

### 16.1 Intent selection

Weighted table conditioned on `archetype × personality`, `activity`, `trust`, `contact_count`, weather regime, `mayday_sent`, and radio range.

| Intent | Primary trigger | Example |
|---|---|---|
| `hail_stranger` | `contact_count == 0` | "You're a new voice. What fleet?" |
| `hail_familiar` | `contact_count > 0`, `trust > 0.3` | "Back again? North line's been quiet." |
| `peer_exchange` | Independent peer | "Longline or gillnet? Birds working 040." |
| `grounds_report_honest` | `trust ≥ 0.4`, honest | "Working birds bearing 040, 12 miles." |
| `grounds_misdirect` | `competitive`, `trust < 0.3` | "Try the south bank — loaded there." |
| `grounds_declined` | `corporate` | "Company business. Can't say." |
| `weather_warning` | Storm front within ~40 nm | "Swell building fast west of the point." |
| `corp_grumble` | Independent peer | "Company boats will take the lot." |
| `corp_fleet_coordination` | Corporate ↔ mothership (overheard) | "Control, No. 18. Position ..." |
| `mothership_warning` | Mothership → independent | "You are working our fleet's line." |
| `quota_check` | Mothership → contracted catcher | "You're two tons from quota." |
| `mayday` | `DISTRESSED`, not yet sent | "Taking water, request assistance." |
| `assist_ack` | Player responds to mayday | "Copy, Maru. Three miles east." |
| `port_gossip` | `ANCHORED` or `RETURNING` | "Auction's short on cod today." |
| `refuse_contact` | Independent rival or `hostile` | "Restricted frequency. Clear it." |
| `treaty_challenge` | `soviet`, near treaty line | "You are inside the treaty line. Turn back." |

**Activity gate:** `HAULING` suppresses extended chat. Only short acknowledgements are eligible.

### 16.2 Intent eligibility by archetype

| Intent | Independent | Corporate catcher | Corporate longliner | Mothership | Coast Guard | Soviet |
|---|---|---|---|---|---|---|
| `hail_stranger` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `hail_familiar` | ✓ | ✓ (slow) | ✓ (slow) | ✗ | ✓ | ✗ |
| `peer_exchange` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `grounds_report_honest` | ✓ | ✗ | ✓ (rare) | ✗ | ✗ | ✗ |
| `grounds_misdirect` | ✓ (rival only) | ✗ | ✗ | ✗ | ✗ | ✗ |
| `grounds_declined` | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| `weather_warning` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `corp_grumble` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `corp_fleet_coordination` | ✗ | ✓ (overheard) | ✗ | ✓ (overheard) | ✗ | ✗ |
| `mothership_warning` | ✓ (target) | ✗ | ✗ | ✓ (source) | ✗ | ✗ |
| `quota_check` | ✗ (no quota) | ✓ | ✗ | ✓ (source) | ✗ | ✗ |
| `refuse_contact` | ✓ (rival) | ✗ | ✗ | ✗ | ✗ | ✓ |
| `treaty_challenge` | ✓ (target) | ✓ (target) | ✓ (target) | ✗ | ✗ | ✓ (source) |
| `mayday` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 17. Slot Filling with Policy

```python
def build_context(ship, player, world):
    truthful = TRUTHFULNESS[ship.personality]
    use_true = (rng.random() < truthful) and (ship.trust > TRUST_THRESHOLD)

    pos = ship.actual_hotspot if use_true else ship.reported_hotspot
    return {
        "vessel": player.name,
        "other_vessel": ship.callsign,
        "mothership": world.motherships.nearest(ship).name,
        "reported_bearing": bearing(player.position, pos),
        "reported_range": int(distance(player.position, pos) / NM),
        "weather": world.weather.phrase_at(ship.position),
        "sea_state": world.weather.sea_state_at(ship.position),
        "activity_phrase": ACTIVITY_PHRASES[ship.activity],
        "port": ship.home_port,
        "market_note": world.market.phrase(),
        ...
    }
```

The player **cannot distinguish** a true report from a false one within the transcript. Verification requires physical investigation or triangulation with other contacts.

---

## 18. Trust Dynamics

```python
CONTACT_EFFECTS = {
    "hail_polite": +0.05,
    "share_report": +0.08,
    "assist_mayday": +0.40,
    "ignore_mayday": -0.50,
    "hail_hostile": -0.10,
    "treaty_violation": -0.30,
    "poach_gear": -0.40,
}

def apply_contact_effect(ship, action, world):
    ship.trust = clamp(ship.trust + CONTACT_EFFECTS.get(action, 0.0), -1.0, 1.0)
    ship.contact_count += 1
    ship.last_contact_sim_time = world.sim_time
    update_relationship_flags(ship)
```

Trust decays **~0.01/day** for independents and **~0.02/day** for corporate vessels without contact. `gossip` personalities propagate trust changes to fleetmates, creating emergent reputation. All contact state is persisted per §8.2.

---

## 19. Conversation Catalog

All templates use 1962 radiotelephone style. Compatible with `radio_chatter.py`.

### 19.1 Routine ship-to-ship

```python
ConversationTemplate(
    "hail_stranger",
    tags=("ship", "routine"),
    weight=2.0,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You're a new voice. What fleet, over?"),
        ("{vessel}", "{other_vessel}, {vessel}. Independent longline out of {port}, over."),
        ("{other_vessel}", "Copy, {vessel}. Mind the tide line; running hard. Out."),
    ),
    requires=("other_vessel", "vessel", "port"),
    cooldown_s=900,
)

ConversationTemplate(
    "hail_familiar",
    tags=("ship", "routine"),
    weight=1.6,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. Back again?"),
        ("{vessel}", "{other_vessel}. Same grounds. Anything moving?"),
        ("{other_vessel}", "Quiet since morning. {activity_phrase} now. Out."),
    ),
    requires=("other_vessel", "vessel"),
    cooldown_s=1200,
)
```

### 19.2 Independent peer exchange

```python
ConversationTemplate(
    "peer_exchange",
    tags=("ship", "intel", "independent"),
    weight=2.4,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. Longline or gillnet?"),
        ("{vessel}", "{other_vessel}. Longline. You?"),
        ("{other_vessel}", "Same. {activity_phrase}. Birds working {reported_bearing} at {reported_range}. Worth a look, out."),
    ),
    requires=("other_vessel", "vessel", "reported_bearing", "reported_range"),
    cooldown_s=900,
)
```

### 19.3 Grounds intelligence (honest)

```python
ConversationTemplate(
    "grounds_report_honest",
    tags=("ship", "intel", "honest"),
    weight=2.2,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. We've been working {activity_phrase}."),
        ("{vessel}", "{other_vessel}, copy. Any bird activity?"),
        ("{other_vessel}", "Aye — working birds {reported_bearing} at {reported_range} miles. Patchy but worth a pass."),
    ),
    requires=("other_vessel", "vessel", "reported_bearing", "reported_range"),
    cooldown_s=1200,
)
```

### 19.4 Grounds intelligence (deceptive — rival only)

```python
ConversationTemplate(
    "grounds_misdirect",
    tags=("ship", "intel", "deceptive"),
    weight=1.4,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You looking for fish?"),
        ("{vessel}", "Always. Where's the school?"),
        ("{other_vessel}", "Try {reported_bearing} at {reported_range} miles. Loaded there this morning."),
    ),
    requires=("other_vessel", "vessel", "reported_bearing", "reported_range"),
    cooldown_s=1800,
)
```

### 19.5 Corporate decline

```python
ConversationTemplate(
    "grounds_declined",
    tags=("ship", "intel", "corporate"),
    weight=1.8,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You're asking about grounds?"),
        ("{vessel}", "{other_vessel}. Just a routine query, over."),
        ("{other_vessel}", "Company business. Can't say. Weather's holding, though. Out."),
    ),
    requires=("other_vessel", "vessel"),
    cooldown_s=1200,
)
```

### 19.6 Weather warning

```python
ConversationTemplate(
    "weather_warning",
    tags=("ship", "weather", "safety"),
    weight=1.8,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You see that {weather} building?"),
        ("{vessel}", "{other_vessel}, we see it. How bad?"),
        ("{other_vessel}", "Sea state {sea_state} and climbing. I'm hauling gear and running for {port}. Recommend you do the same, out."),
    ),
    requires=("other_vessel", "vessel", "weather", "sea_state", "port"),
    cooldown_s=1500,
)
```

### 19.7 Priority: mayday and assistance

```python
ConversationTemplate(
    "mayday_from_ship",
    tags=("ship", "emergency", "priority"),
    weight=0.2,
    lines=(
        ("{other_vessel}", "Mayday, mayday. {other_vessel} taking water near {distress_location}. Request immediate assistance."),
        ("Coast Guard", "{other_vessel}, Coast Guard. Roger mayday. Vessels in vicinity, acknowledge."),
        ("{vessel}", "Coast Guard, {vessel}. We are {assist_distance} away. Proceeding to assist, over."),
    ),
    requires=("other_vessel", "vessel"),
    cooldown_s=7200,
)
```

Priority traffic may **interrupt ambient chatter** (v13v1-11 contract). All other ship traffic queues behind active transcripts.

### 19.8 Hostile and treaty traffic

```python
ConversationTemplate(
    "refuse_contact",
    tags=("ship", "hostile"),
    weight=1.0,
    lines=(
        ("{other_vessel}", "{vessel}, this is a restricted frequency. State your business or clear it."),
        ("{vessel}", "{other_vessel}, {vessel}. Routine hail, over."),
        ("{other_vessel}", "Then we have nothing to discuss. Out."),
    ),
    requires=("other_vessel", "vessel"),
    cooldown_s=3600,
)

ConversationTemplate(
    "treaty_challenge",
    tags=("ship", "hostile", "historic"),
    weight=0.6,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You are inside the treaty line. Turn back."),
        ("{vessel}", "{other_vessel}, {vessel}. We are in unrestricted waters. We hold our course."),
        ("{other_vessel}", "As you wish. {other_vessel} out."),
    ),
    requires=("other_vessel", "vessel"),
    cooldown_s=5400,
)
```

### 19.9 Independent grievance

```python
ConversationTemplate(
    "corp_grumble",
    tags=("ship", "independent", "social"),
    weight=1.4,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You see the company boats working the line?"),
        ("{vessel}", "{other_vessel}. Aye. They'll take the lot and leave us the scraps."),
        ("{other_vessel}", "Auction won't care who caught it. Watch your price. Out."),
    ),
    requires=("other_vessel", "vessel"),
    cooldown_s=2400,
)
```

The auction does not distinguish corporate from independent catch, but corporate boats have guaranteed buyers and independents do not. The grievance is real.

### 19.10 Corporate fleet coordination (overheard)

```python
ConversationTemplate(
    "corp_fleet_coordination",
    tags=("ship", "corporate", "overheard"),
    weight=1.2,
    lines=(
        ("{other_vessel}", "{mothership} Control, {other_vessel}. Position {reported_bearing}, {reported_range} miles. Setting gear, over."),
        ("{mothership} Control", "{other_vessel}, Control. Roger. Report at next haul. Out."),
    ),
    requires=("other_vessel", "mothership"),
    cooldown_s=900,
)
```

This fires **without the player being addressed**. It is overheard traffic — historically accurate (the player's radio would receive nearby corporate transmissions) — and it reinforces the hierarchy without requiring the player to participate. Tagged `overheard`, logged to the Radio Log, but **not queued as player-facing conversation**.

### 19.11 Mothership and port traffic

```python
ConversationTemplate(
    "mothership_warning",
    tags=("ship", "mothership", "corporate"),
    weight=0.8,
    lines=(
        ("{mothership} Control", "{vessel}, {mothership} Control. You are working our fleet's line."),
        ("{vessel}", "{mothership} Control, {vessel}. Independent longline. We're outside your quota."),
        ("{mothership} Control", "Copy, {vessel}. Mind the gear. Out."),
    ),
    requires=("mothership", "vessel"),
    cooldown_s=3600,
)

ConversationTemplate(
    "quota_check",
    tags=("ship", "mothership", "logistics"),
    weight=1.2,
    lines=(
        ("{mothership} Control", "{vessel}, {mothership} Control. Report your catch and position, over."),
        ("{vessel}", "{mothership} Control, {vessel}. {catch} aboard. Position as reported."),
        ("{mothership} Control", "Roger, {vessel}. You are {quota_status}. Return for transfer, out."),
    ),
    requires=("other_vessel", "vessel", "catch"),
    cooldown_s=1800,
)

ConversationTemplate(
    "port_gossip",
    tags=("ship", "harbor", "market"),
    weight=1.6,
    lines=(
        ("{other_vessel}", "{vessel}, {other_vessel}. You back in {port} soon?"),
        ("{vessel}", "Tomorrow, weather willing. Why?"),
        ("{other_vessel}", "Auction's twitchy. {market_note}. Don't hold your catch too long, out."),
    ),
    requires=("other_vessel", "vessel", "port", "market_note"),
    cooldown_s=1800,
)
```

The mothership **cannot** enforce anything on an independent vessel. `quota_check` is eligible only when the target is a **contracted corporate catcher**, not the player. `mothership_warning` is the tense, bounded exchange that fires for independents.

---

## 20. Integration with Existing Systems

### 20.1 Radio queue priority

| Source | Priority | May interrupt ambient? |
|---|---|---|
| Ambient chatter (`radio_chatter.py`) | Low | No |
| Overheard corporate traffic | Low | No |
| Ship hail / response | Medium | No |
| Mayday / assist / Coast Guard | **High** | **Yes** |

### 20.2 Dispatcher

```python
class ShipRadioDispatcher:
    def tick(self, world, player, radio_queue, notebook):
        for ship in world.ships_in_active_range(player):
            if ship.activity == Activity.DISTRESSED and not ship.mayday_sent:
                lines = self.ship_radio.generate(ship, player, world)
                radio_queue.enqueue_priority(lines)
                ship.mayday_sent = True

        for hail in self.pending_hails:
            if in_radio_range(player, hail.ship):
                lines = self.ship_radio.generate(hail.ship, player, world)
                radio_queue.enqueue(lines)

        for ship in world.nearby_corporate(player):
            if rng.random() < OVERHEARD_CHANCE:
                lines = self.ship_radio.generate_overheard(ship, world)
                radio_queue.enqueue_overheard(lines)

        if radio_queue.idle() and rng.random() < CHATTER_CHANCE:
            radio_queue.enqueue(self.ambient_chatter.generate(world_ctx, now=world.sim_time))
```

Every line appends to `notebook.radio_log` with timestamp, speaker, and text, preserving the v13v1-05 contract. Multi-turn transcripts remain contiguous. Overheard traffic is tagged so the UI can render it distinctly (e.g., italic, or a separate sub-stream).

### 20.3 Traffic density by season

- **April:** low density (pre-season; departures beginning).
- **May 20 – Aug 10:** high density within the box, clustered around motherships.
- **Outside box:** sparse independents and transit.
- **Night:** hauling shifts reduce chatter.

---

## 21. Why This Is Harder — and More Realistic

| System | Uncertainty source | Player response |
|---|---|---|
| Navigation | Compass bias, speed-log error | Cross-reference fixes |
| Radio intel | Personality, trust, deception, corporate decline | Verify, build relationships, triangulate |
| Traffic | Range limits, silence, activity gates, corporate opacity | Physical proximity matters |
| Social | Corporate/independent split, auction exposure | Choose who to trust, who to help |
| Mayday | Rare, time-critical | Assistance builds trust; neglect spreads via gossip |

A rival's "loaded there this morning" is a **claim**. A corporate "can't say" is a **boundary**, not a lie. A silent ship may be hauling, hostile, or out of range. A mayday ignored has social cost. This extends "truth never leaks" from the compass to the radio band.

---

## 22. Implementation Order

| Step | Deliverable | Verification |
|---|---|---|
| **1** | `world/` foundation: projection, chunk manager skeleton, deterministic seeding, delta persistence with ship contact state | Chunks regenerate identically; save/load preserves trust and contact state |
| **2** | `weather_grid.py`: 20 nm cells, advection, forecast, snapshot persistence | Forecast matches forward integration; save/load consistent |
| **3** | `traffic.py`: `AIShip`, archetype split, schedule interpolation, coarse fleet (~450) | Ships move correctly on coarse tier; no per-frame cost |
| **4** | `ship_radio.py`: intent selection, `build_context`, trust dynamics, rival flag | Deception and decline paths behave correctly; rival flag triggers |
| **5** | Core templates: `hail_stranger`, `peer_exchange`, `grounds_report_honest`, `grounds_misdirect`, `grounds_declined`, `refuse_contact` | World feels populated; intel varies by archetype and personality |
| **6** | `ShipRadioDispatcher`: priority tiers, radio range gating, overheard path, Radio Log | Queuing, interruption, logging match v13v1-05/v13v1-11 |
| **7** | Mayday + assist | Priority interrupts ambient; trust applies; transcript logged |
| **8** | Historical flavor: `treaty_challenge`, `corp_grumble`, `corp_fleet_coordination`, `mothership_warning`, `port_gossip` | 1962 atmosphere; corporate/independent hierarchy visible |

Steps 1–3 build the world. 4–5 populate it. 6–7 make contact consequential. 8 adds period texture.

---

## 23. Test Plan

```python
def test_chunk_seed_deterministic_across_processes():
    assert chunk_seed(42, 3, 7) == EXPECTED_CRC32_VALUE  # fixed expected value

def test_contact_state_survives_chunk_unload():
    ship = make_ship(trust=0.7, contact_count=4)
    world.ships_contacted[ship.id] = ship
    world.unload_chunk(containing(ship))
    reloaded = load_world()
    assert reloaded.ships_contacted[ship.id].trust == 0.7

def test_competitive_ship_misdirects_until_trusted():
    ship = make_ship(personality="competitive", trust=0.0)
    ship.actual_hotspot = (42.0, 141.0)
    ship.reported_hotspot = (41.7, 140.6)
    assert build_context(ship, player, world)["reported_bearing"] != bearing_to(ship.actual_hotspot)
    for _ in range(20):
        apply_contact_effect(ship, "hail_polite", world)
    assert build_context(ship, player, world)["reported_bearing"] == bearing_to(ship.actual_hotspot)

def test_corporate_never_misdirects():
    ship = make_ship(archetype=Archetype.CORPORATE_CATCHER, personality="corporate")
    for _ in range(100):
        assert select_intent(ship, player, world) != "grounds_misdirect"

def test_independent_peer_shares_honestly():
    ship = make_ship(archetype=Archetype.INDEPENDENT_LONGLINE, personality="cooperative", trust=0.5)
    assert select_intent(ship, player, world) in ("peer_exchange", "grounds_report_honest")

def test_mothership_cannot_enforce_on_independent():
    ship = make_ship(archetype=Archetype.MOTHERSHIP)
    player.vessel.archetype = Archetype.PLAYER
    assert select_intent(ship, player, world) != "quota_check"

def test_overheard_traffic_not_queued_as_player_facing():
    lines = generate_overheard(corp_ship, world)
    assert all(line.source == "overheard" for line in lines)
    assert not radio_queue.contains_player_facing(lines)

def test_rival_flag_requires_negative_trust():
    ship = make_ship(archetype=Archetype.INDEPENDENT_LONGLINE, trust=0.0)
    update_relationship_flags(ship)
    assert not ship.is_rival
    ship.trust = -0.3
    update_relationship_flags(ship)
    assert ship.is_rival

def test_contact_blocked_beyond_radio_range():
    ship = make_ship(radio_range_nm=27)
    player.position = (0, 0)
    ship.position = (0, 30)
    assert not can_hail(player, ship)

def test_mayday_interrupts_ambient():
    queue = RadioQueue()
    queue.enqueue(ambient_line())
    queue.enqueue_priority(mayday_lines)
    assert queue.peek().speaker == ship.callsign

def test_hauling_suppresses_extended_chat():
    ship = make_ship(activity=Activity.HAULING, personality="gossip")
    assert select_intent(ship, player, world) not in EXTENDED_CHAT_INTENTS

def test_weather_snapshot_roundtrip():
    world.weather.advance_to(sim_time=10000)
    snapshot = world.weather.snapshot()
    restored = WeatherGrid.from_snapshot(snapshot)
    assert restored.phrase_at(some_point) == world.weather.phrase_at(some_point)
```

Additional checks: trust decay (faster for corporate); gossip propagation; every line logged; distress rarity; treaty-line gating; corporate decline vs. competitive misdirect legibility in transcripts.

---

## 24. Open Questions for Playtesting

1. **Radio range tuning.** Is 27 nm (DSB) too restrictive, or does it correctly make contact earned?
2. **Deception legibility.** Can players learn which personalities misdirect, or is deception indistinguishable from noise?
3. **Decline vs. deceive.** Is corporate `grounds_declined` distinguishable in play from competitive `grounds_misdirect`, or will players treat all refusals as lies?
4. **Fleet scale in Python.** Does ~450 coarse ships plus 30–50 active entities hold frame rate without NumPy tuning?
5. **Independent pool size.** Is ~40 independent longliners enough to feel like a community, or too few to sustain a campaign's social layer?
6. **Overheard traffic volume.** Does corporate fleet coordination add atmosphere, or does it crowd the Radio Log?
7. **Seasonal density.** Does May–August peak create a satisfying "fleet arrives" moment, or is April too empty?
8. **Trust pacing.** Is 20 polite hails to trust a competitive ship earned, or tedious?
9. **Mothership warning frequency.** Does the mothership hailing an independent feel tense and rare, or does it fire too often?
10. **Phase A vs. Phase B.** Does the regional map feel complete, or does the high-seas box need content earlier?
11. **Projection error.** Is < 0.5% equirectangular error acceptable once navigation uncertainty is layered on?

---

## 25. Sources Consulted

- NOAA / NMFS, *Japanese Mothership Salmon Fishery Means Research for NMFS* — fleet composition, area bounds, season, gear scale.
- *Commercial Fisheries Review*, Vol. 24 No. 7 (July 1962) — Japan–Soviet negotiations, 1962 fleet authorization (702 land-based: 333 gillnet, 369 longline), quota, displaced vessels.
- Japan Ministry of Internal Affairs and Communications, radio system history — 1W DSB (1955), SSB (1960), frequencies, ranges, distress channel.
- Japanese fisheries crew and operation studies — 漁労長, 船長, 通信士 roles; shift-based hauling; 400-basket maximum.
- Marine VHF radiotelephone procedure — prowords, terse style, channel discipline.
- *Fishing: North Atlantic* and *The Honest Little Fisher* Sea Radio Chatter — comparable commercial-fishing-sim design precedent.

---

*Pre-implementation plan. Does not modify the v13v1-05 changelog or claim playtested behavior. All realism claims sourced above; weights, ranges, chunk sizes, and trust thresholds are starting points for playtesting.*
```

---

## Implementation Notes — v13.2.04 (2026-10-22)

M8 has a first shared identity adapter. The active Coast Guard tow launch registers in `TrafficWorld` as a runtime `AIShip` using the same stable `vessel_id` as `TowEscort`. This common contact supplies spatial-index membership, chart marker, radio candidate identity, and radio transcript source metadata. The specialized `PLACE HOLDER SHIP` hull remains the single sea-view renderer for the live launch. The `TowEscort` captain and crew remain the source of conversation and escort state.

`TowEscort.snapshot()/from_snapshot()` and JSON helpers preserve active en-route/alongside/under-tow/arrived states, captain, crew, positions/reports, clocks, fuel, patience, and line-risk flags with a schema version. Tests cover round-tripping en-route and under-tow snapshots, shared ID registration, avoiding schedule overwrite, avoiding duplicate rendering, radio routing, and priority distress interruption. These snapshot primitives are **not yet integrated into the legacy career save/load system**; that is M10 scope. The regional weather tick also remains above the roadmap's 2 ms target and should be optimized before Phase B population.

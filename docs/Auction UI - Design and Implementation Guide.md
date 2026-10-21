# Auction UI — Design & Implementation Guide

A companion document to `WORLD_NAVIGATION_AND_FISHING.md`. This one is about the other half of the economic loop: what happens when the fish come off the ice hold and go to market.

Reference: `fishing_sim_11.py`. Class `Catch`, class `Game`, function `Game.settle()`, function `Game.docked()`.

---

## 1. How selling works today

The current sell step is a single function — `Game.settle()` — which is called in two places:

- Automatically, when the ship has been at the quay for three seconds (`at_quay and not self.arrival_done and self.dock_t > 3.0`)
- Manually, when the player presses `B` (`self.settle(manual=True)`)

Inside `settle()`, everything happens in one pass:

```python
if self.hold:
    self.market = clamp(lerp(self.market, 1.0, 0.3) + random.uniform(-0.15, 0.15), 0.7, 1.3)
    total, counts = 0, {}
    for c in self.hold:
        total += int(c.sale_value() * self.market * random.uniform(0.9, 1.1))
        counts[c.grade()] = counts.get(c.grade(), 0) + 1
    say("Auction: %d fish (%s) sold for %d yen, market x%.2f." % (...))
    self.hold.clear()
    self.cash += total
    self.earned += total
```

Then, immediately:

- Ice is bought up to `ICE_CAP` at `ICE_PRICE` per unit
- Fuel is bought up to `FUEL_CAP` at `FUEL_PRICE` per litre
- Gaffs are bought up to `GAFFS` at `GAFF_PRICE` each
- Bait is bought up to `BAIT_FILL` with the currently selected bait
- Crew wages (`s.owed`) are paid, either in full or short

So the current flow is: dock for three seconds → all fish sold for one aggregate number → everything refilled → crew paid → done. The player sees one crew log line and the cash tick up.

### What each fish actually knows

A `Catch` object (from the longline→gaff→dress→hold pipeline) carries:

| Field | Meaning |
|---|---|
| `name` | species ("albacore", "yellowfin", "bigeye", "swordfish", "blue shark") |
| `value` | base yen value for that species (2400 / 3800 / 5200 / 6500 / 600) |
| `quality` | 0.0–1.0, degraded by warmth, stress, sloppy cutting, and time |
| `bled` | bool — the gill/tail cut was made |
| `gutted` | bool — de-gilled and gutted |
| `core` | internal temperature, tracked over the trip |

And a `Catch` can answer three questions:

- `grade()` → returns "Sashimi" / "A" / "B" / "C" / "Scrap" from `quality`
- `sale_value()` → `value × grade_mult × (1 if bled else 0.85) × (1 if gutted else 0.8)`

`grade_of(quality)` returns `(name, multiplier)` from:

| Quality | Grade | Multiplier |
|---|---|---|
| ≥ 0.88 | Sashimi | 1.5× |
| ≥ 0.72 | A | 1.15× |
| ≥ 0.50 | B | 0.8× |
| ≥ 0.30 | C | 0.5× |
| < 0.30 | Scrap | 0.2× |

The `self.market` field is a global supply/demand index (0.7–1.3) that drifts after every sale and is broadcast on `F3` as a market report. It multiplies every fish's sale value equally, as if the whole market were up or down.

### What the player sees

Currently the player sees:

- A single crew-log line: **"Auction: 7 fish (3 Sashimi, 2 A, 1 B, 1 C) sold for 34,200 yen, market x0.95."**
- Cash ticking up in the HUD
- The market index shifting

They don't see:

- Which fish was which
- What each one sold for
- Who bought it
- Whether it was worth keeping
- What they could have got for it elsewhere

The economic decision-making — could I have got more? Should I have kept that swordfish one more session? Was the sashimi really sashimi-grade? — is invisible.

---

## 2. Design goals for the auction UI

**What the new system should add:**

1. **Per-fish visibility.** The player sees each fish on the block: its species, grade, quality, and expected value range.
2. **Buyer personalities.** Different buyers want different things. A sashimi chef pays a premium for a premium fish; a canner pays the same for anything; a collector pays for the rare swordfish regardless of grade. This makes the fish feel *valued by someone* rather than by an abstraction.
3. **Player agency.** For each fish, the player chooses: sell now at the current bid, hold for a higher bid, or keep it for another session. This is the trading decision the current auto-sell removes.
4. **Consequence.** A fish kept between sessions degrades. A fish sold too cheaply is lost revenue. A fish held for a better bid might get it, or might see the top bidder walk. Choices that matter.
5. **End-of-session summary.** A "session total" showing what was sold, what was kept, and what was earned — the moment the player sees whether it was a good trip.

**What the new system should preserve:**

1. **Ice/fuel/gaff/bait purchases.** These still need to happen — but they should happen *after* the auction, because the auction changes how much cash the player has.
2. **Crew wages.** Same — paid after.
3. **The market index.** It still drifts between sessions and still multiplies everything.
4. **Skippability.** A player who doesn't want to micromanage every albacore should be able to `ACCEPT ALL` and move on.
5. **The current `settle()` contract.** Other parts of the game (autodock, auto-fish return) call `settle()` expecting the hold to be emptied and cash to be credited. The refactor must preserve that contract.

---

## 3. The auction model

### 3.1 Buyer archetypes

Three to five buyer types, each with its own valuation logic. This is the *heart* of the auction — the reason the UI exists beyond "see each fish individually."

Recommended archetypes:

**The Sashimi Chef** (or sashimi restaurant buyer)

- High quality premium: `mult = 2.2` for grade Sashimi, `1.5` for grade A, `1.0` for grade B, `0.5` for grade C, `0.3` for scrap
- Also multiplies by `1.2` if `bled and gutted` (his kitchen only wants clean fish)
- Species preference: swordfish (1.3×), bigeye (1.2×), yellowfin (1.1×), albacore (1.0×), shark (0.4×)
- Doesn't buy: more than one fish per session (he's a chef, not a wholesaler)

**The Canner**

- Flat multiplier: `1.0` across all grades (canneries don't care about sashimi grade)
- But multiplies by `0.6` if `not bled` or `not gutted` (canneries do want clean kills)
- Species preference: albacore (1.4× — this is the canned-tuna species), yellowfin (1.0×), bigeye (0.9×), swordfish (0.7×), shark (1.2×)
- Buys everything, pays moderate

**The Wholesaler**

- Flat multiplier: `1.1` across grades
- But only bids on **lots**: 3+ fish of the same species in the same session. Otherwise no bid.
- Small per-fish premium for quantity: `1.0 + 0.05 * (count - 3)`, so 5 albacore gets 1.1 × 1.1 = ~1.21×
- Species preference: albacore (1.2×), yellowfin (1.2×), bigeye (1.0×), swordfish (0.8×), shark (1.0×)

**The Harbour Trader** (always present, the fallback)

- Flat `0.85×` across all grades — a floor price for anything
- No quality preferences
- Buys everything, pays least
- Guarantees a sale for a fish that no specialist wants

**The Collector** (rare)

- Only appears ~15% of sessions, and only for one specific trigger:
  - A swordfish of grade A or Sashimi → 1.8× premium
  - A bigeye over quality 0.9 → 1.6× premium
  - A shark of any quality → 0.5× (they're not interested in sharks)
- Buys only the one triggered fish, then leaves

The point of these archetypes is *variety*. A yellowfin A with saury: the chef bids high, the canner bids moderate, the wholesaler bids low if there are 3+, the harbour trader bids the floor. The player sees 3 different numbers and can pick the one they trust.

### 3.2 The bidding model

Two viable models. Pick one based on complexity budget.

**Model A — Direct offer menu (simple, recommended for v1)**

Each buyer's offer is fixed once the fish is on the block. Show 2–4 buyers with their offers. Player picks one, or holds.

```
FISH 3/7 — Yellowfin — Grade A (0.74)
Base value: 3,800 yen

Offers:
  Sashimi Chef    5,930 yen   [Kuroda, restaurant buyer]
  Canner          2,820 yen   [Hakodate Cannery]
  Wholesaler      — (needs 3+ same species)
  Harbour Trader  2,455 yen   [Trades on the quay]
  
[SELL to Chef]  [KEEP]  [ACCEPT ALL from here]
```

This is easy to implement, easy to read, and delivers all the design goals except "waiting for better bids."

**Model B — Rising bids over time**

Each buyer has a hidden `max_bid`. Every auction tick (0.5 s), the current highest bid rises toward the max of the highest-active bidder. Players can SELL NOW to lock in the current price or wait.

```
FISH 3/7 — Yellowfin — Grade A (0.74)
Current bid: 4,200 (Sashimi Chef)
Ticks remaining for the Chef: 4

Buyers:
  Sashimi Chef    ★★★  Bidding 4,200
  Canner               Passed (max 2,820)
  Harbour Trader       Bidding 2,455
  
[SELL NOW: 4,200]  [KEEP]  [AUTO-SELL from here]
```

More interesting to play, harder to read at a glance. If the top bidder's `max_bid` is 5,000 and current is 4,200, waiting 2–3 ticks usually gets you more, but occasionally the top bidder walks (their patience timer runs out) and you get only the second bidder's 2,455.

Model B is the "real auction" feeling. Model A is the "trade terminals" feeling. Recommend Model A for the first version, Model B for a follow-up if the player enjoys the trading layer.

### 3.3 Session state machine

The auction is a **modal session** with distinct states:

```
OFF
  → docked with fish in hold → OPENING
  → player presses B with fish in hold → OPENING (with warning if not docked)

OPENING (2 s)
  → show auction house location, buyers arriving
  → BUYERS_READY

BUYERS_READY
  → default to first fish
  → FISH_ON_BLOCK

FISH_ON_BLOCK
  → player views one fish and its offers
  → SELL_NOW → SOLD (add to session total, advance)
  → KEEP → KEPT (add to kept list, advance)
  → ACCEPT_ALL → AUTO_SELL_ALL

SOLD
  → brief confirmation (0.8 s)
  → if more fish → FISH_ON_BLOCK (next)
  → if no more → CLOSING

KEPT
  → brief confirmation (0.5 s)
  → if more fish → FISH_ON_BLOCK (next)
  → if no more → CLOSING

AUTO_SELL_ALL
  → sells every remaining fish to the best available buyer
  → brief scroll of "Sold" lines (1.5 s)
  → CLOSING

CLOSING (2 s)
  → session summary: total sold, total kept, buyers used
  → restore cash/fish state
  → return to normal dock state
  → call `settle()` for supplies/crew (with fish sale skipped)

CANCELLED (via ESC)
  → any unsold fish return to hold
  → session total is 0
  → call `settle()` for supplies/crew (with fish sale skipped)
```

Interruptions:

- **Man overboard during auction** — this shouldn't happen because the ship is stopped in harbour. But if the state somehow triggers (an NPC falls in the water near the ship), the auction should either pause or force-cancel. Recommend force-cancel with an explanatory line: *"The auctioneer stops the bidding: 'There's a man in the water!'"*
- **Window closed during auction** — currently no save/load, so state is lost. Note as a known limitation.
- **Player presses ESC** — soft-cancel; kept fish stay in hold, session total is added to cash, supplies are bought, crew paid.

### 3.4 Per-fish state during the block

Each fish cycles through:

```
WAITING → ON_BLOCK → SOLD / KEPT → (out of session)
```

Once a fish is on the block, its offers are visible. Its `quality` is frozen at the moment the fish goes on the block (the world is paused, so it wouldn't change anyway, but freezing makes the logic explicit).

If a fish is **kept**, it goes back into `self.hold` with a `kept_for_session += 1` marker. When the auction resumes next session, the fish has `quality -= 0.05 * kept_for_session` applied (via `Catch.tick` over a virtual holding period), so keeping it costs something.

---

## 4. UI layout

### 4.1 Dimensions

Full-screen modal (not a small panel) — the auction is a distinct scene, not a HUD element. Fade the world behind it to 20% opacity and lay a large card over the centre.

Roughly:

- Modal frame: 80% × 85% of the screen (centred)
- Three columns inside:

```
┌─────────────────────────────────────────────────────────────┐
│  AUCTION HOUSE — DAY 3, 14:22 — Market x0.95       Fish 3/7 │
├──────────────────┬───────────────────────┬──────────────────┤
│                  │                       │                  │
│  FISH            │  BUYERS               │  ACTIONS         │
│                  │                       │                  │
│  [fish drawing]  │  ● Sashimi Chef       │  [SELL NOW]      │
│                  │    5,930 yen          │                  │
│  Yellowfin       │    [Kuroda, rest.]    │  [KEEP]          │
│  Grade A (0.74)  │                       │                  │
│  Bled, Gutted    │  ● Canner             │  [ACCEPT ALL]    │
│                  │    2,820 yen          │                  │
│  Base 3,800      │    [Hakodate]         │  ─────────       │
│  Cold 1.2°C      │                       │                  │
│                  │  ● Harbour Trader     │  [CLOSE (ESC)]   │
│                  │    2,455 yen          │                  │
│                  │    [Quay trader]      │                  │
├──────────────────┴───────────────────────┴──────────────────┤
│  Session so far: 14,320 yen · 2 sold · 0 kept · 4 to go     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Left column — the fish

Top down:

1. **Fish drawing** — reuse `draw_fish()` at a large size (base_px 200+), on a dark card. This is the visual anchor.
2. **Species name** — "Yellowfin" / "Bigeye Tuna" / "Swordfish" / "Albacore" / "Blue Shark"
3. **Grade** — big coloured text: Sashimi (bright green), A (light green), B (yellow), C (orange), Scrap (red)
4. **Quality** — "0.74 / 1.00" with a small quality bar
5. **Handling tags** — inline badges: `BLED`, `GUTTED`, `ON ICE`, or the negative forms: `NOT BLED`, `NOT GUTTED`, `WARM 12°C`
6. **Base value** — "3,800 yen" (what this fish would be worth at grade Sashimi, bled, gutted — the maximum)
7. **Core temperature** — "1.2°C" with a small thermometer icon; red if above 5°C
8. **Current highest offer** — bold, at the bottom of the left column: "Best offer: 5,930 yen"

### 4.3 Middle column — the buyers

Each buyer is a **card** within the column, vertically stacked:

```
┌─────────────────────────────────────────┐
│ ● Sashimi Chef                          │
│   Kuroda, from the Ginza                │
│   ─────────────────────────────          │
│   Offer: 5,930 yen                      │
│   Grade A + bled + gutted → premium     │
└─────────────────────────────────────────┘
```

The buyer card shows:

- **Coloured dot** — green if the buyer is bidding, yellow if they're considering but not bidding (Model B), grey if they've passed
- **Buyer name** — the shop/company
- **Buyer identity line** — a one-line description ("Kuroda, from the Ginza", "Hakodate Cannery", "the harbour trader")
- **Offer** — the yen amount, or "—" if not bidding
- **A short rationale** — why this offer. "Grade A + bled + gutted → premium" / "Canneries don't care about grade" / "Needs 3+ same species". This is the *teaching* element — the player learns how buyers behave by reading these lines.

Buyer order: highest to lowest. The best offer is at the top.

If no buyer bids (e.g. a scrap shark when the Collector isn't present and the harbour trader's floor is still 0.85× so they *always* bid — so this is rare), show "No offers for this fish." with only `KEEP` available.

### 4.4 Right column — actions

Five buttons, top-to-bottom:

1. **`SELL NOW`** — large, primary colour (green). Accepts the best offer. This is what the player presses 90% of the time.
2. **`KEEP`** — medium, secondary colour (grey). Moves the fish back to the hold. The player learns: the fish will degrade a bit before next session.
3. **`ACCEPT ALL`** — small, warning colour (amber). Auto-sells every remaining fish to their respective best offers. For when the player trusts the buyer pool and wants to move on.
4. **Divider**
5. **`CLOSE (ESC)`** — small, danger colour (red). Ends the session immediately. Unsold fish stay in hold. **Requires a confirmation** — a second click within 2 s to confirm, because this is destructive.

Below the buttons, a hint:

> **Tip:** the Chef pays for grade and clean handling. The Canner buys anything. Keeping a fish loses about 5% quality per session.

This hint changes with the buyer pool present.

### 4.5 Bottom bar — session total

A thin strip at the bottom:

```
Session so far: 14,320 yen · 2 sold · 0 kept · 4 to go
```

Live-updating. Turns green when the total goes up.

At the end of the session, this becomes:

```
Session closed: 34,200 yen from 5 fish · 2 kept for later · Market x0.95
```

with a `Press any key` prompt or a 3-second timeout before returning.

### 4.6 Keyboard shortcuts

- `Space` or `Enter` = SELL NOW
- `K` = KEEP
- `A` = ACCEPT ALL
- `Esc` = CLOSE (with confirmation)
- `←` / `→` = switch fish (view offers for a different fish before committing)
- `↑` / `↓` = highlight a specific buyer's offer (still defaults to best)

The mouse is primary; keyboard is for speed once the player learns the rhythm.

---

## 5. Data model additions

New classes / fields to add, without writing the actual code:

### 5.1 `BuyerProfile`

A configuration object describing a buyer's personality:

- `name` — display name ("Sashimi Chef")
- `identity` — one-line description
- `species_prefs` — dict of species → multiplier
- `grade_prefs` — dict of grade name → multiplier
- `handling_required` — optional; if True, no offer unless `bled and gutted`
- `bulk_min` — if > 1, only bid when the session has this many same-species fish
- `bulk_bonus` — per-extra-fish multiplier
- `max_fish_per_session` — how many fish this buyer will buy (chef buys 1, canner buys all)
- `appearance_chance` — 1.0 for always-present (harbour trader), < 1.0 for rare (collector)
- `off_offer` — a fraction of the base sale_value if no other multiplier applies (fallback)
- `patience` — for Model B, how many ticks before they drop out
- `rationale_lines` — a template for the "why this offer" line

### 5.2 `Buyer`

Runtime instance of a buyer within a session:

- `profile` — the `BuyerProfile`
- `fish_bought_this_session` — counter for `max_fish_per_session`
- `state` — `WAITING / BIDDING / PASSED`

### 5.3 `FishLot`

Represents one fish on the block:

- `fish` — the underlying `Catch`
- `offers` — dict of `Buyer → yen amount`
- `best_offer` — the highest offer
- `best_buyer` — who made it
- `session_index` — position in the session (1 of 7)
- `state` — `WAITING / ON_BLOCK / SOLD / KEPT`
- `sold_to` — buyer or None
- `sold_for` — amount or 0

### 5.4 `AuctionSession`

The session itself:

- `lots` — list of `FishLot`, in the order they'll be shown
- `current_index` — which lot is on the block
- `buyers` — the buyers present this session
- `opening_time`, `close_time` — bookkeeping
- `total_sold`, `total_kept`, `total_yen`
- `market_multiplier` — the `self.market` snapshot at session start
- `state` — per §3.3

### 5.5 `Game` additions

- `self.auction` — current `AuctionSession` or None
- `self.auction_active` — bool for fast-path checks
- `self.auction_pause` — flag so `update()` skips world sim
- `self.settle_pending` — flag so `settle()` runs after the auction closes
- `self.last_auction_summary` — the last `CLOSED` session, so the player can review it from the HUD

### 5.6 `Catch` additions

- `kept_session_count` — incremented each time the fish is kept; used to apply quality decay between sessions

---

## 6. Integration with existing code

### 6.1 Splitting `settle()`

Currently `settle()` does fish sale + supplies + wages in one function. Split into two halves:

**New `settle_supplies_and_wages(manual=False)`** — everything settle does *except* selling fish:

- Buy ice, fuel, gaffs, bait
- Pay crew wages
- Set `self.arrival_done = True`
- The crew-log lines for these purchases remain

**New `start_auction(manual=False)`** — opens the auction UI:

- If `self.hold` is empty and not manual → `settle_supplies_and_wages()` directly, return
- If `self.hold` is empty and manual → say "Nothing in the hold to sell", return
- If not docked → say "We're not alongside", return
- Otherwise: build the `AuctionSession`, set `self.auction_active = True`, pause the world, don't yet touch cash

**The original `settle()` becomes a shim:**

```python
def settle(self, manual=False):
    if self.hold:
        self.start_auction(manual)
    else:
        self.settle_supplies_and_wages(manual)
```

This preserves every existing call site. `settle()` still exists, still does the right thing, still returns the same result. The auction is inserted in the middle when there's something to sell.

### 6.2 Where the call happens

Currently, in `Game.update()`:

```python
if at_quay:
    for s in self.sailors:
        if s.mode == Sailor.ABOARD:
            s.health = min(1.0, s.health + 0.03 * dt)
            s.fatigue = max(s.fatigue - 0.004 * dt, 0.0)
    if not self.arrival_done and self.dock_t > 3.0:
        self.settle()
```

Change:

```python
if not self.arrival_done and self.dock_t > 3.0 and not self.auction_active:
    self.settle()                # now opens auction if hold has fish
```

And add an `auction_active` guard near the top of `update()`:

```python
if self.auction_active:
    self.update_auction(dt)      # auction UI state machine
    return                       # skip world update
```

The world is paused during auction. No weather updates, no fish decay, no crew movements. All the other systems (engine, crew, radio) sit idle while the player is trading.

### 6.3 `B` key behaviour

In `handle()`:

```python
elif k == pygame.K_b:
    self.settle(manual=True)
```

Because `settle()` now opens the auction when the hold has fish, this "just works." `B` becomes "sell the catch" instead of "do the auto-settle."

### 6.4 Events during auction

Add a top-level handler at the start of `handle()`:

```python
if self.auction_active:
    return self.handle_auction(ev)
```

`handle_auction` handles:

- Mouse: click on a buyer card → highlight that buyer; click on SELL NOW → accept highlighted or best; click on KEEP / ACCEPT ALL / CLOSE
- Keyboard: Space/Enter/K/A/Esc/arrows as above
- Window resize: normal path continues, auction recomputes its layout from the new screen size
- Quit: normal path (window closes, session lost)

Mouse clicks *outside* the modal should be ignored (or return to the game? No — the auction is modal, so a click outside the modal frame should be ignored).

### 6.5 Drawing order

Add to `Game.draw()` at the very end, after everything else including the HUD:

```python
if self.auction_active:
    self.draw_auction()
```

`draw_auction` is responsible for:

1. Fading the world behind it (a black rectangle at 70% alpha over the screen)
2. Drawing the modal frame
3. Drawing the three columns
4. Drawing the bottom session bar
5. Drawing any transient overlays (CONFIRM CLOSE, SOLD popup)

It draws over the HUD. When the auction closes, normal draw resumes.

### 6.6 The `arrival_done` interaction

The current logic uses `arrival_done` to gate re-triggering `settle()`. During auction:

- `arrival_done` should be set to True at auction *start*, not end
- This prevents the auto-settle from firing again during the auction
- If the player presses `B` during the auction, `handle_auction` catches it and ignores it
- When the auction closes and calls `settle_supplies_and_wages()`, that function checks `arrival_done` and returns early if already True

Or, simpler: add `auction_active` as a second gate:

```python
if not self.arrival_done and self.dock_t > 3.0 and not self.auction_active:
    self.settle()
```

This way `arrival_done` stays False until the auction completes, but the guard prevents double-triggering.

### 6.7 Radio F3 interaction

`F3` currently gives a market report — "buyer index x0.95". During auction, F3 should be ignored (or re-scoped to show the current session total).

Recommendation: ignore F3 during auction.

### 6.8 Concurrent events

The world is paused, so:

- Weather cannot change mid-auction
- Crew cannot run off
- Radio calls cannot arrive
- Fish don't rot

This is the correct behaviour for a modal. If the player leaves the auction open for 10 real minutes, nothing decays.

But — if the player abandons the auction (closes the window via the OS), the state is lost. Since there's no save/load, this is already true of the game. Note it but don't try to fix it.

---

## 7. Edge cases

### 7.1 Empty hold at quay

`settle()` opens nothing; goes straight to `settle_supplies_and_wages()`. No auction modal appears. This preserves the fast "dock and refuel" flow.

### 7.2 `B` pressed while offshore

`settle(manual=True)` → `start_auction(manual=True)` → checks `self.docked()` → says "We're not alongside" → returns. Same as current behavior.

### 7.3 `B` pressed with empty hold at quay

`settle(manual=True)` → `start_auction(manual=True)` → hold is empty → says "Nothing in the hold to sell" → returns. Same as current behavior.

### 7.4 Fish kept between sessions

Every kept fish gets `kept_session_count += 1`. At the start of the next auction (or the next `settle` call), apply:

```python
for c in self.hold:
    if c.kept_session_count > 0:
        c.quality -= 0.05 * c.kept_session_count
        c.quality = max(c.quality, 0.0)
```

Or use `Catch.tick` with a simulated 6-hour period at ambient ice-hold temperature. The exact mechanism is up to implementation; the *outcome* is that keeping a fish for a week makes it worse.

### 7.5 Buyer pool empty

If no buyer bids on a fish (very rare — the harbour trader always bids at least 0.85×), the only available action is KEEP. Show a message in the buyer column: "No offers for this fish."

### 7.6 Wholesaler's lot requirement

The Wholesaler only bids when the session has 3+ of the same species. This is checked per-fish, not per-session — so a Yellowfin in a session with 2 Yellowfin and 5 Bigeye does not get a Wholesaler bid (the Wholesaler wants 3+ *Yellowfin specifically*). Implemented as `bulk_min_species_count` check on the current fish's species across `self.hold`.

### 7.7 Multiple buyers want the same single fish

If two buyers both want to be the sole buyer of a rare fish (Sashimi Chef at most 1/session, Collector at most 1/session), there's no conflict — they both bid, player picks one, and only that one marks `fish_bought_this_session += 1`.

But if the Sashimi Chef is already at `fish_bought_this_session = 1`, he doesn't bid on the next fish. The player sees fewer buyers on later fish, which is realistic (the chef filled his quota and went home).

### 7.8 Player closes the window during auction

State lost. Note as known limitation. Could add an autosave-on-auction-open hook later.

### 7.9 Player presses ESC at the end of the auction

The last fish sold, the CLOSING state runs, and the world resumes. ESC during CLOSING is ignored.

### 7.10 Auction during a man-overboard alarm

`self.crew.alarm_target is not None` → the ship is likely not docked (a MOB usually happens at sea). But if somehow the ship is docked and a MOB alarm is active, `docked()` returns False (it checks `alarm_target`). So `settle()` won't auto-trigger. If the player pressed `B` and the alarm fires mid-auction:

- Force-cancel the auction
- Any unsold fish stay in hold
- Session total is added to cash
- Supplies/wages still happen
- Return to normal

The crew-log line makes the interruption clear: *"The auctioneer stops the bidding — there's a man in the water!"*

### 7.11 Selling during a tow

`tow_in()` puts the ship back at the berth with `arrival_done = False`. If the player then waits at the quay, `settle()` triggers 3 seconds later → auction opens → player sells. Same as if they'd docked normally.

---

## 8. Tuning

### 8.1 Buyer personality values

Start with these as v1 defaults:

| Buyer | Sashimi | A | B | C | Scrap | Species pref |
|---|---|---|---|---|---|---|
| Sashimi Chef | 2.2× | 1.5× | 1.0× | 0.5× | 0.3× | swordfish 1.3, bigeye 1.2, yellowfin 1.1, albacore 1.0, shark 0.4 |
| Canner | 1.0× | 1.0× | 1.0× | 1.0× | 1.0× | albacore 1.4, yellowfin 1.0, bigeye 0.9, swordfish 0.7, shark 1.2 |
| Wholesaler | 1.1× | 1.1× | 1.1× | 1.1× | 1.1× | albacore 1.2, yellowfin 1.2, bigeye 1.0, swordfish 0.8, shark 1.0 |
| Harbour Trader | 0.85× | 0.85× | 0.85× | 0.85× | 0.85× | all 1.0 |
| Collector | — | 1.8× (sword) | — | — | — | swordfish only, quality > 0.72 |

Also: Sashimi Chef multiplies by 1.2× if `bled and gutted`, and 0.6× if either is missing (he only wants clean kills).

Canner multiplies by 0.6× if not bled or gutted.

Wholesaler requires `same_species_count >= 3` in the session.

Collector requires the trigger condition (specific fish + quality threshold) and buys only one per session.

The market multiplier (`self.market`) applies on top of all of these.

### 8.2 Appearance probabilities

Per session:

- Sashimi Chef: always appears if any fish is grade A or better; 40% otherwise
- Canner: 90%
- Wholesaler: always appears if `self.hold` has 3+ of the same species; otherwise 0%
- Harbour Trader: always
- Collector: 15% chance, and only if the triggering fish exists

If fewer than 3 buyers appear, pad with Harbour Trader copies (e.g. "Harbour Trader A", "Harbour Trader B" with slightly different multipliers) to keep the choice interesting.

### 8.3 Market multiplier interaction

The existing `self.market` (0.7–1.3) multiplies all offers. This gives sessions a "market up" or "market down" feel. Consider:

- Sashimi Chef's multiplier is more sensitive to market (uses `market^1.2`)
- Canner's is less sensitive (uses `market^0.8`)
- The market drifts slower during a bad streak and faster during a good one

This is a tuning layer, not a design choice. Ship v1 with the market applied uniformly and adjust if playtest demands.

### 8.4 Quality decay between sessions

`0.05 per kept session` — this is 5% quality loss per quay visit for a kept fish. So a Sashimi (0.9) kept for one session becomes an A (0.85). Kept for two: 0.80, still A. Kept for three: 0.75, still A. Four: 0.70, B. Five: 0.65, B. Nine: 0.45, C. Twelve: 0.30, still C. Fifteen: 0.15, Scrap.

That's a slow decay — a fish can be held for 2–3 sessions without dramatic loss, but holding for 10+ destroys it. Feels right for a fish on ice in 1962 (no vacuum sealing).

### 8.5 Bid pacing (if Model B)

- Session opens: 2.0 s "buyers arriving" animation
- Per fish, per tick: 0.5 s
- Max ticks per fish: 8 (so a single fish can take up to 4 s to settle)
- Player can act any time during the ticks
- After the last tick, if the top buyer hasn't been accepted, auto-advance to "top bid locked" and require SELL or KEEP

This gives a session of 7 fish a 20–30 second minimum, 60 second maximum. Enough to feel like a session, not so long the player gets bored.

---

## 9. Testing checklist

Before shipping the auction, verify each of these works:

**Functional:**
- [ ] Docking with an empty hold → no auction, straight to supplies
- [ ] Docking with one fish → auction opens with 1/1, one buyer per archetype present
- [ ] Docking with 7 mixed fish → auction opens with 1/7, cycling through all
- [ ] SELL NOW on each fish → cash ticks up by the offer amount, fish leaves hold
- [ ] KEEP on a fish → fish stays in hold, session total doesn't include it
- [ ] ACCEPT ALL → every fish sells to its best offer in one pass
- [ ] CLOSE (ESC) → confirmation, then session ends, kept fish stay, sold fish credited
- [ ] After auction → ice/fuel/gaff/bait topped up, crew paid, HUD shows new cash
- [ ] Press `B` offshore → "not alongside"
- [ ] Press `B` with empty hold at quay → "nothing in the hold"
- [ ] Press `B` after docking (before auto-trigger) → opens auction, doesn't double-settle

**Edge cases:**
- [ ] Keep a fish for 3 sessions, verify quality drops 15%
- [ ] Keep a fish, close auction early, verify it's still in hold with `kept_session_count = 1`
- [ ] Sell everything, verify `arrival_done` is True and no further settle fires
- [ ] Force a MOB during auction → verify auto-cancel and clean state
- [ ] Window resize during auction → verify layout recalculates
- [ ] Toggle fullscreen during auction → same
- [ ] Time passes in real life for 10 min with auction open → fish quality unchanged
- [ ] Market index is captured at session start, mid-session `self.market` changes don't retroactively adjust offers

**Visual:**
- [ ] Fish drawings render correctly at large scale
- [ ] Quality bar fills to the correct proportion
- [ ] Grade colour coding is correct for all 5 grades
- [ ] Buyer cards show the correct offers
- [ ] Offers are ordered highest to lowest
- [ ] Session total updates live
- [ ] Confirmation dialog on ESC doesn't leak into the game underneath
- [ ] Auction modal is centred on any window size

**Balance:**
- [ ] A good trip (5 sashimi fish) fetches roughly 2× a mediocre trip (5 A fish)
- [ ] Keeping a fish for later is sometimes but not always worth it
- [ ] The Chef, Canner, and Trader give visibly different offers on the same fish
- [ ] The Wholesaler only appears when there are 3+ of a species

---

## 10. Future extensions

Once the auction UI is stable and the player enjoys it, these extensions are natural:

**10.1 Radio pre-auction (F3 becomes valuable)**

While offshore, `F3` could preview the market: "At current prices, your 3 sashimi yellowfin would fetch ~17,000." This gives the player a reason to radio before deciding whether to head home. It's also a hook for a future "sell while at sea via radio, but at a discount" mechanic.

**10.2 Auction house location**

The auction is currently a modal — the player is at the quay and the auction happens. A more visual version could show the harbour market building in the background during the auction (the existing `_building` draw code has a `"market"` kind with a saw-tooth roof and loading canopy). This would tie the auction to its physical place.

**10.3 Buyer relationships**

Track buyer satisfaction over sessions. A chef who paid for a premium fish and got one is happier; a chef who paid for A and got B is grumpier. Happy buyers bid higher and appear more often. Long-term relationship-building — Phase 7+ material.

**10.4 Auctioneer voice**

"Four thousand yen — do I hear four-five? Four-five for this fine yellowfin — sold to the gentleman from the Ginza!" Crew-log lines during a session would sell the *drama* of the auction. Cheap to add once the session state machine exists.

**10.5 Seasonality**

Tuna prices rise in winter, fall in summer. Prices rise when the fleet has a bad year. Seaonal cycles give the long-term game texture and reward keeping a logbook of when prices peak.

**10.6 Buyer acceptance animation**

A small animation of a handshake or a numbered ticket being handed over when a fish sells. Ten seconds of art, twenty seconds of polish. Worth it if the game's visual identity has settled.

---

## Summary

The current system is a single `settle()` call that sells everything for one aggregate price and refills supplies in one pass. It works, but it hides the economic decisions from the player.

The auction UI turns that into a per-fish trading session with three to four buyers who value different things. Player agency expands from "nothing" to "sell now vs. keep for later, and which buyer." The plumbing is a modest refactor — split `settle()` in two, add a modal state machine, and pause the world while the auction runs.

Five buyer archetypes (Chef, Canner, Wholesaler, Harbour Trader, Collector) give the fish personality. Session summaries, `ACCEPT ALL`, and `CLOSE (ESC)` give the player control over the pacing. The world pause makes it feel like a real trading session, not an interruption.

Estimated scope: **~500–700 lines** across the new `AuctionSession` / `BuyerProfile` / `Buyer` / `FishLot` classes, the `_draw_auction()` UI, the `settle()` refactor, and the input routing. Should fit in two focused sessions — one for the data model and state machine, one for the UI and drawing.

The design keeps everything the current code already does: fish quality flows through unchanged, the market multiplier still applies, crew wages and supplies still happen. It just inserts a player-facing decision where there was previously a single log line. That's the whole point.
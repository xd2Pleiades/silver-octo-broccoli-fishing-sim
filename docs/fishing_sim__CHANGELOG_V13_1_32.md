# Fishing Simulator v13.1.32

## Cohesion pass: Phases 3 and 4

Audit of v13.1.31 by running the real crew AI headlessly. Most of Phases 3-6 was already in place; this release fixes what
did not hang together and adds the one Phase 3 item that was still missing.

### Crew no longer pile into the engine room
- **Cause.** The veteran's "mentor" bonus made every idle deckhand pick him as a chat partner, and the veteran is usually the
  engineer, so the whole crew followed him below. Idle men below deck also stayed put forever. Within a minute four deckhands
  were standing in the engine room and the crowd shoved the engineer off his station (46 station flickers in 180 s, with
  repeated "No engineer below" warnings).
- **Fix.** Idle crew below deck (sleepers excepted) walk back up to the deck standby. Chat partners must be on the same level
  and awake, so nobody goes down to chat with the engineer or wakes a sleeper. Engine-watch flicker in the same scenario drops
  from 46 to 9 and the engine checks are attended again.

### Sleeping
- A berth is now better rest than the deck standby (fatigue 0.045/s, morale +0.008/s against 0.028 and 0.005).
- A shout is muffled below deck: sailors below hear a man-overboard call 1.2 s later, and a man asleep in his bunk 1.8 s later
  still. This is the cost of resting far from the rail described in the roadmap.

### Captain's orders (Phase 3)
- Right-click the **captain** to open his orders in the existing context menu (the title shows the trip status):
  - **Fish: 3-day trip**: the crew set and haul as often as they can for three game days (1,800 s), keeping the catch in the
    ice hold, then come home, dock, and sell. The trip heads home early, and says why, when fuel runs low, bait runs out, or
    the ice is nearly gone with fish aboard.
  - **Return to port**: stops fishing and autodocks. If the line is still out the crew haul it first, then go home. If the line
    is out under manual control the captain tells you to haul it first.
  - Assign: rest, and Select captain, as before.
- Standing down with `L`, a cancelled dock, or a fuel stand-down also ends the trip. The operations HUD shows `TRIP 1.4/3d`.
- Plain `L` auto-fishing is unchanged (it still returns after each catch).

### Tests
- New `test_v13_1_32_cohesion.py` (15 behavioural tests): crew leave the engine room, chat partners, engine-watch stability,
  sleeping and the captain's handover, the captain's menu, trip logic and reasons to head home, return to port in each state,
  and a full end-to-end trip (set, haul, set, haul, home).
- Fixed two tests that were failing in v13.1.31: the tow test expected an instant position reset that the physical tow no
  longer does (it now checks the reset on arrival), and `cache/errors/README.md` is now shipped.
- Full suite: 424 tests pass.

### Known notes (not changed)
- Opening conditions are rough (sea 0.55). In an 8-seed test about 5 runs lose a man overboard in the first four minutes, the
  same with and without this release. That is a balance question, not a regression.
- A fresh ship carries about 40 units of bait and a set uses 24, so a 3-day trip normally ends early for lack of bait unless
  the crew load more. The captain says so when it happens.
- Pygame was run with a dummy video driver; a live graphical playtest is still needed.

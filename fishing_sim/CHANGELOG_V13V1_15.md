# V13V1-15 — Marine Gear Collisions, Rescue Routing, and Reliable Fishing Spots

## Implemented

- Added headless marine collision geometry for circle/segment contact, circle/polygon projection, and rescue routes around the expanded ship-hull envelope.
- Longline particles and buoys now resolve against land, the reef, the ship hull, and a deployed rescue boat. Rope segments are swept between particles after the rope constraints so a long segment cannot skip across a narrow obstacle in a single frame. Surface buoys and rope near the surface collide with the rescue boat; deeply submerged hooks do not become artificial surface walls.
- The rescue boat now has collision resolution against shore, reef, hull, and surface longline gear/buoys. Outbound and return legs share a route-around-hull planner and contact slide/replan behavior instead of moving in a straight line through the vessel.
- In rough seas, the small launch remains prohibited. The ship approaches the swimmer at dead slow, checks candidate headings against land/reef, then presents the starboard rail while stopped for a safer lifeline recovery.
- Rescue-boat occupants have an explicit face/nose mark pointing toward local starboard (+y), so their direction remains readable while the boat rotates with world/camera orientation.
- Fishing hotspots spawn after a short initial delay. Once the vessel is offshore, spawning first searches validated water around the current fishing area, so cues can appear in reachable waters. Global offshore search and a deterministic fallback around the normal fishing grounds remain available. Successful spawns now retry after 45–75 game seconds; failed spawns retry after 6–12 seconds; the active-school cap remains four.
- Kept the hook minimap removed. The compact depth-profile HUD remains beneath the cash/date cards, with its existing profile origin at y=82.
- Updated the roadmap and preserved the full Markdown documentation set in the release archive.

## Verification

Run from the project directory:

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

Headless tests cover circle contact, polygon escape, rescue routes around the hull envelope, line-particle/segment collision hooks, rescue-boat contacts and routing, starboard-facing rendering contract, hotspot spawn retries/current-area seeding, and the no-minimap/depth-HUD layout. The full suite passes and Python compilation passes.

## Graphical-test limitation

Pygame is unavailable in the build environment, so the project has not been live-playtested here. In particular, visually verify rope stability under constraint solving, dinghy clearance around the bow/stern in different headings, starboard face marks at normal zoom, and depth-panel overlap on resized windows.

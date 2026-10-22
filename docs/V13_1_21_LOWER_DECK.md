# v13.1.21 — Lower Deck Layout & Bunk Sleeping

> **Historical note:** The continuous-centre-aisle plan described here was superseded in the v13.2.13 ship-overhaul merge. The merged working build has five separated spaces and real bulkhead walls; see [Ship Overhaul Integration](SHIP_OVERHAUL_MERGE_V13_2_13.md).


## Layout

The bow points in the positive ship-length direction (`+x`). The below-deck work zones now extend from the aft stores near `x = -0.455 L` through the ice hold and engine room to the crew cabin ending near `x = +0.375 L`, covering just over 80% of the hull's normalized length inside the tapered ends. The lower floor itself is the inboard hull footprint.

A continuous centre aisle runs from aft stores through ice hold and engine room to the forward cabin. Room rectangles are for drawing/work semantics; they are not sealed navigation islands. Engine casing and six bunks are the actual walking solids.

## Berths

There are six bunks in paired port/starboard rows. Each is approximately `0.075 L × 0.115 B`, or around 88 × 32 world units at the standard 1100 × 280 ship scale. Each has a unique stand point in the aisle, so two people don't reserve the exact same approach coordinate.

Rest duty walks to the stand point. Once reached, the sailor is placed on the mattress and rendered horizontally. In that state the sailor does not move, does not collide against their own bed, and is ignored by crew-separation and local path avoidance. Switching to a different task wakes the sailor at their reserved aisle stand before normal movement resumes.

## Path-failure behavior

A* no longer invents a direct target path when no route exists. The sailor slows and retries planning from the current position. This prevents unreachable destinations from producing repeated collision pushes against engine casing or bunks. The main remaining validation is graphical: check routes from both ladders to the engineer station, ice hold and each bunk on a running desktop build.

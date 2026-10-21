# v13.1.25 implementation notes

This patch improves the physical interaction between the longline and the starboard-quarter hauler, makes automatic fish stowage self-contained, fixes a bow-end navigation deadlock, supports local storm maneuvering, and adds location-aware right-click actions.

## Hauling alignment
The drum/hauler pickup is at local deck point `(-0.32 L, +0.5 B)`. During the final pickup, the helm gradually aligns the aft starboard quarter with the line instead of forcing the bow to point at the buoy. Current, inertia, helm availability, and the existing rudder response remain active.

## Fouled buoy or mainline
A floating marker or a non-leading mainline span close to the quarter roller accumulates exposure. It can trigger a timed haul pause and small line-condition loss. This can clear naturally after the short interval or be cleared immediately by a deckhand stationed aft (M or the context menu).

## Hatch workflow
Fish-dressing hands open the ice-hold hatch at the landing they reach, stow the fish, and close it again when no one is on the ladder. The hold-ladder link is mapped to the hatch physically aligned with it (hold_1), fixing the previous mismatch. Context-menu hatch orders send an available deckhand to the correct same-level interaction point and perform the action once in reach.

## Storm plotting
Storm, fog, darkness, and rain reduce the range of a short ocean steer-to instead of making all local maneuvering impossible. A short steer-to is available during manual soaking/hauling, but a persistent A→B leg still waits until the fishing line is secured; auto-fishing keeps helm priority. The chart remains appropriate for longer routes. When a leg or quick target is reached, the waypoints and stale route origin are discarded.

## Bow navigation
The navigation grid can resolve a requested point that is unsafe or outside the sailor’s connected walkable component to the nearest safe endpoint in the starting component. Sailors persist that resolved endpoint and test arrival against it, instead of continuing to chase an unreachable coordinate forever. The original hull clearance remains unchanged, and path smoothing still checks obstacle clearance.

## Context menu gestures
- Right-click a sailor: select or change duty.
- Right-click a hatch: queue open/close for the selected sailor.
- Right-click the hauler/roller: assign hauling work or clear gear fouling.
- Right-click a visible buoy/line point: inspect the gear, start hauling during soak, or clear a snag.
- Right-click empty water: the existing quick steer-to order.
- Right-click empty walkable deck: open the DECK ORDER menu for moving a sailor, assigning hauling/setting work, or assigning engine watch. The sea remains available for short right-click steer-to orders.

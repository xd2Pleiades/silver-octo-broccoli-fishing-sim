# Fishing Simulator 12v13

## Changes
- Muster is now a true ship-wide order: available aboard crew, including captain/station keepers, leave stations and navigate to deck muster positions.
- Fishing tension and gaff UI are pinned to the top of the screen and can be hidden/restored with **F6**. The separate controls overlay remains on **F5**.
- **SPACE** is now the manual tension-brake input and gaff/heave input; Z/X remain fine tension adjustments.
- Added engine-room bilge flooding from sea conditions and deck water. Bucket-equipped crew can form a deck bucket chain when the deck is very wet, and bail engine-room water when bilge flooding rises.
- Slips at open rails can now carry a sailor overboard into the swimming state instead of always ending in an edge collision.

## Hotfix — 12v13.1
- Fixed a storm-triggered `NameError` in `Sailor._move()`: the open-rail slip check now uses the sailor's game reference, and a slip uses one fall transition rather than reporting man-overboard twice.
- Replaced the timer-only deck bucket effect with an assigned bucket-line task. Eligible deckhands pathfind to distinct stern positions; the sailors show bucket props and face over the stern.
- Deck water is removed only after at least two assigned hands physically reach the bucket-line positions. Water reduction is repeated while the line is operating, rather than being applied to any two sailors who happen to be aboard.
- Engine-room bilge bailing remains separate and now treats buckets as reusable equipment.
- Added regression checks for the undefined game reference and the real bucket-task/pathfinding workflow.

## Verification / limitations
- Automated source-contract tests and Python compilation are included in this release workflow.
- Bucket crew now walk to visible bucket-line positions and perform the task; water transfer itself remains a timed gameplay simulation, not a fluid-particle simulation. Engine-room flooding is separate from deck flooding.
- Full Pygame graphical playtest remains necessary on a machine with Pygame installed.

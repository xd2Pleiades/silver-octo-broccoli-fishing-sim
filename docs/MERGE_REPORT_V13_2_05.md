# Merge Report — v13.2.05

## Inputs

- Current project: v13.2.04 (contains the shared Coast Guard/tow identity adapter, traffic foundation, radio UI and weather grid).
- User-supplied WIP: `fishing_sim_v13_2_04_wip.zip` (based on v13.2.03 and containing hull-wave/sea/flooding work).

## Strategy

The WIP did not replace the newer project wholesale. `fishing_sim/core/game.py` was merged three-way using the common v13.2.03 source, the current v13.2.04 file and the WIP file, retaining disjoint changes from both branches. The resulting source contained no merge-conflict markers and compiled. WIP-only `sea_interaction.py` was added and `sea_foam.py` was merged from the WIP. Existing M8 traffic/tow identity files were preserved from v13.2.04.

The new M9 distress dispatcher and UI decisions were then built on the merged source. The WIP's older copies of README/roadmap/controls/plan were not blindly overlaid; the newer v13.2.04 documentation was updated to reflect both the merged WIP features and the M9 implementation. This avoids rolling status/version notes backward.

## Merge outcomes

- Preserved one shared Coast Guard `vessel_id` across tow, traffic, chart and radio systems.
- Added wave/hull interaction and flooding simulation from the WIP.
- Added coarse/non-rendered AI MAYDAY events and player assist/ignore decisions.
- Added bounded rescue-contact promotion and distress snapshot fields.
- Updated version to v13.2.05 and refreshed controls, README, roadmap, changelog and implementation status.
- Kept all Markdown files under `/docs`, using distinct names for historical variants.

## Validation boundaries

- Compile: passed.
- Focused regression suite: 133 tests passed.
- Pygame visual playtest: unavailable in this environment.
- Physical assist-route/rescue outcome and global career-save integration remain future work.
